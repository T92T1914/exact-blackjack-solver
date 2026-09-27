"""Audit and render the saved matched comparison without invoking either solver."""
import argparse
import csv
import hashlib
import html
import io
import itertools
import json
import math
import subprocess

try:
    from .presentation import ROOT, FACES, TOKEN_REVISION, load_tokens
except ImportError:
    from presentation import ROOT, FACES, TOKEN_REVISION, load_tokens

DATA = 'docs/joint-split-results.json'
FIRST = 'docs/joint-split-first-invalid.json'
MEASURED = '9b8f54c85fe7689490503a8874e41f7d48b53127'
INVALID = '58330ad09985ad265d25cc3cb93069d2d09d7aa5'
# The authored interpretation belongs to these retained attempts only.
RESULT_SHA256_LF = 'eb5fe4047ceeafc4245d8b43354bb9f2d95d98525ff46fbcbd2613b9319aef4b'
FIRST_SHA256_LF = '4b7b24c8eee7a8a8a908e800ca1db89275c1ad50bfcae85b6050536f95cc7ded'
RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', 'T', 'A']
PRODUCTION_RANKS = ['A', '2', '3', '4', '5', '6', '7', '8', '9', 'T']
PALETTE = {'6': ('#365f78', '#b3c8d8'), 'T': ('#775419', '#e2c58a'),
           'A': ('#73558d', '#c9b9dc')}


def digest(path):
    return hashlib.sha256(path.read_text(encoding='utf-8').encode()).hexdigest()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def close(value, expected, reason):
    require(type(value) in (int, float) and math.isfinite(value)
            and math.isclose(value, expected, abs_tol=1e-12, rel_tol=0), reason)


def validate(data, protocol):
    require(data['evaluated_revision'] == MEASURED, 'not the corrected measured revision')
    require(data['protocol'] == protocol and protocol['rank_order'] == RANKS,
            'protocol identity differs')
    expected = list(itertools.product(protocol['unseen_shoes'], protocol['pair_ranks'],
                                     protocol['dealer_upcards'], protocol['double_after_split']))
    require(len(data['rows']) == len(expected) == 48, 'conditions were lost or duplicated')
    require(data['unattempted'] == [], 'unattempted conditions need an incomplete report')
    for row, (name, pair, up, das) in zip(data['rows'], expected, strict=True):
        require(row['id'] == f'{name}/{pair}/{up}/das-{str(das).lower()}'
                and row['shoe_name'] == name and row['pair'] == pair
                and row['dealer_up'] == up and row['double_after_split'] is das
                and row['shoe'] == protocol['unseen_shoes'][name], 'condition identity differs')
        statuses = {'completed', 'unsupported', 'reference_limit', 'timed_out', 'failed'}
        require(row['status'] in statuses,
                'unknown condition status')
        if row['status'] != 'completed':
            require(bool(row.get('error')), 'exclusion needs its exact reason')
            continue
        require(row['production_rank_order'] == PRODUCTION_RANKS,
                'production rank order is missing or changed')
        expected_counts = {rank: row['shoe'][i] for i, rank in enumerate(RANKS)}
        actual_counts = dict(zip(row['production_rank_order'], row['production_shoe'], strict=True))
        require(expected_counts == actual_counts, 'different rank compositions were compared')
        reference = row['reference']
        require(reference['states'] == sum(n for _, n in reference['state_counts'])
                and 0 < reference['states'] <= protocol['limits']['max_states'],
                'work count differs')
        require(0 <= reference['maximum_probability_mass_error'] <= 1e-12, 'probability mass error')
        require(0 <= reference['elapsed_seconds'] <= protocol['limits']['reference_seconds'],
                'invalid reference time')
        close(reference['value'], reference['value'], 'nonfinite reference')
        require(abs(reference['value']) <= (4 if das else 2) + 1e-12, 'split wager bound exceeded')
        for kind in ('production', 'joint'):
            ranking = row[kind]
            values = ranking['values']
            require(set(values) == {'S', 'H', 'D', 'P'}, 'missing root action')
            require(all(math.isfinite(value) for value in values.values()), 'nonfinite root action')
            ordered = sorted(values.values(), reverse=True)
            best = {key for key, value in values.items() if ordered[0] - value <= 1e-12}
            require(set(ranking['best']) == best, 'recommendation differs from retained values')
            close(ranking['margin'], ordered[0] - ordered[1], 'margin differs')
        for action in ('S', 'H', 'D'):
            require(row['production']['values'][action] == row['joint']['values'][action],
                    'single hand action value was replaced')
        close(row['joint']['values']['P'], reference['value'], 'joint action differs')
        gap = row['production']['values']['P'] - reference['value']
        close(row['signed_gap'], gap, 'signed gap differs')
        close(row['absolute_gap'], abs(gap), 'absolute gap differs')
        changed = set(row['production']['best']) != set(row['joint']['best'])
        require(row['decision_changed'] is changed,
                'recommendation change differs')
    require(data['status'] == ('completed' if all(r['status'] == 'completed' for r in data['rows'])
                               else 'with_exclusions'), 'run status differs')


