"""Tests for bj.ev, the exact composition-dependent EV solver.

WHAT THIS SUITE IS FOR
----------------------
bj.ev is the only module in the project that can say a recommendation is worth
0.044 units rather than 0.0008.  Nothing downstream can catch it being wrong,
because nothing downstream has an independent opinion.  So the tests here are
mostly external: they check the solver against numbers Wizard of Odds
published for this exact ruleset, transcribed into the handoff appendix.

THE RULE THESE TESTS OBEY
-------------------------
Where a computed number disagrees with the published one, the disagreement is
RECORDED, not closed, and the record has to name the right culprit.  No
tolerance in this file was widened to make a number pass and no constant in
bj/ev.py was nudged.  Every number written down below was printed by the code
in this repository on the date given.

A NOTE ON THE PREVIOUS VERSION OF THIS HEADER
---------------------------------------------
Until 2026-09-02 this file recorded two residuals and MISDIAGNOSED BOTH, and
both misdiagnoses blamed Wizard of Odds rather than this code.  That is the
worst way to be wrong in a project whose whole point is being able to defend
its numbers out loud, so the corrections are stated here plainly rather than
quietly edited away.

  * 11 vs A double, recorded as -0.00250 and explained as "the published cell
    is probably not the (6,5) composition it is labelled with".  It IS that
    composition.  The solver was wrong.  bj.ev applied the dealer peek only to
    the dealer's own draw and never to the player's, even though at a peek
    table the hole card is dealt and the peek resolved before the player is
    allowed to act.  Fixed; the residual is now +0.00001.  See the PEEK section
    of the bj.ev docstring.

  * 9,9 vs 7 split, recorded as +0.00480 and explained as the independent-split
    -hands approximation, "optimistic, in the predicted direction".  It is not
    that.  It is a RESPLIT CONVENTION difference.  Wizard of Odds Appendix 9
    resplits whenever the table allows; bj.ev resplits only when resplitting is
    worth more, which for 9,9 against a 7 it usually is not.  Forcing the
    resplit reproduces the published cell: +0.36385 against +0.3642, a residual
    of -0.00035.  test_nine_nine_vs_seven_is_a_resplit_convention_difference
    computes both conventions so the claim is checked, not asserted.

MEASURED RESIDUALS, computed minus published, 2026-09-02, post-fix
------------------------------------------------------------------
All 15 rows of handoff appendix section 4, 6 decks S17 DAS peek, exact card
removal for the named two-card composition:

    hand           stand      hit     double     split
    12 v 2  T,2   -0.00002  +0.00005  -0.00000
    12 v 3  T,2   -0.00003  +0.00005  -0.00000
    12 v 4  T,2   -0.00002  +0.00004  -0.00003
    13 v 2  T,3   +0.00003  -0.00003  +0.00003
    15 v 10 T,5   +0.00004  -0.00001  -0.00001
    16 v 10 T,6   +0.00005  +0.00002  +0.00005
    11 v A  6,5   +0.00002  -0.00000  +0.00001
    10 v 10 8,2   -0.00002  -0.00001  +0.00004
    9 v 2   7,2   -0.00001  +0.00000  -0.00002
    A,7 v 9       -0.00004  +0.00003  -0.00002
    A,7 v 10      +0.00004  -0.00001  -0.00005
    A,6 v 2       -0.00001  -0.00001  +0.00005
    A,7 v A       +0.00002  -0.00004  -0.00001
    8,8 v 10      +0.00005  +0.00004  -0.00002  +0.00050
    9,9 v 7       -0.00002  +0.00002  +0.00005  +0.00480

Every stand, hit and double lands within 0.00005 - the published tables' own
display precision - so there is no KNOWN_GAPS list any more and none is wanted.
The two split residuals are the only ones left, and both are explained above:
+0.00050 on 8,8 vs 10 is the independent-hands approximation, and +0.00480 on
9,9 vs 7 is the resplit convention, which collapses to -0.00035 when the
convention is matched.

HOUSE EDGE, computed 2026-09-02
-------------------------------
    composition-dependent optimum  -0.004029   (published -0.004026, gap 3e-06)
    the printed chart in bj.strategy -0.004044 (published working ~-0.0041)
The optimum moved from -0.004068 to -0.004029 across the peek and shared-pool
fixes, i.e. TOWARDS the published -0.004026, and it now sits 3e-06 from it.
The chart moved from -0.004083 to -0.004044, i.e. away from the handoff's
rounded "about 0.41%" and towards 0.40%.  Two honest notes on that:

  * -0.0041 is a rounded working figure quoted in prose, not a solved cell, and
    the same appendix gives the solved optimum as -0.4026%.  A chart that costs
    1.5e-05 more than the optimum is a more credible reading than one costing
    7e-05, because the printed chart differs from the optimum on a handful of
    rare cells and nothing else.
  * -0.004083, not the -0.004101 recorded earlier, is the correct "before" for
    the chart, because bj/strategy.py's 4,4 row was corrected in between (4,4
    vs 4 is H, not Ph) and that is not this module's doing.  The two numbers
    reconcile exactly: putting the old Ph cell back costs 1.8e-05, and
    -0.004083 - 0.000018 = -0.004101.  Of the total move, +3.9e-05 belongs to
    this module and +1.8e-05 to the 4,4 correction.  Inside this module's
    +3.9e-05: +5.9e-05 from the shared resplit pool, and -2.0e-05 from the peek
    correction.  The peek correction is a small net LOSS to the player, and it
    is a net of both signs, not a one-way push - it raises 11 vs A double by
    0.00251 and lowers A,7 vs A hit by 0.00037.  The optimum, which never reads
    bj.strategy, moved by the same +3.9e-05.

CHART DIFF
----------
derive_table() now reproduces all 170 hard cells, all 80 soft cells and all 100
pair cells of bj.strategy: zero disagreements.  The 4,4 vs 4 cell that this
file used to carry as a permitted exception is no longer one - bj.strategy was
corrected to H, which is what this solver derives, by 0.039 units.  The
allowance has been deleted rather than left in place, because a permitted
exception nobody can trigger is a hole in the only test that grades the
transcription.

RUNTIME
-------
The two house_edge calls and the two derive_table calls dominate: roughly 90 s,
5 s, 75 s and 15 s cold, sharing memo tables, so the suite lands around two
minutes.  They are session-scoped fixtures so each runs once.  The shared
resplit pool is part of why the optimum is slower than it was; it evaluates
split subtrees the halved budget could not reach.
"""
from __future__ import annotations

