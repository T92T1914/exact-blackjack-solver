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

## Create a record from retained counts

Use `--unseen-counts` when you already have a rank tally:

```text
bj-advise T,4 T --unseen-counts 0,1,1,0,0,0,1,1,1,1 --json
```

Supply exactly ten nonnegative decimal integers in `A,2,3,4,5,6,7,8,9,T`
order. Surrounding ASCII whitespace and leading zeros are accepted. Empty
fields, signs, fractions, exponents, underscores, Boolean words, rank labels
and non-ASCII digits are rejected. `--unseen` remains the physical-card-list
alternative. The two options cannot be combined. Without `--json`, the command
prints the existing text advice and retained rank counts.

Counts include the dealer's reserved hidden hole and already exclude visible
cards. The command passes them directly to the engine without another
subtraction. Other unseen cards of a visible rank may remain counted. Zero is
a valid count, but an all-zero tally or an impossible post-peek hole produces
the existing state error. Validation cannot confirm your external bookkeeping.
`--decks` does not rescale or clamp supplied counts to fresh-deck maxima.

The existing rule and split options still apply. Keep cards in their dealt
order: the first card of a split hand is its split rank. `--hand-count` includes
completed hands in that round. Explicit-shoe advice and records compute one
decision with no fresh-shoe whole-game estimate. Raw JSON values and the
supported model remain unchanged. Counts cannot accompany `--table` or
`--replay`.

Save successful stdout as UTF-8 to a fresh file using byte-preserving capture
or your shell's byte-preserving redirection, keeping stderr separate. Then run:

```text
bj-advise --replay saved-decision.json --json
```

Creation syntax/state errors and arithmetic overflow exit 2 with an explanation
on stderr and no record on stdout. Replay retains its separate failure statuses
below. Python's integer conversion limit may reject a decimal token. No new
count maximum, numerical work limit or cache limit is imposed, and large
supported tallies can exceed arithmetic range or require substantial resources.

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

## Inspect and compare local records in the browser

The [project page](https://t92t1914.github.io/exact-blackjack-solver/) can inspect
one or two local schema-v1 decision files. Export a record through an installed
package, save the JSON output as UTF-8, then select it as record A. For example,
the six unseen cards keep this example small:

```text
bj-advise T,4 T --unseen 2,3,7,8,9,T --json
```

The existing Python example above also creates a saved file without shell
redirection encoding differences. The browser displays the complete dealt
order, dealer upcard, total and softness, split state, retained counts, every
rule and model declaration, schema/package labels and recorded answer. It
keeps integer counts exact and shows raw finite binary-float answer values
without display rounding. Supported recorded action codes include split `P`.

Selecting record B shows changed modeled inputs before recorded answer
differences. An action present in only one record is explicitly absent on the
other side, with no numeric delta. A changed input pair does not identify a
single cause, especially when several inputs changed. Matching supplied
values and package labels do not authenticate origin or establish numerical
correctness.

The page derives actions permitted by the admitted modeled state separately
from the supplied EV keys. It uses the exporter's default double/split buttons,
the retained unseen counts, dealt order and declared split/rule state. A total
of 21 permits stand only. Otherwise hit/double need a drawable card in addition
to the hidden hole, and split needs two. Double also requires two dealt cards
and permission after splitting. Frozen split aces, ace resplitting and the
shared hand cap retain the engine's existing eligibility rules. The first
dealt card remains the split rank. Counts are summed as exact integers without
removing visible cards again. External table buttons are outside this model.

All four action codes show their permitted status and supplied EV presence.
A supplied unavailable action, an omitted permitted action or an unavailable
recorded recommendation produces a warning. It does not reject the record or
replace the saved answer. Finite altered recommendations, margins and action
sets remain visible. The comparison shows each input's derived eligibility
before the raw recorded answer differences.

Eligibility does not establish that an action's EV can be calculated for the
supplied shoe. Dealer draw exhaustion, floating-point range and computation
resources remain separate engine questions. Browser admission/eligibility
checks do not recompute EVs or validate their numerical correctness. Focused
tests compare eligibility with the existing `best_action` branches while four
valuation routines are stubbed to zero. That is action-key parity, not an
independent numerical reference. Use `bj-advise --replay PATH --json` for
installed recalculation and
comparison with the engine. Browser inspection does not change the model or
provide a general error bound for split valuation.

Files and names remain in the current page session. Imports do not enter
share links, URL/history parameters, uploads or browser storage. Clearing one
or both records releases retained state. Reload clears all imports. Selecting
a replacement immediately clears the old result. A failed replacement leaves
that slot empty with an explanation, and an earlier slow read cannot restore
a replaced or cleared record. Bundled example links retain their existing
behavior. Local inspection also works when bundled example data cannot load.

The browser uses the existing 65,536 UTF-8 byte and eight-container depth
limits. It additionally refuses integer tokens longer than 4,300 decimal
digits before conversion, matching ordinary Python 3.11 JSON parsing. A Python
caller can configure a different integer parsing limit, so this is an explicit
browser representation limit, not a solver count maximum. Supported supplied
counts may exceed fresh-shoe maxima and floating-point arithmetic range. They
remain exact integers in the viewer. Payouts and recorded answers must convert
to finite binary floats. Integer-only fields reject floating tokens such as
`1.0` even when they have the same numerical value.

No-script delivery retains the static evidence and explains that local record
inspection needs JavaScript. Browser file admission limits do not bound work
or memory during installed engine recalculation.

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
