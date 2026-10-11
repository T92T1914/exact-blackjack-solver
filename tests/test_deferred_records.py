"""Deferred record identity, exact replay and captured-result admission."""
from __future__ import annotations

import copy
from dataclasses import replace
import json
import math
import sys
from unittest.mock import patch

import pytest

from bj import calculation, deferred_second_card, record, replay, supervised_replay
from bj.core import RANKS, STANDARD


def rules(**changes):
    selected = {'peek': False, 'surrender': False, 'max_hands': 1,
                'resplit_aces': False, 'hit_split_aces': False,
                'double_any_two': True, 'tens_are_pairs': True}
    selected.update(changes)
    return replace(STANDARD, **selected)


def counts(stock):
    return tuple(stock.count(rank) for rank in RANKS)


def saved(*, stock=('A', 'T', 'T'), double=True, max_states=100_000,
          max_seconds=10.0):
    return record.deferred_second_card_record(
        ('9', '2'), 'T', rules(), shoe=counts(stock), can_double=double,
        max_states=max_states, max_seconds=max_seconds)


def policy():
    with patch.object(sys, 'platform', 'linux'):
        return calculation._policy(1, None)


def envelope(source, report=None):
    captured = calculation._json_bytes(source)
    report = replay.replay_json(captured) if report is None else report
    selected = policy()
    path = 'captured-deferred-record.json'
    message = {'operation': supervised_replay.OPERATION, 'record_path': path,
               'source_record': supervised_replay._source(captured),
               'policy': selected, 'report': report, 'error': None}
    return message, captured, path, selected


def validate(message, captured, path, selected):
    return supervised_replay._validated_report(
        calculation._json_bytes(message), captured, path,
        replay.EXIT_STATUSES[message['report']['status']], selected)


def test_supplied_counts_and_visible_inputs_are_owned_without_subtraction():
    cards = [9, 2]
    stock = list(counts(('A', 'T', 'T')))
    before = copy.deepcopy(stock)
    result = record.deferred_second_card_record(cards, 10, rules(), shoe=stock)
    assert cards == [9, 2] and stock == before
    assert result['schema'] == {'name': 'blackjack-decision', 'version': 7}
    assert result['state']['cards'] == ['9', '2']
    assert result['state']['dealer_up'] == 'T'
    assert result['state']['shoe'] == {
        'rank_order': list(RANKS), 'counts': before, 'source': 'supplied_unseen',
        'includes_hidden_hole': False, 'visible_cards_already_removed': True}
    cards[0], stock[0] = 10, 9
    assert result['state']['cards'] == ['9', '2']
    assert result['state']['shoe']['counts'] == before


def test_certain_natural_sole_stand_bypasses_only_the_old_negative_peek():
    original = saved(stock=('A',))
    assert original['decision']['evs'] == {'S': -1.0}
    assert original['decision']['margin'] is None
    assert original['model']['hole_rank_excluded_by_peek'] is None
    with pytest.raises(ValueError, match='after the peek'):
        record._record_inputs(('9', '2'), 'T', STANDARD, counts(('A',)), False, 1)
    with patch.object(record, '_record_inputs', side_effect=AssertionError('post peek')), \
            patch.object(record, 'best_action', side_effect=AssertionError('old engine')):
        report = replay.replay_json(json.dumps(original))
    assert report['status'] == 'agreement'
    assert report['recomputed'] == original['decision']
    assert report['work']['cache_retired'] is True


def test_historical_sole_margin_and_hidden_hole_defaults_remain_numeric_and_true():
    original = record.decision_record(('T', 'T'), '7', shoe=counts(('T',)),
                                      can_split=False)
    assert original['schema']['version'] == 2
    assert original['decision']['margin'] == 0.0
    assert original['state']['shoe']['includes_hidden_hole'] is True
    assert replay.replay_json(json.dumps(original))['status'] == 'agreement'
    with pytest.raises(record._UnsupportedRules, match='post-peek'):
        record.decision_record(('9', '2'), 'T', rules(), shoe=counts(('A',)))


def test_direct_replay_dispatches_same_family_counts_and_original_limits():
    original = saved(max_states=2000, max_seconds=0.75)
    retained = tuple(original['state']['shoe']['counts'])
    decide = deferred_second_card.decide
    calls = []

    def checked(hand, up, unseen, selected_rules, **options):
        calls.append((tuple(hand), up, unseen, selected_rules, options))
        assert unseen == retained
        return decide(hand, up, unseen, selected_rules, **options)

    with patch.object(deferred_second_card, 'decide', side_effect=checked), \
            patch.object(record, 'decision_record', side_effect=AssertionError('old model')):
        report = replay.replay_json(json.dumps(original).encode())
    assert report['status'] == 'agreement'
    assert report['recomputed'] == original['decision']
    assert len(calls) == 1
    assert calls[0][4] == {'can_double': True, 'can_split': False,
                           'max_states': 2000, 'max_seconds': 0.75}
    assert report['work']['limit'] == 2000
    assert report['work']['max_seconds'] == 0.75
    assert report['work']['elapsed_seconds'] <= 0.75
    assert report['work']['computation_method'] == (
        'deferred_second_card_request_local_binary64_v1')
    assert report['work']['cache_scope'] == 'request_local_player_and_dealer'
    assert report['work']['cache_retired'] is True


