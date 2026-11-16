# Resplitting on the six deck table

[Saved results](resplit-study-results.json) | [The script](../tools/resplit_study.py) | [The two hand study](split-error-study.md)

The default table allows up to four hands. The default solver values a split
there as independent hands that share one pool of extra hands. I measured that
value against plays that deal every hand from one shared shoe, in every pair and
upcard cell of the six deck table. The best play from one shared shoe is out of
reach at six decks, so the comparison is with a lower bound on it: the best of
three plays I can value exactly.

In 95 of the 100 cells the default is not above that bound by more than
rounding, which reaches 1.1e-16 here. In the other 5 cells it is above by at
most 0.000009505 units of the
original wager, for 6,6 against 2. There the default states slightly more than
its own resplitting earns from one shoe, and split stays the best action by at
least 0.0089 units. The largest gap the other way is 0.000094950 units, for 7,7
against T. No cell changes its best action under the bound.

## What is compared

The table is the solver's default: six decks, dealer stands on soft 17, double
after split, the dealer peeks, up to four hands, and split aces take one card
and are not resplit. Every value is post peek and in units of the original
wager. The shoe is a fresh six deck shoe minus the pair and the upcard, so 309
unseen cards including the hidden hole.

The default value is `ev_split` from `bj/ev.py`. Each split hand is valued
against the shoe at the split minus the pair cards resplits above it took. A
hand resplits when that raises its own value, and the second hand gets what the
first left of the pool.

From one shared shoe the hands are dealt in table order. A hand plays out
before the next takes a card, a resplit's two new hands come before any older
hand still waiting, and every hand settles against one dealer. The player
never sees the hole card.

## Why a lower bound

The best shared shoe play chooses each action with every card seen so far and
every earlier hand's total in mind. With two hands that already needed up to
614,501 dealer shoes for one cell in the two hand study, where a 2,2 hand can
end in 8,050 ways. With four hands the state holds the endings of three earlier
hands, so I expect it to be far past one machine at six decks. I did not
attempt it. Instead I valued three plays a player at this table can follow,
each exact to rounding.

1. The default's own play. Every hand decides from its own cards and the shoe
   the default gave it, and resplits when the default would.
2. The default's play for a table of three hands. It makes every resplit choice
   with a pool of one extra hand and never takes a fourth, which a player here
   may decline.
3. The two hand shared shoe value from the [two hand study](split-error-study.md).
   It never resplits and uses every card it has seen.

The best play is worth at least the largest of the three. In each of the 42
cells where the default resplits, the largest is its own play. In the other 58
the default never resplits, so its own play is its two hand play, and the two
hand value is at least as large. The three hand play is never larger than both
of the others.

## The table

Each entry is the default value minus the lower bound, in units of the original
wager, to three significant digits. A 0 means the two differ by no more than
1e-12. A positive entry means the default is above every value computed here.

<!-- resplit-table-bound:begin -->
| Pair | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | T | A |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A,A | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| T,T | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | −1.38e−5 | 0 |
| 9,9 | −8.03e−6 | −1.96e−5 | −2.31e−5 | −2.86e−5 | −2.79e−5 | 0 | −1.29e−5 | −1.10e−5 | −3.75e−5 | 0 |
| 8,8 | −3.52e−5 | −3.84e−5 | −5.03e−5 | −5.50e−5 | −6.50e−5 | −8.69e−5 | −4.92e−5 | −1.98e−5 | −7.76e−6 | −8.33e−6 |
| 7,7 | −9.96e−6 | −1.28e−5 | −1.77e−5 | −3.53e−5 | −4.46e−5 | −2.26e−5 | 0 | 0 | −9.49e−5 | −2.89e−6 |
| 6,6 | 9.50e−6 | 3.50e−6 | −7.93e−6 | −1.46e−5 | −2.89e−5 | 0 | 0 | 0 | −8.66e−6 | −1.25e−6 |
| 5,5 | −2.16e−6 | 0 | 0 | 0 | −1.66e−9 | 0 | 0 | 0 | −5.45e−11 | −5.70e−6 |
| 4,4 | −5.97e−7 | 0 | 0 | 5.52e−6 | 4.15e−6 | 0 | 0 | 0 | −1.25e−5 | −6.54e−6 |
| 3,3 | 3.29e−6 | −2.54e−6 | −5.38e−6 | −1.01e−5 | −1.36e−5 | −1.12e−6 | 0 | 0 | −6.92e−5 | −1.47e−6 |
| 2,2 | −1.87e−6 | −6.33e−6 | −1.10e−5 | −1.32e−5 | −1.71e−5 | −7.66e−6 | 0 | 0 | −8.60e−5 | −1.13e−5 |
<!-- resplit-table-bound:end -->

