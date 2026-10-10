"""Independent tiny arithmetic and explicit bounded-model integration."""
from __future__ import annotations

import asyncio
import copy
from dataclasses import replace
from fractions import Fraction
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from bj import common_shoe, joint_split, record, replay
from bj._enumeration import EnumerationLimitExceeded, scope, state
from bj.caches import clear_all_caches
from bj.core import RANKS, STANDARD
from test_joint_split import permutation_oracle
from test_ev_physical_reference import physical_reference


def counts(cards):
    return tuple(cards.count(rank) for rank in RANKS)


def rules(**changes):
    return replace(STANDARD, max_hands=2, **changes)


@pytest.fixture(autouse=True)
def cold_root_caches():
    clear_all_caches()
    yield
    clear_all_caches()


@pytest.mark.parametrize('pair,up,unseen,das,s17', [
    ('8', '6', ('7', '7', '8', '9', 'T', 'T'), False, True),
    ('8', 'T', ('7', '7', '8', '9', 'T', 'T'), True, True),
    ('A', 'A', ('7', '8', '9', 'T', 'T'), False, True),
    ('A', 'T', ('A', '7', '8', '9', 'T'), True, True),
    ('A', '6', ('A', '7', '8', '9', 'T', 'T'), False, False),
])
def test_explicit_record_matches_independent_physical_rounds(pair, up, unseen, das, s17):
    saved = record.common_shoe_record((pair, pair), up, rules(das=das, s17=s17),
                                      shoe=counts(unseen))
    expected = permutation_oracle(pair, up, unseen, das=das, s17=s17)
    assert saved['decision']['evs']['P'] == pytest.approx(float(expected), rel=0, abs=1e-12)
    root = physical_reference((pair, pair), up, unseen, s17=s17)
    for action in ('S', 'H', 'D'):
        assert saved['decision']['evs'][action] == pytest.approx(
            float(root[action]), rel=0, abs=1e-12)
    assert saved['schema']['version'] == 3
    assert saved['state']['shoe']['counts'] == list(counts(unseen))
    assert saved['model']['split'] == common_shoe.SPLIT_MODEL
    assert replay.replay_json(json.dumps(saved))['status'] == 'agreement'


def test_hidden_hole_is_never_revealed_to_split_policy():
    unseen = ('7', '7', '8', '9', 'T', 'T', 'T')
    lawful = permutation_oracle('5', 'T', unseen, das=True)
    illegal = permutation_oracle('5', 'T', unseen, das=True, reveal_hole=True)
    assert lawful == Fraction(-9, 7)
    assert illegal == Fraction(-107, 84)
    saved = record.common_shoe_record(('5', '5'), 'T', rules(), shoe=counts(unseen))
    assert saved['decision']['evs']['P'] == pytest.approx(float(lawful), rel=0, abs=1e-12)
    assert saved['decision']['evs']['P'] < float(illegal)


@pytest.mark.parametrize('das,expected', [(False, 2), (True, 4)])
def test_seven_eights_cover_all_branches_and_combined_wagers(das, expected):
    unseen = ('8',) * 7
    # Dealer 7+8 must take another 8 and bust. A split two can reach 18
    # with two draws, or double10 to18. Seven cards also cover first-hand
    # bust, a surviving second hand and the required shared dealer draw.
    assert permutation_oracle('2', '7', unseen, das=das) == Fraction(expected)
    saved = record.common_shoe_record(('2', '2'), '7', rules(das=das), shoe=counts(unseen))
    assert saved['decision']['evs']['P'] == expected


@pytest.mark.parametrize('das', [False, True])
def test_split_aces_close_after_one_card_without_natural_premium(das):
    saved = record.common_shoe_record(('A', 'A'), '7', rules(das=das, blackjack_payout=2.5),
                                      shoe=counts(('T',) * 4))
    assert permutation_oracle('A', '7', ('T',) * 4, das=das) == 2
    assert saved['decision']['evs']['P'] == 2
    assert saved['model']['split_aces'] == 'one_card_no_double_no_natural_premium'


@pytest.mark.parametrize('double,pair', [(True, True), (False, True),
                                      (True, False), (False, False)])
def test_current_controls_preserve_continuation_and_explicit_record(double, pair):
    unseen = ('A',) + ('T',) * 5
    saved = record.common_shoe_record(('T', 'T'), '7', rules(), shoe=counts(unseen),
                                      can_double=double, can_split=pair)
    values = saved['decision']['evs']
    assert set(values) == {'S', 'H'} | ({'D'} if double else set()) | ({'P'} if pair else set())
    assert values['S'] == 1
    assert values['H'] == pytest.approx(float(Fraction(-2, 3)), rel=0, abs=1e-12)
    if double:
        assert values['D'] == pytest.approx(float(Fraction(-4, 3)), rel=0, abs=1e-12)
    if pair:
        assert values['P'] == 2
        assert saved['decision']['action'] == 'P'
        assert saved['decision']['margin'] == 1
    assert saved['state']['action_controls'] == {'can_double': double, 'can_split': pair}
    assert saved['schema']['version'] == 3


def test_rank_adapter_is_asymmetric_and_reference_agreement_is_regression_only():
    unseen = counts(('A', '7', '8', '9', 'T', 'T'))
    adapted = common_shoe.reference_counts(unseen)
    assert dict(zip(joint_split.RANKS, adapted)) == dict(zip(RANKS, unseen))
    assert adapted != unseen
    saved = record.common_shoe_record(('A', 'A'), '6', rules(s17=False), shoe=unseen)
    # The same reference arithmetic is intentionally reused. This assertion
    # checks the adapter/rule integration, not independent mathematical truth.
    expected = joint_split.joint_split_value('A', '6', adapted, stand_soft_17=False)
    assert saved['decision']['evs']['P'] == expected.value
    assert expected.maximum_probability_mass_error <= 1e-12


