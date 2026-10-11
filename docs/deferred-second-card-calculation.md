# Calculate before the dealer receives its second card

Use the separate version 6 request for one original two-card hand below 21.
The dealer has only its upcard during player choices. Its second card is dealt
afterward without a negative peek. A later dealer natural takes every committed
wager, including both units of a double and a hit-produced 21.

This named model supports stand, hit and an optional initial double. It excludes
split, surrender, insurance, even money and an initial natural. It does not
change the older post-peek calculations or interpret their records differently.

## Install, calculate and replay

Follow the [local calculation guide](https://github.com/T92T1914/exact-blackjack-solver/blob/main/docs/local-calculation.md)
to install a reviewed wheel or source archive. No development checkout is needed
at runtime. Choose an engine revision supporting calculation request 6 and
decision record 7. A saved package label does not identify source bytes or
install an older engine for replay.

Save the [request download](https://t92t1914.github.io/exact-blackjack-solver/deferred-second-card-request.json)
as `deferred-second-card-request.json`, then use a new directory for each attempt:

```sh
bj-calculate deferred-second-card-request.json --output-dir deferred-001 --wall-seconds 30
bj-advise --replay deferred-001/result/decision.json --json
```

Calculation captures the modeled request and starts the existing owned worker.
A successful attempt publishes `result/decision.json` and its completion receipt
after worker and transport retirement. A refused, resource-limited, failed,
timed-out or cancelled attempt has an explicit outcome and no accepted partial
decision. Earlier successful records are not overwritten or retried.

Press Ctrl+C to cancel the owned attempt before result publication. Cancellation
has its own visible outcome and retirement observations. A later interruption
does not remove a result whose completion has already been selected and committed.
No interrupted calculation resumes or retries automatically. Retained candidate
worker output is diagnostic evidence, not a completed decision.

Direct replay validates the record, reconstructs its modeled inputs and
recomputes through the installed engine. Saved action values, recommendation
and margin remain comparison data. For the existing protected replay command:

```sh
bj-replay deferred-001/result/decision.json --output-dir deferred-replay-001 --wall-seconds 30
```

The [protected replay guide](https://t92t1914.github.io/exact-blackjack-solver/protected-replay.md)
describes its captured source identity, comparison report, operational receipt,
ordinary local-file restrictions and process limits. It uses the same recorded
model and limits. It does not substitute a post-peek answer or a different cap.

The supplied eight-card example has original 9,2 against T and retained
`A,3,5,7,8,9,T,T`. Its visible cards have already been removed. No dealer second
card has been removed. This composition was retained in the bounded mathematical
qualification. Independent labelled-card reference coverage was limited to six
retained cards, so that reference does not establish eight-card physical
coverage. The example is a small supplied calculation, not a full-shoe chart or
a promise that all admitted shoes complete.

## Supply the original hand and retained counts

Select this exact model in calculation request 6:

```json
{"name": "deferred_second_card_all_wagers_sdh", "version": 1}
```

Supply exactly two original unsplit cards below 21, `is_split_hand=false`,
`hand_count=1`, `can_split=false` and a Boolean `can_double`. Counts are ten
nonnegative integers in `A,2,3,4,5,6,7,8,9,T` order, with 1 through 20 cards
retained. The counts already exclude the player's cards and dealer upcard once.
The engine does not subtract them again. With no second dealer card yet dealt,
the record declares `includes_hidden_hole=false`.

Set `peek=false`, `surrender=false`, `max_hands=1`, `double_any_two=true`,
`tens_are_pairs=true`, `resplit_aces=false` and `hit_split_aces=false`. S17/H17
can vary. Valid `decks`, `das`, `blackjack_payout` and `insurance_payout` values
are retained context. They do not price splits, initial natural premiums or
insurance in this restricted family.

One retained card offers stand only. With at least two, hit is offered and
`can_double=true` also permits an initial double. Disabling double removes that
original alternative without changing hit continuations. Later choices are
stand and hit only. A double draws once at two original-wager units.

## Follow the final card and required settlement

A surviving player draw from a two-card remainder leaves one card and forces
stand. A total 21 also stops player drawing. Player bust loses its committed
wager immediately. Otherwise the dealer receives its second card from the
remaining stock and draws according to S17/H17. No second-card rank is excluded
by a peek, and player choices do not use a revealed future card.

The dealer may consume its final card when that card settles its hand. If
another required draw is unavailable, the whole original decision is refused.
Every offered root action and every lawful recursive stand/hit alternative must
complete, including an alternative that would lose or would not be selected.
There is no partial accepted maximum, dropped probability, refill or approximate
fallback. Admission of 1 through 20 cards does not guarantee completion for each
composition.

All action returns use original-wager units. A dealer natural takes one unit
after stand or hit and two after double. A hit-produced 21 loses to that natural,
while ordinary equal totals against a nonnatural dealer push. This all-wagers
rule is the named model's selected settlement, not a claim about every table
described as no-peek.

## Bound an attempt

Set `limits.max_states` to an integer from 1 through 100000 and
`limits.max_seconds` to a finite positive number at most 10. The state limit
counts entered uncached root, player, hit, stand, double, dealer-distribution and
dealer-resolution bodies across the whole request. It is not a physical-deal
count or a memory bound. Player and dealer memoization belong to the request
and retire on success or refusal.

The cooperative performance-counter deadline begins before model admission,
checks cache lookups as well as uncached work and continues through result
assembly. It is separate from `--wall-seconds` and cannot preempt a stalled
operating-system call. A smaller state/time limit can refuse a composition that
completed under a larger declared limit. Replay preserves the recorded limits.

The existing supervisor supplies outer wall time, cancellation, retirement and
platform policy. On Windows its aggregate Job committed-memory limit is
established before the calculation worker receives input. The default is
256 MiB, with supported `--memory-mib` values from 64 through 4096. Committed
memory is not physical RSS. On Linux the existing direct worker has wall limits
and an explicitly memory-uncapped policy. Requested hard-memory mode is refused
there before startup. Other platforms remain outside the supervised commands.

The worker deadline has a separate five-second cleanup allowance. Output setup,
ordinary parent filesystem work and publication have their own boundaries, so
the deadline is not an exact whole-command duration promise. The original
commands retain their bounded transport and complete-result rules. See the
local calculation and protected replay guides for the actual outcome fields and
capture limits.

Direct `bj.record.deferred_second_card_record` calls and `bj-advise --replay`
execute in their caller. They retain the model's numerical state/time limits,
but do not add OS memory containment or command cancellation. Use `bj-calculate`
or `bj-replay` for the existing owned process policy.

## Inspect and compare a completed record

Decision record 7 retains the ordered visible hand, supplied counts, false
hidden-hole flag, rules, current initial double permission, full model identity,
state/time limits and raw binary64 answer. A complete stand-only result has
`margin=null`: there is no runner-up. That is different from a zero numerical
gap between two offered actions.

Recommendations use the raw binary64 values with stable stand/hit/double order
when those raw values tie. Exact rational values may tie while floating-point
rounding separates their serialized values. The model does not recover rational
ties, apply a policy epsilon, establish a general rounding-error bound or claim
unrestricted optimal table play.

Select `result/decision.json` in the [local record inspector](https://t92t1914.github.io/exact-blackjack-solver/#record-inspector).
It shows model, retained inputs and permitted actions before supplied answers.
Import a second record to compare current permission, card timing, rules,
counts, work limits and saved values. Different post-peek and deferred families
are identified in either comparison order. Their answer differences do not
establish an engine regression. Missing saved actions remain distinct from zero.
Null and numeric margins are displayed without treating null as zero.

The inspector parses local files only. It performs no EV calculation, uploads
no imported content and does not select an engine by package label. Use installed
replay for recomputation. Its exact stored-float comparison has no tolerance.
Agreement establishes agreement with the installed modeled calculation, not
authenticated provenance or independent mathematical proof. An altered saved
answer can remain readable and report differences without changing the original.

Older record schemas 1 through 6 retain their accepted post-peek meanings and
refusal boundaries. This new request is not a `peek=false` toggle for the ordinary
engine, a split extension, insurance advice or a general house-edge calculation.
