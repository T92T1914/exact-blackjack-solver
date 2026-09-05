"""Tests for bj.simulate.

Six jobs, in descending order of how expensive the bug would be:

1.  Prove the COMPILED strategy is the same strategy the advisory tool plays.
    The simulator does not call bj.strategy in its hot loop; it compiles it
    into lookup arrays.  If a compiled cell were wrong, every number this
    project quotes would describe a strategy nobody plays, and nothing else in
    the suite would notice.  So the engine is replayed on identical seeds
    against ``basic_action`` itself and the two must agree card for card, and
    ``compiled_action`` is checked against ``basic_action`` on four- and
    five-card hands, which are NOT the hands the tables were generated from,
    and on every live all-small hand up to twenty-one cards, which is where the
    fourth shape class lives.  That fourth class exists because bj.strategy
    grew a second composition exception and the three-class key could not
    express it; the replay test caught that, and it is the reason the key was
    widened rather than the rule copied into bj/simulate.py.

2.  Prove the round mechanics are the table's.  Peek before the player acts,
    a natural pays 3:2 but a split 21 does not, one card on a double and only
    on two cards, split limits, DAS, split aces, and above all that
    ``max_extra_units`` really does stop money going onto the table - that
    parameter is the entire honesty of the bet analysis downstream.

3.  Prove the dealing and settlement are right by comparing them against EXACT
    combinatorics rather than against another simulation.  A player who always
    stands on his first two cards is solvable in closed form through
    bj.dealer, so the deal, the peek, the natural payout and the settlement
    comparison can be checked with no sampling error on the reference side.

4.  Compare the aggregate output with the published reference and REPORT the
    gaps.  Two of them do not close; see ``test_published_win_loss_split_is_a
    _known_disagreement``, which pins the size of the gap so that nobody
    quietly narrows it and nobody quietly forgets it.

5.  COVER THE MULTI-WORKER PATH.  This file used to contain zero occurrences of
    the word "workers" outside ``simulate_parallel``'s own tests, so
    ``outcome_distributions(..., workers=N)`` was entirely uncovered - and it
    raised TypeError on every call, because it spawned a SeedSequence child and
    handed it to a function that re-seeded from it.  The crash was the cheap
    half of that hole.  The expensive half is the failure it hides: four
    workers running the SAME stream would return a number that looks fine and
    a standard error that is wrong by a factor of two, everywhere in the
    project.  So the tests below check both that the parallel answer agrees
    with the serial one AND that the four streams are actually different, with
    a control showing the difference test can fail.

6.  PIN THE NUMBERS THE MODULE DOCSTRING QUOTES.  Where that docstring makes an
    arithmetic argument - the double decomposition, the dealer bust rate, the
    all-in distribution - the numbers in it are measured here, so the argument
    can be checked rather than believed.  A docstring number nobody recomputes
    is how the "9.6 percent of rounds" claim survived for as long as it did.

The heavy statistical runs are marked ``slow`` AND skipped unless BJ_SLOW is
set, so ``python -m pytest tests/ -q`` stays quick.  The marker is not
registered in a pytest.ini because this module does not own that file; the
resulting UnknownMark warning is cosmetic, and one line
(``markers = slow: ...``) in the project's pytest config removes it.
"""
from __future__ import annotations

import itertools
import math
import os
import time
from functools import lru_cache

import pytest

import numpy as np

from bj.core import (
    CARDS_PER_DECK,
    STANDARD,
    RANKS,
    RANK_INDEX,
    Rules,
    fresh_shoe,
    hand_total,
    remove_card,
    shoe_size,
)
from bj.dealer import IBUST, dealer_distribution
from bj.simulate import (
    Cards,
    REFERENCE,
    RoundResult,
    Stats,
    compiled_action,
    outcome_distributions,
    play_round,
    simulate,
    simulate_parallel,
    verification_run,
)
from bj.simulate import _Accum, _merge, _seed_sequence, _shape_class, _stats
from bj.strategy import DEALER_UPS, basic_action

S17_DAS = Rules()                                  # the original table
NO_DAS = Rules(das=False)
H17 = Rules(s17=False)
LIBERAL = Rules(resplit_aces=True, hit_split_aces=True)
# the two unknown-at-the-table flags, separated: a game that lets you draw to
# split aces but not resplit them is the awkward combination, because A,A on a
# split hand then falls through the pair chart to a soft 12 that must hit
DRAW_ACES_ONLY = Rules(hit_split_aces=True)
TWO_HANDS = Rules(max_hands=2)

ALL_RULES = (S17_DAS, NO_DAS, H17, LIBERAL, DRAW_ACES_ONLY, TWO_HANDS)

SLOW = pytest.mark.skipif(
    not os.environ.get('BJ_SLOW'),
    reason='heavy statistical run; set BJ_SLOW=1 to include it',
)


# --- helpers ---------------------------------------------------------------

class Recorder:
    """A strategy hook that plays real basic strategy and keeps the receipts.

    Used two ways: as the reference strategy in the replay test, and as a
    window onto what the engine actually offered the player, which is the only
    way to assert things like "a split ace is never asked to act" from
    outside.
    """

    def __init__(self, rules: Rules = STANDARD):
        self.rules = rules
        self.contexts = []       # (cards, up, can_double, can_split, is_split, n)
        self.actions = []

    def __call__(self, cards, up, *, can_double, can_split, is_split_hand,
                 hand_count):
        act = basic_action(cards, up, self.rules,
                           can_double=can_double, can_split=can_split,
                           is_split_hand=is_split_hand,
                           hand_count=hand_count).action
        self.contexts.append((cards, up, can_double, can_split, is_split_hand,
                              hand_count))
        self.actions.append(act)
        return act


def always_stand(cards, up, **kw):
    return 'S'


def run_rounds(n, rules=STANDARD, *, seed=12345, **kw):
    cards = Cards(seed, decks=rules.decks)
    return [play_round(cards, rules, **kw) for _ in range(n)]


@lru_cache(maxsize=None)
def moderate_run(n=400000, seed=20260902):
    """One shared 400,000 round run.  Several tests interrogate the same
    numbers and there is no reason to pay for the rounds more than once."""
    return simulate(n, seed=seed)


@lru_cache(maxsize=None)
def exact_stand_game(rules: Rules = STANDARD):
    """(EV, win, loss, push) for a player who always stands on two cards.

    Exact.  Enumerates the player's two cards and the dealer upcard with true
    without-replacement probabilities, applies the peek by hand, and gets the
    dealer's outcome distribution from bj.dealer, which is combinatorial.  No
    sampling anywhere on this side of the comparison.

    Why this game: it strips out every strategy decision and leaves precisely
    the parts of the round engine that have no other independent check - the
    deal order, the peek, the 3:2 natural, and the settlement comparison.
    """
    shoe0 = fresh_shoe(rules.decks)
    n0 = shoe_size(shoe0)
    ev = win = loss = push = 0.0
    for a in range(10):
        if shoe0[a] == 0:
            continue
        pa = shoe0[a] / n0
        s1 = list(shoe0)
        s1[a] -= 1
        for u in range(10):
            if s1[u] == 0:
                continue
            pu = s1[u] / (n0 - 1)
            s2 = list(s1)
            s2[u] -= 1
            for b in range(10):
                if s2[b] == 0:
                    continue
                p = pa * pu * (s2[b] / (n0 - 2))
                s3 = list(s2)
                s3[b] -= 1
                shoe = tuple(s3)
                up = RANKS[u]
                ptot, _ = hand_total((RANKS[a], RANKS[b]))
                player_bj = (ptot == 21)

                nat_hole = None
                if up == 'A':
                    nat_hole = RANK_INDEX['T']
                elif up == 'T':
                    nat_hole = RANK_INDEX['A']
                p_nat = (shoe[nat_hole] / shoe_size(shoe)
                         if nat_hole is not None else 0.0)

                if p_nat > 0.0:                      # dealer natural, peeked
                    q = p * p_nat
                    if player_bj:
                        push += q
                    else:
                        ev -= q
                        loss += q

                rest = p * (1.0 - p_nat)
                if rest <= 0.0:
                    continue
                if player_bj:
                    ev += rest * rules.blackjack_payout
                    win += rest
                    continue
                dist = dealer_distribution(up, shoe, rules, peek_resolved=True)
                for k, dtot in enumerate((17, 18, 19, 20, 21)):
                    q = rest * dist[k]
                    if ptot > dtot:
                        ev += q
                        win += q
                    elif ptot < dtot:
                        ev -= q
                        loss += q
                    else:
                        push += q
                q = rest * dist[IBUST]
                ev += q
                win += q
    return ev, win, loss, push


