"""Set the resplit study beside the published exact splitting values, cell by cell.

Nairn, "Exact and approximate pair splitting values for blackjack"
(arXiv:1909.13710), Tables 1 and 2, lists splitting values for a single deck
where the dealer stands on soft 17, with doubling after a split on any two
cards, once with no resplitting and once with resplitting to four hands. The
saved studies of this repository with one deck, S17, DAS, a peeking dealer and
no resplitting of aces describe the same table. This script lines the two up
for every cell both state, with the published value transcribed in
`docs/published-resplit-paper-values.json`.

A cell is left out when the rules differ or the published value is unreadable:
dealer up cards A and T, where the published values leave out a dealer natural
that the peeking dealer here includes, the resplit row of A,A, where the paper
resplits aces and this table does not, and the one cell the paper prints
without a readable value. Three values of this repository sit in each cell.

1. `default`, the default's own split value.
2. `play`, what the default's own choices earn when every hand is dealt from
   one shared shoe, which is how the published values are dealt.
3. `best`, the best two hand shared shoe value in the no resplit row, and in
   the resplit row the bound from `docs/resplit-study-decks-1-results.json`,
   which is a lower bound on the best value.

The published strategy is a fixed basic strategy, which is not the strategy of
either value here, so two exact values of different plays are compared, not
two estimates of one number. The difference is the published value subtracted
from this repository's value.

    python tools/published_resplit_comparison.py --output docs/published-resplit-comparison.json
    python tools/published_resplit_comparison.py --check
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'
SOURCE = DOCS / 'published-resplit-paper-values.json'
RESULTS = DOCS / 'published-resplit-comparison.json'
TWO_HAND = DOCS / 'split-error-study-decks-1-results.json'
RESPLIT = DOCS / 'resplit-study-decks-1-results.json'
UPS = '23456789'
ROWS = {'no_resplit': 'no resplit', 'resplit_to_4': 'resplit to 4'}


def _cells(path):
    return {(cell['pair'], cell['up']): cell
            for cell in json.loads(path.read_text(encoding='utf-8'))['cells']}


def _ours(row, cell):
    if row == 'no_resplit':
        return {'default': cell['default_split'], 'play': cell['default_policy_in_common_shoe'],
                'best': cell['common_shoe_split']}
    return {'default': cell['default_split'], 'play': cell['default_play_in_common_shoe'],
            'best': cell['common_shoe_lower_bound']}


def compute():
    source = json.loads(SOURCE.read_text(encoding='utf-8'))
    studies = {'no_resplit': _cells(TWO_HAND), 'resplit_to_4': _cells(RESPLIT)}
    for path, table in ((TWO_HAND, 'two hand'), (RESPLIT, 'resplit')):
        rules = json.loads(path.read_text(encoding='utf-8'))['rules']
        want = dict(decks=1, s17=True, das=True, peek=True, resplit_aces=False,
                    double_any_two=True, max_hands=2 if table == 'two hand' else 4)
        wrong = {key: rules[key] for key, value in want.items() if rules[key] != value}
        if wrong:
            raise ValueError(f'the {table} study does not use the published rules: {wrong}')
    cells = []
    for hand, rows in source['values'].items():
        pair = hand[0]
        for row, by_up in rows.items():
            if row == 'resplit_to_4' and pair == 'A':
                continue
            for up in UPS:
                published = by_up[up]
                if published is None:
                    continue
                table = 1 if up in '2345' else 2
                ours = _ours(row, studies[row][(pair, up)])
                cells.append({
                    'pair': pair, 'up': up, 'row': ROWS[row], 'table': table,
                    'published': published, 'ours': ours,
                    'difference': {key: value - published for key, value in ours.items()}})
    return {'source': source['source'], 'cells': cells}


def summary(results):
    """Counts and size of the differences, split the way the document reads them."""
    cells = results['cells']
    no_resplit = {(c['pair'], c['up']): c['published'] for c in cells if c['row'] == 'no resplit'}
    groups = {
        'no resplit': [c for c in cells if c['row'] == 'no resplit'],
        'resplit, published value at least its no resplit value':
            [c for c in cells if c['row'] == 'resplit to 4'
             and c['published'] >= no_resplit[(c['pair'], c['up'])]],
        'resplit, published value below its no resplit value':
            [c for c in cells if c['row'] == 'resplit to 4'
             and c['published'] < no_resplit[(c['pair'], c['up'])]]}
    out = {}
    for name, group in groups.items():
        differences = [abs(c['difference']['play']) for c in group]
        worst = max(group, key=lambda c: abs(c['difference']['play']))
        out[name] = {
            'cells': len(group),
            'mean_abs_play': statistics.fmean(differences),
            'max_abs_play': max(differences),
            'worst': f"{worst['pair']},{worst['pair']} v {worst['up']}",
            'play_below_published': sum(c['difference']['play'] < 0 for c in group)}
    # Where the published resplit value is below its own no resplit value, that row
    # cannot be a value with an optional resplit, so also set it against the other row.
    last = out['resplit, published value below its no resplit value']
    gaps = [abs(c['ours']['play'] - no_resplit[(c['pair'], c['up'])])
            for c in groups['resplit, published value below its no resplit value']]
    last['mean_abs_play_vs_published_no_resplit'] = statistics.fmean(gaps)
    last['max_abs_play_vs_published_no_resplit'] = max(gaps)
    return out


def dump(results):
    nl = chr(10)
    cells = (',' + nl).join('  ' + json.dumps(cell) for cell in results['cells'])
    return (f'{{{nl} "source": {json.dumps(results["source"], indent=1)},{nl}'
            f' "summary": {json.dumps(results["summary"], indent=1)},{nl}'
            f' "cells": [{nl}{cells}{nl} ]{nl}}}{nl}')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--output', type=Path, help='write a new results file here')
    action.add_argument('--check', action='store_true',
                        help='recompute every cell and compare it with the saved table')
    args = parser.parse_args(argv)
    if args.output and args.output.exists():
        parser.error(f'{args.output} exists. Choose a new path.')
    results = compute()
    results['summary'] = summary(results)
    for name, line in results['summary'].items():
        print(name, line)
    if args.output:
        args.output.write_text(dump(results), encoding='utf-8', newline='\n')
        return 0
    if json.loads(RESULTS.read_text(encoding='utf-8')) != json.loads(json.dumps(results)):
        print('check failed: the saved table differs from a recomputation')
        return 1
    print('check passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
