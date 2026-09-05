"""Exact, shoe-composition-aware dealer outcome solver.

Everything downstream (the EV solver, and through it every recommendation the
tool ever makes) rests on this module, so it is exact combinatorics rather than
simulation.  A Monte Carlo dealer would have been ~20 lines shorter and would
have introduced a sampling error of order 1/sqrt(N) into every EV comparison we
make.  Several of the decisions this tool has to get right are separated by less
than 0.001 units (12 vs 4 is decided by a margin of 0.00075, pinned in
tests/test_ev.py).  You cannot resolve a 0.00075 margin with a simulated dealer without
burning millions of trials per query, and the recursion below answers in
microseconds once warm.  So: enumeration, not sampling.

WHAT "EXACT" MEANS HERE
-----------------------
We draw *without replacement* from the actual remaining shoe.  The alternative,
used by most published charts and by every "infinite deck" approximation, is to
treat each draw as independent with fixed probabilities 1/13 (4/13 for tens).
That is wrong by a few tenths of a percent per cell, and it is wrong in a
direction that changes answers: removing the player's own cards from the shoe is
exactly the effect that makes a multi-card 16 vs 10 a stand.  Since we are going
to claim composition-dependent accuracy downstream, the dealer has to honour it.

WHAT THIS MODULE DELIBERATELY DOES NOT MODEL
--------------------------------------------
The dealer never makes a decision.  There is no strategy here, only the fixed
house drawing rule: hit below 17, stand at hard 17 and above, and hit or stand
soft 17 according to rules.s17.  The original table is S17 (its rules panel,
confirmed in play), but H17 is implemented because the rule flags are meant to
be live, not decorative: a different table is a config change here.

PEEK CONDITIONING
-----------------
The original table peeks: a dealer natural resolves the hand before the player
acts (observed directly - a Jack up produced an instant loss with no insurance
prompt).  That means that by the time the player is choosing
an action, the hole card is *known not to* complete a natural.  With
peek_resolved=True we drop that one hole-card rank from the enumeration and
renormalise over the rest, which is Bayes' rule for conditioning on
"not a natural".  Index 6 is then exactly 0.0, because the branch cannot happen.

The alternative implementation - compute the full distribution and divide the
non-natural mass by (1 - P(natural)) - is algebraically identical.  Dropping the
rank is preferred because it makes the impossible branch unreachable instead of
merely small, so a future bug cannot leak natural probability into a
post-peek number.

APPROXIMATIONS
--------------
1.  None in the combinatorics.  Given a shoe, the returned vector is the exact
    rational probability of each dealer outcome, computed in float64.  The only
    error is floating-point rounding, which accumulates to roughly 1e-15 over
    the deepest recursion; the row-sum test in tests/test_dealer.py pins it.
2.  Suits are not modelled and ten-value ranks are collapsed to 'T' (see
    core.py).  This is not an approximation for probability purposes - the four
    ten-value ranks are mathematically interchangeable - but it does mean this
    module cannot support a "seventh copy of one specific card" shoe-
    persistence check, which would need its own suit-aware tracker.
3.  The published Wizard of Odds table this module is checked against
    (transcribed in tests/test_dealer.py) is itself computed under conventions we cannot
    inspect - most such tables burn only the upcard, as our test does, but some
    average over player compositions.  Agreement is therefore expected to a few
    ten-thousandths, not to machine precision.  Where the computed number and
    the published number disagree, the test reports the gap; the code is never
    tuned to close it.  See the test module for the measured residuals.
4.  Callers pass a shoe with the player's cards and the upcard already removed.
    This module does not verify that claim - it cannot, since it does not know
    what the player holds.  Garbage in, garbage out.
"""
from __future__ import annotations

from functools import lru_cache

from .core import (
    STANDARD,
    RANK_INDEX,
    RANKS,
    RANK_VALUE,
    Rules,
    Shoe,
    normalize,
    remove_card,
    shoe_size,
)

#: Index order of the returned probability vector.  'BUST' and 'BJ' are strings
#: rather than sentinel ints so that a caller who prints OUTCOMES gets something
#: readable, and so that no arithmetic accidentally treats them as totals.
OUTCOMES: tuple[object, ...] = (17, 18, 19, 20, 21, 'BUST', 'BJ')

#: Index constants, so downstream code never hard-codes a magic 5.
I17, I18, I19, I20, I21, IBUST, IBJ = range(7)

_ACE = RANK_INDEX['A']
_TEN = RANK_INDEX['T']

_BUST_VECTOR = (0.0, 0.0, 0.0, 0.0, 0.0, 1.0)


def _stand_vector(total: int) -> tuple[float, ...]:
    """Point mass on a final standing total of 17..21."""
    v = [0.0] * 6
    v[total - 17] = 1.0
    return tuple(v)


