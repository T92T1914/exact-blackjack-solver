# Changelog

Notable changes to this project, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); version numbers
follow [Semantic Versioning](https://semver.org/). The version the package
reports is `bj.__version__`.

## [Unreleased]

### Added
* `pyproject.toml`: `pip install -e .` installs the package and a `bj-advise`
  command; pytest and ruff configuration live there too.
* `bj/cli.py`: the command line, with `--table` (the basic strategy chart the
  solver derives, as Markdown), `--decks`, `--h17` and `--no-das`.
* `bj/chart.py`: renders a chart as Markdown and parses one back, so the chart
  in the README is checked cell by cell against `derive_table()` by the tests.
* CI: a `lint` job (`ruff check .`) that can fail, and a test matrix on
  Python 3.11, 3.12 and 3.13.
* `tests/test_chart.py`, `tests/test_cli.py`, and `tests/conftest.py` holding
  the three session scoped exact computations.
* `.gitattributes` pinning LF line endings.

### Changed
* GitHub Actions moved to the Node 24 releases: `actions/checkout@v5`,
  `actions/setup-python@v6`.
* Docstrings and comments no longer refer to the private project's design
  document, UI, or files that are not in this repository; "the spec" is
  defined once in `bj/__init__.py`, and the package docstring states the
  problem being solved (a single agent finite horizon MDP, not game theory).
* Type hints use built in generics (PEP 585) and `X | None` (PEP 604);
  `bj/core.py` gains a `CardLike` alias and hints on the shoe helpers.
* `demo.py` is a thin front door over `bj.cli.main`; its output for a hand is
  unchanged and pinned by `tests/test_cli.py`.

### Removed
* `pytest.ini` (moved into `pyproject.toml`).
* The `python -m pyflakes ... || true` CI step, which never ran because
  pyflakes was not installed.

## [0.1.0], 2026-09-05

### Added
* Initial public extraction: the exact composition dependent solver
  (`bj/ev.py`), the exact dealer model (`bj/dealer.py`), the transcribed
  basic strategy with its fallbacks (`bj/strategy.py`), the Monte Carlo
  verification harness (`bj/simulate.py`), `demo.py`, and 831 tests with six
  multi million hand statistical runs gated behind `BJ_SLOW=1`.
