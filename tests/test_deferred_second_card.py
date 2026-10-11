"""Frozen physical-card witnesses and numerical ownership for deferred S/H/D.

The Fraction maps were qualified before this public implementation. Their
exact ties remain separate from the candidate's raw binary64 recommendation.
Local/global dealer parity checks cover reuse, not independent mathematics.
"""
from __future__ import annotations

import math
from dataclasses import replace
from fractions import Fraction
from unittest.mock import Mock, patch

import pytest

from bj import dealer, deferred_second_card as model
from bj._enumeration import FAMILIES as LEGACY_FAMILIES
from bj._enumeration import EnumerationLimitExceeded, scope, state
from bj.core import RANKS, STANDARD


def counts(cards):
    return tuple(cards.count(rank) for rank in RANKS)


def rules(**changes):
    return replace(STANDARD, **{'peek': False, 'max_hands': 1, **changes})


def assert_work(work, *, complete):
    assert set(work) == {
        'limit', 'states', 'attempted_states', 'state_counts', 'max_seconds',
        'elapsed_seconds', 'computation_method', 'cache_scope', 'cache_retired',
    }
    assert work['computation_method'] == 'deferred_second_card_request_local_binary64_v1'
    assert work['cache_scope'] == 'request_local_player_and_dealer'
    assert work['cache_retired'] is True
    assert 0 <= work['states'] <= work['limit'] <= 100000
    assert work['states'] == sum(work['state_counts'].values())
    assert set(work['state_counts']) <= model.FAMILIES
    assert all(type(value) is int and value > 0 for value in work['state_counts'].values())
    assert work['attempted_states'] - work['states'] in ((0,) if complete else (0, 1))
    assert math.isfinite(work['elapsed_seconds']) and work['elapsed_seconds'] >= 0
    if complete:
        assert work['elapsed_seconds'] <= work['max_seconds']


# Each tuple is cards, upcard, retained cards, S17, initial double permission,
# and the complete independent Fraction map. None of these values was selected
# from this public implementation's output.
MANUAL_CASES = [
    (('9', '2'), 'T', ('A', 'T', 'T'), True, True,
     {'S': '-1', 'H': '-1/3', 'D': '-2/3'}),
    (('T', '6'), 'T', ('A', '5', 'T'), True, True,
     {'S': '-1/3', 'H': '-1/3', 'D': '-2/3'}),
    (('T', '8'), '6', ('A', '4', 'T'), True, True,
     {'S': '0', 'H': '-1', 'D': '-2'}),
    (('T', '8'), '6', ('A', '4', 'T'), False, True,
     {'S': '-1/3', 'H': '-1', 'D': '-2'}),
    (('9', '2'), 'T', ('T', 'T'), True, True,
     {'S': '-1', 'H': '1', 'D': '2'}),
    (('9', '2'), 'T', ('A',), True, True, {'S': '-1'}),
    (('A', '6'), 'A', ('6', 'T', 'T'), True, True,
     {'S': '-2/3', 'H': '-2/3', 'D': '-4/3'}),
    (('2', '2'), 'A', ('7', '8', '9', 'T'), True, True,
     {'S': '-1', 'H': '-1/3', 'D': '-2'}),
    (('2', '2'), 'A', ('7', '8', '9', 'T'), True, False,
     {'S': '-1', 'H': '-1/3'}),
    (('2', '2'), 'T', ('7', '8', 'T'), True, True,
     {'S': '-1', 'H': '-1/3', 'D': '-2'}),
    (('9', '2'), 'A', ('9', '9', 'T'), True, True,
     {'S': '-1', 'H': '0', 'D': '0'}),
    (('9', '2'), '9', ('2', 'T', 'T'), True, True,
     {'S': '-1', 'H': '0', 'D': '0'}),
    (('T', '6'), '6', ('5', '5', 'T'), True, True,
     {'S': '-1/3', 'H': '-1/3', 'D': '-2/3'}),
    (('2', '2'), 'T', ('2', '5', 'T', 'T'), True, True,
     {'S': '-1/3', 'H': '0', 'D': '-2/3'}),
    (('2', '2'), 'T', ('2', '8', 'T', 'T'), True, True,
     {'S': '-2/3', 'H': '-2/3', 'D': '-4/3'}),
]


@pytest.mark.parametrize('hand,up,retained,s17,double,expected', MANUAL_CASES)
def test_frozen_complete_fraction_maps(hand, up, retained, s17, double, expected):
    action, values, margin, work = model.decide(
        hand, up, counts(retained), rules(s17=s17), can_double=double)
    assert list(values) == list(expected)
    for offered, exact in expected.items():
        assert values[offered] == pytest.approx(float(Fraction(exact)), abs=1e-12, rel=0)
    ranked = sorted(values, key=values.get, reverse=True)
    assert action == ranked[0]
    assert margin == (values[ranked[0]] - values[ranked[1]] if len(ranked) > 1 else None)
    assert_work(work, complete=True)


