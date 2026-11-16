"""Measure the default split value with resplitting against one shared shoe.

The default table allows up to four hands. `bj.ev` values every split hand
against the shoe at its own split and spends the resplit allowance from one
shared pool. This script asks what that same play earns when every hand is
dealt from one shared shoe, in every pair and upcard cell of the six deck table.

The best play from one shared shoe with up to four hands is not computed here.
Its state is the ending of every earlier hand, and one 2,2 hand alone can end
in 8,050 ways, so I expect it to be far past one machine at six decks and did
not attempt it. Three values below it are computed instead, and the largest
one is a lower bound on it.

1. The default's own choices played from one shared shoe. Every hand still
   decides from its own cards and the shoe the default gave it, and resplits
   when the default would, so this is a play a player could follow.
2. The same for the default's choices on a table of three hands. Those choices
   use a pool of one extra hand and never take a fourth, which a player here
   may decline, so that play is legal too.
3. The two hand shared shoe value from `docs/split-error-study-results.json`.
   A player here may decline every resplit, so that value is a legal play too.

How the first two are computed. Suppose every split hand took its first card
before any hand played on. Every complete deal, meaning the cards each hand and
the dealer end with, can happen in that order and in table order, with the same
probability, because a deal's probability depends only on which cards left the
shoe. So both orders have the same value. In the reordered deal a hand that
plays on meets, on average, the shoe as it stood right after its own first
card, because a hand that decides from its own cards cannot steer what stays
behind. So the value needs only the first cards. The chance of a first card
that is not a pair card is the chance of any card less the chance of a pair
card, and any card drops out by the same averaging. What is left is single
hands played in shoes that differ only in how many pair cards are gone.

    python tools/resplit_study.py --output docs/resplit-study-results.json
    python tools/resplit_study.py --check
    python tools/resplit_study.py --table h17 --check
    python tools/resplit_study.py --table no-das --check
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import subprocess
import sys
import time
from dataclasses import asdict, replace
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bj import ev  # noqa: E402
from bj.core import DOUBLE, HIT, SPLIT, STAND, RANK_INDEX, Rules, remove_card, shoe_size  # noqa: E402
from tools import split_error_study as two_hand  # noqa: E402

RESULTS = ROOT / 'docs/resplit-study-results.json'
DOCUMENT = ROOT / 'docs/resplit-study.md'
TWO_HAND_RESULTS = two_hand.RESULTS
SOURCE_FILES = ('tools/resplit_study.py', 'tools/split_error_study.py', 'bj/ev.py',
                'bj/dealer.py', 'bj/core.py')
#: The default table: six decks, S17, DAS, peek, up to four hands, one card to
#: each split ace and no resplitting aces.
TABLE = Rules()
#: Study tables by option name: the default and each of two one rule changes.
RULE_TABLES = {'default': TABLE, 'h17': replace(TABLE, s17=False),
               'no-das': replace(TABLE, das=False)}
TOLERANCE = two_hand.TOLERANCE
RANKS = two_hand.RANKS
PAIRS = two_hand.PAIRS
UPCARDS = RANKS[1:] + RANKS[:1]
ACE = RANK_INDEX['A']
#: Option order at a hand node, as in the two hand study.
OPTIONS = (STAND, HIT, DOUBLE)
#: Document tables by name: the gap to the lower bound, and the default's own play.
TABLES = ('bound', 'own-play')


def table_name(rules):
    """The option name of a study table, or None for any other rules."""
    return next((name for name, known in RULE_TABLES.items() if known == rules), None)


def results_path(name='default'):
    """The saved results of one study table."""
    if name == 'default':
        return RESULTS
    return ROOT / f'docs/resplit-study-{name}-results.json'


def two_hand_table(rules):
    """The two hand study's table for these rules: the same, with two hands."""
    return replace(rules, max_hands=2)


def _minus(shoe, rank, count=1):
    return shoe[:rank] + (shoe[rank] - count,) + shoe[rank + 1:]


