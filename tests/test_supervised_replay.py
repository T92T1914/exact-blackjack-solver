"""Captured-record identity, exact comparison and owned publication boundaries."""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from bj import _calculation_process as transport
from bj import _replay_worker as worker
from bj import calculation as calc
from bj import ev
from bj.core import Rules
from bj import replay
from bj import supervised_replay as protected

FIXTURE = Path(__file__).parent / 'fixtures/saved-decision-v1-7a38141.json'


def saved():
    raw = FIXTURE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == (
        '28a9fdc931f8c6fdb19b099218d4204d45522dee86d6b936c6ea7016d648a4f1')
    return json.loads(raw)


def policy():
    with patch.object(sys, 'platform', 'linux'):
        return calc._policy(1, None)


def message(payload, directory):
    envelope = json.loads(payload)
    with Path(envelope['record_path']).open('rb') as stream:
        raw = stream.read(replay.MAX_RECORD_BYTES + 1)
    calc._exclusive_bytes(directory / 'record-source.json', raw)
    source = json.loads(raw) if len(raw) <= replay.MAX_RECORD_BYTES else None
    current = saved()['decision']
    if source is None:
        report = replay._failure('invalid_input', ValueError('record exceeds 65536 bytes'))
    else:
        comparison = replay._compare(source['decision'], current)
        agreement = (comparison['legal_actions']['matches'] and comparison['evs_match']
                     and comparison['recommendation']['matches']
                     and comparison['margin']['matches'])
        report = replay._report('agreement' if agreement else 'differences', saved=source,
                                recomputed=current, comparison=comparison)
    return {'operation': protected.OPERATION, 'record_path': envelope['record_path'],
            'source_record': protected._source(raw),
            'policy': envelope['policy'], 'report': report, 'error': None}


def returned(value):
    delivery = (value.get('error') or {}).get('type') == 'CapturedRecordDelivery'
    status = (value['report']['status'] if value['report'] else
              'delivery_failed' if delivery else 'resource_limited')
    return {'status': 'returned', 'error': None, 'stdout': calc._json_bytes(value),
            'stderr': b'', 'worker': {'pid': 123, 'returncode': protected.EXIT_STATUSES[status]},
            'policy_established': True, 'elapsed_seconds': 0.01,
            'cleanup': {'retired': True, 'worker_retired': True, 'transport_retired': True,
                        'job_empty': None, 'errors': []}}


def success(payload, selected_policy, directory, cancellation, **options):
    assert options == {'worker': protected.WORKER}
    assert json.loads(payload)['policy'] == selected_policy
    return returned(message(payload, directory))


def run(tmp_path, value=None, dispatch=success, cancellation=None):
    path = tmp_path / 'source.json'
    raw = FIXTURE.read_bytes() if value is None else calc._json_bytes(value)
    path.write_bytes(raw)
    with patch.object(protected, 'execute', side_effect=dispatch), patch.object(
            replay, 'replay_json', side_effect=AssertionError('parent must not replay')):
        result = protected._run(path, tmp_path / 'attempt', policy(),
                                cancellation or threading.Event())
    assert path.read_bytes() == raw
    return result


def test_complete_comparison_preserves_source_and_separate_report(tmp_path):
    result = run(tmp_path)
    assert result['status'] == result['replay_status'] == 'agreement'
    directory = tmp_path / 'attempt'
    raw = (directory / 'record-source.json').read_bytes()
    assert raw == FIXTURE.read_bytes()
    assert result['source_record'] == protected._source(raw)
    assert result['capture_verified'] is True
    report = (directory / 'result/replay.json').read_bytes()
    assert result['report'] == {'path': 'result/replay.json', 'bytes': len(report),
                                'sha256': hashlib.sha256(report).hexdigest()}
    assert json.loads((directory / 'result/receipt.json').read_bytes()) == result
    assert json.loads(report)['recorded'] == saved()['decision']
    assert not (directory / 'result/decision.json').exists()
    assert not (directory / 'pending-result').exists()


@pytest.mark.parametrize('change', [
    lambda value: value['decision']['evs'].update(
        S=math.nextafter(value['decision']['evs']['S'], math.inf)),
    lambda value: value['decision']['evs'].pop('D'),
    lambda value: value['decision'].update(margin=99.0),
    lambda value: value['decision'].update(action='S', action_name='STAND', margin=0),
])
def test_altered_answers_are_complete_differences_not_calculation_requests(tmp_path, change):
    value = saved()
    change(value)
    result = run(tmp_path, value)
    assert result['status'] == result['replay_status'] == 'differences'
    report = json.loads((tmp_path / 'attempt/result/replay.json').read_bytes())
    assert report['recorded'] == value['decision']
    assert report['recomputed'] == saved()['decision']
    assert report['comparison'] == replay._compare(value['decision'], saved()['decision'])


