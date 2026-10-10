"""Independent tiny-shoe physical-deal/Fraction reference for an original ace pair.

No Solver arithmetic is imported. Complete labeled physical permutations retain
one concealed hole and the actual remaining deck. Visible draws group worlds
before a player maximum. Split-ace children admit only mandatory deal and S/P.

Physical world construction and policy/audit traversal are timed. At most eight
retained cards produce at most 40320 labeled permutations. That is distinct from
the at-most-100000 uncached recurrence-state allowance and from physical memory.
The caller owns external worker wall, committed-memory and retirement policies.

Adapted from the immutable ace qualification physical oracle, SHA-256
963c6e60252321af63254da8c3e13fd23232b619f75141805cd335aab9e01ddf.
Its arithmetic is preserved. This new test identity corrects the unsafe
revealed-hole audit's visible-information label. The qualification's original
source and six failed diagnostic checks remain evidence of that earlier defect.

Provenance: world grouping/cache cleanup is adapted from accepted test-only
resplit_physical_reference.py, SHA-256
6008f29bc84737311b01524a8773bbec03774c6fb7953e35465d5050ee4eb678.
Original last-player-draw standing is independently anchored in accepted
test_ev_physical_reference.py, SHA-256
9405fbff2a19dc4a63b2f14c3d5ed70ac90dd55c3abc13b2f4a478d3093d2f6d.
The ace S/P continuation and manual cases are authored separately from the new
count candidate. This test-only reference is not an installed interface. Values
can test depletion and shared settlement, but cannot discriminate the ancestry
order of exchangeable one-card ace children after the global slot is spent.
"""
from collections import Counter, defaultdict
from fractions import Fraction
from functools import lru_cache
from itertools import permutations
from math import factorial, isfinite
from time import perf_counter


RANKS = tuple("A23456789T")
ACTION_ORDER = ("S", "H", "D", "P")
MODEL = "common_shoe_bounded_ace_resplit_v1_test_physical_reference"
MAX_PHYSICAL_CARDS = 8
MAX_LABELED_PERMUTATIONS = 40320
MAX_STATES = 100000
MAX_SECONDS = 10.0


class OracleRefusal(ValueError):
    def __init__(self, stage, message, diagnostics):
        super().__init__(message)
        self.stage = stage
        self.diagnostics = diagnostics


class OracleLimit(RuntimeError):
    def __init__(self, kind, diagnostics):
        super().__init__("private physical oracle exceeded " + kind)
        self.kind = kind
        self.diagnostics = diagnostics


def hand_total(cards):
    low = sum(1 if rank == "A" else 10 if rank == "T" else int(rank)
              for rank in cards)
    soft = "A" in cards and low + 10 <= 21
    return low + (10 if soft else 0), soft


def fraction_text(value):
    return str(value.numerator) + "/" + str(value.denominator)


def _world_mass(worlds):
    return sum((weight for _, _, weight in worlds), Fraction(0))


def _compress(raw):
    counted = defaultdict(Fraction)
    for hole, deck, weight in raw:
        counted[(hole, deck)] += weight
    return tuple((hole, deck, weight)
                 for (hole, deck), weight in sorted(counted.items()))


def _visible_groups(worlds):
    groups = defaultdict(list)
    for hole, deck, weight in worlds:
        if not deck:
            return None
        groups[deck[0]].append((hole, deck[1:], weight))
    return tuple((rank, _compress(group)) for rank, group in sorted(groups.items()))


