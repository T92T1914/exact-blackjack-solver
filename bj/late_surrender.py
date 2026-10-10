"""One original initial hand with an explicitly offered post-peek half-loss."""
from __future__ import annotations

from . import ev
from ._enumeration import MAX_STATES, scope, state_limit
from .core import DOUBLE, HIT, STAND, hand_total

MODEL = {'name': 'post_peek_late_surrender', 'version': 1}
SURRENDER = 'R'
ACTION_NAMES = {STAND: 'STAND', HIT: 'HIT', DOUBLE: 'DOUBLE', SURRENDER: 'SURRENDER'}
ROOT_FAMILIES = frozenset(('root_draw', 'root_hit', 'root_double',
                           'root_distribution', 'root_dealer'))


def validate_rules(rules):
    """Require this family's rules after the shared value/type validation."""
    if not rules.peek or not rules.surrender:
        raise ValueError('late-surrender model requires peek=True and surrender=True')
    if not rules.double_any_two or not rules.tens_are_pairs:
        raise ValueError('late-surrender model requires any-two-card double '
                         'and collapsed ten-value ranks')
    if rules.max_hands != 1 or rules.resplit_aces or rules.hit_split_aces:
        raise ValueError('late-surrender model requires max_hands=1, '
                         'no resplits and no hittable split aces')


def validate(hand, rules, unseen, is_split_hand, hand_count, max_states, *, can_split=False):
    """Validate the normalized initial-only domain without pricing an action."""
    state_limit(max_states)
    validate_rules(rules)
    if len(hand) != 2 or hand_total(hand)[0] >= 21:
        raise ValueError('late-surrender model requires an initial two-card hand below 21')
    if is_split_hand or hand_count != 1 or can_split:
        raise ValueError('late-surrender model requires one original hand with no split choice')
    if not 3 <= sum(unseen) <= 20:
        raise ValueError('late-surrender model requires 3 to 20 unseen cards including the hole')


def model_record(up, max_states):
    """Declare the exact conditional family and its replay work allowance."""
    return {
        **MODEL, 'dealer_information': 'hidden_hole_post_peek',
        'hole_rank_excluded_by_peek': 'T' if up == 'A' else 'A' if up == 'T' else None,
        'ten_value_ranks': 'collapsed_to_T', 'insurance_priced': False,
        'hit_stand_double': 'finite_enumeration_binary_floating_point',
        'split': 'excluded_single_original_hand',
        'decision_phase': 'initial_original_two_card_below_21',
        'surrender': 'terminal_half_original_wager_post_negative_peek',
        'surrender_after_hit': False, 'surrender_after_double': False, 'surrender_draws': 0,
        'player_last_draw': 'stand_then_require_dealer_settlement',
        'enumeration_state_limit': state_limit(max_states),
    }


def rank(values):
    """Choose the first raw maximum in the declared S,H,D,R order."""
    ordered = sorted(((action, values[action]) for action in ACTION_NAMES if action in values),
                     key=lambda item: item[1], reverse=True)
    action, best = ordered[0]
    margin = best - ordered[1][1] if len(ordered) > 1 else 0.0
    return action, margin


def decide(hand, up, unseen, rules, *, can_double=True, can_surrender=True,
           max_states=MAX_STATES):
    """Price every offered alternative, retaining accepted S/H/D continuations.

    Inputs have passed shared record normalization. A failed ordinary branch
    withholds the whole decision even though surrender's terminal value is known.
    No later hit or double decision offers surrender.
    """
    for name, value in (('can_double', can_double), ('can_surrender', can_surrender)):
        if type(value) is not bool:
            raise ValueError(f'{name} must be a boolean')
    validate(hand, rules, unseen, False, 1, max_states)
    with scope(max_states) as budget:
        _, values, _ = ev.best_action(hand, up, shoe=unseen, rules=rules,
                                      can_double=can_double, can_split=False)
        if can_surrender:
            values[SURRENDER] = -0.5
        action, margin = rank(values)
        return action, values, margin, budget.snapshot()
