"""Scoped accounting of actual uncached enumeration state bodies."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from threading import Lock

MAX_STATES = 100_000
FAMILIES = frozenset(('root_draw', 'root_hit', 'root_double', 'root_distribution',
                      'root_dealer', 'joint_draw', 'joint_play', 'joint_settle', 'joint_dealer'))
_active = ContextVar('solver_enumeration_budget', default=None)


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
    def __init__(self, limit):
        self.limit = state_limit(limit)
        self.counts = {}
        self.attempted = 0
        self.lock = Lock()

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
            self.counts[family] = self.counts.get(family, 0) + 1


def state(family):
    """Enter an uncached state, or do nothing for an ordinary legacy call."""
    budget = _active.get()
    if budget is not None:
        budget.enter(family)


@contextmanager
def scope(limit):
    budget = _Budget(limit)
    token = _active.set(budget)
    try:
        yield budget
    finally:
        _active.reset(token)