In 41 of the 100 cells the default and the bound agree within 1e-12. Where the
default never resplits, the cell repeats the two hand study's gap, because the
default's play there is its two hand play. That covers A,A, since split aces
are not resplit on this table, and cells such as 7,7 against T where splitting
is not the best action.

## What the default's own resplitting earns

Each entry is the default's own play dealt from one shared shoe minus the
default value. A positive entry means the play earns more than the default
says.

<!-- resplit-table-own-play:begin -->
| Pair | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | T | A |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A,A | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| T,T | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 9,9 | 8.03e−6 | 1.96e−5 | 2.31e−5 | 2.86e−5 | 2.79e−5 | 0 | 1.29e−5 | 1.10e−5 | 0 | 0 |
| 8,8 | 3.52e−5 | 3.84e−5 | 5.03e−5 | 5.50e−5 | 6.50e−5 | 8.69e−5 | 4.92e−5 | 1.98e−5 | 7.76e−6 | 8.33e−6 |
| 7,7 | 9.96e−6 | 1.28e−5 | 1.77e−5 | 3.53e−5 | 4.46e−5 | 2.26e−5 | 0 | 0 | 0 | 0 |
| 6,6 | −9.50e−6 | −3.50e−6 | 7.93e−6 | 1.46e−5 | 2.89e−5 | 0 | 0 | 0 | 0 | 0 |
| 5,5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 4,4 | 0 | 0 | 0 | −5.52e−6 | −4.15e−6 | 0 | 0 | 0 | 0 | 0 |
| 3,3 | −3.29e−6 | 2.54e−6 | 5.38e−6 | 1.01e−5 | 1.36e−5 | 1.12e−6 | 0 | 0 | 0 | 0 |
| 2,2 | 1.87e−6 | 6.33e−6 | 1.10e−5 | 1.32e−5 | 1.71e−5 | 7.66e−6 | 0 | 0 | 0 | 0 |
<!-- resplit-table-own-play:end -->

In 37 of the 100 cells the default's own play earns more from one shoe than the
default says, by up to 0.000086885 units for 8,8 against 7. In 5 cells it earns
less, by up to 0.000009505 units for 6,6 against 2. In every other cell the two
agree to rounding. Those are the cells where the default never resplits, and
the two hand study shows why they must agree there.

Part of the difference comes from the pool. The default prices the second
hand's chance to pair as if the first hand had taken no pair cards. From one
shoe the two are linked. When the first hand does not resplit, its first card
was not a pair card, so the second hand is a little more likely to pair while
the whole pool is still there. When the first hand does resplit, it has taken
pair cards out, so the second hand is less likely to pair just when fewer
slots remain. In every cell where the default resplits, its play from one shoe
reaches more hands on average than the default counts, 2.159954 against
2.159815 for 8,8 against 7. The other part is that each hand settles in a shoe
the earlier hands have changed. I have not separated the two, so I cannot say
which one turns the 5 cells the other way.

## How the shared shoe value is computed

Suppose every split hand took its first card before any hand played on. Every
complete deal, meaning the cards each hand and the dealer end with, can happen
in that order and in table order, with the same probability, because a deal's
probability depends only on which cards left the shoe. So both orders give the
same value.