class _PhysicalOracle:
    def __init__(self, up, cards, s17, max_states, max_seconds,
                 force_first_eligible_resplit, reveal_hole):
        self.started = perf_counter()
        self.up, self.cards, self.s17 = up, cards, s17
        self.max_states, self.max_seconds = max_states, max_seconds
        self.force_first = force_first_eligible_resplit
        self.reveal_hole = reveal_hole
        self.family_counts = Counter()
        self.attempts = 0
        self.maximum_hands = 0
        self.resplit_offered_nodes = 0
        self.resplit_unique_best_nodes = 0
        self.resplit_tied_best_nodes = 0
        self.resplit_declined_nodes = 0
        self.no_slot_pair_nodes = 0
        self.split_twenty_one_nodes = 0
        self.ordinary_last_draw_stand_nodes = 0
        self.forced_resplit_overrides = 0
        self.audit = []
        self.settlement_audit = []
        self.actions = {}
        self.physical_deals = factorial(len(cards))
        self.permutations_considered = 0
        self.filtered_deals = 0
        self.unique_rank_worlds = None
        counted = Counter()
        # This is a separate finite construction bound. Recurrence-state caps
        # do not count permutations, bound these tuples' bytes or replace time.
        for order in permutations(range(len(cards))):
            if self.permutations_considered % 128 == 0:
                self.check_time()
            self.permutations_considered += 1
            if self.permutations_considered > MAX_LABELED_PERMUTATIONS:
                raise OracleLimit("physical deal limit", self.diagnostics())
            hole = cards[order[0]]
            if (up == "A" and hole == "T") or (up == "T" and hole == "A"):
                continue
            counted[(hole, tuple(cards[index] for index in order[1:]))] += 1
            self.filtered_deals += 1
        self.check_time()
        self.worlds = tuple((hole, deck, Fraction(weight))
                            for (hole, deck), weight in sorted(counted.items()))
        self.unique_rank_worlds = len(self.worlds)
        self.original_hole_groups = defaultdict(list)
        for world in self.worlds:
            self.original_hole_groups[world[0]].append(world)
        self.original_hole_groups = {
            hole: tuple(group) for hole, group in self.original_hole_groups.items()
        }
        self.check_time()
        if not self.worlds:
            self.refuse("peek", "negative peek leaves no possible hidden hole")

    def diagnostics(self):
        return {
            "states": sum(self.family_counts.values()),
            "state_entry_attempts": self.attempts,
            "state_counts": dict(sorted(self.family_counts.items())),
            "physical_deals_before_peek": self.physical_deals,
            "physical_permutations_considered": self.permutations_considered,
            "physical_deals_after_peek": self.filtered_deals,
            "unique_complete_rank_worlds": self.unique_rank_worlds,
            "maximum_hands": self.maximum_hands,
            "resplit_offered_nodes": self.resplit_offered_nodes,
            "resplit_unique_best_nodes": self.resplit_unique_best_nodes,
            "resplit_tied_best_nodes": self.resplit_tied_best_nodes,
            "resplit_declined_nodes": self.resplit_declined_nodes,
            "no_slot_pair_nodes": self.no_slot_pair_nodes,
            "split_twenty_one_terminal_nodes": self.split_twenty_one_nodes,
            "ordinary_last_draw_stand_nodes": self.ordinary_last_draw_stand_nodes,
            "forced_resplit_overrides": self.forced_resplit_overrides,
            "elapsed_seconds": perf_counter() - self.started,
        }

    def check_time(self):
        if perf_counter() - self.started >= self.max_seconds:
            raise OracleLimit("time limit", self.diagnostics())

    def enter(self, family):
        self.check_time()
        self.attempts += 1
        if sum(self.family_counts.values()) >= self.max_states:
            raise OracleLimit("state limit", self.diagnostics())
        self.family_counts[family] += 1

    def refuse(self, stage, message):
        raise OracleRefusal(stage, message, self.diagnostics())

    @lru_cache(maxsize=None)
    def dealer(self, hole, deck, scope):
        self.enter(scope + " dealer")
        hand, cursor = (self.up, hole), 0
        while True:
            self.check_time()
            total, soft = hand_total(hand)
            if total > 17 or (total == 17 and (self.s17 or not soft)):
                return total, hand, cursor
            if cursor == len(deck):
                self.refuse(scope + " dealer draw", "required dealer continuation exhausts shoe")
            hand += (deck[cursor],)
            cursor += 1

    @lru_cache(maxsize=None)
    def settle(self, worlds, completed, scope):
        self.enter(scope + " settlement")
        answer = Fraction(0)
        denominator = _world_mass(worlds)
        for index, (hole, deck, weight) in enumerate(worlds):
            if index % 64 == 0:
                self.check_time()
            if all(total > 21 for total, _ in completed):
                payoff = -sum(wager for _, wager in completed)
            else:
                dealer_total, dealer_hand, draws = self.dealer(hole, deck, scope)
                payoff = sum(-wager if total > 21 else
                             wager if dealer_total > 21 or total > dealer_total else
                             -wager if total < dealer_total else 0
                             for total, wager in completed)
                # Reserve finite storage for each scope so ordinary root
                # witnesses cannot crowd every joint settlement out of audit.
                if sum(row["scope"] == scope for row in self.settlement_audit) < 32:
                    self.settlement_audit.append({
                        "scope": scope, "completed_wagers": [list(row) for row in completed],
                        "post_choice_hole": hole, "one_dealer_hand": list(dealer_hand),
                        "dealer_draws": list(deck[:draws]),
                        "remaining_after_one_dealer": list(deck[draws:]),
                        "conditional_world_probability": fraction_text(weight / denominator),
                        "combined_payoff": payoff,
                    })
            answer += weight * payoff
        return answer / denominator

    @lru_cache(maxsize=None)
    def finish(self, worlds, hand, pending, completed, slots):
        self.enter("ace finish")
        complete = completed + ((hand_total(hand)[0], 1),)
        if pending:
            return self.play(worlds, pending[0], pending[1:], complete, slots)
        return self.settle(worlds, complete, "ace")

    @lru_cache(maxsize=None)
    def mandatory_deal(self, worlds, hand, pending, completed, slots):
        self.enter("ace mandatory deal")
        groups = _visible_groups(worlds)
        if groups is None:
            self.refuse("ace mandatory deal", "required ace-child deal exhausts drawable shoe")
        denominator = _world_mass(worlds)
        return sum((_world_mass(group) / denominator * self.play(
            group, hand + (rank,), pending, completed, slots)
            for rank, group in groups), Fraction(0))

    @lru_cache(maxsize=None)
    def play(self, worlds, hand, pending, completed, slots):
        self.enter("ace player")
        self.maximum_hands = max(self.maximum_hands, len(completed) + 1 + len(pending))
        if len(hand) == 1:
            return self.mandatory_deal(worlds, hand, pending, completed, slots)
        if len(hand) != 2 or hand[0] != "A":
            raise AssertionError("private ace continuation escaped its frozen domain")
        is_pair = hand == ("A", "A")
        if is_pair and slots == 0:
            self.no_slot_pair_nodes += 1
        if hand_total(hand)[0] == 21:
            self.split_twenty_one_nodes += 1
        # A one-card-only child never evaluates H or D. Whole action completion
        # still evaluates every offered S/P branch, including an inferior P.
        stand = self.finish(worlds, hand, pending, completed, slots)
        if not is_pair or slots == 0:
            return stand
        self.resplit_offered_nodes += 1
        options = {"S": stand, "P": self.play(
            worlds, ("A",), (("A",),) + pending, completed, slots - 1)}
        best = max(options.values())
        tied = tuple(action for action in ("S", "P") if options[action] == best)
        chosen = tied[0]
        if "P" in tied:
            if len(tied) == 1:
                self.resplit_unique_best_nodes += 1
            else:
                self.resplit_tied_best_nodes += 1
        else:
            self.resplit_declined_nodes += 1
        if self.force_first:
            if options["P"] < best:
                self.forced_resplit_overrides += 1
            chosen = "P"
        self.actions[(worlds, hand, pending, completed, slots)] = chosen
        if len(self.audit) < 64:
            posterior = defaultdict(Fraction)
            for hole, _, weight in worlds:
                posterior[hole] += weight
            denominator = _world_mass(worlds)
            self.audit.append({
                "hand": list(hand), "pending_seeds": [list(seed) for seed in pending],
                "completed": [list(row) for row in completed], "remaining_extra_slots": slots,
                "visible_remaining_cards": len(worlds[0][1]),
                "hole_posterior": {hole: fraction_text(weight / denominator)
                                   for hole, weight in sorted(posterior.items())},
                "action_values": {action: fraction_text(value)
                                  for action, value in options.items()},
                "maximizing_actions": list(tied), "chosen_action": chosen,
                "choice_uses_visible_history_only": not self.reveal_hole,
            })
        return options[chosen]

    @lru_cache(maxsize=None)
    def ordinary(self, worlds, hand):
        self.enter("ordinary player")
        total = hand_total(hand)[0]
        # This explicitly preserves accepted ordinary semantics. It does not
        # transfer last-draw standing into an unpaid mandatory ace-child deal.
        if total >= 21 or not worlds[0][1]:
            if total < 21 and not worlds[0][1]:
                self.ordinary_last_draw_stand_nodes += 1
            return self.settle(worlds, ((total, 1),), "ordinary")
        stand = self.settle(worlds, ((total, 1),), "ordinary")
        hit = self.ordinary_draw(worlds, hand, False)
        return max(stand, hit)

    @lru_cache(maxsize=None)
    def ordinary_draw(self, worlds, hand, doubled):
        self.enter("ordinary observable draw")
        groups = _visible_groups(worlds)
        if groups is None:
            self.refuse("ordinary player draw", "forced original draw exhausts drawable shoe")
        answer, denominator = Fraction(0), _world_mass(worlds)
        for rank, group in groups:
            next_hand = hand + (rank,)
            future = (self.settle(group, ((hand_total(next_hand)[0], 2),), "ordinary")
                      if doubled else self.ordinary(group, next_hand))
            answer += _world_mass(group) / denominator * future
        return answer

    def root_values(self, worlds, extra_slots, include_root, can_double, can_split):
        values = {}
        if include_root:
            self.maximum_hands = max(self.maximum_hands, 1)
            values["S"] = self.settle(worlds, ((12, 1),), "ordinary")
            values["H"] = self.ordinary_draw(worlds, ("A", "A"), False)
            if can_double:
                values["D"] = self.ordinary_draw(worlds, ("A", "A"), True)
        if can_split:
            values["P"] = self.play(worlds, ("A",), (("A",),), (), extra_slots)
        return values

    def joint_policy_audit(self, worlds, slots):
        """Traverse the canonical optimum's complete visible outcomes.

        Counts concern unique decision states, not their event probability.
        Audit storage is bounded. Recurrence completion already covers branches
        of alternatives not selected by the lawful policy.
        """
        visited, samples, counts = set(), [], Counter()

        def follow(current, hand, pending, completed, remaining_slots):
            self.check_time()
            key = (current, hand, pending, completed, remaining_slots)
            if key in visited:
                return
            visited.add(key)
            counts["visited_states"] += 1
            if len(hand) == 1:
                action = "mandatory"
            elif hand == ("A", "A") and remaining_slots:
                action = self.actions[key]
                counts["eligible_pair_states"] += 1
                counter = "selected_resplit_states" if action == "P" else "declined_resplit_states"
                counts[counter] += 1
                if len(samples) < 32:
                    samples.append({"hand": list(hand), "pending_seed_count": len(pending),
                                    "completed_hand_count": len(completed),
                                    "remaining_extra_slots": remaining_slots,
                                    "selected_action": action})
            else:
                action = "closed"
                if hand == ("A", "A"):
                    counts["slot_exhausted_pair_states"] += 1
            if action == "P":
                follow(current, ("A",), (("A",),) + pending, completed, remaining_slots - 1)
            elif action == "mandatory":
                groups = _visible_groups(current)
                if groups is None:
                    raise AssertionError("accepted ace policy has an unavailable mandatory deal")
                for rank, group in groups:
                    follow(group, hand + (rank,), pending, completed, remaining_slots)
            elif pending:
                done = completed + ((hand_total(hand)[0], 1),)
                follow(current, pending[0], pending[1:], done, remaining_slots)

        follow(worlds, ("A",), (("A",),), (), slots)
        return {"state_counts": dict(sorted(counts.items())), "samples": samples,
                "tie_rule": "S before P, no policy epsilon", "audit_sample_limit": 32}


