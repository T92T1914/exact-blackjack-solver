"""Monte Carlo round engine: a fresh 6-deck shoe for every single round.

This is the module that turns the strategy tables into numbers.  It plays whole
rounds - deal, peek, split, double, dealer draw, settle - and reports the
distribution of what comes back.

WHY A FRESH SHOE EVERY ROUND
    Settled, not inferred.  The site's own state endpoint exposes a
    provably-fair triple - server seed hash, client seed, and a nonce that
    increments once per bet - and every row of the transaction log carries its
    own fair_nonce, so each round is dealt from a shoe shuffled for that round.
    The client script says the same thing in a comment in its blackjack start
    routine.  Both are recorded in docs/verified-live-2026-09-02.md, which
    moved this from the handoff's original 85 percent inference to about 99
    percent verified and deleted counting from the project's scope entirely.
    Nothing here carries state between rounds, which is the model, made
    visible.  The residual doubt is only that every piece of that evidence is
    client-side: it is the server's own account of what the server does.

WHY THE STRATEGY IS COMPILED RATHER THAN RE-IMPLEMENTED
    Calling ``bj.strategy.basic_action`` inside the round loop costs roughly
    fifteen microseconds per decision, most of it spent building an English
    reason string that nobody reads at two million rounds.  The alternative
    everyone reaches for - re-typing the charts as ``if`` statements inside the
    simulator - creates a second copy of the strategy that can silently drift
    from the first, which is the single most expensive bug this project could
    have: the simulator would then be verifying a strategy the phone tool does
    not play.

    So the tables here are GENERATED.  At first use, every reachable hand state
    is handed to ``basic_action`` as a real list of cards and the answer is
    stored in a flat lookup array.  One strategy, two consumers.  The test
    suite closes the loop end to end: the same seed is played twice, once
    through the compiled tables and once through ``basic_action`` itself, and
    the two rounds must come out card for card identical.  If a compiled cell
    were ever wrong the two runs would draw different cards and the test would
    fail.

    The price of a flat table is that its key has to carry every property of a
    hand that bj.strategy can look at.  When that module grew the
    soft-18-vs-ace composition exception, the key here did not cover it and
    those two replay tests failed - which is the design working.  The fix was
    to widen the key, never to special-case the exception in this file: a
    second copy of the rule here is exactly the drift the compilation exists to
    prevent.

APPROXIMATIONS
    1.  Fresh shoe per round, as above.  Verified from the site's own
        provably-fair nonce rather than assumed; it is listed here only
        because the evidence for it is the server's word.
    2.  The dealer's hand is ALWAYS played to completion, including when every
        player hand has already busted and when the player held a natural.  A
        real dealer stops there.  This costs nothing in EV, because those cards
        are drawn after every player decision has been made and cannot change
        one, and it buys a ``dealer_bust_rate`` that is an UNCONDITIONAL
        figure, the same quantity as the 0.28192 that this project's own exact
        dealer solver computes (out/dealer_check.json).  Measuring bust only on
        rounds where the dealer actually had to draw would condition on the
        player having stood, which is correlated with a weak upcard, and would
        print a number that looks like the published one but is not the same
        quantity.
    3.  The dealer here draws from a shoe the player has already taken cards
        from; the exact dealer table removes only the dealer's own cards, and
        the player's hits preferentially remove small ones.  That difference is
        real but this engine cannot resolve it from zero: at 35,000,000 rounds
        it returns a bust rate of 0.281943 +/- 0.000076 against the exact
        0.281921, which is +0.3 standard errors.  So the measured magnitude of
        the approximation is under 0.0002, and it is reported rather than
        tuned away.

        It is NOT the reason this engine disagrees with the handoff's 28.3
        percent headline.  That headline contradicts the handoff's own
        per-upcard dealer bust table printed a few lines above it: weight those
        ten rows by upcard frequency and apply the peek and they come to
        0.281899, not 0.283.  The exact solver puts the same quantity at
        0.28192.  The engine agrees with the table; the headline is the
        outlier, and it is the headline that REFERENCE still quotes.
    4.  Cards are drawn by partial Fisher-Yates over one reusable 312-element
        array rather than by walking a 10-element cumulative count table.  Both
        are exact draws without replacement; the array version is about twice
        as fast because it is four list operations instead of an average of
        five loop iterations.  The array never needs resetting between rounds:
        swapping two entries leaves the same multiset of 312 cards, so
        restarting the draw index at zero is already a fresh shoe.  The one
        thing this costs is that the shoe cannot be inspected mid-round, which
        nothing here wants to do.
    5.  ``rules.peek=False`` is REFUSED, not approximated.  The three charts in
        bj.strategy are peek charts; a no-hole-card game changes both the
        strategy and the settlement of doubles and splits against a dealer
        natural.  Simulating it with peek tables would produce a confident
        number about a game nobody is playing.
    6.  The composition-dependent 16 vs 10 exception uses whatever form
        bj.strategy is asked for; the default is that module's default (the
        loose "three or more cards" rule).  ``comp16_requires_45=True`` selects
        the sharper published form and rebuilds the tables.
    7.  ``max_extra_units`` models MONEY, not a table rule.  It caps how much
        more than the base bet the player can put up, so 0 is an all-in bet:
        the DOUBLE and SPLIT buttons exist but there is nothing left to press
        them with.  This is the whole reason the bet analysis downstream is
        honest - quoting the 0.41 percent house edge for an all-in hand would
        overstate an all-in climb, because roughly a fifth of basic strategy's
        value comes from doubling and splitting.
    8.  Suits do not exist and ten-value cards are one rank, per bj.core.  No
        decision in blackjack depends on either.

KNOWN DISAGREEMENT WITH THE PUBLISHED REFERENCE
    Measured over 35,000,000 rounds, seed 20260902, 16 workers - the worker
    count is part of the seed here, because a parallel run subdivides the
    stream and is reproducible against itself rather than against a serial run.
    Six of the eight sanity numbers in the handoff's "Simulator sanity checks"
    land inside their stated tolerance:

        EV per hand      -0.00389 +/- 0.00020   published -0.0041   (+1.1 sd)
        SD per hand       1.1547                published  1.15
        player natural    4.750%                published  4.75%
        dealer natural    4.754%                published  4.75%
        dealer bust      28.194%                published 28.3%
        push (per hand)   8.465%                published  8.5%

    Two do not:

        win  (per hand)  43.600%                published 42.2%   (+169 sd)
        loss (per hand)  47.935%                published 49.1%   (-140 sd)

    Note also that two million rounds - the sample size the same section asks
    for - cannot decide the EV check at all.  Its band is 0.0006 on the tight
    side and the standard error there is 0.00082, so the band is +/-0.73 sigma
    and a correct engine lands outside it 43 percent of the time.  A 2,000,000
    round run that passes has told you nothing, and one that fails has told you
    nothing either.  Every Check reports its own power for that reason.

    Nothing was tuned.  The engine was checked four ways first.  (1) The deal,
    the peek, the natural payout and the settlement were verified against an
    exact enumeration - a player who always stands on his first two cards,
    solved combinatorially through bj.dealer, agrees with this engine to
    0.0003 on every rate and to 1.2 standard errors on EV.  (2) The compiled
    strategy reproduces ``bj.strategy.basic_action`` card for card over 60,000
    replayed rounds across six rule sets and four budget caps.  (3) The
    dealer's own final-total distribution matches the exactly-computed one to
    5e-5 in every one of the sixty cells (out/dealer_check.json).  (4) Best of
    all, the EV agrees with bj.ev, which enumerates all 1,000 ordered opening
    deals and recurses through every draw exactly: that solver puts the printed
    chart at -0.004044 with no sampling error at all, and this engine's
    -0.003888 +/- 0.000195 is 0.8 standard errors from it.  The two modules
    share bj.core and bj.strategy and nothing else - not the dealing, not the
    settlement, not the split logic - so that agreement is worth more than
    agreement with any published figure.

    The published win/loss pair is also internally inconsistent with the
    published house edge, which is the reason to doubt it rather than the
    engine.  Add it up.  The identity is exact:

        EV per round = (hand win - hand loss) x hands per round
                       + 0.5 x P(natural that is paid)
                       + (doubled hands per round) x (their win - their loss)

    Feed it the published split and this engine's measurements of the other
    three terms.  At 1.0283 hands per round the published (0.422 - 0.491) is
    -0.0709 per round if every hand paid one unit.  The 3:2 bonus on a natural
    adds +0.5 x 0.0453 = +0.0227.  Rearranged for the last term, this engine's
    own -0.00389 leaves +0.0180 riding on doubles.  Splitting is already inside
    the 1.0283 and is not added again.  The total is -0.0302, a three percent
    house edge - seven times the 0.41 percent the same appendix quotes.  For
    the published pair to sit alongside a 0.41 percent edge, doubled hands
    would have to win about 68 percent of the time.  They win 55.

    That +0.0180 is a residual: it is what the identity leaves once the other
    three terms are measured.  The second engine described below keeps per-hand
    records and can decompose it directly - 0.1037 doubled HANDS per round,
    winning 55.2 percent and losing 37.9 percent, 0.1037 x 0.1726 = +0.0179.
    Two routes to the same term, agreeing to 0.0001.  This module cannot take
    the second route on its own, because ``RoundResult`` records doubling per
    ROUND and cannot say which hand of a split round was the doubled one; it
    can and does count doubled hands through the strategy hook, and gets
    0.10396 +/- 0.00015 over 4,200,000 rounds against the second engine's
    0.10372 +/- 0.00006 over 25,200,000.

    Three numbers here are close together and easy to confuse, so:
        0.1037  doubled HANDS per round        <- the one this sum needs
        0.1026  ROUNDS containing a double     <- ``Stats.double_rate``, printed
        0.0955  rounds that doubled and did NOT split
    An earlier draft of this docstring said "doubles happen on 9.6 percent of
    rounds", which named the second and measured the third.  It is the first
    that belongs in the arithmetic: a round that splits and doubles twice puts
    up two extra units, and the double_rate counts it once.

    Note too that the published triple sums to 99.8, not 100, so it was already
    rounded or assembled from more than one source.  The most likely
    explanation is that the win/loss figures come from a different convention
    or a different ruleset than the EV figure beside them.

    A SECOND ENGINE AGREES WITH THIS ONE, so the disagreement is no longer
    hedged.  A from-scratch round engine sharing only bj.core and
    bj.strategy - its own shoe (a shuffled 312-card list, not a partial
    Fisher-Yates over a reused array), its own deal, its own peek, its own
    split logic, its own settlement, calling ``basic_action`` directly instead
    of compiling it - returns, over 25,200,000 rounds:

        win  (per hand)  43.591% +/- 0.010%   this engine 43.600%  (0.7 sd)
        loss (per hand)  47.932% +/- 0.010%   this engine 47.935%  (0.2 sd)
        EV per round    -0.004085 +/- 0.00023  this engine -0.003888  (0.7 sd)

    Two independent implementations landing within one standard error of each
    other, on numbers that sit 169 and 140 standard errors from the published
    pair, is not a coincidence in either engine.  Together with the exact
    solver's agreement on EV and the exact stand-only cross-check on the deal
    and the settlement, the published win/loss pair is the thing that is wrong.
    REFERENCE still quotes it, and the checks still print MISS, because
    REFERENCE is a record of what the source says, not a target.

HONESTY
    Every expected value this module can produce is negative.  It reports the
    number it computed, including when that number disagrees with the published
    reference; the verification helper prints both side by side and marks the
    gap rather than moving the code until it closes.
"""
from __future__ import annotations

