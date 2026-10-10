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
from fractions import Fraction
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
from bj import bounded_ace_resplit, bounded_resplit, common_shoe, late_surrender


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


def common_request(cards, up, counts, *, rules=None, double=True, pair=True, limit=100000):
    value = request(cards, up, counts, rules={'max_hands': 2, **(rules or {})},
                    double=double, pair=pair)
    value.update(schema=dict(calc.COMMON_REQUEST_SCHEMA), model=dict(common_shoe.MODEL),
                 limits={'max_states': limit})
    return value


def surrender_request(cards, up, counts, *, rules=None, double=True, surrender=True,
                      limit=100000):
    value = request(cards, up, counts,
                    rules={'max_hands': 1, 'surrender': True, 'resplit_aces': False,
                           'hit_split_aces': False, **(rules or {})},
                    double=double, pair=False)
    value['input']['can_surrender'] = surrender
    value.update(schema=dict(calc.SURRENDER_REQUEST_SCHEMA), model=dict(late_surrender.MODEL),
                 limits={'max_states': limit})
    return value


def resplit_request(cards, up, counts, *, rules=None, double=True, pair=True, limit=100000):
    value = request(cards, up, counts,
                    rules={'max_hands': 3, 'surrender': False, 'resplit_aces': False,
                           'hit_split_aces': False, **(rules or {})},
                    double=double, pair=pair)
    value.update(schema=dict(calc.RESPLIT_REQUEST_SCHEMA), model=dict(bounded_resplit.MODEL),
                 limits={'max_states': limit})
    return value


def ace_request(up, counts, *, rules=None, double=True, pair=True, limit=100000):
    value = request(['A', 'A'], up, counts,
                    rules={'max_hands': 3, 'surrender': False, 'resplit_aces': True,
                           'hit_split_aces': False, **(rules or {})},
                    double=double, pair=pair)
    value.update(schema=dict(calc.ACE_RESPLIT_REQUEST_SCHEMA),
                 model=dict(bounded_ace_resplit.MODEL), limits={'max_states': limit})
    return value


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
    bounded = value['schema']['version'] in (2, 3, 4, 5)
    if bounded:
        work = receipt['work']
        require(saved['schema']['version'] == value['schema']['version'] + 1 and
                saved['model']['enumeration_state_limit'] == value['limits']['max_states'] and
                work['limit'] == value['limits']['max_states'] and
                0 <= work['states'] <= work['limit'] and
                work['states'] == work['attempted_states'] == sum(work['state_counts'].values()),
                'bounded model or whole-request state accounting differs')
        if value['schema']['version'] == 3:
            require(saved['model'] == late_surrender.model_record(
                        value['input']['dealer_up'], value['limits']['max_states']) and
                    saved['state']['action_controls'] == {
                        'can_double': value['input']['can_double'], 'can_split': False,
                        'can_surrender': value['input']['can_surrender']} and
                    set(work['state_counts']) <= late_surrender.ROOT_FAMILIES and
                    receipt['policy']['algorithmic_work_limit']['includes'] ==
                    'root_draw_hit_double_distribution_dealer' and
                    'split_cooperative_seconds' not in receipt['policy']['algorithmic_work_limit'],
                    'late model, controls or root-only policy differs')
        elif value['schema']['version'] == 4:
            require(saved['model'] == bounded_resplit.model_record(
                        value['input']['dealer_up'], value['limits']['max_states']) and
                    saved['state']['action_controls'] == {
                        'can_double': value['input']['can_double'],
                        'can_split': value['input']['can_split']} and
                    set(work['state_counts']) <= bounded_resplit.FAMILIES and
                    receipt['policy']['algorithmic_work_limit'] == {
                        'name': 'whole_request_uncached_enumeration_states',
                        'max_states': value['limits']['max_states'],
                        'includes': 'root_draw_hit_double_distribution_dealer_and_'
                                    'resplit_draw_play_settle_dealer',
                        'split_cooperative_seconds': 10.0},
                    'resplit model, current controls or whole-family policy differs')
            require(value['input']['can_split'] or
                    set(work['state_counts']) <= bounded_resplit.ROOT_FAMILIES,
                    'disabled original split still entered a joint continuation')
        elif value['schema']['version'] == 5:
            require(saved['model'] == bounded_ace_resplit.model_record(
                        value['input']['dealer_up'], value['limits']['max_states']) and
                    saved['model']['name'] == 'common_shoe_bounded_ace_resplit' and
                    saved['model']['version'] == 1 and
                    saved['state']['action_controls'] == {
                        'can_double': value['input']['can_double'],
                        'can_split': value['input']['can_split']} and
                    set(work['state_counts']) <= bounded_ace_resplit.FAMILIES and
                    receipt['policy']['algorithmic_work_limit'] == {
                        'name': 'whole_request_uncached_enumeration_states',
                        'max_states': value['limits']['max_states'],
                        'includes': 'root_draw_hit_double_distribution_dealer_and_'
                                    'ace_resplit_draw_play_settle_dealer',
                        'split_cooperative_seconds': 10.0},
                    'ace model, current controls or whole-family policy differs')
            require(any(name.startswith('ace_resplit_') for name in work['state_counts'])
                    is value['input']['can_split'],
                    'original split control differs from actual ace work')
            require(value['input']['can_split'] or
                    set(work['state_counts']) <= bounded_ace_resplit.ROOT_FAMILIES,
                    'disabled original ace split entered a joint continuation')
    require(saved['state']['cards'] == value['input']['cards'] and
            saved['state']['shoe']['counts'] == value['input']['unseen_counts'],
            'card order or supplied counts changed')
    replay = command(['bj-advise', '--replay', str(record_path), '--json'], 0)
    require(replay['status'] == 'agreement' and replay['recorded'] == replay['recomputed'],
            'existing installed replay differs')
    require(replay['modeled_input'] == {'state': saved['state'], 'rules': saved['rules'],
                                      'model': saved['model']},
            'installed replay did not retain the complete saved modeled inputs')
    require(digest(record_path) == {k: receipt['record'][k] for k in ('bytes', 'sha256')},
            'replay modified successful record')
    return saved, {'label': label, 'record': str(record_path), **digest(record_path),
                   'status': receipt['status'], 'replay': replay['status'],
                   'policy': receipt['policy'], 'cleanup': receipt['cleanup'],
                   **({'work': receipt['work'], 'schema': saved['schema'],
                       'model': saved['model']} if bounded else {})}


