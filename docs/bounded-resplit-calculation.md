# Calculate a pair with one shared resplit slot

Use the separate version 4 request to calculate an original non-ace pair with
up to three resulting hands. The initial split creates two hands. Either
hand can spend one shared extra resplit slot when it holds a matching pair
before hitting or doubling. All completed wagers settle against the same
dealer, using the same depleted shoe and concealed post-peek hole.

Save the [example request](https://t92t1914.github.io/exact-blackjack-solver/bounded-resplit-request.json) as
`bounded-resplit-request.json`, then run these commands in the environment
containing your installed engine:

```sh
bj-calculate bounded-resplit-request.json --output-dir resplit-001 --wall-seconds 5
bj-advise --replay resplit-001/result/decision.json --json
```

The first command creates a new attempt directory. A completed calculation
retains `result/decision.json` and its completion receipt. The second admits
that record, reconstructs its inputs and recomputes through the installed
engine. The example has stand 1, hit -1, double -2 and split 3 in original
wager units. Its selected initial action is split. These deliberately small
modeled counts are a reproducible example, not a full-shoe strategy table.

The [local calculation guide](https://github.com/T92T1914/exact-blackjack-solver/blob/main/docs/local-calculation.md) describes installation
from a reviewed wheel or the repository's source archive. No development
checkout is needed at runtime. This model requires an installation that
supports request 4 and record 5. A package version label alone does not
identify the source bytes. The generated preview also offers a
[request download](https://t92t1914.github.io/exact-blackjack-solver/bounded-resplit-request.json)
and [this guide](https://t92t1914.github.io/exact-blackjack-solver/bounded-resplit-calculation.md).

## Supply the original state

The model selector is `{"name":"common_shoe_bounded_resplit","version":1}`.
The request must declare schema `solver-calculation-request`, version 4,
and `limits.max_states` from 1 through 100000. Its input has the existing
cards, dealer upcard, retained counts, split-state fields and present
double/split permissions. It contains no answer or surrender permission.

Supported inputs are exactly two matching non-ace cards in one original
unsplit hand. Set `is_split_hand` to false and `hand_count` to 1. Supply
3 through 20 unseen cards in `A,2,3,4,5,6,7,8,9,T` order. Counts already
exclude visible cards and still include the hidden dealer hole. The engine
uses them once. A negative peek excludes an ace hole under a ten and a ten
hole under an ace. The hole remains concealed while player decisions are
chosen. Visible draws update the information available to later choices.

Set `max_hands` to 3, `peek`, `double_any_two` and `tens_are_pairs` to true,
and `surrender`, `resplit_aces` and `hit_split_aces` to false. Dealer S17/H17
and double after split may vary. The retained natural payout field remains
part of the declaration, but a non-ace original pair cannot be a natural.
Every split 21 receives ordinary wager settlement, without a natural premium.
Split aces, no-peek play, surrender, insurance and arbitrary saved split
continuation states are outside this family.

`can_split=false` removes the original split action and its joint work.
It keeps this declared model identity. `can_double=false` removes only the
original double action. Double after split still follows `rules.das`.
These controls do not represent external table buttons. Unknown fields,
inconsistent state and unsupported rules are refused before dispatch.

## Follow the shared cards and wagers

After a split or resplit, finish the active left child before dealing the
mandatory second card to the next child. A new sibling goes ahead of the
older pending hand. Consuming the extra slot immediately prevents a fourth
hand, even if a later child also draws a matching rank.

Each choice maximizes the combined settlement of completed, active and
pending hands. A locally attractive action can change cards available to
later hands or consume their only resplit slot. Completed stakes remain
in the calculation. Double draws one card and terminates that hand with
twice its wager. Dealer settlement occurs once after player completion.

Every legally offered joint branch must finish. A depleted shoe is refused
if any offered hit, double, resplit or required dealer continuation runs out
of cards, including branches that the best policy would decline. There is
no partial answer or approximation fallback. The 3 through 20 count envelope
is an admission limit, not a promise that every admitted shoe can complete.
For example, tens against 6 with two aces and six tens retained can consume
all seven drawable cards across three children and leave a dealer 16 needing
another card. A good stand path does not make that joint request complete.

Original stand/hit/double retain the existing last-player-draw convention:
stand after the last player draw and still require dealer settlement. This
does not relax the stricter joint split completion rule.

## Bound an attempt and inspect its outcome

The request cap counts uncached work across root draw, hit, double,
distribution and dealer states, plus resplit draw, play, settle and dealer
states. The receipt names the allowance and records the families actually
entered. The split continuation also has a cooperative 10 second limit.
This state cap is neither a wall-clock timeout nor a memory measurement.

The existing supervisor separately owns the worker and enforces the chosen
wall time. On Windows it establishes its Job memory policy before computation.
The [local calculation guide](https://github.com/T92T1914/exact-blackjack-solver/blob/main/docs/local-calculation.md) describes platform limits,
cancellation, retirement and incomplete receipts. Failed, refused, cancelled,
resource-limited and timed-out attempts expose an outcome without a completed
decision. Use a new output directory for the next attempt. Earlier successful
records remain reusable. A policy setup failure does not establish execution.

Direct callers can use `bj.record.bounded_resplit_record` with explicit counts
and a state cap. That call returns the same record family and propagates
refusal or limit exceptions. It does not create the command's OS supervisor,
attempt directory or cancellation control. Replay also runs in its caller.

## Reuse a completed record

Record schema 5 carries the entire model declaration, retained counts,
rules, original double/split controls, recorded action values and recommendation.
Replay validates the declaration before recomputing. Agreement means those
saved and newly computed binary float results agree under the recorded model.
It does not authenticate provenance or independently prove the mathematics.

Select the file in the [local record inspector](https://t92t1914.github.io/exact-blackjack-solver/#record-inspector).
The page shows full modeled inputs and current permitted actions before the
saved answer. It keeps missing action values absent. It displays effective
surrender permission as false while preserving that no surrender control
was stored. Files remain in the page session and are not uploaded.

Comparisons with ordinary, two-hand common-shoe or late-surrender records
identify different mathematical families before displaying value differences.
Comparisons within this family still expose changed counts, rules, controls
and work caps. The page reads supplied results without repricing them.

The engine enumerates finite modeled states using binary floating point.
It does not return symbolic fractions. Raw root ties use the explicit order
stand, hit, double, split, without an epsilon. Tiny floating point differences
can choose different internal actions at an exact rational tie. Independent
tiny-shoe tests use complete physical deals and exact fractions, including
shared-slot, concealed-hole and strict exhaustion witnesses. That evidence
does not establish optimality for other models, full-shoe performance, or
the safety or value of real wagering.
