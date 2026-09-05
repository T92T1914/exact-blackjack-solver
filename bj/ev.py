"""Exact, composition-dependent expected-value solver.

This is the module that lets the tool print a *margin* next to a
recommendation, and it is the module that GRADES the hard-coded chart in
bj.strategy instead of trusting it.  bj.strategy is a transcription of a
published table; this file is an independent derivation.  If they disagree,
the disagreement is a finding, not a bug to be papered over.

WHY EXACT ENUMERATION AND NOT SIMULATION
----------------------------------------
The alternative was a Monte Carlo player to sit alongside a Monte Carlo
dealer.  It was rejected for the same reason bj.dealer rejected it, only more
so: this module has to resolve differences of 0.0008 units (12 vs 4, the
closest decision in blackjack) and 0.0014 units (9,7 vs 10).  A simulator
needs on the order of (1.15 / 0.0008)^2 ~ 2 million hands *per cell* to see a
0.0008 edge at one standard error, and roughly a hundred times that to call it
with confidence.  There are 550 cells.  The recursion below answers every one
of them exactly, and once the memo tables are warm it answers in microseconds.

WHY DRAWING WITHOUT REPLACEMENT MATTERS HERE
--------------------------------------------
Every draw comes out of the actual remaining shoe, player cards and upcard
already removed.  This is not pedantry: it is the entire content of the
composition-dependent claims the tool makes.  A hard 16 made of 8,5,3 has
consumed three low cards, which are precisely the cards that would have
rescued a hit, and that is why standing overtakes hitting there while
two-card 10,6 still hits.  Under an infinite-deck model those two hands are
the same hand and the exception disappears.

WHAT "OPTIMAL" MEANS IN THIS FILE
----------------------------------
ev_hit plays the rest of the hand optimally: after each draw the player again
takes the better of stand and hit.  Double is deliberately NOT offered after a
hit, because no blackjack table anywhere allows it and the example table is no
exception (handoff, "Notes for the coder": Double only on exactly two cards).
That restriction makes the recursion cheaper AND correct; allowing it would
inflate every hit EV and quietly break the comparison against the published
numbers.

PEEK
----
Every number in this module is a *post-peek* number, and the peek is applied
in the order the table applies it.  the example table deals the hole card and peeks
under a ten or an ace BEFORE the player is allowed to touch a button, so "the
dealer has no natural" is information the player already holds while the draw
pile is still full.  That has two consequences, and this module implements
both:

  * the DEALER distribution is conditioned on it - bj.dealer's
    peek_resolved=True, which is what _stand_ev consults; and
  * the cards the PLAYER is about to draw are conditioned on it too.  Under an
    ace the hole card is known not to be a ten, so the tens that are left are
    likelier to still be in the pile than their raw count suggests; under a ten
    it is the aces that are enriched.  _draw_probs is the whole of that
    correction, and every draw taken anywhere in this module goes through it.

The second one is easy to miss - it was missing here until 2026-09-02 - and it
is not free: it is worth up to 5e-4 against a ten and 2.5e-3 against an ace,
which is why 11 vs A DOUBLE used to read +0.1272 against a published +0.1297.
It is exactly zero for upcards 2 to 9, where the peek rules nothing out.

The hole card is still HIDDEN.  The peek says what it is not, never what it is.
Every stand/hit/double comparison here is therefore made on a value averaged
over the surviving hole cards, never on one hole card at a time.  Taking the
maximum inside a hole-card loop is clairvoyant play, and it is not a subtle
error: it reports +0.1867 for hitting 11 vs A instead of the correct +0.1476.
tests/test_ev.py pins both numbers so that mistake cannot come back quietly.

Why the correction is arithmetic and not a second recursion: the player's own
cards say nothing about the hole card beyond removing themselves from the pile,
so his belief about it is always "one of the cards I cannot see, uniformly,
minus the rank the peek ruled out".  With `shoe` the cards the player cannot
see - the hole card is one of them - and `out` the ruled-out rank,

    P(next card is r)  =  (shoe[r] - w_r) / (n - 1),
        w_r = shoe[r] / (n - shoe[out])   for r != out,   w_out = 0.

That is _draw_probs in one line, and it agrees to 2e-16 with an explicit
belief-propagating solver written independently (out/scratch/v_beliefhit.py) on
every published marginal hand.

What the claim at the top of this section is worth, measured: all 45 stand,
hit and double cells of handoff appendix section 4 now land within 0.00005 of
the published table, which is that table's own display precision, against a
target of 0.002.  No cell is exempt and no residual is being carried.  The two
split cells that still miss are not peek residuals; they are APPROXIMATIONS 1
and 2, and tests/test_ev.py computes the cause of each rather than asserting
it.

house_edge() puts the dealer-natural branch back in explicitly, because that
branch is part of the game even though it is not part of any decision.  There
is no support for a European no-hole-card game here.  rules.peek is not
consulted by the per-hand functions at all - they always answer the peek game,
which is the only game this module models - and house_edge refuses a no-peek
ruleset rather than silently returning a number that is wrong by the ~0.11%
the handoff quotes for that rule.

APPROXIMATIONS
--------------
1.  SPLIT HANDS ARE TREATED AS INDEPENDENT.  When a pair is split, the two
    resulting hands are dealt from the same shoe in reality: the cards the
    first hand consumes are not available to the second.  Modelling that
    exactly means carrying the joint state of both hands through the whole
    recursion, which multiplies the state space by roughly the size of the
    shoe-depletion space and is what makes exact split EV a research-grade
    computation rather than a page of code.  Instead each split hand is valued
    against the shoe as it stood when the split was made, and the results are
    added.

    Direction and size of the error: the effect is second-order and slightly
    OPTIMISTIC.  It ignores the negative correlation between the two hands -
    if hand one eats the tens, hand two is less likely to find one - so it
    understates the variance clearly, and overstates the mean by a small
    amount because each hand is credited with a shoe that is a card or two
    richer than the one it will actually face.  Published comparisons of this
    "independent hands" convention against full joint enumeration put the mean
    error at well under 0.001 units on a split, i.e. under 0.0001 on the
    overall house edge, and the one clean local reading available here agrees:
    8,8 vs 10 comes out +0.00050 above the published cell once the resplit
    convention is matched.  The test suite checks the two published split
    values (8,8 vs 10 and 9,9 vs 7) to 0.01, which is 10x looser than the
    stand/hit tolerance, for this reason and for the convention difference
    tests/test_ev.py records against 9,9 vs 7.

2.  THE RESPLIT BUDGET IS A SHARED POOL; THE RESPLIT DECISION INSIDE IT IS
    GREEDY.  rules.max_hands caps the number of hands in play across the whole
    round, and that cap is one pool, not one allowance per hand.

    This module used to halve the budget at every split - max_hands=4 gave each
    child 2 - and claimed in this note that the halving "only becomes lossy for
    an odd max_hands" and "costs nothing at this table".  BOTH CLAIMS WERE
    FALSE and are withdrawn.  Halving caps the tree at the right number of
    hands but forbids a shape a real table is perfectly happy with: hand one
    resplitting twice while hand two never pairs at all.  It is lossy for every
    max_hands >= 3.  Measured here against the shared pool, on this table and
    this shoe: it understated 8,8 vs 7 by 0.0109, understated 42 of the 100
    pair cells - every cell where splitting is the play, of which 26 by more
    than 0.002, which is the tolerance this project holds a play EV to - and
    moved the house edge by 0.0059 percentage points.  It is gone.
    _split_hand_outcomes now returns a distribution over how many extra hands
    the subtree actually consumed, and the second hand is dealt whatever the
    first one leaves, in the order a real table plays them.

    What is still approximate is the DECISION, not the budget: a hand resplits
    when resplitting raises its own EV, without charging itself for the slot it
    takes away from its sibling.  That is a policy a player could actually
    follow, so the number returned is a genuine LOWER bound on the shared-pool
    optimum; giving both hands the whole pool at once, which no table would
    allow, is an upper bound.  Measured width of that bracket over all 100 pair
    cells at max_hands=4: at most 0.00084 units on a split (8,8 vs 7), and
    4.5e-06 on the house edge.  So what is left of this approximation is about
    a thirteenth of what the divided budget was costing.

3.  derive_table's HARD rows average over compositions.  A printed chart has
    one cell for "hard 16", but 16 is 10+6, 9+7 and 8+8, and this solver gives
    each of them a different number.  Grading one printed cell therefore means
    averaging each action's EV over every two-card composition of that total,
    weighted by how often the deal produces it, and then picking the winner.
    That is the honest grade of a total-dependent cell, but it does mean a
    derive_table hard cell is not the answer for any one specific hand -
    best_action is.  Soft and pair rows have exactly one two-card composition
    each and need no averaging.

4.  Card removal is modelled; card ORDER within the shoe is not, and neither
    are suits (bj.core collapses all ten-value ranks to 'T').  For probability
    this is exact, not an approximation.  It does mean this module cannot see
    a rigged deal or support the seventh-copy shoe-persistence test.

5.  initial_shoe_for() assumes a FULL fresh shoe minus the visible cards.  The
    handoff concludes the example table reshuffles every hand (~85% confidence,
    "Observed vs inferred"), so that is the right default, but it is an
    assumption inherited from that section rather than anything this module
    proves.  Pass your own depleted shoe if you ever prove otherwise.

6.  Floating point.  Everything is float64.  The deepest recursion accumulates
    on the order of 1e-15 of rounding, which is six orders of magnitude below
    the tightest margin the tool ever reports.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace as _dc_replace
from functools import lru_cache

from .core import (
    STANDARD,
    DOUBLE,
    HIT,
    RANKS,
    RANK_INDEX,
    RANK_VALUE,
    Rules,
    SPLIT,
    STAND,
    Shoe,
    fresh_shoe,
    hand_total,
    is_pair,
    normalize,
    normalize_hand,
    remove_card,
    remove_cards,
    shoe_size,
)
# _distribution is bj.dealer's private cached core.  The public wrapper
# re-normalises the upcard and re-tuples the shoe on every call, which is
# free at the UI but not inside a loop that runs tens of millions of times.
# The handoff for that module explicitly marks _distribution as stable for a
# sibling to lean on, so this is a sanctioned shortcut, not a raid.
from .dealer import IBUST, _distribution

__all__ = [
    'initial_shoe_for', 'ev_stand', 'ev_hit', 'ev_double', 'ev_split',
    'best_action', 'house_edge', 'derive_table', 'clear_caches',
]

_ACE = RANK_INDEX['A']
_TEN = RANK_INDEX['T']
#: rank values by shoe index, so the hot loop never touches a dict
_VALUES: tuple[int, ...] = tuple(RANK_VALUE[r] for r in RANKS)


# --- hand arithmetic -------------------------------------------------------

def _draw(total: int, soft: bool, i: int) -> tuple[int, bool]:
    """Add the card at shoe index `i` to a (total, soft) hand state.

    (total, soft) is a complete description of a blackjack hand for every
    purpose except the composition exceptions, which are handled one level up
    by keying on the actual cards.  Collapsing a hand to two numbers is what
    makes the memo table small enough to be useful: 8,5,3 and 5,8,3 and 3,8,5
    are one entry, not six.

    Only one ace can ever count as 11 (two would be 22), so "soft" is a bool
    rather than a count, and demotion is a single subtraction.
    """
    if i == _ACE:
        if soft:
            # The new ace is forced to 1.  If that still busts, the ace already
            # counted as 11 has to come down too: a SOFT 21 drawing an ace is a
            # HARD 12, not a 22.  Scoring it as a bust cost ev_hit 0.064 and
            # ev_double 0.128 on hands like A,4,6 - found by a verifier, not by
            # any published cell, because it moves none of them.
            t = total + 1
            return (t, True) if t <= 21 else (t - 10, False)
        t = total + 11
        if t > 21:
            return total + 1, False
        return t, True
    t = total + _VALUES[i]
    if t > 21 and soft:
        return t - 10, False
    return t, soft


def _two_card_state(i: int, j: int) -> tuple[int, bool]:
    """(total, soft) for a two-card hand of shoe indices i and j."""
    t, s = _draw(0, False, i)
    return _draw(t, s, j)


def _peek_out(up: str) -> int:
    """Shoe index of the hole card the peek ruled out, or -1 if it ruled out none.

    Only a ten and an ace can be peeked under, because only they can complete a
    natural, and for each there is exactly one rank that does it.  Against
    2 through 9 the peek happens (the dealer looks at nothing) and tells the
    player nothing, so this returns -1 and every draw below stays uniform.
    """
    if up == 'A':
        return _TEN
    if up == 'T':
        return _ACE
    return -1


@lru_cache(maxsize=None)
def _draw_probs(shoe: Shoe, up: str) -> tuple[float, ...]:
    """Probability of each rank being the player's NEXT card, post-peek.

    `shoe` is everything the player cannot see, WHICH INCLUDES THE DEALER'S HOLE
    CARD.  That is the convention every function in this module uses, and it is
    what makes this correction necessary: the player is not drawing from `shoe`,
    he is drawing from `shoe` minus one unknown card, and the peek has told him
    something about which card that is.

    Against 2 through 9 nothing was ruled out and this is just count/n.  Against
    a ten or an ace, the hole card is uniform over the ruled-in ranks - the
    player's own cards carry no other information about it - so with
    w_r = shoe[r]/(n - shoe[out]) the chance the hole card is an r,

        P(next card is r) = sum_h w_h * (shoe[r] - [h == r]) / (n - 1)
                          = (shoe[r] - w_r) / (n - 1).

    The ruled-out rank has w = 0 and so gets shoe[out]/(n-1): strictly MORE than
    its raw share, because it is the one rank that certainly is not face down.
    Everything else is scaled down to pay for that.  See the PEEK section of the
    module docstring for why this is the entire post-peek correction.
    """
    n = shoe_size(shoe)
    if n == 0:
        raise ValueError('no cards left to draw')
    out = _peek_out(up)
    if out < 0:
        # Nothing was ruled out, so there is no hole card to condition on and
        # the draw is uniform.  This is the path every upcard from 2 to 9 takes,
        # and it is a short-circuit, not an approximation: the general formula
        # below collapses to exactly this when shoe[out] is 0.
        return tuple(c / n for c in shoe)
    if n < 2:
        # One card left under a peeked upcard means that card IS the hole card.
        raise ValueError('the only card left is the dealer hole card; the player cannot draw')
    live = n - shoe[out]
    if live <= 0:
        # Every remaining card would have completed a natural, so "the dealer
        # peeked and did not have one" had probability zero.  bj.dealer refuses
        # the same shoe for the same reason.
        raise ValueError(f'after the peek there is no possible hole card for upcard {up}')
    return tuple(
        (c if i == out else c - c / live) / (n - 1)
        for i, c in enumerate(shoe)
    )


def initial_shoe_for(player_cards, dealer_up, rules: Rules = STANDARD) -> Shoe:
    """A fresh shoe with the player's cards and the dealer's upcard removed.

    This is the shoe every other function in this module expects: the cards
    that are already face up are gone from it.  Forgetting to remove them is
    the single easiest way to get a plausible-looking wrong answer, so the
    helper exists to make the correct thing the short thing.
    """
    cards = normalize_hand(player_cards)
    return remove_cards(fresh_shoe(rules.decks), cards + (normalize(dealer_up),))


# --- the three primitives --------------------------------------------------
# _stand_ev is deliberately NOT memoised.  It is five multiply-adds on top of
# bj.dealer's cached distribution, so a cache of its own would spend memory on
# 18 player totals per shoe to save arithmetic that costs less than the dict
# lookup.  The expensive part - the dealer recursion - is already cached where
# it belongs.

def _stand_ev(total: int, up: str, shoe: Shoe, s17: bool) -> float:
    """EV of standing on `total`, in units of the original bet.

    Post-peek, so the dealer cannot hold a natural and a dealer 21 in this
    vector is always a drawn 21, which a player 21 pushes against.  Naturals
    are handled by the callers that can actually see a two-card hand; by the
    time the recursion is running there is no such thing as a natural.
    """
    if total > 21:
        return -1.0
    d = _distribution(up, shoe, s17, True)
    ev = d[IBUST]
    for k in range(5):
        dealer_total = 17 + k
        if total > dealer_total:
            ev += d[k]
        elif total < dealer_total:
            ev -= d[k]
        # equal totals push and contribute nothing
    return ev


@lru_cache(maxsize=None)
def _hit_ev(total: int, soft: bool, up: str, shoe: Shoe, s17: bool) -> float:
    """EV of taking one card and then playing the rest of the hand optimally.

    "Optimally" here is max(stand, hit) at every later node - no double, which
    is the table rule, and no split, which is impossible once a third card has
    landed.  The recursion bottoms out on a bust or on a total of 21.

    Standing on 21 is treated as forced rather than compared.  That is a real
    theorem, not a shortcut: 21 is the highest total a hand can hold, drawing
    can only leave it unchanged-or-worse (a soft 21 that draws an ace becomes
    a hard 12), and _stand_ev is monotone in the total.  Skipping the
    comparison prunes a large, entirely pointless subtree.
    """
    if shoe_size(shoe) == 0:
        # A real 312-card shoe cannot run out under a hand that draws at most
        # a dozen cards, but a caller can hand us a toy shoe.  Raising beats
        # inventing an outcome for "the player wants a card and there are none".
        raise ValueError(f'player wants to hit {total} but the shoe is empty')

    ev = 0.0
    for i, p in enumerate(_draw_probs(shoe, up)):
        if p <= 0.0:
            continue
        nt, ns = _draw(total, soft, i)
        if nt > 21:
            ev -= p
            continue
        sub = remove_card(shoe, i)
        stand_here = _stand_ev(nt, up, sub, s17)
        if nt == 21:
            ev += p * stand_here
            continue
        hit_here = _hit_ev(nt, ns, up, sub, s17)
        ev += p * (stand_here if stand_here > hit_here else hit_here)
    return ev


@lru_cache(maxsize=None)
def _double_ev(total: int, soft: bool, up: str, shoe: Shoe, s17: bool) -> float:
    """EV of doubling: exactly one card, then stand, at two units.

    The factor of 2 is applied at the end rather than inside the loop so that
    the loop body is identical to the hit loop and can be read against it.
    Note that this is NOT "2 x ev_hit": the doubled hand has no second
    decision, which is what makes doubling a 15 vs 10 so much worse than
    hitting it even though the first card is drawn from the same shoe.
    """
    if shoe_size(shoe) == 0:
        raise ValueError(f'player wants to double {total} but the shoe is empty')

    ev = 0.0
    for i, p in enumerate(_draw_probs(shoe, up)):
        if p <= 0.0:
            continue
        nt, _ns = _draw(total, soft, i)
        if nt > 21:
            ev -= p
        else:
            ev += p * _stand_ev(nt, up, remove_card(shoe, i), s17)
    return 2.0 * ev


# --- splits ----------------------------------------------------------------

#: One row of a split-hand outcome distribution: (extra hands this subtree
#: consumed, probability of that, mean subtree EV given it).
Outcomes = tuple[tuple[int, float, float], ...]


def _as_outcomes(acc: dict[int, list]) -> Outcomes:
    """Turn a {slots_used: [probability, probability*ev]} accumulator into rows."""
    return tuple((used, p, w / p) for used, (p, w) in sorted(acc.items()))


def _add_outcome(acc: dict[int, list], used: int, p: float, value: float) -> None:
    row = acc.get(used)
    if row is None:
        acc[used] = [p, p * value]
    else:
        row[0] += p
        row[1] += p * value


@lru_cache(maxsize=None)
def _split_hand_outcomes(rank_i: int, up: str, shoe: Shoe, slots: int,
                         s17: bool, das: bool, hit_split_aces: bool,
                         resplit_aces: bool) -> Outcomes:
    """ONE split hand holding a single card, as an outcome DISTRIBUTION.

    Returns rows of (extra hands consumed, probability, mean EV of the whole
    subtree).  The EV is already in units of the ORIGINAL bet summed over the
    subtree, so a hand that resplits into two contributes both halves; the
    probabilities sum to 1.

    Why a distribution and not a number: `slots` is the number of EXTRA hands
    still available to the whole round, and it is one shared pool.  If this hand
    spends two of them the sibling can only have what is left, so the caller has
    to know how many were spent and how likely each amount was.  Halving the
    pool at each split instead is what this module used to do, and APPROXIMATIONS
    note 2 records what that cost.

    The rules flags are passed as loose scalars instead of a Rules object so
    that the memo key does not fragment on fields the split maths never reads
    (decks, payout, insurance).  Two rulesets that differ only in blackjack
    payout share every entry in this table.
    """
    if shoe_size(shoe) == 0:
        raise ValueError('cannot deal to a split hand: the shoe is empty')

    is_ace = (rank_i == _ACE)
    acc: dict[int, list] = {}
    for i, p in enumerate(_draw_probs(shoe, up)):
        if p <= 0.0:
            continue
        sub = remove_card(shoe, i)
        total, soft = _two_card_state(rank_i, i)

        # Option A: play the two-card hand out, spending no extra hand.
        if is_ace and not hit_split_aces:
            # Split aces get one card and the hand is over.  A,T here is 21
            # and pays 1:1 - a hand born of a split is never a natural
            # (core.is_blackjack encodes the same rule).  Nothing to compare.
            play_value = _stand_ev(total, up, sub, s17)
        else:
            play_value = _stand_ev(total, up, sub, s17)
            hit_value = _hit_ev(total, soft, up, sub, s17)
            if hit_value > play_value:
                play_value = hit_value
            if das:
                double_value = _double_ev(total, soft, up, sub, s17)
                if double_value > play_value:
                    play_value = double_value

        if not (i == rank_i and slots >= 1 and (resplit_aces or not is_ace)):
            _add_outcome(acc, 0, p, play_value)
            continue

        # Option B: this hand pairs up again and is resplit.  That spends one
        # slot immediately; the two children then share what is left, the first
        # one playing out completely before the second is dealt to, which is the
        # order a real table deals them in.
        branch: dict[int, list] = {}
        resplit_value = 0.0
        first = _split_hand_outcomes(rank_i, up, sub, slots - 1, s17, das,
                                     hit_split_aces, resplit_aces)
        for used_a, p_a, ev_a in first:
            second = _split_hand_outcomes(rank_i, up, sub, slots - 1 - used_a,
                                          s17, das, hit_split_aces, resplit_aces)
            for used_b, p_b, ev_b in second:
                q = p_a * p_b
                pair_value = ev_a + ev_b
                resplit_value += q * pair_value
                _add_outcome(branch, 1 + used_a + used_b, q, pair_value)

        # The resplit decision is greedy: this hand's own EV, not the round's.
        # APPROXIMATIONS note 2 brackets what that costs.
        if resplit_value > play_value:
            for used, q, value in _as_outcomes(branch):
                _add_outcome(acc, used, p * q, value)
        else:
            _add_outcome(acc, 0, p, play_value)
    return _as_outcomes(acc)


def _split_pool(rules: Rules, hand_count: int) -> int:
    """Extra hands still available after splitting the hand in front of you.

    hand_count is how many hands are already in play.  Splitting one of them
    makes hand_count+1, so what is left of the cap is the pool the two resulting
    hands share.  At the top of a round (hand_count=1, max_hands=4) that is 2.
    """
    if rules.max_hands < 2:
        raise ValueError('rules.max_hands < 2: this table does not allow splitting')
    pool = rules.max_hands - hand_count - 1
    if pool < 0:
        raise ValueError(
            f'{hand_count} hands are already in play and rules.max_hands is '
            f'{rules.max_hands}: this hand cannot be split'
        )
    return pool


def _split_total_ev(rank_i: int, up: str, shoe: Shoe, rules: Rules,
                    hand_count: int = 1) -> float:
    """EV of the whole split, both hands, in units of the original bet."""
    pool = _split_pool(rules, hand_count)
    flags = (rules.s17, rules.das, rules.hit_split_aces, rules.resplit_aces)
    total = 0.0
    for used, p, ev_first in _split_hand_outcomes(rank_i, up, shoe, pool, *flags):
        second = _split_hand_outcomes(rank_i, up, shoe, pool - used, *flags)
        total += p * (ev_first + sum(q * value for _u, q, value in second))
    return total


# --- public per-hand EV ----------------------------------------------------

def ev_stand(player_cards, dealer_up, shoe: Shoe | None = None,
             rules: Rules = STANDARD, *, is_split_hand: bool = False) -> float:
    """EV of standing, in units of the original bet.

    shoe defaults to a fresh shoe minus the visible cards, which is the right
    default for a table that reshuffles every hand.

    A two-card 21 that is not a split hand is a natural and is worth
    rules.blackjack_payout flat.  Post-peek the dealer cannot match it, and a
    natural beats a drawn 21, so there is no dealer distribution to consult.
    """
    cards = normalize_hand(player_cards)
    up = normalize(dealer_up)
    if shoe is None:
        shoe = initial_shoe_for(cards, up, rules)
    total, _soft = hand_total(cards)
    if len(cards) == 2 and total == 21 and not is_split_hand:
        return float(rules.blackjack_payout)
    return _stand_ev(total, up, tuple(shoe), rules.s17)


def ev_hit(player_cards, dealer_up, shoe: Shoe | None = None,
           rules: Rules = STANDARD) -> float:
    """EV of hitting once and then playing the rest of the hand optimally."""
    cards = normalize_hand(player_cards)
    up = normalize(dealer_up)
    if shoe is None:
        shoe = initial_shoe_for(cards, up, rules)
    total, soft = hand_total(cards)
    if total > 21:
        raise ValueError(f'hand {cards} is busted at {total}; it cannot hit')
    return _hit_ev(total, soft, up, tuple(shoe), rules.s17)


def ev_double(player_cards, dealer_up, shoe: Shoe | None = None,
              rules: Rules = STANDARD) -> float:
    """EV of doubling: one card, then stand, two units at risk.

    The function does not police whether the table would allow the double.
    That is best_action's job; here the number is wanted even when it is
    unavailable, because "you would have doubled if the button were there" is
    a thing the tool should be able to say.
    """
    cards = normalize_hand(player_cards)
    up = normalize(dealer_up)
    if shoe is None:
        shoe = initial_shoe_for(cards, up, rules)
    total, soft = hand_total(cards)
    if total > 21:
        raise ValueError(f'hand {cards} is busted at {total}; it cannot double')
    return _double_ev(total, soft, up, tuple(shoe), rules.s17)


def ev_split(pair_rank, dealer_up, shoe: Shoe | None = None,
             rules: Rules = STANDARD, *, hand_count: int = 1) -> float:
    """EV of splitting a pair, summed over every resulting hand.

    pair_rank is ONE rank ('8' means the player holds 8,8).  shoe follows the
    same convention as every other function here: BOTH cards of the pair and
    the dealer's upcard are already out of it, which is what
    initial_shoe_for((r, r), up) produces.  Passing a shoe with only one of
    the pair removed is the obvious way to misuse this and would flatter every
    split by about a card's worth of composition.

    hand_count is how many hands are ALREADY in play, so it is 1 for the first
    split of a round and larger when this pair is itself a split hand.  It
    matters because rules.max_hands is one shared pool: at hand_count=3 with a
    cap of 4 the two hands this split produces have no resplits left between
    them, and 8,8 vs 7 is worth +0.2184 rather than the +0.3077 a fresh round
    would give.

    The return value is directly comparable with ev_stand/ev_hit: it is in
    units of the original bet, so -0.4749 for 8,8 vs 10 means the split as a
    whole loses 47.5 cents per dollar of the ORIGINAL wager even though two
    dollars end up on the table.
    """
    r = normalize(pair_rank)
    up = normalize(dealer_up)
    if shoe is None:
        shoe = initial_shoe_for((r, r), up, rules)
    return _split_total_ev(RANK_INDEX[r], up, tuple(shoe), rules, hand_count)


# --- the recommendation ----------------------------------------------------

def best_action(player_cards, dealer_up, shoe: Shoe | None = None,
                rules: Rules = STANDARD, *, can_double: bool = True,
                can_split: bool = True, is_split_hand: bool = False,
                hand_count: int = 1) -> tuple[str, dict[str, float], float]:
    """The exact optimum for one hand, with the EV of every legal alternative.

    Returns (action, evs, margin):
        action  one of core.HIT / STAND / DOUBLE / SPLIT
        evs     {action_code: ev} for the actions this table actually allows.
                Unavailable actions are absent rather than present-and-None,
                so a caller cannot accidentally rank against a number that was
                never on offer.
        margin  best EV minus the second-best AVAILABLE EV.  This is the
                number the tool prints next to its advice, and it is the only
                honest measure of how much the decision matters: 0.044 on
                12 vs 2 means the play is real, 0.0008 on 12 vs 4 means it is
                a coin flip and the user should not agonise.

    can_double / can_split describe the BUTTONS, and are intersected with the
    rules: passing can_double=True on a three-card hand does not conjure a
    double, because no table allows doubling after a hit.

    hand_count is how many hands are already in play, and it does two things,
    not one.  It removes the SPLIT button at the cap, and it also SHRINKS the
    split's value, because rules.max_hands is a pool the whole round spends out
    of: 8,8 vs 7 as the third hand of a round is worth +0.2184, not the +0.3077
    it is worth on the first decision, and quoting the fresh-round number to a
    player who has already split twice is quoting an option he does not have.

    A natural is not a decision.  It returns STAND with a margin of 0.0.
    """
    cards = normalize_hand(player_cards)
    up = normalize(dealer_up)
    if len(cards) < 2:
        raise ValueError('a hand needs at least two cards before it has a decision')
    total, soft = hand_total(cards)
    if total > 21:
        raise ValueError(f'hand {cards} is busted at {total}; there is no decision left')
    if shoe is None:
        shoe = initial_shoe_for(cards, up, rules)
    shoe = tuple(shoe)

    two_cards = len(cards) == 2
    if two_cards and total == 21 and not is_split_hand:
        return STAND, {STAND: float(rules.blackjack_payout)}, 0.0

    pair = is_pair(cards, rules.tens_are_pairs)
    can_double = bool(can_double) and two_cards and (not is_split_hand or rules.das)
    blocked_resplit_aces = (is_split_hand and pair and cards[0] == 'A'
                            and not rules.resplit_aces)
    can_split = (bool(can_split) and two_cards and pair
                 and hand_count < rules.max_hands and not blocked_resplit_aces)

    # A split ace is frozen: the table deals it exactly one card and the hand is
    # over.  The only button it can still have is SPLIT, and only where the
    # table allows resplitting aces.  Offering HIT or DOUBLE here would be
    # advice the dealer will not accept, and - worse - would put a number the
    # player cannot collect into the margin.  cards[0] is the split rank by the
    # convention every caller in this project follows, so 7,A (a split seven
    # that drew an ace) is correctly NOT frozen.
    frozen_split_ace = (is_split_hand and two_cards and cards[0] == 'A'
                        and not rules.hit_split_aces)

    evs: dict[str, float] = {STAND: _stand_ev(total, up, shoe, rules.s17)}
    if not frozen_split_ace:
        evs[HIT] = _hit_ev(total, soft, up, shoe, rules.s17)
        if can_double:
            evs[DOUBLE] = _double_ev(total, soft, up, shoe, rules.s17)
    if can_split:
        # hand_count, not 1: rules.max_hands is a pool shared by the whole
        # round, so a pair being split as the third hand of a round has fewer
        # resplits behind it than the same pair on the first decision.
        evs[SPLIT] = _split_total_ev(RANK_INDEX[cards[0]], up, shoe, rules,
                                     hand_count)

    ordered = sorted(evs.items(), key=lambda kv: kv[1], reverse=True)
    action, best = ordered[0]
    margin = best - ordered[1][1] if len(ordered) > 1 else 0.0
    return action, evs, margin


# --- playing a hand out under a FIXED strategy -----------------------------
# Everything above finds the optimum.  house_edge(strategy=...) needs the
# opposite: the EV of obeying a chart even where the chart is wrong.  That
# cannot be done by scoring only the first decision, because a chart that says
# "hit 12 vs 2" also dictates what happens to the 15 that hit produces.  These
# two functions therefore follow the strategy all the way to the end of the
# hand.

def _strategy_action(strategy, cards, up, rules, can_double, can_split,
                     is_split_hand) -> str:
    """Call a strategy and reduce whatever it returns to an action code.

    bj.strategy.basic_action returns an Advice dataclass; a test double may
    return a bare 'H'.  Accepting both keeps house_edge usable as a grader for
    anything chart-shaped, not just this project's one chart.
    """
    out = strategy(cards, up, rules, can_double=can_double,
                   can_split=can_split, is_split_hand=is_split_hand,
                   hand_count=1)
    return getattr(out, 'action', out)


@lru_cache(maxsize=None)
def _strategy_play_ev(cards: tuple[str, ...], up: str, shoe: Shoe,
                      rules: Rules, strategy: Callable, is_split_hand: bool,
                      can_double: bool) -> float:
    """EV of a hand played to the end by `strategy`.  No split decisions here.

    Keyed on the full card tuple rather than (total, soft) because a
    composition-dependent chart - and bj.strategy has one, the multi-card
    16 vs 10 exception - can give different answers to hands with the same
    total.  Reducing to (total, soft) here would silently grade a chart the
    project does not actually print.
    """
    total, soft = hand_total(cards)
    if total > 21:
        return -1.0
    action = _strategy_action(strategy, cards, up, rules, can_double, False,
                              is_split_hand)
    if action == STAND:
        return _stand_ev(total, up, shoe, rules.s17)
    if action == DOUBLE:
        return _double_ev(total, soft, up, shoe, rules.s17)
    if action != HIT:
        raise ValueError(f'strategy returned {action!r} on {cards} vs {up}, '
                         'which is not a hit, stand or double')

    if shoe_size(shoe) == 0:
        raise ValueError('strategy wants to hit but the shoe is empty')
    ev = 0.0
    for i, p in enumerate(_draw_probs(shoe, up)):
        if p <= 0.0:
            continue
        drawn = cards + (RANKS[i],)
        if hand_total(drawn)[0] > 21:
            ev -= p
            continue
        # can_double is False from here on: the hand has three cards.
        ev += p * _strategy_play_ev(drawn, up, remove_card(shoe, i), rules,
                                    strategy, is_split_hand, False)
    return ev


@lru_cache(maxsize=None)
def _strategy_split_hand_outcomes(rank_i: int, up: str, shoe: Shoe, slots: int,
                                  rules: Rules, strategy: Callable) -> Outcomes:
    """The strategy-driven twin of _split_hand_outcomes.  Same shared pool.

    The only difference is who decides: here the chart does, so there is no
    comparison of resplit against play-out, and a chart that says P spends a
    slot whether or not that was the better idea.
    """
    if shoe_size(shoe) == 0:
        raise ValueError('cannot deal to a split hand: the shoe is empty')
    is_ace = (rank_i == _ACE)
    rank = RANKS[rank_i]
    acc: dict[int, list] = {}
    for i, p in enumerate(_draw_probs(shoe, up)):
        if p <= 0.0:
            continue
        sub = remove_card(shoe, i)
        # The split rank stays FIRST in the tuple.  bj.strategy identifies a
        # one-card-only split ace by cards[0], so sorting these would tell it
        # that 5,5 which drew an ace is a split ace.
        cards = (rank, RANKS[i])
        can_resplit = (i == rank_i and slots >= 1
                       and (rules.resplit_aces or not is_ace))

        if can_resplit and _strategy_action(strategy, cards, up, rules,
                                            rules.das, True, True) == SPLIT:
            first = _strategy_split_hand_outcomes(rank_i, up, sub, slots - 1,
                                                  rules, strategy)
            for used_a, p_a, ev_a in first:
                second = _strategy_split_hand_outcomes(
                    rank_i, up, sub, slots - 1 - used_a, rules, strategy)
                for used_b, p_b, ev_b in second:
                    _add_outcome(acc, 1 + used_a + used_b, p * p_a * p_b, ev_a + ev_b)
        elif is_ace and not rules.hit_split_aces:
            # A table rule, not a strategy choice: one card and done.  This
            # branch is reached whether or not a resplit was on offer, so a
            # chart is never asked to play a hand the table has already closed.
            _add_outcome(acc, 0, p, _stand_ev(hand_total(cards)[0], up, sub, rules.s17))
        else:
            _add_outcome(acc, 0, p,
                         _strategy_play_ev(cards, up, sub, rules, strategy,
                                           True, rules.das))
    return _as_outcomes(acc)


def _strategy_split_total_ev(rank_i: int, up: str, shoe: Shoe, rules: Rules,
                             strategy: Callable, hand_count: int = 1) -> float:
    """EV of a whole strategy-driven split, both hands, original-bet units."""
    pool = _split_pool(rules, hand_count)
    total = 0.0
    for used, p, ev_first in _strategy_split_hand_outcomes(
            rank_i, up, shoe, pool, rules, strategy):
        second = _strategy_split_hand_outcomes(rank_i, up, shoe, pool - used,
                                               rules, strategy)
        total += p * (ev_first + sum(q * value for _u, q, value in second))
    return total


# --- house edge ------------------------------------------------------------

@lru_cache(maxsize=None)
def _cell_ev(i: int, j: int, k: int, shoe: Shoe, rules: Rules,
             strategy: Callable | None) -> float:
    """EV of one initial deal: player holds RANKS[i], RANKS[j] vs upcard RANKS[k].

    `shoe` already has all three cards removed.  The dealer-natural branch is
    added back here, because it is part of the round even though it is not
    part of any decision: the player never acts on it, so it cannot live
    inside the post-peek recursion.

    Keyed on i <= j by the caller, so the 1,000 ordered deals collapse to 550
    distinct problems.
    """
    up = RANKS[k]
    n = shoe_size(shoe)
    if k == _ACE:
        p_natural = shoe[_TEN] / n
    elif k == _TEN:
        p_natural = shoe[_ACE] / n
    else:
        p_natural = 0.0

    player_natural = ((i == _ACE and j == _TEN) or (i == _TEN and j == _ACE))
    if player_natural:
        # Both naturals push; otherwise the player is paid 3:2.
        return (1.0 - p_natural) * float(rules.blackjack_payout)

    cards = (RANKS[i], RANKS[j])
    pair = (i == j) and rules.max_hands >= 2
    if strategy is None:
        _action, _evs, _margin = best_action(cards, up, shoe, rules,
                                             can_double=True, can_split=pair)
        played = max(_evs.values())
    else:
        action = _strategy_action(strategy, cards, up, rules, True, pair, False)
        if action == SPLIT:
            played = _strategy_split_total_ev(i, up, shoe, rules, strategy)
        else:
            played = _strategy_play_ev(cards, up, shoe, rules, strategy, False, True)

    # A dealer natural costs the player exactly the original bet: the peek
    # happens before any money can be added, so no double or split is exposed.
    return p_natural * (-1.0) + (1.0 - p_natural) * played


def house_edge(rules: Rules = STANDARD, strategy: Callable | None = None) -> float:
    """Expected result per unit wagered, averaged over every possible deal.

    Returns a NEGATIVE number.  It is the player's expectation, not the
    house's, and it is reported with the sign it actually has because the
    project's honesty rules forbid dressing a loss up as an edge.  -0.004026
    means the player loses just over four units per thousand wagered.

    strategy=None plays the exact composition-dependent optimum - the
    theoretical ceiling for a non-counter, and the number Wizard of Odds
    Appendix 9 calls the game EV.

    Pass bj.strategy.basic_action to measure the printed chart instead.  That
    number is worse, and the gap between the two is the price of carrying a
    chart on paper rather than a solver in your pocket.  The chart is followed
    all the way down, not just on the first decision, because a chart that
    misplays a 12 also owns the 16 that the misplay produces.

    Every initial deal is weighted by its exact probability from a fresh shoe,
    drawing without replacement: P = n_a/N * n_b/(N-1) * n_up/(N-2), summed
    over all 1,000 ordered (card, card, upcard) triples.  Ordered rather than
    combinations, because getting the multiplicities right by hand is a
    classic source of a silently-wrong third decimal place, and 1,000 cheap
    iterations over 550 memoised cells costs nothing.
    """
    if not rules.peek:
        # A no-hole-card game is a materially different game: doubles and
        # splits made against a ten or an ace can be lost to a natural that
        # was never peeked for, worth about -0.11% per the handoff's rule
        # table.  None of that is modelled here.  Returning the peek number
        # under a no-peek ruleset would be a quiet lie.
        raise NotImplementedError(
            'house_edge models the dealer-peek game only; rules.peek is False'
        )

    base = fresh_shoe(rules.decks)
    n = shoe_size(base)
    total = 0.0
    for i, ci in enumerate(base):
        if ci == 0:
            continue
        p_i = ci / n
        s1 = remove_card(base, i)
        for j, cj in enumerate(s1):
            if cj == 0:
                continue
            p_j = cj / (n - 1)
            s2 = remove_card(s1, j)
            lo, hi = (i, j) if i <= j else (j, i)
            for k, ck in enumerate(s2):
                if ck == 0:
                    continue
                p_k = ck / (n - 2)
                s3 = remove_card(s2, k)
                total += p_i * p_j * p_k * _cell_ev(lo, hi, k, s3, rules, strategy)
    return total


# --- deriving the chart from scratch ---------------------------------------

_SOFT_KEYS = tuple(f'A,{d}' for d in range(2, 10))


def _code_for(evs: dict[str, float], das_evs: dict[str, float] | None = None) -> str:
    """Turn a set of action EVs into one of the chart's printed codes.

    The vocabulary has to match bj.strategy exactly or the diff is useless:
      H   hit          S   stand
      D   double, else hit        Ds  double, else stand
      P   split        Ph  split only because DAS is allowed
    'D' vs 'Ds' is decided by which of hit and stand would win if the double
    button were missing, which is precisely what the printed code means.
    'Ph' is decided by re-running the split without DAS; das_evs carries that
    second computation, and is only supplied for pair cells.
    """
    action = max(evs.items(), key=lambda kv: kv[1])[0]
    if action == STAND:
        return 'S'
    if action == HIT:
        return 'H'
    if action == DOUBLE:
        return 'Ds' if evs[STAND] > evs[HIT] else 'D'
    if action == SPLIT:
        if das_evs is not None:
            no_das = max(das_evs.items(), key=lambda kv: kv[1])[0]
            if no_das != SPLIT:
                return 'Ph'
        return 'P'
    raise ValueError(f'cannot name an action for {evs!r}')


def derive_table(rules: Rules = STANDARD) -> dict[str, dict[tuple[object, str], str]]:
    """Recompute the whole basic-strategy chart from the solver.

    Returns {'hard': ..., 'soft': ..., 'pairs': ...}, each keyed exactly like
    the matching dict in bj.strategy, so a verifier can do a dict diff and
    print the disagreeing cells.  This exists so that nobody has to take the
    transcribed chart on faith - including the one known transcription
    dispute the strategy module flags at 4,4 vs 4.

    Hard rows average each action's EV over every two-card composition of that
    total, weighted by deal frequency (APPROXIMATIONS note 3).  Pair
    compositions are included in the hard rows because the hard chart is
    exactly what a pair falls through to when the split button is gone, and
    split is not among the actions compared there.  Ace-containing hands are
    excluded from hard rows: they are soft, and have their own chart.
    """
    ups = tuple(RANKS[i] for i in range(1, 10)) + ('A',)  # 2..9, T, A
    hard: dict[tuple[object, str], str] = {}
    soft: dict[tuple[object, str], str] = {}
    pairs: dict[tuple[object, str], str] = {}

    base = fresh_shoe(rules.decks)

    for up in ups:
        u = RANK_INDEX[up]

        # --- hard totals: bucket the two-card non-ace compositions by total
        buckets: dict[int, list] = {}
        for a in range(1, 10):          # skip the ace: those hands are soft
            for b in range(a, 10):
                shoe = remove_cards(base, (RANKS[a], RANKS[b], up))
                # relative weight = ordered ways to be dealt this pair of
                # ranks out of the shoe that remains once the upcard is gone
                after_up = remove_card(base, u)
                if a == b:
                    weight = after_up[a] * (after_up[a] - 1)
                else:
                    weight = 2 * after_up[a] * after_up[b]
                if weight <= 0:
                    continue
                total, _soft = _two_card_state(a, b)
                buckets.setdefault(total, []).append((weight, a, b, shoe))

        for total, comps in buckets.items():
            wsum = sum(w for w, _a, _b, _s in comps)
            acc = {STAND: 0.0, HIT: 0.0, DOUBLE: 0.0}
            for weight, a, b, shoe in comps:
                _t, is_soft = _two_card_state(a, b)
                acc[STAND] += weight * _stand_ev(total, up, shoe, rules.s17)
                acc[HIT] += weight * _hit_ev(total, is_soft, up, shoe, rules.s17)
                acc[DOUBLE] += weight * _double_ev(total, is_soft, up, shoe, rules.s17)
            hard[(total, up)] = _code_for({k: v / wsum for k, v in acc.items()})

        # --- soft totals A,2 .. A,9: one composition each, no averaging.
        # d is a SHOE INDEX, not a pip value: RANKS[1] is '2'.  The two happen
        # to be off by one and conflating them silently shifts every soft row
        # by one column, which is a mistake this comment exists to prevent
        # anyone repeating.
        for d in range(1, 9):
            kicker = RANKS[d]
            shoe = remove_cards(base, ('A', kicker, up))
            total, is_soft = _two_card_state(_ACE, d)
            evs = {
                STAND: _stand_ev(total, up, shoe, rules.s17),
                HIT: _hit_ev(total, is_soft, up, shoe, rules.s17),
                DOUBLE: _double_ev(total, is_soft, up, shoe, rules.s17),
            }
            soft[(f'A,{kicker}', up)] = _code_for(evs)

        # --- pairs
        for r in range(10):
            rank = RANKS[r]
            shoe = remove_cards(base, (rank, rank, up))
            total, is_soft = _two_card_state(r, r)
            evs = {
                STAND: _stand_ev(total, up, shoe, rules.s17),
                HIT: _hit_ev(total, is_soft, up, shoe, rules.s17),
                DOUBLE: _double_ev(total, is_soft, up, shoe, rules.s17),
                SPLIT: _split_total_ev(r, up, shoe, rules),
            }
            das_evs = None
            if max(evs.items(), key=lambda kv: kv[1])[0] == SPLIT and rules.das:
                no_das_rules = _dc_replace(rules, das=False)
                das_evs = dict(evs)
                das_evs[SPLIT] = _split_total_ev(r, up, shoe, no_das_rules)
            key = f'{rank},{rank}'
            pairs[(key, up)] = _code_for(evs, das_evs)

    return {'hard': hard, 'soft': soft, 'pairs': pairs}


def clear_caches() -> None:
    """Drop this module's memo tables.

    Correctness never depends on it - every key is immutable - but a long
    simulation that walks many distinct shoes will otherwise grow these tables
    without bound.  Does NOT clear bj.dealer's caches; call
    bj.dealer.clear_caches() for those, separately and on purpose.
    """
    _draw_probs.cache_clear()
    _hit_ev.cache_clear()
    _double_ev.cache_clear()
    _split_hand_outcomes.cache_clear()
    _strategy_play_ev.cache_clear()
    _strategy_split_hand_outcomes.cache_clear()
    _cell_ev.cache_clear()
