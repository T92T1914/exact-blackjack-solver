"""Bounded original-hand S/H/D with a deferred, unpeeked dealer second card.

Retained counts already exclude the visible cards. Each surviving player draw
leaves at least one card for the dealer. A dealer natural loses every committed
wager unit, including a nonnatural player 21 or a doubled wager.
"""
from __future__ import annotations

import math
from numbers import Integral
from time import perf_counter

from . import dealer
from ._enumeration import (MAX_STATES, EnumerationLimitExceeded, scope, state,
                           state_limit)
from .core import (RANK_VALUE, hard_total, hand_total, normalize, normalize_hand,
                   normalize_shoe, remove_card)

MODEL = {'name': 'deferred_second_card_all_wagers_sdh', 'version': 1}
MAX_SECONDS = 10.0
COMPUTATION_METHOD = 'deferred_second_card_request_local_binary64_v1'
CACHE_SCOPE = 'request_local_player_and_dealer'
FAMILIES = frozenset(('deferred_root', 'deferred_player', 'deferred_hit',
                      'deferred_stand', 'deferred_double', 'root_distribution',
                      'root_dealer'))
_PLAYER_FAMILIES = FAMILIES - frozenset(('root_distribution', 'root_dealer'))
_LOW_VALUES = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)


class DeferredTimeLimitExceeded(RuntimeError):
    """A cooperative numerical deadline refused the whole original decision."""

    def __init__(self, work=None):
        super().__init__('whole-request deferred second-card time limit exceeded')
        self.work = work


class UnsupportedContinuation(ValueError):
    """An offered continuation cannot settle with the supplied finite stock."""

    def __init__(self, message, work=None):
        super().__init__(message)
        self.work = work


def time_limit(value):
    if (type(value) not in (int, float) or not 0 < value <= MAX_SECONDS
            or not math.isfinite(value)):
        raise ValueError('max_seconds must be finite, positive and at most 10')
    return float(value)


def validate_rules(rules):
    """Reuse full rule value validation before admitting this restricted family."""
    from .record import _rule_values

    _rule_values(rules)
    if rules.peek or rules.surrender:
        raise ValueError('deferred second-card model requires peek=False and surrender=False')
    if not rules.double_any_two or not rules.tens_are_pairs:
        raise ValueError('deferred second-card model requires any-two-card double '
                         'and collapsed ten-value ranks')
    if rules.max_hands != 1 or rules.resplit_aces or rules.hit_split_aces:
        raise ValueError('deferred second-card model requires max_hands=1, '
                         'resplit_aces=False and hit_split_aces=False')


def validate(hand, rules, unseen, is_split_hand, hand_count, max_states, *,
             can_split=False, max_seconds=MAX_SECONDS):
    """Admit an explicit original two-card decision without pricing any action."""
    state_limit(max_states)
    time_limit(max_seconds)
    validate_rules(rules)
    for name, value in (('is_split_hand', is_split_hand), ('can_split', can_split)):
        if type(value) is not bool:
            raise ValueError(f'{name} must be a boolean')
    if not isinstance(hand_count, Integral) or isinstance(hand_count, bool):
        raise ValueError('hand_count must be an integer')
    if is_split_hand or hand_count != 1 or can_split:
        raise ValueError('deferred second-card model requires one original unsplit hand '
                         'and can_split=False')
    cards = normalize_hand(hand)
    if len(cards) != 2 or hand_total(cards)[0] >= 21:
        raise ValueError('deferred second-card model requires two nonnatural cards below 21')
    counts = normalize_shoe(unseen)
    if not 1 <= sum(counts) <= 20:
        raise ValueError('deferred second-card model requires 1 to 20 retained unseen cards')


def model_record(up, max_states, max_seconds):
    """Declare the dealer timing, wager loss, finite stock and numerical limits."""
    normalize(up)
    return {
        **MODEL, 'dealer_information': 'deferred_unpeeked_second_card',
        'hole_rank_excluded_by_peek': None, 'ten_value_ranks': 'collapsed_to_T',
        'insurance_priced': False,
        'hit_stand_double': 'finite_enumeration_binary_floating_point',
        'initial_natural': 'excluded',
        'dealer_natural': 'lose_all_committed_wager_units',
        'player_last_draw': 'leave_one_card_then_force_stand',
        'dealer_last_draw': 'consume_if_terminal_otherwise_refuse_required_next_draw',
        'split': 'not_supported',
        'continuation_exhaustion': 'refuse_whole_original_decision',
        'retained_cards_min': 1, 'retained_cards_max': 20,
        'enumeration_state_limit': state_limit(max_states),
        'enumeration_seconds_limit': time_limit(max_seconds),
        'computation_method': COMPUTATION_METHOD, 'cache_scope': CACHE_SCOPE,
    }


def rank(values):
    """Rank raw floats in S/H/D tie order, with no runner-up for a sole S."""
    ordered = sorted(((action, values[action]) for action in ('S', 'H', 'D')
                      if action in values), key=lambda item: item[1], reverse=True)
    action, best = ordered[0]
    return action, best - ordered[1][1] if len(ordered) > 1 else None


def _total(low, has_ace):
    return low + 10 if has_ace and low + 10 <= 21 else low