import math
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np

from .core import (
    CARDS_PER_DECK,
    STANDARD,
    DOUBLE,
    HIT,
    RANKS,
    RANK_INDEX,
    Rules,
    SPLIT,
    STAND,
    hand_total,
    normalize,
    normalize_hand,
)
from .strategy import DEALER_UPS, basic_action
# Private on purpose, imported on purpose.  The compiled key below has to
# reproduce bj.strategy's notion of a "small" card exactly; taking the set from
# that module means a rename or a widening breaks this import loudly instead of
# leaving a stale copy of the rule answering questions in a lookup array.
from .strategy import _SOFT18_ACE_SMALL_RANKS as _STRATEGY_SMALL_RANKS

__all__ = [
    'Cards', 'RoundResult', 'Stats', 'Check', 'Verification',
    'play_round', 'simulate', 'simulate_parallel', 'outcome_distributions',
    'compiled_action', 'verification_run', 'REFERENCE',
]

# --- rank plumbing ---------------------------------------------------------
# Everything in the hot loop works on rank INDICES (ints), never on strings.
# The strings only reappear at the boundary: table generation and the optional
# custom-strategy hook.

_ACE = RANK_INDEX['A']
_TEN = RANK_INDEX['T']
_FOUR = RANK_INDEX['4']
_FIVE = RANK_INDEX['5']
_TWO = RANK_INDEX['2']
_THREE = RANK_INDEX['3']

#: the ranks bj.strategy's soft-18-vs-ace exception calls "small".  Derived
#: from that module's own constant rather than retyped, so a widening is picked
#: up here automatically and a rename breaks the import at the top of this file
#: instead of leaving a stale copy of the rule inside a lookup array.
_SMALL = frozenset(RANK_INDEX[r] for r in _STRATEGY_SMALL_RANKS)

#: card value with every ace counted as 1; the soft +10 is applied separately
_VALUE: tuple[int, ...] = tuple(
    1 if r == 'A' else (10 if r == 'T' else int(r)) for r in RANKS
)

#: rank index -> column in the strategy charts, whose order is 2..9, T, A
_UP_COL: tuple[int, ...] = tuple(DEALER_UPS.index(r) for r in RANKS)

# action codes inside the engine.  Small ints because they index nothing but
# are compared millions of times.
_STAND, _HIT, _DOUBLE, _SPLIT = 0, 1, 2, 3
_ACT_CODE = {STAND: _STAND, HIT: _HIT, DOUBLE: _DOUBLE, SPLIT: _SPLIT}
_ACT_NAME = {_STAND: STAND, _HIT: HIT, _DOUBLE: DOUBLE, _SPLIT: SPLIT}

# flags packed into one int so the round function returns one small tuple
_F_PLAYER_BJ = 1
_F_DEALER_BJ = 2
_F_DOUBLED = 4
_F_SPLIT = 8


# --- the compiled strategy tables ------------------------------------------
# Decision state is (can_double, best total, soft, SHAPE CLASS, upcard).
# The shape class is the whole of what bj.strategy looks at beyond the total,
# and it has four values:
#
#   0  exactly two cards          - gates the double
#   1  three or more cards, no 4 or 5, and not class 3
#   2  three or more cards containing a 4 or a 5
#        1 and 2 together gate the 16 vs 10 composition exception, whose
#        sharper form additionally requires the 4 or the 5
#   3  four or more cards, every one of them small (an ace, a 2 or a 3)
#        gates the soft-18-vs-ace composition exception
#
# Class 3 was added when bj.strategy grew that second exception.  Classes 2 and
# 3 cannot overlap - a 4 and a 5 are not small - so this stays a single flat
# dimension rather than two flags, and the key keeps FIXED ARITY: one integer,
# same shape for every hand.  A variable-width key is how a lookup table starts
# lying.
#
# The alternative was to leave the key alone and special-case the exception in
# this file.  That is rejected on the same grounds as re-typing the charts:
# it makes a second copy of a rule that already exists in bj.strategy, and the
# two copies can drift without anything failing.