# The memo key is (total, soft, shoe, s17).  That is a *complete* description of
# the remaining problem: the dealer has no memory beyond his current total and
# softness, and the shoe tuple is immutable and fully determines the
# distribution of every future draw.  Two different card orders that leave the
# same total and the same shoe are the same subproblem, and there are a great
# many of them (2,3 and 3,2 collapse immediately), which is where the speed
# comes from.  lru_cache is safe precisely because Shoe is a tuple of ints:
# nothing a caller can do will mutate a key out from under the cache.  s17 is in
# the key rather than closed over so that S17 and H17 results can coexist
# without one poisoning the other.
@lru_cache(maxsize=None)
def _resolve(total: int, soft: bool, shoe: Shoe, s17: bool) -> tuple[float, ...]:
    """Probabilities of (17, 18, 19, 20, 21, BUST) from a dealer hand in progress.

    Six entries, not seven: a natural is decided by the first two cards and is
    handled by the caller, so it can never arise inside the draw loop.
    """
    if total > 21:
        return _BUST_VECTOR
    if total >= 18:
        return _stand_vector(total)
    if total == 17 and (s17 or not soft):
        return _stand_vector(total)

    # Dealer must draw.
    n = shoe_size(shoe)
    if n == 0:
        # Cannot happen at a real table (a 312-card shoe against a dealer who
        # draws at most a dozen cards), but a caller can hand us a toy shoe.
        # Raising beats inventing an outcome: there is no defensible answer for
        # "the dealer must hit and there are no cards".
        raise ValueError(
            f'dealer must draw to {total} but the shoe is empty'
        )

    acc = [0.0] * 6
    for i, count in enumerate(shoe):
        if count == 0:
            continue
        p = count / n
        if i == _ACE:
            if soft:
                # Only one ace can ever be counted as 11 (two would be 22), so a
                # second ace is forced to 1 and the hand stays soft.
                nt, ns = total + 1, True
            else:
                nt, ns = total + 11, True
                if nt > 21:
                    nt, ns = total + 1, False
        else:
            nt, ns = total + RANK_VALUE[RANKS[i]], soft
            if nt > 21 and ns:
                # Demote the one soft ace.  After this the hand is hard, because
                # there was only ever one ace being counted high.
                nt, ns = nt - 10, False

        sub = _resolve(nt, ns, remove_card(shoe, i), s17)
        for k in range(6):
            acc[k] += p * sub[k]
    return tuple(acc)


@lru_cache(maxsize=None)
def _distribution(up: str, shoe: Shoe, s17: bool, peek_resolved: bool) -> tuple[float, ...]:
    """Cached core of dealer_distribution.

    Keyed on s17 alone rather than on the whole Rules object: s17 is the only
    field that touches the dealer's drawing rule, and keying on the dataclass
    would split the cache every time an unrelated flag (das, max_hands, payout)
    differed, for identical arithmetic.

    bj.ev imports this directly, bypassing the public wrapper's per-call
    normalisation inside a loop that runs tens of millions of times.  Treat the
    signature as stable for that reason.
    """
    n = shoe_size(shoe)
    if n == 0:
        raise ValueError('empty shoe: the dealer has no hole card to draw')

    # A dealer natural needs an ace and a ten, so only these two upcards can
    # produce one, and for each there is exactly one hole-card rank that does it.
    if up == 'A':
        natural_hole = _TEN
    elif up == 'T':
        natural_hole = _ACE
    else:
        natural_hole = None

    denom = n
    if peek_resolved and natural_hole is not None:
        denom = n - shoe[natural_hole]
        if denom <= 0:
            # Every remaining card would complete a natural, so "the dealer
            # peeked and did not have one" is an event of probability zero.
            # There is nothing to condition on.
            raise ValueError(
                f'after the peek there is no possible hole card for upcard {up}'
            )

    up_value = RANK_VALUE[up]
    acc = [0.0] * 7
    for i, count in enumerate(shoe):
        if count == 0:
            continue
        if i == natural_hole:
            if peek_resolved:
                continue  # conditioned away; renormalisation is via `denom`
            acc[IBJ] += count / n
            continue

        p = count / denom
        # Two-card total.  Only the upcard or the hole card can be an ace here,
        # and A,A is the sole double-ace case, so the demotion is a single step.
        hole_value = RANK_VALUE[RANKS[i]]
        total = up_value + hole_value
        soft = (up == 'A') or (i == _ACE)
        if total > 21:  # only A,A = 22
            total -= 10

        sub = _resolve(total, soft, remove_card(shoe, i), s17)
        for k in range(6):
            acc[k] += p * sub[k]
    return tuple(acc)


def dealer_distribution(up, shoe: Shoe, rules: Rules = STANDARD, *,
                        peek_resolved: bool = True) -> tuple[float, ...]:
    """Exact distribution of the dealer's final hand, indexed by OUTCOMES.

    Args:
        up: dealer upcard rank, in any form core.normalize accepts ('K', 10, 'a').
        shoe: immutable Shoe tuple with the player's cards AND the dealer upcard
            already removed.  This module trusts the caller on that.
        rules: only rules.s17 is consulted; the dealer has no other choices.
        peek_resolved: True models the original table as played - the dealer has already
            peeked and does not have a natural, so the distribution is
            conditioned on that and index 6 (BJ) is exactly 0.0.  False returns
            the unconditional distribution with the natural at index 6, which is
            what you want for insurance arithmetic or for a no-hole-card game.

    Returns:
        A 7-tuple of floats summing to 1.0.
    """
    return _distribution(normalize(up), tuple(shoe), bool(rules.s17), bool(peek_resolved))


def dealer_bust_prob(up, shoe: Shoe, rules: Rules = STANDARD) -> float:
    """P(dealer busts), conditioned on the peek having already happened.

    Post-peek is the right default because it is the number that matters at the
    moment the player is deciding: the natural, if there was one, already ended
    the hand.  It is also the convention of the published per-upcard bust row
    (PUBLISHED_BUST in tests/test_dealer.py).
    """
    return dealer_distribution(up, shoe, rules, peek_resolved=True)[IBUST]


def clear_caches() -> None:
    """Drop both memo tables.

    Only useful for measuring cold-start cost or for keeping memory flat across
    a long simulation with many distinct shoes; correctness never depends on it,
    because every cache key is immutable.
    """
    _resolve.cache_clear()
    _distribution.cache_clear()
