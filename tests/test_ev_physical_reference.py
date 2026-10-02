"""Bounded rational references for the public hit, stand and double values.

Complete physical deals retain the hidden hole and the actual dealer deck.
Continuation choices group deals by visible player draws before maximizing.
The oracle uses no production card-total, draw-probability or dealer helpers.
Each fixture contains six unseen cards, so it enumerates at most 720 deals.
These constructed cases do not establish a full-shoe or split error bound.
"""
from dataclasses import replace
from fractions import Fraction
from itertools import permutations

import pytest

from bj import ev
from bj.core import DOUBLE, HIT, STANDARD, STAND


# Adapter for the public count-tuple format. The oracle below uses the rank
# labels of physical cards directly, independently of this representation.
COUNT_ORDER = ('A', '2', '3', '4', '5', '6', '7', '8', '9', 'T')


def _shoe(cards):
    return tuple(cards.count(rank) for rank in COUNT_ORDER)


def _total(cards):
    low = sum(1 if r == 'A' else 10 if r == 'T' else int(r) for r in cards)
    soft = 'A' in cards and low + 10 <= 21
    return low + (10 if soft else 0), soft


def physical_reference(cards, up, unseen, *, s17=True, reveal_hole=False,
                       allow_later_double=False):
    """Exact rational forced-action values for the declared nonnatural fixtures.

    The last two switches are deliberately invalid-information or invalid-action
    controls. Production comparisons always keep both switches off.
    """
    assert 2 <= len(unseen) <= 6
    worlds = [(unseen[order[0]], tuple(unseen[i] for i in order[1:]))
              for order in permutations(range(len(unseen)))
              if not (up == 'A' and unseen[order[0]] == 'T')
              and not (up == 'T' and unseen[order[0]] == 'A')]
    if not worlds:
        raise ValueError('oracle peek is impossible')

    def stand(hand, deals):
        value = _total(hand)[0]
        if value > 21:
            return Fraction(-1)
        net = 0
        for hole, deck in deals:
            dealer, cursor = [up, hole], 0
            while True:
                dt, soft = _total(dealer)
                if dt > 17 or (dt == 17 and (s17 or not soft)):
                    break
                if cursor == len(deck):
                    raise ValueError('oracle dealer exhausted')
                dealer.append(deck[cursor])
                cursor += 1
            net += 1 if dt > 21 or value > dt else -1 if value < dt else 0
        return Fraction(net, len(deals))

    def draw(hand, deals, doubled=False):
        groups = {}
        for hole, deck in deals:
            if not deck:
                raise ValueError('oracle player exhausted')
            groups.setdefault(deck[0], []).append((hole, deck[1:]))
        answer = Fraction(0)
        for rank, group in groups.items():
            next_hand = hand + (rank,)
            value = 2 * stand(next_hand, group) if doubled else play(next_hand, group)
            answer += Fraction(len(group), len(deals)) * value
        return answer

    def play(hand, deals):
        if _total(hand)[0] >= 21 or not deals[0][1]:
            return stand(hand, deals)
        options = [stand(hand, deals), draw(hand, deals)]
        if allow_later_double:
            options.append(draw(hand, deals, doubled=True))
        return max(options)

    def values(deals):
        return {STAND: stand(cards, deals), HIT: draw(cards, deals),
                DOUBLE: draw(cards, deals, doubled=True)}

    if not reveal_hole:
        return values(worlds)
    groups = {}
    for world in worlds:
        groups.setdefault(world[0], []).append(world)
    known_hole_values = [(len(group), values(group)) for group in groups.values()]
    return {action: sum(Fraction(count, len(worlds)) * result[action]
                        for count, result in known_hole_values)
            for action in (STAND, HIT, DOUBLE)}


