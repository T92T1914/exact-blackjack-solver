"""Completed twenty-one also ends play inside the split recurrence."""
from dataclasses import replace
from fractions import Fraction

import pytest

from bj import ev
from bj.core import CARDS_PER_DECK, DOUBLE, HIT, RANKS, SPLIT, STANDARD, STAND
from bj.record import decision_record
from bj.simulate import Cards, play_round
from bj.strategy import basic_action


def _shoe(cards):
    return tuple(cards.count(rank) for rank in RANKS)


@pytest.mark.parametrize('das', [False, True])
@pytest.mark.parametrize('s17', [False, True])
def test_split_tens_stop_at_twenty_one_before_ranking_or_recording(das, s17):
    # Independent arithmetic: the dealer has 17 or 18, and each split ten
    # receives T or A, making 20 or 21. Standing therefore wins two units.
    # On 20, a further T busts and the only A makes 21. Even after the other
    # hand draws, at least two drawable cards remain, so P(A) <= 1/2. Hit or
    # double cannot beat the certain one-unit stand. A completed 21 is closed.
    expected = Fraction(2)
    unseen = _shoe(('A', 'T', 'T', 'T', 'T', 'T'))
    rules = replace(STANDARD, max_hands=2, das=das, s17=s17)

    assert ev.ev_split('T', '7', unseen, rules) == float(expected)
    action, values, margin = ev.best_action(('T', 'T'), '7', unseen, rules)
    assert action == SPLIT
    assert values[SPLIT] == float(expected)
    assert values[STAND] == 1
    assert margin == 1

    record = decision_record(('T', 'T'), '7', rules, shoe=unseen)
    assert record['decision']['action'] == SPLIT
    assert record['decision']['evs'][SPLIT] == float(expected)
    assert record['decision']['margin'] == 1


@pytest.mark.parametrize('hit_split_aces', [False, True])
def test_split_ace_twenty_one_keeps_its_one_unit_settlement(hit_split_aces):
    # Only tens remain. Dealer 17 loses to both completed split aces. The
    # natural premium and a hypothetical double on 21 are both unavailable.
    unseen = _shoe(('T', 'T', 'T', 'T', 'T'))
    rules = replace(STANDARD, max_hands=2, hit_split_aces=hit_split_aces)
    assert ev.ev_split('A', '7', unseen, rules) == 2
    assert ev.best_action(('A', 'T'), '7', unseen, rules,
                          is_split_hand=True, hand_count=2) == (
        STAND, {STAND: 1}, 0,
    )


@pytest.mark.parametrize('das,expected', [(False, 2), (True, 4)])
def test_doubling_before_twenty_one_remains_available(das, expected):
    # Each split two receives an eight, making ten. One more eight gives18,
    # while the dealer draws from15 to23. DAS therefore permits two winning
    # doubles, rather than two winning single-wager hands.
    unseen = _shoe(('8', '8', '8', '8', '8'))
    rules = replace(STANDARD, max_hands=2, das=das)
    assert ev.ev_split('2', '7', unseen, rules) == expected


@pytest.mark.parametrize('closed_action', [HIT, DOUBLE])
def test_strategy_grading_never_requests_an_action_on_completed_split_twenty_one(
        closed_action):
    requests = []

    def strategy(cards, up, rules, **context):
        requests.append(cards)
        return SPLIT if cards == ('A', 'A') else closed_action

    # This is house_edge's actual per-deal caller. Splitting aces yields two
    # completed21s against dealer17. A hostile chart cannot buy another draw
    # or add a wager after either hand has closed.
    unseen = _shoe(('T', 'T', 'T', 'T', 'T'))
    rules = replace(STANDARD, max_hands=2, hit_split_aces=True)
    assert ev._cell_ev(RANKS.index('A'), RANKS.index('A'), RANKS.index('7'),
                       unseen, rules, strategy) == 2
    assert requests == [('A', 'A')]


def _ordered_cards(prefix, decks=1):
    """Use the real draw path with one declared physical full-shoe order."""
    cards = Cards(0, decks=decks, block=64)
    counts = [copies * decks for copies in CARDS_PER_DECK]
    ordered = []
    for rank in prefix:
        index = RANKS.index(rank)
        ordered.append(index)
        counts[index] -= 1
        assert counts[index] >= 0
    cards._arr = ordered + [index for index, count in enumerate(counts) for _ in range(count)]
    # Fisher-Yates chooses the next physical card at each swap.
    cards._buf = [0.0] * 64
    return cards


@pytest.mark.parametrize('closed_action', [HIT, DOUBLE])
def test_simulation_closes_a_split_twenty_one_before_custom_strategy(closed_action):
    requests = []

    def strategy(hand, up, **context):
        requests.append((hand, context['is_split_hand']))
        if not context['is_split_hand']:
            return SPLIT
        return closed_action if hand == ('T', 'A') else STAND

    # Initial T,T splits. Its children receive A and T against dealer17.
    # The physical round therefore wins two single wagers and consumes six
    # cards. The trailing tens expose any extra draw or double after21.
    cards = _ordered_cards(('T', '7', 'T', 'T', 'A', 'T', 'T', 'T'))
    result = play_round(cards, replace(STANDARD, decks=1, max_hands=2), strategy=strategy)
    assert (result.net, result.wagered, result.doubled) == (2, 2, False)
    assert result.split and not result.player_bj
    assert result.player_finals == [21, 20]
    assert result.dealer_final == 17
    assert cards.cards_drawn == 6
    assert requests == [(('T', 'T'), False), (('T', 'T'), True)]


def test_simulation_closes_twenty_one_reached_by_hitting():
    requests = []

    def strategy(hand, up, **context):
        requests.append(hand)
        return HIT

    cards = _ordered_cards(('T', '7', '5', 'T', '6', 'T'))
    result = play_round(cards, replace(STANDARD, decks=1), strategy=strategy)
    assert (result.net, result.wagered, result.doubled) == (1, 1, False)
    assert result.player_finals == [21]
    assert cards.cards_drawn == 5
    assert requests == [('T', '5')]


@pytest.mark.parametrize('hit_split_aces', [False, True])
@pytest.mark.parametrize('custom_chart', [False, True])
def test_simulation_default_chart_keeps_completed_split_aces(hit_split_aces, custom_chart):
    rules = replace(STANDARD, decks=1, max_hands=2, hit_split_aces=hit_split_aces)
    cards = _ordered_cards(('A', '7', 'A', 'T', 'T', 'T'))

    def strategy(hand, up, **context):
        return basic_action(hand, up, rules, **context).action

    result = play_round(cards, rules, strategy=strategy if custom_chart else None)
    assert (result.net, result.wagered, result.doubled) == (2, 2, False)
    assert result.player_finals == [21, 21]
    assert result.split and not result.player_bj
    assert cards.cards_drawn == 6


def test_simulation_still_allows_a_custom_double_below_twenty_one():
    def strategy(hand, up, **context):
        return DOUBLE if context['is_split_hand'] else SPLIT

    # Two split twos double10 to18 while dealer15 draws to23. Six eights are
    # available in this two-deck physical order, so all nine draws are legal.
    cards = _ordered_cards(('2', '7', '2', '8', '8', '8', '8', '8', '8'), decks=2)
    result = play_round(cards, replace(STANDARD, decks=2, max_hands=2), strategy=strategy)
    assert (result.net, result.wagered, result.doubled) == (4, 4, True)
    assert result.player_finals == [18, 18]
    assert result.dealer_final == 23
    assert cards.cards_drawn == 9
