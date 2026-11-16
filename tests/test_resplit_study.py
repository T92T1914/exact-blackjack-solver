"""The resplit study: its shortcut, the default's choices and the saved results.

The shortcut values the default's play in one shared shoe from first cards
alone. A deal by deal enumeration checks it on small shoes that cannot run out,
with three and four hands. The bounded optimum in `bj.joint_resplit` checks
that the play never beats the best play on the same shoes. The choices are
checked by rebuilding the default's own value from them on the full shoe.
"""
from __future__ import annotations

import json
import math
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
    reason='heavy recomputation, set BJ_SLOW=1 to include it',
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
    # The peek with resplitting: a ten up, an ace up, and a pair of the rank
    # the peek under an ace rules out.
    ('8', 'T', (0, 0, 1, 0, 0, 1, 2, 4, 0, 5)),
    ('9', 'A', (0, 1, 1, 0, 0, 0, 2, 0, 3, 5)),
    ('T', 'A', (1, 0, 0, 0, 2, 1, 0, 1, 0, 7)),
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


def physical_value(model, information=False):
    """Deal the default's play card by card from one shoe and settle every hand together.

    With `information` the second of the first two hands plays the information
    play in a round where neither of the two resplits: every choice is the best
    one on the value of the whole round, found here by trying each.
    """
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
            # Only the second hand waits, and every slot is left, so the first
            # hand did not resplit.
            informed = information and waiting == (0,) and slots == model.pool
            value = 0.0
            for rank, chance in enumerate(draws(shoe)):
                if chance <= 0.0:
                    continue
                if rank == pair and model.resplits(depth, slots):
                    value += chance * deal(take(shoe, rank), (depth + 1, depth + 1) + rest,
                                           slots - 1, None, completed)
                else:
                    value += chance * deal(take(shoe, rank), rest, slots,
                                           (depth, (rank,), informed), completed)
            return value
        depth, drawn, informed = hand
        total, soft = _state((pair,) + drawn)
        if total > 21 or (total == 21 and len(drawn) > 1):
            return deal(shoe, waiting, slots, None, tuple(sorted(completed + ((total, 1),))))
        if informed:
            stand = deal(shoe, waiting, slots, None, tuple(sorted(completed + ((total, 1),))))
            if total == 21 or (pair == 0 and not rules.hit_split_aces):
                return stand
            hit = double = 0.0
            for rank, chance in enumerate(draws(shoe)):
                if chance <= 0.0:
                    continue
                hit += chance * deal(take(shoe, rank), waiting, slots,
                                     (depth, drawn + (rank,), True), completed)
                ending = ((_total((pair,) + drawn + (rank,)), 2),)
                double += chance * deal(take(shoe, rank), waiting, slots, None,
                                        tuple(sorted(completed + ending)))
            if len(drawn) == 1 and rules.das:
                return max(stand, hit, double)
            return max(stand, hit)
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
                                       (depth, drawn + (rank,), False), completed)
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


@pytest.mark.parametrize('max_hands', [3, 4])
@pytest.mark.parametrize('pair, up, shoe', SMALL + BOUNDED)
def test_information_play_matches_a_deal_by_deal_enumeration(pair, up, shoe, max_hands):
    for rules in (Rules(max_hands=max_hands), Rules(max_hands=max_hands, das=False, s17=False)):
        model = study.DefaultResplit(pair, up, shoe, rules)
        gain = study.information_gain(pair, up, shoe, rules)
        if gain is None:
            # Then the default never resplits and the play is a two hand play.
            assert not model.resplits(0, model.pool)
            continue
        assert gain >= 0.0
        expected = physical_value(model, information=True)
        assert model.shared_shoe_value() + gain == pytest.approx(expected, abs=1e-12, rel=0)
        study.clear_caches()