def test_full_context_is_retained_without_pricing_inactive_rules():
    original = saved()
    alternative = record.deferred_second_card_record(
        ('9', '2'), 'T', rules(decks=2, das=False, blackjack_payout=7.0,
                               insurance_payout=5.0), shoe=counts(('A', 'T', 'T')))
    assert alternative['decision'] == original['decision']
    assert alternative['rules']['decks'] == 2
    assert alternative['rules']['das'] is False
    assert alternative['rules']['blackjack_payout'] == 7.0
    assert alternative['rules']['insurance_payout'] == 5.0
    assert alternative['model']['initial_natural'] == 'excluded'
    assert alternative['model']['insurance_priced'] is False
    assert alternative['model']['split'] == 'not_supported'


@pytest.mark.parametrize('double', [False, True])
def test_permission_and_stock_derive_current_action_menu(double):
    original = saved(double=double)
    report = replay.replay_json(json.dumps(original))
    assert report['status'] == 'agreement'
    assert set(report['recomputed']['evs']) == ({'S', 'H', 'D'} if double else {'S', 'H'})
    assert original['state']['action_controls'] == {
        'can_double': double, 'can_split': False}
    supervised_replay._current(original, report['recomputed'])


@pytest.mark.parametrize('change', [
    lambda item: item['decision']['evs'].update(
        S=math.nextafter(item['decision']['evs']['S'], math.inf)),
    lambda item: item['decision'].update(margin=None),
    lambda item: item['decision'].update(action='S', action_name='STAND', margin=9.0),
    lambda item: item['decision']['evs'].pop('D'),
])
def test_recognizable_saved_answers_are_exact_comparison_data(change):
    original = saved()
    expected = copy.deepcopy(original['decision'])
    change(original)
    report = replay.replay_json(json.dumps(original))
    assert report['status'] == 'differences'
    assert report['recorded'] == original['decision']
    assert report['recomputed'] == expected
    assert report['comparison_policy']['absolute_tolerance'] == 0.0
    assert report['comparison_policy']['relative_tolerance'] == 0.0


def test_numeric_saved_sole_margin_is_a_difference_from_current_null():
    original = saved(stock=('A',))
    original['decision']['margin'] = 0
    report = replay.replay_json(json.dumps(original))
    assert report['status'] == 'differences'
    assert report['recomputed']['margin'] is None
    assert report['comparison']['margin'] == {
        'recorded': 0, 'recomputed': None, 'matches': False}


@pytest.mark.parametrize('action', ['P', 'R'])
def test_absent_model_actions_cannot_be_relabelled_as_saved_comparison_data(action):
    original = saved()
    original['decision']['evs'][action] = 1.0
    with patch.object(deferred_second_card, 'decide', side_effect=AssertionError('pricing')):
        report = replay.replay_json(json.dumps(original))
    assert report['status'] == 'invalid_input'
    assert report['recomputed'] is None


@pytest.mark.parametrize('change', [
    lambda item: item['model'].update(name='post_peek_late_surrender'),
    lambda item: item['model'].update(version=2),
    lambda item: item['model'].update(dealer_information='hidden_hole_post_peek'),
    lambda item: item['model'].update(dealer_natural='lose_original_wager_only'),
    lambda item: item['model'].update(enumeration_state_limit=0),
    lambda item: item['model'].update(enumeration_seconds_limit=11),
    lambda item: item['rules'].update(peek=True),
    lambda item: item['rules'].update(surrender=True),
    lambda item: item['state']['action_controls'].update(can_split=True),
    lambda item: item['state']['shoe'].update(includes_hidden_hole=True),
    lambda item: item['state']['shoe'].update(source='fresh_minus_visible'),
])
def test_unqualified_information_rules_and_limits_refuse_before_pricing(change):
    original = saved()
    change(original)
    with patch.object(deferred_second_card, 'decide', side_effect=AssertionError('pricing')):
        report = replay.replay_json(json.dumps(original))
    assert report['status'] == 'unsupported_record'
    assert report['recomputed'] is None and report['comparison'] is None


@pytest.mark.parametrize('seconds', [True, '10', None])
def test_new_stored_seconds_requires_finite_non_boolean_numeric_data(seconds):
    original = saved()
    original['model']['enumeration_seconds_limit'] = seconds
    with patch.object(deferred_second_card, 'decide', side_effect=AssertionError('pricing')):
        report = replay.replay_json(json.dumps(original))
    assert report['status'] == 'invalid_input'
    assert report['recomputed'] is None