_N_TOTAL = 22          # best totals 0..21; only 4..21 are ever reached
_N_SHAPE = 4           # the four classes above
_SHAPE_STRIDE = _N_SHAPE * 10
_DEC_SIZE = 2 * _N_TOTAL * 2 * _SHAPE_STRIDE
#: offset added to a key when the DOUBLE button is available
_CD_STRIDE = _N_TOTAL * 2 * _SHAPE_STRIDE


def _dec_key(cd: int, total: int, soft: int, multi: int, up_col: int) -> int:
    return (((cd * _N_TOTAL + total) * 2 + soft) * _SHAPE_STRIDE
            + multi * 10 + up_col)


def _shape_class(idx: Sequence[int]) -> int:
    """The class above, for a hand given as rank indices."""
    nc = len(idx)
    if nc == 2:
        return 0
    if nc >= 4 and all(c in _SMALL for c in idx):
        return 3
    return 2 if (_FOUR in idx or _FIVE in idx) else 1


def _representative_hands() -> tuple[tuple[str, ...], ...]:
    """Real card lists covering every reachable (total, soft, shape class).

    Two- and three-card combinations cover classes 0, 1 and 2: bj.strategy
    distinguishes "two cards" from "three or more" there, never "three" from
    "five".  Non-pairs are ordered first so that a pair is only ever chosen as
    the representative for a state no non-pair can reach (hard 4 is 2,2 and
    hard 20 is T,T, and there is nothing else they can be).  That matters
    because ``basic_action`` routes pairs through the pair chart even when
    splitting is unavailable.  Those cells agree with the totals chart in every
    case - the pair rows that are not P or Ph are 10,10 stand (= hard 20
    stand), 5,5 double (= hard 10 double), 9,9 vs 7/10/A stand (= hard 18
    stand) and the 7,7 / 6,6 / 4,4 / 3,3 / 2,2 hit cells (= their hard totals
    hit) - but ordering non-pairs first means the table does not depend on that
    agreement holding.

    Class 3 needs its own generation, because it starts at FOUR cards and three
    of anything cannot reach it.  Every all-small multiset of four or more
    cards whose hard total is still live is enumerated - not just the six hands
    that stand, because the class covers cells all over the chart and an
    unfilled cell silently defaults to HIT.  Seven small cards can make a hard
    19, 20 or 21, so the enumeration runs to the total limit rather than
    stopping at six cards; 3,3,3,3,3,3,3 is not reachable under basic strategy
    but ``compiled_action`` is a public function and is allowed to be asked.
    """
    two: list[tuple[str, ...]] = []
    for i in range(10):
        for j in range(i, 10):
            two.append((RANKS[i], RANKS[j]))
    two.sort(key=lambda h: h[0] == h[1])          # pairs last
    three: list[tuple[str, ...]] = []
    for i in range(10):
        for j in range(i, 10):
            for k in range(j, 10):
                three.append((RANKS[i], RANKS[j], RANKS[k]))

    small = sorted(_SMALL)                        # rank indices, ascending
    allsmall: list[tuple[str, ...]] = []

    def grow(prefix: list[int], start: int, hard: int) -> None:
        if len(prefix) >= 4:
            allsmall.append(tuple(RANKS[c] for c in prefix))
        for pos in range(start, len(small)):
            c = small[pos]
            if hard + _VALUE[c] > 21:
                continue
            prefix.append(c)
            grow(prefix, pos, hard + _VALUE[c])
            prefix.pop()

    grow([], 0, 0)
    return tuple(two + three + allsmall)


_REPRESENTATIVES = _representative_hands()


@lru_cache(maxsize=None)
def _tables(rules: Rules, comp16_requires_45: bool):
    """Compile bj.strategy into (decision array, split array).

    Cached on the frozen Rules object, so a run with H17 or no-DAS builds its
    own pair of tables once and then costs nothing.  Roughly 5,000 calls into
    ``basic_action``, about a tenth of a second.
    """
    dec = [_HIT] * _DEC_SIZE
    filled = bytearray(_DEC_SIZE)
    for combo in _REPRESENTATIVES:
        total, soft = hand_total(combo)
        if total > 21:
            continue                     # busted hands have no decision
        s = 1 if soft else 0
        multi = _shape_class([RANK_INDEX[r] for r in combo])
        base = (total * 2 + s) * _SHAPE_STRIDE + multi * 10
        for cd in (0, 1):
            off = cd * _CD_STRIDE
            for up_col, up in enumerate(DEALER_UPS):
                k = off + base + up_col
                if filled[k]:
                    continue
                filled[k] = 1
                adv = basic_action(combo, up, rules,
                                   can_double=bool(cd), can_split=False,
                                   is_split_hand=False,
                                   comp16_requires_45=comp16_requires_45)
                dec[k] = _ACT_CODE[adv.action]

    # Split decisions are a separate, tiny table: the pair chart never depends
    # on whether the DOUBLE button is lit (its non-split cells resolve to hit,
    # stand or double, never to split), so can_double is not part of the key.
    spl = [False] * 100
    for r_i, r in enumerate(RANKS):
        for up_col, up in enumerate(DEALER_UPS):
            adv = basic_action((r, r), up, rules,
                               can_double=True, can_split=True,
                               is_split_hand=False,
                               comp16_requires_45=comp16_requires_45)
            spl[r_i * 10 + up_col] = (adv.action == SPLIT)
    return tuple(dec), tuple(spl)


def compiled_action(cards, dealer_up, rules: Rules = STANDARD, *,
                    can_double: bool, can_split: bool,
                    is_split_hand: bool = False,
                    comp16_requires_45: bool = False) -> str:
    """The compiled table's answer, in the same vocabulary as basic_action.

    Readable equivalent of what the round loop does inline.  Exposed so the
    integrator (and the tests) can compare the compiled strategy against
    ``bj.strategy.basic_action`` directly instead of inferring it from
    simulated results.  This is the slow, obvious version; the round loop
    inlines it for speed and the test suite proves the two agree by replaying
    identical seeds through both.
    """
    idx = [RANK_INDEX[r] for r in normalize_hand(cards)]
    dec, spl = _tables(rules, comp16_requires_45)
    up_col = _UP_COL[RANK_INDEX[normalize(dealer_up)]]

    nc = len(idx)
    hard = sum(_VALUE[c] for c in idx)
    aces = sum(1 for c in idx if c == _ACE)
    if aces and hard + 10 <= 21:
        total, soft = hard + 10, 1
    else:
        total, soft = hard, 0
    if total > 21:
        raise ValueError('busted hand has no decision')

    if can_split and nc == 2 and idx[0] == idx[1] and spl[idx[0] * 10 + up_col]:
        return SPLIT
    if (is_split_hand and idx[0] == _ACE and nc == 2
            and not rules.hit_split_aces and not can_split):
        return STAND
    multi = _shape_class(idx)
    cd = 1 if (can_double and nc == 2) else 0
    return _ACT_NAME[dec[_dec_key(cd, total, soft, multi, up_col)]]


# --- the shoe --------------------------------------------------------------

