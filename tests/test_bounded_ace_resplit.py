"""One-card ace semantics, complete root controls and bounded refusal."""
from __future__ import annotations

import math
from dataclasses import replace
from unittest.mock import patch

import pytest

from bj import bounded_ace_resplit, ev, joint_ace_resplit, record
from bj._enumeration import EnumerationLimitExceeded, scope
from bj.caches import clear_all_caches
from bj.core import RANKS, STANDARD
from bj.joint_split import ReferenceLimitExceeded, UnsupportedShoeError


def counts(cards):
    return tuple(cards.count(rank) for rank in RANKS)


def rules(**changes):
    return replace(STANDARD, **{'max_hands': 3, 'resplit_aces': True, **changes})


def joint_counts(cards):
    return tuple(cards.count(rank) for rank in joint_ace_resplit.RANKS)


@pytest.fixture(autouse=True)
def cold_caches():
    clear_all_caches()
    yield
    clear_all_caches()


@pytest.mark.parametrize('double,split', [(True, True), (True, False),
                                        (False, True), (False, False)])
def test_complete_original_actions_and_current_controls(double, split):
    retained = counts(('T',) * 4)
    saved, work = record._bounded_ace_resplit_record(
        ('A', 'A'), '7', rules(), shoe=retained, can_double=double, can_split=split)
    assert saved['schema']['version'] == 6
    assert saved['decision']['evs'] == (
        {'S': -1.0, 'H': -1.0} | ({'D': -2.0} if double else {}) |
        ({'P': 2.0} if split else {}))
    assert saved['decision']['action'] == ('P' if split else 'S')
    assert saved['state']['action_controls'] == {'can_double': double, 'can_split': split}
    assert saved['state']['shoe']['counts'] == list(retained)
    assert saved['model'] == bounded_ace_resplit.model_record('7', 100000)
    assert set(work['state_counts']) <= bounded_ace_resplit.FAMILIES
    assert work['states'] == work['attempted_states'] == sum(work['state_counts'].values())
    assert any(name.startswith('ace_resplit_') for name in work['state_counts']) is split


def test_split_twenty_one_has_no_natural_premium_and_das_does_not_add_child_double():
    retained = counts(('T',) * 4)
    for das in (False, True):
        saved = record.bounded_ace_resplit_record(('A', 'A'), '6', rules(das=das), shoe=retained)
        assert saved['decision']['evs'] == {'S': 1.0, 'H': 1.0, 'D': 2.0, 'P': 2.0}
        assert saved['decision']['action'] == 'D' and saved['decision']['margin'] == 0.0
        assert saved['rules']['das'] is das


def test_optional_resplit_uses_one_shared_slot_and_may_be_declined():
    increased = record.bounded_ace_resplit_record(
        ('A', 'A'), '7', rules(), shoe=counts(('A',) + ('T',) * 5))
    assert increased['decision']['evs']['P'] == pytest.approx(7 / 3, abs=1e-12, rel=0)
    declined = record.bounded_ace_resplit_record(
        ('A', 'A'), '7', rules(), shoe=counts(('A',) * 5))
    assert declined['decision']['evs'] == {'S': -1.0, 'H': -1.0, 'D': -2.0, 'P': -2.0}
    assert declined['decision']['action'] == 'S'


def test_concealed_information_manual_value_is_outside_the_player_maximum():
    saved = record.bounded_ace_resplit_record(
        ('A', 'A'), '7', rules(), shoe=counts(('A',) * 3 + ('T',) * 2))
    assert saved['decision']['evs']['P'] == pytest.approx(3 / 10, abs=1e-12, rel=0)
    assert saved['decision']['evs']['P'] != 0.5  # Known-hole policy is a different model.
    assert saved['model']['dealer_information'] == 'hidden_hole_post_peek'


def test_root_last_draw_and_retained_counts_match_existing_engine():
    retained = counts(('A',) * 3)
    accepted = ev.best_action(('A', 'A'), '7', shoe=retained, rules=rules(), can_split=False)
    saved = record.bounded_ace_resplit_record(
        ('A', 'A'), '7', rules(), shoe=retained, can_split=False)
    assert saved['decision']['evs'] == accepted[1] == {'S': -1.0, 'H': -1.0, 'D': -2.0}
    assert saved['state']['shoe']['counts'] == list(retained)
    assert saved['model']['player_last_draw'] == 'stand_then_require_dealer_settlement'


