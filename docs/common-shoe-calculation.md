# Calculate two split hands from one shared shoe

After [installing the engine and preparing a local folder](local-calculation.md),
save the [small common-shoe request](../examples/common-shoe-request.json) as
`common-shoe-request.json`. Use an installed build that includes this guide.

```sh
bj-calculate common-shoe-request.json --output-dir common-attempt --wall-seconds 5
bj-advise --replay common-attempt/result/decision.json --json
```

The first command captures the request, prices the present alternatives in one
owned worker and publishes a complete decision and receipt. The second admits
that saved record, selects its recorded model and state cap, and recomputes the
decision without using the saved EVs as inputs. The attempt directory must be
new. A prior attempt is preserved rather than overwritten.

The existing source-archive installation route uses ordinary HTTPS and pip:

```sh
python -m pip install https://github.com/T92T1914/exact-blackjack-solver/archive/refs/heads/main.zip
```

This is a floating `main` archive. It requires network access and pip's packaging
backend support, and it does not pin a reviewed revision or install from a package
registry. For a reproduced release, use the wheel built from the identified
reviewed source. The [local calculation guide](local-calculation.md) describes
installation, outcome files and supported platforms.

## What this model changes

The ordinary solver retains its independent-hand split approximation and shared
resplit-slot accounting. This explicitly selected model carries each visible
draw into a common remaining shoe, retains the first completed hand's exposure
while choosing the second hand's actions, and settles both hands against one
dealer outcome. Player choices average hidden-hole information before choosing
an action. They never get the actual hole card.

The first hand finishes before the second receives its additional card. This
deal order is part of the model. It does not represent a table that deals both
additional split cards before the first decision. A total of 21 closes the
hand. A double takes exactly one card and stands with two original-wager units
at risk. Split aces take one card each, cannot double, and receive ordinary
one-unit settlement rather than the natural premium.

The small example has two visible fives against T. Its seven unseen cards are
7,7,8,9,T,T,T. Existing independent physical-card enumeration with rational
arithmetic gives the split alternative an expected net return of `-9/7`
original-wager units. The deliberately illegal policy that learns the actual
hole before choosing gives `-107/84`. This is a useful information-boundary
witness. It does not assert that splitting is the recommendation or that either
value applies to an arbitrary shoe.

All possible continuations in the declared domain are enumerated using binary
floating-point arithmetic. A completed calculation is exact for that finite
mathematical model in this numerical sense. It is not symbolic exactness, a
full-game proof, a general split-error bound or a wagering advantage claim.

## Explicit request and coverage

Version 2 requires the model identifier and a positive integer work cap:

```json
{
  "schema": {"name": "solver-calculation-request", "version": 2},
  "model": {"name": "common_shoe_two_hand", "version": 1},
  "limits": {"max_states": 100000},
  "rules": {"max_hands": 2, "resplit_aces": false, "hit_split_aces": false},
  "input": {
    "cards": ["5", "5"],
    "dealer_up": "T",
    "unseen_counts": [0, 0, 0, 0, 0, 0, 2, 1, 1, 3],
    "is_split_hand": false,
    "hand_count": 1,
    "can_double": true,
    "can_split": true
  }
}
```

The retained count order is A,2,3,4,5,6,7,8,9,T. Counts already exclude both
visible pair cards and the dealer upcard, and include one reserved hidden hole.
They are passed once, without another subtraction. Internal reference order
differs, so the engine translates counts by rank name.

The supported input is an initial two-card pair with exactly one current hand,
`is_split_hand=false`, `hand_count=1` and 3 through 20 unseen cards. Require
`max_hands=2`, `resplit_aces=false` and `hit_split_aces=false`. Both S17/H17 and
DAS choices are supported. The existing post-peek, no-surrender,
any-two-card-double and collapsed-ten restrictions still apply. The complete
normalized rule set is captured and recorded. Unsupported settings refuse
before pricing.

`can_double` and `can_split` restrict only the current alternatives. Disabling
the present double does not disable DAS within a chosen split. Disabling the
present split leaves the declared common model and cap in the record, but no
split value is calculated. Root stand, hit and double use the existing
one-hand arithmetic. No approximate split is calculated as an intermediate
answer. New records use schema 3 and always store both controls explicitly.

Within the joint split calculation, any admitted branch that needs an
unavailable player or required dealer card refuses the calculation, including
a branch that would not ultimately win the action comparison. The joint
calculation does not omit that branch, force a stand, reshuffle, invent a payoff
or fall back to approximation. Root stand, hit and double retain the accepted
single-hand behavior, including standing after the last legal player draw.
Their required dealer draws still refuse exhaustion. At most 20 cards is an
input ceiling, not a promise that every supplied composition can finish.

## Actual work and operational limits

The default and largest admitted state cap is 100,000. A smaller positive
integer is supported. One scoped counter covers actual uncached state-body
entries across root draw, hit and double, root dealer distribution and
recursion, and joint draw, play, settlement and dealer recursion. It refuses
the first entry beyond the cap before that state body proceeds. The old
four-family reference counter alone is not reported as whole-request work.

