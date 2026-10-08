"""Test-only admission and eligibility parity, with all EV routines stubbed.

The action-key check is not independent numerical validation.
"""
from contextlib import ExitStack
import json
import sys
from dataclasses import fields
from unittest.mock import patch

from bj import ev, record, replay
from bj.core import ACTION_NAMES, RANKS, Rules


def main():
    cases = json.load(sys.stdin)
    outcomes = []
    permitted = []
    for case in cases:
        try:
            hand, up, unseen, rules, split, hands = replay._admit(
                replay._parse(bytes(case["bytes"])))
            status = "accepted"
            # Keep existing eligibility branches and replace every valuation.
            with ExitStack() as replacements:
                for name in ("_stand_ev", "_hit_ev", "_double_ev", "_split_total_ev"):
                    replacements.enter_context(patch.object(ev, name, return_value=0.0))
                _, values, _ = ev.best_action(hand, up, shoe=unseen, rules=rules,
                                              is_split_hand=split, hand_count=hands)
            permitted.append([action for action in ACTION_NAMES if action in values])
        except replay._UnsupportedRecord:
            status = "unsupported_record"
            permitted.append(None)
        except replay._InvalidRecord:
            status = "invalid_input"
            permitted.append(None)
        outcomes.append(status)
    print(json.dumps({
        "outcomes": outcomes,
        "permitted": permitted,
        "eligibility_scope": "best_action action keys with four EV routines stubbed to zero",
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
