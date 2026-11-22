"""The saved named shoe table against exact fractions.

`tools/rational_named_shoes.py` compares every action value on five named small
shoes with the exact reference and saves one cell per hand, dealer upcard and
rule. These tests check that the saved table is complete and within rounding,
that one shoe still recomputes to the same cells, and that
`docs/rational-cross-check.md` states what the table holds. Recomputing every
shoe takes several minutes, so that comparison runs with BJ_SLOW set.
"""
from __future__ import annotations

import json
import os
from fractions import Fraction
from pathlib import Path

import pytest

from tools import rational_named_shoes as named

ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = ROOT / 'docs/rational-cross-check.md'
SLOW = pytest.mark.skipif(
    not os.environ.get('BJ_SLOW'),
    reason='heavy recomputation, set BJ_SLOW=1 to include it',
)


@pytest.fixture(scope='module')
def saved():
    return json.loads(named.RESULTS.read_text(encoding='utf-8'))


def test_the_table_names_every_shoe_and_every_cell(saved):
    assert list(saved['shoes']) == list(named.SHOES)
    keys = [f'{rule} {named.hand_name(cards)} v {up}'
            for rule in named.S17 for cards in named.hands()
            for up in 'A23456789T']
    for name, body in saved['shoes'].items():
        assert tuple(body['unseen']) == named.SHOES[name]
        assert list(body['cells']) == keys, name
        for key, cell in body['cells'].items():
            hand = key.split(' ')[1].split(',')
            assert ('P' in cell) == (hand[0] == hand[1]), key


def test_every_compared_value_is_within_rounding(saved):
    compared = 0
    for name, body in saved['shoes'].items():
        for key, cell in body['cells'].items():
            for action, value in cell.items():
                if action == 'refused' or 'difference' not in value:
                    continue
                compared += 1
                assert abs(Fraction(value['difference'])) < named.BOUND, (name, key, action)
    assert compared == sum(line['values'] for line in saved['summary'].values())


def test_the_saved_summary_matches_the_saved_cells(saved):
    assert named.summary(saved) == saved['summary']


def test_a_shoe_recomputes_to_the_saved_cells(saved):
    again = named.compute(['aces and tens'])
    assert again['shoes']['aces and tens'] == saved['shoes']['aces and tens']


@SLOW
def test_every_shoe_recomputes_to_the_saved_table(saved):
    again = named.compute()
    again['summary'] = named.summary(again)
    assert again == saved


def test_the_document_states_what_the_table_holds(saved):
    text = ' '.join(DOCUMENT.read_text(encoding='utf-8').split())
    summary = saved['summary']
    assert f"{sum(line['values'] for line in summary.values()):,} values" in text
    for name, line in summary.items():
        assert f'`{name}`' in text
        row = (f"| `{name}` | {sum(saved['shoes'][name]['unseen'])} | {line['values']:,} "
               f"| {line['refused']} | {line['limited']} "
               f"| {abs(line['largest']['difference']):.2e} | {line['largest']['cell']} |")
        assert row in text, row
    largest = max(summary.values(), key=lambda line: abs(line['largest']['difference']))
    assert f"{abs(largest['largest']['difference']):.2e}" in text
    readme = ' '.join((ROOT / 'README.md').read_text(encoding='utf-8').split())
    assert f"{sum(line['values'] for line in summary.values()):,} values" in readme
    assert f"{abs(largest['largest']['difference']):.2e}" in readme
