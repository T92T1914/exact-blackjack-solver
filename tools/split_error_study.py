"""Measure the default split value against the two hand common shoe value.

The study covers every pair against every upcard with two hands and no resplit,
on the six deck table and on two variants of it: the dealer hitting soft 17 and
no double after split. For each cell it records the default independent split
value from `bj.ev`, the two hand common shoe value and their difference.

`bj.joint_split` is the bounded reference for the common shoe model. It accepts
at most twenty unseen cards, and a six deck shoe holds 309 after the split. This
script evaluates the same model at full size. The first hand can end in a few
thousand card multisets, and the second hand plays the same tree after each of
them, so the second hand is solved for every first hand ending at once with
numpy. The dealer distribution is computed once for every distinct shoe that
both hands can leave behind.

The tests compare this evaluator with `bj.joint_split` on small shoes and its
dealer with `bj.dealer` on the full shoe. Arithmetic is binary64. A refused
continuation becomes NaN, and NaN reaches the result only through a
continuation the model admits, so this evaluator refuses the shoes the bounded
reference refuses.

    python tools/split_error_study.py --output docs/split-error-study-results.json
    python tools/split_error_study.py --check
    python tools/split_error_study.py --table h17 --check
    python tools/split_error_study.py --table no-das --check
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
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bj import ev  # noqa: E402
from bj.common_shoe import SPLIT_MODEL  # noqa: E402
from bj.core import DOUBLE, HIT, STAND, SPLIT, Rules  # noqa: E402

RESULTS = ROOT / 'docs/split-error-study-results.json'
DOCUMENT = ROOT / 'docs/split-error-study.md'
SOURCE_FILES = ('tools/split_error_study.py', 'bj/ev.py', 'bj/dealer.py', 'bj/core.py')
#: Six decks, S17, DAS, peek, one card to split aces, two hands and no resplit.
TABLE = Rules(max_hands=2)
#: The same table with the dealer hitting soft 17.
H17 = Rules(max_hands=2, s17=False)
#: The same table with no double after split.
NO_DAS = Rules(max_hands=2, das=False)
#: Study tables by option name. Each has its own saved results and document table.
TABLES = {'default': TABLE, 'h17': H17, 'no-das': NO_DAS}
#: Differences this small print as 0, and actions this close share a rank.
#: Rounding alone stays near 1e-15 here, so a smaller real gain can hide below it.
TOLERANCE = 1e-12

#: Production rank order, the same as `bj.core.RANKS`.
RANKS = ('A', '2', '3', '4', '5', '6', '7', '8', '9', 'T')
PAIRS = ('A', 'T', '9', '8', '7', '6', '5', '4', '3', '2')
HARD = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
ACE, TEN = 0, 9
#: Each rank count takes six bits of a multiset key, so keys add like counts.
BITS = 6
FIELD = (1 << BITS) - 1
UNIT = tuple(1 << (BITS * r) for r in range(10))
#: Dealer outcome columns: final 17, 18, 19, 20, 21, then bust, as in `bj.dealer`.
BUST = 5
#: Union shoes per dealer batch. This bounds memory and does not change a value.
DEALER_BATCH = 1 << 16
#: Option order at a player node.
OPTIONS = (STAND, HIT, DOUBLE)


class UnsupportedShoeError(ValueError):
    """An admitted continuation needs a card the supplied shoe cannot provide."""


@dataclass(frozen=True)
class StudyValue:
    value: float
    hand_nodes: int
    first_hand_endings: int
    union_shoes: int
    dealer_nodes: int


def results_path(table='default'):
    """The saved results of one study table."""
    if table == 'default':
        return RESULTS
    return ROOT / f'docs/split-error-study-{table}-results.json'


def table_markers(table='default'):
    """The comment lines that fence one table's rendering in the document."""
    suffix = '' if table == 'default' else f'-{table}'
    return (f'<!-- split-error-table{suffix}:begin -->',
            f'<!-- split-error-table{suffix}:end -->')


def table_name(rules):
    """The option name of a study table, or None for any other rules."""
    return next((name for name, known in TABLES.items() if known == rules), None)


