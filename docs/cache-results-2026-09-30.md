# Production cache measurements, September 30, 2026

I kept the solver arithmetic and cache policy unchanged. Forty fresh interpreters
completed the declared sequences, producing 150 usable query results. Every
action, floating action value and margin matched bit for bit for an identical
input. All nine tables had zero counters and occupancy after each combined clear.
There were no time or sampled resident-memory exclusions in this series.

For the one declared 49-card composition, the untraced first-query median was
2.7651 ms. Its first repeated-query median was
8.90 microseconds. These are query intervals after
imports. They exclude process startup, snapshots and clearing. The retained
complete-child times include those costs and are separate observations.

Allocation tracing substantially changed this small workload. The corresponding
traced first-query median was 51.9711 ms. Across the five
matched replicates, its median on/off ratio was 19.02.
I kept both sets of timings and did not subtract an estimated overhead.

The median cache-snapshot interval across the 115 snapshots in each tracing
condition was 40.60 microseconds without tracing and
201.00 microseconds with it. Even this small diagnostic
cost was larger than several warm-query intervals. It remains outside the query
timer and inside complete-child wall time.

## Inputs and timing boundaries

The [protocol](cache-protocol.json) was committed at
`97cb02ccac55be371460911b16684b1eaad0517b` before collection. It uses a ten and a six against
a dealer ten, two high-rank toy compositions and one ordinary remaining
one-deck composition. Splitting is disabled. Each single-case process runs its
first query, two warm queries, then a query after a combined clear. The separate
varied sequence runs the first toy composition, the second, then the first again.

Each sequence has five independent replicates with tracing off and on. Pair order
alternates by replicate. The run order was fixed before results. Warm queries are
shown separately below, so ten warm samples are not presented as ten independent
processes. The varied sequence's repeated first case is also kept separate.

Query timing includes completion and return of all host values from the same
validated cards, shoe and rules. Shoe preparation is recorded outside that
interval for both paths. Output serialization, cache snapshots and memory readings
are separate. Launch-to-ready includes delivery of the readiness record, so it
is not a measurement of pure interpreter startup. No overlapping intervals are
added to claim end-to-end elapsed time.

## Completed query intervals

Every row below has five independent processes. Units are microseconds.

| Case or sequence | Tracing | Query | Median | Range |
| --- | --- | --- | ---: | ---: |
| tiny-16-ten | off | first | 47.20 | 37.00 to 50.80 |
| tiny-16-ten | off | warm 1 | 14.50 | 10.90 to 16.90 |
| tiny-16-ten | off | warm 2 | 10.10 | 8.50 to 12.20 |
| tiny-16-ten | off | after clear | 35.70 | 23.90 to 36.20 |
| tiny-16-ten | on | first | 194.20 | 186.60 to 225.50 |
| tiny-16-ten | on | warm 1 | 61.00 | 52.00 to 70.00 |
| tiny-16-ten | on | warm 2 | 50.40 | 44.80 to 72.00 |
| tiny-16-ten | on | after clear | 157.00 | 150.50 to 313.50 |
| tiny-varied-16-ten | off | first | 50.00 | 37.30 to 52.30 |
| tiny-varied-16-ten | off | warm 1 | 12.30 | 11.20 to 18.20 |
| tiny-varied-16-ten | off | warm 2 | 9.70 | 8.80 to 23.80 |
| tiny-varied-16-ten | off | after clear | 29.30 | 25.10 to 37.60 |
| tiny-varied-16-ten | on | first | 198.30 | 184.20 to 281.70 |
| tiny-varied-16-ten | on | warm 1 | 52.10 | 49.80 to 71.40 |
| tiny-varied-16-ten | on | warm 2 | 46.00 | 44.70 to 71.70 |
| tiny-varied-16-ten | on | after clear | 163.50 | 148.80 to 178.60 |
| one-deck-16-ten | off | first | 2765.10 | 2726.50 to 3332.50 |
| one-deck-16-ten | off | warm 1 | 8.90 | 8.50 to 9.80 |
| one-deck-16-ten | off | warm 2 | 8.30 | 7.90 to 9.00 |
| one-deck-16-ten | off | after clear | 2780.00 | 2371.70 to 3854.80 |
| one-deck-16-ten | on | first | 51971.10 | 51423.40 to 70224.10 |
| one-deck-16-ten | on | warm 1 | 50.20 | 47.10 to 51.40 |
| one-deck-16-ten | on | warm 2 | 45.30 | 43.00 to 59.00 |
| one-deck-16-ten | on | after clear | 49186.50 | 48747.60 to 71000.40 |
| varied_states | off | first toy | 37.30 | 36.00 to 50.30 |
| varied_states | off | varied toy | 28.70 | 27.80 to 29.40 |
| varied_states | off | first toy again | 8.80 | 8.40 to 9.20 |
| varied_states | on | first toy | 190.00 | 189.00 to 212.40 |
| varied_states | on | varied toy | 190.00 | 160.90 to 235.30 |
| varied_states | on | first toy again | 52.30 | 47.20 to 72.50 |

