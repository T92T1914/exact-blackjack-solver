"""New-family fixed-worker binding through the unchanged calculation owner."""
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

from bj import calculation as calc, late_surrender, record
from bj import _calculation_worker as worker
from bj.caches import clear_all_caches
from test_calculation import policy, request as legacy_request
from test_common_calculation import common_request
from test_late_surrender import counts


def surrender_request(limit=100000, *, double=True, surrender=True, tie=False):
    return {
        'schema': dict(calc.SURRENDER_REQUEST_SCHEMA),
        'model': dict(late_surrender.MODEL), 'limits': {'max_states': limit},
        'rules': {'surrender': True, 'max_hands': 1},
        'input': {'cards': ['T', '8'] if tie else ['T', '6'], 'dealer_up': 'T',
                  'unseen_counts': list(counts(('T', 'T', '8', '8') if tie else ('T',) * 3)),
                  'is_split_hand': False, 'hand_count': 1, 'can_double': double,
                  'can_split': False, 'can_surrender': surrender},
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


def test_request_and_root_only_policy_capture_without_pricing():
    value = surrender_request(50, double=False, surrender=False)
    value['input']['cards'] = ['10', '6']
    with patch.object(late_surrender, 'decide', side_effect=AssertionError('must not price')):
        captured = calc._normalise(value)
    assert captured['input']['cards'] == ['T', '6']
    assert captured['input']['unseen_counts'] == value['input']['unseen_counts']
    assert captured['input']['can_surrender'] is False
    assert captured['rules']['surrender'] is True
    assert captured['rules']['max_hands'] == 1
    selected = calc._request_policy(policy(), captured)
    assert selected['algorithmic_work_limit'] == {
        'name': 'whole_request_uncached_enumeration_states', 'max_states': 50,
        'includes': 'root_draw_hit_double_distribution_dealer'}
    assert policy()['algorithmic_work_limit'] is None


@pytest.mark.parametrize('change', [
    lambda item: item['schema'].update(version=True),
    lambda item: item['model'].update(name='other'),
    lambda item: item['model'].update(version=True),
    lambda item: item['rules'].update(surrender=False),
    lambda item: item['rules'].update(peek=False),
    lambda item: item['rules'].update(max_hands=2),
    lambda item: item['rules'].update(resplit_aces=True),
    lambda item: item['input'].update(cards=['A', 'T']),
    lambda item: item['input'].update(cards=['T', '6', '2']),
    lambda item: item['input'].update(is_split_hand=True),
    lambda item: item['input'].update(hand_count=2),
    lambda item: item['input'].update(can_split=True),
    lambda item: item['input'].update(can_surrender=1),
    lambda item: item['input'].pop('can_surrender'),
    lambda item: item['input'].update(unseen_counts=[0] * 9 + [21]),
    lambda item: item['limits'].update(max_states=0),
    lambda item: item['limits'].update(max_states=True),
    lambda item: item['limits'].update(max_states=100001),
    lambda item: item.pop('model'),
    lambda item: item.pop('limits'),
])
def test_invalid_family_request_refuses_before_worker_and_destination(tmp_path, change):
    value = surrender_request()
    change(value)
    source = tmp_path / 'input.json'
    source.write_bytes(calc._json_bytes(value))
    with patch.object(calc, 'execute') as dispatch:
        receipt = calc._run(source, tmp_path / 'attempt', policy(), threading.Event())
    assert receipt['status'] == 'invalid_request'
    assert receipt['record'] is None
    assert not dispatch.called
    assert not (tmp_path / 'attempt').exists()


@pytest.mark.parametrize('double,surrender', [(True, True), (True, False),
                                           (False, True), (False, False)])
def test_real_fixed_worker_prices_the_complete_selected_family(double, surrender):
    code, message, captured, selected = fixed_message(
        surrender_request(double=double, surrender=surrender))
    assert code == 0 and message['status'] == 'completed'
    assert message['decision']['schema']['version'] == 4
    assert message['decision']['decision']['evs'] == (
        {'S': -1.0, 'H': -1.0} | ({'D': -2.0} if double else {}) |
        ({'R': -0.5} if surrender else {}))
    assert set(message['work']['state_counts']) <= late_surrender.ROOT_FAMILIES
    with patch.object(late_surrender, 'decide', side_effect=AssertionError('parent pricing')):
        status, raw, error, work = validate(message, captured, selected, code)
    assert status == 'completed' and error is None
    assert json.loads(raw) == message['decision']
    assert work == message['work']


def test_genuine_state_and_dealer_refusals_have_no_complete_decision():
    code, message, captured, selected = fixed_message(surrender_request(1))
    assert code == 4 and message['status'] == 'resource_limited'
    assert message['decision'] is None
    assert message['work'] == {'limit': 1, 'states': 1, 'attempted_states': 2,
                               'state_counts': {'root_distribution': 1}}
    assert validate(message, captured, selected, code)[1] is None
    value = surrender_request()
    value['input'].update(dealer_up='2', unseen_counts=list(counts(('2', '2', '2'))))
    clear_all_caches()
    code, message, captured, selected = fixed_message(value)
    assert code == 5 and message['status'] == 'calculation_error'
    assert message['decision'] is None and message['work'] is None
    assert message['error']['type'] == 'ValueError'
    assert 'dealer must draw' in message['error']['message']
    assert validate(message, captured, selected, code)[1] is None


def test_complete_message_commits_without_parent_recalculation(tmp_path):
    code, message, _, _ = fixed_message(surrender_request())
    source = tmp_path / 'input.json'
    source.write_bytes(calc._json_bytes(surrender_request()))
    with patch.object(calc, 'execute', side_effect=returned(message, code)), patch.object(
            late_surrender, 'decide', side_effect=AssertionError('parent pricing')):
        receipt = calc._run(source, tmp_path / 'attempt', policy(), threading.Event())
    assert receipt['status'] == 'completed'
    assert receipt['work'] == message['work']
    committed = json.loads((tmp_path / 'attempt/result/decision.json').read_bytes())
    assert committed == message['decision']
    assert json.loads((tmp_path / 'attempt/result/receipt.json').read_bytes()) == receipt


def only_r(message):
    message['decision']['decision'].update(evs={'R': -0.5}, margin=0.0)


def wrong_r(message):
    message['decision']['decision']['evs']['R'] = -0.25
    message['decision']['decision']['margin'] = 0.75


def joint_work(message):
    counts = message['work']['state_counts']
    counts['joint_draw'] = counts.pop('root_distribution')


@pytest.mark.parametrize('change', [
    only_r,
    lambda item: item['decision']['decision']['evs'].pop('H'),
    wrong_r,
    lambda item: item['decision']['state']['action_controls'].update(can_surrender=False),
    lambda item: item['decision']['state']['action_controls'].update(can_double=False),
    lambda item: item['decision']['state']['shoe']['counts'].__setitem__(9, 4),
    lambda item: item['decision']['package'].update(version='unrelated'),
    lambda item: item['decision']['model'].update(name='other'),
    lambda item: item['decision']['model'].update(enumeration_state_limit=99999),
    lambda item: item['work'].update(limit=99999),
    lambda item: item['work'].update(attempted_states=True),
    joint_work,
    lambda item: item.update(work=None),
])
def test_incomplete_or_unbound_worker_completion_never_commits(tmp_path, change):
    code, original, _, _ = fixed_message(surrender_request())
    altered = copy.deepcopy(original)
    change(altered)
    source = tmp_path / 'input.json'
    source.write_bytes(calc._json_bytes(surrender_request()))
    with patch.object(calc, 'execute', side_effect=returned(altered, code)), patch.object(
            late_surrender, 'decide', side_effect=AssertionError('parent pricing')):
        receipt = calc._run(source, tmp_path / 'attempt', policy(), threading.Event())
    assert receipt['status'] == 'worker_failed'
    assert receipt['record'] is None
    assert not (tmp_path / 'attempt/result').exists()


def test_parent_tie_rule_does_not_follow_received_ev_key_order():
    code, message, captured, selected = fixed_message(surrender_request(tie=True))
    answer = message['decision']['decision']
    answer['evs'] = dict(reversed(list(answer['evs'].items())))
    with patch.object(late_surrender, 'decide', side_effect=AssertionError('parent pricing')):
        assert validate(message, captured, selected, code)[0] == 'completed'
        answer.update(action='R', action_name='SURRENDER')
        with pytest.raises(ValueError, match='canonical ranking'):
            validate(message, captured, selected, code)


def test_legacy_and_common_worker_routes_remain_distinct():
    with patch.object(record, '_late_surrender_record', side_effect=AssertionError('new model')):
        for value, version in ((legacy_request(), 1), (common_request(), 3)):
            clear_all_caches()
            code, message, captured, selected = fixed_message(value)
            assert code == 0 and message['decision']['schema']['version'] == version
            assert validate(message, captured, selected, code)[0] == 'completed'
