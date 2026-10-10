"""Exercise an externally installed calculation command and owned lifecycle.

Small numerical cases use the genuine worker. Fixed lifecycle faults replace
only that private worker's pricing function after its input gate. They are not
numerical acceptance or public dispatch features. No console event is sent.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from unittest.mock import patch

import bj
from bj import calculation as calc
from bj import _calculation_process as transport


def require(value, message):
    if not value:
        raise AssertionError(message)


def digest(path):
    raw = path.read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def request(cards, up, counts, *, rules=None, split=False, double=True, pair=True):
    return {'schema': dict(calc.REQUEST_SCHEMA), 'rules': rules or {},
            'input': {'cards': cards, 'dealer_up': up, 'unseen_counts': counts,
                      'is_split_hand': split, 'hand_count': 2 if split else 1,
                      'can_double': double, 'can_split': pair}}


def command(argv, expected):
    require(argv[0] in ('bj-calculate', 'bj-advise'), 'unsupported installed command')
    entry = Path(sys.executable).parent / (argv[0] + ('.exe' if os.name == 'nt' else ''))
    env = {key: value for key, value in os.environ.items()
           if key.upper() not in ('PYTHONPATH', 'PYTHONHOME')}
    options = {'creationflags': 0x08000000} if os.name == 'nt' else {}
    completed = subprocess.run([str(entry), *argv[1:]], env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               timeout=20, check=False, **options)
    require(completed.returncode == expected, f'command exit: {completed.stderr!r}')
    require(len(completed.stdout) <= 65536 and completed.stdout.endswith(b'\n'),
            'command did not deliver one bounded complete JSON message')
    return json.loads(completed.stdout)


def retired(receipt):
    require(receipt['policy_established'], 'policy was not established')
    cleanup = receipt['cleanup']
    require(cleanup['retired'] and cleanup['worker_retired'] and cleanup['transport_retired']
            and cleanup['errors'] == [], 'owned worker/transport did not retire')
    if sys.platform == 'win32':
        require(cleanup['job_empty'] is True, 'Windows Job was not observed empty')


def calculate(root, label, value):
    path = root / (label + '-request.json')
    path.write_bytes(calc._json_bytes(value))
    source = digest(path)
    directory = root / label
    receipt = command(['bj-calculate', str(path), '--output-dir', str(directory),
                       '--wall-seconds', '5'], 0)
    require(receipt['status'] == 'completed', 'genuine calculation incomplete')
    retired(receipt)
    record_path = directory / 'result/decision.json'
    require(receipt['record'] == {'path': 'result/decision.json', **digest(record_path)},
            'record identity differs from completed receipt')
    require(json.loads((directory / 'result/receipt.json').read_bytes()) == receipt,
            'retained receipt differs')
    require(digest(path) == source and
            (directory / 'request-source.json').read_bytes() == path.read_bytes(),
            'caller request or captured source changed')
    saved = json.loads(record_path.read_bytes())
    require(saved['state']['cards'] == value['input']['cards'] and
            saved['state']['shoe']['counts'] == value['input']['unseen_counts'],
            'card order or supplied counts changed')
    replay = command(['bj-advise', '--replay', str(record_path), '--json'], 0)
    require(replay['status'] == 'agreement' and replay['recorded'] == replay['recomputed'],
            'existing installed replay differs')
    require(digest(record_path) == {k: receipt['record'][k] for k in ('bytes', 'sha256')},
            'replay modified successful record')
    return saved, {'label': label, 'record': str(record_path), **digest(record_path),
                   'status': receipt['status'], 'replay': replay['status'],
                   'policy': receipt['policy'], 'cleanup': receipt['cleanup']}


def lifecycle(root, source, mode):
    """Run public main with a fixed controlled child, including its real Job."""
    directory = root / ('controlled-' + mode)
    ready = root / (mode + '-ready')
    code = (
        'import io,pathlib,runpy,sys,time;raw=sys.stdin.buffer.read();'
        'from bj import record\n'
        'def controlled(*args,**kwargs):\n'
        f' pathlib.Path({str(ready)!r}).write_text("entered")\n')
    if mode == 'memory':
        code += (' blocks=[]\n'
                 ' for _ in range(12): blocks.append(bytearray(8*1024*1024))\n'
                 ' raise AssertionError("controlled allocation exceeded the selected cap")\n')
    elif mode == 'error':
        code += ' raise ValueError("controlled calculation refusal")\n'
    elif mode == 'exit':
        code += ' import os;os._exit(17)\n'
    else:
        code += ' time.sleep(20)\n'
    code += ('record.decision_record=controlled\n'
             'sys.stdin=io.TextIOWrapper(io.BytesIO(raw))\n'
             'runpy.run_module("bj._calculation_worker",run_name="__main__")\n')
    original = subprocess.Popen

    def fixed_child(argv, **options):
        require(argv == [sys.executable, '-I', '-B', '-m', 'bj._calculation_worker'],
                'unexpected private worker command')
        return original([sys.executable, '-I', '-B', '-c', code], **options)

    cancellation_errors = []
    observer = None
    if mode == 'cancel':
        def cancel_entered():
            deadline = time.monotonic() + 5
            while not ready.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            if not ready.exists():
                cancellation_errors.append('child did not enter controlled long calculation')
                return
            # This raises SIGINT in this calling process only. It does not use
            # CTRL_C_EVENT, CTRL_BREAK_EVENT, a console attachment or keyboard.
            signal.raise_signal(signal.SIGINT)
        observer = threading.Thread(target=cancel_entered)
        observer.start()
    output, error = io.TextIOWrapper(io.BytesIO()), io.TextIOWrapper(io.BytesIO())
    args = [str(source), '--output-dir', str(directory), '--wall-seconds',
            '1' if mode == 'timeout' else '8']
    if mode == 'memory':
        args += ['--memory-mib', '64']
    try:
        with patch.object(transport.subprocess, 'Popen', side_effect=fixed_child), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            status = calc.main(args)
    finally:
        if observer is not None:
            observer.join(timeout=6)
    raw = output.buffer.getvalue()
    output.close()
    error.close()
    require(raw.endswith(b'\n') and len(raw) <= 65536, 'incomplete public attempt report')
    receipt = json.loads(raw)
    expected = {'timeout': ('timed_out', 124), 'cancel': ('cancelled', 130),
                'memory': ('resource_limited', 4), 'error': ('calculation_error', 5),
                'exit': ('worker_failed', 6)}[mode]
    require((receipt['status'], status) == expected, 'controlled outcome differs')
    require(ready.exists() and not cancellation_errors, 'controlled pricing was not entered')
    require(observer is None or not observer.is_alive(), 'cancellation observer did not retire')
    retired(receipt)
    require(receipt['record'] is None and not (directory / 'result').exists(),
            'incomplete calculation exposed a completed decision')
    require(json.loads((directory / 'outcome.json').read_bytes()) == receipt,
            'retained incomplete outcome differs')
    if mode == 'memory':
        require(receipt['error']['type'] == 'MemoryError', 'memory denial was not observed')
    return {'label': 'controlled-' + mode, 'status': receipt['status'], 'exit': status,
            'policy': receipt['policy'], 'cleanup': receipt['cleanup'], 'controlled': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path, help='new external acceptance directory')
    args = parser.parse_args()
    origin = Path(bj.__file__).resolve()
    require('site-packages' in origin.parts, 'requires an externally installed package')
    root = args.output.absolute()
    root.mkdir(exist_ok=False)
    ordinary = request(['T', '4'], 'T', [0, 1, 1, 0, 0, 0, 1, 1, 1, 1])
    cases = [('ordinary', ordinary), ('natural', request(['A', 'T'], '9',
             [3, 4, 4, 4, 4, 4, 4, 4, 3, 15], rules={'decks': 1, 'blackjack_payout': 1.25}))]
    cases += [('split-' + ''.join(cards), request(cards, 'T', [0]*8 + [1, 0],
               rules={'das': False, 'max_hands': 2}, split=True))
              for cards in (['A', 'T'], ['T', 'A'])]
    cases += [('control-' + label, request(['T', 'T'], '7', [1]+[0]*8+[5],
               rules={'max_hands': 2}, double=double, pair=pair))
              for label, double, pair in [('TT', True, True), ('FT', False, True),
                                         ('TF', True, False), ('FF', False, False)]]
    rows = []
    for label, value in cases:
        saved, row = calculate(root, label, value)
        evs = saved['decision']['evs']
        if label == 'ordinary':
            require(saved['decision']['action'] == 'H' and
                    evs == {'S': -0.6666666666666665, 'H': -0.5916666666666668,
                            'D': -1.2000000000000002} and
                    saved['decision']['margin'] == 0.07499999999999973,
                    'retained historical tiny decision differs')
        elif label == 'natural':
            require(evs == {'S': 1.25}, 'declared natural payout differs')
        elif label.startswith('split-'):
            require(evs == {'S': 1.0}, 'ordinary split-21 settlement differs')
        else:
            inputs = value['input']
            permitted = {'S', 'H'} | ({'D'} if inputs['can_double'] else set()) | (
                {'P'} if inputs['can_split'] else set())
            require(set(evs) == permitted and evs['S'] == 1.0 and
                    (not inputs['can_split'] or evs['P'] == 2.0), 'current controls differ')
        rows.append(row)
    preserved = digest(root / 'ordinary/result/decision.json')
    for mode in ('timeout', 'cancel', 'error', 'exit'):
        rows.append(lifecycle(root, root / 'ordinary-request.json', mode))
    if sys.platform == 'win32':
        rows.append(lifecycle(root, root / 'ordinary-request.json', 'memory'))
    saved, row = calculate(root, 'following', ordinary)
    rows.append(row)
    require(digest(root / 'ordinary/result/decision.json') == preserved,
            'later incomplete attempts changed the prior successful result')
    result = {'status': 'passed', 'installed_origin': str(origin), 'platform': sys.platform,
              'records': rows, 'boundary': 'Genuine small calculations and replay; '
              'controlled faults establish owned lifecycle, not numerical stress performance.'}
    (root / 'acceptance.json').write_bytes(calc._json_bytes(result))
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
