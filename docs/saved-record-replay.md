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

An explicitly selected [common-shoe calculation](common-shoe-calculation.md)
emits schema 3. Replay selects that record's two-hand model and whole-request
state cap. Existing schema 1 and 2 records keep their declared approximate
split semantics. Saved EVs remain comparison data for every supported model.
An explicitly selected [late-surrender calculation](late-surrender-calculation.md)
emits schema 4 for one original initial two-card hand below 21. Replay uses its
current surrender permission, retained counts, coverage and root-only state
cap. Older models remain outside surrender coverage.

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

## Select the round's hand cap

Use `--max-hands N` for the maximum hands the rules allow in a round.
`--hand-count` is the number already created, including completed hands.
Omitting the cap keeps the existing default of four. For a two-hand limit:

```text
bj-advise T,T 7 --unseen-counts 1,0,0,0,0,0,0,0,0,5 --max-hands 2 --json
bj-advise T,T 7 --unseen-counts 1,0,0,0,0,0,0,0,0,5 --max-hands 2 --split-hand --hand-count 2 --json
```

The first command describes an unsplit hand below the cap. The second
describes a hand after splitting, at the cap, so SPLIT is unavailable.
Both retain the supplied counts directly. Do not change the current hand
count to imitate a different rule cap. Cards stay in dealt order, with the
first card identifying a split hand's original rank.

The cap must be a positive ASCII decimal integer. Surrounding ASCII
whitespace and leading zeros are accepted. Zero, signs, fractions, exponents,
underscores, Boolean words and non-ASCII digits or whitespace are rejected.
A cap of one permits an unsplit hand and prevents splitting. A split hand
requires at least two created hands and cannot fit that cap. Invalid input
exits with status 2, an explanation on stderr and no record on stdout.

Text advice, JSON records and `--table` use the selected cap. JSON keeps
the complete rules and raw values. Save successful stdout as described above,
then replay without overrides. Explicit `--max-hands` cannot accompany
`--replay`, even when it equals the default. The saved record supplies its cap.

No new upper cap or numerical-work bound is imposed. Python's integer
conversion limit still applies. Larger supported caps can require more work,
and the existing independent-hand and greedy resplit-budget approximations
remain unchanged. No general split-error bound follows from selecting a cap.

## Declare the split-ace rules

Use `--resplit-aces` when your declared rules allow ace resplitting and
`--hit-split-aces` when a split ace may receive more cards. Both default to
false, are independent, and can be combined or repeated. They take no value.
For a small split pair with three retained unseen cards:

```text
bj-advise A,A T --split-hand --hand-count 2 --max-hands 3 --unseen-counts 0,0,0,0,0,0,0,0,1,2 --resplit-aces --hit-split-aces --json
```

These are table and continuation rules, distinct from the current
`--no-double` and `--no-split` exclusions below. They cannot restore an
alternative blocked by doubling-after-split rules, the hand cap, remaining
cards or completed 21. Keep dealt order: the first card identifies the split
rank. Without hitting enabled, a split ace receives one card and a split-ace
hand with more than two cards is invalid. A split 21 does not become a natural.

The flags work with text advice, JSON and `--table`. The chart caption names
enabled ace resplitting and the selected hitting rule. Supplied counts still
include the reserved hole and already exclude visible cards. Choosing a flag
declares your rules; it does not verify permissions at an external table.

Save successful stdout as described above and replay without either flag:

```text
bj-advise --replay saved-decision.json --json
```

Replay takes both rules from the saved record and refuses overrides before
reading it. Ace flags alone retain version 1. Current-choice exclusions still
produce version 2. Default outputs, raw values and the existing independent-hand
and greedy shared-budget split approximation remain unchanged. No general
split-error bound, whole-round optimality or numerical-work limit is added.

## Declare the natural payout

Use `--blackjack-payout N` for the net payout per original wager on an
unsplit two-card natural. `1.5` means 3:2 and `1.2` means 6:5. The stake is
not included in N. Omitting the option keeps the existing 1.5 default.
Declare a 6:5 natural with one retained unseen card:

