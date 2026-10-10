"""Capture one request, compute in an owned worker, and publish a complete record."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import signal
import stat
import sys
import threading
import uuid
from pathlib import Path

from . import __version__, record, replay
from ._calculation_process import CLEANUP_SECONDS, execute
from .core import Rules

__all__ = ['main']

EXIT_STATUSES = {'completed': 0, 'invalid_request': 2, 'unsupported_policy': 3,
                 'resource_limited': 4, 'calculation_error': 5, 'worker_failed': 6,
                 'cleanup_failed': 7, 'delivery_failed': 8, 'timed_out': 124,
                 'cancelled': 130}
REQUEST_SCHEMA = {'name': 'solver-calculation-request', 'version': 1}
COMMON_REQUEST_SCHEMA = {'name': 'solver-calculation-request', 'version': 2}
SURRENDER_REQUEST_SCHEMA = {'name': 'solver-calculation-request', 'version': 3}
INPUT_KEYS = ('cards', 'dealer_up', 'unseen_counts', 'is_split_hand', 'hand_count',
              'can_double', 'can_split')
SURRENDER_INPUT_KEYS = INPUT_KEYS + ('can_surrender',)


class _Cancelled(Exception):
    pass


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=True, allow_nan=False, indent=2) + '\n').encode()


def _normalise(value):
    if not isinstance(value, dict):
        raise ValueError('request must be an object')
    schema = replay._object(value.get('schema'), ('name', 'version'), 'request.schema')
    common = type(schema['version']) is int and schema['version'] == 2
    surrender = type(schema['version']) is int and schema['version'] == 3
    bounded = common or surrender
    selected_schema = (SURRENDER_REQUEST_SCHEMA if surrender else
                       COMMON_REQUEST_SCHEMA if common else REQUEST_SCHEMA)
    keys = ('schema', 'rules', 'input', 'model', 'limits') if bounded else (
        'schema', 'rules', 'input')
    replay._object(value, keys, 'request')
    for key, expected in selected_schema.items():
        if type(schema[key]) is not type(expected) or schema[key] != expected:
            raise ValueError('unsupported solver calculation request schema')
    supplied_rules = value['rules']
    if not isinstance(supplied_rules, dict):
        raise ValueError('request.rules must be an object of supported rule fields')
    try:
        rules = Rules(**supplied_rules)
    except TypeError as exc:
        raise ValueError(str(exc)) from exc
    rule_values = (record._surrender_rules_record(rules) if surrender else
                   record._rules_record(rules))
    inputs = replay._object(value['input'], SURRENDER_INPUT_KEYS if surrender else INPUT_KEYS,
                           'request.input')
    if (not isinstance(inputs['cards'], list)
            or any(not isinstance(card, str) for card in inputs['cards'])):
        raise ValueError('request.input.cards must be an ordered list of card strings')
    if not isinstance(inputs['dealer_up'], str):
        raise ValueError('request.input.dealer_up must be a card string')
    if not isinstance(inputs['unseen_counts'], list):
        raise ValueError('request.input.unseen_counts must be ten retained counts')
    if type(inputs['hand_count']) is not int:
        raise ValueError('request.input.hand_count must be an integer, not a boolean')
    boolean_fields = ('is_split_hand', 'can_double', 'can_split')
    if surrender:
        boolean_fields += ('can_surrender',)
    for name in boolean_fields:
        if type(inputs[name]) is not bool:
            raise ValueError(f'request.input.{name} must be a boolean')
    cards, up, unseen, hand_count = record._record_inputs(
        inputs['cards'], inputs['dealer_up'], rules, inputs['unseen_counts'],
        inputs['is_split_hand'], inputs['hand_count'])
    captured = {'schema': dict(selected_schema), 'rules': rule_values,
            'input': {'cards': list(cards), 'dealer_up': up, 'unseen_counts': list(unseen),
                      'is_split_hand': inputs['is_split_hand'], 'hand_count': hand_count,
                      'can_double': inputs['can_double'], 'can_split': inputs['can_split']}}
    if surrender:
        captured['input']['can_surrender'] = inputs['can_surrender']
    if common:
        from . import common_shoe
        model = replay._object(value['model'], ('name', 'version'), 'request.model')
        for key, expected in common_shoe.MODEL.items():
            if type(model[key]) is not type(expected) or model[key] != expected:
                raise ValueError('unsupported common-shoe calculation model')
        limits = replay._object(value['limits'], ('max_states',), 'request.limits')
        common_shoe.validate(cards, rules, unseen, inputs['is_split_hand'], hand_count,
                             limits['max_states'])
        captured.update(model=dict(common_shoe.MODEL), limits=dict(limits))
    elif surrender:
        from . import late_surrender
        model = replay._object(value['model'], ('name', 'version'), 'request.model')
        for key, expected in late_surrender.MODEL.items():
            if type(model[key]) is not type(expected) or model[key] != expected:
                raise ValueError('unsupported late-surrender calculation model')
        limits = replay._object(value['limits'], ('max_states',), 'request.limits')
        late_surrender.validate(cards, rules, unseen, inputs['is_split_hand'], hand_count,
                                limits['max_states'], can_split=inputs['can_split'])
        captured.update(model=dict(late_surrender.MODEL), limits=dict(limits))
    return captured


def _request_policy(policy, captured):
    """Bind the operation's algorithmic cap to the normalized captured request."""
    if captured['schema']['version'] == 1:
        return policy
    if captured['schema']['version'] == 3:
        return {**policy, 'algorithmic_work_limit': {
            'name': 'whole_request_uncached_enumeration_states',
            'max_states': captured['limits']['max_states'],
            'includes': 'root_draw_hit_double_distribution_dealer'}}
    return {**policy, 'algorithmic_work_limit': {
        'name': 'whole_request_uncached_enumeration_states',
        'max_states': captured['limits']['max_states'],
        'includes': 'root_draw_hit_double_dealer_and_joint_draw_play_settle_dealer',
        'split_cooperative_seconds': 10.0}}


