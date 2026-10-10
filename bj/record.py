"""Portable records for one completed solver call, without display rounding.

The record owns normalized copies of the visible cards, remaining rank counts
and rules. Ordinary records retain the existing post-peek game. Explicit
bounded records identify their two-hand, non-ace resplit, ace resplit or
late-surrender model.
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

__all__ = ['SCHEMA_VERSION', 'CONTROLLED_SCHEMA_VERSION', 'COMMON_SCHEMA_VERSION',
           'SURRENDER_SCHEMA_VERSION', 'RESPLIT_SCHEMA_VERSION', 'ACE_RESPLIT_SCHEMA_VERSION',
           'decision_record',
           'decision_json', 'common_shoe_record', 'late_surrender_record',
           'bounded_resplit_record', 'bounded_ace_resplit_record']

SCHEMA_VERSION = 1
CONTROLLED_SCHEMA_VERSION = 2
COMMON_SCHEMA_VERSION = 3
SURRENDER_SCHEMA_VERSION = 4
RESPLIT_SCHEMA_VERSION = 5
ACE_RESPLIT_SCHEMA_VERSION = 6


class _UnsupportedRules(ValueError):
    """Well-typed rules outside the decision record's declared model."""


def _rule_values(rules: Rules) -> dict[str, Any]:
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
    return values


def _rules_record(rules: Rules) -> dict[str, Any]:
    values = _rule_values(rules)
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


def _surrender_rules_record(rules: Rules) -> dict[str, Any]:
    from .late_surrender import validate_rules

    values = _rule_values(rules)
    try:
        validate_rules(rules)
    except ValueError as exc:
        raise _UnsupportedRules(str(exc)) from exc
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


def _common_model_record(up, max_states):
    from .common_shoe import SPLIT_MODEL
    from ._enumeration import state_limit

    return {**_model_record(up), 'split': SPLIT_MODEL, 'split_hands': 2,
            'split_deal_order': 'finish_first_before_dealing_second',
            'split_aces': 'one_card_no_double_no_natural_premium',
            'split_exhaustion': 'refuse_any_unavailable_continuation',
            'enumeration_state_limit': state_limit(max_states)}


def _surrender_model_record(up, max_states):
    from .late_surrender import model_record

    return model_record(up, max_states)


def _resplit_model_record(up, max_states):
    from .bounded_resplit import model_record

    return model_record(up, max_states)


def _ace_resplit_model_record(up, max_states):
    from .bounded_ace_resplit import model_record

    return model_record(up, max_states)


