"""Tests for bj.strategy.

Three jobs, in order of importance:

1.  Prove the printed chart in the handoff is the chart in the code.  Every
    cell of all three tables is driven through basic_action with a real hand,
    so a typo in a table literal fails a test instead of costing money.
2.  Prove the fallbacks (no double button, no split left, DAS off) downgrade
    the way the table intends rather than silently returning something else.
3.  Prove the engine reproduces the 37-hand log in section 5 of the handoff,
    which is the only real-world data this project has.
"""
from __future__ import annotations

import pytest

from bj.core import ACTION_NAMES, DOUBLE, HIT, Rules, SPLIT, STAND, hand_total
from bj.strategy import (
    DEALER_UPS,
    HARD_TABLE,
    H17_DIFFERENCES,
    PAIR_TABLE,
    RAW_CODES,
    SOFT_TABLE,
    basic_action,
    resolve_code,
    take_insurance,
)

S17_DAS = Rules()                       # the the example table table
NO_DAS = Rules(das=False)
H17 = Rules(s17=False)


# --- representative hands --------------------------------------------------
# One concrete hand per printed row.  Hard rows use non-pair, ace-free cards so
# the pair and soft charts cannot answer for them; 20 and 21 need three cards
# because every two-card version is a pair or a natural.

HARD_HANDS = {
    5: ('3', '2'), 6: ('4', '2'), 7: ('5', '2'), 8: ('6', '2'),
    9: ('7', '2'), 10: ('8', '2'), 11: ('9', '2'),
    12: ('T', '2'), 13: ('T', '3'), 14: ('T', '4'), 15: ('T', '5'),
    16: ('T', '6'), 17: ('T', '7'), 18: ('T', '8'), 19: ('T', '9'),
    20: ('T', '4', '6'), 21: ('T', '5', '6'),
}


def test_tables_are_the_right_shape():
    assert len(HARD_TABLE) == 17 * 10       # totals 5..21
    assert len(SOFT_TABLE) == 8 * 10        # A,2 .. A,9
    assert len(PAIR_TABLE) == 10 * 10       # A,A .. 2,2
    for table in (HARD_TABLE, SOFT_TABLE, PAIR_TABLE):
        for (key, up), code in table.items():
            assert up in DEALER_UPS
            assert code in RAW_CODES, f'{key} vs {up} has bogus code {code!r}'


def test_hard_hands_cover_every_printed_row():
    assert sorted(HARD_HANDS) == sorted({k for k, _ in HARD_TABLE})
    for total, cards in HARD_HANDS.items():
        got, soft = hand_total(cards)
        assert (got, soft) == (total, False)


# --- every cell of every table round-trips ---------------------------------

@pytest.mark.parametrize('total,up', sorted(HARD_TABLE))
def test_every_hard_cell_round_trips(total, up):
    cards = HARD_HANDS[total]
    can_double = len(cards) == 2            # doubling is a two-card-only action
    adv = basic_action(cards, up, S17_DAS)
    expected = resolve_code(HARD_TABLE[(total, up)],
                            can_double=can_double, can_split=False, das=True)
    assert adv.action == expected
    assert adv.raw_code == HARD_TABLE[(total, up)]


@pytest.mark.parametrize('key,up', sorted(SOFT_TABLE))
def test_every_soft_cell_round_trips(key, up):
    partner = key.split(',')[1]
    adv = basic_action(('A', partner), up, S17_DAS)
    expected = resolve_code(SOFT_TABLE[(key, up)],
                            can_double=True, can_split=False, das=True)
    assert adv.action == expected
    assert adv.raw_code == SOFT_TABLE[(key, up)]


@pytest.mark.parametrize('key,up', sorted(PAIR_TABLE))
def test_every_pair_cell_round_trips(key, up):
    rank = key.split(',')[0]
    adv = basic_action((rank, rank), up, S17_DAS)
    expected = resolve_code(PAIR_TABLE[(key, up)],
                            can_double=True, can_split=True, das=True)
    assert adv.action == expected
    assert adv.raw_code == PAIR_TABLE[(key, up)]
    assert adv.source == 'table'