# ===========================================================================
# 1. the compiled strategy IS bj.strategy
# ===========================================================================

@pytest.mark.parametrize('rules', ALL_RULES,
                         ids=('standard', 'no-das', 'h17', 'liberal',
                              'draw-aces-only', 'max2'))
@pytest.mark.parametrize('extra', (None, 0, 1, 2))
def test_compiled_engine_replays_basic_action_exactly(rules, extra):
    """Same seed, two strategies, identical rounds.

    The engine's inline table lookup and bj.strategy.basic_action are given
    the same shoe.  Because a different action would draw a different card and
    every card after it would differ, ANY disagreement in ANY cell shows up as
    a diverged round, not as a slightly different average.  This is the test
    that makes "the tables are generated, not retyped" a claim rather than a
    hope.
    """
    fast = Cards(20260902, decks=rules.decks)
    slow = Cards(20260902, decks=rules.decks)
    ref = Recorder(rules)
    for i in range(2500):
        a = play_round(fast, rules, max_extra_units=extra)
        b = play_round(slow, rules, max_extra_units=extra, strategy=ref)
        assert a == b, f'round {i} diverged: compiled {a} vs basic_action {b}'


@pytest.mark.parametrize('up', DEALER_UPS)
def test_compiled_action_matches_basic_action_on_long_hands(up):
    """Four- and five-card hands were never used to build the tables.

    The lookup arrays were generated from two- and three-card representatives,
    on the argument that bj.strategy only ever distinguishes "two cards" from
    "three or more".  This test is where that argument gets checked instead of
    asserted: every four- and five-card hand that is still alive is looked up
    both ways.
    """
    checked = 0
    for i in range(10):
        for j in range(i, 10):
            for k in range(j, 10):
                for m in range(k, 10):
                    for extra in ((), *[(RANKS[q],) for q in range(m, 10)]):
                        hand = (RANKS[i], RANKS[j], RANKS[k], RANKS[m]) + extra
                        total, _ = hand_total(hand)
                        if total > 21:
                            continue
                        for cd in (False, True):
                            want = basic_action(hand, up, STANDARD,
                                                can_double=cd,
                                                can_split=False).action
                            got = compiled_action(hand, up, STANDARD,
                                                  can_double=cd,
                                                  can_split=False)
                            assert got == want, (hand, up, cd, got, want)
                            checked += 1
    # 774 distinct live 4- and 5-card hands per upcard, each looked up with
    # the double button on and off
    assert checked == 1548


@pytest.mark.parametrize('up', DEALER_UPS)
def test_compiled_split_decisions_match_basic_action(up):
    for r in RANKS:
        want = basic_action((r, r), up, STANDARD,
                            can_double=True, can_split=True).action
        got = compiled_action((r, r), up, STANDARD,
                              can_double=True, can_split=True)
        assert got == want, (r, up, got, want)


@pytest.mark.parametrize('up', DEALER_UPS)
def test_split_table_does_not_depend_on_the_double_button(up):
    """The engine's split table is keyed on (pair, upcard) only.

    That is legitimate only because no pair cell resolves to SPLIT for one
    value of can_double and something else for the other.  If bj.strategy ever
    changed so that it did, this test fails before the omission becomes a
    silent wrong answer.
    """
    for r in RANKS:
        a = basic_action((r, r), up, STANDARD, can_double=True, can_split=True)
        b = basic_action((r, r), up, STANDARD, can_double=False, can_split=True)
        assert (a.action == 'P') == (b.action == 'P'), (r, up)


def test_compiled_action_refuses_a_busted_hand():
    with pytest.raises(ValueError):
        compiled_action(('T', 'T', 'T'), '6', can_double=False, can_split=False)


# --- the shape class, which is the compiled key's only concession to
# --- composition-dependent play

#: bj.strategy's soft-18-vs-ace exception, enumerated with the exact solver and
#: pinned with its EV gains in tests/test_strategy.py.
#: The three HITs are the whole reason the rule is not just "four or more
#: cards"; a compiled key that gets the six STANDs and also stands on these has
#: implemented the naive version.
SOFT18_ACE_STAND = (('A', 'A', '3', '3'), ('A', '2', '2', '3'),
                    ('A', 'A', 'A', '2', '3'), ('A', 'A', '2', '2', '2'),
                    ('A', 'A', 'A', 'A', 'A', '3'),
                    ('A', 'A', 'A', 'A', '2', '2'))
SOFT18_ACE_HIT = (('A', 'A', '2', '4'), ('A', 'A', 'A', '5'),
                  ('A', 'A', 'A', 'A', '4'))


@pytest.mark.parametrize('hand', SOFT18_ACE_STAND)
def test_compiled_key_carries_the_soft18_vs_ace_exception(hand):
    assert compiled_action(hand, 'A', can_double=False, can_split=False) == 'S'


@pytest.mark.parametrize('hand', SOFT18_ACE_HIT)
def test_compiled_key_does_not_over_apply_the_soft18_exception(hand):
    """A key that stands on these has implemented "4+ cards" instead of
    "4+ cards and every non-ace is a 2 or a 3"."""
    assert compiled_action(hand, 'A', can_double=False, can_split=False) == 'H'


def test_shape_class_is_four_valued_and_the_classes_do_not_overlap():
    """Fixed arity, four classes, and 2 and 3 mutually exclusive by
    construction: a 4 or a 5 is not a small card, so no hand is both."""
    idx = [RANK_INDEX[r] for r in ('A', '7')]
    assert _shape_class(idx) == 0
    assert _shape_class([RANK_INDEX[r] for r in ('T', '6', '2')]) == 1
    assert _shape_class([RANK_INDEX[r] for r in ('T', '4', '2')]) == 2
    assert _shape_class([RANK_INDEX[r] for r in ('A', 'A', '3', '3')]) == 3
    # three small cards are still class 1: the exception starts at four
    assert _shape_class([RANK_INDEX[r] for r in ('A', '2', '3')]) == 1
    # one big card takes an otherwise-small hand back out of class 3
    assert _shape_class([RANK_INDEX[r] for r in ('A', '2', '3', '9')]) == 1


def test_the_small_rank_set_is_bj_strategys_own():
    """Not a copy.  If bj.strategy widens or renames its notion of a small
    card, bj.simulate must fail loudly rather than keep answering the old
    question out of a lookup array."""
    from bj.simulate import _SMALL
    from bj.strategy import _SOFT18_ACE_SMALL_RANKS
    assert {RANKS[i] for i in _SMALL} == set(_SOFT18_ACE_SMALL_RANKS)