def _key(counts):
    return sum(c << (BITS * r) for r, c in enumerate(counts))


def _decode(keys):
    shifts = np.arange(10, dtype=np.int64) * BITS
    return (keys[:, None] >> shifts) & FIELD


def _total(base, counts):
    """Best total for one starting card plus drawn counts, and whether it is soft."""
    low = HARD[base] + sum(c * HARD[r] for r, c in enumerate(counts))
    soft = (base == ACE or counts[ACE] > 0) and low + 10 <= 21
    return low + (10 if soft else 0), soft


def _excluded(up):
    """The hole rank a completed negative peek rules out, or -1."""
    return TEN if up == ACE else ACE if up == TEN else -1


def _payoff(total, wager):
    """Settlement against each dealer outcome column in original wager units."""
    if total > 21:
        return np.full(6, -float(wager))
    row = [wager * ((total > dealer) - (total < dealer)) for dealer in range(17, 22)]
    return np.array(row + [wager], dtype=float)


def _draw_rows(unseen, cards, excluded):
    """Player draw probabilities after the peek, and the rows that cannot draw.

    `unseen` holds the hidden hole. The hole is uniform over the eligible unseen
    cards, so P(next is r) = (S[r] - w_r) / (n - 1) with w_r = S[r] / eligible
    for an eligible rank and 0 for the excluded rank.
    """
    eligible = cards - (unseen[:, excluded] if excluded >= 0 else 0.0)
    refused = (eligible <= 0) | (cards - 1 <= 0)
    with np.errstate(divide='ignore', invalid='ignore'):
        hole = unseen / eligible[:, None]
        if excluded >= 0:
            hole[:, excluded] = 0.0
        probabilities = (unseen - hole) / (cards - 1)[:, None]
    return probabilities, refused


class _Hands:
    """Every multiset of cards one split hand can draw from this shoe, by depth."""

    def __init__(self, pair, shoe):
        self.levels = []
        self.counts = {}
        self.total = {}
        self.soft = {}
        self.internal = {}
        level = {}
        for r in range(10):
            if shoe[r] >= 1:
                counts = tuple(int(r == j) for j in range(10))
                level[_key(counts)] = counts
        while level:
            self.levels.append(tuple(sorted(level)))
            following = {}
            for key, counts in level.items():
                self.counts[key] = counts
                self.total[key], self.soft[key] = _total(pair, counts)
                # Split aces take one card. A hand at 21 or more is complete.
                self.internal[key] = pair != ACE and self.total[key] < 21
                if self.internal[key]:
                    for r in range(10):
                        if counts[r] < shoe[r]:
                            child = counts[:r] + (counts[r] + 1,) + counts[r + 1:]
                            following[key + UNIT[r]] = child
            level = following

    def children(self, key):
        return [(r, key + UNIT[r]) for r in range(10) if key + UNIT[r] in self.counts]

    def __len__(self):
        return len(self.counts)


def _dealer_outcome(up, drawn, stand_soft_17):
    """Outcome column for a finished dealer, or None while the dealer draws."""
    if not drawn:
        return None
    counts = [0] * 10
    for r in drawn:
        counts[r] += 1
    total, soft = _total(up, counts)
    if total > 21:
        return BUST
    if total > 17 or (total == 17 and (stand_soft_17 or not soft)):
        return total - 17
    return None


class _DealerGraph:
    """Dealer card multisets that still draw, grouped by the number of cards drawn."""

    def __init__(self, up, stand_soft_17):
        self.levels = []
        self.edges = {}
        level = [()]
        while level:
            self.levels.append(level)
            following = set()
            for drawn in level:
                edges = []
                for r in range(10):
                    child = tuple(sorted(drawn + (r,)))
                    column = _dealer_outcome(up, child, stand_soft_17)
                    edges.append((r, drawn.count(r), child, column))
                    if column is None:
                        following.add(child)
                self.edges[drawn] = edges
            level = sorted(following)
        self.size = len(self.edges)


