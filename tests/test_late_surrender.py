"""Independent physical-card arithmetic for one initial half-loss alternative."""
from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from unittest.mock import patch

import pytest

from bj import ev, late_surrender, record
from bj._enumeration import EnumerationLimitExceeded
from bj.caches import clear_all_caches
from bj.core import ACTION_NAMES, RANKS, STANDARD
from test_ev_physical_reference import physical_reference


def counts(cards):
    return tuple(cards.count(rank) for rank in RANKS)


def rules(**changes):
    return replace(STANDARD, **{'surrender': True, 'max_hands': 1, **changes})


# These rational values were qualified independently before implementation.
# The retained physical reference owns its own totals, dealer and observations.
CASES = (
    (('T', '6'), 'T', ('T', 'T', 'T'), True, (-1, -1, -2), 'R'),
    (('T', '8'), 'T', ('T', 'T', '8', '8'), True, (Fraction(-1, 2), -1, -2), 'S'),
    (('T', 'T'), 'T', ('T', 'T', 'T'), True, (0, -1, -2), 'S'),
    (('T', '8'), '6', ('A', '4', 'T'), True, (0, -1, -2), 'S'),
    (('T', '8'), '6', ('A', '4', 'T'), False, (Fraction(-1, 3), -1, -2), 'S'),
    (('T', '4'), 'T', ('2', '3', '7', '8', '9', 'T'), True,
     (Fraction(-2, 3), Fraction(-71, 120), Fraction(-6, 5)), 'R'),
    (('T', '4'), 'T', ('A', '3', '7', '8', '9', 'T'), True,
     (Fraction(-39, 50), Fraction(-61, 100), Fraction(-61, 50)), 'R'),
    (('T', '2'), 'A', ('6', '7', '8', '9', 'T', 'T'), False,
     (Fraction(-7, 10), Fraction(-1, 4), Fraction(-1, 2)), 'H'),
    (('2', '2'), 'T', ('T', 'T', 'T'), True, (-1, -1, -2), 'R'),
    (('A', '6'), 'T', ('A', 'A', 'A', '7'), True, (0, 1, 2), 'D'),
    (('T', '6'), 'A', ('8', 'T', 'T'), True, (-1, -1, -2), 'R'),
)


@pytest.fixture(autouse=True)
def cold_caches():
    clear_all_caches()
    yield
    clear_all_caches()


@pytest.mark.parametrize('cards,up,unseen,s17,literals,action', CASES)
def test_complete_values_match_independent_physical_deals(
        cards, up, unseen, s17, literals, action):
    expected = physical_reference(cards, up, unseen, s17=s17)
    assert expected == dict(zip(('S', 'H', 'D'), literals, strict=True))
    expected['R'] = Fraction(-1, 2)
    saved = record.late_surrender_record(cards, up, rules(s17=s17), shoe=counts(unseen))
    values = saved['decision']['evs']
    assert set(values) == set(expected)
    assert values == pytest.approx({a: float(v) for a, v in expected.items()}, rel=0, abs=1e-12)
    assert saved['decision']['action'] == action
    ordered = sorted(expected.values(), reverse=True)
    assert saved['decision']['margin'] == pytest.approx(
        float(ordered[0] - ordered[1]), rel=0, abs=1e-12)
    assert saved['schema']['version'] == 4
    assert saved['state']['cards'] == list(cards)
    assert saved['state']['shoe']['counts'] == list(counts(unseen))
    assert saved['state']['shoe']['source'] == 'supplied_unseen'
    assert saved['model']['dealer_information'] == 'hidden_hole_post_peek'
    assert saved['model']['surrender_after_hit'] is False


def test_hole_information_remains_hidden_even_when_surrender_is_best():
    cards, up, unseen = CASES[5][:3]
    lawful = physical_reference(cards, up, unseen)
    illegal = physical_reference(cards, up, unseen, reveal_hole=True)
    assert lawful['H'] == Fraction(-71, 120)
    assert illegal['H'] == Fraction(-8, 15)
    saved = record.late_surrender_record(cards, up, rules(), shoe=counts(unseen))
    assert saved['decision']['action'] == 'R'
    assert saved['decision']['evs']['H'] == pytest.approx(float(lawful['H']), rel=0, abs=1e-12)
    assert saved['decision']['evs']['H'] < float(illegal['H'])


def test_hit_does_not_gain_a_later_surrender_or_double():
    unseen = ('T', 'T', 'T')
    expected = physical_reference(('2', '2'), 'T', unseen)
    assert expected['H'] == Fraction(-1)
    # An illegal R at the later 14 would instead raise forced-H to -1/2.
    saved = record.late_surrender_record(('2', '2'), 'T', rules(), shoe=counts(unseen))
    assert saved['decision']['evs']['H'] == -1
    assert saved['decision']['evs']['H'] != -0.5
    cards, up, unseen = ('2', '2'), 'T', ('7', '7', '8', '9', 'T', 'T')
    lawful = physical_reference(cards, up, unseen)
    illegal = physical_reference(cards, up, unseen, allow_later_double=True)
    saved = record.late_surrender_record(cards, up, rules(), shoe=counts(unseen))
    assert lawful['H'] == Fraction(-1, 60)
    assert illegal['H'] == Fraction(1, 12)
    assert saved['decision']['evs']['H'] == pytest.approx(float(lawful['H']), rel=0, abs=1e-12)


