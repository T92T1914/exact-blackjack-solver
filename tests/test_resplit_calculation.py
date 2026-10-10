"""Strict new-family worker binding through the preserved calculation owner."""
from __future__ import annotations

import copy
import hashlib
import io
import json
import sys
import threading
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from bj import bounded_resplit, calculation as calc, record
from bj import _calculation_worker as worker
from bj.caches import clear_all_caches
from test_bounded_resplit import counts
from test_calculation import policy, request as legacy_request
from test_common_calculation import common_request
from test_surrender_calculation import surrender_request


def resplit_request(limit=100000, *, double=True, split=True, tie=False):
    return {
        'schema': dict(calc.RESPLIT_REQUEST_SCHEMA),
        'model': dict(bounded_resplit.MODEL), 'limits': {'max_states': limit},
        'rules': {'max_hands': 3, 'das': False},
        'input': {'cards': ['T', 'T'] if tie else ['8', '8'],
                  'dealer_up': 'T' if tie else '6',
                  'unseen_counts': list(counts(('T',) * 8 if tie else ('8',) * 8)),
                  'is_split_hand': False, 'hand_count': 1,
                  'can_double': double, 'can_split': split},
    }


@pytest.fixture(autouse=True)
def cold_caches():
    clear_all_caches()
    yield
    clear_all_caches()


def fixed_message(value):
    captured = calc._normalise(value)
    selected = calc._request_policy(policy(), captured)
    digest = hashlib.sha256(calc._json_bytes(captured)).hexdigest()
    payload = calc._json_bytes({'request': captured, 'request_sha256': digest,
                               'policy': selected})
    output = io.BytesIO()
    with patch.object(sys, 'stdin', SimpleNamespace(buffer=io.BytesIO(payload))), patch.object(
            sys, 'stdout', SimpleNamespace(buffer=output)):
        code = worker.main()
    return code, json.loads(output.getvalue()), captured, selected


def validate(message, captured, selected, code=0):
    return calc._validated_decision(calc._json_bytes(message), captured,
                                    message['request_sha256'], code, selected)


def returned(message, code=0):
    """Synthetic transport result, separate from actual owned-worker acceptance."""
    def operation(payload, *_):
        captured = json.loads(payload)
        output = {**message, 'request_sha256': captured['request_sha256'],
                  'policy': captured['policy']}
        return {'status': 'returned', 'error': None, 'stdout': calc._json_bytes(output),
                'stderr': b'', 'worker': {'pid': 123, 'returncode': code},
                'policy_established': True,
                'cleanup': {'retired': True, 'worker_retired': True, 'transport_retired': True,
                            'job_empty': None, 'errors': []}, 'elapsed_seconds': 0.01}
    return operation


def test_normalization_and_policy_capture_are_non_pricing():
    value = resplit_request(50, double=False, split=False, tie=True)
    value['input']['cards'] = ['10', '10']
    with patch.object(bounded_resplit, 'decide', side_effect=AssertionError('must not price')):
        captured = calc._normalise(value)
    assert captured['input']['cards'] == ['T', 'T']
    assert captured['input']['unseen_counts'] == value['input']['unseen_counts']
    assert captured['model'] == bounded_resplit.MODEL
    assert captured['rules']['max_hands'] == 3
    selected = calc._request_policy(policy(), captured)
    assert selected['algorithmic_work_limit'] == {
        'name': 'whole_request_uncached_enumeration_states', 'max_states': 50,
        'includes': 'root_draw_hit_double_distribution_dealer_and_resplit_draw_play_settle_dealer',
        'split_cooperative_seconds': 10.0}
    assert policy()['algorithmic_work_limit'] is None


