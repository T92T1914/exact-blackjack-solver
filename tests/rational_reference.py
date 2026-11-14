"""Exact rational values for the published cells and the bounded example requests.

This module is test only and imports nothing from `bj`. It restates three
models with `fractions.Fraction`, so every probability and every value is an
exact ratio of integers:

1. One post peek hand with stand, hit and double, as `bj.ev` values it,
   including its last card convention on small shoes.
2. The common shoe split families: two hands with no resplit, up to three
   non ace hands with one shared resplit, and split aces with one shared
   resplit. One recursion covers all three.
3. One original hand with the dealer's second card dealt after the player
   finishes and a dealer natural taking every committed wager.

Counts are in production rank order A, 2 to 9, T and exclude the visible
cards. In the post peek models they hold the hidden hole. Any continuation the
model admits that needs an unavailable card raises `Refused`, as the floating
point engine refuses it.
"""
from __future__ import annotations

from fractions import Fraction
from functools import lru_cache

RANKS = ('A', '2', '3', '4', '5', '6', '7', '8', '9', 'T')
LOW = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
ACE, TEN = 0, 9
ZERO = Fraction(0)


class Refused(ValueError):
    """An admitted continuation needs a card the counts cannot supply."""


def _add(total, soft, rank):
    """Add one card to a best total, keeping at most one ace counted high."""
    if rank == ACE:
        if soft:
            total += 1
            return (total, True) if total <= 21 else (total - 10, False)
        return (total + 11, True) if total + 11 <= 21 else (total + 1, False)
    total += LOW[rank]
    if total > 21 and soft:
        return total - 10, False
    return total, soft


def _hand(cards):
    total, soft = 0, False
    for rank in cards:
        total, soft = _add(total, soft, rank)
    return total, soft


def _take(counts, rank):
    return counts[:rank] + (counts[rank] - 1,) + counts[rank + 1:]


def _excluded(up):
    return TEN if up == ACE else ACE if up == TEN else None


def _settlement(total, wager, outcome):
    """One hand's result against a dealer outcome: 17 to 21, 'bust' or 'natural'."""
    if total > 21 or outcome == 'natural':
        return -wager
    if outcome == 'bust':
        return wager
    return wager * ((total > outcome) - (total < outcome))


class _Dealer:
    """Dealer outcome distributions as exact fractions, memoized per instance."""

    def __init__(self, stand_soft_17):
        self.stand_soft_17 = stand_soft_17
        self.resolve = lru_cache(maxsize=None)(self._resolve)

    def _resolve(self, total, soft, counts):
        if total > 21:
            return {'bust': Fraction(1)}
        if total > 17 or (total == 17 and (self.stand_soft_17 or not soft)):
            return {total: Fraction(1)}
        size = sum(counts)
        if not size:
            raise Refused(f'the dealer must draw at {total} from an empty shoe')
        outcomes = {}
        for rank, count in enumerate(counts):
            if count:
                for outcome, p in self.resolve(*_add(total, soft, rank),
                                               _take(counts, rank)).items():
                    outcomes[outcome] = outcomes.get(outcome, ZERO) + Fraction(count, size) * p
        return outcomes

    def after_peek(self, up, counts):
        """The hole is one of the counts, never the rank the peek ruled out."""
        excluded = _excluded(up)
        eligible = sum(c for rank, c in enumerate(counts) if rank != excluded)
        if not eligible:
            raise Refused('the completed peek leaves no possible hole')
        outcomes = {}
        for hole, count in enumerate(counts):
            if count and hole != excluded:
                start = _add(*_add(0, False, up), hole)
                for outcome, p in self.resolve(*start, _take(counts, hole)).items():
                    outcomes[outcome] = (outcomes.get(outcome, ZERO)
                                         + Fraction(count, eligible) * p)
        return outcomes

    def unpeeked(self, up, counts):
        """The second dealer card comes from the counts, and a natural can occur."""
        size = sum(counts)
        if not size:
            raise Refused('the dealer has no second card')
        natural = _excluded(up)
        outcomes = {}
        for hole, count in enumerate(counts):
            if not count:
                continue
            if hole == natural:
                outcomes['natural'] = outcomes.get('natural', ZERO) + Fraction(count, size)
                continue
            start = _add(*_add(0, False, up), hole)
            for outcome, p in self.resolve(*start, _take(counts, hole)).items():
                outcomes[outcome] = outcomes.get(outcome, ZERO) + Fraction(count, size) * p
        return outcomes


def _player_draws(up, counts):
    """Exact chance of each rank as the player's next card, after the peek."""
    excluded = _excluded(up)
    size = sum(counts)
    eligible = size - (counts[excluded] if excluded is not None else 0)
    if size < 2:
        raise Refused('the only unseen card is the hidden hole')
    if eligible <= 0:
        raise Refused('the completed peek leaves no possible hole')
    rows = []
    for rank, count in enumerate(counts):
        held_back = ZERO if rank == excluded else Fraction(count, eligible)
        p = (count - held_back) / (size - 1)
        if p > 0:
            rows.append((rank, p, _take(counts, rank)))
    return rows


