"""Exact composition-dependent blackjack solver.

The problem, stated so the code can be read against it: one blackjack hand is
a single-agent, finite-horizon Markov decision process.  The state is the
player's (total, softness), the dealer's upcard and the exact composition of
the cards nobody has seen; the actions are hit, stand, double and split; the
transitions are card draws WITHOUT replacement from that composition; the
reward is the settlement at the end of the hand.  The dealer is part of the
environment - a fixed drawing rule, never an opponent - so there is no game
theory here, no equilibrium and no adversary.  There is no learning either:
the value of every state is computed exactly by dynamic programming over the
reachable continuations, memoised on the immutable shoe tuple, so re-running
gives bit-identical numbers.

    core.py      ranks, hands, the immutable shoe, the Rules dataclass
    dealer.py    exact dealer outcome distribution (peek and hole card modelled)
    ev.py        the solver: stand / hit / double / split EV by enumeration
    strategy.py  the printed total-dependent chart, and the fallbacks around it
    simulate.py  Monte Carlo harness that re-derives the same numbers

Every entry point starts from a fresh shoe minus the visible cards, or from a
shoe the caller supplies.  Nothing carries state between hands.

Vocabulary.  Comments and tests refer to "the spec": the design notes of the
private project this was extracted from, which transcribed the Wizard of Odds
figures for the original table's ruleset (6 decks, S17, DAS, peek) and logged
a 37-hand session of real play.  The notes are not in this repository; every
number they supplied is reproduced in tests/, so nothing here depends on
having them.  "The original table" and "the original game" are that table.
"""

__version__ = '0.1.0'
