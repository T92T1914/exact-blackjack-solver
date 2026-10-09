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
import json
import math
import re
from collections.abc import Sequence
from dataclasses import replace
from numbers import Integral

from .chart import describe_rules, render_chart
from .core import (ACTION_NAMES, RANKS, STANDARD, CardLike, Rules, Shoe, hand_total,
                   normalize, normalize_hand, normalize_shoe)
from .ev import best_action, derive_table, house_edge
from .record import decision_json
from .replay import EXIT_STATUSES, replay_file
from .strategy import basic_action

__all__ = ['advise', 'table', 'main']


def advise(cards: str | Sequence[CardLike], dealer_up: CardLike,
           rules: Rules = STANDARD, *, shoe: Shoe | None = None,
           is_split_hand: bool = False, hand_count: int | None = None,
           can_double: bool = True, can_split: bool = True) -> str:
    """The report for one hand: the text `bj-advise CARDS UP` prints.

    Every action the table allows, ranked by modeled EV; the margin between the
    best and the next-best, which is the honest measure of how much the
    decision is worth, and the player's expectation per hand
    at this table under the printed chart, which bj.ev.house_edge follows all
    the way down under the stated rules and split approximations.

    An explicit shoe contains every unseen card, including the reserved dealer
    hole card. Visible cards have already been removed. Its report omits the
    fresh-shoe whole-game estimate. Split state changes available actions and
    distinguishes a split 21 from a natural, without changing the solver.
    False action controls restrict only the current double or split choice.
    """
    for name, value in (('can_double', can_double), ('can_split', can_split)):
        if not isinstance(value, bool):
            raise ValueError(f'{name} must be a boolean')
    if hand_count is None:
        hand_count = 2 if is_split_hand else 1
    if (not isinstance(hand_count, Integral) or isinstance(hand_count, bool)
            or not 1 <= hand_count <= rules.max_hands):
        raise ValueError(f'hand_count must be an integer from 1 to {rules.max_hands}')
    if is_split_hand and hand_count < 2:
        raise ValueError('a split hand requires at least two hands in the round')
    if not is_split_hand and hand_count != 1:
        raise ValueError('hand_count above 1 requires a split hand')
    hand = normalize_hand(cards)
    up = normalize(dealer_up)
    total, soft = hand_total(hand)
    unseen = None if shoe is None else normalize_shoe(shoe)
    action, evs, margin = best_action(hand, up, shoe=unseen, rules=rules,
                                    is_split_hand=is_split_hand, hand_count=hand_count,
                                    can_double=can_double, can_split=can_split)

    label = ('soft ' if soft else '') + str(total)
    lines = [f'Hand: {" ".join(hand)}  ({label})  vs dealer {up}', '']
    if unseen is not None:
        lines += ['Unseen shoe (includes dealer hole): '
                  + ', '.join(f'{rank}={count}' for rank, count in zip(RANKS, unseen)), '']
    if is_split_hand or hand_count != 1:
        lines += [f'Round state: {"split hand" if is_split_hand else "unsplit hand"}, '
                  f'{hand_count} hands in the round', '']
    restricted = [name for name, enabled in (('DOUBLE', can_double), ('SPLIT', can_split))
                  if not enabled]
    if restricted:
        lines += ['Current action restrictions: ' + ', '.join(restricted), '']
    for act, ev in sorted(evs.items(), key=lambda kv: -kv[1]):
        star = '  <- recommended' if act == action else ''
        lines.append(f'  {ACTION_NAMES[act]:<8} EV {ev:+.4f}{star}')
    lines += ['',
              f'Recommended: {ACTION_NAMES[action]}  '
              f'(margin {margin:+.4f} over the next-best action)',
              '']
    if unseen is None and not is_split_hand and hand_count == 1 and not restricted:
        edge = house_edge(rules, strategy=basic_action)
        lines.append('Player EV per hand under basic strategy (split approximations apply): '
                     f'{100 * edge:+.4f}%')
    elif restricted:
        lines.append('Values apply to this hand and declared current choices. '
                     'No whole-game estimate is computed.')
    else:
        lines.append('Values apply to this hand and stated round state. '
                     'No whole-game estimate is computed.')
    return '\n'.join(lines)


