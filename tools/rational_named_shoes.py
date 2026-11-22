"""Compare every action value on named small shoes with exact fractions.

`docs/rational-cross-check.md` checks 45 published cells, the bounded example
requests and random small shoes. This script adds a table anyone can read cell
by cell. For each named shoe below it takes every two card player hand that is
not a natural and every dealer upcard, values stand, hit and double with
`bj.ev.best_action`, values the two hand split of each pair with
`bj.joint_split`, and compares each value with the exact fraction from
`tests/rational_reference.py`, which imports nothing from `bj`. The difference
is computed exactly, as the floating point value converted to a fraction minus
the exact value, and only then turned into a float.

A shoe lists the unseen counts in the order A, 2 to 9, T. They include the
dealer's hole card, as the unseen counts of a request do. A value the engine
refuses must also be refused by the reference, and the table records those
cells as refusals, not as zeros.

    python tools/rational_named_shoes.py --output docs/rational-named-shoes-results.json
    python tools/rational_named_shoes.py --check
"""
from __future__ import annotations

import argparse
import json
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]

import rational_reference as exact  # noqa: E402

from bj import ev  # noqa: E402
from bj.common_shoe import reference_counts  # noqa: E402
from bj.core import Rules  # noqa: E402
from bj.joint_split import (ReferenceLimitExceeded, UnsupportedShoeError,  # noqa: E402
                            joint_split_value)

RESULTS = ROOT / 'docs/rational-named-shoes-results.json'
#: A difference above this would be more than rounding in values of a few units.
BOUND = Fraction(1, 10 ** 13)
SHOES = {
    'one of each rank': (1, 1, 1, 1, 1, 1, 1, 1, 1, 1),
    'ten rich': (1, 1, 1, 1, 1, 1, 1, 0, 0, 4),
    'aces and tens': (3, 0, 0, 0, 0, 0, 0, 0, 0, 5),
    'low cards': (2, 2, 2, 2, 2, 1, 0, 0, 0, 0),
    'middle cards': (0, 0, 1, 1, 2, 2, 2, 2, 1, 1),
}
S17 = {'S17': True, 'H17': False}


def hands():
    """Every two card hand below 21, as sorted rank index pairs."""
    return [(a, b) for a in range(10) for b in range(a, 10) if exact._hand((a, b))[0] < 21]


def hand_name(cards):
    return ','.join(exact.RANKS[card] for card in cards)


def _cell(engine, value):
    """One compared value. The difference is exact before it becomes a float."""
    return {'engine': engine, 'exact': float(value),
            'difference': float(Fraction(engine) - value)}


def post_peek_cells(cards, up, counts, s17):
    names = tuple(exact.RANKS[card] for card in cards)
    reference = exact.PostPeekHand(up, s17)
    try:
        _, engine, _ = ev.best_action(names, exact.RANKS[up], shoe=counts,
                                      rules=Rules(s17=s17), can_split=False)
    except ValueError:
        try:
            reference.values(cards, counts)
        except exact.Refused:
            return {'refused': True}
        raise AssertionError(f'{names} v {exact.RANKS[up]} refused only by the engine')
    values = reference.values(cards, counts)
    assert set(values) == set(engine), (names, up)
    return {action: _cell(engine[action], values[action]) for action in sorted(values)}


def split_cell(pair, up, counts, s17):
    options = dict(double_after_split=True, stand_soft_17=s17)
    arguments = (pair, up, counts)
    # Only the state cap may stop a cell, never the clock, so a rerun finds the same cells.
    try:
        found = joint_split_value(exact.RANKS[pair], exact.RANKS[up], reference_counts(counts),
                                 max_seconds=1e9, **options).value
    except ReferenceLimitExceeded:
        return {'limited': True}
    except UnsupportedShoeError:
        try:
            exact.common_shoe_split(*arguments, extra_slots=0, **options)
        except exact.Refused:
            return {'refused': True}
        raise AssertionError(f'{pair},{pair} v {up} refused only by the engine')
    return _cell(found, exact.common_shoe_split(*arguments, extra_slots=0, **options))


def compute(names=None):
    """Every cell of the named shoes, or of just `names`."""
    shoes = {}
    for name in names or SHOES:
        counts = SHOES[name]
        cells = {}
        for rule, s17 in S17.items():
            for cards in hands():
                for up in range(10):
                    key = f'{rule} {hand_name(cards)} v {exact.RANKS[up]}'
                    cell = post_peek_cells(cards, up, counts, s17)
                    if cards[0] == cards[1]:
                        cell['P'] = split_cell(cards[0], up, counts, s17)
                    cells[key] = cell
        shoes[name] = {'unseen': list(counts), 'cells': cells}
    return {'description': __doc__.split('\n\n')[0].replace('\n', ' '),
            'order': 'A, 2 to 9, T', 'shoes': shoes}


def summary(results):
    """Counts and the largest difference per shoe, as the document states them."""
    out = {}
    for shoe, body in results['shoes'].items():
        values = refusals = limited = 0
        worst = (None, 0.0)
        for key, cell in body['cells'].items():
            if cell.get('refused'):
                refusals += 1
            for action, value in cell.items():
                if action == 'refused':
                    continue
                if 'difference' in value:
                    values += 1
                    if abs(value['difference']) > abs(worst[1]):
                        worst = (f'{key} {action}', value['difference'])
                elif value.get('refused'):
                    refusals += 1
                elif value.get('limited'):
                    limited += 1
        out[shoe] = {'values': values, 'refused': refusals, 'limited': limited,
                     'largest': {'cell': worst[0], 'difference': worst[1]}}
    return out


def dump(results):
    """JSON with one line per cell, so the saved file stays readable and small."""
    nl = chr(10)
    shoes = []
    for name, body in results['shoes'].items():
        cells = (',' + nl).join(f'   {json.dumps(key)}: {json.dumps(cell)}'
                                for key, cell in body['cells'].items())
        shoes.append(f'  {json.dumps(name)}: {{"unseen": {json.dumps(body["unseen"])}, '
                     f'"cells": {{{nl}{cells}{nl}  }}}}')
    lines = ['{', f' "description": {json.dumps(results["description"])},',
             f' "order": {json.dumps(results["order"])},', ' "shoes": {',
             (',' + nl).join(shoes), ' },',
             f' "summary": {json.dumps(results["summary"], indent=1)}', '}']
    return nl.join(lines) + nl


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--output', type=Path, help='write a new results file here')
    action.add_argument('--check', action='store_true',
                        help='recompute every cell and compare it with the saved table')
    args = parser.parse_args(argv)
    results = compute()
    results['summary'] = summary(results)
    for shoe, line in results['summary'].items():
        print(shoe, line, flush=True)
    for shoe, body in results['shoes'].items():
        for key, cell in body['cells'].items():
            for action_, value in cell.items():
                if isinstance(value, dict) and 'difference' in value:
                    assert abs(Fraction(value['difference'])) < BOUND, (shoe, key, action_)
    if args.output:
        if args.output.exists():
            parser.error(f'{args.output} exists. Choose a new path.')
        args.output.write_text(dump(results), encoding='utf-8', newline='\n')
        return 0
    saved = json.loads(RESULTS.read_text(encoding='utf-8'))
    if saved != json.loads(json.dumps(results)):
        print('check failed: the saved table differs from a recomputation')
        return 1
    print('check passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
