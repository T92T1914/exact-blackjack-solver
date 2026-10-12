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
    assert 0 < work['states'] == work['attempted_states'] <= 59669
    assert work['states'] == sum(work['state_counts'].values())
    assert set(work['state_counts']) <= bounded_ace_resplit.FAMILIES


def test_h17_full_request_at_observed_insufficient_cap_publishes_no_value():
    with pytest.raises(EnumerationLimitExceeded) as error:
        record.bounded_ace_resplit_record(
            ('A', 'A'), 'A', rules(s17=False),
            shoe=(1, 2, 1, 2, 2, 2, 2, 2, 2, 4), max_states=82779)
    assert error.value.work['states'] == 82779
    assert error.value.work['attempted_states'] == 82780
    assert error.value.work['states'] == sum(error.value.work['state_counts'].values())


def test_ace_upcard_h17_twenty_card_full_map_matches_original_below_original_cap():
    retained = [1, 2, 1, 2, 2, 2, 2, 2, 2, 4]
    saved, work = record._bounded_ace_resplit_record(
        ('A', 'A'), 'A', rules(s17=False), shoe=retained)
    answer = saved['decision']
    assert saved['schema']['version'] == 6
    assert saved['state']['shoe']['counts'] == retained
    assert retained == [1, 2, 1, 2, 2, 2, 2, 2, 2, 4]
    assert list(answer['evs']) == ['S', 'H', 'D', 'P']
    assert {action: value.hex() for action, value in answer['evs'].items()} == {
        'S': '-0x1.5c169153f2a34p-1', 'H': '0x1.bf9edbd5c53ccp-6',
        'D': '-0x1.2cc1b8f43200dp-1', 'P': '-0x1.317c500abfae6p-3'}
    assert answer['action'] == 'H'
    assert answer['margin'].hex() == '0x1.69702b8578560p-3'
    assert work['limit'] == 100000
    assert 0 < work['states'] == work['attempted_states'] <= work['limit']
    assert work['states'] == sum(work['state_counts'].values())
    assert set(work['state_counts']) <= bounded_ace_resplit.FAMILIES