@pytest.mark.parametrize('pair,up,unseen', [
    ('A', '2', ('2', '3', '4')), ('8', 'T', ('7', '8', '9', 'T')),
    ('2', '7', ('8',) * 6),
])
def test_any_exhausted_branch_refuses_without_partial_record(pair, up, unseen):
    with pytest.raises(ValueError):
        record.common_shoe_record((pair, pair), up, rules(), shoe=counts(unseen))


def test_whole_request_budget_refuses_root_before_joint_and_remains_inactive_for_legacy():
    unseen = counts(('A',) + ('T',) * 5)
    with patch.object(common_shoe.joint_split, 'joint_split_value') as joint:
        with pytest.raises(EnumerationLimitExceeded) as error:
            record.common_shoe_record(('T', 'T'), '7', rules(), shoe=unseen, max_states=1)
    assert not joint.called
    assert error.value.work == {'limit': 1, 'states': 1, 'attempted_states': 2,
                                'state_counts': {'root_distribution': 1}}
    assert record.decision_record(('T', 'T'), '7', rules(), shoe=unseen)['schema']['version'] == 1


def test_single_budget_includes_root_and_all_joint_state_families():
    unseen = counts(('7', '7', '8', '9', 'T', 'T', 'T'))
    saved, work = record._common_shoe_record(('5', '5'), 'T', rules(), shoe=unseen)
    assert saved['model']['enumeration_state_limit'] == work['limit'] == 100000
    assert work['states'] == work['attempted_states'] == sum(work['state_counts'].values())
    assert set(work['state_counts']) == {
        'root_draw', 'root_hit', 'root_double', 'root_distribution', 'root_dealer',
        'joint_draw', 'joint_play', 'joint_settle', 'joint_dealer'}
    cap = sum(value for key, value in work['state_counts'].items() if key.startswith('root_'))
    clear_all_caches()
    with pytest.raises(EnumerationLimitExceeded) as error:
        record.common_shoe_record(('5', '5'), 'T', rules(), shoe=unseen, max_states=cap)
    assert error.value.work['states'] == cap
    assert error.value.work['attempted_states'] == cap + 1
    assert all(key.startswith('root_') for key in error.value.work['state_counts'])


def test_context_tokens_restore_and_concurrent_tasks_do_not_share_caps():
    with scope(2) as outer:
        state('root_draw')
        with scope(1) as inner:
            state('root_hit')
        state('root_double')
    assert outer.snapshot()['states'] == 2
    assert inner.snapshot()['states'] == 1
    state('root_hit')  # No inherited budget after scope exit.

    async def caller(limit):
        with scope(limit) as counter:
            for _ in range(limit):
                state('root_hit')
                await asyncio.sleep(0)
            return counter.snapshot()

    async def together():
        return await asyncio.gather(caller(1), caller(3))

    assert [item['states'] for item in asyncio.run(together())] == [1, 3]


@pytest.mark.parametrize('changes', [
    {'cards': ('5', '6')}, {'shoe': None}, {'shoe': counts(('T',) * 21)},
    {'rules': replace(STANDARD, max_hands=3)}, {'rules': rules(resplit_aces=True)},
    {'rules': rules(hit_split_aces=True)}, {'max_states': 0}, {'max_states': 100001},
    {'max_states': True}, {'can_double': 1}, {'can_split': 0},
])
def test_unmodeled_or_malformed_contract_refuses_before_pricing(changes):
    kwargs = dict(cards=('T', 'T'), dealer_up='7', rules=rules(),
                  shoe=counts(('A',) + ('T',) * 5))
    kwargs.update(changes)
    with patch.object(common_shoe.ev, 'best_action', side_effect=AssertionError('must not price')):
        with pytest.raises(ValueError):
            record.common_shoe_record(**kwargs)


def test_replay_selects_recorded_model_and_never_trusts_saved_values():
    saved = record.common_shoe_record(('5', '5'), 'T', rules(),
                                      shoe=counts(('7', '7', '8', '9', 'T', 'T', 'T')))
    altered = copy.deepcopy(saved)
    altered['decision']['evs']['P'] = 7
    with patch.object(record, 'decision_record', side_effect=AssertionError('legacy route')):
        result = replay.replay_json(json.dumps(altered))
    assert result['status'] == 'differences'
    assert result['recomputed']['evs']['P'] == saved['decision']['evs']['P']
    refused = copy.deepcopy(saved)
    refused['model']['enumeration_state_limit'] = 1
    clear_all_caches()
    result = replay.replay_json(json.dumps(refused))
    assert result['status'] == 'resource_limited'
    assert result['recomputed'] is None
    assert result['work']['states'] == 1
    unknown = copy.deepcopy(saved)
    unknown['model']['split'] = 'unrecognized_common_model'
    with patch.object(record, 'common_shoe_record', side_effect=AssertionError('must not price')):
        assert replay.replay_json(json.dumps(unknown))['status'] == 'unsupported_record'


def test_legacy_fixture_routes_legacy_without_common_pricing():
    fixture = Path(__file__).parent / 'fixtures/saved-decision-v1-7a38141.json'
    with patch.object(record, 'common_shoe_record', side_effect=AssertionError('common route')):
        assert replay.replay_json(fixture.read_bytes())['status'] == 'agreement'
