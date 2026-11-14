# Split error on the six deck table

[Saved results](split-error-study-results.json) | [The script](../tools/split_error_study.py) | [The bounded two hand reference](joint-split.md)

The default solver values a split as two independent hands. I measured how far
that value is from the two hand common shoe value in every pair and upcard
cell of the six deck table, with two hands and no resplit. The default is never
above the common shoe value by more than rounding, which reaches 1.5e-15. The
largest gap is 0.000538738 units of the original wager, for 2,2 against 4. In
73 of the 100 cells the two values are within 1e-12 of each other, and no cell
changes its best action.

## What is compared

The table is the solver's default table with the hand limit set to two: six
decks, dealer stands on soft 17, double after split, the dealer peeks, split
aces take one card, and no hand can be split again. Every value is post peek
and in units of the original wager. The shoe is a fresh six deck shoe minus the
pair and the upcard, so 309 unseen cards including the hidden hole.

The default value is `ev_split` from `bj/ev.py` under those rules. Each split
hand is valued against the shoe as it stood at the split, minus only its own
cards, and the two values are added.

The common shoe value is the model of `bj/joint_split.py`, which
`bj/common_shoe.py` names
`common_shoe_sequential_two_hand_no_resplit_binary_float_v1`. The first hand
plays out before the second takes its card. The second hand sees the first
hand's cards. Both hands settle against one dealer, and every choice is made on
the combined value of the round. The player never sees the hole card. That
reference refuses more than twenty unseen cards, so this study evaluates the
same model at full size with `tools/split_error_study.py`.

## The table

Each entry is the default value minus the common shoe value, in units of the
original wager, to three significant digits. A 0 means the two differ by no
more than 1e-12.

<!-- split-error-table:begin -->
| Pair | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | T | A |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A,A | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| T,T | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | −1.38e−5 | 0 |
| 9,9 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | −3.75e−5 | 0 |
| 8,8 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | −4.72e−5 | 0 |
| 7,7 | −1.37e−4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | −9.49e−5 | −2.89e−6 |
| 6,6 | −4.26e−5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | −8.66e−6 | −1.25e−6 |
| 5,5 | −2.16e−6 | 0 | 0 | 0 | −1.66e−9 | 0 | 0 | 0 | −5.45e−11 | −5.70e−6 |
| 4,4 | −5.97e−7 | 0 | 0 | 0 | −1.76e−9 | 0 | 0 | 0 | −1.25e−5 | −6.54e−6 |
| 3,3 | −6.70e−7 | 0 | −1.26e−10 | 0 | −1.78e−7 | 0 | 0 | 0 | −6.92e−5 | −1.47e−6 |
| 2,2 | −3.43e−5 | 0 | −5.39e−4 | −5.97e−6 | 0 | 0 | 0 | 0 | −8.60e−5 | −1.13e−5 |
<!-- split-error-table:end -->

Every gap larger than 1e-5 is against 2, 4, T or A. Every cell against 3, 7
and 8 is 0. Of the 73 cells shown as 0, 69 differ by at most 1.6e-15, which is
rounding. The other four are 2,2, 3,3, 4,4 and 5,5 against 9, with gaps from
1.6e-14 to 9.4e-13. That is far more than the rounding the next section
measures in the same cells, so I read them as real gains too small to matter.

## Why the default is never higher

The default's own choices are one way to play the common shoe round. Each hand
decides from its own cards and the shoe at the split, and ignores the other
hand. The common shoe player is free to play exactly that way, so the best
common shoe play is worth at least as much.

That way of playing also earns exactly the default value in the common shoe.
When a hand stops drawing, it has stopped on cards it has already seen, so it
cannot steer which cards stay behind. The chance that the next few cards form
any given sequence is a martingale as cards come out: given everything seen so
far, its expected next value is its current value. So its expected value at the
moment a hand stops equals its value before the hand began. The second hand
therefore meets, on average, the cards it would have met if the first hand had
never drawn. The dealer meets, on average, the cards it would have met if the
second hand had never drawn, so each hand's settlement averages out to what
that hand alone would have faced. This needs two things. A hand's choice to stop must
depend only on cards already seen, which is true of any legal play. The shoe
must not run out, which it cannot here.

The study checks that rather than assumes it. For every cell it plays the
default's choices through the common shoe evaluator and compares the result
with the default value. The largest difference across the 100 cells is 1.6e-15.
That is the size of rounding here, and it is also why some cells in the table
show the default above the common shoe value by up to 1.5e-15.

So the gap in the table is what the common shoe player gains, and nothing
else. The second hand can use the first hand's cards, and either hand can
choose with the other hand's settlement in mind. Where neither of those ever
changes a choice, the gap is zero.

## How the full shoe is computed

One split hand can end in a few thousand card multisets. For 2,2 that is 7,995
hand states and 8,050 first hand endings once doubles are counted. The second
hand plays the same tree after every one of them, so the evaluator solves the
second hand for all first hand endings at once with numpy arrays. The first
hand is then solved one shoe at a time on the combined values.

Every settlement needs the dealer's distribution for the shoe both hands leave
behind, and for 2,2 there are up to 614,501 of those shoes. The evaluator walks
the dealer's card multisets forward once for all of them together. The hole is
the first dealer card and is never the rank the peek ruled out.

The full study ran in 13 minutes in one process on a shared desktop
machine. That is a record of one run, not a speed claim.

## How it is checked

Four checks in `tests/test_split_error_study.py` hold this together.

1. On 120 random shoes of three to eleven cards, with random pairs, upcards,
   DAS settings and soft 17 rules, the evaluator matches `bj.joint_split`
   within 1e-12 in all 39 shoes the reference completes, and it refuses all 81
   shoes the reference refuses.
2. Its dealer pass matches `bj.dealer` within 1e-14 on a sample of six deck
   shoes for every upcard and both soft 17 rules.
3. The default's choices earn the default value in the common shoe for seven
   cells, including one without DAS and one with the dealer hitting soft 17.
4. The saved cells for A,A and T,T recompute, and this table and the README
   sentence follow from the saved results.

The slow set runs the script's check mode, which recomputes all 100 cells and
compares every value with the saved results.

```sh
python tools/split_error_study.py --check
python tools/split_error_study.py --output new-split-error-study.json
```

## What this does not show

This is one table, one deal order and two hands. The default table allows up
to four hands, and the derived chart and the whole game estimate use that
limit. Resplitting adds the shared slot approximation described in `bj/ev.py`,
and this study measures none of it. Other deck counts, H17, no DAS and
depleted shoes are not in the table. A table that deals both split cards
before the first decision is a different model.

The values are binary64, not rational arithmetic. The lower bound argument is
about the model, and the check above confirms it numerically to rounding. It
does not make the floating point values exact.
