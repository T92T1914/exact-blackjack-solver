# exact-blackjack-solver

[![CI](https://github.com/T92T1914/exact-blackjack-solver/actions/workflows/ci.yml/badge.svg)](https://github.com/T92T1914/exact-blackjack-solver/actions/workflows/ci.yml)

An exact, composition-dependent blackjack solver: for any hand against any
dealer upcard, it computes the true expected value of hit, stand, double, and
split by enumerating every reachable continuation, weighted by the exact
composition of the remaining shoe. No lookup tables, no simulation, no
training — re-running gives bit-identical results.

Extracted and generalized from a larger private project: a read-only advisory
overlay I built for a friends' fake-currency blackjack game, which advised one
decision per hand and scored how closely the player followed it. This repo is
the algorithmic core of that system — the solver, its dealer model, and its
verification harness — with a self-contained CLI and test suite, no network and
no game attached, so every number here is runnable on any machine with Python
3.11+.

Two things this is **not**, stated up front because both would be easy to
assume and both are wrong:

- **There is no machine learning here.** No training set, no weights, no
  fitting. The strategy comes from exact enumeration — a recursive solver that
  walks every reachable continuation of a hand against every dealer hole card,
  weighted by the exact composition of the remaining shoe and memoised on an
  immutable shoe tuple.
- **It is not game theory.** The dealer does not respond to anything; it follows
  a published rule. There is no opponent model, no equilibrium, nothing
  adversarial. It is a single-agent finite-horizon **Markov decision process
  solved exactly by dynamic programming.**

## Why composition-dependent, and why it is not a table

Most blackjack "basic strategy" is a fixed chart: 16 vs 10 → hit, always. That
chart is an average over a full shoe. It is very nearly right and slightly
wrong, because the right move depends on the exact cards left. This solver never
consults a chart — it prices each action against the actual remaining shoe, so
its advice shifts, correctly, as cards are removed. The chart is what you get if
you ask it about a fresh shoe; the point is that it does not have to.

The interesting cases are the ones where the decision barely matters and the
solver says so. Hard 16 versus a dealer ten is the textbook "always hit," and
here it is — but by a **margin of +0.0063**, a coin flip the solver refuses to
dress up as a firm rule. Soft 18 versus a 3 flips the other way: **double**, at
+0.1793, a real edge worth acting on. The margin — best EV minus the next-best
*available* action — is the honest measure of how much a decision is worth, and
the tool prints it next to every recommendation.

## What's in the box

```
bj/
  core.py       ranks, hands, the immutable shoe, the Rules dataclass
  dealer.py     exact dealer outcome distribution (peek + hole-card modeled)
  ev.py         the solver: stand / hit / double / split EV by enumeration
  strategy.py   total-dependent basic strategy derived from the solver
  simulate.py   a Monte-Carlo harness that re-derives the same numbers
demo.py         advise one hand, ranked, with the EV of every action
tests/          the four test modules below
```

`ev.py` is the core. `dealer.py` computes, for a given upcard and shoe, the
exact distribution over the dealer's final total — including the peek rule (a
dealer natural resolves before the player acts) modeled where it changes the
math. `strategy.py` derives the fixed chart from the solver so the two can be
cross-checked. `simulate.py` exists to check the exact math a second,
independent way: it plays hands under fresh randomness and its long-run figures
must land on the enumerated ones.

## A worked decision

`python demo.py 8,8 T` — the famous split-eights hand, against a dealer ten:

```
Hand: 8 8  (16)  vs dealer T

  SPLIT    EV -0.4749  <- recommended
  HIT      EV -0.5354
  STAND    EV -0.5369
  DOUBLE   EV -1.0707

Recommended: SPLIT  (margin +0.0605 over the next-best action)

Player EV per hand at this table under exact basic strategy: -0.4044%
```

Every EV is negative — 16 versus a ten is a losing spot no matter what — and the
solver's job is to lose the *least*. Splitting into two hands of 8 is worth
+0.0605 over just hitting, because two hands each starting on 8 face the ten
better than one stuck on 16. Nothing told it that; it is the enumeration. And
the bottom line is the honest one: played perfectly, every hand at this table is
worth **−0.4044%** to the player. Perfect play makes the loss small; it does not
make it positive.

## What is verified, and how

The test suite runs the solver against independent checks rather than against
itself:

- **Exact vs. simulated.** `simulate.py` plays hands under fresh randomness; its
  long-run dealer-bust rate and its house edge must match the enumerated figures
  (the heavy runs are multi-million-hand simulations, gated behind `BJ_SLOW=1`).
- **Two decision paths agree.** A compiled fast-path action function is checked
  against the solver's `basic_action` across every hand shape and dealer upcard.
- **Rule sensitivity is pinned.** Doubling after split, dealer S17 vs H17,
  resplit and hit-split-aces, deck count, and blackjack payout each move the EV
  in a known direction, and the tests assert those directions rather than magic
  constants.

```
831 passed, 6 skipped   (the 6 are the BJ_SLOW statistical runs)
```

## What this does not prove

- **The headline numbers are one table.** The solver is parameterized by a
  `Rules` object, and the tests exercise rule variations, but the worked example
  and the −0.4044% are a single six-deck, S17, 3:2 table. A different table is a
  config change, not a re-derivation, and its numbers are its own.
- **It models one hand, not a session.** Every entry point starts from a fresh
  shoe minus the visible cards. There is no cross-hand shoe tracking, so **card
  counting is out of scope by construction** — this prices the decision in front
  of you, not an edge built up over a shoe.
- **It sees only what a player sees.** The dealer's hole card is never an input;
  a solver allowed to read it would be trivial and useless. Every hard problem
  here exists because it is restricted to legitimate information.
- **Two of the split rules were conservative defaults** in the original table
  (resplit aces, hit split aces), and the solver's defaults follow them. The EV
  of a table that allows them is computed correctly on request; it just is not
  the default.

## Run it

```
python demo.py 8,8 T                 # one decision, ranked, with EVs
python demo.py T,6 T                 # hard 16 vs ten - the coin flip
python -m pytest -q                  # 831 tests, ~2 minutes
BJ_SLOW=1 python -m pytest -q        # + the multi-million-hand statistical runs
```

Requires `numpy` and `pytest` (`pip install -r requirements.txt`). Python 3.11+.

## License

MIT
