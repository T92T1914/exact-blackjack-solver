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
FACES = {'Regular': (400, False), 'SemiBold': (600, False), 'Bold': (700, False)}
RETAINED_CLAIR = tuple(f'docs/blackjack-composition-clair{suffix}.{ext}'
                       for suffix in ('', '-wide') for ext in ('png', 'svg'))
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
    """Require the three static Inter faces Obscur allows, with no fallback or download."""
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


DPI = 200
FLOOR_POINTS_AT_100_DPI = 30
INSET = 12
NBSP = ' '


def floor_points(dpi):
    """The 30 pt at 100 dpi floor of Obscur, as points at another resolution."""
    return FLOOR_POINTS_AT_100_DPI * 100 / dpi


def text_width(renderer, font, text):
    width, _, _ = renderer.get_text_width_height_descent(text.replace(NBSP, ' '), font, False)
    return width


def wrap_text(renderer, font, text, limit):
    """Wrap by measured width. A non-breaking space keeps its words together."""
    lines = []
    for paragraph in text.split('\n'):
        current = ''
        for word in paragraph.split(' '):
            trial = f'{current} {word}' if current else word
            if text_width(renderer, font, trial) <= limit:
                current = trial
            elif not current:
                raise ValueError(f'A word does not fit its line, change the layout: {word}')
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return '\n'.join(line.replace(NBSP, ' ') for line in lines)