def test_resolve_code_by_hand():
    assert resolve_code('H', can_double=True, can_split=True, das=True) == HIT
    assert resolve_code('S', can_double=True, can_split=True, das=True) == STAND
    assert resolve_code('D', can_double=True, can_split=False, das=True) == DOUBLE
    assert resolve_code('D', can_double=False, can_split=False, das=True) == HIT
    assert resolve_code('Ds', can_double=True, can_split=False, das=True) == DOUBLE
    assert resolve_code('Ds', can_double=False, can_split=False, das=True) == STAND
    assert resolve_code('P', can_double=True, can_split=True, das=True) == SPLIT
    # None means "the pair rule declined, go read the totals chart"
    assert resolve_code('P', can_double=True, can_split=False, das=True) is None
    assert resolve_code('Ph', can_double=True, can_split=True, das=True) == SPLIT
    assert resolve_code('Ph', can_double=True, can_split=True, das=False) is None
    assert resolve_code('Ph', can_double=True, can_split=False, das=True) is None
    with pytest.raises(ValueError):
        resolve_code('X', can_double=True, can_split=True, das=True)


# --- double not allowed ----------------------------------------------------

def test_double_falls_back_to_hit_after_a_hit():
    # hard 9 vs 3 is a D cell, but this 9 is three cards, so the button is gone
    adv = basic_action(('2', '3', '4'), '3', S17_DAS)
    assert adv.action == HIT
    assert adv.action_word == 'HIT'
    assert adv.source == 'fallback'
    assert adv.fallback_of == 'D'


def test_double_falls_back_when_the_ui_says_no():
    adv = basic_action(('9', '2'), '6', S17_DAS, can_double=False)
    assert (adv.action, adv.source, adv.fallback_of) == (HIT, 'fallback', 'D')


def test_ds_falls_back_to_stand_not_hit():
    # A,7 vs 4 is Ds: if you cannot double you stand on the 18, you do not hit
    adv = basic_action(('A', '7'), '4', S17_DAS, can_double=False)
    assert (adv.action, adv.source, adv.fallback_of) == (STAND, 'fallback', 'Ds')


def test_no_double_after_split_when_das_is_off():
    adv = basic_action(('9', '2'), '5', NO_DAS, is_split_hand=True)
    assert (adv.action, adv.fallback_of) == (HIT, 'D')
    # ... but the same hand doubles on a split hand when DAS is on
    assert basic_action(('9', '2'), '5', S17_DAS, is_split_hand=True).action == DOUBLE


def test_can_double_true_cannot_conjure_a_double_after_a_hit():
    # the UI can only ever be more restrictive than the chart, never less
    adv = basic_action(('2', '3', '4'), '3', S17_DAS, can_double=True)
    assert adv.action == HIT


# --- split not allowed -----------------------------------------------------

def test_eights_that_cannot_be_split_are_a_hard_16():
    adv = basic_action(('8', '8'), 'T', S17_DAS, hand_count=4)   # already 4 hands
    assert adv.action == HIT                 # hard 16 vs 10, two cards
    assert adv.source == 'fallback'
    assert adv.fallback_of == 'P'
    assert adv.raw_code == 'H'


def test_split_declined_by_the_ui():
    adv = basic_action(('8', '8'), '6', S17_DAS, can_split=False)
    assert adv.action == STAND               # hard 16 vs 6
    assert (adv.source, adv.fallback_of) == ('fallback', 'P')


def test_threes_that_cannot_be_split_are_a_hard_six():
    adv = basic_action(('3', '3'), '4', S17_DAS, can_split=False)
    assert (adv.action, adv.fallback_of) == (HIT, 'P')


def test_hand_count_gate():
    assert basic_action(('8', '8'), '9', S17_DAS, hand_count=3).action == SPLIT
    assert basic_action(('8', '8'), '9', S17_DAS, hand_count=4).action == HIT


# --- DAS off flips the Ph cells -------------------------------------------

PH_CELLS = [('6,6', '2'), ('4,4', '5'), ('4,4', '6'),
            ('3,3', '2'), ('3,3', '3'), ('2,2', '2'), ('2,2', '3')]


def test_ph_cells_are_exactly_the_ones_the_handoff_lists():
    found = sorted(k for k, code in PAIR_TABLE.items() if code == 'Ph')
    assert found == sorted(PH_CELLS)