import math
from dataclasses import replace

import pytest

from bj.core import (
    STANDARD,
    DOUBLE,
    HIT,
    RANKS,
    RANK_INDEX,
    SPLIT,
    STAND,
    fresh_shoe,
    hand_total,
    remove_cards,
    shoe_size,
)
from bj import ev
from bj import strategy as st
from bj.strategy import basic_action

# --- the published reference -----------------------------------------------
# Handoff appendix section 4, "EV tables for marginal hands (6-deck S17, per
# unit; WoO Appendix 9 6ds17r4)".  Transcribed verbatim, including the two-card
# composition each row names, because the composition is the whole point: a
# 12 vs 2 made of T,2 is not the same problem as one made of 7,5.
#   (label, player cards, upcard, stand, hit, double, split or None, best action)
PUBLISHED = (
    ('12 v 2 (T,2)',  ('T', '2'), '2', -0.2958, -0.2519, -0.5037, None, HIT),
    ('12 v 3 (T,2)',  ('T', '2'), '3', -0.2545, -0.2314, -0.4627, None, HIT),
    ('12 v 4 (T,2)',  ('T', '2'), '4', -0.2111, -0.2104, -0.4207, None, HIT),
    ('13 v 2 (T,3)',  ('T', '3'), '2', -0.2958, -0.3071, -0.6143, None, STAND),
    ('15 v 10 (T,5)', ('T', '5'), 'T', -0.5401, -0.5039, -1.0078, None, HIT),
    ('16 v 10 (T,6)', ('T', '6'), 'T', -0.5410, -0.5347, -1.0694, None, HIT),
    ('11 v A (6,5)',  ('6', '5'), 'A', -0.6619, +0.1476, +0.1297, None, HIT),
    ('10 v 10 (8,2)', ('8', '2'), 'T', -0.5392, +0.0262, -0.0064, None, HIT),
    ('9 v 2 (7,2)',   ('7', '2'), '2', -0.2908, +0.0761, +0.0702, None, HIT),
    ('A,7 v 9',       ('A', '7'), '9', -0.1826, -0.0985, -0.2848, None, HIT),
    ('A,7 v 10',      ('A', '7'), 'T', -0.1796, -0.1429, -0.3427, None, HIT),
    ('A,7 v A',       ('A', '7'), 'A', -0.1003, -0.0953, -0.3623, None, HIT),
    ('A,6 v 2',       ('A', '6'), '2', -0.1496, +0.0007, -0.0040, None, HIT),
    ('8,8 v 10',      ('8', '8'), 'T', -0.5369, -0.5354, -1.0707, -0.4754, SPLIT),
    ('9,9 v 7',       ('9', '9'), '7', +0.3996, -0.5872, -1.1744, +0.3642, STAND),
)

TOL_PLAY = 0.002    # stand / hit / double, as specified for this task
TOL_SPLIT = 0.01    # splits carry the independent-hands approximation

#: Tightened to the published tables' own display precision.  Every one of the
#: 45 stand/hit/double cells clears it, so TOL_PLAY above is now slack the
#: suite never uses; this is the tolerance that would actually catch a
#: regression, and test_published_marginal_hand_evs_to_display_precision is the
#: test that enforces it.  There is deliberately no exemption list.
TOL_TIGHT = 0.0001


def _evs(cards, up, rules=STANDARD):
    """Every action's EV for a hand, off a fresh shoe minus the visible cards."""
    shoe = ev.initial_shoe_for(cards, up, rules)
    out = {
        'stand': ev.ev_stand(cards, up, shoe, rules),
        'hit': ev.ev_hit(cards, up, shoe, rules),
        'double': ev.ev_double(cards, up, shoe, rules),
    }
    if len(cards) == 2 and cards[0] == cards[1]:
        out['split'] = ev.ev_split(cards[0], up, shoe, rules)
    return out


# --- session fixtures: the three expensive computations --------------------

@pytest.fixture(scope='session')
def edge_optimal():
    return ev.house_edge()


@pytest.fixture(scope='session')
def edge_chart():
    return ev.house_edge(strategy=basic_action)


@pytest.fixture(scope='session')
def derived():
    return ev.derive_table()


# ===========================================================================
# 1. Shape and units.  Cheap tests that would catch a catastrophe before the
#    slow ones run.
# ===========================================================================

def test_initial_shoe_removes_exactly_the_visible_cards():
    shoe = ev.initial_shoe_for(('T', '6'), 'T')
    full = fresh_shoe(6)
    assert shoe_size(shoe) == shoe_size(full) - 3
    assert shoe[RANKS.index('T')] == full[RANKS.index('T')] - 2
    assert shoe[RANKS.index('6')] == full[RANKS.index('6')] - 1


def test_initial_shoe_refuses_a_hand_the_shoe_cannot_contain():
    # Seven aces of the same rank cannot come out of a six-deck shoe (24 aces
    # exist, so this needs 25).  The point is that the helper fails loudly
    # rather than handing the solver a negative count.
    with pytest.raises(ValueError):
        ev.initial_shoe_for(['A'] * 25, '5')


def test_deck_count_is_honoured():
    assert shoe_size(ev.initial_shoe_for(('T', '6'), 'T',
                                         replace(STANDARD, decks=1))) == 52 - 3


@pytest.mark.parametrize('total', list(range(4, 22)))
def test_stand_ev_is_bounded_by_plus_and_minus_one(total):
    shoe = ev.initial_shoe_for(('T', '6'), '7')
    value = ev._stand_ev(total, '7', shoe, True)
    assert -1.0 <= value <= 1.0


def test_stand_ev_never_falls_as_the_total_rises():
    # A higher standing total wins strictly more dealer outcomes and loses
    # strictly fewer.  If this ever inverts, the win/lose/push comparison in
    # _stand_ev has been written backwards, which is the kind of sign error
    # that still produces plausible-looking numbers.
    shoe = ev.initial_shoe_for(('T', '6'), '9')
    values = [ev._stand_ev(t, '9', shoe, True) for t in range(12, 22)]
    assert values == sorted(values)


def test_busting_is_worth_exactly_minus_one():
    assert ev._stand_ev(22, 'T', ev.initial_shoe_for(('T', '6'), 'T'), True) == -1.0