def test_immutable_capture_survives_original_replacement(tmp_path):
    path = tmp_path / 'source.json'
    raw = FIXTURE.read_bytes()
    path.write_bytes(raw)

    def replacement(payload, *args, **options):
        result = success(payload, *args, **options)
        path.write_bytes(b'replaced after capture\n')
        return result

    with patch.object(protected, 'execute', side_effect=replacement):
        result = protected._run(path, tmp_path / 'attempt', policy(), threading.Event())
    assert result['status'] == 'agreement'
    assert (tmp_path / 'attempt/record-source.json').read_bytes() == raw
    assert result['source_record'] == protected._source(raw)
    assert path.read_bytes() == b'replaced after capture\n'


def test_parent_parsing_occurs_only_after_verified_retirement(tmp_path):
    parse = replay._parse
    retired = False

    def dispatch(payload, *args, **options):
        nonlocal retired
        result = success(payload, *args, **options)
        retired = True
        return result

    def after_retirement(raw):
        assert retired
        return parse(raw)

    with patch.object(replay, '_parse', side_effect=after_retirement):
        assert run(tmp_path, dispatch=dispatch)['status'] == 'agreement'


def test_oversized_source_is_captured_only_in_worker_without_full_file_digest(tmp_path):
    path = tmp_path / 'source.json'
    path.write_bytes(b' ' * (replay.MAX_RECORD_BYTES + 20))
    with patch.object(protected, 'execute', side_effect=success):
        result = protected._run(path, tmp_path / 'attempt', policy(), threading.Event())
    assert result['status'] == 'invalid_input'
    assert result['source_record'] == protected._source(b' ' * (replay.MAX_RECORD_BYTES + 1))
    assert result['source_record']['complete'] is False
    assert result['capture_verified'] is True
    assert len((tmp_path / 'attempt/record-source.json').read_bytes()) == 65537
    assert not (tmp_path / 'attempt/result').exists()


def test_parent_never_opens_original_and_reads_capture_only_after_retirement(tmp_path):
    capture = protected._capture
    observed, retired = [], False

    def dispatch(payload, *args, **options):
        nonlocal retired
        result = success(payload, *args, **options)
        retired = True
        return result

    def owned_capture(path, cancellation):
        assert retired
        observed.append(path)
        assert path == tmp_path / 'attempt/record-source.json'
        return capture(path, cancellation)

    with patch.object(protected, '_capture', side_effect=owned_capture):
        assert run(tmp_path, dispatch=dispatch)['status'] == 'agreement'
    assert observed == [tmp_path / 'attempt/record-source.json']


@pytest.mark.parametrize('status', ['timed_out', 'cancelled', 'worker_failed'])
def test_capture_did_not_complete_has_no_parent_read_or_verified_identity(tmp_path, status):
    def stopped(payload, selected_policy, directory, cancellation, **options):
        # A contained worker can leave a partial diagnostic artifact before retirement.
        calc._exclusive_bytes(directory / 'record-source.json', b'partial')
        value = returned({'report': None, 'operation': protected.OPERATION})
        value.update(status=status, stdout=b'')
        return value

    with patch.object(protected, '_capture', side_effect=AssertionError('no capture read')):
        result = run(tmp_path, dispatch=stopped)
    assert result['status'] == status and result['source_record'] is None
    assert result['capture_verified'] is False and result['report'] is None
    assert not (tmp_path / 'attempt/result').exists()


@pytest.mark.parametrize('delivery', [False, True])
def test_contained_capture_refusal_has_no_parent_artifact_read_or_result(tmp_path, delivery):
    def refused(payload, selected_policy, directory, cancellation, **options):
        envelope = json.loads(payload)
        value = {'operation': protected.OPERATION, 'record_path': envelope['record_path'],
                 'source_record': None, 'policy': selected_policy, 'error': None,
                 'report': replay._failure('io_error', OSError('controlled file lookup'))}
        if delivery:
            calc._exclusive_bytes(directory / 'record-source.json', b'partial')
            value.update(report=None, error={'type': 'CapturedRecordDelivery', 'message': 'write'})
        return returned(value)

    with patch.object(protected, '_capture', side_effect=AssertionError('no artifact read')):
        result = run(tmp_path, dispatch=refused)
    assert result['status'] == ('delivery_failed' if delivery else 'io_error')
    assert result['source_record'] is None and result['capture_verified'] is False
    assert result['report'] is None and not (tmp_path / 'attempt/result').exists()


