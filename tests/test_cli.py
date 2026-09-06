"""Tests for bj.cli and the demo.py front door.

The command line is the first thing a reader runs, and README.md quotes its
output verbatim, so the report format is pinned here character for character
and the README is checked against the live output.  The EV figures asserted
are the published marginal-hand cells tests/test_ev.py holds the solver to;
here they are checked at the level of what a user sees printed.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from bj import cli
from bj.chart import parse_chart
from bj.core import Rules

ROOT = Path(__file__).resolve().parent.parent

SPLIT_EIGHTS = """\
Hand: 8 8  (16)  vs dealer T

  SPLIT    EV -0.4749  <- recommended
  HIT      EV -0.5354
  STAND    EV -0.5369
  DOUBLE   EV -1.0707

Recommended: SPLIT  (margin +0.0605 over the next-best action)

Player EV per hand under basic strategy (split approximations apply): -0.4044%"""


def _run(capsys, argv):
    assert cli.main(argv) == 0
    return capsys.readouterr().out


# --- the report ------------------------------------------------------------

def test_split_eights_report_is_pinned():
    assert cli.advise('8,8', 'T') == SPLIT_EIGHTS


def test_readme_quotes_the_live_output():
    assert SPLIT_EIGHTS in (ROOT / 'README.md').read_text(encoding='utf-8')


def test_main_defaults_to_split_eights_against_a_ten(capsys):
    assert _run(capsys, []) == SPLIT_EIGHTS + '\n'


def test_sixteen_versus_ten_is_the_coin_flip(capsys):
    out = _run(capsys, ['T,6', 'T'])
    assert 'Hand: T 6  (16)  vs dealer T' in out
    assert '  HIT      EV -0.5347  <- recommended' in out
    assert '  STAND    EV -0.5410' in out
    assert 'Recommended: HIT  (margin +0.0063 over the next-best action)' in out
    assert 'DOUBLE' in out and 'SPLIT' not in out      # a non-pair has no split button


def test_soft_eighteen_versus_three_doubles(capsys):
    out = _run(capsys, ['A,7', '3'])
    assert 'Hand: A 7  (soft 18)  vs dealer 3' in out
    assert '  DOUBLE   EV +0.1793  <- recommended' in out
    assert 'Recommended: DOUBLE  (margin +0.0282 over the next-best action)' in out


def test_card_spellings_are_interchangeable():
    assert cli.advise('KQ', 'j') == cli.advise('T,T', 'T') == cli.advise(['10', 'Q'], 10)
    assert cli.advise('a7', '3') == cli.advise('A,7', '3')


def test_a_natural_is_reported_as_a_non_decision():
    text = cli.advise('A,T', '9')
    assert '  STAND    EV +1.5000  <- recommended' in text
    assert 'HIT' not in text and 'DOUBLE' not in text
    assert 'margin +0.0000' in text


# --- rule flags ------------------------------------------------------------

def test_no_das_turns_a_ph_cell_into_a_hit():
    # 2,2 vs 2 is a 'Ph' cell: split only because double-after-split exists.
    assert 'Recommended: SPLIT' in cli.advise('2,2', '2')
    assert 'Recommended: HIT' in cli.advise('2,2', '2', Rules(das=False))


def test_h17_flag_flips_eleven_versus_ace_to_a_double(capsys):
    # The S17-sensitive cell bj.strategy's H17 overlay and bj.ev both agree on.
    assert 'Recommended: HIT' in _run(capsys, ['6,5', 'A'])
    assert 'Recommended: DOUBLE' in _run(capsys, ['6,5', 'A', '--h17'])


def test_deck_count_changes_the_bottom_line(capsys):
    six = _run(capsys, ['T,6', 'T']).splitlines()[-1]
    one = _run(capsys, ['T,6', 'T', '--decks', '1']).splitlines()[-1]
    prefix = 'Player EV per hand under basic strategy (split approximations apply): '
    assert six.startswith(prefix) and one.startswith(prefix)
    assert six != one
    float(one[len(prefix):-1])                  # a number, followed by the % sign


@pytest.mark.parametrize('argv', (
    ['Z,Z', 'T'],                # not a card
    ['T,T,T', '5'],              # busted: there is no decision
    ['T,6', 'T', '--decks', '0'],
    ['A,A,A,A,A', '5', '--decks', '1'],   # five aces do not fit in one deck
))
def test_bad_input_is_a_usage_error(capsys, argv):
    with pytest.raises(SystemExit) as exc:
        cli.main(argv)
    assert exc.value.code == 2
    assert 'usage:' in capsys.readouterr().err


# --- the chart -------------------------------------------------------------

def test_table_prints_the_chart_the_solver_derives(capsys, derived):
    out = _run(capsys, ['--table'])
    assert out.startswith(
        'Basic strategy derived by the solver (split approximations apply): 6 decks, ')
    assert parse_chart(out) == derived


# --- the front door --------------------------------------------------------

def test_demo_script_is_the_installed_command():
    spec = importlib.util.spec_from_file_location('demo', ROOT / 'demo.py')
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    assert demo.main is cli.main