## Cache ownership and memory

The repeated queries added hits without adding misses or occupied states for
the identical input. The varied toy composition added distinct states, then
returning to the first composition reused its earlier work. The machine-readable
analysis retains every per-table delta, including tables untouched by this
no-split query. Occupancy counts states, not bytes.

The one-deck first query occupied 2,385 states across five of the nine
tables. In each varied toy sequence, total occupancy went from eight to sixteen
and stayed at sixteen when the first composition was queried again. The final
combined clear returned every counter and occupied-state count to zero.

The largest Windows process peak working set observed in the retained snapshots
was 25.527 MiB. That is the whole child's resident memory, including
imports, code and receipt objects. It is not the solver's cache byte size. Current
and peak traced Python allocations are also retained for the traced children.
Tracing began before solver imports and continued through subsequent child work.
It excludes orchestration imports and does not account for all native memory.

Clearing reset all table counters and entries. Resident memory did not have to
fall at the same boundary. The Python allocator and other retained objects can
keep pages resident. This brief observation does not establish a leak or prove
that arbitrary inputs have a similar memory bound.

The parent supervised one child at a time, with a 30-second wall bound and a
256-MiB sampled RSS threshold. RSS was polled every 50 ms while the child ran.
A threshold could be overshot between samples. This is not an OS allocation
limit. Windows peak working set is an independent OS peak reading available in
the child's snapshots. No user process was stopped or inspected by this runner.

## Environment, artifacts and decision

Execution used CPython 3.11.8, 64-bit Windows build 26200 and psutil 5.9.8 on a
shared workstation. A single performance slot was reserved, while ordinary
user applications remained open. There was no CPU affinity, priority or power
setting change. This is neither a dedicated-host study nor Linux measurement.

The reviewed collector and synthetic orchestration checks remain in the private
working record. The public evidence consists of
[sanitized samples](results/cache-2026-09-30/samples.jsonl),
[source and protocol identities](results/cache-2026-09-30/metadata.json), and
[generated statistics and per-table deltas](results/cache-2026-09-30/analysis.json).
The derivative removes process IDs. It keeps numerical results, run order,
timestamps as durations, memory readings and exclusions. Its hash is separate
from the original private rows. One path-inventory failure before any child
launched is recorded separately. It is not a failed numerical query.

The result supports reuse for these repeated inputs and a quiescent combined
clear when the caller wants to retire retained states. It does not justify a
new eviction policy, production limit or general speedup claim. Five repeats
do not characterize extreme tails. The exact stand, hit and double model,
approximate production split and bounded joint reference remain unchanged.
No full-shoe bound, house-edge claim, wagering advantage or GPU result follows.

Memory definitions follow the
[psutil 5.9.8 documentation](https://github.com/giampaolo/psutil/blob/release-5.9.8/docs/index.rst)
and [Python allocation tracing documentation](https://docs.python.org/3.11/library/tracemalloc.html).