def test_changed_captured_artifact_does_not_match_worker_identity(tmp_path):
    def changed(payload, selected_policy, directory, cancellation, **options):
        value = success(payload, selected_policy, directory, cancellation, **options)
        (directory / 'record-source.json').write_bytes(b'changed artifact\n')
        return value

    result = run(tmp_path, dispatch=changed)
    assert result['status'] == 'worker_failed' and result['report'] is None
    assert result['source_record'] is None and result['capture_verified'] is False
    assert not (tmp_path / 'attempt/result').exists()


def test_nonregular_source_and_descriptor_identity_change_refuse(tmp_path):
    with pytest.raises(ValueError):
        protected._capture(tmp_path, threading.Event())
    path = tmp_path / 'source.json'
    path.write_bytes(FIXTURE.read_bytes())
    observed = path.stat()
    changed = SimpleNamespace(st_mode=observed.st_mode, st_dev=observed.st_dev,
                              st_ino=observed.st_ino + 1)
    with patch.object(protected.os, 'fstat', return_value=changed):
        with pytest.raises(ValueError, match='identity'):
            protected._capture(path, threading.Event())


def test_pre_capture_cancellation_never_opens_source_or_launches(tmp_path):
    cancellation = threading.Event()
    cancellation.set()
    with patch.object(protected.os, 'open', side_effect=AssertionError('no open')), patch.object(
            protected, 'execute', side_effect=AssertionError('no worker')):
        result = protected._run('not-read', tmp_path / 'attempt', policy(), cancellation)
    assert result['status'] == 'cancelled'
    assert result['worker']['pid'] is None
    assert not (tmp_path / 'attempt').exists()


def test_input_link_refuses_without_reading_target(tmp_path):
    path = tmp_path / 'target.json'
    path.write_bytes(FIXTURE.read_bytes())
    link = tmp_path / 'link.json'
    try:
        link.symlink_to(path)
    except OSError as exc:
        pytest.skip(f'host does not permit disposable symlinks: {exc}')
    with patch.object(protected.os, 'open', side_effect=AssertionError('no target read')):
        with pytest.raises(ValueError, match='ordinary'):
            protected._capture(link, threading.Event())


@pytest.mark.skipif(os.name == 'nt', reason='POSIX FIFO replacement uses nonblocking open')
def test_regular_to_fifo_open_race_cannot_block_capture(tmp_path):
    path = tmp_path / 'source.json'
    path.write_bytes(b'original')
    open_descriptor = os.open

    def replace_then_open(value, flags):
        assert flags & os.O_NONBLOCK and flags & os.O_NOFOLLOW
        path.unlink()
        os.mkfifo(path)
        return open_descriptor(value, flags)

    with patch.object(protected.os, 'open', side_effect=replace_then_open):
        with pytest.raises(ValueError, match='regular'):
            protected._capture(path, threading.Event())


def test_existing_attempt_is_preserved_before_dispatch(tmp_path):
    directory = tmp_path / 'attempt'
    directory.mkdir()
    previous = directory / 'previous'
    previous.write_bytes(b'accepted earlier bytes')
    with patch.object(protected, 'execute', side_effect=AssertionError('no worker')):
        result = run(tmp_path)
    assert result['status'] == 'delivery_failed'
    assert result['report'] is None
    assert previous.read_bytes() == b'accepted earlier bytes'
    assert list(directory.iterdir()) == [previous]


@pytest.mark.parametrize('status', ['invalid_input', 'unsupported_record', 'resource_limited',
                                    'calculation_error', 'interrupted'])
def test_incomplete_replay_is_not_a_comparison(tmp_path, status):
    def failure(payload, selected_policy, directory, cancellation, **options):
        value = message(payload, directory)
        admitted = status not in ('invalid_input', 'unsupported_record')
        value['report'] = replay._report(status, saved=saved() if admitted else None,
                                          error={'type': 'Controlled', 'message': status})
        return returned(value)

    result = run(tmp_path, dispatch=failure)
    assert result['status'] == result['replay_status'] == status
    assert result['report'] is None
    assert not (tmp_path / 'attempt/result').exists()
    assert json.loads((tmp_path / 'attempt/outcome.json').read_bytes()) == result


