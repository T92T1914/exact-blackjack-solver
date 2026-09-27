"""Verify saved values, painted labels, portable glyphs and actual consumers."""
import copy
import json
import shutil
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

from tools import render_composition_figure as figure

NS = {'s': 'http://www.w3.org/2000/svg', 'dc': 'http://purl.org/dc/elements/1.1/'}


def test_receipt_retains_negative_returns_margins_and_six_genuine_faces():
    record = figure.check_outputs()
    evidence = record['evidence']
    assert evidence['retained_values']['source_commit'] == '23a42e6'
    assert evidence['solver_rerun'] is False
    assert evidence['displayed_actions'] == ['H', 'S']
    assert evidence['recommendation'] == ['Hit', 'Stand']
    assert 'No split approximation' in evidence['scope']
    assert record['layout']['clair'] == record['layout']['obscur']
    assert set(record['typography']['painted_faces']) == set(figure.FACES)
    for name, (weight, italic) in figure.FACES.items():
        actual = record['typography']['files'][name]
        assert (actual['postscript'], actual['weight'], actual['italic']) == (
            f'Inter-{name}', weight, italic)
        assert len(actual['sha256']) == 64


def test_originals_are_preserved_with_normalized_text_checkouts():
    for name, checksum, text in (
        (figure.DATA, '1ac4d099c647d3db974e53258639c884c61d86b1ca4e84011e5b7fed1138001c', True),
        ('docs/blackjack-composition-example.svg',
         '5d24097c4ce0c40ad512aba965d6669c549a77ce0d5377b8fc44ba038e2e65a3', True),
        ('docs/blackjack-composition-example.png',
         '3ec9b6c355f85afbf25a7765c6f3d2fd2f94a7a71d71768417279e9618d37d9c', False),
    ):
        assert figure.digest(figure.ROOT / name, text=text) == checksum


def svg_root(mode, suffix=""):
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    path = figure.ROOT / f'docs/blackjack-composition-{mode}{suffix}.svg'
    return ET.parse(path, parser).getroot()


def comment_text(node):
    return ''.join(child.text.strip() for child in node.iter() if child.tag == ET.Comment)


@pytest.mark.parametrize("suffix", ["", "-wide"])
def test_painted_numeric_labels_retain_values_and_geometry_in_both_editions(suffix):
    roots = [svg_root(mode, suffix) for mode in ('clair', 'obscur')]
    tokens = figure.load_tokens()
    for index, hand in enumerate(figure.load_data()['hands']):
        for mode, root in zip(('clair', 'obscur'), roots, strict=True):
            for action in ('H', 'S'):
                value = root.find(f".//s:g[@id='value-{index}-{action}']", NS)
                assert comment_text(value) == f"{hand['values'][action]:.6f}"
                label = root.find(f".//s:g[@id='action-{index}-{action}']/s:g", NS)
                assert tokens['themes'][mode.capitalize()][figure.ACTIONS[action]] in (
                    label.attrib['style'])
            assert comment_text(root.find(f".//s:g[@id='margin-{index}']", NS)) == (
                f"Margin: {hand['margin']:.6f} wager units")
            assert comment_text(root.find(f".//s:g[@id='recommendation-{index}']", NS)) == (
                'Hit' if index == 0 else 'Stand')
    paths = [[node.attrib.get('d') for node in root.findall('.//s:path', NS)] for root in roots]
    assert paths[0] == paths[1]


@pytest.mark.parametrize("suffix", ["", "-wide"])
def test_png_dimensions_and_metadata_match_the_vector_evidence(suffix):
    for mode in ('clair', 'obscur'):
        raw = (figure.ROOT / f'docs/blackjack-composition-{mode}{suffix}.png').read_bytes()
        assert raw[:8] == b'\x89PNG\r\n\x1a\n'
        assert struct.unpack('>II', raw[16:24]) == ((1800, 1280) if suffix else (960, 2080))
        offset, description = 8, None
        while offset < len(raw):
            length = struct.unpack('>I', raw[offset:offset + 4])[0]
            kind, content = raw[offset + 4:offset + 8], raw[offset + 8:offset + 8 + length]
            if kind == b'tEXt' and content.startswith(b'Description\0'):
                description = json.loads(content.split(b'\0', 1)[1])
            offset += length + 12
        assert description == figure.semantic_record(figure.load_data())
        vector_description = json.loads(svg_root(mode, suffix).find('.//dc:description', NS).text)
        assert vector_description == description


