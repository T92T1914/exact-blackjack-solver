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

## Two rule variants

The same study ran three more times, with the rules of the table changed and
everything else as above. One run has the dealer hit soft 17. One allows no
double after split. The third makes both changes together. Each has its own
saved results file, and each is recomputed by its own check mode.

```sh
python tools/split_error_study.py --table h17 --check
python tools/split_error_study.py --table no-das --check
python tools/split_error_study.py --table h17-no-das --check
```

Entries mean the same as in the first table.

### Dealer hits soft 17

[Saved results](split-error-study-h17-results.json). The default is never above
the common shoe value by more than 1.2e-15. The largest gap is 0.0000949498
units for 7,7 against T, smaller than the 0.000538738 of the first table. In 73 of the 100 cells the two values are within 1e-12, and no cell
changes its best action. Playing the default's choices through the common shoe
gives the default value to 1.9e-15 in every cell.

<!-- split-error-table-h17:begin -->
| Pair | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | T | A |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A,A | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| T,T | 0 | 0 | −8.38e−5 | 0 | 0 | 0 | 0 | 0 | −1.38e−5 | 0 |
| 9,9 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | −3.75e−5 | 0 |
| 8,8 | 0 | −7.34e−8 | 0 | 0 | 0 | 0 | 0 | 0 | −4.72e−5 | 0 |
| 7,7 | −1.88e−5 | −2.05e−8 | 0 | 0 | 0 | 0 | 0 | 0 | −9.49e−5 | 0 |
| 6,6 | −4.17e−5 | −4.67e−8 | 0 | 0 | 0 | 0 | 0 | 0 | −8.66e−6 | 0 |
| 5,5 | −1.62e−6 | −8.34e−8 | 0 | 0 | −1.71e−9 | 0 | 0 | 0 | −5.45e−11 | 0 |
| 4,4 | −5.57e−7 | −8.13e−7 | 0 | 0 | −8.09e−9 | 0 | 0 | 0 | −1.25e−5 | 0 |
| 3,3 | −5.27e−7 | 0 | −1.08e−9 | 0 | −2.07e−7 | 0 | 0 | 0 | −6.92e−5 | 0 |
| 2,2 | −3.06e−5 | −3.52e−10 | 0 | −2.45e−6 | 0 | 0 | 0 | 0 | −8.60e−5 | 0 |
<!-- split-error-table-h17:end -->

Of the 73 cells shown as 0, 68 differ by at most 1.6e-15. T,T against 2 differs
by 1.7e-15, and 2,2 to 5,5 against 9 differ by 1.6e-14 to 9.4e-13.

### No double after split

[Saved results](split-error-study-no-das-results.json). The default is never
above the common shoe value by more than 1.4e-15. The largest gap is 0.000541544
units for 2,2 against 4, close to the 0.000538738 of the first table. In 84 of
the 100 cells the two values are within 1e-12, and no cell changes its best
action. Playing the default's choices through the common shoe gives the default
value to 1.6e-15 in every cell.

<!-- split-error-table-no-das:begin -->
| Pair | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | T | A |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A,A | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| T,T | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | −1.38e−5 | 0 |
| 9,9 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | −4.16e−5 | 0 |
| 8,8 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | −4.84e−5 | 0 |
| 7,7 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | −9.50e−5 | −2.88e−6 |
| 6,6 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | −1.53e−5 | −2.65e−8 |
| 5,5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | −8.17e−11 | −3.88e−6 |
| 4,4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | −1.26e−5 | −6.39e−6 |
| 3,3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | −6.98e−5 | −1.46e−6 |
| 2,2 | 0 | 0 | −5.42e−4 | 0 | 0 | 0 | 0 | 0 | −8.98e−5 | −1.13e−5 |
<!-- split-error-table-no-das:end -->

Of the 84 cells shown as 0, 80 differ by at most 1.6e-15. The other four are
2,2 to 5,5 against 9, with gaps from 1.6e-14 to 9.4e-13.

### Both changes

