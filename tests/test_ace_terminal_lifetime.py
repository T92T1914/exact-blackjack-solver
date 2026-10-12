"""Actual registry retirement and restoration of an enclosing selected scope."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from bj import _enumeration, bounded_ace_resplit, ev
from bj._enumeration import EnumerationLimitExceeded
from bj.caches import clear_all_caches
from test_bounded_ace_resplit import counts, rules


@pytest.fixture(autouse=True)
def cold_caches():
    clear_all_caches()
    yield
    clear_all_caches()


def test_nested_success_and_refusal_retire_real_containers_and_restore_outer_owner():
    retained = counts(('A', 'A', 'A', 'T', 'T'))
    selected_rules = rules(das=False)
    prior = _enumeration._active.get()
    retired = []
    original_retire = _enumeration._TerminalReuse.retire

    def observed_retire(registry):
        owner = _enumeration._active.get()
        assert owner._terminal_reuse is registry
        original_retire(registry)
        assert registry.phase == 'retired'
        assert not registry.results and not registry.reused
        retired.append((owner, registry))

    with patch.object(_enumeration._TerminalReuse, 'retire', new=observed_retire):
        with _enumeration.scope(100000, terminal_reuse=True) as outer:
            ev.best_action(('A', 'A'), '7', shoe=retained, rules=selected_rules,
                           can_double=True, can_split=False)
            outer.freeze_terminal_reuse()
            registry = outer._terminal_reuse
            assert registry.phase == 'ace' and registry.results
            before = (dict(registry.results), set(registry.reused), outer.snapshot())
            bounded_ace_resplit._decide_with_diagnostics(
                ('A', 'A'), '7', retained, selected_rules)
            assert _enumeration._active.get() is outer
            with pytest.raises(EnumerationLimitExceeded):
                bounded_ace_resplit._decide_with_diagnostics(
                    ('A', 'A'), '7', retained, selected_rules, max_states=1)
            assert _enumeration._active.get() is outer
            assert registry.phase == 'ace'
            assert before == (dict(registry.results), set(registry.reused), outer.snapshot())
            assert len(retired) == 2
            assert all(owner is not outer and child is not registry for owner, child in retired)
            assert retired[0][0] is not retired[1][0]
            assert retired[0][1] is not retired[1][1]
        assert len(retired) == 3 and retired[-1] == (outer, registry)
    assert _enumeration._active.get() is prior
