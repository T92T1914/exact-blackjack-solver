"""A split ace that receives one card cannot become a three-card hand."""
from dataclasses import replace

import pytest

from bj import caches, cli, ev, record
from bj.core import RANKS, STANDARD, STAND


def _shoe(cards):
    return tuple(cards.count(rank) for rank in RANKS)


CASES = [('a,5,5', '6', ('T', 'T')), ('A,2,3', '7', ('T', 'T', 'T'))]


@pytest.mark.parametrize('cards,up,unseen', CASES)
@pytest.mark.parametrize('resplit_aces', [False, True])
@pytest.mark.parametrize('consumer', [ev.best_action, cli.advise,
                                     record.decision_record, record.decision_json])
def test_impossible_split_ace_refuses_before_cache_admission(
        cards, up, unseen, resplit_aces, consumer):
    # Resplitting produces new one-ace hands. It does not permit extra draws
    # to the same hand when each split ace is limited to one additional card.
    rules = replace(STANDARD, resplit_aces=resplit_aces)
    caches.clear_all_caches()
    before = caches.cache_info()
    with pytest.raises(ValueError, match='split ace receives only one card'):
        consumer(cards, up, rules=rules, shoe=_shoe(unseen),
                 is_split_hand=True, hand_count=2)
    assert caches.cache_info() == before


@pytest.mark.parametrize('cards,up,unseen', CASES)
@pytest.mark.parametrize('json_mode', [False, True])
def test_cli_refuses_impossible_split_ace_without_a_report(cards, up, unseen, json_mode, capsys):
    arguments = [cards, up, '--unseen', ','.join(unseen), '--split-hand']
    if json_mode:
        arguments.append('--json')
    with pytest.raises(SystemExit) as exc:
        cli.main(arguments)
    assert exc.value.code == 2
    output = capsys.readouterr()
    assert output.out == ''
    assert 'split ace receives only one card' in output.err


@pytest.mark.parametrize('cards,up,unseen,split,hit_split_aces,expected', [
    (('A', '6'), '7', ('T', 'T'), True, False, 0),
    (('A', '5', '5'), '6', ('T', 'T'), True, True, 1),
    (('5', 'A', '5'), '6', ('T', 'T'), True, False, 1),
    (('A', '5', '5'), '6', ('T', 'T'), False, False, 1),
])
def test_legal_controls_keep_their_analytic_settlement(
        cards, up, unseen, split, hit_split_aces, expected):
    # With only tens unseen, 7+T makes dealer17 and pushes A,6. Dealer6+T
    # must draw the other ten and busts at26, losing to every declared21.
    # A later ace does not change the original split rank, which stays first.
    rules = replace(STANDARD, hit_split_aces=hit_split_aces)
    context = {'is_split_hand': split, 'hand_count': 2 if split else 1}
    assert ev.best_action(cards, up, _shoe(unseen), rules, **context) == (
        STAND, {STAND: expected}, 0.0,
    )
    answer = record.decision_record(cards, up, rules, shoe=_shoe(unseen), **context)
    assert answer['decision']['evs'] == {STAND: expected}
    assert answer['state']['cards'] == list(cards)
