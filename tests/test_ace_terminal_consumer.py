"""Ace work diagnostics stay private, model-bound and separate from saved answers."""
from __future__ import annotations

import copy
import json
import threading
from contextlib import ExitStack
from unittest.mock import patch

import pytest

from bj import _enumeration, bounded_ace_resplit, bounded_resplit
from bj import calculation as calc, record, replay, supervised_replay as protected
from bj._enumeration import EnumerationLimitExceeded
from bj.caches import clear_all_caches
from test_ace_resplit_calculation import ace_request
from test_bounded_ace_resplit import counts, rules
from test_calculation import policy
from test_common_calculation import common_request
from test_deferred_calculation import request as deferred_request
from test_resplit_calculation import fixed_message, resplit_request, returned, validate
from test_surrender_calculation import surrender_request

HISTORICAL_WORK = {'limit', 'states', 'attempted_states', 'state_counts'}


@pytest.fixture(autouse=True)
def cold_caches():
    clear_all_caches()
    yield
    clear_all_caches()


def no_parent_pricing():
    stack = ExitStack()
    for name in ('decide', '_decide_with_diagnostics'):
        stack.enter_context(patch.object(bounded_ace_resplit, name,
                                        side_effect=AssertionError('parent pricing')))
    return stack


def detached_reuse(*, seeded=0, lookups=0, hits=0, unique=0):
    return {'computation_method': _enumeration.TERMINAL_REUSE_METHOD,
            'cache_scope': _enumeration.TERMINAL_REUSE_SCOPE, 'cache_retired': True,
            'root_terminal_keys': seeded, 'registry_lookups': lookups,
            'registry_hits': hits, 'unique_reused_keys': unique}


def plausible_returned_work(limit, *, complete=True):
    """Synthetic returned accounting for strict transport validation cases."""
    return {'limit': limit, 'states': 5, 'attempted_states': 5 if complete else 6,
            'state_counts': {'root_dealer': 3, 'ace_resplit_dealer': 2},
            'terminal_reuse': detached_reuse(seeded=3, lookups=4, hits=2, unique=1)}


def protected_validation(saved, report):
    captured = calc._json_bytes(saved)
    path, selected = 'captured-ace-record.json', policy()
    message = {'operation': protected.OPERATION, 'record_path': path,
               'source_record': protected._source(captured), 'policy': selected,
               'report': report, 'error': None}
    with no_parent_pricing():
        return protected._validated_report(calc._json_bytes(message), captured, path,
                                           protected.EXIT_STATUSES[report['status']], selected)


@pytest.mark.parametrize('split', [True, False])
def test_private_record_keeps_public_document_and_uses_selected_diagnostic_path(split):
    args = (('A', 'A'), '7', rules())
    options = {'shoe': counts(('T',) * 4), 'can_split': split}
    with patch.object(bounded_ace_resplit, '_decide_with_diagnostics',
                      side_effect=AssertionError('public diagnostic path')):
        public = record.bounded_ace_resplit_record(*args, **options)
    clear_all_caches()
    selected = bounded_ace_resplit._decide_with_diagnostics
    with patch.object(bounded_ace_resplit, '_decide_with_diagnostics',
                      wraps=selected) as private_path, patch.object(
            bounded_ace_resplit, 'decide', side_effect=AssertionError('private public path')):
        private, work = record._bounded_ace_resplit_record(*args, **options)
    assert private_path.call_count == 1
    assert calc._json_bytes(private) == calc._json_bytes(public)
    assert 'terminal_reuse' not in json.dumps(private)
    assert set(work) == HISTORICAL_WORK | ({'terminal_reuse'} if split else set())
    if split:
        assert work['terminal_reuse']['cache_retired'] is True


def test_split_disabled_private_and_public_records_allocate_no_registry():
    with patch.object(_enumeration, '_TerminalReuse',
                      side_effect=AssertionError('disabled registry allocation')):
        private, work = record._bounded_ace_resplit_record(
            ('A', 'A'), '7', rules(), shoe=counts(('T',) * 4), can_split=False)
        public = record.bounded_ace_resplit_record(
            ('A', 'A'), '7', rules(), shoe=counts(('T',) * 4), can_split=False)
    assert private == public and set(work) == HISTORICAL_WORK


