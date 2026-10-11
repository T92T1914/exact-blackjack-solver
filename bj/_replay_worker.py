"""Fixed replay worker. Original-file lookup follows the established owner gate."""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

MAX_ENVELOPE_BYTES = 32768
MAX_PATH_BYTES = 4096
MAX_STREAM_BYTES = 65536
OPERATION = 'saved_record_replay'


def main():
    raw = sys.stdin.buffer.read(MAX_ENVELOPE_BYTES + 1)
    if len(raw) > MAX_ENVELOPE_BYTES:
        return 6
    try:
        payload = json.loads(raw)
        if (not isinstance(payload, dict)
                or set(payload) != {'operation', 'record_path', 'policy'}
                or payload['operation'] != OPERATION
                or not isinstance(payload['record_path'], str)
                or len(payload['record_path'].encode('utf-8')) > MAX_PATH_BYTES):
            return 6
        from . import calculation, replay, supervised_replay

        policy = payload['policy']
        memory = policy['memory']
        memory_mib = (memory['bytes'] // (1024 * 1024)
                      if memory['mode'] == 'windows_job_commit' else None)
        if calculation._policy(policy['wall_seconds'], memory_mib) != policy:
            return 6
        path = payload['record_path']
        if str(supervised_replay._local_path(path)) != path:
            return 6
        identity, error = None, None
        try:
            # Capture, including ordinary-path lookup, belongs to this contained process.
            captured = supervised_replay._capture(path, threading.Event())
        except (OSError, ValueError) as exc:
            report = replay._failure('io_error', exc)
        else:
            try:
                calculation._exclusive_bytes(Path.cwd() / 'record-source.json', captured)
            except (OSError, ValueError) as exc:
                # An incomplete artifact is diagnostic and has no verified capture identity.
                report, error = None, {'type': 'CapturedRecordDelivery', 'message': str(exc)}
            else:
                identity = supervised_replay._source(captured)
                report = replay.replay_json(captured)
        output = {'operation': OPERATION, 'record_path': path, 'source_record': identity,
                  'policy': policy, 'report': report, 'error': error}
        encoded = calculation._json_bytes(output)
        if len(encoded) > MAX_STREAM_BYTES:
            output.update(report=None, error={
                'type': 'ReplayOutputLimit',
                'message': 'complete replay message exceeds 65536 bytes'})
            encoded = calculation._json_bytes(output)
            status = 4
        elif report is None:
            status = 8
        else:
            status = replay.EXIT_STATUSES[report['status']]
        if len(encoded) > MAX_STREAM_BYTES:
            return 6
        if sys.stdout.buffer.write(encoded) != len(encoded):
            return 8
        sys.stdout.buffer.flush()
        return status
    except (OSError, ValueError, TypeError, KeyError,
            MemoryError, RecursionError, OverflowError):
        return 6


if __name__ == '__main__':
    status = main()
    if status not in (0, 1):
        try:
            sys.stdout.close()
        except (OSError, ValueError, KeyboardInterrupt):
            pass
    raise SystemExit(status)
