"""Tests for bj.dealer.

Two kinds of test live here and they are kept visibly separate.

1.  REFERENCE tests compare the solver against numbers published by somebody
    else (Wizard of Odds, via the spec's appendix).  These can fail for a
    reason that is not a bug: the published source may use a different
    convention.  When one fails, the job is to find out which convention
    differs, not to nudge a constant until it passes.  The tolerances below are
    therefore justified out loud, in terms of the number of digits the source
    actually printed.

2.  STRUCTURAL tests check things that must be true of any correct solver
    regardless of what anyone published - rows sum to one, conditioning is
    consistent, the S17 flag does what it says, depleting the shoe moves the
    answer in the right direction.  A structural failure is always a bug.

Measured residuals when this file was written (see the assertions for the
tolerances actually enforced):
  * all 60 cells of the after-peek table: worst |error| 4.91e-05, at upcard 6 /
    total 20.  The published table is printed to four decimals, so half of the
    last digit is 5.0e-05.  Every cell is inside that, which says the published
    table is this same computation rounded for display - a fresh six-deck shoe
    with only the upcard removed.  No convention gap to report.
  * the section 4 bust row (printed to one decimal place as a percentage):
    worst |error| 4.96e-04, at upcard 2, where the exact value 0.353504 is
    displayed as 35.4%.  Half of the last printed digit is 5.0e-04.  Again pure
    display rounding.
  * P(dealer natural | ace up) is 96/311 to the last bit of a float64.
"""
from __future__ import annotations

import math

import pytest

from bj.core import RANKS, Rules, fresh_shoe, remove_card, remove_cards, shoe_size
from bj.dealer import (
    OUTCOMES,
    clear_caches,
    dealer_bust_prob,
    dealer_distribution,
)

# --- published reference data ----------------------------------------------

#: Spec appendix, "Dealer probabilities (6-deck S17, after peek)".
#: Columns are 17, 18, 19, 20, 21, Bust.  Source: Wizard of Odds,
#: "Dealer Odds, US Rules".  Printed to four decimal places.
PUBLISHED_AFTER_PEEK = {
    '2': (.1397, .1344, .1300, .1240, .1184, .3535),
    '3': (.1343, .1305, .1252, .1208, .1149, .3742),
    '4': (.1306, .1241, .1213, .1164, .1119, .3958),
    '5': (.1218, .1224, .1176, .1118, .1079, .4184),
    '6': (.1657, .1062, .1064, .1016, .0973, .4228),
    '7': (.3692, .1379, .0784, .0787, .0738, .2619),
    '8': (.1289, .3600, .1287, .0692, .0695, .2437),
    '9': (.1203, .1173, .3519, .1204, .0609, .2292),
    'T': (.1213, .1210, .1213, .3684, .0377, .2302),
    'A': (.1881, .1892, .1889, .1894, .0774, .1670),
}

#: Spec, "Dealer bust probability by upcard".  Printed to one
#: decimal place as a percentage, i.e. to 0.001 as a probability.
PUBLISHED_BUST = {
    '2': .354, '3': .374, '4': .396, '5': .418, '6': .423,
    '7': .262, '8': .244, '9': .229, 'T': .230, 'A': .167,
}

UPCARDS = tuple(PUBLISHED_AFTER_PEEK)

#: The tolerance the task specifies.  Deliberately far looser than the residual
#: we actually measure, so that this test tells us "the solver still models the
#: same game" rather than "the last bit of float arithmetic did not change".
TASK_TOLERANCE = 0.0015

#: Half of the last digit the source printed.  Any error inside this is display
#: rounding in the source and nothing else.  Enforced as a second, tighter
#: assertion so that a real drift of 0.001 - invisible to TASK_TOLERANCE - still
#: gets caught.
DISPLAY_ROUNDING_5DP = 5.0e-05
DISPLAY_ROUNDING_3DP = 5.05e-04


def shoe_minus_upcard(up: str, decks: int = 6):
    """The shoe the published tables are computed from: fresh, upcard burned."""
    return remove_card(fresh_shoe(decks), up)


# --- reference tests --------------------------------------------------------