def test_public_refusal_and_direct_replay_keep_historical_work_private_refusal_retires():
    saved = record.bounded_ace_resplit_record(
        ('A', 'A'), '7', rules(), shoe=counts(('T',) * 4))
    options = {'shoe': counts(('T',) * 4), 'max_states': 1}
    for call, keys in ((record.bounded_ace_resplit_record, HISTORICAL_WORK),
                       (record._bounded_ace_resplit_record,
                        HISTORICAL_WORK | {'terminal_reuse'})):
        clear_all_caches()
        with pytest.raises(EnumerationLimitExceeded) as refused:
            call(('A', 'A'), '7', rules(), **options)
        assert set(refused.value.work) == keys
        if 'terminal_reuse' in keys:
            assert refused.value.work['terminal_reuse']['cache_retired'] is True
        assert _enumeration._active.get() is None
    saved['model']['enumeration_state_limit'] = 1
    clear_all_caches()
    report = replay.replay_json(calc._json_bytes(saved))
    assert report['status'] == 'resource_limited'
    assert report['recomputed'] is report['comparison'] is None
    assert set(report['work']) == HISTORICAL_WORK


@pytest.mark.parametrize('split', [True, False])
def test_actual_worker_work_validates_and_existing_commit_preserves_saved_document(tmp_path, split):
    value = ace_request(split=split)
    code, message, captured, selected = fixed_message(value)
    assert code == 0 and message['status'] == 'completed'
    assert set(message['work']) == HISTORICAL_WORK | ({'terminal_reuse'} if split else set())
    source = tmp_path / 'request.json'
    source.write_bytes(calc._json_bytes(value))
    with no_parent_pricing(), patch.object(calc, 'execute', side_effect=returned(message, code)):
        status, raw, error, work = validate(message, captured, selected, code)
        receipt = calc._run(source, tmp_path / 'attempt', policy(), threading.Event())
    assert status == receipt['status'] == 'completed' and error is None
    assert work == receipt['work'] == message['work']
    assert json.loads(raw) == message['decision']
    assert (tmp_path / 'attempt/result/decision.json').read_bytes() == raw
    assert json.loads((tmp_path / 'attempt/result/receipt.json').read_bytes()) == receipt


@pytest.mark.parametrize('complete', [True, False])
def test_historical_four_field_ace_worker_work_remains_valid(complete):
    code, message, captured, selected = fixed_message(ace_request(100000 if complete else 1))
    assert code == (0 if complete else 4)
    message['work'].pop('terminal_reuse')
    with no_parent_pricing():
        status, raw, error, work = validate(message, captured, selected, code)
    assert status == ('completed' if complete else 'resource_limited')
    assert set(work) == HISTORICAL_WORK
    assert (raw is not None) is complete
    assert (error is None) is complete


@pytest.mark.parametrize('change', [
    lambda work: work.update(extra=0),
    lambda work: work['terminal_reuse'].update(extra=0),
    lambda work: work['terminal_reuse'].update(cache_retired=False),
    lambda work: work['terminal_reuse'].update(cache_retired=1),
    lambda work: work['terminal_reuse'].update(computation_method='other'),
    lambda work: work['terminal_reuse'].update(cache_scope='process'),
    lambda work: work['terminal_reuse'].update(root_terminal_keys=True),
    lambda work: work['terminal_reuse'].update(registry_lookups=-1),
    lambda work: work['terminal_reuse'].update(root_terminal_keys=4),
    lambda work: work['terminal_reuse'].update(registry_hits=5),
    lambda work: work['terminal_reuse'].update(unique_reused_keys=3),
    lambda work: work['terminal_reuse'].update(unique_reused_keys=0),
    lambda work: work['terminal_reuse'].update(registry_lookups=5),
])
def test_forged_returned_diagnostics_cannot_pass_parent_binding(change):
    code, message, captured, selected = fixed_message(ace_request())
    message['work'] = plausible_returned_work(captured['limits']['max_states'])
    change(message['work'])
    with no_parent_pricing(), pytest.raises(ValueError):
        validate(message, captured, selected, code)


