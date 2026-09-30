# Cache ownership and inspection

The production solver has nine process-wide memo tables. They have immutable
keys and no eviction limit. Repeated states can reuse an earlier calculation.
Different shoe compositions can keep additional entries until the owning
module clears them or the process exits.

The existing reset functions deliberately have different scope.
`bj.ev.clear_caches()` clears its seven tables. `bj.dealer.clear_caches()`
clears the dealer's two tables. Neither is a complete production reset alone.
`bj.caches` adds an explicit combined operation and detached diagnostic values.
It does not change either existing function or any numerical calculation.

```python
from bj.caches import cache_info, clear_all_caches
from bj.ev import best_action

clear_all_caches()  # At a boundary where your solver workers have stopped.
result = best_action(('T', '6'), 'T')
for name, info in cache_info().items():
    print(name, info.hits, info.misses, info.currsize, info.maxsize)
clear_all_caches()
```

The names below identify the table rather than exposing its entries or keys.

| Diagnostic name | Cached work |
| --- | --- |
| `dealer.resolve` | Dealer continuations from a total, softness and remaining shoe |
| `dealer.distribution` | Dealer outcome distributions from an upcard and shoe |
| `ev.draw_probs` | Player draw probabilities conditioned on the completed peek |
| `ev.hit` | Hit and later optimal stand/hit continuation |
| `ev.double` | One draw and settlement at two units |
| `ev.split_hand_outcomes` | Production independent split-hand approximation |
| `ev.strategy_play` | Continuation under a supplied fixed strategy |
| `ev.strategy_split_hand_outcomes` | Split-hand continuation under that strategy |
| `ev.cell` | Initial-deal valuation used by the whole-game calculation |

`cache_info()` returns a new dictionary of frozen `CacheInfo` values with
`hits`, `misses`, `maxsize` and `currsize`. It does not walk the tables or count
their bytes. A miss includes a wrapped invocation that raises, so misses are
not a count of completed mathematical states. Each table is read in turn.
The combined snapshot is not atomic if other workers are calculating.

Both resets release cache-owned references and reset counters. A calculation
already running can add entries afterward. Callers own that synchronization
boundary. Clearing is not cancellation, a shutdown barrier or a memory cap.
The Python allocator may retain released storage, and other live objects can
also keep memory resident. A high resident-memory reading after clear does not
by itself establish that cached entries remain live. These distinctions follow
the documented [Python cache behavior](https://docs.python.org/3.11/library/functools.html#functools.lru_cache)
and [Python allocation tracing](https://docs.python.org/3.11/library/tracemalloc.html).

The fixed-strategy tables include the strategy callable in their keys. A
caller's strategy must remain deterministic for those inputs while its values
are cached. Clear the production tables before reusing a callable whose
external behavior has changed. This API does not inspect a callable's mutable
closure or make a nondeterministic policy valid.

`bj.joint_split` constructs four separate tables inside each reference call.
They are not in this registry or affected by the combined reset. The reference
already reports its own states and cache hits and raises on a work or time
limit. Its small two-hand scope remains distinct from production split
valuation. Simulation action caches are also outside this production registry.

## Verification and measurement status

The focused tests use high-rank toy shoes to check identical cold, warm and
cleared outputs, detached snapshots, varied compositions, preserved module
ownership, failed invocations and independent reference-call caches.
They have no timing threshold. Cache equivalence does not independently prove
the mathematics. The existing rational permutation reference tests provide a
separate check within their declared toy-shoe scope.

The [bounded measurement protocol](cache-protocol.json) was declared before
collection. It separates a fresh process from empty tables in a process that
has already imported the solver. It keeps completed-query timing, table
counters, allocation tracing, process memory and instrumentation overhead
distinct. Measurement collection remains pending. There is no new performance,
memory-release or leak result in this change.

No eviction policy or production work limit is added. The exact stand, hit and
double model and approximate production split remain unchanged. Historical
joint-reference results are retained, with no new claim about a full shoe,
house edge or wagering advantage.
