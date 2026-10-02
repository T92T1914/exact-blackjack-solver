"""Physical permutation oracles with exact rational expectations on tiny shoes."""
from fractions import Fraction
from itertools import permutations

import pytest

from bj import joint_split as reference


def shoe(cards):
    return tuple(cards.count(rank) for rank in reference.RANKS)


def permutation_oracle(pair, up, cards, das=False, s17=True, reveal_hole=False):
    """Group physical deals by visible history before optimizing their expectation.

    This deliberately uses a list of complete deals and Fraction, not count
    transitions or any production dealer or Bellman helper. A hidden hole is
    never exposed to the policy unless the explicit counterexample asks for it.
    """
    def total(hand):
        low = sum(1 if rank == 'A' else 10 if rank == 'T' else int(rank) for rank in hand)
        soft = 'A' in hand and low <= 11
        return low + 10 * soft, soft

    def settlement(worlds, first, second):
        result = 0
        for hole, deck in worlds:
            hands = (first, second)
            if all(t > 21 for t, _ in hands):
                result -= sum(w for _, w in hands)
                continue
            dealer, cursor = [up, hole], 0
            while True:
                dt, soft = total(dealer)
                if dt > 17 or (dt == 17 and (s17 or not soft)):
                    break
                if cursor == len(deck):
                    raise ValueError('oracle dealer exhausted')
                dealer.append(deck[cursor])
                cursor += 1
            result += sum(-w if t > 21 else w if dt > 21 or t > dt
                          else -w if t < dt else 0 for t, w in hands)
        return Fraction(result, len(worlds))

    def finish(worlds, hand, first, wager=1):
        current = (total(hand)[0], wager)
        return (play(worlds, (pair,), current) if first is None
                else settlement(worlds, first, current))

    def observed_draw(worlds, hand, first, doubled=False):
        groups = {}
        for hole, deck in worlds:
            if not deck:
                raise ValueError('oracle player exhausted')
            groups.setdefault(deck[0], []).append((hole, deck[1:]))
        result = Fraction(0)
        for rank, group in groups.items():
            value = (finish(group, hand + (rank,), first, 2) if doubled
                     else play(group, hand + (rank,), first))
            result += Fraction(len(group), len(worlds)) * value
        return result

    def play(worlds, hand, first):
        if len(hand) == 1:
            return observed_draw(worlds, hand, first)
        if total(hand)[0] >= 21 or pair == 'A':
            return finish(worlds, hand, first)
        options = [finish(worlds, hand, first)]
        options.append(observed_draw(worlds, hand, first))
        if das and len(hand) == 2:
            options.append(observed_draw(worlds, hand, first, True))
        return max(options)

    physical = permutations(range(len(cards)))
    worlds = [(cards[p[0]], tuple(cards[i] for i in p[1:])) for p in physical
              if not (up == 'A' and cards[p[0]] == 'T')
              and not (up == 'T' and cards[p[0]] == 'A')]
    if not worlds:
        raise ValueError('oracle peek is impossible')
    if not reveal_hole:
        return play(worlds, (pair,), None)
    groups = {}
    for world in worlds:
        groups.setdefault(world[0], []).append(world)
    return sum(Fraction(len(group), len(worlds)) * play(group, (pair,), None)
               for group in groups.values())


@pytest.mark.parametrize('pair,up,cards,das,s17', [
    ('8', '6', ('7', '7', '8', '9', 'T', 'T'), False, True),
    ('8', 'T', ('7', '7', '8', '9', 'T', 'T'), True, True),
    ('A', 'A', ('7', '8', '9', 'T', 'T'), False, True),
    ('A', 'T', ('A', '7', '8', '9', 'T'), True, True),
    ('A', '6', ('A', '7', '8', '9', 'T', 'T'), False, False),
])
def test_float_enumeration_matches_separate_fraction_oracle(pair, up, cards, das, s17):
    expected = permutation_oracle(pair, up, cards, das, s17)
    result = reference.joint_split_value(pair, up, shoe(cards),
                                       double_after_split=das, stand_soft_17=s17)
    assert result.value == pytest.approx(float(expected), abs=1e-12)
    assert result.maximum_probability_mass_error <= 1e-12
    assert result.states == sum(count for _, count in result.state_counts)


def test_decision_cannot_use_hidden_hole():
    cards = ('7', '7', '8', '9', 'T', 'T', 'T')
    observed = permutation_oracle('5', 'T', cards, das=True)
    clairvoyant = permutation_oracle('5', 'T', cards, das=True, reveal_hole=True)
    assert observed == Fraction(-9, 7)
    assert clairvoyant == Fraction(-107, 84)
    result = reference.joint_split_value('5', 'T', shoe(cards))
    assert result.value == pytest.approx(float(observed), abs=1e-12)
    assert result.value < float(clairvoyant)


def test_split_aces_take_one_card_and_never_receive_natural_premium():
    for das in (False, True):
        result = reference.joint_split_value('A', '7', shoe(('T',) * 4),
                                           double_after_split=das)
        assert result.value == 2.0