@pytest.mark.parametrize('up', UPCARDS)
def test_after_peek_table_matches_published(up):
    """Every one of the 10 x 6 published after-peek cells, to 0.0015."""
    computed = dealer_distribution(up, shoe_minus_upcard(up))
    published = PUBLISHED_AFTER_PEEK[up]
    labels = ('17', '18', '19', '20', '21', 'BUST')
    for i, label in enumerate(labels):
        gap = computed[i] - published[i]
        assert abs(gap) <= TASK_TOLERANCE, (
            f'upcard {up} outcome {label}: computed {computed[i]:.6f}, '
            f'published {published[i]:.4f}, gap {gap:+.6f}'
        )


@pytest.mark.parametrize('up', UPCARDS)
def test_after_peek_table_is_published_table_rounded(up):
    """Tighter than the task asks: the gap is only the source's display rounding.

    This is the assertion that would actually notice a subtle modelling change,
    e.g. someone switching the recursion to draw with replacement, which moves
    cells by a few ten-thousandths - enough to matter downstream, not enough to
    trip the 0.0015 tolerance above.
    """
    computed = dealer_distribution(up, shoe_minus_upcard(up))
    published = PUBLISHED_AFTER_PEEK[up]
    worst = max(abs(computed[i] - published[i]) for i in range(6))
    assert worst <= DISPLAY_ROUNDING_5DP, (
        f'upcard {up}: worst gap {worst:.3e} exceeds half of the last published '
        f'digit ({DISPLAY_ROUNDING_5DP:.1e}).  That is a convention difference '
        f'or a bug, not rounding - investigate, do not retune.'
    )


@pytest.mark.parametrize('up', UPCARDS)
def test_after_peek_row_sums_to_one(up):
    row = dealer_distribution(up, shoe_minus_upcard(up))
    assert math.isclose(sum(row), 1.0, rel_tol=0, abs_tol=1e-12)
    assert row[6] == 0.0, 'a peeked-through natural must be impossible, not merely rare'


@pytest.mark.parametrize('up', UPCARDS)
def test_bust_row_matches_published(up):
    """The section 4 bust row: 2 -> 35.4% through A -> 16.7%."""
    computed = dealer_bust_prob(up, shoe_minus_upcard(up))
    published = PUBLISHED_BUST[up]
    gap = computed - published
    assert abs(gap) <= DISPLAY_ROUNDING_3DP, (
        f'upcard {up}: computed bust {computed:.5f}, published {published:.3f}, '
        f'gap {gap:+.5f}'
    )


def test_bust_probability_ordering():
    """The shape of the bust row, not just its values.

    Bust rises monotonically from 2 through 6 (the stiff upcards), collapses at
    7, and the ace is the safest upcard in the deck.  If a refactor ever inverts
    a comparison this catches it even if the reference table is edited.
    """
    bust = {up: dealer_bust_prob(up, shoe_minus_upcard(up)) for up in UPCARDS}
    for low, high in (('2', '3'), ('3', '4'), ('4', '5'), ('5', '6')):
        assert bust[low] < bust[high]
    assert bust['6'] > bust['7'] + 0.15, 'the 6-to-7 cliff should be enormous'
    assert bust['A'] == min(bust.values())
    assert bust['6'] == max(bust.values())


def test_dealer_natural_probability_with_ace_up():
    """96/311 = 0.30868, the number the original game's insurance prompt calls 'about 31%'.

    311 = 312 cards minus the ace already showing; 96 = the ten-value cards in
    six decks.  Exact rational arithmetic, so this is asserted to 1e-6 as the
    task requires and in practice matches to the last bit of the float.
    """
    shoe = shoe_minus_upcard('A')
    assert shoe_size(shoe) == 311
    full = dealer_distribution('A', shoe, peek_resolved=False)
    assert full[6] == pytest.approx(96 / 311, abs=1e-6)
    assert full[6] == pytest.approx(0.30868, abs=1e-5)
    assert math.isclose(sum(full), 1.0, rel_tol=0, abs_tol=1e-12)


def test_dealer_natural_probability_with_ten_up():
    """The mirror case: 24 aces out of 311."""
    shoe = shoe_minus_upcard('T')
    full = dealer_distribution('T', shoe, peek_resolved=False)
    assert full[6] == pytest.approx(24 / 311, abs=1e-12)