def test_double_is_exactly_twice_one_card_then_stand():
    # Recomputed here from scratch rather than by calling the module, so the
    # test is an independent statement of what "double" means: exactly one
    # card, no further decision, two units.
    from bj.core import remove_card
    cards, up = ('5', '6'), '6'
    shoe = ev.initial_shoe_for(cards, up)
    total, soft = hand_total(cards)
    n = shoe_size(shoe)
    manual = 0.0
    for i, count in enumerate(shoe):
        p = count / n
        new_total, _ = ev._draw(total, soft, i)
        if new_total > 21:
            manual -= p
        else:
            manual += p * ev._stand_ev(new_total, up, remove_card(shoe, i), True)
    assert ev.ev_double(cards, up, shoe) == pytest.approx(2.0 * manual, abs=1e-12)


def test_hit_is_never_worse_than_doubling_for_half_the_money():
    # Hitting is "draw one card, then choose again"; half a double is "draw one
    # card, then stand".  Extra choice cannot hurt, so this inequality must
    # hold for every hand.  It is the cheapest available check that the hit
    # recursion is really taking a maximum and not, say, an average.
    for cards, up in ((('9', '2'), '7'), (('T', '6'), 'T'), (('A', '7'), '9'),
                      (('5', '3'), '5'), (('T', '5'), 'A')):
        shoe = ev.initial_shoe_for(cards, up)
        assert ev.ev_hit(cards, up, shoe) >= ev.ev_double(cards, up, shoe) / 2 - 1e-12


def test_a_natural_pays_the_posted_payout_and_nothing_else():
    # Post-peek the dealer cannot hold a natural, and a natural beats a drawn
    # 21, so there is no distribution to consult: the number is the payout.
    assert ev.ev_stand(('A', 'T'), '9') == pytest.approx(1.5)
    assert ev.ev_stand(('A', 'T'), 'A') == pytest.approx(1.5)
    six_five = replace(STANDARD, blackjack_payout=1.2)
    assert ev.ev_stand(('A', 'T'), '9', None, six_five) == pytest.approx(1.2)


def test_a_split_hand_that_makes_21_is_not_a_natural():
    shoe = ev.initial_shoe_for(('A', 'T'), '9')
    assert ev.ev_stand(('A', 'T'), '9', shoe, is_split_hand=True) < 1.0


def test_busted_hands_raise_rather_than_being_advised():
    shoe = ev.initial_shoe_for(('T', '9', '5'), '7')
    for fn in (ev.ev_hit, ev.ev_double):
        with pytest.raises(ValueError):
            fn(('T', '9', '5'), '7', shoe)
    with pytest.raises(ValueError):
        ev.best_action(('T', '9', '5'), '7', shoe)


def test_an_empty_shoe_raises_rather_than_inventing_an_outcome():
    empty = (0,) * 10
    with pytest.raises(ValueError):
        ev._hit_ev(12, False, '6', empty, True)
    with pytest.raises(ValueError):
        ev._double_ev(12, False, '6', empty, True)


# ===========================================================================
# 2. The published marginal-hand table.  This is the load-bearing test.
# ===========================================================================

@pytest.mark.parametrize('row', PUBLISHED, ids=[r[0] for r in PUBLISHED])
def test_published_marginal_hand_evs(row):
    """The acceptance target: 0.002 on stand/hit/double, 0.01 on splits.

    No cell is exempt.  The exemption this test used to carry, for 11 vs A
    double, was hiding a real bug in bj.ev and not a flaw in the published
    table; see this module's docstring.
    """
    label, cards, up, p_stand, p_hit, p_double, p_split, _best = row
    got = _evs(cards, up)
    checks = (('stand', p_stand, TOL_PLAY),
              ('hit', p_hit, TOL_PLAY),
              ('double', p_double, TOL_PLAY),
              ('split', p_split, TOL_SPLIT))
    failures = []
    for name, published, tol in checks:
        if published is None:
            continue
        gap = got[name] - published
        if abs(gap) > tol:
            failures.append(f'{name}: computed {got[name]:+.5f} vs published '
                            f'{published:+.5f}, gap {gap:+.5f} > {tol}')
    assert not failures, f'{label}\n  ' + '\n  '.join(failures)


@pytest.mark.parametrize('row', PUBLISHED, ids=[r[0] for r in PUBLISHED])
def test_published_marginal_hand_evs_to_display_precision(row):
    """The same 45 non-split cells at 0.0001 instead of 0.002.

    The looser test above is the contract; this one is the actual state of the
    module, and it is the one that will notice a regression.  A change that
    keeps every cell inside 0.002 while moving one of them by 0.0005 is not a
    rounding difference, it is a modelling change, and it should have to be
    argued for rather than absorbed by slack.
    """
    label, cards, up, p_stand, p_hit, p_double, _p_split, _best = row
    got = _evs(cards, up)
    for name, published in (('stand', p_stand), ('hit', p_hit),
                            ('double', p_double)):
        assert got[name] == pytest.approx(published, abs=TOL_TIGHT), (
            f'{label} {name}: computed {got[name]:+.6f} vs published '
            f'{published:+.5f}')


def test_eleven_vs_ace_is_not_played_clairvoyantly():
    """The trap the peek fix has to avoid, pinned by number.

    The dealer's hole card is dealt and peeked at before the player acts, so
    the peek belongs in the player's own draw distribution and not only in the
    dealer's.  But the player still cannot SEE the hole card, so every
    stand/hit comparison has to be made on a value averaged over the surviving
    hole cards.  Taking the maximum inside the hole-card loop instead is
    clairvoyant play: it is a legal-looking recursion that returns the EV of a
    player who is being told the hole card before deciding.

    On this exact hand the two answers are 0.1476 and 0.1867 - four whole
    percent of a bet apart - so this assertion is not a rounding guard, it is
    the difference between modelling blackjack and modelling a cheat.  Two
    people wrote the clairvoyant version of this hand on the same day, which is
    why the number it produces is pinned here by name.
    """
    got = ev.ev_hit(('6', '5'), 'A')
    assert got == pytest.approx(0.1476, abs=TOL_TIGHT)
    assert abs(got - 0.1867) > 0.03, (
        f'ev_hit for 6,5 vs A came out {got:+.5f}, which is the clairvoyant '
        'value: the hole-card maximum is being taken inside the loop instead '
        'of on the belief-averaged value')


def test_eleven_vs_ace_double_now_matches_the_published_cell():
    """The blocker, closed.

    This used to be a recorded disagreement of -0.00250 with a note blaming the
    published table.  The table was right.  Pinned tightly so the fix cannot
    rot back.
    """
    assert ev.ev_double(('6', '5'), 'A') == pytest.approx(0.1297, abs=TOL_TIGHT)