def load():
    require(digest(ROOT / DATA) == RESULT_SHA256_LF, 'retained result bytes changed')
    require(digest(ROOT / FIRST) == FIRST_SHA256_LF, 'retained first attempt bytes changed')
    data = json.loads((ROOT / DATA).read_text())
    protocol = json.loads((ROOT / 'docs/joint-split-protocol.json').read_text())
    validate(data, protocol)
    require(data['implementation_sha256_lf']['docs/joint-split-protocol.json']
            == digest(ROOT / 'docs/joint-split-protocol.json'), 'declared protocol bytes changed')
    first = json.loads((ROOT / FIRST).read_text())
    require(first['evaluated_revision'] == INVALID and first['protocol'] == protocol
            and len(first['rows']) == 48, 'invalid attempt identity changed')
    for name in ('bj/joint_split.py', 'bj/ev.py', 'bj/core.py', 'bj/dealer.py',
                 'docs/joint-split-protocol.json'):
        require(first['implementation_sha256_lf'][name] == data['implementation_sha256_lf'][name],
                'the corrected attempt changed more than the rank adapter')
    return data


def summary(rows):
    complete = [r for r in rows if r['status'] == 'completed']
    require(bool(complete), 'no completed condition to summarize')
    return dict(completed=len(complete), excluded=len(rows) - len(complete),
                minimum=min(r['signed_gap'] for r in complete),
                maximum=max(r['signed_gap'] for r in complete),
                mean_absolute=math.fsum(r['absolute_gap'] for r in complete) / len(complete),
                changed=sum(r['decision_changed'] for r in complete),
                strict_changes=sum(not set(r['production']['best']) & set(r['joint']['best'])
                                   for r in complete),
                below=sum(r['signed_gap'] < -1e-12 for r in complete),
                above=sum(r['signed_gap'] > 1e-12 for r in complete),
                tied=sum(abs(r['signed_gap']) <= 1e-12 for r in complete))


def label(row):
    return (('Balanced' if row['shoe_name'] == 'balanced_high' else 'Ten rich')
            + f" / {row['pair']},{row['pair']} vs {row['dealer_up']} / DAS "
            + ('on' if row['double_after_split'] else 'off'))


def table(rows, changes=False):
    selected = [r for r in rows if r.get('decision_changed')] if changes else rows
    caption = 'Changed recommendation sets' if changes else 'Every declared condition'
    headers = ['Condition', 'Status', 'Production split', 'Joint split', 'Signed gap',
               'Production best', 'Joint best', 'Production margin', 'Joint margin',
               'States', 'Reference seconds']
    result = [f'<div class="table-wrap" tabindex="0" role="region" aria-label="{caption}">',
              '<table id="' + ('changes' if changes else 'conditions') + '">',
              f'<caption>{caption}. Net original bet units. '
              'Displayed to nine decimal places.</caption>',
              '<thead><tr>' + ''.join(f'<th scope="col">{h}</th>' for h in headers)
              + '</tr></thead><tbody>']
    for row in selected:
        values = [label(row), row['status']]
        if row['status'] == 'completed':
            values += [f"{row['production']['values']['P']:.9f}",
                       f"{row['reference']['value']:.9f}", f"{row['signed_gap']:+.9f}",
                       '/'.join(row['production']['best']), '/'.join(row['joint']['best']),
                       f"{row['production']['margin']:.9f}", f"{row['joint']['margin']:.9f}",
                       row['reference']['states'], f"{row['reference']['elapsed_seconds']:.6f}"]
        else:
            values += [row['error']] + ['not available'] * 8
        result.append('<tr>' + ''.join(f'<td>{html.escape(str(v))}</td>' for v in values) + '</tr>')
    return '\n'.join(result + ['</tbody></table></div>'])


