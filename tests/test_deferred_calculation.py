"""Captured requests and complete publication for the deferred dealer family."""
from __future__ import annotations

import copy
import hashlib
import json
import threading
from dataclasses import asdict
from unittest.mock import patch

import pytest

from bj import calculation as calc, deferred_second_card as deferred, record
from bj.core import Rules


def request(counts=None):
    return {'schema': dict(calc.DEFERRED_REQUEST_SCHEMA),
            'rules': asdict(Rules(peek=False, max_hands=1, resplit_aces=False)),
            'input': {'cards': ['9', '2'], 'dealer_up': 'T',
                      'unseen_counts': counts or [1, 0, 0, 0, 0, 0, 0, 0, 0, 2],
                      'is_split_hand': False, 'hand_count': 1,
                      'can_double': True, 'can_split': False},
            'model': dict(deferred.MODEL),
            'limits': {'max_states': 100000, 'max_seconds': 10.0}}


def completed_message(captured, policy):
    inputs = captured['input']
    decision, work = record._deferred_second_card_record(
        inputs['cards'], inputs['dealer_up'], Rules(**captured['rules']),
        shoe=inputs['unseen_counts'], can_double=inputs['can_double'], can_split=False,
        **captured['limits'])
    return {'status': 'completed', 'decision': decision, 'work': work, 'error': None,
            'request_sha256': hashlib.sha256(calc._json_bytes(captured)).hexdigest(),
            'policy': policy}


def policy(captured):
    with patch.object(calc.sys, 'platform', 'linux'):
        return calc._request_policy(calc._policy(1, None), captured)


@pytest.mark.parametrize('change', [
    lambda value: value['rules'].update(peek=True),
    lambda value: value['rules'].update(surrender=True),
    lambda value: value['input'].update(can_split=True),
    lambda value: value['input'].update(is_split_hand=True),
    lambda value: value['input'].update(cards=['A', 'T']),
    lambda value: value['input'].update(hand_count=True),
    lambda value: value['input'].update(unseen_counts=[0] * 10),
    lambda value: value['limits'].update(max_seconds=True),
    lambda value: value['limits'].update(max_seconds=10.1),
    lambda value: value['limits'].update(max_states=100001),
])
def test_invalid_new_family_refuses_before_dispatch(tmp_path, change):
    value = request()
    change(value)
    source = tmp_path / 'request.json'
    source.write_bytes(calc._json_bytes(value))
    with patch.object(calc, 'execute') as dispatch:
        result = calc._run(source, tmp_path / 'attempt', {}, threading.Event())
    assert result['status'] == 'invalid_request'
    assert result['record'] is None and not dispatch.called
    assert not (tmp_path / 'attempt').exists()


def test_new_capture_keeps_counts_and_all_natural_rank_stock():
    value = request([1, 0, 0, 0, 0, 0, 0, 0, 0, 0])
    captured = calc._normalise(value)
    assert captured['input']['unseen_counts'] == value['input']['unseen_counts']
    message = completed_message(captured, policy(captured))
    assert message['decision']['decision']['evs'] == {'S': -1.0}
    assert message['decision']['decision']['margin'] is None
    status, raw, error, work = calc._validated_decision(
        calc._json_bytes(message), captured, message['request_sha256'], 0, message['policy'])
    assert status == 'completed' and error is None
    assert json.loads(raw)['state']['shoe']['includes_hidden_hole'] is False
    assert work['cache_retired'] is True


@pytest.mark.parametrize('change', [
    lambda message: message['work'].update(cache_retired=False),
    lambda message: message['work'].update(max_seconds=9.0),
    lambda message: message['work'].update(elapsed_seconds=10.1),
    lambda message: message['work']['state_counts'].update(joint_play=1),
    lambda message: message['work'].update(attempted_states=True),
    lambda message: message['decision']['state']['shoe'].update(includes_hidden_hole=True),
    lambda message: message['decision']['model'].update(enumeration_state_limit=1),
    lambda message: message['decision']['decision']['evs'].pop('D'),
])
def test_complete_worker_claim_cannot_escape_captured_contract(change):
    captured = calc._normalise(request())
    message = completed_message(captured, policy(captured))
    change(message)
    with pytest.raises(ValueError):
        calc._validated_decision(calc._json_bytes(message), captured,
                                 message['request_sha256'], 0, message['policy'])


def test_capture_replacement_publishes_original_and_retired_work(tmp_path):
    source = tmp_path / 'source.json'
    original = calc._json_bytes(request())
    source.write_bytes(original)
    captured = calc._normalise(request())
    selected_policy = policy(captured)
    message = completed_message(captured, selected_policy)

    def completed(payload, *unused):
        source.write_bytes(b'replaced after capture\n')
        assert json.loads(payload)['request'] == captured
        return {'status': 'returned', 'error': None, 'stdout': calc._json_bytes(message),
                'stderr': b'', 'worker': {'pid': 123, 'returncode': 0},
                'policy_established': True, 'elapsed_seconds': 0.01,
                'cleanup': {'retired': True, 'worker_retired': True,
                            'transport_retired': True, 'job_empty': None, 'errors': []}}

    with patch.object(calc, 'execute', side_effect=completed):
        result = calc._run(source, tmp_path / 'attempt', selected_policy, threading.Event())
    assert result['status'] == 'completed'
    assert (tmp_path / 'attempt/request-source.json').read_bytes() == original
    assert json.loads((tmp_path / 'attempt/result/decision.json').read_bytes()) == (
        message['decision'])
    assert result['work'] == message['work']


@pytest.mark.parametrize('error_type,status,elapsed', [
    ('DeferredTimeLimitExceeded', 'resource_limited', 0.5),
    ('UnsupportedContinuation', 'resource_limited', 11.0),
    ('EnumerationLimitExceeded', 'calculation_error', 11.0),
])
def test_typed_refusal_requires_its_truthful_outcome(error_type, status, elapsed):
    captured = calc._normalise(request())
    message = completed_message(captured, policy(captured))
    message.update(status=status, decision=None, error={'type': error_type, 'message': 'refused'})
    message['work'] = copy.deepcopy(message['work'])
    message['work']['elapsed_seconds'] = elapsed
    with pytest.raises(ValueError):
        calc._validated_decision(calc._json_bytes(message), captured,
                                 message['request_sha256'], calc.EXIT_STATUSES[status],
                                 message['policy'])