def test_the_peek_only_touches_the_two_upcards_it_can_touch():
    """The player-side peek correction is exactly zero for 2 through 9.

    Against those upcards the dealer looks at nothing, so the draw distribution
    must be bit-for-bit the naive one.  This is the cheapest available proof
    that the correction is conditioned on the right thing: if it ever starts
    nudging a 7, it is conditioning on something that did not happen.
    """
    for up in ('2', '3', '4', '5', '6', '7', '8', '9'):
        shoe = ev.initial_shoe_for(('6', '5'), up)
        n = shoe_size(shoe)
        assert ev._draw_probs(shoe, up) == tuple(c / n for c in shoe)
        assert ev._peek_out(up) == -1


@pytest.mark.parametrize('up,enriched', (('A', 'T'), ('T', 'A')))
def test_the_peek_enriches_the_rank_it_ruled_out(up, enriched):
    """Under an ace the player's next card is ten-RICH, not ten-poor.

    The hole card is one of the cards the player cannot see, and the peek has
    just certified that it is not a ten.  So every ten that is left is still in
    the draw pile, while every other rank has to share the pile with one card
    that has been removed from it.  Getting this backwards would look just as
    plausible and would move 11 vs A the wrong way.
    """
    shoe = ev.initial_shoe_for(('6', '5'), up)
    n = shoe_size(shoe)
    probs = ev._draw_probs(shoe, up)
    out = RANKS.index(enriched)
    assert probs[out] > shoe[out] / n
    assert probs[out] == pytest.approx(shoe[out] / (n - 1))
    for i, count in enumerate(shoe):
        if i != out and count:
            assert probs[i] < count / n
    assert sum(probs) == pytest.approx(1.0, abs=1e-12)


def test_the_peek_correction_is_a_probability_distribution_everywhere():
    # A conditioning step that does not sum to one is the classic way to get a
    # small, plausible, and completely wrong answer out of a recursion.
    for up in RANKS:
        for cards in ((up, '5'), ('T', 'T'), ('A', 'A')):
            shoe = ev.initial_shoe_for(cards, up)
            probs = ev._draw_probs(shoe, up)
            assert sum(probs) == pytest.approx(1.0, abs=1e-12)
            assert all(p >= 0.0 for p in probs)
            assert all(p == 0.0 for p, c in zip(probs, shoe) if c == 0)


@pytest.mark.parametrize('row', PUBLISHED, ids=[r[0] for r in PUBLISHED])
def test_published_best_action_column(row):
    """The "Best" column of the published table, all fifteen rows.

    This is the assertion that actually matters at the table.  An EV can be a
    thousandth off and cost nothing; a wrong Best column is a wrong button.
    Includes the three near-ties the handoff calls out (12 vs 4 at 0.0008,
    A,7 vs A at 0.005, 16 vs 10 at 0.0063), which is the whole reason the
    dealer and the player are both solved exactly.
    """
    label, cards, up, _s, _h, _d, p_split, expected = row
    action, evs, margin = ev.best_action(cards, up,
                                         can_split=p_split is not None)
    assert action == expected, (
        f'{label}: solver says {action}, published Best column says {expected}; '
        f'evs={ {k: round(v, 5) for k, v in evs.items()} }')
    assert margin > 0.0


@pytest.mark.parametrize('cards,up,published_margin,tol', (
    # 12 vs 4, the closest decision in the game.  Computed 0.00075.
    (('T', '2'), '4', 0.0008, 0.0002),
    # Two-card 16 vs a ten.  Computed 0.00628.
    (('T', '6'), 'T', 0.0063, 0.0002),
    # Soft 18 vs an ace.  Computed 0.00493.  This cell used to need 0.0004 of
    # slack, justified in this file by a +0.00033 residual on the A,7 vs A hit.
    # That residual was the peek bug, not a fact about the published table, and
    # it is gone: the hit is now -0.09534 against a published -0.0953.  The
    # slack went with it.
    (('A', '7'), 'A', 0.005, 0.0002),
    # 11 vs A, the hand the peek bug lived on.  Hit over double, and the margin
    # is the published 0.018 rather than the 0.0196 the bug produced.
    (('6', '5'), 'A', 0.018, 0.0002),
))
def test_published_near_tie_margins(cards, up, published_margin, tol):
    """The three near-ties, checked as margins rather than as actions.

    Getting the action right on a 0.0008 margin could be luck.  Getting the
    margin right to a ten-thousandth cannot be.
    """
    _action, _evs_, margin = ev.best_action(cards, up)
    assert margin == pytest.approx(published_margin, abs=tol)


# ===========================================================================
# 3. The composition-dependent claims.  These are the reason the module
#    exists: an infinite-deck or total-only solver gets all three wrong.
# ===========================================================================

@pytest.mark.parametrize('cards,up,claimed_stand_minus_hit', (
    (('8', '5', '3'), 'T', +0.004),    # three-card 16: standing wins
    (('T', '6'), 'T', -0.0063),        # two-card 16: hitting wins
    (('9', '7'), 'T', -0.0014),        # the closer two-card 16
))
def test_multi_card_sixteen_versus_ten(cards, up, claimed_stand_minus_hit):
    shoe = ev.initial_shoe_for(cards, up)
    gap = ev.ev_stand(cards, up, shoe) - ev.ev_hit(cards, up, shoe)
    assert gap == pytest.approx(claimed_stand_minus_hit, abs=0.0005)
    expected = STAND if claimed_stand_minus_hit > 0 else HIT
    assert ev.best_action(cards, up, shoe)[0] == expected


def test_the_exception_is_about_composition_not_card_count():
    """A three-card 16 vs a ten does NOT always stand.

    This is a finding, not a rule the handoff prints.  Of the fifteen hard
    three-card 16s, the solver stands on nine and hits six.  4,6,6 in
    particular hits by 0.0043 despite containing a 4, because it has eaten two
    of the sixes that would have busted the hit.  The handoff's loose rule
    ("3+ cards -> stand") is right on 9 of 15; its sharper rule ("contains a 4
    or a 5") is right on 12 of 15, missing 4,6,6 and wrongly hitting A,7,8 and
    2,7,7.  The test asserts the two ends of that spread so nobody upgrades
    either heuristic into a claim of exactness.
    """
    stands = ev.initial_shoe_for(('4', '5', '7'), 'T')
    hits = ev.initial_shoe_for(('4', '6', '6'), 'T')
    assert ev.best_action(('4', '5', '7'), 'T', stands)[0] == STAND
    assert ev.best_action(('4', '6', '6'), 'T', hits)[0] == HIT


