"""Exact rational cross check of the floating point values the README relies on.

`tests/rational_reference.py` restates the post peek hand, the common shoe
split families and the deferred second card model with exact fractions and
imports nothing from `bj`. These tests compare it with the engine on the 45
published stand, hit and double cells, on every bounded example request and on
random small shoes for every model it restates. `docs/rational-cross-check.md`
records what they find, and the last test keeps that record honest.
"""
from __future__ import annotations

import json
import math
import random
from fractions import Fraction
from pathlib import Path

import pytest

from bj import deferred_second_card, ev, record
from bj.calculation import _normalise
from bj.common_shoe import reference_counts
from bj.core import Rules
from bj.joint_ace_resplit import joint_ace_resplit_value
from bj.joint_resplit import joint_resplit_value
from bj.joint_split import ReferenceLimitExceeded, UnsupportedShoeError, joint_split_value

import rational_reference as exact
from test_ev import PUBLISHED

ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = ROOT / 'docs/rational-cross-check.md'
#: A difference above this would be more than rounding in values of a few units.
BOUND = Fraction(1, 10 ** 13)
RECORDS = {2: record._common_shoe_record, 3: record._late_surrender_record,
           4: record._bounded_resplit_record, 5: record._bounded_ace_resplit_record,
           6: record._deferred_second_card_record}
EXTRA_SLOTS = {2: 0, 4: 1, 5: 1}
SPLIT_FAMILIES = {'two hands': (exact.RANKS, 0), 'non ace resplit': (exact.RANKS[1:], 1),
                  'ace resplit': (('A',), 1)}
#: Shoe sizes and rank weights per split family. A resplit needs more cards
#: before it can finish, so its shoes lean toward high ranks, like the retained
#: comparison shoes, to keep enough of them from running out.
SPLIT_SHOES = {'two hands': (3, 11, None), 'non ace resplit': (4, 11, (1,) * 6 + (3,) * 4),
               'ace resplit': (3, 11, None)}


def _ranks(cards):
    return tuple(exact.RANKS.index(card) for card in cards)


def _gap(engine, value):
    return abs(Fraction(engine) - value), engine


def published_differences():
    """Exact difference and engine value of every published cell."""
    found = {}
    by_up = {}
    for row in PUBLISHED:
        by_up.setdefault(row[2], []).append(row)
    for up, rows in by_up.items():
        hand = exact.PostPeekHand(exact.RANKS.index(up))
        for label, cards, *_ in rows:
            shoe = ev.initial_shoe_for(cards, up)
            engine = {'S': ev.ev_stand(cards, up, shoe), 'H': ev.ev_hit(cards, up, shoe),
                      'D': ev.ev_double(cards, up, shoe)}
            values = hand.values(_ranks(cards), tuple(shoe))
            for action in 'SHD':
                found[f'{label} {action}'] = _gap(engine[action], values[action])
    return found


def request_values(path):
    """Engine and exact values for every action of one bounded example request."""
    request = _normalise(json.loads(path.read_text(encoding='utf-8')))
    version = request['schema']['version']
    inputs, rules, limits = request['input'], Rules(**request['rules']), request['limits']
    options = dict(shoe=tuple(inputs['unseen_counts']), can_double=inputs['can_double'],
                   max_states=limits['max_states'])
    if version == 3:
        options['can_surrender'] = inputs['can_surrender']
    else:
        options['can_split'] = inputs['can_split']
    if version == 6:
        options['max_seconds'] = limits['max_seconds']
    decision, _ = RECORDS[version](inputs['cards'], inputs['dealer_up'], rules, **options)
    engine = decision['decision']['evs']

    cards, up = _ranks(inputs['cards']), exact.RANKS.index(inputs['dealer_up'])
    counts = tuple(inputs['unseen_counts'])
    if version == 6:
        values = exact.deferred_second_card(cards, up, counts, stand_soft_17=rules.s17,
                                            can_double=inputs['can_double'])
    else:
        values = exact.PostPeekHand(up, rules.s17).values(cards, counts,
                                                          can_double=inputs['can_double'])
        if version == 3 and inputs['can_surrender']:
            values['R'] = Fraction(-1, 2)
        if version in EXTRA_SLOTS and inputs['can_split']:
            values['P'] = exact.common_shoe_split(
                cards[0], up, counts, double_after_split=rules.das,
                stand_soft_17=rules.s17, extra_slots=EXTRA_SLOTS[version])
    assert set(values) == set(engine), path.name
    return engine, values


