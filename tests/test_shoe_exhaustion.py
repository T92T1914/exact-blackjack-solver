"""Unseen cards include the dealer's reserved card, even without a peek."""
import pytest

from bj import ev
from bj.core import RANKS


@pytest.mark.parametrize('up', RANKS)
def test_player_cannot_draw_the_only_unseen_card(up):
    shoe = (0, 0, 0, 0, 0, 0, 0, 1, 0, 0)  # one nine, held by the dealer
    with pytest.raises(ValueError, match='hole card'):
        ev._draw_probs(shoe, up)


def test_busting_does_not_allow_hitting_with_no_draw_pile():
    shoe = (0, 0, 0, 0, 0, 0, 0, 0, 1, 0)  # dealer's ten
    with pytest.raises(ValueError, match='hole card'):
        ev.ev_hit(('T', 'T'), '7', shoe)


def test_one_drawable_card_remains_a_valid_distribution():
    # Each of the two hidden cards is equally likely to be reserved; the
    # player's sole draw is the other one. No peek information under a seven.
    shoe = (1, 0, 0, 0, 0, 0, 0, 0, 1, 0)
    assert ev._draw_probs(shoe, '7') == (0.5, 0, 0, 0, 0, 0, 0, 0, 0.5, 0)