def test_identical_totals_from_different_cards_get_different_answers():
    # 10,6 and 9,7 are both a hard 16 vs a ten, and the solver must not think
    # they are the same hand.  A total-only cache key would collapse them.
    a = ev.initial_shoe_for(('T', '6'), 'T')
    b = ev.initial_shoe_for(('9', '7'), 'T')
    assert ev.ev_stand(('T', '6'), 'T', a) != ev.ev_stand(('9', '7'), 'T', b)
    assert ev.ev_hit(('T', '6'), 'T', a) != ev.ev_hit(('9', '7'), 'T', b)


# ===========================================================================
# 4. Splits.
# ===========================================================================

def _one_split_hand(rank, up, shoe, pool, rules=STANDARD):
    """EV of ONE pending split hand allowed `pool` extra hands of its own.

    Composed from bj.ev's own primitive, which is the point: the tests below
    reassemble the OLD halved-budget allocation out of it and compare, so the
    comparison does not depend on a second implementation nobody maintains.
    """
    rows = ev._split_hand_outcomes(RANK_INDEX[rank], up, shoe, pool, rules.s17,
                                   rules.das, rules.hit_split_aces,
                                   rules.resplit_aces)
    assert sum(p for _u, p, _m in rows) == pytest.approx(1.0, abs=1e-12)
    return sum(p * m for _u, p, m in rows)


def test_split_ev_is_in_original_bet_units():
    # 8,8 vs 10 puts two units on the table and still loses; -0.4749 is per
    # ORIGINAL unit, not per unit finally wagered.  If the module were
    # reporting per-hand rather than per-original-bet, this number would be
    # about half.
    shoe = ev.initial_shoe_for(('8', '8'), 'T')
    assert ev.ev_split('8', 'T', shoe) == pytest.approx(-0.4754, abs=TOL_SPLIT)


def test_the_resplit_budget_is_one_shared_pool_not_two_allowances():
    """max_hands is a pool the round spends out of, not an allowance per hand.

    bj.ev used to halve the budget at each split, which caps the tree at the
    right number of hands but forbids a shape a real table allows: hand one
    resplitting twice while hand two never pairs at all.  The old allocation is
    reconstructed here from the module's own primitive - two hands with one
    extra hand each - and the shared pool must beat it, because the shared pool
    can produce every tree the divided one can and more.

    8,8 vs 7 is pinned because it is the worst cell measured: the halved budget
    was 0.0109 low there, which is five times the tolerance this suite holds a
    stand or a hit to.  It was low on 42 of the 100 pair cells, 26 of them by
    more than that 0.002 tolerance.
    """
    shoe = ev.initial_shoe_for(('8', '8'), '7')
    shared = ev.ev_split('8', '7', shoe)
    divided = 2 * _one_split_hand('8', '7', shoe, 1)
    assert shared == pytest.approx(0.31863, abs=5e-5)
    assert divided == pytest.approx(0.30771, abs=5e-5)
    assert shared - divided == pytest.approx(0.01093, abs=5e-5)


@pytest.mark.parametrize('pair,up', (('8', '6'), ('7', '6'), ('2', '5'),
                                     ('3', '4'), ('6', '3'), ('9', '6')))
def test_the_shared_pool_is_never_worse_than_the_divided_one(pair, up):
    # Not a pinned number: a theorem.  Every tree the halved budget can build
    # is still legal under the shared pool, so the shared value dominates cell
    # by cell.  If this ever inverts, the pool bookkeeping is losing hands.
    shoe = ev.initial_shoe_for((pair, pair), up)
    assert ev.ev_split(pair, up, shoe) >= 2 * _one_split_hand(pair, up, shoe, 1) - 1e-12


def test_splitting_late_in_a_round_has_fewer_resplits_behind_it():
    """best_action must shrink the split budget by hand_count.

    bj.simulate reaches this path: it calls best_action with
    hand_count=len(hands).  Before this was fixed, a player who had already
    split twice was quoted +0.3077 for splitting 8,8 vs 7 - the value of a
    split with two resplits still available, which he does not have.  The true
    remaining budget is worth +0.2184.  Quoting the first number is quoting an
    option the table will not sell him.
    """
    shoe = ev.initial_shoe_for(('8', '8'), '7')
    fresh = ev.best_action(('8', '8'), '7', shoe, hand_count=1)[1][SPLIT]
    late = ev.best_action(('8', '8'), '7', shoe, hand_count=3)[1][SPLIT]
    assert fresh == pytest.approx(0.31863, abs=5e-5)
    assert late == pytest.approx(0.21842, abs=5e-5)
    assert late < fresh


def test_the_last_split_of_a_round_is_worth_exactly_a_split_to_two_hands():
    """An identity, not a measurement.

    Splitting as the third of four allowed hands leaves the two resulting hands
    no resplits between them, which is the same game as a table that only ever
    allows two hands.  The two routes into that state must return the same
    float, and they exercise different arithmetic to get there.
    """
    shoe = ev.initial_shoe_for(('8', '8'), '7')
    late = ev.ev_split('8', '7', shoe, STANDARD, hand_count=3)
    no_resplit_table = ev.ev_split('8', '7', shoe, replace(STANDARD, max_hands=2))
    assert late == no_resplit_table


@pytest.mark.parametrize('hand_count', (1, 2))
def test_split_value_falls_monotonically_as_hands_fill_up(hand_count):
    # hand_count runs to max_hands - 1: at max_hands there is nothing to split
    # into, which the next test checks is refused rather than valued.
    shoe = ev.initial_shoe_for(('8', '8'), '6')
    here = ev.ev_split('8', '6', shoe, STANDARD, hand_count=hand_count)
    later = ev.ev_split('8', '6', shoe, STANDARD, hand_count=hand_count + 1)
    assert here >= later - 1e-12


def test_splitting_a_hand_that_cannot_be_split_is_refused():
    shoe = ev.initial_shoe_for(('8', '8'), '6')
    with pytest.raises(ValueError):
        ev.ev_split('8', '6', shoe, STANDARD, hand_count=STANDARD.max_hands)


