"""Independent complete physical deals for the bounded original ace-pair model.

These are the qualified tiny/manual witnesses, not a new search campaign. Exact
Fraction ties remain separate from the engine's raw binary64 ranking. Production
imports belong in this comparator, never in the independent arithmetic helper.
"""
from dataclasses import replace
from fractions import Fraction
from math import factorial

import pytest

from bj import bounded_ace_resplit, joint_ace_resplit, record
from bj._enumeration import EnumerationLimitExceeded
from bj.caches import clear_all_caches
from bj.core import STANDARD
from bj.joint_split import UnsupportedShoeError
from ace_resplit_physical_reference import OracleLimit, OracleRefusal, qualify_case, run_case


PUBLIC_RANKS = tuple("A23456789T")
ACTION_ORDER = ("S", "H", "D", "P")
HIDDEN_CARDS = ("A", "A", "A", "T", "T")


def public_counts(cards):
    return tuple(cards.count(rank) for rank in PUBLIC_RANKS)


def joint_counts(cards):
    return tuple(cards.count(rank) for rank in ("2", "3", "4", "5", "6", "7", "8", "9", "T", "A"))


def rules(**changes):
    return replace(STANDARD, max_hands=3, resplit_aces=True, hit_split_aces=False,
                   **changes)


def exact_values(reference):
    return {key: Fraction(value) for key, value in reference["root_action_values"].items()}


def assert_complete_comparison(reference, up, cards, *, das=False, s17=True,
                               can_double=True, can_split=True):
    exact = exact_values(reference)
    supplied = public_counts(cards)
    saved, work = record._bounded_ace_resplit_record(
        ("A", "A"), up, rules(das=das, s17=s17), shoe=supplied,
        can_double=can_double, can_split=can_split)
    values = saved["decision"]["evs"]
    assert set(values) == set(exact)
    assert values == pytest.approx({key: float(value) for key, value in exact.items()},
                                  abs=1e-12, rel=0)
    # Values are compared with a numerical tolerance. Ranking has no epsilon:
    # compute its expectation from the actual binary64 values, not Fraction ties.
    ordered = sorted((key for key in ACTION_ORDER if key in values),
                     key=lambda key: values[key], reverse=True)
    assert saved["decision"]["action"] == ordered[0]
    raw_margin = values[ordered[0]] - values[ordered[1]] if len(ordered) > 1 else 0.0
    assert saved["decision"]["margin"] == raw_margin
    assert saved["schema"]["version"] == 6
    assert saved["model"] == bounded_ace_resplit.model_record(up, 100000)
    assert saved["model"]["name"] == "common_shoe_bounded_ace_resplit"
    assert saved["model"]["version"] == 1
    assert saved["state"]["shoe"]["source"] == "supplied_unseen"
    assert saved["state"]["shoe"]["counts"] == list(supplied)
    assert supplied == public_counts(cards)
    assert saved["state"]["action_controls"] == {
        "can_double": can_double, "can_split": can_split}
    assert work["limit"] == 100000
    assert work["states"] == work["attempted_states"] == sum(work["state_counts"].values())
    assert 0 < work["states"] <= work["limit"]
    assert set(work["state_counts"]) <= bounded_ace_resplit.FAMILIES
    assert any(name.startswith("ace_resplit_") for name in work["state_counts"]) is can_split
    return saved


@pytest.fixture(autouse=True)
def cold_engine_caches():
    clear_all_caches()
    yield
    clear_all_caches()


COMPLETE_CASES = [
    # A+T children have ordinary one-unit split settlement, no natural premium.
    ("ordinary-split21", "7", ("T",) * 4, False, (-1, -1, -2, 2), ("P",)),
    # FourT against6 yields an exact original D/P tie and one common dealer bust.
    ("root-fraction-tie", "6", ("T",) * 4, True, (1, 1, 2, 2), ("D", "P")),
    ("one-extra-ace", "7", ("A",) + ("T",) * 5, True,
     (-1, -1, -2, Fraction(7, 3)), ("P",)),
    ("shared-slot-exhausted", "7", ("A", "A") + ("T",) * 6, False,
     (-1, -1, -2, Fraction(59, 28)), ("P",)),
    ("concealed-hole", "7", HIDDEN_CARDS, False,
     (-1, -1, -2, Fraction(3, 10)), ("P",)),
    ("optional-resplit-declined", "7", ("A",) * 5, False,
     (-1, -1, -2, -2), ("S", "H")),
    ("ten-up-negative-peek", "T", ("A",) + ("T",) * 4, False,
     (-1, -1, -2, Fraction(5, 2)), ("P",)),
    ("ace-up-negative-peek", "A", ("8",) + ("T",) * 4, False,
     (-1, -1, -2, 2), ("P",)),
]


