"""Scoped accounting of actual uncached enumeration state bodies."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from threading import Lock

MAX_STATES = 100_000
FAMILIES = frozenset(('root_draw', 'root_hit', 'root_double', 'root_distribution',
                      'root_dealer', 'joint_draw', 'joint_play', 'joint_settle', 'joint_dealer'))
_active = ContextVar('solver_enumeration_budget', default=None)
TERMINAL_REUSE_METHOD = 'bounded_ace_root_terminal_pointmass_reuse_binary64_v1'
TERMINAL_REUSE_SCOPE = 'bounded_ace_request'


def _terminal_outcome(total, soft, s17):
    if total > 21:
        return 0
    if total >= 18 or (total == 17 and (s17 or not soft)):
        return total
    return None


class _TerminalReuse:
    """Exact root terminal results owned by one selected enumeration scope."""

    def __init__(self, lock):
        self.lock = lock
        self.phase = 'root'
        self.results = {}
        self.reused = set()
        self.root_terminal_keys = 0
        self.registry_lookups = 0
        self.registry_hits = 0
        self.unique_reused_keys = 0

    def seed(self, total, soft, shoe, s17, result):
        with self.lock:
            if self.phase != 'root':
                return
        outcome = _terminal_outcome(total, soft, s17)
        if outcome is None:
            return
        if (type(total) is not int or type(soft) is not bool or type(s17) is not bool
                or type(shoe) is not tuple or len(shoe) != 10
                or any(type(count) is not int or count < 0 for count in shoe)):
            raise ArithmeticError('root terminal reuse key is invalid')
        position = 5 if outcome == 0 else outcome - 17
        if (type(result) is not tuple or len(result) != 6
                or any(type(value) is not float for value in result)
                or any(value.hex() != ('0x1.0000000000000p+0' if index == position
                                       else '0x0.0p+0')
                       for index, value in enumerate(result))):
            raise ArithmeticError('root terminal reuse requires a literal point mass')
        key = (total, soft, shoe[1:] + shoe[:1], s17)
        singleton = ((outcome, result[position]),)
        with self.lock:
            if self.phase != 'root':
                return
            if key in self.results:
                if self.results[key] != singleton:
                    raise ArithmeticError('root terminal reuse key changes its point mass')
            else:
                self.results[key] = singleton
                self.root_terminal_keys += 1

    def freeze(self):
        with self.lock:
            if self.phase != 'root':
                raise RuntimeError('root terminal reuse phase cannot be frozen twice')
            self.phase = 'ace'

    def lookup(self, low, has_ace, remaining, s17):
        if type(low) is not int or type(has_ace) is not bool or type(s17) is not bool:
            raise ArithmeticError('ace terminal reuse state is invalid')
        soft = has_ace and low + 10 <= 21
        total = low + (10 if soft else 0)
        if _terminal_outcome(total, soft, s17) is None:
            return None
        if (type(remaining) is not tuple or len(remaining) != 10
                or any(type(count) is not int or count < 0 for count in remaining)):
            raise ArithmeticError('ace terminal reuse counts are invalid')
        key = (total, soft, remaining, s17)
        with self.lock:
            if self.phase != 'ace':
                return None
            self.registry_lookups += 1
            result = self.results.get(key)
            if result is not None:
                self.registry_hits += 1
                if key not in self.reused:
                    self.reused.add(key)
                    self.unique_reused_keys += 1
            return result

    def retire(self):
        with self.lock:
            self.phase = 'retiring'
            try:
                self.results.clear()
            finally:
                self.reused.clear()
            self.phase = 'retired'

    def snapshot(self):
        with self.lock:
            return {
                'computation_method': TERMINAL_REUSE_METHOD,
                'cache_scope': TERMINAL_REUSE_SCOPE,
                'cache_retired': (self.phase == 'retired'
                                  and not self.results and not self.reused),
                'root_terminal_keys': self.root_terminal_keys,
                'registry_lookups': self.registry_lookups,
                'registry_hits': self.registry_hits,
                'unique_reused_keys': self.unique_reused_keys,
            }


class EnumerationLimitExceeded(RuntimeError):
    """The first state beyond the admitted cap was refused before execution."""

    def __init__(self, work):
        super().__init__('whole-request enumeration state limit exceeded')
        self.work = work


def state_limit(value):
    if type(value) is not int or not 1 <= value <= MAX_STATES:
        raise ValueError(f'max_states must be an integer from 1 through {MAX_STATES}')
    return value


class _Budget:
    def __init__(self, limit, deadline_check=None, *, terminal_reuse=False):
        self.limit = state_limit(limit)
        self.deadline_check = deadline_check
        self.counts = {}
        self.attempted = 0
        self.lock = Lock()
        self._terminal_reuse = _TerminalReuse(self.lock) if terminal_reuse else None

    def freeze_terminal_reuse(self):
        if self._terminal_reuse is None:
            raise RuntimeError('terminal reuse is disabled for this scope')
        self._terminal_reuse.freeze()

    def terminal_reuse_snapshot(self):
        if self._terminal_reuse is None:
            raise RuntimeError('terminal reuse is disabled for this scope')
        return self._terminal_reuse.snapshot()

    def retire_terminal_reuse(self):
        if self._terminal_reuse is not None:
            self._terminal_reuse.retire()

    def snapshot(self):
        with self.lock:
            return self._snapshot()

    def _snapshot(self):
        return {'limit': self.limit, 'states': sum(self.counts.values()),
                'attempted_states': self.attempted,
                'state_counts': dict(sorted(self.counts.items()))}

    def enter(self, family):
        with self.lock:
            self.attempted += 1
            if self.attempted > self.limit:
                raise EnumerationLimitExceeded(self._snapshot())
            if self.deadline_check is not None:
                # The hook must not inspect this locked budget. A caller can
                # attach its snapshot after the refused entry unwinds.
                self.deadline_check()
            self.counts[family] = self.counts.get(family, 0) + 1


def state(family):
    """Enter an uncached state, or do nothing for an ordinary legacy call."""
    budget = _active.get()
    if budget is not None:
        budget.enter(family)


def _seed_root_terminal(total, soft, shoe, s17, result):
    """Register only a completed root terminal result during selected root work."""
    budget = _active.get()
    registry = getattr(budget, '_terminal_reuse', None)
    if registry is not None:
        registry.seed(total, soft, shoe, s17, result)


def _ace_terminal_result(low, has_ace, remaining, s17):
    """Return a prior terminal result without entering a new numerical body."""
    budget = _active.get()
    registry = getattr(budget, '_terminal_reuse', None)
    if registry is None:
        return None
    return registry.lookup(low, has_ace, remaining, s17)


@contextmanager
def scope(limit, *, deadline_check=None, terminal_reuse=False):
    budget = _Budget(limit, deadline_check, terminal_reuse=terminal_reuse)
    token = _active.set(budget)
    try:
        yield budget
    finally:
        try:
            budget.retire_terminal_reuse()
        finally:
            _active.reset(token)