@pytest.mark.parametrize('key,up', PH_CELLS)
def test_ph_splits_with_das_and_falls_through_without(key, up):
    rank = key.split(',')[0]
    assert basic_action((rank, rank), up, S17_DAS).action == SPLIT

    adv = basic_action((rank, rank), up, NO_DAS)
    assert adv.action != SPLIT
    assert adv.source == 'fallback'
    assert adv.fallback_of == 'Ph'
    # the fall-through answer is the hard total for that pair
    total = 2 * (10 if rank == 'T' else int(rank))
    expected = resolve_code(HARD_TABLE[(max(total, 5), up)],
                            can_double=True, can_split=False, das=False)
    assert adv.action == expected


def test_the_corrected_4_4_row():
    """4,4 vs 4 hits.  The spec row that said Ph was a transcription slip.

    Two independent exact solvers give, for 6 decks / S17 / DAS / peek:
        4,4 vs 4   split +0.00870   hit +0.04803   -> hit better by 0.03932
        4,4 vs 5   split +0.11085   hit +0.08362   -> split better by 0.02722
        4,4 vs 6   split +0.16681   hit +0.12440   -> split better by 0.04241
    The owner ruled the corrected pair row to be H H H Ph Ph H H H H H with a
    DAS note of "4,4 vs 5 and 6".  This test pins the corrected row so that
    reverting it is a deliberate act with a failing test attached.  Note that
    the handoff markdown had not been edited to match when this was written;
    see SPEC CORRECTION in bj/strategy.py.
    """
    assert PAIR_TABLE[('4,4', '4')] == 'H'
    assert basic_action(('4', '4'), '4', S17_DAS).action == HIT
    # vs 4 the fall-through answer is the hard-8 row, which hits
    assert basic_action(('4', '4'), '4', S17_DAS).raw_code == 'H'
    # the cells that did not change
    assert PAIR_TABLE[('4,4', '3')] == 'H'
    assert PAIR_TABLE[('4,4', '5')] == 'Ph'
    assert PAIR_TABLE[('4,4', '6')] == 'Ph'
    assert basic_action(('4', '4'), '5', S17_DAS).action == SPLIT
    assert basic_action(('4', '4'), '6', S17_DAS).action == SPLIT


def test_the_full_corrected_4_4_row_reads_as_the_spec_prints_it():
    printed = 'H H H Ph Ph H H H H H'.split()
    assert [PAIR_TABLE[('4,4', up)] for up in DEALER_UPS] == printed


def test_p_cells_are_unaffected_by_das():
    # 3,3 vs 4 is a plain P: it splits with or without DAS
    assert basic_action(('3', '3'), '4', NO_DAS).action == SPLIT
    assert basic_action(('8', '8'), 'A', NO_DAS).action == SPLIT


# --- soft hands after multiple hits ---------------------------------------

def test_multi_card_soft_uses_the_soft_total():
    # A,2,3 is soft 16, which is the A,5 row: D vs 5, but three cards cannot
    # double, so it hits
    adv = basic_action(('A', '2', '3'), '5', S17_DAS)
    assert adv.raw_code == 'D'
    assert (adv.action, adv.source, adv.fallback_of) == (HIT, 'fallback', 'D')
    # same soft 16 against a 9 is a plain hit off the chart
    assert basic_action(('A', '2', '3'), '9', S17_DAS).source == 'table'
    assert basic_action(('A', '2', '3'), '9', S17_DAS).action == HIT


def test_soft_18_built_from_three_cards():
    adv = basic_action(('A', '4', '3'), '7', S17_DAS)
    assert adv.action == STAND
    assert adv.raw_code == 'S'


def test_soft_hand_that_hardens_uses_the_hard_chart():
    # A,9,7 is 17 hard once the ace is forced to 1
    adv = basic_action(('A', '9', '7'), 'T', S17_DAS)
    assert hand_total(('A', '9', '7')) == (17, False)
    assert adv.action == STAND


def test_soft_21_is_not_looked_up_as_an_11():
    # the trap: hard_total(A,T) is 11, and 11 doubles almost everywhere
    assert basic_action(('A', 'T'), '6', S17_DAS).action == STAND
    assert basic_action(('A', '6', '4'), '6', S17_DAS).action == STAND
    assert 'lackjack' in basic_action(('A', 'T'), '6', S17_DAS).reason