@pytest.mark.parametrize("label,up,cards,das,expected,maximizing", COMPLETE_CASES,
                         ids=[row[0] for row in COMPLETE_CASES])
def test_complete_original_result_matches_physical_deals(
        label, up, cards, das, expected, maximizing):
    reference = qualify_case(up, cards, das=das)
    assert reference["evidence_scope"] == "complete original decision"
    assert exact_values(reference) == dict(zip(ACTION_ORDER, expected, strict=True))
    assert reference["root_maximizing_actions"] == list(maximizing)
    assert reference["diagnostics"]["physical_deals_before_peek"] == factorial(len(cards))
    assert reference["diagnostics"]["physical_permutations_considered"] == factorial(len(cards))
    assert reference["diagnostics"]["maximum_hands"] <= 3
    saved = assert_complete_comparison(reference, up, cards, das=das)
    if label == "shared-slot-exhausted":
        assert reference["diagnostics"]["maximum_hands"] == 3
        assert reference["diagnostics"]["no_slot_pair_nodes"] > 0
    if label == "ten-up-negative-peek":
        assert reference["diagnostics"]["physical_deals_after_peek"] == 96
        assert saved["model"]["hole_rank_excluded_by_peek"] == "A"
    if label == "ace-up-negative-peek":
        assert reference["diagnostics"]["physical_deals_after_peek"] == 24
        assert saved["model"]["hole_rank_excluded_by_peek"] == "T"


@pytest.mark.parametrize("double,split", [(True, True), (False, True),
                                        (True, False), (False, False)])
def test_original_controls_remove_only_original_actions(double, split):
    reference = qualify_case("7", HIDDEN_CARDS, can_double=double, can_split=split)
    expected = {"S": Fraction(-1), "H": Fraction(-1)}
    if double:
        expected["D"] = Fraction(-2)
    if split:
        expected["P"] = Fraction(3, 10)
    assert exact_values(reference) == expected
    assert_complete_comparison(reference, "7", HIDDEN_CARDS,
                               can_double=double, can_split=split)


def test_concealed_hole_is_averaged_before_optional_resplit_maximum():
    reference = qualify_case("7", HIDDEN_CARDS)
    first_pair = next(row for row in reference["bounded_action_audit"]
                      if row["pending_seeds"] == [["A"]] and not row["completed"])
    assert first_pair["hand"] == ["A", "A"]
    assert first_pair["hole_posterior"] == {"A": "1/2", "T": "1/2"}
    assert first_pair["action_values"] == {"S": "-1/6", "P": "0/1"}
    assert first_pair["maximizing_actions"] == ["P"]
    assert first_pair["chosen_action"] == "P"
    assert all(row["choice_uses_visible_history_only"] is True
               for row in reference["bounded_action_audit"])
    assert Fraction(reference["root_action_values"]["P"]) == Fraction(3, 10)


def test_one_shared_slot_and_completed_wagers_remain_in_the_joint_choice():
    cards = ("A",) + ("T",) * 5
    reference = qualify_case("7", cards)
    assert Fraction(reference["root_action_values"]["P"]) == Fraction(7, 3)
    assert reference["diagnostics"]["resplit_offered_nodes"] > 0
    assert reference["diagnostics"]["resplit_unique_best_nodes"] > 0
    assert reference["diagnostics"]["maximum_hands"] == 3
    assert any([21, 1] in row["completed"] for row in reference["bounded_action_audit"])
    two_hands = qualify_case("7", cards, extra_slots=0)
    assert two_hands["maximum_supported_hands"] == 2
    assert Fraction(two_hands["root_action_values"]["P"]) == Fraction(4, 3)
    assert two_hands["diagnostics"]["maximum_hands"] == 2
    # All pending seeds are identical one-card aces at unit wager. These values
    # cannot independently distinguish ancestry order after spending the slot.