def _dealer_rows(up, shoe, unions, graph):
    """Post peek dealer outcome probabilities for every union shoe.

    The hole is the first dealer card and never the excluded rank. A row is NaN
    when a reached dealer state needs a card the shoe cannot supply, or when no
    hole is possible.
    """
    excluded = _excluded(up)
    rows = np.empty((len(unions), 6))
    for start in range(0, len(unions), DEALER_BATCH):
        used = _decode(unions[start:start + DEALER_BATCH])
        unseen = np.asarray(shoe, dtype=float)[None, :] - used
        cards = unseen.sum(axis=1)
        eligible = cards - (unseen[:, excluded] if excluded >= 0 else 0.0)
        bad = eligible <= 0
        result = np.zeros((len(unseen), 6))
        masses = {}
        for depth, level in enumerate(graph.levels):
            remaining = cards - depth
            denominator = eligible if depth == 0 else remaining
            following = {}
            for drawn in level:
                mass = masses.pop(drawn, None) if depth else 1.0
                if mass is None:
                    continue
                if depth:
                    bad |= (mass > 0) & (remaining <= 0)
                for r, taken, child, column in graph.edges[drawn]:
                    if depth == 0 and r == excluded:
                        continue
                    available = unseen[:, r] - taken
                    with np.errstate(divide='ignore', invalid='ignore'):
                        weight = mass * np.where((available > 0) & (denominator > 0),
                                                 available / denominator, 0.0)
                    if column is not None:
                        result[:, column] += weight
                    elif child in following:
                        following[child] += weight
                    else:
                        following[child] = weight
            masses = following
        result[bad] = np.nan
        rows[start:start + len(unseen)] = result
    return rows


def _unions(shoe, hands):
    """Sorted keys of every card multiset the two hands can remove together."""
    keys = np.array(sorted(hands.counts), dtype=np.int64)
    limit = np.asarray(shoe, dtype=np.int64)
    found = []
    for start in range(0, len(keys), 512):
        sums = np.unique((keys[start:start + 512, None] + keys[None, :]).ravel())
        found.append(sums[(_decode(sums) <= limit).all(axis=1)])
    return np.unique(np.concatenate(found))


def _choose(options, choice):
    """The chosen option, or the maximum, with any refused option refusing the node."""
    stacked = np.vstack(options)
    refused = np.isnan(stacked).any(axis=0)
    chosen = stacked.max(axis=0) if choice is None else stacked[choice]
    return np.where(refused, np.nan, chosen)