def test_compiled_action_matches_basic_action_on_every_all_small_hand():
    """Class 3 covers cells all over the chart, not just soft 18 vs an ace.

    An unfilled cell in the decision array silently reads back as HIT, so every
    live all-small hand of four or more cards is looked up both ways - up to
    twenty-one aces, well past the five-card limit of the general test above,
    because seven small cards can make a hard 21 and ``compiled_action`` is a
    public function that is allowed to be asked about one.
    """
    checked = 0
    for k in range(4, 22):
        for hand in itertools.combinations_with_replacement(('A', '2', '3'), k):
            if hand_total(hand)[0] > 21:
                continue
            for up in DEALER_UPS:
                for cd in (False, True):
                    want = basic_action(hand, up, STANDARD, can_double=cd,
                                        can_split=False).action
                    got = compiled_action(hand, up, STANDARD, can_double=cd,
                                          can_split=False)
                    assert got == want, (hand, up, cd, got, want)
                    checked += 1
    assert checked == 7720


# ===========================================================================
# 2. round mechanics
# ===========================================================================

def test_round_invariants():
    for r in run_rounds(20000, seed=101):
        assert isinstance(r, RoundResult)
        assert 1 <= r.n_hands <= STANDARD.max_hands
        assert len(r.player_finals) == r.n_hands
        # every unit on the table is either the base bet, a split hand or a
        # double; nothing else can add money
        assert r.n_hands <= r.wagered <= 2 * r.n_hands
        assert r.wagered == int(r.wagered)
        assert r.dealer_final >= 17
        # net can only move in half units, and only the 3:2 natural makes a half
        assert abs(round(r.net * 2) - r.net * 2) < 1e-12
        if r.net != 1.5:
            assert abs(r.net) <= r.wagered
        if not r.split:
            assert r.n_hands == 1
        if not r.split and not r.doubled:
            assert r.wagered == 1.0


def test_dealer_natural_ends_the_round_before_any_money_goes_on():
    """The peek is not cosmetic: it is worth 0.11 percent, and getting it wrong
    would let the player double into a hand the dealer has already won."""
    seen = 0
    for r in run_rounds(30000, seed=202):
        if not r.dealer_bj:
            continue
        seen += 1
        assert r.n_hands == 1
        assert r.wagered == 1.0
        assert not r.doubled and not r.split
        assert r.dealer_final == 21
        assert r.net == (0.0 if r.player_bj else -1.0)
    assert seen > 800, 'dealer naturals should be about 4.75% of rounds'


def test_player_natural_pays_three_to_two_and_ends_the_round():
    seen = 0
    for r in run_rounds(30000, seed=303):
        if not r.player_bj:
            continue
        seen += 1
        assert r.n_hands == 1
        assert r.wagered == 1.0
        assert not r.doubled and not r.split
        assert r.player_finals == [21]
        assert r.net == (0.0 if r.dealer_bj else 1.5)
    assert seen > 800


def test_a_split_21_is_not_a_natural():
    """A 21 built from a split hand pays 1:1.  The engine's only 1.5 payouts
    come from the two-card branch that runs before any split can happen, so
    the way to test this is that no split round ever pays a half unit."""
    for r in run_rounds(60000, seed=404):
        if r.split:
            assert r.net == int(r.net), r


def test_double_takes_exactly_one_card_and_only_on_two():
    """Observed through the strategy hook: a DOUBLE is only ever offered when
    the hand has two cards, and a hand that doubled never gets asked again."""
    rec = Recorder(STANDARD)
    cards = Cards(505)
    for _ in range(20000):
        play_round(cards, STANDARD, strategy=rec)
    doubles = 0
    for (hand, _up, can_double, _cs, _is, _n), act in zip(rec.contexts,
                                                          rec.actions):
        if can_double:
            assert len(hand) == 2
        if act == 'D':
            assert can_double and len(hand) == 2
            doubles += 1
    assert doubles > 1000


def test_a_doubled_hand_never_acts_again():
    """Double takes exactly one card, and never after a hit.

    Play a strategy that doubles at every opportunity and stands otherwise.
    Under it no hand ever hits, so a hand can only reach three cards by
    doubling.  If a doubled hand were ever asked to act again, a three-card
    decision context would appear.  None does.
    """
    seen = []

    def double_everything(cards, up, *, can_double, **kw):
        seen.append(cards)
        return 'D' if can_double else 'S'

    cards = Cards(2468)
    for _ in range(20000):
        play_round(cards, STANDARD, strategy=double_everything)
    assert len(seen) > 15000
    assert all(len(h) == 2 for h in seen)


@pytest.mark.parametrize('extra', (0, 1, 2, 3))
def test_max_extra_units_caps_the_money(extra):
    """The parameter any honest bet-sizing analysis rests on.

    extra=0 is an all-in bet.  There is no money left, so the DOUBLE and SPLIT
    buttons might as well not exist, and the strategy must fall back through
    the chart rather than crash or clamp.
    """
    seen_double = seen_split = False
    for r in run_rounds(15000, seed=606, max_extra_units=extra):
        assert r.wagered <= 1 + extra
        assert r.n_hands <= 1 + extra
        seen_double |= r.doubled
        seen_split |= r.split
        if extra == 0:
            assert r.wagered == 1.0
            assert not r.doubled and not r.split
            assert r.n_hands == 1
            assert r.net in (-1.0, 0.0, 1.0, 1.5)
    if extra > 0:
        assert seen_double and seen_split


def test_all_in_is_a_much_worse_game_than_the_quoted_house_edge():
    """The number any bet-sizing analysis has to respect.

    Basic strategy's 0.41 percent assumes the player can double and split.  An
    all-in player cannot.  If this ever stops being a large, clearly separated
    gap, the reach-a-target maths downstream has quietly started quoting the
    wrong edge for the biggest bet a player ever makes.
    """
    full = simulate(200000, seed=707)
    allin = simulate(200000, seed=707, max_extra_units=0)
    assert allin.ev_per_hand < full.ev_per_hand
    # measured at 5,000,000 rounds each: -0.0235 vs -0.0042, a gap of 0.019
    gap = full.ev_per_hand - allin.ev_per_hand
    assert 0.012 < gap < 0.027, gap
    assert allin.wagered_per_round == 1.0


def test_split_limit_is_honoured():
    for rules, cap in ((Rules(max_hands=2), 2), (Rules(max_hands=3), 3),
                       (STANDARD, 4)):
        got = max(r.n_hands for r in run_rounds(40000, rules, seed=808))
        assert got <= cap
        assert got == cap, f'{cap}-hand cap never reached; test is not testing'


def test_split_aces_get_one_card_and_no_decision():
    """With hit_split_aces off, a hand born of a split ace is never asked to
    act.  Turning the rule on must make those decisions appear, otherwise the
    flag is dead code."""
    off = Recorder(STANDARD)
    cards = Cards(909)
    for _ in range(40000):
        play_round(cards, STANDARD, strategy=off)
    assert not [c for c in off.contexts if c[4] and c[0][0] == 'A'], \
        'a split ace was asked to act with hit_split_aces=False'

    on = Recorder(LIBERAL)
    cards = Cards(909)
    for _ in range(40000):
        play_round(cards, LIBERAL, strategy=on)
    assert [c for c in on.contexts if c[4] and c[0][0] == 'A' and len(c[0]) > 2]


def test_resplit_aces_flag_actually_gates_the_resplit():
    off = Recorder(STANDARD)
    on = Recorder(LIBERAL)
    for rules, rec in ((STANDARD, off), (LIBERAL, on)):
        cards = Cards(1010)
        for _ in range(60000):
            play_round(cards, rules, strategy=rec)

    def resplit_offers(rec):
        return [c for c in rec.contexts
                if c[4] and c[0] == ('A', 'A') and c[3]]

    assert not resplit_offers(off)
    assert resplit_offers(on)


def test_das_flag_gates_doubling_after_a_split():
    with_das = Recorder(STANDARD)
    without = Recorder(NO_DAS)
    for rules, rec in ((STANDARD, with_das), (NO_DAS, without)):
        cards = Cards(1111)
        for _ in range(40000):
            play_round(cards, rules, strategy=rec)
    assert [c for c in with_das.contexts if c[4] and c[2]]
    assert not [c for c in without.contexts if c[4] and c[2]]


