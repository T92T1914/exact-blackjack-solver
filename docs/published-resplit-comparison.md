# Against a published resplit table

[The comparison](published-resplit-comparison.json) | [The transcribed values](published-resplit-paper-values.json) | [The tool](../tools/published_resplit_comparison.py)

Nairn's "Exact and approximate pair splitting values for blackjack"
([arXiv:1909.13710](https://arxiv.org/abs/1909.13710)) lists splitting values
for a single deck where the dealer stands on soft 17, once with no resplitting
and once with resplitting to four hands, with doubling after a split on any two
cards. The one deck tables of the [split error study](split-error-study.md) and
the [resplit study](resplit-study.md) use the same rules, so I set them side by
side in every cell both state. The published values are
[Table 1](https://arxiv.org/pdf/1909.13710) for dealer up cards A to 5 and
Table 2 for 6 to T. Each compared cell in the saved file names its table.

## What is compared

Both sides are one deck, S17, doubling after a split on any two cards, a dealer
who peeks, a maximum of four hands for the resplit row and no resplitting of
aces. The comparison covers dealer up cards 2 to 9, which is 80 cells with no
resplit and 71 with resplit.

It leaves out dealer up cards A and T, because the published values assume the
dealer has no natural and the table here includes it. It leaves out the resplit
row of A,A, because the paper resplits aces and this table does not. It leaves
out one cell, 8,8 against 8 with resplitting, because Table 2 prints that
value as `-59524.5`, which I cannot read as a value.

I read the published values from the PDF text with a one off script that I did
not keep, not from the page images. While reading, the script checked that every
hand has ten lines of two values, and that the two columns of the A,A and T,T
no resplit rows are equal, as the paper says they must be. The tests here check
only the shape of the saved transcription. I did not check any value against
the printed page, so a mistyped value would pass every check in this repository.

## What differs

The published strategy is a fixed basic strategy. This repository's values are
the default's own choices, which look at the cards left in the shoe. So these
are two exact values of different plays, and a difference is not an error in
either one. The published value is subtracted from this repository's value, and
the table uses the default's own choices dealt from one shared shoe, which is
how the paper deals the cards.

| Cells | Count | Mean absolute difference | Largest | Cell |
| --- | --- | --- | --- | --- |
| No resplit | 80 | 0.00068 | 0.00886 | 2,2 v 6 |
| Resplit, published value at least its no resplit value | 43 | 0.00082 | 0.01065 | 2,2 v 6 |
| Resplit, published value below its no resplit value | 28 | 0.09376 | 0.43958 | T,T v 9 |

The first two rows agree to about a thousandth on average, with the value here
above the published one in some cells and below it in others, 58 above and 22
below with no resplit.

The third row does not agree, and the reason is in the published table. In those
28 cells the paper's resplit value is below its own no resplit value, so its
resplit row looks like a play that resplits every time, which can lose to not
resplitting. The default here may decline, so it cannot be worse than not
resplitting. Set against the published no resplit value instead, the same 28
cells differ by 0.00092 on average and by at most 0.00577. So I read the third
row as a difference in the rule being valued, not as a gap to close. I did not
confirm that reading in the paper's text, which does not say it in these words.

## What it does not show

This does not show that either table is right. The values here are the
default's, so they sit below the best play wherever the default is not the best.
The resplit bound is a lower bound. The comparison covers one deck only, because
the paper's tables do. Its multiple deck results are approximate, and I did not
set them against anything.

```sh
python tools/published_resplit_comparison.py --check
```

The check reads the two saved studies and the transcribed values, so it runs in
a few seconds and is part of the ordinary tests.