def test_completed_work_has_no_refused_entry_allowance_but_refusal_has_one():
    complete = plausible_returned_work(100000)
    complete['terminal_reuse']['registry_lookups'] = 5
    options = {'families': bounded_ace_resplit.FAMILIES, 'terminal_reuse': True}
    with pytest.raises(ValueError, match='entered/reused'):
        calc._validated_work(complete, 100000, complete=True, **options)
    refused = copy.deepcopy(complete)
    refused['attempted_states'] += 1
    calc._validated_work(refused, 100000, complete=False, **options)


def test_split_disabled_capture_refuses_extension_even_with_ace_family():
    code, message, captured, selected = fixed_message(ace_request(split=False))
    message['work']['terminal_reuse'] = detached_reuse()
    with no_parent_pricing(), pytest.raises(ValueError, match='split-enabled ace'):
        validate(message, captured, selected, code)


@pytest.mark.parametrize('factory', [common_request, surrender_request,
                                     resplit_request, deferred_request])
def test_foreign_calculation_families_refuse_terminal_extension(factory):
    code, message, captured, selected = fixed_message(factory())
    assert code == 0
    message['work']['terminal_reuse'] = detached_reuse()
    with no_parent_pricing(), pytest.raises(ValueError):
        validate(message, captured, selected, code)


def test_internal_permission_flag_cannot_extend_a_foreign_family_set():
    work = {'limit': 100000, 'states': 3, 'attempted_states': 3,
            'state_counts': {'root_dealer': 3},
            'terminal_reuse': detached_reuse(seeded=1, lookups=1, hits=1, unique=1)}
    with pytest.raises(ValueError, match='split-enabled ace'):
        calc._validated_work(work, 100000, complete=True,
                             families=bounded_resplit.FAMILIES, terminal_reuse=True)


def test_direct_and_protected_success_keep_original_report_shape_and_exact_comparison():
    saved = record.bounded_ace_resplit_record(
        ('A', 'A'), '7', rules(), shoe=counts(('T',) * 4))
    raw = calc._json_bytes(saved)
    clear_all_caches()
    report = replay.replay_json(raw)
    assert report['status'] == 'agreement' and report['recomputed'] == saved['decision']
    assert set(report) == set(replay._report('agreement')) and 'work' not in report
    assert protected_validation(saved, report) == ('agreement', report, None)
    assert calc._json_bytes(saved) == raw
    changed = copy.deepcopy(report)
    changed['work'] = plausible_returned_work(100000)
    with pytest.raises(ValueError, match='status or work'):
        protected_validation(saved, changed)


@pytest.mark.parametrize('split', [True, False])
def test_protected_refusal_accepts_historical_work_and_only_admitted_ace_extension(split):
    saved = record.bounded_ace_resplit_record(
        ('A', 'A'), '7', rules(), shoe=counts(('T',) * 4), can_split=split)
    saved['model']['enumeration_state_limit'] = 1
    clear_all_caches()
    report = replay.replay_json(calc._json_bytes(saved))
    assert report['status'] == 'resource_limited' and set(report['work']) == HISTORICAL_WORK
    assert protected_validation(saved, report)[0] == 'resource_limited'
    report['work']['terminal_reuse'] = detached_reuse()
    if split:
        assert protected_validation(saved, report)[0] == 'resource_limited'
    else:
        with pytest.raises(ValueError, match='split-enabled ace'):
            protected_validation(saved, report)


@pytest.mark.parametrize('factory', [common_request, surrender_request, resplit_request])
def test_protected_refusal_rejects_extension_on_foreign_recorded_family(factory):
    code, message, _, _ = fixed_message(factory())
    assert code == 0
    saved = message['decision']
    work = {'limit': saved['model']['enumeration_state_limit'],
            'states': 1, 'attempted_states': 2, 'state_counts': {'root_dealer': 1},
            'terminal_reuse': detached_reuse()}
    report = replay._failure('resource_limited', EnumerationLimitExceeded(work), saved)
    with pytest.raises(ValueError, match='split-enabled ace'):
        protected_validation(saved, report)