def decision_record(cards: str | Sequence[CardLike], dealer_up: CardLike,
                    rules: Rules = STANDARD, *, shoe: Shoe | None = None,
                    is_split_hand: bool = False,
                    hand_count: int | None = None, can_double: bool = True,
                    can_split: bool = True) -> dict[str, Any]:
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
    False controls remove only the current double or split alternative. They
    produce schema version 2, without changing continuation rules or policy.
    """
    for name, value in (('can_double', can_double), ('can_split', can_split)):
        if not isinstance(value, bool):
            raise ValueError(f'{name} must be a boolean')
    rule_values = _rules_record(rules)
    hand, up, unseen, hand_count = _record_inputs(
        cards, dealer_up, rules, shoe, is_split_hand, hand_count)
    action, evs, margin = best_action(hand, up, shoe=unseen, rules=rules,
                                    is_split_hand=is_split_hand, hand_count=hand_count,
                                    can_double=can_double, can_split=can_split)
    version = SCHEMA_VERSION if can_double and can_split else CONTROLLED_SCHEMA_VERSION
    return _decision_document(hand, up, unseen, rule_values, is_split_hand, hand_count,
                              can_double, can_split, action, evs, margin, version,
                              _model_record(up), shoe is None)


def _decision_document(hand, up, unseen, rule_values, is_split_hand, hand_count,
                       can_double, can_split, action, evs, margin, version, model, fresh,
                       *, action_names=ACTION_NAMES, can_surrender=None):
    """Assemble the shared numerical record without calculating another answer."""
    if not evs or action not in evs or any(key not in action_names for key in evs):
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
        'schema': {'name': 'blackjack-decision', 'version': version},
        'package': {'name': 'exact-blackjack-solver', 'version': __version__},
        'state': {
            'cards': list(hand), 'dealer_up': up, 'total': total, 'soft': soft,
            'is_split_hand': is_split_hand, 'hand_count': hand_count,
            **({} if version == SCHEMA_VERSION else {
                'action_controls': {'can_double': can_double, 'can_split': can_split,
                                    **({} if can_surrender is None else {
                                        'can_surrender': can_surrender})}}),
            'shoe': {
                'rank_order': list(RANKS), 'counts': list(unseen),
                'source': 'fresh_minus_visible' if fresh else 'supplied_unseen',
                'includes_hidden_hole': True, 'visible_cards_already_removed': True,
            },
        },
        'rules': rule_values,
        'decision': {
            'action': action, 'action_name': action_names[action], 'evs': values,
            'margin': float(margin), 'units': 'original_wager',
            'whole_game_estimate': None,
        },
        'model': model,
    }


def _common_shoe_record(cards, dealer_up, rules, *, shoe, can_double=True,
                        can_split=True, max_states=100_000):
    from . import common_shoe

    if shoe is None:
        raise ValueError('common-shoe records require explicit retained unseen counts')
    for name, value in (('can_double', can_double), ('can_split', can_split)):
        if type(value) is not bool:
            raise ValueError(f'{name} must be a boolean')
    rule_values = _rules_record(rules)
    hand, up, unseen, hand_count = _record_inputs(cards, dealer_up, rules, shoe, False, 1)
    common_shoe.validate(hand, rules, unseen, False, hand_count, max_states)
    action, evs, margin, work = common_shoe.decide(
        hand, up, unseen, rules, can_double=can_double, can_split=can_split,
        max_states=max_states)
    document = _decision_document(hand, up, unseen, rule_values, False, hand_count,
                                  can_double, can_split, action, evs, margin,
                                  COMMON_SCHEMA_VERSION, _common_model_record(up, max_states),
                                  False)
    return document, work


def common_shoe_record(cards: str | Sequence[CardLike], dealer_up: CardLike,
                       rules: Rules = STANDARD, *, shoe: Shoe,
                       can_double: bool = True, can_split: bool = True,
                       max_states: int = 100_000) -> dict[str, Any]:
    """Record an explicit initial-pair common-shoe decision within its finite cap.

    This additive model requires two sequential hands, no resplits, one-card
    split aces and 3..20 supplied unseen cards. Counts include the hidden hole
    and already exclude visible cards. All root and joint uncached states
    share max_states. A refused branch or budget produces no partial record.
    Ordinary decision_record retains its existing approximate split model.
    """
    return _common_shoe_record(cards, dealer_up, rules, shoe=shoe,
                               can_double=can_double, can_split=can_split,
                               max_states=max_states)[0]


def _late_surrender_record(cards, dealer_up, rules, *, shoe, can_double=True,
                           can_surrender=True, max_states=100_000):
    from . import late_surrender

    if shoe is None:
        raise ValueError('late-surrender records require explicit retained unseen counts')
    for name, value in (('can_double', can_double), ('can_surrender', can_surrender)):
        if type(value) is not bool:
            raise ValueError(f'{name} must be a boolean')
    rule_values = _surrender_rules_record(rules)
    hand, up, unseen, hand_count = _record_inputs(cards, dealer_up, rules, shoe, False, 1)
    late_surrender.validate(hand, rules, unseen, False, hand_count, max_states)
    action, evs, margin, work = late_surrender.decide(
        hand, up, unseen, rules, can_double=can_double, can_surrender=can_surrender,
        max_states=max_states)
    document = _decision_document(
        hand, up, unseen, rule_values, False, hand_count, can_double, False,
        action, evs, margin, SURRENDER_SCHEMA_VERSION, _surrender_model_record(up, max_states),
        False, action_names=late_surrender.ACTION_NAMES, can_surrender=can_surrender)
    return document, work


def late_surrender_record(cards: str | Sequence[CardLike], dealer_up: CardLike,
                          rules: Rules, *, shoe: Shoe, can_double: bool = True,
                          can_surrender: bool = True,
                          max_states: int = 100_000) -> dict[str, Any]:
    """Record one explicitly selected initial post-peek late-surrender decision.

    Require surrender=True, one original two-card hand below 21, no split and
    3..20 retained unseen cards including the hole. All offered S/H/D values
    finish before adding the optional terminal R=-0.5. Any failure withholds
    the whole record. Current controls do not change later hit/stand policy.
    The direct call has a state cap, without an owned wall or memory supervisor.
    """
    return _late_surrender_record(cards, dealer_up, rules, shoe=shoe,
                                  can_double=can_double, can_surrender=can_surrender,
                                  max_states=max_states)[0]


def _bounded_resplit_record(cards, dealer_up, rules, *, shoe, can_double=True,
                            can_split=True, max_states=100_000):
    from . import bounded_resplit

    if shoe is None:
        raise ValueError('bounded-resplit records require explicit retained unseen counts')
    for name, value in (('can_double', can_double), ('can_split', can_split)):
        if type(value) is not bool:
            raise ValueError(f'{name} must be a boolean')
    rule_values = _rules_record(rules)
    hand, up, unseen, hand_count = _record_inputs(cards, dealer_up, rules, shoe, False, 1)
    bounded_resplit.validate(hand, rules, unseen, False, hand_count, max_states)
    action, evs, margin, work = bounded_resplit.decide(
        hand, up, unseen, rules, can_double=can_double, can_split=can_split,
        max_states=max_states)
    document = _decision_document(hand, up, unseen, rule_values, False, hand_count,
                                  can_double, can_split, action, evs, margin,
                                  RESPLIT_SCHEMA_VERSION, _resplit_model_record(up, max_states),
                                  False)
    return document, work


def bounded_resplit_record(cards: str | Sequence[CardLike], dealer_up: CardLike,
                           rules: Rules, *, shoe: Shoe, can_double: bool = True,
                           can_split: bool = True,
                           max_states: int = 100_000) -> dict[str, Any]:
    """Record a bounded original non-ace pair with one extra common-shoe resplit.

    Require max_hands=3 and 3..20 supplied counts including the concealed hole.
    New children precede older pending hands. Complete combined S/H/D/P pricing
    shares one state cap and refuses any unavailable joint continuation. Root
    S/H/D retains its accepted last-draw convention. Direct use has no owned wall
    or memory supervisor, and split continuation has a ten-second deadline.
    """
    return _bounded_resplit_record(cards, dealer_up, rules, shoe=shoe,
                                   can_double=can_double, can_split=can_split,
                                   max_states=max_states)[0]


def _bounded_ace_resplit_record(cards, dealer_up, rules, *, shoe, can_double=True,
                                can_split=True, max_states=100_000):
    from . import bounded_ace_resplit

    if shoe is None:
        raise ValueError('bounded-ace-resplit records require explicit retained unseen counts')
    for name, value in (('can_double', can_double), ('can_split', can_split)):
        if type(value) is not bool:
            raise ValueError(f'{name} must be a boolean')
    rule_values = _rules_record(rules)
    hand, up, unseen, hand_count = _record_inputs(cards, dealer_up, rules, shoe, False, 1)
    bounded_ace_resplit.validate(hand, rules, unseen, False, hand_count, max_states)
    action, evs, margin, work = bounded_ace_resplit.decide(
        hand, up, unseen, rules, can_double=can_double, can_split=can_split,
        max_states=max_states)
    document = _decision_document(
        hand, up, unseen, rule_values, False, hand_count, can_double, can_split,
        action, evs, margin, ACE_RESPLIT_SCHEMA_VERSION, _ace_resplit_model_record(up, max_states),
        False)
    return document, work


def bounded_ace_resplit_record(cards: str | Sequence[CardLike], dealer_up: CardLike,
                               rules: Rules, *, shoe: Shoe, can_double: bool = True,
                               can_split: bool = True,
                               max_states: int = 100_000) -> dict[str, Any]:
    """Record original A,A with at most three one-card common-shoe ace hands.

    Require max_hands=3, resplit_aces=True, hit_split_aces=False and 3..20 supplied
    counts including the concealed hole. An eligible child may stand or spend
    the round's single extra resplit slot. Every offered original S/H/D/P value
    completes under one state cap. Any unavailable continuation withholds the
    whole record. Root S/H/D retains the accepted last-draw convention. Direct
    use has no owned wall or memory supervisor; joint work is cooperative up to
    ten seconds. Successful values are unrounded binary floating point.
    """
    return _bounded_ace_resplit_record(cards, dealer_up, rules, shoe=shoe,
                                       can_double=can_double, can_split=can_split,
                                       max_states=max_states)[0]


def decision_json(cards: str | Sequence[CardLike], dealer_up: CardLike,
                  rules: Rules = STANDARD, *, shoe: Shoe | None = None,
                  is_split_hand: bool = False, hand_count: int | None = None,
                  can_double: bool = True, can_split: bool = True) -> str:
    """Serialize a decision record as one JSON object, with no display rounding."""
    return json.dumps(decision_record(cards, dealer_up, rules, shoe=shoe,
                                     is_split_hand=is_split_hand, hand_count=hand_count,
                                     can_double=can_double, can_split=can_split),
                      indent=2, allow_nan=False)
