"""Render the retained composition example without running the solver."""
import argparse
import hashlib
import json
import math
import tempfile
from pathlib import Path

try:
    from .presentation import load_tokens, TOKEN_REVISION
except ImportError:
    from presentation import load_tokens, TOKEN_REVISION

ROOT = Path(__file__).resolve().parents[1]
DATA = 'docs/visual-example-data.json'
MANIFEST = 'docs/blackjack-composition-figure.json'
INPUTS = (DATA, 'presentation/tokens.json', 'tools/presentation.py',
          'tools/render_composition_figure.py')
FACES = {'Regular': (400, False), 'SemiBold': (600, False), 'Bold': (700, False),
         'Italic': (400, True), 'SemiBoldItalic': (600, True), 'BoldItalic': (700, True)}
ACTIONS = {'H': 'accent', 'S': 'warning'}


def digest(path, text=False):
    data = path.read_text(encoding='utf-8').encode() if text else path.read_bytes()
    return hashlib.sha256(data).hexdigest()


def load_data():
    data = json.loads((ROOT / DATA).read_text(encoding='utf-8'))
    expected = [
        dict(cards=['T', '6'], dealer='T', action='H',
             values=dict(S=-0.5409544390190252, H=-0.5346755624525633, D=-1.0693511249051266),
             margin=0.006278876566461866),
        dict(cards=['8', '5', '3'], dealer='T', action='S',
             values=dict(S=-0.539886705281481, H=-0.5440039696389283),
             margin=0.004117264357447303),
    ]
    if (data['source_commit'] != '23a42e6' or data['source'] != 'bj.ev.best_action'
            or data['rules'] != 'Six decks; visible cards removed; dealer stands on soft 17; '
            'peek completed without blackjack; no surrender'
            or data['units'] != 'Expected net return per original wager; not win probabilities'
            or data['hands'] != expected):
        raise ValueError('The figure requires the retained values, units and source')
    for hand in data['hands']:
        ordered = sorted(hand['values'].values(), reverse=True)
        if (not all(value < 0 for value in hand['values'].values())
                or not math.isclose(ordered[0] - ordered[1], hand['margin'], abs_tol=1e-15)):
            raise ValueError('Retained action margins or negative returns differ')
    return data


def font_files(directory):
    """Require six actual static Inter faces without fallback or a font download."""
    from fontTools.ttLib import TTFont

    files, evidence = {}, {}
    for name, (weight, italic) in FACES.items():
        path = directory / f'Inter-{name}.ttf'
        with TTFont(path) as font:
            postscript = font['name'].getDebugName(6)
            if (postscript != f'Inter-{name}' or font['OS/2'].usWeightClass != weight
                    or bool(font['OS/2'].fsSelection & 1) != italic
                    or not set(range(32, 127)).issubset(font.getBestCmap())):
                raise ValueError(f'Incorrect Inter face or missing Latin glyphs: {path.name}')
            evidence[name] = dict(sha256=digest(path), postscript=postscript,
                                  weight=weight, italic=italic)
        files[name] = path
    return files, evidence


def semantic_record(data):
    return dict(retained_values=data, solver_rerun=False, token_revision=TOKEN_REVISION,
                series_roles=ACTIONS, displayed_actions=['H', 'S'], decimal_places=6,
                recommendation=['Hit', 'Stand'],
                scope='Exact hit and stand enumeration within the stated model. '
                      'No split approximation is involved in these two examples.',
                split_reference='The later joint split study is separate evidence.')