def test_the_engine_never_splits_tens():
    """Honesty rule, enforced where the money is.  The original game offers SPLIT on Q,J;
    the simulator must never take it, at any budget."""
    for up in DEALER_UPS:
        assert compiled_action(('T', 'T'), up, can_double=True,
                               can_split=True) == 'S'
    rec = Recorder(STANDARD)
    cards = Cards(1212)
    for _ in range(40000):
        play_round(cards, STANDARD, strategy=rec)
    for ctx, act in zip(rec.contexts, rec.actions):
        if ctx[0] == ('T', 'T'):
            assert act != 'P'


def test_custom_strategy_may_not_invent_an_action_the_table_forbids():
    def cheat_split(cards, up, *, can_split, **kw):
        return 'P'

    def cheat_double(cards, up, *, can_double, **kw):
        return 'D'

    # one shoe, many rounds: with the same seed every round would be the same
    # round, and a round that ends on a natural never asks the strategy
    with pytest.raises(ValueError, match='SPLIT'):
        cards = Cards(1)
        for _ in range(200):
            play_round(cards, STANDARD, max_extra_units=0, strategy=cheat_split)
    with pytest.raises(ValueError, match='DOUBLE'):
        cards = Cards(1)
        for _ in range(200):
            play_round(cards, STANDARD, max_extra_units=0, strategy=cheat_double)


def test_no_peek_is_refused_rather_than_approximated():
    with pytest.raises(ValueError, match='peek'):
        play_round(Cards(1), Rules(peek=False))
    with pytest.raises(ValueError, match='peek'):
        simulate(10, Rules(peek=False))


# ===========================================================================
# the shoe
# ===========================================================================

def test_a_round_draws_a_real_six_deck_shoe_without_replacement():
    """Draw the whole shoe inside one round and count it.

    This is the simulator-side version of the spec's own persistence test:
    a seventh copy of any rank would prove the draw is not a shoe.  Here the
    entire shoe is dealt out and must come back as exactly 24 of each rank and
    96 tens, no more and no fewer.
    """
    cards = Cards(31337)
    fresh = fresh_shoe(6)
    for _round in range(50):
        cards.new_round()
        counts = [0] * 10
        for _ in range(sum(fresh)):
            counts[cards.draw()] += 1
        assert tuple(counts) == fresh
        with pytest.raises(RuntimeError):
            cards.draw()


def test_every_round_starts_from_a_full_shoe():
    """No state carries between rounds.  If it did, the second round's first
    card would be drawn from a depleted shoe and the long-run rank frequency
    of first cards would drift away from the deck composition."""
    scipy_stats = pytest.importorskip('scipy.stats')
    cards = Cards(4242)
    counts = [0] * 10
    n = 200000
    for _ in range(n):
        cards.new_round()
        counts[cards.draw()] += 1
    expected = [n * c / 52 for c in CARDS_PER_DECK]
    chi2, p = scipy_stats.chisquare(counts, expected)
    assert p > 0.001, (counts, expected, chi2, p)


def test_same_seed_same_rounds_different_seed_different_rounds():
    a = run_rounds(500, seed=77)
    b = run_rounds(500, seed=77)
    c = run_rounds(500, seed=78)
    assert a == b
    assert a != c


# ===========================================================================
# 3. exact cross-check of dealing, peek and settlement
# ===========================================================================

def test_stand_only_game_matches_exact_combinatorics():
    """No strategy, no sampling error on the reference side.

    Measured at 4,000,000 rounds the gap was 0.0006 on EV (1.2 sigma) and
    under 0.0003 on every rate.  This runs a shorter version; the tolerance is
    four standard errors, computed rather than guessed.
    """
    ev, win, loss, push = exact_stand_game(STANDARD)
    n = 300000
    st = simulate(n, seed=515, strategy=always_stand)
    se = st.sd_per_hand / math.sqrt(n)
    assert abs(st.ev_per_hand - ev) < 4 * se, (st.ev_per_hand, ev, se)
    for got, want, label in ((st.hand_win_rate, win, 'win'),
                             (st.hand_loss_rate, loss, 'loss'),
                             (st.hand_push_rate, push, 'push')):
        rate_se = math.sqrt(want * (1 - want) / n)
        assert abs(got - want) < 4 * rate_se, (label, got, want, rate_se)


@lru_cache(maxsize=None)
def exact_overall_dealer_bust(rules: Rules = STANDARD) -> float:
    """The unconditional dealer bust rate, exactly, from bj.dealer.

    Same convention as ``Stats.dealer_bust_rate``: every upcard weighted by its
    frequency in a fresh shoe, the peek applied so a dealer natural is not a
    bust, and the dealer's own two cards removed.  It does NOT remove the
    player's cards, which is APPROXIMATIONS note 3 in the module docstring.
    """
    shoe0 = fresh_shoe(rules.decks)
    n0 = shoe_size(shoe0)
    total = 0.0
    for i, r in enumerate(RANKS):
        s1 = remove_card(shoe0, i)
        n1 = shoe_size(s1)
        if r == 'A':
            p_nat = s1[RANK_INDEX['T']] / n1
        elif r == 'T':
            p_nat = s1[RANK_INDEX['A']] / n1
        else:
            p_nat = 0.0
        dist = dealer_distribution(r, s1, rules, peek_resolved=True)
        total += (shoe0[i] / n0) * (1.0 - p_nat) * dist[IBUST]
    return total


#: the spec appendix's per-upcard dealer bust row, quoted verbatim.  It is
#: the OTHER half of the 28.3 percent contradiction: these ten numbers and that
#: headline are printed a dozen lines apart and do not agree.
PUBLISHED_BUST_BY_UPCARD = {
    '2': .3535, '3': .3742, '4': .3958, '5': .4184, '6': .4228,
    '7': .2619, '8': .2437, '9': .2292, 'T': .2302, 'A': .1670,
}


def weighted_published_bust() -> float:
    """The published per-upcard row, weighted by upcard and peeked."""
    total = 0.0
    for r, bust in PUBLISHED_BUST_BY_UPCARD.items():
        n_up = 96 if r == 'T' else 24
        p_up = n_up / 312
        if r == 'A':
            p_nat = 96 / 311
        elif r == 'T':
            p_nat = 24 / 311
        else:
            p_nat = 0.0
        total += p_up * (1.0 - p_nat) * bust
    return total


def test_the_spec_contradicts_itself_on_the_dealer_bust_rate():
    """APPROXIMATIONS note 3, checked rather than asserted.

    The note used to blame the engine's 28.20 percent on player card removal.
    It is not that.  The spec's headline 28.3 percent disagrees with the
    spec's own per-upcard bust table: weight those ten rows by upcard
    frequency, apply the peek, and they come to 0.2819.  This project's exact
    dealer solver, on the same convention, gives 0.28192.  The engine matches
    both; the headline is the outlier.
    """
    exact = exact_overall_dealer_bust(STANDARD)
    published_table = weighted_published_bust()
    assert exact == pytest.approx(0.28192, abs=5e-5)
    # the published row is quantised to 1e-4 per cell, so it can only be
    # expected to reproduce the exact figure to about that
    assert published_table == pytest.approx(exact, abs=2e-4)
    assert published_table == pytest.approx(0.28190, abs=5e-5)
    # and the headline is nowhere near either of them
    assert abs(0.283 - exact) > 5 * abs(published_table - exact)