In the reordered deal a hand that plays on meets, on average, the shoe as it
stood right after its own first card. A hand that decides from its own cards
cannot steer which cards stay behind, which is the argument the two hand study
uses for its dealer. So the value needs only the first cards. The chance of a
first card that is not a pair card is the chance of any card less the chance of
a pair card, and any card drops out by the same averaging. What is left is
single hands played in shoes that differ only in how many pair cards are gone.

Each hand decides from the shoe the default gave it and settles in the shoe the
shared deal leaves, so the script plays the default's choices through a second
shoe rather than recomputing them. The full study ran in 78 seconds in one
process on a shared desktop machine. That is a record of one run, not a speed
claim.

## How it is checked

Five checks in `tests/test_resplit_study.py` hold this together.

1. A deal by deal enumeration plays the default's choices card by card from one
   shoe and settles every hand against the final shoe. On 16 small shoes, with
   three and four hands, and with S17 and DAS and again with H17 and no DAS, it
   agrees with the shortcut within 1e-12. The largest difference on this run
   was 4.4e-16. The shoes include a ten and an ace up with resplitting, and T,T
   against an ace, where the pair is the rank the peek rules out. In 14 of the
   16 four hands reach further than three on average, so the second resplit is
   tested too. No deal on those shoes can run out of cards, and the
   enumeration fails if one does.
2. On 10 of those shoes, each with a resplit the default takes, the play never
   beats the bounded three hand optimum in `bj/joint_resplit.py` by more than
   1e-12, with DAS on and off. On this run it was never above by more than
   1.1e-16, and it equals the optimum on some shoes.
3. Rebuilding the default value from the choices the script reads off matches
   `ev_split` within 5.6e-17 in all 100 cells, so the play is the default's.
4. With two hands the shortcut gives back the default value, which is the two
   hand study's own check.
5. The saved tables and the numbers in this page and the README follow from the
   saved cells.

The slow set runs the script's check mode. It recomputes all 100 cells,
compares every value with the saved results and confirms the two hand results
it reads have not changed.

```sh
python tools/resplit_study.py --check
python tools/resplit_study.py --output new-resplit-study.json
```

## The dealer hitting soft 17, and no double after split

I ran the same comparison on two more tables, changing one rule at a time. One
has the dealer hit soft 17, the other allows no double after split. Each table
reads its own two hand results as the third play in the bound, and each has its
own saved file: [H17](resplit-study-h17-results.json) and
[no DAS](resplit-study-no-das-results.json). The shoe, the four hand limit and
the method are the same.

```sh
python tools/resplit_study.py --table h17 --check
python tools/resplit_study.py --table no-das --check
```

### H17

In 95 of the 100 cells the default is not above the bound by more than
rounding, which reaches 1.1e-16 here. In the other 5 cells it is above by at
most 0.000008657 units, for 6,6 against 2, and split stays the best action by
at least 0.0098 units. The largest gap the other way is 0.000094950 units, for
7,7 against T. No cell changes its best action under the bound. Where split is
not the best action, the closest call is 3,3 against 8, where split trails by
0.0106 units. The default and the bound agree within 1e-12 in 44 cells, and the
default resplits in 42. The own play earns more than the default says in 37
cells, by up to 0.000086885 units for 8,8 against 7, and less in 5 cells. The
run took 83 seconds.

The first table is the default value minus the lower bound. The second is the
default's own play minus the default value.

