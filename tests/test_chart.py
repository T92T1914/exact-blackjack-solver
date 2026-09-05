"""Tests for bj.chart: the Markdown renderer and its inverse.

The renderer prints whichever chart it is given and parse_chart reads one
back.  Round-tripping the transcription is the cheap test.  The one that
matters is the last: the chart printed in README.md is parsed and compared
cell by cell with what bj.ev.derive_table computes, so the README cannot
carry a stale or hand-edited chart without this file failing.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from bj.chart import LEGEND, describe_rules, parse_chart, render_chart, transcribed_chart
from bj.core import STANDARD, Rules
from bj.strategy import DEALER_UPS, HARD_TABLE, PAIR_TABLE, RAW_CODES, SOFT_TABLE

README = Path(__file__).resolve().parent.parent / 'README.md'
CHART_BEGIN = '<!-- chart:begin -->'
CHART_END = '<!-- chart:end -->'


def _labels(text: str, heading: str) -> list[str]:
    """The first-column labels of the rows under one '### heading'."""
    labels, inside = [], False
    for line in text.splitlines():
        if line.startswith('### '):
            inside = line[4:].strip() == heading
        elif inside and line.startswith('| ') and not line.startswith('|:'):
            labels.append(line.split('|')[1].strip())
    return labels[1:]                       # drop the header row


# --- rendering -------------------------------------------------------------

def test_render_round_trips_the_transcription():
    chart = transcribed_chart()
    assert parse_chart(render_chart(chart)) == {
        'hard': dict(HARD_TABLE), 'soft': dict(SOFT_TABLE), 'pairs': dict(PAIR_TABLE),
    }


def test_hard_rows_merge_the_way_printed_charts_do():
    text = render_chart(transcribed_chart())
    assert _labels(text, 'Hard totals') == ['5-8', '9', '10', '11', '12', '13-16', '17-21']


def test_soft_and_pair_rows_are_in_chart_order():
    text = render_chart(transcribed_chart())
    assert _labels(text, 'Soft totals') == [f'A,{k}' for k in range(2, 10)]
    assert _labels(text, 'Pairs') == ['A,A', 'T,T', '9,9', '8,8', '7,7', '6,6',
                                      '5,5', '4,4', '3,3', '2,2']


def test_merging_needs_adjacent_totals_as_well_as_identical_codes():
    # 5, 6 and 8 all hit everywhere, but there is no 7, so "5-8" would claim a
    # cell the chart does not have.  The gap must not be bridged.
    hard = {(t, up): 'H' for t in (5, 6, 8) for up in DEALER_UPS}
    text = render_chart({'hard': hard, 'soft': {}, 'pairs': {}})
    assert _labels(text, 'Hard totals') == ['5-6', '8']


@pytest.mark.parametrize('row', (
    '| 5-8 | H | H | H | H | H | H | H | H | H | H |',
    '| 11 | D | D | D | D | D | D | D | D | D | H |',
    '| 17-21 | S | S | S | S | S | S | S | S | S | S |',
    '| A,7 | S | Ds | Ds | Ds | Ds | S | S | H | H | H |',
    '| 8,8 | P | P | P | P | P | P | P | P | P | P |',
    '| 4,4 | H | H | H | Ph | Ph | H | H | H | H | H |',
))
def test_pinned_rows_of_the_transcription(row):
    assert row in render_chart(transcribed_chart()).splitlines()


def test_dealer_columns_print_ten_as_10():
    text = render_chart(transcribed_chart())
    assert '| Hard | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | A |' in text.splitlines()


def test_legend_covers_every_code_and_nothing_else():
    assert {code for code, _meaning in LEGEND} == RAW_CODES
    text = render_chart(transcribed_chart())
    for code, meaning in LEGEND:
        assert f'**{code}** {meaning}' in text


def test_title_is_optional_and_leads_when_given():
    assert render_chart(transcribed_chart()).startswith('### Hard totals')
    assert render_chart(transcribed_chart(), title='Chart').startswith('Chart\n\n### Hard')


# --- parsing ---------------------------------------------------------------

def test_parse_rejects_an_unknown_code():
    text = render_chart(transcribed_chart()).replace('| 11 | D |', '| 11 | X |')
    with pytest.raises(ValueError, match="'X'"):
        parse_chart(text)


def test_parse_ignores_prose_around_the_tables():
    text = 'Some prose.\n\n' + render_chart(transcribed_chart()) + '\n\nMore prose.'
    assert parse_chart(text)['soft'] == dict(SOFT_TABLE)


# --- rules line ------------------------------------------------------------

def test_describe_rules_names_the_original_table():
    assert describe_rules(STANDARD) == (
        '6 decks, dealer stands on soft 17, double after split, dealer peeks, '
        'no surrender, up to 4 hands, split aces get one card, blackjack pays 3:2'
    )


def test_describe_rules_reflects_every_flag_it_names():
    text = describe_rules(Rules(decks=1, s17=False, das=False, peek=False, surrender=True,
                                max_hands=2, hit_split_aces=True, blackjack_payout=1.2))
    assert text == ('1 deck, dealer hits on soft 17, no double after split, no peek, '
                    'surrender, up to 2 hands, split aces may be hit, blackjack pays 6:5')
    assert 'blackjack pays 2:1' in describe_rules(Rules(blackjack_payout=2.0))