def test_later_hit_choices_are_useful_and_double_is_not_twice_hit():
    _, values, _, work = model.decide(
        ('2', '2'), 'A', counts(('7', '8', '9', 'T')), rules())
    assert values['H'] == pytest.approx(-1 / 3, abs=1e-12, rel=0)
    assert values['D'] == -2.0 and values['D'] != 2 * values['H']
    assert work['state_counts']['deferred_player'] > 1
    assert work['state_counts']['deferred_hit'] > 1


def test_dealer_natural_takes_both_doubled_units_and_no_ordinary_21_premium():
    _, values, _, _ = model.decide(
        ('9', '2'), 'T', counts(('A', 'T', 'T')), rules())
    assert values == pytest.approx({'S': -1, 'H': -1 / 3, 'D': -2 / 3}, abs=1e-12, rel=0)
    assert values['D'] != pytest.approx(-1 / 3, abs=1e-12, rel=0)


def test_hidden_information_value_does_not_become_known_second_card_policy():
    _, values, _, _ = model.decide(
        ('T', '6'), 'T', counts(('A', '5', 'T')), rules())
    # The independent revealed-card control's policy value is 0, while both
    # lawful S/H values are -1/3. Tolerant agreement cannot recover a raw tie.
    assert max(values.values()) == pytest.approx(-1 / 3, abs=1e-12, rel=0)
    assert max(values.values()) < -0.1


@pytest.mark.parametrize('double', (False, True))
def test_sole_stand_certain_future_natural_is_admitted_with_null_margin(double):
    action, values, margin, work = model.decide(
        ('9', '2'), 'T', counts(('A',)), rules(), can_double=double)
    assert (action, values, margin) == ('S', {'S': -1.0}, None)
    assert not {'deferred_hit', 'deferred_double', 'deferred_player'} & set(work['state_counts'])
    assert_work(work, complete=True)


def test_last_player_draw_leaves_dealer_second_and_dealer_final_card_can_settle():
    action, values, margin, _ = model.decide(
        ('9', '2'), 'T', counts(('T', 'T')), rules())
    assert (action, values, margin) == ('D', {'S': -1.0, 'H': 1.0, 'D': 2.0}, 1.0)
    local = dealer._request_local_cache(lambda: None)
    try:
        assert local.resolve(16, False, counts(('T',)), True) == (
            0.0, 0.0, 0.0, 0.0, 0.0, 1.0)
        with pytest.raises(ValueError, match='shoe is empty'):
            local.resolve(12, False, counts(('2',)), True)
    finally:
        local.clear()


def test_raw_rank_ties_and_one_ulp_difference_remain_distinct():
    assert model.rank({'D': 2.0, 'H': 2.0, 'S': 2.0}) == ('S', 0.0)
    greater = math.nextafter(2.0, math.inf)
    assert model.rank({'S': 2.0, 'H': greater, 'D': 1.0}) == ('H', greater - 2.0)
    assert model.rank({'S': -1.0}) == ('S', None)


@pytest.mark.parametrize('changes', [
    {'peek': True}, {'surrender': True}, {'max_hands': 2}, {'resplit_aces': True},
    {'hit_split_aces': True}, {'double_any_two': False}, {'tens_are_pairs': False},
    {'s17': 1}, {'das': 'yes'}, {'decks': True}, {'insurance_payout': math.nan},
])
def test_unqualified_rules_refuse_before_pricing(changes):
    with patch.object(model, '_Request', side_effect=AssertionError('pricing')):
        with pytest.raises(ValueError):
            model.decide(('9', '2'), 'T', counts(('T', 'T')), rules(**changes))


@pytest.mark.parametrize('hand', [('A', 'T'), ('9',), ('2', '2', '2')])
def test_only_original_two_card_nonnatural_hand_is_admitted(hand):
    with patch.object(model, '_Request', side_effect=AssertionError('pricing')):
        with pytest.raises(ValueError, match='two nonnatural cards below 21'):
            model.decide(hand, 'T', counts(('T', 'T')), rules())


@pytest.mark.parametrize('kwargs', [
    {'can_double': 1}, {'can_split': True}, {'can_split': 0}, {'max_states': True},
    {'max_states': 0}, {'max_states': 100001}, {'max_states': 1.0},
    {'max_seconds': False}, {'max_seconds': 0}, {'max_seconds': -1},
    {'max_seconds': 10.1}, {'max_seconds': math.inf}, {'max_seconds': math.nan},
    {'max_seconds': 10 ** 400},
])
def test_controls_and_numeric_limits_refuse_before_pricing(kwargs):
    with patch.object(model, '_Request', side_effect=AssertionError('pricing')):
        with pytest.raises(ValueError):
            model.decide(('9', '2'), 'T', counts(('T', 'T')), rules(), **kwargs)


