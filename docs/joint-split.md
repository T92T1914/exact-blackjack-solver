# A bounded reference for two hands

The production solver prices each split hand against the starting shoe. That
keeps its state space manageable, but the first hand actually removes cards
before the second hand plays. The second hand also changes the dealer's draw
pile, so a completed first hand still matters to later choices.

I added a separate numerical reference in `bj/joint_split.py`. It supports
exactly two hands and no resplits. Its counts include a reserved hidden dealer
hole, after a completed peek has ruled out a natural. The first hand finishes
before the second receives its additional card. Both hands settle against one
dealer outcome, with a separate wager for each. Split aces get one card each.
The supported player continuation ends at 21, and a double takes one card.

## Information before choice

For each possible hidden hole, the reference computes how many cards of each
rank remain drawable. It averages those probabilities before branching on an
observed player card. After that visible draw, the remaining eligible hole
counts give the updated belief. A choice never receives the actual hole rank.
The maximum is over combined round values under that common belief. Moving
the maximum inside the hole loop would give the player information it lacks.

The first hand's total and wager remain in state while the second plays. Its
settlement is not replaced with an independent expectation at the moment it
stands. Each possible terminal dealer result settles both recorded hands.
Every transition removes an actual card from the common immutable counts.

This is complete enumeration inside the stated model using floating point.
It is not symbolic exact arithmetic. A separate test oracle enumerates physical
card permutations and groups them by visible history using `Fraction` values.
The tests compare tiny cases, preserve probability mass and demonstrate the
value incorrectly gained by revealing the hidden hole. No production hand,
dealer or Bellman helper supplies the reference arithmetic.

## Bounded execution and comparison

The API accepts 3 to 20 unseen cards. Defaults cap enumeration at 100,000 states
and ten seconds. Each call owns its caches. Exceeding a limit is an explicit
failure, not a partial value. The time cap is checked at each new enumeration
state and before returning a completed value. It is a cooperative check, not a
process watchdog. The final check includes preparation of the result diagnostics.

An unavailable draw in any admitted continuation also fails the case. This
includes an action that would not be selected after
all valid values were known. The reference does not invent a reshuffle.
For example, if the second hand is below 21 with only the hidden hole left,
its hit action cannot be valued. The reference refuses the whole condition
even when standing could settle. It does not silently force that hand to stand.

The [declared protocol](joint-split-protocol.json) fixes 48 conditions across two
eight card high rank shoes, four pairs, three dealer upcards and both DAS states.
Its first comparison must run from a clean reviewed commit. The runner retains
the first attempt, every exclusion, source identities, values, margins, runtimes
and work counts. It never replaces an existing result path.
The reference uses rank order 2 through T, then A. Production uses A, then 2
through T. The comparison translates counts by rank name and records the
production order and counts in every completed row. Positional equivalence is
not assumed.

```python
from bj.joint_split import joint_split_value

# Rank order is 2, 3, 4, 5, 6, 7, 8, 9, T, A. Visible cards are already excluded.
result = joint_split_value('5', 'T', (0, 0, 0, 0, 0, 2, 2, 2, 2, 0))
print(result.value, result.states, result.maximum_probability_mass_error)
```

```sh
python tools/compare_joint_split.py --output ../joint-split-attempt.json
```

The signed gap is production minus joint value. Root comparisons replace only
the split action, retaining production stand, hit and double values. Ties within
`1e-12` are reported as an action set. The best value minus the next value remains
the numerical margin. A changed action set is a recorded decision change, even
when its margin is small. No condition is selected after seeing its error.

The historical resplit bracket concerns one shared slot decision inside the
independent hand approximation. It does not bound joint shoe or information
effects. This new toy family also cannot establish a full shoe error bound or
house edge. The production API continues to use its existing approximation.


## Retained comparison

The [public report](https://t92t1914.github.io/exact-blackjack-solver/joint-split.html)
uses the saved [matched result](joint-split-results.json) from revision
`9b8f54c85fe7689490503a8874e41f7d48b53127`. All 48 conditions completed. The largest
absolute gap was 0.032142857 units, for twos against T in the ten rich shoe with
DAS enabled. Its sign was negative, so production valued the split lower.
The mean absolute gap was 0.003056107 units.

For fives against 6 in the balanced shoe with DAS enabled, the best action set
expanded from D to a D/P tie. The production margin was 0.023809524 and the
joint margin was zero. No best action set became disjoint from its production
counterpart. A tie expansion is not a strict reversal.

The [invalid first attempt](joint-split-first-invalid.json) ran at
`58330ad09985ad265d25cc3cb93069d2d09d7aa5`. Its runner passed reference ordered
counts directly into production, whose first rank is A. Its production values,
gaps and combined root recommendations therefore compare different shoes and
cannot support the declared claim. The raw attempt remains unchanged. A rank
keyed adapter and asymmetric mapping regression were committed before the
single corrected run. The frozen protocol and reference arithmetic did not
change. Every completed corrected row records both rank orders and counts.

The report auditor independently checks these identities and recomputes gaps,
root rankings and margins from saved values. It does not invoke either solver.
The maximum reference work count was 3,260 states. The largest observed
reference time was about 0.014 seconds on a shared machine, which is bounded
feasibility evidence rather than a controlled speed comparison.

```sh
python tools/render_joint_report.py --check
python tools/build_site.py
```

The site build includes all rows, data downloads and editable SVG editions.
Auto, Clair and Obscur preserve dealer identities, units and values. Print
uses Clair. Inter resolves locally when available, with system fallback for
other visitors and no remote font requests. The old diagram and its evidence
retain their original bytes. The renderer revision is recorded separately
from the measured source revision. Rebuilding does not rerun the study.