def _qualify_case(up, cards, *, s17=True, das=False, can_double=True, can_split=True,
                  include_root=True, extra_slots=1, max_states=MAX_STATES,
                  max_seconds=MAX_SECONDS, reveal_hole=False,
                  force_first_eligible_resplit=False):
    if type(cards) not in (list, tuple):
        raise ValueError("physical retained cards must be an explicit list or tuple")
    cards = tuple(cards)
    if type(up) is not str or up not in RANKS:
        raise ValueError("oracle requires a canonical dealer upcard")
    if not 3 <= len(cards) <= MAX_PHYSICAL_CARDS or any(
            type(rank) is not str or rank not in RANKS for rank in cards):
        raise ValueError("physical reference admits 3 through 8 canonical retained cards")
    flags = (s17, das, can_double, can_split, include_root, reveal_hole,
             force_first_eligible_resplit)
    if any(type(flag) is not bool for flag in flags):
        raise ValueError("every oracle flag must be a strict boolean")
    if type(extra_slots) is not int or extra_slots not in (0, 1):
        raise ValueError("private lawful capacity is two hands or one shared extra slot")
    if type(max_states) is not int or not 1 <= max_states <= MAX_STATES:
        raise ValueError("private recurrence cap must be 1 through 100000")
    if (type(max_seconds) not in (int, float) or not isfinite(max_seconds)
            or not 0 < max_seconds <= MAX_SECONDS):
        raise ValueError("cooperative construction/calculation time must be positive "
                         "and at most ten seconds")
    if not include_root and not can_split:
        raise ValueError("forced-initial-P evidence requires can_split=true")
    oracle = _PhysicalOracle(up, cards, s17, max_states, max_seconds,
                             force_first_eligible_resplit, reveal_hole)
    groups = ((None, oracle.worlds),)
    if reveal_hole:
        groups = tuple(sorted(oracle.original_hole_groups.items()))
    totals, best_value, policy = defaultdict(Fraction), Fraction(0), []
    denominator = _world_mass(oracle.worlds)
    for revealed, worlds in groups:
        values = oracle.root_values(worlds, extra_slots, include_root, can_double, can_split)
        probability = _world_mass(worlds) / denominator
        for action, value in values.items():
            totals[action] += probability * value
        best_value += probability * max(values.values())
        if can_split:
            policy.append({"revealed_hole": revealed, "probability": fraction_text(probability),
                           "joint_policy": oracle.joint_policy_audit(worlds, extra_slots)})
    oracle.check_time()
    maximizing = (None if reveal_hole else
                  [action for action in ACTION_ORDER if totals.get(action) == best_value])
    sorted_values = sorted(totals.values(), reverse=True)
    margin = sorted_values[0] - sorted_values[1] if len(sorted_values) > 1 else Fraction(0)
    policy_counts = Counter()
    for group in policy:
        policy_counts.update(group["joint_policy"]["state_counts"])
    diagnostics = oracle.diagnostics()
    diagnostics["joint_policy_state_counts"] = dict(sorted(policy_counts.items()))
    evidence_scope = ("explicit unsafe revealed-hole control" if reveal_hole else
                      "explicit unsafe forced-first-resplit control" if
                      force_first_eligible_resplit else
                      "complete original decision" if include_root else "forced initial P only")
    result = {
        "status": "completed", "model": MODEL,
        "arithmetic": "exact Fraction expectation of complete labeled physical deals",
        "evidence_scope": evidence_scope,
        "pair": "A", "up": up, "cards": list(cards), "s17": s17, "das": das,
        "can_double": can_double, "can_split": can_split, "include_root": include_root,
        "extra_slots": extra_slots, "maximum_supported_hands": 2 + extra_slots,
        "unsafe_reveal_hole": reveal_hole,
        "unsafe_force_first_eligible_resplit": force_first_eligible_resplit,
        "root_action_values": {action: fraction_text(value) for action, value in totals.items()},
        "root_best_value": fraction_text(best_value), "root_maximizing_actions": maximizing,
        "root_recommended_action": None if maximizing is None else maximizing[0],
        "root_margin": None if reveal_hole else fraction_text(margin),
        "root_choice_semantics": ("illegal per-hole maxima before averaging" if reveal_hole else
                                  "maximize after averaging concealed worlds by visible history"),
        "diagnostics": diagnostics, "bounded_action_audit": oracle.audit,
        "joint_initial_split_policy_audit": policy,
        "settlement_audit": oracle.settlement_audit,
        "limits": {"max_states": max_states, "max_seconds": max_seconds,
                   "maximum_physical_cards": MAX_PHYSICAL_CARDS,
                   "maximum_labeled_permutations": MAX_LABELED_PERMUTATIONS,
                   "recurrence_state_cap_is_not_deal_or_memory_cap": True},
    }
    methods = (oracle.dealer, oracle.settle, oracle.finish, oracle.mandatory_deal,
               oracle.play, oracle.ordinary, oracle.ordinary_draw)
    result["diagnostics"]["cache_hits"] = sum(method.cache_info().hits for method in methods)
    oracle.check_time()
    return result


