"""Portable state, rational references and refusals for the opt-in record."""
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import pytest

from bj import __version__, cli, record
from bj.core import RANKS, STANDARD, STAND, Rules
from bj.ev import best_action
from test_ev_physical_reference import CASES, physical_reference


def _shoe(cards):
    return tuple(cards.count(rank) for rank in RANKS)


@pytest.mark.parametrize('cards,up,unseen,s17', CASES)
def test_record_matches_independent_physical_deals_and_replays(cards, up, unseen, s17):
    rules = replace(STANDARD, s17=s17)
    answer = json.loads(record.decision_json(cards, up, rules, shoe=_shoe(unseen)))
    expected = physical_reference(cards, up, unseen, s17=s17)
    decision = answer['decision']
    assert decision['evs'] == pytest.approx({a: float(v) for a, v in expected.items()},
                                          rel=0, abs=1e-12)
    ordered = sorted(expected.values(), reverse=True)
    assert decision['margin'] == pytest.approx(float(ordered[0] - ordered[1]),
                                             rel=0, abs=1e-12)
    assert expected[decision['action']] == ordered[0]
    state = answer['state']
    replay = best_action(state['cards'], state['dealer_up'],
                         shoe=tuple(state['shoe']['counts']), rules=Rules(**answer['rules']),
                         is_split_hand=state['is_split_hand'], hand_count=state['hand_count'])
    assert replay == (decision['action'], decision['evs'], decision['margin'])
    assert answer['rules'] == asdict(rules)
    assert answer['schema'] == {'name': 'blackjack-decision', 'version': 1}
    assert answer['package'] == {'name': 'exact-blackjack-solver', 'version': __version__}
    assert answer['model']['hole_rank_excluded_by_peek'] == (
        'T' if up == 'A' else 'A' if up == 'T' else None)
    assert answer['model']['dealer_information'] == 'hidden_hole_post_peek'
    assert answer['model']['split_error_bound'] is None
    assert decision['units'] == 'original_wager'
    assert decision['whole_game_estimate'] is None


def test_normalized_snapshot_is_owned_and_does_not_round_values():
    cards = ['K', 4]
    unseen = list(_shoe(('2', '3', '7', '8', '9', 'T')))
    answer = record.decision_record(cards, '10', shoe=unseen)
    cards[:] = ['A', 'A']
    unseen[:] = [0] * 10
    assert answer['state']['cards'] == ['T', '4']
    assert answer['state']['dealer_up'] == 'T'
    assert answer['state']['shoe']['rank_order'] == list(RANKS)
    assert answer['state']['shoe']['counts'] == list(_shoe(('2', '3', '7', '8', '9', 'T')))
    assert answer['state']['shoe']['source'] == 'supplied_unseen'
    assert answer['decision']['evs']['H'] == pytest.approx(-71 / 120, rel=0, abs=1e-12)
    assert answer['decision']['evs']['H'] != round(-71 / 120, 4)
    assert answer['state']['shoe']['includes_hidden_hole'] is True
    assert answer['state']['shoe']['visible_cards_already_removed'] is True


def test_only_declared_rule_fields_enter_a_public_record():
    @dataclass(frozen=True)
    class AnnotatedRules(Rules):
        private_note: str = 'private context must stay out of the record'
    answer = record.decision_record('A,T', '9', AnnotatedRules())
    assert answer['rules'] == asdict(STANDARD)
    assert 'private_note' not in json.dumps(answer)


def test_fresh_shoe_is_removed_once_and_replay_uses_retained_counts():
    rules = replace(STANDARD, decks=1, blackjack_payout=1.25)
    answer = record.decision_record('a,K', 9, rules)
    assert answer['state']['shoe']['source'] == 'fresh_minus_visible'
    assert answer['state']['shoe']['counts'] == [3, 4, 4, 4, 4, 4, 4, 4, 3, 15]
    assert answer['decision']['evs'] == {STAND: 1.25}
    assert answer['decision']['margin'] == 0.0
    assert answer['state']['total'] == 21
    assert answer['state']['soft'] is True
    state = answer['state']
    assert best_action(state['cards'], state['dealer_up'], tuple(state['shoe']['counts']),
                       Rules(**answer['rules'])) == (STAND, {STAND: 1.25}, 0.0)