def test_information_play_gains_on_small_shoes():
    # Otherwise the enumeration above would only test a gain of 0, and the
    # bounded optimum below would never meet a real gain.
    def gains(shoes, rules):
        found = [study.information_gain(pair, up, shoe, rules) for pair, up, shoe in shoes]
        return sum(gain is not None and gain > 1e-5 for gain in found)

    assert gains(SMALL + BOUNDED, Rules()) == 4
    assert gains(SMALL + BOUNDED, Rules(das=False, s17=False)) == 3
    assert gains(BOUNDED, Rules(max_hands=3)) == 1
    study.clear_caches()


def _at_least(value: float) -> str:
    # The prose says split stays best by "at least" this margin, so round down.
    return f'{math.floor(value * 1e4) / 1e4:.4f}'


def test_small_shoes_reach_more_than_two_hands():
    # Otherwise the enumeration above would not test resplitting at all. The
    # 9,9 shoe against an ace never resplits and covers the peek under an ace.
    hands = [study.DefaultResplit(pair, up, shoe, Rules()).shared_shoe_hands()
             for pair, up, shoe in SMALL]
    assert sum(count > 2.1 for count in hands) == len(SMALL) - 1
    study.clear_caches()


def test_four_hands_reach_further_than_three_on_small_shoes():
    # So the enumeration with four hands takes the second resplit, not only the first.
    more = 0
    for pair, up, shoe in SMALL + BOUNDED:
        three = study.DefaultResplit(pair, up, shoe, Rules(max_hands=3)).shared_shoe_hands()
        four = study.DefaultResplit(pair, up, shoe, Rules()).shared_shoe_hands()
        assert four >= three - 1e-12
        more += four > three + 0.01
        study.clear_caches()
    assert more >= len(SMALL + BOUNDED) - 2


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
        gain = study.information_gain(pair, up, shoe, rules)
        if gain is not None:
            assert own <= own + gain <= optimum + 1e-12, (pair, up, das)
        study.clear_caches()


@pytest.mark.parametrize('pair, up', [('8', '7'), ('8', 'T'), ('2', '4'), ('7', '7'),
                                      ('A', '6'), ('9', '9')])
