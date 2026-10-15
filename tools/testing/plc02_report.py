"""PLC-02 qualification-only exact-node accounting; no application imports."""
import json
import os
from pathlib import Path


def pytest_addoption(parser):
    parser.addoption('--plc02-case-report',default=None)


def pytest_configure(config):
    config._plc02_cases={}


def pytest_collection_finish(session):
    session.config._plc02_nodes=[item.nodeid for item in session.items]


class Recorder:
    def __init__(self,config):self.config=config
    def pytest_runtest_logreport(self,report):
        cases=self.config._plc02_cases
        value=cases.setdefault(report.nodeid,{'phases':{},'duration':0.0})
        value['phases'][report.when]=report.outcome
        value['duration']+=report.duration


def pytest_sessionstart(session):
    session.config.pluginmanager.register(Recorder(session.config),'plc02-node-recorder')


def pytest_sessionfinish(session,exitstatus):
    name=session.config.getoption('--plc02-case-report')
    if name is None:return
    root=Path(__file__).resolve().parents[2]
    path=Path(name)
    if not path.is_absolute():path=root/path
    permitted=root/'output/plc02-evidence'
    if not path.is_relative_to(permitted) or '..' in path.parts:
        raise ValueError('PLC02_REPORT_PATH_INVALID')
    if any(p.is_symlink() for p in (path,*path.parents)):
        raise ValueError('PLC02_REPORT_PATH_INVALID')
    path.parent.mkdir(parents=True,exist_ok=True)
    value={'mode':'COLLECTION' if session.config.option.collectonly else 'EXECUTION',
           'exit_status':int(exitstatus),'nodes':getattr(session.config,'_plc02_nodes',[]),
           'cases':session.config._plc02_cases}
    raw=json.dumps(value,sort_keys=True,ensure_ascii=True,separators=(',',':')).encode()+b'\n'
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(raw)
