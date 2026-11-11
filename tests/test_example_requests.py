"""The published example requests stay runnable, replayable and linked from the README."""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from bj import calculation as calc, replay
from bj.caches import clear_all_caches
from test_calculation import policy
from test_resplit_calculation import fixed_message, returned

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / 'README.md').read_text(encoding='utf-8')
EXAMPLES = sorted((ROOT / 'examples').glob('*-request.json'))
LINK = re.compile(r'\[[^\]]+\]\(([^)#]+)(?:#[^)]*)?\)')


def model_table():
    """Rows of the README table of supported calculation models."""
    lines = README.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith('| Selected calculation |'))
    rows = []
    for line in lines[start + 2:]:
        if not line.startswith('|'):
            break
        selected, _scope, links = (cell.strip() for cell in line.strip('|').split('|'))
        rows.append((selected, LINK.findall(links)))
    return rows


@pytest.fixture(autouse=True)
def cold_caches():
    clear_all_caches()
    yield
    clear_all_caches()


def test_every_model_row_links_an_existing_guide_and_matching_request():
    rows = model_table()
    assert len(rows) == 6
    for selected, links in rows:
        guides = [link for link in links if link.startswith('docs/')]
        requests = [link for link in links if link.startswith('examples/')]
        assert len(guides) == 1 and len(requests) == 1, selected
        assert (ROOT / guides[0]).is_file(), guides[0]
        request = json.loads((ROOT / requests[0]).read_bytes())
        named = re.fullmatch(r'`(\w+)`, version (\d+)', selected)
        if named is None:
            assert selected == 'Original/default'
            assert 'model' not in request and request['schema']['version'] == 1
        else:
            assert request['model'] == {'name': named[1], 'version': int(named[2])}


def test_every_example_request_is_linked_from_the_readme_or_a_guide():
    linked = set()
    for document in [ROOT / 'README.md', *(ROOT / 'docs').glob('*.md')]:
        for target in LINK.findall(document.read_text(encoding='utf-8')):
            linked.add((document.parent / target).resolve())
    assert EXAMPLES
    assert [path.name for path in EXAMPLES if path.resolve() not in linked] == []


def calculate(tmp_path, path):
    """Owned worker arithmetic in process, then the parent's validation and publication."""
    code, message, _, _ = fixed_message(json.loads(path.read_bytes()))
    assert (code, message['status'], message['error']) == (0, 'completed', None)
    source = tmp_path / path.name
    source.write_bytes(path.read_bytes())
    with patch.object(calc, 'execute', side_effect=returned(message, code)):
        receipt = calc._run(source, tmp_path / 'attempt', policy(), threading.Event())
    assert receipt['status'] == 'completed'
    raw = (tmp_path / 'attempt/result/decision.json').read_bytes()
    assert json.loads(raw) == message['decision']
    return raw, receipt


@pytest.mark.parametrize('path', EXAMPLES, ids=[path.stem for path in EXAMPLES])
def test_example_request_completes_and_its_saved_record_replays_in_agreement(tmp_path, path):
    raw, _ = calculate(tmp_path, path)
    clear_all_caches()
    report = replay.replay_json(raw)
    assert report['status'] == 'agreement'
    assert report['recomputed'] == json.loads(raw)['decision']


def test_readme_h17_ace_values_are_the_example_calculation(tmp_path):
    section = README.split('## A complete H17 ace calculation', 1)[1].split('\n## ', 1)[0]
    assert '(examples/bounded-ace-resplit-h17-request.json)' in section
    printed = dict(re.findall(r'^\| ([SHDP]), \w+ \| (-?\d\.\d+) \|$', section, re.MULTILINE))
    selected = re.search(r'selects ([SHDP]) with margin `(\d\.\d+)`', section)
    assert set(printed) == {'S', 'H', 'D', 'P'} and selected is not None
    path = ROOT / 'examples/bounded-ace-resplit-h17-request.json'
    request = json.loads(path.read_bytes())
    raw, receipt = calculate(tmp_path, path)
    decision = json.loads(raw)['decision']
    # The README prints each binary64 value in its shortest round trip form.
    assert {action: repr(value) for action, value in decision['evs'].items()} == printed
    assert (decision['action'], repr(decision['margin'])) == (selected[1], selected[2])
    # The prose around the table describes the same cold request and its work.
    counts = ','.join(map(str, request['input']['unseen_counts']))
    assert f'Counts were `[{counts}]`' in section
    assert f"faced dealer {request['input']['dealer_up']} after a negative peek" in section
    assert request['rules']['s17'] is False and 'with H17 and DAS enabled' in section
    assert request['rules'].get('das', True) is True
    work = receipt['work']
    assert (work['states'], work['limit']) == (82780, request['limits']['max_states'])
    assert f"in {work['states']:,} entered states" in section
    assert f"unchanged {work['limit']:,} state cap" in section