def test_shared_dealer_and_wagers_are_counted_per_hand():
    cards = ('7', '7', '8', '9', 'T', 'T')
    no_double = reference.joint_split_value('8', '6', shoe(cards), double_after_split=False)
    double = reference.joint_split_value('8', '6', shoe(cards), double_after_split=True)
    assert double.value >= no_double.value
    assert double.value == pytest.approx(float(permutation_oracle('8', '6', cards, True)))


def test_inputs_and_other_calls_cannot_mutate_a_reference():
    counts = list(shoe(('7', '7', '8', '9', 'T', 'T')))
    original = counts.copy()
    first = reference.joint_split_value('8', 'T', counts)
    reference.joint_split_value('A', '6', counts, stand_soft_17=False)
    again = reference.joint_split_value('8', 'T', counts)
    assert counts == original
    assert first.value == again.value
    assert first.states == again.states


def test_exhaustion_is_an_error_not_a_zero_or_an_omitted_action():
    with pytest.raises(reference.UnsupportedShoeError, match='dealer must draw'):
        reference.joint_split_value('A', '2', shoe(('2', '3', '4')))
    with pytest.raises(reference.UnsupportedShoeError, match='player draw'):
        reference.joint_split_value('2', 'T', shoe(('7', '8', '9')))
    with pytest.raises(reference.UnsupportedShoeError, match='peek'):
        reference.joint_split_value('A', 'A', shoe(('T',) * 4))


def test_second_hand_cannot_drop_a_hit_when_only_the_hole_remains():
    # The first hand can consume two cards and bust. The second mandatory card
    # leaves a standing total below 21 and only the hole. Stand can settle, but
    # the admitted hit cannot draw. The whole condition must be unsupported.
    cards = ('7', '8', '9', 'T')
    with pytest.raises(reference.UnsupportedShoeError, match='player draw'):
        reference.joint_split_value('8', 'T', shoe(cards), double_after_split=False)
    with pytest.raises(ValueError, match='oracle player exhausted'):
        permutation_oracle('8', 'T', cards)


@pytest.mark.parametrize('kwargs', [
    {'pair_rank': 'J'}, {'dealer_up': 'bad'}, {'shoe': (1,)},
    {'shoe': (True,) + (0,) * 9}, {'shoe': (-1,) + (1,) * 9},
    {'shoe': (3,) * 10}, {'double_after_split': 1}, {'stand_soft_17': 'yes'},
    {'max_states': False}, {'max_states': 0}, {'max_seconds': float('nan')},
    {'max_seconds': 0},
])
def test_invalid_contracts_are_rejected(kwargs):
    arguments = dict(pair_rank='8', dealer_up='T', shoe=shoe(('7', '7', '8', '9', 'T', 'T')))
    arguments.update(kwargs)
    with pytest.raises(ValueError):
        reference.joint_split_value(**arguments)


def test_state_limit_and_deadline_are_explicit(monkeypatch):
    counts = shoe(('7', '7', '8', '9', 'T', 'T'))
    with pytest.raises(reference.ReferenceLimitExceeded, match='state limit') as exc:
        reference.joint_split_value('8', 'T', counts, max_states=1)
    assert exc.value.states == 2
    times = iter((0, 2))
    monkeypatch.setattr(reference, 'perf_counter', lambda: next(times))
    with pytest.raises(reference.ReferenceLimitExceeded, match='time limit'):
        reference.joint_split_value('8', 'T', counts, max_seconds=1)


def test_completion_deadline_refuses_a_late_final_result(monkeypatch):
    counts = shoe(('T',) * 4)
    completed = reference.joint_split_value('A', '7', counts)
    # Every admitted state starts before the deadline. The completed arithmetic
    # can still consume time after the last state entry.
    times = iter([0.0] * (completed.states + 1) + [2.0])
    monkeypatch.setattr(reference, 'perf_counter', lambda: next(times))
    with pytest.raises(reference.ReferenceLimitExceeded, match='time limit') as exc:
        reference.joint_split_value('A', '7', counts, max_seconds=1)
    assert exc.value.states == completed.states
    assert exc.value.elapsed_seconds == 2.0


@pytest.mark.parametrize('elapsed', [0.75, 1.0])
def test_completed_deadline_boundary_preserves_numerical_diagnostics(monkeypatch, elapsed):
    counts = shoe(('T',) * 4)
    completed = reference.joint_split_value('A', '7', counts)
    times = iter([0.0] * (completed.states + 1) + [elapsed])
    monkeypatch.setattr(reference, 'perf_counter', lambda: next(times))
    result = reference.joint_split_value(
        'A', '7', counts, max_seconds=1, max_states=completed.states)
    assert result.elapsed_seconds == elapsed
    assert result.value == completed.value
    assert result.states == completed.states
    assert result.cache_hits == completed.cache_hits
    assert result.state_counts == completed.state_counts
    assert result.maximum_probability_mass_error == completed.maximum_probability_mass_error