def test_extra_resplit_is_optional_and_split21_uses_one_ordinary_dealer_settlement():
    declined = qualify_case("7", ("A",) * 5)
    assert declined["diagnostics"]["resplit_declined_nodes"] > 0
    assert all(row["action_values"] == {"S": "-2/1", "P": "-3/1"}
               and row["chosen_action"] == "S" for row in declined["bounded_action_audit"])
    result = qualify_case("7", ("T",) * 4)
    assert result["diagnostics"]["split_twenty_one_terminal_nodes"] > 0
    ace_settlements = [row for row in result["settlement_audit"] if row["scope"] == "ace"]
    assert ace_settlements
    assert all(row["completed_wagers"] == [[21, 1], [21, 1]]
               and row["one_dealer_hand"] == ["7", "T"]
               and row["combined_payoff"] == 2 for row in ace_settlements)


@pytest.mark.parametrize("up,cards,expected", [
    ("7", ("A",) * 3, {"S": -1, "H": -1, "D": -2}),
    ("6", ("T",) * 3, {"S": 1, "H": 1, "D": 2}),
])
def test_complete_original_hit_preserves_last_draw_standing(up, cards, expected):
    reference = qualify_case(up, cards, can_split=False)
    assert exact_values(reference) == expected
    if cards[0] == "A":
        assert reference["diagnostics"]["ordinary_last_draw_stand_nodes"] > 0
    assert_complete_comparison(reference, up, cards, can_split=False)


def test_forced_initial_split_is_separate_from_complete_original_decision():
    conditional = qualify_case("7", HIDDEN_CARDS, include_root=False)
    assert conditional["evidence_scope"] == "forced initial P only"
    assert exact_values(conditional) == {"P": Fraction(3, 10)}
    value = joint_ace_resplit.joint_ace_resplit_value("7", joint_counts(HIDDEN_CARDS))
    assert value.value == pytest.approx(float(Fraction(3, 10)), abs=1e-12, rel=0)
    whole = record.bounded_ace_resplit_record(("A", "A"), "7", rules(),
                                            shoe=public_counts(HIDDEN_CARDS))
    assert set(whole["decision"]["evs"]) == set(ACTION_ORDER)


def test_forced_split_refusal_keeps_its_ace_scope_separate_from_ordinary_root():
    # H17 needs another card on an offered three-child continuation's soft17.
    # Full-root evaluation can refuse earlier in the ordinary H continuation.
    conditional = run_case({"up": "6", "cards": ("A",) * 5,
                            "s17": False, "include_root": False})
    assert conditional["status"] == "unsupported_continuation"
    assert conditional["evidence_scope"] == "forced initial P only"
    assert conditional["stage"] == "ace dealer draw"
    assert "root_action_values" not in conditional
    with pytest.raises(UnsupportedShoeError):
        joint_ace_resplit.joint_ace_resplit_value(
            "6", joint_counts(("A",) * 5), stand_soft_17=False)


@pytest.mark.parametrize("up,cards,s17,stage", [
    ("6", ("T",) * 3, True, "ace dealer draw"),
    ("7", ("A",) * 3, True, "ace mandatory deal"),
    ("6", ("A",) * 5, False, "ordinary dealer draw"),
])
def test_every_offered_continuation_must_finish_before_returning_a_root(up, cards, s17, stage):
    with pytest.raises(OracleRefusal) as independent:
        qualify_case(up, cards, s17=s17)
    assert independent.value.stage == stage
    result = run_case({"up": up, "cards": cards, "s17": s17})
    assert result["status"] == "unsupported_continuation"
    assert result["stage"] == stage
    assert not {"root_action_values", "root_best_value", "root_recommended_action",
                "root_margin", "bounded_action_audit", "settlement_audit"} & set(result)
    expected_type = ValueError if stage == "ordinary dealer draw" else UnsupportedShoeError
    expected_message = ("dealer must draw to 17 but the shoe is empty"
                        if stage == "ordinary dealer draw" else None)
    with pytest.raises(expected_type, match=expected_message) as production:
        record.bounded_ace_resplit_record(("A", "A"), up, rules(s17=s17),
                                         shoe=public_counts(cards))
    assert type(production.value) is expected_type