[Saved results](split-error-study-h17-no-das-results.json). This run has the
dealer hit soft 17 and allows no double after split, the two changes together.
The default is never above the common shoe value by more than 1.2e-15. The
largest gap is 0.0000949549 units for 7,7 against T, the same cell as in the
H17 table and nearly the same size. In 84 of the 100 cells the two values are
within 1e-12, and no cell changes its best action. Playing the default's
choices through the common shoe gives the default value to 1.7e-15 in every
cell.

<!-- split-error-table-h17-no-das:begin -->
| Pair | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | T | A |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A,A | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| T,T | 0 | 0 | −8.38e−5 | 0 | 0 | 0 | 0 | 0 | −1.38e−5 | 0 |
| 9,9 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | −4.16e−5 | 0 |
| 8,8 | 0 | −7.34e−8 | 0 | 0 | 0 | 0 | 0 | 0 | −4.84e−5 | 0 |
| 7,7 | 0 | −6.73e−8 | 0 | 0 | 0 | 0 | 0 | 0 | −9.50e−5 | 0 |
| 6,6 | 0 | −1.67e−7 | 0 | 0 | 0 | 0 | 0 | 0 | −1.53e−5 | 0 |
| 5,5 | 0 | −1.49e−7 | 0 | 0 | 0 | 0 | 0 | 0 | −8.17e−11 | 0 |
| 4,4 | 0 | −9.61e−7 | 0 | 0 | 0 | 0 | 0 | 0 | −1.26e−5 | 0 |
| 3,3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | −6.98e−5 | 0 |
| 2,2 | 0 | −3.52e−10 | 0 | 0 | 0 | 0 | 0 | 0 | −8.98e−5 | 0 |
<!-- split-error-table-h17-no-das:end -->

Of the 84 cells shown as 0, 78 differ by at most 1.6e-15. T,T and 5,5 against 2
differ by 1.7e-15, and 2,2 to 5,5 against 9 differ by 1.6e-14 to 9.4e-13.

## Other deck counts

The same study ran with one, two, four and eight decks, the default rules and the hand limit of two otherwise unchanged. The six deck table is the one above. Each run has its own saved results file and its own check mode.

```sh
python tools/split_error_study.py --table decks-1 --check
python tools/split_error_study.py --table decks-2 --check
python tools/split_error_study.py --table decks-4 --check
python tools/split_error_study.py --table decks-8 --check
```

Entries mean the same as in the first table. The shoe is a fresh shoe of that many decks minus the pair and the upcard.

### One deck

[Saved results](split-error-study-decks-1-results.json). The default is never above the common shoe value by more than 1.3e-15. The largest gap is 0.004040552 units for 3,3 against 2. In 18 of the 100 cells the two values are within 1e-12, and no cell changes its best action. Playing the default's choices through the common shoe gives the default value to 2.3e-15 in every cell. The run took 250 seconds.

<!-- split-error-table-decks-1:begin -->
| Pair | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | T | A |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A,A | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| T,T | −2.14e−6 | −4.66e−4 | −2.66e−6 | −2.75e−4 | −1.83e−6 | −4.38e−5 | −1.15e−5 | −6.34e−5 | −1.17e−4 | 0 |
| 9,9 | −1.47e−3 | −9.62e−4 | 0 | 0 | 0 | −7.56e−7 | −3.61e−5 | −1.23e−4 | −3.26e−4 | −8.15e−4 |
| 8,8 | −8.28e−4 | −6.51e−6 | −6.36e−5 | −7.21e−4 | −8.66e−4 | −1.77e−6 | −9.63e−6 | −9.80e−5 | −4.76e−4 | −1.18e−4 |
| 7,7 | −9.41e−4 | −1.47e−5 | 0 | 0 | 0 | −4.76e−4 | −1.04e−5 | −1.26e−5 | −1.17e−3 | −7.31e−4 |
| 6,6 | −3.83e−4 | −2.79e−6 | −1.35e−4 | 0 | −5.65e−4 | −6.80e−4 | −1.69e−5 | −1.63e−4 | −8.89e−4 | −1.34e−3 |
| 5,5 | −8.14e−4 | −9.16e−5 | −3.61e−4 | −1.43e−7 | −7.79e−8 | −1.27e−3 | −3.40e−4 | −3.52e−4 | −8.88e−4 | −5.43e−4 |
| 4,4 | −9.16e−4 | −1.94e−4 | −4.83e−5 | −1.27e−5 | −1.09e−5 | −1.35e−3 | −4.62e−4 | −3.56e−4 | −2.55e−4 | −9.32e−4 |
| 3,3 | −4.04e−3 | −2.27e−3 | −2.83e−4 | −1.52e−5 | −1.33e−5 | −1.58e−3 | −7.09e−4 | −5.24e−4 | −6.55e−4 | −6.97e−4 |
| 2,2 | −9.42e−4 | −7.69e−4 | −2.23e−3 | −1.39e−4 | −2.49e−3 | −1.46e−3 | −4.34e−4 | −9.53e−4 | −6.97e−4 | −7.25e−4 |
<!-- split-error-table-decks-1:end -->