@lru_cache(maxsize=None)
def _policy_hit(total, soft, up, decide, value, s17):
    """A hand that has just hit, deciding from shoe `decide` and valued in shoe `value`.

    After a hit the default stands when standing beats hitting in its own shoe
    and hits otherwise, so a tie hits, the way `bj.ev._hit_ev` breaks it.
    """
    result = 0.0
    for rank, probability in enumerate(ev._draw_probs(value, up)):
        if probability <= 0.0:
            continue
        new_total, new_soft = ev._draw(total, soft, rank)
        if new_total > 21:
            result -= probability
            continue
        decide_next, value_next = remove_card(decide, rank), remove_card(value, rank)
        if new_total == 21:
            result += probability * ev._stand_ev(new_total, up, value_next, s17)
        elif (ev._stand_ev(new_total, up, decide_next, s17)
              > ev._hit_ev(new_total, new_soft, up, decide_next, s17)):
            result += probability * ev._stand_ev(new_total, up, value_next, s17)
        else:
            result += probability * _policy_hit(new_total, new_soft, up, decide_next,
                                                value_next, s17)
    return result


class DefaultResplit:
    """The default's split play for one pair, upcard and shoe.

    `shoe` excludes both pair cards and the upcard and holds the hidden hole,
    as everywhere in `bj.ev`. A split hand at depth d is one that d resplits
    lie above. The default gives it the shoe at the split minus d pair cards,
    and it plays every choice from that shoe minus its own later cards.

    `shared_shoe_value()` assumes that no hand and no dealer can run out of
    cards. A six deck shoe cannot. The tests check it against a deal by deal
    enumeration on small shoes that cannot run out either.
    """

    def __init__(self, pair, up, shoe, rules=TABLE):
        self.pair = RANK_INDEX[pair]
        self.up = up
        self.shoe = tuple(int(count) for count in shoe)
        self.rules = rules
        self.flags = (rules.s17, rules.das, rules.hit_split_aces, rules.resplit_aces)
        self.pool = ev._split_pool(rules, 1)
        if shoe_size(self.shoe) < 3:
            raise ValueError('splitting requires two drawable cards plus the dealer hole card')
        self._leaves = {}

    def start(self, depth):
        """The shoe the default gives a split hand at this depth."""
        return _minus(self.shoe, self.pair, depth)

    def resplits(self, depth, slots):
        """Whether the default resplits a hand at this depth that draws a pair card.

        This repeats the comparison in `bj.ev._split_hand_outcomes`: resplit
        when the two new hands are worth more than the pair played on, both
        valued in the default's own shoes.
        """
        rules, pair, up = self.rules, self.pair, self.up
        sub = self.start(depth + 1)
        if not (slots >= 1 and shoe_size(sub) >= 3 and (rules.resplit_aces or pair != ACE)):
            return False
        total, soft = ev._two_card_state(pair, pair)
        play = ev._stand_ev(total, up, sub, rules.s17)
        if not (pair == ACE and not rules.hit_split_aces):
            play = max(play, ev._hit_ev(total, soft, up, sub, rules.s17))
            if rules.das:
                play = max(play, ev._double_ev(total, soft, up, sub, rules.s17))
        value = 0.0
        for used, chance, first in ev._split_hand_outcomes(pair, up, sub, slots - 1,
                                                           *self.flags):
            for _, other, second in ev._split_hand_outcomes(pair, up, sub,
                                                            slots - 1 - used, *self.flags):
                value += chance * other * (first + second)
        return value > play

    def action(self, depth, card):
        """The default's choice for a split hand holding the pair card and `card`."""
        rules, up = self.rules, self.up
        total, soft = ev._two_card_state(self.pair, card)
        if total == 21 or (self.pair == ACE and not rules.hit_split_aces):
            return STAND
        decide = _minus(self.start(depth), card)
        best, choice = ev._stand_ev(total, up, decide, rules.s17), STAND
        hit = ev._hit_ev(total, soft, up, decide, rules.s17)
        if hit > best:
            best, choice = hit, HIT
        if rules.das and ev._double_ev(total, soft, up, decide, rules.s17) > best:
            choice = DOUBLE
        return choice

    def leaf(self, depth, card, value):
        """A hand at this depth holding the pair card and `card`, valued in shoe `value`.

        `value` already excludes `card`. The hand decides from the default's
        shoe and settles in `value`.
        """
        key = (depth, card, value)
        if key not in self._leaves:
            rules, up = self.rules, self.up
            total, soft = ev._two_card_state(self.pair, card)
            choice = self.action(depth, card)
            if choice == STAND:
                result = ev._stand_ev(total, up, value, rules.s17)
            elif choice == DOUBLE:
                result = ev._double_ev(total, soft, up, value, rules.s17)
            else:
                decide = _minus(self.start(depth), card)
                result = _policy_hit(total, soft, up, decide, value, rules.s17)
            self._leaves[key] = result
        return self._leaves[key]

    def default_value(self):
        """The default's own split value, rebuilt from the choices above.

        Every hand is valued in the shoe the default gives it and the second of
        two hands receives the slots the first left over. The tests compare
        this with `bj.ev.ev_split`, which shows the choices are the default's.
        """
        def hand(depth, slots):
            start = self.start(depth)
            rows = {}
            for card, chance in enumerate(ev._draw_probs(start, self.up)):
                if chance <= 0.0:
                    continue
                if card == self.pair and self.resplits(depth, slots):
                    for used_a, p_a, v_a in hand(depth + 1, slots - 1):
                        for used_b, p_b, v_b in hand(depth + 1, slots - 1 - used_a):
                            row = rows.setdefault(1 + used_a + used_b, [0.0, 0.0])
                            row[0] += chance * p_a * p_b
                            row[1] += chance * p_a * p_b * (v_a + v_b)
                else:
                    row = rows.setdefault(0, [0.0, 0.0])
                    row[0] += chance
                    row[1] += chance * self.leaf(depth, card, _minus(start, card))
            return [(used, p, w / p) for used, (p, w) in sorted(rows.items())]

        total = 0.0
        for used, chance, first in hand(0, self.pool):
            second = math.fsum(p * v for _, p, v in hand(0, self.pool - used))
            total += chance * (first + second)
        return total

    def shared_shoe_value(self, leaf=None):
        """The same choices with every hand dealt from one shared shoe.

        Hands are dealt in table order: a resplit's two new hands come before
        any older hand still waiting. `leaf(depth, card, shoe)` defaults to the
        settled value of a hand. Passing a function that returns 1 counts hands.

        The walk follows first cards only. `k` counts the pair cards removed so
        far and `weight` carries the sign of the expansion described in the
        module notes.
        """
        leaf = leaf or self.leaf
        terms = []

        def walk(waiting, slots, k, weight):
            if not waiting:
                return
            depth, rest = waiting[0], waiting[1:]
            shoe = _minus(self.shoe, self.pair, k)
            draws = ev._draw_probs(shoe, self.up)
            pair = draws[self.pair]
            for card, chance in enumerate(draws):
                if card != self.pair and chance > 0.0:
                    terms.append(weight * chance * leaf(depth, card, _minus(shoe, card)))
            # The rest of the round after a first card that is not a pair card.
            walk(rest, slots, k, weight)
            if pair > 0.0:
                walk(rest, slots, k + 1, -weight * pair)
                if self.resplits(depth, slots):
                    walk((depth + 1, depth + 1) + rest, slots - 1, k + 1, weight * pair)
                else:
                    terms.append(weight * pair * leaf(depth, self.pair,
                                                      _minus(shoe, self.pair)))
                    walk(rest, slots, k + 1, weight * pair)

        walk((0, 0), self.pool, 0, 1.0)
        return math.fsum(terms)

    def default_hands(self):
        """Expected number of hands in the default's own accounting."""
        def used(depth, slots):
            start = self.start(depth)
            rows = {}
            for card, chance in enumerate(ev._draw_probs(start, self.up)):
                if chance <= 0.0:
                    continue
                if card == self.pair and self.resplits(depth, slots):
                    for used_a, p_a in used(depth + 1, slots - 1):
                        for used_b, p_b in used(depth + 1, slots - 1 - used_a):
                            key = 1 + used_a + used_b
                            rows[key] = rows.get(key, 0.0) + chance * p_a * p_b
                else:
                    rows[0] = rows.get(0, 0.0) + chance
            return sorted(rows.items())

        total = 2.0
        for first, chance in used(0, self.pool):
            total += chance * (first + math.fsum(p * n for n, p in used(0, self.pool - first)))
        return total

    def shared_shoe_hands(self):
        """Expected number of hands when the same play is dealt from one shoe."""
        return self.shared_shoe_value(lambda depth, card, shoe: 1.0)


