"""Bounded joint continuation for two or three sequential non-ace split hands.

Counts exclude visible cards once and include the concealed negative-peek hole.
One extra slot is shared by the whole round. New children precede older pending
hands. Every choice maximizes combined settlement after hidden-world averaging.
All offered branches must complete, including ultimately unchosen resplits.
Enumeration uses binary floats, with local caches and explicit state/time limits.
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


@dataclass(frozen=True)
class ResplitResult:
    value: float
    states: int
    elapsed_seconds: float
    cache_hits: int
    maximum_probability_mass_error: float
    state_counts: tuple[tuple[str, int], ...]


def _total(cards):
    low = sum(VALUES[index] for index in cards)
    soft = 9 in cards and low + 10 <= 21
    return low + (10 if soft else 0), soft


def _take(counts, index):
    return tuple(count - (rank == index) for rank, count in enumerate(counts))


def joint_resplit_value(pair_rank, dealer_up, shoe, *, double_after_split=True,
                        stand_soft_17=True, max_states=100_000, max_seconds=10.0):
    """Value the forced initial split with at most one later extra split.

    Require an original non-ace pair and 3..20 explicit retained unseen cards.
    Exhaustion in any admitted continuation refuses the whole calculation.
    No ordinary-root last-draw convention is introduced into this joint model.
    """
    if type(pair_rank) is not str or pair_rank not in RANKS[:-1]:
        raise ValueError('pair must be a canonical non-ace rank 2 through 9 or T')
    if type(dealer_up) is not str or dealer_up not in RANKS:
        raise ValueError('dealer upcard must be a canonical rank')
    counts = tuple(shoe)
    if len(counts) != 10 or any(type(count) is not int or count < 0 for count in counts):
        raise ValueError('shoe must contain ten nonnegative integer counts')
    if not 3 <= sum(counts) <= 20:
        raise ValueError('joint resplit requires 3 to 20 unseen cards including the hole')
    if type(double_after_split) is not bool or type(stand_soft_17) is not bool:
        raise ValueError('DAS and S17 flags must be boolean')
    state_limit(max_states)
    if (type(max_seconds) not in (int, float) or not math.isfinite(max_seconds)
            or max_seconds <= 0):
        raise ValueError('max_seconds must be positive and finite')
    pair, up = RANKS.index(pair_rank), RANKS.index(dealer_up)
    excluded = 8 if up == 9 else 9 if up == 8 else None
    started = perf_counter()
    state_counts = dict(draw=0, dealer=0, settle=0, play=0)
    mass_error = 0.0

    def tick(kind):
        _enumeration_state('resplit_' + kind)
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
            raise UnsupportedShoeError('player draw would consume the hidden hole')
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
        if all(total > 21 for total, _ in completed):
            return -float(sum(wager for _, wager in completed))
        values = []
        for hole, probability in holes(unseen):
            for outcome, weight in dealer((up, hole), _take(unseen, hole)):
                reward = sum(-wager if total > 21 else
                             wager if outcome == 0 or total > outcome else
                             -wager if total < outcome else 0
                             for total, wager in completed)
                values.append(probability * weight * reward)
        return math.fsum(values)

    def finish(unseen, cards, pending, completed, slot, wager=1):
        completed = completed + ((_total(cards)[0], wager),)
        if pending:
            return play(unseen, (pending[0],), pending[1:], completed, slot)
        return settle(unseen, completed)

    @cache
    def play(unseen, cards, pending, completed, slot):
        tick('play')
        total, _ = _total(cards)
        if len(cards) == 1:
            return math.fsum(probability * play(sub, cards + (rank,), pending, completed, slot)
                             for rank, probability, sub in draw(unseen))
        if total >= 21:
            return finish(unseen, cards, pending, completed, slot)
        # Complete every combined alternative before choosing. No player
        # maximum occurs inside a hole loop or discards an exhausted branch.
        options = [finish(unseen, cards, pending, completed, slot)]
        options.append(math.fsum(
            probability * play(sub, cards + (rank,), pending, completed, slot)
            for rank, probability, sub in draw(unseen)))
        if double_after_split and len(cards) == 2:
            options.append(math.fsum(
                probability * finish(sub, cards + (rank,), pending, completed, slot, 2)
                for rank, probability, sub in draw(unseen)))
        if slot == 1 and len(cards) == 2 and cards[0] == cards[1]:
            options.append(play(unseen, (cards[0],), (cards[1],) + pending, completed, 0))
        return max(options)

    holes(counts)
    value = play(counts, (pair,), (pair,), (), 1)
    states = sum(state_counts.values())
    elapsed = perf_counter() - started
    if elapsed > max_seconds:
        raise ReferenceLimitExceeded('time limit exceeded', states, elapsed)
    hits = sum(function.cache_info().hits for function in (draw, dealer, settle, play))
    return ResplitResult(value, states, elapsed, hits, mass_error, tuple(state_counts.items()))
