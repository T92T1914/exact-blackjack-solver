"""Independent physical/Fraction witnesses for the declared resplit family.

The reference uses separate complete physical deals. Production imports belong
only to this comparator, never to the independent arithmetic helper.
"""
from dataclasses import replace
from fractions import Fraction

import pytest

from bj import bounded_resplit, joint_resplit
from bj._enumeration import EnumerationLimitExceeded
from bj.core import STANDARD
from bj.joint_split import ReferenceLimitExceeded, UnsupportedShoeError
from bj.record import bounded_resplit_record
from resplit_physical_reference import OracleLimit, OracleRefusal, qualify_case


PUBLIC_RANKS = tuple("A23456789T")


def public_counts(cards):
    return tuple(cards.count(rank) for rank in PUBLIC_RANKS)


def joint_counts(cards):
    return tuple(cards.count(rank) for rank in ("2", "3", "4", "5", "6", "7", "8", "9", "T", "A"))


CASES = [
    ("8", "6", ("8",) * 8, False, True, (1, -1, -2, 3), "P"),
    ("8", "6", ("8",) * 8, True, False, (1, -1, -2, 3), "P"),
    ("T", "T", ("T",) * 8, True, True, (0, -1, -2, 0), "S"),
    ("8", "T", ("8",) * 8, True, True, (-1, -1, -2, -2), "S"),
    ("T", "9", ("8", "8", "9", "9", "T", "T", "T", "T"), True, True,
     (1, -1, -2, Fraction(106, 105)), "P"),
    ("T", "T", ("A", "A") + ("T",) * 6, True, True,
     (0, Fraction(-3, 7), Fraction(-6, 7), Fraction(9, 7)), "P"),
    # Other negative-peek direction: T cannot be the hole under A. The retained
    # 8 is the only possible hole; dealer A+8 already stands at19.
    ("T", "A", ("8",) + ("T",) * 7, True, True, (1, -1, -2, 3), "P"),
]


@pytest.mark.parametrize("pair,up,cards,das,s17,expected,action", CASES)
def test_full_result_matches_independent_physical_worlds(
        pair, up, cards, das, s17, expected, action):
    reference = qualify_case(pair, up, cards, das=das, s17=s17, max_seconds=30)
    exact = {key: Fraction(value) for key, value in reference["root_action_values"].items()}
    assert exact == dict(zip(("S", "H", "D", "P"), expected, strict=True))
    rules = replace(STANDARD, max_hands=3, das=das, s17=s17)
    saved = bounded_resplit_record((pair, pair), up, rules, shoe=public_counts(cards))
    assert set(saved["decision"]["evs"]) == set(exact)
    assert saved["decision"]["evs"] == pytest.approx(
        {key: float(value) for key, value in exact.items()}, abs=1e-12, rel=0)
    assert saved["decision"]["action"] == action
    assert saved["schema"]["version"] == 5
    assert saved["model"] == bounded_resplit.model_record(up, 100000)
    assert saved["state"]["shoe"]["counts"] == list(public_counts(cards))
    assert reference["diagnostics"]["maximum_hands"] == 3
    assert reference["diagnostics"]["no_slot_pair_nodes"] > 0
    assert reference["diagnostics"]["physical_deals_before_peek"] == 40320
    if up == "A":
        assert reference["diagnostics"]["physical_deals_after_peek"] == 5040
        assert saved["model"]["hole_rank_excluded_by_peek"] == "T"
    if up == "T" and "A" in cards:
        assert reference["diagnostics"]["physical_deals_after_peek"] == 30240
        assert reference["diagnostics"]["split_twenty_one_terminal_nodes"] > 0


def test_global_slot_is_deferred_on_a_tie_then_used_on_the_later_hand():
    result = qualify_case("8", "6", ("8",) * 8, max_seconds=30)
    first = next(row for row in result["bounded_action_audit"] if row["pending_seeds"])
    assert first["action_values"] == {"S": "3/1", "H": "1/1", "P": "3/1"}
    assert first["chosen_action"] == "S"
    policy = result["joint_initial_split_policy_audit"][0]["joint_policy"]
    assert policy["state_counts"]["selected_resplit_states"] == 1
    assert policy["state_counts"]["slot_exhausted_pair_states"] > 0
    assert any(row["pending_seed_count"] == 0 and row["selected_action"] == "P"
               for row in policy["samples"])
    two = qualify_case("8", "6", ("8",) * 8, extra_slots=0, max_seconds=30)
    assert two["root_action_values"]["P"] == "2/1"
    assert two["diagnostics"]["maximum_hands"] == 2