def test_the_engine_bust_rate_matches_the_exact_figure():
    """Fast tier, and it says what it cannot do.

    At 400,000 rounds the standard error on the bust rate is about 0.0007, so
    this run cannot separate the exact 0.28192 from the published 0.283 - the
    two are 1.5 standard errors apart here.  It checks the engine against the
    exact figure and leaves the discrimination to the slow tier.
    """
    n = 400000
    st = moderate_run(n)
    exact = exact_overall_dealer_bust(STANDARD)
    se = math.sqrt(exact * (1 - exact) / n)
    assert abs(st.dealer_bust_rate - exact) < 4 * se
    assert abs(0.283 - exact) / se < 3.0, (
        'this sample size is not supposed to be able to tell them apart; if '
        'it now can, tighten the assertion above')


@pytest.mark.slow
@SLOW
def test_the_engine_bust_rate_prefers_the_exact_figure_over_the_headline():
    """35,000,000 rounds, where the two references are finally distinguishable.

    Measured, seed 20260902 across 16 workers: 0.281943 +/- 0.000076 against
    the exact 0.281921 (+0.3 sigma) and the published headline 0.283
    (-13.9 sigma).  The +0.3 sigma is where the player-card-removal effect of
    APPROXIMATIONS note 3 would show up if this sample size could see it.  It
    cannot, and that bound is the measured magnitude the note quotes.

    The worker count is written out rather than left to the core count,
    because a parallel run subdivides the stream by worker and a 14-worker run
    of the same seed is a different sample.
    """
    st = simulate_parallel(35_000_000, 16, seed=20260902)
    exact = exact_overall_dealer_bust(STANDARD)
    se = math.sqrt(exact * (1 - exact) / st.n)
    print(f'\nbust {st.dealer_bust_rate:.5f}  exact {exact:.5f}  '
          f'{(st.dealer_bust_rate - exact) / se:+.1f} sigma  '
          f'headline 0.283 {(st.dealer_bust_rate - 0.283) / se:+.1f} sigma')
    assert abs(st.dealer_bust_rate - exact) < 3 * se
    assert abs(st.dealer_bust_rate - 0.283) > 8 * se


#: bj.ev.house_edge(STANDARD, strategy=bj.strategy.basic_action), the exact
#: expectation of the printed chart on this ruleset.  Pinned here because
#: recomputing it costs about sixteen seconds; the slow tier recomputes it live
#: so the constant cannot go stale unnoticed.
#:
#: It WENT stale once already, which is the argument for that slow test: it
#: read -0.004101 until bj.strategy grew the soft-18-vs-ace exception and had
#: its 4,4 row corrected, and the chart's exact expectation moved to -0.004044.
#: This constant describes bj.strategy's chart, so it moves whenever that chart
#: does, and the recomputation is the only thing that notices.
EXACT_CHART_EV = -0.004044


def test_ev_matches_the_exact_solver():
    """Two independent implementations of the same game, agreeing.

    bj.ev enumerates all 1,000 ordered opening deals and recurses through
    every draw with exact without-replacement probabilities.  This module
    samples.  They share bj.core and bj.strategy and nothing else - not the
    dealing, not the settlement, not the split logic - so agreement is real
    evidence rather than a shared bug agreeing with itself.

    This is a much better reference than the published 0.41 percent, because
    it has no sampling error and no unknown conventions: it is the exact
    expectation of the chart in this repo, on the rules in this repo.
    """
    n = 400000
    st = moderate_run(n)
    se = st.sd_per_hand / math.sqrt(n)
    assert abs(st.ev_per_hand - EXACT_CHART_EV) < 4 * se, (
        st.ev_per_hand, EXACT_CHART_EV, se)


@pytest.mark.slow
@SLOW
def test_exact_solver_constant_is_still_current():
    """Recompute the pinned exact number rather than trusting the comment."""
    from bj.ev import house_edge
    assert house_edge(STANDARD, strategy=basic_action) == pytest.approx(
        EXACT_CHART_EV, abs=5e-6)


@pytest.mark.slow
@SLOW
def test_ev_agrees_with_the_exact_solver_at_full_size():
    from bj.ev import house_edge
    exact = house_edge(STANDARD, strategy=basic_action)
    st = simulate_parallel(35_000_000, 16, seed=515151)
    print(f'\nexact {exact:+.6f}   simulated {st.ev_per_hand:+.6f} '
          f'+/- {st.stderr:.6f}   '
          f'{(st.ev_per_hand - exact) / st.stderr:+.2f} sigma')
    assert abs(st.ev_per_hand - exact) < 3 * st.stderr


def test_stand_only_game_is_far_worse_than_basic_strategy():
    """Sanity on the direction of the whole exercise: playing the charts is
    worth about fifteen points of house edge over never taking a card."""
    ev, _w, _l, _p = exact_stand_game(STANDARD)
    assert ev < -0.15
    assert simulate(100000, seed=616).ev_per_hand > ev + 0.10


# ===========================================================================
# 4. aggregates against the published reference
# ===========================================================================

def test_stats_are_internally_consistent():
    st = simulate(50000, seed=1717)
    assert st.n == 50000
    assert abs(sum(st.net_distribution.values()) - 1.0) < 1e-9
    ev = sum(k * p for k, p in st.net_distribution.items())
    assert abs(ev - st.ev_per_hand) < 1e-9
    assert abs(st.win_rate + st.loss_rate + st.push_rate - 1.0) < 1e-12
    assert abs(st.hand_win_rate + st.hand_loss_rate
               + st.hand_push_rate - 1.0) < 1e-12
    assert abs(st.stderr - st.sd_per_hand / math.sqrt(st.n)) < 1e-12
    # doubles and splits put money on hands that are better than average, so
    # the per-unit figure is always the smaller loss of the two
    assert st.ev_per_unit_wagered > st.ev_per_hand
    assert st.hands_per_round > 1.0
    assert st.wagered_per_round > 1.0


def test_moderate_run_lands_near_the_published_numbers():
    """Fast tier.  Tolerances are four standard errors at this sample size,
    not the spec's tolerances - a 400,000 round run genuinely cannot resolve
    the house edge to 0.0007, and pretending otherwise would make this test
    flaky rather than strict."""
    n = 400000
    st = moderate_run(n)
    se = st.sd_per_hand / math.sqrt(n)
    assert abs(st.ev_per_hand - (-0.0041)) < 4 * se
    assert abs(st.sd_per_hand - 1.15) < 0.03
    assert abs(st.player_bj_rate - 0.0475) < 0.002
    assert abs(st.dealer_bj_rate - 0.0475) < 0.002
    assert abs(st.dealer_bust_rate - 0.283) < 0.005
    assert abs(st.hand_push_rate - 0.085) < 0.004
    assert st.ev_per_hand < 0.0


def test_published_win_loss_split_is_a_known_disagreement():
    """PINNED, NOT TUNED.

    The spec quotes win 42.2 percent and loss 49.1 percent.  This engine
    measures about 43.6 and 47.9 at twenty million rounds.  Everything around
    those two numbers agrees - EV, SD, push rate, both natural rates, the
    dealer's whole final-total distribution, and the exact stand-only
    cross-check above - so the disagreement is isolated to the split between
    wins and losses.

    The published pair is also arithmetically incompatible with the published
    house edge that sits beside it; that argument is run as a test of its own
    in ``test_the_double_term_in_the_docstring_arithmetic``, which reaches
    about -0.030, a three percent house edge, not the 0.41 percent quoted two
    lines earlier in the same appendix.

    And a SECOND from-scratch engine, sharing only bj.core and bj.strategy,
    returns 43.591 +/- 0.010 percent and 47.932 +/- 0.010 percent over
    25,200,000 rounds - 0.7 and 0.2 standard errors from this engine, against
    169 and 140 from the published pair.  Two independent implementations do
    not agree to one standard error by accident.

    So this test asserts the disagreement rather than the reference.  It fails
    if the gap moves, in either direction, which is what you want: a future
    change to the engine that closes it deserves a fresh argument, and so does
    one that widens it.
    """
    n = 400000
    st = moderate_run(n)
    se = math.sqrt(0.44 * 0.56 / n)

    pub_win, pub_loss = REFERENCE['win_rate'][0], REFERENCE['loss_rate'][0]
    closed = 'gap closed - re-read this docstring before deleting the test'
    assert st.hand_win_rate > REFERENCE['win_rate'][2], closed
    assert st.hand_loss_rate < REFERENCE['loss_rate'][1], closed

    # the measured values, pinned to within four standard errors of the
    # thirty-five-million-round figures (seed 20260902, 16 workers)
    assert abs(st.hand_win_rate - 0.4360) < 4 * se
    assert abs(st.hand_loss_rate - 0.4794) < 4 * se
    assert st.hand_win_rate - pub_win == pytest.approx(0.0140, abs=4 * se)
    assert st.hand_loss_rate - pub_loss == pytest.approx(-0.0117, abs=4 * se)

    # and the reference table says so out loud
    assert REFERENCE['win_rate'][4]
    assert REFERENCE['loss_rate'][4]
    v_checks = [c for c in _fake_checks(st) if c.name in ('win_rate', 'loss_rate')]
    assert all(not c.ok and c.known_gap for c in v_checks)


