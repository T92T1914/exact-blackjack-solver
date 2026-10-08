"""Portable records for one completed solver call, without display rounding.

The record owns normalized copies of the visible cards, remaining rank counts
and rules. It prices the existing post-peek game, not an alternate rules model.
No whole-game estimate, timestamp, filename or environment identifier is added.
"""
from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import fields
from numbers import Integral, Real
from typing import Any

from . import __version__
from .core import (ACTION_NAMES, RANKS, STANDARD, CardLike, Rules, Shoe, hand_total,
                   normalize, normalize_hand, normalize_shoe)
from .ev import best_action, initial_shoe_for

__all__ = ['SCHEMA_VERSION', 'decision_record', 'decision_json']

SCHEMA_VERSION = 1


class _UnsupportedRules(ValueError):
    """Well-typed rules outside the decision record's declared model."""


def _rules_record(rules: Rules) -> dict[str, Any]:
    if not isinstance(rules, Rules):
        raise ValueError('rules must be a Rules instance')
    values = {field.name: getattr(rules, field.name) for field in fields(Rules)}
    for name in ('decks', 'max_hands'):
        value = values[name]
        if not isinstance(value, Integral) or isinstance(value, bool) or value < 1:
            raise ValueError(f'{name} must be a positive integer')
        values[name] = int(value)
    for name in ('s17', 'das', 'peek', 'surrender', 'resplit_aces', 'hit_split_aces',
                 'double_any_two', 'tens_are_pairs'):
        if not isinstance(values[name], bool):
            raise ValueError(f'{name} must be a boolean')
    for name in ('blackjack_payout', 'insurance_payout'):
        value = values[name]
        if not isinstance(value, Real) or isinstance(value, bool):
            raise ValueError(f'{name} must be finite and nonnegative')
        try:
            values[name] = float(value)
        except (OverflowError, ValueError):
            raise ValueError(f'{name} must be finite and nonnegative') from None
        if not math.isfinite(values[name]) or values[name] < 0:
            raise ValueError(f'{name} must be finite and nonnegative')
    if not rules.peek:
        raise _UnsupportedRules('decision records model the post-peek game; peek must be True')
    if rules.surrender:
        raise _UnsupportedRules('decision records do not model surrender')
    if not rules.double_any_two:
        raise _UnsupportedRules('decision records require doubling on any two-card hand')
    if not rules.tens_are_pairs:
        raise _UnsupportedRules(
            'decision records collapse ten-value ranks and require tens_are_pairs')
    return values


def _record_inputs(cards, dealer_up, rules, shoe, is_split_hand, hand_count):
    """Normalize the shared exporter/importer boundary without calculating EVs."""
    if not isinstance(is_split_hand, bool):
        raise ValueError('is_split_hand must be a boolean')
    if hand_count is None:
        hand_count = 2 if is_split_hand else 1
    if (not isinstance(hand_count, Integral) or isinstance(hand_count, bool)
            or not 1 <= hand_count <= rules.max_hands):
        raise ValueError(f'hand_count must be an integer from 1 to {rules.max_hands}')
    if is_split_hand and hand_count < 2:
        raise ValueError('a split hand requires at least two hands in the round')
    if not is_split_hand and hand_count != 1:
        raise ValueError('hand_count above 1 requires a split hand')
    hand = normalize_hand(cards)
    up = normalize(dealer_up)
    if len(hand) < 2:
        raise ValueError('a hand needs at least two cards before it has a decision')
    total, _soft = hand_total(hand)
    if total > 21:
        raise ValueError(f'hand {hand} is busted at {total}; there is no decision left')
    if (is_split_hand and hand[0] == 'A' and len(hand) > 2
            and not rules.hit_split_aces):
        raise ValueError('a split ace receives only one card when hit_split_aces is False')
    unseen = normalize_shoe(initial_shoe_for(hand, up, rules) if shoe is None else shoe)
    if not sum(unseen):
        raise ValueError('an unseen shoe must include the reserved dealer hole card')
    excluded = 'T' if up == 'A' else 'A' if up == 'T' else None
    if excluded is not None and sum(unseen) == unseen[RANKS.index(excluded)]:
        raise ValueError(f'after the peek there is no possible hole card for upcard {up}')
    return hand, up, unseen, int(hand_count)


