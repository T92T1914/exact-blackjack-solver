"""Advise one blackjack hand straight from a checkout, nothing installed.

    python demo.py 8,8 T        # the split-eights classic
    python demo.py T,6 T        # hard 16 vs a dealer ten - the coin flip
    python demo.py A,7 3        # soft 18 vs 3 - a real edge
    python demo.py --table      # the whole chart, derived by the solver
    python demo.py --help       # every option

This is the same command line as the installed `bj-advise`; the code is in
bj/cli.py.  Arguments are the CARDS you hold, not a total.
"""
from bj.cli import main

if __name__ == '__main__':
    raise SystemExit(main())