```text
bj-advise A,T 9 --unseen-counts 0,0,0,0,0,0,0,0,1,0 --blackjack-payout 1.2 --json
```

Decimal and scientific spellings such as `1.25`, `.5`, `1.` and `125e-2`
are accepted, with optional signs and surrounding ASCII whitespace. Ratios
such as `3:2`, fractions, expressions, underscores, Boolean words, Unicode
digits or whitespace, embedded whitespace, NaN and infinity are rejected.
The converted value must be finite and not less than zero. Invalid input
exits 2 with an explanation on stderr and no record on stdout.

Conversion uses binary floating point, not exact decimal arithmetic.
Underflow can become zero. Signed zero is retained, including a negative
tiny spelling that underflows to it. Use equals syntax for negative
spellings, for example `--blackjack-payout=-0.0` or
`--blackjack-payout=-1e-9999`. Replay's numeric equality treats both zero
signs as equal, so agreement does not prove bitwise identity.

Text, JSON and the existing chart caption use the declared payout. A split
21 receives ordinary settlement, not the natural premium. Current-choice
exclusions still select version 2 independently of payout. Retained counts
are passed once, without another visible-card subtraction.

Save successful stdout as described above, then replay without an override:

```text
bj-advise --replay saved-decision.json --json
```

Every explicit payout conflicts with replay before file reading, even 1.5
or signed zero. The saved record supplies its rules. No upper payout cap or
new work limit is imposed. Large finite values can exceed downstream
arithmetic range. Insurance, unsupported rules and split approximations
remain unchanged.

## Restrict the current choices

Use `--no-double` or `--no-split` when the current decision must exclude that
alternative. They can be combined or repeated. For a small retained pair:

```text
bj-advise T,T 7 --unseen-counts 1,0,0,0,0,0,0,0,0,5 --max-hands 2 --no-double --no-split --json
```

The controls restrict only the present alternatives. They do not change the
rules, later continuation policy or split approximation. In particular,
`--no-das` is the separate rule about doubling after splitting. Existing cards,
retained counts, hand cap and split-state inputs keep their meaning. Neither
disable can accompany `--table` or `--replay`; replay takes its controls from
the saved state and refuses overrides before reading the file.

The public `advise`, `decision_record` and `decision_json` wrappers accept
keyword-only `can_double` and `can_split`, both defaulting to `True`. They
require genuine booleans. For example:

```python
from bj.record import decision_json

text = decision_json("T,T", "7", shoe=(1, 0, 0, 0, 0, 0, 0, 0, 0, 5),
                     can_double=False, can_split=False)
```

True still intersects with the hand's existing eligibility. It cannot restore
double after a hit, split at the cap, frozen split-ace draws or another choice
at 21. The recommendation and margin use only the remaining alternatives.
Restricted text advice names the disabled choices and computes no fresh-shoe
whole-game estimate, even without explicit counts.

Default and explicit true/true exports retain version 1 bytes and contain no
control field. Disabling either choice produces version 2, with this state
field after `hand_count` and before `shoe`:

```json
"action_controls": {"can_double": false, "can_split": false}
```

Version 2 requires exactly those two boolean keys. Readers also accept an
explicit true/true version 2 declaration. Replay preserves the stored state
and recomputes once with effective controls, passing retained counts directly
without another visible-card subtraction. Version 1 implies true/true without
adding fields to the saved state. These declarations do not establish which
buttons an external table offers or authenticate the record.

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
meaning: `S` stand, `H` hit, `D` double and `P` split. Only schema 4 supports
`R` surrender in its separate initial-hand family. P is outside that family.

The comparison policy is `exact_binary_float`, with zero absolute and relative
tolerance. Finite saved numeric values are interpreted as Python binary
floats and compared by numerical equality. This is not a byte or signed-zero
comparison. Action identity is compared exactly even when the values differ
by a very small amount or the margins agree. The report and text output keep
raw numbers, so display rounding cannot hide a near tie. Replay uses the
existing engine's action selection, including its tie behavior, without a
new ranking or tolerance policy.

