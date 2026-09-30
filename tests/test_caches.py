"""Cache ownership checks on small high-rank shoes, with no timing threshold."""
import ast
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from bj import caches, dealer, ev, joint_split
from bj.core import RANKS, Rules
from bj.strategy import basic_action


def shoe(cards):
    return tuple(cards.count(rank) for rank in RANKS)


@pytest.fixture(autouse=True)
def empty_tables():
    caches.clear_all_caches()
    yield
    caches.clear_all_caches()


def query(cards=('T', '6'), up='T', counts=None):
    counts = counts or shoe(('7', '7', '8', '8', '9', '9', 'T', 'T'))
    return ev.best_action(cards, up, counts, Rules(max_hands=2), can_split=False)


def test_every_production_memo_table_is_exposed():
    # Adding another decorated solver table must not silently omit it from diagnostics.
    expected = set()
    for module in (dealer, ev):
        tree = ast.parse(Path(module.__file__).read_text(encoding='utf-8'))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and any(
                    isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name)
                    and dec.func.id == 'lru_cache' for dec in node.decorator_list):
                expected.add(getattr(module, node.name))
    assert set(caches._TABLES.values()) == expected
    assert len(caches.cache_info()) == 9
    assert all(info.maxsize is None for info in caches.cache_info().values())


def test_snapshot_is_detached_and_reading_does_not_populate_a_table():
    before = caches.cache_info()
    assert before == caches.cache_info()
    assert all(info.currsize == info.hits == info.misses == 0 for info in before.values())
    with pytest.raises(FrozenInstanceError):
        before['ev.hit'].hits = 3
    before.clear()
    assert len(caches.cache_info()) == 9


def test_cold_warm_and_cleared_results_are_bit_identical():
    first = query()
    cold = caches.cache_info()
    warm_result = query()
    warm = caches.cache_info()
    assert first == warm_result
    assert warm['ev.hit'].hits > cold['ev.hit'].hits
    assert all(warm[name].misses == info.misses for name, info in cold.items())
    assert all(warm[name].currsize == info.currsize for name, info in cold.items())
    caches.clear_all_caches()
    assert all(info.currsize == info.hits == info.misses == 0
               for info in caches.cache_info().values())
    assert query() == first
    assert caches.cache_info() == cold


def test_varied_shoes_remain_separate_and_reset_does_not_mutate_returned_values():
    first = query()
    retained = dict(first[1])
    after_first = caches.cache_info()
    varied = query(counts=shoe(('7', '8', '8', '9', 'T', 'T', 'T', 'T')))
    assert caches.cache_info()['ev.hit'].misses > after_first['ev.hit'].misses
    caches.clear_all_caches()
    assert first[1] == retained
    assert query() == first
    assert query(counts=shoe(('7', '8', '8', '9', 'T', 'T', 'T', 'T'))) == varied


def test_existing_module_resets_keep_their_ownership():
    query()
    dealer_before = {name: info for name, info in caches.cache_info().items()
                     if name.startswith('dealer.')}
    ev.clear_caches()
    snapshot = caches.cache_info()
    assert {name: info for name, info in snapshot.items()
            if name.startswith('dealer.')} == dealer_before
    assert all(info.currsize == 0 for name, info in snapshot.items()
               if name.startswith('ev.'))
    query()
    ev_before = {name: info for name, info in caches.cache_info().items()
                 if name.startswith('ev.')}
    dealer.clear_caches()
    assert {name: info for name, info in caches.cache_info().items()
            if name.startswith('ev.')} == ev_before


def test_combined_reset_empties_every_populated_production_table():
    counts = shoe(('7', '7', '8', '8', '9', '9', 'T', 'T'))
    rules = Rules(max_hands=2)
    ev.best_action(('8', '8'), 'T', counts, rules)
    ev._strategy_play_ev(('T', '6'), 'T', counts, rules, basic_action, False, True)
    ev._strategy_split_hand_outcomes(RANKS.index('8'), 'T', counts, 0,
                                     rules, basic_action)
    ev._cell_ev(RANKS.index('6'), RANKS.index('T'), RANKS.index('T'),
                counts, rules, basic_action)
    assert all(info.currsize > 0 for info in caches.cache_info().values())
    caches.clear_all_caches()
    assert all(info.currsize == info.hits == info.misses == 0
               for info in caches.cache_info().values())


def test_reference_caches_are_per_call_and_outside_the_production_reset():
    counts = tuple(('7', '7', '8', '9', 'T', 'T').count(rank)
                   for rank in joint_split.RANKS)
    before = caches.cache_info()
    first = joint_split.joint_split_value('8', 'T', counts)
    assert caches.cache_info() == before
    caches.clear_all_caches()
    again = joint_split.joint_split_value('8', 'T', counts)
    assert (again.value, again.states, again.cache_hits) == (
        first.value, first.states, first.cache_hits)


def test_failed_invocation_is_a_miss_without_a_fabricated_cached_value():
    with pytest.raises(ValueError, match='hole card'):
        ev.ev_hit(('T', '6'), 'T', shoe(('T',)))
    snapshot = caches.cache_info()
    assert snapshot['ev.hit'].misses == 1
    assert snapshot['ev.hit'].currsize == 0
    caches.clear_all_caches()
    assert snapshot['ev.hit'].misses == 1