class TwoHandSplit:
    """The two hand common shoe split for one pair, upcard and shoe.

    The model is `bj.joint_split`'s, in production rank order A, 2 to 9, T.
    `shoe` excludes both pair cards and the upcard and holds the hidden hole.
    The first hand finishes before the second takes its card, both settle
    against one dealer, split aces take one card, and there is no resplit or
    surrender. `value()` chooses each action on the combined round value.
    `value(policy)` instead plays a fixed action at each hand node and still
    settles both hands in the common shoe.
    """

    def __init__(self, pair, up, shoe, *, double_after_split=True, stand_soft_17=True):
        self.pair, self.up = RANKS.index(pair), RANKS.index(up)
        self.shoe = tuple(int(c) for c in shoe)
        if len(self.shoe) != 10 or any(c < 0 for c in self.shoe):
            raise ValueError('shoe must contain ten nonnegative counts')
        if sum(self.shoe) < 3:
            raise ValueError('a split needs two drawable cards and the hidden hole')
        self.das = bool(double_after_split)
        self.excluded = _excluded(self.up)
        self.hands = _Hands(self.pair, self.shoe)
        self.dealer_graph = _DealerGraph(self.up, bool(stand_soft_17))

        # First hand endings: every node standing or complete, and every double.
        # Two second cards can reach the same doubled multiset, so keep one row each.
        endings = dict.fromkeys((key, 1) for key in self.hands.counts)
        if self.das and self.hands.levels:
            for key in self.hands.levels[0]:
                if self.hands.internal[key]:
                    endings.update(dict.fromkeys(
                        (child, 2) for _, child in self.hands.children(key)))
        endings = list(endings)
        self.endings = endings
        self.first_keys = np.array([key for key, _ in endings], dtype=np.int64)
        self.first_wagers = np.array([wager for _, wager in endings], dtype=float)
        totals = [self.hands.total[key] for key, _ in endings]
        self.first_payoffs = np.array([_payoff(t, w) for t, w in zip(totals, self.first_wagers)])
        self.first_bust = np.array(totals) > 21
        self.unions = _unions(self.shoe, self.hands)
        self.dealer = _dealer_rows(self.up, self.shoe, self.unions, self.dealer_graph)

    def diagnostics(self, value):
        return StudyValue(value, len(self.hands), len(self.endings), len(self.unions),
                          self.dealer_graph.size)

    def _settle(self, key, wager):
        """Combined settlement of every first hand ending with this second hand."""
        total = self.hands.total[key]
        query = self.first_keys + key
        index = np.minimum(np.searchsorted(self.unions, query), len(self.unions) - 1)
        found = self.unions[index] == query
        outcome = np.where(found[:, None], self.dealer[index], np.nan)
        value = (outcome * (self.first_payoffs + _payoff(total, wager))).sum(axis=1)
        if total > 21:
            # Both hands lost. The bounded reference settles this without a dealer.
            value = np.where(self.first_bust, -(self.first_wagers + wager), value)
        return value

    def _second_hand(self, policy):
        """Second hand values for every first hand ending, deepest level first."""
        first_unseen = np.asarray(self.shoe, dtype=float)[None, :] - _decode(self.first_keys)
        first_cards = first_unseen.sum(axis=1)
        deeper = {}
        with np.errstate(invalid='ignore'):
            for depth in range(len(self.hands.levels) - 1, -1, -1):
                current = {}
                for key in self.hands.levels[depth]:
                    stand = self._settle(key, 1)
                    if not self.hands.internal[key]:
                        current[key] = stand
                        continue
                    unseen = first_unseen - np.asarray(self.hands.counts[key], dtype=float)
                    p, refused = _draw_rows(unseen, first_cards - (depth + 1), self.excluded)
                    hit = np.zeros(len(self.endings))
                    double = np.zeros(len(self.endings)) if self.das and depth == 0 else None
                    for r, child in self.hands.children(key):
                        live = p[:, r] > 0
                        hit += np.where(live, p[:, r] * deeper[child], 0.0)
                        if double is not None:
                            double += np.where(live, p[:, r] * self._settle(child, 2), 0.0)
                    options = [stand, np.where(refused, np.nan, hit)]
                    if double is not None:
                        options.append(np.where(refused, np.nan, double))
                    current[key] = _choose(options, None if policy is None else policy[key])
                deeper = current
            p, refused = _draw_rows(first_unseen, first_cards, self.excluded)
            second = np.zeros(len(self.endings))
            for r in range(10):
                if UNIT[r] in deeper:
                    second += np.where(p[:, r] > 0, p[:, r] * deeper[UNIT[r]], 0.0)
        return dict(zip(self.endings, np.where(refused, np.nan, second).tolist()))

    def _draws(self, counts):
        unseen = np.asarray(self.shoe, dtype=float)[None, :] - np.asarray(counts, dtype=float)
        p, refused = _draw_rows(unseen, unseen.sum(axis=1), self.excluded)
        return p[0], bool(refused[0])

    @staticmethod
    def _expect(p, refused, values):
        if refused:
            return math.nan
        return math.fsum(p[r] * value for r, value in values if p[r] > 0)

    def value(self, policy=None):
        """Split value in original wager units, optimal or under a fixed policy."""
        ending = self._second_hand(policy)
        deeper = {}
        for depth in range(len(self.hands.levels) - 1, -1, -1):
            current = {}
            for key in self.hands.levels[depth]:
                stand = ending[(key, 1)]
                if not self.hands.internal[key]:
                    current[key] = stand
                    continue
                p, refused = self._draws(self.hands.counts[key])
                children = self.hands.children(key)
                options = [stand, self._expect(p, refused, [(r, deeper[c]) for r, c in children])]
                if self.das and depth == 0:
                    options.append(self._expect(p, refused,
                                                [(r, ending[(c, 2)]) for r, c in children]))
                if any(map(math.isnan, options)):
                    current[key] = math.nan
                else:
                    current[key] = max(options) if policy is None else options[policy[key]]
            deeper = current
        p, refused = self._draws((0,) * 10)
        value = self._expect(p, refused, [(r, deeper[UNIT[r]]) for r in range(10)
                                          if UNIT[r] in deeper])
        if math.isnan(value):
            raise UnsupportedShoeError('an admitted continuation needs an unavailable card')
        return value


