"""Render a basic-strategy chart as Markdown, and read one back.

Both charts this project holds have the same shape - a {(player_key,
dealer_up): code} dict each for hard totals, soft totals and pairs - whether
they come from the transcription in bj.strategy or from bj.ev.derive_table,
which recomputes them with the solver.  That shared shape is what lets
tests/test_ev.py diff the two cell by cell, and it is what lets this module
print either without knowing which it was given.

Markdown on purpose: it is readable in a terminal and pastes straight into the
README, so the chart shown there can be the solver's own output rather than a
hand-typed copy.  parse_chart is the inverse of render_chart, which is how
tests/test_chart.py proves the README's chart is the code's chart and not a
stale paste.
"""
from __future__ import annotations

from collections.abc import Mapping

from .core import RANK_VALUE, Rules
from .strategy import DEALER_UPS, HARD_TABLE, PAIR_TABLE, RAW_CODES, SOFT_TABLE

__all__ = ['LEGEND', 'Chart', 'describe_rules', 'parse_chart', 'render_chart',
           'transcribed_chart']

#: one section of a chart: (player key, dealer upcard) -> printed code
Chart = Mapping[tuple[object, str], str]

#: what each printed code means, in the order the legend prints them
LEGEND: tuple[tuple[str, str], ...] = (
    ('H', 'hit'),
    ('S', 'stand'),
    ('D', 'double, else hit'),
    ('Ds', 'double, else stand'),
    ('P', 'split'),
    ('Ph', 'split only if doubling after a split is allowed, else play the hard total'),
)

#: section key -> printed heading, in print order
_SECTIONS: tuple[tuple[str, str], ...] = (
    ('hard', 'Hard totals'),
    ('soft', 'Soft totals'),
    ('pairs', 'Pairs'),
)
_HEADING_TO_SECTION = {heading: key for key, heading in _SECTIONS}
_FIRST_COLUMN = {'hard': 'Hard', 'soft': 'Soft', 'pairs': 'Pair'}


def transcribed_chart() -> dict[str, Chart]:
    """The printed chart bj.strategy carries, in derive_table's shape."""
    return {'hard': HARD_TABLE, 'soft': SOFT_TABLE, 'pairs': PAIR_TABLE}


def describe_rules(rules: Rules) -> str:
    """One line naming the table a chart was derived for."""
    if rules.blackjack_payout == 1.5:
        payout = '3:2'
    elif rules.blackjack_payout == 1.2:
        payout = '6:5'
    else:
        payout = f'{rules.blackjack_payout:g}:1'
    return ', '.join((
        f'{rules.decks} deck{"" if rules.decks == 1 else "s"}',
        f'dealer {"stands" if rules.s17 else "hits"} on soft 17',
        'double after split' if rules.das else 'no double after split',
        'dealer peeks' if rules.peek else 'no peek',
        'surrender' if rules.surrender else 'no surrender',
        f'up to {rules.max_hands} hands',
        'split aces may be hit' if rules.hit_split_aces else 'split aces get one card',
        f'blackjack pays {payout}',
    ))


# --- rendering -------------------------------------------------------------

def _hard_rows(chart: Chart) -> list[tuple[str, tuple[str, ...]]]:
    """Hard rows in ascending order, runs of identical adjacent totals merged.

    Printed charts write "5-8" and "17+" rather than one line per total, and
    the merge is exactly that: consecutive totals whose ten codes are
    identical become one 'lo-hi' row.  Both conditions are required - a gap
    in the totals is never bridged, so a chart missing 7 can never print
    "5-8".
    """
    runs: list[list] = []                       # [lo, hi, codes]
    for total in sorted({key for key, _up in chart}):
        codes = tuple(chart[(total, up)] for up in DEALER_UPS)
        if runs and runs[-1][2] == codes and runs[-1][1] == total - 1:
            runs[-1][1] = total
        else:
            runs.append([total, total, codes])
    return [(str(lo) if lo == hi else f'{lo}-{hi}', codes) for lo, hi, codes in runs]


