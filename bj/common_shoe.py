"""Explicit initial-pair decisions with two sequential hands sharing one shoe."""
from __future__ import annotations

from . import ev, joint_split
from ._enumeration import MAX_STATES, scope, state_limit
from .core import RANKS, SPLIT

MODEL = {'name': 'common_shoe_two_hand', 'version': 1}
SPLIT_MODEL = 'common_shoe_sequential_two_hand_no_resplit_binary_float_v1'


def validate(hand, rules, unseen, is_split_hand, hand_count, max_states):
    """Validate the normalized common domain without pricing any action."""
    state_limit(max_states)
    if len(hand) != 2 or hand[0] != hand[1]:
        raise ValueError('common-shoe model requires an initial two-card pair')
    if is_split_hand or hand_count != 1:
        raise ValueError('common-shoe model requires an unsplit initial hand')
    if rules.max_hands != 2 or rules.resplit_aces or rules.hit_split_aces:
        raise ValueError('common-shoe model requires max_hands=2, no resplits '
                         'and one-card split aces')
    if not 3 <= sum(unseen) <= 20:
        raise ValueError('common-shoe model requires 3 to 20 unseen cards including the hole')


def reference_counts(unseen):
    """Translate retained production counts by rank identity, never position."""
    by_rank = dict(zip(RANKS, unseen, strict=True))
    return tuple(by_rank[rank] for rank in joint_split.RANKS)


def decide(hand, up, unseen, rules, *, can_double=True, can_split=True,
           max_states=MAX_STATES):
    """Return a complete decision and work observations, or refuse the attempt.

    Inputs have passed shared record normalization. No approximate split is
    evaluated. Current controls leave the joint continuation rules intact.
    The returned work counts actual new state bodies across root and split.
    """
    validate(hand, rules, unseen, False, 1, max_states)
    with scope(max_states) as budget:
        _, values, _ = ev.best_action(hand, up, shoe=unseen, rules=rules,
                                      can_double=can_double, can_split=False)
        if can_split:
            result = joint_split.joint_split_value(
                hand[0], up, reference_counts(unseen), double_after_split=rules.das,
                stand_soft_17=rules.s17, max_states=max_states)
            values[SPLIT] = result.value
        ordered = sorted(values.items(), key=lambda item: item[1], reverse=True)
        action, best = ordered[0]
        margin = best - ordered[1][1] if len(ordered) > 1 else 0.0
        return action, values, margin, budget.snapshot()