CASES = (
    (('T', '4'), 'T', ('2', '3', '7', '8', '9', 'T'), True),
    (('T', '4'), 'T', ('A', '3', '7', '8', '9', 'T'), True),
    (('T', '2'), 'A', ('6', '7', '8', '9', 'T', 'T'), True),
    (('T', '2'), 'A', ('6', '7', '8', '9', 'T', 'T'), False),
    (('A', '6'), 'T', ('A', 'A', '7', '8', '9', 'T'), True),
    (('A', '6'), '9', ('A', '7', '8', '9', 'T', 'T'), True),
    (('6', '5'), 'T', ('A', '2', '7', '8', '9', 'T'), True),
    (('T', '6'), '6', ('A', '7', '8', '9', 'T', 'T'), True),
)


@pytest.mark.parametrize('cards,up,unseen,s17', CASES)
def test_public_values_and_advice_match_rational_physical_deals(cards, up, unseen, s17):
    rules = replace(STANDARD, s17=s17)
    shoe = _shoe(unseen)
    expected = physical_reference(cards, up, unseen, s17=s17)
    actual = {STAND: ev.ev_stand(cards, up, shoe, rules),
              HIT: ev.ev_hit(cards, up, shoe, rules),
              DOUBLE: ev.ev_double(cards, up, shoe, rules)}
    assert actual == pytest.approx({a: float(v) for a, v in expected.items()},
                                   rel=0, abs=1e-12)

    action, values, margin = ev.best_action(cards, up, shoe, rules, can_split=False)
    assert set(values) == set(expected)
    assert values == pytest.approx({a: float(v) for a, v in expected.items()},
                                   rel=0, abs=1e-12)
    best = max(expected.values())
    assert action in {a for a, v in expected.items() if v == best}
    ordered = sorted(expected.values(), reverse=True)
    assert margin == pytest.approx(float(ordered[0] - ordered[1]), rel=0, abs=1e-12)


def test_continuation_decisions_cannot_see_the_hidden_hole():
    cards, up, unseen = CASES[0][:3]
    observed = physical_reference(cards, up, unseen)
    clairvoyant = physical_reference(cards, up, unseen, reveal_hole=True)
    assert observed[HIT] == Fraction(-71, 120)
    assert clairvoyant[HIT] == Fraction(-8, 15)
    assert clairvoyant[HIT] > observed[HIT]
    assert ev.ev_hit(cards, up, _shoe(unseen)) == pytest.approx(
        float(observed[HIT]), rel=0, abs=1e-12)


def test_double_takes_one_card_and_never_uses_the_later_hit_policy():
    cards, up, unseen = CASES[6][:3]
    expected = physical_reference(cards, up, unseen)
    assert expected[HIT] == Fraction(11, 75)
    assert expected[DOUBLE] == Fraction(-53, 150)
    assert expected[DOUBLE] != 2 * expected[HIT]
    assert ev.ev_double(cards, up, _shoe(unseen)) == pytest.approx(
        float(expected[DOUBLE]), rel=0, abs=1e-12)


def test_hit_continuations_do_not_admit_a_later_double():
    cards, up, unseen = ('2', '2'), 'T', ('7', '7', '8', '9', 'T', 'T')
    observed = physical_reference(cards, up, unseen)
    illegal = physical_reference(cards, up, unseen, allow_later_double=True)
    assert observed[HIT] == Fraction(-1, 60)
    assert illegal[HIT] == Fraction(1, 12)
    assert illegal[HIT] > observed[HIT]
    assert ev.ev_hit(cards, up, _shoe(unseen)) == pytest.approx(
        float(observed[HIT]), rel=0, abs=1e-12)

    # After the next visible seven, doubling remains unavailable even if the
    # caller supplies an affirmative button flag. The counterfactual API can
    # still price a double, so this checks the actual recommendation boundary.
    next_hand = ('2', '2', '7')
    remaining = ('7', '8', '9', 'T', 'T')
    _action, values, _margin = ev.best_action(next_hand, up, _shoe(remaining),
                                            can_double=True, can_split=False)
    assert set(values) == {STAND, HIT}
    expected = physical_reference(next_hand, up, remaining)
    assert values == pytest.approx({a: float(expected[a]) for a in (STAND, HIT)},
                                   rel=0, abs=1e-12)