def _soft_rows(chart: Chart) -> list[tuple[str, tuple[str, ...]]]:
    """'A,2' through 'A,9', one row each."""
    keys = sorted({key for key, _up in chart}, key=lambda k: int(str(k).split(',')[1]))
    return [(str(key), tuple(chart[(key, up)] for up in DEALER_UPS)) for key in keys]


def _pair_rows(chart: Chart) -> list[tuple[str, tuple[str, ...]]]:
    """A,A first, then T,T down to 2,2: the order every printed chart uses."""
    keys = sorted({key for key, _up in chart},
                  key=lambda k: (str(k)[0] != 'A', -RANK_VALUE[str(k)[0]]))
    return [(str(key), tuple(chart[(key, up)] for up in DEALER_UPS)) for key in keys]


_ROWS = {'hard': _hard_rows, 'soft': _soft_rows, 'pairs': _pair_rows}


def render_chart(chart: Mapping[str, Chart], *, title: str | None = None) -> str:
    """The three tables as GitHub-flavoured Markdown, with a legend.

    `chart` is {'hard': ..., 'soft': ..., 'pairs': ...} as bj.ev.derive_table
    returns it or transcribed_chart() builds it.  Dealer upcards run left to
    right in DEALER_UPS order, with 'T' printed as 10 because that is what a
    reader is looking at.
    """
    out: list[str] = []
    if title:
        out += [title, '']
    columns = ' | '.join('10' if up == 'T' else up for up in DEALER_UPS)
    for key, heading in _SECTIONS:
        out += [f'### {heading}', '',
                f'| {_FIRST_COLUMN[key]} | {columns} |',
                '|:---|' + ':---:|' * len(DEALER_UPS)]
        for label, codes in _ROWS[key](chart[key]):
            out.append(f'| {label} | ' + ' | '.join(codes) + ' |')
        out.append('')
    out.append('Legend: ' + '; '.join(f'**{code}** {meaning}' for code, meaning in LEGEND))
    return '\n'.join(out)


# --- parsing ---------------------------------------------------------------

def _expand_label(section: str, label: str) -> list[object]:
    """The chart keys one printed row stands for ('13-16' is four hard keys)."""
    if section != 'hard':
        return [label]
    if '-' in label:
        lo, hi = label.split('-')
        return list(range(int(lo), int(hi) + 1))
    return [int(label)]


def parse_chart(text: str) -> dict[str, dict[tuple[object, str], str]]:
    """Inverse of render_chart: the Markdown back into the three code dicts.

    Merged hard rows are expanded to one key per total, so
    parse_chart(render_chart(c)) == c for any complete chart c.  Text outside
    the three tables is ignored, which is what lets a README section be parsed
    straight from the file.  An unknown code anywhere is an error, not a
    silent skip: a chart that reads back with a typo has to fail loudly.
    """
    out: dict[str, dict[tuple[object, str], str]] = {key: {} for key, _ in _SECTIONS}
    section: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith('### '):
            section = _HEADING_TO_SECTION.get(line[4:].strip())
            continue
        if section is None or not line.startswith('|'):
            continue
        cells = [cell.strip() for cell in line.strip('|').split('|')]
        if len(cells) != len(DEALER_UPS) + 1:
            raise ValueError(f'expected {len(DEALER_UPS) + 1} cells, got {len(cells)}: {raw!r}')
        label, codes = cells[0], cells[1:]
        if label in _FIRST_COLUMN.values() or set(label) <= set(':-'):
            continue                            # the header row and the rule under it
        for code in codes:
            if code not in RAW_CODES:
                raise ValueError(f'unknown strategy code {code!r} in row {label!r}')
        for key in _expand_label(section, label):
            for up, code in zip(DEALER_UPS, codes):
                out[section][(key, up)] = code
    return out