class Cards:
    """One reusable 312-card array plus a buffered RNG.  Fresh shoe per round.

    ``new_round()`` resets the draw index to zero, which IS the reshuffle: the
    array is always a permutation of the full multiset, because every draw
    swaps rather than removes.  Partial Fisher-Yates then hands out cards
    uniformly without replacement from a complete shoe.

    Random numbers arrive in blocks and are converted with ``.tolist()``.  That
    detail is worth a line: indexing a numpy array yields a numpy scalar, and
    arithmetic on numpy scalars is several times slower than on Python floats,
    which at seven draws per round is most of the difference between hitting
    the speed target and missing it.
    """
    __slots__ = ('_gen', '_arr', '_n', '_i', '_buf', '_pos', '_block')

    def __init__(self, rng=None, decks: int = 6, block: int = 8192):
        self._gen = np.random.default_rng(rng)
        arr: list[int] = []
        for idx, per_deck in enumerate(CARDS_PER_DECK):
            arr.extend([idx] * (per_deck * decks))
        self._arr = arr
        self._n = len(arr)
        self._i = 0
        self._block = block
        self._buf = self._gen.random(block).tolist()
        self._pos = 0

    @property
    def cards_drawn(self) -> int:
        return self._i

    def new_round(self) -> None:
        self._i = 0

    def draw(self) -> int:
        p = self._pos
        if p >= self._block:
            self._buf = self._gen.random(self._block).tolist()
            p = 0
        u = self._buf[p]
        self._pos = p + 1
        i = self._i
        n = self._n
        if i >= n:
            # Unreachable at 6 decks: the worst possible round is four hands of
            # 21 aces plus a 21-card dealer hand, 105 cards.  The check exists
            # so a one-deck experiment fails loudly instead of by IndexError.
            raise RuntimeError('shoe exhausted inside a single round')
        j = i + int(u * (n - i))
        arr = self._arr
        c = arr[j]
        arr[j] = arr[i]
        arr[i] = c
        self._i = i + 1
        return c


# --- results ---------------------------------------------------------------

@dataclass
class RoundResult:
    """What one round returned, in units of the base bet.

    net             signed return on the base bet.  +1.5 is a natural, -2 is a
                    lost double, +3 could be three won split hands.
    wagered         total money put up, base bet included.  Always
                    1 + (doubles and extra split hands), so it is also the
                    check that ``max_extra_units`` was respected.
    n_hands         hands the player finished with, splits included
    dealer_final    dealer's total; > 21 means bust.  21 on a dealer natural.
    player_finals   each hand's final total, in the order played; > 21 is bust
    """
    net: float
    wagered: float
    n_hands: int
    player_bj: bool
    dealer_bj: bool
    doubled: bool
    split: bool
    dealer_final: int
    player_finals: list[int]


@dataclass
class Stats:
    """Aggregate of many rounds.  Rates are per ROUND unless named otherwise.

    ev_per_hand           mean net per round, per unit of BASE bet.  This is
                          the quantity the published "house edge" refers to.
    ev_per_unit_wagered   mean net divided by mean money at risk.  Smaller in
                          magnitude, because doubles and splits are money put
                          up on hands that are better than average.  The
                          published name for it is the element of risk.
    stderr                standard error of ev_per_hand.  Quote it every time
                          you quote the EV; at a million rounds it is still
                          about 0.0012, which is a third of the house edge.
    win_rate/loss_rate/push_rate
                          classified by the sign of the ROUND's net.  A split
                          round that wins one hand and loses the other counts
                          as a push here, because that is what the balance did.
                          The hand_* fields below classify each resolved hand
                          separately; published win/lose/push figures are the
                          hand-level ones and the two differ by a few tenths.
    double_rate/split_rate
                          rounds in which the player doubled / split at least
                          once.
    net_distribution      net -> probability.  Feeds the bet module's DP.
    """
    n: int
    ev_per_hand: float
    ev_per_unit_wagered: float
    stderr: float
    sd_per_hand: float
    win_rate: float
    loss_rate: float
    push_rate: float
    player_bj_rate: float
    dealer_bj_rate: float
    dealer_bust_rate: float
    double_rate: float
    split_rate: float
    net_distribution: dict[float, float]
    hands_per_round: float = 1.0
    wagered_per_round: float = 1.0
    hand_win_rate: float = 0.0
    hand_loss_rate: float = 0.0
    hand_push_rate: float = 0.0

    def report(self) -> str:
        """Plain-text block, computed numbers beside the published reference.

        The reference column is what the handoff appendix quotes.  Any line
        that disagrees is meant to stay disagreeing until someone works out
        why, not until someone edits the code.
        """
        rows = [
            ('rounds', f'{self.n:,}', ''),
            ('EV per hand', f'{self.ev_per_hand:+.5f}', '-0.00410'),
            ('  +/- 1 stderr', f'{self.stderr:.5f}', ''),
            ('EV per unit wagered', f'{self.ev_per_unit_wagered:+.5f}', ''),
            ('SD per hand', f'{self.sd_per_hand:.4f}', '1.15'),
            ('win rate (round)', f'{self.win_rate * 100:.2f}%',
             '~42.2% - KNOWN DISAGREEMENT, see module docstring'),
            ('loss rate (round)', f'{self.loss_rate * 100:.2f}%',
             '~49.1% - KNOWN DISAGREEMENT, see module docstring'),
            ('push rate (round)', f'{self.push_rate * 100:.2f}%', '~8.5%'),
            ('win rate (hand)', f'{self.hand_win_rate * 100:.2f}%',
             '~42.2% - KNOWN DISAGREEMENT, see module docstring'),
            ('loss rate (hand)', f'{self.hand_loss_rate * 100:.2f}%',
             '~49.1% - KNOWN DISAGREEMENT, see module docstring'),
            ('push rate (hand)', f'{self.hand_push_rate * 100:.2f}%', '~8.5%'),
            ('player natural', f'{self.player_bj_rate * 100:.2f}%', '~4.75%'),
            ('dealer natural', f'{self.dealer_bj_rate * 100:.2f}%', '~4.75%'),
            ('dealer bust', f'{self.dealer_bust_rate * 100:.2f}%', '~28.3%'),
            ('doubled', f'{self.double_rate * 100:.2f}%', ''),
            ('split', f'{self.split_rate * 100:.2f}%', ''),
            ('hands per round', f'{self.hands_per_round:.4f}', ''),
            ('wagered per round', f'{self.wagered_per_round:.4f}', ''),
        ]
        w = max(len(r[0]) for r in rows)
        out = [f'{a.ljust(w)}  {b:>12}  {c}' for a, b, c in rows]
        if self.ev_per_hand >= 0.0:
            # Honesty rule, enforced in the one place a reader would be misled.
            # A short run can print a positive mean; that is sampling noise,
            # and saying so beside the number is cheaper than hoping nobody
            # screenshots it.
            out.append('')
            out.append(f'NOTE: the sampled mean is positive at n={self.n:,}. '
                       f'That is noise, not an edge - the standard error is '
                       f'{self.stderr:.5f}, so this run cannot even resolve '
                       f'the sign. There is no player edge in this game at '
                       f'any bet size.')
        out.append('')
        out.append('net distribution (per unit of base bet):')
        for k in sorted(self.net_distribution):
            out.append(f'  {k:+6.2f}  {self.net_distribution[k] * 100:8.4f}%')
        return '\n'.join(out)


# --- the round -------------------------------------------------------------

def _dealer_finish(draw, hard: int, aces: int, s17: bool) -> int:
    """Play the dealer out and return the final total (> 21 means bust)."""
    while True:
        if aces and hard + 10 <= 21:
            best, soft = hard + 10, True
        else:
            best, soft = hard, False
        if best > 17:
            return best
        if best == 17 and (s17 or not soft):
            return best
        c = draw()
        hard += _VALUE[c]
        if c == _ACE:
            aces += 1