def _fake_checks(st: Stats):
    from bj.simulate import _checks_for
    return _checks_for(st)


def test_the_three_double_frequencies_are_three_different_numbers():
    """The mistake the module docstring used to make, pinned as a test.

    It said "doubles happen on 9.6 percent of rounds", which named the rate of
    ROUNDS containing a double and measured the rate of rounds that doubled and
    did NOT split.  Neither is the quantity its arithmetic needed, which is
    doubled HANDS per round: a round that splits and then doubles both hands
    puts up two extra units and ``double_rate`` counts it once.

    All three are measured here so the next person to quote one has to pick.
    """
    cards = Cards(1313)
    n = 200000
    rounds_with_a_double = unsplit = won = lost = 0
    for _ in range(n):
        r = play_round(cards)
        if r.doubled:
            rounds_with_a_double += 1
            if r.n_hands == 1:
                unsplit += 1
                won += r.net > 0
                lost += r.net < 0
    se = math.sqrt(0.10 * 0.90 / n)                      # about 0.00067
    assert abs(rounds_with_a_double / n - 0.1026) < 4 * se
    assert abs(unsplit / n - 0.0955) < 4 * se
    assert unsplit < rounds_with_a_double, 'the two are not the same quantity'

    # doubled HANDS per round, the figure the arithmetic uses.  Only the
    # strategy hook can see it: RoundResult records doubling per round.
    hands = _doubled_hands_per_round(60000, seed=1314)
    assert abs(hands - 0.1037) < 4 * math.sqrt(0.10 * 0.90 / 60000)
    assert hands > rounds_with_a_double / n

    # the 55 / 38 split, on the unsplit rounds where a round's net does
    # identify the doubled hand's outcome
    assert abs(won / unsplit - 0.5508) < 0.01
    assert abs(lost / unsplit - 0.3797) < 0.01


def _doubled_hands_per_round(n, seed):
    """Count DOUBLE decisions through the strategy hook, which is the only way
    bj.simulate can report doubling per HAND rather than per round."""
    count = [0]

    def hook(cards, up, **kw):
        act = basic_action(cards, up, STANDARD, can_double=kw['can_double'],
                           can_split=kw['can_split'],
                           is_split_hand=kw['is_split_hand'],
                           hand_count=kw['hand_count']).action
        if act == 'D':
            count[0] += 1
        return act

    cards = Cards(seed)
    for _ in range(n):
        play_round(cards, STANDARD, strategy=hook)
    return count[0] / n


def test_the_double_term_in_the_docstring_arithmetic():
    """+0.0180, the last term of the identity the module docstring uses.

        EV per round = (hand win - hand loss) x hands per round
                       + 0.5 x P(natural that is paid)
                       + (doubled hands per round) x (their win - their loss)

    P(natural paid) is exactly the +1.5 cell of the net distribution: nothing
    else in the game returns half a unit, which
    ``test_a_split_21_is_not_a_natural`` is the other half of.  Rearranged, the
    double term is a residual this module can measure without per-hand records,
    and it is what makes the "-0.030, not -0.0041" argument checkable.

    Two million rounds, because at 400,000 the residual's own spread across
    seeds is 0.0005 and the band would have to be wide enough to admit the
    wrong number this test exists to exclude.
    """
    st = simulate_parallel(2_000_000, 8, seed=20260902)
    unit = (st.hand_win_rate - st.hand_loss_rate) * st.hands_per_round
    natural = st.net_distribution[1.5]
    double_term = st.ev_per_hand - unit - 0.5 * natural
    assert abs(double_term - 0.0180) < 0.0012
    # the value the docstring used to claim, from the wrong double frequency
    assert double_term > 0.016

    # and the whole argument, run end to end with the PUBLISHED win/loss pair
    pub = (REFERENCE['win_rate'][0] - REFERENCE['loss_rate'][0])
    implied = pub * st.hands_per_round + 0.5 * natural + double_term
    assert implied == pytest.approx(-0.0302, abs=0.0015), (
        'the published win/loss pair implies this house edge')
    assert implied < -0.02, 'seven times the 0.41 percent quoted beside it'

    # what doubled hands would have to do for the published pair to sit
    # alongside a 0.41 percent edge
    needed = (-0.0041 - pub * st.hands_per_round - 0.5 * natural)
    per_hand = _doubled_hands_per_round(60000, seed=1315)
    assert needed / per_hand == pytest.approx(0.425, abs=0.03)


# ===========================================================================
# outcome distributions (built for the original project's bet-sizing module)
# ===========================================================================

def test_outcome_distributions_shape_and_support():
    n = 60000
    d = outcome_distributions(n, seed=2020, extras=(0, 1, 2, 3))
    assert sorted(d) == [0, 1, 2, 3]
    for e, dist in d.items():
        assert abs(sum(dist.values()) - 1.0) < 1e-9
        assert all(0.0 <= p <= 1.0 for p in dist.values())
        # the most that can be lost is every unit on the table; the most that
        # can be won is the same, except that a natural pays 3:2 on one unit
        assert max(abs(k) for k in dist) <= max(1 + e, STANDARD.blackjack_payout) + 1e-9
        assert min(dist) >= -(1 + e) - 1e-9
    assert set(d[0]) <= {-1.0, 0.0, 1.0, 1.5}
    assert set(d[0]) == {-1.0, 0.0, 1.0, 1.5}
    # a bigger budget can only widen the support
    for a, b in ((0, 1), (1, 2), (2, 3)):
        assert max(d[a]) <= max(d[b])
        assert min(d[a]) >= min(d[b])


def test_no_budget_produces_a_player_edge():
    """The honesty rule, checked as a number rather than as a promise.

    Not 'every sampled mean is negative' - at any affordable sample size one
    of them will occasionally come out positive by luck.  The claim that must
    hold is that none of them is SIGNIFICANTLY positive.
    """
    n = 80000
    d = outcome_distributions(n, seed=3030, extras=(0, 1, 2, 3, None))
    for e, dist in d.items():
        ev = sum(k * p for k, p in dist.items())
        var = sum(p * (k - ev) ** 2 for k, p in dist.items())
        se = math.sqrt(var / n)
        assert ev < 3 * se, f'extras={e} shows a player edge: {ev:+.5f}'
    assert sum(k * p for k, p in d[0].items()) < -0.015


def test_outcome_distributions_accepts_unlimited():
    d = outcome_distributions(20000, seed=4040, extras=(0, None))
    assert set(d) == {0, None}