@pytest.mark.parametrize('change', [
    lambda value: value['source_record'].update(sha256='0' * 64),
    lambda value: value['policy'].update(wall_seconds=2),
    lambda value: value['report']['comparison']['recommendation'].update(matches=False),
    lambda value: value['report'].update(status='differences'),
    lambda value: value['report'].update(recomputed=None),
])
def test_forged_or_inconsistent_message_withholds_comparison(tmp_path, change):
    def altered(payload, selected_policy, directory, cancellation, **options):
        value = message(payload, directory)
        change(value)
        return returned(value)

    result = run(tmp_path, dispatch=altered)
    assert result['status'] == 'worker_failed'
    assert result['report'] is None
    assert not (tmp_path / 'attempt/result').exists()


@pytest.mark.parametrize('change', [
    lambda value: value['evs'].pop('D'),
    lambda value: value['evs'].update(P=0.0),
    lambda value: value.update(action='S', action_name='STAND'),
    lambda value: value.update(margin=99.0),
    lambda value: (value['evs'].update(S=value['evs']['H']), value.update(margin=0)),
])
def test_self_consistent_comparison_cannot_admit_incomplete_current_result(tmp_path, change):
    def altered(payload, selected_policy, directory, cancellation, **options):
        value = message(payload, directory)
        report = value['report']
        change(report['recomputed'])
        report['comparison'] = replay._compare(report['recorded'], report['recomputed'])
        report['status'] = 'differences'
        return returned(value)

    result = run(tmp_path, dispatch=altered)
    assert result['status'] == 'worker_failed'
    assert result['report'] is None
    assert not (tmp_path / 'attempt/result').exists()


@pytest.mark.parametrize('version', [3, 4, 5, 6])
def test_refusal_work_uses_only_the_original_model_families(version):
    source = {'schema': {'version': version}, 'model': {'enumeration_state_limit': 1}}
    work = {'limit': 1, 'states': 1, 'attempted_states': 2, 'state_counts': {'root_hit': 1}}
    protected._work(work, source)
    work['state_counts'] = {'invented_state_family': 1}
    with pytest.raises(ValueError, match='families'):
        protected._work(work, source)
    if version == 4:
        work['state_counts'] = {'joint_play': 1}
        with pytest.raises(ValueError, match='families'):
            protected._work(work, source)


@pytest.mark.parametrize('cards,split,changes,count,controls', [
    (['A', 'T'], False, {}, 3, (True, True)),
    (['T', '6', 'A'], False, {}, 3, (True, True)),
    (['A', '7'], True, {}, 3, (True, True)),
    (['7', 'A'], True, {}, 3, (True, True)),
    (['A', 'A'], True, {'resplit_aces': True}, 3, (True, True)),
    (['A', 'A'], True, {'resplit_aces': False}, 3, (True, True)),
    (['T', '9'], True, {'das': False}, 3, (True, True)),
    (['T', 'T'], False, {}, 1, (True, True)),
    (['T', 'T'], False, {}, 3, (False, True)),
    (['T', 'T'], False, {}, 3, (True, False)),
])
def test_complete_current_eligibility_matches_original_engine_with_prices_stubbed(
        cards, split, changes, count, controls, monkeypatch):
    # Source-control parity uses original best_action eligibility, not new numerical evidence.
    for name in ('_stand_ev', '_hit_ev', '_double_ev', '_split_total_ev'):
        monkeypatch.setattr(ev, name, lambda *args: 0.0)
    rules = Rules(**{**saved()['rules'], **changes})
    source = calc.record.decision_record(
        cards, '9', rules, shoe=[0] * 9 + [count], is_split_hand=split,
        hand_count=2 if split else 1, can_double=controls[0], can_split=controls[1])
    protected._current(source, source['decision'])
    wrong = json.loads(json.dumps(source['decision']))
    wrong['evs']['H' if set(wrong['evs']) == {'S'} else 'R'] = 0.0
    with pytest.raises(ValueError):
        protected._current(source, wrong)


