"""Advise one blackjack hand: the exact EV of every legal action.

    python demo.py T,6 T     # hard 16 vs a dealer ten
    python demo.py A,7 3     # soft 18 vs 3
    python demo.py 8,8 T     # the split-eights classic
    python demo.py           # a default hand

Arguments are the CARDS you hold, not a total: 'T,6' is a ten and a six
(hard 16), not the number sixteen.

No table state is needed: the shoe defaults to a fresh six-deck shoe with
the cards you can see removed. Ten-value cards are written 'T'; 'A,7' and
'A7' both parse. Every number below is exact enumeration, not simulation
or a lookup table - re-running gives bit-identical results.
"""
import sys

from bj.core import ACTION_NAMES, hand_total, normalize, normalize_hand
from bj.ev import best_action, house_edge
from bj.strategy import basic_action


def main():
    args = sys.argv[1:]
    player, up = (args[0], args[1]) if len(args) >= 2 else ('8,8', 'T')
    cards = normalize_hand(player)
    upc = normalize(up)
    total, soft = hand_total(cards)

    action, evs, margin = best_action(cards, upc)

    label = ('soft ' if soft else '') + str(total)
    print("Hand: %s  (%s)  vs dealer %s" % (' '.join(cards), label, upc))
    print()
    for act, ev in sorted(evs.items(), key=lambda kv: -kv[1]):
        star = '  <- recommended' if act == action else ''
        print("  %-8s EV %+.4f%s" % (ACTION_NAMES[act], ev, star))
    print()
    print("Recommended: %s  (margin %+.4f over the next-best action)"
          % (ACTION_NAMES[action], margin))
    print()
    he = house_edge(strategy=basic_action)
    print("Player EV per hand at this table under exact basic strategy: "
          "%+.4f%%" % (100 * he))


if __name__ == '__main__':
    main()
