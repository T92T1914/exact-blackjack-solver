"""Request 5 and record 6 binding through the existing calculation owner."""
from __future__ import annotations

import copy
import json
import threading
from unittest.mock import patch

import pytest

from bj import bounded_ace_resplit, calculation as calc, record
from bj.caches import clear_all_caches
from test_bounded_ace_resplit import counts
from test_calculation import policy, request as legacy_request
from test_common_calculation import common_request
from test_resplit_calculation import fixed_message, resplit_request, returned, validate
from test_surrender_calculation import surrender_request


def ace_request(limit=100000, *, double=True, split=True, tie=False):
    return {
        'schema': dict(calc.ACE_RESPLIT_REQUEST_SCHEMA),
        'model': dict(bounded_ace_resplit.MODEL), 'limits': {'max_states': limit},
        'rules': {'max_hands': 3, 'resplit_aces': True},
        'input': {'cards': ['A', 'A'], 'dealer_up': '6' if tie else '7',
                  'unseen_counts': list(counts(('T',) * 4)),
                  'is_split_hand': False, 'hand_count': 1,
                  'can_double': double, 'can_split': split},
    }


@pytest.fixture(autouse=True)
def cold_caches():
    clear_all_caches()
    yield
    clear_all_caches()


def test_non_pricing_capture_and_exact_policy_identity():
    value = ace_request(50, double=False, split=False)
    with patch.object(bounded_ace_resplit, 'decide', side_effect=AssertionError('pricing')):
        captured = calc._normalise(value)
    assert captured['model'] == bounded_ace_resplit.MODEL
    assert captured['input'] == value['input']
    assert calc._request_policy(policy(), captured)['algorithmic_work_limit'] == {
        'name': 'whole_request_uncached_enumeration_states', 'max_states': 50,
        'includes': ('root_draw_hit_double_distribution_dealer_and_'
                     'ace_resplit_draw_play_settle_dealer'),
        'split_cooperative_seconds': 10.0}
    assert policy()['algorithmic_work_limit'] is None


@pytest.mark.parametrize('change', [
    lambda item: item['schema'].update(version=True),
    lambda item: item['schema'].update(version=6),
    lambda item: item['model'].update(name='common_shoe_bounded_resplit'),
    lambda item: item['model'].update(version=True),
    lambda item: item['rules'].update(resplit_aces=False),
    lambda item: item['rules'].update(hit_split_aces=True),
    lambda item: item['rules'].update(max_hands=4),
    lambda item: item['input'].update(cards=['8', '8']),
    lambda item: item['input'].update(is_split_hand=True, hand_count=2),
    lambda item: item['input'].update(can_split=1),
    lambda item: item['input'].update(include_root=False),
    lambda item: item['model'].update(allow_resplit=False),
    lambda item: item['limits'].update(max_states=100001),
])
def test_invalid_or_experimental_request_fields_refuse_before_dispatch(tmp_path, change):
    value = ace_request()
    change(value)
    source = tmp_path / 'input.json'
    source.write_bytes(calc._json_bytes(value))
    with patch.object(calc, 'execute') as dispatch:
        receipt = calc._run(source, tmp_path / 'attempt', policy(), threading.Event())
    assert receipt['status'] == 'invalid_request' and receipt['record'] is None
    assert not dispatch.called and not (tmp_path / 'attempt').exists()


@pytest.mark.parametrize('double,split', [(True, True), (True, False),
                                        (False, True), (False, False)])
def test_worker_completes_exact_original_action_set_without_parent_pricing(double, split):
    code, message, captured, selected = fixed_message(ace_request(double=double, split=split))
    assert code == 0 and message['status'] == 'completed'
    assert message['decision']['schema']['version'] == 6
    assert message['decision']['decision']['evs'] == (
        {'S': -1.0, 'H': -1.0} | ({'D': -2.0} if double else {}) |
        ({'P': 2.0} if split else {}))
    with patch.object(bounded_ace_resplit, 'decide', side_effect=AssertionError('parent pricing')):
        status, raw, error, work = validate(message, captured, selected, code)
    assert status == 'completed' and error is None
    assert json.loads(raw) == message['decision'] and work == message['work']