def _policy(wall_seconds, memory_mib):
    if (type(wall_seconds) not in (int, float) or not math.isfinite(wall_seconds)
            or not 0 < wall_seconds <= 300):
        raise ValueError('wall_seconds must be positive and at most 300 seconds')
    if memory_mib is not None and (type(memory_mib) is not int or not 64 <= memory_mib <= 4096):
        raise ValueError('memory_mib must be an integer from 64 through 4096')
    if sys.platform == 'win32':
        memory = {'mode': 'windows_job_commit', 'bytes': (memory_mib or 256) * 1024 * 1024,
                  'meaning': 'aggregate Job committed memory, not physical RSS'}
        ownership = 'windows_job'
    elif sys.platform.startswith('linux') and memory_mib is None:
        memory = {'mode': 'uncapped', 'bytes': None,
                  'meaning': 'no memory cap; process caches retire with the direct worker'}
        ownership = 'linux_direct_worker_no_descendants'
    elif sys.platform.startswith('linux'):
        raise NotImplementedError('hard memory mode is unsupported on Linux; no worker started')
    else:
        raise NotImplementedError('supervised calculation supports Windows and Linux only')
    return {'wall_seconds': float(wall_seconds), 'cleanup_seconds': CLEANUP_SECONDS,
            'memory': memory, 'ownership': ownership, 'algorithmic_work_limit': None,
            'worker_stdout_limit': 65536, 'worker_stderr_limit': 65536}


def _error(exc):
    return {'type': type(exc).__name__, 'message': str(exc)[:512]}


def _write_complete(stream, raw):
    if stream.write(raw) != len(raw):
        raise OSError('incomplete output write')
    stream.flush()


def _exclusive_bytes(path, raw):
    with path.open('xb') as stream:
        _write_complete(stream, raw)


def _ordinary(path, directory=False):
    info = path.lstat()
    if (stat.S_ISLNK(info.st_mode)
            or getattr(info, 'st_file_attributes', 0) & 0x400
            or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))):
        raise ValueError('use ordinary local files and directories, without links/reparse points')


