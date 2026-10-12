# Complete the supplied H17 ace calculation

Save the [H17 request](../examples/bounded-ace-resplit-h17-request.json) as
`bounded-ace-resplit-h17-request.json`. Install a reviewed wheel or source
archive that includes this request and terminal reuse, following the
[local calculation guide](local-calculation.md). No development checkout
is needed at runtime. Pin the engine source when comparing computational
work. A package version alone does not identify that source.

Use a fresh directory for each owned operation:

```sh
bj-calculate bounded-ace-resplit-h17-request.json --output-dir ace-h17-001 --wall-seconds 30
bj-replay ace-h17-001/result/decision.json --output-dir ace-h17-replay-001 --wall-seconds 30
bj-advise --replay ace-h17-001/result/decision.json --json
```

`bj-calculate` publishes a complete decision and receipt after its worker
retires. `bj-replay` recomputes that saved model through the existing
[protected replay owner](protected-replay.md). Direct `bj-advise` replay
runs in its caller. Replay reconstructs the recorded inputs and compares
answers after computation. It does not trust the saved answer as an input.

Select `ace-h17-001/result/decision.json` in the
[local record inspector](https://t92t1914.github.io/exact-blackjack-solver/#record-inspector)
to inspect its inputs, action values and model, or compare it with another
record. The inspector reads files locally and does not recompute values.

## The supported request and observed cold result

The request uses the existing `common_shoe_bounded_ace_resplit` model,
version 1, calculation request 5 and decision record 6. Original A,A faces
dealer A after a completed negative peek, with H17 and DAS enabled. The
original stand, hit, double and split actions are permitted. Split ace
children still take one card, with at most one optional shared resplit and
three resulting hands. They cannot hit or double.

Retained counts are `[1,2,1,2,2,2,2,2,2,4]` in `A,2,3,4,5,6,7,8,9,T`
order. The twenty cards already exclude the visible player cards and
upcard, and still include the concealed hole. Use them once. The negative
peek excludes a ten-valued hole without revealing the eligible hole.
The same hidden information, shared depletion and combined dealer
settlement apply throughout the calculation.

The retained cold source calculation completed all four action values
under the original 100,000 state cap and selected H. Its ordered binary64
values and margin matched the retained original arithmetic map. Actual
entered and attempted work was 82,780 states. The detached diagnostic
snapshot recorded:

| Counter | Observed value | Meaning |
| --- | ---: | --- |
| `root_terminal_keys` | 41,581 | Distinct completed root terminal keys retained for this request |
| `registry_lookups` | 41,061 | Terminal probes during the joint ace calculation |
| `registry_hits` | 26,234 | Probes that found an eligible retained point mass |
| `unique_reused_keys` | 26,234 | Distinct retained keys used by those hits |
| `cache_retired` | `true` | Request-local values and reused-key storage were cleared |

These are cold source observations, not a latency benchmark or a promise
about every admitted twenty-card shoe. The historical PR47 report retains
its [frozen table](ace-resplit-dealer-computation.md). Its H17 refusal and
259,540-entry original-arithmetic verification belong to older numerical
source. That count is not a current full-request denominator, a speedup
baseline or permission to raise the product cap.

## Reuse only a completed terminal point mass

A terminal dealer state requires no further card. It has total above 21,
total 18 through 21, or total 17 when hard or when S17 applies. Soft 17
under H17 is not terminal and is not shared by this method.

The ordinary root returns a six-entry probability vector for 17, 18, 19,
20, 21 and bust. An eligible terminal result contains one exact binary64
`1.0` and five exact `0.0` entries. The ace dealer represents the same
result as one outcome with mass `1.0`. The reuse path checks that literal
point mass. It does not transfer a nonterminal distribution or a natural
blackjack probability.

The root count tuple is A-first, while the ace dealer count tuple is
A-last. Rotating the ten counts is a reversible one-to-one permutation.
The ace dealer's low total and ace flag recover the same total and
softness. The key also retains the depleted counts and S17/H17 rule.
This does not claim that every raw dealer history has a distinct key.

Completed root results seed storage owned by one bounded ace request.
That storage freezes after the original S/H/D work finishes. A later
eligible ace probe can reuse an earlier completed point mass before
entering its dealer body. A miss follows the original dealer body. Every
body actually entered still counts against the original state cap.
Reuse counters remain separate from entered states.

The nonterminal rank loop, probabilities, floating-point operation order,
player choices and hidden information remain unchanged. No broader
dealer distribution, hole-card law, natural settlement or wager shortcut
is introduced. Replaying with this method is reproduction by the selected
engine, not independent proof of the entire model.

## Receipts, caches and operational limits

The computation method is
`bounded_ace_root_terminal_pointmass_reuse_binary64_v1`, scoped to
`bounded_ace_request`. When supplied, the calculation receipt's optional
`terminal_reuse` diagnostic identifies that method and the detached
counters above. It contains no dealer keys or probabilities and is
captured after request-local retirement.

Decision record 6, model version 1 and the successful replay report keep
their existing shapes. Direct record creation retains its public return
and exception behavior. A saved record remains input to the same record,
replay and inspection interfaces. Diagnostics describe computation and do
not become part of the numerical model or a saved answer to trust.

Fresh owned workers and long-lived direct callers can have different
global memo-cache states. A global root-cache hit may return without
entering the body that seeds this request's terminal storage. Missing
seeds use the original ace dealer path. Warm work counts and refusal
points therefore need not match the cold snapshot. The request-local
storage does not become a process-global cache. Storage is cleared during
successful retirement. A retirement failure withholds a completed result,
while the enclosing context is restored. These describe in-process
retirement, not cleanup after worker termination.

The original 100,000 whole-request state cap and ten-second joint
cooperative allowance remain. The joint clock does not cover original
root pricing or replace the owner's wall limit. Timeout, cancellation,
unsupported input, unavailable required cards and incomplete calculation
still withhold a complete result. No partial action map is accepted.

The cold engineering check used a 512 MiB Windows Job committed-memory
allowance. That is not a physical resident-memory measurement or proof of
completion at the installed command's default 256 MiB allowance.
Separately, an externally installed Windows wheel completed this supplied
request with the default 256 MiB Job cap and a five-second wall policy.
Calculation and protected replay recorded empty retirement, and direct
replay also agreed. This is acceptance of this input, not a memory bound
for other shoes.
Windows and Linux retain their existing policies: Windows owns a
committed-memory cap, while Linux is wall-only and memory-uncapped.
See the [calculation guide](local-calculation.md) and
[protected replay guide](protected-replay.md) for supported policy flags
and cleanup outcomes. Direct APIs remain caller-owned.

The [ace calculation guide](bounded-ace-resplit-calculation.md) retains
the supported rules and exhaustion behavior. Arbitrary twenty-card
completion, full-shoe coverage, changes to other split families, symbolic
real arithmetic, stronger play and a wagering advantage are outside this
result.