@pytest.mark.parametrize('change', [
    lambda item: item['schema'].update(version=True),
    lambda item: item['schema'].update(version=5),
    lambda item: item['model'].update(name='other'),
    lambda item: item['model'].update(version=True),
    lambda item: item['rules'].update(surrender=True),
    lambda item: item['rules'].update(peek=False),
    lambda item: item['rules'].update(max_hands=2),
    lambda item: item['rules'].update(resplit_aces=True),
    lambda item: item['rules'].update(hit_split_aces=True),
    lambda item: item['input'].update(cards=['A', 'A']),
    lambda item: item['input'].update(cards=['8', '9']),
    lambda item: item['input'].update(is_split_hand=True, hand_count=2),
    lambda item: item['input'].update(can_split=1),
    lambda item: item['input'].update(can_surrender=False),
    lambda item: item['input'].update(unseen_counts=[0] * 9 + [21]),
    lambda item: item['limits'].update(max_states=0),
    lambda item: item['limits'].update(max_states=True),
    lambda item: item['limits'].update(max_states=100001),
    lambda item: item.pop('model'),
    lambda item: item.pop('limits'),
])
def test_invalid_request_refuses_before_worker_or_destination(tmp_path, change):
    value = resplit_request()
    change(value)
    source = tmp_path / 'input.json'
    source.write_bytes(calc._json_bytes(value))
    with patch.object(calc, 'execute') as dispatch:
        receipt = calc._run(source, tmp_path / 'attempt', policy(), threading.Event())
    assert receipt['status'] == 'invalid_request' and receipt['record'] is None
    assert not dispatch.called and not (tmp_path / 'attempt').exists()


@pytest.mark.parametrize('double,split', [(True, True), (True, False),
                                        (False, True), (False, False)])
def test_fixed_worker_completes_exact_selected_actions_without_parent_pricing(double, split):
    code, message, captured, selected = fixed_message(resplit_request(double=double, split=split))
    assert code == 0 and message['status'] == 'completed'
    assert message['decision']['schema']['version'] == 5
    assert message['decision']['decision']['evs'] == (
        {'S': 1.0, 'H': -1.0} | ({'D': -2.0} if double else {}) |
        ({'P': 3.0} if split else {}))
    assert set(message['work']['state_counts']) <= bounded_resplit.FAMILIES
    with patch.object(bounded_resplit, 'decide', side_effect=AssertionError('parent pricing')):
        status, raw, error, work = validate(message, captured, selected, code)
    assert status == 'completed' and error is None
    assert json.loads(raw) == message['decision'] and work == message['work']


def test_state_cap_and_unavailable_joint_branch_accept_no_complete_record():
    code, message, captured, selected = fixed_message(resplit_request(1))
    assert code == 4 and message['status'] == 'resource_limited'
    assert message['decision'] is None
    assert message['work']['states'] == 1 and message['work']['attempted_states'] == 2
    assert validate(message, captured, selected, code)[1] is None
    value = resplit_request()
    value['input']['unseen_counts'] = list(counts(('8',) * 7))
    clear_all_caches()
    code, message, captured, selected = fixed_message(value)
    assert code == 5 and message['status'] == 'calculation_error'
    assert message['decision'] is None and message['work'] is None
    assert 'dealer must draw' in message['error']['message']
    assert validate(message, captured, selected, code)[1] is None


def test_bound_complete_message_commits_using_existing_result_and_receipt(tmp_path):
    code, message, _, _ = fixed_message(resplit_request())
    source = tmp_path / 'input.json'
    source.write_bytes(calc._json_bytes(resplit_request()))
    with patch.object(calc, 'execute', side_effect=returned(message, code)), patch.object(
            bounded_resplit, 'decide', side_effect=AssertionError('parent pricing')):
        receipt = calc._run(source, tmp_path / 'attempt', policy(), threading.Event())
    assert receipt['status'] == 'completed' and receipt['work'] == message['work']
    assert json.loads(
        (tmp_path / 'attempt/result/decision.json').read_bytes()) == message['decision']
    assert json.loads((tmp_path / 'attempt/result/receipt.json').read_bytes()) == receipt