def _validated_decision(raw, captured, digest, returncode, policy):
    if not raw.endswith(b'\n'):
        raise ValueError('worker did not deliver a complete LF-terminated message')
    message = replay._parse(raw)
    common = captured['schema']['version'] == 2
    surrender = captured['schema']['version'] == 3
    bounded = common or surrender
    if surrender:
        from . import late_surrender
    work_families = late_surrender.ROOT_FAMILIES if surrender else None
    keys = ('status', 'decision', 'error', 'request_sha256', 'policy')
    if bounded:
        keys += ('work',)
    replay._object(message, keys,
                   'worker message')
    if message['request_sha256'] != digest or message['policy'] != policy:
        raise ValueError('worker message does not identify the captured request and policy')
    status = message['status']
    if status not in ('completed', 'resource_limited', 'calculation_error', 'worker_failed'):
        raise ValueError('worker returned an unsupported outcome')
    if returncode != EXIT_STATUSES[status]:
        raise ValueError('worker exit does not match its complete outcome')
    if status != 'completed':
        if message['decision'] is not None or not isinstance(message['error'], dict):
            raise ValueError('incomplete worker outcome must contain no decision')
        replay._object(message['error'], ('type', 'message'), 'worker error')
        if any(not isinstance(value, str) for value in message['error'].values()):
            raise ValueError('worker error fields must be strings')
        if bounded and message['work'] is not None:
            _validated_work(message['work'], captured['limits']['max_states'], complete=False,
                             families=work_families)
        if bounded and message['error']['type'] == 'EnumerationLimitExceeded' and (
                status != 'resource_limited' or message['work'] is None):
            raise ValueError('enumeration refusal must identify its resource limit and work')
        return status, None, message['error'], message.get('work')
    if message['error'] is not None:
        raise ValueError('completed worker outcome contains an error')
    decision = message['decision']
    admitted = replay._admit(decision)  # Structural/input admission, no recomputation.
    cards, up, unseen, rules, is_split, hand_count, can_double, can_split = admitted
    inputs = captured['input']
    rule_values = (record._surrender_rules_record(rules) if surrender else
                   record._rules_record(rules))
    actual = (list(cards), up, list(unseen), rule_values, is_split,
              hand_count, can_double, can_split)
    expected = (inputs['cards'], inputs['dealer_up'], inputs['unseen_counts'], captured['rules'],
                inputs['is_split_hand'], inputs['hand_count'], inputs['can_double'],
                inputs['can_split'])
    if surrender:
        actual += (decision['state']['action_controls']['can_surrender'],)
        expected += (inputs['can_surrender'],)
    expected_version = (record.SURRENDER_SCHEMA_VERSION if surrender else
                        record.COMMON_SCHEMA_VERSION if common else
                        1 if can_double and can_split else 2)
    expected_model = (record._surrender_model_record(up, captured['limits']['max_states'])
                      if surrender else record._common_model_record(
                          up, captured['limits']['max_states']) if common else None)
    if (actual != expected or decision['state']['shoe']['source'] != 'supplied_unseen'
            or decision['package']['version'] != __version__
            or decision['schema']['version'] != expected_version
            or bounded and decision['model'] != expected_model):
        raise ValueError('completed decision differs from the captured request/package')
    answer = decision['decision']
    if surrender:
        offered = {'S', 'H'} | ({'D'} if inputs['can_double'] else set()) | (
            {'R'} if inputs['can_surrender'] else set())
        if set(answer['evs']) != offered or (
                inputs['can_surrender'] and answer['evs']['R'] != -0.5):
            raise ValueError('completed late-surrender decision lacks its exact offered values')
        action, margin = late_surrender.rank(answer['evs'])
        if answer['action'] != action or answer['margin'] != margin:
            raise ValueError('late-surrender decision contradicts its canonical ranking')
    values = list(answer['evs'].values())
    ranked = sorted(values, reverse=True)
    margin = ranked[0] - ranked[1] if len(ranked) > 1 else 0.0
    if answer['evs'][answer['action']] != ranked[0] or answer['margin'] != margin:
        raise ValueError('worker decision has an inconsistent recommendation or margin')
    result = _json_bytes(decision)
    if len(result) > replay.MAX_RECORD_BYTES:
        raise ValueError('completed decision exceeds existing replay/inspection record admission')
    if bounded:
        _validated_work(message['work'], captured['limits']['max_states'], complete=True,
                         families=work_families)
    return status, result, None, message.get('work')


