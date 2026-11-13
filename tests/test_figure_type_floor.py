"""Every Obscur figure holds the 30 pt at 100 dpi floor, read from the delivered files."""
import json
import re
import struct
import xml.etree.ElementTree as ET

import pytest

from tools import render_composition_figure as composition
from tools import render_evidence_figure as evidence
from tools import render_share_preview as sharing

SVG = '{http://www.w3.org/2000/svg}'
FLOOR_PX = 30 * 100 / 72
GLYPH_GROUP = re.compile(r'scale\(([0-9.]+) -([0-9.]+)\)')


def png_size(path):
    raw = path.read_bytes()
    assert raw[:8] == b'\x89PNG\r\n\x1a\n'
    return struct.unpack('>II', raw[16:24])


def smallest_outlined_label_px(path, png_width):
    """Size of the smallest painted label, in pixels of the PNG that matches the SVG."""
    root = ET.parse(path).getroot()
    assert not list(root.iter(SVG + 'text')), 'An outlined figure holds no text element'
    box = [float(value) for value in root.attrib['viewBox'].split()]
    sizes = []
    for node in root.iter(SVG + 'g'):
        match = GLYPH_GROUP.search(node.attrib.get('transform', ''))
        if match and node.attrib.get('style', '').startswith('fill'):
            assert match.group(1) == match.group(2)
            sizes.append(float(match.group(1)) * 100)
    assert sizes, 'No outlined label found'
    return min(sizes) * png_width / box[2]


@pytest.mark.parametrize('suffix', ['', '-wide'])
def test_composition_labels_hold_the_floor_in_both_formats(suffix):
    record = composition.check_outputs()
    layout = record['wide_layout' if suffix else 'layout']['obscur']
    assert layout['floor_points_at_100_dpi'] == 30
    assert layout['minimum_font_points_at_100_dpi'] >= 30
    name = f'docs/blackjack-composition-obscur{suffix}'
    width, height = png_size(composition.ROOT / f'{name}.png')
    assert (width, height) == (layout['width'], layout['height'])
    assert smallest_outlined_label_px(composition.ROOT / f'{name}.svg', width) >= FLOOR_PX - 1e-6


def test_evidence_labels_hold_the_floor_in_both_formats():
    record = evidence.check_outputs()
    layout = record['layout']['obscur']
    assert layout['minimum_font_points_at_100_dpi'] >= 30
    name = f'docs/{evidence.STEM}-obscur'
    width, height = png_size(evidence.ROOT / f'{name}.png')
    assert (width, height) == (layout['width'], layout['height'])
    assert smallest_outlined_label_px(evidence.ROOT / f'{name}.svg', width) >= FLOOR_PX - 1e-6


def test_evidence_svg_outlines_its_labels_and_keeps_its_values_readable():
    values = evidence.load_values()
    path = evidence.ROOT / f'docs/{evidence.STEM}-obscur.svg'
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    root = ET.parse(path, parser).getroot()
    assert not list(root.iter(SVG + 'text'))
    assert f"{values['entered_states']:,}" in root.find(SVG + 'desc').text
    assert f"{values['state_cap']:,}" in root.find(SVG + 'desc').text
    for gid, expected in (('entered-states-value', f"{values['entered_states']:,}"),
                          ('state-cap-value', f"{values['state_cap']:,} cap")):
        group = root.find(f".//{SVG}g[@id='{gid}']")
        assert ''.join(c.text.strip() for c in group.iter() if c.tag is ET.Comment) == expected
    anchor = root.find(f'.//{SVG}a')
    assert anchor.attrib['href'] == evidence.GUIDE
    assert anchor.attrib['aria-label'] == 'Source guide'


def test_the_clair_evidence_edition_is_left_as_first_drawn():
    record = evidence.check_outputs()
    assert (record['editions']['clair']['png']['width'],
            record['editions']['clair']['png']['height']) == (1440, 720)
    assert png_size(evidence.ROOT / f'docs/{evidence.STEM}-clair.png') == (1440, 720)


def test_sharing_card_labels_hold_the_floor():
    receipt = sharing.check()
    assert png_size(sharing.ROOT / 'site/share-preview.png') == (1800, 900)
    assert sharing.FLOOR_PX >= FLOOR_PX
    assert min(item['size'] for item in receipt['painted_labels']) >= FLOOR_PX
    assert receipt['minimum_label_px'] >= FLOOR_PX
    config = json.loads((sharing.ROOT / 'docs/sharing-card.json').read_text())
    page = (sharing.ROOT / config['pages'][0]).read_text(encoding='utf-8')
    assert '<meta property="og:image:width" content="1800">' in page
    assert '<meta property="og:image:height" content="900">' in page


def test_a_label_below_the_floor_is_refused_by_the_receipt_check(tmp_path, monkeypatch):
    receipt = json.loads(sharing.RECEIPT.read_text())
    receipt['painted_labels'][0]['size'] = 41
    changed = tmp_path / 'receipt.json'
    changed.write_text(json.dumps(receipt))
    monkeypatch.setattr(sharing, 'RECEIPT', changed)
    with pytest.raises(ValueError, match='below the Obscur type floor'):
        sharing.check()