@pytest.mark.parametrize("suffix", ["", "-wide"])
def test_every_inter_face_supplies_outlines_without_an_external_font_dependency(suffix):
    for mode in ('clair', 'obscur'):
        path = figure.ROOT / f'docs/blackjack-composition-{mode}{suffix}.svg'
        raw = path.read_text(encoding='utf-8')
        references = [value for node in ET.fromstring(raw).iter()
                      for key, value in node.attrib.items() if key.endswith('href')]
        for name in figure.FACES:
            assert f'id="Inter-{name}-' in raw
            assert any(value.startswith(f'#Inter-{name}-') for value in references)
        assert 'DejaVu' not in raw and '<text' not in raw and '@font-face' not in raw
        for node in ET.fromstring(raw).iter():
            for name, value in node.attrib.items():
                if name.endswith('href'):
                    assert value.startswith('#')


@pytest.mark.parametrize('key', ['value', 'margin', 'action', 'revision', 'units', 'rules'])
def test_changed_retained_meaning_is_rejected(key, tmp_path, monkeypatch):
    data = copy.deepcopy(figure.load_data())
    if key == 'value':
        data['hands'][0]['values']['H'] = 0.5346755624525633
    elif key == 'margin':
        data['hands'][0]['margin'] = .5
    elif key == 'action':
        data['hands'][0]['action'] = 'S'
    elif key == 'revision':
        data['source_commit'] = 'unknown'
    elif key == 'units':
        data['units'] = 'Win probability'
    else:
        data['rules'] = 'Infinite deck'
    (tmp_path / 'docs').mkdir()
    (tmp_path / figure.DATA).write_text(json.dumps(data), encoding='utf-8')
    monkeypatch.setattr(figure, 'ROOT', tmp_path)
    with pytest.raises(ValueError, match='retained values'):
        figure.load_data()


@pytest.mark.parametrize('changed', ['presentation/tokens.json',
                                     'docs/blackjack-composition-clair.png'])
def test_changed_inputs_or_outputs_fail_before_publication(changed, tmp_path, monkeypatch):
    files = [*figure.INPUTS, figure.MANIFEST, *figure.check_outputs()['outputs_sha256']]
    for name in files:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(figure.ROOT / name, target)
    with (tmp_path / changed).open('ab') as stream:
        stream.write(b'changed')
    monkeypatch.setattr(figure, 'ROOT', tmp_path)
    with pytest.raises(ValueError, match='Figure (input|output) changed'):
        figure.check_outputs()


def test_render_requires_explicit_fonts_and_does_not_download_them():
    result = subprocess.run([sys.executable, 'tools/render_composition_figure.py'],
                            cwd=figure.ROOT, capture_output=True, text=True)
    assert result.returncode == 2
    assert '--font-dir is required' in result.stderr


def test_real_consumers_use_both_editions_and_preserve_original_access():
    for name in ('README.md', 'docs/visual-example.md'):
        content = (figure.ROOT / name).read_text(encoding='utf-8')
        assert '<picture>' in content
        for mode in ('clair', 'obscur'):
            assert f'blackjack-composition-{mode}.png' in content
    page = (figure.ROOT / 'site/index.html').read_text(encoding='utf-8')
    for mode in ('clair', 'obscur'):
        assert f'src="composition-{mode}.png"' in page
        assert f'href="composition-{mode}.svg" download' in page
        assert f'href="composition-{mode}.png" download' in page
    assert 'href="example.svg"' in page
