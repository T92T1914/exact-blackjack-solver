# Recompute a saved decision

`bj-advise --replay PATH` validates a supported saved JSON record, reconstructs
its modeled inputs and calculates the decision through the installed solver.
The report shows the saved answer beside the new answer. Add `--json` for a
machine-readable report with the same status and comparison.

```text
bj-advise --replay saved-decision.json
bj-advise --replay saved-decision.json --json
```

The saved record supplies the cards, dealer upcard, remaining counts, every
rule and the split state. Replay cannot be combined with positional cards,
`--table`, or hand/rule options. Existing advice and `--json` export commands
keep their behavior. Replay calculates one decision and no whole-game value.

For a small installed-package example, copy
[`examples/replay_saved_decision.py`](../examples/replay_saved_decision.py)
outside the checkout and run it with the Python environment containing the
installed package:

```text
python replay_saved_decision.py saved-decision.json
bj-advise --replay saved-decision.json --json
```

The example creates a new UTF-8 file using exclusive creation, then replays it
through the public API. Choose an unused filename. It never replaces an
existing record. Its six unseen cards keep the calculation small. A large
otherwise-supported shoe can require substantially more work and memory.

## Public API and report

```python
import json
from pathlib import Path
from bj.replay import replay_file, replay_json

report = replay_file(Path("saved-decision.json"))
print(report["status"])
print(json.dumps(report, indent=2, allow_nan=False))

text = Path("saved-decision.json").read_bytes()
same_report = replay_json(text)  # UTF-8 bytes or a JSON string.
assert same_report == report
```

Both functions return a JSON-compatible dictionary. `modeled_input` retains
the admitted state, rules and model. `recorded` is the saved decision.
`recomputed` is the newly calculated decision. `comparison` contains the
saved and current legal-action sets, every action's raw EV, recommendation
and raw margin, each with an explicit `matches` flag. A missing action has a
null value on that side and a false match. Action codes retain their existing
meaning: `S` stand, `H` hit, `D` double and `P` split.

The comparison policy is `exact_binary_float`, with zero absolute and relative
tolerance. Finite saved numeric values are interpreted as Python binary
floats and compared by numerical equality. This is not a byte or signed-zero
comparison. Action identity is compared exactly even when the values differ
by a very small amount or the margins agree. The report and text output keep
raw numbers, so display rounding cannot hide a near tie. Replay uses the
existing engine's action selection, including its tie behavior, without a
new ranking or tolerance policy.

`recorded_package`, `current_package` and `package_version_matches` describe
the version labels. A different package-version label does not make schema
version 1 unsupported and does not fetch or install that version. Neither
matching labels nor agreement authenticate a record's origin. Recalculation
by the same engine is a reproducibility check. Independent mathematical
validation remains a separate question.

## Outcomes and command exit status

| Report status | Exit | Meaning |
| --- | --- | --- |
| `agreement` | 0 | Calculation completed and all compared fields agree. |
| `differences` | 1 | Calculation completed, with a different legal-action set, EV, recommendation or margin. |
| `invalid_input` | 2 | JSON or a required representation/consistency check failed before calculation. |
| `unsupported_record` | 3 | The declared schema, rules, units or model is outside supported replay. |
| `resource_limited` | 4 | `MemoryError` or calculation recursion exhaustion prevented completion. |
| `calculation_error` | 5 | An admitted state could not be calculated, such as dealer draw exhaustion or floating-point overflow. |
| `io_error` | 6 | The local file could not be read. |
| `interrupted` | 130 | A `KeyboardInterrupt` stopped reading, admission or calculation. |

A supported supplied count can exceed the engine's floating-point arithmetic
range. That produces `calculation_error`, with the admitted input and saved
answer retained. Admission does not impose a new count maximum.

An incomplete replay has `recomputed` and `comparison` set to null. When
admission completed, it still includes the modeled input and saved answer.
The `error` field describes the reported exception. Invalid or unsupported
input has no admitted answer. CLI option conflicts remain argparse usage
errors with exit 2 and an explanation on stderr. Otherwise `--replay --json`
prints one JSON object on stdout, including errors, with no progress chatter.
API callers inspect `status` directly. `bj.replay.EXIT_STATUSES` exposes the
command's mapping.

## Admission and retained counts

Supported replay is the `blackjack-decision` schema, version 1. The importer
requires every declared field and rejects unknown fields at every object,
duplicate JSON keys, nonfinite values, Boolean numeric parameters and
inconsistent derived hand totals or softness. Cards must be normalized ranks
in their original dealt order. The rank-order list must exactly match
`A,2,3,4,5,6,7,8,9,T`. The first card of a split hand remains the split rank,
so reversing dealt cards is not a general replay invariant.

Input is limited to 65,536 UTF-8 bytes and eight nested JSON containers. File
reading takes at most that limit plus one byte to detect excess size. Depth
is checked before the JSON decoder allocates nested objects. These are
admission limits for this small format, not calculation resource limits.

Counts already exclude visible cards and include the hidden dealer hole.
Replay passes the retained counts directly to the solver, exactly once. It
never subtracts visible cards again or infers a specific hole card. For
`fresh_minus_visible`, admission checks counts against the declared fresh
shoe for consistency. Execution still uses the saved counts. For
`supplied_unseen`, counts need not fit the fresh-deck maxima. A consistently
changed supported state is calculated normally and compared with its saved
answer.

The importer checks the declared post-peek hidden-hole model, collapsed
ten-value ranks, original-wager units and the existing split approximation.
Unsupported no-peek, surrender, restricted-double or distinct-ten rules are
refused. Saved EVs, recommendations and margins are historical comparison
data. Known action-code sets may differ from the current legal set, and a
finite altered saved answer remains visible as a difference after calculation.

## Resource ownership and evidence

The production solver has no work, time or memory limit. Its process-wide
memo tables have no eviction limit and remain owned by the caller's process.
Replay preserves that behavior and does not create workers, clear shared
caches, launch a supervisor or guarantee recovery after an operating-system
kill. A reported `MemoryError`, `RecursionError` or `KeyboardInterrupt` is
distinct from a numerical difference. Caller-selected execution limits still
apply. See the [cache guide](caches.md) for explicit cache inspection/reset
and the limits of those operations.

The immutable test fixture `saved-decision-v1-7a38141.json` was emitted on
October 8, 2026 from baseline source `7a38141`, which predates the replay
consumer. Its bytes are hash-pinned and are not regenerated by replay tests.
It preserves the supported old schema, without claiming a historical emission
date or authenticated authorship. Focused tests reuse the existing independent
physical-deal references for tiny shoes, plus admission faults, changed
answers, split state, source-file preservation and CLI compatibility. These
constructed checks do not establish a full-shoe error bound for split.
