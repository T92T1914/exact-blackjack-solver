"""Invalid batch sizes should not build tables or advance random streams."""
from unittest.mock import patch

import numpy as np
import pytest

from bj.simulate import outcome_distributions, simulate, simulate_parallel


@pytest.mark.parametrize('bad', [0, -1, True, False, 2.5, '3', float('nan')])
@pytest.mark.parametrize('function', [simulate, simulate_parallel, outcome_distributions])
def test_invalid_round_count_fails_before_setup(function, bad):
    seed = np.random.SeedSequence(42)
    with patch('bj.simulate._tables') as tables:
        with pytest.raises(ValueError, match='n must be a positive integer'):
            function(bad, seed=seed)
        tables.assert_not_called()
    assert seed.n_children_spawned == 0


@pytest.mark.parametrize('bad', [0, -1, True, False, 2.5, '3'])
@pytest.mark.parametrize('function', [simulate_parallel, outcome_distributions])
def test_invalid_worker_count_is_not_coerced(function, bad):
    seed = np.random.SeedSequence(42)
    with patch('bj.simulate._tables') as tables:
        with pytest.raises(ValueError, match='workers must be a positive integer'):
            function(10, workers=bad, seed=seed)
        tables.assert_not_called()
    assert seed.n_children_spawned == 0


def test_numpy_integer_sizes_remain_supported():
    expected = simulate(10, seed=123)
    assert simulate(np.int64(10), seed=123) == expected
    assert simulate_parallel(np.int64(10), np.int64(2), seed=123) == expected
