# Working on Exact Blackjack Solver

I want to be able to follow a numerical disagreement back to a hand, a rule and a calculation. Include those details before trying to explain a difference with a whole game percentage.

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

Include the rules, visible cards, remaining shoe and available actions. State whether a hand is already split and what resplit budget remains. A result from different rules is a different calculation, even if the displayed hand looks the same.

Keep the independent check alongside the change. A small hand calculation, separate simulation or reference with matching rules can explain a disagreement. Include sampling uncertainty for simulations, and do not change README chart cells just to make a changed result appear consistent.

## Evidence and scope

State the rules, the visible cards and the remaining shoe when reporting a numerical difference. Preserve the distinction between exact hit, stand and double calculations and approximate split valuation. Use an independent derivation, reference or simulation when checking numerical changes. A test that calls the same solver twice does not independently verify its mathematics.

Useful next work includes comparing split approximations with a small exact reference model and widening independent checks across rule variations. Report the tested configurations instead of treating a measured difference as a universal error bound.

## Longer statistical runs

These can take substantially longer than the ordinary suite. In PowerShell,
set `$env:BJ_SLOW = '1'` before running `python -m pytest -q`, then clear it
with `$env:BJ_SLOW = ''` when finished. In a Unix shell, use:

```sh
BJ_SLOW=1 python -m pytest -q
```

## Development container and public site

Open this repository in Codespaces or use VS Code Dev Containers. The container uses Python 3.11 and installs the project into `.venv` during setup. Its image is pinned by digest. The `Project access` workflow builds that same environment and runs `.devcontainer/smoke.sh`. Runtime dependencies still follow the project configuration. Codespaces uses the creating account's compute and storage allowance.

Run `python tools/build_site.py` to assemble the public page in `_site`, then `python -m http.server 8080 --directory _site` to preview it. The builder copies only the listed example files. The page reads saved evidence; it does not silently rerun the experiment or claim current results. Pages deploys from `main` after the site and development environment checks pass.

The appearance adapter reads the pinned `presentation/tokens.json` from
Clair/Obscur revision `7a57fe750ff50205a17e1d342106a0d3f2777159` and generates
`_site/appearance.css`. Review the pin and token changes together. The six local
Inter aliases cover 400, 600 and 700 with genuine italics. Code keeps a monospace
font, other scripts can use language fallbacks, and visitors without Inter keep
their system font. Print uses Clair without changing the saved screen preference.
The storage key is `exact-blackjack-solver.appearance.v1`.

Presentation checks do not rerun the retained calculation:

```sh
python -m pytest -q tests/test_presentation.py
node --test tests/selection-state.test.mjs tests/appearance.test.mjs
npm ci --ignore-scripts
python tools/build_site.py
npm run test:browser
```

The browser suite uses fresh, isolated headless contexts with Chromium's sandbox
enabled. Set `SOLVER_BROWSER_CHANNEL=chrome` to use installed Google Chrome, as CI
does. Otherwise install Playwright's Chromium with `npx playwright install chromium`.
The optional `SOLVER_REQUIRE_INTER=1` adds strict rendered-glyph checks in an
environment where the six Inter faces are installed. The default test still
checks deliberate missing-font fallback and does not claim Inter coverage.
`SOLVER_SCREENSHOT_DIR` can save captures outside the repository. Headless checks
cover the page, not native browser chrome, a physical phone or display comfort.
