"""Capture one saved record and replay it in the existing owned process."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import os
import signal
import stat
import sys
import threading
import uuid
from pathlib import Path

from . import __version__, calculation, replay
from ._calculation_process import CLEANUP_SECONDS, MAX_STREAM_BYTES, execute

__all__ = ['main']

OPERATION = 'saved_record_replay'
WORKER = 'bj._replay_worker'
MAX_ENVELOPE_BYTES = 32768
MAX_PATH_BYTES = 4096
COMPLETE = frozenset(('agreement', 'differences'))
EXIT_STATUSES = {
    **replay.EXIT_STATUSES, 'unsupported_policy': 3, 'worker_failed': 6,
    'cleanup_failed': 7, 'delivery_failed': 8, 'timed_out': 124, 'cancelled': 130,
}


class _Cancelled(Exception):
    pass


def _local_path(value):
    path = Path(value).absolute()
    if os.name == 'nt':
        spelling = os.fspath(path)
        drive, tail = os.path.splitdrive(spelling)
        if (not drive or spelling.startswith('\\\\') or ':' in tail
                or any(part.split('.')[0].upper() in (
                    'CON', 'PRN', 'AUX', 'NUL',
                    *(f'COM{number}' for number in range(1, 10)),
                    *(f'LPT{number}' for number in range(1, 10)))
                       for part in path.parts[1:])):
            raise ValueError('use an ordinary local file, without device or network paths')
    return path


def _ordinary_parents(path):
    for parent in reversed(path.parents):
        calculation._ordinary(parent, directory=True)


def _open_regular(path, flags):
    if os.name != 'nt':
        return os.open(path, flags | os.O_NONBLOCK | os.O_NOFOLLOW)
    from ctypes import wintypes
    import msvcrt

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                                  wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    # OPEN_EXISTING, shared read/write/delete, OPEN_REPARSE_POINT | SEQUENTIAL_SCAN.
    # Final reparse handles are rejected below. Ancestor lookup is contained in the worker.
    handle = kernel.CreateFileW(str(path), 0x80000000, 7, None, 3, 0x08200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return msvcrt.open_osfhandle(int(handle), flags)
    except BaseException:
        kernel.CloseHandle(handle)
        raise


def _capture(path, cancellation):
    """Read a bounded descriptor in the worker, or its owned artifact after retirement."""
    if cancellation.is_set():
        raise _Cancelled()
    path = _local_path(path)
    _ordinary_parents(path)
    calculation._ordinary(path)
    expected = path.lstat()
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_CLOEXEC', 0)
    descriptor = _open_regular(path, flags)
    try:
        observed = os.fstat(descriptor)
        if (not stat.S_ISREG(observed.st_mode)
                or getattr(observed, 'st_file_attributes', 0) & 0x400
                or (observed.st_dev, observed.st_ino) != (expected.st_dev, expected.st_ino)):
            raise ValueError('source changed identity or is not an ordinary regular file')
        with os.fdopen(descriptor, 'rb') as stream:
            descriptor = None
            raw = stream.read(replay.MAX_RECORD_BYTES + 1)
        if cancellation.is_set():
            raise _Cancelled()
        return raw
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _source(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
            'complete': len(raw) <= replay.MAX_RECORD_BYTES}


def _envelope(path, policy):
    path = os.fspath(_local_path(path))
    if len(path.encode('utf-8')) > MAX_PATH_BYTES:
        raise ValueError('record path exceeds 4096 UTF-8 bytes')
    result = calculation._json_bytes({
        'operation': OPERATION, 'record_path': path, 'policy': policy,
    })
    if len(result) > MAX_ENVELOPE_BYTES:
        raise ValueError('replay path envelope exceeds 32768 bytes')
    return result


def _error(value, path):
    replay._object(value, ('type', 'message'), path)
    if any(not isinstance(item, str) for item in value.values()):
        raise ValueError(f'{path} must contain string error fields')


def _work(value, saved, *, complete=False):
    record = calculation.record
    if saved['schema']['version'] == record.DEFERRED_SCHEMA_VERSION:
        calculation._validated_deferred_work(
            value, saved['model']['enumeration_state_limit'],
            saved['model']['enumeration_seconds_limit'], complete=complete)
        return
    from . import bounded_ace_resplit, bounded_resplit, late_surrender
    from ._enumeration import FAMILIES

    families = {
        record.COMMON_SCHEMA_VERSION: FAMILIES,
        record.SURRENDER_SCHEMA_VERSION: late_surrender.ROOT_FAMILIES,
        record.RESPLIT_SCHEMA_VERSION: bounded_resplit.FAMILIES,
        record.ACE_RESPLIT_SCHEMA_VERSION: bounded_ace_resplit.FAMILIES,
    }.get(saved['schema']['version'])
    if families is None:
        raise ValueError('this recorded model has no enumeration work report')
    calculation._validated_work(
        value, saved['model']['enumeration_state_limit'], complete=complete, families=families,
        terminal_reuse=(type(value) is dict and 'terminal_reuse' in value
                        and saved['schema']['version'] == record.ACE_RESPLIT_SCHEMA_VERSION
                        and saved['state']['action_controls']['can_split'] is True))


def _current(saved, recomputed):
    """Validate complete current actions/ranking without restricting historical answers."""
    from .core import hand_total, is_pair

    cards, _up, unseen, rules, split, hand_count, can_double, can_split = replay._admit(
        {**saved, 'package': {'name': 'exact-blackjack-solver', 'version': __version__},
         'decision': recomputed})
    record = calculation.record
    version = saved['schema']['version']
    bounded = version in (record.COMMON_SCHEMA_VERSION, record.SURRENDER_SCHEMA_VERSION,
                          record.RESPLIT_SCHEMA_VERSION, record.ACE_RESPLIT_SCHEMA_VERSION)
    surrender = version == record.SURRENDER_SCHEMA_VERSION
    deferred = version == record.DEFERRED_SCHEMA_VERSION
    if deferred:
        offered = {'S'}
        if sum(unseen) >= 2:
            offered.add('H')
            if can_double:
                offered.add('D')
    elif bounded:
        offered = {'S', 'H'} | ({'D'} if can_double else set())
        if surrender:
            if saved['state']['action_controls']['can_surrender']:
                offered.add('R')
        elif can_split:
            offered.add('P')
    else:
        total, _soft = hand_total(cards)
        two_cards, count = len(cards) == 2, sum(unseen)
        offered = {'S'}
        if total != 21:
            pair = is_pair(cards, rules.tens_are_pairs)
            frozen = split and two_cards and cards[0] == 'A' and not rules.hit_split_aces
            if not frozen and count >= 2:
                offered.add('H')
                if can_double and two_cards and (not split or rules.das):
                    offered.add('D')
            blocked = split and pair and cards[0] == 'A' and not rules.resplit_aces
            if (can_split and two_cards and pair and count >= 3
                    and hand_count < rules.max_hands and not blocked):
                offered.add('P')
        elif two_cards and not split and float(recomputed['evs'].get('S', 0)) != (
                rules.blackjack_payout):
            raise ValueError('recomputed natural does not retain its declared payout')
    if set(recomputed['evs']) != offered:
        raise ValueError('recomputed result does not contain exactly its offered actions')
    values = {action: float(value) for action, value in recomputed['evs'].items()}
    if 'R' in values and values['R'] != -0.5:
        raise ValueError('recomputed late surrender must retain its half-wager loss')
    order = ('S', 'H', 'D') if deferred else (
        ('S', 'H', 'D', 'R') if surrender else ('S', 'H', 'D', 'P'))
    ranked = sorted(((action, values[action]) for action in order if action in values),
                    key=lambda item: item[1], reverse=True)
    margin = ranked[0][1] - ranked[1][1] if len(ranked) > 1 else None if deferred else 0.0
    actual_margin = None if recomputed['margin'] is None else float(recomputed['margin'])
    if recomputed['action'] != ranked[0][0] or actual_margin != margin:
        raise ValueError('recomputed result contradicts its canonical ranking or margin')


def _validated_report(raw, captured, path, returncode, policy):
    """Join complete output after retirement without running a decision engine."""
    if not raw.endswith(b'\n') or len(raw) > MAX_STREAM_BYTES:
        raise ValueError('worker did not deliver one bounded LF-terminated message')
    message = replay._parse(raw)
    replay._object(message, ('operation', 'record_path', 'source_record',
                            'policy', 'report', 'error'),
                   'worker message')
    identity = message['source_record']
    if identity is not None:
        replay._object(identity, ('bytes', 'sha256', 'complete'), 'source_record')
        replay._integer(identity['bytes'], 'source_record.bytes')
        if type(identity['complete']) is not bool:
            raise ValueError('source completeness must be a boolean')
    expected_identity = None if captured is None else _source(captured)
    if (message['operation'] != OPERATION or message['record_path'] != path
            or identity != expected_identity
            or message['policy'] != policy):
        raise ValueError('worker message does not identify the captured record and policy')
    report, error = message['report'], message['error']
    if report is None:
        _error(error, 'worker error')
        outcomes = {'ReplayOutputLimit': ('resource_limited', 4),
                    'CapturedRecordDelivery': ('delivery_failed', 8)}
        selected = outcomes.get(error['type'])
        if selected is None or returncode != selected[1]:
            raise ValueError('worker has no complete replay outcome')
        if error['type'] == 'ReplayOutputLimit' and captured is None:
            raise ValueError('output refusal lacks its captured input identity')
        return selected[0], None, error
    if error is not None or not isinstance(report, dict):
        raise ValueError('worker replay envelope has inconsistent report/error fields')
    status = report.get('status')
    if status not in replay.EXIT_STATUSES or returncode != replay.EXIT_STATUSES[status]:
        raise ValueError('worker exit does not match its replay outcome')
    keys = set(replay._report(status))
    if 'work' in report:
        keys.add('work')
    replay._object(report, keys, 'replay report')
    admitted = report['modeled_input'] is not None
    saved = None
    if admitted:
        if captured is None or len(captured) > replay.MAX_RECORD_BYTES:
            raise ValueError('admitted replay lacks a complete captured record')
        saved = replay._parse(captured)
        replay._admit(saved)  # Nonpricing structure/model checks, after worker retirement.
    expected = replay._report(status, saved=saved, recomputed=report['recomputed'],
                              comparison=report['comparison'], error=report['error'])
    if any(report[key] != expected[key] for key in expected):
        raise ValueError('replay report differs from captured input or current package')
    if status in COMPLETE:
        if not admitted or report['error'] is not None:
            raise ValueError('completed comparison lacks admitted input or contains an error')
        recomputed = report['recomputed']
        _current(saved, recomputed)
        comparison = replay._compare(saved['decision'], recomputed)
        if comparison != report['comparison']:
            raise ValueError('worker comparison does not match its recorded/recomputed answers')
        agreement = (comparison['legal_actions']['matches'] and comparison['evs_match']
                     and comparison['recommendation']['matches']
                     and comparison['margin']['matches'])
        deferred = saved['schema']['version'] == calculation.record.DEFERRED_SCHEMA_VERSION
        if (status == 'agreement') != agreement or ('work' in report) != deferred:
            raise ValueError('completed comparison status or work is inconsistent')
        if deferred:
            _work(report['work'], saved, complete=True)
    else:
        if report['recomputed'] is not None or report['comparison'] is not None:
            raise ValueError('incomplete replay must contain no recomputed answer or comparison')
        _error(report['error'], 'replay error')
        if status in ('invalid_input', 'unsupported_record') and admitted:
            raise ValueError('input refusal must not contain admitted data')
        error_type = report['error']['type']
        deferred = (admitted and
                    saved['schema']['version'] == calculation.record.DEFERRED_SCHEMA_VERSION)
        enumeration = error_type == 'EnumerationLimitExceeded'
        timed = error_type == 'DeferredTimeLimitExceeded'
        exhausted = error_type == 'UnsupportedContinuation'
        if (timed or exhausted) and not deferred:
            raise ValueError('deferred model refusal lacks its captured family')
        if (enumeration or timed) and (
                status != 'resource_limited' or not admitted or 'work' not in report):
            raise ValueError('enumeration refusal must retain its applicable work report')
        if exhausted and (status != 'calculation_error' or 'work' not in report):
            raise ValueError('deferred exhaustion must retain refused calculation work')
        if 'work' in report:
            expected_status = 'calculation_error' if exhausted else 'resource_limited'
            if status != expected_status or not admitted or not (enumeration or timed or exhausted):
                raise ValueError('model work belongs only to an admitted typed refusal')
            _work(report['work'], saved)
            if deferred and enumeration:
                limit = saved['model']['enumeration_state_limit']
                if (report['work']['states'] != limit or
                        report['work']['attempted_states'] != limit + 1):
                    raise ValueError('deferred state refusal did not reach its recorded cap')
            if (timed and report['work']['elapsed_seconds'] <
                    saved['model']['enumeration_seconds_limit']):
                raise ValueError('deferred deadline refusal did not reach its recorded allowance')
    return status, report, report['error']


def _publish(directory, report, receipt, cancellation):
    if cancellation.is_set():
        raise _Cancelled()
    staged = directory / 'pending-result'
    staged.mkdir()
    calculation._exclusive_bytes(staged / 'replay.json', report)
    calculation._exclusive_bytes(staged / 'receipt.json', calculation._json_bytes(receipt))
    if cancellation.is_set():
        raise _Cancelled()
    destination = directory / 'result'
    if destination.exists():
        raise FileExistsError('result destination already exists')
    # The final cancellation observation selects this ordinary filesystem commit.
    os.rename(staged, destination)


def _run(record_path, output, policy, cancellation):
    receipt = {
        'schema': {'name': 'solver-replay-attempt', 'version': 1},
        'status': 'io_error', 'attempt_id': None,
        'package': {'name': 'exact-blackjack-solver', 'version': __version__},
        'source_record': None, 'policy': policy, 'policy_established': False,
        'worker': {'pid': None, 'returncode': None}, 'cleanup': None,
        'replay_status': None, 'capture_verified': False, 'report': None, 'error': None,
    }
    directory = None
    try:
        receipt['status'] = 'invalid_input'
        payload = _envelope(record_path, policy)
        path = os.fspath(_local_path(record_path))
        if cancellation.is_set():
            raise _Cancelled()
        receipt['status'] = 'delivery_failed'
        directory = _local_path(output)
        _ordinary_parents(directory)
        directory.mkdir()
        receipt['attempt_id'] = uuid.uuid4().hex
        receipt['status'] = 'delivery_failed'
        calculation._exclusive_bytes(directory / 'attempt.json', calculation._json_bytes(
            {**receipt, 'status': 'prepared'}))
        result = execute(payload, policy, directory, cancellation, worker=WORKER)
        receipt['worker'], receipt['cleanup'] = result['worker'], result['cleanup']
        receipt['policy_established'] = result['policy_established']
        receipt['worker_elapsed_seconds'] = result['elapsed_seconds']
        receipt['status'] = result['status']
        receipt['error'] = ({'type': 'WorkerTransport', 'message': result['error']}
                            if result['error'] else None)
        for stream in ('stdout', 'stderr'):
            if result[stream]:
                calculation._exclusive_bytes(directory / f'worker.{stream}', result[stream])
        report = None
        # Retirement precedes parsing captured JSON and validating comparison data.
        clean = receipt['cleanup']['retired'] and not receipt['cleanup']['errors']
        if receipt['status'] == 'returned' and not clean:
            receipt['status'] = 'cleanup_failed'
        elif receipt['status'] == 'returned':
            try:
                # The original path is opened only by the contained worker. This parent
                # reads the owned capture only after retirement and joins the returned digest.
                message = replay._parse(result['stdout'])
                has_capture = isinstance(message, dict) and message.get('source_record') is not None
                captured = (_capture(directory / 'record-source.json', threading.Event())
                            if has_capture else None)
                status, report, error = _validated_report(
                    result['stdout'], captured, path, result['worker']['returncode'], policy)
                if captured is not None:
                    receipt['source_record'] = _source(captured)
                    receipt['capture_verified'] = True
                receipt.update(status=status, replay_status=status, error=error)
            except (MemoryError, RecursionError) as exc:
                receipt['status'], receipt['error'] = 'resource_limited', calculation._error(exc)
            except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
                receipt['status'], receipt['error'] = 'worker_failed', calculation._error(exc)
        if receipt['status'] in COMPLETE and not receipt['policy_established']:
            receipt['status'], receipt['error'] = 'unsupported_policy', {
                'type': 'UnestablishedPolicy', 'message': 'worker policy was not established'}
        if receipt['status'] in COMPLETE and clean:
            encoded = calculation._json_bytes(report)
            receipt['report'] = {'path': 'result/replay.json', 'bytes': len(encoded),
                                 'sha256': hashlib.sha256(encoded).hexdigest()}
            _publish(directory, encoded, receipt, cancellation)
            return receipt
        receipt['report'] = None
    except _Cancelled:
        receipt['status'], receipt['report'] = 'cancelled', None
    except FileExistsError as exc:
        receipt['status'], receipt['error'] = 'delivery_failed', calculation._error(exc)
        if receipt['attempt_id'] is None:
            directory = None
    except (OSError, ValueError, TypeError, OverflowError, MemoryError, RecursionError) as exc:
        if isinstance(exc, (MemoryError, RecursionError)):
            receipt['status'] = 'resource_limited'
        elif receipt['attempt_id'] is not None:
            receipt['status'] = 'delivery_failed'
        receipt['report'], receipt['error'] = None, calculation._error(exc)
    if directory is not None and receipt['attempt_id'] is not None:
        try:
            calculation._exclusive_bytes(directory / 'outcome.json',
                                          calculation._json_bytes(receipt))
        except (OSError, ValueError) as exc:
            receipt['status'], receipt['report'] = 'delivery_failed', None
            receipt['receipt_delivery_error'] = calculation._error(exc)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('record', type=Path, help='one existing versioned decision record')
    parser.add_argument('--output-dir', type=Path, required=True,
                        help='new attempt directory under an existing ordinary directory')
    parser.add_argument('--wall-seconds', type=float, default=30,
                        help='worker startup/replay/transport deadline, 0 < N <= 300 (default 30)')
    parser.add_argument('--memory-mib', type=int,
                        help='Windows Job committed-memory cap, 64..4096 (default 256); '
                             'hard memory modes are refused on Linux')
    args = parser.parse_args(argv)
    try:
        policy = calculation._policy(args.wall_seconds, args.memory_mib)
    except (ValueError, NotImplementedError) as exc:
        result = {'status': 'unsupported_policy', 'error': calculation._error(exc), 'report': None}
        try:
            calculation._write_complete(sys.stdout.buffer, calculation._json_bytes(result))
        except (OSError, ValueError):
            calculation._retire_stdout()
            return EXIT_STATUSES['delivery_failed']
        return EXIT_STATUSES['unsupported_policy']
    cancellation = threading.Event()
    previous = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, lambda *_: cancellation.set())
    try:
        explanation = ('Windows Job committed-memory cap required before replay'
                       if policy['memory']['mode'] == 'windows_job_commit'
                       else 'Linux wall-only mode; memory is uncapped; fixed direct worker only')
        calculation._write_complete(sys.stderr.buffer,
                                    (f'Policy: {explanation}; worker deadline '
                                     f'{policy["wall_seconds"]}s; cleanup allowance '
                                     f'{CLEANUP_SECONDS}s.\n').encode())
        result = _run(args.record, args.output_dir, policy, cancellation)
        calculation._write_complete(sys.stdout.buffer, calculation._json_bytes(result))
        return EXIT_STATUSES[result['status']]
    except (OSError, ValueError) as exc:
        try:
            sys.stderr.write(f'Replay report delivery failed: {exc}\n')
            sys.stderr.flush()
        except (OSError, ValueError):
            pass
        calculation._retire_stdout()
        return EXIT_STATUSES['delivery_failed']
    finally:
        signal.signal(signal.SIGINT, previous)


if __name__ == '__main__':
    status = main()
    if status == EXIT_STATUSES['delivery_failed']:
        calculation._retire_stdout()
    raise SystemExit(status)
