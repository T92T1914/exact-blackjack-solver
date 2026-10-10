"""Bounded numerical reference for two sequential hands sharing one shoe.

This module is independent of the production hand, dealer and Bellman arithmetic.
The input counts exclude both visible pair cards and the dealer upcard, but
include the reserved hidden hole. The completed peek excludes a natural hole.
Each decision averages over that hidden information before taking a maximum.
The objective is the combined settlement, including the completed first hand.

There are exactly two hands, no resplits and no surrender. Split aces receive
one card each. Other hands can stand, hit or double on two cards when DAS is on.
A total of 21 ends play, as in the production hit continuation. Doubling takes
one card and stands. Split 21 pays one unit, never the natural premium.

All possible draws are enumerated in floating point. This is not symbolic
arithmetic, an arbitrary shoe performance guarantee or the production default.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from functools import cache
from time import perf_counter
from ._enumeration import state as _enumeration_state

RANKS = ('2', '3', '4', '5', '6', '7', '8', '9', 'T', 'A')
VALUES = (2, 3, 4, 5, 6, 7, 8, 9, 10, 1)


class ReferenceLimitExceeded(RuntimeError):
    """The reference did not finish within its declared work or time limit."""

    def __init__(self, reason, states, elapsed_seconds):
        super().__init__(reason)
        self.states = states
        self.elapsed_seconds = elapsed_seconds


class UnsupportedShoeError(ValueError):
    """An admitted continuation requires a card unavailable in the supplied shoe."""


@dataclass(frozen=True)
class ReferenceResult:
    value: float
    states: int
    elapsed_seconds: float
    cache_hits: int
    maximum_probability_mass_error: float
    state_counts: tuple[tuple[str, int], ...]


def _total(cards):
    low = sum(VALUES[i] for i in cards)
    soft = 9 in cards and low + 10 <= 21
    return low + (10 if soft else 0), soft


def _take(counts, index):
    return tuple(c - (i == index) for i, c in enumerate(counts))


def joint_split_value(pair_rank, dealer_up, shoe, *, double_after_split=True,
                      stand_soft_17=True, max_states=100_000, max_seconds=10.0):
    """Return the optimal combined split value in original bet units.

    Only canonical ranks and at most twenty unseen cards are accepted. This
    explicit small model refuses unsupported exhaustion even in an action
    that would not ultimately be chosen. It never drops a branch or replaces
    failure with a losing value. Inputs are copied and all caches are local.
    """
    if pair_rank not in RANKS or dealer_up not in RANKS:
        raise ValueError('use canonical ranks 2 through 9, T or A')
    counts = tuple(shoe)
    if len(counts) != 10 or any(type(c) is not int or c < 0 for c in counts):
        raise ValueError('shoe must contain ten nonnegative integer counts')
    if not 3 <= sum(counts) <= 20:
        raise ValueError('reference requires 3 to 20 unseen cards including the hole')
    if type(double_after_split) is not bool or type(stand_soft_17) is not bool:
        raise ValueError('DAS and S17 flags must be boolean')
    if type(max_states) is not int or max_states < 1:
        raise ValueError('max_states must be a positive integer')
    if (type(max_seconds) not in (int, float) or not math.isfinite(max_seconds)
            or max_seconds <= 0):
        raise ValueError('max_seconds must be positive and finite')
    pair, up = RANKS.index(pair_rank), RANKS.index(dealer_up)
    excluded = 8 if up == 9 else 9 if up == 8 else None
    started = perf_counter()
    counts_by_kind = dict(draw=0, dealer=0, settle=0, play=0)
    mass_error = 0.0

    def tick(kind):
        _enumeration_state('joint_' + kind)
        counts_by_kind[kind] += 1
        states = sum(counts_by_kind.values())
        elapsed = perf_counter() - started
        if states > max_states:
            raise ReferenceLimitExceeded('state limit exceeded', states, elapsed)
        if elapsed > max_seconds:
            raise ReferenceLimitExceeded('time limit exceeded', states, elapsed)

    def mass(probabilities):
        nonlocal mass_error
        error = abs(math.fsum(probabilities) - 1.0)
        mass_error = max(error, mass_error)
        if error > 1e-12:
            raise ArithmeticError('probability mass is not conserved')

    def holes(unseen):
        eligible = sum(c for i, c in enumerate(unseen) if i != excluded)
        if not eligible:
            raise UnsupportedShoeError('completed peek has no possible hidden hole')
        rows = tuple((i, c / eligible) for i, c in enumerate(unseen)
                     if c and i != excluded)
        mass(p for _, p in rows)
        return rows

    @cache
    def draw(unseen):
        tick('draw')
        remaining = sum(unseen) - 1
        if remaining <= 0:
            raise UnsupportedShoeError('player draw would consume the hidden hole')
        # Explicitly marginalize each physical hole before observing a player card.
        belief = holes(unseen)
        rows = []
        for rank, count in enumerate(unseen):
            if not count:
                continue
            probability = math.fsum(p * (count - (hole == rank)) / remaining
                                    for hole, p in belief)
            if probability > 0:
                rows.append((rank, probability, _take(unseen, rank)))
        mass(p for _, p, _ in rows)
        return tuple(rows)

    @cache
    def dealer(cards, remaining):
        tick('dealer')
        total, soft = _total(cards)
        if total > 21:
            return ((0, 1.0),)
        if total > 17 or (total == 17 and (stand_soft_17 or not soft)):
            return ((total, 1.0),)
        n = sum(remaining)
        if n == 0:
            raise UnsupportedShoeError(f'dealer must draw at {total} with an empty shoe')
        outcomes = {}
        for rank, count in enumerate(remaining):
            if count:
                for outcome, probability in dealer(cards + (rank,), _take(remaining, rank)):
                    outcomes.setdefault(outcome, []).append(count / n * probability)
        rows = tuple((outcome, math.fsum(parts)) for outcome, parts in outcomes.items())
        mass(p for _, p in rows)
        return rows

    @cache
    def settle(unseen, first, second):
        tick('settle')
        completed = (first, second)
        if all(total > 21 for total, _ in completed):
            return -float(sum(wager for _, wager in completed))
        values = []
        for hole, probability in holes(unseen):
            for outcome, p in dealer((up, hole), _take(unseen, hole)):
                reward = sum(-wager if total > 21 else
                             wager if outcome == 0 or total > outcome else
                             -wager if total < outcome else 0
                             for total, wager in completed)
                values.append(probability * p * reward)
        return math.fsum(values)

    def finish(unseen, cards, first, wager=1):
        total, _ = _total(cards)
        completed = (total, wager)
        if first is None:
            return play(unseen, (pair,), completed)
        return settle(unseen, first, completed)

    @cache
    def play(unseen, cards, first):
        tick('play')
        total, _ = _total(cards)
        if len(cards) == 1:
            return math.fsum(p * play(sub, cards + (rank,), first)
                             for rank, p, sub in draw(unseen))
        if total >= 21 or pair == 9:
            return finish(unseen, cards, first)
        # Each action is a combined round EV under the same observable state.
        # In particular this maximum is never inside a hidden hole loop.
        options = [finish(unseen, cards, first)]
        options.append(math.fsum(p * play(sub, cards + (rank,), first)
                                 for rank, p, sub in draw(unseen)))
        if double_after_split and len(cards) == 2:
            options.append(math.fsum(p * finish(sub, cards + (rank,), first, 2)
                                     for rank, p, sub in draw(unseen)))
        return max(options)

    holes(counts)
    value = play(counts, (pair,), None)
    states = sum(counts_by_kind.values())
    hits = sum(fn.cache_info().hits for fn in (draw, dealer, settle, play))
    state_counts = tuple(counts_by_kind.items())
    elapsed = perf_counter() - started
    if elapsed > max_seconds:
        raise ReferenceLimitExceeded('time limit exceeded', states, elapsed)
    return ReferenceResult(value, states, elapsed, hits, mass_error, state_counts)