def test_soft_12_that_cannot_be_split_hits():
    # A,A with no splits left is soft 12: it cannot bust, so it always hits
    for up in DEALER_UPS:
        adv = basic_action(('A', 'A'), up, S17_DAS, hand_count=4)
        assert adv.action == HIT, f'A,A vs {up}'
        # the chart is clamped to its lowest printed row for this hand; the
        # reason must still name the real total, not the clamp
        assert 'soft 12' in adv.reason.lower()
        assert ' 5 ' not in adv.reason


def test_hard_four_that_cannot_be_split_hits():
    adv = basic_action(('2', '2'), '6', S17_DAS, hand_count=4)
    assert adv.action == HIT
    assert 'hard 4' in adv.reason.lower()


# --- the 16 vs 10 composition exception ------------------------------------

def test_two_card_16_vs_ten_still_hits():
    adv = basic_action(('T', '6'), 'T', S17_DAS)
    assert adv.action == HIT
    assert adv.source == 'table'


def test_three_card_16_vs_ten_stands():
    adv = basic_action(('9', '5', '2'), 'T', S17_DAS)
    assert adv.action == STAND
    assert adv.source == 'composition'
    assert adv.raw_code == 'S'


def test_composition_exception_is_ten_only():
    assert basic_action(('9', '5', '2'), '9', S17_DAS).action == HIT
    assert basic_action(('9', '5', '2'), 'A', S17_DAS).action == HIT


def test_composition_exception_does_not_touch_other_totals():
    assert basic_action(('T', '3', '2'), 'T', S17_DAS).action == HIT     # 15 still hits
    assert basic_action(('9', '4', '2'), 'T', S17_DAS).action == HIT     # 15 still hits
    assert basic_action(('T', '4', '3'), 'T', S17_DAS).action == STAND   # 17, plain chart
    assert basic_action(('T', '4', '3'), 'T', S17_DAS).source == 'table'


def test_sharper_variant_needs_a_four_or_five():
    no_45 = ('T', '3', '3')          # 16, three cards, no 4 and no 5
    assert basic_action(no_45, 'T', S17_DAS).action == STAND             # default rule
    sharp = basic_action(no_45, 'T', S17_DAS, comp16_requires_45=True)
    assert sharp.action == HIT
    assert sharp.source == 'table'
    with_5 = ('9', '5', '2')
    assert basic_action(with_5, 'T', S17_DAS, comp16_requires_45=True).action == STAND


def test_soft_16_is_not_a_composition_16():
    # A,5 is soft 16 and belongs to the soft chart, exception or not
    assert basic_action(('A', '2', '3'), 'T', S17_DAS).action == HIT


# --- the soft 18 vs ace composition exception ------------------------------
# Found by this project's exact solver, not copied from a chart.  All 13
# soft-18 compositions from 2 to 6 cards were enumerated against an ace.  The
# rule is: STAND on 4+ cards when every non-ace card is a 2 or a 3, else hit.
#
# The three HIT rows below are the whole point of this block.  An
# implementation that takes the naive "4+ cards" shortcut passes all six STAND
# cases and fails all three of these; the shortcut is wrong by 0.00799 in EV.

SOFT18_ACE_STAND = [
    (('A', 'A', '3', '3'), 0.00298),
    (('A', '2', '2', '3'), 0.00280),
    (('A', 'A', 'A', '2', '3'), 0.00214),
    (('A', 'A', '2', '2', '2'), 0.00197),
    (('A', 'A', 'A', 'A', 'A', '3'), 0.00147),
    (('A', 'A', 'A', 'A', '2', '2'), 0.00131),
]

SOFT18_ACE_HIT = [
    ('A', 'A', '2', '4'),        # 4 cards, but a 4 is in there
    ('A', 'A', 'A', '5'),        # 4 cards, but a 5 is in there
    ('A', 'A', 'A', 'A', '4'),   # 5 cards, but a 4 is in there
]


@pytest.mark.parametrize('cards,gain', SOFT18_ACE_STAND,
                         ids=['+'.join(c) for c, _ in SOFT18_ACE_STAND])
