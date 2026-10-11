"""A formerly capped complete action map and unchanged publication boundaries."""
import json
from dataclasses import replace

import pytest

from bj import common_shoe, record, replay
from bj._enumeration import EnumerationLimitExceeded
from bj.caches import clear_all_caches
from bj.core import STANDARD


@pytest.fixture(autouse=True)
def cold_caches():
    clear_all_caches()
    yield
    clear_all_caches()


def test_twenty_card_peek_request_completes_without_raising_the_product_cap():
    # Original ordered-history arithmetic was completed separately under a
    # declared verification-only ceiling. Its full map is the regression
    # witness here, not an independent mathematical oracle.
    counts = (2, 1, 2, 1, 2, 2, 2, 2, 2, 4)
    rules = replace(STANDARD, max_hands=2, s17=False)
    saved, work = record._common_shoe_record(('A', 'A'), 'A', rules, shoe=counts)
    assert {a: v.hex() for a, v in saved['decision']['evs'].items()} == {
        'S': '-0x1.5a111902c4bf3p-1', 'H': '0x1.f237d5793a25cp-6',
        'D': '-0x1.2917e8ad4dcdap-1', 'P': '-0x1.875af261bdc11p-3',
    }
    assert saved['decision']['action'] == 'H'
    assert saved['schema']['version'] == 3
    assert saved['model']['split'] == common_shoe.SPLIT_MODEL
    assert saved['state']['shoe']['counts'] == list(counts)
    assert work['limit'] == 100000
    assert work['states'] == work['attempted_states'] == sum(work['state_counts'].values())
    assert 0 < work['states'] <= work['limit']
    assert replay.replay_json(json.dumps(saved))['status'] == 'agreement'


def test_compressed_request_still_refuses_instead_of_publishing_at_a_small_cap():
    with pytest.raises(EnumerationLimitExceeded) as error:
        record.common_shoe_record(('A', 'A'), 'A',
            replace(STANDARD, max_hands=2, s17=False),
            shoe=(2, 1, 2, 1, 2, 2, 2, 2, 2, 4), max_states=100)
    assert error.value.work['states'] == 100
    assert error.value.work['attempted_states'] == 101
