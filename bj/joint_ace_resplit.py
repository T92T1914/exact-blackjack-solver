"""Common-shoe one-card split aces with one optional shared resplit slot.

Every choice uses the visible history and concealed-hole posterior. The active
child finishes before the next pending seed receives its card. All completed
wagers settle against one dealer hand. Enumeration uses binary floating point.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from functools import cache
from time import perf_counter

from ._enumeration import state as _enumeration_state, state_limit
from .joint_split import ReferenceLimitExceeded, UnsupportedShoeError

RANKS = ('2', '3', '4', '5', '6', '7', '8', '9', 'T', 'A')
VALUES = (2, 3, 4, 5, 6, 7, 8, 9, 10, 1)
ACE = 9


@dataclass(frozen=True)
class AceResplitResult:
    value: float
    states: int
    elapsed_seconds: float
    cache_hits: int
    maximum_probability_mass_error: float
    state_counts: tuple[tuple[str, int], ...]


def _total(cards):
    low = sum(VALUES[index] for index in cards)
    soft = ACE in cards and low + 10 <= 21
    return low + (10 if soft else 0), soft


def _take(counts, index):
    return tuple(count - (rank == index) for rank, count in enumerate(counts))


def joint_ace_resplit_value(dealer_up, shoe, *, double_after_split=True,
                            stand_soft_17=True, max_states=100_000, max_seconds=10.0):
    """Price the forced initial A,A split, without pricing the original root.

    Counts follow this module's RANKS, exclude visible cards and include the
    hidden hole. Require 3..20 retained cards. A split ace receives one card,
    then may stand or resplit A,A if the round's sole extra slot is available.
    DAS is retained as a declared rule but never offers double on these children.
    Any unavailable continuation refuses the whole value, even if unchosen.
    The time allowance is cooperative joint work, without a wall supervisor.
    """
    if type(dealer_up) is not str or dealer_up not in RANKS:
        raise ValueError('dealer upcard must be a canonical rank')
    counts = tuple(shoe)
    if len(counts) != 10 or any(type(count) is not int or count < 0 for count in counts):
        raise ValueError('shoe must contain ten nonnegative integer counts')
    if not 3 <= sum(counts) <= 20:
        raise ValueError('joint ace resplit requires 3 to 20 unseen cards including the hole')
    if type(double_after_split) is not bool or type(stand_soft_17) is not bool:
        raise ValueError('DAS and S17 flags must be boolean')
    state_limit(max_states)
    if (type(max_seconds) not in (int, float) or not math.isfinite(max_seconds)
            or not 0 < max_seconds <= 10):
        raise ValueError('max_seconds must be positive and at most 10 seconds')
    up = RANKS.index(dealer_up)
    excluded = 8 if up == ACE else ACE if up == 8 else None
    started = perf_counter()
    state_counts = dict(draw=0, dealer=0, settle=0, play=0)
    mass_error = 0.0

    def tick(kind):
        _enumeration_state('ace_resplit_' + kind)
        states = sum(state_counts.values())
        elapsed = perf_counter() - started
        if states >= max_states:
            raise ReferenceLimitExceeded('state limit exceeded', states + 1, elapsed)
        if elapsed > max_seconds:
            raise ReferenceLimitExceeded('time limit exceeded', states, elapsed)
        state_counts[kind] += 1

    def mass(probabilities):
        nonlocal mass_error
        error = abs(math.fsum(probabilities) - 1.0)
        mass_error = max(mass_error, error)
        if error > 1e-12:
            raise ArithmeticError('probability mass is not conserved')

    def holes(unseen):
        eligible = sum(count for rank, count in enumerate(unseen) if rank != excluded)
        if not eligible:
            raise UnsupportedShoeError('completed peek has no possible hidden hole')
        rows = tuple((rank, count / eligible) for rank, count in enumerate(unseen)
                     if count and rank != excluded)
        mass(probability for _, probability in rows)
        return rows

    @cache
    def draw(unseen):
        tick('draw')
        remaining = sum(unseen) - 1
        if remaining <= 0:
            raise UnsupportedShoeError('mandatory ace draw would consume the hidden hole')
        belief = holes(unseen)
        rows = []
        for rank, count in enumerate(unseen):
            if count:
                probability = math.fsum(
                    weight * (count - (hole == rank)) / remaining
                    for hole, weight in belief)
                if probability > 0:
                    rows.append((rank, probability, _take(unseen, rank)))
        mass(probability for _, probability, _ in rows)
        return tuple(rows)

    @cache
    def dealer(cards, remaining):
        tick('dealer')
        total, soft = _total(cards)
        if total > 21:
            return ((0, 1.0),)
        if total > 17 or (total == 17 and (stand_soft_17 or not soft)):
            return ((total, 1.0),)
        size = sum(remaining)
        if not size:
            raise UnsupportedShoeError(f'dealer must draw at {total} with an empty shoe')
        outcomes = {}
        for rank, count in enumerate(remaining):
            if count:
                for outcome, probability in dealer(cards + (rank,), _take(remaining, rank)):
                    outcomes.setdefault(outcome, []).append(count / size * probability)
        rows = tuple((outcome, math.fsum(parts)) for outcome, parts in outcomes.items())
        mass(probability for _, probability in rows)
        return rows

    @cache
    def settle(unseen, completed):
        tick('settle')
        values = []
        for hole, probability in holes(unseen):
            for outcome, weight in dealer((up, hole), _take(unseen, hole)):
                reward = sum(wager if outcome == 0 or total > outcome else
                             -wager if total < outcome else 0
                             for total, wager in completed)
                values.append(probability * weight * reward)
        return math.fsum(values)

    def finish(unseen, cards, pending, completed, slot):
        completed = completed + ((_total(cards)[0], 1),)
        if pending:
            return play(unseen, (pending[0],), pending[1:], completed, slot)
        return settle(unseen, completed)

    @cache
    def play(unseen, cards, pending, completed, slot):
        tick('play')
        if len(completed) + 1 + len(pending) > 3:
            raise ArithmeticError('shared ace resplit slot exceeded three hands')
        if len(cards) == 1:
            return math.fsum(probability * play(sub, cards + (rank,), pending, completed, slot)
                             for rank, probability, sub in draw(unseen))
        if len(cards) != 2 or cards[0] != ACE:
            raise ArithmeticError('split ace must have exactly one additional card')
        if cards[1] != ACE or slot == 0:
            return finish(unseen, cards, pending, completed, slot)
        # Both alternatives finish before the visible-history maximum. Stand
        # retains the shared slot; resplit spends it and puts the new sibling
        # ahead of older pending seeds. Neither alternative reveals the hole.
        stand = finish(unseen, cards, pending, completed, slot)
        resplit = play(unseen, (ACE,), (ACE,) + pending, completed, 0)
        return max(stand, resplit)

    holes(counts)
    value = play(counts, (ACE,), (ACE,), (), 1)
    states = sum(state_counts.values())
    elapsed = perf_counter() - started
    if elapsed > max_seconds:
        raise ReferenceLimitExceeded('time limit exceeded', states, elapsed)
    hits = sum(function.cache_info().hits for function in (draw, dealer, settle, play))
    return AceResplitResult(value, states, elapsed, hits, mass_error, tuple(state_counts.items()))