def _unseen_cards(text: str) -> Shoe:
    """Convert a comma-separated physical rank list without removing visible cards."""
    parts = text.split(',')
    if any(not part.strip() for part in parts):
        raise argparse.ArgumentTypeError('--unseen needs a nonempty comma-separated card list')
    try:
        cards = tuple(normalize(part.strip()) for part in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    return tuple(cards.count(rank) for rank in RANKS)


def _unseen_counts(text: str) -> Shoe:
    """Admit decimal rank tallies without changing the caller's retained counts."""
    parts = text.split(',')
    if len(parts) != len(RANKS):
        raise argparse.ArgumentTypeError(
            '--unseen-counts needs exactly ten counts in A,2,3,4,5,6,7,8,9,T order')
    counts = []
    for rank, part in zip(RANKS, parts):
        digits = part.strip(' \t\r\n\v\f')
        if not digits or any(char < '0' or char > '9' for char in digits):
            raise argparse.ArgumentTypeError(
                f'--unseen-counts count for {rank} must be a nonnegative base-10 integer')
        try:
            counts.append(int(digits, 10))
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                f'--unseen-counts count for {rank} cannot be converted '
                'by this Python runtime') from exc
    return normalize_shoe(counts)


def _max_hands(text: str) -> int:
    """Parse the existing positive rule cap without imposing an upper bound."""
    digits = text.strip(' \t\r\n\v\f')
    message = '--max-hands must be a positive ASCII decimal integer'
    if not digits or any(char < '0' or char > '9' for char in digits):
        raise argparse.ArgumentTypeError(message)
    try:
        cap = int(digits, 10)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            '--max-hands cannot be converted by this Python runtime') from exc
    if cap < 1:
        raise argparse.ArgumentTypeError(message)
    return cap


