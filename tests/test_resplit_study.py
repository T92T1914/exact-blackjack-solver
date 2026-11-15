"""The resplit study: its shortcut, the default's choices and the saved results.

The shortcut values the default's play in one shared shoe from first cards
alone. A deal by deal enumeration checks it on small shoes that cannot run out,
with three and four hands. The bounded optimum in `bj.joint_resplit` checks
that the play never beats the best play on the same shoes. The choices are
checked by rebuilding the default's own value from them on the full shoe.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from functools import lru_cache
import os
import subprocess
import sys

import pytest

from bj import dealer, ev
from bj.common_shoe import reference_counts
from bj.core import DOUBLE, RANKS, STAND, Rules
from bj.joint_resplit import joint_resplit_value
from tools import resplit_study as study

SLOW = pytest.mark.skipif(
    not os.environ.get('BJ_SLOW'),
    reason='heavy recomputation; set BJ_SLOW=1 to include it',
)

#: Small shoes in production order A, 2 to 9, T. None of them can run out in
#: any deal below, and the enumeration raises if one ever did.
SMALL = [
    ('8', '7', (1, 1, 1, 0, 1, 2, 2, 3, 2, 6)),
    ('9', 'A', (1, 0, 1, 0, 0, 2, 2, 2, 3, 7)),
    ('7', '6', (0, 1, 1, 0, 1, 1, 3, 2, 2, 7)),
    ('6', '5', (1, 0, 0, 0, 1, 3, 2, 2, 2, 6)),
    ('7', '7', (0, 1, 1, 0, 1, 2, 2, 2, 2, 8)),
    ('3', '4', (0, 0, 2, 0, 0, 1, 2, 2, 2, 8)),
]
#: Shoes of 11 to 14 cards that the bounded optimum completes inside its state
#: limit, each with a resplit the default takes. Found by a seeded search.
BOUNDED = [
    ('T', '4', (2, 0, 5, 0, 0, 0, 0, 0, 2, 5)),
    ('T', '2', (1, 1, 0, 0, 2, 1, 0, 0, 1, 6)),
    ('8', '4', (0, 1, 0, 0, 1, 1, 0, 3, 0, 5)),
    ('9', '2', (0, 1, 0, 0, 1, 3, 0, 0, 4, 5)),
    ('8', '6', (1, 0, 1, 0, 1, 1, 1, 1, 1, 5)),
    ('9', '6', (1, 0, 0, 0, 3, 0, 0, 1, 3, 5)),
    ('7', '6', (2, 0, 0, 0, 0, 3, 2, 0, 0, 5)),
]


def saved():
    return json.loads(study.RESULTS.read_text(encoding='utf-8'))


def _state(cards):
    """Best total of production rank indices, and whether an ace counts as 11."""
    low = sum(1 if rank == 0 else 10 if rank == 9 else rank + 1 for rank in cards)
    soft = 0 in cards and low + 10 <= 21
    return low + (10 if soft else 0), soft


def _total(cards):
    return _state(cards)[0]


def physical_value(model):
    """Deal the default's play card by card from one shoe and settle every hand together."""
    up, rules, pair = model.up, model.rules, model.pair
    excluded = {'A': 9, 'T': 0}.get(up, -1)

    def draws(shoe):
        n = sum(shoe)
        assert n >= 2, 'a deal ran out of cards'
        if excluded < 0:
            return [count / n for count in shoe]
        # The hole is uniform over the ranks the peek allows and is never drawn.
        live = n - shoe[excluded]
        assert live > 0, 'no hole card is possible'
        return [(count if rank == excluded else count - count / live) / (n - 1)
                for rank, count in enumerate(shoe)]

    def take(shoe, rank):
        return shoe[:rank] + (shoe[rank] - 1,) + shoe[rank + 1:]

    def settle(shoe, completed):
        final = dealer.dealer_distribution(up, shoe, rules)
        value = 0.0
        for total, wager in completed:
            if total > 21:
                value -= wager
                continue
            value += wager * final[dealer.IBUST]
            for column in range(5):
                value += wager * final[column] * ((total > 17 + column) - (total < 17 + column))
        return value

    @lru_cache(maxsize=None)
    def deal(shoe, waiting, slots, hand, completed):
        if hand is None:
            if not waiting:
                return settle(shoe, completed)
            depth, rest = waiting[0], waiting[1:]
            value = 0.0
            for rank, chance in enumerate(draws(shoe)):
                if chance <= 0.0:
                    continue
                if rank == pair and model.resplits(depth, slots):
                    value += chance * deal(take(shoe, rank), (depth + 1, depth + 1) + rest,
                                           slots - 1, None, completed)
                else:
                    value += chance * deal(take(shoe, rank), rest, slots, (depth, (rank,)),
                                           completed)
            return value
        depth, drawn = hand
        total, soft = _state((pair,) + drawn)
        if total > 21 or (total == 21 and len(drawn) > 1):
            return deal(shoe, waiting, slots, None, tuple(sorted(completed + ((total, 1),))))
        if len(drawn) == 1:
            choice = model.action(depth, drawn[0])
        else:
            # After a hit the default decides from its own shoe less this hand's cards.
            decide = model.start(depth)
            for rank in drawn:
                decide = take(decide, rank)
            stand = ev._stand_ev(total, up, decide, rules.s17)
            choice = STAND if stand > ev._hit_ev(total, soft, up, decide, rules.s17) else 'H'
        if choice == STAND:
            return deal(shoe, waiting, slots, None, tuple(sorted(completed + ((total, 1),))))
        value = 0.0
        for rank, chance in enumerate(draws(shoe)):
            if chance <= 0.0:
                continue
            if choice == DOUBLE:
                ending = ((_total((pair,) + drawn + (rank,)), 2),)
                value += chance * deal(take(shoe, rank), waiting, slots, None,
                                       tuple(sorted(completed + ending)))
            else:
                value += chance * deal(take(shoe, rank), waiting, slots,
                                       (depth, drawn + (rank,)), completed)
        return value

    return deal(model.shoe, (0, 0), model.pool, None, ())