class PostPeekHand:
    """Stand, hit and double for one original hand, as `bj.ev` defines them."""

    def __init__(self, up, stand_soft_17=True):
        self.up = up
        self.dealer = _Dealer(stand_soft_17)
        self.distribution = lru_cache(maxsize=None)(
            lambda counts: self.dealer.after_peek(self.up, counts))
        self.hit = lru_cache(maxsize=None)(self._hit)

    def stand(self, total, counts):
        if total > 21:
            return Fraction(-1)
        return sum((p * _settlement(total, 1, outcome)
                    for outcome, p in self.distribution(counts).items()), ZERO)

    def _hit(self, total, soft, counts):
        value = ZERO
        last = sum(counts) == 2
        for rank, p, rest in _player_draws(self.up, counts):
            new_total, new_soft = _add(total, soft, rank)
            if new_total > 21:
                value -= p
                continue
            stand = self.stand(new_total, rest)
            if new_total == 21 or last:
                # After the last drawable card only standing remains.
                value += p * stand
            else:
                value += p * max(stand, self.hit(new_total, new_soft, rest))
        return value

    def double(self, total, soft, counts):
        value = ZERO
        for rank, p, rest in _player_draws(self.up, counts):
            value += p * self.stand(_add(total, soft, rank)[0], rest)
        return 2 * value

    def values(self, cards, counts, *, can_double=True):
        """Stand, hit and double for a two card hand below 21, as offered."""
        total, soft = _hand(cards)
        values = {'S': self.stand(total, counts)}
        if sum(counts) >= 2:
            values['H'] = self.hit(total, soft, counts)
            if can_double:
                values['D'] = self.double(total, soft, counts)
        return values


def common_shoe_split(pair, up, counts, *, double_after_split, stand_soft_17,
                      extra_slots):
    """Exact split value for the common shoe families, in original wager units.

    The first hand finishes before the next takes its second card, and a new
    child goes ahead of older pending hands. All hands settle against one
    dealer, and every choice is made on the combined value of the round.
    `extra_slots` is 0 for two hands and 1 for one shared resplit. Split aces
    take one card and may resplit only on another ace while a slot remains.
    """
    dealer = _Dealer(stand_soft_17)
    excluded = _excluded(up)

    @lru_cache(maxsize=None)
    def settle(unseen, completed):
        if all(total > 21 for total, _ in completed):
            return -sum(wager for _, wager in completed)
        return sum((p * sum(_settlement(total, wager, outcome) for total, wager in completed)
                    for outcome, p in dealer.after_peek(up, unseen).items()), ZERO)

    def finish(unseen, cards, pending, completed, slot, wager=1):
        completed = tuple(sorted(completed + ((_hand(cards)[0], wager),)))
        if pending:
            return play(unseen, (pending[0],), pending[1:], completed, slot)
        return settle(unseen, completed)

    @lru_cache(maxsize=None)
    def play(unseen, cards, pending, completed, slot):
        if len(cards) == 1:
            return sum((p * play(rest, cards + (rank,), pending, completed, slot)
                        for rank, p, rest in _player_draws(up, unseen)), ZERO)
        can_resplit = slot and len(cards) == 2 and cards[1] == cards[0]

        def resplit():
            # The new sibling goes ahead of older pending hands and spends the slot.
            return play(unseen, (cards[0],), (cards[1],) + pending, completed, slot - 1)

        if pair == ACE:
            stand = finish(unseen, cards, pending, completed, slot)
            return max(stand, resplit()) if can_resplit else stand
        total, _ = _hand(cards)
        if total >= 21:
            return finish(unseen, cards, pending, completed, slot)
        options = [finish(unseen, cards, pending, completed, slot)]
        options.append(sum((p * play(rest, cards + (rank,), pending, completed, slot)
                            for rank, p, rest in _player_draws(up, unseen)), ZERO))
        if double_after_split and len(cards) == 2:
            options.append(sum((p * finish(rest, cards + (rank,), pending, completed, slot, 2)
                                for rank, p, rest in _player_draws(up, unseen)), ZERO))
        if can_resplit:
            options.append(resplit())
        return max(options)

    if excluded is not None and sum(counts) == counts[excluded]:
        raise Refused('the completed peek leaves no possible hole')
    return play(tuple(counts), (pair,), (pair,), (), extra_slots)


def deferred_second_card(cards, up, counts, *, stand_soft_17, can_double=True):
    """Stand, hit and double when the dealer's second card comes after the player.

    Player draws are uniform over the counts. The player stands once a draw
    would leave the dealer no card. A dealer natural takes every wager unit.
    """
    dealer = _Dealer(stand_soft_17)
    distribution = lru_cache(maxsize=None)(lambda rest: dealer.unpeeked(up, rest))

    def stand(total, rest, wager):
        if total > 21:
            return Fraction(-wager)
        return sum((p * _settlement(total, wager, outcome)
                    for outcome, p in distribution(rest).items()), ZERO)

    @lru_cache(maxsize=None)
    def player(total, soft, rest):
        if total > 21:
            return Fraction(-1)
        standing = stand(total, rest, 1)
        if total == 21 or sum(rest) < 2:
            return standing
        return max(standing, hit(total, soft, rest))

    @lru_cache(maxsize=None)
    def hit(total, soft, rest):
        size = sum(rest)
        return sum((Fraction(count, size) * player(*_add(total, soft, rank), _take(rest, rank))
                    for rank, count in enumerate(rest) if count), ZERO)

    def double(total, soft, rest):
        size = sum(rest)
        return sum((Fraction(count, size)
                    * stand(_add(total, soft, rank)[0], _take(rest, rank), 2)
                    for rank, count in enumerate(rest) if count), ZERO)

    total, soft = _hand(cards)
    counts = tuple(counts)
    values = {'S': stand(total, counts, 1)}
    if sum(counts) >= 2:
        values['H'] = hit(total, soft, counts)
        if can_double:
            values['D'] = double(total, soft, counts)
    return values