@pytest.mark.parametrize('retained', [(), ('T',) * 21])
def test_retained_stock_envelope_refuses_before_pricing(retained):
    with patch.object(model, '_Request', side_effect=AssertionError('pricing')):
        with pytest.raises(ValueError, match='1 to 20'):
            model.decide(('9', '2'), 'T', counts(retained), rules())


@pytest.mark.parametrize('split_hand,hand_count', [(True, 1), (False, 2), (False, True)])
def test_original_hand_admission_does_not_allow_split_metadata(split_hand, hand_count):
    with pytest.raises(ValueError):
        model.validate(('9', '2'), rules(), counts(('T', 'T')),
                       split_hand, hand_count, 100000)


def test_alias_normalization_does_not_subtract_visible_cards_or_mutate_counts():
    retained = list(counts(('T', 'T')))
    original = retained.copy()
    result = model.decide(('9', 2), 'K', retained, rules())
    assert result[:3] == ('D', {'S': -1.0, 'H': 1.0, 'D': 2.0}, 1.0)
    assert retained == original


def test_inactive_rule_context_does_not_price_extra_products():
    retained = counts(('A', 'T', 'T'))
    first = model.decide(('9', '2'), 'T', retained, rules())[:3]
    changed = rules(decks=1, das=False, blackjack_payout=8, insurance_payout=0)
    assert model.decide(('9', '2'), 'T', retained, changed)[:3] == first


@pytest.mark.parametrize('hand,up,retained', [
    (('9', '2'), '2', ('2', '3', '4')),
    (('9', '2'), 'T', ('6', 'T')),
    (('2', '2'), 'T', ('5', '6', 'T')),
])
def test_required_or_nonchosen_dealer_exhaustion_refuses_whole_decision(hand, up, retained):
    with pytest.raises(model.UnsupportedContinuation, match='shoe is empty') as caught:
        model.decide(hand, up, counts(retained), rules())
    assert_work(caught.value.work, complete=False)
    assert not {'action', 'values', 'evs', 'margin'} & vars(caught.value).keys()


def test_cap_refusal_counts_first_unentered_body_and_retains_no_action_map():
    with pytest.raises(EnumerationLimitExceeded) as caught:
        model.decide(('9', '2'), 'T', counts(('T', 'T')), rules(), max_states=1)
    work = caught.value.work
    assert (work['states'], work['attempted_states'], work['state_counts']) == (
        1, 2, {'deferred_root': 1})
    assert_work(work, complete=False)
    assert not {'action', 'values', 'evs', 'margin'} & vars(caught.value).keys()


@pytest.mark.parametrize('samples,states,attempts', [
    ([0.0, 2.0, 2.0], 0, 0),
    ([0.0, 0.0, 2.0, 2.0], 0, 1),
])
def test_deadline_before_entry_and_on_scoped_entry(samples, states, attempts):
    with patch.object(model, 'perf_counter', side_effect=samples):
        with pytest.raises(model.DeferredTimeLimitExceeded) as caught:
            model.decide(('9', '2'), 'T', counts(('T', 'T')), rules(), max_seconds=1)
    work = caught.value.work
    assert (work['states'], work['attempted_states']) == (states, attempts)
    assert work['elapsed_seconds'] == 2.0
    assert_work(work, complete=False)
    assert not {'action', 'values', 'evs', 'margin'} & vars(caught.value).keys()


def test_deadline_after_numeric_ranking_withholds_an_otherwise_complete_result():
    real_rank = model.rank
    clock = Mock(return_value=0.0)

    def finishing_rank(values):
        result = real_rank(values)
        clock.return_value = 2.0
        return result

    with patch.object(model, 'perf_counter', clock), patch.object(model, 'rank', finishing_rank):
        with pytest.raises(model.DeferredTimeLimitExceeded) as caught:
            model.decide(('9', '2'), 'T', counts(('T', 'T')), rules(), max_seconds=1)
    assert caught.value.work['states'] > 0
    assert caught.value.work['elapsed_seconds'] == 2.0
    assert_work(caught.value.work, complete=False)
    assert not {'action', 'values', 'evs', 'margin'} & vars(caught.value).keys()


def test_success_reports_the_same_final_sample_that_was_checked():
    phase = {'ranked': False, 'final_samples': 0}
    real_rank = model.rank

    def clock():
        if not phase['ranked']:
            return 0.0
        phase['final_samples'] += 1
        return 0.75 if phase['final_samples'] == 1 else 2.0

    def finishing_rank(values):
        result = real_rank(values)
        phase['ranked'] = True
        return result

    with patch.object(model, 'perf_counter', clock), patch.object(model, 'rank', finishing_rank):
        result = model.decide(('9', '2'), 'T', counts(('T', 'T')), rules(), max_seconds=1)
    assert result[3]['elapsed_seconds'] == 0.75 and phase['final_samples'] == 1
    assert_work(result[3], complete=True)