def bounded_requests():
    return [path for path in sorted((ROOT / 'examples').glob('*-request.json'))
            if json.loads(path.read_text(encoding='utf-8'))['schema']['version'] in RECORDS]


@pytest.fixture(scope='module')
def published():
    return published_differences()


@pytest.fixture(scope='module')
def requests():
    found = {}
    for path in bounded_requests():
        engine, values = request_values(path)
        found.update({f'{path.name} {action}': _gap(engine[action], values[action])
                      for action in values})
    return found


def largest(differences):
    label = max(differences, key=lambda key: differences[key][0])
    return label, *differences[label]


def test_every_bounded_family_has_an_example_request():
    versions = [json.loads(path.read_text(encoding='utf-8'))['schema']['version']
                for path in bounded_requests()]
    assert set(versions) == set(RECORDS)
    assert len(versions) == 8


def test_published_cells_match_exact_arithmetic(published):
    assert len(published) == 45
    assert largest(published)[1] < BOUND


def test_bounded_example_requests_match_exact_arithmetic(requests):
    assert len(requests) == 31
    assert largest(requests)[1] < BOUND


def test_the_two_hand_example_ties_hit_and_double_exactly():
    engine, values = request_values(ROOT / 'examples/common-shoe-request.json')
    assert values['H'] == values['D'] == 0
    # Only rounding separates them in floating point, and hit is first in tie order.
    assert 0 < engine['H'] - engine['D'] < 1e-15


def _random_shoe(rng, smallest, largest_size, weights=None):
    shoe = [0] * 10
    for _ in range(rng.randint(smallest, largest_size)):
        shoe[rng.choices(range(10), weights)[0]] += 1
    return shoe


def _random_hand(rng):
    while True:
        cards = (rng.randrange(10), rng.randrange(10))
        if exact._hand(cards)[0] < 21:
            return cards


def floating_split(family, pair, up, counts, das, s17):
    """The engine's split value in the reference rank order of the joint modules."""
    options = dict(double_after_split=das, stand_soft_17=s17)
    if family == 'two hands':
        return joint_split_value(pair, up, counts, **options).value
    if family == 'non ace resplit':
        return joint_resplit_value(pair, up, counts, **options).value
    return joint_ace_resplit_value(up, counts, **options).value


def split_sweep(family):
    """Compare one split family on random shoes, plus fixed cases a sweep can miss."""
    pairs, slots = SPLIT_FAMILIES[family]
    rng = random.Random(f'rational {family}')
    cases = []
    for _ in range(100):
        shoe = _random_shoe(rng, *SPLIT_SHOES[family])
        cases.append((rng.choice(pairs), rng.choice(exact.RANKS), shoe,
                      rng.random() < 0.5, rng.random() < 0.5))
    if family == 'two hands':
        # A first hand of 8,3,8,2 reaches 21 and must stop there.
        cases.append(('8', '3', [2, 0, 1, 0, 1, 1, 1, 2, 1, 0], True, True))
    counts = dict(values=0, refusals=0, limited=0)
    for pair, up, shoe, das, s17 in cases:
        arguments = (exact.RANKS.index(pair), exact.RANKS.index(up), tuple(shoe))
        options = dict(double_after_split=das, stand_soft_17=s17, extra_slots=slots)
        try:
            found = floating_split(family, pair, up, reference_counts(tuple(shoe)), das, s17)
        except ReferenceLimitExceeded:
            # The engine did not finish inside its own state cap, so there is no value.
            counts['limited'] += 1
            continue
        except UnsupportedShoeError:
            with pytest.raises(exact.Refused):
                exact.common_shoe_split(*arguments, **options)
            counts['refusals'] += 1
            continue
        assert abs(Fraction(found) - exact.common_shoe_split(*arguments, **options)) < BOUND
        counts['values'] += 1
    return counts


