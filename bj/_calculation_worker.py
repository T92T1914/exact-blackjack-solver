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
        from .calculation import EXIT_STATUSES, _error, _json_bytes, _normalise
        from .core import Rules

        request = _normalise(payload['request'])
        if (request != payload['request']
                or hashlib.sha256(_json_bytes(request)).hexdigest() != payload['request_sha256']):
            return 6
        result = {'status': 'worker_failed', 'decision': None, 'error': None,
                  'request_sha256': payload['request_sha256'], 'policy': payload['policy']}
        try:
            inputs = request['input']
            result['decision'] = record.decision_record(
                inputs['cards'], inputs['dealer_up'], Rules(**request['rules']),
                shoe=tuple(inputs['unseen_counts']), is_split_hand=inputs['is_split_hand'],
                hand_count=inputs['hand_count'], can_double=inputs['can_double'],
                can_split=inputs['can_split'])
            result['status'] = 'completed'
        except (MemoryError, RecursionError) as exc:
            result['status'], result['error'] = 'resource_limited', _error(exc)
        except (ValueError, OverflowError) as exc:
            result['status'], result['error'] = 'calculation_error', _error(exc)
        except Exception as exc:
            result['status'], result['error'] = 'worker_failed', _error(exc)
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