def _play(cards: Cards, cfg, dec, spl, max_extra, strategy):
    """One round.  Returns a flat tuple; RoundResult is built from it by
    ``play_round``.  ``simulate`` consumes the tuple directly, because
    allocating a dataclass per round costs about a microsecond and at two
    million rounds that is two seconds spent on a shape nobody reads.

    cfg is a plain tuple of the rule scalars.  Reading them off the frozen
    dataclass inside the loop would be a dict lookup per access.
    """
    s17, das, max_hands, resplit_aces, hit_split_aces, bj_pay = cfg
    draw = cards.draw
    SMALL = _SMALL          # local: membership-tested on every card drawn
    cards.new_round()

    # Deal in table order: player, dealer up, player, dealer hole.
    p1 = draw()
    up = draw()
    p2 = draw()
    hole = draw()
    up_col = _UP_COL[up]

    d_hard = _VALUE[up] + _VALUE[hole]
    d_aces = (1 if up == _ACE else 0) + (1 if hole == _ACE else 0)
    # exactly one ace plus a ten is the only way to make 21 on two cards
    dealer_bj = (d_aces == 1 and d_hard == 11)
    player_bj = ((p1 == _ACE and p2 == _TEN) or (p1 == _TEN and p2 == _ACE))

    # --- the peek.  Happens BEFORE the player acts, so no money can be added
    # to a round the dealer has already won.
    if dealer_bj:
        if player_bj:
            return (0.0, 1.0, 1, _F_PLAYER_BJ | _F_DEALER_BJ, 21, [21], 0, 0, 1)
        ph = _VALUE[p1] + _VALUE[p2]
        if (p1 == _ACE or p2 == _ACE) and ph + 10 <= 21:
            ph += 10
        return (-1.0, 1.0, 1, _F_DEALER_BJ, 21, [ph], 0, 1, 0)

    # --- player natural.  Paid immediately at rules.blackjack_payout.  The
    # dealer is still played out; see APPROXIMATIONS note 2.
    if player_bj:
        d_final = _dealer_finish(draw, d_hard, d_aces, s17)
        return (bj_pay, 1.0, 1, _F_PLAYER_BJ, d_final, [21], 1, 0, 0)

    # --- the player's hands.  A work list, appended to on a split, so a
    # resplit is just another entry rather than a special case.
    # entry = [hard total, aces, ncards, has a 4 or 5, first card, bet,
    #          is a split hand, card list, every card so far is small]
    # "small" is the running form of the shape class 3 test; see _shape_class.
    hands = [[_VALUE[p1] + _VALUE[p2],
              (1 if p1 == _ACE else 0) + (1 if p2 == _ACE else 0),
              2,
              p1 == _FOUR or p1 == _FIVE or p2 == _FOUR or p2 == _FIVE,
              p1,
              1.0,
              False,
              [p1, p2],
              p1 in SMALL and p2 in SMALL]]
    finals: list[int] = []
    bets: list[float] = []
    n_extra = 0
    doubled = False
    did_split = False

    i = 0
    while i < len(hands):
        hard, aces, nc, has45, first, bet, issplit, hc, small = hands[i]
        if nc == 1:
            # A hand created by a split waits for its second card until it is
            # its turn, which is the order the table deals in.
            c = draw()
            hc.append(c)
            hard += _VALUE[c]
            if c == _ACE:
                aces += 1
            if c == _FOUR or c == _FIVE:
                has45 = True
            if c not in SMALL:
                small = False
            nc = 2

        while True:
            if aces and hard + 10 <= 21:
                best, soft = hard + 10, 1
            else:
                best, soft = hard, 0
            if best > 21:
                break

            can_split = (nc == 2 and hc[0] == hc[1]
                         and len(hands) < max_hands
                         and (max_extra is None or n_extra < max_extra)
                         and not (issplit and first == _ACE and not resplit_aces))

            # Split aces take one card and the hand is over.  That is a table
            # rule, not a strategy choice, so it is enforced here and a custom
            # strategy never gets asked.  Checked after can_split so that a
            # legal resplit of A,A still happens.
            if (issplit and first == _ACE and not hit_split_aces
                    and not can_split):
                break

            can_double = (nc == 2 and (not issplit or das)
                          and (max_extra is None or n_extra < max_extra))

            if strategy is None:
                if can_split and spl[hc[0] * 10 + up_col]:
                    act = _SPLIT
                else:
                    cd = _CD_STRIDE if can_double else 0
                    # inlined _shape_class, same order of tests
                    if nc == 2:
                        multi = 0
                    elif nc >= 4 and small:
                        multi = 30
                    elif has45:
                        multi = 20
                    else:
                        multi = 10
                    act = dec[cd + (best * 2 + soft) * _SHAPE_STRIDE
                              + multi + up_col]
            else:
                word = strategy(tuple(RANKS[c] for c in hc), RANKS[up],
                                can_double=can_double, can_split=can_split,
                                is_split_hand=issplit, hand_count=len(hands))
                act = _ACT_CODE[word]
                if act == _SPLIT and not can_split:
                    raise ValueError('strategy returned SPLIT where splitting '
                                     'is not available')
                if act == _DOUBLE and not can_double:
                    raise ValueError('strategy returned DOUBLE where doubling '
                                     'is not available')

            if act == _STAND:
                break

            if act == _SPLIT:
                n_extra += 1
                did_split = True
                x = hc[0]
                xv = _VALUE[x]
                xa = 1 if x == _ACE else 0
                x45 = (x == _FOUR or x == _FIVE)
                xsmall = x in SMALL
                # the sibling hand waits with one card; it draws when reached
                hands.append([xv, xa, 1, x45, x, 1.0, True, [x], xsmall])
                c = draw()
                hc = [x, c]
                hard = xv + _VALUE[c]
                aces = xa + (1 if c == _ACE else 0)
                nc = 2
                has45 = x45 or (c == _FOUR or c == _FIVE)
                small = xsmall and c in SMALL
                issplit = True
                first = x
                continue

            if act == _DOUBLE:
                n_extra += 1
                doubled = True
                bet += bet
                c = draw()
                hc.append(c)
                hard += _VALUE[c]
                if c == _ACE:
                    aces += 1
                nc += 1
                # `small` is deliberately not updated: the hand is finished on
                # the next line and nothing reads it again
                # exactly one card, then the hand is finished
                if aces and hard + 10 <= 21:
                    best = hard + 10
                else:
                    best = hard
                break

            # HIT
            c = draw()
            hc.append(c)
            hard += _VALUE[c]
            if c == _ACE:
                aces += 1
            if c == _FOUR or c == _FIVE:
                has45 = True
            if c not in SMALL:
                small = False
            nc += 1

        finals.append(best)
        bets.append(bet)
        i += 1

    d_final = _dealer_finish(draw, d_hard, d_aces, s17)

    net = 0.0
    wagered = 0.0
    hw = hl = hp = 0
    for k in range(len(finals)):
        f = finals[k]
        b = bets[k]
        wagered += b
        if f > 21:
            net -= b
            hl += 1
        elif d_final > 21 or f > d_final:
            net += b
            hw += 1
        elif f < d_final:
            net -= b
            hl += 1
        else:
            hp += 1

    flags = (_F_DOUBLED if doubled else 0) | (_F_SPLIT if did_split else 0)
    return (net, wagered, len(finals), flags, d_final, finals, hw, hl, hp)


def _cfg(rules: Rules):
    return (rules.s17, rules.das, rules.max_hands, rules.resplit_aces,
            rules.hit_split_aces, float(rules.blackjack_payout))


def _check_rules(rules: Rules) -> None:
    if not rules.peek:
        raise ValueError(
            'rules.peek=False is not simulated. The charts in bj.strategy are '
            'peek charts; a no-hole-card game changes both the strategy and '
            'the settlement of doubles and splits against a dealer natural. '
            'Simulating it here would return a confident number about a game '
            'nobody is playing.')


