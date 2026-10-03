"""Explicit remaining-shoe and split-state reports through the public front door."""
from fractions import Fraction

import pytest

from bj import cli


def test_physical_reference_case_has_the_declared_shoe_and_values(capsys):
    # Retained independent physical-deal oracle: hit=-71/120. The CLI must
    # not remove the visible cards a second time.
    assert cli.main(['T,4', 'T', '--unseen', '2,3,7,8,9,T']) == 0
    out = capsys.readouterr().out
    assert 'A=0, 2=1, 3=1, 4=0, 5=0, 6=0, 7=1, 8=1, 9=1, T=1' in out
    assert f'  HIT      EV {float(Fraction(-71, 120)):+.4f}' in out
    assert 'No whole-game estimate is computed.' in out
    assert 'Player EV per hand under basic strategy' not in out


def test_explicit_shoe_report_never_computes_an_unrelated_fresh_shoe_edge(monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError('fresh-shoe edge must not run')

    monkeypatch.setattr(cli, 'house_edge', unexpected)
    text = cli.advise('T,4', 'T', shoe=[0, 1, 1, 0, 0, 0, 1, 1, 1, 1])
    assert 'Recommended: HIT' in text


def test_split_ace_twenty_one_is_ordinary_settlement_not_a_natural(capsys):
    assert cli.main(['A,T', 'T', '--unseen', '9', '--split-hand']) == 0
    out = capsys.readouterr().out
    assert 'Round state: split hand, 2 hands in the round' in out
    assert '  STAND    EV +1.0000  <- recommended' in out
    assert 'margin +0.0000' in out
    assert 'HIT' not in out and 'DOUBLE' not in out and 'SPLIT' not in out
    assert '+1.5000' not in out


def test_exhaustion_remains_a_usage_error_instead_of_an_invented_settlement(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(['T,6', '6', '--unseen', '2'])
    assert exc.value.code == 2
    assert 'dealer must draw to 8 but the shoe is empty' in capsys.readouterr().err


def test_only_reserved_hole_remains_so_stand_is_the_only_action(capsys):
    assert cli.main(['T,6', 'T', '--unseen', '9']) == 0
    out = capsys.readouterr().out
    assert 'STAND' in out and 'margin +0.0000' in out
    assert 'HIT' not in out and 'DOUBLE' not in out


def test_aliases_preserve_actual_rank_counts(capsys):
    assert cli.main(['T,4', 'T', '--unseen', 'K,Q,J,10']) == 0
    assert 'T=4' in capsys.readouterr().out


@pytest.mark.parametrize('argv', [
    ['--table', '--unseen', '9'],
    ['--table', '--split-hand'],
    ['--table', '--hand-count', '1'],
    ['--unseen', ''], ['--unseen', '2,,9'], ['--unseen', 'Z'],
    ['--unseen=-1'], ['--unseen', '2.0'],
    ['--hand-count', '2'], ['--hand-count', '0'],
    ['--split-hand', '--hand-count', '1'],
    ['--split-hand', '--hand-count', '5'],
])
def test_unusable_state_rejects_before_calculation(capsys, monkeypatch, argv):
    def unexpected(*args, **kwargs):
        raise AssertionError('invalid state reached calculation')

    monkeypatch.setattr(cli, 'best_action', unexpected)
    monkeypatch.setattr(cli, 'derive_table', unexpected)
    with pytest.raises(SystemExit) as exc:
        cli.main(argv)
    assert exc.value.code == 2
    assert 'usage:' in capsys.readouterr().err


@pytest.mark.parametrize('count', [0, 5, True, 2.0])
def test_report_api_rejects_invalid_hand_count(count):
    with pytest.raises(ValueError, match='hand_count'):
        cli.advise('8,8', '7', is_split_hand=True, hand_count=count)


def test_split_state_and_no_das_remove_double(capsys):
    assert cli.main(['6,5', 'T', '--unseen', '7,8,9,T',
                     '--split-hand', '--no-das']) == 0
    assert 'DOUBLE' not in capsys.readouterr().out


def test_split_cap_removes_split_and_discloses_total_hand_count(capsys):
    assert cli.main(['8,8', 'T', '--unseen', '7,8,9,T',
                     '--split-hand', '--hand-count', '4']) == 0
    out = capsys.readouterr().out
    assert 'Round state: split hand, 4 hands in the round' in out
    assert '  SPLIT' not in out