def _validated_work(work, limit, *, complete, families=None):
    from ._enumeration import FAMILIES

    allowed = FAMILIES if families is None else families

    replay._object(work, ('limit', 'states', 'attempted_states', 'state_counts'), 'worker work')
    for key in ('limit', 'states', 'attempted_states'):
        if type(work[key]) is not int:
            raise ValueError('worker work counters must be integer tokens')
    counts = work['state_counts']
    if (not isinstance(counts, dict) or any(key not in allowed for key in counts)
            or any(type(value) is not int or value < 1 for value in counts.values())):
        raise ValueError('worker work state families are invalid')
    states, attempted = work['states'], work['attempted_states']
    if (work['limit'] != limit or not 0 <= states <= limit
            or states != sum(counts.values())
            or attempted != states + (0 if complete else 1)):
        raise ValueError('worker work differs from the captured state cap/accounting')


def _publish(directory, decision, receipt, cancellation):
    """One parent observation selects cancellation or the final directory commit."""
    if cancellation.is_set():
        raise _Cancelled()
    staged = directory / 'pending-result'
    staged.mkdir()
    _exclusive_bytes(staged / 'decision.json', decision)
    _exclusive_bytes(staged / 'receipt.json', _json_bytes(receipt))
    if cancellation.is_set():
        raise _Cancelled()
    # Completion is selected at this final observation. A later cancellation
    # cannot relabel the committed result. An unsuccessful rename is delivery
    # failure. This is an ordinary filesystem commit, not a durability promise.
    destination = directory / 'result'
    if destination.exists():
        raise FileExistsError('result destination already exists')
    os.rename(staged, destination)


