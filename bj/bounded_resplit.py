"""Initial non-ace pair with one globally shared common-shoe resplit slot."""
from __future__ import annotations

from . import ev, joint_resplit
from ._enumeration import MAX_STATES, scope, state_limit
from .core import RANKS, SPLIT

MODEL = {'name': 'common_shoe_bounded_resplit', 'version': 1}
SPLIT_MODEL = 'common_shoe_sequential_up_to_three_one_extra_resplit_binary_float_v1'
ROOT_FAMILIES = frozenset(('root_draw', 'root_hit', 'root_double',
                           'root_distribution', 'root_dealer'))
FAMILIES = ROOT_FAMILIES | frozenset(('resplit_draw', 'resplit_play',
                                    'resplit_settle', 'resplit_dealer'))


def validate_rules(rules):
    """Require this family after shared rule value/type validation."""
    if not rules.peek or rules.surrender:
        raise ValueError('bounded-resplit model requires peek=True and surrender=False')
    if not rules.double_any_two or not rules.tens_are_pairs:
        raise ValueError('bounded-resplit model requires any-two-card double '
                         'and collapsed ten-value ranks')
    if rules.max_hands != 3 or rules.resplit_aces or rules.hit_split_aces:
        raise ValueError('bounded-resplit model requires max_hands=3 '
                         'and no split-ace extensions')


def validate(hand, rules, unseen, is_split_hand, hand_count, max_states):
    """Validate the normalized original-pair domain without pricing actions."""
    state_limit(max_states)
    validate_rules(rules)
    if len(hand) != 2 or hand[0] != hand[1] or hand[0] == 'A':
        raise ValueError('bounded-resplit model requires an initial non-ace two-card pair')
    if is_split_hand or hand_count != 1:
        raise ValueError('bounded-resplit model requires one original unsplit hand')
    if not 3 <= sum(unseen) <= 20:
        raise ValueError('bounded-resplit model requires 3 to 20 unseen cards including the hole')


def model_record(up, max_states):
    """Declare the full conditional model, including the ordinary root convention."""
    return {
        **MODEL, 'dealer_information': 'hidden_hole_post_peek',
        'hole_rank_excluded_by_peek': 'T' if up == 'A' else 'A' if up == 'T' else None,
        'ten_value_ranks': 'collapsed_to_T', 'insurance_priced': False,
        'hit_stand_double': 'finite_enumeration_binary_floating_point',
        'player_last_draw': 'stand_then_require_dealer_settlement',
        'split': SPLIT_MODEL, 'split_max_hands': 3, 'split_max_extra_resplits': 1,
        'split_deal_order': 'finish_active_child_before_dealing_next_pending',
        'split_child_order': 'new_sibling_before_older_pending',
        'split_eligibility': 'matching_two_card_active_hand_before_hit_or_double',
        'split_aces': 'excluded_non_ace_initial_pair',
        'split_twenty_one': 'ordinary_wager_no_natural_premium',
        'split_objective': 'combined_settlement_all_completed_wagers',
        'split_exhaustion': 'refuse_any_unavailable_continuation',
        'split_cooperative_seconds': 10.0,
        'enumeration_state_limit': state_limit(max_states),
    }


def rank(values):
    """Use the first raw maximum in S,H,D,P order, without a tie epsilon."""
    ordered = sorted(((action, values[action]) for action in ('S', 'H', 'D', 'P')
                      if action in values),
                     key=lambda item: item[1], reverse=True)
    action, best = ordered[0]
    return action, best - ordered[1][1] if len(ordered) > 1 else 0.0


def decide(hand, up, unseen, rules, *, can_double=True, can_split=True,
           max_states=MAX_STATES):
    """Complete accepted root pricing and the optional joint continuation."""
    for name, value in (('can_double', can_double), ('can_split', can_split)):
        if type(value) is not bool:
            raise ValueError(f'{name} must be a boolean')
    validate(hand, rules, unseen, False, 1, max_states)
    with scope(max_states) as budget:
        _, values, _ = ev.best_action(hand, up, shoe=unseen, rules=rules,
                                      can_double=can_double, can_split=False)
        if can_split:
            by_rank = dict(zip(RANKS, unseen, strict=True))
            result = joint_resplit.joint_resplit_value(
                hand[0], up, tuple(by_rank[rank] for rank in joint_resplit.RANKS),
                double_after_split=rules.das, stand_soft_17=rules.s17,
                max_states=max_states)
            values[SPLIT] = result.value
        action, margin = rank(values)
        return action, values, margin, budget.snapshot()
