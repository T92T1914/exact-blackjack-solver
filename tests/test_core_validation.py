"""Validate shoe construction before invalid counts enter a solver cache."""

import pytest

from bj.core import CARDS_PER_DECK, fresh_shoe, shoe_size


@pytest.mark.parametrize('decks', [0, -1, True, False, 1.5, 2.0, '6', None])
def test_fresh_shoe_rejects_invalid_deck_counts(decks):
    with pytest.raises(ValueError, match='decks must be a positive integer'):
        fresh_shoe(decks)


@pytest.mark.parametrize('decks', [1, 6, 8])
def test_fresh_shoe_preserves_rank_counts(decks):
    shoe = fresh_shoe(decks)
    assert shoe == tuple(count * decks for count in CARDS_PER_DECK)
    assert shoe_size(shoe) == 52 * decks