def test_nine_nine_vs_seven_is_a_resplit_convention_difference():
    """The second corrected misdiagnosis, computed rather than asserted.

    This file used to blame the +0.00480 gap on the independent-split-hands
    approximation.  It is the resplit convention: Wizard of Odds Appendix 9
    resplits whenever the table allows, bj.ev resplits only when resplitting is
    worth more, and for 9,9 against a 7 it usually is not.  The test forces the
    other convention and shows the published cell falling out of it.

    Forcing it is done by taking the module's own resplit subtree and adding it
    up without the comparison, which is exactly the difference between the two
    conventions and nothing else.
    """
    up, rank = '7', '9'
    shoe = ev.initial_shoe_for((rank, rank), up)
    rank_i = RANK_INDEX[rank]
    published = 0.3642

    only_when_better = ev.ev_split(rank, up, shoe)
    assert only_when_better == pytest.approx(0.36900, abs=5e-5)
    assert only_when_better - published == pytest.approx(0.00480, abs=5e-5)

    # The same tree, resplitting on every pair the table would allow.
    pool = ev._split_pool(STANDARD, 1)

    def forced(shoe_, slots):
        acc = {}
        for i, p in enumerate(ev._draw_probs(shoe_, up)):
            if p <= 0.0:
                continue
            sub = remove_cards(shoe_, (RANKS[i],))
            if i == rank_i and slots >= 1:
                for k1, p1, m1 in forced(sub, slots - 1):
                    for k2, p2, m2 in forced(sub, slots - 1 - k1):
                        key = 1 + k1 + k2
                        q, w = acc.get(key, (0.0, 0.0))
                        acc[key] = (q + p * p1 * p2, w + p * p1 * p2 * (m1 + m2))
                continue
            total, soft = ev._two_card_state(rank_i, i)
            best = max(ev._stand_ev(total, up, sub, STANDARD.s17),
                       ev._hit_ev(total, soft, up, sub, STANDARD.s17),
                       ev._double_ev(total, soft, up, sub, STANDARD.s17))
            q, w = acc.get(0, (0.0, 0.0))
            acc[0] = (q + p, w + p * best)
        return tuple((k, q, w / q) for k, (q, w) in sorted(acc.items()))

    whenever_allowed = 0.0
    for used, p, first in forced(shoe, pool):
        whenever_allowed += p * (first + sum(q * m for _u, q, m in forced(shoe, pool - used)))

    assert whenever_allowed == pytest.approx(0.36385, abs=5e-5)
    assert abs(whenever_allowed - published) < abs(only_when_better - published)
    assert whenever_allowed - published == pytest.approx(-0.00035, abs=5e-5)


def test_the_frozen_split_ace_is_never_offered_a_hit_or_a_double():
    """A split ace gets one card, so HIT and DOUBLE are not on the table.

    Under resplit_aces with hit_split_aces off - a real combination, and one of
    the two rules the handoff lists as unconfirmed at the example table - best_action
    used to hand back HIT and DOUBLE entries for a split pair of aces because
    the "no decision" shortcut was skipped whenever a resplit was available.
    That breaks its own docstring promise that unavailable actions are absent,
    and it corrupts the margin, which is measured against the second-best
    AVAILABLE action.
    """
    rules = replace(STANDARD, resplit_aces=True, hit_split_aces=False)
    shoe = ev.initial_shoe_for(('A', 'A'), '6', rules)
    action, evs, margin = ev.best_action(('A', 'A'), '6', shoe, rules,
                                         is_split_hand=True, hand_count=2)
    assert set(evs) == {STAND, SPLIT}
    assert action == SPLIT
    assert margin == pytest.approx(evs[SPLIT] - evs[STAND])

    # With hitting split aces allowed, all four buttons come back.
    generous = replace(rules, hit_split_aces=True)
    _a, evs, _m = ev.best_action(('A', 'A'), '6', shoe, generous,
                                 is_split_hand=True, hand_count=2)
    assert set(evs) == {STAND, HIT, DOUBLE, SPLIT}


def test_a_split_seven_that_drew_an_ace_is_not_a_frozen_split_ace():
    # The freeze keys on the SPLIT rank, which callers keep first in the tuple,
    # not on "the hand contains an ace".  7,A is a soft 18 with every button.
    rules = replace(STANDARD, resplit_aces=True, hit_split_aces=False)
    shoe = ev.initial_shoe_for(('7', 'A'), '6', rules)
    _a, evs, _m = ev.best_action(('7', 'A'), '6', shoe, rules,
                                 is_split_hand=True, hand_count=2)
    assert set(evs) == {STAND, HIT, DOUBLE}


def test_splitting_eights_against_a_ten_beats_giving_up_and_hitting():
    # The handoff calls this out specifically: do not "give up" on 8,8 vs 10.
    shoe = ev.initial_shoe_for(('8', '8'), 'T')
    action, evs, margin = ev.best_action(('8', '8'), 'T', shoe)
    assert action == SPLIT
    assert evs[SPLIT] - max(evs[HIT], evs[STAND]) == pytest.approx(0.060, abs=0.01)


def test_more_hands_allowed_is_never_worse():
    # Resplitting is optional, so raising the cap can only add options.
    shoe = ev.initial_shoe_for(('8', '8'), '6')
    two = ev.ev_split('8', '6', shoe, replace(STANDARD, max_hands=2))
    four = ev.ev_split('8', '6', shoe, replace(STANDARD, max_hands=4))
    assert four >= two
    assert four > two          # 8,8 vs 6 genuinely wants the resplits


def test_das_is_worth_something_and_the_solver_can_see_it():
    shoe = ev.initial_shoe_for(('2', '2'), '6')
    with_das = ev.ev_split('2', '6', shoe, STANDARD)
    without = ev.ev_split('2', '6', shoe, replace(STANDARD, das=False))
    assert with_das > without


def test_split_aces_get_one_card_unless_the_rules_say_otherwise():
    # The two unknown rules from the handoff.  Turning both on is worth a lot
    # per split hand, which is why the handoff says the house edge could drop
    # toward 0.30% if they turn out to be allowed.
    shoe = ev.initial_shoe_for(('A', 'A'), '6')
    strict = ev.ev_split('A', '6', shoe, STANDARD)
    generous = ev.ev_split('A', '6', shoe,
                           replace(STANDARD, hit_split_aces=True, resplit_aces=True))
    assert generous > strict + 0.3


def test_split_aces_have_no_decision_to_offer():
    shoe = ev.initial_shoe_for(('A', 'A'), '6')
    shoe = remove_cards(shoe, ('7',))
    action, evs, margin = ev.best_action(('A', '7'), '6', shoe,
                                         is_split_hand=True, hand_count=2)
    assert action == STAND
    assert set(evs) == {STAND}
    assert margin == 0.0


