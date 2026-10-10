# Calculate an initial late-surrender decision

Install an engine build containing this guide through the existing
[source-archive or reviewed-wheel route](local-calculation.md). Save the
[small request](../examples/late-surrender-request.json) as
`late-surrender-request.json` in a local folder. A development checkout is
unnecessary at runtime.

```sh
bj-calculate late-surrender-request.json --output-dir late-attempt --wall-seconds 5
bj-advise --replay late-attempt/result/decision.json --json
```

The first command captures the request, prices every offered alternative in
one owned disposable worker, and retains a decision and receipt after
completion and retirement. The second admits that decision's model and
retained inputs, recomputes through the installed engine, and explains
agreement or differences. The output directory must be new. Existing attempts
are preserved.

Select `late-attempt/result/decision.json` in the existing
[local record inspector](https://t92t1914.github.io/exact-blackjack-solver/).
The request and attempt receipt are separate files, not decision records.
The inspector admits and displays saved values without recomputing them,
uploading local files, or authenticating their origin.

## The selected family

`post_peek_late_surrender`, version 1, supports one original initial
two-card hand below 21, after the dealer-natural condition has been resolved
negatively. The hole remains concealed. Under an ace upcard it cannot be T,
under T it cannot be A, and under two through nine no rank is excluded.
Player choices average the surviving hidden worlds before selecting an action.

The caller declares that this is the initial decision and supplies current
surrender permission. Two visible cards do not prove that no previous action
occurred. Model admission does not observe a table or establish that an
external table offers surrender.

An offered R ends the original wager at exactly `-0.5` net units, takes no
additional stake and draws no card. S, H and D retain the existing one-hand
arithmetic. H takes a card and later chooses only hit or stand. Those later
choices never offer surrender or double. D takes exactly one card, then stands
at two original-wager units. Split, resplit, natural, already-hit and later
surrender decisions are outside this family.

The selected timing and half-wager settlement follow the inspected
[Massachusetts Gaming Commission rules dated February 11, 2019](https://massgaming.com/wp-content/uploads/RULES-Blackjack-2-11-19.pdf),
Sections 6(j), 8 and 12(b), together with the operator's
[GameSense guide](https://www.mgmresorts.com/en/gamesense/guide-to-blackjack.html).
These support a named conditional subset. They do not establish universal
current table rules or availability.

## Supply the request

Request schema 3 selects the family explicitly:

```json
{
  "schema": {"name": "solver-calculation-request", "version": 3},
  "model": {"name": "post_peek_late_surrender", "version": 1},
  "limits": {"max_states": 100000},
  "rules": {"max_hands": 1, "surrender": true, "resplit_aces": false, "hit_split_aces": false},
  "input": {
    "cards": ["T", "6"],
    "dealer_up": "T",
    "unseen_counts": [0, 0, 0, 0, 0, 0, 0, 0, 0, 3],
    "is_split_hand": false,
    "hand_count": 1,
    "can_double": true,
    "can_split": false,
    "can_surrender": true
  }
}
```

The ten counts are in A,2,3,4,5,6,7,8,9,T order. They already exclude the
visible player cards and dealer upcard, and include the concealed reserved
hole. They are passed once. The engine does not subtract the visible cards
again or infer their history. Require three through twenty unseen cards,
exactly two player cards below 21, `is_split_hand=false`, `hand_count=1`,
`can_split=false` and `max_hands=1`.

Rules require `peek=true`, `surrender=true`, `double_any_two=true`,
`tens_are_pairs=true`, `resplit_aces=false` and `hit_split_aces=false`.
S17 and H17 are both supported. Omitted rule fields receive the existing typed
defaults, and the captured request expands all effective fields. The natural
and insurance payout fields remain retained rules, although this restricted
family prices neither settlement. Unknown fields or unsupported domains
refuse before pricing.

`can_double` and `can_surrender` must be booleans. False removes only that
current alternative. `can_surrender=false` keeps this explicit family and its
table-level surrender setting while leaving no R value in the decision.
Unavailable actions are absent, not zero. Current restrictions do not change
H's continuation policy or any remaining price.

For the example, the dealer always settles at twenty. Standing loses one
unit, a hit busts for one unit, and a double busts for two. R loses half a unit,
so the complete action set is S=`-1`, H=`-1`, D=`-2`, R=`-0.5`, with R selected
and a margin of `0.5`. This constructed depleted shoe is an independent tiny
arithmetic example, not evidence about an arbitrary shoe or live play.

## Work and failure boundaries

`max_states` is an integer from 1 through 100,000. One scoped cap covers actual
uncached entries in root draw, hit, double, dealer distribution and dealer
recursion. R is a constant terminal settlement and opens no recursive family.
There is no joint split work or split cooperative deadline in this model.
The first state beyond the cap is refused before its body executes.

The completed receipt contains `work.limit`, `work.states`,
`work.attempted_states` and `work.state_counts`. The two entry counters agree
on completion. A genuine cap refusal retains one extra attempted entry. For
example, the small request with `max_states=1` enters one dealer-distribution
state and refuses the second attempted state. Cache reuse can reduce these
counts in direct API or replay calls. Owned calculations start with a fresh
worker. Entry counts describe work, not bytes, physical RSS or elapsed time.

The [existing execution policy](local-calculation.md#select-execution-policy)
applies. Windows requires the owned Job's aggregate committed-memory cap,
not an RSS cap. Linux remains wall-only with uncapped memory. The worker's
wall expiry starts retirement, with a separate cleanup allowance. This is
not a promise of exact command duration.

Every offered price must finish, even when R's constant value is already
known. If S/H/D reaches an unavailable required dealer draw, the whole
attempt is a calculation error. A state cap, timeout, cancellation, failed
worker or unresolved retirement produces no accepted decision. There is no
fallback to R, omitted offered branch, invented settlement or approximation.
Three through twenty cards is an admission range, not a completion guarantee
for every composition.

S/H/D preserve the existing depleted-shoe convention: after the last legal
player draw, only standing remains. Dealer settlement must still finish with
the remaining cards. A total of 21 closes the hand. These are explicit model
semantics, separate from the strict exhaustion convention in joint splitting.

All finite continuations are enumerated using binary floating-point
arithmetic. This is exact enumeration of the declared finite model in that
numerical sense. It is not symbolic arithmetic, full-shoe or full-game
coverage, a wagering advantage claim, or support for early/no-peek surrender,
insurance, splitting, continuation surrender or every table variation.

## Keep, replay and compare the result

The completed schema 4 record stores all three current controls, supplied
counts, complete rules, initial-only coverage, terminal half-loss, absence of
later surrender, ordinary last-draw behavior and the recorded state cap.
The producer ranks raw values in S,H,D,R order. An exact R tie preserves the
previous available action, and the raw margin is highest minus second-highest
offered value. No epsilon or display rounding changes ranking.

Replay takes these inputs from the record and accepts no rule or control
overrides. It calculates all offered values and compares them, action keys,
recommendation and margin with exact finite binary-float equality. Altered
saved answers remain comparison data. Matching package labels or replay
agreement do not authenticate origin or independently prove the mathematics.
Direct replay enforces the recorded state cap but creates no owned worker,
wall supervisor or memory cap. Its caches remain caller-owned.

In the inspector, compare two schema 4 results to inspect changed controls,
retained counts, rules or cap before their raw answers. Compare with an older
ordinary or common-shoe result to see incompatible mathematical families in
either direction. An older record has effective surrender permission false,
and no stored surrender control. The viewer displays that missing field
separately from an explicit false declaration. R's absence has no numeric
delta and never becomes a zero value.

Existing request schemas 1/2 and record schemas 1/2/3 retain their historical
model, action vocabulary and surrender refusal. Ordinary `bj-advise` exports
retain their behavior. New surrender records come from this explicitly
selected calculation or the additive API, not an ordinary advice flag.

```python
from dataclasses import replace
from bj.core import STANDARD
from bj.record import late_surrender_record

rules = replace(STANDARD, surrender=True, max_hands=1)
saved = late_surrender_record(("T", "6"), "T", rules,
                             shoe=(0, 0, 0, 0, 0, 0, 0, 0, 0, 3),
                             can_double=True, can_surrender=True,
                             max_states=100000)
```

The direct API requires explicit rules and shoe and uses caller-owned
execution. Use `bj-calculate` when the accepted owned-process policy is
needed. See the [outcome guide](local-calculation.md#completion-cancellation-and-failure)
and [saved-record guide](saved-record-replay.md) for the existing receipt,
failure and reuse interfaces.
