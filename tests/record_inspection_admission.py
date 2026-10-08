"""Test-only admission oracle. It never calls the decision engine."""
import json
import sys
from dataclasses import fields

from bj import record, replay
from bj.core import ACTION_NAMES, RANKS, Rules


def main():
    cases = json.load(sys.stdin)
    outcomes = []
    for case in cases:
        try:
            replay._admit(replay._parse(bytes(case["bytes"])))
            status = "accepted"
        except replay._UnsupportedRecord:
            status = "unsupported_record"
        except replay._InvalidRecord:
            status = "invalid_input"
        outcomes.append(status)
    print(json.dumps({
        "outcomes": outcomes,
        "contract": {
            "max_bytes": replay.MAX_RECORD_BYTES,
            "max_depth": replay.MAX_RECORD_DEPTH,
            "schema_version": record.SCHEMA_VERSION,
            "rule_fields": [field.name for field in fields(Rules)],
            "ranks": list(RANKS),
            "actions": ACTION_NAMES,
            "models": {rank: record._model_record(rank) for rank in RANKS},
        },
    }))


if __name__ == "__main__":
    main()