def common_shoe_two_hand_split(pair, up, shoe, *, double_after_split=True,
                               stand_soft_17=True):
    """Optimal two hand common shoe split value with the size of its enumeration."""
    model = TwoHandSplit(pair, up, shoe, double_after_split=double_after_split,
                         stand_soft_17=stand_soft_17)
    return model.diagnostics(model.value())


def default_policy(model, rules):
    """The action the default solver takes at each hand node, from its own shoe.

    The default values each split hand against the shoe at the split minus that
    hand's own cards. This returns that choice at every node where play continues,
    as an index into stand, hit and double. Ties break the way `bj.ev` breaks
    them: toward standing on two cards and toward hitting after a hit.
    """
    up = RANKS[model.up]
    policy = {}
    for depth, level in enumerate(model.hands.levels):
        for key in level:
            if not model.hands.internal[key]:
                continue
            counts = model.hands.counts[key]
            shoe = tuple(c - k for c, k in zip(model.shoe, counts))
            total, soft = model.hands.total[key], model.hands.soft[key]
            stand = ev._stand_ev(total, up, shoe, rules.s17)
            hit = ev._hit_ev(total, soft, up, shoe, rules.s17)
            if depth:
                policy[key] = 0 if stand > hit else 1
                continue
            best, choice = (hit, 1) if hit > stand else (stand, 0)
            if rules.das and ev._double_ev(total, soft, up, shoe, rules.s17) > best:
                choice = 2
            policy[key] = choice
    return policy


# --- the study ---------------------------------------------------------------

def _ranking(values):
    """Actions within rounding of the best, in S, H, D, P order, and the margin."""
    ordered = sorted(values.values(), reverse=True)
    best = [action for action in OPTIONS + (SPLIT,)
            if action in values and ordered[0] - values[action] <= TOLERANCE]
    return best, ordered[0] - ordered[1]


def study_cell(pair, up, rules=TABLE):
    """One cell of the study on a fresh shoe minus the pair and the upcard."""
    if rules.max_hands != 2 or rules.resplit_aces or rules.hit_split_aces:
        # Otherwise the default would price resplits or drawing to split aces
        # that the common shoe model does not have.
        raise ValueError('the study compares two hands with no resplit and one card '
                         'to each split ace')
    shoe = ev.initial_shoe_for((pair, pair), up, rules)
    default = ev.ev_split(pair, up, shoe, rules)
    model = TwoHandSplit(pair, up, shoe, double_after_split=rules.das,
                         stand_soft_17=rules.s17)
    joint = model.value()
    policy_value = model.value(default_policy(model, rules))
    _, others, _ = ev.best_action((pair, pair), up, shoe, rules, can_split=False)
    default_best, default_margin = _ranking({**others, SPLIT: default})
    joint_best, joint_margin = _ranking({**others, SPLIT: joint})
    size = model.diagnostics(joint)
    return dict(
        pair=pair, up=up, shoe=list(shoe),
        default_split=default, common_shoe_split=joint,
        difference=default - joint,
        default_policy_in_common_shoe=policy_value,
        default_policy_difference=policy_value - default,
        other_actions=others,
        default_best=default_best, default_margin=default_margin,
        common_shoe_best=joint_best, common_shoe_margin=joint_margin,
        decision_changed=default_best != joint_best,
        hand_nodes=size.hand_nodes, first_hand_endings=size.first_hand_endings,
        union_shoes=size.union_shoes, dealer_nodes=size.dealer_nodes,
    )


