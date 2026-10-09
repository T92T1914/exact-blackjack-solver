"""Explicit remaining-shoe and split-state reports through the public front door."""
import json
import sys
from dataclasses import replace
from fractions import Fraction

import pytest

from bj import chart, cli, record
from bj.core import RANKS, STANDARD
from bj.ev import best_action
from bj.replay import replay_file
from test_ev_physical_reference import physical_reference


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


CAP_COUNTS = (1, 0, 0, 0, 0, 0, 0, 0, 0, 5)
CAP_CSV = '1,0,0,0,0,0,0,0,0,5'


@pytest.mark.parametrize('cap,split,count', [(1, False, 1), (2, False, 1), (2, True, 2)])
def test_selected_cap_preserves_complete_record_and_public_values(capsys, cap, split, count):
    flags = ['--max-hands', str(cap), '--hand-count', str(count)]
    if split:
        flags += ['--split-hand']
    actual = _json_advice(capsys, ['T,T', '7', '--unseen-counts', CAP_CSV, *flags])
    rules = replace(STANDARD, max_hands=cap)
    expected = record.decision_record('T,T', '7', rules, shoe=CAP_COUNTS,
                                      is_split_hand=split, hand_count=count)
    assert actual == expected
    decision = actual['decision']
    assert (decision['action'], decision['evs'], decision['margin']) == best_action(
        'T,T', '7', CAP_COUNTS, rules, is_split_hand=split, hand_count=count)
    assert actual['rules']['max_hands'] == cap
    assert actual['state']['cards'] == ['T', 'T']
    assert actual['state']['shoe']['counts'] == list(CAP_COUNTS)
    assert actual['state']['hand_count'] == count
    assert actual['state']['is_split_hand'] is split
    assert decision['whole_game_estimate'] is None
    if cap == 2 and not split:
        # Reuse the retained six-card arithmetic fixture in test_split_completed_hand.
        assert decision['evs']['P'] == 2.0
        assert decision['evs']['S'] == 1.0
        assert decision['action'] == 'P' and decision['margin'] == 1.0
    else:
        assert 'P' not in decision['evs']