def test_insurance_is_never_justified_by_these_numbers():
    """An honesty guard, not a maths test.

    Insurance pays 2:1, so it needs P(dealer natural) > 1/3 to break even.  Off
    the top of a six-deck shoe it is 0.3087.  This test exists so that if any
    future change to the solver ever produced a number above 1/3 from a fresh
    shoe, the build fails loudly rather than a downstream module quietly
    starting to recommend insurance.
    """
    p = dealer_distribution('A', shoe_minus_upcard('A'), peek_resolved=False)[6]
    assert p < 1 / 3
    insurance_ev = 2.0 * p - (1.0 - p)
    assert insurance_ev < 0
    assert insurance_ev == pytest.approx(-0.0740, abs=5e-4)  # ~7.4% house edge


# --- structural tests -------------------------------------------------------

@pytest.mark.parametrize('up', UPCARDS)
def test_peek_conditioning_is_bayes(up):
    """Dropping the natural hole card must equal renormalising the full vector.

    Two routes to the same number: the implementation excludes the one hole-card
    rank that makes 21 and divides by what is left, and this test instead
    computes the unconditional vector and divides the non-natural mass by
    (1 - P(natural)).  They are the same theorem, so they must agree exactly.
    """
    shoe = shoe_minus_upcard(up)
    peeked = dealer_distribution(up, shoe, peek_resolved=True)
    full = dealer_distribution(up, shoe, peek_resolved=False)
    scale = 1.0 - full[6]
    for i in range(6):
        assert peeked[i] == pytest.approx(full[i] / scale, rel=1e-12)


@pytest.mark.parametrize('up', ('2', '3', '4', '5', '6', '7', '8', '9'))
def test_peek_is_a_no_op_for_upcards_that_cannot_have_a_natural(up):
    """A natural needs an ace and a ten, so nothing else is conditioned at all."""
    shoe = shoe_minus_upcard(up)
    assert (dealer_distribution(up, shoe, peek_resolved=True)
            == dealer_distribution(up, shoe, peek_resolved=False))


def test_outcomes_vector_shape():
    assert OUTCOMES == (17, 18, 19, 20, 21, 'BUST', 'BJ')
    row = dealer_distribution('6', shoe_minus_upcard('6'))
    assert len(row) == len(OUTCOMES) == 7
    assert all(isinstance(x, float) and 0.0 <= x <= 1.0 for x in row)


def test_upcard_aliases_are_equivalent():
    """'K', 'j', 10 and 'T' are the same card to this solver, and 'a' is an ace."""
    shoe = shoe_minus_upcard('T')
    base = dealer_distribution('T', shoe)
    for alias in ('K', 'j', 'Q', 10, '10'):
        assert dealer_distribution(alias, shoe) == base
    ace_shoe = shoe_minus_upcard('A')
    assert dealer_distribution('a', ace_shoe) == dealer_distribution('A', ace_shoe)


def test_composition_awareness_removing_tens_cuts_the_bust_rate():
    """The whole reason this solver is exact rather than infinite-deck.

    Strip every ten out of the shoe and a dealer showing 6 stops busting nearly
    as often, because the cards that break a stiff hand are gone.  An
    infinite-deck or with-replacement solver would return the same number for
    both shoes, so this test is what proves depletion is really modelled.
    """
    base_shoe = shoe_minus_upcard('6')
    no_tens = tuple(0 if RANKS[i] == 'T' else c for i, c in enumerate(base_shoe))
    assert dealer_bust_prob('6', no_tens) < dealer_bust_prob('6', base_shoe) - 0.05


def test_composition_awareness_player_cards_change_the_answer():
    """Removing the player's own cards moves the dealer distribution.

    Hand 13 of the logged session (tests/test_strategy.py): player 9,5 against
    a ten.  The realistic shoe for that
    decision is 312 minus the upcard minus those two cards, and it is not the
    same shoe the published chart uses.  The difference is small - this is a
    six-deck game, which is exactly why counting is worthless here - but it is
    not zero, and the EV solver is entitled to it.
    """
    up = 'T'
    chart_shoe = shoe_minus_upcard(up)
    real_shoe = remove_cards(chart_shoe, ('9', '5'))
    assert dealer_distribution(up, real_shoe) != dealer_distribution(up, chart_shoe)
    # ...but only just: three cards out of 312 cannot move anything far.
    for a, b in zip(dealer_distribution(up, real_shoe),
                    dealer_distribution(up, chart_shoe)):
        assert abs(a - b) < 0.01