def test_wrong_exit_or_incomplete_message_withholds_comparison(tmp_path):
    for label, change in [('exit', lambda value: value['worker'].update(returncode=1)),
                          ('lf', lambda value: value.update(stdout=value['stdout'][:-1]))]:
        directory = tmp_path / label
        directory.mkdir()

        def altered(payload, *args, **options):
            value = success(payload, *args, **options)
            change(value)
            return value

        assert run(directory, dispatch=altered)['status'] == 'worker_failed'


def test_unresolved_retirement_prevents_parent_parse_and_publication(tmp_path):
    def unresolved(payload, *args, **options):
        value = success(payload, *args, **options)
        value['cleanup'].update(retired=False, errors=['controlled retirement refusal'])
        return value

    with patch.object(replay, '_parse', side_effect=AssertionError('no parse before retirement')):
        result = run(tmp_path, dispatch=unresolved)
    assert result['status'] == 'cleanup_failed'
    assert result['cleanup']['retired'] is False
    assert result['report'] is None


def test_policy_not_established_withholds_complete_comparison(tmp_path):
    def unestablished(payload, *args, **options):
        value = success(payload, *args, **options)
        value['policy_established'] = False
        return value

    assert run(tmp_path, dispatch=unestablished)['status'] == 'unsupported_policy'
    assert not (tmp_path / 'attempt/result').exists()


def test_cancellation_before_and_after_publication_have_distinct_results(tmp_path):
    cancellation = threading.Event()
    write = calc._exclusive_bytes

    def cancel_staged(path, raw):
        write(path, raw)
        if path.name == 'receipt.json':
            cancellation.set()

    with patch.object(calc, '_exclusive_bytes', side_effect=cancel_staged):
        result = run(tmp_path, cancellation=cancellation)
    assert result['status'] == 'cancelled'
    assert result['report'] is None
    assert not (tmp_path / 'attempt/result').exists()
    following = tmp_path / 'following'
    following.mkdir()
    cancellation.clear()
    rename = os.rename

    def commit_then_cancel(source, destination):
        rename(source, destination)
        cancellation.set()

    with patch.object(protected.os, 'rename', side_effect=commit_then_cancel):
        result = run(following, cancellation=cancellation)
    assert result['status'] == 'agreement'
    assert (following / 'attempt/result/replay.json').is_file()


@pytest.mark.parametrize('phase', ['write', 'receipt', 'rename'])
@pytest.mark.parametrize('error_type', [OSError, FileExistsError], ids=['os-error', 'file-exists'])
def test_publication_failure_has_no_accepted_result(tmp_path, phase, error_type):
    write = calc._exclusive_bytes

    def fail_report(path, raw):
        selected = 'replay.json' if phase == 'write' else 'receipt.json'
        if path.parent.name == 'pending-result' and path.name == selected:
            raise error_type('controlled write/flush refusal')
        return write(path, raw)

    target = (patch.object(calc, '_exclusive_bytes', side_effect=fail_report)
              if phase != 'rename' else
              patch.object(protected.os, 'rename',
                           side_effect=error_type('controlled rename refusal')))
    with target:
        result = run(tmp_path)
    assert result['status'] == 'delivery_failed'
    assert result['report'] is None
    assert not (tmp_path / 'attempt/result').exists()
    outcome = json.loads((tmp_path / 'attempt/outcome.json').read_bytes())
    assert outcome == result
    assert outcome['report'] is None
    assert outcome['error']['type'] == error_type.__name__


def test_result_collision_preserves_other_files_without_accepting_report(tmp_path):
    directory = tmp_path / 'attempt'
    destination = directory / 'result'
    sentinel = destination / 'previous'
    earlier = b'previous destination bytes\n'
    original = FIXTURE.read_bytes()
    write = calc._exclusive_bytes
    staged = {}
    calls = []

    def collide_after_staging(path, raw):
        write(path, raw)
        if path.parent.name == 'pending-result':
            staged[path.name] = raw
            if path.name == 'receipt.json':
                destination.mkdir()
                sentinel.write_bytes(earlier)

    def completed(payload, *args, **options):
        calls.append(payload)
        return success(payload, *args, **options)

    with (
        patch.object(calc, '_exclusive_bytes', side_effect=collide_after_staging),
        patch.object(transport, 'execute', side_effect=AssertionError('no real transport')),
        patch.object(transport.subprocess, 'Popen', side_effect=AssertionError('no worker launch')),
        patch.object(calc.record, 'best_action', side_effect=AssertionError('must not price')),
        patch.object(ev, 'best_action', side_effect=AssertionError('must not price')),
    ):
        result = run(tmp_path, dispatch=completed)
    assert result['status'] == 'delivery_failed' and result['report'] is None
    assert result['error']['type'] == 'FileExistsError'
    assert json.loads((directory / 'outcome.json').read_bytes()) == result
    assert len(calls) == 1
    assert sentinel.read_bytes() == earlier and list(destination.iterdir()) == [sentinel]
    assert (tmp_path / 'source.json').read_bytes() == original
    assert (directory / 'record-source.json').read_bytes() == original
    assert result['source_record'] == protected._source(original)
    assert result['capture_verified'] is True
    assert json.loads(staged['replay.json'])['status'] == 'agreement'
    assert json.loads(staged['receipt.json'])['status'] == 'agreement'
    for name, raw in staged.items():
        assert (directory / 'pending-result' / name).read_bytes() == raw