The completed receipt contains `work.limit`, `work.states`,
`work.attempted_states` and `work.state_counts`. On complete computation the
two entry counters agree. A genuine state refusal reports the admitted entry
count and the first refused attempt, so a cap of one reports one admitted
entry and two attempted entries. Entry counts do not say that every entered
state finished. State families identify root and joint work separately.

Cached results can reduce actual uncached work in direct API calls and replay.
Every owned calculation starts in a fresh fixed worker. The counter is scoped
to the explicit common call and inactive during ordinary legacy calls. Its
finite fanout and small admitted shoe give an algorithmic work bound. A state
count is not a measured byte, RSS or seconds limit. The joint arithmetic also
retains its cooperative ten-second check at state entry and after the final
calculation. An incomplete cooperative-limit outcome produces no record.

The [existing supervisor](local-calculation.md#select-execution-policy)
still owns worker startup, finite wall policy, transport and retirement.
Windows requires a Job cap on aggregate committed memory before pricing. It
does not cap physical RSS. Linux is wall-only with uncapped memory and the
fixed direct worker's no-descendants contract. Wall expiry starts retirement
with the existing five-second cleanup allowance. It does not promise that all
cleanup ends at the original worker deadline.

| Outcome | Exit | Common-model meaning |
|---|---|---|
| `completed` | 0 | Entire admitted calculation finished and committed decision/receipt after retirement |
| `invalid_request` | 2 | Malformed request, unsupported model selection, domain, rules or state cap before pricing |
| `unsupported_policy` | 3 | Required operational policy could not be established |
| `resource_limited` | 4 | Actual state cap, joint cooperative limit, memory/recursion or bounded transport prevented completion |
| `calculation_error` | 5 | Admitted calculation could not be priced, including an exhausted branch |
| `worker_failed` | 6 | Worker message, identity, exit or computation failure outside the stated calculation outcomes |
| `cleanup_failed` | 7 | Otherwise completed result withheld because owned retirement was unresolved |
| `delivery_failed` | 8 | Capture or result/report delivery failed |
| `timed_out` | 124 | Worker wall deadline initiated retirement |
| `cancelled` | 130 | Cancellation won before the result commit |

A late cancellation cannot relabel a committed result. A refused or interrupted
attempt has no ordinary completed record and does not replace earlier successful
outputs. Inspect the attempt's outcome and cleanup fields before reusing any
result. Work diagnostics describe that execution, separately from the numerical
record's model and state limit.

## Reuse and compare

The schema 3 decision declares common-shoe coverage, deal order, split-ace and
exhaustion rules, and the cap needed for replay. Replay chooses those declared
semantics. It compares finite binary-float values, action identity, permitted
keys and raw margin with exact numerical equality and no tolerance. Differences
remain visible even near ties. Saved answers do not enter the calculation.

Direct replay enforces the recorded common model's algorithmic cap. It does
not establish an owned worker, Job memory cap or wall supervisor. Legacy schema
1/2 replay retains its existing caller-owned, unbounded behavior. Old records
continue to select their approximate split model, rather than being silently
reinterpreted as a common-shoe result.

Select `common-attempt/result/decision.json` in the existing
[local record inspector](https://t92t1914.github.io/exact-blackjack-solver/).
Select an older approximate record as the other input to inspect model identity
and coverage before raw EV differences. Common fields and absent legacy fields
are compared in both directions. Imported files and names stay in the page
session, with no upload or browser-storage persistence. The inspector validates
representation and derives modeled action eligibility. It does not recompute
or independently validate the numerical answers.

For a Python caller, the additive API is:

```python
from dataclasses import replace
from bj.core import STANDARD
from bj.record import common_shoe_record

saved = common_shoe_record(
    ["5", "5"], "T", replace(STANDARD, max_hands=2),
    shoe=(0, 0, 0, 0, 0, 0, 2, 1, 1, 3), max_states=100000,
)
```

That direct call has the state cap but no worker, wall or memory supervisor.
Use the installed calculation command for owned operational policy. Existing
`decision_record`, `best_action`, ordinary CLI entry behavior and old record
bytes keep their declared approximate semantics.

## Numerical and consumer evidence

The implementation reuses the existing joint reference. Its agreement with
that reference is integration regression evidence. The existing physical-card
permutation and Fraction tests remain the independent mathematical checks.
They cover hidden information, common settlement, peek exclusions, H17, split
aces and branch exhaustion. The additional deterministic seven-eights case
checks two ordinary winning hands without DAS and two doubled winning hands
with DAS. Seven eights cover every admitted branch, including a first-hand
bust followed by a surviving second hand and the required dealer draw.

The installed safeguard exercises genuine completed common requests, replay,
whole-root state refusal and exhaustion. Its controlled timeout/cancellation
witnesses replace only the private pricing function after the input gate and
exercise owned retirement. They are not computation-stress measurements or
proof of performance for all admitted shoes. The existing generated-browser
checks can use actual installed common records on desktop and mobile. The
[retained joint study](joint-split.md) and its invalid first attempt remain
unchanged historical evidence.
