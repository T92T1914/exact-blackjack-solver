"""Independent tiny-shoe physical-deal/Fraction reference; imports no engine.

Adapted without mathematical changes from the frozen bounded-resplit
qualification oracle, SHA-256 bf253641b8371f65ce444f108c39860938cb5db86212f66383e270d4d6f4ec1f.
This test-only reference is not a supported Solver interface. The caller owns
process retirement and physical resource limits. All legally offered branches
must complete before any result can be returned. Ordinary root comparisons are
limited to these high-rank fixtures; the reference does not replace the engine's
ordinary last-player-draw standing convention.
"""
from collections import Counter, defaultdict
from fractions import Fraction
from functools import lru_cache
from itertools import permutations
from math import factorial, isfinite
from time import perf_counter


RANKS = tuple("A23456789T")
ACTION_ORDER = ("S", "H", "D", "P")


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


def hand_total(hand):
    low = sum(1 if rank == "A" else 10 if rank == "T" else int(rank)
              for rank in hand)
    soft = "A" in hand and low <= 11
    return low + (10 if soft else 0), soft


def fraction_text(value):
    return str(value.numerator) + "/" + str(value.denominator)


def _world_mass(worlds):
    return sum((weight for _, _, weight in worlds), Fraction(0))


def _compress(raw):
    counter = defaultdict(Fraction)
    for hole, deck, weight in raw:
        counter[(hole, deck)] += weight
    return tuple((hole, deck, weight)
                 for (hole, deck), weight in sorted(counter.items()))


def _visible_groups(worlds):
    groups = defaultdict(list)
    for hole, deck, weight in worlds:
        if not deck:
            return None
        groups[deck[0]].append((hole, deck[1:], weight))
    return tuple((rank, _compress(group)) for rank, group in sorted(groups.items()))