def clear_caches():
    _policy_hit.cache_clear()
    ev.clear_caches()


# --- the study ---------------------------------------------------------------

def _ranking(values):
    """Actions within rounding of the best, in S, H, D, P order, and the margin."""
    ordered = sorted(values.values(), reverse=True)
    best = [action for action in OPTIONS + (SPLIT,)
            if action in values and ordered[0] - values[action] <= TOLERANCE]
    return best, ordered[0] - ordered[1]


def two_hand_cells(path=TWO_HAND_RESULTS, rules=TABLE):
    saved = json.loads(Path(path).read_text(encoding='utf-8'))
    if saved['rules'] != asdict(two_hand_table(rules)):
        raise ValueError(f'{path} does not hold the two hand table for these rules')
    return {(cell['pair'], cell['up']): cell for cell in saved['cells']}


def study_cell(pair, up, two_hand_cell, rules=TABLE):
    """One cell of the study on a fresh shoe minus the pair and the upcard."""
    if table_name(rules) is None:
        raise ValueError('the study covers the default table and its H17 and no DAS '
                         'variants only')
    shoe = ev.initial_shoe_for((pair, pair), up, rules)
    if (two_hand_cell['pair'], two_hand_cell['up'], two_hand_cell['shoe']) != (
            pair, up, list(shoe)):
        raise ValueError(f'the two hand cell does not hold {pair},{pair} against {up}')
    default = ev.ev_split(pair, up, shoe, rules)
    model = DefaultResplit(pair, up, shoe, rules)
    own_play = model.shared_shoe_value()
    # The three hand default's play is legal here too. It never takes a fourth hand.
    three = DefaultResplit(pair, up, shoe, replace(rules, max_hands=3)).shared_shoe_value()
    two = two_hand_cell['common_shoe_split']
    bounds = {'default play': own_play, 'three hand play': three, 'two hand': two}
    source = max(bounds, key=bounds.get)
    bound = bounds[source]
    _, others, _ = ev.best_action((pair, pair), up, shoe, rules, can_split=False)
    default_best, default_margin = _ranking({**others, SPLIT: default})
    bound_best, bound_margin = _ranking({**others, SPLIT: bound})
    return dict(
        pair=pair, up=up, shoe=list(shoe),
        default_split=default,
        default_rebuilt=model.default_value(),
        default_play_in_common_shoe=own_play,
        three_hand_play_in_common_shoe=three,
        two_hand_common_shoe_split=two,
        common_shoe_lower_bound=bound,
        lower_bound_source=source,
        difference=default - bound,
        default_policy_difference=own_play - default,
        default_hands=model.default_hands(),
        common_shoe_hands=model.shared_shoe_hands(),
        other_actions=others,
        default_best=default_best, default_margin=default_margin,
        lower_bound_best=bound_best, lower_bound_margin=bound_margin,
        decision_changed=default_best != bound_best,
        split_shortfall=max(others.values()) - bound,
    )