def test_selected_cap_text_and_other_rule_flags_match_public_api(capsys, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('explicit shoe advice computed a whole-game estimate')

    monkeypatch.setattr(cli, 'house_edge', forbidden)
    rules = replace(STANDARD, max_hands=2, decks=1, s17=False, das=False)
    flags = ['--max-hands', '2', '--split-hand', '--hand-count', '2',
             '--decks', '1', '--h17', '--no-das']
    args = ['T,T', '7', '--unseen-counts', CAP_CSV, *flags]
    assert cli.main(args) == 0
    captured = capsys.readouterr()
    assert captured.err == ''
    assert captured.out == cli.advise('T,T', '7', rules, shoe=CAP_COUNTS,
                                      is_split_hand=True, hand_count=2) + '\n'
    actual = _json_advice(capsys, args)
    assert actual == record.decision_record('T,T', '7', rules, shoe=CAP_COUNTS,
                                           is_split_hand=True, hand_count=2)
    assert 'P' not in actual['decision']['evs'] and 'D' not in actual['decision']['evs']
    assert 'Round state: split hand, 2 hands in the round' in captured.out
    assert 'No whole-game estimate is computed.' in captured.out


def test_omitted_cap_and_explicit_default_preserve_text_and_record(capsys, monkeypatch):
    monkeypatch.setattr(cli, 'house_edge', lambda *a, **k: pytest.fail('whole-game estimate'))
    args = ['T,4', 'T', '--unseen-counts', TINY_CSV]
    assert cli.main(args) == 0
    omitted = capsys.readouterr()
    assert cli.main([*args, '--max-hands', '4']) == 0
    explicit = capsys.readouterr()
    assert omitted.out == explicit.out == cli.advise('T,4', 'T', shoe=TINY_COUNTS) + '\n'
    assert omitted.err == explicit.err == ''
    assert _json_advice(capsys, args) == _json_advice(capsys, [*args, '--max-hands', '4'])


def test_cap_above_default_is_retained_without_a_split_search(capsys):
    counts = (0, 0, 0, 0, 0, 0, 0, 0, 1, 0)
    actual = _json_advice(capsys, ['A,T', '9', '--unseen-counts',
                                  '0,0,0,0,0,0,0,0,1,0', '--max-hands', '5'])
    assert actual == record.decision_record('A,T', '9', replace(STANDARD, max_hands=5),
                                           shoe=counts)
    assert actual['rules']['max_hands'] == 5
    assert actual['state']['hand_count'] == 1
    assert actual['decision']['evs'] == {'S': 1.5}


def test_selected_cap_keeps_first_split_rank_and_dealt_order(capsys):
    for cards in ('A,7', '7,A'):
        actual = _json_advice(capsys, [cards, 'T', '--unseen-counts', TINY_CSV,
                                      '--max-hands', '2', '--split-hand'])
        assert actual == record.decision_record(
            cards, 'T', replace(STANDARD, max_hands=2), shoe=TINY_COUNTS,
            is_split_hand=True, hand_count=2)
        assert actual['state']['cards'] == cards.split(',')
        assert set(actual['decision']['evs']) == ({'S'} if cards == 'A,7' else {'S', 'H', 'D'})


@pytest.mark.parametrize('flags', [[], ['--json']])
@pytest.mark.parametrize('options', [
    ['--max-hands', '1', '--split-hand'],
    ['--max-hands', '2', '--split-hand', '--hand-count', '3'],
    ['--max-hands', '2', '--hand-count', '2'],
])
def test_cap_state_refusal_keeps_real_validators_before_calculation(
        capsys, monkeypatch, flags, options):
    def forbidden(*args, **kwargs):
        pytest.fail('invalid cap state reached calculation')

    monkeypatch.setattr(cli, 'best_action', forbidden)
    monkeypatch.setattr(record, 'best_action', forbidden)
    with pytest.raises(SystemExit) as exc:
        cli.main(['T,T', '7', '--unseen-counts', CAP_CSV, *options, *flags])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ''
    assert ('hand_count' in captured.err or '--hand-count' in captured.err)
    assert 'usage:' in captured.err and 'Traceback' not in captured.err


@pytest.mark.parametrize('token', ['2', '0002', ' \t002\r\n\v\f '])
def test_positive_ascii_cap_forms_reach_the_same_record(capsys, token):
    actual = _json_advice(capsys, ['T,T', '7', '--unseen-counts', CAP_CSV,
                                  '--max-hands', token])
    assert actual == record.decision_record('T,T', '7', replace(STANDARD, max_hands=2),
                                           shoe=CAP_COUNTS)


@pytest.mark.parametrize('options', [
    ['--max-hands'],
    *[['--max-hands=' + token] for token in (
        '', ' \t', '0', '000', '-1', '+2', '2.0', '2e1', '2_0', '0x2', '2,3',
        'A', 'A=2', 'True', 'False', '\u0662', '\uff12', '\u00a02', '2\u00a0', '2 2',
    )],
    ['--max-hands', '0', '--max-hands', '2'],
])
def test_cap_syntax_refuses_before_any_input_work(capsys, monkeypatch, options):
    _forbid_input_work(monkeypatch)
    with pytest.raises(SystemExit) as exc:
        cli.main(['T,T', '7', '--json', *options])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ''
    assert '--max-hands' in captured.err and 'usage:' in captured.err
    assert 'Traceback' not in captured.err


def test_real_cap_integer_conversion_limit_is_an_explained_refusal(capsys, monkeypatch):
    limit = sys.get_int_max_str_digits()
    if not limit or limit > 10_000:
        pytest.skip('runtime decimal conversion limit is disabled or beyond this tiny test')
    _forbid_input_work(monkeypatch)
    token = '9' * (limit + 1)
    with pytest.raises(SystemExit) as exc:
        cli.main(['--max-hands', token, '--json'])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ''
    assert '--max-hands cannot be converted by this Python runtime' in captured.err
    assert token not in captured.err and 'Traceback' not in captured.err


def test_repeated_cap_option_keeps_last_valid_value(capsys):
    actual = _json_advice(capsys, ['T,T', '7', '--unseen-counts', CAP_CSV,
                                  '--max-hands', '1', '--max-hands', '2'])
    assert actual['rules']['max_hands'] == 2 and 'P' in actual['decision']['evs']


@pytest.mark.parametrize('split', [False, True])
def test_selected_cap_record_replays_without_rule_overrides(capsys, tmp_path, split):
    flags = ['--max-hands', '2']
    if split:
        flags += ['--split-hand', '--hand-count', '2']
    assert cli.main(['T,T', '7', '--unseen-counts', CAP_CSV, *flags, '--json']) == 0
    created = capsys.readouterr()
    assert created.err == ''
    saved = json.loads(created.out)
    path = tmp_path / 'cap-record.json'
    with path.open('x', encoding='utf-8', newline='') as stream:
        stream.write(created.out)
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    assert cli.main(['--replay', str(path), '--json']) == 0
    captured = capsys.readouterr()
    assert captured.err == ''
    actual = json.loads(captured.out)
    assert actual == replay_file(path)
    assert actual['status'] == 'agreement' and actual['error'] is None
    assert actual['modeled_input']['rules'] == saved['rules']
    assert actual['modeled_input']['rules']['max_hands'] == 2
    assert actual['recorded'] == actual['recomputed'] == saved['decision']
    assert actual['comparison']['legal_actions']['matches']
    assert actual['comparison']['evs_match'] and actual['comparison']['margin']['matches']
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


@pytest.mark.parametrize('cap', ['2', '4'])
def test_replay_refuses_explicit_cap_even_when_default(capsys, monkeypatch, tmp_path, cap):
    path = tmp_path / 'existing-record.json'
    path.write_text(record.decision_json('A,T', '9', shoe=(0,) * 8 + (1, 0)),
                    encoding='utf-8')
    _forbid_input_work(monkeypatch)
    with pytest.raises(SystemExit) as exc:
        cli.main(['--replay', str(path), '--max-hands', cap, '--json'])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ''
    assert '--replay cannot be combined' in captured.err


@pytest.mark.parametrize('cap', [2, 10 ** 100])
def test_table_receives_selected_cap_and_keeps_title_without_chart_work(
        capsys, monkeypatch, cap):
    observed = []

    def small_chart(rules):
        observed.append(rules)
        return {'hard': {}, 'soft': {}, 'pairs': {}}

    monkeypatch.setattr(cli, 'derive_table', small_chart)
    assert cli.main(['--table', '--max-hands', str(cap), '--decks', '1',
                     '--h17', '--no-das']) == 0
    captured = capsys.readouterr()
    assert captured.err == ''
    assert observed == [replace(STANDARD, max_hands=cap, decks=1, s17=False, das=False)]
    assert f'up to {cap} hands' in captured.out.splitlines()[0]


@pytest.mark.parametrize('options', [
    ['--json'], ['--unseen', '9'], ['--unseen-counts', CAP_CSV],
    ['--split-hand'], ['--hand-count', '1'],
])
def test_selected_table_cap_preserves_state_and_json_refusals(capsys, monkeypatch, options):
    _forbid_input_work(monkeypatch)
    with pytest.raises(SystemExit) as exc:
        cli.main(['--table', '--max-hands', '2', *options])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == '' and '--table cannot be combined' in captured.err


@pytest.mark.parametrize('can_double,can_split', [
    (True, True), (False, True), (True, False), (False, False),
])
def test_current_controls_create_and_replay_the_actual_saved_stdout(
        capsys, tmp_path, can_double, can_split):
    flags = ([] if can_double else ['--no-double']) + ([] if can_split else ['--no-split'])
    args = ['T,T', '7', '--unseen-counts', CAP_CSV, '--max-hands', '2', *flags]
    assert cli.main([*args, '--json']) == 0
    created = capsys.readouterr()
    assert created.err == ''
    saved = json.loads(created.out)
    expected = record.decision_record('T,T', '7', replace(STANDARD, max_hands=2),
                                      shoe=CAP_COUNTS, can_double=can_double,
                                      can_split=can_split)
    assert saved == expected
    assert saved['state']['shoe']['counts'] == list(CAP_COUNTS)
    assert set(saved['decision']['evs']) == (
        {'H', 'S'} | ({'D'} if can_double else set()) | ({'P'} if can_split else set()))
    path = tmp_path / 'current-choices.json'
    with path.open('x', encoding='utf-8', newline='') as stream:
        stream.write(created.out)
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    assert cli.main(['--replay', str(path), '--json']) == 0
    captured = capsys.readouterr()
    assert captured.err == ''
    replayed = json.loads(captured.out)
    assert replayed['status'] == 'agreement'
    assert replayed['modeled_input']['state'] == saved['state']
    assert replayed['recorded'] == replayed['recomputed'] == saved['decision']
    assert replayed['comparison']['evs_match'] and replayed['comparison']['margin']['matches']
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


@pytest.mark.parametrize('flag,disabled', [
    ('--no-double', 'DOUBLE'), ('--no-split', 'SPLIT'),
])
def test_repeated_disable_is_harmless_and_text_names_only_disabled_choice(capsys, flag, disabled):
    args = ['T,T', '7', '--unseen-counts', CAP_CSV, '--max-hands', '2', flag]
    assert cli.main(args) == 0
    once = capsys.readouterr()
    assert cli.main([*args, flag]) == 0
    repeated = capsys.readouterr()
    assert once == repeated
    assert 'Current action restrictions: ' + disabled + '\n' in once.out
    assert 'Values apply to this hand and declared current choices.' in once.out
    assert 'Player EV per hand under basic strategy' not in once.out


def test_disabled_choices_omit_fresh_whole_game_work(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail('current choice restrictions reached whole-game work')
    monkeypatch.setattr(cli, 'house_edge', forbidden)
    # A natural settles immediately, so this fresh-shoe witness adds no search.
    assert cli.main(['A,T', '9', '--no-double', '--no-split']) == 0
    captured = capsys.readouterr()
    assert captured.err == ''
    assert 'Current action restrictions: DOUBLE, SPLIT\n' in captured.out
    assert '  STAND' in captured.out
    assert 'No whole-game estimate is computed.' in captured.out


@pytest.mark.parametrize('flag', ['--no-double', '--no-split'])
@pytest.mark.parametrize('dispatch', [
    ['--table'], ['--table', '--json'], ['--replay', 'not-read.json'],
    ['--replay', 'not-read.json', '--json'],
])
def test_current_control_dispatch_conflicts_refuse_before_work(
        monkeypatch, capsys, flag, dispatch):
    _forbid_input_work(monkeypatch)
    with pytest.raises(SystemExit) as exc:
        cli.main([*dispatch, flag])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == '' and 'usage:' in captured.err
    assert 'cannot be combined' in captured.err and 'Traceback' not in captured.err


def test_controls_keep_existing_split_rule_and_direct_count_options(capsys):
    counts = (0, 0, 0, 0, 0, 0, 1, 1, 1, 1)
    flags = ['--split-hand', '--hand-count', '2', '--max-hands', '2',
             '--h17', '--no-das', '--decks', '1', '--no-double', '--no-split']
    actual = _json_advice(capsys, ['8,8', 'T', '--unseen-counts',
                                  '0,0,0,0,0,0,1,1,1,1', *flags])
    physical = _json_advice(capsys, ['8,8', 'T', '--unseen', '7,8,9,T', *flags])
    expected = record.decision_record(
        '8,8', 'T', replace(STANDARD, decks=1, s17=False, das=False, max_hands=2),
        shoe=counts, is_split_hand=True, hand_count=2, can_double=False, can_split=False)
    assert actual == physical == expected
    assert actual['state']['cards'] == ['8', '8']
    assert set(actual['decision']['evs']) == {'H', 'S'}


ACE_COUNTS = (0, 0, 0, 0, 0, 0, 0, 0, 1, 2)
ACE_CSV = '0,0,0,0,0,0,0,0,1,2'
ACE_STATE = ['--split-hand', '--hand-count', '2', '--max-hands', '3']
ACE_PAIRS = [
    (False, False, {'S'}), (True, False, {'S', 'P'}),
    (False, True, {'S', 'H', 'D'}), (True, True, {'S', 'H', 'D', 'P'}),
]
DEFAULT_CAPTION = (
    '6 decks, dealer stands on soft 17, double after split, dealer peeks, '
    'no surrender, up to 4 hands, split aces get one card, blackjack pays 3:2'
)


def _ace_flags(resplit, hit):
    return (['--resplit-aces'] if resplit else []) + (['--hit-split-aces'] if hit else [])


@pytest.mark.parametrize('resplit,hit,actions', ACE_PAIRS)
def test_ace_rules_create_complete_v1_and_replay_saved_stdout_once(
        capsys, monkeypatch, tmp_path, resplit, hit, actions):
    flags = _ace_flags(resplit, hit)
    rules = replace(STANDARD, max_hands=3, resplit_aces=resplit, hit_split_aces=hit)
    assert cli.main(['A,A', 'T', '--unseen-counts', ACE_CSV,
                     *ACE_STATE, *flags, '--json']) == 0
    created = capsys.readouterr()
    assert created.err == ''
    saved = json.loads(created.out)
    expected = record.decision_record('A,A', 'T', rules, shoe=ACE_COUNTS,
                                      is_split_hand=True, hand_count=2)
    physical = _json_advice(capsys, ['A,A', 'T', '--unseen', '9,T,T', *ACE_STATE, *flags])
    assert saved == physical == expected
    assert created.out == record.decision_json(
        'A,A', 'T', rules, shoe=ACE_COUNTS, is_split_hand=True, hand_count=2) + '\n'
    assert saved['rules']['resplit_aces'] is resplit
    assert saved['rules']['hit_split_aces'] is hit
    assert saved['schema']['version'] == 1 and 'action_controls' not in saved['state']
    assert saved['state']['shoe']['counts'] == list(ACE_COUNTS)
    assert saved['state']['shoe']['source'] == 'supplied_unseen'
    assert saved['state']['cards'] == ['A', 'A'] and saved['state']['hand_count'] == 2
    assert set(saved['decision']['evs']) == actions
    action, values, margin = best_action(
        'A,A', 'T', shoe=ACE_COUNTS, rules=rules, is_split_hand=True, hand_count=2)
    assert (saved['decision']['action'], saved['decision']['evs'],
            saved['decision']['margin']) == (action, values, margin)
    assert saved['decision']['whole_game_estimate'] is None
    assert saved['model']['split_error_bound'] is None

    path = tmp_path / 'ace-rules.json'
    with path.open('x', encoding='utf-8', newline='') as stream:
        stream.write(created.out)
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    original = record.best_action
    observed = []

    def observed_decision(cards, up, *, shoe, rules, is_split_hand, hand_count,
                          can_double, can_split):
        observed.append((tuple(cards), up, shoe, rules, is_split_hand, hand_count,
                         can_double, can_split))
        return original(cards, up, shoe=shoe, rules=rules, is_split_hand=is_split_hand,
                        hand_count=hand_count, can_double=can_double, can_split=can_split)

    monkeypatch.setattr(record, 'best_action', observed_decision)
    assert cli.main(['--replay', str(path), '--json']) == 0
    captured = capsys.readouterr()
    assert captured.err == ''
    replayed = json.loads(captured.out)
    assert observed == [(('A', 'A'), 'T', ACE_COUNTS, rules, True, 2, True, True)]
    assert replayed['status'] == 'agreement' and replayed['error'] is None
    assert replayed['modeled_input']['rules'] == saved['rules']
    assert replayed['modeled_input']['state'] == saved['state']
    assert replayed['modeled_input']['model'] == saved['model']
    assert replayed['recorded'] == replayed['recomputed'] == saved['decision']
    assert replayed['comparison']['evs_match']
    assert replayed['comparison']['recommendation']['matches']
    assert replayed['comparison']['margin']['matches']
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_ace_defaults_keep_existing_text_json_and_caption_bytes(capsys, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('retained ace advice reached a whole-game estimate')

    monkeypatch.setattr(cli, 'house_edge', forbidden)
    rules = replace(STANDARD, max_hands=3)
    args = ['A,A', 'T', '--unseen-counts', ACE_CSV, *ACE_STATE]
    assert cli.main(args) == 0
    actual = capsys.readouterr()
    assert actual.err == ''
    assert actual.out == cli.advise(
        'A,A', 'T', rules, shoe=ACE_COUNTS, is_split_hand=True, hand_count=2) + '\n'
    assert cli.main([*args, '--json']) == 0
    actual = capsys.readouterr()
    assert actual.err == ''
    assert actual.out == record.decision_json(
        'A,A', 'T', rules, shoe=ACE_COUNTS, is_split_hand=True, hand_count=2) + '\n'
    assert chart.describe_rules(STANDARD) == DEFAULT_CAPTION


def test_ace_rule_permissions_keep_combined_current_controls_v2(
        capsys, monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail('constrained ace advice reached a whole-game estimate')

    monkeypatch.setattr(cli, 'house_edge', forbidden)
    rules = replace(STANDARD, max_hands=3, resplit_aces=True, hit_split_aces=True)
    args = ['A,A', 'T', '--unseen-counts', ACE_CSV, *ACE_STATE,
            '--resplit-aces', '--hit-split-aces', '--no-double', '--no-split']
    assert cli.main([*args, '--json']) == 0
    created = capsys.readouterr()
    assert created.err == ''
    saved = json.loads(created.out)
    assert saved == record.decision_record(
        'A,A', 'T', rules, shoe=ACE_COUNTS, is_split_hand=True, hand_count=2,
        can_double=False, can_split=False)
    assert saved['schema']['version'] == 2
    assert list(saved['state']) == [
        'cards', 'dealer_up', 'total', 'soft', 'is_split_hand', 'hand_count',
        'action_controls', 'shoe',
    ]
    assert list(saved['state']['action_controls']) == ['can_double', 'can_split']
    assert saved['state']['action_controls']['can_double'] is False
    assert saved['state']['action_controls']['can_split'] is False
    assert set(saved['decision']['evs']) == {'S', 'H'}
    assert cli.main(args) == 0
    captured = capsys.readouterr()
    assert captured.err == ''
    assert captured.out == cli.advise(
        'A,A', 'T', rules, shoe=ACE_COUNTS, is_split_hand=True, hand_count=2,
        can_double=False, can_split=False) + '\n'
    assert 'Current action restrictions: DOUBLE, SPLIT\n' in captured.out
    path = tmp_path / 'constrained-aces.json'
    with path.open('x', encoding='utf-8', newline='') as stream:
        stream.write(created.out)
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    assert cli.main(['--replay', str(path), '--json']) == 0
    replayed = json.loads(capsys.readouterr().out)
    assert replayed['status'] == 'agreement'
    assert replayed['modeled_input']['state'] == saved['state']
    assert replayed['modeled_input']['rules'] == saved['rules']
    assert replayed['recorded'] == replayed['recomputed'] == saved['decision']
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


@pytest.mark.parametrize('options,cap,csv,actions', [
    (['--no-das'], 3, ACE_CSV, {'S', 'H', 'P'}),
    (['--no-double'], 3, ACE_CSV, {'S', 'H', 'P'}),
    (['--no-split'], 3, ACE_CSV, {'S', 'H', 'D'}),
    ([], 2, ACE_CSV, {'S', 'H', 'D'}),
    ([], 3, '0,0,0,0,0,0,0,0,1,1', {'S', 'H', 'D'}),
])
def test_ace_permissions_still_intersect_other_eligibility(capsys, options, cap, csv, actions):
    actual = _json_advice(capsys, ['A,A', 'T', '--unseen-counts', csv,
                                  '--split-hand', '--hand-count', '2', '--max-hands', str(cap),
                                  '--resplit-aces', '--hit-split-aces', *options])
    assert actual['rules']['resplit_aces'] is True
    assert actual['rules']['hit_split_aces'] is True
    assert actual['rules']['max_hands'] == cap
    assert set(actual['decision']['evs']) == actions


def test_ace_rule_flags_keep_first_split_rank_and_dealt_order(capsys):
    results = {}
    rules = replace(STANDARD, max_hands=3, resplit_aces=True)
    for cards in ('A,7', '7,A'):
        actual = _json_advice(capsys, [cards, 'T', '--unseen-counts', TINY_CSV,
                                      *ACE_STATE, '--resplit-aces'])
        assert actual == record.decision_record(cards, 'T', rules, shoe=TINY_COUNTS,
                                               is_split_hand=True, hand_count=2)
        assert actual['state']['cards'] == cards.split(',')
        results[cards] = set(actual['decision']['evs'])
    assert results == {'A,7': {'S'}, '7,A': {'S', 'H', 'D'}}


def test_hit_enabled_three_card_split_ace_uses_existing_validation(capsys, monkeypatch):
    args = ['A,5,5', '6', '--unseen-counts', '0,0,0,0,0,0,0,0,0,2', *ACE_STATE, '--h17']
    actual = _json_advice(capsys, [*args, '--hit-split-aces'])
    assert actual == record.decision_record(
        'A,5,5', '6', replace(STANDARD, max_hands=3, s17=False, hit_split_aces=True),
        shoe=(0,) * 9 + (2,), is_split_hand=True, hand_count=2)
    assert actual['state']['cards'] == ['A', '5', '5']
    assert set(actual['decision']['evs']) == {'S'}

    def forbidden(*args, **kwargs):
        pytest.fail('invalid three-card split ace reached the engine')

    monkeypatch.setattr(record, 'best_action', forbidden)
    with pytest.raises(SystemExit) as exc:
        cli.main([*args, '--json'])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ''
    assert 'a split ace receives only one card when hit_split_aces is False' in captured.err


@pytest.mark.parametrize('split,payout', [(False, 1.5), (True, 1.0)])
def test_enabled_ace_rules_do_not_reopen_twenty_one_or_make_a_split_natural(
        capsys, split, payout):
    flags = ACE_STATE if split else ['--max-hands', '3']
    actual = _json_advice(capsys, ['A,T', 'T', '--unseen-counts', ACE_CSV, *flags,
                                  '--resplit-aces', '--hit-split-aces'])
    assert actual['state']['is_split_hand'] is split
    assert actual['decision']['evs'] == {'S': payout}
    assert actual['decision']['action'] == 'S' and actual['decision']['margin'] == 0.0


@pytest.mark.parametrize('flag', ['--resplit-aces', '--hit-split-aces'])
def test_repeated_ace_enable_keeps_the_same_raw_record(capsys, flag):
    args = ['A,A', 'T', '--unseen-counts', ACE_CSV, *ACE_STATE, flag, '--json']
    assert cli.main(args) == 0
    once = capsys.readouterr()
    assert cli.main([*args, flag]) == 0
    repeated = capsys.readouterr()
    assert once == repeated and once.err == ''


@pytest.mark.parametrize('options', [
    ['--resplit-aces=false'], ['--hit-split-aces=True'], ['--resplit-aces=0'],
    ['--hit-split-aces=1'], ['--no-resplit-aces'], ['--no-hit-split-aces'],
])
def test_ace_enables_refuse_values_and_inverse_syntax_before_work(
        monkeypatch, capsys, options):
    _forbid_input_work(monkeypatch)
    with pytest.raises(SystemExit) as exc:
        cli.main(['A,A', 'T', '--json', *options])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == '' and 'usage:' in captured.err
    assert 'Traceback' not in captured.err


@pytest.mark.parametrize('flag', ['--resplit-aces', '--hit-split-aces'])
@pytest.mark.parametrize('json_flag', [[], ['--json']])
def test_replay_refuses_ace_rule_overrides_before_reading(monkeypatch, capsys, flag, json_flag):
    _forbid_input_work(monkeypatch)
    with pytest.raises(SystemExit) as exc:
        cli.main(['--replay', 'not-read-aces.json', flag, *json_flag])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ''
    assert ('--replay cannot be combined with cards, upcard, --table or state options'
            in captured.err)


@pytest.mark.parametrize('resplit,hit,actions', ACE_PAIRS)
def test_table_ace_rules_forward_and_caption_without_chart_work(
        monkeypatch, capsys, resplit, hit, actions):
    observed = []

    def empty_chart(rules):
        observed.append(rules)
        return {'hard': {}, 'soft': {}, 'pairs': {}}

    monkeypatch.setattr(cli, 'derive_table', empty_chart)
    assert cli.main(['--table', '--decks', '1', '--h17', '--no-das', '--max-hands', '3',
                     *_ace_flags(resplit, hit)]) == 0
    captured = capsys.readouterr()
    rules = replace(STANDARD, decks=1, s17=False, das=False, max_hands=3,
                    resplit_aces=resplit, hit_split_aces=hit)
    assert observed == [rules] and captured.err == ''
    phrase = 'ace resplitting allowed, ' if resplit else ''
    hitting = 'split aces may be hit' if hit else 'split aces get one card'
    caption = ('1 deck, dealer hits on soft 17, no double after split, dealer peeks, '
               f'no surrender, up to 3 hands, {phrase}{hitting}, blackjack pays 3:2')
    assert chart.describe_rules(rules) == caption
    assert captured.out.splitlines()[0] == (
        'Basic strategy derived by the solver (split approximations apply): ' + caption + '.')


@pytest.mark.parametrize('options', [
    ['--json'], ['--unseen', '9'], ['--split-hand'], ['--hand-count', '1'],
    ['--no-double'], ['--no-split'],
])
def test_ace_table_rules_keep_existing_dispatch_refusals(monkeypatch, capsys, options):
    _forbid_input_work(monkeypatch)
    with pytest.raises(SystemExit) as exc:
        cli.main(['--table', '--resplit-aces', '--hit-split-aces', *options])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == '' and '--table cannot be combined' in captured.err


PAYOUT_COUNTS = (0, 0, 0, 0, 0, 0, 0, 0, 1, 0)
PAYOUT_CSV = '0,0,0,0,0,0,0,0,1,0'


@pytest.mark.parametrize('token,expected', [
    ('0', 0.0), ('1.5', 1.5), ('1.2', 1.2), ('1.25', 1.25),
    ('+01.250', 1.25), ('.5', 0.5), ('1.', 1.0), ('125e-2', 1.25),
    ('0e10', 0.0), (' \t\r\n\v\f1.25 \t\r\n\v\f', 1.25),
    ('1E+2', 100.0), ('1e308', 1e308), ('5e-324', 5e-324),
    ('1e-9999', 0.0), ('-0.0', -0.0), ('-1e-9999', -0.0),
])
def test_payout_ascii_grammar_forwards_the_converted_float_without_work(
        capsys, monkeypatch, token, expected):
    _forbid_input_work(monkeypatch)
    observed = []

    def forwarded(cards, up, rules, **state):
        observed.append((cards, up, rules, state))
        return 'payout dispatch'

    monkeypatch.setattr(cli, 'decision_json', forwarded)
    assert cli.main(['A,T', '9', '--blackjack-payout=' + token, '--json']) == 0
    captured = capsys.readouterr()
    assert captured.out == 'payout dispatch\n' and captured.err == ''
    assert len(observed) == 1
    cards, up, rules, state = observed[0]
    assert (cards, up) == ('A,T', '9')
    assert rules == replace(STANDARD, blackjack_payout=expected)
    assert rules.blackjack_payout.hex() == expected.hex()
    assert state == {'shoe': None, 'is_split_hand': False, 'hand_count': 1,
                     'can_double': True, 'can_split': True}
    assert STANDARD.blackjack_payout.hex() == (1.5).hex()


@pytest.mark.parametrize('token', [
    '', ' \t\r\n\v\f', '3:2', '6:5', '3/2', '1+0.5', '1_5', '1,5',
    'True', 'false', 'NaN', 'nan', 'inf', '+Infinity', '-inf', '0x1.8p0',
    '1 2', '1\t.5', '1\n.5', '.', '+', '1e', '1e+', '1.2.3',
    '\u0661.5', '\uff11.5', '\u22120', '\uff0b1', '\u00a01.5',
    '1.5\u00a0', '\u20031.5', '\u00851.5', '-1', '-.5', '-1e-300',
    '-5e-324', '1e309', '-1e309', '9' * 400,
])
@pytest.mark.parametrize('json_flags', [[], ['--json']])
def test_payout_syntax_and_value_refusals_precede_every_input_work(
        capsys, monkeypatch, token, json_flags):
    _forbid_input_work(monkeypatch)
    with pytest.raises(SystemExit) as exc:
        cli.main(['A,T', '9', '--blackjack-payout=' + token, *json_flags])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ''
    assert '--blackjack-payout' in captured.err
    assert 'finite nonnegative ASCII decimal or scientific number' in captured.err
    assert 'usage:' in captured.err and 'Traceback' not in captured.err


@pytest.mark.parametrize('error', [ValueError, OverflowError])
def test_payout_conversion_exceptions_are_argparse_refusals(capsys, monkeypatch, error):
    _forbid_input_work(monkeypatch)

    def unavailable(token):
        raise error('conversion unavailable')

    monkeypatch.setattr(cli, 'float', unavailable, raising=False)
    with pytest.raises(SystemExit) as exc:
        cli.main(['A,T', '9', '--blackjack-payout=1.25', '--json'])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == '' and '--blackjack-payout' in captured.err
    assert 'finite nonnegative' in captured.err and 'Traceback' not in captured.err


@pytest.mark.parametrize('token,payout', [
    ('1.5', 1.5), ('1.2', 1.2), ('1.25', 1.25),
    ('0', 0.0), ('-0.0', -0.0), ('-1e-9999', -0.0),
])
def test_declared_natural_payout_is_the_complete_raw_settlement(capsys, token, payout):
    rules = replace(STANDARD, blackjack_payout=payout)
    assert cli.main(['A,T', '9', '--unseen-counts', PAYOUT_CSV,
                     '--blackjack-payout=' + token, '--json']) == 0
    captured = capsys.readouterr()
    saved = json.loads(captured.out)
    assert captured.err == ''
    assert saved == record.decision_record('A,T', '9', rules, shoe=PAYOUT_COUNTS)
    assert captured.out == record.decision_json(
        'A,T', '9', rules, shoe=PAYOUT_COUNTS) + '\n'
    assert saved['schema']['version'] == 1 and 'action_controls' not in saved['state']
    assert saved['state']['shoe']['counts'] == list(PAYOUT_COUNTS)
    assert saved['decision']['evs'] == {'S': payout}
    assert saved['decision']['action'] == 'S'
    assert saved['decision']['action_name'] == 'STAND'
    assert saved['decision']['margin'] == 0.0
    assert saved['rules']['blackjack_payout'].hex() == payout.hex()
    assert saved['decision']['evs']['S'].hex() == payout.hex()
    assert best_action('A,T', '9', PAYOUT_COUNTS, rules) == ('S', {'S': payout}, 0.0)
    if payout.hex() == (-0.0).hex():
        assert '"blackjack_payout": -0.0' in captured.out
        assert '"S": -0.0' in captured.out


@pytest.mark.parametrize('json_flags', [[], ['--json']])
def test_payout_omission_and_explicit_default_keep_existing_output_bytes(
        capsys, monkeypatch, json_flags):
    def forbidden(*args, **kwargs):
        pytest.fail('retained payout advice reached a whole-game estimate')

    monkeypatch.setattr(cli, 'house_edge', forbidden)
    args = ['A,T', '9', '--unseen-counts', PAYOUT_CSV, *json_flags]
    assert cli.main(args) == 0
    omitted = capsys.readouterr()
    assert cli.main([*args, '--blackjack-payout=1.5']) == 0
    explicit = capsys.readouterr()
    expected = (record.decision_json('A,T', '9', shoe=PAYOUT_COUNTS) if json_flags
                else cli.advise('A,T', '9', shoe=PAYOUT_COUNTS)) + '\n'
    assert omitted.out == explicit.out == expected
    assert omitted.err == explicit.err == ''
    assert chart.describe_rules(STANDARD) == DEFAULT_CAPTION


def test_custom_payout_v2_keeps_retained_counts_and_physical_reference(capsys):
    rules = replace(STANDARD, blackjack_payout=1.25)
    args = ['T,4', 'T', '--blackjack-payout=1.25', '--no-double', '--no-split']
    saved = _json_advice(capsys, [*args, '--unseen-counts', TINY_CSV])
    physical = _json_advice(capsys, [*args, '--unseen', '2,3,7,8,9,T'])
    expected = record.decision_record(
        'T,4', 'T', rules, shoe=TINY_COUNTS, can_double=False, can_split=False)
    assert saved == physical == expected
    assert saved['schema']['version'] == 2
    assert list(saved['state']) == [
        'cards', 'dealer_up', 'total', 'soft', 'is_split_hand', 'hand_count',
        'action_controls', 'shoe',
    ]
    assert saved['state']['action_controls'] == {'can_double': False, 'can_split': False}
    assert saved['state']['shoe']['counts'] == list(TINY_COUNTS)
    assert saved['state']['shoe']['rank_order'] == list(RANKS)
    assert saved['state']['shoe']['source'] == 'supplied_unseen'
    assert saved['state']['cards'] == ['T', '4']
    assert saved['decision']['whole_game_estimate'] is None
    assert saved['model']['dealer_information'] == 'hidden_hole_post_peek'
    reference = physical_reference(('T', '4'), 'T', ('2', '3', '7', '8', '9', 'T'))
    assert saved['decision']['evs'] == pytest.approx(
        {key: float(reference[key]) for key in ('S', 'H')}, rel=0, abs=1e-12)
    assert reference['H'] == Fraction(-71, 120)
    action, values, margin = best_action(
        'T,4', 'T', TINY_COUNTS, rules, can_double=False, can_split=False)
    assert (saved['decision']['action'], saved['decision']['evs'],
            saved['decision']['margin']) == (action, values, margin)


def test_custom_payout_text_forwards_rules_and_counts_without_whole_game_work(
        capsys, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('retained payout advice reached a whole-game estimate')

    monkeypatch.setattr(cli, 'house_edge', forbidden)
    rules = replace(STANDARD, decks=1, s17=False, das=False, max_hands=2,
                    blackjack_payout=1.25, resplit_aces=True, hit_split_aces=True)
    args = ['T,4', 'T', '--unseen-counts', TINY_CSV, '--blackjack-payout=1.25',
            '--decks', '1', '--h17', '--no-das', '--max-hands', '2',
            '--resplit-aces', '--hit-split-aces', '--no-double', '--no-split']
    assert cli.main(args) == 0
    captured = capsys.readouterr()
    assert captured.err == ''
    assert captured.out == cli.advise(
        'T,4', 'T', rules, shoe=TINY_COUNTS, can_double=False, can_split=False) + '\n'
    assert 'A=0, 2=1, 3=1, 4=0, 5=0, 6=0, 7=1, 8=1, 9=1, T=1' in captured.out
    assert 'Current action restrictions: DOUBLE, SPLIT\n' in captured.out
    assert 'No whole-game estimate is computed.' in captured.out


def test_custom_payout_does_not_turn_split_twenty_one_into_a_natural(capsys):
    rules = replace(STANDARD, blackjack_payout=1.25)
    saved = _json_advice(capsys, ['A,T', 'T', '--unseen', '9', '--split-hand',
                                 '--hand-count', '2', '--blackjack-payout=1.25'])
    assert saved == record.decision_record(
        'A,T', 'T', rules, shoe=PAYOUT_COUNTS, is_split_hand=True, hand_count=2)
    assert saved['state']['is_split_hand'] is True
    assert saved['state']['cards'] == ['A', 'T']
    assert saved['state']['hand_count'] == 2
    assert saved['decision']['evs'] == {'S': 1.0}
    assert saved['decision']['action'] == 'S' and saved['decision']['margin'] == 0.0


@pytest.mark.parametrize('cards', ['A,7', '7,A'])
def test_payout_keeps_dealt_order_first_split_rank_and_other_rules(capsys, cards):
    rules = replace(STANDARD, max_hands=2, das=False, blackjack_payout=1.25)
    saved = _json_advice(capsys, [cards, 'T', '--unseen-counts', TINY_CSV,
                                 '--split-hand', '--max-hands', '2', '--no-das',
                                 '--blackjack-payout=1.25'])
    assert saved == record.decision_record(
        cards, 'T', rules, shoe=TINY_COUNTS, is_split_hand=True, hand_count=2)
    assert saved['state']['cards'] == cards.split(',')
    assert saved['state']['shoe']['counts'] == list(TINY_COUNTS)
    assert set(saved['decision']['evs']) == ({'S'} if cards == 'A,7' else {'S', 'H'})


@pytest.mark.parametrize('cards,up,csv,token,split,controlled', [
    ('A,T', '9', PAYOUT_CSV, '1.2', False, False),
    ('A,T', '9', PAYOUT_CSV, '-0.0', False, False),
    ('T,4', 'T', TINY_CSV, '1.25', False, True),
    ('A,T', 'T', PAYOUT_CSV, '1.25', True, False),
])
def test_declared_payout_saved_stdout_replays_once_without_rule_overrides(
        capsys, monkeypatch, tmp_path, cards, up, csv, token, split, controlled):
    flags = (['--split-hand', '--hand-count', '2'] if split else [])
    if controlled:
        flags += ['--no-double', '--no-split']
    assert cli.main([cards, up, '--unseen-counts', csv,
                     '--blackjack-payout=' + token, *flags, '--json']) == 0
    created = capsys.readouterr()
    assert created.err == ''
    saved = json.loads(created.out)
    path = tmp_path / 'declared-payout.json'
    with path.open('x', encoding='utf-8', newline='') as stream:
        stream.write(created.out)
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    original = record.best_action
    observed = []

    def observed_decision(hand, dealer, *, shoe, rules, is_split_hand, hand_count,
                          can_double, can_split):
        observed.append((tuple(hand), dealer, shoe, rules, is_split_hand, hand_count,
                         can_double, can_split))
        return original(hand, dealer, shoe=shoe, rules=rules, is_split_hand=is_split_hand,
                        hand_count=hand_count, can_double=can_double, can_split=can_split)

    monkeypatch.setattr(record, 'best_action', observed_decision)
    assert cli.main(['--replay', str(path), '--json']) == 0
    replayed_output = capsys.readouterr()
    assert replayed_output.err == ''
    replayed = json.loads(replayed_output.out)
    assert len(observed) == 1
    assert observed == [(
        tuple(saved['state']['cards']), saved['state']['dealer_up'],
        tuple(saved['state']['shoe']['counts']),
        replace(STANDARD, blackjack_payout=float(token)), split, 2 if split else 1,
        not controlled, not controlled,
    )]
    assert replayed['status'] == 'agreement' and replayed['error'] is None
    assert replayed['modeled_input']['rules'] == saved['rules']
    assert replayed['modeled_input']['state'] == saved['state']
    assert replayed['modeled_input']['model'] == saved['model']
    assert replayed['recorded'] == replayed['recomputed'] == saved['decision']
    assert replayed['comparison']['evs_match']
    assert replayed['comparison']['recommendation']['matches']
    assert replayed['comparison']['margin']['matches']
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    if token == '-0.0':
        assert replayed['modeled_input']['rules']['blackjack_payout'].hex() == (-0.0).hex()
        assert replayed['recorded']['evs']['S'].hex() == (-0.0).hex()
        assert replayed['recomputed']['evs']['S'].hex() == (-0.0).hex()


@pytest.mark.parametrize('token', ['1.5', '1.2', '0', '-0.0', '-1e-9999', '1e308'])
@pytest.mark.parametrize('json_flags', [[], ['--json']])
def test_explicit_payout_replay_conflict_is_pre_read_even_when_default(
        capsys, monkeypatch, token, json_flags):
    _forbid_input_work(monkeypatch)
    with pytest.raises(SystemExit) as exc:
        cli.main(['--replay', 'not-read-payout.json',
                  '--blackjack-payout=' + token, *json_flags])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ''
    assert '--replay cannot be combined' in captured.err and 'Traceback' not in captured.err


@pytest.mark.parametrize('token,payout,caption', [
    (None, 1.5, '3:2'), ('1.5', 1.5, '3:2'), ('1.2', 1.2, '6:5'),
    ('1.25', 1.25, '1.25:1'), ('0', 0.0, '0:1'), ('-0.0', -0.0, '-0:1'),
])
def test_payout_table_dispatch_keeps_existing_caption_without_chart_work(
        capsys, monkeypatch, token, payout, caption):
    observed = []

    def empty_chart(rules):
        observed.append(rules)
        return {'hard': {}, 'soft': {}, 'pairs': {}}

    monkeypatch.setattr(cli, 'derive_table', empty_chart)
    flags = [] if token is None else ['--blackjack-payout=' + token]
    assert cli.main(['--table', *flags]) == 0
    captured = capsys.readouterr()
    expected = replace(STANDARD, blackjack_payout=payout)
    assert observed == [expected] and captured.err == ''
    assert observed[0].blackjack_payout.hex() == payout.hex()
    expected_caption = DEFAULT_CAPTION.rsplit('3:2', 1)[0] + caption
    assert chart.describe_rules(expected) == expected_caption
    assert captured.out.splitlines()[0] == (
        'Basic strategy derived by the solver (split approximations apply): '
        + expected_caption + '.')
    assert captured.out == cli.render_chart(
        {'hard': {}, 'soft': {}, 'pairs': {}},
        title=('Basic strategy derived by the solver (split approximations apply): '
               + expected_caption + '.')) + '\n'


@pytest.mark.parametrize('options', [
    ['--json'], ['--unseen', '9'], ['--unseen-counts', PAYOUT_CSV],
    ['--split-hand'], ['--hand-count', '1'], ['--no-double'], ['--no-split'],
])
def test_payout_table_preserves_existing_state_and_json_refusals(
        capsys, monkeypatch, options):
    _forbid_input_work(monkeypatch)
    with pytest.raises(SystemExit) as exc:
        cli.main(['--table', '--blackjack-payout=1.25', *options])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == '' and '--table cannot be combined' in captured.err