def draw(data, tokens, mode, files, output, wide=False):
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import rc_context
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from matplotlib.font_manager import FontProperties
    from matplotlib.patches import FancyBboxPatch

    roles = tokens['themes'][mode.capitalize()]
    fonts = {name: FontProperties(fname=str(path)) for name, path in files.items()}
    with rc_context({'svg.fonttype': 'path', 'svg.hashsalt': 'solver-composition-v1'}):
        fig = Figure(figsize=(9, 6.4) if wide else (4.8, 10.4), dpi=200, facecolor=roles['canvas'])
        labels = []

        def label(x, y, text, size=13, face='Regular', color=None, gid=None, **kwargs):
            item = fig.text(x, y, text, fontsize=size, fontproperties=fonts[face],
                            color=color or roles['text'], va='top', linespacing=1.3,
                            gid=gid, **kwargs)
            labels.append(item)
            return item

        label(.055 if wide else .075, .96, 'EXACT BLACKJACK SOLVER',
              12, 'SemiBold', roles['accent'])
        label(.055 if wide else .075, .90 if wide else .918,
              'Same total. Different decision.' if wide else 'Same total.\nDifferent decision.',
              26, 'Bold')
        label(.055 if wide else .075, .815, 'Both hands total 16 against a dealer ten.', 12.5)
        for index, hand in enumerate(data['hands']):
            top = .72 if wide else .762 - index * .235
            left = .055 + index * .48 if wide else .055
            text_x = left + .02 if wide else .085
            right = left + (.385 if wide else .86)
            scale = 1.55 if wide else 1
            panel = FancyBboxPatch((left, top - .214 * scale), .41 if wide else .89, .212 * scale,
                                   boxstyle='round,pad=0.006,rounding_size=0.012',
                                   transform=fig.transFigure, facecolor=roles['panel'],
                                   edgecolor=roles['divider'], linewidth=.8)
            fig.add_artist(panel)
            title = '10 + 6' if index == 0 else '8 + 5 + 3'
            label(text_x, top - .018 * scale, title, 22, 'Bold')
            recommended = 'Hit' if hand['action'] == 'H' else 'Stand'
            label(right, top - .025 * scale, recommended, 15, 'SemiBold',
                  roles[ACTIONS[hand['action']]], ha='right', gid=f'recommendation-{index}')
            for j, action in enumerate(('H', 'S')):
                y = top - (.077 + j * .046) * scale
                color = roles[ACTIONS[action]]
                label(text_x, y, 'Hit' if action == 'H' else 'Stand', 14, 'SemiBold', color,
                      gid=f'action-{index}-{action}')
                label(right, y, f"{hand['values'][action]:.6f}", 14,
                      'Bold' if action == hand['action'] else 'Regular',
                      ha='right', gid=f'value-{index}-{action}')
            label(text_x, top - .172 * scale, f"Margin: {hand['margin']:.6f} wager units", 12.5,
                  'SemiBoldItalic', roles['muted'], gid=f'margin-{index}')
        if wide:
            label(.055, .35, 'Both expected returns are negative.', 14, 'BoldItalic')
            label(.055, .30, 'Expected net return per original wager. Not a win probability.',
                  13, 'Italic', roles['muted'])
            label(.055, .24, 'Only hit and stand shown. Doubling 10 + 6 is worse. '
                  'No double on 8 + 5 + 3.', 12.5)
            label(.055, .185, 'Six decks. Dealer stands on soft 17. '
                  'Peek found no blackjack. Visible cards removed.',
                  12.5, color=roles['muted'])
            label(.055, .13, 'Exact hit and stand values in this model. '
                  'Split values elsewhere are approximate.', 12.5)
            label(.055, .07, 'Recorded source: 23a42e6.', 12, 'SemiBold', roles['muted'])
        else:
            label(.075, .283, 'Both expected returns are negative.', 13.5, 'BoldItalic')
            label(.075, .246, 'Expected net return per original wager.\nNot a win probability.',
                  12.5, 'Italic', roles['muted'])
            label(.075, .191, 'Only hit and stand shown. Doubling 10 + 6\n'
                  'is worse. No double on 8 + 5 + 3.', 12.2)
            label(.075, .135, 'Six decks. Dealer stands on soft 17.\n'
                  'Peek found no blackjack. Visible cards removed.', 11.8, color=roles['muted'])
            label(.075, .080, 'Exact hit and stand values in this model.\n'
                  'Split values elsewhere are approximate.', 12.2)
            label(.075, .027, 'Recorded source: 23a42e6.', 12, 'SemiBold', roles['muted'])
        canvas = FigureCanvasAgg(fig)
        canvas.draw()
        bounds = [item.get_window_extent(canvas.get_renderer()) for item in labels]
        if any(b.x0 < 0 or b.y0 < 0 or b.x1 > fig.bbox.width or b.y1 > fig.bbox.height
               for b in bounds):
            raise ValueError('A figure label extends outside the canvas')
        layout = dict(width=int(fig.bbox.width), height=int(fig.bbox.height),
                      labels_within_canvas=len(bounds),
                      minimum_font_points=min(item.get_fontsize() for item in labels))
        for ext in ('png', 'svg'):
            metadata = {'Description': json.dumps(semantic_record(data), sort_keys=True)}
            if ext == 'svg':
                metadata['Date'] = None
            suffix = '-wide' if wide else ''
            path = output / f'blackjack-composition-{mode}{suffix}.{ext}'
            fig.savefig(path, metadata=metadata)
            if ext == 'svg':
                path.write_text('\n'.join(line.rstrip() for line in path.read_text(
                    encoding='utf-8').splitlines()) + '\n', encoding='utf-8', newline='\n')
        fig.clear()
        return layout


