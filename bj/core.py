"""Core primitives shared by every module.

Ten-value cards (10, J, Q, K) collapse to the single rank 'T' because they are
mathematically identical in blackjack.  The only place the distinction matters
is cosmetic display, which this engine does not do.

A shoe is an immutable tuple of 10 integers, indexed by RANK_INDEX.  Immutable
so that it can be used as a memoisation key in the exact EV solver.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

# --- ranks -----------------------------------------------------------------

RANKS: tuple[str, ...] = ('A', '2', '3', '4', '5', '6', '7', '8', '9', 'T')
RANK_INDEX = {r: i for i, r in enumerate(RANKS)}
RANK_VALUE = {'A': 11, '2': 2, '3': 3, '4': 4, '5': 5,
              '6': 6, '7': 7, '8': 8, '9': 9, 'T': 10}
#: cards of each rank in one 52-card deck, same order as RANKS
CARDS_PER_DECK = (4, 4, 4, 4, 4, 4, 4, 4, 4, 16)

_ALIASES = {
    'A': 'A', 'a': 'A', '1': 'A', 'ACE': 'A',
    '10': 'T', 'T': 'T', 't': 'T',
    'J': 'T', 'j': 'T', 'Q': 'T', 'q': 'T', 'K': 'T', 'k': 'T',
}


def normalize(rank) -> str:
    """'K' -> 'T', 10 -> 'T', 'a' -> 'A'.  Raises ValueError on junk."""
    if isinstance(rank, int):
        rank = str(rank)
    r = _ALIASES.get(rank)
    if r is not None:
        return r
    r = str(rank).strip().upper()
    r = _ALIASES.get(r, r)
    if r not in RANK_INDEX:
        raise ValueError(f'unknown card rank: {rank!r}')
    return r


def normalize_hand(cards) -> tuple[str, ...]:
    """Accepts 'A,7' / 'A7' / ['A','7'] / ('a', 10) -> ('A', '7')."""
    if isinstance(cards, str):
        s = cards.replace(',', ' ').replace('-', ' ').strip()
        if ' ' in s:
            parts = s.split()
        else:
            parts, i = [], 0
            while i < len(s):
                if s[i:i + 2] == '10':
                    parts.append('10')
                    i += 2
                else:
                    parts.append(s[i])
                    i += 1
        return tuple(normalize(p) for p in parts)
    return tuple(normalize(c) for c in cards)


# --- hands -----------------------------------------------------------------

def hand_total(cards) -> tuple[int, bool]:
    """Return (best total <= 21 if possible, is_soft).

    is_soft is True when an ace is still being counted as 11.
    A busted hand returns its hard total with is_soft False.
    """
    total = 0
    aces = 0
    for c in cards:
        r = normalize(c)
        if r == 'A':
            aces += 1
            total += 11
        else:
            total += RANK_VALUE[r]
    soft = aces > 0
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
        soft = aces > 0
    return total, soft


def hard_total(cards) -> int:
    """Total with every ace counted as 1."""
    return sum(1 if normalize(c) == 'A' else RANK_VALUE[normalize(c)] for c in cards)


def is_busted(cards) -> bool:
    return hand_total(cards)[0] > 21


def is_blackjack(cards, is_split_hand: bool = False) -> bool:
    """Natural: exactly two cards totalling 21, and not a hand born of a split."""
    if is_split_hand or len(cards) != 2:
        return False
    return hand_total(cards)[0] == 21


def is_pair(cards, tens_are_pairs: bool = True) -> bool:
    """Two cards the table will let you split.

    the example table offers SPLIT on any two ten-value cards (Q+J counts), so the
    default folds all ten-value ranks together.
    """
    if len(cards) != 2:
        return False
    a, b = normalize(cards[0]), normalize(cards[1])
    if tens_are_pairs:
        return a == b
    return a == b  # ranks are already collapsed to 'T'; kept for signature clarity


# --- rules -----------------------------------------------------------------

@dataclass(frozen=True)
class Rules:
    """the example table defaults, taken from the in-app rules panel."""
    decks: int = 6
    s17: bool = True                # dealer stands on all 17s
    das: bool = True                # double after split
    peek: bool = True               # dealer peeks for blackjack
    surrender: bool = False
    resplit_aces: bool = False      # unknown at the table; conservative default
    hit_split_aces: bool = False    # unknown at the table; conservative default
    max_hands: int = 4              # split up to 4 hands
    blackjack_payout: float = 1.5   # 3:2
    double_any_two: bool = True
    tens_are_pairs: bool = True
    insurance_payout: float = 2.0   # 2:1


STANDARD = Rules()


# --- shoe ------------------------------------------------------------------

Shoe = tuple[int, ...]


def fresh_shoe(decks: int = 6) -> Shoe:
    return tuple(c * decks for c in CARDS_PER_DECK)


def shoe_size(shoe: Shoe) -> int:
    return sum(shoe)


def remove_card(shoe: Shoe, rank) -> Shoe:
    i = rank if isinstance(rank, int) else RANK_INDEX[normalize(rank)]
    if shoe[i] <= 0:
        raise ValueError(f'no {RANKS[i]} left in shoe')
    lst = list(shoe)
    lst[i] -= 1
    return tuple(lst)


def remove_cards(shoe: Shoe, cards: Iterable) -> Shoe:
    lst = list(shoe)
    for c in cards:
        i = c if isinstance(c, int) else RANK_INDEX[normalize(c)]
        if lst[i] <= 0:
            raise ValueError(f'no {RANKS[i]} left in shoe')
        lst[i] -= 1
    return tuple(lst)


def add_card(shoe: Shoe, rank) -> Shoe:
    i = rank if isinstance(rank, int) else RANK_INDEX[normalize(rank)]
    lst = list(shoe)
    lst[i] += 1
    return tuple(lst)


def draw_prob(shoe: Shoe, rank) -> float:
    n = shoe_size(shoe)
    if n == 0:
        return 0.0
    i = rank if isinstance(rank, int) else RANK_INDEX[normalize(rank)]
    return shoe[i] / n


# --- actions ---------------------------------------------------------------

HIT, STAND, DOUBLE, SPLIT = 'H', 'S', 'D', 'P'
ACTION_NAMES = {HIT: 'HIT', STAND: 'STAND', DOUBLE: 'DOUBLE', SPLIT: 'SPLIT'}
