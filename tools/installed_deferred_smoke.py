"""Calculate and reuse explicit deferred-dealer records from an installed wheel."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from unittest.mock import patch

import bj
from bj import _calculation_process as transport
from bj import calculation, deferred_second_card, supervised_replay
from bj.core import Rules


def require(value, message):
    if not value:
        raise AssertionError(message)


def identity(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def command(name, args, directory, code):
    entry = Path(sys.executable).parent / (name + ('.exe' if os.name == 'nt' else ''))
    env = {key: value for key, value in os.environ.items()
           if key.upper() not in ('PYTHONPATH', 'PYTHONHOME')}
    options = {'creationflags': 0x08000000} if os.name == 'nt' else {}
    result = subprocess.run([str(entry), *args], cwd=directory, env=env,
                            capture_output=True, timeout=20, **options)
    require(result.returncode == code, f'{name} exit: {result.stderr!r} {result.stdout!r}')
    require(len(result.stdout) <= 65536 and result.stdout.endswith(b'\n'),
            'entry did not deliver a complete bounded JSON message')
    return json.loads(result.stdout)


def retired(receipt):
    cleanup = receipt['cleanup']
    require(receipt['policy_established'] and cleanup['retired']
            and cleanup['worker_retired'] and cleanup['transport_retired']
            and cleanup['job_empty'] is not False and not cleanup['errors'],
            'owned worker did not establish policy and retire')


def request(counts, *, cards=None, up='T', s17=True, max_states=100000, max_seconds=10.0):
    return {'schema': dict(calculation.DEFERRED_REQUEST_SCHEMA),
            'rules': asdict(Rules(peek=False, max_hands=1, resplit_aces=False, s17=s17)),
            'input': {'cards': cards or ['9', '2'], 'dealer_up': up, 'unseen_counts': counts,
                      'is_split_hand': False, 'hand_count': 1,
                      'can_double': True, 'can_split': False},
            'model': dict(deferred_second_card.MODEL),
            'limits': {'max_states': max_states, 'max_seconds': max_seconds}}


def calculate(root, label, value, status='completed', code=0):
    path = root / f'{label}-request.json'
    raw = calculation._json_bytes(value)
    path.write_bytes(raw)
    attempt = root / label
    receipt = command('bj-calculate', [str(path), '--output-dir', str(attempt),
                                       '--wall-seconds', '5'], root, code)
    require(receipt['status'] == status, 'calculation outcome differs')
    require(path.read_bytes() == raw, 'calculation changed its source')
    if status == 'invalid_request':
        require(receipt['record'] is None and not attempt.exists(),
                'invalid request started an attempt')
    else:
        retired(receipt)
        require((attempt / 'request-source.json').read_bytes() == raw,
                'captured request differs from original')
        if status == 'completed':
            record_path = attempt / 'result/decision.json'
            require(receipt['record'] == {'path': 'result/decision.json',
                                           **identity(record_path.read_bytes())},
                    'complete record identity differs')
            calculation._validated_deferred_work(receipt['work'], value['limits']['max_states'],
                                                  value['limits']['max_seconds'], complete=True)
        else:
            require(receipt['record'] is None and not (attempt / 'result').exists(),
                    'incomplete calculation published an answer')
    return {'label': label, 'receipt': receipt, 'source': identity(raw)}


def semantic(report):
    result = json.loads(json.dumps(report))
    if 'work' in result:
        result['work'].pop('elapsed_seconds')
    return result


def reuse(root, label, path, status='agreement', code=0):
    raw = path.read_bytes()
    stamp = path.stat().st_mtime_ns
    direct = command('bj-advise', ['--replay', str(path), '--json'], root, code)
    attempt = root / label
    receipt = command('bj-replay', [str(path), '--output-dir', str(attempt),
                                    '--wall-seconds', '5'], root, code)
    retired(receipt)
    require(receipt['status'] == receipt['replay_status'] == direct['status'] == status,
            'installed direct and protected outcomes differ')
    require(receipt['capture_verified'] and receipt['source_record'] == {
        **identity(raw), 'complete': True}, 'captured record identity differs')
    require((attempt / 'record-source.json').read_bytes() == raw,
            'protected source differs from immutable input')
    if code in (0, 1):
        report_raw = (attempt / 'result/replay.json').read_bytes()
        report = json.loads(report_raw)
        require(semantic(report) == semantic(direct), 'protected dispatch changed replay semantics')
        require(receipt['report'] == {'path': 'result/replay.json', **identity(report_raw)},
                'published report identity differs')
        saved = json.loads(raw)
        for work in (direct['work'], report['work']):
            calculation._validated_deferred_work(
                work, saved['model']['enumeration_state_limit'],
                saved['model']['enumeration_seconds_limit'], complete=True)
    else:
        require(direct['recomputed'] is None and direct['comparison'] is None
                and receipt['report'] is None and not (attempt / 'result').exists(),
                'incomplete replay published a comparison')
    require(path.read_bytes() == raw and path.stat().st_mtime_ns == stamp,
            'installed reuse changed its source')
    return {'label': label, 'input': str(path), 'source': identity(raw), 'receipt': receipt}


def lifecycle(root, source, operation, mode):
    """Hold the new private pricing seam after its gate, using the existing owner."""
    label = f'controlled-{operation}-{mode}'
    ready = root / (label + '-entered')
    directory = root / label
    module = 'bj._replay_worker' if operation == 'replay' else 'bj._calculation_worker'
    code = (
        'import io,pathlib,runpy,sys,time;raw=sys.stdin.buffer.read();'
        'from bj import record\n'
        'def controlled(*args,**kwargs):\n'
        f' pathlib.Path({str(ready)!r}).write_bytes(b"entered")\n'
        ' while True: time.sleep(0.01)\n'
        'record._deferred_second_card_record=controlled\n'
        'sys.stdin=io.TextIOWrapper(io.BytesIO(raw))\n'
        f'runpy.run_module({module!r},run_name="__main__")\n')
    launch = subprocess.Popen

    def child(argv, **options):
        require(argv == [sys.executable, '-I', '-B', '-m', module],
                'unexpected fixed worker command')
        return launch([sys.executable, '-I', '-B', '-c', code], **options)

    cancellation = threading.Event()
    errors = []
    observer = None
    if mode == 'cancel':
        def cancel_entered():
            deadline = time.monotonic() + 4
            while not ready.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            if not ready.exists():
                errors.append('contained child did not enter new-family pricing seam')
            cancellation.set()
        observer = threading.Thread(target=cancel_entered)
        observer.start()
    original = source.read_bytes()
    try:
        with patch.object(transport.subprocess, 'Popen', side_effect=child):
            run = supervised_replay._run if operation == 'replay' else calculation._run
            receipt = run(source, directory, calculation._policy(
                1 if mode == 'timeout' else 5, None), cancellation)
    finally:
        if observer is not None:
            observer.join(timeout=5)
    require(ready.exists() and not errors and (observer is None or not observer.is_alive()),
            'controlled lifecycle was not entered and retired')
    require(receipt['status'] == ('timed_out' if mode == 'timeout' else 'cancelled'),
            'external owner did not select the requested incomplete outcome')
    retired(receipt)
    require(receipt['report' if operation == 'replay' else 'record'] is None
            and not (directory / 'result').exists(), 'incomplete operation published an answer')
    require(source.read_bytes() == original, 'lifecycle check changed original input')
    return {'label': label, 'receipt': receipt, 'controlled': True,
            'boundary': 'Installed model admission and owner, with only its private pricing seam '
            'held after the input gate. Caller Event, no console/host signal. This witnesses '
            'outer timeout/cancellation/retirement, not real numerical runtime or memory stress.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path, help='new external acceptance directory')
    args = parser.parse_args()
    origin = Path(bj.__file__).resolve()
    require('site-packages' in origin.parts, 'requires an externally installed wheel')
    root = args.output.absolute()
    root.mkdir(exist_ok=False)
    rows = []
    tiny = request([1, 0, 0, 0, 0, 0, 0, 0, 0, 2])
    rows.append(calculate(root, 'delayed-natural', tiny))
    natural = root / 'delayed-natural/result/decision.json'
    values = json.loads(natural.read_bytes())['decision']['evs']
    require(set(values) == {'S', 'H', 'D'} and all(
        math.isclose(values[key], expected, rel_tol=0, abs_tol=1e-12)
        for key, expected in {'S': -1, 'H': -1 / 3, 'D': -2 / 3}.items()),
        'tiny all-wagers settlement differs from independently qualified values')
    rows.append(reuse(root, 'natural-replay', natural))
    rows.append(calculate(root, 'sole-stand', request([1, 0, 0, 0, 0, 0, 0, 0, 0, 0])))
    sole = root / 'sole-stand/result/decision.json'
    require(json.loads(sole.read_bytes())['decision']['margin'] is None,
            'sole stand has no runner-up margin')
    rows.append(reuse(root, 'sole-replay', sole))
    rows.append(calculate(root, 'eight-card', request([1, 0, 1, 0, 1, 0, 1, 1, 1, 2])))
    eight = root / 'eight-card/result/decision.json'
    rows.append(reuse(root, 'eight-replay', eight))
    for label, value, expected in [
        ('h17', request([1, 0, 0, 1, 0, 0, 0, 0, 0, 1],
                        cards=['T', '8'], up='6', s17=False),
         {'S': -1 / 3, 'H': -1, 'D': -2}),
        ('later-hit', request([0, 0, 0, 0, 0, 0, 1, 1, 1, 1], cards=['2', '2'], up='A'),
         {'S': -1, 'H': -1 / 3, 'D': -2}),
        ('raw-rational-tie', request([0, 1, 0, 0, 0, 0, 0, 1, 0, 2], cards=['2', '2']),
         {'S': -2 / 3, 'H': -2 / 3, 'D': -4 / 3}),
    ]:
        rows.append(calculate(root, label, value))
        path = root / label / 'result/decision.json'
        answer = json.loads(path.read_bytes())['decision']
        require(answer['evs'].keys() == expected.keys() and all(
            math.isclose(answer['evs'][key], exact, rel_tol=0, abs_tol=1e-12)
            for key, exact in expected.items()), 'installed qualified full map differs')
        require((answer['action'], answer['margin']) == deferred_second_card.rank(answer['evs']),
                'installed raw ranking differs')
        if label == 'raw-rational-tie':
            require(answer['action'] in ('S', 'H'), 'raw winner is not an exact tied maximizer')
        rows.append(reuse(root, label + '-replay', path))
    derived = json.loads(eight.read_bytes())
    derived['decision']['evs']['H'] = math.nextafter(derived['decision']['evs']['H'], math.inf)
    changed = root / 'altered-answer.json'
    changed.write_bytes(calculation._json_bytes(derived))
    rows.append(reuse(root, 'altered-replay', changed, 'differences', 1))
    for label, limits in [('state-refusal', {'max_states': 1}),
                          ('time-refusal', {'max_seconds': 1e-9})]:
        rows.append(calculate(root, label, request(tiny['input']['unseen_counts'], **limits),
                              'resource_limited', 4))
        limited = json.loads(natural.read_bytes())
        for key, value in limits.items():
            limited['model']['enumeration_state_limit' if key == 'max_states'
                             else 'enumeration_seconds_limit'] = value
        path = root / f'{label}-record.json'
        path.write_bytes(calculation._json_bytes(limited))
        rows.append(reuse(root, label + '-replay', path, 'resource_limited', 4))
    exhausted = request([0, 0, 0, 0, 0, 1, 0, 0, 0, 1])
    rows.append(calculate(root, 'continuation-refusal', exhausted, 'calculation_error', 5))
    invalid = request(tiny['input']['unseen_counts'])
    invalid['input']['can_split'] = True
    rows.append(calculate(root, 'unsupported-split', invalid, 'invalid_request', 2))
    for operation, source in [('calculate', root / 'delayed-natural-request.json'),
                               ('replay', natural)]:
        for mode in ('timeout', 'cancel'):
            rows.append(lifecycle(root, source, operation, mode))
    rows.append(reuse(root, 'following-success', eight))
    result = {'status': 'passed', 'installed_origin': str(origin), 'platform': sys.platform,
              'records': rows,
              'boundary': 'Genuine installed calculation, direct/protected replay and retained '
              'source/work joins. Altered answers and limit records are labeled derived cases. '
              'This is consumer and tiny-value acceptance, not a universal stock-size, '
              'independent general-mathematics, memory-stress or native/browser claim.'}
    (root / 'acceptance.json').write_bytes(calculation._json_bytes(result))
    print(json.dumps({'status': result['status'], 'cases': len(rows),
                      'installed_origin': str(origin)}, allow_nan=False))


if __name__ == '__main__':
    main()
