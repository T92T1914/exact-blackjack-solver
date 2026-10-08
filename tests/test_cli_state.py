"""Explicit remaining-shoe and split-state reports through the public front door."""
import json
from dataclasses import replace
from fractions import Fraction

import pytest

from bj import cli, record
from bj.core import STANDARD


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


TINY_COUNTS = (0, 1, 1, 0, 0, 0, 1, 1, 1, 1)
TINY_CSV = '0,1,1,0,0,0,1,1,1,1'


def _json_advice(capsys, args):
    assert cli.main([*args, '--json']) == 0
    captured = capsys.readouterr()
    assert captured.err == ''
    return json.loads(captured.out)


def _forbid_input_work(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('refused input reached calculation or file reading')

    for name in ('best_action', 'decision_json', 'derive_table', 'replay_file'):
        monkeypatch.setattr(cli, name, forbidden)


@pytest.mark.parametrize('csv', [
    TINY_CSV,
    ' \t00\r,\n01\v,\f01 ,00,00,00,01,01,01,01 ',
])
def test_count_input_preserves_visible_ranks_and_raw_record(capsys, csv):
    actual = _json_advice(capsys, ['T,4', 'T', '--unseen-counts', csv])
    physical = _json_advice(capsys, ['T,4', 'T', '--unseen', '2,3,7,8,9,T'])
    expected = record.decision_record('T,4', 'T', shoe=TINY_COUNTS)
    assert actual == physical == expected
    assert actual['state']['cards'] == ['T', '4']
    assert actual['state']['shoe']['counts'] == list(TINY_COUNTS)
    assert actual['state']['shoe']['source'] == 'supplied_unseen'
    assert actual['decision']['whole_game_estimate'] is None
    hit = actual['decision']['evs']['H']
    assert hit == pytest.approx(float(Fraction(-71, 120)), rel=0, abs=1e-12)
    assert hit != round(hit, 4)


def test_count_text_matches_physical_input_without_whole_game_work(capsys, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('explicit count advice computed an unrelated whole-game estimate')

    monkeypatch.setattr(cli, 'house_edge', forbidden)
    assert cli.main(['T,4', 'T', '--unseen-counts', TINY_CSV]) == 0
    actual = capsys.readouterr()
    assert cli.main(['T,4', 'T', '--unseen', '2,3,7,8,9,T']) == 0
    physical = capsys.readouterr()
    assert actual.out == physical.out
    assert actual.err == physical.err == ''
    assert 'A=0, 2=1, 3=1, 4=0, 5=0, 6=0, 7=1, 8=1, 9=1, T=1' in actual.out
    assert 'No whole-game estimate is computed.' in actual.out


def test_count_input_keeps_split_cap_rules_and_raw_values(capsys):
    counts = (0, 0, 0, 0, 0, 0, 1, 1, 1, 1)
    flags = ['--split-hand', '--hand-count', '4', '--no-das', '--h17', '--decks', '1']
    actual = _json_advice(capsys, ['8,8', 'T', '--unseen-counts',
                                  '0,0,0,0,0,0,1,1,1,1', *flags])
    physical = _json_advice(capsys, ['8,8', 'T', '--unseen', '7,8,9,T', *flags])
    rules = replace(STANDARD, decks=1, s17=False, das=False)
    expected = record.decision_record('8,8', 'T', rules, shoe=counts,
                                      is_split_hand=True, hand_count=4)
    assert actual == physical == expected
    assert actual['state']['shoe']['counts'] == list(counts)
    assert actual['state']['hand_count'] == 4
    assert actual['state']['is_split_hand'] is True
    assert set(actual['decision']['evs']) == {'S', 'H'}


def test_count_input_keeps_dealt_order_and_first_split_rank(capsys):
    results = {}
    for cards in ('A,7', '7,A'):
        actual = _json_advice(capsys, [cards, 'T', '--unseen-counts', TINY_CSV,
                                      '--split-hand'])
        expected = record.decision_record(cards, 'T', shoe=TINY_COUNTS,
                                          is_split_hand=True)
        assert actual == expected
        assert actual['state']['cards'] == cards.split(',')
        results[cards] = actual['decision']['evs']
    assert set(results['A,7']) == {'S'}
    assert set(results['7,A']) == {'S', 'H', 'D'}


def test_count_input_does_not_clamp_to_deck_metadata(capsys):
    counts = (0,) * 9 + (17,)
    actual = _json_advice(capsys, ['A,T', '9', '--decks', '1', '--unseen-counts',
                                  '0,0,0,0,0,0,0,0,0,17'])
    expected = record.decision_record('A,T', '9', replace(STANDARD, decks=1), shoe=counts)
    assert actual == expected
    assert actual['state']['shoe']['counts'] == list(counts)


def test_repeated_count_option_keeps_the_last_supplied_tally(capsys):
    actual = _json_advice(capsys, ['T,4', 'T', '--unseen-counts',
                                  '0,0,0,0,0,0,0,0,0,0', '--unseen-counts', TINY_CSV])
    assert actual == record.decision_record('T,4', 'T', shoe=TINY_COUNTS)


@pytest.mark.parametrize('options', [
    ['--unseen-counts'],
    ['--unseen-counts', ''],
    ['--unseen-counts', '0,1'],
    ['--unseen-counts', TINY_CSV + ',0'],
    ['--unseen-counts', '0,,1,0,0,0,1,1,1,1'],
    *[['--unseen-counts', value + ',1,1,0,0,0,1,1,1,1'] for value in (
        '-1', '+1', '1.0', '1e2', '0x1', '1_0', 'True', 'T', 'A=0', '\u0660', '0 0',
        '\u00a00',
    )],
])
def test_count_syntax_refuses_before_any_work(capsys, monkeypatch, options):
    _forbid_input_work(monkeypatch)
    with pytest.raises(SystemExit) as exc:
        cli.main(['T,4', 'T', '--json', *options])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ''
    assert '--unseen-counts' in captured.err
    assert 'usage:' in captured.err
    assert 'Traceback' not in captured.err


def test_count_integer_conversion_refusal_has_a_bounded_explanation(capsys, monkeypatch):
    # Exercise the conversion boundary without changing process-wide Python settings.
    def unavailable(text, base):
        raise ValueError('runtime rejected a token: ' + text)

    monkeypatch.setattr(cli, 'int', unavailable, raising=False)
    _forbid_input_work(monkeypatch)
    token = '9' * 5000
    with pytest.raises(SystemExit) as exc:
        cli.main(['--unseen-counts', token + ',0,0,0,0,0,0,0,0,0', '--json'])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ''
    assert '--unseen-counts count for A cannot be converted by this Python runtime' in captured.err
    assert token not in captured.err
    assert 'Traceback' not in captured.err


@pytest.mark.parametrize('options', [
    ['--unseen', '9', '--unseen-counts', TINY_CSV],
    ['--unseen-counts', TINY_CSV, '--unseen', '9'],
    ['--table', '--unseen-counts', TINY_CSV],
    ['--table', '--unseen-counts', '0,0,0,0,0,0,0,0,0,0'],
    ['--replay', 'not-read.json', '--unseen-counts', TINY_CSV],
    ['--replay', 'not-read.json', '--unseen-counts', '0,0,0,0,0,0,0,0,0,0'],
    ['--unseen-counts', TINY_CSV, '--hand-count', '2'],
    ['--unseen-counts', TINY_CSV, '--split-hand', '--hand-count', '1'],
])
def test_count_option_conflicts_refuse_before_any_work(capsys, monkeypatch, options):
    _forbid_input_work(monkeypatch)
    with pytest.raises(SystemExit) as exc:
        cli.main([*options, '--json'])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ''
    assert 'usage:' in captured.err


@pytest.mark.parametrize('csv,message', [
    ('0,0,0,0,0,0,0,0,0,0', 'reserved dealer hole'),
    ('1,0,0,0,0,0,0,0,0,0', 'no possible hole'),
])
def test_valid_count_syntax_reaches_unchanged_state_refusal(capsys, csv, message):
    with pytest.raises(SystemExit) as exc:
        cli.main(['T,4', 'T', '--unseen-counts', csv, '--json'])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ''
    assert message in captured.err
    assert 'nonnegative base-10 integer' not in captured.err


@pytest.mark.parametrize('json_flags', [[], ['--json']])
def test_real_large_count_overflow_is_an_explained_creation_refusal(capsys, json_flags):
    # Same admitted arithmetic-range state as the retained replay failure witness.
    csv = ','.join(['0'] * 9 + [str(10 ** 400)])
    with pytest.raises(SystemExit) as exc:
        cli.main(['T,4', 'T', '--unseen-counts', csv, *json_flags])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ''
    assert 'error: cannot calculate decision: arithmetic overflow' in captured.err
    assert 'Traceback' not in captured.err


def test_table_overflow_keeps_its_existing_exception_behavior(monkeypatch, capsys):
    def unavailable(*args, **kwargs):
        raise OverflowError('table calculation range')

    monkeypatch.setattr(cli, 'table', unavailable)
    with pytest.raises(OverflowError, match='table calculation range'):
        cli.main(['--table'])
    captured = capsys.readouterr()
    assert captured.out == captured.err == ''
