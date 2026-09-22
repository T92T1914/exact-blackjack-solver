"""Unseen cards include the dealer's reserved card, even without a peek."""
from fractions import Fraction
from itertools import permutations

import pytest

from bj import ev
from bj.core import DOUBLE, HIT, RANKS, SPLIT, STAND


def _shoe(*cards):
    return tuple(cards.count(rank) for rank in RANKS)


@pytest.mark.parametrize('up', RANKS)
def test_player_cannot_draw_the_only_unseen_card(up):
    shoe = (0, 0, 0, 0, 0, 0, 0, 1, 0, 0)  # one nine, held by the dealer
    with pytest.raises(ValueError, match='hole card'):
        ev._draw_probs(shoe, up)


def test_busting_does_not_allow_hitting_with_no_draw_pile():
    shoe = (0, 0, 0, 0, 0, 0, 0, 0, 1, 0)  # dealer's ten
    with pytest.raises(ValueError, match='hole card'):
        ev.ev_hit(('T', 'T'), '7', shoe)


def test_one_drawable_card_remains_a_valid_distribution():
    # Each of the two hidden cards is equally likely to be reserved; the
    # player's sole draw is the other one. No peek information under a seven.
    shoe = (1, 0, 0, 0, 0, 0, 0, 0, 1, 0)
    assert ev._draw_probs(shoe, '7') == (0.5, 0, 0, 0, 0, 0, 0, 0, 0.5, 0)


def test_last_draw_has_an_exact_two_world_value():
    # The hole card and the sole drawable card are the two permutations of
    # 7,8. The dealer stands in either world; the player wins after either
    # draw. This calculation does not call the solver's card or EV helpers.
    worlds = list(permutations((7, 8)))
    wins = [int(12 + draw > 10 + hole) for hole, draw in worlds]
    expected_hit = sum(Fraction(win, len(worlds)) for win in wins)
    assert expected_hit == 1
    shoe = _shoe('7', '8')

    assert ev.ev_stand(('T', '2'), 'T', shoe) == -1
    assert ev.ev_hit(('T', '2'), 'T', shoe) == expected_hit
    assert ev.ev_double(('T', '2'), 'T', shoe) == 2 * expected_hit
    action, values, margin = ev.best_action(('T', '2'), 'T', shoe)
    assert action == DOUBLE
    assert values == {STAND: -1, HIT: 1, DOUBLE: 2}
    assert margin == 1


@pytest.mark.parametrize('cards,up,unseen,expected', [
    (('T', '2'), '9', ('8', '9'), 1),  # no peek; either draw wins
    (('T', '2'), 'A', ('8', '9'), Fraction(1, 2)),  # win or push
    (('T', '2'), 'T', ('A', '9'), -1),  # peek reserves 9; player must draw A
    (('T', '2'), 'A', ('8', 'T'), -1),  # peek reserves 8; player must draw T
    (('T', '2'), 'T', ('7', '7'), 1),  # repeated rank, not two distinct ranks
    (('A', '6'), 'T', ('7', '8'), -1),  # soft hand demotes and loses
])
def test_last_draw_keeps_peek_conditioning_and_hand_settlement(cards, up, unseen, expected):
    shoe = _shoe(*unseen)
    assert ev.ev_hit(cards, up, shoe) == expected
    assert ev.ev_double(cards, up, shoe) == 2 * expected


@pytest.mark.parametrize('up,hole', [('7', 'T'), ('T', '7'), ('A', '8')])
def test_only_reserved_hole_card_leaves_stand_as_the_only_action(up, hole):
    # The dealer can settle without another card. Even a pair cannot split
    # or double once the draw pile is empty.
    action, values, margin = ev.best_action(('T', 'T'), up, _shoe(hole))
    assert action == STAND
    assert values == {STAND: 1}
    assert margin == 0


def test_one_drawable_card_cannot_supply_two_split_hands():
    action, values, margin = ev.best_action(('T', 'T'), 'T', _shoe('7', '8'))
    assert action == STAND
    assert values == {STAND: 1, HIT: -1, DOUBLE: -2}
    assert margin == 2


@pytest.mark.parametrize('operation', [ev.ev_hit, ev.ev_double])
def test_explicit_draw_still_rejects_a_reserved_only_shoe(operation):
    with pytest.raises(ValueError, match='hole card'):
        operation(('T', '2'), 'T', _shoe('7'))


def test_last_draw_does_not_invent_a_dealer_settlement():
    # The player can draw a 7 or 8, but the dealer's remaining card only
    # brings a 2 upcard to 9 or 10. No defined terminal outcome exists.
    with pytest.raises(ValueError, match='dealer must draw'):
        ev.ev_hit(('T', '2'), '2', _shoe('7', '8'))


def test_several_draws_can_reach_the_last_draw_boundary():
    # A ten upcard's negative peek forces the seven into the hole. Starting
    # from six, the three aces produce soft 17, 18, then 19. The final two
    # totals beat the dealer's 17; an unavailable fourth draw adds no value.
    shoe = _shoe('A', 'A', 'A', '7')
    assert ev.ev_stand(('4', '2'), 'T', shoe) == -1
    assert ev.ev_hit(('4', '2'), 'T', shoe) == 1
    assert ev.ev_double(('4', '2'), 'T', shoe) == 0
    assert ev.best_action(('4', '2'), 'T', shoe) == (
        HIT, {STAND: -1, HIT: 1, DOUBLE: 0}, 1,
    )


@pytest.mark.parametrize('unseen', [(), ('9',), ('9', 'T')])
def test_explicit_split_requires_two_drawable_cards(unseen):
    # Valuing independent split hands must not turn one available draw into
    # a valid initial deal to two hands, including one-card-only split aces.
    with pytest.raises(ValueError, match='two drawable cards'):
        ev.ev_split('A', 'T', _shoe(*unseen))


@pytest.mark.parametrize('rank', ['A', 'T'])
def test_two_drawable_cards_allow_a_split_but_not_a_resplit(rank):
    # The dealer has 17 and both split hands receive a ten. Each wins one
    # unit, including split aces, which never receive a natural payout.
    # Paired tens cannot consume the original shoe again for a resplit.
    shoe = _shoe('T', 'T', 'T')
    assert ev.ev_split(rank, '7', shoe) == 2
    action, values, _margin = ev.best_action((rank, rank), '7', shoe)
    assert action == SPLIT
    assert values[SPLIT] == 2


def test_rejected_empty_draw_does_not_poison_a_later_valid_request():
    for operation in (ev.ev_hit, ev.ev_double):
        with pytest.raises(ValueError, match='shoe is empty'):
            operation(('T', '2'), 'T', _shoe())
    with pytest.raises(ValueError, match='no hole card'):
        ev.best_action(('T', '2'), 'T', _shoe())
    assert ev.best_action(('T', '2'), 'T', _shoe('7', '8')) == (
        DOUBLE, {STAND: -1, HIT: 1, DOUBLE: 2}, 1,
    )