def lifecycle(root, source, mode, *, common=False, surrender=False, resplit=False, ace=False):
    """Use existing main or a bounded family's owned Event with one controlled child."""
    require(sum((common, surrender, resplit, ace)) <= 1,
            'controlled child requires one selected family')
    label = 'controlled-' + ('ace-' if ace else 'resplit-' if resplit else 'late-' if surrender else
                            'common-' if common else '') + mode
    directory = root / label
    ready = root / (label + '-ready')
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
    target = ('_bounded_ace_resplit_record' if ace else '_bounded_resplit_record' if resplit else
              '_late_surrender_record' if surrender else
              '_common_shoe_record' if common else 'decision_record')
    code += (f'record.{target}=controlled\n'
             'sys.stdin=io.TextIOWrapper(io.BytesIO(raw))\n'
             'runpy.run_module("bj._calculation_worker",run_name="__main__")\n')
    original = subprocess.Popen

    def fixed_child(argv, **options):
        require(argv == [sys.executable, '-I', '-B', '-m', 'bj._calculation_worker'],
                'unexpected private worker command')
        return original([sys.executable, '-I', '-B', '-c', code], **options)

    cancellation_errors = []
    observer = None
    cancellation = threading.Event()
    if mode == 'cancel':
        def cancel_entered():
            deadline = time.monotonic() + 5
            while not ready.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            if not ready.exists():
                cancellation_errors.append('child did not enter controlled long calculation')
                return
            if common or surrender or resplit or ace:
                cancellation.set()  # Owned caller Event, no console or host signal.
            else:
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
            if common or surrender or resplit or ace:
                selected = calc._policy(1 if mode == 'timeout' else 8, None)
                receipt = calc._run(source, directory, selected, cancellation)
                status = calc.EXIT_STATUSES[receipt['status']]
                output.buffer.write(calc._json_bytes(receipt))
            else:
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
    return {'label': label, 'status': receipt['status'], 'exit': status,
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
    cases += [('common-hidden', common_request(['5', '5'], 'T', [0]*6+[2, 1, 1, 3])),
              ('common-double', common_request(['2', '2'], '7', [0]*7+[7, 0, 0])),
              ('common-aces', common_request(['A', 'A'], '7', [0]*9+[4])),
              ('common-h17', common_request(['A', 'A'], '6', [1]+[0]*5+[1, 1, 1, 2],
                                           rules={'das': False, 's17': False}))]
    cases += [('common-control-' + label, common_request(['T', 'T'], '7', [1]+[0]*8+[5],
               double=double, pair=pair))
              for label, double, pair in [('TT', True, True), ('FT', False, True),
                                         ('TF', True, False), ('FF', False, False)]]
    cases += [
        ('late-winning', surrender_request(['T', '6'], 'T', [0]*9+[3])),
        ('late-disabled', surrender_request(['T', '6'], 'T', [0]*9+[3], surrender=False)),
        ('late-tie', surrender_request(['T', '8'], 'T', [0]*7+[2, 0, 2])),
        ('late-hidden', surrender_request(['T', '4'], 'T', [0, 1, 1, 0, 0, 0, 1, 1, 1, 1])),
        ('late-peek', surrender_request(['T', '4'], 'T', [1, 0, 1, 0, 0, 0, 1, 1, 1, 1])),
        ('late-h17', surrender_request(['T', '8'], '6', [1, 0, 0, 1, 0, 0, 0, 0, 0, 1],
                                       rules={'s17': False})),
        ('late-last-draw', surrender_request(['A', '6'], 'T', [3, 0, 0, 0, 0, 0, 1, 0, 0, 0])),
        ('late-continuation', surrender_request(['2', '2'], 'T', [0]*9+[3])),
        ('late-control-FT', surrender_request(['T', '6'], 'T', [0]*9+[3], double=False)),
        ('late-control-FF', surrender_request(['T', '6'], 'T', [0]*9+[3],
                                               double=False, surrender=False)),
    ]
    resplit_eights = [0]*7+[8, 0, 0]
    cases += [
        ('resplit-winning', resplit_request(['8', '8'], '6', resplit_eights,
                                            rules={'das': False})),
        ('resplit-das-h17', resplit_request(['8', '8'], '6', resplit_eights,
                                            rules={'das': True, 's17': False})),
        ('resplit-disabled', resplit_request(['8', '8'], '6', resplit_eights, pair=False)),
        ('resplit-control-FT', resplit_request(['8', '8'], '6', resplit_eights, double=False)),
        ('resplit-tie', resplit_request(['T', 'T'], 'T', [0]*9+[8])),
        ('resplit-declined', resplit_request(['8', '8'], 'T', resplit_eights)),
        ('resplit-hidden', resplit_request(['T', 'T'], '9', [0]*7+[2, 2, 4])),
        ('resplit-peek', resplit_request(['T', 'T'], 'T', [2]+[0]*8+[6])),
        ('resplit-ace-peek', resplit_request(['T', 'T'], 'A', [0]*7+[1, 0, 7])),
        ('resplit-soft17', resplit_request(['T', 'T'], 'A', [0]*5+[1, 0, 1, 0, 6])),
    ]
    ace_hidden = [3]+[0]*8+[2]
    cases += [
        ('ace-hidden', ace_request('7', ace_hidden, rules={'das': False})),
        ('ace-disabled', ace_request('7', ace_hidden, pair=False)),
        ('ace-optional', ace_request('7', [5]+[0]*9)),
        ('ace-peek', ace_request('T', [1]+[0]*8+[4])),
        ('ace-ace-peek', ace_request('A', [0]*7+[1, 0, 4])),
        ('ace-das', ace_request('7', ace_hidden, rules={'das': True})),
        ('ace-control-FT', ace_request('7', ace_hidden, double=False)),
        ('ace-control-FF', ace_request('7', ace_hidden, double=False, pair=False)),
        ('ace-extra', ace_request('7', [1]+[0]*8+[5])),
    ]
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
        elif label.startswith('ace-'):
            reference = {
                'ace-hidden': {'S': -1, 'H': -1, 'D': -2, 'P': Fraction(3, 10)},
                'ace-disabled': {'S': -1, 'H': -1, 'D': -2},
                'ace-optional': {'S': -1, 'H': -1, 'D': -2, 'P': -2},
                'ace-peek': {'S': -1, 'H': -1, 'D': -2, 'P': Fraction(5, 2)},
                'ace-ace-peek': {'S': -1, 'H': -1, 'D': -2, 'P': 2},
                'ace-das': {'S': -1, 'H': -1, 'D': -2, 'P': Fraction(3, 10)},
                'ace-control-FT': {'S': -1, 'H': -1, 'P': Fraction(3, 10)},
                'ace-control-FF': {'S': -1, 'H': -1},
                'ace-extra': {'S': -1, 'H': -1, 'D': -2, 'P': Fraction(7, 3)},
            }
            expected = reference[label]
            require(set(evs) == set(expected) and all(
                        abs(evs[key] - float(number)) <= 1e-12
                        for key, number in expected.items()),
                    'ace installed prices differ from qualified physical/manual witnesses')
            # Preserve binary64 ranking. Exact Fraction ties do not license a
            # policy epsilon or changing the existing engine's raw recommendation.
            ranked = sorted((key for key in ('S', 'H', 'D', 'P') if key in evs),
                            key=lambda key: evs[key], reverse=True)
            require(saved['decision']['action'] == ranked[0] and
                    saved['decision']['margin'] == evs[ranked[0]] - evs[ranked[1]],
                    'ace recommendation did not use raw binary64 ranking')
            require(saved['model']['split_eligibility'] ==
                    'matching_A_A_after_mandatory_card_with_shared_slot' and
                    saved['model']['split_aces'] ==
                    'one_card_optional_resplit_no_hit_no_double_no_natural_premium',
                    'ace local eligibility or one-card-only settlement declaration differs')
            if label in ('ace-peek', 'ace-ace-peek'):
                excluded = 'A' if value['input']['dealer_up'] == 'T' else 'T'
                require(saved['model']['hole_rank_excluded_by_peek'] == excluded,
                        'ace negative-peek exclusion direction differs')
            if label == 'ace-hidden':
                require(evs['P'] < float(Fraction(1, 2)),
                        'lawful ace price collapsed into the known-hole control')
            if label == 'ace-optional':
                require(evs['P'] != -3, 'ace optional choice became a forced extra resplit')
        elif label in ('common-hidden', 'common-double', 'common-aces', 'common-h17'):
            require(saved['schema']['version'] == 3 and
                    saved['model']['split'] == common_shoe.SPLIT_MODEL,
                    'installed common calculation did not preserve model identity')
            if label == 'common-hidden':
                require(abs(evs['P'] - float(Fraction(-9, 7))) <= 1e-12 and
                        evs['P'] < float(Fraction(-107, 84)),
                        'lawful common expectation differs from independent tiny witness')
            if label == 'common-double':
                require(evs['P'] == 4, 'shared double wagers differ from analytic case')
            if label == 'common-aces':
                require(evs['P'] == 2, 'common split aces received incorrect settlement')
        elif label.startswith('resplit-'):
            if label == 'resplit-soft17':
                require(set(evs) == {'S', 'H', 'D', 'P'} and
                        all(evs[key] == number for key, number in
                            {'S': 1, 'H': -1, 'D': -2}.items()),
                        'soft17 genuine root prices or action set differ')
                # Independent physical test obtains P from complete deals;
                # this consumer boundary does not invent a guessed fraction.
                rows.append(row)
                continue
            reference = {
                'resplit-winning': ({'S': 1, 'H': -1, 'D': -2, 'P': 3}, 'P'),
                'resplit-das-h17': ({'S': 1, 'H': -1, 'D': -2, 'P': 3}, 'P'),
                'resplit-disabled': ({'S': 1, 'H': -1, 'D': -2}, 'S'),
                'resplit-control-FT': ({'S': 1, 'H': -1, 'P': 3}, 'P'),
                'resplit-tie': ({'S': 0, 'H': -1, 'D': -2, 'P': 0}, 'S'),
                'resplit-declined': ({'S': -1, 'H': -1, 'D': -2, 'P': -2}, 'S'),
                'resplit-hidden': ({'S': 1, 'H': -1, 'D': -2, 'P': Fraction(106, 105)}, 'P'),
                'resplit-peek': ({'S': 0, 'H': Fraction(-3, 7),
                                  'D': Fraction(-6, 7), 'P': Fraction(9, 7)}, 'P'),
                'resplit-ace-peek': ({'S': 1, 'H': -1, 'D': -2, 'P': 3}, 'P'),
            }
            expected, action = reference[label]
            require(set(evs) == set(expected) and all(
                        abs(evs[key] - float(number)) <= 1e-12
                        for key, number in expected.items()) and
                    saved['decision']['action'] == action,
                    'resplit installed prices differ from independent tiny expectations')
            if label == 'resplit-tie':
                require(saved['decision']['margin'] == 0, 'resplit root exact tie was changed')
            if label == 'resplit-hidden':
                require(evs['P'] < float(Fraction(136, 105)) and
                        evs['P'] > float(Fraction(29, 30)) and
                        evs['P'] < float(Fraction(152, 147)),
                        'lawful resplit price collapsed into a qualified unsafe control')
            if label in ('resplit-peek', 'resplit-ace-peek'):
                excluded = 'A' if value['input']['dealer_up'] == 'T' else 'T'
                require(saved['model']['hole_rank_excluded_by_peek'] == excluded,
                        'resplit negative-peek exclusion direction differs')
        elif label.startswith('late-'):
            reference = {
                'late-winning': ({'S': -1, 'H': -1, 'D': -2}, 'R'),
                'late-disabled': ({'S': -1, 'H': -1, 'D': -2}, 'S'),
                'late-tie': ({'S': Fraction(-1, 2), 'H': -1, 'D': -2}, 'S'),
                'late-hidden': ({'S': Fraction(-2, 3), 'H': Fraction(-71, 120),
                                 'D': Fraction(-6, 5)}, 'R'),
                'late-peek': ({'S': Fraction(-39, 50), 'H': Fraction(-61, 100),
                               'D': Fraction(-61, 50)}, 'R'),
                'late-h17': ({'S': Fraction(-1, 3), 'H': -1, 'D': -2}, 'S'),
                'late-last-draw': ({'S': 0, 'H': 1, 'D': 2}, 'D'),
                'late-continuation': ({'S': -1, 'H': -1, 'D': -2}, 'R'),
                'late-control-FT': ({'S': -1, 'H': -1}, 'R'),
                'late-control-FF': ({'S': -1, 'H': -1}, 'S'),
            }
            expected, action = reference[label]
            if value['input']['can_surrender']:
                expected['R'] = Fraction(-1, 2)
            require(set(evs) == set(expected) and all(
                        abs(evs[key] - float(number)) <= 1e-12
                        for key, number in expected.items()) and
                    saved['decision']['action'] == action,
                    'late installed prices differ from the frozen independent tiny expectations')
            if 'R' in evs:
                require(evs['R'] == -0.5, 'late terminal price differs')
            if label == 'late-tie':
                require(saved['decision']['margin'] == 0, 'late exact tie was changed')
            if label == 'late-hidden':
                require(evs['H'] < float(Fraction(-8, 15)),
                        'late hit price admits the illegal known-hole policy')
            if label == 'late-continuation':
                require(evs['H'] != -0.5, 'later surrender leaked into the hit price')
        else:
            inputs = value['input']
            permitted = {'S', 'H'} | ({'D'} if inputs['can_double'] else set()) | (
                {'P'} if inputs['can_split'] else set())
            require(set(evs) == permitted and evs['S'] == 1.0 and
                    (not inputs['can_split'] or evs['P'] == 2.0), 'current controls differ')
        rows.append(row)
    preserved = digest(root / 'ordinary/result/decision.json')
    common_preserved = digest(root / 'common-hidden/result/decision.json')
    late_preserved = digest(root / 'late-winning/result/decision.json')
    resplit_preserved = digest(root / 'resplit-hidden/result/decision.json')
    ace_preserved = digest(root / 'ace-hidden/result/decision.json')
    refusals = [('common-state-limit', common_request(['T', 'T'], '7', [1]+[0]*8+[5],
                                                     limit=1), 4, 'resource_limited'),
                ('common-exhaustion', common_request(['8', '8'], 'T', [0]*6+[1, 1, 1, 1]),
                 5, 'calculation_error'),
                ('late-state-limit', surrender_request(['T', '6'], 'T', [0]*9+[3], limit=1),
                 4, 'resource_limited'),
                ('late-exhaustion', surrender_request(['T', '6'], '2', [0, 3]+[0]*8),
                 5, 'calculation_error'),
                ('resplit-state-limit', resplit_request(['8', '8'], '6', resplit_eights,
                                                       limit=1), 4, 'resource_limited'),
                ('resplit-exhaustion', resplit_request(['T', 'T'], '6', [2]+[0]*8+[6]),
                 5, 'calculation_error'),
                ('resplit-h17-exhaustion', resplit_request(['T', 'T'], 'A',
                                                         [0]*5+[1, 0, 1, 0, 6],
                                                         rules={'s17': False}),
                 5, 'calculation_error'),
                ('ace-state-limit', ace_request('7', [0]*9+[4], limit=1),
                 4, 'resource_limited'),
                ('ace-dealer-exhaustion', ace_request('6', [0]*9+[3]),
                 5, 'calculation_error'),
                ('ace-mandatory-exhaustion', ace_request('7', [3]+[0]*9),
                 5, 'calculation_error'),
                ('ace-h17-exhaustion', ace_request('6', [5]+[0]*9,
                                                   rules={'s17': False}),
                 5, 'calculation_error')]
    for label, value, expected_exit, expected_status in refusals:
        source = root / (label + '-request.json')
        source.write_bytes(calc._json_bytes(value))
        directory = root / label
        receipt = command(['bj-calculate', str(source), '--output-dir', str(directory),
                           '--wall-seconds', '5'], expected_exit)
        retired(receipt)
        require(receipt['status'] == expected_status and receipt['record'] is None and
                not (directory / 'result').exists(), 'bounded refusal published a partial answer')
        if expected_exit == 4:
            require(receipt['error']['type'] == 'EnumerationLimitExceeded' and
                    receipt['work']['limit'] == receipt['work']['states'] == 1 and
                    receipt['work']['attempted_states'] == 2 and
                    receipt['work']['state_counts'] == {'root_distribution': 1},
                    'bounded state refusal did not account for actual root work')
        elif label.startswith('ace-'):
            expected_type = ('ValueError' if label == 'ace-h17-exhaustion' else
                             'UnsupportedShoeError')
            require(receipt['work'] is None and receipt['error']['type'] == expected_type,
                    'ace required-continuation refusal differs from the existing worker boundary')
            expected_message = (receipt['error']['message'] ==
                                'dealer must draw to 17 but the shoe is empty'
                                if label == 'ace-h17-exhaustion' else
                                'mandatory' in receipt['error']['message']
                                if label == 'ace-mandatory-exhaustion' else
                                'dealer' in receipt['error']['message'])
            require(expected_message,
                    'ace refusal did not explain the unavailable continuation')
        rows.append({'label': label, 'status': receipt['status'], 'exit': expected_exit,
                     'policy': receipt['policy'], 'cleanup': receipt['cleanup'],
                     'error': receipt['error'], 'work': receipt['work']})
    for mode in ('timeout', 'cancel', 'error', 'exit'):
        rows.append(lifecycle(root, root / 'ordinary-request.json', mode))
    for mode in ('timeout', 'cancel'):
        rows.append(lifecycle(root, root / 'common-hidden-request.json', mode, common=True))
        rows.append(lifecycle(root, root / 'late-winning-request.json', mode, surrender=True))
        rows.append(lifecycle(root, root / 'resplit-winning-request.json', mode, resplit=True))
        rows.append(lifecycle(root, root / 'ace-hidden-request.json', mode, ace=True))
    if sys.platform == 'win32':
        rows.append(lifecycle(root, root / 'ordinary-request.json', 'memory'))
    saved, row = calculate(root, 'following', ordinary)
    rows.append(row)
    saved, row = calculate(root, 'ace-following', ace_request('7', ace_hidden))
    require(abs(saved['decision']['evs']['P'] - float(Fraction(3, 10))) <= 1e-12,
            'following ace calculation differs')
    rows.append(row)
    saved, row = calculate(root, 'resplit-following',
                           resplit_request(['8', '8'], '6', resplit_eights))
    require(saved['decision']['evs']['P'] == 3, 'following resplit calculation differs')
    rows.append(row)
    saved, row = calculate(root, 'late-following',
                           surrender_request(['T', '6'], 'T', [0]*9+[3]))
    require(saved['decision']['action'] == 'R', 'following late calculation differs')
    rows.append(row)
    saved, row = calculate(root, 'common-following',
                           common_request(['T', 'T'], '7', [1]+[0]*8+[5]))
    require(saved['decision']['evs']['P'] == 2, 'following common calculation differs')
    rows.append(row)
    require(digest(root / 'ordinary/result/decision.json') == preserved,
            'later incomplete attempts changed the prior successful result')
    require(digest(root / 'common-hidden/result/decision.json') == common_preserved,
            'later common refusals changed the prior successful common record')
    require(digest(root / 'late-winning/result/decision.json') == late_preserved,
            'later late refusals changed the prior successful late record')
    require(digest(root / 'resplit-hidden/result/decision.json') == resplit_preserved,
            'later resplit refusals changed the prior successful resplit record')
    require(digest(root / 'ace-hidden/result/decision.json') == ace_preserved,
            'later ace refusals changed the prior successful ace record')
    result = {'status': 'passed', 'installed_origin': str(origin), 'platform': sys.platform,
              'records': rows, 'boundary': 'Genuine small calculations and replay; '
              'controlled faults establish owned lifecycle, not numerical stress performance. '
              'Ace records are complete original decisions under the named bounded model; '
              'no full-shoe feasibility or independent ancestry-order proof is claimed.'}
    (root / 'acceptance.json').write_bytes(calc._json_bytes(result))
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
