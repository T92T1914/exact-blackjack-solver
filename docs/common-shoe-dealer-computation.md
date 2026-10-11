# Common-shoe dealer computation

[Calculation guide](common-shoe-calculation.md) | [Frozen protocol](common-shoe-dealer-protocol.json) | [Every raw comparison](common-shoe-dealer-results.json)

The bounded two-hand model can now complete a mixed twenty-card request that
the previous computation refused at its original 100,000 state cap. This is
an unchanged-model computational improvement. No card ceiling, work ceiling,
legal alternative or settlement rule was changed.

## What is shared

The previous dealer memo key retained the ordered card history and remaining
counts. The current method, `joint_dealer_low_ace_counts_binary64_v1`, retains
integer low total, ace presence and remaining counts. S17/H17 is fixed within
the request. In this post-peek dealer recurrence, neither card order nor card
count affects a draw or settlement. Low total and ace presence determine soft
status even when an ace can no longer count as eleven.

For each shared state, the same rank loop visits remaining cards in the same
order. Child outcome insertion, multiplication and `math.fsum` order remain
literal. Induction on remaining-card count therefore preserves the ordered
binary64 outcome tuple. Player memo keys, hole beliefs, choices and combined
wagers are unchanged. This argument does not qualify resplit compression or
another dealer convention. Any required unavailable card still refuses the
whole calculation.

## Frozen deciding results

The comparison used original source `7f2cbe0900d4b88325984c00732d18c88290e17e`
and candidate core `f3b996ed05749c9ee7457a15a728b429735c5b40`. Later delivery
documentation and consumer changes retain that candidate numerical body.
The protocol was frozen before the candidate and deciding cases. Each
twenty-card composition has three fresh baseline/candidate process pairs,
with alternating order. All twelve candidate full maps matched original
arithmetic in ordered hexadecimal S/H/D/P values, selected action and margin.

| Case | Original product entries | Current entries | Complete-result comparison |
| --- | ---: | ---: | --- |
| A,A / 3, S17 | 88,857 | 34,001 | Bitwise identical |
| A,A / 6, H17 | 38,691 | 24,243 | Bitwise identical |
| A,A / A, H17 | Refused at 100,000 admitted / 100,001 attempted | 92,358 | Bitwise identical to bounded original arithmetic |
| A,A / T, S17 | 32,083 | 28,046 | Bitwise identical |

The newly complete A/A case is the supplied mixed request. Original arithmetic
was separately completed at 232,005 combined root and joint entries under a
private verification-only ceiling of 500,000. That observer counts every
entered body and resets afterward. It does not change the installed product's
100,000 maximum, produce an old-product result under that maximum, or permit a
cap increase in a request. Its original joint dealer count was 169,528; the
current count is 29,881. Other state-family counts are unchanged in this case.

The larger verification bound supplies old/new computation comparison, not
independent mathematical validation. Existing physical permutation and
Fraction tests independently exercise tiny shared-shoe, H17, ace and ten peek,
combined wager and lawful-hidden-information cases. Their mathematical test
tolerance does not become a ranking or replay epsilon.

## Measured timing and limits

Only completed product calculations have timing ratios:

| Case | Baseline median seconds | Current median seconds | Baseline / current |
| --- | ---: | ---: | ---: |
| A,A / 3, S17 | 0.2360160 | 0.0925581 | 2.5499 |
| A,A / 6, H17 | 0.0951167 | 0.0581766 | 1.6350 |
| A,A / T, S17 | 0.0701227 | 0.0576041 | 1.2173 |

A ratio above one favors the current computation. No ratio compares the old
refusal with the new completion. Every individual timing and state observation
is retained in the raw file, including the refused repetitions.

The actual timer includes the calculation and small hexadecimal answer-map
assembly through exception/result handling. Imports, rules construction, file
serialization and process startup/retirement are outside it. The frozen plan
described a call-only interval; this additional answer assembly is reported
explicitly rather than silently relabeled. Instrumented exploratory profiles
are separate qualification evidence and are not timing speedups.

Collection used Python 3.11.8 on shared Windows, a Ryzen 7 7800X3D with sixteen
logical processors, and one engineering process at a time. Each operation had
a 512 MiB aggregate committed-memory Job allowance, a finite wall policy and
observed retirement into an empty Job. Normal user activity was preserved.
This is a small declared family, not an exclusive-machine experiment,
significance test, general acceleration guarantee or measured RSS result.

`joint_dealer` now counts actual uncached summary bodies. Cache hits, work
counts, time and the point of a work refusal can change legitimately. Complete
numerical values, physical inputs, model identities and saved comparison
semantics remain invariant. Existing receipts retain their strict fields and
do not identify source bytes or method names by themselves. Pin the source
and protocol for a computational reproduction.

## Reproduce and use

The raw file includes each full frozen case, both body identities and the
exact private measurement-cell source. Reproduce only in a caller-owned,
bounded environment with one fresh interpreter per variant. The reproduction
cell's `original-verification` mode is explicitly separate from an installed
product calculation. Its combined counter has a 500,000 ceiling. Do not use
that mode as a product request or compare its instrumented elapsed time as a
product speedup.

For ordinary use, install the accepted engine, download the mixed request and
follow the existing calculation guide. Successful results remain schema 3
records reusable by direct replay, protected replay and the local-file
inspector. Unsupported limits, unavailable branches and operational failures
retain their existing explicit outcomes. Full-shoe calculations, arbitrary
twenty-card completion, symbolic exactness and a wagering advantage remain
outside this result.
