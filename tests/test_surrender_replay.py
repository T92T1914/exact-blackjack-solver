"""Model dispatch and untrusted numerical answers across preserved schemas."""
from __future__ import annotations

import copy
from dataclasses import replace
import json
import math
from unittest.mock import patch

import pytest

from bj import late_surrender, record, replay
from bj.caches import clear_all_caches
from bj.core import STANDARD
from test_late_surrender import counts, rules


@pytest.fixture(autouse=True)
def cold_caches():
    clear_all_caches()
    yield
    clear_all_caches()


def saved(*, double=True, surrender=True, tie=False):
    return record.late_surrender_record(('T', '8') if tie else ('T', '6'), 'T', rules(),
                                        shoe=counts(('T', 'T', '8', '8') if tie else ('T',) * 3),
                                        can_double=double, can_surrender=surrender)


def test_replay_selects_the_family_and_uses_retained_counts_once():
    original = saved()
    retained = tuple(original['state']['shoe']['counts'])
    best_action = late_surrender.ev.best_action
    calls = []

    def checked(cards, up, *, shoe, rules, can_double, can_split):
        calls.append((tuple(cards), up, shoe, can_double, can_split))
        assert shoe == retained
        return best_action(cards, up, shoe=shoe, rules=rules,
                           can_double=can_double, can_split=can_split)

    with patch.object(late_surrender.ev, 'best_action', side_effect=checked), patch.object(
            record, 'decision_record', side_effect=AssertionError('ordinary route')), patch.object(
            record, 'common_shoe_record', side_effect=AssertionError('common route')):
        result = replay.replay_json(json.dumps(original).encode())
    assert result['status'] == 'agreement'
    assert len(calls) == 1 and calls[0][4] is False
    assert len(replay._admit(original)) == 8
    assert result['recomputed'] == original['decision']


@pytest.mark.parametrize('double,surrender', [(True, True), (True, False),
                                           (False, True), (False, False)])
def test_current_controls_are_replayed_explicitly(double, surrender):
    original = saved(double=double, surrender=surrender)
    result = replay.replay_json(json.dumps(original))
    assert result['status'] == 'agreement'
    assert result['modeled_input']['state']['action_controls'] == {
        'can_double': double, 'can_split': False, 'can_surrender': surrender}
    assert set(result['recomputed']['evs']) == (
        {'S', 'H'} | ({'D'} if double else set()) | ({'R'} if surrender else set()))


def test_changed_permission_recomputes_the_same_family_without_trusting_r():
    original = saved()
    original['state']['action_controls']['can_surrender'] = False
    result = replay.replay_json(json.dumps(original))
    assert result['status'] == 'differences'
    assert result['recorded']['action'] == 'R'
    assert result['recomputed']['action'] == 'S'
    assert result['comparison']['legal_actions']['recomputed'] == ['D', 'H', 'S']
    assert result['modeled_input']['model']['name'] == 'post_peek_late_surrender'


def test_one_float_step_in_saved_tie_remains_a_visible_difference():
    original = saved(tie=True)
    modified = copy.deepcopy(original)
    altered_r = math.nextafter(-0.5, 0.0)
    modified['decision']['evs']['R'] = altered_r
    modified['decision'].update(action='R', action_name='SURRENDER', margin=altered_r + 0.5)
    result = replay.replay_json(json.dumps(modified))
    assert result['status'] == 'differences'
    assert result['recorded'] == modified['decision']
    assert result['recomputed'] == original['decision']
    assert result['comparison']['evs']['R']['matches'] is False
    assert result['comparison']['recommendation']['matches'] is False
    assert result['comparison']['margin']['matches'] is False
    assert result['comparison_policy']['absolute_tolerance'] == 0


@pytest.mark.parametrize('change', [
    lambda item: item['decision']['evs'].pop('H'),
    lambda item: item['decision']['evs'].update(R=7.0),
    lambda item: item['decision'].update(margin=3.0),
    lambda item: item['decision'].update(action='H', action_name='HIT'),
])
def test_recognizable_altered_answers_are_comparison_data(change):
    original = saved()
    expected = copy.deepcopy(original['decision'])
    change(original)
    result = replay.replay_json(json.dumps(original))
    assert result['status'] == 'differences'
    assert result['recorded'] == original['decision']
    assert result['recomputed'] == expected


def test_missing_r_and_unavailable_saved_d_are_not_accepted_as_truth():
    original = saved()
    original['decision']['evs'].pop('R')
    original['decision'].update(action='S', action_name='STAND', margin=0.0)
    result = replay.replay_json(json.dumps(original))
    assert result['status'] == 'differences'
    assert result['comparison']['evs']['R']['recorded'] is None
    original = saved(double=False)
    original['decision']['evs']['D'] = -2.0
    result = replay.replay_json(json.dumps(original))
    assert result['status'] == 'differences'
    assert result['comparison']['evs']['D']['recomputed'] is None


@pytest.mark.parametrize('change', [
    lambda item: item['model'].update(name='other'),
    lambda item: item['model'].update(version=2),
    lambda item: item['model'].update(surrender_after_hit=True),
    lambda item: item['model'].update(surrender_after_double=True),
    lambda item: item['model'].update(surrender_draws=1),
    lambda item: item['model'].update(enumeration_state_limit=0),
    lambda item: item['rules'].update(surrender=False),
    lambda item: item['rules'].update(max_hands=2),
    lambda item: item['state']['action_controls'].update(can_split=True),
])
def test_changed_family_or_outside_domain_refuses_before_pricing(change):
    original = saved()
    change(original)
    with patch.object(late_surrender, 'decide', side_effect=AssertionError('must not price')):
        result = replay.replay_json(json.dumps(original))
    assert result['status'] == 'unsupported_record'
    assert result['recomputed'] is None


def test_recorded_cap_refuses_genuine_cold_recomputation():
    original = saved()
    original['model']['enumeration_state_limit'] = 1
    clear_all_caches()
    result = replay.replay_json(json.dumps(original))
    assert result['status'] == 'resource_limited'
    assert result['recomputed'] is None
    assert result['work'] == {'limit': 1, 'states': 1, 'attempted_states': 2,
                              'state_counts': {'root_distribution': 1}}


@pytest.mark.parametrize('version', [1, 2, 3])
@pytest.mark.parametrize('forgery', ['action', 'controls', 'rules'])
def test_historical_records_do_not_gain_surrender(version, forgery):
    if version == 3:
        original = record.common_shoe_record(('T', 'T'), '7', replace(STANDARD, max_hands=2),
                                             shoe=counts(('A',) + ('T',) * 5))
    else:
        original = record.decision_record(('T', '6'), 'T', shoe=counts(('T',) * 3),
                                           can_split=version == 1)
    assert original['schema']['version'] == version
    if forgery == 'action':
        original['decision']['evs']['R'] = -0.5
    elif forgery == 'controls':
        original['state'].setdefault('action_controls', {})['can_surrender'] = True
    else:
        original['rules']['surrender'] = True
    with patch.object(late_surrender, 'decide', side_effect=AssertionError('new model')):
        result = replay.replay_json(json.dumps(original))
    assert result['status'] == ('unsupported_record' if forgery == 'rules' else 'invalid_input')


def test_version_four_cannot_store_the_excluded_split_action():
    original = saved()
    original['decision']['evs']['P'] = 2.0
    assert replay.replay_json(json.dumps(original))['status'] == 'invalid_input'
