"""Model boundaries, whole-request work and preserved root continuation."""
from __future__ import annotations

from dataclasses import replace
from unittest.mock import patch

import pytest

from bj import bounded_resplit, ev, joint_resplit, record
from bj._enumeration import EnumerationLimitExceeded, FAMILIES, scope
from bj.caches import clear_all_caches
from bj.core import RANKS, STANDARD
from bj.joint_split import ReferenceLimitExceeded, UnsupportedShoeError


def counts(cards):
    return tuple(cards.count(rank) for rank in RANKS)


def rules(**changes):
    return replace(STANDARD, **{'max_hands': 3, **changes})


@pytest.fixture(autouse=True)
def cold_caches():
    clear_all_caches()
    yield
    clear_all_caches()


@pytest.mark.parametrize('double,split', [(True, True), (True, False),
                                        (False, True), (False, False)])
def test_complete_record_and_controls_are_current_only(double, split):
    saved, work = record._bounded_resplit_record(
        ('8', '8'), '6', rules(das=False), shoe=counts(('8',) * 8),
        can_double=double, can_split=split)
    assert saved['schema']['version'] == 5
    assert saved['state']['action_controls'] == {'can_double': double, 'can_split': split}
    assert saved['decision']['evs'] == (
        {'S': 1.0, 'H': -1.0} | ({'D': -2.0} if double else {}) |
        ({'P': 3.0} if split else {}))
    assert saved['decision']['action'] == ('P' if split else 'S')
    assert saved['state']['shoe']['counts'] == list(counts(('8',) * 8))
    assert saved['state']['shoe']['source'] == 'supplied_unseen'
    assert saved['model'] == bounded_resplit.model_record('6', 100000)
    assert set(work['state_counts']) <= bounded_resplit.FAMILIES
    assert work['states'] == work['attempted_states'] == sum(work['state_counts'].values())
    assert any(name.startswith('resplit_') for name in work['state_counts']) is split
    assert not any(name.startswith('resplit_') for name in FAMILIES)


def test_raw_ties_keep_declared_order_without_reusing_core_dictionary_order():
    assert bounded_resplit.rank({'P': 0.0, 'H': -1.0, 'D': -2.0, 'S': 0.0}) == ('S', 0.0)
    assert bounded_resplit.rank({'H': -1.0, 'S': -1.0}) == ('S', 0.0)
    saved = record.bounded_resplit_record(('T', 'T'), 'T', rules(), shoe=counts(('T',) * 8))
    assert saved['decision']['action'] == 'S'
    assert saved['decision']['margin'] == 0.0


def test_root_uses_retained_shoe_once_and_preserves_last_draw_convention():
    unseen = counts(('A', 'A', 'A', '7'))
    accepted = ev.best_action(('2', '2'), 'T', shoe=unseen, rules=rules(), can_split=False)
    saved = record.bounded_resplit_record(('2', '2'), 'T', rules(), shoe=unseen,
                                         can_split=False)
    assert saved['decision']['evs'] == accepted[1]
    assert saved['state']['shoe']['counts'] == list(unseen)
    assert saved['model']['player_last_draw'] == 'stand_then_require_dealer_settlement'
    original = list(unseen)
    record.bounded_resplit_record(('2', '2'), 'T', rules(), shoe=unseen, can_split=False)
    assert list(unseen) == original


@pytest.mark.parametrize('changes', [
    {'max_hands': 2}, {'max_hands': 4}, {'peek': False}, {'surrender': True},
    {'resplit_aces': True}, {'hit_split_aces': True}, {'double_any_two': False},
    {'tens_are_pairs': False}, {'das': 1}, {'s17': 'yes'},
])
def test_unqualified_rules_refuse_before_pricing(changes):
    with patch.object(bounded_resplit.ev, 'best_action', side_effect=AssertionError('pricing')):
        with pytest.raises(ValueError):
            record.bounded_resplit_record(('8', '8'), '6', rules(**changes),
                                           shoe=counts(('8',) * 8))


@pytest.mark.parametrize('cards', [('A', 'A'), ('8', '9'), ('8', '8', '2')])
def test_only_original_non_ace_pair_is_supported(cards):
    with pytest.raises(ValueError, match='initial non-ace'):
        record.bounded_resplit_record(cards, '6', rules(), shoe=counts(('8',) * 8))


@pytest.mark.parametrize('kwargs', [{'shoe': None}, {'can_double': 1}, {'can_split': 0},
                                   {'max_states': 0}, {'max_states': True},
                                   {'max_states': 100001}])
def test_explicit_counts_controls_and_state_cap_are_strict(kwargs):
    arguments = {'shoe': counts(('8',) * 8), **kwargs}
    with pytest.raises(ValueError):
        record.bounded_resplit_record(('8', '8'), '6', rules(), **arguments)


def test_whole_request_cap_refuses_before_second_uncached_body():
    with pytest.raises(EnumerationLimitExceeded) as caught:
        record.bounded_resplit_record(('8', '8'), '6', rules(),
                                       shoe=counts(('8',) * 8), max_states=1)
    assert caught.value.work['states'] == 1
    assert caught.value.work['attempted_states'] == 2
    assert caught.value.work['limit'] == 1


def test_scope_includes_root_and_new_joint_families_without_legacy_joint_names():
    saved, work = record._bounded_resplit_record(('T', 'T'), '9', rules(),
                                                 shoe=counts(('8', '8', '9', '9') + ('T',) * 4))
    assert saved['decision']['action'] == 'P'
    assert any(name.startswith('root_') for name in work['state_counts'])
    assert any(name.startswith('resplit_') for name in work['state_counts'])
    assert not any(name.startswith('joint_') for name in work['state_counts'])
    with scope(1):
        with pytest.raises(EnumerationLimitExceeded):
            joint_resplit.joint_resplit_value('8', '6', (0,) * 6 + (8,) + (0,) * 3)


@pytest.mark.parametrize('s17', [True, False])
def test_unavailable_joint_branch_withholds_whole_result_even_when_root_prices_exist(s17):
    unseen = counts(('A', 'A') + ('T',) * 6)
    root = record.bounded_resplit_record(('T', 'T'), '6', rules(s17=s17),
                                        shoe=unseen, can_split=False)
    assert set(root['decision']['evs']) == {'S', 'H', 'D'}
    with pytest.raises(UnsupportedShoeError, match='dealer must draw'):
        record.bounded_resplit_record(('T', 'T'), '6', rules(s17=s17), shoe=unseen)


def test_new_joint_has_local_limits_completion_deadline_and_detached_input():
    unseen = [0] * 6 + [8] + [0] * 3
    original = unseen.copy()
    result = joint_resplit.joint_resplit_value('8', '6', unseen)
    assert result.value == 3.0 and unseen == original
    assert result.states == sum(value for _, value in result.state_counts)
    assert result.maximum_probability_mass_error <= 1e-12
    with pytest.raises(ReferenceLimitExceeded, match='state limit'):
        joint_resplit.joint_resplit_value('8', '6', unseen, max_states=1)
    with patch.object(joint_resplit, 'perf_counter', side_effect=[0.0, 2.0]):
        with pytest.raises(ReferenceLimitExceeded, match='time limit'):
            joint_resplit.joint_resplit_value('8', '6', unseen, max_seconds=1)
    times = [0.0] * (result.states + 1) + [2.0]
    with patch.object(joint_resplit, 'perf_counter', side_effect=times):
        with pytest.raises(ReferenceLimitExceeded, match='time limit'):
            joint_resplit.joint_resplit_value('8', '6', unseen, max_seconds=1)