@pytest.mark.parametrize('name', sorted(study.RULE_TABLES))
def test_the_choices_rebuild_the_default_value(pair, up, name):
    rules = study.RULE_TABLES[name]
    shoe = ev.initial_shoe_for((pair, pair), up, rules)
    model = study.DefaultResplit(pair, up, shoe, rules)
    assert model.default_value() == pytest.approx(ev.ev_split(pair, up, shoe, rules),
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
    for rules in (Rules(hit_split_aces=True), Rules(decks=2), Rules(s17=False, das=False)):
        assert study.table_name(rules) is None
        with pytest.raises(ValueError, match='variants only'):
            study.study_cell('8', '7', cell, rules)
    with pytest.raises(ValueError, match='does not hold'):
        study.study_cell('8', 'T', cell)


def test_the_variants_read_their_own_two_hand_results():
    assert study.table_name(study.TABLE) == 'default'
    for name, rules in study.RULE_TABLES.items():
        assert study.table_name(rules) == name
        assert study.two_hand.TABLES[name] == study.two_hand_table(rules)
        cells = study.two_hand_cells(study.two_hand.results_path(name), rules)
        assert len(cells) == 100
    with pytest.raises(ValueError, match='does not hold'):
        study.two_hand_cells(study.two_hand.results_path('h17'), study.TABLE)


def test_a_results_file_must_hold_the_table_it_is_checked_as(capsys):
    with pytest.raises(SystemExit):
        study.main(['--check', '--table', 'h17', '--results', str(study.RESULTS)])
    assert 'does not hold the h17 table' in capsys.readouterr().err


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
    assert summary['largest_rebuild_difference'] <= 1e-14
    assert summary['decision_changes'] == []
    # Where the default is above every value computed here, split is still the
    # best action under that value, by far more than the excess.
    above = [cell for cell in results['cells'] if cell['difference'] > study.TOLERANCE]
    for cell in above:
        assert cell['default_best'] == cell['lower_bound_best'] == ['P']
        assert cell['lower_bound_margin'] > 100 * cell['difference']
    # Where the default resplits its own play gives the bound. Elsewhere that
    # play is its two hand play, and the two hand value is at least as large.
    for cell in results['cells']:
        assert cell['three_hand_play_in_common_shoe'] <= max(
            cell['default_play_in_common_shoe'], cell['two_hand_common_shoe_split'])
        if cell['default_hands'] > 2.0:
            assert cell['lower_bound_source'] == 'default play'
        else:
            assert abs(cell['default_policy_difference']) <= study.TOLERANCE
            assert (cell['two_hand_common_shoe_split']
                    >= cell['default_play_in_common_shoe'] - study.TOLERANCE)
    # The prose states these numbers, so they must follow from the saved cells.
    text = ' '.join(document.split())
    readme = ' '.join((study.ROOT / 'README.md').read_text(encoding='utf-8').split())
    worst, gain = summary['worst'], summary['largest_own_play_gain']
    excess, closest = summary['largest_default_excess'], summary['closest_split_shortfall']
    for source in (text, readme):
        for cell in (worst, gain, excess):
            assert f"{cell['pair']},{cell['pair']} against {cell['up']}" in source
        assert f"{-worst['difference']:.9f}" in source
        assert f"{gain['difference']:.9f}" in source
        assert f"{excess['difference']:.9f}" in source
        assert f"{closest['shortfall']:.4f} units" in source
    assert f"{closest['pair']},{closest['pair']} against {closest['up']}" in text
    assert _at_least(min(cell['lower_bound_margin'] for cell in above)) in text
    assert f"{summary['own_play_above_default']} of the 100 cells" in text
    assert f"In {summary['own_play_below_default']} cells it earns less" in text
    assert f"other {summary['default_above_lower_bound']} cells" in text
    assert f"{summary['within_tolerance']} of the 100 cells" in text
    assert f"{100 - summary['default_above_lower_bound']} of the 100 cells" in text
    rounding = max(c['difference'] for c in results['cells'] if c not in above)
    assert f"rounding, which reaches {rounding:.1e} here" in text
    assert f"the {summary['resplitting_cells']} cells where the default resplits" in text
    assert f"{round(results['elapsed_seconds'])} seconds" in text


def _section(document, name):
    """The document text of one variant: from its heading to the next heading."""
    heading = {'h17': '### H17\n', 'no-das': '### No double after split\n'}[name]
    start = document.index(heading) + len(heading)
    end = document.find('\n#', start)
    return ' '.join(document[start:end].split())


@pytest.mark.parametrize('name', ['h17', 'no-das'])
def test_saved_variant_studies_match_their_document(name):
    path = study.results_path(name)
    results = json.loads(path.read_text(encoding='utf-8'))
    rules = study.RULE_TABLES[name]
    assert len(results['cells']) == 100
    assert results['rules'] == asdict(rules)
    assert results['summary'] == study.summarize(results['cells'])
    two_hand_path = study.two_hand.results_path(name)
    assert results['two_hand_results_sha256_lf'] == study._sha256(two_hand_path)
    assert results['evaluated_sources_modified'] is False
    document = study.DOCUMENT.read_text(encoding='utf-8')
    for table in study.TABLES:
        assert study.document_table(document, table, name) == study.render_table(results, table)
    summary = results['summary']
    assert summary['largest_rebuild_difference'] <= 1e-14
    assert summary['decision_changes'] == []
    above = [cell for cell in results['cells'] if cell['difference'] > study.TOLERANCE]
    for cell in above:
        assert cell['default_best'] == cell['lower_bound_best'] == ['P']
        assert cell['lower_bound_margin'] > 100 * cell['difference']
    for cell in results['cells']:
        assert cell['three_hand_play_in_common_shoe'] <= max(
            cell['default_play_in_common_shoe'], cell['two_hand_common_shoe_split'])
        if cell['default_hands'] > 2.0:
            assert cell['lower_bound_source'] == 'default play'
        else:
            assert abs(cell['default_policy_difference']) <= study.TOLERANCE
    # The prose states these numbers, so they must follow from the saved cells.
    text = _section(document, name)
    worst, gain = summary['worst'], summary['largest_own_play_gain']
    excess, closest = summary['largest_default_excess'], summary['closest_split_shortfall']
    for cell in (worst, gain, excess, closest):
        assert f"{cell['pair']},{cell['pair']} against {cell['up']}" in text
    assert f"{-worst['difference']:.9f} units" in text
    assert f"{gain['difference']:.9f} units" in text
    assert f"{excess['difference']:.9f} units" in text
    assert f"{closest['shortfall']:.4f} units" in text
    assert f"{_at_least(min(cell['lower_bound_margin'] for cell in above))} units" in text
    assert f"{summary['own_play_above_default']} cells" in text
    assert f"less in {summary['own_play_below_default']} cells" in text
    assert f"In the other {summary['default_above_lower_bound']} cells" in text
    assert f"within 1e-12 in {summary['within_tolerance']} cells" in text
    assert f"resplits in {summary['resplitting_cells']}" in text
    assert f"In {100 - summary['default_above_lower_bound']} of the 100 cells" in text
    rounding = max(c['difference'] for c in results['cells'] if c not in above)
    assert f"rounding, which reaches {rounding:.1e} here" in text
    assert f"{round(results['elapsed_seconds'])} seconds" in text


def test_the_readme_states_the_variant_extremes():
    readme = ' '.join((study.ROOT / 'README.md').read_text(encoding='utf-8').split())
    summaries = [json.loads(study.results_path(name).read_text(encoding='utf-8'))['summary']
                 for name in ('h17', 'no-das')]
    assert all(summary['default_above_lower_bound'] == 5 for summary in summaries)
    most_above = max(s['largest_default_excess']['difference'] for s in summaries)
    most_below = max(-s['worst']['difference'] for s in summaries)
    assert f'{most_above:.9f} units' in readme
    assert f'{most_below:.9f} units' in readme


def test_h17_equals_the_default_where_no_soft_17_arises():
    # A dealer 7, 8, 9 or T cannot reach a soft 17, so H17 changes nothing there.
    default = {(c['pair'], c['up']): c for c in saved()['cells']}
    h17 = json.loads(study.results_path('h17').read_text(encoding='utf-8'))
    for cell in h17['cells']:
        if cell['up'] in '789T':
            other = default[(cell['pair'], cell['up'])]
            assert cell['default_split'] == other['default_split']
            assert cell['difference'] == other['difference']


@pytest.mark.parametrize('name', ['default', 'h17', 'no-das'])
@pytest.mark.parametrize('pair', ['A', 'T'])
def test_cheap_saved_cells_recompute(pair, name):
    path = study.results_path(name)
    results = json.loads(path.read_text(encoding='utf-8'))
    cells = [cell for cell in results['cells'] if cell['pair'] == pair]
    fresh = study.run_study(pairs=(pair,), upcards=tuple(cell['up'] for cell in cells),
                            rules=study.RULE_TABLES[name])
    assert study.compare({'cells': cells}, fresh) == []


@SLOW
@pytest.mark.slow
@pytest.mark.parametrize('name', ['default', 'h17', 'no-das'])
def test_check_mode_recomputes_every_saved_cell(name):
    result = subprocess.run([sys.executable, str(study.ROOT / 'tools/resplit_study.py'),
                             '--check', '--table', name], capture_output=True, text=True,
                            cwd=study.ROOT)
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-4000:]
    assert 'check passed' in result.stdout


def test_ranks_are_in_production_order():
    assert tuple(RANKS) == study.RANKS
