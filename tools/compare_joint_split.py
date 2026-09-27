"""Run the declared bounded comparison once and preserve every attempted cell."""
from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import os
import platform
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / 'docs/joint-split-protocol.json'
SOURCE_FILES = ('bj/joint_split.py', 'bj/ev.py', 'bj/core.py', 'bj/dealer.py',
                'tools/compare_joint_split.py', 'docs/joint-split-protocol.json')


def sha(path):
    return hashlib.sha256(path.read_text(encoding='utf-8').encode()).hexdigest()


def conditions(protocol):
    return [dict(id=f'{name}/{pair}/{up}/das-{str(das).lower()}', shoe_name=name,
                 shoe=shoe, pair=pair, dealer_up=up, double_after_split=das)
            for name, shoe in protocol['unseen_shoes'].items()
            for pair in protocol['pair_ranks']
            for up in protocol['dealer_upcards']
            for das in protocol['double_after_split']]


def ranking(values, tolerance):
    ordered = sorted(values.values(), reverse=True)
    return dict(best=[key for key, value in values.items() if ordered[0] - value <= tolerance],
                margin=ordered[0] - ordered[1], values=values)


def _worker(connection, case, protocol):
    # Import only inside the isolated child. The reference itself has no production imports.
    sys.path.insert(0, str(ROOT))
    from bj import ev
    from bj.core import Rules
    from bj.joint_split import ReferenceLimitExceeded, UnsupportedShoeError, joint_split_value

    output = {}
    started = time.perf_counter()
    try:
        limits = protocol['limits']
        reference = joint_split_value(case['pair'], case['dealer_up'], case['shoe'],
                                      double_after_split=case['double_after_split'],
                                      stand_soft_17=protocol['stand_soft_17'],
                                      max_states=limits['max_states'],
                                      max_seconds=limits['reference_seconds'])
        output['reference'] = asdict(reference)
        connection.send(dict(output, stage='reference_complete'))
        rules = Rules(s17=protocol['stand_soft_17'], das=case['double_after_split'],
                      max_hands=2, resplit_aces=False, hit_split_aces=False)
        ev.clear_caches()
        measured = time.perf_counter()
        pair = (case['pair'],) * 2
        counts = tuple(case['shoe'])
        _, values, _ = ev.best_action(pair, case['dealer_up'], counts, rules)
        output['production_seconds'] = time.perf_counter() - measured
        output['production'] = ranking(values, limits['decision_tie_tolerance'])
        exact_values = dict(values, P=reference.value)
        output['joint'] = ranking(exact_values, limits['decision_tie_tolerance'])
        output['signed_gap'] = values['P'] - reference.value
        output['absolute_gap'] = abs(output['signed_gap'])
        output['decision_changed'] = output['production']['best'] != output['joint']['best']
        output['status'] = 'completed'
    except ReferenceLimitExceeded as exc:
        output.update(status='reference_limit', error=str(exc), states=exc.states,
                      elapsed_seconds=exc.elapsed_seconds)
    except UnsupportedShoeError as exc:
        output.update(status='unsupported', error=str(exc))
    except Exception as exc:
        output.update(status='failed', error=f'{type(exc).__name__}: {exc}')
    output['worker_seconds'] = time.perf_counter() - started
    connection.send(dict(output, stage='finished'))
    connection.close()


def run_case(case, protocol):
    context = mp.get_context('spawn')
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_worker, args=(sender, case, protocol))
    started = time.perf_counter()
    result = {}
    process.start()
    sender.close()
    try:
        while time.perf_counter() - started < protocol['limits']['case_wall_seconds']:
            if receiver.poll(0.05):
                try:
                    result = receiver.recv()
                except EOFError:
                    break
                if result['stage'] == 'finished':
                    break
            elif not process.is_alive():
                break
        else:
            result.update(status='timed_out', error='case wall time limit exceeded')
        if result.get('stage') != 'finished' and result.get('status') != 'timed_out':
            result.update(status='failed', error='worker exited without a completed result')
    finally:
        process.join(timeout=0.5)
        if process.is_alive():
            process.terminate()
            process.join(timeout=2)
        receiver.close()
    result['case_wall_seconds'] = time.perf_counter() - started
    result['worker_exit_code'] = process.exitcode
    return dict(case, **result)


def write(path, document):
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.name + '.', suffix='.tmp')
    try:
        with os.fdopen(handle, 'w', encoding='utf-8', newline='\n') as stream:
            json.dump(document, stream, indent=2, allow_nan=False)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    path = args.output.resolve()
    if path.exists() or path.is_relative_to(ROOT):
        parser.error('use a new output path outside the checkout')
    status = subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True)
    if status.strip():
        parser.error('commit and review the implementation and protocol before comparison')
    protocol = json.loads(PROTOCOL.read_text())
    cases = conditions(protocol)
    if len(cases) != protocol['conditions']:
        raise ValueError('protocol condition count does not match the declared Cartesian product')
    path.parent.mkdir(parents=True, exist_ok=True)
    # Reserve the attempt path before computation. Existing attempts cannot be overwritten.
    with path.open('x', encoding='utf-8') as stream:
        stream.write('{}\n')
    document = dict(schema_version=1, protocol=protocol,
                    evaluated_revision=subprocess.check_output(
                        ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                    implementation_sha256_lf={p: sha(ROOT / p) for p in SOURCE_FILES},
                    started_utc=datetime.now(timezone.utc).isoformat(),
                    python=platform.python_version(), platform=platform.system(),
                    status='running', rows=[])
    write(path, document)
    try:
        for case in cases:
            row = run_case(case, protocol)
            document['rows'].append(row)
            write(path, document)
            print(case['id'], row['status'], flush=True)
        document['status'] = ('completed' if all(r['status'] == 'completed'
                                               for r in document['rows']) else 'with_exclusions')
    except BaseException:
        document['status'] = 'interrupted'
        raise
    finally:
        document['finished_utc'] = datetime.now(timezone.utc).isoformat()
        document['unattempted'] = [c['id'] for c in cases[len(document['rows']):]]
        write(path, document)
    print(json.dumps(dict(status=document['status'], conditions=len(document['rows']))))


if __name__ == '__main__':
    main()