Of the 18 cells shown as 0, 18 differ by at most 1.6e-15.

### Two decks

[Saved results](split-error-study-decks-2-results.json). The default is never above the common shoe value by more than 1.3e-15. The largest gap is 0.001357668 units for 3,3 against 2. In 28 of the 100 cells the two values are within 1e-12, and no cell changes its best action. Playing the default's choices through the common shoe gives the default value to 1.7e-15 in every cell. The run took 656 seconds.

<!-- split-error-table-decks-2:begin -->
| Pair | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | T | A |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A,A | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| T,T | −1.13e−4 | 0 | 0 | −8.36e−5 | −7.52e−5 | −1.51e−8 | 0 | −1.91e−7 | −4.96e−5 | 0 |
| 9,9 | −3.01e−4 | −1.15e−4 | 0 | 0 | 0 | −4.15e−12 | −1.86e−8 | −4.44e−6 | −1.31e−4 | −2.14e−4 |
| 8,8 | 0 | −2.32e−4 | 0 | −2.73e−5 | −1.90e−4 | −1.40e−10 | 0 | −1.20e−5 | −1.49e−4 | −5.22e−4 |
| 7,7 | −2.39e−4 | −2.78e−4 | 0 | 0 | 0 | −1.93e−6 | −1.84e−11 | −9.61e−8 | −3.69e−4 | −2.31e−4 |
| 6,6 | −7.66e−5 | −2.38e−4 | 0 | −1.26e−5 | −6.64e−5 | −6.95e−6 | −8.70e−9 | −2.24e−7 | −6.55e−5 | −3.95e−5 |
| 5,5 | −3.21e−5 | −4.16e−4 | 0 | −9.25e−5 | 0 | −5.46e−5 | −1.97e−5 | −1.98e−4 | −1.79e−5 | −4.85e−5 |
| 4,4 | −1.63e−4 | −4.91e−4 | 0 | −4.24e−5 | −9.73e−5 | −9.80e−5 | −2.43e−5 | −1.77e−4 | −3.53e−5 | −1.67e−4 |
| 3,3 | −1.36e−3 | −2.31e−4 | −1.07e−5 | −7.83e−5 | 0 | −6.89e−5 | −3.24e−5 | −7.16e−5 | −1.73e−4 | −3.47e−4 |
| 2,2 | −1.97e−4 | −1.33e−4 | −1.08e−3 | −2.73e−5 | −2.03e−4 | −6.90e−5 | −1.52e−5 | −7.22e−5 | −2.28e−4 | −6.26e−4 |
<!-- split-error-table-decks-2:end -->

Of the 28 cells shown as 0, 27 differ by at most 1.6e-15.

### Four decks

[Saved results](split-error-study-decks-4-results.json). The default is never above the common shoe value by more than 3.1e-15. The largest gap is 0.000656128 units for 2,2 against 4. In 49 of the 100 cells the two values are within 1e-12, and no cell changes its best action. Playing the default's choices through the common shoe gives the default value to 3.1e-15 in every cell. The run took 762 seconds.

