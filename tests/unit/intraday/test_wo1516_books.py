"""Dedicated WO15/16 authority tests: isolated sources only, no production state."""
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from threading import RLock
from zipfile import ZipFile
import csv
import json
import pytest

from kronos.application.intraday_books import IntradayBooks, FactualRow, factual_row
from kronos.application.intraday_lifecycle import IntradayLifecycleApplication
from kronos.browser.reports import (INTRADAY_FIELDS, project_intraday_reports, ReportsQuery, ReportProduct, ReportView, export_reports_json, export_reports_csv, export_reports_xlsx, reports_excel_filename)
from kronos.swing.v1.models import V1Direction
from kronos.browser.views import render_portfolio, render_reports
from kronos.intraday.wo11_lifecycle_contract import digest
from tests.unit.intraday.test_wo14_journal import build, Fact, Facts
from tests.unit.intraday.test_wo11_lifecycle import tick, NOW
from tests.unit.application.test_swing_opportunities import _ready
from tests.unit.browser.test_browser_reports import _xlsx_rows


def fixture(tmp_path, *, truth="PAPER_POSITION", state="ACTIVE", entered=True, monitoring="LIVE"):
    journal, futures, lifecycle, selection, action, old = build(tmp_path)
    d = dict(old.data, truth_class=truth, state=state, display_state=state,
             entry=old.data["entry"] if entered else None,
             exit=None if state=="ACTIVE" else old.data["exit"],
             exit_reason=None if state=="ACTIVE" else old.data["exit_reason"],
             terminal_status=None if state=="ACTIVE" else old.data["terminal_status"],
             last_price="105", last_observed_at="2026-09-13T10:15:00+05:30", last_sequence=7,
             last_connection="CONNECTION", last_fact_identity="FACT", baseline_required=False, gaps=[])
    current = Fact("TRACK", d)
    lifecycle.store.values["TRACK"] = current
    lifecycle.store.restore = lambda: (current,)
    lifecycle.portfolio_observation = lambda identity, retained: dict(monitoring=monitoring,
        price="105" if monitoring=="LIVE" else None, observed_at=d["last_observed_at"] if monitoring=="LIVE" else None)
    books = IntradayBooks(research=journal.research, futures=futures, lifecycle=lifecycle)
    books.bind()
    return books, journal, futures, lifecycle, current


def projection(books, **filters):
    return project_intraday_reports(books.snapshot(), ReportsQuery(product=ReportProduct.INTRADAY, **filters))


@pytest.mark.parametrize("truth,entered,state,count", [
    ("PAPER_POSITION",True,"ACTIVE",1), ("PAPER_OBSERVATION",True,"ACTIVE",0),
    ("PAPER_POSITION",False,"ACTIVE",0), ("PAPER_POSITION",True,"CLOSED",0),
    ("PAPER_POSITION",False,"EXPIRED_BEFORE_ENTRY",0),
    ("PAPER_POSITION",True,"OUTCOME_AMBIGUOUS",0),
    ("PAPER_POSITION",True,"CLOSED_OUTCOME_UNAVAILABLE",0),
])
def test_wo15_exposure_population(tmp_path,truth,entered,state,count):
    books,*_ = fixture(tmp_path,truth=truth,entered=entered,state=state)
    assert len(books.portfolio()) == count
    assert len(projection(books).records) == 1


@pytest.mark.parametrize("field,expected", [("opportunity_id","LUPIN-20260913-100000"),
    ("opportunity_identity","OPP-IDENTITY"),("track_identity","AUTH"),("model_lots",1),
    ("selected_lots_context",4),("subject","NSE-EQ-LUPIN"),("direction","LONG")])
def test_wo15_exact_upstream_facts(tmp_path,field,expected):
    books,*_ = fixture(tmp_path)
    assert books.portfolio()[0][field] == expected


@pytest.mark.parametrize("state",["LIVE","INTERRUPTED","IDLE","UNAVAILABLE"])
def test_wo15_per_owner_state_preserves_exposure(tmp_path,state):
    books,*_ = fixture(tmp_path,monitoring=state)
    row, = books.portfolio()
    assert row["current_observation"]["monitoring"] == state
    assert (row["current_observation"]["price"] is not None) == (state=="LIVE")
    assert (row["metrics"] is not None) == (state=="LIVE")
    assert len(books.portfolio(monitoring=state)) == 1
    assert books.portfolio(monitoring="SOMETHING_ELSE") == ()