def test_raw_rank_order_does_not_apply_an_epsilon_or_use_received_key_order():
    assert bounded_ace_resplit.rank({'P': 2.0, 'D': 2.0, 'H': 1.0, 'S': 1.0}) == ('D', 0.0)
    assert bounded_ace_resplit.rank({'H': -1.0, 'S': -1.0}) == ('S', 0.0)
    higher = math.nextafter(2.0, math.inf)
    assert bounded_ace_resplit.rank({'D': 2.0, 'P': higher}) == ('P', higher - 2.0)


@pytest.mark.parametrize('changes', [
    {'max_hands': 2}, {'max_hands': 4}, {'resplit_aces': False}, {'hit_split_aces': True},
    {'peek': False}, {'surrender': True}, {'double_any_two': False},
    {'tens_are_pairs': False}, {'das': 1}, {'s17': 'yes'},
])
def test_unqualified_rules_refuse_before_root_pricing(changes):
    with patch.object(bounded_ace_resplit.ev, 'best_action', side_effect=AssertionError('pricing')):
        with pytest.raises(ValueError):
            record.bounded_ace_resplit_record(
                ('A', 'A'), '7', rules(**changes), shoe=counts(('T',) * 4))


@pytest.mark.parametrize('cards', [('8', '8'), ('A', 'T'), ('A', 'A', '2')])
def test_only_original_ace_pair_is_supported(cards):
    with pytest.raises(ValueError, match='initial A,A'):
        record.bounded_ace_resplit_record(cards, '7', rules(), shoe=counts(('T',) * 4))


@pytest.mark.parametrize('kwargs', [
    {'shoe': None}, {'shoe': counts(('T',) * 2)}, {'shoe': counts(('T',) * 21)},
    {'can_double': 1}, {'can_split': 0}, {'max_states': True}, {'max_states': 0},
    {'max_states': 100001},
])
def test_explicit_counts_current_controls_and_state_cap_are_strict(kwargs):
    with pytest.raises(ValueError):
        record.bounded_ace_resplit_record(
            ('A', 'A'), '7', rules(), **{'shoe': counts(('T',) * 4), **kwargs})


def test_whole_request_cap_and_direct_joint_scope_refuse_without_partial_value():
    with pytest.raises(EnumerationLimitExceeded) as caught:
        record.bounded_ace_resplit_record(
            ('A', 'A'), '7', rules(), shoe=counts(('T',) * 4), max_states=1)
    assert caught.value.work == {'limit': 1, 'states': 1, 'attempted_states': 2,
                                 'state_counts': {'root_distribution': 1}}
    with scope(1):
        with pytest.raises(EnumerationLimitExceeded):
            joint_ace_resplit.joint_ace_resplit_value('7', joint_counts(('T',) * 4))


@pytest.mark.parametrize('up,cards,message', [
    ('6', ('T',) * 3, 'dealer must draw'),
    ('7', ('A',) * 3, 'mandatory ace draw'),
])
def test_unavailable_offered_joint_branch_withholds_completed_root(up, cards, message):
    root = record.bounded_ace_resplit_record(
        ('A', 'A'), up, rules(), shoe=counts(cards), can_split=False)
    assert set(root['decision']['evs']) == {'S', 'H', 'D'}
    with pytest.raises(UnsupportedShoeError, match=message):
        record.bounded_ace_resplit_record(('A', 'A'), up, rules(), shoe=counts(cards))


def test_direct_joint_limits_completion_sample_and_detached_input():
    retained = list(joint_counts(('T',) * 4))
    original = retained.copy()
    result = joint_ace_resplit.joint_ace_resplit_value('7', retained)
    assert result.value == 2.0 and retained == original
    assert result.states == sum(value for _, value in result.state_counts)
    assert result.maximum_probability_mass_error <= 1e-12
    with pytest.raises(ReferenceLimitExceeded, match='state limit'):
        joint_ace_resplit.joint_ace_resplit_value('7', retained, max_states=1)
    with patch.object(joint_ace_resplit, 'perf_counter', side_effect=[0.0, 2.0]):
        with pytest.raises(ReferenceLimitExceeded, match='time limit'):
            joint_ace_resplit.joint_ace_resplit_value('7', retained, max_seconds=1)
    times = [0.0] * (result.states + 1) + [1.0]
    with patch.object(joint_ace_resplit, 'perf_counter', side_effect=times) as clock:
        finished = joint_ace_resplit.joint_ace_resplit_value('7', retained, max_seconds=1)
    assert finished.elapsed_seconds == 1.0 and clock.call_count == len(times)
    times[-1] = 1.001
    with patch.object(joint_ace_resplit, 'perf_counter', side_effect=times):
        with pytest.raises(ReferenceLimitExceeded, match='time limit'):
            joint_ace_resplit.joint_ace_resplit_value('7', retained, max_seconds=1)
