"""The split error study: its evaluator, its dealer pass and its saved results.

The evaluator answers the same model as `bj.joint_split`, so the bounded
reference checks it value for value and refusal for refusal on small shoes.
The dealer pass is checked against `bj.dealer` on the full six deck shoe. The
saved study is checked against its document and the README, and the slow set
recomputes every saved cell through the script's check mode.
"""
from __future__ import annotations

import json
from dataclasses import asdict
import os
import random
import subprocess
import sys

import numpy as np
import pytest

from bj import dealer, ev
from bj.common_shoe import reference_counts
from bj.core import Rules
from bj.joint_split import UnsupportedShoeError as ReferenceRefused, joint_split_value
from tools import split_error_study as study

SLOW = pytest.mark.skipif(
    not os.environ.get('BJ_SLOW'),
    reason='heavy recomputation; set BJ_SLOW=1 to include it',
)


def saved():
    return json.loads(study.RESULTS.read_text(encoding='utf-8'))


def test_evaluator_matches_the_bounded_reference_on_small_shoes():
    rng = random.Random(20261114)
    agreed = refused = 0
    for _ in range(120):
        shoe = [0] * 10
        for _ in range(rng.randint(3, 11)):
            shoe[rng.randrange(10)] += 1
        pair, up = rng.choice(study.RANKS), rng.choice(study.RANKS)
        rules = dict(double_after_split=rng.random() < 0.5, stand_soft_17=rng.random() < 0.5)
        try:
            expected = joint_split_value(pair, up, reference_counts(tuple(shoe)),
                                         max_states=1_000_000, max_seconds=60, **rules).value
        except ReferenceRefused:
            with pytest.raises(study.UnsupportedShoeError):
                study.common_shoe_two_hand_split(pair, up, shoe, **rules)
            refused += 1
            continue
        found = study.common_shoe_two_hand_split(pair, up, shoe, **rules).value
        assert found == pytest.approx(expected, abs=1e-12, rel=0), (pair, up, shoe, rules)
        agreed += 1
    # This seed gives 39 values and 81 refusals. Both kinds must stay well represented.
    assert agreed >= 30 and refused >= 30


@pytest.mark.parametrize('up', study.RANKS)
@pytest.mark.parametrize('stand_soft_17', [True, False])
def test_dealer_pass_matches_the_production_dealer_on_six_decks(up, stand_soft_17):
    rules = Rules(max_hands=2, s17=stand_soft_17)
    shoe = ev.initial_shoe_for(('8', '8'), up, rules)
    hands = study._Hands(study.RANKS.index('8'), shoe)
    unions = study._unions(shoe, hands)
    sample = unions[::max(1, len(unions) // 25)]
    graph = study._DealerGraph(study.RANKS.index(up), stand_soft_17)
    rows = study._dealer_rows(study.RANKS.index(up), shoe, sample, graph)
    for removed, row in zip(study._decode(sample), rows):
        remaining = tuple(int(c) for c in np.asarray(shoe) - removed)
        expected = dealer.dealer_distribution(up, remaining, rules)[:6]
        assert row == pytest.approx(expected, abs=1e-14, rel=0)


@pytest.mark.parametrize('pair, up, rules', [
    ('A', 'A', study.TABLE),
    ('T', '6', study.TABLE),
    ('9', '7', study.TABLE),
    ('8', 'T', study.TABLE),
    ('8', 'A', study.TABLE),
    ('9', '2', Rules(max_hands=2, das=False)),
    ('8', '6', Rules(max_hands=2, s17=False)),
])
def test_the_default_policy_earns_the_default_value_in_a_common_shoe(pair, up, rules):
    cell = study.study_cell(pair, up, rules)
    # The default's own choices, settled in one shared shoe, give back its value.
    assert abs(cell['default_policy_difference']) <= study.TOLERANCE
    # So the optimum over a larger set of policies cannot be lower.
    assert cell['difference'] <= study.TOLERANCE


def test_saved_study_matches_its_document_and_the_readme():
    results = saved()
    assert len(results['cells']) == 100
    assert results['rules'] == asdict(study.TABLE)
    assert results['summary'] == study.summarize(results['cells'])
    document = study.DOCUMENT.read_text(encoding='utf-8')
    assert study.document_table(document) == study.render_table(results)
    summary = results['summary']
    assert summary['default_above_common_shoe'] == 0
    assert summary['largest_default_excess'] <= study.TOLERANCE
    assert summary['largest_default_policy_difference'] <= study.TOLERANCE
    # The prose states these numbers, so they must follow from the saved cells.
    assert summary['decision_changes'] == []
    assert f"{summary['within_tolerance']} of the 100 cells" in ' '.join(document.split())
    assert f"{summary['largest_default_excess']:.1e}" in document
    assert f"{summary['largest_default_policy_difference']:.1e}" in document
    twos = max(results['cells'], key=lambda cell: cell['union_shoes'])
    assert f"{twos['union_shoes']:,}" in document
    assert f"{twos['first_hand_endings']:,} first hand endings" in document
    assert f"{round(results['elapsed_seconds'] / 60)} minutes" in document
    worst = summary['worst']
    readme = ' '.join((study.ROOT / 'README.md').read_text(encoding='utf-8').split())
    for text in (' '.join(document.split()), readme):
        assert f"{worst['pair']},{worst['pair']} against {worst['up']}" in text
        assert f"{-worst['difference']:.9f}" in text
    assert 'no best action changes' in readme


@pytest.mark.parametrize('pair', ['A', 'T'])
def test_cheap_saved_cells_recompute(pair):
    cells = [cell for cell in saved()['cells'] if cell['pair'] == pair]
    fresh = study.run_study(pairs=(pair,), upcards=tuple(cell['up'] for cell in cells))
    assert study.compare({'cells': cells}, fresh) == []


@pytest.mark.parametrize('rules', [Rules(), Rules(max_hands=2, resplit_aces=True),
                                   Rules(max_hands=2, hit_split_aces=True)])
def test_study_refuses_rules_the_common_shoe_model_lacks(rules):
    with pytest.raises(ValueError, match='two hands with no resplit'):
        study.study_cell('A', '6', rules)


@pytest.mark.parametrize('shoe', [(0,) * 10, (0,) * 9 + (2,)])
def test_evaluator_needs_two_drawable_cards_and_the_hole(shoe):
    with pytest.raises(ValueError, match='hidden hole'):
        study.TwoHandSplit('8', '6', shoe)


def test_output_never_replaces_an_existing_file(tmp_path, capsys):
    existing = tmp_path / 'results.json'
    existing.write_text('{}', encoding='utf-8')
    with pytest.raises(SystemExit):
        study.main(['--output', str(existing)])
    assert existing.read_text(encoding='utf-8') == '{}'
    assert 'Choose a new path' in capsys.readouterr().err


@SLOW
@pytest.mark.slow
def test_check_mode_recomputes_every_saved_cell():
    result = subprocess.run([sys.executable, str(study.ROOT / 'tools/split_error_study.py'),
                             '--check'], capture_output=True, text=True, cwd=study.ROOT)
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-4000:]
    assert 'check passed' in result.stdout