class _Request:
    """Own player and dealer memo tables for exactly one admitted calculation."""

    def __init__(self, hand, up, unseen, rules, can_double, max_seconds, started):
        self.low = hard_total(hand)
        self.has_ace = any(RANK_VALUE[rank] == 11 for rank in hand)
        self.up = up
        self.unseen = unseen
        self.s17 = rules.s17
        self.can_double = can_double
        self.max_seconds = max_seconds
        self.started = started
        self.caches = {family: {} for family in _PLAYER_FAMILIES}
        self.dealer = dealer._request_local_cache(self.check_deadline)
        self.retired = False

    def elapsed(self):
        return perf_counter() - self.started

    def check_deadline(self, elapsed=None):
        if (self.elapsed() if elapsed is None else elapsed) > self.max_seconds:
            raise DeferredTimeLimitExceeded()

    def memo(self, family, key, body):
        self.check_deadline()
        cache = self.caches[family]
        if key in cache:
            return cache[key]
        state(family)
        value = body()
        cache[key] = value
        return value

    def retire(self):
        if self.retired:
            return
        for cache in self.caches.values():
            cache.clear()
        self.dealer.clear()
        self.retired = True

    def work(self, budget, elapsed=None):
        return {
            **budget.snapshot(), 'max_seconds': self.max_seconds,
            'elapsed_seconds': self.elapsed() if elapsed is None else elapsed,
            'computation_method': COMPUTATION_METHOD, 'cache_scope': CACHE_SCOPE,
            'cache_retired': self.retired,
        }

    def stand(self, total, counts, wager):
        return self.memo('deferred_stand', (total, counts, wager),
                         lambda: self._stand(total, counts, wager))

    def _stand(self, total, counts, wager):
        if total > 21:
            return -float(wager)
        try:
            probabilities = self.dealer.distribution(self.up, counts, self.s17, False)
        except ValueError as exc:
            raise UnsupportedContinuation(str(exc)) from exc
        contributions = []
        for outcome, probability in zip(dealer.OUTCOMES, probabilities, strict=True):
            if outcome == 'BJ':
                payoff = -wager
            elif outcome == 'BUST':
                payoff = wager
            else:
                payoff = wager * ((total > outcome) - (total < outcome))
            contributions.append(probability * payoff)
        return math.fsum(contributions)

    def player(self, low, has_ace, counts):
        return self.memo('deferred_player', (low, has_ace, counts),
                         lambda: self._player(low, has_ace, counts))

    def _player(self, low, has_ace, counts):
        total = _total(low, has_ace)
        if total > 21:
            return -1.0
        stand = self.stand(total, counts, 1)
        if total == 21 or sum(counts) < 2:
            return stand
        hit = self.hit(low, has_ace, counts)
        return max(stand, hit)

    def hit(self, low, has_ace, counts):
        return self.memo('deferred_hit', (low, has_ace, counts),
                         lambda: self._hit(low, has_ace, counts))

    def _hit(self, low, has_ace, counts):
        n = sum(counts)
        contributions = []
        for index, count in enumerate(counts):
            if count:
                future = self.player(low + _LOW_VALUES[index], has_ace or index == 0,
                                     remove_card(counts, index))
                contributions.append((count / n) * future)
        return math.fsum(contributions)

    def double(self, low, has_ace, counts):
        return self.memo('deferred_double', (low, has_ace, counts),
                         lambda: self._double(low, has_ace, counts))

    def _double(self, low, has_ace, counts):
        n = sum(counts)
        contributions = []
        for index, count in enumerate(counts):
            if count:
                total = _total(low + _LOW_VALUES[index], has_ace or index == 0)
                future = (-2.0 if total > 21 else
                          self.stand(total, remove_card(counts, index), 2))
                contributions.append((count / n) * future)
        return math.fsum(contributions)

    def root(self):
        return self.memo('deferred_root', (), self._root)

    def _root(self):
        total = _total(self.low, self.has_ace)
        actions = [('S', self.stand(total, self.unseen, 1))]
        if sum(self.unseen) >= 2:
            actions.append(('H', self.hit(self.low, self.has_ace, self.unseen)))
            if self.can_double:
                actions.append(('D', self.double(self.low, self.has_ace, self.unseen)))
        return tuple(actions)


def decide(hand, up, unseen, rules, *, can_double=True, can_split=False,
           max_states=MAX_STATES, max_seconds=MAX_SECONDS):
    """Return a complete original S/H/D decision or a whole-decision refusal.

    Limits are cooperative and cover admission through result assembly. This
    direct numerical call does not acquire the supervised process owner.
    """
    started = perf_counter()
    if type(can_double) is not bool:
        raise ValueError('can_double must be a boolean')
    hand, up, unseen = normalize_hand(hand), normalize(up), normalize_shoe(unseen)
    validate(hand, rules, unseen, False, 1, max_states,
             can_split=can_split, max_seconds=max_seconds)
    request = _Request(hand, up, unseen, rules, can_double, time_limit(max_seconds), started)
    with scope(max_states, deadline_check=request.check_deadline) as budget:
        try:
            values = dict(request.root())
            action, margin = rank(values)
            request.retire()
            work = request.work(budget, elapsed=0.0)
            result = action, values, margin, work
            elapsed = request.elapsed()
            request.check_deadline(elapsed)
            work['elapsed_seconds'] = elapsed
            return result
        except EnumerationLimitExceeded as exc:
            request.retire()
            raise EnumerationLimitExceeded(request.work(budget)) from exc
        except (DeferredTimeLimitExceeded, UnsupportedContinuation) as exc:
            request.retire()
            exc.work = request.work(budget)
            raise
        finally:
            request.retire()