<!-- resplit-table-h17-bound:begin -->
| Pair | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | T | A |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A,A | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| T,T | 0 | 0 | −8.38e−5 | 0 | 0 | 0 | 0 | 0 | −1.38e−5 | 0 |
| 9,9 | −8.85e−6 | −2.04e−5 | −2.39e−5 | −2.90e−5 | −3.33e−5 | 0 | −1.29e−5 | −1.10e−5 | −3.75e−5 | 0 |
| 8,8 | −3.38e−5 | −3.66e−5 | −4.93e−5 | −5.45e−5 | −5.82e−5 | −8.69e−5 | −4.92e−5 | −1.98e−5 | −7.76e−6 | 4.79e−6 |
| 7,7 | −9.33e−6 | −1.17e−5 | −1.73e−5 | −3.50e−5 | −4.17e−5 | −2.26e−5 | 0 | 0 | −9.49e−5 | 0 |
| 6,6 | 8.66e−6 | 2.75e−6 | −8.06e−6 | −1.46e−5 | −2.95e−5 | 0 | 0 | 0 | −8.66e−6 | 0 |
| 5,5 | −1.62e−6 | −8.34e−8 | 0 | 0 | −1.71e−9 | 0 | 0 | 0 | −5.45e−11 | 0 |
| 4,4 | −5.57e−7 | −8.13e−7 | 0 | 5.23e−6 | −6.41e−8 | 0 | 0 | 0 | −1.25e−5 | 0 |
| 3,3 | 3.21e−6 | −2.65e−6 | −5.51e−6 | −1.02e−5 | −1.46e−5 | −1.12e−6 | 0 | 0 | −6.92e−5 | 0 |
| 2,2 | −1.59e−6 | −6.07e−6 | −1.12e−5 | −1.33e−5 | −1.83e−5 | −7.66e−6 | 0 | 0 | −8.60e−5 | 0 |
<!-- resplit-table-h17-bound:end -->

<!-- resplit-table-h17-own-play:begin -->
| Pair | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | T | A |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A,A | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| T,T | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 9,9 | 8.85e−6 | 2.04e−5 | 2.39e−5 | 2.90e−5 | 3.33e−5 | 0 | 1.29e−5 | 1.10e−5 | 0 | 0 |
| 8,8 | 3.38e−5 | 3.66e−5 | 4.93e−5 | 5.45e−5 | 5.82e−5 | 8.69e−5 | 4.92e−5 | 1.98e−5 | 7.76e−6 | −4.79e−6 |
| 7,7 | 9.33e−6 | 1.17e−5 | 1.73e−5 | 3.50e−5 | 4.17e−5 | 2.26e−5 | 0 | 0 | 0 | 0 |
| 6,6 | −8.66e−6 | −2.75e−6 | 8.06e−6 | 1.46e−5 | 2.95e−5 | 0 | 0 | 0 | 0 | 0 |
| 5,5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 4,4 | 0 | 0 | 0 | −5.23e−6 | 6.41e−8 | 0 | 0 | 0 | 0 | 0 |
| 3,3 | −3.21e−6 | 2.65e−6 | 5.51e−6 | 1.02e−5 | 1.46e−5 | 1.12e−6 | 0 | 0 | 0 | 0 |
| 2,2 | 1.59e−6 | 6.07e−6 | 1.12e−5 | 1.33e−5 | 1.83e−5 | 7.66e−6 | 0 | 0 | 0 | 0 |
<!-- resplit-table-h17-own-play:end -->

### No double after split

In 95 of the 100 cells the default is not above the bound by more than
rounding, which reaches 1.1e-16 here. In the other 5 cells it is above by at
most 0.000009928 units, for 6,6 against 3, and split stays the best action by
at least 0.0111 units. The largest gap the other way is 0.000094955 units, for
7,7 against T. No cell changes its best action under the bound. Where split is
not the best action, the closest call is 2,2 against 3, where split trails by
0.0124 units. The default and the bound agree within 1e-12 in 51 cells, and the
default resplits in 35. The own play earns more than the default says in 30
cells, by up to 0.000078700 units for 8,8 against 7, and less in 5 cells. The
run took 75 seconds.