@pytest.mark.parametrize("needle,count",[("LUPIN",1),("LUPIN-20260913",1),("26SEPFUT",1),("RELIANCE",0)])
def test_wo15_search(tmp_path,needle,count):
    books,*_ = fixture(tmp_path)
    assert len(books.portfolio(search=needle)) == count


def test_wo15_cached_reads_and_restart(tmp_path):
    books,journal,futures,lifecycle,current = fixture(tmp_path)
    before = books.portfolio()
    source = dict(lifecycle.store.values)
    for item in (books.research,futures,lifecycle.store):
        item.load = lambda *args: (_ for _ in ()).throw(AssertionError("SOURCE_SCAN_ON_GET"))
        item.records = item.load
    lifecycle.store.restore = lifecycle.store.load
    for _ in range(5):
        assert books.portfolio() == before
        assert projection(books).records[0].record_identity == before[0]["record_identity"]
    assert lifecycle.store.values == source
    assert lifecycle.owner_count == lifecycle.subscription_count == 1
    restarted,*_ = fixture(tmp_path / "restart")
    assert restarted.portfolio() == before


@pytest.mark.parametrize("product",["SWING","INTRADAY"])
def test_wo15_shared_shell_and_no_controls(tmp_path,product):
    books,*_ = fixture(tmp_path)
    html=render_portfolio(_ready(),books.portfolio(),product=product)
    assert 'action="/portfolio"' not in html if product=="SWING" else 'method="get"' in html
    assert 'method="post" action="/portfolio' not in html
    assert 'DELETE' not in html and 'SPONSOR EXIT' not in html
    assert '/assets/brand' in html or 'brandmark' in html
    assert 'href="/portfolio?product=SWING"' in html and 'href="/portfolio?product=INTRADAY"' in html


def test_wo15_empty_healthy_and_live_not_commissioned():
    html=render_portfolio(_ready(),product="INTRADAY")
    assert "NO ACTIVE INTRADAY PAPER POSITIONS" in html and "LIVE is not commissioned" in html


@pytest.mark.parametrize("truth",["PAPER_POSITION","PAPER_OBSERVATION"])
@pytest.mark.parametrize("state",["ACTIVE","CLOSED","OUTCOME_AMBIGUOUS","CLOSED_OUTCOME_UNAVAILABLE","EXPIRED_BEFORE_ENTRY"])
def test_wo16_full_truth_population(tmp_path,truth,state):
    books,*_ = fixture(tmp_path,truth=truth,state=state,entered=state!="EXPIRED_BEFORE_ENTRY")
    report=projection(books)
    values=json.loads(report.records[0].intraday_facts)
    assert values["truth_class"]==truth and values["status"]==state
    assert values["model_lots"]==1 and values["track_identity"]=="AUTH"
    assert report.overview.net_pnl is None and report.overview.win_rate is None
    assert len(projection(books,view=ReportView.ALL_RECORDS).records)==1
    assert projection(books,view=ReportView.LIVE).records==()


@pytest.mark.parametrize("kind,identity,truth",[("SELECTION","SELECTION","NONE"),("ACTION","ACTION","DO_NOTHING")])
def test_wo16_unselected_decisions_not_exposure(tmp_path,kind,identity,truth):
    books,journal,*_ = fixture(tmp_path)
    books.snapshot()
    books.consume_source(kind,identity)
    rows=[r for r in projection(books).records if json.loads(r.intraday_facts)["truth_class"]==truth]
    assert len(rows)==1
    value=json.loads(rows[0].intraday_facts)
    assert value["entry"] is None and value["model_lots"] is None and value["track_identity"] is None
    assert len(books.portfolio())==1


@pytest.mark.parametrize("kwargs,count",[
    ({"instrument":"LUPIN"},1),({"instrument":"LUPIN-20260913"},1),({"instrument":"OTHER"},0),
    ({"from_date":date(2026,9,14)},0),({"to_date":date(2026,9,12)},0),
    ({"from_date":date(2026,9,13),"to_date":date(2026,9,13)},1),
    ({"view":ReportView.PAPER},1),({"view":ReportView.PAPER_OBSERVATIONS},0),({"view":ReportView.LIVE},0),
    ({"status":"CLOSED"},1),({"status":"TARGET"},1),({"status":"STOP_LOSS"},0),
    ({"exit_reason":"TARGET"},1),({"exit_reason":"STOP_LOSS"},0),
    ({"completeness":"COMPLETE"},1),({"completeness":"INCOMPLETE"},0),
    ({"direction":V1Direction.LONG},1),({"direction":V1Direction.SHORT},0)])