def qualify_case(up, cards, **controls):
    """Serial private entry with cache release on success and every exception."""
    try:
        return _qualify_case(up, cards, **controls)
    finally:
        for name in ("dealer", "settle", "finish", "mandatory_deal", "play",
                     "ordinary", "ordinary_draw"):
            getattr(_PhysicalOracle, name).cache_clear()


def run_case(case):
    """Dictionary adapter. Metadata id is preserved without mathematical use.

    Required fields are up and cards. pair, when supplied, must be the canonical
    original rank A. Unknown input fields refuse instead of changing semantics.
    Result values are reduced fraction strings, never candidate binary floats.
    A valid required-continuation refusal or resource limit is a returned outcome
    with reason and diagnostics only. It carries no partial numerical values or
    audits. Malformed private API inputs still raise ValueError.
    """
    if type(case) is not dict:
        raise ValueError("case must be an ordinary dictionary")
    allowed = {"id", "pair", "up", "cards", "s17", "das", "can_double", "can_split",
               "include_root", "extra_slots", "max_states", "max_seconds", "reveal_hole",
               "force_first_eligible_resplit"}
    if set(case) - allowed or not {"up", "cards"} <= set(case):
        raise ValueError("case fields do not match the private physical API")
    if case.get("pair", "A") != "A":
        raise ValueError("the private candidate is an original ace pair")
    controls = {key: value for key, value in case.items()
                if key not in {"id", "pair", "up", "cards"}}
    try:
        result = qualify_case(case["up"], case["cards"], **controls)
    except OracleRefusal as error:
        result = {
            "status": "unsupported_continuation", "model": MODEL,
            "type": "OracleRefusal", "stage": error.stage,
            "reason": str(error), "diagnostics": error.diagnostics,
            "evidence_scope": ("complete original decision" if controls.get("include_root", True)
                               else "forced initial P only"),
        }
    except OracleLimit as error:
        result = {
            "status": "resource_limited", "model": MODEL,
            "type": "OracleLimit", "stage": "resource", "limit_kind": error.kind,
            "reason": str(error), "diagnostics": error.diagnostics,
            "evidence_scope": ("complete original decision" if controls.get("include_root", True)
                               else "forced initial P only"),
        }
    if "id" in case:
        result["id"] = case["id"]
    return result
