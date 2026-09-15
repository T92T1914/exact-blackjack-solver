# Contributing to Exact Blackjack Solver

I welcome focused fixes, clearer examples and results that challenge an assumption in the project. If something looks wrong, I would rather have a small case I can run than a broad claim that it is broken.

## Start locally

Use Python 3.11 or later and run these commands from the repository root. A virtual environment keeps the development dependencies separate from your other projects.

```sh
python -m venv .venv
```

Activate it with `.venv\Scripts\Activate.ps1` in PowerShell, or `source .venv/bin/activate` on macOS or Linux. Then install what this project needs:

```sh
python -m pip install -e ".[dev]"
```

## Check a change

```sh
python -m pytest -q -m "not slow"
ruff check .
```

Start with [the solver](bj/ev.py), [dealer outcomes](bj/dealer.py) and [the simulation](bj/simulate.py). The README decision and chart are checked by [CLI tests](tests/test_cli.py) and [chart tests](tests/test_chart.py).

## Report a bug or propose a change

Check the existing issues first. Include the revision, Python version, operating system, command, expected behavior and actual output. For a numerical issue, include the smallest input that demonstrates it. Remove credentials and private data from logs before posting.

Keep a pull request focused on one problem. Explain what changes for someone using the project, why the approach fits and which checks you ran. Add a regression test when it captures a real failure. Documentation changes should be checked against the current code and examples.

## Evidence and scope

State the rules, the visible cards and the remaining shoe when reporting a numerical difference. Preserve the distinction between exact hit, stand and double calculations and approximate split valuation. Use an independent derivation, reference or simulation when checking numerical changes. A test that calls the same solver twice does not independently verify its mathematics.

Useful next work includes comparing split approximations with a small exact reference model and widening independent checks across rule variations. Report the tested configurations instead of treating a measured difference as a universal error bound.

## Writing

Use plain language and concrete examples. Avoid em dashes and unnecessary hyphens in authored prose. Preserve the exact spelling of code, commands, paths, package names, links and quoted evidence. Claims about performance should link to measurements and say what was actually tested.

Be respectful when discussing a change. Questions and disagreements are welcome; keep them about the work.
