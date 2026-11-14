# Changelog

Notable changes to this project, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Version numbers
follow [Semantic Versioning](https://semver.org/). The version the package
reports is `bj.__version__`.

## [Unreleased]

### Added
* `pyproject.toml`: `pip install -e .` installs the package and a `bj-advise`
  command. The pytest and ruff configuration live there too.
* `bj/cli.py`: the command line, with `--table` (the basic strategy chart the
  solver derives, as Markdown), `--decks`, `--h17` and `--no-das`.
* `bj/chart.py`: renders a chart as Markdown and parses one back, so the chart
  in the README is checked cell by cell against `derive_table()` by the tests.
* CI: a `lint` job (`ruff check .`) that can fail, and a test matrix on
  Python 3.11, 3.12 and 3.13.
* `tests/test_chart.py`, `tests/test_cli.py`, and `tests/conftest.py` holding
  the three session scoped exact computations.
* `.gitattributes` pinning LF line endings.
* A browser demo under `site/`, built by `tools/build_site.py` from an explicit
  list of public files. It keeps each saved example's source revision,
  assumptions and limits beside the result (#3). The selected example lives in
  the URL under its visible label, so links survive reordering and Back and
  Forward restore earlier selections (#6). The page offers Auto, Clair and
  Obscur appearances and keeps the original diagram's bytes (#9).
* `.devcontainer/` with a pinned Python environment and a smoke check, and the
  Project access workflow (`.github/workflows/access.yml`) that checks it and
  deploys the site from `main` (#3).
* `bj/joint_split.py`, an independent bounded joint split reference for two
  hands without resplitting, with the retained 48 condition comparison from
  `tools/compare_joint_split.py` and `docs/joint-split.md` (#10).
* Retained composition figures in Clair and Obscur from
  `tools/render_composition_figure.py`, explained in `docs/visual-example.md`
  (#11, #12), and an Obscur sharing card from `tools/render_share_preview.py`
  with its receipt in `docs/sharing-card-receipt.json` (#13).
* `bj/caches.py`: production cache diagnostics and one combined reset (#14),
  described in `docs/caches.md`, with the bounded lifecycle measurements in
  `docs/cache-results-2026-09-30.md` (#15).
* `tests/test_ev_physical_reference.py`: an independent `Fraction` reference
  that deals physical card permutations with a hidden dealer hole for eight
  six card hit, stand and double conditions (#24). Later split references
  follow the same pattern in `tests/resplit_physical_reference.py` (#42) and
  `tests/ace_resplit_physical_reference.py` (#43).
* `bj-advise` state options: `--unseen` and `--unseen-counts` for an explicit
  remaining shoe, `--split-hand` and `--hand-count` for a hand inside a split
  round (#25, #32), `--max-hands` (#33), `--no-double` and `--no-split` (#34),
  `--resplit-aces` and `--hit-split-aces` (#36), and `--blackjack-payout` for a
  declared natural payout (#37).
* `bj/record.py` and `bj-advise --json`: a versioned portable record of one
  decision with its normalized state, rules and qualifications (#26).
* `bj/replay.py` and `bj-advise --replay`: replay of a saved record through the
  installed solver without trusting its saved answer, documented in
  `docs/saved-record-replay.md` with `examples/replay_saved_decision.py` (#30).
* The local record inspector in the browser demo, which reads and compares
  saved records without uploading or recomputing them (#31).
* `bj-calculate` (`bj/calculation.py`): captures a request and calculates it in
  one disposable owned worker under a wall policy, with a Job memory limit on
  Windows, and publishes a decision and receipt only after the worker is
  retired (#39). Guide:
  `docs/local-calculation.md`.
* Five separately selected bounded calculation models, each with a request
  schema, a guide under `docs/` and a request under `examples/`:
  `common_shoe_two_hand` in `bj/common_shoe.py` (#40),
  `post_peek_late_surrender` in `bj/late_surrender.py` (#41),
  `common_shoe_bounded_resplit` in `bj/bounded_resplit.py` (#42),
  `common_shoe_bounded_ace_resplit` in `bj/bounded_ace_resplit.py` (#43) and
  `deferred_second_card_all_wagers_sdh` in `bj/deferred_second_card.py` (#45).
* `bj-replay` (`bj/supervised_replay.py`): protected replay of a saved record in
  the same kind of owned worker, documented in `docs/protected-replay.md` (#44).
* Mixed twenty card requests for the common shoe and ace resplit models, and
  the H17 ace request, each completing under the unchanged 100,000 state cap
  through shared dealer states and terminal reuse (#46, #47, #48). The method
  and counters are recorded in `docs/common-shoe-dealer-computation.md`,
  `docs/ace-resplit-dealer-computation.md` and `docs/ace-terminal-reuse.md`.
* Reuse of completed settlement states in bounded resplits, which lets two
  declared sixteen card non ace requests complete under the same cap (#53).
  The README describes them without a latency, memory or universal
  completion claim (#55).
* Tests for a calculation that commits its decision and receipt before the
  stdout report fails (#54).
* Translation help: literal code and identifiers on the project page carry
  `translate="no"` (#61), and the README and page link a translation reading
  guide (#62).
* `tools/split_error_study.py`: the default split value against the two hand
  common shoe value for every pair and upcard on the six deck table, with two
  hands and no resplit. The saved cells are in
  `docs/split-error-study-results.json`, and `docs/split-error-study.md`
  explains the table and its limits (#71). The script takes `--table h17` and
  `--table no-das` for the dealer hitting soft 17 and for no double after
  split, each with its own saved results file.

### Changed
* GitHub Actions moved to the Node 24 releases: `actions/checkout@v5`,
  `actions/setup-python@v6`.
* Docstrings and comments no longer refer to the private project's design
  document, UI, or files that are not in this repository. The phrase "the spec" is
  defined once in `bj/__init__.py`, and the package docstring states the
  problem being solved (a single agent finite horizon MDP, not game theory).
* Type hints use built in generics (PEP 585) and `X | None` (PEP 604).
  `bj/core.py` gains a `CardLike` alias and hints on the shoe helpers.
* `demo.py` is a thin front door over `bj.cli.main`. Its output for a hand is
  unchanged and pinned by `tests/test_cli.py`.
* `bj.cli.table(rules)` labels the returned chart with its modeled peek and no
  surrender scope and adds a note when a caller asks for other flags. The
  default chart is unchanged (#38).
* Reports for an explicit shoe print the supplied rank counts and the split
  round state, and omit the fresh shoe whole game estimate (#25).
* The README, guides and package docstrings describe the calculations as
  enumeration in binary floating point, name the original independent hand
  split approximation, and separate it from the named bounded models (#2, #4,
  #49, #50, #51, #59, #63). The replay guides cover every supported record
  family (#60).
* The browser demo starts in Obscur and leads with the saved examples. Clair
  and Auto remain selectable (#58). README figures stay Obscur in either
  appearance, with Clair editions linked (#64).
* The Obscur figures and the sharing card use the monochrome Obscur values and three
  static Inter faces with no italics. The Clair editions stay as first drawn.
* The Obscur figures and the sharing card hold the 30 pt at 100 dpi type floor, with
  every label wrapped by measured width. The Obscur composition and evidence figures
  draw their labels as outlines in the SVG, and the sharing card is now 1800 by 900
  pixels.
* The demo keeps selectors inside narrow panels and makes wide evidence tables
  keyboard scrollable (#7). At phone width with enlarged text, headings and
  prose wrap instead of widening the page (#19).

### Removed
* `pytest.ini` (moved into `pyproject.toml`).
* The `python -m pyflakes ... || true` CI step, which never ran because
  pyflakes was not installed.

### Fixed
* Simulation sizes are validated before any random state is consumed (#1).
* A fresh shoe rejects an invalid deck count (#5), and malformed custom shoe
  counts are rejected before a cached calculation (#16).
* Finite shoe decisions handle the final drawable card without drawing the
  dealer's hole card (#8).
* Explicit chart availability and the compiled action lookup respect the
  table rules (#17, #22).
* Installed wheels include the `py.typed` marker (#18).
* The joint reference enforces its deadline before returning a value (#20)
  and retires its runner resources when startup fails (#21).
* Advice stops at a completed 21 (#23), and a completed split 21 receives no
  further split actions (#29).
* Impossible dealer holes are rejected before a natural is paid (#27), and
  impossible three card split ace states are rejected (#28).
* The browser test resolves the joint report link from the admitted base, so
  it holds for both a local origin and the published Pages directory (#35).
* Publication requires a complete offered action map (#51), and fresh replies
  keep canonical tied recommendations (#52).
* Receipts from a publication collision no longer reference uncommitted
  artifacts (#56).
* Request capture refuses a final path component replaced by a link (#57).

## [0.1.0], 2026-09-05

### Added
* Initial public extraction: the exact composition dependent solver
  (`bj/ev.py`), the exact dealer model (`bj/dealer.py`), the transcribed
  basic strategy with its fallbacks (`bj/strategy.py`), the Monte Carlo
  verification harness (`bj/simulate.py`), `demo.py`, and 831 tests with six
  multi million hand statistical runs gated behind `BJ_SLOW=1`.
