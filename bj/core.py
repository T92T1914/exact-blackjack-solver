"""Core primitives shared by every module.

Ten-value cards (10, J, Q, K) collapse to the single rank 'T' because they are
mathematically identical in blackjack.  The only place the distinction matters
is cosmetic display, which this engine does not do.

A shoe is an immutable tuple of 10 integers, indexed by RANK_INDEX: how many
cards of each rank remain unseen.  Immutable so that it can be a memoisation
key in the exact solvers - every cached result in bj.dealer and bj.ev is keyed
on a Shoe, and a key nobody can mutate is a cache nobody can poison.  Removing
a card returns a new tuple; nothing here is ever modified in place.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

# --- ranks -----------------------------------------------------------------

RANKS: tuple[str, ...] = ('A', '2', '3', '4', '5', '6', '7', '8', '9', 'T')
RANK_INDEX = {r: i for i, r in enumerate(RANKS)}
RANK_VALUE = {'A': 11, '2': 2, '3': 3, '4': 4, '5': 5,
              '6': 6, '7': 7, '8': 8, '9': 9, 'T': 10}
#: cards of each rank in one 52-card deck, same order as RANKS
CARDS_PER_DECK = (4, 4, 4, 4, 4, 4, 4, 4, 4, 16)

#: a card rank in any spelling normalize() accepts: 'K', 'k', 10, '10', 'a', ...
CardLike = str | int

_ALIASES = {
    'A': 'A', 'a': 'A', '1': 'A', 'ACE': 'A',
    '10': 'T', 'T': 'T', 't': 'T',
    'J': 'T', 'j': 'T', 'Q': 'T', 'q': 'T', 'K': 'T', 'k': 'T',
}


def normalize(rank: CardLike) -> str:
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


def normalize_hand(cards: str | Iterable[CardLike]) -> tuple[str, ...]:
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

def hand_total(cards: Iterable[CardLike]) -> tuple[int, bool]:
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


def hard_total(cards: Iterable[CardLike]) -> int:
    """Total with every ace counted as 1."""
    return sum(1 if normalize(c) == 'A' else RANK_VALUE[normalize(c)] for c in cards)


def is_busted(cards: Iterable[CardLike]) -> bool:
    """True once even the hard total is over 21."""
    return hand_total(cards)[0] > 21


def is_blackjack(cards: Sequence[CardLike], is_split_hand: bool = False) -> bool:
    """Natural: exactly two cards totalling 21, and not a hand born of a split."""
    if is_split_hand or len(cards) != 2:
        return False
    return hand_total(cards)[0] == 21


def is_pair(cards: Sequence[CardLike], tens_are_pairs: bool = True) -> bool:
    """Two cards of the same rank, i.e. a hand the table will let you split.

    The original table offers SPLIT on any two ten-value cards (Q+J counts),
    and because every ten-value card is already the single rank 'T' here that
    is the only behaviour this module can express.  ``tens_are_pairs`` mirrors
    the Rules field so call sites read naturally; it cannot change the answer,
    since the rank distinction it would need is not modelled.
    """
    return len(cards) == 2 and normalize(cards[0]) == normalize(cards[1])


# --- rules -----------------------------------------------------------------

@dataclass(frozen=True)
class Rules:
    """The table the solver prices.  Every solver function takes one.

    The defaults are the original table's, read off its rules panel: six
    decks, dealer stands on soft 17, double after split, dealer peeks for a
    natural, no surrender, up to four hands, 3:2 on a natural.  Frozen so a
    Rules object can sit inside a memo key.
    """
    decks: int = 6
    s17: bool = True                # dealer stands on all 17s
    das: bool = True                # double after split
    peek: bool = True               # dealer peeks for blackjack
    surrender: bool = False
    resplit_aces: bool = False      # unconfirmed at the original table; conservative default
    hit_split_aces: bool = False    # unconfirmed at the original table; conservative default
    max_hands: int = 4              # split up to 4 hands
    blackjack_payout: float = 1.5   # 3:2
    double_any_two: bool = True
    tens_are_pairs: bool = True
    insurance_payout: float = 2.0   # 2:1


STANDARD = Rules()


# --- shoe ------------------------------------------------------------------

#: count of unseen cards per rank, in RANKS order.  Immutable on purpose:
#: see the module docstring.
Shoe = tuple[int, ...]


def fresh_shoe(decks: int = 6) -> Shoe:
    """A full shoe of `decks` decks with nothing removed."""
    return tuple(c * decks for c in CARDS_PER_DECK)


def shoe_size(shoe: Shoe) -> int:
    """How many cards are left."""
    return sum(shoe)


def _index(rank: int | CardLike) -> int:
    """A shoe index from either an index (the hot loops pass ints) or a rank."""
    return rank if isinstance(rank, int) else RANK_INDEX[normalize(rank)]


def remove_card(shoe: Shoe, rank: int | CardLike) -> Shoe:
    """A new shoe with one card of `rank` taken out.  Raises if none is left.

    `rank` is a shoe INDEX when it is an int - that is what every inner loop
    in bj.dealer and bj.ev passes - and otherwise any spelling of a rank.
    """
    i = _index(rank)
    if shoe[i] <= 0:
        raise ValueError(f'no {RANKS[i]} left in shoe')
    lst = list(shoe)
    lst[i] -= 1
    return tuple(lst)


def remove_cards(shoe: Shoe, cards: Iterable[int | CardLike]) -> Shoe:
    """A new shoe with each of `cards` taken out; same index-or-rank rule."""
    lst = list(shoe)
    for c in cards:
        i = _index(c)
        if lst[i] <= 0:
            raise ValueError(f'no {RANKS[i]} left in shoe')
        lst[i] -= 1
    return tuple(lst)


def add_card(shoe: Shoe, rank: int | CardLike) -> Shoe:
    """A new shoe with one card of `rank` put back."""
    i = _index(rank)
    lst = list(shoe)
    lst[i] += 1
    return tuple(lst)


def draw_prob(shoe: Shoe, rank: int | CardLike) -> float:
    """Probability that the next card drawn is `rank`; 0.0 from an empty shoe."""
    n = shoe_size(shoe)
    if n == 0:
        return 0.0
    return shoe[_index(rank)] / n


# --- actions ---------------------------------------------------------------

HIT, STAND, DOUBLE, SPLIT = 'H', 'S', 'D', 'P'
ACTION_NAMES = {HIT: 'HIT', STAND: 'STAND', DOUBLE: 'DOUBLE', SPLIT: 'SPLIT'}
