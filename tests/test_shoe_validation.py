"""Reject malformed custom shoes before they enter production memo tables."""
import numpy as np
import pytest

from bj import caches, dealer, ev
from bj.core import DOUBLE, HIT, SPLIT, STAND


COUNTS = (0, 0, 0, 0, 0, 0, 0, 0, 0, 3)
OPERATIONS = (
    (lambda shoe: dealer.dealer_distribution('7', shoe),
     (1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)),
    (lambda shoe: ev.ev_stand(('T', 'T'), '7', shoe), 1.0),
    (lambda shoe: ev.ev_hit(('T', 'T'), '7', shoe), -1.0),
    (lambda shoe: ev.ev_double(('T', 'T'), '7', shoe), -2.0),
    (lambda shoe: ev.ev_split('T', '7', shoe), 2.0),
    (lambda shoe: ev.best_action(('T', 'T'), '7', shoe),
     (SPLIT, {STAND: 1.0, HIT: -1.0, DOUBLE: -2.0, SPLIT: 2.0}, 1.0)),
)


@pytest.fixture(autouse=True)
def empty_tables():
    caches.clear_all_caches()
    yield
    caches.clear_all_caches()


@pytest.mark.parametrize('operation,expected', OPERATIONS)
@pytest.mark.parametrize('bad', (
    COUNTS[:-1], COUNTS + (0,), (), 3,
    (-1,) + COUNTS[1:],
    (0.5,) + COUNTS[1:],
    (0.0,) + COUNTS[1:],
    (True,) + COUNTS[1:],
    (np.bool_(True),) + COUNTS[1:],
    ('0',) + COUNTS[1:],
    (float('nan'),) + COUNTS[1:],
    (float('inf'),) + COUNTS[1:],
    ([],) + COUNTS[1:],
))
def test_invalid_custom_shoe_is_rejected_before_cache_admission(operation, expected, bad):
    assert operation(COUNTS) == expected
    before = caches.cache_info()
    with pytest.raises(ValueError, match='ten nonnegative integer counts'):
        operation(bad)
    assert caches.cache_info() == before


@pytest.mark.parametrize('operation', (ev.ev_stand, ev.best_action))
def test_natural_shortcut_still_validates_a_supplied_shoe(operation):
    with pytest.raises(ValueError, match='ten nonnegative integer counts'):
        operation(('A', 'T'), '9', ())
    assert all(info.currsize == info.hits == info.misses == 0
               for info in caches.cache_info().values())


@pytest.mark.parametrize('operation,expected', OPERATIONS)
def test_valid_counts_are_copied_and_integer_types_have_one_cache_identity(operation, expected):
    counts = list(COUNTS)
    assert operation(counts) == expected
    original = tuple(counts)
    counts[-1] = 0
    assert original == COUNTS
    before = caches.cache_info()
    assert operation(iter(original)) == expected
    assert operation(np.array(original, dtype=np.int64)) == expected
    after = caches.cache_info()
    assert all(after[name].misses == info.misses and after[name].currsize == info.currsize
               for name, info in before.items())