def _run(request_path, output, policy, cancellation):
    receipt = {'schema': {'name': 'solver-calculation-attempt', 'version': 1},
               'status': 'invalid_request', 'attempt_id': None,
               'package': {'name': 'exact-blackjack-solver', 'version': __version__},
               'source_request': None, 'request_sha256': None, 'policy': policy,
               'policy_established': False,
               'worker': {'pid': None, 'returncode': None}, 'cleanup': None,
               'record': None, 'error': None}
    directory = None
    try:
        path = Path(request_path)
        _ordinary(path)
        with path.open('rb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError('request must be a regular local file')
            raw = stream.read(replay.MAX_RECORD_BYTES + 1)
        receipt['source_request'] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                                     'complete': len(raw) <= replay.MAX_RECORD_BYTES}
        captured = _normalise(replay._parse(raw))
        policy = _request_policy(policy, captured)
        receipt['policy'] = policy
        normalized = _json_bytes(captured)
        if len(normalized) > replay.MAX_RECORD_BYTES:
            raise ValueError('normalized request exceeds 65536 bytes')
        receipt['request_sha256'] = hashlib.sha256(normalized).hexdigest()
        directory = Path(output).absolute()
        _ordinary(directory.parent, directory=True)
        directory.mkdir()  # Exclusive ownership. Existing attempts are preserved.
        receipt['attempt_id'] = uuid.uuid4().hex
        receipt['status'] = 'delivery_failed'
        _exclusive_bytes(directory / 'request-source.json', raw)
        _exclusive_bytes(directory / 'request.json', normalized)
        _exclusive_bytes(directory / 'attempt.json', _json_bytes({**receipt, 'status': 'prepared'}))
        payload = _json_bytes({'request': captured, 'request_sha256': receipt['request_sha256'],
                               'policy': policy})
        result = execute(payload, policy, directory, cancellation)
        receipt['worker'], receipt['cleanup'] = result['worker'], result['cleanup']
        receipt['policy_established'] = result['policy_established']
        receipt['worker_elapsed_seconds'] = result['elapsed_seconds']
        receipt['status'] = result['status']
        receipt['error'] = ({'type': 'WorkerTransport', 'message': result['error']}
                            if result['error'] else None)
        if result['stderr']:
            _exclusive_bytes(directory / 'worker.stderr', result['stderr'])
        if result['stdout']:
            _exclusive_bytes(directory / 'worker.stdout', result['stdout'])
        if receipt['status'] == 'returned':
            try:
                status, decision, error, work = _validated_decision(
                    result['stdout'], captured, receipt['request_sha256'],
                    result['worker']['returncode'], policy)
                receipt['status'], receipt['error'] = status, error
                if captured['schema']['version'] in (2, 3):
                    receipt['work'] = work
            except (ValueError, TypeError, KeyError, OverflowError) as exc:
                receipt['status'], receipt['error'] = 'worker_failed', _error(exc)
        else:
            decision = None
        if receipt['status'] == 'completed' and not receipt['policy_established']:
            receipt['status'], receipt['error'] = 'unsupported_policy', {
                'type': 'UnestablishedPolicy', 'message': 'worker policy was not established'}
        if not receipt['cleanup']['retired'] or receipt['cleanup']['errors']:
            if receipt['status'] == 'completed':
                receipt['status'] = 'cleanup_failed'
            receipt['record'] = None
        elif receipt['status'] == 'completed':
            receipt['record'] = {'path': 'result/decision.json', 'bytes': len(decision),
                                 'sha256': hashlib.sha256(decision).hexdigest()}
            _publish(directory, decision, receipt, cancellation)
            return receipt
        if cancellation.is_set() and receipt['status'] == 'completed':
            receipt['status'] = 'cancelled'
        receipt['record'] = None
    except _Cancelled:
        receipt['status'], receipt['record'] = 'cancelled', None
    except FileExistsError as exc:
        receipt['status'], receipt['error'] = 'delivery_failed', _error(exc)
        if receipt['attempt_id'] is None:
            directory = None  # Never write into someone else's existing directory.
    except (OSError, ValueError, TypeError, OverflowError) as exc:
        receipt['status'] = 'invalid_request' if directory is None else 'delivery_failed'
        receipt['record'], receipt['error'] = None, _error(exc)
    if directory is not None and receipt['attempt_id'] is not None:
        try:
            _exclusive_bytes(directory / 'outcome.json', _json_bytes(receipt))
        except (OSError, ValueError) as exc:
            receipt['status'], receipt['record'] = 'delivery_failed', None
            receipt['receipt_delivery_error'] = _error(exc)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('request', type=Path, help='versioned modeled-input JSON request')
    parser.add_argument('--output-dir', type=Path, required=True,
                        help='new attempt directory under an existing ordinary directory')
    parser.add_argument('--wall-seconds', type=float, default=30,
                        help='worker startup/calculation/transport deadline, '
                             '0 < N <= 300 (default 30)')
    parser.add_argument('--memory-mib', type=int,
                        help='Windows Job committed-memory cap, 64..4096 (default 256); '
                             'hard memory modes are refused on Linux')
    args = parser.parse_args(argv)
    try:
        policy = _policy(args.wall_seconds, args.memory_mib)
    except (ValueError, NotImplementedError) as exc:
        result = {'status': 'unsupported_policy', 'error': _error(exc), 'record': None}
        try:
            _write_complete(sys.stdout.buffer, _json_bytes(result))
        except (OSError, ValueError):
            _retire_stdout()
            return EXIT_STATUSES['delivery_failed']
        return EXIT_STATUSES[result['status']]
    cancellation = threading.Event()
    previous = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, lambda *_: cancellation.set())
    try:
        explanation = ('Windows Job committed-memory cap required before computation'
                       if policy['memory']['mode'] == 'windows_job_commit'
                       else 'Linux wall-only mode; memory is uncapped; fixed direct worker only')
        _write_complete(sys.stderr.buffer,
                        (f'Policy: {explanation}; worker deadline {policy["wall_seconds"]}s; '
                         f'cleanup allowance {CLEANUP_SECONDS}s.\n').encode())
        result = _run(args.request, args.output_dir, policy, cancellation)
        _write_complete(sys.stdout.buffer, _json_bytes(result))
        return EXIT_STATUSES[result['status']]
    except (OSError, ValueError) as exc:
        try:
            sys.stderr.write(f'Calculation report delivery failed: {exc}\n')
            sys.stderr.flush()
        except (OSError, ValueError):
            pass
        _retire_stdout()
        return EXIT_STATUSES['delivery_failed']
    finally:
        signal.signal(signal.SIGINT, previous)


def _retire_stdout():
    try:
        sys.stdout.close()
    except (OSError, ValueError, KeyboardInterrupt):
        pass


if __name__ == '__main__':
    status = main()
    if status == EXIT_STATUSES['delivery_failed']:
        try:
            sys.stdout.close()
        except (OSError, ValueError, KeyboardInterrupt):
            pass
    raise SystemExit(status)