def test_player_and_dealer_cache_hits_still_check_deadline():
    with patch.object(model, 'perf_counter', return_value=0.0) as clock:
        request = model._Request(('9', '2'), 'T', counts(('T', 'T')), rules(), True, 1, 0)
        with scope(100000, deadline_check=request.check_deadline) as budget:
            try:
                assert request.stand(11, request.unseen, 1) == -1.0
                before = budget.snapshot()
                clock.return_value = 2.0
                with pytest.raises(model.DeferredTimeLimitExceeded):
                    request.stand(11, request.unseen, 1)
                with pytest.raises(model.DeferredTimeLimitExceeded):
                    request.dealer.distribution('T', request.unseen, True, False)
                assert budget.snapshot() == before
            finally:
                request.retire()
        assert request.retired and not any(request.caches.values())
        assert all(info.currsize == 0 for info in request.dealer.cache_info())


@pytest.mark.parametrize('outcome', ('completed', 'cap', 'exhausted'))
def test_each_request_retires_real_local_tables_and_can_be_followed_by_success(outcome):
    created = []
    real_request = model._Request

    def capture(*args, **kwargs):
        request = real_request(*args, **kwargs)
        created.append(request)
        return request

    retained = counts(('6', 'T')) if outcome == 'exhausted' else counts(('T', 'T'))
    with patch.object(model, '_Request', side_effect=capture):
        if outcome == 'completed':
            model.decide(('9', '2'), 'T', retained, rules())
        else:
            error = EnumerationLimitExceeded if outcome == 'cap' else model.UnsupportedContinuation
            with pytest.raises(error):
                model.decide(('9', '2'), 'T', retained, rules(),
                             max_states=1 if outcome == 'cap' else 100000)
        assert model.decide(('9', '2'), 'T', counts(('T', 'T')), rules())[0] == 'D'
    assert len(created) == 2
    for request in created:
        assert request.retired and not any(request.caches.values())
        assert all(info.currsize == 0 for info in request.dealer.cache_info())


@pytest.mark.parametrize('up,retained,s17,peek', [
    ('T', ('A', 'T', 'T'), True, False),
    ('T', ('A', 'T', 'T'), True, True),
    ('6', ('A', '4', 'T'), True, False),
    ('6', ('A', '4', 'T'), False, False),
    ('A', ('A', 'T', 'T'), True, False),
])
def test_local_dealer_matches_global_float_vector_without_touching_global_caches(
        up, retained, s17, peek):
    shoe = counts(retained)
    expected = dealer._distribution(up, shoe, s17, peek)
    before = dealer._resolve.cache_info(), dealer._distribution.cache_info()
    local = dealer._request_local_cache(lambda: None)
    try:
        with scope(100000) as budget:
            assert local.distribution(up, shoe, s17, peek) == expected
            cold = budget.snapshot()
            assert local.distribution(up, shoe, s17, peek) == expected
            assert budget.snapshot() == cold
            assert set(cold['state_counts']) <= {'root_dealer', 'root_distribution'}
    finally:
        local.clear()
    assert (dealer._resolve.cache_info(), dealer._distribution.cache_info()) == before
    assert all(info.currsize == 0 for info in local.cache_info())


def test_public_decision_neither_reads_nor_clears_legacy_dealer_caches():
    dealer._distribution('6', counts(('A', '4', 'T')), True, False)
    before = dealer._resolve.cache_info(), dealer._distribution.cache_info()
    first = model.decide(('T', '8'), '6', counts(('A', '4', 'T')), rules())
    second = model.decide(('T', '8'), '6', counts(('A', '4', 'T')), rules())
    assert first[:3] == second[:3]
    assert first[3]['state_counts'] == second[3]['state_counts']
    assert (dealer._resolve.cache_info(), dealer._distribution.cache_info()) == before


def test_legacy_scope_and_cap_keep_their_original_families_and_four_field_work():
    assert LEGACY_FAMILIES == frozenset((
        'root_draw', 'root_hit', 'root_double', 'root_distribution', 'root_dealer',
        'joint_draw', 'joint_play', 'joint_settle', 'joint_dealer'))
    with scope(1) as budget:
        state('root_draw')
        with pytest.raises(EnumerationLimitExceeded) as caught:
            state('root_hit')
    assert caught.value.work == budget.snapshot() == {
        'limit': 1, 'states': 1, 'attempted_states': 2, 'state_counts': {'root_draw': 1}}