def play_round(rng, rules: Rules = STANDARD, *,
               max_extra_units: int | None = None,
               strategy: Callable[..., str] | None = None,
               comp16_requires_45: bool = False) -> RoundResult:
    """Play one complete round and return what it paid.

    rng             a ``Cards`` instance for speed, or anything numpy's
                    ``default_rng`` accepts (int seed, SeedSequence, Generator,
                    None) for convenience.  The convenience path builds a new
                    shoe object per call, which costs more than the round does;
                    ``simulate`` reuses one ``Cards`` and so should any other
                    loop.
    max_extra_units how many units BEYOND the base bet the player can still
                    commit.  None is unlimited.  0 is an all-in bet: DOUBLE and
                    SPLIT are unavailable because there is no money to add, and
                    the strategy falls back through the chart's own hierarchy
                    (D becomes hit, Ds becomes stand, a declined split is
                    played as its total) rather than being clamped here.
    strategy        optional callable
                    ``f(cards, up, *, can_double, can_split, is_split_hand,
                    hand_count) -> 'H'|'S'|'D'|'P'`` used instead of the
                    compiled basic-strategy tables.  Card ranks are strings.
                    Roughly twenty times slower; it exists so error-rate and
                    alternative-strategy studies do not need a second engine.
    """
    _check_rules(rules)
    if not isinstance(rng, Cards):
        rng = Cards(rng, decks=rules.decks, block=64)
    dec, spl = _tables(rules, comp16_requires_45)
    (net, wagered, n_hands, flags, d_final,
     finals, _hw, _hl, _hp) = _play(rng, _cfg(rules), dec, spl,
                                    max_extra_units, strategy)
    return RoundResult(
        net=net,
        wagered=wagered,
        n_hands=n_hands,
        player_bj=bool(flags & _F_PLAYER_BJ),
        dealer_bj=bool(flags & _F_DEALER_BJ),
        doubled=bool(flags & _F_DOUBLED),
        split=bool(flags & _F_SPLIT),
        dealer_final=d_final,
        player_finals=list(finals),
    )


# --- accumulation ----------------------------------------------------------
# Workers return sufficient statistics, not Stats, so that merging two chunks
# is arithmetic rather than an average of averages.

@dataclass
class _Accum:
    n: int = 0
    sum_net: float = 0.0
    sum_net2: float = 0.0
    sum_wagered: float = 0.0
    hands: int = 0
    wins: int = 0
    losses: int = 0
    pushes: int = 0
    hand_wins: int = 0
    hand_losses: int = 0
    hand_pushes: int = 0
    player_bj: int = 0
    dealer_bj: int = 0
    dealer_bust: int = 0
    doubles: int = 0
    splits: int = 0
    nets: dict[float, int] = field(default_factory=dict)


def _merge(parts: Sequence[_Accum]) -> _Accum:
    out = _Accum()
    for p in parts:
        out.n += p.n
        out.sum_net += p.sum_net
        out.sum_net2 += p.sum_net2
        out.sum_wagered += p.sum_wagered
        out.hands += p.hands
        out.wins += p.wins
        out.losses += p.losses
        out.pushes += p.pushes
        out.hand_wins += p.hand_wins
        out.hand_losses += p.hand_losses
        out.hand_pushes += p.hand_pushes
        out.player_bj += p.player_bj
        out.dealer_bj += p.dealer_bj
        out.dealer_bust += p.dealer_bust
        out.doubles += p.doubles
        out.splits += p.splits
        for k, v in p.nets.items():
            out.nets[k] = out.nets.get(k, 0) + v
    return out


def _stats(acc: _Accum) -> Stats:
    n = acc.n
    if n == 0:
        raise ValueError('no rounds simulated')
    mean = acc.sum_net / n
    if n > 1:
        var = (acc.sum_net2 - n * mean * mean) / (n - 1)
    else:
        var = 0.0
    sd = math.sqrt(var) if var > 0.0 else 0.0
    dist: dict[float, float] = {}
    for k, v in acc.nets.items():
        key = round(k, 6)
        dist[key] = dist.get(key, 0.0) + v / n
    return Stats(
        n=n,
        ev_per_hand=mean,
        ev_per_unit_wagered=(acc.sum_net / acc.sum_wagered
                             if acc.sum_wagered else 0.0),
        stderr=sd / math.sqrt(n),
        sd_per_hand=sd,
        win_rate=acc.wins / n,
        loss_rate=acc.losses / n,
        push_rate=acc.pushes / n,
        player_bj_rate=acc.player_bj / n,
        dealer_bj_rate=acc.dealer_bj / n,
        dealer_bust_rate=acc.dealer_bust / n,
        double_rate=acc.doubles / n,
        split_rate=acc.splits / n,
        net_distribution=dict(sorted(dist.items())),
        hands_per_round=acc.hands / n,
        wagered_per_round=acc.sum_wagered / n,
        hand_win_rate=acc.hand_wins / acc.hands if acc.hands else 0.0,
        hand_loss_rate=acc.hand_losses / acc.hands if acc.hands else 0.0,
        hand_push_rate=acc.hand_pushes / acc.hands if acc.hands else 0.0,
    )


def _run(n: int, rules: Rules, seed, max_extra_units, comp16_requires_45,
         strategy=None) -> _Accum:
    """The hot loop.  Everything it touches is a local."""
    _check_rules(rules)
    dec, spl = _tables(rules, comp16_requires_45)
    cfg = _cfg(rules)
    cards = Cards(seed, decks=rules.decks)
    acc = _Accum()
    nets = acc.nets
    play = _play

    sum_net = sum_net2 = sum_wag = 0.0
    hands = wins = losses = pushes = 0
    hw_t = hl_t = hp_t = 0
    pbj = dbj = dbust = ndouble = nsplit = 0

    for _ in range(n):
        (net, wagered, nh, flags, d_final,
         _finals, hw, hl, hp) = play(cards, cfg, dec, spl,
                                     max_extra_units, strategy)
        sum_net += net
        sum_net2 += net * net
        sum_wag += wagered
        hands += nh
        if net > 0.0:
            wins += 1
        elif net < 0.0:
            losses += 1
        else:
            pushes += 1
        hw_t += hw
        hl_t += hl
        hp_t += hp
        if flags & _F_PLAYER_BJ:
            pbj += 1
        if flags & _F_DEALER_BJ:
            dbj += 1
        if d_final > 21:
            dbust += 1
        if flags & _F_DOUBLED:
            ndouble += 1
        if flags & _F_SPLIT:
            nsplit += 1
        nets[net] = nets.get(net, 0) + 1

    acc.n = n
    acc.sum_net = sum_net
    acc.sum_net2 = sum_net2
    acc.sum_wagered = sum_wag
    acc.hands = hands
    acc.wins = wins
    acc.losses = losses
    acc.pushes = pushes
    acc.hand_wins = hw_t
    acc.hand_losses = hl_t
    acc.hand_pushes = hp_t
    acc.player_bj = pbj
    acc.dealer_bj = dbj
    acc.dealer_bust = dbust
    acc.doubles = ndouble
    acc.splits = nsplit
    return acc


def _seed_sequence(seed) -> np.random.SeedSequence:
    """A SeedSequence from whatever the caller passed, including one of these.

    Both places in this module that subdivide a stream go through here, and
    that is the point.  ``np.random.SeedSequence(x)`` is a TypeError when x is
    already a SeedSequence, so the two-line version of this had to be written
    twice and was written once: ``outcome_distributions`` spawned a child per
    budget and handed it straight to ``simulate_parallel``, which re-seeded from
    it, so every call with workers > 1 raised

        TypeError: SeedSequence expects int or sequence of ints for entropy
                   not SeedSequence(...)

    Nothing caught it because no test in the suite passed ``workers`` to
    ``outcome_distributions`` at all.  Two shipped callers did:
    scripts/run_simulation.py and bj.advisor both default it to the core count,
    so this was the ordinary path, not a corner.

    Spawning from an existing sequence is the documented way to subdivide a
    stream, so the answer is to spawn from whatever we were given rather than
    to re-seed - and to have exactly one function that decides that.
    """
    if isinstance(seed, np.random.SeedSequence):
        return seed
    return np.random.SeedSequence(seed)


