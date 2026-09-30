"""Inspect or clear the production solver's process-wide memo tables.

Call these at a boundary where the caller has stopped its solver workers.
They do not lock a calculation, cancel work, impose a memory limit or control
the separate per-call joint split reference.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import dealer, ev

__all__ = ['CacheInfo', 'cache_info', 'clear_all_caches']


@dataclass(frozen=True)
class CacheInfo:
    """One table's counters and occupied entries, not its byte size."""

    hits: int
    misses: int
    maxsize: int | None
    currsize: int


_TABLES = {
    'dealer.resolve': dealer._resolve,
    'dealer.distribution': dealer._distribution,
    'ev.draw_probs': ev._draw_probs,
    'ev.hit': ev._hit_ev,
    'ev.double': ev._double_ev,
    'ev.split_hand_outcomes': ev._split_hand_outcomes,
    'ev.strategy_play': ev._strategy_play_ev,
    'ev.strategy_split_hand_outcomes': ev._strategy_split_hand_outcomes,
    'ev.cell': ev._cell_ev,
}


def cache_info() -> dict[str, CacheInfo]:
    """Return detached counters for all nine production tables.

    Reading does not enumerate cache entries or change a table. The collection
    is sequential, so another worker may change counters between table reads.
    A miss counts a wrapped invocation, including one that raises. It is not
    a count of successfully completed mathematical states.
    """
    return {name: CacheInfo(*function.cache_info())
            for name, function in _TABLES.items()}


def clear_all_caches() -> None:
    """Clear EV and dealer tables and reset their counters.

    Existing module-level clear_caches functions retain their original scope.
    An in-flight calculation can repopulate a table after this call, so callers
    must arrange their own quiescent boundary. Clearing releases cache-owned
    references, but does not promise a lower process resident-memory reading.
    """
    ev.clear_caches()
    dealer.clear_caches()