#: The all-in round - no double, no split - enumerated exactly by a scratch
#: script in the original project (not included here): every player two-card
#: hand, every dealer upcard, every hole card, full composition dependence,
#: peek applied by hand, no sampling anywhere.
#:
#: This is the strongest check in the file.  extras=0 is the distribution the
#: original project's bet-sizing answers were built on, and it is the one
#: place where a Monte Carlo number in this project has an exact counterpart
#: to be graded against rather than another simulation.
ALLIN_EXACT = {-1.0: 0.48012466, 0.0: 0.08586196,
               1.0: 0.38869039, 1.5: 0.04532299}


def test_all_in_distribution_matches_the_exact_enumeration():
    """Fast tier.  Four standard errors per cell at 400,000 rounds."""
    n = 400000
    st = simulate(n, seed=20260902, max_extra_units=0)
    got = st.net_distribution
    assert set(got) == set(ALLIN_EXACT)
    for k, p in ALLIN_EXACT.items():
        se = math.sqrt(p * (1 - p) / n)
        assert abs(got[k] - p) < 4 * se, (k, got[k], p, se)
    ev = sum(k * v for k, v in got.items())
    assert abs(ev - (-0.02344979)) < 4 * st.stderr


@pytest.mark.slow
@SLOW
def test_all_in_distribution_matches_the_exact_enumeration_at_full_size():
    """20,000,000 rounds, where every cell is worth about a ten-thousandth.

    Measured, seed 20260902 across 14 workers: -1 at +0.23 sigma, push at
    +0.90, +1 at -0.76, +1.5 at +0.02.  Worst cell 0.90 sigma.  If a future
    change to the round engine moves any of these past three sigma, the
    all-in number the bet analysis quotes has stopped being the game the exact
    solver enumerated.

    (Those four sigmas are a property of the card stream, so they move when the
    stream does.  Before the compiled key was widened to four shape classes the
    same seed gave +0.23 / +1.05 / -1.02 / +0.41, worst 1.05 - a different
    sample of the same distribution, not a different distribution.  Only the
    "worst < 3" assertion is load-bearing.)
    """
    n = 20_000_000
    st = simulate_parallel(n, 14, seed=20260902, max_extra_units=0)
    worst = 0.0
    for k, p in ALLIN_EXACT.items():
        se = math.sqrt(p * (1 - p) / n)
        sigma = (st.net_distribution[k] - p) / se
        print(f'\n  net {k:+5.1f}  exact {p:.8f}  simulated '
              f'{st.net_distribution[k]:.8f}  {sigma:+.2f} sigma')
        worst = max(worst, abs(sigma))
    assert worst < 3.0, worst


# ===========================================================================
# parallelism
# ===========================================================================

def test_merge_of_two_chunks_is_the_stats_of_the_whole():
    a = _Accum(n=3, sum_net=2.0, sum_net2=6.0, sum_wagered=4.0, hands=3,
               wins=2, losses=1, pushes=0, hand_wins=2, hand_losses=1,
               hand_pushes=0, player_bj=1, dealer_bj=0, dealer_bust=1,
               doubles=1, splits=0, nets={1.0: 2, 0.0: 1})
    b = _Accum(n=2, sum_net=-1.0, sum_net2=1.0, sum_wagered=2.0, hands=2,
               wins=0, losses=1, pushes=1, hand_wins=0, hand_losses=1,
               hand_pushes=1, player_bj=0, dealer_bj=1, dealer_bust=0,
               doubles=0, splits=1, nets={-1.0: 1, 0.0: 1})
    m = _merge([a, b])
    assert m.n == 5
    assert m.sum_net == 1.0
    assert m.nets == {1.0: 2, 0.0: 2, -1.0: 1}
    st = _stats(m)
    assert st.ev_per_hand == pytest.approx(0.2)
    assert st.ev_per_unit_wagered == pytest.approx(1.0 / 6.0)
    assert st.net_distribution[0.0] == pytest.approx(0.4)


def test_single_worker_parallel_is_the_serial_run():
    a = simulate_parallel(5000, 1, seed=606)
    b = simulate(5000, seed=606)
    assert a == b


def test_parallel_agrees_with_serial_and_is_reproducible():
    n = 150000
    p = simulate_parallel(n, 4, seed=808)
    s = simulate(n, seed=909)
    assert p.n == n
    se = math.sqrt(p.stderr ** 2 + s.stderr ** 2)
    assert abs(p.ev_per_hand - s.ev_per_hand) < 5 * se
    assert p == simulate_parallel(n, 4, seed=808)
    assert abs(sum(p.net_distribution.values()) - 1.0) < 1e-9


def test_parallel_refuses_a_custom_strategy():
    with pytest.raises(ValueError, match='picklable'):
        simulate_parallel(50000, 4, strategy=always_stand)


def test_parallel_rejects_unknown_keywords():
    with pytest.raises(TypeError):
        simulate_parallel(50000, 4, nonsense=1)


# ===========================================================================
# the multi-worker path, which used to be uncovered and used to crash
# ===========================================================================

class _RecordingPool:
    """Stands in for ``multiprocessing.Pool`` and keeps what the workers got.

    ``simulate_parallel`` does ``import multiprocessing as mp`` inside the
    function body and then calls ``mp.Pool``, so patching the attribute on the
    module reaches it.  Running the chunks in this process is the whole point:
    the argument tuples the real pool would have pickled and thrown over a
    process boundary stay here, where a test can look at the seeds.
    """

    calls = []          # list of (args, results) per starmap

    def __init__(self, processes):
        self.processes = processes

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starmap(self, fn, args):
        args = list(args)
        results = [fn(*a) for a in args]
        _RecordingPool.calls.append((args, results))
        return results


@pytest.fixture
def recording_pool(monkeypatch):
    import multiprocessing
    _RecordingPool.calls = []
    monkeypatch.setattr(multiprocessing, 'Pool', _RecordingPool)
    return _RecordingPool


def _first_cards(seed, k=80):
    """The first k cards a worker seeded this way would deal."""
    c = Cards(seed, decks=6)
    return tuple(c.draw() for _ in range(k))


def test_every_worker_gets_a_different_stream(recording_pool):
    """The failure that would have been worse than the crash.

    If two workers were handed the same seed they would replay the same rounds,
    the merged sample would contain each of them twice, and every standard
    error computed from it - which is every standard error in this project -
    would come out smaller than the truth by up to sqrt(workers).  Nothing
    downstream would look wrong.  It would just be wrong.

    So this asserts the streams differ, and the control below it asserts that
    the comparison is capable of failing.
    """
    n, workers = 40000, 4
    simulate_parallel(n, workers, seed=13579)

    assert len(recording_pool.calls) == 1
    args, results = recording_pool.calls[0]
    assert len(args) == workers
    assert sum(a[0] for a in args) == n, 'the chunks must add up to n'

    seeds = [a[2] for a in args]
    assert all(isinstance(s, np.random.SeedSequence) for s in seeds)
    assert len({_first_cards(s) for s in seeds}) == workers, \
        'two workers were handed the same card stream'

    # and the consequence, at the level that actually matters: no two chunks
    # returned the same sufficient statistics
    assert len({(r.sum_net, r.sum_net2, r.hands) for r in results}) == workers


def test_the_distinct_stream_check_can_fail(recording_pool):
    """Control for the test above.  Two Cards built from the SAME seed deal the
    same cards, so ``_first_cards`` really does detect a shared stream rather
    than always returning something different."""
    one = np.random.SeedSequence(2468)
    assert _first_cards(one) == _first_cards(np.random.SeedSequence(2468))
    assert _first_cards(one) != _first_cards(np.random.SeedSequence(2469))


def test_seed_sequence_helper_accepts_both_forms():
    """``np.random.SeedSequence(x)`` is a TypeError when x is already one.  The
    helper is the single place in the module that knows that."""
    ss = np.random.SeedSequence(99)
    assert _seed_sequence(ss) is ss
    assert isinstance(_seed_sequence(99), np.random.SeedSequence)
    # and the two forms are the same stream, so passing a SeedSequence through
    # is not quietly a different run
    a = _seed_sequence(99).spawn(3)
    b = _seed_sequence(np.random.SeedSequence(99)).spawn(3)
    assert [_first_cards(x) for x in a] == [_first_cards(x) for x in b]