def simulate(n: int, rules: Rules = STANDARD, *, seed=0,
             max_extra_units: int | None = None,
             comp16_requires_45: bool = False,
             strategy: Callable[..., str] | None = None) -> Stats:
    """Play n rounds on one core and summarise them.

    ``seed`` is anything numpy's ``default_rng`` accepts.  The same seed always
    replays the same rounds, which is what makes a regression test possible.
    """
    return _stats(_run(n, rules, seed, max_extra_units, comp16_requires_45,
                       strategy))


def simulate_parallel(n: int, workers: int = 8, **kw) -> Stats:
    """Same numbers as ``simulate``, spread over processes.

    Each worker gets an INDEPENDENT stream from ``SeedSequence.spawn``, not the
    same generator jumped forward and not seed+1: spawning is the documented
    way to get streams that are statistically independent by construction
    rather than by hope.  Because the chunks are independent, merging is just
    summing sufficient statistics, so the merged Stats is exactly the Stats of
    one long run over the same rounds.

    A parallel run is NOT reproducible against a serial run of the same seed -
    the round order differs.  It is reproducible against itself: same seed,
    same worker count, same answer.
    """
    if kw.get('strategy') is not None:
        raise ValueError('simulate_parallel cannot ship a custom strategy to '
                         'a worker process; a callable is not reliably '
                         'picklable. Use simulate() for strategy studies.')
    rules = kw.pop('rules', STANDARD)
    seed = kw.pop('seed', 0)
    max_extra_units = kw.pop('max_extra_units', None)
    comp16 = kw.pop('comp16_requires_45', False)
    kw.pop('strategy', None)
    if kw:
        raise TypeError(f'unexpected keyword arguments: {sorted(kw)}')
    _check_rules(rules)

    workers = max(1, int(workers))
    if workers == 1 or n < 20000:
        # Process startup on Windows costs about a second per worker; below
        # this it is pure loss.
        return _stats(_run(n, rules, seed, max_extra_units, comp16))

    children = _seed_sequence(seed).spawn(workers)
    counts = [n // workers + (1 if i < n % workers else 0)
              for i in range(workers)]
    args = [(counts[i], rules, children[i], max_extra_units, comp16)
            for i in range(workers) if counts[i] > 0]

    import multiprocessing as mp
    with mp.Pool(len(args)) as pool:
        parts = pool.starmap(_run, args)
    return _stats(_merge(parts))


def outcome_distributions(n: int, rules: Rules = STANDARD, *, seed=0,
                          extras: Sequence[int | None] = (0, 1, 2, 3),
                          workers: int = 1,
                          comp16_requires_45: bool = False
                          ) -> dict[int | None, dict[float, float]]:
    """Net-return distribution per unit of BASE bet, one per extras budget.

    This is what the bet module needs and the reason ``max_extra_units``
    exists.  A player betting his whole balance cannot double or split, so his
    round is not the 0.41 percent game; enumerating the distribution for each
    budget is the only way the reach-a-target maths can be honest about that.

    Keys are the ``extras`` values (None means unlimited).  Each value maps net
    return, in units of the base bet, to its probability.  With extras=0 the
    support is exactly {-1, 0, +1, +1.5}.

    Each budget gets its own spawned stream.  Common random numbers across
    budgets were considered and rejected: the card sequences diverge at the
    first differing decision anyway, so the pairing buys nothing and would only
    make the four rows look more comparable than they are.

    With ``workers`` above 1 each budget's child stream is spawned again, once
    per worker.  Spawning from a spawned child is the documented way to build a
    tree of independent streams; see ``_seed_sequence`` for the bug that
    shipped when this file re-seeded instead.
    """
    children = _seed_sequence(seed).spawn(len(extras))
    out: dict[int | None, dict[float, float]] = {}
    for child, e in zip(children, extras):
        if workers > 1:
            st = simulate_parallel(n, workers, rules=rules, seed=child,
                                   max_extra_units=e,
                                   comp16_requires_45=comp16_requires_45)
        else:
            st = simulate(n, rules, seed=child, max_extra_units=e,
                          comp16_requires_45=comp16_requires_45)
        out[e] = st.net_distribution
    return out


# --- verification ----------------------------------------------------------
# The published numbers this engine is checked against, with the tolerance the
# handoff's "Notes for the coder" section allows.  They live in one dict so a
# reader can see every claim the code is making about itself in one place.

#: name -> (reference, low, high, source, known_gap_note).  A non-empty note
#: means this module has already investigated the gap and believes the
#: published number, not the engine, is the thing to doubt; see the module
#: docstring for the arithmetic.  It does NOT widen the tolerance, and the
#: check still prints MISS.
REFERENCE = {
    'ev_per_hand': (-0.0041, -0.0048, -0.0035,
                    'handoff appendix s3/s5: WoO 6ds17r4, house edge ~0.41%', ''),
    'win_rate': (0.422, 0.418, 0.426,
                 'handoff appendix s5: player win ~42.2%',
                 'known disagreement, and it is the reference that is wrong: '
                 'the published win/loss pair implies a ~3% house edge, not '
                 'the 0.41% printed beside it, and a second from-scratch '
                 'engine lands within 2 standard errors of this one. See the '
                 'module docstring.'),
    'loss_rate': (0.491, 0.487, 0.495,
                  'handoff appendix s5: player loss ~49.1%',
                  'known disagreement: see win_rate.'),
    'push_rate': (0.085, 0.081, 0.089,
                  'handoff appendix s5: push ~8.5%', ''),
    'player_bj_rate': (0.0475, 0.0455, 0.0495,
                       'handoff appendix s5: a natural occurs ~4.7% of hands', ''),
    # The 28.3% is the handoff's headline. Its own per-upcard bust table,
    # weighted by upcard and peeked, comes to 0.281899, and this project's
    # exact dealer solver to 0.28192. The band is wide enough that the check
    # passes against either; APPROXIMATIONS note 3 says which one to believe.
    'dealer_bust_rate': (0.283, 0.273, 0.293,
                         'handoff appendix s5: overall dealer bust ~28.3%', ''),
    'sd_per_hand': (1.15, 1.12, 1.18,
                    'handoff appendix s5/s7: SD ~1.15 units per hand', ''),
}


@dataclass
class Check:
    """One published number, the number computed, and the check's own power.

    ``stderr`` is what turns this from a pass/fail into a statement.  A check
    whose acceptance band is narrower than one standard error cannot fail
    honestly and cannot pass honestly either - it is a coin flip dressed as a
    verification - so ``band_sigma`` is printed beside every result and
    ``powered`` says whether the band is worth at least three standard errors
    at this sample size.

    The handoff's band on EV per hand is [-0.0048, -0.0035] around -0.0041, so
    it is not symmetric and ``band_sigma`` takes the TIGHTER half, 0.0006.  At
    the 2,000,000 rounds the same sentence asks for, the standard error of the
    mean is 1.1547/sqrt(2e6) = 0.000817, which makes that band +/-0.73 sigma:
    a perfectly correct engine misses it about two times in five.  Three sigma
    needs (3 x 1.1547/0.0006)^2 = 33.3 million rounds, which is where
    ``verification_run``'s default of 35 million comes from.
    """
    name: str
    computed: float
    reference: float
    low: float
    high: float
    source: str
    known_gap: str = ''
    stderr: float = 0.0

    @property
    def ok(self) -> bool:
        return self.low <= self.computed <= self.high

    @property
    def sigma(self) -> float:
        """How far the computed number sits from the reference, in std errors."""
        if self.stderr <= 0.0:
            return float('nan')
        return (self.computed - self.reference) / self.stderr

    @property
    def band_sigma(self) -> float:
        """Half-width of the acceptance band, in standard errors."""
        if self.stderr <= 0.0:
            return float('inf')
        half = min(self.reference - self.low, self.high - self.reference)
        return half / self.stderr

    @property
    def powered(self) -> bool:
        return self.band_sigma >= 3.0

    def __str__(self) -> str:
        flag = 'ok  ' if self.ok else 'MISS'
        line = (f'{flag} {self.name:<18} computed {self.computed:+.5f}  '
                f'reference {self.reference:+.5f}  '
                f'accept [{self.low:+.5f}, {self.high:+.5f}]  '
                f'off by {self.sigma:+.1f} sigma, band +/-{self.band_sigma:.1f} '
                f'sigma  ({self.source})')
        if not self.powered:
            line += ('\n     UNDERPOWERED: this band is narrower than three '
                     'standard errors at this sample size, so neither its '
                     'pass nor its miss means much. Run more rounds.')
        if not self.ok and self.known_gap:
            line += f'\n     {self.known_gap}'
        return line