def post_peek_sweep():
    """Stand, hit and double from `ev.best_action` on random small shoes."""
    rng = random.Random('rational post peek')
    counts = dict(values=0, refusals=0)
    for _ in range(150):
        cards, up = _random_hand(rng), rng.randrange(10)
        shoe, s17 = _random_shoe(rng, 1, 12), rng.random() < 0.5
        names = tuple(exact.RANKS[card] for card in cards)
        try:
            _, engine, _ = ev.best_action(names, exact.RANKS[up], shoe=tuple(shoe),
                                          rules=Rules(s17=s17), can_split=False)
        except ValueError:
            with pytest.raises(exact.Refused):
                exact.PostPeekHand(up, s17).values(cards, tuple(shoe))
            counts['refusals'] += 1
            continue
        values = exact.PostPeekHand(up, s17).values(cards, tuple(shoe))
        assert set(values) == set(engine)
        for action, value in values.items():
            assert abs(Fraction(engine[action]) - value) < BOUND
        counts['values'] += 1
    return counts


def deferred_sweep():
    """The deferred second card family on random small shoes, plus a fixed case."""
    rng = random.Random('rational deferred')
    cases = [(_random_hand(rng), rng.randrange(10), _random_shoe(rng, 1, 12),
              rng.random() < 0.5) for _ in range(150)]
    # 8,A against 8 with A and 9 unseen: after a hit one card is left, so the
    # player must stand and leave it for the dealer.
    cases.append(((8, 0), 8, [1, 0, 0, 0, 0, 0, 0, 0, 1, 0], True))
    counts = dict(values=0, refusals=0)
    for cards, up, shoe, s17 in cases:
        names = tuple(exact.RANKS[card] for card in cards)
        rules = Rules(peek=False, max_hands=1, s17=s17)
        try:
            _, engine, _, _ = deferred_second_card.decide(names, exact.RANKS[up], tuple(shoe),
                                                          rules)
        except deferred_second_card.UnsupportedContinuation:
            with pytest.raises(exact.Refused):
                exact.deferred_second_card(cards, up, tuple(shoe), stand_soft_17=s17)
            counts['refusals'] += 1
            continue
        values = exact.deferred_second_card(cards, up, tuple(shoe), stand_soft_17=s17)
        assert set(values) == set(engine)
        for action, value in values.items():
            assert abs(Fraction(engine[action]) - value) < BOUND
        counts['values'] += 1
    return counts


@pytest.fixture(scope='module')
def sweeps():
    found = {family: split_sweep(family) for family in SPLIT_FAMILIES}
    found['post peek'] = post_peek_sweep()
    found['deferred'] = deferred_sweep()
    return found


def test_random_small_shoes_match_exact_arithmetic(sweeps):
    # Every comparison and refusal is asserted inside the sweeps. Both kinds
    # of outcome must stay well represented for each model.
    for name, counts in sweeps.items():
        assert counts['values'] >= 10 and counts['refusals'] >= 10, (name, counts)


def test_the_document_states_what_the_tests_find(published, requests, sweeps):
    text = ' '.join(DOCUMENT.read_text(encoding='utf-8').split())
    for differences, count in ((published, 45), (requests, 31)):
        label, difference, value = largest(differences)
        assert f'{float(difference):.2e}' in text
        assert label.rsplit(' ', 1)[0] in text
        assert f'{float(difference) / math.ulp(value):.2f}' in text
        assert f'{abs(value):.4f}' in text
        assert f' {count} ' in text
    split = [sweeps[family] for family in SPLIT_FAMILIES]
    assert ', '.join(str(c['values']) for c in split[:2]) + f" and {split[2]['values']}" in text
    assert (', '.join(str(c['refusals']) for c in split[:2])
            + f" and {split[2]['refusals']}") in text
    for name in ('post peek', 'deferred'):
        assert f"{sweeps[name]['values']} values and {sweeps[name]['refusals']} refusals" in text
    difference, value = published['A,6 v 2 H']
    assert f'about {round(float(difference) / math.ulp(value))} units off' in text
    overall = max(largest(published)[1], largest(requests)[1])
    readme = (ROOT / 'README.md').read_text(encoding='utf-8')
    assert f'{float(overall):.2e}' in readme
