"""Declared-model replay with saved answers retained as comparison material."""
from __future__ import annotations

import copy
import json
import math
from unittest.mock import patch

import pytest

from bj import bounded_resplit, record, replay
from bj.caches import clear_all_caches
from test_bounded_resplit import counts, rules


@pytest.fixture(autouse=True)
def cold_caches():
    clear_all_caches()
    yield
    clear_all_caches()


def saved(*, double=True, split=True, tie=False):
    return record.bounded_resplit_record(
        ('T', 'T') if tie else ('8', '8'), 'T' if tie else '6', rules(das=False),
        shoe=counts(('T',) * 8 if tie else ('8',) * 8),
        can_double=double, can_split=split)


def test_replay_selects_new_family_and_reuses_retained_counts_once():
    original = saved()
    retained = tuple(original['state']['shoe']['counts'])
    decide = bounded_resplit.decide
    calls = []

    def checked(hand, up, unseen, selected_rules, **kwargs):
        calls.append((tuple(hand), up, unseen, selected_rules, kwargs))
        assert unseen == retained
        return decide(hand, up, unseen, selected_rules, **kwargs)

    with patch.object(bounded_resplit, 'decide', side_effect=checked), patch.object(
            record, 'decision_record', side_effect=AssertionError('ordinary')), patch.object(
            record, 'common_shoe_record', side_effect=AssertionError('two hand')), patch.object(
            record, 'late_surrender_record', side_effect=AssertionError('surrender')):
        report = replay.replay_json(json.dumps(original).encode())
    assert report['status'] == 'agreement'
    assert report['recomputed'] == original['decision']
    assert len(calls) == 1 and len(replay._admit(original)) == 8


@pytest.mark.parametrize('double,split', [(True, True), (True, False),
                                        (False, True), (False, False)])
def test_replay_retains_current_controls_and_continuation_rules(double, split):
    original = saved(double=double, split=split)
    report = replay.replay_json(json.dumps(original))
    assert report['status'] == 'agreement'
    assert report['modeled_input']['state']['action_controls'] == {
        'can_double': double, 'can_split': split}
    assert set(report['recomputed']['evs']) == (
        {'S', 'H'} | ({'D'} if double else set()) | ({'P'} if split else set()))
    assert report['modeled_input']['rules']['max_hands'] == 3


def test_one_binary_float_step_in_saved_exact_tie_stays_visible():
    original = saved(tie=True)
    changed = copy.deepcopy(original)
    changed_p = math.nextafter(0.0, math.inf)
    changed['decision']['evs']['P'] = changed_p
    changed['decision'].update(action='P', action_name='SPLIT', margin=changed_p)
    report = replay.replay_json(json.dumps(changed))
    assert report['status'] == 'differences'
    assert report['recomputed'] == original['decision']
    assert report['comparison']['evs']['P']['matches'] is False
    assert report['comparison']['recommendation']['matches'] is False
    assert report['comparison']['margin']['matches'] is False
    assert report['comparison_policy']['absolute_tolerance'] == 0.0


def test_missing_p_and_changed_permission_are_comparison_data():
    original = saved()
    changed = copy.deepcopy(original)
    changed['decision']['evs'].pop('P')
    changed['decision'].update(action='S', action_name='STAND', margin=2.0)
    report = replay.replay_json(json.dumps(changed))
    assert report['status'] == 'differences'
    assert report['comparison']['evs']['P']['recorded'] is None
    assert report['recomputed'] == original['decision']
    changed = copy.deepcopy(original)
    changed['state']['action_controls']['can_split'] = False
    report = replay.replay_json(json.dumps(changed))
    assert report['status'] == 'differences'
    assert report['comparison']['evs']['P']['recomputed'] is None
    assert report['recomputed']['action'] == 'S'


@pytest.mark.parametrize('change', [
    lambda item: item['model'].update(name='other'),
    lambda item: item['model'].update(version=2),
    lambda item: item['model'].update(split_max_hands=4),
    lambda item: item['model'].update(split_max_extra_resplits=2),
    lambda item: item['model'].update(split_child_order='older_pending_before_new_sibling'),
    lambda item: item['model'].update(split_objective='current_hand_only'),
    lambda item: item['model'].update(split_cooperative_seconds=20.0),
    lambda item: item['model'].update(enumeration_state_limit=0),
    lambda item: item['rules'].update(max_hands=2),
    lambda item: item['rules'].update(surrender=True),
    lambda item: item['rules'].update(resplit_aces=True),
])
def test_unqualified_model_changes_refuse_before_pricing(change):
    original = saved()
    change(original)
    with patch.object(bounded_resplit, 'decide', side_effect=AssertionError('must not price')):
        report = replay.replay_json(json.dumps(original))
    assert report['status'] == 'unsupported_record'
    assert report['recomputed'] is None


@pytest.mark.parametrize('value', [True, '10', None])
def test_cooperative_seconds_requires_finite_non_boolean_numeric_token(value):
    original = saved()
    original['model']['split_cooperative_seconds'] = value
    with patch.object(bounded_resplit, 'decide', side_effect=AssertionError('must not price')):
        assert replay.replay_json(json.dumps(original))['status'] == 'invalid_input'


def test_integer_and_float_ten_admit_the_same_cooperative_deadline():
    original = saved()
    original['model']['split_cooperative_seconds'] = 10
    assert replay.replay_json(json.dumps(original))['status'] == 'agreement'


def test_recorded_cap_refuses_actual_cold_recomputation():
    original = saved()
    original['model']['enumeration_state_limit'] = 1
    clear_all_caches()
    report = replay.replay_json(json.dumps(original))
    assert report['status'] == 'resource_limited' and report['recomputed'] is None
    assert report['work']['limit'] == report['work']['states'] == 1
    assert report['work']['attempted_states'] == 2


def test_valid_changed_shoe_can_refuse_without_promoting_saved_answer():
    original = saved()
    original['state']['shoe']['counts'] = list(counts(('8',) * 7))
    clear_all_caches()
    report = replay.replay_json(json.dumps(original))
    assert report['status'] == 'calculation_error'
    assert report['recomputed'] is None
    assert report['error']['type'] == 'UnsupportedShoeError'


def test_future_schema_and_wrong_initial_state_are_refused_before_pricing():
    original = saved()
    original['schema']['version'] = 6
    with patch.object(bounded_resplit, 'decide', side_effect=AssertionError('must not price')):
        assert replay.replay_json(json.dumps(original))['status'] == 'unsupported_record'
    original = saved()
    original['state']['is_split_hand'] = True
    original['state']['hand_count'] = 2
    with patch.object(bounded_resplit, 'decide', side_effect=AssertionError('must not price')):
        assert replay.replay_json(json.dumps(original))['status'] == 'unsupported_record'


def test_recognizable_historical_package_version_is_reported_not_installed():
    original = saved()
    original['package']['version'] = 'historical'
    report = replay.replay_json(json.dumps(original))
    assert report['status'] == 'agreement' and report['package_version_matches'] is False


def test_controlled_new_arithmetic_failure_is_a_structured_incomplete_replay():
    original = saved()
    with patch.object(bounded_resplit, 'decide', side_effect=ArithmeticError('controlled witness')):
        report = replay.replay_json(json.dumps(original))
    assert report['status'] == 'calculation_error'
    assert report['recomputed'] is None and report['comparison'] is None
    assert report['error']['type'] == 'ArithmeticError'