@pytest.mark.parametrize('case', [0, 5])
@pytest.mark.parametrize('double,surrender', [(True, True), (True, False),
                                           (False, True), (False, False)])
def test_current_controls_only_remove_present_alternatives(case, double, surrender):
    cards, up, unseen = CASES[case][:3]
    expected = physical_reference(cards, up, unseen)
    if not double:
        expected.pop('D')
    if surrender:
        expected['R'] = Fraction(-1, 2)
    saved = record.late_surrender_record(cards, up, rules(), shoe=counts(unseen),
                                         can_double=double, can_surrender=surrender)
    assert set(saved['decision']['evs']) == set(expected)
    assert saved['decision']['evs'] == pytest.approx(
        {a: float(v) for a, v in expected.items()}, rel=0, abs=1e-12)
    assert saved['decision']['action'] == ('R' if surrender else 'S' if case == 0 else 'H')
    assert saved['state']['action_controls'] == {
        'can_double': double, 'can_split': False, 'can_surrender': surrender}


def test_exact_tie_and_binary_float_residue_are_not_rounded():
    tie = record.late_surrender_record(('T', '8'), 'T', rules(), shoe=counts(('T', 'T', '8', '8')))
    assert tie['decision']['evs']['S'] == tie['decision']['evs']['R'] == -0.5
    assert tie['decision']['action'] == 'S'
    assert tie['decision']['margin'] == 0
    residue = record.late_surrender_record(('T', '8'), '6', rules(), shoe=counts(('A', '4', 'T')))
    assert 0 < residue['decision']['evs']['S'] < 1e-12


def test_last_legal_draw_and_repeated_ace_depletion_retain_root_semantics():
    unseen = ('A', 'A', 'A', '7')
    saved = record.late_surrender_record(('A', '6'), 'T', rules(), shoe=counts(unseen))
    assert saved['decision']['evs'] == {'S': 0.0, 'H': 1.0, 'D': 2.0, 'R': -0.5}


def test_root_work_and_genuine_refusals_produce_no_partial_record():
    saved, work = record._late_surrender_record(('T', '6'), 'T', rules(),
                                                shoe=counts(('T', 'T', 'T')))
    assert saved['decision']['action'] == 'R'
    assert work == {'limit': 100000, 'states': 5, 'attempted_states': 5,
                    'state_counts': {family: 1 for family in late_surrender.ROOT_FAMILIES}}
    clear_all_caches()
    with pytest.raises(EnumerationLimitExceeded) as error:
        record.late_surrender_record(('T', '6'), 'T', rules(),
                                     shoe=counts(('T', 'T', 'T')), max_states=1)
    assert error.value.work == {'limit': 1, 'states': 1, 'attempted_states': 2,
                                'state_counts': {'root_distribution': 1}}
    with pytest.raises(ValueError, match='dealer must draw'):
        record.late_surrender_record(('T', '6'), '2', rules(), shoe=counts(('2', '2', '2')))


@pytest.mark.parametrize('changes', [
    {'cards': ('A', 'T')}, {'cards': ('T', 'A')}, {'cards': ('T', '6', '2')},
    {'cards': ('T',)}, {'cards': ('T', 'T', 'T')}, {'shoe': None},
    {'shoe': counts(('T', 'T'))}, {'shoe': counts(('T',) * 21)},
    {'shoe': counts(('A', 'A', 'A'))}, {'shoe': (True,) + (0,) * 9},
    {'shoe': (1.0,) + (0,) * 9}, {'shoe': (-1,) + (0,) * 9}, {'shoe': (1,) * 9},
    {'rules': rules(peek=False)}, {'rules': rules(surrender=False)},
    {'rules': rules(max_hands=2)}, {'rules': rules(resplit_aces=True)},
    {'rules': rules(hit_split_aces=True)}, {'rules': rules(double_any_two=False)},
    {'rules': rules(tens_are_pairs=False)}, {'can_double': 1}, {'can_surrender': 0},
    {'max_states': 0}, {'max_states': True}, {'max_states': 100001},
])
def test_unsupported_or_malformed_api_domain_refuses_before_pricing(changes):
    supplied = {'cards': ('T', '6'), 'dealer_up': 'T', 'rules': rules(),
                'shoe': counts(('T', 'T', 'T')), **changes}
    with patch.object(ev, 'best_action', side_effect=AssertionError('must not price')):
        with pytest.raises(ValueError):
            record.late_surrender_record(**supplied)


def test_old_action_vocabulary_and_ordinary_surrender_refusal_are_preserved():
    assert ACTION_NAMES == {'H': 'HIT', 'S': 'STAND', 'D': 'DOUBLE', 'P': 'SPLIT'}
    with pytest.raises(ValueError, match='do not model surrender'):
        record.decision_record(('T', '6'), 'T', rules(), shoe=counts(('T', 'T', 'T')))
    with patch.object(late_surrender, 'decide', side_effect=AssertionError('new family')):
        old = record.decision_record(('T', '6'), 'T', shoe=counts(('T', 'T', 'T')),
                                      can_split=False)
    assert old['schema']['version'] == 2
    assert set(old['decision']['evs']) == {'S', 'H', 'D'}
