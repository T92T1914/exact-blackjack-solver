"""Request, publication and lifecycle witnesses using retained data and inert faults."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from bj import calculation as calc
from bj import _calculation_process as transport

FIXTURE = Path(__file__).parent / 'fixtures/saved-decision-v1-7a38141.json'


def saved():
    raw = FIXTURE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == (
        '28a9fdc931f8c6fdb19b099218d4204d45522dee86d6b936c6ea7016d648a4f1')
    return json.loads(raw)


def request():
    record = saved()
    state = record['state']
    return {'schema': dict(calc.REQUEST_SCHEMA), 'rules': record['rules'],
            'input': {'cards': state['cards'], 'dealer_up': state['dealer_up'],
                      'unseen_counts': state['shoe']['counts'],
                      'is_split_hand': state['is_split_hand'], 'hand_count': state['hand_count'],
                      'can_double': True, 'can_split': True}}


def policy():
    with patch.object(sys, 'platform', 'linux'):
        return calc._policy(1, None)


def success(payload, *_):
    captured = json.loads(payload)
    message = {'status': 'completed', 'decision': saved(), 'error': None,
               'request_sha256': captured['request_sha256'], 'policy': captured['policy']}
    return {'status': 'returned', 'error': None, 'stdout': calc._json_bytes(message),
            'stderr': b'', 'worker': {'pid': 123, 'returncode': 0},
            'policy_established': True,
            'cleanup': {'retired': True, 'worker_retired': True, 'transport_retired': True,
                        'job_empty': None, 'errors': []}, 'elapsed_seconds': 0.01}


def input_file(tmp_path, value=None):
    path = tmp_path / 'request.json'
    path.write_bytes(calc._json_bytes(request() if value is None else value))
    return path


def run(tmp_path, value=None, worker=success, cancellation=None):
    path = input_file(tmp_path, value)
    with patch.object(calc, 'execute', side_effect=worker), patch.object(
            calc.record, 'best_action', side_effect=AssertionError('parent must not price')):
        result = calc._run(path, tmp_path / 'attempt', policy(),
                           cancellation or threading.Event())
    return result


def test_complete_record_is_committed_separately_from_request_and_receipt(tmp_path):
    result = run(tmp_path)
    assert result['status'] == 'completed'
    directory = tmp_path / 'attempt'
    record = (directory / 'result/decision.json').read_bytes()
    assert json.loads(record) == saved()
    assert result['record']['sha256'] == hashlib.sha256(record).hexdigest()
    assert result['record']['bytes'] == len(record)
    assert json.loads((directory / 'result/receipt.json').read_bytes()) == result
    assert not (directory / 'decision.json').exists()
    assert not (directory / 'pending-result').exists()
    assert json.loads((directory / 'request.json').read_bytes()) == calc._normalise(request())


def test_request_capture_survives_original_replacement_after_dispatch(tmp_path):
    path = input_file(tmp_path)
    original = path.read_bytes()

    def replace_after_capture(payload, *args):
        path.write_bytes(b'not the dispatched request\n')
        return success(payload, *args)

    with patch.object(calc, 'execute', side_effect=replace_after_capture):
        result = calc._run(path, tmp_path / 'attempt', policy(), threading.Event())
    assert result['status'] == 'completed'
    assert (tmp_path / 'attempt/request-source.json').read_bytes() == original
    assert result['source_request'] == {'bytes': len(original), 'complete': True,
                                         'sha256': hashlib.sha256(original).hexdigest()}
    assert json.loads((tmp_path / 'attempt/result/decision.json').read_bytes()) == saved()


@pytest.mark.parametrize('change', [
    lambda item: item.update(decision={'action': 'S'}),
    lambda item: item['input'].update(hand_count=True),
    lambda item: item['input'].update(unseen_counts=[0] * 10),
    lambda item: item['input'].update(can_double=0),
    lambda item: item['rules'].update(peek=False),
    lambda item: item['rules'].update(surrender=True),
    lambda item: item['input'].update(cards=['T', 'T', 'T']),
    lambda item: item['schema'].update(version=True),
])
def test_invalid_modeled_request_refuses_before_worker_and_destination(tmp_path, change):
    item = request()
    change(item)
    path = input_file(tmp_path, item)
    raw = path.read_bytes()
    with patch.object(calc, 'execute') as dispatch, patch.object(
            calc.record, 'best_action', side_effect=AssertionError('must not price')):
        result = calc._run(path, tmp_path / 'attempt', policy(), threading.Event())
    assert result['status'] == 'invalid_request'
    assert result['record'] is None
    assert not dispatch.called
    assert not (tmp_path / 'attempt').exists()
    assert path.read_bytes() == raw


@pytest.mark.parametrize('raw', [b'{"schema":1,"schema":2}', b'\xff', b'[' * 9,
                                b'x' * 65537, b'{"x":NaN}'],
                         ids=['duplicate-key', 'non-utf8', 'depth', 'oversized', 'nonfinite'])
def test_bad_request_representation_refuses_before_worker(tmp_path, raw):
    path = tmp_path / 'request.json'
    path.write_bytes(raw)
    with patch.object(calc, 'execute') as dispatch:
        result = calc._run(path, tmp_path / 'attempt', policy(), threading.Event())
    assert result['status'] == 'invalid_request'
    assert not dispatch.called
    assert not (tmp_path / 'attempt').exists()


def test_normalisation_preserves_order_and_retained_counts_without_pricing():
    item = request()
    item['input'].update(cards=['a', 'T'], is_split_hand=True, hand_count=2)
    item['rules']['blackjack_payout'] = 1.25
    item['input']['can_split'] = False
    with patch.object(calc.record, 'best_action', side_effect=AssertionError('must not price')):
        captured = calc._normalise(item)
    assert captured['input']['cards'] == ['A', 'T']
    assert captured['input']['unseen_counts'] == item['input']['unseen_counts']
    assert captured['input']['hand_count'] == 2
    assert captured['input']['can_split'] is False
    assert captured['rules']['blackjack_payout'] == 1.25


def test_prior_attempt_and_result_are_preserved(tmp_path):
    path = input_file(tmp_path)
    directory = tmp_path / 'attempt'
    directory.mkdir()
    earlier = directory / 'decision.json'
    earlier.write_bytes(b'earlier completed bytes\n')
    with patch.object(calc, 'execute') as dispatch:
        result = calc._run(path, directory, policy(), threading.Event())
    assert result['status'] == 'delivery_failed'
    assert not dispatch.called
    assert earlier.read_bytes() == b'earlier completed bytes\n'
    assert sorted(p.name for p in directory.iterdir()) == ['decision.json']


@pytest.mark.parametrize('phase', ['decision.json', 'receipt.json', 'rename'])
def test_publication_failure_never_exposes_completed_result(tmp_path, phase):
    original_write = calc._exclusive_bytes

    def fail_selected(path, raw):
        if path.parent.name == 'pending-result' and path.name == phase:
            raise OSError('controlled complete-file delivery refusal')
        return original_write(path, raw)

    with patch.object(calc, '_exclusive_bytes', side_effect=fail_selected), patch.object(
            calc.os, 'rename', side_effect=OSError('controlled commit refusal')
            if phase == 'rename' else os.rename):
        result = run(tmp_path)
    assert result['status'] == 'delivery_failed'
    assert result['record'] is None
    assert not (tmp_path / 'attempt/result').exists()
    outcome = json.loads((tmp_path / 'attempt/outcome.json').read_bytes())
    assert outcome['status'] == 'delivery_failed'


@pytest.mark.parametrize('failure', ['short', 'flush', 'close'])
def test_completed_candidate_file_failure_cannot_commit_result(tmp_path, failure):
    original_open = Path.open
    closed = []

    class RefusingFile:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def write(self, raw):
            count = self.stream.write(raw)
            return count - 1 if failure == 'short' else count

        def flush(self):
            self.stream.flush()
            if failure == 'flush':
                raise OSError('controlled candidate flush refusal')

        def __exit__(self, *args):
            self.stream.close()
            closed.append(self.stream.closed)
            if failure == 'close':
                raise OSError('controlled candidate close refusal')

    def selected_open(path, *args, **kwargs):
        stream = original_open(path, *args, **kwargs)
        if path.parent.name == 'pending-result' and path.name == 'decision.json':
            return RefusingFile(stream)
        return stream

    with patch.object(Path, 'open', selected_open):
        result = run(tmp_path)
    assert result['status'] == 'delivery_failed'
    assert result['record'] is None
    assert closed == [True]
    assert not (tmp_path / 'attempt/result').exists()
    outcome = json.loads((tmp_path / 'attempt/outcome.json').read_bytes())
    assert outcome['status'] == 'delivery_failed'


def test_cancellation_observed_before_commit_wins_over_finished_child(tmp_path):
    cancellation = threading.Event()
    original_write = calc._exclusive_bytes

    def cancel_after_staging(path, raw):
        original_write(path, raw)
        if path.parent.name == 'pending-result' and path.name == 'receipt.json':
            cancellation.set()

    with patch.object(calc, '_exclusive_bytes', side_effect=cancel_after_staging):
        result = run(tmp_path, cancellation=cancellation)
    assert result['status'] == 'cancelled'
    assert result['record'] is None
    assert not (tmp_path / 'attempt/result').exists()
    assert (tmp_path / 'attempt/pending-result').is_dir()


def test_cancellation_after_commit_does_not_relabel_completed_record(tmp_path):
    cancellation = threading.Event()
    original_rename = os.rename

    def commit_then_cancel(source, target):
        original_rename(source, target)
        cancellation.set()

    with patch.object(calc.os, 'rename', side_effect=commit_then_cancel):
        result = run(tmp_path, cancellation=cancellation)
    assert result['status'] == 'completed'
    assert json.loads((tmp_path / 'attempt/result/receipt.json').read_bytes()) == result


def test_identity_changed_worker_output_is_not_a_record(tmp_path):
    def changed_identity(payload, *args):
        result = success(payload, *args)
        message = json.loads(result['stdout'])
        message['decision']['state']['shoe']['counts'][1] += 1
        result['stdout'] = calc._json_bytes(message)
        return result

    result = run(tmp_path, worker=changed_identity)
    assert result['status'] == 'worker_failed'
    assert not (tmp_path / 'attempt/result').exists()


@pytest.mark.parametrize('change', [
    lambda item: item.update(stdout=item['stdout'][:-1]),
    lambda item: item.update(stdout=b'{"incomplete":\n'),
    lambda item: item['worker'].update(returncode=1),
])
def test_incomplete_message_or_nonordinary_exit_cannot_publish_record(tmp_path, change):
    def incomplete(payload, *args):
        result = success(payload, *args)
        change(result)
        return result

    result = run(tmp_path, worker=incomplete)
    assert result['status'] == 'worker_failed'
    assert result['record'] is None
    assert not (tmp_path / 'attempt/result').exists()


@pytest.mark.parametrize('status,code', [('resource_limited', 4), ('calculation_error', 5),
                                       ('worker_failed', 6)])
def test_reported_failure_remains_distinct_and_has_no_decision(tmp_path, status, code):
    def failed(payload, *args):
        result = success(payload, *args)
        message = json.loads(result['stdout'])
        message.update(status=status, decision=None,
                       error={'type': 'ControlledFault', 'message': 'constructed evidence'})
        result['stdout'], result['worker']['returncode'] = calc._json_bytes(message), code
        return result

    result = run(tmp_path, worker=failed)
    assert result['status'] == status
    assert result['record'] is None
    assert not (tmp_path / 'attempt/result').exists()


def test_unresolved_cleanup_withholds_an_otherwise_complete_decision(tmp_path):
    def pending_cleanup(payload, *args):
        result = success(payload, *args)
        result['cleanup'].update(retired=False, worker_retired=False,
                                 errors=['controlled cleanup refusal'])
        return result

    result = run(tmp_path, worker=pending_cleanup)
    assert result['status'] == 'cleanup_failed'
    assert result['cleanup']['retired'] is False
    assert result['record'] is None
    assert not (tmp_path / 'attempt/result').exists()


def test_complete_message_without_established_policy_is_withheld(tmp_path):
    def unestablished(payload, *args):
        result = success(payload, *args)
        result['policy_established'] = False
        return result

    result = run(tmp_path, worker=unestablished)
    assert result['status'] == 'unsupported_policy'
    assert result['record'] is None
    assert not (tmp_path / 'attempt/result').exists()


def test_cancelled_outcome_keeps_unresolved_retirement_visible(tmp_path):
    def failed_retirement(payload, *args):
        result = success(payload, *args)
        result.update(status='cancelled', stdout=b'')
        result['cleanup'].update(retired=False, worker_retired=False,
                                 errors=['controlled retirement refusal'])
        return result

    result = run(tmp_path, worker=failed_retirement)
    assert result['status'] == 'cancelled'
    assert result['cleanup']['retired'] is False
    assert result['cleanup']['errors'] == ['controlled retirement refusal']
    assert result['record'] is None
    assert not (tmp_path / 'attempt/result').exists()


def test_linux_hard_memory_request_refuses_before_dispatch():
    with patch.object(sys, 'platform', 'linux'):
        with pytest.raises(NotImplementedError, match='hard memory'):
            calc._policy(30, 256)
        assert calc._policy(30, None)['memory']['mode'] == 'uncapped'


def test_windows_declares_committed_memory_not_rss():
    with patch.object(sys, 'platform', 'win32'):
        selected = calc._policy(30, None)
    assert selected['memory']['bytes'] == 256 * 1024 * 1024
    assert selected['memory']['mode'] == 'windows_job_commit'
    assert 'not physical RSS' in selected['memory']['meaning']
    assert selected['algorithmic_work_limit'] is None


class Stream:
    def __init__(self, fail=None):
        self.buffer = self
        self.bytes = bytearray()
        self.closed = False
        self.fail = fail

    def write(self, raw):
        if isinstance(raw, str):
            raw = raw.encode()
        self.bytes.extend(raw)
        return len(raw) - 1 if self.fail == 'short' else len(raw)

    def flush(self):
        if self.fail == 'flush':
            raise OSError('controlled flush refusal')

    def close(self):
        self.closed = True
        if self.fail == 'close':
            raise OSError('controlled close refusal')


@pytest.mark.parametrize('failure', ['short', 'flush'])
def test_command_report_delivery_refusal_returns_8_and_retires_stdout(failure):
    output, error = Stream(failure), Stream()
    with patch.object(sys, 'platform', 'linux'), patch.object(sys, 'stdout', output), patch.object(
            sys, 'stderr', error), patch.object(calc, '_run', return_value={'status': 'completed'}):
        code = calc.main(['request.json', '--output-dir', 'new-attempt'])
    assert code == 8
    assert output.closed


def test_actual_transport_timeout_and_following_small_use(tmp_path):
    original_popen = subprocess.Popen

    def fixture_command(command, **options):
        assert command[-2:] == ['-m', 'bj._calculation_worker']
        code = 'import sys,time;sys.stdin.buffer.read();time.sleep(20)'
        return original_popen([sys.executable, '-I', '-B', '-c', code], **options)

    selected = policy()
    selected['wall_seconds'] = 0.1
    with patch.object(transport.subprocess, 'Popen', side_effect=fixture_command):
        result = transport.execute(b'{}\n', selected, tmp_path, threading.Event())
    assert result['status'] == 'timed_out'
    assert result['worker']['pid'] > 0
    assert result['cleanup']['retired']

    def small_command(command, **options):
        code = 'import sys;sys.stdin.buffer.read();sys.stdout.buffer.write(b"complete\\n")'
        return original_popen([sys.executable, '-I', '-B', '-c', code], **options)

    with patch.object(transport.subprocess, 'Popen', side_effect=small_command):
        following = transport.execute(b'{}\n', policy(), tmp_path, threading.Event())
    assert following['status'] == 'returned'
    assert following['stdout'] == b'complete\n'
    assert following['cleanup']['retired']


def test_actual_transport_explicit_cancellation_retires_owned_child(tmp_path):
    original_popen = subprocess.Popen
    cancellation = threading.Event()
    ready = tmp_path / 'worker-ready'

    def fixture_command(command, **options):
        code = ('import pathlib,sys,time;sys.stdin.buffer.read();'
                f'pathlib.Path({str(ready)!r}).write_text("ready");time.sleep(20)')
        return original_popen([sys.executable, '-I', '-B', '-c', code], **options)

    def cancel_ready():
        import time
        deadline = time.monotonic() + 2
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        cancellation.set()

    observer = threading.Thread(target=cancel_ready)
    selected = policy()
    selected['wall_seconds'] = 3
    observer.start()
    try:
        with patch.object(transport.subprocess, 'Popen', side_effect=fixture_command):
            result = transport.execute(b'{}\n', selected, tmp_path, cancellation)
    finally:
        observer.join(timeout=3)
    assert ready.exists(), 'controlled child never reached its intentional long-running state'
    assert result['status'] == 'cancelled'
    assert result['cleanup']['retired']
    assert not observer.is_alive()


def test_windows_policy_creation_refusal_never_launches_worker(tmp_path):
    selected = copy.deepcopy(policy())
    selected['memory'] = {'mode': 'windows_job_commit', 'bytes': 256 * 1024 * 1024}
    with patch.object(transport, '_WindowsJob', side_effect=OSError('controlled Job refusal')):
        with patch.object(transport.subprocess, 'Popen') as launch:
            result = transport.execute(b'{}\n', selected, tmp_path, threading.Event())
    assert result['status'] == 'unsupported_policy'
    assert result['cleanup']['retired']
    assert result['policy_established'] is False
    assert not launch.called


def test_assignment_refusal_keeps_input_gate_closed_and_retires_child(tmp_path):
    original_popen = subprocess.Popen
    gate = tmp_path / 'input-gate-opened'

    class RefusedJob:
        closed = False

        def assign(self, process):
            raise OSError('controlled assignment refusal')

        def close(self):
            self.closed = True

    job = RefusedJob()

    def gated_command(command, **options):
        code = ('import pathlib,sys;data=sys.stdin.buffer.read();'
                f'pathlib.Path({str(gate)!r}).write_bytes(data) if data else None')
        return original_popen([sys.executable, '-I', '-B', '-c', code], **options)

    selected = copy.deepcopy(policy())
    selected['memory'] = {'mode': 'windows_job_commit', 'bytes': 256 * 1024 * 1024}
    with patch.object(transport, '_WindowsJob', return_value=job), patch.object(
            transport.subprocess, 'Popen', side_effect=gated_command):
        result = transport.execute(b'captured modeled input\n', selected, tmp_path,
                                   threading.Event())
    assert result['status'] == 'unsupported_policy'
    assert result['worker']['pid'] > 0
    assert result['cleanup']['retired']
    assert result['policy_established'] is False
    assert not gate.exists()
    assert job.closed


def test_actual_transport_overflow_is_bounded_and_retires_owned_child(tmp_path):
    original_popen = subprocess.Popen

    def overflowing_command(command, **options):
        code = ('import sys,time;sys.stdin.buffer.read();'
                'sys.stdout.buffer.write(b"x"*73728);sys.stdout.buffer.flush();time.sleep(20)')
        return original_popen([sys.executable, '-I', '-B', '-c', code], **options)

    selected = policy()
    selected['wall_seconds'] = 3
    with patch.object(transport.subprocess, 'Popen', side_effect=overflowing_command):
        result = transport.execute(b'{}\n', selected, tmp_path, threading.Event())
    assert result['status'] == 'resource_limited'
    assert len(result['stdout']) == transport.MAX_STREAM_BYTES
    assert result['cleanup']['retired']


def test_cancellation_before_start_does_not_launch_worker(tmp_path):
    cancellation = threading.Event()
    cancellation.set()
    with patch.object(transport.subprocess, 'Popen') as launch:
        result = transport.execute(b'{}\n', policy(), tmp_path, cancellation)
    assert result['status'] == 'cancelled'
    assert result['worker']['pid'] is None
    assert result['policy_established'] is False
    assert result['cleanup']['retired']
    assert not launch.called
