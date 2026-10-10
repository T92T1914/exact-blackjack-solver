"""New request/model binding and fixed-worker outcomes through existing delivery."""
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

from bj import calculation as calc, common_shoe, record
from bj import _calculation_worker as worker
from bj.caches import clear_all_caches
from test_calculation import policy, request


def common_request(limit=100000):
    value = request()
    value['schema'] = dict(calc.COMMON_REQUEST_SCHEMA)
    value['rules'].update(max_hands=2, resplit_aces=False, hit_split_aces=False)
    value['input'].update(cards=['T', 'T'], dealer_up='7',
                           unseen_counts=[1] + [0] * 8 + [5])
    value.update(model=dict(common_shoe.MODEL), limits={'max_states': limit})
    return value


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


def test_request_normalization_and_policy_are_explicit_and_nonpricing():
    value = common_request(50)
    with patch.object(common_shoe, 'decide', side_effect=AssertionError('must not price')):
        captured = calc._normalise(value)
    assert captured['input']['unseen_counts'] == value['input']['unseen_counts']
    assert captured['limits'] == {'max_states': 50}
    selected = calc._request_policy(policy(), captured)
    assert selected['algorithmic_work_limit']['max_states'] == 50
    assert selected['algorithmic_work_limit']['name'] == 'whole_request_uncached_enumeration_states'
    assert policy()['algorithmic_work_limit'] is None


@pytest.mark.parametrize('change', [
    lambda item: item['model'].update(name='other'),
    lambda item: item['model'].update(version=True),
    lambda item: item['limits'].update(max_states=True),
    lambda item: item['limits'].update(max_states=100001),
    lambda item: item['rules'].update(max_hands=4),
    lambda item: item['rules'].update(resplit_aces=True),
    lambda item: item['rules'].update(hit_split_aces=True),
    lambda item: item['input'].update(cards=['T', '9']),
    lambda item: item['input'].update(is_split_hand=True, hand_count=2),
    lambda item: item['input'].update(unseen_counts=[0] * 9 + [21]),
    lambda item: item.pop('limits'),
    lambda item: item.pop('schema'),
])
def test_common_domain_refuses_before_dispatch_or_attempt(tmp_path, change):
    value = common_request()
    change(value)
    source = tmp_path / 'input.json'
    source.write_bytes(calc._json_bytes(value))
    with patch.object(calc, 'execute') as dispatch:
        result = calc._run(source, tmp_path / 'attempt', policy(), threading.Event())
    assert result['status'] == 'invalid_request'
    assert result['record'] is None
    assert not dispatch.called
    assert not (tmp_path / 'attempt').exists()


def test_fixed_worker_completion_and_whole_root_state_refusal():
    clear_all_caches()
    code, message, captured, selected = fixed_message(common_request())
    assert code == 0 and message['status'] == 'completed'
    assert message['decision']['schema']['version'] == 3
    assert message['decision']['decision']['evs']['P'] == 2
    calc._validated_decision(calc._json_bytes(message), captured,
                             message['request_sha256'], code, selected)
    clear_all_caches()
    code, refused, captured, selected = fixed_message(common_request(1))
    assert code == 4 and refused['status'] == 'resource_limited'
    assert refused['decision'] is None
    assert refused['error']['type'] == 'EnumerationLimitExceeded'
    assert refused['work'] == {'limit': 1, 'states': 1, 'attempted_states': 2,
                               'state_counts': {'root_distribution': 1}}
    calc._validated_decision(calc._json_bytes(refused), captured,
                             refused['request_sha256'], code, selected)
    clear_all_caches()


def test_complete_common_message_commits_without_parent_pricing(tmp_path):
    clear_all_caches()
    code, message, _, _ = fixed_message(common_request())
    value = common_request()
    source = tmp_path / 'input.json'
    source.write_bytes(calc._json_bytes(value))

    def returned(payload, *_):
        captured = json.loads(payload)
        output = {**message, 'request_sha256': captured['request_sha256'],
                  'policy': captured['policy']}
        return {'status': 'returned', 'error': None, 'stdout': calc._json_bytes(output),
                'stderr': b'', 'worker': {'pid': 123, 'returncode': code},
                'policy_established': True,
                'cleanup': {'retired': True, 'worker_retired': True, 'transport_retired': True,
                            'job_empty': None, 'errors': []}, 'elapsed_seconds': 0.01}

    with patch.object(calc, 'execute', side_effect=returned), patch.object(
            common_shoe, 'decide', side_effect=AssertionError('parent must not price')):
        result = calc._run(source, tmp_path / 'attempt', policy(), threading.Event())
    assert result['status'] == 'completed'
    assert result['work'] == message['work']
    assert result['work']['states'] == sum(result['work']['state_counts'].values())
    assert json.loads((tmp_path / 'attempt/result/receipt.json').read_bytes()) == result
    committed = json.loads((tmp_path / 'attempt/result/decision.json').read_bytes())
    assert committed == message['decision']
    clear_all_caches()


@pytest.mark.parametrize('change', [
    lambda item: item['decision']['model'].update(enumeration_state_limit=99999),
    lambda item: item['decision'].update(schema={'name': 'blackjack-decision', 'version': 2}),
    lambda item: item['work'].update(limit=99999),
    lambda item: item['work'].update(attempted_states=True),
    lambda item: item['work']['state_counts'].update(unknown=1),
    lambda item: item.update(work=None),
])
def test_model_limit_and_work_diagnostics_cannot_change_completed_request(change):
    clear_all_caches()
    code, message, captured, selected = fixed_message(common_request())
    altered = copy.deepcopy(message)
    change(altered)
    with patch.object(common_shoe, 'decide', side_effect=AssertionError('must not price')):
        with pytest.raises(ValueError):
            calc._validated_decision(calc._json_bytes(altered), captured,
                                     message['request_sha256'], code, selected)
    clear_all_caches()


def test_legacy_request_shape_and_record_identity_stay_legacy():
    captured = calc._normalise(request())
    assert captured == request()
    assert calc._request_policy(policy(), captured)['algorithmic_work_limit'] is None
    with patch.object(record, '_common_shoe_record', side_effect=AssertionError('common route')):
        code, message, _, _ = fixed_message(request())
    assert code == 0 and message['decision']['schema']['version'] == 1
    assert 'work' not in message
