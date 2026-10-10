"""Saved ace records recompute their explicit model without trusting the answer."""
from __future__ import annotations

import copy
import json
import math
from unittest.mock import patch

import pytest

from bj import bounded_ace_resplit, record, replay
from bj.caches import clear_all_caches
from test_bounded_ace_resplit import counts, rules


@pytest.fixture(autouse=True)
def cold_caches():
    clear_all_caches()
    yield
    clear_all_caches()


def saved(*, double=True, split=True, tie=False):
    return record.bounded_ace_resplit_record(
        ('A', 'A'), '6' if tie else '7', rules(), shoe=counts(('T',) * 4),
        can_double=double, can_split=split)


def test_explicit_ace_dispatch_reuses_retained_counts_once():
    original = saved()
    retained = tuple(original['state']['shoe']['counts'])
    decide = bounded_ace_resplit.decide
    calls = []

    def checked(hand, up, unseen, selected_rules, **kwargs):
        calls.append((tuple(hand), up, unseen, selected_rules, kwargs))
        assert unseen == retained
        return decide(hand, up, unseen, selected_rules, **kwargs)

    with patch.object(bounded_ace_resplit, 'decide', side_effect=checked), patch.object(
            record, 'decision_record', side_effect=AssertionError('ordinary')), patch.object(
            record, 'common_shoe_record', side_effect=AssertionError('two hand')), patch.object(
            record, 'bounded_resplit_record', side_effect=AssertionError('non ace')):
        report = replay.replay_json(json.dumps(original).encode())
    assert report['status'] == 'agreement' and report['recomputed'] == original['decision']
    assert len(calls) == 1 and len(replay._admit(original)) == 8


@pytest.mark.parametrize('double,split', [(True, True), (True, False),
                                        (False, True), (False, False)])
def test_current_controls_and_ace_rules_survive_replay(double, split):
    original = saved(double=double, split=split)
    report = replay.replay_json(json.dumps(original))
    assert report['status'] == 'agreement'
    assert report['modeled_input']['state']['action_controls'] == {
        'can_double': double, 'can_split': split}
    assert set(report['recomputed']['evs']) == (
        {'S', 'H'} | ({'D'} if double else set()) | ({'P'} if split else set()))
    assert report['modeled_input']['rules']['resplit_aces'] is True
    assert report['modeled_input']['rules']['hit_split_aces'] is False


def test_one_binary_float_step_from_raw_tie_remains_a_difference():
    original = saved(tie=True)
    changed = copy.deepcopy(original)
    higher = math.nextafter(2.0, math.inf)
    changed['decision']['evs']['P'] = higher
    changed['decision'].update(action='P', action_name='SPLIT', margin=higher - 2.0)
    report = replay.replay_json(json.dumps(changed))
    assert report['status'] == 'differences' and report['recomputed'] == original['decision']
    assert report['comparison']['evs']['P']['matches'] is False
    assert report['comparison']['recommendation']['matches'] is False
    assert report['comparison']['margin']['matches'] is False
    assert report['comparison_policy']['absolute_tolerance'] == 0.0


def test_missing_action_and_changed_current_permission_are_comparison_data():
    original = saved()
    changed = copy.deepcopy(original)
    changed['decision']['evs'].pop('P')
    changed['decision'].update(action='S', action_name='STAND', margin=0.0)
    report = replay.replay_json(json.dumps(changed))
    assert report['status'] == 'differences'
    assert report['comparison']['evs']['P']['recorded'] is None
    assert report['recomputed'] == original['decision']
    changed = copy.deepcopy(original)
    changed['state']['action_controls']['can_split'] = False
    report = replay.replay_json(json.dumps(changed))
    assert report['status'] == 'differences'
    assert report['comparison']['evs']['P']['recomputed'] is None


@pytest.mark.parametrize('change', [
    lambda item: item['model'].update(name='common_shoe_bounded_resplit'),
    lambda item: item['model'].update(version=2),
    lambda item: item['model'].update(split_max_hands=4),
    lambda item: item['model'].update(split_max_extra_resplits=2),
    lambda item: item['model'].update(split_child_order='older_pending_before_new_sibling'),
    lambda item: item['model'].update(split_aces='allow_hit'),
    lambda item: item['model'].update(split_cooperative_seconds=20),
    lambda item: item['model'].update(enumeration_state_limit=0),
    lambda item: item['rules'].update(max_hands=2),
    lambda item: item['rules'].update(resplit_aces=False),
    lambda item: item['rules'].update(hit_split_aces=True),
])
def test_unqualified_declarations_refuse_before_pricing(change):
    original = saved()
    change(original)
    with patch.object(bounded_ace_resplit, 'decide', side_effect=AssertionError('pricing')):
        report = replay.replay_json(json.dumps(original))
    assert report['status'] == 'unsupported_record' and report['recomputed'] is None


@pytest.mark.parametrize('value', [True, '10', None])
def test_cooperative_allowance_requires_a_finite_non_boolean_number(value):
    original = saved()
    original['model']['split_cooperative_seconds'] = value
    with patch.object(bounded_ace_resplit, 'decide', side_effect=AssertionError('pricing')):
        assert replay.replay_json(json.dumps(original))['status'] == 'invalid_input'


def test_integer_ten_and_historical_package_are_not_new_installed_claims():
    original = saved()
    original['model']['split_cooperative_seconds'] = 10
    original['package']['version'] = 'historical'
    report = replay.replay_json(json.dumps(original))
    assert report['status'] == 'agreement' and report['package_version_matches'] is False


def test_recorded_cap_and_changed_shoe_withhold_recomputation():
    original = saved()
    original['model']['enumeration_state_limit'] = 1
    clear_all_caches()
    report = replay.replay_json(json.dumps(original))
    assert report['status'] == 'resource_limited' and report['recomputed'] is None
    assert report['work']['limit'] == report['work']['states'] == 1
    assert report['work']['attempted_states'] == 2
    original = saved(tie=True)
    original['state']['shoe']['counts'] = list(counts(('T',) * 3))
    clear_all_caches()
    report = replay.replay_json(json.dumps(original))
    assert report['status'] == 'calculation_error' and report['recomputed'] is None
    assert report['error']['type'] == 'UnsupportedShoeError'


def test_future_schema_wrong_domain_and_arithmetic_failure_are_explicit():
    original = saved()
    original['schema']['version'] = 7
    with patch.object(bounded_ace_resplit, 'decide', side_effect=AssertionError('pricing')):
        assert replay.replay_json(json.dumps(original))['status'] == 'unsupported_record'
    original = saved()
    original['state']['is_split_hand'] = True
    original['state']['hand_count'] = 2
    with patch.object(bounded_ace_resplit, 'decide', side_effect=AssertionError('pricing')):
        assert replay.replay_json(json.dumps(original))['status'] == 'unsupported_record'
    original = saved()
    with patch.object(bounded_ace_resplit, 'decide',
                      side_effect=ArithmeticError('controlled witness')):
        report = replay.replay_json(json.dumps(original))
    assert report['status'] == 'calculation_error'
    assert report['recomputed'] is None and report['comparison'] is None
    assert report['error']['type'] == 'ArithmeticError'
