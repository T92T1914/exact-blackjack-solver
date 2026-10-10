"""Private fixed worker. No pricing import occurs before its stdin gate."""
from __future__ import annotations

import hashlib
import json
import sys


def main():
    # Parent starts readers only after its Windows Job assignment, then sends
    # captured input. A launch/assignment refusal cannot open this gate.
    raw = sys.stdin.buffer.read(81921)
    if len(raw) > 81920:
        return 6
    try:
        payload = json.loads(raw)
        if set(payload) != {'request', 'request_sha256', 'policy'}:
            return 6
        from . import record
        from .calculation import (EXIT_STATUSES, _error, _json_bytes, _normalise,
                                  _request_policy)
        from .core import Rules
        from ._enumeration import EnumerationLimitExceeded
        from .joint_split import ReferenceLimitExceeded

        request = _normalise(payload['request'])
        if (request != payload['request']
                or hashlib.sha256(_json_bytes(request)).hexdigest() != payload['request_sha256']):
            return 6
        if _request_policy(payload['policy'], request) != payload['policy']:
            return 6
        common = request['schema']['version'] == 2
        surrender = request['schema']['version'] == 3
        resplit = request['schema']['version'] == 4
        ace_resplit = request['schema']['version'] == 5
        bounded = common or surrender or resplit or ace_resplit
        result = {'status': 'worker_failed', 'decision': None, 'error': None,
                  'request_sha256': payload['request_sha256'], 'policy': payload['policy']}
        if bounded:
            result['work'] = None
        try:
            inputs = request['input']
            if common:
                result['decision'], result['work'] = record._common_shoe_record(
                    inputs['cards'], inputs['dealer_up'], Rules(**request['rules']),
                    shoe=tuple(inputs['unseen_counts']), can_double=inputs['can_double'],
                    can_split=inputs['can_split'], max_states=request['limits']['max_states'])
            elif surrender:
                result['decision'], result['work'] = record._late_surrender_record(
                    inputs['cards'], inputs['dealer_up'], Rules(**request['rules']),
                    shoe=tuple(inputs['unseen_counts']), can_double=inputs['can_double'],
                    can_surrender=inputs['can_surrender'],
                    max_states=request['limits']['max_states'])
            elif resplit:
                result['decision'], result['work'] = record._bounded_resplit_record(
                    inputs['cards'], inputs['dealer_up'], Rules(**request['rules']),
                    shoe=tuple(inputs['unseen_counts']), can_double=inputs['can_double'],
                    can_split=inputs['can_split'], max_states=request['limits']['max_states'])
            elif ace_resplit:
                result['decision'], result['work'] = record._bounded_ace_resplit_record(
                    inputs['cards'], inputs['dealer_up'], Rules(**request['rules']),
                    shoe=tuple(inputs['unseen_counts']), can_double=inputs['can_double'],
                    can_split=inputs['can_split'], max_states=request['limits']['max_states'])
            else:
                result['decision'] = record.decision_record(
                    inputs['cards'], inputs['dealer_up'], Rules(**request['rules']),
                    shoe=tuple(inputs['unseen_counts']), is_split_hand=inputs['is_split_hand'],
                    hand_count=inputs['hand_count'], can_double=inputs['can_double'],
                    can_split=inputs['can_split'])
            result['status'] = 'completed'
        except EnumerationLimitExceeded as exc:
            result['status'], result['error'] = 'resource_limited', _error(exc)
            if bounded:
                result['work'] = exc.work
        except (MemoryError, RecursionError, ReferenceLimitExceeded) as exc:
            result['status'], result['error'] = 'resource_limited', _error(exc)
        except (ValueError, OverflowError) as exc:
            result['status'], result['error'] = 'calculation_error', _error(exc)
        except Exception as exc:
            status = ('calculation_error' if (resplit or ace_resplit)
                      and isinstance(exc, ArithmeticError)
                      else 'worker_failed')
            result['status'], result['error'] = status, _error(exc)
        output = _json_bytes(result)
        if len(output) > 65536:
            return 6
        if sys.stdout.buffer.write(output) != len(output):
            return 8
        sys.stdout.buffer.flush()
        return EXIT_STATUSES[result['status']]
    except (OSError, ValueError, TypeError, KeyError, MemoryError, RecursionError):
        return 6


if __name__ == '__main__':
    status = main()
    if status != 0:
        try:
            sys.stdout.close()
        except (OSError, ValueError, KeyboardInterrupt):
            pass
    raise SystemExit(status)
