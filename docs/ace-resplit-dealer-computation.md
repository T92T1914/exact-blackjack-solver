# Ace-resplit dealer computation

[Calculation guide](bounded-ace-resplit-calculation.md) | [Frozen protocol](ace-resplit-dealer-protocol.json) | [Every observation](ace-resplit-dealer-results.json)

This report preserves the historical PR47 dealer-summary comparison. In
that frozen source snapshot, a mixed twenty-card request completed under
the original 100,000 whole-request state cap. The card ceiling, offered
actions, hidden information and optional shared resplit slot were unchanged.
The later [terminal reuse calculation](ace-terminal-reuse.md) completes the
supplied A,A against A, H17 request under the same cap. Its evidence is
separate from this frozen table and its original verification allowance.

## Dealer summaries and the player boundary

The method `ace_resplit_dealer_low_ace_counts_binary64_v1` memoizes the dealer
distribution by integer low total, ace presence and remaining counts. S17/H17
is captured for the request. Those values determine the total, softness,
mandatory draw and settlement without retaining the ordered dealer history.

The same rank loop visits children in the same order. Outcome insertion,
multiplication and `math.fsum` order remain literal. Induction on remaining
cards therefore preserves the ordered binary64 outcome tuple, including ace
demotion under H17. This summary applies to the dealer distribution only.

Player cards, pending seeds, completed wagers and the remaining shared slot
keep their original memo keys. A new sibling remains before older pending
seeds. The active child finishes before the next pending seed receives a
card. Stand and resplit both finish their hidden-hole expectations before
the visible-history maximum. All completed wagers still settle against one
dealer hand. A required unavailable continuation refuses the entire value.

## Historical PR47 frozen coverage comparison

The protocol was frozen before that candidate or its deciding observations.
Original source was `72ae11f40094ba2318e56d0a3ad5aed309419a14`, with candidate
numerical source `69ea000843a39187e40d99440e7857b6411aec08`. The raw evidence
retains all three fresh baseline/current repetitions per input, alternating
order, plus one original-arithmetic verification per input. Counts below are
the actual whole-request root and joint entries in that snapshot. The
"Current product" column names its candidate, not a later installed engine.
The table and linked frozen observations are retained unchanged.

| Frozen request | Original product | Current product | Original arithmetic verification |
| --- | ---: | ---: | ---: |
| A,A / 6, S17, mixed twenty cards | Refused at 100,000 / 100,001 attempted | Complete at 59,669 | Complete at 121,565 |
| A,A / T, S17, mixed twenty cards | Complete at 51,288 | Complete at 40,900 | Complete at 51,288 |
| A,A / A, H17, mixed twenty cards | Refused at 100,000 / 100,001 attempted | Still refused at 100,000 / 100,001 attempted | Complete at 259,540 |
| A,A / 7, one retained ace and five tens | Complete at 46 | Complete at 46 | Complete at 46 |

All nine candidate complete maps in that comparison match the original
ordered S/H/D/P hexadecimal values, selected action and margin exactly.
The six-upcard case established additional complete coverage, including
retained aces and the optional resplit continuation. Its ace-upcard
verification was not an installed result under the product cap. That
snapshot's refusal is preserved here. See the [terminal reuse note](ace-terminal-reuse.md)
for the later cold H17 completion. The historical 259,540 entries are not
a current full-request work denominator or an installed allowance.

The private original-arithmetic verifier admits at most 500,000 combined
root and ace entries. Only its fresh imported joint limit validator and
observer are temporarily extended. The original numerical recurrence, rank
rule and cooperative ten-second guard are retained. Both private bindings
restore afterward. Product `MAX_STATES`, validation, request limits and
process supervision remain unchanged. This verifier is computation parity
evidence, not independent mathematical validation or a supported product
mode. The first observations ran in fresh processes before an explicit
alias-restoration addition, which changed no arithmetic and was already
removed by interpreter retirement. The raw source and note retain that fact.

Existing independent physical-card and Fraction tests exercise tiny concealed
hole, peek, shared slot, optional split, combined wager and strict exhaustion
cases. Their numerical tolerance does not become a ranking or replay epsilon.
Exchangeable unit-wager ace children after the slot is spent cannot distinguish
ancestry order in that physical reference. The unchanged player recurrence
preserves that order without claiming a new independent discrimination test.

## Work, timing and reuse

The raw file retains every timing, including refusals. The timer includes the
calculation and small answer-map assembly, excluding imports, input, file
serialization and process startup. No speedup ratio compares refusal with
completion. The deciding acceptance criterion is additional useful bounded
coverage. It does not establish a general timing improvement.

Collection used Python 3.11.8 on shared Windows, a Ryzen 7 7800X3D, and one
engineering process at a time. Each process had a 512 MiB aggregate committed
memory Job allowance and finite wall policy, with observed empty retirement.
That is an engineering verification allowance, not the installed command's
default 256 MiB allowance, a resident-memory measurement or a native check.

`ace_resplit_dealer` now counts actual uncached summary bodies. Cache hits,
work counts and refusal points can change. Model identity, request version 5,
record version 6, original physical input and comparison semantics remain
unchanged. Successful records work with direct replay, protected replay and
the existing local-file inspector. Pin source and protocol when reproducing
computational work. Unsupported limits, timeout, cancellation and incomplete
calculation continue to withhold a complete result.

Full-shoe completion, arbitrary twenty-card completion, changes to other
resplit models, symbolic real arithmetic and a wagering advantage are outside
this result. Direct APIs remain caller-owned. Linux supervision remains
wall-only and memory-uncapped under its current worker boundary.