@pytest.mark.parametrize('max_hands', [3, 4])
@pytest.mark.parametrize('pair, up, shoe', SMALL + BOUNDED)
def test_shortcut_matches_a_deal_by_deal_enumeration(pair, up, shoe, max_hands):
    for rules in (Rules(max_hands=max_hands), Rules(max_hands=max_hands, das=False, s17=False)):
        model = study.DefaultResplit(pair, up, shoe, rules)
        expected = physical_value(model)
        assert model.shared_shoe_value() == pytest.approx(expected, abs=1e-12, rel=0)
        study.clear_caches()


def test_small_shoes_reach_more_than_two_hands():
    # Otherwise the enumeration above would not test resplitting at all. The
    # 9,9 shoe against an ace never resplits and covers the peek under an ace.
    hands = [study.DefaultResplit(pair, up, shoe, Rules()).shared_shoe_hands()
             for pair, up, shoe in SMALL]
    assert sum(count > 2.1 for count in hands) == len(SMALL) - 1
    study.clear_caches()


@pytest.mark.parametrize('pair, up, shoe', BOUNDED)
def test_the_play_never_beats_the_bounded_optimum(pair, up, shoe):
    # bj.joint_resplit allows three hands and chooses every action on the round.
    assert study.DefaultResplit(pair, up, shoe, Rules(max_hands=3)).shared_shoe_hands() > 2.1
    for das in (True, False):
        rules = Rules(max_hands=3, das=das)
        optimum = joint_resplit_value(pair, up, reference_counts(shoe), double_after_split=das,
                                      stand_soft_17=True, max_states=100_000,
                                      max_seconds=120).value
        own = study.DefaultResplit(pair, up, shoe, rules).shared_shoe_value()
        assert own <= optimum + 1e-12, (pair, up, das)
        study.clear_caches()


@pytest.mark.parametrize('pair, up', [('8', '7'), ('8', 'T'), ('2', '4'), ('7', '7'),
                                      ('A', '6'), ('9', '9')])
def test_the_choices_rebuild_the_default_value(pair, up):
    shoe = ev.initial_shoe_for((pair, pair), up, study.TABLE)
    model = study.DefaultResplit(pair, up, shoe)
    assert model.default_value() == pytest.approx(ev.ev_split(pair, up, shoe, study.TABLE),
                                                  abs=1e-14, rel=0)
    study.clear_caches()


