"""Command line: advise one hand, or print the chart the solver derives.

    bj-advise 8,8 T          # one decision, ranked, with the EV of every action
    bj-advise T,6 T          # hard 16 vs a ten - the coin flip
    bj-advise A,7 3          # soft 18 vs 3 - a real edge
    bj-advise 6,5 A --h17    # the same solver at a dealer-hits-soft-17 table
    bj-advise --table        # the whole basic-strategy chart, derived (about a minute)

`python demo.py ...` from a checkout is the same command without installing.

Arguments are the CARDS you hold, not a total: 'T,6' is a ten and a six (hard
16), not the number sixteen.  Ten-value cards are written T; K, Q, J and 10
are accepted and mean the same thing.  'A,7' and 'A7' both parse.

No table state is needed: the shoe defaults to a fresh shoe of --decks decks
with the cards you can see removed. Hit, stand and double use exact
enumeration. Split values use independent-hand and greedy resplit-budget
approximations, which also affect whole-game estimates. Re-running is deterministic.
"""
from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import replace

from .chart import describe_rules, render_chart
from .core import ACTION_NAMES, STANDARD, CardLike, Rules, hand_total, normalize, normalize_hand
from .ev import best_action, derive_table, house_edge
from .strategy import basic_action

__all__ = ['advise', 'table', 'main']


def advise(cards: str | Sequence[CardLike], dealer_up: CardLike,
           rules: Rules = STANDARD) -> str:
    """The report for one hand: the text `bj-advise CARDS UP` prints.

    Every action the table allows, ranked by modeled EV; the margin between the
    best and the next-best, which is the honest measure of how much the
    decision is worth; and the bottom line - the player's expectation per hand
    at this table under the printed chart, which bj.ev.house_edge follows all
    the way down under the stated rules and split approximations.
    """
    hand = normalize_hand(cards)
    up = normalize(dealer_up)
    total, soft = hand_total(hand)
    action, evs, margin = best_action(hand, up, rules=rules)

    label = ('soft ' if soft else '') + str(total)
    lines = [f'Hand: {" ".join(hand)}  ({label})  vs dealer {up}', '']
    for act, ev in sorted(evs.items(), key=lambda kv: -kv[1]):
        star = '  <- recommended' if act == action else ''
        lines.append(f'  {ACTION_NAMES[act]:<8} EV {ev:+.4f}{star}')
    lines += ['',
              f'Recommended: {ACTION_NAMES[action]}  '
              f'(margin {margin:+.4f} over the next-best action)',
              '']
    edge = house_edge(rules, strategy=basic_action)
    lines.append('Player EV per hand under basic strategy (split approximations apply): '
                 f'{100 * edge:+.4f}%')
    return '\n'.join(lines)


def table(rules: Rules = STANDARD) -> str:
    """The whole chart, derived cell by cell by the solver, as Markdown.

    Slow on purpose - about a minute cold - because every cell is priced by
    enumeration (split approximations apply); hard rows average every two-card
    composition of each total (bj.ev.derive_table).  This is the text the
    README's chart section holds; tests/test_chart.py parses that section
    back and checks it against derive_table, so the README cannot drift.
    """
    return render_chart(
        derive_table(rules),
        title=('Basic strategy derived by the solver (split approximations apply): '
               f'{describe_rules(rules)}.'),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog='bj-advise',
        description='Enumerated EVs for one blackjack hand or a strategy chart. '
                    'Hit/stand/double are exact; split uses documented approximations.',
        epilog=__doc__.split('\n\n', 1)[1],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('cards', nargs='?', default='8,8',
                        help='your cards, in dealt order: 8,8  T6  A,7  KQ  (default: 8,8)')
    parser.add_argument('upcard', nargs='?', default='T',
                        help="the dealer's upcard: 2-9, T (or K, Q, J, 10), A  (default: T)")
    parser.add_argument('--table', action='store_true',
                        help='print the full basic-strategy chart the solver derives '
                             '(Markdown; about a minute) instead of advising a hand')
    parser.add_argument('--decks', type=int, default=STANDARD.decks, metavar='N',
                        help=f'decks in the shoe (default: {STANDARD.decks})')
    parser.add_argument('--h17', action='store_true',
                        help='dealer hits soft 17 (default: stands)')
    parser.add_argument('--no-das', action='store_true',
                        help='no doubling after a split (default: allowed)')
    args = parser.parse_args(argv)
    if args.decks < 1:
        parser.error('--decks must be at least 1')
    rules = replace(STANDARD, decks=args.decks, s17=not args.h17, das=not args.no_das)

    try:
        text = table(rules) if args.table else advise(args.cards, args.upcard, rules)
    except ValueError as exc:
        # Unknown card, a busted hand, more cards than the shoe holds: the
        # solver refuses rather than guessing, and so does the command line.
        parser.error(str(exc))
    print(text)
    return 0