<!-- split-error-table-decks-4:begin -->
| Pair | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | T | A |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A,A | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| T,T | −7.83e−5 | 0 | 0 | 0 | −1.44e−5 | 0 | 0 | 0 | −2.28e−5 | 0 |
| 9,9 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | −5.91e−5 | −9.27e−9 |
| 8,8 | 0 | −5.19e−7 | 0 | 0 | −5.93e−6 | 0 | 0 | 0 | −7.42e−5 | −3.35e−6 |
| 7,7 | −2.46e−4 | −7.25e−7 | 0 | 0 | 0 | 0 | 0 | 0 | −1.54e−4 | −8.70e−5 |
| 6,6 | −2.42e−4 | −1.34e−6 | 0 | 0 | 0 | 0 | 0 | 0 | −1.44e−5 | −2.16e−4 |
| 5,5 | −1.40e−4 | −1.75e−6 | 0 | 0 | −2.69e−5 | −1.62e−9 | −7.01e−10 | −1.39e−6 | 0 | −2.23e−4 |
| 4,4 | −8.26e−5 | −3.15e−6 | 0 | 0 | −1.27e−5 | −1.29e−8 | −1.81e−9 | −1.69e−6 | −1.66e−5 | −1.06e−4 |
| 3,3 | −8.02e−5 | −4.60e−9 | −6.31e−6 | 0 | −3.71e−5 | −1.25e−8 | −1.06e−8 | −5.29e−7 | −9.49e−5 | −4.41e−5 |
| 2,2 | −1.40e−4 | −1.59e−8 | −6.56e−4 | −6.54e−7 | −3.87e−6 | −1.01e−8 | −2.17e−9 | −4.50e−7 | −1.21e−4 | −2.27e−5 |
<!-- split-error-table-decks-4:end -->

Of the 49 cells shown as 0, 45 differ by at most 1.6e-15.

### Eight decks

[Saved results](split-error-study-decks-8-results.json). The default is never above the common shoe value by more than 2.6e-15. The largest gap is 0.000360496 units for 2,2 against 4. In 77 of the 100 cells the two values are within 1e-12, and no cell changes its best action. Playing the default's choices through the common shoe gives the default value to 2.6e-15 in every cell. The run took 764 seconds.

<!-- split-error-table-decks-8:begin -->
| Pair | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | T | A |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A,A | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| T,T | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | −9.37e−6 | 0 |
| 9,9 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | −2.73e−5 | 0 |
| 8,8 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | −3.37e−5 | 0 |
| 7,7 | −8.38e−5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | −6.64e−5 | −3.73e−7 |
| 6,6 | −5.96e−6 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | −5.87e−6 | −3.65e−9 |
| 5,5 | −8.91e−10 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | −7.90e−9 | −6.77e−7 |
| 4,4 | −5.43e−10 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | −1.05e−5 | −1.27e−6 |
| 3,3 | −3.59e−10 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | −5.65e−5 | −7.86e−6 |
| 2,2 | −1.77e−7 | 0 | −3.60e−4 | −1.82e−5 | 0 | 0 | 0 | 0 | −6.78e−5 | −2.93e−6 |
<!-- split-error-table-decks-8:end -->

Of the 77 cells shown as 0, 74 differ by at most 1.6e-15.

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
machine. The H17 and no DAS runs took 14 and 13 minutes the same way, and the run with
both changes took 13. Those are records of single runs, not a speed claim.

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

This is eight tables, one deal order and two hands. The default table allows up
to four hands, and the derived chart and the whole game estimate use that
limit. Resplitting adds the shared slot approximation described in `bj/ev.py`,
and this study measures none of it. The [resplit study](resplit-study.md)
compares the default with a lower bound on the shared shoe value when the
table allows four hands. Other rule changes, resplit aces, hit split aces, deck counts other than 1, 2, 4,
6 and 8, and depleted shoes are not in the study. A table that deals both split cards
before the first decision is a different model.

The values are binary64, not rational arithmetic. The lower bound argument is
about the model, and the check above confirms it numerically to rounding. It
does not make the floating point values exact.