def test_soft_seventeen_changes_completion_with_a_shared_dealer():
    # Both possible negative-peek holes give S17 a terminal soft17/soft19.
    # H17 can consume the last8, reach hard15 and require an unavailable draw.
    cards = ("6", "8") + ("T",) * 6
    reference = qualify_case("T", "A", cards, das=True, s17=True, max_seconds=30)
    exact = {key: Fraction(value) for key, value in reference["root_action_values"].items()}
    assert {key: exact[key] for key in ("S", "H", "D")} == {"S": 1, "H": -1, "D": -2}
    saved = bounded_resplit_record(("T", "T"), "A", replace(STANDARD, max_hands=3),
                                  shoe=public_counts(cards))
    assert saved["decision"]["evs"] == pytest.approx(
        {key: float(value) for key, value in exact.items()}, abs=1e-12, rel=0)
    with pytest.raises(OracleRefusal) as independent:
        qualify_case("T", "A", cards, das=True, s17=False, max_seconds=30)
    assert independent.value.stage == "dealer draw"
    with pytest.raises(UnsupportedShoeError, match="dealer must draw"):
        bounded_resplit_record(("T", "T"), "A", replace(STANDARD, max_hands=3, s17=False),
                              shoe=public_counts(cards))


@pytest.mark.parametrize("up,cards,s17", [
    ("6", ("A", "A") + ("T",) * 6, True),
    ("6", ("A", "A") + ("T",) * 6, False),
    ("6", ("8",) * 7, True),
])
def test_all_offered_continuations_must_settle_even_when_a_good_policy_exists(up, cards, s17):
    pair = "8" if cards[0] == "8" else "T"
    with pytest.raises(OracleRefusal) as independent:
        qualify_case(pair, up, cards, das=pair == "T", s17=s17, max_seconds=30)
    assert independent.value.stage == "dealer draw"
    with pytest.raises(UnsupportedShoeError, match="dealer must draw"):
        bounded_resplit_record((pair, pair), up,
                              replace(STANDARD, max_hands=3, das=pair == "T", s17=s17),
                              shoe=public_counts(cards))


def test_root_and_joint_state_caps_refuse_without_an_answer():
    with pytest.raises(OracleLimit) as independent:
        qualify_case("8", "6", ("8",) * 8, max_states=1, max_seconds=30)
    assert independent.value.kind == "state limit"
    assert independent.value.diagnostics["states"] == 1
    assert independent.value.diagnostics["state_entry_attempts"] == 2
    with pytest.raises(EnumerationLimitExceeded):
        bounded_resplit_record(("8", "8"), "6", replace(STANDARD, max_hands=3),
                              shoe=public_counts(("8",) * 8), max_states=1)
    with pytest.raises(ReferenceLimitExceeded):
        joint_resplit.joint_resplit_value("8", "6", joint_counts(("8",) * 8), max_states=1)


@pytest.mark.parametrize("control,expected", [
    ("reveal_hole", Fraction(136, 105)),
    ("force_first_eligible_resplit", Fraction(29, 30)),
    ("replenish_between_hands", Fraction(152, 147)),
])
def test_mixed_fixture_distinguishes_precisely_labeled_unsafe_controls(control, expected):
    # Frozen qualification comparisons, not a benchmark or a production option.
    # Forced P does not represent every positive-marginal greedy policy. The
    # replenished control restores prior consumed cards but preserves one hole.
    cards = ("8", "8", "9", "9", "T", "T", "T", "T")
    result = qualify_case("T", "9", cards, das=True, max_seconds=30, **{control: True})
    assert Fraction(result["root_action_values"]["P"]) == expected
    assert expected != Fraction(106, 105)
    assert result["unsafe_" + control] is True