def old_joint_work(message):
    counts = message['work']['state_counts']
    counts['joint_draw'] = counts.pop('resplit_draw')


@pytest.mark.parametrize('change', [
    lambda item: item['decision']['decision']['evs'].pop('H'),
    lambda item: item['decision']['decision'].update(evs={'P': 3.0}, margin=0.0),
    lambda item: item['decision']['state']['action_controls'].update(can_split=False),
    lambda item: item['decision']['state']['action_controls'].update(can_double=False),
    lambda item: item['decision']['state']['shoe']['counts'].__setitem__(7, 9),
    lambda item: item['decision']['rules'].update(das=True),
    lambda item: item['decision']['package'].update(version='other'),
    lambda item: item['decision']['model'].update(name='other'),
    lambda item: item['decision']['model'].update(split_max_extra_resplits=2),
    lambda item: item['decision']['model'].update(enumeration_state_limit=99999),
    lambda item: item['work'].update(limit=99999),
    lambda item: item['work'].update(attempted_states=True),
    old_joint_work,
    lambda item: item.update(work=None),
])
def test_incomplete_or_unbound_completion_never_commits(tmp_path, change):
    code, original, _, _ = fixed_message(resplit_request())
    altered = copy.deepcopy(original)
    change(altered)
    source = tmp_path / 'input.json'
    source.write_bytes(calc._json_bytes(resplit_request()))
    with patch.object(calc, 'execute', side_effect=returned(altered, code)), patch.object(
            bounded_resplit, 'decide', side_effect=AssertionError('parent pricing')):
        receipt = calc._run(source, tmp_path / 'attempt', policy(), threading.Event())
    assert receipt['status'] == 'worker_failed' and receipt['record'] is None
    assert not (tmp_path / 'attempt/result').exists()


def test_parent_canonical_tie_ignores_received_key_order():
    code, message, captured, selected = fixed_message(resplit_request(tie=True))
    answer = message['decision']['decision']
    answer['evs'] = dict(reversed(list(answer['evs'].items())))
    assert validate(message, captured, selected, code)[0] == 'completed'
    answer.update(action='P', action_name='SPLIT')
    with pytest.raises(ValueError, match='canonical ranking'):
        validate(message, captured, selected, code)


def test_historical_worker_routes_keep_their_models_and_versions():
    with patch.object(record, '_bounded_resplit_record', side_effect=AssertionError('new model')):
        for value, version in ((legacy_request(), 1), (common_request(), 3),
                               (surrender_request(), 4)):
            clear_all_caches()
            code, message, captured, selected = fixed_message(value)
            assert code == 0 and message['decision']['schema']['version'] == version
            assert validate(message, captured, selected, code)[0] == 'completed'


def test_controlled_arithmetic_failure_is_an_incomplete_calculation():
    with patch.object(bounded_resplit.joint_resplit, 'joint_resplit_value',
                      side_effect=ArithmeticError('controlled witness')):
        code, message, captured, selected = fixed_message(resplit_request())
    assert code == 5 and message['status'] == 'calculation_error'
    assert message['decision'] is None and message['work'] is None
    assert message['error']['type'] == 'ArithmeticError'
    assert validate(message, captured, selected, code)[1] is None


@pytest.mark.parametrize('field', ['request_sha256', 'policy'])
def test_worker_cannot_change_captured_digest_or_policy(field):
    code, original, captured, selected = fixed_message(resplit_request())
    altered = copy.deepcopy(original)
    if field == 'request_sha256':
        altered[field] = '0' * 64
    else:
        altered[field]['algorithmic_work_limit']['max_states'] = 99999
    digest = hashlib.sha256(calc._json_bytes(captured)).hexdigest()
    with patch.object(bounded_resplit, 'decide', side_effect=AssertionError('parent pricing')):
        with pytest.raises(ValueError, match='captured request and policy'):
            calc._validated_decision(calc._json_bytes(altered), captured, digest, code, selected)
