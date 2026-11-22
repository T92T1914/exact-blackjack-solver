"""The comparison with the published single deck splitting table.

`tools/published_resplit_comparison.py` sets the one deck cells of the saved
split and resplit studies beside the values transcribed from arXiv:1909.13710.
These tests recompute the saved comparison, check the transcription for the
structure the paper guarantees, and keep `docs/published-resplit-comparison.md`
and the README honest about what the comparison finds.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import published_resplit_comparison as comparison

ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = ROOT / 'docs/published-resplit-comparison.md'
HANDS = ['A,A', '2,2', '3,3', '4,4', '5,5', '6,6', '7,7', '8,8', '9,9', 'T,T']


@pytest.fixture(scope='module')
def saved():
    return json.loads(comparison.RESULTS.read_text(encoding='utf-8'))


@pytest.fixture(scope='module')
def source():
    return json.loads(comparison.SOURCE.read_text(encoding='utf-8'))


def test_the_saved_comparison_is_what_the_tool_computes(saved):
    again = comparison.compute()
    again['summary'] = comparison.summary(again)
    assert again == json.loads(json.dumps(saved))


def test_the_transcription_has_the_published_shape(source):
    values = source['values']
    assert list(values) == HANDS
    unreadable = []
    for hand, rows in values.items():
        assert set(rows) == {'no_resplit', 'resplit_to_4'}
        for row, by_up in rows.items():
            assert list(by_up) == list('23456789'), (hand, row)
            unreadable += [(hand, row, up) for up, value in by_up.items() if value is None]
    assert unreadable == [('8,8', 'resplit_to_4', '8')]


def test_every_compared_cell_names_its_table_and_the_cells_left_out(saved):
    cells = saved['cells']
    assert len(cells) == 151
    assert len([c for c in cells if c['row'] == 'no resplit']) == 80
    assert not [c for c in cells if c['row'] == 'resplit to 4' and c['pair'] == 'A']
    assert not [c for c in cells if c['up'] in 'AT']
    assert not [c for c in cells if (c['pair'], c['up'], c['row']) == ('8', '8', 'resplit to 4')]
    for cell in cells:
        assert cell['table'] == (1 if cell['up'] in '2345' else 2)
        for key, value in cell['ours'].items():
            assert cell['difference'][key] == pytest.approx(value - cell['published'], abs=1e-15)


def test_one_cell_matches_to_the_digits_the_paper_prints(saved):
    # A,A against 2 with no resplit: published 0.565702, here 0.5657038.
    cell = next(c for c in saved['cells']
                if (c['pair'], c['up'], c['row']) == ('A', '2', 'no resplit'))
    assert cell['published'] == 0.565702
    assert abs(cell['difference']['play']) < 5e-6


def test_the_document_and_readme_state_what_the_comparison_finds(saved):
    text = ' '.join(DOCUMENT.read_text(encoding='utf-8').split())
    readme = ' '.join((ROOT / 'README.md').read_text(encoding='utf-8').split())
    summary = saved['summary']
    names = list(summary)
    assert len(names) == 3
    for name, line in summary.items():
        row = (f"| {name[0].upper() + name[1:]} | {line['cells']} | {line['mean_abs_play']:.5f} "
               f"| {line['max_abs_play']:.5f} | {line['worst']} |")
        assert row in text, row
    first, _, last = (summary[name] for name in names)
    above = first['cells'] - first['play_below_published']
    assert f"{above} above and {first['play_below_published']} below with no resplit" in text
    assert (f"{last['mean_abs_play_vs_published_no_resplit']:.5f}" in text
            and f"{last['max_abs_play_vs_published_no_resplit']:.5f}" in text)
    assert last['play_below_published'] == 0
    assert 'published-resplit-comparison.md' in readme