def check_outputs():
    record = json.loads((ROOT / MANIFEST).read_text(encoding='utf-8'))
    if record['evidence'] != semantic_record(load_data()):
        raise ValueError('Figure evidence is stale')
    for name in INPUTS:
        if record['inputs_sha256_lf'][name] != digest(ROOT / name, text=True):
            raise ValueError(f'Figure input changed: {name}')
    expected = {f'docs/blackjack-composition-{mode}{suffix}.{ext}'
                for mode in ('clair', 'obscur') for suffix in ('', '-wide')
                for ext in ('png', 'svg')}
    if set(record['outputs_sha256']) != expected:
        raise ValueError('Both PNG and SVG editions are required')
    for name, checksum in record['outputs_sha256'].items():
        if digest(ROOT / name) != checksum:
            raise ValueError(f'Figure output changed: {name}')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--font-dir', type=Path, help='Directory of six official static Inter TTFs')
    parser.add_argument('--check', action='store_true',
                        help='Verify committed output without rendering')
    args = parser.parse_args()
    if args.check:
        check_outputs()
        print('Both editions match the retained source and renderer')
        return
    if args.font_dir is None:
        parser.error('--font-dir is required for rendering. No font download is performed.')
    data = load_data()
    files, font_evidence = font_files(args.font_dir)
    with tempfile.TemporaryDirectory() as temp:
        output = Path(temp)
        layouts = {mode: draw(data, load_tokens(), mode, files, output)
                   for mode in ('clair', 'obscur')}
        wide_layouts = {mode: draw(data, load_tokens(), mode, files, output, wide=True)
                        for mode in ('clair', 'obscur')}
        import matplotlib
        record = dict(schema_version=2, evidence=semantic_record(data),
                      renderer=dict(matplotlib=matplotlib.__version__, backend='Agg'),
                      layout=layouts, wide_layout=wide_layouts,
                      typography=dict(files=font_evidence, painted_faces=list(FACES),
                                      png='Glyphs rasterized from explicit Inter files',
                                      svg='Labels outlined from the same Inter files. '
                                          'Selectable explanations and data accompany them.'),
                      inputs_sha256_lf={name: digest(ROOT / name, text=True) for name in INPUTS},
                      outputs_sha256={'docs/' + p.name: digest(p)
                                      for p in sorted(output.iterdir())})
        for path in output.iterdir():
            (ROOT / 'docs' / path.name).write_bytes(path.read_bytes())
        (ROOT / MANIFEST).write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    check_outputs()
    print('Rendered both editions from retained data with six verified Inter faces')


if __name__ == '__main__':
    main()