@dataclass
class Verification:
    stats: Stats
    checks: list[Check]
    rounds_per_second: float

    @property
    def all_ok(self) -> bool:
        return all(c.ok for c in self.checks)

    @property
    def unexplained(self) -> list[Check]:
        """Checks that miss AND have no investigated explanation on file."""
        return [c for c in self.checks if not c.ok and not c.known_gap]

    @property
    def underpowered(self) -> list[Check]:
        return [c for c in self.checks if not c.powered]

    def report(self) -> str:
        lines = [self.stats.report(), '',
                 f'throughput: {self.rounds_per_second:,.0f} rounds/second',
                 '', 'checks against the published reference:']
        lines += ['  ' + str(c) for c in self.checks]
        if self.underpowered:
            lines.append('')
            lines.append('These bands are narrower than three standard errors '
                         'at n=' + f'{self.stats.n:,}: '
                         + ', '.join(c.name for c in self.underpowered)
                         + '. Their result is close to a coin flip either way.')
            worst = max(self.underpowered, key=lambda c: 1.0 / max(c.band_sigma, 1e-9))
            need = int(self.stats.n * (3.0 / max(worst.band_sigma, 1e-9)) ** 2)
            lines.append(f'{worst.name} would need about {need:,} rounds for '
                         f'its band to be worth three standard errors.')
        if not self.all_ok:
            lines.append('')
            lines.append('At least one number disagrees with the published '
                         'reference. That is reported, not corrected.')
            if self.unexplained:
                lines.append('One or more of the gaps has no explanation on '
                             'file. Work out why before changing a line of '
                             'the engine.')
        return '\n'.join(lines)


def _checks_for(st: Stats) -> list[Check]:
    #: which rates are measured per resolved HAND rather than per round
    per_hand = {'win_rate': 'hand_win_rate',
                'loss_rate': 'hand_loss_rate',
                'push_rate': 'hand_push_rate'}
    hands = max(1.0, st.n * st.hands_per_round)
    out = []
    for name, (ref, lo, hi, src, note) in REFERENCE.items():
        # use the hand-level rates for win/loss/push: the published figures
        # classify resolved hands, not net round outcomes.  Both are reported
        # by Stats and they differ by about two tenths of a point, which is
        # nowhere near the size of the win/loss gap.
        key = per_hand.get(name, name)
        value = getattr(st, key)
        if name == 'ev_per_hand':
            se = st.stderr
        elif name == 'sd_per_hand':
            # normal-theory standard error of a standard deviation.  The net
            # distribution is not normal, so this is an order-of-magnitude
            # figure and is labelled as such rather than trusted to two digits.
            se = st.sd_per_hand / math.sqrt(2.0 * max(1, st.n - 1))
        else:
            denom = hands if name in per_hand else st.n
            se = math.sqrt(max(value * (1.0 - value), 0.0) / denom)
        out.append(Check(name, value, ref, lo, hi, src, note, se))
    return out


def verification_run(n: int = 35_000_000, *, workers: int | None = None,
                     seed=20260902, rules: Rules = STANDARD) -> Verification:
    """Full-size run against the published numbers.  Script-callable.

    The default is 35 million rounds and not the 2 million the handoff's
    "Simulator sanity checks" asks for, because 2 million cannot decide the
    question that section poses.  Its acceptance band on EV per hand is
    -0.0035 to -0.0048 around a reference of -0.0041, so the tighter half is
    0.0006.  The standard error of the mean at 2 million rounds is
    1.1547/sqrt(2e6) = 0.00082, which makes that band +/-0.73 sigma: for an
    engine whose true mean is the exact -0.004044, the chance of landing
    outside it is 0.42.

    Measured, seed 20260902 across 16 workers: 2,000,000 rounds returns
    -0.00362, which is INSIDE the band, and 35,000,000 returns -0.00389, which
    is also inside.  Neither of those is evidence of anything at 2 million -
    that is the whole finding, and it is why the report prints every check's
    power beside its result rather than a bare pass.  35 million rounds is
    where 0.0006 becomes three standard errors.  "At least 2,000,000" is
    satisfied by running more.

    Kept out of the default test run: 35 million rounds is about twenty
    seconds across sixteen workers on an unloaded sixteen-core box, and about
    two minutes on one.  ``python -m bj.simulate`` calls it; ``-n`` overrides.
    """
    if workers is None:
        import os
        workers = max(1, (os.cpu_count() or 1))
    t0 = time.perf_counter()
    if workers > 1:
        st = simulate_parallel(n, workers, rules=rules, seed=seed)
    else:
        st = simulate(n, rules, seed=seed)
    dt = time.perf_counter() - t0
    return Verification(stats=st, checks=_checks_for(st),
                        rounds_per_second=n / dt if dt > 0 else float('inf'))


def main(argv: Sequence[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('-n', '--rounds', type=int, default=35_000_000,
                    help='default 35,000,000: the point at which the '
                         "handoff's own EV tolerance becomes a three-sigma "
                         'test. See verification_run.')
    ap.add_argument('-w', '--workers', type=int, default=None)
    ap.add_argument('-s', '--seed', type=int, default=20260902)
    ap.add_argument('--extras', action='store_true',
                    help='also print the per-budget net distributions')
    a = ap.parse_args(argv)
    v = verification_run(a.rounds, workers=a.workers, seed=a.seed)
    print(v.report())
    if a.extras:
        print()
        print('net distribution by max_extra_units '
              '(0 = all-in: no money left to double or split):')
        each = max(a.rounds // len((0, 1, 2, 3)), 100000)
        d = outcome_distributions(each, seed=a.seed, workers=a.workers or 1)
        for e in sorted(d, key=lambda x: (x is None, x)):
            ev = sum(k * p for k, p in d[e].items())
            var = sum(p * (k - ev) ** 2 for k, p in d[e].items())
            se = math.sqrt(var / each)
            # The standard error is printed next to every one of these because
            # at any affordable sample size the gap between extras=2 and
            # extras=3 is smaller than the noise, and a reader who sees four
            # bare numbers will rank them.
            print(f'  extras={e}: EV {ev:+.5f} +/- {se:.5f}  '
                  f'support {sorted(d[e])}')
        print('  Every one of these is negative in expectation. Where a '
              'sampled mean comes out positive, the standard error beside it '
              'is larger than the mean.')
    # Exit non-zero only for a gap nobody has explained yet.  The two
    # investigated win/loss gaps still print MISS above; suppressing the exit
    # code for them is a decision about CI noise, not about the finding.
    return 1 if v.unexplained else 0


if __name__ == '__main__':
    raise SystemExit(main())