# --- the S17 / H17 flag -----------------------------------------------------

H17 = Rules(s17=False)


def test_s17_flag_changes_soft_17_behaviour_deterministically():
    """A tiny hand-checkable shoe, so the flag is tested without any reference table.

    Upcard A, and the only cards left are sixes.  The hole card is a six, so the
    dealer holds soft 17.  Under S17 he stands: 17 with probability 1.  Under
    H17 he must draw - six takes him to soft 23, which demotes to hard 13, and
    the next six makes 19.  So H17 gives 19 with probability 1.  Every step is
    forced, so any deviation is a bug and not a tolerance question.
    """
    six_index = RANKS.index('6')
    only_sixes = tuple(10 if i == six_index else 0 for i in range(10))

    stands = dealer_distribution('A', only_sixes, peek_resolved=False)
    assert stands[0] == pytest.approx(1.0)   # final total 17

    hits = dealer_distribution('A', only_sixes, H17, peek_resolved=False)
    assert hits[2] == pytest.approx(1.0)     # final total 19


#: Upcards that can reach soft 17, and therefore the only ones the S17/H17 flag
#: can possibly touch.  Soft 17 means one ace counted as 11 plus six points of
#: other cards, so the upcard must itself be worth 6 or less - or be the ace.
#: A dealer showing 7 through T can never hold soft 17 (7 alone already exceeds
#: the 6 points available), so for those four upcards the two rules give
#: bit-identical distributions.  This was written the other way round first,
#: asserting H17 busts more on *every* upcard; the test failed on upcard 7 and
#: the test was wrong, not the solver.
S17_SENSITIVE_UPCARDS = ('2', '3', '4', '5', '6', 'A')
S17_INERT_UPCARDS = ('7', '8', '9', 'T')


@pytest.mark.parametrize('up', S17_SENSITIVE_UPCARDS)
def test_h17_busts_more_where_soft_17_is_reachable(up):
    """Hitting soft 17 gives the dealer extra chances to break.

    The spec prices the S17 credit at +0.22% to the player; part of the
    mechanism is visible here as a higher dealer bust rate under H17.
    """
    shoe = shoe_minus_upcard(up)
    assert dealer_bust_prob(up, shoe, H17) > dealer_bust_prob(up, shoe)


@pytest.mark.parametrize('up', S17_INERT_UPCARDS)
def test_s17_and_h17_agree_where_soft_17_is_unreachable(up):
    """Not approximately equal - identical, because no branch ever differs."""
    shoe = shoe_minus_upcard(up)
    assert dealer_distribution(up, shoe, H17) == dealer_distribution(up, shoe)


def test_h17_ace_bust_rate_is_much_higher():
    """The ace is where the rule bites hardest, since A,6 is a common start."""
    shoe = shoe_minus_upcard('A')
    assert dealer_bust_prob('A', shoe, H17) - dealer_bust_prob('A', shoe) > 0.03


def test_rules_fields_other_than_s17_do_not_affect_the_dealer():
    """The dealer never splits, doubles or gets paid, so those flags are inert.

    Worth pinning: the cache key is s17 alone, and this test is what makes that
    optimisation safe to keep.
    """
    shoe = shoe_minus_upcard('9')
    base = dealer_distribution('9', shoe)
    for other in (Rules(das=False), Rules(blackjack_payout=1.2),
                  Rules(max_hands=2), Rules(surrender=True),
                  Rules(resplit_aces=True), Rules(hit_split_aces=True)):
        assert dealer_distribution('9', shoe, other) == base


# --- deterministic micro-shoes ---------------------------------------------

def _only(rank: str, count: int = 12):
    i = RANKS.index(rank)
    return tuple(count if j == i else 0 for j in range(10))


def test_forced_stand_on_two_cards():
    """Upcard 9, nothing left but eights: 9+8 = 17, stand, done."""
    row = dealer_distribution('9', _only('8'))
    assert row == pytest.approx((1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0))


def test_forced_bust():
    """Upcard T, nothing left but sixes: 16, must draw, 22.  Bust with certainty."""
    row = dealer_distribution('T', _only('6'))
    assert row[5] == pytest.approx(1.0)