@pytest.mark.parametrize('up', ('2', '3', '4', '5', '6', '7', '8', '9', 'T', 'A'))
def test_never_split_tens(up):
    """A project honesty rule, checked as arithmetic rather than asserted.

    Splitting tens is the most expensive common mistake in the game (~8% per
    the handoff).  The tool is forbidden from recommending it; this shows the
    solver would not want to anyway, against every upcard.
    """
    shoe = ev.initial_shoe_for(('T', 'T'), up)
    assert ev.ev_stand(('T', 'T'), up, shoe) > ev.ev_split('T', up, shoe)
    assert ev.best_action(('T', 'T'), up, shoe)[0] == STAND


# ===========================================================================
# 5. best_action's contract.
# ===========================================================================

def test_margin_is_the_gap_to_the_second_best_available_action():
    action, evs, margin = ev.best_action(('T', '2'), '4')
    ranked = sorted(evs.values(), reverse=True)
    assert evs[action] == ranked[0]
    assert margin == pytest.approx(ranked[0] - ranked[1])


def test_unavailable_actions_are_absent_not_zero():
    _a, evs, _m = ev.best_action(('8', '8'), 'T', can_double=False, can_split=False)
    assert set(evs) == {STAND, HIT}


def test_a_third_card_removes_the_double_button_even_if_the_caller_says_otherwise():
    # No table on earth allows doubling after a hit.  A caller passing
    # can_double=True on a three-card hand is wrong, and the module must not
    # take its word for it.
    _a, evs, _m = ev.best_action(('8', '5', '3'), 'T', can_double=True)
    assert DOUBLE not in evs


def test_hand_count_at_the_cap_removes_the_split_button():
    _a, evs, _m = ev.best_action(('8', '8'), '6', hand_count=4)
    assert SPLIT not in evs
    _a, evs, _m = ev.best_action(('8', '8'), '6', hand_count=3)
    assert SPLIT in evs


def test_das_off_removes_the_double_button_on_a_split_hand():
    shoe = ev.initial_shoe_for(('8', '3'), '6')
    _a, evs, _m = ev.best_action(('8', '3'), '6', shoe,
                                 replace(STANDARD, das=False), is_split_hand=True)
    assert DOUBLE not in evs
    _a, evs, _m = ev.best_action(('8', '3'), '6', shoe, STANDARD, is_split_hand=True)
    assert DOUBLE in evs


def test_a_natural_is_reported_as_a_non_decision():
    action, evs, margin = ev.best_action(('A', 'T'), '9')
    assert action == STAND
    assert evs == {STAND: 1.5}
    assert margin == 0.0


def test_shoe_defaults_to_a_fresh_one_minus_the_visible_cards():
    explicit = ev.best_action(('T', '6'), 'T', ev.initial_shoe_for(('T', '6'), 'T'))
    implied = ev.best_action(('T', '6'), 'T')
    assert explicit == implied


def test_card_input_forms_are_interchangeable():
    a = ev.best_action(['K', 6], 'Q')
    b = ev.best_action('T,6', 'T')
    assert a == b


# ===========================================================================
# 6. House edge.
# ===========================================================================

def test_house_edge_of_the_composition_dependent_optimum(edge_optimal):
    """Published: -0.4026% (Wizard of Odds Appendix 9, 6ds17r4, with DAS).

    The contract is 0.0004.  The second assertion is much tighter than that on
    purpose: the peek and shared-pool fixes moved this number from -0.004068 to
    -0.004029, which is 3e-06 from the published cell, and a pin at that level
    is the only thing that would notice either fix silently regressing.
    """
    assert edge_optimal == pytest.approx(-0.004026, abs=0.0004), (
        f'computed {edge_optimal:.6f}')
    assert edge_optimal == pytest.approx(-0.004029, abs=2e-05), (
        f'computed {edge_optimal:.6f}; this used to be -0.004068 before the '
        'peek and shared-pool fixes')


def test_house_edge_of_the_printed_chart(edge_chart):
    """Published working figure for total-dependent basic strategy: ~-0.41%.

    -0.0041 is prose, rounded, and the same appendix solves the optimum at
    -0.4026%.  This computes -0.004044, which is 1.5e-05 worse than the
    optimum - a chart that differs from the optimum on a handful of rare cells
    should cost about that, and the module docstring says so with its working.
    """
    assert edge_chart == pytest.approx(-0.0041, abs=0.0004), (
        f'computed {edge_chart:.6f}')
    assert edge_chart == pytest.approx(-0.004044, abs=2e-05), (
        f'computed {edge_chart:.6f}')


def test_the_chart_cannot_beat_the_optimum(edge_optimal, edge_chart):
    # The optimum is a maximum over the same action set the chart chooses from,
    # so this is a theorem.  If it ever fails, one of the two paths is solving
    # a different game - which is exactly the bug that a pair of independently
    # written recursions is here to catch.
    assert edge_optimal >= edge_chart - 1e-12


def test_the_chart_costs_less_than_a_hundredth_of_a_percent(edge_optimal, edge_chart):
    # Recorded because it is the honest answer to "should I carry the phone
    # tool or the card?".  About 1.5e-05 per unit: one and a half gems per
    # hundred thousand wagered.  The tool's value is not the edge, it is not
    # making the mistake the owner made on hand 37.
    assert 0.0 <= edge_optimal - edge_chart < 0.0001
    assert edge_optimal - edge_chart == pytest.approx(1.5e-05, abs=5e-06)


def test_no_player_edge_is_ever_claimed(edge_optimal, edge_chart):
    """A project honesty rule, enforced numerically."""
    assert edge_optimal < 0.0
    assert edge_chart < 0.0


def test_house_edge_refuses_a_game_it_does_not_model():
    with pytest.raises(NotImplementedError):
        ev.house_edge(replace(STANDARD, peek=False))


def test_a_worse_payout_makes_a_worse_game():
    # A cheap directional check on the whole house_edge pipeline using a small
    # shoe so it runs in seconds: 6:5 must be materially worse than 3:2.
    one_deck = replace(STANDARD, decks=1)
    good = ev.house_edge(one_deck)
    bad = ev.house_edge(replace(one_deck, blackjack_payout=1.2))
    assert bad < good
    # ~4.75% of hands are naturals, each losing 0.3 units of payout.
    assert (good - bad) == pytest.approx(0.0475 * 0.3, abs=0.004)


# ===========================================================================
# 7. Rederiving the chart, and diffing it against the transcription.
# ===========================================================================

