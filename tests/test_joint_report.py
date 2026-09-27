"""Audit saved values and output geometry without executing either solver."""
import ast
import copy
import csv
import io
import json
import math
import re
import xml.etree.ElementTree as ET

import pytest

from tools import render_joint_report as report


@pytest.fixture
def saved():
    return report.load()


def test_declared_aggregate_and_tie_tail(saved):
    # Independent arithmetic from retained root values, not the runner's gap fields.
    gaps = [row['production']['values']['P'] - row['reference']['value']
            for row in saved['rows']]
    assert min(gaps) == pytest.approx(-0.032142857142857195, abs=1e-14)
    assert max(gaps) <= 1e-12
    assert math.fsum(abs(value) for value in gaps) / 48 == pytest.approx(
        0.0030561067019400767, abs=1e-14)
    changes = [row for row in saved['rows'] if row['decision_changed']]
    assert len(changes) == 1
    assert changes[0]['id'] == 'balanced_high/5/6/das-true'
    assert changes[0]['production']['best'] == ['D']
    assert set(changes[0]['joint']['best']) == {'D', 'P'}
    assert changes[0]['joint']['margin'] == 0
    stats = report.summary(saved['rows'])
    assert (stats['completed'], stats['excluded'], stats['below'], stats['above'], stats['tied'],
            stats['changed'], stats['strict_changes']) == (48, 0, 8, 0, 40, 1, 0)


@pytest.mark.parametrize('mutation,reason', [
    (lambda data: data['rows'].pop(), 'lost or duplicated'),
    (lambda data: data['rows'].__setitem__(1, data['rows'][0]), 'condition identity'),
    (lambda data: data.update(evaluated_revision=report.INVALID), 'corrected measured'),
    (lambda data: data['rows'][0].update(production_shoe=data['rows'][0]['shoe']),
     'different rank compositions'),
    (lambda data: data['rows'][0].update(signed_gap=0.1), 'signed gap'),
    (lambda data: data['rows'][0]['joint'].update(best=[]), 'recommendation differs'),
    (lambda data: data['rows'][0]['joint'].update(margin=0.8), 'margin differs'),
    (lambda data: data['rows'][0]['joint']['values'].update(S=0.4), 'recommendation|single hand'),
    (lambda data: data['rows'][0]['reference'].update(states=0), 'work count'),
    (lambda data: data['rows'][0]['reference'].update(maximum_probability_mass_error=.1),
     'probability mass'),
])
def test_auditor_rejects_changed_conditions_and_misleading_values(saved, mutation, reason):
    changed = copy.deepcopy(saved)
    mutation(changed)
    with pytest.raises(ValueError, match=reason):
        report.validate(changed, saved['protocol'])


def test_unsupported_condition_is_retained_without_numeric_imputation(saved):
    saved['rows'][0] = dict(saved['rows'][0], status='unsupported', error='No drawable card')
    saved['status'] = 'with_exclusions'
    report.validate(saved, saved['protocol'])
    rows = list(csv.DictReader(io.StringIO(report.csv_data(saved['rows']))))
    assert len(rows) == 48 and rows[0]['error'] == 'No drawable card'
    assert rows[0]['joint_split'] == rows[0]['signed_gap'] == ''
    assert report.summary(saved['rows'])['excluded'] == 1
    assert 'No drawable card' in report.table(saved['rows'])


def test_changed_result_cannot_reuse_the_authored_interpretation(tmp_path, monkeypatch, saved):
    (tmp_path / 'docs').mkdir()
    saved['rows'][0]['reference']['elapsed_seconds'] = .1
    (tmp_path / report.DATA).write_text(json.dumps(saved), encoding='utf-8')
    monkeypatch.setattr(report, 'ROOT', tmp_path)
    with pytest.raises(ValueError, match='retained result bytes changed'):
        report.load()


def test_download_values_roundtrip_without_rounding_and_schema_identity(saved):
    rows = list(csv.DictReader(io.StringIO(report.csv_data(saved['rows']))))
    for original, exported in zip(saved['rows'], rows, strict=True):
        assert original['id'] == exported['id']
        assert float(exported['joint_split']) == original['reference']['value']
        assert float(exported['production_split']) == original['production']['values']['P']
        assert float(exported['signed_gap']) == original['signed_gap']
        assert int(exported['states']) == original['reference']['states']
        assert dict(zip(report.RANKS, original['shoe'], strict=True)) == dict(zip(
            original['production_rank_order'], original['production_shoe'], strict=True))


def test_figure_positions_share_one_quantitative_scale_and_meaning(saved):
    ns = {'s': 'http://www.w3.org/2000/svg'}
    for mode, index in [('Clair', 0), ('Obscur', 1)]:
        tree = ET.fromstring(report.svg(saved, {}, mode))
        groups = tree.findall('s:g[@data-condition]', ns)
        assert len(groups) == 48
        for group, row in zip(groups, saved['rows'], strict=True):
            assert group.attrib['data-condition'] == row['id']
            marker = group.find('s:rect' if row['double_after_split'] else 's:circle', ns)
            assert marker is not None
            x = float(marker.attrib['x']) + 4 if row['double_after_split'] else float(
                marker.attrib['cx'])
            expected = 690 + (row['production']['values']['P'] - row['reference']['value']) * 6000
            assert x == pytest.approx(expected, abs=1e-10)
            assert marker.attrib['fill'] == report.PALETTE[row['dealer_up']][index]
        assert len(tree.findall('s:style', ns)) == 1
        assert tree.find('s:style', ns).text.count('@font-face') == 6
        assert 'url(' not in ET.tostring(tree, encoding='unicode')


def test_rendered_artifacts_retain_identity_invalid_attempt_and_local_links(saved):
    outputs = report.render_outputs()
    record = json.loads(outputs['joint-split-presentation.json'])
    assert record['evaluated_revision'] == report.MEASURED
    assert record['invalid_first_revision'] == report.INVALID
    assert record['experiment_rerun'] is False
    assert json.loads(outputs['joint-split-results.json']) == saved
    first = json.loads(outputs['joint-split-first-invalid.json'])
    assert first['evaluated_revision'] == report.INVALID
    assert record['summary']['mean_absolute'] == report.summary(saved['rows'])['mean_absolute']
    text = outputs['joint-split.html'].decode()
    assert 'The first comparison was invalid' in text
    assert 'excluded from every summary and figure' in text
    assert '1 tie expansion' in text and 'no strict reversal' in text
    assert '{measured}' not in text and '{table}' not in text
    local_links = re.findall(r'href="(joint-split[^"#]+)"', text)
    assert set(local_links) <= set(outputs)
    assert set(outputs) - {'joint-split.html'} == set(local_links)
    assert 'sourceMappingURL' not in text and 'https://fonts' not in text
    assert text.count('<tr>') == 51  # Two headers, 48 conditions and one changed set.
    assert text.index('@media print') > text.index('@media(prefers-color-scheme:dark)')


def test_renderer_does_not_import_either_solver_or_comparison_runner():
    source = (report.ROOT / 'tools/render_joint_report.py').read_text()
    modules = [node.module for node in ast.walk(ast.parse(source))
               if isinstance(node, ast.ImportFrom)]
    assert not any(module and (module.startswith('bj') or 'compare_joint' in module)
                   for module in modules)
    assert 'joint_split_value' not in source and 'best_action(' not in source