`recorded_package`, `current_package` and `package_version_matches` describe
the version labels. A different package-version label does not make either
supported schema version unsupported and does not fetch or install that version. Neither
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
| `resource_limited` | 4 | Memory/recursion exhaustion, a recorded bounded-model state cap, or the common model's cooperative limit prevented completion. |
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

Supported replay is the `blackjack-decision` schema, versions 1, 2, 3 and 4. The importer
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
ten-value ranks, original-wager units and the selected split model. Schemas 1
and 2 retain the existing approximation. Schema 3 requires its common-shoe
coverage, deal order, split-ace/exhaustion declarations and recorded state cap.
Schema 4 requires its explicit post-peek late-surrender identity, original
initial two-card hand below 21, no split, supplied three through twenty unseen
cards, current surrender control, terminal half-loss, no later surrender and
recorded root-only cap. S/H/D retain the ordinary last-draw standing convention
and required dealer-settlement exhaustion refusal. Surrender in schemas 1/2/3,
no-peek, restricted-double and distinct-ten rules remain refused. Saved EVs,
recommendations and margins are historical comparison
data. Known action-code sets may differ from the current legal set, and a
finite altered saved answer remains visible as a difference after calculation.

## Inspect and compare local records in the browser

The [project page](https://t92t1914.github.io/exact-blackjack-solver/) can inspect
one or two local version 1, 2, 3 or 4 decision files. Export a record through an installed
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
without display rounding. Older models support split P. Schema 4 supports
R in its explicit initial-hand family and excludes P. Admission does not widen
an older schema's action vocabulary.

Selecting record B shows model compatibility and changed modeled inputs before
recorded answer differences. Schema 3 coverage fields absent from an older
model remain visible in either comparison direction. Schema 4's initial-only
late-surrender coverage is incompatible with ordinary and common split models
in both directions. Comparing different mathematical families does not
attribute their EV differences to a single input change. Same-family current
permission, retained-count and cap changes remain visible input differences.
An action present in only one record is explicitly absent on the
other side, with no numeric delta. A changed input pair does not identify a
single cause, especially when several inputs changed. Matching supplied
values and package labels do not authenticate origin or establish numerical
correctness.

The page derives actions permitted by the admitted modeled state separately
from the supplied EV keys. It displays both effective current action controls,
distinguishing implicit version 1 defaults from stored version 2/3 booleans.
Schema 4 stores `can_surrender` beside its current double and false split
controls. Older models have effective surrender permission false and no stored
surrender control. The viewer distinguishes that absence from an explicit
false declaration without adding fields to old records.
Version 1 and declared true/true version 2 have equal control inputs in either
comparison direction, with their schema difference shown as metadata.
It uses those effective controls,
the retained unseen counts, dealt order and declared split/rule state. A total
of 21 permits stand only. Otherwise hit/double need a drawable card in addition
to the hidden hole, and split needs two. Double also requires two dealt cards
and permission after splitting. Frozen split aces, ace resplitting and the
shared hand cap retain the engine's existing eligibility rules. The first
dealt card remains the split rank. Counts are summed as exact integers without
removing visible cards again. External table buttons are outside this model.

Each model's four action codes show their permitted status and supplied EV presence.
For schema 4 these are S/H/D/R, with R's initial eligibility and current
permission derived without pricing. Older models retain H/S/D/P. Mixed
comparisons show the union, including unavailable or absent R on the old side.
A deliberately disabled action absent from EVs is not an omission.
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
valuation routines are stubbed to zero, plus schema 4's admitted current R
permission. That is action-key parity, not an
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

Legacy production models have no work, time or memory limit. The explicit
schema 3 common model adds its recorded whole-request uncached-state cap and
the joint calculation's cooperative limit. Schema 4 adds a root-only cap and
no split cooperative limit. A failed offered price yields no completed result,
even if R's constant value is already known. Process-wide memo tables have no
eviction limit and remain owned by the caller's process.
Replay does not create workers, clear shared
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