def test_state_cap_and_exhaustion_return_no_partial_record():
    code, message, captured, selected = fixed_message(ace_request(1))
    assert code == 4 and message['status'] == 'resource_limited' and message['decision'] is None
    assert message['work']['states'] == 1 and message['work']['attempted_states'] == 2
    assert validate(message, captured, selected, code)[1] is None
    value = ace_request()
    value['input'].update(dealer_up='6', unseen_counts=list(counts(('T',) * 3)))
    clear_all_caches()
    code, message, captured, selected = fixed_message(value)
    assert code == 5 and message['status'] == 'calculation_error'
    assert message['decision'] is None and message['work'] is None
    assert message['error']['type'] == 'UnsupportedShoeError'
    assert validate(message, captured, selected, code)[1] is None


def test_existing_commit_path_delivers_complete_record_and_receipt(tmp_path):
    code, message, _, _ = fixed_message(ace_request())
    source = tmp_path / 'input.json'
    source.write_bytes(calc._json_bytes(ace_request()))
    with patch.object(calc, 'execute', side_effect=returned(message, code)), patch.object(
            bounded_ace_resplit, 'decide', side_effect=AssertionError('parent pricing')):
        receipt = calc._run(source, tmp_path / 'attempt', policy(), threading.Event())
    assert receipt['status'] == 'completed' and receipt['work'] == message['work']
    assert json.loads(
        (tmp_path / 'attempt/result/decision.json').read_bytes()) == message['decision']
    assert json.loads((tmp_path / 'attempt/result/receipt.json').read_bytes()) == receipt


def wrong_family(message):
    counters = message['work']['state_counts']
    counters['resplit_draw'] = counters.pop('ace_resplit_draw')


@pytest.mark.parametrize('change', [
    lambda item: item['decision']['decision']['evs'].pop('H'),
    lambda item: item['decision']['decision'].update(evs={'P': 2.0}, margin=0.0),
    lambda item: item['decision']['state']['action_controls'].update(can_split=False),
    lambda item: item['decision']['rules'].update(resplit_aces=False),
    lambda item: item['decision']['package'].update(version='other'),
    lambda item: item['decision']['model'].update(split_max_extra_resplits=2),
    lambda item: item['decision']['model'].update(enumeration_state_limit=99999),
    lambda item: item['work'].update(limit=99999),
    lambda item: item.update(work=None),
    wrong_family,
])
def test_unbound_or_partial_completion_cannot_commit(tmp_path, change):
    code, message, _, _ = fixed_message(ace_request())
    altered = copy.deepcopy(message)
    change(altered)
    source = tmp_path / 'input.json'
    source.write_bytes(calc._json_bytes(ace_request()))
    with patch.object(calc, 'execute', side_effect=returned(altered, code)), patch.object(
            bounded_ace_resplit, 'decide', side_effect=AssertionError('parent pricing')):
        receipt = calc._run(source, tmp_path / 'attempt', policy(), threading.Event())
    assert receipt['status'] == 'worker_failed' and receipt['record'] is None
    assert not (tmp_path / 'attempt/result').exists()


def test_canonical_raw_tie_and_structured_arithmetic_refusal():
    code, message, captured, selected = fixed_message(ace_request(tie=True))
    answer = message['decision']['decision']
    answer['evs'] = dict(reversed(list(answer['evs'].items())))
    assert validate(message, captured, selected, code)[0] == 'completed'
    answer.update(action='P', action_name='SPLIT')
    with pytest.raises(ValueError, match='canonical ranking'):
        validate(message, captured, selected, code)
    clear_all_caches()
    with patch.object(bounded_ace_resplit.joint_ace_resplit, 'joint_ace_resplit_value',
                      side_effect=ArithmeticError('controlled witness')):
        code, message, captured, selected = fixed_message(ace_request())
    assert code == 5 and message['status'] == 'calculation_error'
    assert message['decision'] is None and message['error']['type'] == 'ArithmeticError'
    assert validate(message, captured, selected, code)[1] is None


def test_all_historical_worker_routes_keep_their_identity():
    with patch.object(record, '_bounded_ace_resplit_record',
                      side_effect=AssertionError('ace route')):
        for value, version in ((legacy_request(), 1), (common_request(), 3),
                               (surrender_request(), 4), (resplit_request(), 5)):
            clear_all_caches()
            code, message, captured, selected = fixed_message(value)
            assert code == 0 and message['decision']['schema']['version'] == version
            assert validate(message, captured, selected, code)[0] == 'completed'