def test_split_state_and_legal_actions_are_retained():
    rules = replace(STANDARD, das=False, max_hands=2)
    answer = record.decision_record('A,T', 'T', rules, shoe=_shoe(('9',)),
                                    is_split_hand=True, hand_count=2)
    assert answer['state']['is_split_hand'] is True
    assert answer['state']['hand_count'] == 2
    assert answer['decision']['evs'] == {STAND: 1.0}
    assert answer['decision']['margin'] == 0.0
    at_cap = record.decision_record('8,8', 'T', rules, shoe=_shoe(('7', '8', '9', 'T')),
                                    is_split_hand=True, hand_count=2)
    assert 'P' not in at_cap['decision']['evs']
    assert 'D' not in at_cap['decision']['evs']


@pytest.mark.parametrize('changes,match', [
    ({'peek': False}, 'post-peek'),
    ({'surrender': True}, 'surrender'),
    ({'double_any_two': False}, 'any two-card'),
    ({'tens_are_pairs': False}, 'collapse ten-value'),
    ({'decks': 0}, 'positive integer'),
    ({'decks': True}, 'positive integer'),
    ({'max_hands': 0}, 'positive integer'),
    ({'max_hands': 2.5}, 'positive integer'),
    ({'s17': 1}, 'boolean'),
    ({'blackjack_payout': float('nan')}, 'finite'),
    ({'blackjack_payout': float('inf')}, 'finite'),
    ({'blackjack_payout': -1}, 'nonnegative'),
    ({'insurance_payout': float('inf')}, 'finite'),
    ({'insurance_payout': True}, 'finite'),
])
def test_invalid_or_unmodeled_rules_refuse_before_calculation(monkeypatch, changes, match):
    def forbidden(*args, **kwargs):
        pytest.fail('invalid rules reached calculation')
    monkeypatch.setattr(record, 'best_action', forbidden)
    with pytest.raises(ValueError, match=match):
        record.decision_record('T,4', 'T', replace(STANDARD, **changes),
                               shoe=_shoe(('2', '3', '7', '8', '9', 'T')))


@pytest.mark.parametrize('kwargs,match', [
    ({'hand_count': 2}, 'requires a split hand'),
    ({'is_split_hand': True, 'hand_count': 1}, 'at least two'),
    ({'hand_count': True}, 'integer'),
    ({'hand_count': 0}, 'integer'),
    ({'hand_count': 5}, 'integer'),
    ({'is_split_hand': 1}, 'boolean'),
    ({'shoe': (0,) * 10}, 'reserved dealer hole'),
    ({'shoe': (1,) + (0,) * 9}, 'no possible hole'),
    ({'shoe': (1.0,) * 10}, 'integer counts'),
])
def test_invalid_state_refuses_without_a_record(kwargs, match):
    with pytest.raises(ValueError, match=match):
        record.decision_record('A,T', 'T', **kwargs)


def test_required_dealer_draw_shortage_is_not_hidden_by_serialization():
    with pytest.raises(ValueError, match='shoe is empty'):
        record.decision_json('T,6', '6', shoe=_shoe(('2',)))


@pytest.mark.parametrize('result,match', [
    (('S', {'S': float('nan')}, 0.0), 'nonfinite'),
    (('S', {'S': float('inf')}, 0.0), 'nonfinite'),
    (('S', {'S': True}, 0.0), 'invalid action value'),
    (('S', {'S': 0.0}, float('nan')), 'nonfinite'),
    (('S', {'S': 0.0}, -1.0), 'inconsistent'),
    (('S', {'S': 0.0, 'H': 1.0}, 1.0), 'inconsistent'),
    (('S', {}, 0.0), 'action set'),
    (('X', {'X': 0.0}, 0.0), 'action set'),
])
def test_invalid_solver_result_cannot_be_emitted(monkeypatch, result, match):
    monkeypatch.setattr(record, 'best_action', lambda *args, **kwargs: result)
    with pytest.raises(ValueError, match=match):
        record.decision_json('A,T', '9')