def _model_record(up):
    return {
        'dealer_information': 'hidden_hole_post_peek',
        'hole_rank_excluded_by_peek': 'T' if up == 'A' else 'A' if up == 'T' else None,
        'ten_value_ranks': 'collapsed_to_T', 'insurance_priced': False,
        'hit_stand_double': 'finite_enumeration_binary_floating_point',
        'split': 'independent_hands_greedy_shared_resplit_budget',
        'split_error_bound': None,
    }


def decision_record(cards: str | Sequence[CardLike], dealer_up: CardLike,
                    rules: Rules = STANDARD, *, shoe: Shoe | None = None,
                    is_split_hand: bool = False,
                    hand_count: int | None = None) -> dict[str, Any]:
    """Return a versioned JSON-compatible record of this hand's modeled decision.

    ``shoe`` is every unseen card, including the hidden dealer hole. Supplied
    counts already exclude visible cards. Without them, a fresh shoe is made
    and the visible cards are removed once. The resulting counts are retained
    in either case, so replay does not depend on the fresh-shoe convention.

    Split state and the full rules accompany raw binary floating-point EVs in
    original wager units. Hit, stand and double enumerate finite continuations.
    Split retains the independent-hand and greedy shared-budget approximation.
    Unsupported rules and nonfinite results are errors rather than JSON claims.
    The ordinary text interface remains independent of this stricter record.
    """
    rule_values = _rules_record(rules)
    hand, up, unseen, hand_count = _record_inputs(
        cards, dealer_up, rules, shoe, is_split_hand, hand_count)
    action, evs, margin = best_action(hand, up, shoe=unseen, rules=rules,
                                    is_split_hand=is_split_hand, hand_count=hand_count)
    if not evs or action not in evs or any(key not in ACTION_NAMES for key in evs):
        raise ValueError('solver returned an invalid action set')
    values = {}
    for key, value in evs.items():
        if not isinstance(value, Real) or isinstance(value, bool) or not math.isfinite(value):
            raise ValueError('solver returned a nonfinite or invalid action value')
        values[key] = float(value)
    if not isinstance(margin, Real) or isinstance(margin, bool) or not math.isfinite(margin):
        raise ValueError('solver returned a nonfinite or invalid decision margin')
    ranked = sorted(values.values(), reverse=True)
    expected_margin = ranked[0] - ranked[1] if len(ranked) > 1 else 0.0
    if values[action] != ranked[0] or margin != expected_margin:
        raise ValueError('solver returned an inconsistent recommendation or margin')
    total, soft = hand_total(hand)
    return {
        'schema': {'name': 'blackjack-decision', 'version': SCHEMA_VERSION},
        'package': {'name': 'exact-blackjack-solver', 'version': __version__},
        'state': {
            'cards': list(hand), 'dealer_up': up, 'total': total, 'soft': soft,
            'is_split_hand': is_split_hand, 'hand_count': hand_count,
            'shoe': {
                'rank_order': list(RANKS), 'counts': list(unseen),
                'source': 'fresh_minus_visible' if shoe is None else 'supplied_unseen',
                'includes_hidden_hole': True, 'visible_cards_already_removed': True,
            },
        },
        'rules': rule_values,
        'decision': {
            'action': action, 'action_name': ACTION_NAMES[action], 'evs': values,
            'margin': float(margin), 'units': 'original_wager',
            'whole_game_estimate': None,
        },
        'model': _model_record(up),
    }


def decision_json(cards: str | Sequence[CardLike], dealer_up: CardLike,
                  rules: Rules = STANDARD, *, shoe: Shoe | None = None,
                  is_split_hand: bool = False, hand_count: int | None = None) -> str:
    """Serialize a decision record as one JSON object, with no display rounding."""
    return json.dumps(decision_record(cards, dealer_up, rules, shoe=shoe,
                                     is_split_hand=is_split_hand, hand_count=hand_count),
                      indent=2, allow_nan=False)