def summarize(cells):
    worst = min(cells, key=lambda cell: cell['difference'])
    excess = max(cells, key=lambda cell: cell['difference'])
    gain = max(cells, key=lambda cell: cell['default_policy_difference'])
    trailing = [cell for cell in cells if SPLIT not in cell['lower_bound_best']]
    closest = min(trailing, key=lambda cell: cell['split_shortfall'], default=None)
    return dict(
        cells=len(cells),
        worst=dict(pair=worst['pair'], up=worst['up'], difference=worst['difference']),
        within_tolerance=sum(abs(c['difference']) <= TOLERANCE for c in cells),
        default_above_lower_bound=sum(c['difference'] > TOLERANCE for c in cells),
        largest_default_excess=dict(pair=excess['pair'], up=excess['up'],
                                    difference=excess['difference']),
        largest_own_play_gain=dict(pair=gain['pair'], up=gain['up'],
                                   difference=gain['default_policy_difference']),
        own_play_above_default=sum(c['default_policy_difference'] > TOLERANCE for c in cells),
        own_play_below_default=sum(c['default_policy_difference'] < -TOLERANCE for c in cells),
        largest_own_play_shortfall=-min(c['default_policy_difference'] for c in cells),
        largest_rebuild_difference=max(abs(c['default_rebuilt'] - c['default_split'])
                                       for c in cells),
        resplitting_cells=sum(c['default_hands'] > 2.0 for c in cells),
        decision_changes=[f"{c['pair']},{c['pair']} vs {c['up']}" for c in cells
                          if c['decision_changed']],
        # None when split is the best action in every cell, as for A,A alone.
        closest_split_shortfall=None if closest is None else dict(
            pair=closest['pair'], up=closest['up'], shortfall=closest['split_shortfall']),
    )


