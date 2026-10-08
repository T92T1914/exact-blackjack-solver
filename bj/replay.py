"""Bounded JSON admission and comparison through the existing decision engine.

Saved values are historical comparison data. They never enter the calculation.
No file is changed, no package version is installed and no external data is read.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import fields
from typing import Any

from . import __version__, record
from .core import ACTION_NAMES, RANKS, Rules, hand_total

__all__ = ['MAX_RECORD_BYTES', 'MAX_RECORD_DEPTH', 'EXIT_STATUSES',
           'replay_json', 'replay_file']

MAX_RECORD_BYTES = 64 * 1024
MAX_RECORD_DEPTH = 8
EXIT_STATUSES = {
    'agreement': 0, 'differences': 1, 'invalid_input': 2, 'unsupported_record': 3,
    'resource_limited': 4, 'calculation_error': 5, 'io_error': 6, 'interrupted': 130,
}
_POLICY = {'name': 'exact_binary_float', 'absolute_tolerance': 0.0,
           'relative_tolerance': 0.0, 'action_identity': 'exact'}


class _InvalidRecord(ValueError):
    pass


class _UnsupportedRecord(ValueError):
    pass


def _object(value, keys, path):
    if not isinstance(value, dict):
        raise _InvalidRecord(f'{path} must be an object')
    expected = set(keys)
    missing, unknown = expected - value.keys(), value.keys() - expected
    if missing or unknown:
        raise _InvalidRecord(f'{path}: missing fields {sorted(missing)}, '
                             f'unknown fields {sorted(unknown)}')
    return value


def _string(value, path):
    if not isinstance(value, str) or not value:
        raise _InvalidRecord(f'{path} must be a nonempty string')
    return value


def _integer(value, path):
    if not isinstance(value, int) or isinstance(value, bool):
        raise _InvalidRecord(f'{path} must be an integer, not a boolean')
    return value


def _number(value, path):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise _InvalidRecord(f'{path} must be a finite number, not a boolean')
    try:
        result = float(value)
    except (OverflowError, ValueError):
        raise _InvalidRecord(f'{path} must be a finite number') from None
    if not math.isfinite(result):
        raise _InvalidRecord(f'{path} must be a finite number')
    return result


def _constant(value, expected, path, *, derived=False):
    if expected is None and value is not None and isinstance(value, (int, float)):
        _number(value, path)
        raise _UnsupportedRecord(f'{path} must be None')
    if type(value) is not type(expected):
        raise _InvalidRecord(f'{path} has the wrong type')
    if value != expected:
        error = _InvalidRecord if derived else _UnsupportedRecord
        raise error(f'{path} must be {expected!r}')


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise _InvalidRecord(f'duplicate JSON key: {key!r}')
        value[key] = item
    return value


def _nonfinite(value):
    raise _InvalidRecord(f'nonfinite JSON number: {value}')


def _float(value):
    return _number(float(value), 'JSON number')


def _parse(text):
    if isinstance(text, str):
        if len(text) > MAX_RECORD_BYTES:
            raise _InvalidRecord(f'record exceeds {MAX_RECORD_BYTES} UTF-8 bytes')
        try:
            raw = text.encode('utf-8')
        except UnicodeEncodeError as exc:
            raise _InvalidRecord('record must be valid UTF-8') from exc
    elif isinstance(text, bytes):
        raw = text
    else:
        raise _InvalidRecord('record must be JSON text or UTF-8 bytes')
    if len(raw) > MAX_RECORD_BYTES:
        raise _InvalidRecord(f'record exceeds {MAX_RECORD_BYTES} UTF-8 bytes')
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise _InvalidRecord('record must be valid UTF-8') from exc

    # Bound container depth before the JSON decoder allocates nested objects.
    depth, in_string, escaped = 0, False, False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in '{[':
            depth += 1
            if depth > MAX_RECORD_DEPTH:
                raise _InvalidRecord(f'record exceeds container depth {MAX_RECORD_DEPTH}')
        elif char in '}]':
            depth -= 1
    try:
        return json.loads(text, object_pairs_hook=_pairs,
                          parse_constant=_nonfinite, parse_float=_float)
    except (ValueError, RecursionError) as exc:
        raise _InvalidRecord(str(exc)) from exc


def _admit(saved):
    if not isinstance(saved, dict):
        raise _InvalidRecord('record must be an object')
    schema = _object(saved.get('schema'), ('name', 'version'), 'schema')
    name = _string(schema['name'], 'schema.name')
    version = _integer(schema['version'], 'schema.version')
    if name != 'blackjack-decision' or version != record.SCHEMA_VERSION:
        raise _UnsupportedRecord(f'unsupported schema {name!r}, version {version}')
    _object(saved, ('schema', 'package', 'state', 'rules', 'decision', 'model'), 'record')
    package = _object(saved['package'], ('name', 'version'), 'package')
    _constant(package['name'], 'exact-blackjack-solver', 'package.name')
    _string(package['version'], 'package.version')
    state = _object(saved['state'], ('cards', 'dealer_up', 'total', 'soft', 'is_split_hand',
                                    'hand_count', 'shoe'), 'state')
    cards, up = state['cards'], state['dealer_up']
    if (not isinstance(cards, list) or any(not isinstance(card, str) or card not in RANKS
                                         for card in cards)):
        raise _InvalidRecord('state.cards must be a list of normalized ranks in dealt order')
    if not isinstance(up, str) or up not in RANKS:
        raise _InvalidRecord('state.dealer_up must be a normalized rank')
    _integer(state['total'], 'state.total')
    _integer(state['hand_count'], 'state.hand_count')
    for key in ('soft', 'is_split_hand'):
        if not isinstance(state[key], bool):
            raise _InvalidRecord(f'state.{key} must be a boolean')
    shoe = _object(state['shoe'], ('rank_order', 'counts', 'source', 'includes_hidden_hole',
                                   'visible_cards_already_removed'), 'state.shoe')
    _constant(shoe['rank_order'], list(RANKS), 'state.shoe.rank_order', derived=True)
    if not isinstance(shoe['counts'], list):
        raise _InvalidRecord('state.shoe.counts must be a list')
    _constant(shoe['includes_hidden_hole'], True, 'state.shoe.includes_hidden_hole')
    _constant(shoe['visible_cards_already_removed'], True,
              'state.shoe.visible_cards_already_removed')
    source = _string(shoe['source'], 'state.shoe.source')
    if source not in ('fresh_minus_visible', 'supplied_unseen'):
        raise _UnsupportedRecord(f'unsupported shoe source {source!r}')
    rule_values = _object(saved['rules'], (field.name for field in fields(Rules)), 'rules')
    rules = Rules(**rule_values)
    try:
        record._rules_record(rules)
        hand, up, unseen, hand_count = record._record_inputs(
            cards, up, rules, shoe['counts'], state['is_split_hand'], state['hand_count'])
    except record._UnsupportedRules as exc:
        raise _UnsupportedRecord(str(exc)) from exc
    except ValueError as exc:
        raise _InvalidRecord(str(exc)) from exc
    total, soft = hand_total(hand)
    _constant(state['total'], total, 'state.total', derived=True)
    _constant(state['soft'], soft, 'state.soft', derived=True)
    if source == 'fresh_minus_visible':
        try:
            expected = record.initial_shoe_for(hand, up, rules)
        except ValueError as exc:
            raise _InvalidRecord(str(exc)) from exc
        if unseen != expected:
            raise _InvalidRecord('fresh_minus_visible counts disagree with the declared state')
    model = _object(saved['model'], record._model_record(up).keys(), 'model')
    for key, expected in record._model_record(up).items():
        _constant(model[key], expected, f'model.{key}',
                  derived=key == 'hole_rank_excluded_by_peek')
    decision = _object(saved['decision'], ('action', 'action_name', 'evs', 'margin', 'units',
                                         'whole_game_estimate'), 'decision')
    _constant(decision['units'], 'original_wager', 'decision.units')
    _constant(decision['whole_game_estimate'], None, 'decision.whole_game_estimate')
    action, evs = decision['action'], decision['evs']
    if not isinstance(action, str) or action not in ACTION_NAMES:
        raise _InvalidRecord('decision.action must be a supported action code')
    _constant(decision['action_name'], ACTION_NAMES[action], 'decision.action_name', derived=True)
    if (not isinstance(evs, dict) or not evs or action not in evs
            or any(key not in ACTION_NAMES for key in evs)):
        raise _InvalidRecord('decision.evs must have supported action codes and include action')
    # Check representation only. An altered recommendation, margin or legal
    # action set is comparison data and must remain visible in the replay.
    for key, value in evs.items():
        _number(value, f'decision.evs.{key}')
    if _number(decision['margin'], 'decision.margin') < 0:
        raise _InvalidRecord('decision.margin must be nonnegative')
    return hand, up, unseen, rules, state['is_split_hand'], hand_count


def _report(status, *, saved=None, recomputed=None, comparison=None, error=None):
    package = saved['package'] if saved is not None else None
    return {
        'status': status, 'comparison_policy': dict(_POLICY),
        'recorded_package': package,
        'current_package': {'name': 'exact-blackjack-solver', 'version': __version__},
        'package_version_matches': package['version'] == __version__ if package else None,
        'modeled_input': {'state': saved['state'], 'rules': saved['rules'],
                          'model': saved['model']} if saved is not None else None,
        'recorded': saved['decision'] if saved is not None else None,
        'recomputed': recomputed, 'comparison': comparison, 'error': error,
    }


def _failure(status, exc, saved=None):
    return _report(status, saved=saved,
                   error={'type': type(exc).__name__, 'message': str(exc)})


def _compare(recorded, current):
    left, right = recorded['evs'], current['evs']
    codes = sorted(left.keys() | right.keys())
    evs = {
        code: {'recorded': left.get(code), 'recomputed': right.get(code),
               'matches': code in left and code in right
                          and float(left[code]) == float(right[code])}
        for code in codes
    }
    action_matches = recorded['action'] == current['action']
    margin_matches = float(recorded['margin']) == float(current['margin'])
    return {
        'legal_actions': {'recorded': sorted(left), 'recomputed': sorted(right),
                          'matches': left.keys() == right.keys()},
        'evs': evs, 'evs_match': all(item['matches'] for item in evs.values()),
        'recommendation': {'recorded': recorded['action'], 'recomputed': current['action'],
                           'matches': action_matches},
        'margin': {'recorded': recorded['margin'], 'recomputed': current['margin'],
                   'matches': margin_matches},
    }


def replay_json(text: str | bytes) -> dict[str, Any]:
    """Admit schema-v1 JSON, recalculate, and report exact numerical agreement.

    The report distinguishes invalid/unsupported input from differences and
    incomplete calculation. No tolerance is applied, including near ties.
    Production recursion and caches retain their existing unbounded lifetime.
    MemoryError and RecursionError report resource_limited, KeyboardInterrupt
    reports interrupted. There is no new time, work or memory supervisor.
    """
    admitted = None
    try:
        saved = _parse(text)
        hand, up, unseen, rules, is_split_hand, hand_count = _admit(saved)
        admitted = saved
        current = record.decision_record(
            hand, up, rules, shoe=unseen, is_split_hand=is_split_hand,
            hand_count=hand_count)['decision']
        comparison = _compare(saved['decision'], current)
        agrees = (comparison['legal_actions']['matches'] and comparison['evs_match']
                  and comparison['recommendation']['matches'] and comparison['margin']['matches'])
        return _report('agreement' if agrees else 'differences', saved=saved,
                       recomputed=current, comparison=comparison)
    except _InvalidRecord as exc:
        return _failure('invalid_input', exc)
    except _UnsupportedRecord as exc:
        return _failure('unsupported_record', exc)
    except KeyboardInterrupt as exc:
        return _failure('interrupted', exc, admitted)
    except (MemoryError, RecursionError) as exc:
        return _failure('resource_limited', exc, admitted)
    except (ValueError, OverflowError) as exc:
        return _failure('calculation_error', exc, admitted)


def replay_file(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Read at most 64 KiB plus one byte from a local file, without modifying it."""
    try:
        if not isinstance(path, (str, os.PathLike)) or not isinstance(os.fspath(path), str):
            raise _InvalidRecord('path must be a local filename, not a file descriptor')
        with open(path, 'rb') as stream:
            text = stream.read(MAX_RECORD_BYTES + 1)
    except (TypeError, ValueError) as exc:
        return _failure('invalid_input', exc)
    except OSError as exc:
        return _failure('io_error', exc)
    except KeyboardInterrupt as exc:
        return _failure('interrupted', exc)
    except MemoryError as exc:
        return _failure('resource_limited', exc)
    return replay_json(text)
