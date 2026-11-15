# Rational cross check

[The exact reference](../tests/rational_reference.py) | [The comparison](../tests/test_rational_cross_check.py)

The solver computes in binary64 floating point. Every probability in these
models is a ratio of card counts, so every true value is a rational number. I
recomputed the values the README leans on with Python's `fractions.Fraction`,
in a separate implementation that imports nothing from `bj`, and measured how
far the floating point values are from the exact ones.

Across the 45 published stand, hit and double cells, the largest difference is
2.05e-16, for the double in 16 v 10 (T,6). Across the 31 action values of the
eight bounded example requests, which cover all five bounded families, the
largest difference is 1.86e-16, for the double in
`common-shoe-mixed-request.json`. So every one of those 76 values is within
2.05e-16 of exact, in units of the original wager.

That bound is absolute, not relative. The spacing between neighboring binary64
numbers, one unit in the last place, shrinks with the value. The two largest
differences are 0.92 of a unit at −1.0694 and 1.67 units at −0.5803. A value
near zero can be many units off while its absolute error stays this small. The
A,6 v 2 hit value is about 0.0007 and is about 178 units off, because its
rounding comes from intermediate sums much larger than the result.

## What is recomputed

The published cells are the stand, hit and double values for the fifteen
marginal hands in `tests/test_ev.py`, each on a fresh six deck shoe minus the
visible cards. They are post peek values from `bj.ev`. The reference restates
that model: the hole is one of the unseen cards and never the rank the peek
ruled out, the player's draws are conditioned on that, and a hit continues
with the better of standing and hitting until 21 or a bust.

The example requests are the files under `examples/` for the five bounded
families. Their stand, hit and double values come from the same post peek
model on small shoes, with its rule that a hand stands after the last drawable
card. Their split values come from one exact recursion that covers the three
common shoe families: two hands with no resplit, up to three non ace hands
sharing one resplit, and split aces sharing one resplit. Late surrender is a
loss of exactly half the wager. The deferred second card family has its own
short recursion, with the dealer's second card dealt after the player and a
dealer natural taking every wager.

The engine values for the requests come from the same record functions that
`bj-calculate` uses. Each difference is computed exactly, as the floating
point number converted to a fraction minus the exact value, and only then
turned into a float for this page.

## Random small shoes

Fixed inputs can miss a branch the models rarely reach, so every restated
model also runs on random small shoes.

The split recursion runs against `bj.joint_split`, `bj.joint_resplit` and
`bj.joint_ace_resplit` on 100 shoes for each family, with the resplit shoes
leaning toward high ranks so that more of them can finish. Small shoes often
run out, so many of these are refusals: 25, 23 and 68 shoes complete with a
value, and 70, 77 and 32 are refused. Six two hand shoes are skipped because
the floating point reference stopped at its own state cap. A fixed two hand
case also checks that a hand reaching 21 by hitting stops there.

Stand, hit and double run against `ev.best_action` on 150 shoes of one to
twelve cards, with 116 values and 34 refusals. The deferred second card model
runs against its own `decide` on the same kind of shoes plus one fixed case
where the player must stand to leave the dealer a card, with 110 values and 41
refusals.

Every value agrees within 1e-13, and the floating point and exact versions
refuse exactly the same shoes.

Earlier rational checks deal every physical card order of a tiny shoe, which
only works for a handful of cards (`tests/test_ev_physical_reference.py` and
the two resplit references). This one works from card counts, so it reaches
the full six deck shoe.

## What it shows and what it does not

On these inputs every floating point value is within 2.05e-16 of exact. Where
a best action wins by more than about 1e-15, rounding cannot have changed it
on these inputs.

One shipped example sits inside that caveat. In `common-shoe-request.json`,
5,5 against T, hitting and doubling both have an exact value of 0. Floating
point puts hitting ahead by 5.6e-17, which is rounding. Hit is still the
recorded action, because it comes before double in the tie order, but that
margin says nothing about the cards.

This is a check of specific inputs, not a bound for every shoe or every
request. Longer recursions take more rounding steps, and a margin smaller
than the rounding error would still be unsafe to read. The reference shares
the models' definitions, so it catches arithmetic and implementation errors,
not a model that answers a different question from the one a reader has in
mind.

The comparison runs in the ordinary test set:

```sh
python -m pytest -q tests/test_rational_cross_check.py
```