def test_integer_seconds_and_historical_package_are_admitted_without_new_claims():
    original = saved()
    original['model']['enumeration_seconds_limit'] = 10
    original['package']['version'] = 'historical-package'
    report = replay.replay_json(json.dumps(original))
    assert report['status'] == 'agreement'
    assert report['package_version_matches'] is False


@pytest.mark.parametrize('cards,stock', [
    (('9', '2'), ('6', 'T')),
    (('2', '2'), ('5', '6', 'T')),
])
def test_nonchosen_root_or_continuation_exhaustion_withholds_whole_answer(cards, stock):
    original = saved(stock=('A',))
    original['state'].update(cards=list(cards), total=11 if cards[0] == '9' else 4)
    original['state']['shoe']['counts'] = list(counts(stock))
    report = replay.replay_json(json.dumps(original))
    assert report['status'] == 'calculation_error'
    assert report['error']['type'] == 'UnsupportedContinuation'
    assert report['recomputed'] is None and report['comparison'] is None
    assert report['work']['cache_retired'] is True
    assert report['work']['computation_method'] == (
        'deferred_second_card_request_local_binary64_v1')
    message, captured, path, selected = envelope(original, report)
    assert validate(message, captured, path, selected)[0] == 'calculation_error'


@pytest.mark.parametrize('limit_kind', ['states', 'seconds'])
def test_recorded_budget_refuses_with_work_and_following_replay_recovers(limit_kind):
    original = saved()
    key = 'enumeration_state_limit' if limit_kind == 'states' else 'enumeration_seconds_limit'
    original['model'][key] = 1 if limit_kind == 'states' else 1e-9
    report = replay.replay_json(json.dumps(original))
    assert report['status'] == 'resource_limited'
    assert report['recomputed'] is None and report['comparison'] is None
    assert report['work']['cache_retired'] is True
    if limit_kind == 'states':
        assert report['error']['type'] == 'EnumerationLimitExceeded'
        assert report['work']['states'] == 1 and report['work']['attempted_states'] == 2
    else:
        assert report['error']['type'] == 'DeferredTimeLimitExceeded'
        assert report['work']['elapsed_seconds'] >= 1e-9
    message, captured, path, selected = envelope(original, report)
    assert validate(message, captured, path, selected)[0] == 'resource_limited'
    recovery = replay.replay_json(json.dumps(saved()))
    assert recovery['status'] == 'agreement'
    assert recovery['work']['cache_retired'] is True


def test_protected_current_requires_sole_null_and_every_offered_action():
    original = saved(stock=('A',))
    changed = copy.deepcopy(original['decision'])
    changed['margin'] = 0.0
    with pytest.raises(ValueError, match='ranking or margin'):
        supervised_replay._current(original, changed)
    original = saved()
    changed = copy.deepcopy(original['decision'])
    changed['evs'].pop('D')
    with pytest.raises(ValueError, match='exactly its offered'):
        supervised_replay._current(original, changed)


def test_protected_complete_report_joins_immutable_capture_without_parent_pricing():
    original = saved(stock=('A',))
    message, captured, path, selected = envelope(original)
    with patch.object(deferred_second_card, 'decide', side_effect=AssertionError('parent price')):
        status, report, error = validate(message, captured, path, selected)
    assert status == 'agreement' and error is None
    assert report['recomputed'] == original['decision']
    assert report['work']['cache_retired'] is True
    changed = copy.deepcopy(message)
    changed['report']['modeled_input']['state']['shoe']['counts'][0] += 1
    with pytest.raises(ValueError):
        validate(changed, captured, path, selected)


@pytest.mark.parametrize('change', [
    lambda report: report.pop('work'),
    lambda report: report['work'].update(computation_method='physical_permutation'),
    lambda report: report['work'].update(cache_scope='global'),
    lambda report: report['work'].update(cache_retired=False),
    lambda report: report['work'].update(elapsed_seconds=11.0),
    lambda report: report['work'].update(attempted_states=report['work']['states'] + 1),
])
def test_protected_completion_rejects_missing_or_false_method_lifetime_and_work(change):
    original = saved(stock=('A',))
    message, captured, path, selected = envelope(original)
    change(message['report'])
    with pytest.raises(ValueError):
        validate(message, captured, path, selected)


def test_protected_typed_refusal_requires_its_work_and_true_cap_exhaustion():
    original = saved()
    original['model']['enumeration_state_limit'] = 1
    message, captured, path, selected = envelope(original)
    assert message['report']['status'] == 'resource_limited'
    missing = copy.deepcopy(message)
    missing['report'].pop('work')
    with pytest.raises(ValueError):
        validate(missing, captured, path, selected)
    unspent = copy.deepcopy(message)
    unspent['report']['work'].update(states=0, attempted_states=1, state_counts={})
    with pytest.raises(ValueError):
        validate(unspent, captured, path, selected)