def test_derived_table_has_the_shape_of_the_printed_chart(derived):
    assert set(derived) == {'hard', 'soft', 'pairs'}
    assert set(derived['soft']) == set(st.SOFT_TABLE)
    assert set(derived['pairs']) == set(st.PAIR_TABLE)
    # The two hard rows that do not line up, and why:
    #  * the solver derives total 4, which exists only as the pair 2,2 and so
    #    has no printed row of its own;
    #  * the printed "17+" row expands to a total of 21, which no two-card
    #    hand can reach without an ace - and A,T is a natural, not a hard 21.
    #    The chart carries the cell for tidiness; there is nothing to derive.
    assert set(derived['hard']) - set(st.HARD_TABLE) == {(4, u) for u in st.DEALER_UPS}
    assert set(st.HARD_TABLE) - set(derived['hard']) == {(21, u) for u in st.DEALER_UPS}
    for section in derived.values():
        assert all(code in st.RAW_CODES for code in section.values())


@pytest.mark.parametrize('section,printed', (
    ('hard', 'HARD_TABLE'), ('soft', 'SOFT_TABLE'), ('pairs', 'PAIR_TABLE'),
))
def test_derived_table_matches_the_transcribed_chart(derived, section, printed):
    """Grade bj.strategy against a from-scratch derivation.

    There is no permitted disagreement.  This test used to carry one, for
    4,4 vs 4, and it is gone because bj.strategy was corrected to the cell this
    solver derives; see test_the_four_four_cell_that_used_to_be_disputed.  An
    allowance nobody can trigger is worse than no allowance, because the next
    person to read it will assume the two sides are known to differ.

    Every cell must match, including all the DAS-sensitive 'Ph' cells and the
    S17-specific ones (11 vs A hits, A,7 vs 2 stands).
    """
    table = getattr(st, printed)
    diffs = {k: (table[k], v) for k, v in derived[section].items()
             if k in table and table[k] != v}
    assert not diffs, (
        'solver disagrees with the printed chart at: '
        + ', '.join(f'{k}: chart {a} -> solver {b}' for k, (a, b) in sorted(
            diffs.items(), key=str)))


def test_the_four_four_cell_that_used_to_be_disputed(derived):
    """4,4 vs 4: the transcription dispute, now settled, quantified anyway.

    The handoff's pairs row printed Ph here and bj.strategy transcribed it;
    this solver said H and said it by a wide margin.  bj.strategy now says H
    too, so the cell is no longer a disagreement - but the margin is pinned
    because that is the evidence the resolution rested on, and a cell that
    quietly drifted back toward a tie would mean the evidence had evaporated.
    """
    assert st.PAIR_TABLE[('4,4', '4')] == 'H'
    assert derived['pairs'][('4,4', '4')] == 'H'
    shoe = ev.initial_shoe_for(('4', '4'), '4')
    action, evs, margin = ev.best_action(('4', '4'), '4', shoe)
    assert action == HIT
    assert evs[HIT] - evs[SPLIT] == pytest.approx(0.039, abs=0.005)
    # Splitting fours against a four is still better than standing on eight -
    # the chart says hit because hitting is better than both, not because
    # splitting is absurd.
    assert evs[SPLIT] > evs[STAND]


def test_derived_table_reproduces_the_s17_sensitive_cells(derived):
    # Handoff section 4: these three cells are the ones that would flip under
    # H17, and getting them wrong is the classic way to play the wrong chart.
    assert derived['hard'][(11, 'A')] == 'H'
    assert derived['soft'][('A,7', '2')] == 'S'
    assert derived['soft'][('A,8', '6')] == 'S'


def test_derived_table_reproduces_the_das_sensitive_cells(derived):
    # Handoff appendix section 1: the cells you split only because DAS exists.
    # That list also names 4,4 vs 4, which is deliberately NOT checked here:
    # the solver hits it by 0.039 and bj.strategy now agrees, so the handoff's
    # pairs table and its own cheat sheet ("4,4 split vs 5 to 6") disagree with
    # each other and the cheat sheet is the one that matches the arithmetic.
    for key in (('2,2', '2'), ('2,2', '3'), ('3,3', '2'), ('3,3', '3'),
                ('4,4', '5'), ('4,4', '6'), ('6,6', '2')):
        assert derived['pairs'][key] == 'Ph', key


def test_h17_moves_the_cells_the_handoff_says_it_moves():
    """Run the whole derivation again under H17 and diff the two charts.

    bj.strategy carries a hand-written three-cell H17 overlay.  This is the
    independent check on it, and it is worth its runtime: it is the only test
    in the project that could catch that overlay being incomplete.
    """
    h17 = ev.derive_table(replace(STANDARD, s17=False))
    s17 = ev.derive_table(STANDARD)
    moved = set()
    for section in ('hard', 'soft', 'pairs'):
        for key, code in h17[section].items():
            if s17[section][key] != code:
                moved.add((key, s17[section][key], code))
    assert (11, 'A') in {k for k, _a, _b in moved}
    assert ('A,7', '2') in {k for k, _a, _b in moved}
    assert ('A,8', '6') in {k for k, _a, _b in moved}
    # Report the full set: bj.strategy's overlay lists exactly three cells, and
    # if the solver finds more the overlay is short.  This assertion is the
    # finding, so it names them.
    assert {k for k, _a, _b in moved} == set(st.H17_DIFFERENCES), (
        'H17 overlay in bj.strategy covers '
        f'{sorted(map(str, st.H17_DIFFERENCES))} but the solver moves '
        f'{sorted(str(k) for k, _a, _b in moved)}')


# ===========================================================================
# 8. Caches are an optimisation, not part of the answer.
# ===========================================================================

def test_clearing_the_caches_changes_nothing():
    before = ev.best_action(('T', '6'), 'T')
    ev.clear_caches()
    after = ev.best_action(('T', '6'), 'T')
    assert before == after


def test_rules_that_differ_only_in_an_irrelevant_field_agree():
    # The split cache is keyed on loose scalars precisely so that two rulesets
    # differing only in, say, insurance payout share entries.  If a key were
    # wrong, this would return a stale number for the second call.
    shoe = ev.initial_shoe_for(('8', '8'), '6')
    a = ev.ev_split('8', '6', shoe, STANDARD)
    b = ev.ev_split('8', '6', shoe, replace(STANDARD, insurance_payout=3.0))
    assert a == b


def test_every_reported_number_is_finite():
    for cards, up in ((('T', '6'), 'T'), (('A', 'A'), 'A'), (('5', '5'), '5'),
                      (('2', '2'), '2'), (('A', '9'), '6')):
        _a, evs, margin = ev.best_action(cards, up)
        assert all(math.isfinite(v) for v in evs.values())
        assert math.isfinite(margin)
