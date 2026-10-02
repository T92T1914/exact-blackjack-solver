"""Caller availability can remove actions, but cannot override table rules."""
import pytest

from bj import ev
from bj.core import DOUBLE, HIT, SPLIT, STAND, Rules
from bj.strategy import basic_action


@pytest.mark.parametrize('cards,up,rules,context,expected', [
    (('5', '6'), '6', Rules(das=False), {'is_split_hand': True}, HIT),
    (('A', '7'), '4', Rules(das=False), {'is_split_hand': True}, STAND),
    (('8', '8'), '6', Rules(), {'hand_count': 4}, STAND),
    (('8', '8'), 'T', Rules(), {'hand_count': 4}, HIT),
    (('A', 'A'), '6', Rules(), {'is_split_hand': True, 'hand_count': 2}, STAND),
    (('A', 'A'), '6', Rules(max_hands=1), {}, HIT),
    (('A', 'A'), '6', Rules(resplit_aces=True),
     {'is_split_hand': True, 'hand_count': 4}, STAND),
])
def test_true_availability_cannot_make_a_rule_forbidden_action(cards, up, rules,
                                                            context, expected):
    # These expected plays come from the chart's hard/soft fallback cells and
    # the one-card split-ace rule, not from the solver's EV implementation.
    inferred = basic_action(cards, up, rules, **context)
    supplied = basic_action(cards, up, rules, **context, can_double=True, can_split=True)
    assert supplied.action == expected
    assert supplied == inferred


@pytest.mark.parametrize('cards,up,context,allowed,restricted', [
    (('5', '6'), '6', {}, DOUBLE, HIT),
    (('A', '7'), '4', {}, DOUBLE, STAND),
    (('8', '8'), '6', {}, SPLIT, STAND),
    (('A', 'A'), '6', {'is_split_hand': True}, SPLIT, STAND),
])
def test_availability_can_still_remove_a_rule_permitted_action(cards, up, context,
                                                             allowed, restricted):
    rules = Rules(resplit_aces=True)
    assert basic_action(cards, up, rules, **context,
                        can_double=True, can_split=True).action == allowed
    assert basic_action(cards, up, rules, **context,
                        can_double=False, can_split=False).action == restricted


def test_double_override_is_inert_for_every_split_two_card_cell_without_das():
    # The complete 10 by 10 by 10 two-card/upcard grid also includes ten-value
    # aliases. Each caller flag is compared with the ordinary rule path.
    ranks = ('A', '2', '3', '4', '5', '6', '7', '8', '9', 'Q')
    rules = Rules(das=False, hit_split_aces=True)
    for first in ranks:
        for second in ranks:
            for up in ranks:
                hand = (first, second)
                inferred = basic_action(hand, up, rules, is_split_hand=True, hand_count=2)
                supplied = basic_action(hand, up, rules, is_split_hand=True, hand_count=2,
                                        can_double=True)
                assert supplied == inferred, (hand, up)
                assert supplied.action != DOUBLE


def test_split_override_is_inert_at_the_cap_for_every_pair_cell():
    ranks = ('A', '2', '3', '4', '5', '6', '7', '8', '9', 'J')
    rules = Rules(resplit_aces=True)
    for rank in ranks:
        for up in ranks:
            for split_hand in (False, True):
                context = {'hand_count': rules.max_hands, 'is_split_hand': split_hand}
                inferred = basic_action((rank, rank), up, rules, **context)
                supplied = basic_action((rank, rank), up, rules, **context, can_split=True)
                assert supplied == inferred, (rank, up, split_hand)
                assert supplied.action != SPLIT


@pytest.mark.parametrize('cards,rules,context,legal', [
    (('5', '6'), Rules(das=False), {'is_split_hand': True}, {STAND, HIT}),
    (('8', '8'), Rules(), {'hand_count': 4}, {STAND, HIT, DOUBLE}),
    (('A', 'A'), Rules(), {'is_split_hand': True, 'hand_count': 2}, {STAND}),
])
def test_chart_advice_and_ev_admission_share_the_same_rule_boundary(cards, rules, context, legal):
    # Only four unseen cards, all high enough to settle a ten-up dealer.
    # No fresh-shoe table generation or whole-game estimate is involved.
    counts = (0, 0, 0, 0, 0, 0, 1, 1, 1, 1)  # 7, 8, 9, T
    advice = basic_action(cards, 'T', rules, **context, can_double=True, can_split=True)
    _action, values, _margin = ev.best_action(cards, 'T', counts, rules, **context,
                                            can_double=True, can_split=True)
    assert set(values) == legal
    assert advice.action in legal