@pytest.mark.parametrize('pair, up', [('8', 'T'), ('2', '4'), ('9', '7'), ('5', 'A')])
def test_two_hands_give_back_the_default_value(pair, up):
    # With no resplit the shortcut is the two hand study's own check.
    rules = Rules(max_hands=2)
    shoe = ev.initial_shoe_for((pair, pair), up, rules)
    value = study.DefaultResplit(pair, up, shoe, rules).shared_shoe_value()
    assert value == pytest.approx(ev.ev_split(pair, up, shoe, rules), abs=1e-14, rel=0)
    study.clear_caches()


def test_hand_counts_follow_the_pool():
    shoe = ev.initial_shoe_for(('8', '8'), '7', study.TABLE)
    model = study.DefaultResplit('8', '7', shoe)
    assert 2.0 < model.default_hands() < 4.0
    assert 2.0 < model.shared_shoe_hands() < 4.0
    # With no pair card left nothing can resplit, so both sides give two hands.
    empty = shoe[:7] + (0,) + shoe[8:]
    model = study.DefaultResplit('8', '7', empty)
    assert model.default_hands() == 2.0
    assert model.shared_shoe_hands() == pytest.approx(2.0, abs=1e-15)
    study.clear_caches()


def test_study_refuses_other_tables():
    cell = study.two_hand_cells()[('8', '7')]
    with pytest.raises(ValueError, match='default table only'):
        study.study_cell('8', '7', cell, Rules(s17=False))
    with pytest.raises(ValueError, match='does not hold'):
        study.study_cell('8', 'T', cell)


def test_output_never_replaces_an_existing_file(tmp_path, capsys):
    existing = tmp_path / 'results.json'
    existing.write_text('{}', encoding='utf-8')
    with pytest.raises(SystemExit):
        study.main(['--output', str(existing)])
    assert existing.read_text(encoding='utf-8') == '{}'
    assert 'Choose a new path' in capsys.readouterr().err


def test_saved_study_matches_its_document_and_the_readme():
    results = saved()
    assert len(results['cells']) == 100
    assert results['rules'] == asdict(study.TABLE)
    assert results['summary'] == study.summarize(results['cells'])
    assert results['two_hand_results_sha256_lf'] == study._sha256(study.TWO_HAND_RESULTS)
    document = study.DOCUMENT.read_text(encoding='utf-8')
    for table in study.TABLES:
        assert study.document_table(document, table) == study.render_table(results, table)
    summary = results['summary']
    assert summary['default_above_lower_bound'] == 0
    assert summary['largest_default_excess'] <= study.TOLERANCE
    assert summary['largest_own_play_shortfall'] <= study.TOLERANCE
    assert summary['largest_rebuild_difference'] <= 1e-14
    assert summary['decision_changes'] == []
    text = ' '.join(document.split())
    worst, gain = summary['worst'], summary['largest_own_play_gain']
    closest = summary['closest_split_shortfall']
    assert f"{worst['pair']},{worst['pair']} against {worst['up']}" in text
    assert f"{-worst['difference']:.9f}" in text
    assert f"{gain['pair']},{gain['pair']} against {gain['up']}" in text
    assert f"{gain['difference']:.9f}" in text
    assert f"{summary['own_play_above_default']} of the 100 cells" in text
    assert f"{summary['bound_from_default_play']} cells" in text
    assert f"{closest['pair']},{closest['pair']} against {closest['up']}" in text
    assert f"{closest['shortfall']:.6f}" in text
    assert f"{round(results['elapsed_seconds'] / 60)} minutes" in text
    readme = ' '.join((study.ROOT / 'README.md').read_text(encoding='utf-8').split())
    assert f"{-worst['difference']:.9f}" in readme
    assert f"{gain['difference']:.9f}" in readme


@pytest.mark.parametrize('pair', ['A', 'T'])
def test_cheap_saved_cells_recompute(pair):
    cells = [cell for cell in saved()['cells'] if cell['pair'] == pair]
    fresh = study.run_study(pairs=(pair,), upcards=tuple(cell['up'] for cell in cells))
    assert study.compare({'cells': cells}, fresh) == []


@SLOW
@pytest.mark.slow
def test_check_mode_recomputes_every_saved_cell():
    result = subprocess.run([sys.executable, str(study.ROOT / 'tools/resplit_study.py'),
                             '--check'], capture_output=True, text=True, cwd=study.ROOT)
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-4000:]
    assert 'check passed' in result.stdout


def test_ranks_are_in_production_order():
    assert tuple(RANKS) == study.RANKS
