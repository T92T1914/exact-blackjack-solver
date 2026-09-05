"""Total-dependent basic strategy for the the example table blackjack table.

This is the module the owner actually reads on his phone: one word first
(HIT / STAND / DOUBLE / SPLIT), one line of reason second.

DESIGN DECISION: the three tables below store the *raw* strategy codes from the
handoff (H, S, D, Ds, P, Ph) rather than finished actions.  The alternative was
to bake "double else hit" down to a single action at write time, which would
have needed one table per rule combination (DAS on/off, double button lit or
not, two-card or five-card hand).  Keeping the raw code and resolving it at
lookup time means the printed tables can be diffed line by line against section
4 of the handoff, and flipping ``rules.das`` or passing ``can_double=False``
changes the answer without anyone editing a table.

Table provenance: section 4 of the table's rules panel, which is the
Wizard of Odds 6-deck / S17 / DAS / no-surrender / dealer-peeks chart.  The
codes are transcribed exactly as printed, with two departures: the pair row
printed "10,10" is keyed 'T,T' here because bj.core collapses every ten-value
rank to 'T', and the 4,4 row follows the owner's corrected version rather than
the printed one (see SPEC CORRECTION below, which also records that the
markdown itself has not been edited yet).

APPROXIMATIONS
    1.  These are TOTAL-dependent tables.  Two composition-dependent
        exceptions are implemented on top of them:
          * hard 16 vs a ten-value upcard with three or more cards (worth
            ~0.4 cents per dollar, handoff appendix section 2), and
          * soft 18 vs an ace with four or more cards, all of them small
            (note 8 below).
        The other published exception, 12 vs 4 hitting only when composed
        10-2, is deliberately NOT implemented: its margin is 0.00075 units,
        which is smaller than the chance of the owner mis-tapping a card on a
        phone.  Saying so out loud is cheaper than pretending to that
        precision.
    2.  NEITHER FORM OF THE 16 VS 10 EXCEPTION IS EXACT, and the docstring
        used to imply the sharper one was.  Enumerating all 167 hard-16-vs-ten
        compositions from 2 to 8 cards with the exact solver (164 of them have
        three or more cards) gives:
            exact play                    STAND on 143 of the 164
            "any 3+ card 16" (default)    stands wrongly on 21, misses none;
                                          summed EV cost 0.0503
            "3+ cards with a 4 or 5"      stands wrongly on 1 but HITS wrongly
                                          on 47; summed EV cost 0.1356
        So the sharper published form is not sharper over the full set: most
        multi-card 16s vs a ten want to stand whether or not a 4 or 5 is in
        there.  Those are composition counts, not frequencies - an eight-card
        16 never happens - so this is a statement about the rule being
        inexact, not about money; the money at stake either way is a fraction
        of a cent per hand.  Default is the loose "three or more cards" rule
        because that is the rule the owner already played and the 37-hand log
        has to reproduce; ``comp16_requires_45=True`` selects the other form.
        It lives on the function and not on Rules only because bj/core.py is
        frozen for this build.  Both forms agree on the two multi-card 16s in
        the log (9,5,2 and 3,6,4,3 both contain a 4 or a 5), so the log cannot
        tell them apart.
    3.  Split aces are detected by card ORDER: on a split hand the split card
        is dealt first, so ('A', '7') with is_split_hand=True is read as a
        split ace, while ('8', 'A') is read as a split eight that drew an ace.
        The alternative was an extra ``split_card`` argument; rejected because
        every extra field on a phone form is another mis-tap.

        THE OLD JUSTIFICATION FOR THIS WAS WRONG.  It claimed the only hands
        that could be confused were the soft 18/19 from split eights, which
        stand either way.  Measured: of the nine non-ace ranks that can share
        a split hand with an ace, SIX flip the recommendation when the two
        cards are entered in the wrong order - 2, 3, 4, 5, 6 and 7.  Only 8, 9
        and T are safe.  Across the 57 (rank, upcard) cells that flip, reading
        a split 2-through-7 as a split ace costs between 0.005 and 0.61 units
        of the bet, mean 0.32.  The worst case is A,2 vs a weak upcard, where
        the engine says STAND on a hand that should double.  The convention is
        kept, because the split card genuinely is dealt first and a wrong
        ``split_card`` field would be just as wrong, but the exposure is this
        and not "they stand anyway".
    4.  ``rules.double_any_two`` is not consulted.  A "double on 9-11 only"
        table is a different chart, not a filter over this one, so honouring
        the flag here would produce a chart that exists nowhere.
    5.  The H17 overlay (three cells) is complete ONLY because this table has
        no surrender.  With surrender available, H17 also changes 15 vs A and
        17 vs A.  If surrender ever appears in the app, this overlay is wrong.
    6.  ``take_insurance`` computes P(dealer blackjack) from a full shoe minus
        the dealer's ace, ignoring the player's own cards.  That is the same
        convention as the published 30.87% figure.  A player holding two tens
        faces a slightly lower probability; it is never enough to matter,
        because insurance would need 33.3%.
    7.  No card counting, no index deviations, no bet advice.  Section 2 of the
        handoff concludes the shoe is almost certainly reshuffled every hand,
        which makes every index number in the appendix worthless here.
    8.  The soft-18-vs-ace exception (see ``_SOFT18_ACE_*`` below) was found by
        this project's own exact solver, not copied from a chart.  It is a
        CORRECTNESS item, not a money item: the qualifying hands are a 4+ card
        soft 18 built only from aces, 2s and 3s against an ace upcard, and the
        total effect on the house edge is on the order of 1e-7.  It is
        implemented because it is right, not because it wins anything.

SPEC CORRECTION: 4,4 vs 4 (resolved)
    This module used to carry a note flagging 4,4 vs 4 as an unresolved
    disagreement between the printed pair table and every recomputation of it.
    The owner has since corrected the spec, and the table below now matches the
    corrected row.  Recording why, so nobody re-opens it:

        4,4 vs 4     split +0.00870     hit +0.04803    -> HIT  by 0.03932
        4,4 vs 5     split +0.11085     hit +0.08362    -> SPLIT by 0.02722
        4,4 vs 6     split +0.16681     hit +0.12440    -> SPLIT by 0.04241

    Those figures come from two independent exact solvers that agree to the
    digit, and bj.ev reproduces them here.  Hitting 4,4 vs 4 is better by about
    0.04 units, roughly 60 times the margin of the closest real decision in the
    game, so this was never a borderline cell.  The handoff's own cheat sheet
    already said "4,4 split vs 5 to 6", and the published Wizard of Odds 4-8
    deck S17 DAS chart hits it too; the printed row was a transcription slip.

    The owner has ruled the corrected row to be

        4,4   H  H  H  Ph  Ph  H  H  H  H  H

    with the DAS note reading "4,4 vs 5 and 6", and the table below is that
    row.  The order matters: the source document was ruled on first and the
    code follows it.  Tuning a table until it matches a recomputation is how a
    spec and its code quietly stop being the same document.

    STILL OUTSTANDING at the time of writing: the handoff markdown in
    ~/Downloads has not been edited to match.  Every copy of it still prints
    "| 4,4 | H | H | Ph | Ph | Ph | H | H | H | H | H |" on line 100 and
    "4,4 vs 4, 5, 6" in the DAS-sensitive list on line 212, and none of them
    carries the errata section the ruling refers to.  Until those two lines are
    edited, this table does NOT diff clean against the printed spec, and the
    difference is this cell.  That is a documentation task, not a code one; it
    is recorded here rather than silently assumed done.

HONESTY
    There is no player edge in this game and this module never implies one.
    It never returns SPLIT on tens, never recommends insurance, and states the
    dealer bust percentage rather than a feeling about it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from .core import (
    ACTION_NAMES,
    STANDARD,
    DOUBLE,
    HIT,
    Rules,
    SPLIT,
    STAND,
    hand_total,
    hard_total,
    is_blackjack,
    is_pair,
    normalize,
    normalize_hand,
)

__all__ = [
    'HARD_TABLE', 'SOFT_TABLE', 'PAIR_TABLE', 'DEALER_UPS', 'RAW_CODES',
    'H17_DIFFERENCES', 'DEALER_BUST_PCT', 'Advice', 'basic_action',
    'take_insurance', 'resolve_code',
]

# --- raw codes -------------------------------------------------------------
# Exactly the vocabulary the handoff prints, no more.
CODE_HIT = 'H'
CODE_STAND = 'S'
CODE_DOUBLE = 'D'          # double, else hit
CODE_DOUBLE_STAND = 'Ds'   # double, else stand
CODE_SPLIT = 'P'
CODE_SPLIT_DAS = 'Ph'      # split only because DAS is allowed, else fall through

RAW_CODES = frozenset({CODE_HIT, CODE_STAND, CODE_DOUBLE,
                       CODE_DOUBLE_STAND, CODE_SPLIT, CODE_SPLIT_DAS})

#: source values on Advice
SOURCE_TABLE = 'table'
SOURCE_COMPOSITION = 'composition'
SOURCE_FALLBACK = 'fallback'
SOURCE_SPLIT_ACES = 'split-aces'

#: dealer upcard columns, left to right as printed in the handoff
DEALER_UPS: Tuple[str, ...] = ('2', '3', '4', '5', '6', '7', '8', '9', 'T', 'A')

#: dealer bust probability by upcard, 6 decks S17 after the peek.
#: Handoff section 4 ("Dealer bust probability by upcard"), which is the
#: Wizard of Odds "Dealer Odds, US Rules" bust column.  Used only to explain a
#: decision in words; no decision is derived from it.
DEALER_BUST_PCT: Dict[str, float] = {
    '2': 35.4, '3': 37.4, '4': 39.6, '5': 41.8, '6': 42.3,
    '7': 26.2, '8': 24.4, '9': 22.9, 'T': 23.0, 'A': 16.7,
}

#: average dealer total when the dealer does not bust (handoff appendix s5)
DEALER_AVG_MADE_TOTAL = 18.84

# --- the soft-18-vs-ace composition exception ------------------------------
# Found by this project's exact solver, not taken from any published chart.
# All 13 soft-18 compositions from 2 to 6 cards were enumerated against an ace
# upcard.  Six of them stand; the rest hit, as the printed table says.
#
#     A+A+3+3      +0.00298      A+2+2+3      +0.00280
#     A+A+A+2+3    +0.00214      A+A+2+2+2    +0.00197
#     A+A+A+A+A+3  +0.00147      A+A+A+A+2+2  +0.00131
#
# The tempting shortcut is "4+ cards".  It is WRONG on A+A+2+4, A+A+A+5 and
# A+A+A+A+4, which all still hit, and costs 0.00799 across those three.  The
# rule that is exact over all 13 is: four or more cards AND every non-ace card
# is a 2 or a 3.  Both halves are load-bearing, which is why the boundary was
# enumerated instead of generalised from the two hands a coarse sweep found.
#
# Mechanism, and the reason string in one sentence: every qualifying hand is
# built only from aces, 2s and 3s - exactly the cards that improve a soft 18
# without busting it.  Having already consumed them, the draw you are hoping
# for is the draw you are least likely to get.
#
# Magnitude: a 4+ card soft 18 made only of aces, 2s and 3s against an ace
# upcard is vanishingly rare.  Effect on the house edge is of order 1e-7.  This
# is a correctness item, not a money item.
_SOFT18_ACE_MIN_CARDS = 4
_SOFT18_ACE_SMALL_RANKS = frozenset({'A', '2', '3'})
_SOFT18_ACE_REASON = '4+ cards, all small, the improving cards are already in hand.'


def _soft18_vs_ace_stands(cards, total: int, soft: bool, up: str) -> bool:
    """True for the soft-18-vs-ace compositions that stand.  See above."""
    return (soft and total == 18 and up == 'A'
            and len(cards) >= _SOFT18_ACE_MIN_CARDS
            and all(c in _SOFT18_ACE_SMALL_RANKS for c in cards))


def _expand(rows) -> Dict[Tuple[object, str], str]:
    """Turn printed table rows into a {(player_key, dealer_up): code} dict.

    Rows are given as (player_keys, "ten codes separated by spaces") so the
    literal in the source keeps the shape of the printed chart and can be
    eyeballed against the markdown.  A printed row that covers several totals
    ("5 to 8", "17+") lists them all in player_keys.
    """
    table: Dict[Tuple[object, str], str] = {}
    for keys, cells in rows:
        codes = cells.split()
        if len(codes) != len(DEALER_UPS):
            raise ValueError(f'row {keys!r} has {len(codes)} cells, need 10')
        for code in codes:
            if code not in RAW_CODES:
                raise ValueError(f'row {keys!r} has unknown code {code!r}')
        for key in keys:
            for up, code in zip(DEALER_UPS, codes):
                table[(key, up)] = code
    return table


# --- the three tables ------------------------------------------------------
# Dealer upcard order across:      2  3  4  5  6  7  8  9  T  A

#: hard totals, keyed (int total, dealer up rank).  The printed rows "5 to 8"
#: and "17+" are expanded to one key per total so callers never have to know
#: which rows were collapsed on paper.
HARD_TABLE: Dict[Tuple[object, str], str] = _expand((
    ((5, 6, 7, 8),          'H  H  H  H  H  H  H  H  H  H'),   # printed "5 to 8"
    ((9,),                  'H  D  D  D  D  H  H  H  H  H'),
    ((10,),                 'D  D  D  D  D  D  D  D  H  H'),
    ((11,),                 'D  D  D  D  D  D  D  D  D  H'),
    ((12,),                 'H  H  S  S  S  H  H  H  H  H'),
    ((13,),                 'S  S  S  S  S  H  H  H  H  H'),
    ((14,),                 'S  S  S  S  S  H  H  H  H  H'),
    ((15,),                 'S  S  S  S  S  H  H  H  H  H'),
    ((16,),                 'S  S  S  S  S  H  H  H  H  H'),
    ((17, 18, 19, 20, 21),  'S  S  S  S  S  S  S  S  S  S'),   # printed "17+"
))

#: soft totals, keyed by the printed row label ('A,2' .. 'A,9').  A hand is
#: looked up by its soft TOTAL, so A,2,3 vs 5 (soft 16) uses the 'A,5' row.
SOFT_TABLE: Dict[Tuple[object, str], str] = _expand((
    (('A,2',), 'H   H   H   D   D   H  H  H  H  H'),
    (('A,3',), 'H   H   H   D   D   H  H  H  H  H'),
    (('A,4',), 'H   H   D   D   D   H  H  H  H  H'),
    (('A,5',), 'H   H   D   D   D   H  H  H  H  H'),
    (('A,6',), 'H   D   D   D   D   H  H  H  H  H'),
    (('A,7',), 'S   Ds  Ds  Ds  Ds  S  S  H  H  H'),
    (('A,8',), 'S   S   S   S   S   S  S  S  S  S'),
    (('A,9',), 'S   S   S   S   S   S  S  S  S  S'),
))

#: pairs (DAS allowed).  'T,T' is the row printed as "10,10"; bj.core collapses
#: 10/J/Q/K to 'T', and the app treats any two ten-values as a splittable pair.
PAIR_TABLE: Dict[Tuple[object, str], str] = _expand((
    (('A,A',), 'P   P   P   P   P   P  P  P  P  P'),
    (('T,T',), 'S   S   S   S   S   S  S  S  S  S'),
    (('9,9',), 'P   P   P   P   P   S  P  P  S  S'),
    (('8,8',), 'P   P   P   P   P   P  P  P  P  P'),
    (('7,7',), 'P   P   P   P   P   P  H  H  H  H'),
    (('6,6',), 'Ph  P   P   P   P   H  H  H  H  H'),
    (('5,5',), 'D   D   D   D   D   D  D  D  H  H'),
    # 4,4 vs 4 used to read Ph here, transcribed from a spec row that was a
    # slip.  The owner corrected the spec; this row is the corrected one.
    # Split +0.00870 vs hit +0.04803 against a dealer 4, so hitting is better
    # by 0.039 units.  vs 5 and vs 6 are unchanged and still split under DAS.
    # See "SPEC CORRECTION" in the module docstring.
    (('4,4',), 'H   H   H   Ph  Ph  H  H  H  H  H'),
    (('3,3',), 'Ph  Ph  P   P   P   P  H  H  H  H'),
    (('2,2',), 'Ph  Ph  P   P   P   P  H  H  H  H'),
))

#: The complete set of cells that change if the dealer hits soft 17.
#: Handoff section 4 ("S17 vs H17 sensitive cells") and appendix section 1.
#: Applied only when rules.s17 is False.  Keys are (player_key, dealer_up) and
#: cannot collide across tables because hard keys are ints and soft keys are
#: strings.  See APPROXIMATIONS note 5 for why this list is short.
H17_DIFFERENCES: Dict[Tuple[object, str], str] = {
    (11, 'A'): CODE_DOUBLE,          # S17 hits, H17 doubles
    ('A,7', '2'): CODE_DOUBLE_STAND,  # soft 18 vs 2
    ('A,8', '6'): CODE_DOUBLE_STAND,  # soft 19 vs 6
}


# --- advice ----------------------------------------------------------------

@dataclass(frozen=True)
class Advice:
    """One decision, ready to render.

    action        one of core.HIT / STAND / DOUBLE / SPLIT ('H','S','D','P')
    action_word   HIT / STAND / DOUBLE / SPLIT.  This is what the user reads
                  first; everything else is secondary.
    reason        one short plain-English line saying WHY
    source        'table'       straight out of one of the three charts
                  'composition' the multi-card 16 vs 10 exception
                  'fallback'    the chart's code was not available at this
                                table (no double button, no split left) and
                                was downgraded
                  'split-aces'  split aces get one card, there is no decision
    raw_code      the code the action came from.  For a composition exception
                  it is 'S', because the exception overrides the chart's 'H'.
    fallback_of   the code that had to be downgraded, or None
    """
    action: str
    action_word: str
    reason: str
    source: str
    raw_code: str
    fallback_of: Optional[str] = None

    def __str__(self) -> str:  # what the phone page prints
        return f'{self.action_word} - {self.reason}'


def resolve_code(code: str, *, can_double: bool, can_split: bool,
                 das: bool) -> Optional[str]:
    """Turn a raw table code into an action, given what this table allows.

    Returns None when the code is a split code that cannot be honoured (no
    split available, or a Ph cell in a game without DAS).  None means "the
    pair rule declined, go look the hand up in the hard or soft chart"; it is
    not an error.  Split is the one code whose fallback needs the whole hand,
    so it is the one code this function cannot finish on its own.
    """
    if code == CODE_HIT:
        return HIT
    if code == CODE_STAND:
        return STAND
    if code == CODE_DOUBLE:
        # "double else hit": the hand wanted more money on a good spot; if the
        # button is gone the hand still wants a card.
        return DOUBLE if can_double else HIT
    if code == CODE_DOUBLE_STAND:
        # "double else stand": soft 18 vs a weak upcard is already a made hand.
        return DOUBLE if can_double else STAND
    if code == CODE_SPLIT:
        return SPLIT if can_split else None
    if code == CODE_SPLIT_DAS:
        # Ph is only worth splitting because you may double the resulting
        # hands.  Without DAS the split loses its value and the hand is played
        # as a total instead.
        if not das:
            return None
        return SPLIT if can_split else None
    raise ValueError(f'unknown strategy code: {code!r}')


def _cell(table, key, up: str, rules: Rules) -> str:
    """Read one cell, applying the H17 overlay when the dealer hits soft 17."""
    code = table[(key, up)]
    if not rules.s17:
        code = H17_DIFFERENCES.get((key, up), code)
    return code


def _up_name(up: str) -> str:
    """'T' prints as 10.  The owner is looking at a Queen, not a rank code."""
    return '10' if up == 'T' else up


def _bust(up: str) -> str:
    return f'{DEALER_BUST_PCT[up]:.1f}%'


# --- reasons ---------------------------------------------------------------
# Each reason is one line and says WHY, not what.  They are deliberately
# written in table language ("the chart says") only where there is no shorter
# true explanation.

def _hard_reason(total: int, code: str, act: str, up: str) -> str:
    u, b = _up_name(up), _bust(up)
    if act == DOUBLE:
        if total == 11:
            return f'11 makes 21 more often than any other total - get more money out against {u}.'
        if total == 10:
            return f'10 beats {u} to a good total often enough to be worth two bets.'
        return f'9 against a weak {u} ({b} bust) is worth doubling; one card usually lands 19-ish.'
    if code in (CODE_DOUBLE, CODE_DOUBLE_STAND) and act in (HIT, STAND):
        return (f'The chart doubles {total} vs {u}, but the double is not available on this hand - '
                f'{"hit" if act == HIT else "stand"} instead.')
    if act == STAND:
        if total == 21:
            return 'You have 21. Nothing to decide.'
        if total == 20:
            return '20 loses only to a dealer 21 - stand.'
        if total >= 19:
            return f'Hard {total} already beats the dealer average of {DEALER_AVG_MADE_TOTAL}; drawing mostly busts.'
        if total >= 17:
            # 17 and 18 are BELOW the 18.84 average, so the old line here -
            # "already beats the dealer average" - was simply false.  The
            # action was right and stays; the justification is replaced with
            # the true one.  The soft branch already guards at 19 for the same
            # reason.  Bust threshold: hard 17 busts on 5+, hard 18 on 4+.
            # Kept short on purpose: 9,9 that cannot be split reaches this line
            # behind a 25-character "Cannot split this hand - " prefix, and the
            # whole reason still has to fit the phone's 110-character budget.
            return (f'Hard {total} is short of the dealer average {DEALER_AVG_MADE_TOTAL}, '
                    f'but any card over a {21 - total} busts it.')
        return f'Stiff {total}, but {u} busts {b} of the time - make the dealer take the risk.'
    # HIT
    if total <= 11:
        return f'{total} cannot bust - always take the card.'
    return f'Stiff {total} against {u}, who busts only {b} - standing just loses more slowly.'


def _soft_reason(total: int, code: str, act: str, up: str) -> str:
    u, b = _up_name(up), _bust(up)
    if act == DOUBLE:
        if total == 18:
            return f'Soft 18 rarely wins on its own; {u} busts {b}, so double for the money, not the total.'
        return f'Soft {total} cannot bust on one card and {u} busts {b} - double for value.'
    if code == CODE_DOUBLE and act == HIT:
        return f'Soft {total} wants to double vs {u} but the button is gone - hit; the ace protects you.'
    if code == CODE_DOUBLE_STAND and act == STAND:
        return f'Cannot double, so stand - never break a soft 18 against a weak {u}.'
    if act == STAND:
        if total >= 19:
            return f'Soft {total} is already better than the dealer average of {DEALER_AVG_MADE_TOTAL} - stand.'
        return f'Soft 18 is good enough against {u}; hitting turns 18 into 15 too often.'
    # HIT
    if total == 18:
        return f'Soft 18 loses to {u}\'s likely 19 or 20, and you cannot bust - hit.'
    return f'Soft {total} cannot bust on one card - hit.'


def _pair_reason(pkey: str, code: str, act: str, up: str) -> str:
    u, b = _up_name(up), _bust(up)
    if pkey == 'A,A':
        return 'Always split aces: two hands starting on 11 beat one soft 12.'
    if pkey == 'T,T':
        # Honesty rule: the app offers SPLIT on Q,J.  Never take it.
        return 'Never split tens - 20 loses only to a dealer 21, and splitting throws that away.'
    if pkey == '8,8':
        return 'Always split eights: 16 is the worst hand in the game, two 8s are not.'
    if pkey == '5,5':
        if act == DOUBLE:
            return f'Never split fives - a pair of fives is hard 10, and hard 10 doubles against {u}.'
        if code == CODE_DOUBLE:
            # The chart says double here; the button is gone.  Saying "hard 10 only
            # hits against {u}" would contradict this module's own cell.
            return (f'Never split fives - it is hard 10, which would double against {u}, '
                    f'but double is not available, so hit.')
        return f'Never split fives - play it as hard 10, and hard 10 only hits against {u}.'
    if pkey == '9,9':
        if act == SPLIT:
            return f'Split nines: two hands of 9 are worth more than one 18 against {u} ({b} bust).'
        if up == '7':
            return 'Stand on 18: against a 7 the dealer most often makes 17, so 18 is already a winner.'
        return f'Stand on 18 - splitting into {u} turns one mediocre hand into two bad ones.'
    if act == SPLIT:
        if code == CODE_SPLIT_DAS:
            return ('Split only because double-after-split is allowed here - '
                    'without DAS this hand would just hit.')
        return f'Split: two fresh hands against {u} ({b} bust) beat one bad total.'
    # H cells on 7,7 / 6,6 / 4,4 / 3,3 / 2,2
    total = 2 * (10 if pkey[0] == 'T' else int(pkey[0]))
    return f'Not worth splitting against {u} - play it as hard {total} and hit.'


# --- lookups ---------------------------------------------------------------

def _totals_advice(cards, up: str, rules: Rules, can_double: bool,
                   comp16_requires_45: bool, is_split_hand: bool = False) -> Advice:
    """Hard / soft chart lookup, including the 16 vs 10 composition exception."""
    total, soft = hand_total(cards)

    # --- soft chart: rows exist for soft 13 through soft 20 only
    if soft and 13 <= total <= 20:
        # Composition exception, checked before the chart because it overrides
        # the chart's H on soft 18 vs an ace.
        if _soft18_vs_ace_stands(cards, total, soft, up):
            return Advice(
                action=STAND,
                action_word=ACTION_NAMES[STAND],
                reason=_SOFT18_ACE_REASON,
                source=SOURCE_COMPOSITION,
                raw_code=CODE_STAND,
                fallback_of=None,
            )
        key = f'A,{total - 11}'
        code = _cell(SOFT_TABLE, key, up, rules)
        act = resolve_code(code, can_double=can_double, can_split=False, das=rules.das)
        downgraded = code in (CODE_DOUBLE, CODE_DOUBLE_STAND) and act != DOUBLE
        return Advice(
            action=act,
            action_word=ACTION_NAMES[act],
            reason=_soft_reason(total, code, act, up),
            source=SOURCE_FALLBACK if downgraded else SOURCE_TABLE,
            raw_code=code,
            fallback_of=code if downgraded else None,
        )

    # --- everything else uses the hard chart.
    # A soft hand with no row is either a made soft 21 (A,T or A,4,6) or soft
    # 12, which can only be A,A that could not be split.  Keying soft 21 by its
    # hard total would look up 11 and try to double a finished hand, so it is
    # handled explicitly; A,A falls through on its hard total of 2 and lands in
    # the all-hit "5 to 8" row, which is the right answer for a hand that
    # cannot bust.
    clamped = False
    if soft and total >= 21:
        key = 21
    else:
        ht = hard_total(cards)
        # Hard 4 (an unsplittable 2,2) and hard 2 (an unsplittable A,A) are
        # below the printed chart.  Every row below 9 is all-hit, so clamping
        # to the first printed row changes no answer - but it would put a
        # wrong total in the reason line, so the clamp is flagged.
        clamped = ht < 5
        key = 5 if clamped else ht

    # Composition exception, checked before the chart because it overrides it.
    if (not soft) and key == 16 and up == 'T' and len(cards) >= 3:
        has_45 = ('4' in cards) or ('5' in cards)
        if (not comp16_requires_45) or has_45:
            extra = ' with a 4 or 5' if has_45 else ''
            return Advice(
                action=STAND,
                action_word=ACTION_NAMES[STAND],
                reason=(f'Multi-card 16 vs 10{extra}: the low cards you need to draw are '
                        f'already in your hand - stand.'),
                source=SOURCE_COMPOSITION,
                raw_code=CODE_STAND,
                fallback_of=None,
            )

    code = _cell(HARD_TABLE, key, up, rules)
    act = resolve_code(code, can_double=can_double, can_split=False, das=rules.das)
    downgraded = code in (CODE_DOUBLE, CODE_DOUBLE_STAND) and act != DOUBLE
    if soft and key == 21 and is_blackjack(cards, is_split_hand):
        reason = 'Blackjack. It pays 3:2 and there is nothing to decide.'
    elif clamped:
        # do not print the clamped key: the hand is a soft 12 or a hard 4
        reason = (f'{"Soft 12" if soft else f"Hard {total}"} cannot bust - '
                  f'always take the card.')
    else:
        reason = _hard_reason(key, code, act, up)
    return Advice(
        action=act,
        action_word=ACTION_NAMES[act],
        reason=reason,
        source=SOURCE_FALLBACK if downgraded else SOURCE_TABLE,
        raw_code=code,
        fallback_of=code if downgraded else None,
    )


def basic_action(player_cards, dealer_up, rules: Rules = STANDARD, *,
                 can_double: Optional[bool] = None,
                 can_split: Optional[bool] = None,
                 is_split_hand: bool = False,
                 hand_count: int = 1,
                 comp16_requires_45: bool = False) -> Advice:
    """Recommend one action for one hand.

    player_cards   ranks in DEALT ORDER: 'A,7', ['A','7'], ('a', 10) all work.
                   Order matters only on split hands (APPROXIMATIONS note 3).
    dealer_up      the dealer's upcard rank
    can_double     None means "work it out from the rules": exactly two cards,
                   and either this is not a split hand or DAS is allowed.
                   Pass False when the app is not showing the DOUBLE button.
                   Passing True can never create a double on a hand of three or
                   more cards - doubling after a hit is not a table rule
                   anywhere, so the UI can only ever be more restrictive than
                   the chart, never less.
    can_split      None means: two cards, a pair, and fewer hands in play than
                   rules.max_hands (plus the resplit-aces rule).
    is_split_hand  this hand was born of a split
    hand_count     how many hands are currently in play, splits included
    comp16_requires_45
                   use the sharper form of the 16 vs 10 exception.  See
                   APPROXIMATIONS note 2 for why the default is the loose form.
    """
    cards = normalize_hand(player_cards)
    up = normalize(dealer_up)
    if len(cards) < 2:
        raise ValueError('a hand needs at least two cards before it has a decision')
    total, _soft = hand_total(cards)
    if total > 21:
        # Answering "stand" on a busted hand would be a lie dressed as advice.
        raise ValueError(f'hand {cards} is busted at {total}; there is no decision left')

    pair = is_pair(cards, rules.tens_are_pairs)

    if can_double is None:
        can_double = len(cards) == 2 and (not is_split_hand or rules.das)
    else:
        can_double = bool(can_double) and len(cards) == 2

    if can_split is None:
        # resplit_aces defaults to False in core.Rules because it was never
        # confirmed at the table.  Under that assumption a second A,A on a
        # split hand cannot be split again.
        blocked_resplit_aces = (is_split_hand and pair and cards[0] == 'A'
                                and not rules.resplit_aces)
        can_split = (len(cards) == 2 and pair and hand_count < rules.max_hands
                     and not blocked_resplit_aces)
    else:
        can_split = bool(can_split) and len(cards) == 2 and pair

    # --- split aces get one card and the hand is over.
    # Checked before the pair chart, but only when the hand cannot legally be
    # resplit; with resplit_aces on, A,A still splits.
    if (is_split_hand and not rules.hit_split_aces and len(cards) == 2
            and cards[0] == 'A' and not can_split):
        return Advice(
            action=STAND,
            action_word=ACTION_NAMES[STAND],
            reason='Split aces get one card only - there is no decision here.',
            source=SOURCE_SPLIT_ACES,
            raw_code=CODE_STAND,
            fallback_of=None,
        )

    # --- pair chart.
    # Consulted for every two-card pair, even when splitting is unavailable,
    # because several pair cells (10,10 stand; 5,5 double; 7,7 vs 8 hit) are
    # advice in their own right rather than split decisions.
    if pair:
        pkey = f'{cards[0]},{cards[1]}'
        code = _cell(PAIR_TABLE, pkey, up, rules)
        act = resolve_code(code, can_double=can_double, can_split=can_split, das=rules.das)
        if act is not None:
            # A D/Ds pair cell that could not be doubled is a DOWNGRADE and must say so.
            # Reporting source='table' hid the fact that the printed cell was not honoured.
            downgraded = code in (CODE_DOUBLE, CODE_DOUBLE_STAND) and act != DOUBLE
            return Advice(
                action=act,
                action_word=ACTION_NAMES[act],
                reason=_pair_reason(pkey, code, act, up),
                source=SOURCE_FALLBACK if downgraded else SOURCE_TABLE,
                raw_code=code,
                fallback_of=code if downgraded else None,
            )
        # The split was declined.  Fall through to the total: 8,8 that cannot
        # be split is just a hard 16 and has to be played like one.
        adv = _totals_advice(cards, up, rules, can_double, comp16_requires_45,
                             is_split_hand)
        if code == CODE_SPLIT_DAS and not rules.das:
            prefix = 'No double after split here, so the split is not worth it - '
        else:
            prefix = 'Cannot split this hand - '
        # adv.fallback_of is overwritten by the split code on purpose: the
        # split is the decision the player actually lost.  No pair falls
        # through onto a D or Ds cell (the reachable totals are 2,4,6,8,12,14,
        # 16,18), so no double downgrade is being hidden here.
        return Advice(
            action=adv.action,
            action_word=adv.action_word,
            reason=prefix + adv.reason[:1].lower() + adv.reason[1:],
            source=SOURCE_FALLBACK,
            raw_code=adv.raw_code,
            fallback_of=code,
        )

    return _totals_advice(cards, up, rules, can_double, comp16_requires_45,
                          is_split_hand)


# --- insurance -------------------------------------------------------------

def take_insurance(rules: Rules = STANDARD, **kw) -> Tuple[bool, str]:
    """Always (False, reason).  Insurance is a side bet on the hole card.

    **kw absorbs whatever context a caller wants to pass (player_cards,
    dealer_up, running count).  None of it changes the answer, and the
    signature says so by ignoring it.  The only condition that would flip this
    is a Hi-Lo true count at or above +3, which needs a shoe that persists
    between hands; handoff section 2 concludes this one does not.

    The percentages in the reason are computed from rules.decks, not pasted, so
    they stay true if the deck count ever changes.
    """
    tens = 16 * rules.decks
    unseen = 52 * rules.decks - 1          # the dealer's ace is face up
    p_ten = tens / unseen                   # 96/311 = 30.87% at six decks
    break_even = 1.0 / (rules.insurance_payout + 1.0)   # 2:1 pays for itself at 1/3
    edge = 1.0 - (rules.insurance_payout + 1.0) * p_ten  # 1 - 3 x 0.3087 = 7.40%
    reason = (f'No. The dealer has blackjack {p_ten * 100:.2f}% of the time with an ace up, '
              f'and a {rules.insurance_payout:.0f}:1 bet needs {break_even * 100:.1f}% to break even - '
              f'a {edge * 100:.2f}% house edge on the side bet.')
    return False, reason
