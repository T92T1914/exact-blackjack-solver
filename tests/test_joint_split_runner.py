"""Declared Cartesian cases, explicit limits and retained attempt boundaries."""
import json
import subprocess
import sys
from copy import deepcopy

from tools import compare_joint_split as study


def test_protocol_has_all_cases_without_filtering_results():
    protocol = json.loads(study.PROTOCOL.read_text())
    cases = study.conditions(protocol)
    assert len(cases) == len({c['id'] for c in cases}) == 48
    assert all(sum(c['shoe']) == 8 for c in cases)
    assert cases[0]['id'] == 'balanced_high/2/6/das-false'
    assert cases[-1]['id'] == 'ten_rich/A/A/das-true'


def test_ranking_exposes_ties_and_does_not_relabel_other_actions():
    values = {'S': 0.1, 'H': 0.1 + 1e-14, 'D': -0.4, 'P': -0.2}
    result = study.ranking(values, 1e-12)
    assert result['best'] == ['S', 'H']
    assert result['margin'] < 1e-12
    assert result['values'] == values
    assert study.ranking(dict(values, P=0.7), 1e-12)['best'] == ['P']


def test_separate_seven_card_pilot_preserves_both_values_and_work():
    protocol = json.loads(study.PROTOCOL.read_text())
    case = dict(id='test/pilot-seven', pair='5', dealer_up='T',
                shoe=[0, 0, 0, 0, 0, 2, 1, 1, 3, 0], double_after_split=True)
    result = study.run_case(case, protocol)
    assert result['status'] == 'completed'
    assert result['reference']['states'] > 0
    assert abs(result['reference']['value'] + 9 / 7) < 1e-12
    assert result['production']['values']['S'] == result['joint']['values']['S']
    assert result['production']['values']['H'] == result['joint']['values']['H']
    assert result['production']['values']['D'] == result['joint']['values']['D']
    assert result['signed_gap'] == (result['production']['values']['P']
                                    - result['joint']['values']['P'])
    assert result['worker_exit_code'] == 0


def test_timeout_is_retained_and_owned_child_is_stopped():
    protocol = deepcopy(json.loads(study.PROTOCOL.read_text()))
    protocol['limits']['case_wall_seconds'] = 0
    case = dict(id='test/deadline', pair='A', dealer_up='7',
                shoe=[0, 0, 0, 0, 0, 0, 0, 0, 4, 0], double_after_split=False)
    result = study.run_case(case, protocol)
    assert result['status'] == 'timed_out'
    assert result['worker_exit_code'] is not None
    assert 'signed_gap' not in result


def test_existing_attempt_is_not_overwritten(tmp_path):
    output = tmp_path / 'retained.json'
    output.write_text('retained first failure')
    result = subprocess.run([sys.executable, str(study.ROOT / 'tools/compare_joint_split.py'),
                             '--output', str(output)], capture_output=True, text=True)
    assert result.returncode != 0
    assert output.read_text() == 'retained first failure'


def test_atomic_snapshot_keeps_failure_and_unattempted_cases(tmp_path):
    output = tmp_path / 'attempt.json'
    data = dict(status='interrupted', rows=[dict(id='first', status='unsupported')],
                unattempted=['second'])
    study.write(output, data)
    assert json.loads(output.read_text()) == data
    assert list(tmp_path.iterdir()) == [output]
