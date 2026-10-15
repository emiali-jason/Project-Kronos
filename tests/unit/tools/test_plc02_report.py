"""Qualification accounting carries identities/outcomes, never failure payloads."""
from types import SimpleNamespace
import pytest
from tools.testing.plc02_report import Recorder,pytest_sessionfinish as finish


def test_node_recorder_retains_separate_phases_and_duration_only():
    config=SimpleNamespace(_plc02_cases={});recorder=Recorder(config)
    for phase,outcome in (('setup','passed'),('call','failed'),('teardown','passed')):
        recorder.pytest_runtest_logreport(SimpleNamespace(nodeid='SYNTHETIC::case',when=phase,
            outcome=outcome,duration=0.25,longrepr='SYNTHETIC excluded payload'))
    assert config._plc02_cases=={'SYNTHETIC::case':{
        'phases':{'setup':'passed','call':'failed','teardown':'passed'},'duration':0.75}}
    assert 'payload' not in repr(config._plc02_cases)


@pytest.mark.parametrize('path',['/private/tmp/not-a-PLC02-report.json','output/plc02-evidence/../escaped.json'])
def test_report_cannot_publish_outside_qualification_output(path):
    session=SimpleNamespace(config=SimpleNamespace(getoption=lambda _:path))
    with pytest.raises(ValueError,match='PLC02_REPORT_PATH_INVALID'):finish(session,0)