def test_state_exhaustion_has_no_partial_values_and_recovers():
    with pytest.raises(OracleLimit) as independent:
        qualify_case("7", ("T",) * 4, max_states=1)
    assert independent.value.kind == "state limit"
    assert independent.value.diagnostics["states"] == 1
    assert independent.value.diagnostics["state_entry_attempts"] == 2
    limited = run_case({"up": "7", "cards": ("T",) * 4, "max_states": 1})
    assert limited["status"] == "resource_limited" and limited["stage"] == "resource"
    assert "root_action_values" not in limited and "bounded_action_audit" not in limited
    with pytest.raises(EnumerationLimitExceeded):
        record.bounded_ace_resplit_record(("A", "A"), "7", rules(),
                                         shoe=public_counts(("T",) * 4), max_states=1)
    recovered = qualify_case("7", HIDDEN_CARDS)
    assert_complete_comparison(recovered, "7", HIDDEN_CARDS)


def test_impossible_negative_peek_refusals_keep_their_different_boundaries():
    independent = run_case({"up": "A", "cards": ("T",) * 4})
    assert independent["status"] == "unsupported_continuation"
    assert independent["stage"] == "peek"
    assert "root_action_values" not in independent
    # Accepted engine admission rejects this before pricing. It is not renamed
    # as the physical reference's required-continuation outcome for agreement.
    with pytest.raises(ValueError):
        record.bounded_ace_resplit_record(("A", "A"), "A", rules(),
                                         shoe=public_counts(("T",) * 4))


def test_revealed_hole_control_is_explicitly_unsafe_in_every_information_label():
    lawful = qualify_case("7", HIDDEN_CARDS)
    unsafe = qualify_case("7", HIDDEN_CARDS, reveal_hole=True)
    assert lawful["unsafe_reveal_hole"] is False
    assert unsafe["unsafe_reveal_hole"] is True
    assert unsafe["evidence_scope"] == "explicit unsafe revealed-hole control"
    assert unsafe["root_choice_semantics"] == "illegal per-hole maxima before averaging"
    assert unsafe["root_maximizing_actions"] is None
    assert unsafe["root_recommended_action"] is None
    assert unsafe["root_margin"] is None
    assert lawful["bounded_action_audit"] and unsafe["bounded_action_audit"]
    assert all(row["choice_uses_visible_history_only"] is True
               for row in lawful["bounded_action_audit"])
    assert all(row["choice_uses_visible_history_only"] is False
               and len(row["hole_posterior"]) == 1
               and set(row["hole_posterior"].values()) == {"1/1"}
               for row in unsafe["bounded_action_audit"])
    assert {row["revealed_hole"]: row["probability"]
            for row in unsafe["joint_initial_split_policy_audit"]} == {"A": "3/5", "T": "2/5"}
    assert Fraction(unsafe["root_action_values"]["P"]) == Fraction(1, 2)
    assert Fraction(unsafe["root_action_values"]["P"]) - Fraction(
        lawful["root_action_values"]["P"]) == Fraction(1, 5)


def test_forced_first_resplit_control_remains_distinct_from_optional_policy():
    unsafe = qualify_case("7", ("A",) * 5, force_first_eligible_resplit=True)
    assert unsafe["unsafe_force_first_eligible_resplit"] is True
    assert unsafe["evidence_scope"] == "explicit unsafe forced-first-resplit control"
    assert Fraction(unsafe["root_action_values"]["P"]) == -3
    assert unsafe["diagnostics"]["forced_resplit_overrides"] > 0
    assert all(row["choice_uses_visible_history_only"] is True
               for row in unsafe["bounded_action_audit"])


def test_twenty_card_admission_uses_one_manual_witness_not_a_physical_claim():
    # Exactly one retainedA: hidden gives two21 (1/20); either first/later
    # original child receives it and resplits into three21 (2/20); all other
    # positions give two21 (17/20). Thus P=21/10. No twenty-card permutation run.
    cards = ("A",) + ("T",) * 19
    saved = record.bounded_ace_resplit_record(("A", "A"), "7", rules(),
                                            shoe=public_counts(cards))
    assert saved["decision"]["evs"] == pytest.approx(
        {"S": -1, "H": -1, "D": -2, "P": float(Fraction(21, 10))}, abs=1e-12, rel=0)
    assert saved["decision"]["action"] == "P"
    with pytest.raises(ValueError, match="3 through 8"):
        qualify_case("7", cards)