def test_cli_json_is_only_json_and_does_not_compute_a_whole_game(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail('record computed an unrelated whole-game estimate')
    monkeypatch.setattr(cli, 'house_edge', forbidden)
    assert cli.main(['T,4', 'T', '--unseen', '2,3,7,8,9,T', '--json']) == 0
    output = capsys.readouterr()
    assert not output.err
    answer = json.loads(output.out)
    assert answer == record.decision_record('T,4', 'T', shoe=_shoe(('2', '3', '7', '8', '9', 'T')))
    assert cli.main(['A,T', '9', '--json', '--decks', '1']) == 0
    assert json.loads(capsys.readouterr().out)['state']['shoe']['source'] == 'fresh_minus_visible'


@pytest.mark.parametrize('args', [
    ['--json', '--table'],
    ['--json', '--table', '--unseen', '9'],
    ['--json', '--split-hand', '--hand-count', '1'],
    ['--json', '--hand-count', '2'],
])
def test_cli_conflicts_fail_before_any_calculation(monkeypatch, capsys, args):
    def forbidden(*args, **kwargs):
        pytest.fail('conflicting options reached calculation')
    monkeypatch.setattr(cli, 'table', forbidden)
    monkeypatch.setattr(cli, 'decision_json', forbidden)
    with pytest.raises(SystemExit) as exc:
        cli.main(args)
    assert exc.value.code == 2
    assert capsys.readouterr().out == ''


def test_ordinary_cli_text_is_still_the_existing_report(capsys):
    arguments = ['T,4', 'T', '--unseen', '2,3,7,8,9,T']
    expected = cli.advise('T,4', 'T', shoe=_shoe(('2', '3', '7', '8', '9', 'T'))) + '\n'
    assert cli.main(arguments) == 0
    assert capsys.readouterr().out == expected


CONTROL_PAIRS = ((True, True), (False, True), (True, False), (False, False))


@pytest.mark.parametrize('can_double,can_split', CONTROL_PAIRS)
def test_current_controls_preserve_independent_physical_hit_and_stand(
        can_double, can_split):
    # This oracle enumerates physical deals independently. Removing the
    # immediate DOUBLE must not remove later modeled hit/stand continuation.
    cards, up, unseen, s17 = CASES[0]
    expected = physical_reference(cards, up, unseen, s17=s17)
    answer = record.decision_record(cards, up, shoe=_shoe(unseen),
                                    can_double=can_double, can_split=can_split)
    values = answer['decision']['evs']
    permitted = {'H', 'S'} | ({'D'} if can_double else set())
    assert set(values) == permitted
    assert values == pytest.approx({a: float(expected[a]) for a in permitted},
                                   rel=0, abs=1e-12)
    ordered = sorted(values.values(), reverse=True)
    assert values[answer['decision']['action']] == ordered[0]
    assert answer['decision']['margin'] == ordered[0] - ordered[1]
    assert answer['state']['shoe']['counts'] == list(_shoe(unseen))
    if can_double and can_split:
        assert answer['schema']['version'] == record.SCHEMA_VERSION == 1
        assert 'action_controls' not in answer['state']
    else:
        assert answer['schema']['version'] == record.CONTROLLED_SCHEMA_VERSION == 2
        assert list(answer['state']) == [
            'cards', 'dealer_up', 'total', 'soft', 'is_split_hand', 'hand_count',
            'action_controls', 'shoe']
        assert list(answer['state']['action_controls']) == ['can_double', 'can_split']
        assert answer['state']['action_controls'] == {
            'can_double': can_double, 'can_split': can_split}


@pytest.mark.parametrize('can_double,can_split', CONTROL_PAIRS)
def test_current_controls_match_existing_engine_for_retained_split_case(
        can_double, can_split):
    # Same-engine consistency. The retained split case is not an independent
    # split oracle or an approximation error bound.
    rules = replace(STANDARD, max_hands=2)
    counts = (1,) + (0,) * 8 + (5,)
    answer = record.decision_record('T,T', '7', rules, shoe=counts,
                                    can_double=can_double, can_split=can_split)
    expected = best_action('T,T', '7', shoe=counts, rules=rules,
                           can_double=can_double, can_split=can_split)
    assert (answer['decision']['action'], answer['decision']['evs'],
            answer['decision']['margin']) == expected
    assert set(answer['decision']['evs']) == (
        {'H', 'S'} | ({'D'} if can_double else set()) | ({'P'} if can_split else set()))
    if can_split:
        assert answer['decision']['evs']['P'] == 2.0
    assert answer['decision']['evs']['S'] == 1.0


def test_default_and_explicit_true_records_keep_immutable_version_one_bytes():
    fixture = Path(__file__).parent / 'fixtures/saved-decision-v1-7a38141.json'
    expected = fixture.read_text(encoding='utf-8').rstrip('\n')
    args = ('T,4', 'T')
    state = {'shoe': _shoe(('2', '3', '7', '8', '9', 'T'))}
    assert record.decision_json(*args, **state) == expected
    assert record.decision_json(*args, **state, can_double=True, can_split=True) == expected
    old_text = (
        'Hand: T 4  (14)  vs dealer T\n\n'
        'Unseen shoe (includes dealer hole): A=0, 2=1, 3=1, 4=0, 5=0, 6=0, '
        '7=1, 8=1, 9=1, T=1\n\n'
        '  HIT      EV -0.5917  <- recommended\n'
        '  STAND    EV -0.6667\n'
        '  DOUBLE   EV -1.2000\n\n'
        'Recommended: HIT  (margin +0.0750 over the next-best action)\n\n'
        'Values apply to this hand and stated round state. No whole-game estimate is computed.')
    assert cli.advise(*args, **state) == old_text
    assert cli.advise(*args, **state, can_double=True, can_split=True) == old_text


@pytest.mark.parametrize('wrapper', [record.decision_record, record.decision_json, cli.advise])
@pytest.mark.parametrize('key', ['can_double', 'can_split'])
@pytest.mark.parametrize('value', [None, 0, 1, 1.0, 'false', [], {}])
def test_public_controls_are_genuine_booleans_before_pricing(
        monkeypatch, wrapper, key, value):
    def forbidden(*args, **kwargs):
        pytest.fail('invalid action control reached pricing')
    monkeypatch.setattr(record, 'best_action', forbidden)
    monkeypatch.setattr(cli, 'best_action', forbidden)
    with pytest.raises(ValueError, match=key + ' must be a boolean'):
        wrapper('T,4', 'T', shoe=_shoe(('2', '3', '7', '8', '9', 'T')), **{key: value})


@pytest.mark.parametrize('cards,up,unseen,kwargs,expected', [
    ('T,2,2', 'T', ('7', '8', '9', 'T'), {}, {'H', 'S'}),
    ('A,7', 'T', ('7', '8', '9', 'T'), {'is_split_hand': True}, {'S'}),
    ('T,T', '7', ('A', 'T', 'T', 'T', 'T', 'T'),
     {'is_split_hand': True, 'hand_count': 2}, {'H', 'S', 'D'}),
    ('A,T', '9', ('9',), {}, {'S'}),
])
def test_true_controls_cannot_restore_ineligible_actions(cards, up, unseen, kwargs, expected):
    answer = record.decision_record(cards, up, replace(STANDARD, max_hands=2),
                                    shoe=_shoe(unseen), can_double=True, can_split=True,
                                    **kwargs)
    assert set(answer['decision']['evs']) == expected