def test_forced_multi_card_21_is_not_scored_as_a_natural():
    """Three sevens is 21, and it is worth exactly one bet, not three-to-two.

    Index 4 (total 21) and index 6 (natural) are different columns for a reason,
    and downstream payout code depends on the distinction.
    """
    row = dealer_distribution('7', _only('7'), peek_resolved=False)
    assert row[4] == pytest.approx(1.0)
    assert row[6] == 0.0


def test_ace_up_all_aces_left_stands_on_soft_totals():
    """A,A,A,A,A,A,A = soft 17 under S17.

    Seven aces: the first is 11 and the rest are 1.  The dealer keeps drawing
    until soft 17 and stops there.  This exercises the "only one ace can be
    high" branch harder than any real hand will.
    """
    row = dealer_distribution('A', _only('A', 20), peek_resolved=False)
    assert row[0] == pytest.approx(1.0)


def test_peek_with_no_legal_hole_card_raises():
    """Upcard T and only aces left: the peek would always find a natural.

    Conditioning on an event of probability zero has no answer, so the solver
    refuses rather than returning a fabricated vector.
    """
    with pytest.raises(ValueError):
        dealer_distribution('T', _only('A'), peek_resolved=True)
    # Unconditionally it is a certain natural, which is a perfectly good answer.
    full = dealer_distribution('T', _only('A'), peek_resolved=False)
    assert full[6] == pytest.approx(1.0)


def test_empty_shoe_raises():
    with pytest.raises(ValueError):
        dealer_distribution('7', (0,) * 10)


def test_shoe_that_runs_out_mid_draw_raises():
    """Upcard 5 with a single 2 behind it: 5+2 = 7, the dealer must hit, and
    there is nothing to hit with.  There is no honest answer, so it raises."""
    two = RANKS.index('2')
    shoe = tuple(1 if i == two else 0 for i in range(10))
    with pytest.raises(ValueError):
        dealer_distribution('5', shoe, peek_resolved=False)


# --- caching ----------------------------------------------------------------

def test_results_are_identical_before_and_after_clearing_caches():
    """Memoisation must be invisible.

    The cache keys are (total, soft, shoe, s17) and every part is immutable, so
    a cleared cache has to rebuild bit-identical values.  If this ever fails,
    something mutable has crept into a key.
    """
    warm = {up: dealer_distribution(up, shoe_minus_upcard(up)) for up in UPCARDS}
    clear_caches()
    cold = {up: dealer_distribution(up, shoe_minus_upcard(up)) for up in UPCARDS}
    assert warm == cold


def test_clear_caches_actually_empties_them():
    from bj import dealer as dealer_module

    dealer_distribution('A', shoe_minus_upcard('A'))
    assert dealer_module._resolve.cache_info().currsize > 0
    clear_caches()
    assert dealer_module._resolve.cache_info().currsize == 0
    assert dealer_module._distribution.cache_info().currsize == 0


def test_solver_is_fast_enough_for_a_live_decision():
    """Cold, all ten upcards from a fresh shoe, well under a second.

    The spec's requirement is a decision 'within a few seconds of seeing the
    cards', and the EV solver will call this many times per decision.  This is a
    smoke test on the order of magnitude, not a benchmark, so the bound is
    deliberately loose enough not to flake on a busy machine.
    """
    import time

    clear_caches()
    start = time.perf_counter()
    for up in UPCARDS:
        dealer_distribution(up, shoe_minus_upcard(up))
    assert time.perf_counter() - start < 2.0


# --- consistency across shoe sizes ------------------------------------------

@pytest.mark.parametrize('decks', (1, 2, 4, 6, 8))
def test_rows_sum_to_one_for_any_deck_count(decks):
    for up in UPCARDS:
        shoe = shoe_minus_upcard(up, decks)
        for peeked in (True, False):
            row = dealer_distribution(up, shoe, peek_resolved=peeked)
            assert math.isclose(sum(row), 1.0, rel_tol=0, abs_tol=1e-12)
            assert all(x >= 0.0 for x in row)


def test_single_deck_differs_from_six_deck():
    """Depletion is stronger in one deck, so the numbers must not coincide.

    A solver that had accidentally reverted to fixed 1/13 draw probabilities
    would return the same row for both, which is the failure this catches.
    """
    one = dealer_distribution('6', shoe_minus_upcard('6', 1))
    six = dealer_distribution('6', shoe_minus_upcard('6', 6))
    assert one != six
