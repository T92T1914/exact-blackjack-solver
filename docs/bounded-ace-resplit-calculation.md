# Calculate one-card aces with a shared resplit slot

Use the separate version 5 request for an original A,A with one optional
extra ace resplit and at most three resulting hands. Each split child receives
one mandatory card. A child that becomes A,A can stand or spend the single
remaining slot to resplit. Other children stand after their card. Split
children cannot hit or double, even when double after split is enabled.

The children share the same depleted shoe, concealed post-peek hole and
completed wagers. Player choices use visible information. The dealer settles
once after all children finish. A split 21 receives ordinary wager settlement,
without a natural premium.

## Install, calculate and replay

Follow the [local calculation guide](https://github.com/T92T1914/exact-blackjack-solver/blob/main/docs/local-calculation.md)
to install from a reviewed wheel or source archive. No development checkout
is needed at runtime. Choose an engine revision that supports calculation
request 5 and decision record 6. A package version label alone does not identify
its source bytes or establish support for this family.

Save the [ace request download](https://t92t1914.github.io/exact-blackjack-solver/bounded-ace-resplit-request.json)
as `bounded-ace-resplit-request.json`, then run:

```sh
bj-calculate bounded-ace-resplit-request.json --output-dir ace-001 --wall-seconds 5
bj-advise --replay ace-001/result/decision.json --json
```

The calculation captures the request and starts its owned worker. A completed
attempt publishes `result/decision.json` together with its completion receipt
after worker retirement. Replay validates that record, reconstructs its
modeled inputs and recomputes through the installed engine. Saved EVs and
the saved recommendation are comparison data, not calculation inputs.

The example has original A,A against 7 with three aces and two tens retained.
Its mathematical values are stand -1, hit -1, double -2 and split 3/10 in
original wager units. The selected original action is split. Binary floating
point may serialize the split value as `0.30000000000000004`. The record
retains that raw value. This small supplied shoe is a reproducible model
example, not a full-shoe strategy table.

Use a new output directory for each attempt. A refused, failed, cancelled,
timed-out or resource-limited attempt has an explicit outcome and no completed
decision. It does not replace an earlier successful record.

## Supply an original A,A and retained counts

The model selector is:

```json
{"name": "common_shoe_bounded_ace_resplit", "version": 1}
```

The request schema is `solver-calculation-request`, version 5. Supply exactly
two aces in one original unsplit hand: `is_split_hand=false` and
`hand_count=1`. Arbitrary saved split continuation states and non-ace pairs
are outside this family.

Supply 3 through 20 retained counts in `A,2,3,4,5,6,7,8,9,T` order. They
already exclude visible cards and still include the concealed dealer hole.
The engine uses those counts once. A completed negative peek excludes an
ace hole under a ten and a ten hole under an ace. It does not reveal which
eligible hole was dealt. Visible draws update the conditional information
used for later choices.

Set `max_hands=3`, `resplit_aces=true` and `hit_split_aces=false`.
The family requires `peek`, `double_any_two` and `tens_are_pairs` to
be true, and `surrender` to be false. Dealer S17/H17 and DAS may vary.
DAS is retained in the rules but never enables a double on a one-card-only
split ace. The original A,A can still have an original double alternative.

`can_split=false` removes the original split action and its joint work.
`can_double=false` removes only the original double action. Both retain the
declared model identity and do not change continuation rules. Unknown fields,
inconsistent state, unsupported rules and impossible negative-peek input are
refused before computation.

## Follow the shared cards and optional choice

The first split creates two children. Finish the active child before dealing
the mandatory card to an older pending child. A resplit replaces an eligible
A,A with two new ace seeds. Its new sibling goes ahead of the older pending
hand, and the shared slot is spent before either new child receives its card.
A later A,A cannot create a fourth hand.

Standing an eligible A,A may preserve the slot for a later child. The engine
compares the combined settlement of every completed, active and pending
wager. It averages concealed-hole worlds before choosing a player action.
Choosing separately with a known hole would describe different information
and can change the value.

Every legally offered continuation must finish, including an extra resplit
that the best policy would decline. There is no forced stand, reshuffle,
partial accepted answer or approximation fallback when an offered mandatory
child deal or required dealer draw is unavailable. Exactly three aces retained against 7,
for example, let two original split children stand at 12 against dealer 18,
but cannot supply every child card in an offered extra resplit. That request
is refused when the original split is enabled. Disabling it can leave a
complete ordinary-root request.

The 3 through 20 card range is an admission boundary. It does not promise
that every admitted composition will complete. Original stand, hit and
double preserve the existing final-player-draw convention: stand after the
last player draw and still require dealer settlement. That convention
does not relax the split children's mandatory deals.

## Bound and inspect an attempt

Set `limits.max_states` from 1 through 100000. This counts uncached states
across original draw, hit, double, distribution and dealer work, plus
ace-resplit draw, play, settle and dealer work. The receipt names the cap
and the families actually entered. The joint ace continuation also has a
cooperative 10 second allowance. Its clock does not cover the original-root
calculation or replace the supervisor's wall limit.

The existing supervisor provides wall time, cancellation, worker retirement
and platform-specific memory policy. On Windows its Job committed-memory
policy is established before input reaches the calculation worker.
Committed memory is not physical RSS. See the [local calculation guide](https://github.com/T92T1914/exact-blackjack-solver/blob/main/docs/local-calculation.md)
for supported platforms, outcome statuses and cleanup limits. A state cap
is not a wall-clock or memory guarantee.

Direct Python callers can use `bj.record.bounded_ace_resplit_record` with
explicit counts and a state cap. That call propagates refusal and limit
exceptions. Direct record creation and replay execute in their caller and
do not create the calculation command's OS supervisor or cancellation
controls.

## Reuse and compare a completed record

Decision record 6 carries the ace model declaration, original permissions,
retained counts, rules, raw action values and recommendation. Installed
replay checks the complete declaration before recalculation. Agreement means
the saved and recomputed binary-float values and action agree under that
model. It does not authenticate provenance or independently prove the
mathematics.

Select the completed `decision.json` in the [local record inspector](https://t92t1914.github.io/exact-blackjack-solver/#record-inspector).
The page shows modeled inputs and original permitted actions before the
saved answer. It preserves absent action values, effective surrender
permission false and the absence of a stored surrender control. Files stay
in the page session and are not uploaded. The page does not reprice them.

Compare another ace record with changed current controls or retained counts.
The page exposes those changes before answer differences. Comparison with
an ordinary, two-hand common-shoe, late-surrender or non-ace resplit record
identifies different mathematical families before values. A difference
between families is not evidence of an engine regression.

The engine enumerates the declared finite model using binary floating point.
It does not return symbolic fractions. Raw original ties use stand, hit,
double, split order; eligible ace ties use stand before resplit. No policy
epsilon is added. A small floating-point difference can select differently
at an exact rational tie. Independent tiny-shoe tests use complete physical
deals and exact fractions for hidden information, shared resplitting,
settlement and exhaustion witnesses. They do not establish a full-shoe
error bound, universal completion, optimality in other models or the value
of real wagering.
