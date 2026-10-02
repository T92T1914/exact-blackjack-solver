"""The public compiled lookup cannot create actions that table rules forbid."""
from itertools import product

import pytest

from bj.core import DOUBLE, HIT, RANK_INDEX, RANKS, SPLIT, STAND, Rules
from bj.simulate import Cards, compiled_action, play_round
from bj.strategy import basic_action


@pytest.mark.parametrize('cards,up,rules,context,expected', [
    (('5', '6'), '6', Rules(das=False), {'is_split_hand': True}, HIT),
    (('A', '7'), '4', Rules(das=False), {'is_split_hand': True}, STAND),
    (('A', 'A'), '6', Rules(), {'is_split_hand': True}, STAND),
    (('A', '7'), '4', Rules(), {'is_split_hand': True}, STAND),
    (('8', '8'), '6', Rules(), {'hand_count': 4}, STAND),
    (('A', 'A'), '6', Rules(resplit_aces=True),
     {'is_split_hand': True, 'hand_count': 4}, STAND),
    (('2', '2'), '6', Rules(), {'hand_count': 4}, HIT),
    (('7', 'A'), '4', Rules(), {'is_split_hand': True}, DOUBLE),
    (('A', 'A'), '6', Rules(resplit_aces=True), {'is_split_hand': True}, SPLIT),
])
def test_affirmative_buttons_cannot_override_rules(cards, up, rules, context, expected):
    # Expected values are the chart's hard/soft fallbacks and split-ace rule.
    # They do not come from the compiled lookup being checked.
    assert compiled_action(cards, up, rules, can_double=True,
                           can_split=True, **context) == expected


@pytest.mark.parametrize('cards,up,context,expected', [
    (('5', '6'), '6', {}, HIT),
    (('A', '7'), '4', {}, STAND),
    (('8', '8'), '6', {}, STAND),
    (('A', 'A'), '6', {'is_split_hand': True}, STAND),
])
def test_negative_buttons_still_remove_permitted_actions(cards, up, context, expected):
    assert compiled_action(cards, up, Rules(resplit_aces=True),
                           can_double=False, can_split=False, **context) == expected


@pytest.mark.parametrize('rules,split_hand,hand_count', [
    (Rules(), False, 1),
    (Rules(das=False), True, 2),
    (Rules(resplit_aces=True), True, 4),
    (Rules(hit_split_aces=True), True, 2),
    (Rules(s17=False, resplit_aces=True), True, 2),
])
def test_lookup_matches_chart_for_two_card_rule_contexts(rules, split_hand, hand_count):
    # The complete ordered two-card/upcard grid includes both dealt orders
    # for an ace. Each of four button states is checked at the public boundary.
    for first, second, up, can_double, can_split in product(
            RANKS, RANKS, RANKS, (False, True), (False, True)):
        context = dict(can_double=can_double, can_split=can_split,
                       is_split_hand=split_hand, hand_count=hand_count)
        expected = basic_action((first, second), up, rules, **context).action
        actual = compiled_action((first, second), up, rules, **context)
        assert actual == expected, (first, second, up, rules, context)


def test_existing_call_shape_keeps_first_hand_default():
    actual = compiled_action(('8', '8'), '6', can_double=True, can_split=True)
    explicit = compiled_action(('8', '8'), '6', can_double=True, can_split=True,
                               hand_count=1)
    assert actual == explicit == SPLIT


class ScriptedCards(Cards):
    """An owned, fixed deal that fails if the round consumes an extra card."""

    def __init__(self, ranks):
        self.ranks = tuple(RANK_INDEX[rank] for rank in ranks)
        self._i = 0

    def draw(self):
        card = self.ranks[self._i]
        self._i += 1
        return card


@pytest.mark.parametrize('rules,ranks,finals', [
    (Rules(das=False), ('8', '6', '8', 'T', '3', 'T', '3', 'T', 'T'), [21, 21]),
    (Rules(max_hands=2), ('8', '6', '8', 'T', '8', 'T', 'T'), [16, 18]),
])
def test_public_lookup_works_as_the_round_strategy(rules, ranks, finals):
    contexts = []

    def strategy(cards, up, **context):
        contexts.append(context)
        return compiled_action(cards, up, rules, **context)

    inline_cards = ScriptedCards(ranks)
    caller_cards = ScriptedCards(ranks)
    expected = play_round(inline_cards, rules)
    actual = play_round(caller_cards, rules, strategy=strategy)
    assert actual == expected
    # Each hand wins one unit when the dealer's last ten busts 16.
    assert actual.net == 2 and actual.wagered == 2 and actual.n_hands == 2
    assert actual.player_finals == finals and not actual.doubled
    assert inline_cards.cards_drawn == caller_cards.cards_drawn == len(ranks)
    assert contexts[0]['hand_count'] == 1
    assert any(context['is_split_hand'] and context['hand_count'] == 2
               for context in contexts)
