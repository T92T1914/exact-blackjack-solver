"""Session-scoped fixtures for the three expensive exact computations.

house_edge() for the composition-dependent optimum, house_edge() for the
printed chart, and derive_table() cost on the order of 90 s, 5 s and 60 s
cold and share memo tables between them.  Each runs once per session and
every test module that needs one takes it from here rather than paying for
it again.  Everything else in the suite is fast.
"""
from __future__ import annotations

import pytest

from bj import ev
from bj.strategy import basic_action


@pytest.fixture(scope='session')
def edge_optimal() -> float:
    """Player expectation under the exact composition-dependent optimum."""
    return ev.house_edge()


@pytest.fixture(scope='session')
def edge_chart() -> float:
    """Player expectation under bj.strategy's chart, followed all the way down."""
    return ev.house_edge(strategy=basic_action)


@pytest.fixture(scope='session')
def derived():
    """The whole basic-strategy chart, recomputed from the solver."""
    return ev.derive_table()
