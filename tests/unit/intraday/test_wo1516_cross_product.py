"""Cross-product tests with real notification stores and governed lifecycle paths."""
from datetime import timedelta
from decimal import Decimal
import json
import pytest
from kronos.application.intraday_books import IntradayBooks
from kronos.application.intraday_journal import IntradayJournalApplication
from kronos.intraday.wo14_journal_store import JournalStore
from tests.unit.intraday.test_wo1516_books import fixture, projection, Facts, Fact
from tests.unit.intraday.test_wo13_notifications import centre, details, NOW


@pytest.mark.parametrize("truth",["PAPER_POSITION","PAPER_OBSERVATION"])
@pytest.mark.parametrize("mutation",["dismiss","expire_delete","journal_delete"])
def test_cross_deletions_preserve_independent_products(tmp_path,truth,mutation):
    books,journal,futures,lifecycle,current=fixture(tmp_path,truth=truth)
    journal.consume_source("TRACK",current.identity)
    jr,=journal.snapshot().records
    notification=centre(tmp_path)
    row=books.snapshot()[0].data
    notice=notification.accept_intraday(details("PAPER_ENTRY" if truth=="PAPER_POSITION" else "OBSERVATION_ENTRY",
        opportunity_id=row["opportunity_id"],opportunity_identity=row["opportunity_identity"],
        subject=row["subject"],track_identity=row["track_identity"],truth_class=truth,lots=1))
    before=(books.portfolio(),projection(books).records,dict(lifecycle.store.values),dict(journal.research.values))
    notice_before=notification.snapshot(product="INTRADAY")
    if mutation=="journal_delete":
        journal.suppress(journal_identity=jr.journal_identity,revision_identity=jr.revision_identity,action_identity="DELETE")
        assert notification.snapshot(product="INTRADAY")==notice_before
    elif mutation=="dismiss":
        notification.dismiss(notice.notification_identity,notice.integrity_sha256,occurred_at=NOW+timedelta(seconds=1))
        assert journal.snapshot().records==(jr,)
    else:
        notification.expire(notice.notification_identity,notice.integrity_sha256,source_still_valid=False,occurred_at=NOW+timedelta(seconds=1))
        assert notification.dismiss_expired(product="INTRADAY",occurred_at=NOW+timedelta(seconds=2))==1
        assert journal.snapshot().records==(jr,)
    assert before==(books.portfolio(),projection(books).records,dict(lifecycle.store.values),dict(journal.research.values))
    assert lifecycle.owner_count==lifecycle.subscription_count==1
    assert row["opportunity_id"]==jr.data["opportunity_id"]
    assert row["opportunity_identity"]==jr.data["opportunity_identity"]
    assert len(books.portfolio())==int(truth=="PAPER_POSITION")


@pytest.mark.parametrize("action",["ACTIVATE_PAPER","OBSERVE"])
@pytest.mark.parametrize("reason",["TARGET","STOP_LOSS","SPONSOR_EXIT"])
def test_cross_real_lifecycle_entry_exit_and_restart(tmp_path,monkeypatch,action,reason):
    from tests.unit.intraday.test_wo11_lifecycle_application import fixture as real_fixture, emit
    from kronos.intraday.wo12_research_contract import opportunity_origin
    app,handoff,f,provider,clock,cap,hub=real_fixture(tmp_path,monkeypatch)
    intake=handoff.data["plan"]
    opportunity=handoff.data["selection"]["comparison"]["opportunity_identity"]
    # Exact established origin supplied by the isolated upstream fixture.
    origin=Fact("ORIGIN",dict(schema="WO12_OPPORTUNITY_ORIGIN_V1",opportunity_id="TEST-20260911-111500",
        opportunity_identity=opportunity,origin_at=clock[0].isoformat(),market_family="NSE_EQUITY"))
    sources=Facts(origin)
    books=IntradayBooks(research=sources,futures=app.futures.store,lifecycle=app);books.bind()
    journal=IntradayJournalApplication(research=sources,futures=app.futures.store,lifecycle=app,store=JournalStore(tmp_path/'journal'));journal.bind()
    assert books.snapshot()==()
    current=app.action(handoff_identity=handoff.identity,action=action,action_identity='ARM')
    assert books.portfolio()==()
    clock[0]+=timedelta(minutes=5);app.pulse();current=app.store.restore()[0]
    clock[0]+=timedelta(seconds=1)
    current=emit(app,cap,clock,current,str(Decimal(current.data['intake']['entry'])+1))
    assert current.data['state']=='ACTIVE'
    assert len(books.portfolio())==int(action=='ACTIVATE_PAPER')
    if action=='ACTIVATE_PAPER':
        row,=books.portfolio()
        assert row['current_observation']['price']==current.data['last_price']
        assert row['model_lots']==1 and current.data['intake']['selected_lots']==25
    active_report=projection(books)
    ids=(active_report.records[0].record_identity, json.loads(active_report.records[0].intraday_facts)['opportunity_identity'])
    calls=tuple(provider.calls); owners=hub.status_document()['owner_count']
    restored=IntradayBooks(research=sources,futures=app.futures.store,lifecycle=app)
    assert projection(restored).records==active_report.records
    assert hub.status_document()['owner_count']==owners and tuple(provider.calls)==calls
    clock[0]+=timedelta(seconds=1)
    if reason=='SPONSOR_EXIT':
        authorization=app.store.load(current.data['authorization_identity'])
        app.close_track(claim=authorization.data['claim'],action_identity='SPONSOR-CLOSE')
        clock[0]+=timedelta(seconds=1);value=current.data['last_price']
    else:
        value=str(Decimal(current.data['intake']['target'])+1) if reason=='TARGET' else str(Decimal(current.data['intake']['stop'])-1)
    current=emit(app,cap,clock,current,value)
    assert current.data['exit_reason']==reason
    assert books.portfolio()==()
    assert len(projection(books).records)==1 and len(journal.snapshot().records)==1
    assert projection(books).records[0].record_identity==ids[0]
    assert len(app.store.records('WO11_WO12_HANDOFF_V1'))==1
    assert len(app.store.records('WO11_ENTRY_V1'))==len(app.store.records('WO11_EXIT_V1'))==1
    assert tuple(provider.calls)==calls


@pytest.mark.parametrize('truth',['PAPER_POSITION','PAPER_OBSERVATION'])
@pytest.mark.parametrize('product',['SWING','INTRADAY'])
def test_cross_switching_and_research_reads_inert(tmp_path,truth,product):
    from kronos.browser.views import render_portfolio,render_reports
    from tests.unit.application.test_swing_opportunities import _ready
    books,journal,futures,lifecycle,current=fixture(tmp_path,truth=truth)
    before=(books.snapshot(),dict(journal.research.values),dict(lifecycle.store.values))
    render_portfolio(_ready(),books.portfolio(),product=product)
    render_reports(_ready(),projection(books))
    assert before==(books.snapshot(),dict(journal.research.values),dict(lifecycle.store.values))
    assert lifecycle.owner_count==1


@pytest.mark.parametrize('truth',['PAPER_POSITION','PAPER_OBSERVATION'])
def test_cross_same_identity_across_truth_projections(tmp_path,truth):
    books,journal,futures,lifecycle,current=fixture(tmp_path,truth=truth)
    journal.consume_source('TRACK',current.identity)
    b=books.snapshot()[0].data;j=journal.snapshot().records[0].data;r=json.loads(projection(books).records[0].intraday_facts)
    for key in ('opportunity_id','opportunity_identity','track_identity','truth_class','decision_identity'):
        assert b[key]==j[key]==r[key]
    assert r['model_lots']==1 and r['truth_class']==truth