def summarize(cells):
    worst = max(cells, key=lambda cell: abs(cell['difference']))
    return dict(
        cells=len(cells),
        worst=dict(pair=worst['pair'], up=worst['up'], difference=worst['difference']),
        mean_absolute_difference=math.fsum(abs(c['difference']) for c in cells) / len(cells),
        within_tolerance=sum(abs(c['difference']) <= TOLERANCE for c in cells),
        default_above_common_shoe=sum(c['difference'] > TOLERANCE for c in cells),
        largest_default_excess=max(c['difference'] for c in cells),
        largest_default_policy_difference=max(abs(c['default_policy_difference'])
                                              for c in cells),
        decision_changes=[f"{c['pair']},{c['pair']} vs {c['up']}" for c in cells
                          if c['decision_changed']],
    )


def _revision():
    try:
        head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
        dirty = subprocess.run(['git', 'status', '--porcelain', '--', *SOURCE_FILES], cwd=ROOT,
                               capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None, None
    return head, bool(dirty)


def _sources():
    return {name: hashlib.sha256((ROOT / name).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
            for name in SOURCE_FILES}


def run_study(pairs=PAIRS, upcards=RANKS[1:] + RANKS[:1], progress=None, rules=TABLE):
    started = time.perf_counter()
    cells = []
    for pair in pairs:
        for up in upcards:
            cells.append(study_cell(pair, up, rules))
            if progress:
                progress(cells[-1])
        ev.clear_caches()
    revision, dirty = _revision()
    return dict(
        schema_version=1,
        study='split_error_two_hand_no_resplit',
        common_shoe_model=SPLIT_MODEL,
        rules=asdict(rules),
        tolerance=TOLERANCE,
        evaluated_revision=revision,
        evaluated_sources_modified=dirty,
        source_sha256_lf=_sources(),
        python=platform.python_version(),
        numpy=np.__version__,
        platform=platform.platform(),
        elapsed_seconds=time.perf_counter() - started,
        summary=summarize(cells),
        cells=cells,
    )


def _entry(difference):
    """Three significant digits, with a true minus sign, or 0 within tolerance."""
    if abs(difference) <= TOLERANCE:
        return '0'
    mantissa, exponent = f'{difference:.2e}'.split('e')
    return f'{mantissa}e{int(exponent)}'.replace('-', '−')


def render_table(results):
    """The document's table of differences in original wager units."""
    by_cell = {(c['pair'], c['up']): c for c in results['cells']}
    upcards = RANKS[1:] + RANKS[:1]
    lines = ['| Pair | ' + ' | '.join(upcards) + ' |',
             '|:---|' + '---:|' * len(upcards)]
    for pair in PAIRS:
        row = [_entry(by_cell[(pair, up)]['difference']) for up in upcards]
        lines.append(f'| {pair},{pair} | ' + ' | '.join(row) + ' |')
    return '\n'.join(lines)


def document_table(text, table='default'):
    begin, end = table_markers(table)
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
    table = table_name(rules)
    if table is None:
        return ['the saved rules are not one of the study tables']
    problems = []
    if summarize(saved['cells']) != saved['summary']:
        problems.append('the saved summary does not follow from the saved cells')
    if document_table(Path(document_path).read_text(encoding='utf-8'), table) != render_table(saved):
        problems.append('the document table does not match the saved cells')
    fresh = run_study(pairs=tuple(dict.fromkeys(c['pair'] for c in saved['cells'])),
                      upcards=tuple(dict.fromkeys(c['up'] for c in saved['cells'])),
                      progress=progress, rules=rules)
    problems.extend(compare(saved, fresh))
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--output', type=Path, help='write a new results file here')
    action.add_argument('--check', action='store_true',
                        help='recompute every saved cell and compare it with the saved study')
    parser.add_argument('--table', choices=sorted(TABLES), default='default',
                        help='default is six decks, S17 and DAS; h17 and no-das change one rule')
    parser.add_argument('--results', type=Path,
                        help="saved results to check, by default the table's own file")
    args = parser.parse_args(argv)

    def report(cell):
        print(f"{cell['pair']},{cell['pair']} vs {cell['up']}: "
              f"difference {cell['difference']:.6e}", flush=True)

    if args.output:
        if args.output.exists():
            parser.error(f'{args.output} exists. Choose a new path.')
        results = run_study(progress=report, rules=TABLES[args.table])
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