def draw(data, tokens, mode, files, output, wide=False):
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import rc_context
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from matplotlib.font_manager import FontProperties
    from matplotlib.patches import FancyBboxPatch

    roles = tokens['themes'][mode.capitalize()]
    width = 1800 if wide else 960
    margin = 72 if wide else 48
    scale = 1.0 if wide else 1.1
    fonts = {name: FontProperties(fname=str(path)) for name, path in files.items()}
    floor = floor_points(DPI)
    # The narrow edition follows the larger type of the Obscur table, 33 pt against 30 pt.
    small = 15 * scale

    def build(fig, height):
        """Place every label top down in pixels. Return what was placed and where it ends."""
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, width)
        ax.set_ylim(height, 0)
        ax.axis('off')
        renderer = FigureCanvasAgg(fig).get_renderer()
        labels, cards = [], []

        def font(points, face):
            prop = fonts[face].copy()
            prop.set_size(points)
            return prop

        def put(x, top, text, points, face='Regular', color=None, gid=None, ha='left',
                limit=None):
            if points < floor:
                raise ValueError('A label is below the Obscur type floor')
            prop = font(points, face)
            if limit is not None:
                text = wrap_text(renderer, prop, text, limit)
            item = ax.text(x, top, text.replace(NBSP, ' '), fontproperties=prop,
                           color=color or roles['text'], va='top', ha=ha, linespacing=1.3,
                           gid=gid, zorder=3)
            labels.append(item)
            return item

        def extent(item):
            box = item.get_window_extent(renderer)
            return box.x0, height - box.y1, box.x1, height - box.y0

        def card(left, top, card_width, index, hand):
            pad_x, pad_top = 28, 32
            x0, x1 = left + pad_x, left + card_width - pad_x
            inside = x1 - x0
            title = put(x0, top + pad_top, '10 + 6' if index == 0 else '8 + 5 + 3', 22, 'Bold')
            recommended = 'Hit' if hand['action'] == 'H' else 'Stand'
            mark = put(x1, top + pad_top, recommended, 16 * scale, 'SemiBold',
                       roles[ACTIONS[hand['action']]], ha='right',
                       gid=f'recommendation-{index}')
            title_box, mark_box = extent(title), extent(mark)
            mark.set_y(top + pad_top + ((title_box[3] - title_box[1])
                                        - (mark_box[3] - mark_box[1])) / 2)
            cursor = max(extent(title)[3], extent(mark)[3]) + 20
            members = [title, mark]
            for action in ('H', 'S'):
                name = put(x0, cursor, 'Hit' if action == 'H' else 'Stand', 16 * scale,
                           'SemiBold', roles[ACTIONS[action]], gid=f'action-{index}-{action}')
                value = put(x1, cursor, f"{hand['values'][action]:.6f}", 16 * scale,
                            'Bold' if action == hand['action'] else 'Regular', ha='right',
                            gid=f'value-{index}-{action}')
                members += [name, value]
                cursor = max(extent(name)[3], extent(value)[3]) + 14
            note = put(x0, cursor, f"Margin: {hand['margin']:.6f} wager units", small,
                       'SemiBold', roles['muted'], gid=f'margin-{index}', limit=inside)
            members.append(note)
            bottom = extent(note)[3] + pad_top
            ax.add_patch(FancyBboxPatch(
                (left, top), card_width, bottom - top, boxstyle='round,pad=0,rounding_size=18',
                facecolor=roles['control'], edgecolor=roles['border'], linewidth=.72,
                zorder=1))
            cards.append(((left, top, left + card_width, bottom), members))
            return bottom

        limit = width - 2 * margin
        put(margin, margin, 'EXACT BLACKJACK SOLVER', small, 'SemiBold', roles['accent'])
        headline = 'Same total. Different decision.' if wide else 'Same total.\nDifferent decision.'
        title = put(margin, margin + 70, headline, 26, 'Bold')
        subtitle = put(margin, extent(title)[3] + 22, 'Both hands total 16 against a dealer ten.',
                       small, limit=limit)
        top = extent(subtitle)[3] + 40
        if wide:
            card_width = (width - 2 * margin - 78) / 2
            bottoms = [card(margin + index * (card_width + 78), top, card_width, index, hand)
                       for index, hand in enumerate(data['hands'])]
            cursor = max(bottoms)
        else:
            cursor = top
            for index, hand in enumerate(data['hands']):
                cursor = card(margin, cursor, width - 2 * margin, index, hand) + (
                    24 if index == 0 else 0)
        cursor += 56
        paragraphs = [
            ('Both expected returns are negative.', 'Bold', None),
            ('Expected net return per original wager. Not a win probability.', 'Regular',
             'muted'),
            (f'Only hit and stand shown. Doubling 10{NBSP}+{NBSP}6 is worse. '
             f'No double on 8{NBSP}+{NBSP}5{NBSP}+{NBSP}3.', 'Regular', None),
            ('Six decks. Dealer stands on soft 17. Peek found no blackjack. '
             'Visible cards removed.', 'Regular', 'muted'),
            ('Exact hit and stand values in this model. '
             'Original split path is approximate.', 'Regular', None),
            ('Recorded source: 23a42e6.', 'SemiBold', 'muted'),
        ]
        for text, face, role in paragraphs:
            item = put(margin, cursor, text, small, face, roles[role] if role else None,
                       limit=limit)
            cursor = extent(item)[3] + 22
        # Canvas height grows to fit the footer plus 49 px.
        bottom = max(extent(item)[3] for item in labels) + 49
        return ax, labels, cards, extent, bottom

    with rc_context({'svg.fonttype': 'path', 'svg.hashsalt': 'solver-composition-v1'}):
        scratch = Figure(figsize=(width / DPI, 6000 / DPI), dpi=DPI)
        height = math.ceil(build(scratch, 6000)[4])
        fig = Figure(figsize=(width / DPI, height / DPI), dpi=DPI, facecolor=roles['canvas'])
        _, labels, cards, extent, _ = build(fig, height)
        canvas = FigureCanvasAgg(fig)
        canvas.draw()
        boxes = [extent(item) for item in labels]
        if any(b[0] < INSET or b[1] < INSET or b[2] > width - INSET or b[3] > height - INSET
               for b in boxes):
            raise ValueError('A figure label extends outside the canvas')
        for (left, top, right, bottom), members in cards:
            if any(box[0] < left + INSET or box[1] < top + INSET or box[2] > right - INSET
                   or box[3] > bottom - INSET for box in map(extent, members)):
                raise ValueError('A figure label is closer than 12 px to its card edge')
        minimum = min(item.get_fontsize() for item in labels)
        if minimum < floor:
            raise ValueError('A figure label is below the Obscur type floor')
        layout = dict(width=width, height=height, dpi=DPI, labels_within_canvas=len(boxes),
                      minimum_font_points=minimum,
                      minimum_font_points_at_100_dpi=minimum * DPI / 100,
                      floor_points_at_100_dpi=FLOOR_POINTS_AT_100_DPI,
                      minimum_inset_px=INSET)
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
    if set(record['retained_clair']['files']) != set(RETAINED_CLAIR):
        raise ValueError('The retained Clair editions changed')
    for name in RETAINED_CLAIR:
        if record['retained_clair']['files'][name] != digest(ROOT / name):
            raise ValueError(f'Figure output changed: retained Clair edition {name}')
    for name, checksum in record['outputs_sha256'].items():
        if digest(ROOT / name) != checksum:
            raise ValueError(f'Figure output changed: {name}')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--font-dir', type=Path,
                        help='Directory of the three official static Inter TTFs')
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
        layouts = dict(obscur=draw(data, load_tokens(), 'obscur', files, output))
        wide_layouts = dict(obscur=draw(data, load_tokens(), 'obscur', files, output, wide=True))
        import matplotlib
        old = json.loads((ROOT / MANIFEST).read_text(encoding='utf-8'))
        retained = old.get('retained_clair') or dict(
            note='Clair editions are kept as first rendered. They were drawn with six Inter '
                 'faces, including italics, and are not redrawn by this renderer.',
            token_revision=old['evidence']['token_revision'],
            layout=old['layout']['clair'], wide_layout=old['wide_layout']['clair'],
            typography=old['typography'],
            files={name: old['outputs_sha256'][name] for name in RETAINED_CLAIR})
        for name in RETAINED_CLAIR:
            if digest(ROOT / name) != retained['files'][name]:
                raise ValueError(f'Figure output changed: retained Clair edition {name}')
        record = dict(schema_version=3, evidence=semantic_record(data),
                      renderer=dict(matplotlib=matplotlib.__version__, backend='Agg'),
                      layout=layouts, wide_layout=wide_layouts, retained_clair=retained,
                      typography=dict(files=font_evidence, painted_faces=list(FACES),
                                      png='Glyphs rasterized from explicit Inter files',
                                      svg='Labels outlined from the same Inter files. '
                                          'Selectable explanations and data accompany them.'),
                      inputs_sha256_lf={name: digest(ROOT / name, text=True) for name in INPUTS},
                      outputs_sha256=dict(sorted(
                          {**{'docs/' + p.name: digest(p) for p in output.iterdir()},
                           **retained['files']}.items())))
        for path in output.iterdir():
            (ROOT / 'docs' / path.name).write_bytes(path.read_bytes())
        (ROOT / MANIFEST).write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    check_outputs()
    print('Rendered the Obscur editions from retained data with three verified Inter faces')


if __name__ == '__main__':
    main()
