"""A completed twenty-one settles without hypothetical further actions."""
from dataclasses import replace
from fractions import Fraction
from itertools import permutations

import pytest

from bj import cli, ev
from bj.core import STANDARD, RANKS, STAND


def _shoe(cards):
    return tuple(cards.count(rank) for rank in RANKS)


def _settled_twenty_one(up, unseen, s17):
    """Enumerate at most two hidden cards with independent dealer arithmetic."""
    results = []
    for order in permutations(unseen):
        values = {'A': 1, 'T': 10}
        hard = values.get(up, int(up) if up.isdigit() else 0)
        aces = int(up == 'A')
        remaining = iter(order)
        hole = next(remaining)
        hard += values.get(hole, int(hole) if hole.isdigit() else 0)
        aces += int(hole == 'A')
        if (up == 'A' and hole == 'T') or (up == 'T' and hole == 'A'):
            continue  # The public decision is after the negative dealer peek.
        while True:
            soft = aces > 0 and hard + 10 <= 21
            total = hard + 10 if soft else hard
            if total > 21 or total > 17 or (total == 17 and (s17 or not soft)):
                break
            card = next(remaining)
            hard += values.get(card, int(card) if card.isdigit() else 0)
            aces += int(card == 'A')
        results.append(0 if total == 21 else 1)
    return sum(Fraction(result, len(results)) for result in results)


@pytest.mark.parametrize('cards,split,hit_split_aces', [
    (('7', '7', '7'), False, False),
    (('A', '5', '5'), False, False),
    (('T', 'A'), True, False),
    (('A', 'T'), True, False),
    (('A', 'T'), True, True),
])
@pytest.mark.parametrize('up,unseen,expected', [
    ('6', ('T', 'T'), Fraction(1)),
    ('T', ('5', '6'), Fraction(0)),
    ('9', ('2', 'T'), Fraction(1, 2)),
])
def test_completed_twenty_one_has_only_its_exact_settlement(
        cards, split, hit_split_aces, up, unseen, expected):
    # Every legal hidden-card ordering either busts, pushes or stays below21.
    # No extra player card is drawn in this independently declared reference.
    rules = replace(STANDARD, hit_split_aces=hit_split_aces)
    assert _settled_twenty_one(up, unseen, rules.s17) == expected
    assert ev.best_action(cards, up, _shoe(unseen), rules,
                          is_split_hand=split) == (STAND, {STAND: expected}, 0.0)


@pytest.mark.parametrize('s17', [True, False])
def test_completed_hand_keeps_the_actual_dealer_drawing_rule(s17):
    # H17 adds a ten to soft17, making hard17; S17 keeps the soft17. Both lose.
    unseen = ('A', 'T')
    assert _settled_twenty_one('6', unseen, s17) == 1
    assert ev.best_action(('A', '5', '5'), '6', _shoe(unseen),
                          replace(STANDARD, s17=s17)) == (STAND, {STAND: 1}, 0.0)


@pytest.mark.parametrize('payout', [1.2, 1.5, 2.0])
def test_natural_payout_and_split_settlement_remain_distinct(payout):
    rules = replace(STANDARD, blackjack_payout=payout)
    shoe = _shoe(('T', 'T'))
    assert ev.best_action(('A', 'T'), '6', shoe, rules) == (
        STAND, {STAND: payout}, 0.0,
    )
    assert ev.best_action(('T', 'A'), '6', shoe, rules, is_split_hand=True) == (
        STAND, {STAND: 1}, 0.0,
    )


@pytest.mark.parametrize('cards', [(), ('T',), ('T', 'T', '2')])
def test_invalid_or_busted_hands_do_not_enter_completed_hand_settlement(cards):
    with pytest.raises(ValueError):
        ev.best_action(cards, '6', _shoe(('T', 'T')))


@pytest.mark.parametrize('counts', [(), (0,) * 9, (False,) + (0,) * 9,
                                   (0,) * 9 + (1.5,)])
def test_completed_hand_still_validates_the_explicit_shoe(counts):
    with pytest.raises(ValueError, match='ten nonnegative integer'):
        ev.best_action(('7', '7', '7'), '6', counts)


@pytest.mark.parametrize('unseen,error', [((), 'no hole card'),
                                        (('T',), 'dealer must draw')])
def test_completed_hand_does_not_invent_an_unavailable_dealer_result(unseen, error):
    with pytest.raises(ValueError, match=error):
        ev.best_action(('7', '7', '7'), '6', _shoe(unseen))


def test_twenty_is_still_a_decision_and_explicit_counterfactuals_are_unchanged():
    shoe = _shoe(('T', 'T'))
    assert ev.best_action(('T', 'T'), '6', shoe, can_split=False) == (
        STAND, {STAND: 1, 'H': -1, 'D': -2}, 2,
    )
    assert ev.ev_hit(('7', '7', '7'), '6', shoe) == -1
    assert ev.ev_double(('7', '7', '7'), '6', shoe) == -2
    with pytest.raises(ValueError, match='dealer must draw'):
        ev.ev_hit(('T', 'A'), '6', shoe)


def test_actual_advice_report_does_not_print_impossible_actions(monkeypatch):
    # Isolate the unrelated expensive whole-game study. The hand calculation
    # and report formatting remain the actual public caller path.
    monkeypatch.setattr(cli, 'house_edge', lambda *args, **kwargs: 0)
    report = cli.advise('7,7,7', '6', replace(STANDARD, decks=1))
    assert 'STAND' in report and 'margin +0.0000' in report
    assert 'HIT' not in report and 'DOUBLE' not in report and 'SPLIT' not in report
