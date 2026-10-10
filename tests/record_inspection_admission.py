"""Test-only admission and eligibility parity, with all EV routines stubbed.

The action-key check is not independent numerical validation.
"""
from contextlib import ExitStack
import json
import sys
from dataclasses import fields
from unittest.mock import patch

from bj import ev, late_surrender, record, replay
from bj.core import ACTION_NAMES, RANKS, Rules


def main():
    cases = json.load(sys.stdin)
    outcomes = []
    permitted = []
    for case in cases:
        try:
            saved = replay._parse(bytes(case["bytes"]))
            hand, up, unseen, rules, split, hands, double, pair = replay._admit(saved)
            status = "accepted"
            # Keep existing eligibility branches and replace every valuation.
            with ExitStack() as replacements:
                for name in ("_stand_ev", "_hit_ev", "_double_ev", "_split_total_ev"):
                    replacements.enter_context(patch.object(ev, name, return_value=0.0))
                _, values, _ = ev.best_action(hand, up, shoe=unseen, rules=rules,
                                              is_split_hand=split, hand_count=hands,
                                              can_double=double, can_split=pair)
            names = ACTION_NAMES
            if saved['schema']['version'] == record.SURRENDER_SCHEMA_VERSION:
                names = late_surrender.ACTION_NAMES
                if saved['state']['action_controls']['can_surrender']:
                    values['R'] = 0.0  # Eligibility only, not a terminal reward check.
            permitted.append([action for action in names if action in values])
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
        "eligibility_scope": "best_action action keys with four EV routines stubbed to zero; "
                             "schema 4 terminal R from admitted current permission",
        "contract": {
            "max_bytes": replay.MAX_RECORD_BYTES,
            "max_depth": replay.MAX_RECORD_DEPTH,
            "schema_version": record.SCHEMA_VERSION,
            "controlled_schema_version": record.CONTROLLED_SCHEMA_VERSION,
            "common_schema_version": record.COMMON_SCHEMA_VERSION,
            "surrender_schema_version": record.SURRENDER_SCHEMA_VERSION,
            "resplit_schema_version": record.RESPLIT_SCHEMA_VERSION,
            "ace_resplit_schema_version": record.ACE_RESPLIT_SCHEMA_VERSION,
            "rule_fields": [field.name for field in fields(Rules)],
            "ranks": list(RANKS),
            "actions": ACTION_NAMES,
            "surrender_actions": late_surrender.ACTION_NAMES,
            "models": {rank: record._model_record(rank) for rank in RANKS},
            "surrender_models": {rank: record._surrender_model_record(rank, 100000)
                                 for rank in RANKS},
            "resplit_models": {rank: record._resplit_model_record(rank, 100000)
                               for rank in RANKS},
            "ace_resplit_models": {rank: record._ace_resplit_model_record(rank, 100000)
                                   for rank in RANKS},
        },
    }))


if __name__ == "__main__":
    main()