def test_shared_owner_rejects_unselected_worker_before_launch(tmp_path):
    with patch.object(transport.subprocess, 'Popen', side_effect=AssertionError('no launch')):
        with pytest.raises(ValueError, match='fixed'):
            transport.execute(b'', policy(), tmp_path, threading.Event(), worker='arbitrary')


def worker_main(monkeypatch, tmp_path, payload, report):
    output = io.BytesIO()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, 'stdin', SimpleNamespace(buffer=io.BytesIO(payload)))
    monkeypatch.setattr(sys, 'stdout', SimpleNamespace(buffer=output))
    with patch.object(sys, 'platform', 'linux'), patch.object(
            replay, 'replay_json', return_value=report) as dispatch:
        status = worker.main()
    return status, output.getvalue(), dispatch


def test_fixed_worker_calls_original_dispatch_once_with_exact_bytes(monkeypatch, tmp_path):
    raw = FIXTURE.read_bytes()
    payload = protected._envelope(FIXTURE, policy())
    source = saved()
    expected = replay._report('agreement', saved=source, recomputed=source['decision'],
                              comparison=replay._compare(source['decision'], source['decision']))
    status, output, dispatch = worker_main(monkeypatch, tmp_path, payload, expected)
    assert status == 0
    dispatch.assert_called_once_with(raw)
    assert json.loads(output)['report'] == expected
    assert (tmp_path / 'record-source.json').read_bytes() == raw
    assert json.loads(output)['record_path'] == str(FIXTURE.absolute())
    assert json.loads(output)['source_record'] == protected._source(raw)
    assert worker.MAX_ENVELOPE_BYTES == protected.MAX_ENVELOPE_BYTES
    assert worker.MAX_PATH_BYTES == protected.MAX_PATH_BYTES
    assert worker.MAX_STREAM_BYTES == transport.MAX_STREAM_BYTES


@pytest.mark.parametrize('change', [
    lambda value: value.update(operation='unselected_operation'),
    lambda value: value.update(record_path='x' * 4097),
    lambda value: value.update(record_base64='unselected_transport'),
])
def test_worker_envelope_refusal_keeps_capture_and_dispatch_gate_closed(
        monkeypatch, tmp_path, change):
    payload = json.loads(protected._envelope(FIXTURE, policy()))
    change(payload)
    with patch.object(protected, '_capture', side_effect=AssertionError('no original open')):
        status, output, dispatch = worker_main(monkeypatch, tmp_path, calc._json_bytes(payload), {})
    assert status == 6 and output == b''
    dispatch.assert_not_called()


def test_malformed_record_still_reaches_only_original_contained_dispatch(monkeypatch, tmp_path):
    raw = b'\xff'
    path = tmp_path / 'source.json'
    path.write_bytes(raw)
    expected = replay._report('invalid_input', error={'type': 'Controlled', 'message': 'UTF-8'})
    status, output, dispatch = worker_main(
        monkeypatch, tmp_path, protected._envelope(path, policy()), expected)
    assert status == 2
    dispatch.assert_called_once_with(raw)
    assert json.loads(output)['report'] == expected


def test_valid_utf8_record_with_oversized_ascii_report_refuses_completely(monkeypatch, tmp_path):
    source = saved()
    source['package']['version'] = chr(0x20ac) * 11000
    raw = (json.dumps(source, ensure_ascii=False) + '\n').encode('utf-8')
    path = tmp_path / 'source.json'
    path.write_bytes(raw)
    assert len(raw) <= replay.MAX_RECORD_BYTES
    report = replay._report('agreement', saved=source, recomputed=source['decision'],
                            comparison=replay._compare(source['decision'], source['decision']))
    status, output, dispatch = worker_main(
        monkeypatch, tmp_path, protected._envelope(path, policy()), report)
    assert status == 4 and len(output) <= transport.MAX_STREAM_BYTES
    dispatch.assert_called_once_with(raw)
    envelope = json.loads(output)
    assert envelope['report'] is None
    assert envelope['error']['type'] == 'ReplayOutputLimit'