def test_soft_18_vs_ace_exception_stands(cards, gain):
    assert hand_total(cards) == (18, True), cards
    adv = basic_action(cards, 'A', S17_DAS)
    assert adv.action == STAND
    assert adv.source == 'composition'
    assert adv.raw_code == 'S'
    assert adv.reason == '4+ cards, all small, the improving cards are already in hand.'
    assert gain > 0        # the enumerated EV gained by standing, for the record


@pytest.mark.parametrize('cards', SOFT18_ACE_HIT, ids=['+'.join(c) for c in SOFT18_ACE_HIT])
def test_soft_18_vs_ace_naive_four_card_rule_is_rejected(cards):
    """These are the discriminator.  "4+ cards" alone stands here and is wrong."""
    assert hand_total(cards) == (18, True), cards
    adv = basic_action(cards, 'A', S17_DAS)
    assert adv.action == HIT
    assert adv.source == 'table'
    assert adv.raw_code == 'H'


def test_soft_18_vs_ace_exception_needs_the_ace_upcard():
    for up in DEALER_UPS:
        if up == 'A':
            continue
        adv = basic_action(('A', 'A', '3', '3'), up, S17_DAS)
        assert adv.source != 'composition', up


def test_soft_18_vs_ace_exception_needs_four_cards():
    # A,7 vs A is the printed cell: hit, by 0.0049 (handoff appendix section 2)
    assert basic_action(('A', '7'), 'A', S17_DAS).action == HIT
    assert basic_action(('A', '7'), 'A', S17_DAS).source == 'table'
    # no 3-card soft 18 can be built from aces, 2s and 3s alone, so there is
    # nothing for the 4-card guard to exclude at n=3 - but keep it pinned, so a
    # later edit that loosens the card count fails here rather than in the wild
    assert basic_action(('A', '3', '4'), 'A', S17_DAS).action == HIT
    assert basic_action(('A', '2', '5'), 'A', S17_DAS).action == HIT


def test_soft_18_vs_ace_exception_does_not_leak_to_other_soft_totals():
    # soft 17 and soft 19 out of small cards are untouched by the exception
    assert basic_action(('A', 'A', '2', '3'), 'A', S17_DAS).action == HIT     # soft 17
    assert basic_action(('A', 'A', '3', '3', 'A'), 'A', S17_DAS).action == STAND  # soft 19
    assert basic_action(('A', 'A', '3', '3', 'A'), 'A', S17_DAS).source == 'table'


def test_soft_18_vs_ace_exception_survives_the_split_hand_path():
    # a split 3 that grew into A+3+3+A is still the exception; the split-ace
    # short circuit only fires on two cards
    adv = basic_action(('3', '3', 'A', 'A'), 'A', S17_DAS,
                       is_split_hand=True, hand_count=2)
    assert hand_total(('3', '3', 'A', 'A')) == (18, True)
    assert adv.action == STAND
    assert adv.source == 'composition'


# --- tens, insurance, and the other honesty rules --------------------------

@pytest.mark.parametrize('up', DEALER_UPS)
def test_never_split_tens(up):
    adv = basic_action(('T', 'T'), up, S17_DAS)
    assert adv.action == STAND
    assert adv.action != SPLIT
    assert 'never split tens' in adv.reason.lower()


def test_never_split_tens_even_when_the_app_offers_it():
    # the app offers SPLIT on Q,J; core collapses both to 'T'
    adv = basic_action('QJ', '6', S17_DAS, can_split=True)
    assert adv.action == STAND


def test_never_split_fives():
    assert basic_action(('5', '5'), '6', S17_DAS).action == DOUBLE
    assert basic_action(('5', '5'), 'T', S17_DAS).action == HIT
    assert basic_action(('5', '5'), 'A', S17_DAS).action == HIT
    assert 'never split fives' in basic_action(('5', '5'), '6', S17_DAS).reason.lower()


def test_insurance_is_always_declined():
    take, reason = take_insurance()
    assert take is False
    assert '30.87' in reason        # P(dealer blackjack) with an ace up, 6 decks
    assert '33.3' in reason         # break-even for a 2:1 bet
    assert '7.40' in reason         # house edge on the side bet


def test_insurance_ignores_every_argument_thrown_at_it():
    take, _ = take_insurance(player_cards=('T', 'T'), dealer_up='A',
                             running_count=99, true_count=12)
    assert take is False