def test_wo16_filters_and_export_fidelity(tmp_path,kwargs,count):
    books,*_ = fixture(tmp_path,state="CLOSED")
    p=projection(books,**kwargs)
    assert p.total_records==count
    assert len(json.loads(export_reports_json(p))["records"])==count
    assert len(list(csv.DictReader(export_reports_csv(p).decode().splitlines())))==count
    assert len(_xlsx_rows(export_reports_xlsx(p,generated_at=NOW)))==count+1


@pytest.mark.parametrize("prefix",["=1+1","+SUM(1)","-TEXT","@SUM(1)","  =1+1","\t=1+1"])
def test_wo16_formula_safe_text_numeric_preserved(tmp_path,prefix):
    books,*_ = fixture(tmp_path,state="CLOSED")
    rows=books.snapshot(); d=rows[0].data;d["opportunity_id"]=prefix;d["metrics"]["points"]="-2"
    row=factual_row(**d)
    p=project_intraday_reports((row,),ReportsQuery(product=ReportProduct.INTRADAY))
    exported=list(csv.DictReader(export_reports_csv(p).decode().splitlines()))[0]
    assert exported["opportunity_id"].startswith("'") and exported["points"]=="-2"
    with ZipFile(BytesIO(export_reports_xlsx(p,generated_at=NOW))) as archive:
        xml=archive.read("xl/worksheets/sheet1.xml").decode()
        assert '<f>' not in xml and '<v>-2</v>' in xml and 'inlineStr' in xml
        assert not any('externalLink' in name or 'vba' in name for name in archive.namelist())


@pytest.mark.parametrize("truth",["PAPER_POSITION","PAPER_OBSERVATION"])
def test_cross_journal_suppression_is_independent(tmp_path,truth):
    books,journal,futures,lifecycle,current=fixture(tmp_path,truth=truth)
    books.snapshot();journal.consume_source("TRACK",current.identity)
    journal_row,=journal.snapshot().records
    before=(books.portfolio(),projection(books).records,dict(lifecycle.store.values),dict(journal.research.values))
    journal.suppress(journal_identity=journal_row.journal_identity,revision_identity=journal_row.revision_identity,action_identity="DELETE_PRESENTATION")
    assert journal.snapshot().records==()
    assert before==(books.portfolio(),projection(books).records,dict(lifecycle.store.values),dict(journal.research.values))
    assert lifecycle.owner_count==lifecycle.subscription_count==1
    assert journal_row.data["opportunity_id"]==json.loads(projection(books).records[0].intraday_facts)["opportunity_id"]


@pytest.mark.parametrize("reason",["TARGET","STOP_LOSS","SPONSOR_EXIT"])
def test_cross_authoritative_terminal_replaces_exposure_retains_history(tmp_path,reason):
    from kronos.application.notifications import notify_book_persisted
    books,journal,futures,lifecycle,current=fixture(tmp_path)
    assert len(books.portfolio())==1
    terminal=Fact("TERMINAL",dict(current.data,state="CLOSED",display_state="CLOSED",exit_reason=reason,terminal_status="CLOSED",
        exit={"price":"110","at":"2026-09-13T11:00:00+05:30","identity":"EXIT"}))
    lifecycle.store.values[terminal.identity]=terminal
    notify_book_persisted(lifecycle.store,"TRACK",terminal.identity)
    journal.consume_source("TRACK",terminal.identity)
    assert books.portfolio()==()
    assert len(projection(books).records)==1 and len(journal.snapshot().records)==1
    assert json.loads(projection(books).records[0].intraday_facts)["exit_reason"]==reason


def test_wo16_compact_allowlist_no_paths_payloads_or_research(tmp_path):
    books,*_ = fixture(tmp_path,state="CLOSED")
    p=projection(books)
    data=json.loads(export_reports_json(p));row=data["records"][0]
    assert set(row)==set(INTRADAY_FIELDS)
    assert row["source_lifecycle_identity"]=="TRACK" and row["source_identities"]
    assert row["opportunity_identity"]=="OPP-IDENTITY"
    for forbidden in ('/Users/', 'access_token', 'raw_ticks', 'intake', 'observations', 'expectancy', 'win_rate'):
        assert forbidden not in export_reports_json(p).decode()
    assert reports_excel_filename(p,NOW).startswith('KRONOS_INTRADAY_FACTUAL_REPORT_')
    assert 'Research' not in reports_excel_filename(p,NOW)