def font_css():
    return '\n'.join('@font-face{font-family:"Solver Inter";'
                     f'src:local("{full}"),local("{post}");font-weight:{weight};'
                     f'font-style:{style};font-display:swap}}'
                     for weight, style, full, post in FACES)


def svg(data, record, mode=None):
    tokens = load_tokens()

    def role(key):
        return tokens['themes'][mode][key] if mode else f'var(--{key})'

    rows = data['rows']
    extent = max(.01, math.ceil(max(r.get('absolute_gap', 0) for r in rows) * 100) / 100)
    result = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 980 1280" '
              'role="img" aria-labelledby="gap-title gap-desc">',
              '<title id="gap-title">Shared cards change split values</title>',
              '<desc id="gap-desc">All 48 conditions. Signed production minus joint value. '
              'A negative gap means production is lower. Color identifies dealer upcard. '
              'Circle means DAS off and square means DAS on. The report has every numeric '
              'value and exclusion.</desc>',
              '<metadata>' + html.escape(json.dumps(dict(record, appearance=mode or 'Auto')))
              + '</metadata>',
              f'<style>{font_css()}text{{font-family:"Solver Inter",Inter,system-ui,sans-serif;'
              'font-synthesis:none}}</style>',
              f'<rect width="980" height="1280" fill="{role("panel")}"/>',
              f'<g fill="{role("text")}"><text x="24" y="35" font-size="24" font-weight="600">'
              'Shared cards change split values</text><text x="24" y="65" font-size="16">'
              'Two toy shoes, two hands, no resplits. Net units of the original bet.</text></g>']
    for tick in (-extent, -extent / 2, 0, extent / 2, extent):
        x = 690 + tick / extent * 240
        result.append(f'<line x1="{x}" x2="{x}" y1="108" y2="1183" '
                      f'stroke="{role("text" if tick == 0 else "divider")}"/>'
                      f'<text x="{x}" y="99" text-anchor="middle" font-size="14" '
                      f'fill="{role("text")}">{tick:+.2f}</text>')
    for i, row in enumerate(rows):
        y = 130 + 22 * i
        color = PALETTE[row['dealer_up']][0 if mode == 'Clair' else 1] if mode else (
            f'var(--dealer-{row["dealer_up"]})')
        result.append(f'<g data-condition="{row["id"]}"><text x="24" y="{y + 4}" '
                      f'font-size="14" fill="{role("text")}">{label(row)}</text>')
        if row['status'] == 'completed':
            x = 690 + row['signed_gap'] / extent * 240
            marker = (f'<rect x="{x - 4}" y="{y - 4}" width="8" height="8"' if
                      row['double_after_split'] else f'<circle cx="{x}" cy="{y}" r="4"')
            result.append(marker + f' fill="{color}"/>')
        else:
            result.append(f'<text x="450" y="{y + 4}" font-size="14" '
                          f'fill="{role("text")}">{row["status"]}</text>')
        result.append('</g>')
    result += [f'<g fill="{role("text")}" font-size="14"><text x="24" y="1213">'
               'Circle: DAS off. Square: DAS on. Color: dealer 6 blue, T gold, A purple.</text>'
               '<text x="24" y="1243">Negative means production is lower. This family is not '
               'a full shoe error bound.</text></g>', '</svg>']
    return '\n'.join(result)


