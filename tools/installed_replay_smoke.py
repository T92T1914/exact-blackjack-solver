"""Reuse six genuine installed calculation records through protected replay."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

import bj
from bj import _calculation_process as transport
from bj import calculation, supervised_replay


def require(value, message):
    if not value:
        raise AssertionError(message)


def identity(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def command(name, arguments, directory, code):
    entry = Path(sys.executable).parent / (name + ('.exe' if os.name == 'nt' else ''))
    env = {key: value for key, value in os.environ.items()
           if key.upper() not in ('PYTHONPATH', 'PYTHONHOME')}
    options = {'creationflags': 0x08000000} if os.name == 'nt' else {}
    completed = subprocess.run([str(entry), *arguments], cwd=directory, env=env,
                               capture_output=True, timeout=20, **options)
    require(completed.returncode == code, f'entry exit: {completed.stderr!r}')
    require(len(completed.stdout) <= 65536 and completed.stdout.endswith(b'\n'),
            'entry did not deliver one complete bounded JSON message')
    return json.loads(completed.stdout)


def replay_case(root, label, path, expected_status, code):
    raw = path.read_bytes()
    before = path.stat().st_mtime_ns
    attempt = root / label
    receipt = command('bj-replay', [str(path), '--output-dir', str(attempt),
                                   '--wall-seconds', '5'], root, code)
    require(receipt['status'] == receipt['replay_status'] == expected_status,
            'protected outcome differs from requested acceptance case')
    require(receipt['policy_established'], 'worker policy was not established')
    cleanup = receipt['cleanup']
    require(cleanup['retired'] and cleanup['worker_retired'] and cleanup['transport_retired']
            and cleanup['job_empty'] is not False and cleanup['errors'] == [],
            'owned replay did not retire')
    require(receipt['source_record'] == {**identity(raw), 'complete': True},
            'source receipt differs from the immutable input')
    require(receipt['capture_verified'] is True, 'captured bytes were not joined after retirement')
    require((attempt / 'record-source.json').read_bytes() == raw,
            'captured input differs from original bytes')
    direct = command('bj-advise', ['--replay', str(path), '--json'], root, code)
    require(direct['status'] == expected_status, 'original dispatcher outcome differs')
    if code in (0, 1):
        report_raw = (attempt / 'result/replay.json').read_bytes()
        report = json.loads(report_raw)
        require(report == direct, 'protected replay changed the original complete report')
        require(receipt['report'] == {'path': 'result/replay.json', **identity(report_raw)},
                'complete report digest differs from receipt')
        require(json.loads((attempt / 'result/receipt.json').read_bytes()) == receipt,
                'committed receipt differs from entry output')
    else:
        require(receipt['report'] is None and not (attempt / 'result').exists(),
                'incomplete replay published a result')
        message = json.loads((attempt / 'worker.stdout').read_bytes())
        require(message['report'] == direct, 'protected refusal changed original semantics')
    require(path.read_bytes() == raw and path.stat().st_mtime_ns == before,
            'replay modified immutable source')
    return {'label': label, 'input': str(path), **identity(raw), 'receipt': receipt}


def snapshot_case(root, original):
    """Hold the contained child after capture, replacing only a disposable source copy."""
    raw = original.read_bytes()
    source = root / 'snapshot-source.json'
    source.write_bytes(raw)
    attempt = root / 'snapshot-attempt'
    ready, release = root / 'snapshot-ready', root / 'snapshot-release'
    code = (
        'import io,pathlib,runpy,sys,time;raw=sys.stdin.buffer.read();'
        'from bj import calculation\n'
        'write=calculation._exclusive_bytes\n'
        'def held(path,captured):\n'
        ' write(path,captured)\n'
        ' if path.name == "record-source.json":\n'
        f'  pathlib.Path({str(ready)!r}).write_bytes(b"captured")\n'
        '  deadline=time.monotonic()+4\n'
        f'  while not pathlib.Path({str(release)!r}).exists():\n'
        '   if time.monotonic()>deadline: raise TimeoutError("snapshot release absent")\n'
        '   time.sleep(0.01)\n'
        'calculation._exclusive_bytes=held\n'
        'sys.stdin=io.TextIOWrapper(io.BytesIO(raw))\n'
        'runpy.run_module("bj._replay_worker",run_name="__main__")\n')
    launch = subprocess.Popen

    def controlled_child(argv, **options):
        require(argv == [sys.executable, '-I', '-B', '-m', 'bj._replay_worker'],
                'unexpected private snapshot worker command')
        return launch([sys.executable, '-I', '-B', '-c', code], **options)

    errors = []

    def replace_captured():
        try:
            deadline = time.monotonic() + 4
            while not ready.exists():
                if time.monotonic() > deadline:
                    raise TimeoutError('contained worker did not finish source capture')
                time.sleep(0.01)
            source.write_bytes(b'replaced after contained capture\n')
            release.write_bytes(b'release')
        except Exception as exc:
            errors.append(str(exc))

    observer = threading.Thread(target=replace_captured)
    observer.start()
    try:
        with patch.object(transport.subprocess, 'Popen', side_effect=controlled_child):
            receipt = supervised_replay._run(
                source, attempt, calculation._policy(5, None), threading.Event())
    finally:
        observer.join(timeout=5)
    require(not observer.is_alive() and not errors, f'snapshot observer failed: {errors}')
    require(receipt['status'] == 'agreement' and receipt['capture_verified']
            and receipt['policy_established'], 'controlled snapshot replay did not complete')
    cleanup = receipt['cleanup']
    require(cleanup['retired'] and cleanup['worker_retired'] and cleanup['transport_retired']
            and cleanup['job_empty'] is not False and not cleanup['errors'],
            'controlled snapshot worker did not retire')
    require(receipt['source_record'] == {**identity(raw), 'complete': True}
            and (attempt / 'record-source.json').read_bytes() == raw,
            'snapshot receipt/artifact did not retain the original captured bytes')
    require(source.read_bytes() == b'replaced after contained capture\n',
            'controlled original replacement did not occur')
    direct = command('bj-advise', ['--replay', str(original), '--json'], root, 0)
    require(json.loads((attempt / 'result/replay.json').read_bytes()) == direct,
            'replay used the replaced path instead of the original captured record')
    return {'label': 'controlled-snapshot', 'input': str(source), **identity(raw),
            'receipt': receipt, 'boundary': 'Disposable child pause after exclusive capture, '
            'followed by replacement of only a disposable source copy. Installed dispatch and '
            'existing owner run normally. This is a controlled lifecycle witness.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('calculation_journey', type=Path,
                        help='existing installed_calculation_smoke output')
    parser.add_argument('output', type=Path,
                        help='new external protected-replay acceptance directory')
    args = parser.parse_args()
    origin = Path(bj.__file__).resolve()
    require('site-packages' in origin.parts, 'requires an externally installed package')
    root = args.output.absolute()
    root.mkdir(exist_ok=False)
    journey = args.calculation_journey.absolute()
    selections = [('ordinary', 1), ('control-FF', 2), ('common-hidden', 3),
                  ('late-winning', 4), ('resplit-hidden', 5), ('ace-hidden', 6)]
    rows = []
    for label, schema in selections:
        path = journey / label / 'result/decision.json'
        require(json.loads(path.read_bytes())['schema']['version'] == schema,
                'genuine input has the wrong selected historical/model schema')
        rows.append(replay_case(root, label, path, 'agreement', 0))
    ace_path = journey / 'ace-hidden/result/decision.json'
    source = json.loads(ace_path.read_bytes())
    for label, change, status, code in [
        ('one-ulp', lambda value: value['decision']['evs'].update(
            P=math.nextafter(value['decision']['evs']['P'], math.inf)), 'differences', 1),
        ('missing-P', lambda value: (value['decision']['evs'].pop('P'),
                                    value['decision'].update(action='S', action_name='STAND')),
         'differences', 1),
        ('state-limit', lambda value: value['model'].update(
            enumeration_state_limit=1), 'resource_limited', 4),
        ('unsupported-limit', lambda value: value['model'].update(
            enumeration_state_limit=100001), 'unsupported_record', 3),
    ]:
        derived = json.loads(json.dumps(source))
        change(derived)
        path = root / f'{label}.json'
        path.write_bytes((json.dumps(derived, indent=2, allow_nan=False) + '\n').encode())
        rows.append(replay_case(root, label, path, status, code))
    invalid = root / 'invalid.json'
    invalid.write_bytes(b'{"schema":{"version":1,"version":1}}\n')
    rows.append(replay_case(root, 'invalid-input', invalid, 'invalid_input', 2))
    rows.append(replay_case(root, 'following-success', ace_path, 'agreement', 0))
    rows.append(snapshot_case(root, ace_path))
    result = {
        'status': 'passed', 'installed_origin': str(origin), 'platform': sys.platform,
        'records': rows, 'boundary': 'Six genuine completed inputs and separately labeled derived '
        'comparison/refusal cases, plus a controlled same-worker snapshot witness. '
        'This checks protected installed reuse, '
        'not independent numerical '
        'correctness, memory stress, full-shoe feasibility or native/browser behavior.',
    }
    raw = (json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    (root / 'acceptance.json').write_bytes(raw)
    print(json.dumps(result, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