@pytest.mark.parametrize("state",["IDLE","INTERRUPTED","UNAVAILABLE","LIVE"])
def test_wo15_real_owner_read_ignores_rest_connected(state):
    t=tick()
    from dataclasses import asdict
    from kronos.provider.contracts.monitoring import MonitoringConnectionState
    retained=dict(last_price=str(t.last_price),last_observed_at=t.observed_at.isoformat(),last_sequence=t.source_sequence,
        last_connection=t.connection_id,last_fact_identity='WO11_SOURCE_FACT-'+digest(asdict(t)),baseline_required=False,monitoring='AVAILABLE')
    app=IntradayLifecycleApplication(futures=None,store=None,clock=lambda:NOW,session_source=None,timing_source=None,operational_guard=None)
    app._hub=SimpleNamespace(latest_market_ticks=(t,),subscription_owner_identities=lambda instrument:('INTRADAY-WO11-LIFECYCLE:AUTH',)) if state!='UNAVAILABLE' else None
    if state in {'LIVE','INTERRUPTED'}:
        app._registrations['AUTH']=(SimpleNamespace(active=True,connection_state=MonitoringConnectionState.CONNECTED if state=='LIVE' else MonitoringConnectionState.DISCONNECTED),SimpleNamespace(active=True))
    value=app.portfolio_observation('AUTH',retained)
    assert value['monitoring']==state and (value['price'] is not None)==(state=='LIVE')


@pytest.mark.parametrize("change",['newer','late','recovered','gap','other_owner','fact_mismatch'])
def test_wo15_no_stale_cached_or_unowned_price(change):
    from dataclasses import asdict
    from kronos.provider.contracts.monitoring import MonitoringConnectionState
    t=tick();retained=dict(last_price=str(t.last_price),last_observed_at=t.observed_at.isoformat(),last_sequence=t.source_sequence,
        last_connection=t.connection_id,last_fact_identity='WO11_SOURCE_FACT-'+digest(asdict(t)),baseline_required=False,monitoring='AVAILABLE')
    if change=='newer':t=tick(seconds=3)
    if change=='late':t=tick(lag=6)
    if change=='recovered':t=tick(recovered=True)
    if change=='gap':retained['baseline_required']=True
    if change=='fact_mismatch':retained['last_fact_identity']='WRONG'
    app=IntradayLifecycleApplication(futures=None,store=None,clock=lambda:NOW,session_source=None,timing_source=None,operational_guard=None)
    app._hub=SimpleNamespace(latest_market_ticks=(t,),subscription_owner_identities=lambda instrument:() if change=='other_owner' else ('INTRADAY-WO11-LIFECYCLE:AUTH',))
    app._registrations['AUTH']=(SimpleNamespace(active=True,connection_state=MonitoringConnectionState.CONNECTED),SimpleNamespace(active=True))
    assert app.portfolio_observation('AUTH',retained)['price'] is None


@pytest.mark.parametrize('key,value',[('subject','/Users/example/private'),('decision_identity','Bearer secret'),
    ('source_identities',['file://sensitive']),('opportunity_identity','/private/evidence')])
def test_wo16_rejects_nonportable_source_text(tmp_path,key,value):
    books,*_=fixture(tmp_path);d=books.snapshot()[0].data;d[key]=value
    with pytest.raises(ValueError,match='NONPORTABLE'):
        factual_row(**d)


def test_wo16_population_capacity_is_explicit_not_truncation(tmp_path,monkeypatch):
    import kronos.application.intraday_books as module
    books,*_=fixture(tmp_path);books.snapshot();monkeypatch.setattr(module,'MAX_RECORDS',1)
    with pytest.raises(ValueError,match='CAPACITY'):
        books.consume_source('ACTION','ACTION')
    with pytest.raises(ValueError,match='SOURCE_UNAVAILABLE'):
        books.snapshot()


def test_wo15_source_failure_cannot_leave_stale_exposure(tmp_path):
    books,*_=fixture(tmp_path);assert len(books.portfolio())==1
    with pytest.raises(KeyError):books.consume_source('TRACK','MISSING')
    with pytest.raises(ValueError,match='SOURCE_UNAVAILABLE'):books.portfolio()


@pytest.mark.parametrize('number,name',[(15,'portfolio'),(16,'reports')])
def test_separate_policy_contracts_match_publications(number,name):
    import importlib
    from pathlib import Path
    policy=importlib.import_module(f'kronos.intraday.wo{number}_{name}')
    root=Path(__file__).resolve().parents[3]
    document=json.loads((root/f'docs/architecture/products/intraday/KRONOS-INTRADAY-WO{number}-{name.upper()}-POLICY-V1.json').read_text())
    assert document['policy_checksum']==policy.POLICY_CHECKSUM
    assert document['rules']==policy.RULES
    assert document['policy_identity']==policy.POLICY_IDENTITY
