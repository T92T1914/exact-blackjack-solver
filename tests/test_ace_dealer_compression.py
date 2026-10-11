"""Complete-root coverage and literal values from bounded original arithmetic."""
from __future__ import annotations

from dataclasses import replace

import pytest

from bj import bounded_ace_resplit, record
from bj._enumeration import EnumerationLimitExceeded
from bj.caches import clear_all_caches
from bj.core import STANDARD


@pytest.fixture(autouse=True)
def cold_caches():
    clear_all_caches()
    yield
    clear_all_caches()


def rules(**changes):
    return replace(STANDARD, max_hands=3, resplit_aces=True, **changes)


def test_mixed_twenty_card_full_map_matches_original_arithmetic_below_original_cap():
    retained = [1, 2, 1, 2, 2, 2, 2, 2, 1, 5]
    saved, work = record._bounded_ace_resplit_record(
        ('A', 'A'), '6', rules(), shoe=retained)
    assert saved['schema']['version'] == 6
    assert saved['state']['shoe']['counts'] == retained
    assert retained == [1, 2, 1, 2, 2, 2, 2, 2, 1, 5]
    assert {action: value.hex() for action, value in saved['decision']['evs'].items()} == {
        'S': '-0x1.d50aeffd76b9ep-3', 'H': '0x1.8bad5720e5ee0p-3',
        'D': '0x1.48070df0e5d1cp-4', 'P': '0x1.118ea81b61be8p-1'}
    assert saved['decision']['action'] == 'P'
    assert work['limit'] == 100000
    assert work['states'] == work['attempted_states'] == 59669
    assert work['states'] == sum(work['state_counts'].values())
    assert set(work['state_counts']) <= bounded_ace_resplit.FAMILIES


def test_same_mixed_request_with_insufficient_work_cap_publishes_no_value():
    with pytest.raises(EnumerationLimitExceeded) as error:
        record.bounded_ace_resplit_record(
            ('A', 'A'), '6', rules(), shoe=(1, 2, 1, 2, 2, 2, 2, 2, 1, 5),
            max_states=59668)
    assert error.value.work['states'] == 59668
    assert error.value.work['attempted_states'] == 59669


def test_ace_upcard_h17_twenty_card_request_still_refuses_at_original_limit():
    with pytest.raises(EnumerationLimitExceeded) as error:
        record.bounded_ace_resplit_record(
            ('A', 'A'), 'A', rules(s17=False),
            shoe=(1, 2, 1, 2, 2, 2, 2, 2, 2, 4))
    assert error.value.work['states'] == 100000
    assert error.value.work['attempted_states'] == 100001