def test_the_dealer_average_claim_is_only_made_where_it_is_true():
    """Hard 17 and 18 do NOT beat the dealer's 18.84 average made total.

    The reason line used to say they did, on every upcard.  The action was
    right and has not changed; the justification was false and has.  The soft
    branch already guarded this correctly at 19, which is the guard the hard
    branch now copies.
    """
    claim = 'beats the dealer average'
    for up in DEALER_UPS:
        for total, cards in HARD_HANDS.items():
            adv = basic_action(cards, up, S17_DAS)
            if claim in adv.reason:
                assert total > 18.84, f'hard {total} vs {up}: {adv.reason}'
        for partner in ('2', '3', '4', '5', '6', '7', '8', '9'):
            adv = basic_action(('A', partner), up, S17_DAS)
            if 'better than the dealer average' in adv.reason:
                assert 11 + int(partner) > 18.84, f'soft vs {up}: {adv.reason}'

    # hard 17 and 18 still stand, and now say something true about why
    for total, cards in ((17, HARD_HANDS[17]), (18, HARD_HANDS[18])):
        adv = basic_action(cards, 'T', S17_DAS)
        assert adv.action == STAND
        assert claim not in adv.reason
        assert 'short of the dealer average' in adv.reason
        assert f'over a {21 - total} busts it' in adv.reason
    # hard 19 does beat it, and still says so
    assert claim in basic_action(HARD_HANDS[19], 'T', S17_DAS).reason


def test_no_advice_is_ever_an_insurance_or_progression_recommendation():
    for up in DEALER_UPS:
        for hand in (('T', 'T'), ('A', 'A'), ('9', '9'), ('T', '6')):
            adv = basic_action(hand, up, S17_DAS)
            assert adv.action in (HIT, STAND, DOUBLE, SPLIT)
            assert 'insurance' not in adv.reason.lower()


# --- the S17-sensitive cells -----------------------------------------------

def test_s17_sensitive_cells():
    assert basic_action(('7', '4'), 'A', S17_DAS).action == HIT      # 11 vs A hits
    assert basic_action(('A', '7'), '2', S17_DAS).action == STAND    # soft 18 vs 2
    assert basic_action(('A', '8'), '6', S17_DAS).action == STAND    # soft 19 vs 6


def test_h17_overlay_flips_exactly_those_three_cells():
    assert basic_action(('7', '4'), 'A', H17).action == DOUBLE
    assert basic_action(('A', '7'), '2', H17).action == DOUBLE
    assert basic_action(('A', '8'), '6', H17).action == DOUBLE
    # and the Ds cells still stand when the double is unavailable
    assert basic_action(('A', '8'), '6', H17, can_double=False).action == STAND
    assert basic_action(('7', '4'), 'A', H17, can_double=False).action == HIT


def test_h17_overlay_changes_nothing_else():
    changed = []
    for (key, up) in HARD_TABLE:
        if basic_action(HARD_HANDS[key], up, S17_DAS).action != \
                basic_action(HARD_HANDS[key], up, H17).action:
            changed.append((key, up))
    for key in ('A,2', 'A,3', 'A,4', 'A,5', 'A,6', 'A,7', 'A,8', 'A,9'):
        partner = key.split(',')[1]
        for up in DEALER_UPS:
            if basic_action(('A', partner), up, S17_DAS).action != \
                    basic_action(('A', partner), up, H17).action:
                changed.append((key, up))
    assert sorted(changed, key=str) == sorted(H17_DIFFERENCES, key=str)


# --- split hands -----------------------------------------------------------

def test_split_aces_get_one_card():
    adv = basic_action(('A', '7'), '9', S17_DAS, is_split_hand=True)
    assert adv.action == STAND
    assert adv.source == 'split-aces'
    assert 'one card' in adv.reason


def test_split_aces_are_playable_when_the_rule_allows_hitting():
    rules = Rules(hit_split_aces=True)
    adv = basic_action(('A', '7'), '9', rules, is_split_hand=True)
    assert adv.action == HIT            # soft 18 vs 9 is a hit
    assert adv.source == 'table'


def test_a_split_eight_that_draws_an_ace_is_not_a_split_ace():
    # dealt order matters: the split card comes first
    adv = basic_action(('8', 'A'), '6', S17_DAS, is_split_hand=True)
    assert adv.source != 'split-aces'
    assert adv.action == STAND          # soft 19