def _revision(two_hand_path=TWO_HAND_RESULTS):
    try:
        head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
        dirty = subprocess.run(['git', 'status', '--porcelain', '--', *SOURCE_FILES,
                                Path(two_hand_path).resolve().relative_to(ROOT).as_posix()],
                               cwd=ROOT,
                               capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None, None
    return head, bool(dirty)


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def run_study(pairs=PAIRS, upcards=UPCARDS, progress=None, two_hand_path=None, rules=TABLE):
    started = time.perf_counter()
    if two_hand_path is None:
        two_hand_path = two_hand.results_path(table_name(rules) or 'default')
    reference = two_hand_cells(two_hand_path, rules)
    cells = []
    for pair in pairs:
        for up in upcards:
            cells.append(study_cell(pair, up, reference[(pair, up)], rules))
            if progress:
                progress(cells[-1])
        clear_caches()
    revision, dirty = _revision(two_hand_path)
    return dict(
        schema_version=1,
        study='split_error_resplit_four_hands',
        rules=asdict(rules),
        tolerance=TOLERANCE,
        two_hand_results=Path(two_hand_path).resolve().relative_to(ROOT).as_posix(),
        two_hand_results_sha256_lf=_sha256(two_hand_path),
        evaluated_revision=revision,
        evaluated_sources_modified=dirty,
        source_sha256_lf={name: _sha256(ROOT / name) for name in SOURCE_FILES},
        python=platform.python_version(),
        platform=platform.platform(),
        elapsed_seconds=time.perf_counter() - started,
        summary=summarize(cells),
        cells=cells,
    )


def table_markers(table='bound', name='default'):
    """The comment lines that fence one table's rendering in the document."""
    key = table if name == 'default' else f'{name}-{table}'
    return (f'<!-- resplit-table-{key}:begin -->', f'<!-- resplit-table-{key}:end -->')


def render_table(results, table='bound'):
    """The document table: the gap to the lower bound, or the own play gain."""
    field = 'difference' if table == 'bound' else 'default_policy_difference'
    by_cell = {(c['pair'], c['up']): c for c in results['cells']}
    lines = ['| Pair | ' + ' | '.join(UPCARDS) + ' |',
             '|:---|' + '---:|' * len(UPCARDS)]
    for pair in PAIRS:
        row = [two_hand._entry(by_cell[(pair, up)][field]) for up in UPCARDS]
        lines.append(f'| {pair},{pair} | ' + ' | '.join(row) + ' |')
    return '\n'.join(lines)


def document_table(text, table='bound', name='default'):
    begin, end = table_markers(table, name)
    start = text.index(begin) + len(begin)
    return text[start:text.index(end)].strip()


def compare(saved, fresh):
    """Differences between a saved study and a recomputation, as messages."""
    problems = []
    fresh_cells = {(c['pair'], c['up']): c for c in fresh['cells']}
    for cell in saved['cells']:
        other = fresh_cells.get((cell['pair'], cell['up']))
        if other is None:
            problems.append(f"{cell['pair']} vs {cell['up']}: not recomputed")
            continue
        for name, value in cell.items():
            if isinstance(value, float):
                if not abs(value - other[name]) <= TOLERANCE:
                    problems.append(f"{cell['pair']} vs {cell['up']}: {name} "
                                    f"{value!r} became {other[name]!r}")
            elif name == 'other_actions':
                for action, number in value.items():
                    if not abs(number - other[name][action]) <= TOLERANCE:
                        problems.append(f"{cell['pair']} vs {cell['up']}: {action} moved")
            elif value != other[name]:
                problems.append(f"{cell['pair']} vs {cell['up']}: {name} "
                                f"{value!r} became {other[name]!r}")
    if len(fresh['cells']) != len(saved['cells']):
        problems.append('the recomputation has a different number of cells')
    return problems


def check(results_path=RESULTS, document_path=DOCUMENT, progress=None):
    saved = json.loads(Path(results_path).read_text(encoding='utf-8'))
    rules = Rules(**saved['rules'])
    name = table_name(rules)
    if name is None:
        return ['the saved rules are not a table this study covers']
    two_hand_path = two_hand.results_path(name)
    problems = []
    if _sha256(two_hand_path) != saved['two_hand_results_sha256_lf']:
        problems.append('the two hand results changed since this study was saved')
    if summarize(saved['cells']) != saved['summary']:
        problems.append('the saved summary does not follow from the saved cells')
    document = Path(document_path).read_text(encoding='utf-8')
    for table in TABLES:
        if document_table(document, table, name) != render_table(saved, table):
            problems.append(f'the document table {table} does not match the saved cells')
    fresh = run_study(pairs=tuple(dict.fromkeys(c['pair'] for c in saved['cells'])),
                      upcards=tuple(dict.fromkeys(c['up'] for c in saved['cells'])),
                      progress=progress, two_hand_path=two_hand_path, rules=rules)
    problems.extend(compare(saved, fresh))
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--output', type=Path, help='write a new results file here')
    action.add_argument('--check', action='store_true',
                        help='recompute every saved cell and compare it with the saved study')
    parser.add_argument('--table', choices=sorted(RULE_TABLES), default='default',
                        help='default is the default table; h17 and no-das change one rule')
    parser.add_argument('--results', type=Path,
                        help="saved results to check, by default the table's own file")
    args = parser.parse_args(argv)

    def report(cell):
        print(f"{cell['pair']},{cell['pair']} vs {cell['up']}: "
              f"difference {cell['difference']:.6e}, "
              f"own play {cell['default_policy_difference']:.6e}", flush=True)

    if args.output:
        if args.output.exists():
            parser.error(f'{args.output} exists. Choose a new path.')
        results = run_study(progress=report, rules=RULE_TABLES[args.table])
        args.output.write_text(json.dumps(results, indent=1) + '\n', encoding='utf-8')
        print(f"worst {results['summary']['worst']}")
        return 0
    path = args.results or results_path(args.table)
    saved_rules = Rules(**json.loads(path.read_text(encoding='utf-8'))['rules'])
    if table_name(saved_rules) != args.table:
        parser.error(f'{path} does not hold the {args.table} table')
    problems = check(path, progress=report)
    for problem in problems:
        print(problem)
    print('check passed' if not problems else f'check failed with {len(problems)} problems')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