def _blackjack_payout(text: str) -> float:
    """Admit a declared net natural payout through the existing float boundary."""
    token = text.strip(' \t\r\n\v\f')
    pattern = (r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)'
               r'(?:[eE][+-]?[0-9]+)?')
    message = ('--blackjack-payout must be a finite nonnegative ASCII '
               'decimal or scientific number')
    if re.fullmatch(pattern, token) is None:
        raise argparse.ArgumentTypeError(message)
    try:
        payout = float(token)
    except (ValueError, OverflowError) as exc:
        raise argparse.ArgumentTypeError(message) from exc
    if not math.isfinite(payout) or payout < 0:
        raise argparse.ArgumentTypeError(message)
    return payout


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
    parser.add_argument('cards', nargs='?', default=None,
                        help='your cards, in dealt order: 8,8  T6  A,7  KQ  (default: 8,8)')
    parser.add_argument('upcard', nargs='?', default=None,
                        help="the dealer's upcard: 2-9, T (or K, Q, J, 10), A  (default: T)")
    parser.add_argument('--table', action='store_true',
                        help='print the full basic-strategy chart the solver derives '
                             '(Markdown; about a minute) instead of advising a hand')
    parser.add_argument('--json', action='store_true',
                        help='print a versioned decision record with complete state and raw EVs; '
                             'with --replay, print the comparison report as JSON')
    parser.add_argument('--replay', metavar='PATH',
                        help='validate and recompute a saved decision record, '
                             'then compare raw values')
    parser.add_argument('--decks', type=int, default=None, metavar='N',
                        help=f'decks in the shoe (default: {STANDARD.decks})')
    parser.add_argument('--h17', action='store_true',
                        help='dealer hits soft 17 (default: stands)')
    parser.add_argument('--no-das', action='store_true',
                        help='no doubling after a split (default: allowed)')
    parser.add_argument('--blackjack-payout', type=_blackjack_payout,
                        default=None, metavar='N',
                        help='net natural payout per original wager: 1.5 = 3:2, '
                             '1.2 = 6:5 '
                             f'(default: {STANDARD.blackjack_payout})')
    parser.add_argument('--resplit-aces', action='store_true',
                        help='declare that aces may be resplit (default: not allowed)')
    parser.add_argument('--hit-split-aces', action='store_true',
                        help='declare that split aces may receive more cards '
                             '(default: one card only)')
    parser.add_argument('--no-double', action='store_true',
                        help='exclude the current DOUBLE alternative, without changing rules')
    parser.add_argument('--no-split', action='store_true',
                        help='exclude the current SPLIT alternative, without changing rules')
    parser.add_argument('--max-hands', type=_max_hands, default=None, metavar='N',
                        help='maximum hands allowed in a round, including completed hands '
                             f'(default: {STANDARD.max_hands}); distinct from --hand-count')
    unseen = parser.add_mutually_exclusive_group()
    unseen.add_argument('--unseen', type=_unseen_cards, metavar='CARDS',
                        help='explicit unseen cards, including the dealer hole, e.g. '
                             '2,3,7,8,9,T. Visible cards are already removed')
    unseen.add_argument('--unseen-counts', dest='unseen', type=_unseen_counts, metavar='CSV',
                        help='ten nonnegative decimal counts in A,2,3,4,5,6,7,8,9,T order; '
                             'include the dealer hole and already exclude visible cards')
    parser.add_argument('--split-hand', action='store_true',
                        help='this hand came from splitting; first card is the split rank')
    parser.add_argument('--hand-count', type=int, default=None, metavar='N',
                        help='total hands created in this round, including completed hands '
                             '(default: 2 with --split-hand, otherwise 1)')
    args = parser.parse_args(argv)
    if args.replay is not None:
        if (args.cards is not None or args.upcard is not None or args.table
                or args.decks is not None or args.h17 or args.no_das
                or args.blackjack_payout is not None
                or args.resplit_aces or args.hit_split_aces
                or args.no_double or args.no_split
                or args.max_hands is not None or args.unseen is not None
                or args.split_hand or args.hand_count is not None):
            parser.error('--replay cannot be combined with cards, upcard, --table or state options')
        result = replay_file(args.replay)
        print(json.dumps(result, indent=2, allow_nan=False) if args.json else _replay_text(result))
        return EXIT_STATUSES[result['status']]
    args.cards = args.cards if args.cards is not None else '8,8'
    args.upcard = args.upcard if args.upcard is not None else 'T'
    args.decks = args.decks if args.decks is not None else STANDARD.decks
    args.max_hands = args.max_hands if args.max_hands is not None else STANDARD.max_hands
    args.blackjack_payout = (args.blackjack_payout if args.blackjack_payout is not None
                             else STANDARD.blackjack_payout)
    if args.decks < 1:
        parser.error('--decks must be at least 1')
    rules = replace(STANDARD, decks=args.decks, s17=not args.h17, das=not args.no_das,
                    max_hands=args.max_hands, resplit_aces=args.resplit_aces,
                    hit_split_aces=args.hit_split_aces, blackjack_payout=args.blackjack_payout)
    if args.table and (args.unseen is not None or args.split_hand or args.hand_count is not None
                       or args.no_double or args.no_split):
        parser.error('--table cannot be combined with hand-specific state options')
    if args.table and args.json:
        parser.error('--table cannot be combined with --json')
    hand_count = args.hand_count if args.hand_count is not None else 2 if args.split_hand else 1
    if args.split_hand and hand_count < 2:
        parser.error('--split-hand requires at least two hands in the round')
    if not args.split_hand and hand_count != 1:
        parser.error('--hand-count above 1 requires --split-hand')

    try:
        if args.json:
            text = decision_json(args.cards, args.upcard, rules, shoe=args.unseen,
                                 is_split_hand=args.split_hand, hand_count=hand_count,
                                 can_double=not args.no_double, can_split=not args.no_split)
        else:
            text = table(rules) if args.table else advise(args.cards, args.upcard, rules,
                                                        shoe=args.unseen,
                                                        is_split_hand=args.split_hand,
                                                        hand_count=hand_count,
                                                        can_double=not args.no_double,
                                                        can_split=not args.no_split)
    except ValueError as exc:
        # Unknown card, a busted hand, more cards than the shoe holds: the
        # solver refuses rather than guessing, and so does the command line.
        parser.error(str(exc))
    except OverflowError as exc:
        if args.table:
            raise
        parser.error(f'cannot calculate decision: arithmetic overflow ({exc})')
    print(text)
    return 0


def _replay_text(report):
    """Display raw values so small margins and action changes remain visible."""
    lines = [f"Replay: {report['status']}",
             'Comparison: exact_binary_float (zero absolute and relative tolerance)']
    package = report['recorded_package']
    if package is not None:
        lines.append(f"Package version: recorded {package['version']}, "
                     f"current {report['current_package']['version']}, "
                     f"matches={report['package_version_matches']}")
    comparison = report['comparison']
    if comparison is not None:
        actions = comparison['legal_actions']
        lines.append(f"Legal actions: recorded {actions['recorded']}, "
                     f"recomputed {actions['recomputed']}, matches={actions['matches']}")
        for code, values in comparison['evs'].items():
            lines.append(f"{ACTION_NAMES[code]}: recorded {values['recorded']!r}, "
                         f"recomputed {values['recomputed']!r}, matches={values['matches']}")
        for label in ('recommendation', 'margin'):
            values = comparison[label]
            lines.append(f"{label.capitalize()}: recorded {values['recorded']!r}, "
                         f"recomputed {values['recomputed']!r}, matches={values['matches']}")
    if report['error'] is not None:
        lines.append(f"{report['error']['type']}: {report['error']['message']}")
    return '\n'.join(lines)