def test_resplit_aces_follows_the_rule_flag():
    assert basic_action(('A', 'A'), '6', S17_DAS, is_split_hand=True).source == 'split-aces'
    resplit = Rules(resplit_aces=True)
    assert basic_action(('A', 'A'), '6', resplit, is_split_hand=True).action == SPLIT


def test_first_hand_aces_always_split():
    for up in DEALER_UPS:
        assert basic_action(('A', 'A'), up, S17_DAS).action == SPLIT


# --- input handling --------------------------------------------------------

def test_input_formats_agree():
    want = basic_action(('A', '7'), 'T', S17_DAS)
    for spelling in ('A,7', 'A7', ['a', 7], ('A', '7')):
        assert basic_action(spelling, 'K', S17_DAS).action == want.action


def test_busted_and_short_hands_are_errors_not_advice():
    with pytest.raises(ValueError):
        basic_action(('T', '9', '5'), '6', S17_DAS)
    with pytest.raises(ValueError):
        basic_action(('T',), '6', S17_DAS)


def test_action_word_leads_and_reason_is_one_line():
    """The owner reads this on a phone mid-hand. One word, then one line."""
    hands = list(HARD_HANDS.values())
    hands += [('A', str(n)) for n in range(2, 10)]                  # soft rows
    hands += [(r, r) for r in ('A', 'T', '9', '8', '7', '6', '5', '4', '3', '2')]
    hands += [('9', '5', '2'), ('T', '3', '3'), ('A', '2', '3')]    # exceptions
    hands += [c for c, _ in SOFT18_ACE_STAND] + SOFT18_ACE_HIT      # soft 18 vs A
    for up in DEALER_UPS:
        for cards in hands:
            for kw in ({}, {'can_double': False}, {'can_split': False},
                       {'is_split_hand': True, 'hand_count': 2}):
                adv = basic_action(cards, up, S17_DAS, **kw)
                assert adv.action_word in ('HIT', 'STAND', 'DOUBLE', 'SPLIT')
                assert adv.action_word == ACTION_NAMES[adv.action]
                assert '\n' not in adv.reason
                assert 0 < len(adv.reason) <= 110, adv.reason
                assert str(adv).startswith(adv.action_word)
                assert adv.source in ('table', 'composition', 'fallback', 'split-aces')


# --- the 37-hand log -------------------------------------------------------
# Section 5 of the handoff.  Every decision the owner made at the table, in
# order.  Hand 1 resolved on a dealer natural before any action, so it has no
# decision to check.  kwargs mark the hands that came out of a split.