def csv_data(rows):
    fields = ['id', 'status', 'production_split', 'joint_split', 'signed_gap', 'absolute_gap',
              'production_best', 'joint_best', 'production_margin', 'joint_margin', 'states',
              'reference_seconds', 'production_seconds', 'case_wall_seconds', 'error']
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    for row in rows:
        result = dict(id=row['id'], status=row['status'], error=row.get('error', ''))
        if row['status'] == 'completed':
            result.update(production_split=row['production']['values']['P'],
                          joint_split=row['reference']['value'], signed_gap=row['signed_gap'],
                          absolute_gap=row['absolute_gap'],
                          production_best='/'.join(row['production']['best']),
                          joint_best='/'.join(row['joint']['best']),
                          production_margin=row['production']['margin'],
                          joint_margin=row['joint']['margin'], states=row['reference']['states'],
                          reference_seconds=row['reference']['elapsed_seconds'],
                          production_seconds=row['production_seconds'],
                          case_wall_seconds=row['case_wall_seconds'])
        writer.writerow(result)
    return stream.getvalue()


def render_outputs():
    data = load()
    stats = summary(data['rows'])
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    status = subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True)
    dirty = bool(status.strip())
    record = dict(schema_version=1, evaluated_revision=MEASURED,
                  invalid_first_revision=INVALID, renderer_revision=revision, renderer_dirty=dirty,
                  invalid_first_status='invalid comparison of different rank compositions',
                  data_sha256_lf=digest(ROOT / DATA), invalid_first_sha256_lf=digest(ROOT / FIRST),
                  token_revision=TOKEN_REVISION, experiment_rerun=False,
                  renderer_sha256_lf={p: digest(ROOT / p) for p in (
                      'tools/render_joint_report.py', 'tools/presentation.py',
                      'presentation/joint-split.template.html', 'site/style.css')},
                  summary=stats)
    palette = []
    for mode, index in (('Clair', 0), ('Obscur', 1)):
        declarations = ''.join(f'--dealer-{rank}:{colors[index]};'
                               for rank, colors in PALETTE.items())
        selector = ':root' if mode == 'Clair' else ':root[data-appearance="obscur"]'
        palette.append(f'{selector}{{{declarations}}}')
        if mode == 'Obscur':
            palette.append('@media(prefers-color-scheme:dark){'
                           f':root:not([data-appearance="clair"]){{{declarations}}}}}')
    print_colors = ''.join(f'--dealer-{rank}:{colors[0]};' for rank, colors in PALETTE.items())
    palette.append(f'@media print{{:root,:root[data-appearance]{{{print_colors}}}}}')
    # Explicit replacements keep template braces out of embedded CSS and SVG.
    document = (ROOT / 'presentation/joint-split.template.html').read_text()
    replacements = dict(table=table(data['rows']), changes=table(data['rows'], True),
                        chart=svg(data, record), palette='\n'.join(palette),
                        measured=MEASURED, invalid=INVALID, renderer=revision,
                        dirty=' (uncommitted report changes)' if dirty else '',
                        mean=f'{stats["mean_absolute"]:.9f}', minimum=f'{stats["minimum"]:.9f}',
                        completed=stats['completed'], excluded=stats['excluded'],
                        below=stats['below'], above=stats['above'], tied=stats['tied'])
    for key, value in replacements.items():
        document = document.replace('{' + key + '}', str(value))
    return {'joint-split.html': document.encode(),
            'joint-split-clair.svg': svg(data, record, 'Clair').encode(),
            'joint-split-obscur.svg': svg(data, record, 'Obscur').encode(),
            'joint-split-results.json': (ROOT / DATA).read_bytes(),
            'joint-split-first-invalid.json': (ROOT / FIRST).read_bytes(),
            'joint-split-protocol.json': (ROOT / 'docs/joint-split-protocol.json').read_bytes(),
            'joint-split.csv': csv_data(data['rows']).encode(),
            'joint-split-presentation.json': (json.dumps(record, indent=2) + '\n').encode()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', required=True)
    parser.parse_args()
    print(json.dumps(summary(load()['rows']), indent=2))