def test_worker_capture_failure_does_not_admit_or_price(monkeypatch, tmp_path):
    with patch.object(protected, '_capture', side_effect=OSError('controlled lookup refusal')):
        status, output, dispatch = worker_main(
            monkeypatch, tmp_path, protected._envelope(FIXTURE, policy()), {})
    assert status == 6
    dispatch.assert_not_called()
    value = json.loads(output)
    assert value['source_record'] is None and value['report']['status'] == 'io_error'
    assert value['report']['modeled_input'] is None and value['report']['recomputed'] is None
    assert not (tmp_path / 'record-source.json').exists()


def test_worker_capture_delivery_failure_withholds_identity_and_replay(monkeypatch, tmp_path):
    with patch.object(calc, '_exclusive_bytes', side_effect=OSError('controlled capture write')):
        status, output, dispatch = worker_main(
            monkeypatch, tmp_path, protected._envelope(FIXTURE, policy()), {})
    assert status == 8
    dispatch.assert_not_called()
    value = json.loads(output)
    assert value['source_record'] is None and value['report'] is None
    assert value['error']['type'] == 'CapturedRecordDelivery'


def test_worker_replays_immutable_bytes_after_original_replacement(monkeypatch, tmp_path):
    path = tmp_path / 'source.json'
    raw = FIXTURE.read_bytes()
    path.write_bytes(raw)
    write = calc._exclusive_bytes

    def replace_original_after_capture(destination, captured):
        write(destination, captured)
        path.write_bytes(b'replaced after contained capture\n')

    expected = replay._report('invalid_input', error={'type': 'Controlled', 'message': 'inert'})
    with patch.object(calc, '_exclusive_bytes', side_effect=replace_original_after_capture):
        status, output, dispatch = worker_main(
            monkeypatch, tmp_path, protected._envelope(path, policy()), expected)
    assert status == 2
    dispatch.assert_called_once_with(raw)
    assert json.loads(output)['source_record'] == protected._source(raw)
    assert (tmp_path / 'record-source.json').read_bytes() == raw
    assert path.read_bytes() == b'replaced after contained capture\n'


@pytest.mark.parametrize('status,code', [('agreement', 0), ('differences', 1), ('timed_out', 124),
                                       ('cancelled', 130), ('cleanup_failed', 7)])
def test_command_retains_distinct_outcome_exits(tmp_path, monkeypatch, capsys, status, code):
    with patch.object(protected, '_run', return_value={'status': status, 'report': None}):
        assert protected.main(['source.json', '--output-dir', str(tmp_path / 'attempt')]) == code
    assert json.loads(capsys.readouterr().out)['status'] == status


def test_unsupported_policy_does_not_capture_or_dispatch(tmp_path, capsys):
    with patch.object(sys, 'platform', 'linux'), patch.object(
            protected, '_run', side_effect=AssertionError('no capture')):
        assert protected.main(['not-read', '--output-dir', str(tmp_path / 'attempt'),
                               '--memory-mib', '256']) == 3
    assert json.loads(capsys.readouterr().out)['status'] == 'unsupported_policy'


def test_stdout_refusal_after_commit_preserves_completed_files(tmp_path, monkeypatch):
    path = tmp_path / 'source.json'
    path.write_bytes(FIXTURE.read_bytes())

    class RefusedStream:
        closed = False

        @property
        def buffer(self):
            return self

        def write(self, raw):
            return len(raw) - 1

        def flush(self):
            pass

        def close(self):
            self.closed = True

    output = RefusedStream()
    monkeypatch.setattr(sys, 'stdout', output)
    with patch.object(protected, 'execute', side_effect=success):
        status = protected.main([str(path), '--output-dir', str(tmp_path / 'attempt')])
    assert status == 8 and output.closed
    receipt = json.loads((tmp_path / 'attempt/result/receipt.json').read_bytes())
    assert receipt['status'] == 'agreement'
    assert (tmp_path / 'attempt/result/replay.json').is_file()