class _PhysicalOracle:
    def __init__(self, pair, up, cards, das, s17, max_states, max_seconds,
                 replenish_between_hands, force_first_eligible_resplit):
        self.pair, self.up, self.cards = pair, up, cards
        self.das, self.s17 = das, s17
        self.max_states, self.max_seconds = max_states, max_seconds
        self.replenish = replenish_between_hands
        self.force_first = force_first_eligible_resplit
        self.started = perf_counter()
        self.family_counts = Counter()
        self.attempts = 0
        self.maximum_hands = 0
        self.no_slot_pair_nodes = 0
        self.resplit_offered_nodes = 0
        self.resplit_unique_best_nodes = 0
        self.resplit_tied_best_nodes = 0
        self.resplit_declined_nodes = 0
        self.forced_resplit_overrides = 0
        self.split_twenty_one_nodes = 0
        self.actions = {}
        self.audit = []
        self.physical_deals = factorial(len(cards))
        self.filtered_deals = 0
        counted = Counter()
        # Enumerate physical labels, then quotient only identical complete rank
        # sequences. Multiplicity is retained exactly, including peek filtering.
        for number, order in enumerate(permutations(range(len(cards)))):
            if number % 256 == 0:
                self.check_time()
            hole = cards[order[0]]
            if (up == "A" and hole == "T") or (up == "T" and hole == "A"):
                continue
            counted[(hole, tuple(cards[index] for index in order[1:]))] += 1
            self.filtered_deals += 1
        self.worlds = tuple((hole, deck, Fraction(weight))
                            for (hole, deck), weight in sorted(counted.items()))
        self.unique_rank_worlds = len(self.worlds)
        self.original_hole_groups = defaultdict(list)
        for world in self.worlds:
            self.original_hole_groups[world[0]].append(world)
        self.original_hole_groups = {
            hole: tuple(group) for hole, group in self.original_hole_groups.items()
        }
        if not self.worlds:
            self.refuse("peek", "negative peek leaves no possible hidden hole")

    def diagnostics(self):
        return {
            "states": sum(self.family_counts.values()),
            "state_entry_attempts": self.attempts,
            "state_counts": dict(sorted(self.family_counts.items())),
            "physical_deals_before_peek": self.physical_deals,
            "physical_deals_after_peek": self.filtered_deals,
            "unique_complete_rank_worlds": getattr(self, "unique_rank_worlds", None),
            "maximum_hands": self.maximum_hands,
            "no_slot_pair_nodes": self.no_slot_pair_nodes,
            "resplit_offered_nodes": self.resplit_offered_nodes,
            "resplit_unique_best_nodes": self.resplit_unique_best_nodes,
            "resplit_tied_best_nodes": self.resplit_tied_best_nodes,
            "resplit_declined_nodes": self.resplit_declined_nodes,
            "forced_resplit_overrides": self.forced_resplit_overrides,
            "split_twenty_one_terminal_nodes": self.split_twenty_one_nodes,
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

    def restored_worlds(self, worlds):
        # Deliberately illegal counterexample: replace consumed cards when moving
        # to a new hand, but keep the same posterior hole. Never used lawfully.
        by_hole = defaultdict(Fraction)
        for hole, _, weight in worlds:
            by_hole[hole] += weight
        raw = []
        for hole, posterior_mass in by_hole.items():
            original = self.original_hole_groups[hole]
            denominator = _world_mass(original)
            raw.extend((hole, deck, posterior_mass * weight / denominator)
                       for _, deck, weight in original)
        return _compress(raw)

    @lru_cache(maxsize=None)
    def settle(self, worlds, completed):
        self.enter("settlement")
        result = Fraction(0)
        for index, (hole, deck, weight) in enumerate(worlds):
            if index % 64 == 0:
                self.check_time()
            if all(total > 21 for total, _ in completed):
                payoff = -sum(wager for _, wager in completed)
            else:
                dealer, cursor = (self.up, hole), 0
                while True:
                    dealer_total, soft = hand_total(dealer)
                    if dealer_total > 17 or (dealer_total == 17 and (self.s17 or not soft)):
                        break
                    if cursor == len(deck):
                        self.refuse("dealer draw", "offered continuation exhausts dealer draw")
                    dealer += (deck[cursor],)
                    cursor += 1
                payoff = sum(-wager if total > 21 else
                             wager if dealer_total > 21 or total > dealer_total else
                             -wager if total < dealer_total else 0
                             for total, wager in completed)
            result += weight * payoff
        return result / _world_mass(worlds)

    @lru_cache(maxsize=None)
    def finish(self, worlds, hand, pending, completed, slots, wager):
        self.enter("finish")
        complete = completed + ((hand_total(hand)[0], wager),)
        if not pending:
            return self.settle(worlds, complete)
        next_worlds = self.restored_worlds(worlds) if self.replenish else worlds
        return self.play(next_worlds, pending[0], pending[1:], complete, slots)

    @lru_cache(maxsize=None)
    def draw(self, worlds, hand, pending, completed, slots, doubled):
        self.enter("observable draw")
        groups = _visible_groups(worlds)
        if groups is None:
            self.refuse("player draw", "offered continuation exhausts player draw")
        value, denominator = Fraction(0), _world_mass(worlds)
        for rank, group in groups:
            next_hand = hand + (rank,)
            future = (self.finish(group, next_hand, pending, completed, slots, 2)
                      if doubled else self.play(group, next_hand, pending, completed, slots))
            value += _world_mass(group) / denominator * future
        return value

    @lru_cache(maxsize=None)
    def play(self, worlds, hand, pending, completed, slots):
        self.enter("joint player")
        self.maximum_hands = max(self.maximum_hands, len(completed) + 1 + len(pending))
        if len(hand) == 1:
            return self.draw(worlds, hand, pending, completed, slots, False)
        total = hand_total(hand)[0]
        if total >= 21:
            if total == 21 and len(hand) == 2:
                self.split_twenty_one_nodes += 1
            return self.finish(worlds, hand, pending, completed, slots, 1)
        is_pair = len(hand) == 2 and hand[0] == hand[1] == self.pair
        offered_resplit = is_pair and slots > 0
        if is_pair and slots == 0:
            self.no_slot_pair_nodes += 1
        if offered_resplit:
            self.resplit_offered_nodes += 1
        # Order is deliberately explicit. Do not short circuit an inferior draw
        # branch, a known favorable resplit, or a known favorable stand policy.
        options = {"S": self.finish(worlds, hand, pending, completed, slots, 1)}
        options["H"] = self.draw(worlds, hand, pending, completed, slots, False)
        if self.das and len(hand) == 2:
            options["D"] = self.draw(worlds, hand, pending, completed, slots, True)
        if offered_resplit:
            options["P"] = self.play(
                worlds, (hand[0],), ((hand[1],),) + pending, completed, slots - 1)
        best = max(options.values())
        tied = tuple(action for action in ACTION_ORDER if options.get(action) == best)
        chosen = tied[0]
        if offered_resplit:
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
            if len(self.audit) < 32:
                hole_mass = defaultdict(Fraction)
                for hole, _, weight in worlds:
                    hole_mass[hole] += weight
                denominator = _world_mass(worlds)
                self.audit.append({
                    "hand": list(hand), "pending_seeds": [list(seed) for seed in pending],
                    "completed": [[total, wager] for total, wager in completed],
                    "remaining_extra_slots": slots,
                    "visible_remaining_cards": len(worlds[0][1]),
                    "hole_posterior": {hole: fraction_text(weight / denominator)
                                       for hole, weight in sorted(hole_mass.items())},
                    "action_values": {action: fraction_text(value)
                                      for action, value in options.items()},
                    "maximizing_actions": list(tied), "chosen_action": chosen,
                })
        self.actions[(worlds, hand, pending, completed, slots)] = chosen
        return options[chosen]

    @lru_cache(maxsize=None)
    def ordinary(self, worlds, hand):
        self.enter("ordinary player")
        if hand_total(hand)[0] >= 21:
            return self.settle(worlds, ((hand_total(hand)[0], 1),))
        stand = self.settle(worlds, ((hand_total(hand)[0], 1),))
        hit = self.ordinary_draw(worlds, hand, False)
        return max(stand, hit)

    @lru_cache(maxsize=None)
    def ordinary_draw(self, worlds, hand, doubled):
        self.enter("ordinary observable draw")
        groups = _visible_groups(worlds)
        if groups is None:
            self.refuse("ordinary player draw", "offered ordinary draw exhausts shoe")
        result, denominator = Fraction(0), _world_mass(worlds)
        for rank, group in groups:
            next_hand = hand + (rank,)
            value = (self.settle(group, ((hand_total(next_hand)[0], 2),))
                     if doubled else self.ordinary(group, next_hand))
            result += _world_mass(group) / denominator * value
        return result

    def root_values(self, worlds, extra_slots, include_root):
        values = {}
        if include_root:
            original = (self.pair, self.pair)
            values["S"] = self.settle(worlds, ((hand_total(original)[0], 1),))
            values["H"] = self.ordinary_draw(worlds, original, False)
            values["D"] = self.ordinary_draw(worlds, original, True)
        values["P"] = self.play(worlds, (self.pair,), ((self.pair,),), (), extra_slots)
        return values

    def joint_policy_audit(self, worlds, slots):
        """Follow canonical maximizing actions, preserving all visible outcomes.

        This counts unique observable decision states, not probability of use or
        the number of physically dealt episodes. P is last in exact ties.
        """
        visited, samples = set(), []
        counts = Counter()
        def follow(current_worlds, hand, pending, completed, remaining_slots):
            self.check_time()
            key = (current_worlds, hand, pending, completed, remaining_slots)
            if key in visited:
                return
            visited.add(key)
            counts["visited_states"] += 1
            if len(hand) == 1:
                action = "mandatory"
            elif hand_total(hand)[0] >= 21:
                action = "terminal"
            else:
                action = self.actions[key]
            if len(hand) == 2 and hand[0] == hand[1] == self.pair:
                if remaining_slots:
                    counts["eligible_pair_states"] += 1
                    if action == "P":
                        counts["selected_resplit_states"] += 1
                    else:
                        counts["declined_resplit_states"] += 1
                    if len(samples) < 16:
                        samples.append({"hand": list(hand), "pending_seed_count": len(pending),
                                        "completed_hand_count": len(completed),
                                        "remaining_extra_slots": remaining_slots,
                                        "selected_action": action})
                else:
                    counts["slot_exhausted_pair_states"] += 1
            if action == "P":
                follow(current_worlds, (hand[0],), ((hand[1],),) + pending,
                       completed, remaining_slots - 1)
            elif action in ("mandatory", "H", "D"):
                groups = _visible_groups(current_worlds)
                assert groups is not None
                for rank, group in groups:
                    if action == "D":
                        done = completed + ((hand_total(hand + (rank,))[0], 2),)
                        if pending:
                            next_worlds = self.restored_worlds(group) if self.replenish else group
                            follow(next_worlds, pending[0], pending[1:], done, remaining_slots)
                    else:
                        follow(group, hand + (rank,), pending, completed, remaining_slots)
            elif pending:
                done = completed + ((hand_total(hand)[0], 1),)
                next_worlds = (self.restored_worlds(current_worlds) if self.replenish
                               else current_worlds)
                follow(next_worlds, pending[0], pending[1:], done, remaining_slots)
        follow(worlds, (self.pair,), ((self.pair,),), (), slots)
        return {"state_counts": dict(sorted(counts.items())), "samples": samples,
                "tie_rule": "S,H,D,P; P is not selected on a tie"}


def _qualify_case(pair, up, cards, *, das=False, s17=True, reveal_hole=False,
                 replenish_between_hands=False, force_first_eligible_resplit=False,
                 extra_slots=1, max_states=100000, max_seconds=10.0,
                 include_root=True):
    """Return only a complete rational tiny-shoe result or an explicit exception.

    Ordinary S/H/D are priced independently from complete physical deals. P means
    the initial split plus at most one global extra split when extra_slots=1.
    Controls reveal_hole/replenish/force_first/extra_slots=2 are unsafe comparison
    models. They never modify or qualify the lawful result.
    """
    cards = tuple(cards)
    if pair not in RANKS or pair == "A" or up not in RANKS:
        raise ValueError("oracle needs a non-ace original pair and canonical up rank")
    if not 3 <= len(cards) <= 8 or any(rank not in RANKS for rank in cards):
        raise ValueError("private physical qualification uses 3 through 8 canonical cards")
    flags = (das, s17, reveal_hole, replenish_between_hands,
             force_first_eligible_resplit, include_root)
    if any(type(flag) is not bool for flag in flags):
        raise ValueError("all oracle flags must be strict booleans")
    if type(extra_slots) is not int or extra_slots not in (0, 1, 2):
        raise ValueError("extra_slots is 0, 1 lawful, or 2 explicit unsafe capacity")
    if type(max_states) is not int or not 1 <= max_states <= 100000:
        raise ValueError("private state cap must be 1 through 100000")
    if isinstance(max_seconds, bool) or not isfinite(max_seconds) or max_seconds <= 0:
        raise ValueError("private time cap must be finite and positive")
    oracle = _PhysicalOracle(pair, up, cards, das, s17, max_states, max_seconds,
                             replenish_between_hands, force_first_eligible_resplit)
    groups = ((None, oracle.worlds),)
    if reveal_hole:
        groups = tuple(sorted(oracle.original_hole_groups.items()))
    all_values, best_value, policy = defaultdict(Fraction), Fraction(0), []
    denominator = _world_mass(oracle.worlds)
    for revealed_hole, worlds in groups:
        values = oracle.root_values(worlds, extra_slots, include_root)
        probability = _world_mass(worlds) / denominator
        for action, value in values.items():
            all_values[action] += probability * value
        best_value += probability * max(values.values())
        policy.append({"revealed_hole": revealed_hole,
                       "probability": fraction_text(probability),
                       "joint_policy": oracle.joint_policy_audit(worlds, extra_slots)})
    oracle.check_time()
    result = {
        "status": "completed", "arithmetic": "exact Fraction over complete physical deals",
        "pair": pair, "up": up, "cards": list(cards), "das": das, "s17": s17,
        "extra_slots": extra_slots, "maximum_supported_hands": 2 + extra_slots,
        "unsafe_reveal_hole": reveal_hole,
        "unsafe_replenish_between_hands": replenish_between_hands,
        "unsafe_force_first_eligible_resplit": force_first_eligible_resplit,
        "root_action_values": {action: fraction_text(value)
                               for action, value in all_values.items()},
        "root_best_value": fraction_text(best_value),
        "root_maximizing_actions": (None if reveal_hole else
            [action for action in ACTION_ORDER if all_values.get(action) == best_value]),
        "root_choice_semantics": ("average per-hole best values, illegally revealed hole"
                                  if reveal_hole else "maximize after hidden-hole averaging"),
        "diagnostics": oracle.diagnostics(), "bounded_action_audit": oracle.audit,
        "joint_initial_split_policy_audit": policy,
        "limits": {"max_states": max_states, "max_seconds": max_seconds,
                   "maximum_physical_cards": 8},
    }
    methods = (oracle.settle, oracle.finish, oracle.draw, oracle.play,
               oracle.ordinary, oracle.ordinary_draw)
    result["diagnostics"]["cache_hits"] = sum(method.cache_info().hits for method in methods)
    return result


def qualify_case(pair, up, cards, *, das=False, s17=True, reveal_hole=False,
                 replenish_between_hands=False, force_first_eligible_resplit=False,
                 extra_slots=1, max_states=100000, max_seconds=10.0,
                 include_root=True):
    """Serial private entry, with cache clearing on success and every exception.

    Class-scoped functools caches use self in their keys. The finally block is
    needed even when strict branch refusal or a qualification limit interrupts
    a case. Concurrent calls into this private oracle are not supported.
    """
    try:
        return _qualify_case(
            pair, up, cards, das=das, s17=s17, reveal_hole=reveal_hole,
            replenish_between_hands=replenish_between_hands,
            force_first_eligible_resplit=force_first_eligible_resplit,
            extra_slots=extra_slots, max_states=max_states,
            max_seconds=max_seconds, include_root=include_root)
    finally:
        for name in ("settle", "finish", "draw", "play", "ordinary", "ordinary_draw"):
            getattr(_PhysicalOracle, name).cache_clear()