LOG = [
    ('2  6,4 vs T',        ('6', '4'), 'T', {}, 'HIT'),
    ('2  6,4,T vs T',      ('6', '4', 'T'), 'T', {}, 'STAND'),
    ('3  7,A vs T',        ('7', 'A'), 'T', {}, 'HIT'),
    ('3  7,A,A vs T',      ('7', 'A', 'A'), 'T', {}, 'STAND'),
    ('4  Q,3 vs 3',        ('T', '3'), '3', {}, 'STAND'),
    ('5  8,3 vs 7',        ('8', '3'), '7', {}, 'DOUBLE'),
    ('6  6,A vs 3',        ('6', 'A'), '3', {}, 'DOUBLE'),
    ('7  10,5 vs 8',       ('T', '5'), '8', {}, 'HIT'),
    ('7  10,5,A vs 8',     ('T', '5', 'A'), '8', {}, 'HIT'),
    ('8  3,3 vs 4',        ('3', '3'), '4', {}, 'SPLIT'),
    ('8  h1 3,A,T vs 4',   ('3', 'A', 'T'), '4', {'is_split_hand': True, 'hand_count': 2}, 'STAND'),
    ('8  h2 3,9 vs 4',     ('3', '9'), '4', {'is_split_hand': True, 'hand_count': 2}, 'STAND'),
    ('9  10,J vs A',       ('T', 'T'), 'A', {}, 'STAND'),
    ('10 10,4 vs 5',       ('T', '4'), '5', {}, 'STAND'),
    ('11 Q,J vs 7',        ('T', 'T'), '7', {}, 'STAND'),
    ('12 7,3 vs T',        ('7', '3'), 'T', {}, 'HIT'),
    ('12 7,3,4 vs T',      ('7', '3', '4'), 'T', {}, 'HIT'),
    ('13 9,5 vs T',        ('9', '5'), 'T', {}, 'HIT'),
    ('13 9,5,2 vs T',      ('9', '5', '2'), 'T', {}, 'STAND'),   # composition
    ('14 2,K vs 4',        ('2', 'T'), '4', {}, 'STAND'),
    ('15 7,3 vs 9',        ('7', '3'), '9', {}, 'DOUBLE'),
    ('16 8,9 vs 5',        ('8', '9'), '5', {}, 'STAND'),
    ('17 4,2 vs 2',        ('4', '2'), '2', {}, 'HIT'),
    ('17 4,2,J vs 2',      ('4', '2', 'T'), '2', {}, 'STAND'),
    ('18 8,K vs K',        ('8', 'T'), 'T', {}, 'STAND'),
    ('19 8,2 vs J',        ('8', '2'), 'T', {}, 'HIT'),
    ('19 8,2,J vs J',      ('8', '2', 'T'), 'T', {}, 'STAND'),
    ('20 7,2 vs 2',        ('7', '2'), '2', {}, 'HIT'),
    ('21 5,5 vs 5',        ('5', '5'), '5', {}, 'DOUBLE'),       # never split fives
    ('22 3,6 vs J',        ('3', '6'), 'T', {}, 'HIT'),
    ('22 3,6,4 vs J',      ('3', '6', '4'), 'T', {}, 'HIT'),
    ('22 3,6,4,3 vs J',    ('3', '6', '4', '3'), 'T', {}, 'STAND'),  # composition
    ('23 2,K vs 2',        ('2', 'T'), '2', {}, 'HIT'),
    ('24 4,4 vs 5',        ('4', '4'), '5', {}, 'SPLIT'),
    ('24 h1 4,K vs 5',     ('4', 'T'), '5', {'is_split_hand': True, 'hand_count': 2}, 'STAND'),
    ('24 h2 4,Q vs 5',     ('4', 'T'), '5', {'is_split_hand': True, 'hand_count': 2}, 'STAND'),
    ('25 6,2 vs 4',        ('6', '2'), '4', {}, 'HIT'),
    ('25 6,2,K vs 4',      ('6', '2', 'T'), '4', {}, 'STAND'),
    ('26 5,Q vs 4',        ('5', 'T'), '4', {}, 'STAND'),
    ('27 9,2 vs 7',        ('9', '2'), '7', {}, 'DOUBLE'),
    ('28 10,J vs 10',      ('T', 'T'), 'T', {}, 'STAND'),
    ('29 Q,Q vs 8',        ('T', 'T'), '8', {}, 'STAND'),
    ('30 4,9 vs 9',        ('4', '9'), '9', {}, 'HIT'),
    ('31 8,6 vs 2',        ('8', '6'), '2', {}, 'STAND'),
    ('32 K,10 vs 7',       ('T', 'T'), '7', {}, 'STAND'),
    ('33 Q,10 vs Q',       ('T', 'T'), 'T', {}, 'STAND'),
    ('34 10,7 vs K',       ('T', '7'), 'T', {}, 'STAND'),
    ('35 Q,K vs 7',        ('T', 'T'), '7', {}, 'STAND'),
    ('36 6,Q vs K',        ('6', 'T'), 'T', {}, 'HIT'),
    ('37 5,J vs 8',        ('5', 'T'), '8', {}, 'HIT'),
]


@pytest.mark.parametrize('label,cards,up,kw,expected', LOG,
                         ids=[row[0] for row in LOG])
def test_reproduces_the_hand_log(label, cards, up, kw, expected):
    assert basic_action(cards, up, S17_DAS, **kw).action_word == expected


def test_the_log_agrees_under_both_composition_rules():
    # Both multi-card 16s in the log contain a 4 or a 5, so the sharper variant
    # of the exception reproduces the log too.  The log cannot tell the two
    # rules apart; that is why the loose rule is the default rather than the
    # tested-better one.
    for label, cards, up, kw, expected in LOG:
        got = basic_action(cards, up, S17_DAS, comp16_requires_45=True, **kw)
        assert got.action_word == expected, label