def test_simulate_parallel_accepts_an_already_spawned_seed(recording_pool):
    """The exact shape outcome_distributions passes in.  Before the fix this
    raised: TypeError: SeedSequence expects int or sequence of ints for entropy
    not SeedSequence(...)"""
    child = np.random.SeedSequence(20260902).spawn(1)[0]
    st = simulate_parallel(40000, 4, seed=child)
    assert st.n == 40000
    seeds = [a[2] for a in recording_pool.calls[0][0]]
    assert len({_first_cards(s) for s in seeds}) == 4


def test_outcome_distributions_with_four_workers_agrees_with_one():
    """The call that used to raise TypeError, run for real across processes.

    This one does NOT use the recording pool: the point is that the multi-
    process path works end to end, pickling included.  The two runs are
    independent samples of the same distribution - the parallel run subdivides
    each budget's stream again, so it is not the serial run re-ordered - and
    they are compared at four standard errors of the difference.
    """
    n = 200000
    one = outcome_distributions(n, seed=717171, extras=(0,))
    many = outcome_distributions(n, seed=717171, extras=(0,), workers=4)
    assert set(many) == {0}
    assert set(many[0]) == {-1.0, 0.0, 1.0, 1.5}
    assert abs(sum(many[0].values()) - 1.0) < 1e-9
    for k, p in one[0].items():
        se = math.sqrt(2.0 * p * (1.0 - p) / n)     # two independent samples
        assert abs(many[0][k] - p) < 4 * se, (k, p, many[0][k], se)


def test_outcome_distributions_workers_reaches_every_budget():
    """workers > 1 is passed through for each budget, not just the first."""
    n = 30000
    d = outcome_distributions(n, seed=818181, extras=(0, 1, None), workers=4)
    assert sorted(d, key=lambda x: (x is None, x)) == [0, 1, None]
    for e, dist in d.items():
        assert abs(sum(dist.values()) - 1.0) < 1e-9
        assert sum(k * p for k, p in dist.items()) < 0.05


# ===========================================================================
# speed
# ===========================================================================

def test_throughput_clears_the_target():
    """Spec target is 30,000 rounds per second per core.  Measured on the
    author's sixteen-core machine, 2026-09-02: about 290,000 serial, and between
    850,000 and 1,760,000 for a full 35,000,000-round parallel run including
    pool startup - the spread is other work on the box, which is exactly why
    the assertion is not near the measured rate.  Widening the compiled key
    from three shape classes to four costs about 3 percent of the serial rate,
    measured by A/B against the same file with the tracking removed.  The
    assertion is deliberately at 60,000 - a fifth of the serial rate - so a
    loaded CI box fails only when something has genuinely regressed."""
    simulate(1000, seed=1)                       # warm the tables
    n = 60000
    t0 = time.perf_counter()
    simulate(n, seed=2)
    rate = n / (time.perf_counter() - t0)
    assert rate > 60000, f'{rate:,.0f} rounds/s'


# ===========================================================================
# the heavy run
# ===========================================================================

@pytest.mark.slow
@SLOW
def test_two_million_rounds_cannot_decide_the_specs_ev_tolerance():
    """A finding about the spec, not about the engine.

    The spec asks for "at least 2,000,000 rounds" and accepts EV per hand
    in [-0.0048, -0.0035] around -0.0041.  That band is not symmetric; its
    tighter half is 0.0006.  The standard error of the mean at two million
    rounds is 1.1547/sqrt(2e6) = 0.00082, so the band is +/-0.73 standard
    errors wide and a perfectly correct engine lands outside it about two times
    in five.  The check cannot fail honestly and it cannot pass honestly.

    This test asserts the powerlessness STRUCTURALLY - band_sigma is a property
    of the band and the sample size, not of the run - and then demonstrates it
    on twelve seeds.  An earlier version of this test asserted that one named
    seed missed the band, which is a fact about a card stream: widening the
    compiled key in bj/simulate.py shifted every stream slightly and that seed
    now lands inside.  A test that a correct engine can break by getting
    luckier is not a test.

    The per-seed miss probability, for an engine whose true mean is the exact
    -0.004044, is 1 - [Phi(0.67) - Phi(-0.93)] = 0.43, so twelve seeds leave
    P(none of them misses) at 0.57^12 = 0.12 percent.  That is the flakiness
    this test accepts, stated rather than hoped.  Measured on the twelve seeds
    below: 3 of 12 missed.
    """
    v = verification_run(2_000_000, seed=20260902)
    print()
    print(v.report())
    ev = {c.name: c for c in v.checks}['ev_per_hand']
    assert ev.band_sigma < 1.0, 'the band is narrower than one standard error'
    assert not ev.powered
    assert abs(ev.sigma) < 3.0, 'the engine itself is fine at this size'

    lo, hi = REFERENCE['ev_per_hand'][1], REFERENCE['ev_per_hand'][2]
    evs = _twelve_independent_two_million_round_runs()
    misses = sum(not (lo <= ev <= hi) for ev in evs)
    print(f'\n{misses} of 12 correct 2,000,000-round runs missed the '
          f"spec's own EV band: " + ', '.join(f'{e:+.5f}' for e in evs))
    assert misses >= 1, (
        'twelve correct runs all landed inside a band that is 0.73 standard '
        'errors wide; that is a 1-in-850 event, so check band_sigma')


def _twelve_independent_two_million_round_runs():
    """Twelve separate 2,000,000-round runs, in ONE process pool.

    Deliberately not twelve calls to ``simulate_parallel``: that would build
    and tear down twelve pools of sixteen Windows processes, which on a loaded
    box is minutes of process creation and, measured once during development,
    a pool that never finished starting.  One pool, twelve one-core chunks,
    each with its own integer seed and therefore its own stream.
    """
    import multiprocessing as mp
    from bj.simulate import _run
    seeds = (20260902, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)
    args = [(2_000_000, STANDARD, s, None, False) for s in seeds]
    with mp.Pool(len(args)) as pool:
        parts = pool.starmap(_run, args)
    return [_stats(p).ev_per_hand for p in parts]


@pytest.mark.slow
@SLOW
def test_full_size_verification():
    """Thirty-five million rounds: the point where the spec's own tolerance on
    EV per hand is finally worth three standard errors.

    Every check the spec lists is asserted at its STATED tolerance - none of
    them widened - except the win/loss pair, which is the known disagreement
    pinned above.  Those two are reported, not asserted.  The test also
    asserts that each band it relies on is worth at least three standard
    errors at this sample size, so a future change that quietly shrinks the
    run cannot turn these into coin flips.
    """
    v = verification_run(35_000_000, seed=20260902)
    print()
    print(v.report())
    by_name = {c.name: c for c in v.checks}
    for name in ('ev_per_hand', 'push_rate', 'player_bj_rate',
                 'dealer_bust_rate'):
        assert by_name[name].powered, str(by_name[name])
        assert by_name[name].ok, str(by_name[name])
    # sd_per_hand's standard error is a normal-theory approximation on a very
    # non-normal variable, so its band is checked but its power is not claimed
    assert by_name['sd_per_hand'].ok, str(by_name['sd_per_hand'])
    assert not v.unexplained, [str(c) for c in v.unexplained]
    assert not by_name['win_rate'].ok
    assert not by_name['loss_rate'].ok
    # the disagreement is enormous compared with the noise: tens of sigma
    assert abs(by_name['win_rate'].sigma) > 10
    assert abs(by_name['loss_rate'].sigma) > 10
    assert v.rounds_per_second > 30000