<!-- resplit-table-no-das-bound:begin -->
| Pair | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | T | A |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A,A | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| T,T | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | −1.38e−5 | 0 |
| 9,9 | −3.49e−6 | −1.35e−5 | −1.64e−5 | −2.14e−5 | −2.02e−5 | 0 | −9.66e−6 | −9.11e−6 | −4.16e−5 | 0 |
| 8,8 | −2.77e−5 | −3.03e−5 | −3.90e−5 | −4.24e−5 | −5.15e−5 | −7.87e−5 | −4.37e−5 | −1.83e−5 | −6.94e−6 | −8.33e−6 |
| 7,7 | −4.45e−6 | −6.61e−6 | −9.26e−6 | −2.01e−5 | −2.76e−5 | −1.62e−5 | 0 | 0 | −9.50e−5 | −2.88e−6 |
| 6,6 | 0 | 9.93e−6 | 1.98e−7 | −4.28e−6 | −1.34e−5 | 0 | 0 | 0 | −1.53e−5 | −2.65e−8 |
| 5,5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | −8.17e−11 | −3.88e−6 |
| 4,4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | −1.26e−5 | −6.39e−6 |
| 3,3 | 0 | 0 | 4.72e−6 | 7.14e−7 | −1.29e−6 | 2.32e−6 | 0 | 0 | −6.98e−5 | −1.46e−6 |
| 2,2 | 0 | 0 | −7.10e−7 | −2.90e−6 | −5.25e−6 | −3.84e−6 | 0 | 0 | −8.98e−5 | −1.13e−5 |
<!-- resplit-table-no-das-bound:end -->

<!-- resplit-table-no-das-own-play:begin -->
| Pair | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | T | A |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A,A | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| T,T | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 9,9 | 3.49e−6 | 1.35e−5 | 1.64e−5 | 2.14e−5 | 2.02e−5 | 0 | 9.66e−6 | 9.11e−6 | 0 | 0 |
| 8,8 | 2.77e−5 | 3.03e−5 | 3.90e−5 | 4.24e−5 | 5.15e−5 | 7.87e−5 | 4.37e−5 | 1.83e−5 | 6.94e−6 | 8.33e−6 |
| 7,7 | 4.45e−6 | 6.61e−6 | 9.26e−6 | 2.01e−5 | 2.76e−5 | 1.62e−5 | 0 | 0 | 0 | 0 |
| 6,6 | 0 | −9.93e−6 | −1.98e−7 | 4.28e−6 | 1.34e−5 | 0 | 0 | 0 | 0 | 0 |
| 5,5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 4,4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 3,3 | 0 | 0 | −4.72e−6 | −7.14e−7 | 1.29e−6 | −2.32e−6 | 0 | 0 | 0 | 0 |
| 2,2 | 0 | 0 | 7.10e−7 | 2.90e−6 | 5.25e−6 | 3.84e−6 | 0 | 0 | 0 | 0 |
<!-- resplit-table-no-das-own-play:end -->

Both tables agree with the default table on the main point. Where the default
resplits it holds none of the shared shoe gain, and a better shared shoe play
would have to gain more than the closest call above to change a best action.
Two things in the H17 table are new. T,T against 4 is 0.0000838 units below the
bound, where the default table shows no gap for it, and 8,8 against an ace is
above the bound by 0.0000048 units. Against a dealer 7, 8, 9 or T a soft 17
cannot come up, and the H17 cells there equal the default table's exactly.

## What this does not show

The bound is not the best shared shoe play. The real gap can be larger in every
cell, and in the 5 cells where the default is above the bound its sign is open.
Where split is not the best action, the closest call is 3,3 against 8, where
split trails by 0.0106 units. A better shared shoe play would have to gain that
much over these values for a best action to change. The largest gain the two
hand study found for using the shared shoe was 0.000538738 units.

These are three tables. The dealer hitting soft 17 together with no double after
split, other deck counts, resplitting aces, hitting split aces and depleted
shoes are not in them.
The values are binary64, not rational arithmetic. The shortcut also needs a
shoe that cannot run out, which a six deck shoe cannot.
