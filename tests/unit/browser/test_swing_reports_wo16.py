"""Independent historical Reports populations; all fixtures have no authority."""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
import csv
import io
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from kronos.application.swing_reports import read_swing_reports_sources
from kronos.browser.reports import (
    ReportsQuery, ReportView, ReportFamily, ReportsEvidenceUnavailable,
    export_reports_csv, export_reports_json, export_reports_xlsx, project_historical_reports,
)
from kronos.browser.views import render_reports
from kronos.swing.v1.observation_research_ledger_v2 import (
    ObservationResearchLedgerV2Service, LocalObservationResearchLedgerV2Store,
    WebSocketPresentationState,
)
from kronos.swing.v1.paper_observation_track import LocalPaperObservationTrackStore
from kronos.swing.v1.native_sponsor_decision import SponsorTradeChoice
from kronos.swing.v1.sponsor_observation_decision import SponsorActivationDisposition
from kronos.swing.v1.mcx_contract_profile import McxFamily
from tests.unit.swing.v1.test_observation_research_ledger import _service
from tests.unit.swing.v1.test_sponsor_observation_decision import _green, _record, NOW
from tests.unit.browser.test_browser_reports import (
    _empty_journal, _reports_inventory, _reports_get, _xlsx_rows,
    compatibility_reports_server,
)
from tests.unit.application.test_swing_opportunities import _ready
from tests.unit.browser.test_wo14_mcx_journal_integration import fixture, START

ROUTES = ('/reports', '/reports/export.csv', '/reports/export.json', '/reports/export.xlsx')


def history(root, choices=(SponsorTradeChoice.PAPER,), *, counterparts=True):
    sources = []
    constructor_service = None
    for choice in choices:
        completed, observation = _green(root/choice.value)
        disposition = (SponsorActivationDisposition.NOT_APPLICABLE_IGNORE if choice is SponsorTradeChoice.IGNORE
                       else SponsorActivationDisposition.BLOCKED_RISK_UNAVAILABLE)
        source = _record(completed, observation, choice, disposition)
        service = _service(root/choice.value, source)
        constructor_service = service
        sources.extend(service.snapshot())
    v1 = SimpleNamespace(snapshot=lambda: tuple(sources), store=SimpleNamespace(load_links=lambda: ()))
    if constructor_service is None:
        # Empty real service uses the same owning store types.
        from kronos.swing.v1.observation_research_ledger import (
            ObservationResearchLedgerService, LocalObservationResearchLedgerStore)
        from kronos.swing.v1.sponsor_observation_decision import LocalSponsorObservationDecisionStore
        constructor_service = ObservationResearchLedgerService(
            LocalObservationResearchLedgerStore(root/'v1'), LocalSponsorObservationDecisionStore(root/'decisions'))
    v2 = ObservationResearchLedgerV2Service(
        LocalObservationResearchLedgerV2Store(root/'v2'),constructor_service,
        LocalPaperObservationTrackStore(root/'paper'))
    # Aggregate already-validated immutable source projections to reproduce
    # the retained 3:2 shape. Each primary was constructed by its real owner.
    v2.v1 = v1
    if counterparts:
        for source in sources[:2]:
            v2.retain_observation(source)
    window = SimpleNamespace(observation_research_snapshot=v1.snapshot,
                             _observation_research=v1, _observation_research_v2=v2,
                             reports_position_facts=lambda: (WebSocketPresentationState.IDLE, {}),
                             reports_generation=lambda:0)
    native = SimpleNamespace(reports_journal_snapshot=lambda: _empty_journal(root/'step33'))
    return window, native, sources


def project(window, native, control=None, query=None):
    evidence = read_swing_reports_sources(window,native,control,NOW.date())
    return project_historical_reports((),evidence.journal,query or ReportsQuery(),
                                     governed_current_trading_date=NOW.date(),evidence=evidence)


def test_retained_three_v1_two_v2_shape_reports_without_operational_backfill(tmp_path):
    window,native,sources=history(tmp_path,tuple(SponsorTradeChoice))
    before=_reports_inventory(tmp_path)
    with pytest.raises(ValueError,match='SOURCE_INCOMPLETE'):
        window._observation_research_v2.operational_handoffs(governed_current_trading_date=NOW.date())
    projection=project(window,native)
    assert len(projection.records)==3
    assert {dict(row.source_facts)['choice'] for row in projection.records}=={'PAPER','LIVE','IGNORE'}
    assert sum(row.relationship_state=='VALID_V1_ONLY_V2_ABSENT' for row in projection.records)==1
    assert projection.overview.paper_positions==projection.overview.live_positions==0
    assert projection.overview.completed_records==0
    for view in (ReportView.PAPER,ReportView.LIVE,ReportView.PAPER_OBSERVATIONS):
        assert project(window,native,query=ReportsQuery(view=view)).records==()
    assert _reports_inventory(tmp_path)==before
    assert project(window,native)==projection


@pytest.mark.parametrize('route',ROUTES)
def test_four_get_formats_and_failure_paths_preserve_contents_and_metadata(
    tmp_path,compatibility_reports_server,monkeypatch,route):
    server=compatibility_reports_server
    window,native,sources=history(tmp_path/'sources',tuple(SponsorTradeChoice))
    monkeypatch.setattr(server,'trade_window',window)
    def forbid(*a,**k):raise AssertionError('GET crossed admitted owner')
    monkeypatch.setattr(window._observation_research_v2,'synchronize',forbid)
    before=_reports_inventory(tmp_path)
    status,body=_reports_get(server,route+'?product=SWING&view=ALL_RECORDS')
    assert status==200
    assert _reports_inventory(tmp_path)==before
    if route.endswith('.json'):
        payload=json.loads(body)
        assert len(payload['records'])==4  # Three decisions plus independent Step-33 trade.
        assert payload['coverage']['missing_relationships']==1
    server._swing_v2_reconciliation_failure='SOURCE_UNAVAILABLE'
    assert _reports_get(server,route+'?product=SWING')[0]==503
    assert _reports_inventory(tmp_path)==before


@pytest.mark.parametrize('market',['NSE',*list(McxFamily)])
@pytest.mark.parametrize('view',[ReportView.ALL_RECORDS,ReportView.PAPER,ReportView.LIVE])
def test_population_identity_and_coverage_are_identical_in_all_formats(tmp_path,market,view):
    window,native,_=history(tmp_path/'history')
    control=None
    if market!='NSE':
        control,position,instrument,plan=fixture(tmp_path/'mcx',market,active=True,live=view is ReportView.LIVE)
        if view is ReportView.LIVE:
            seed_live_attestation(control,position,plan,tmp_path/'live')
    else:
        from tests.unit.swing.v1.test_native_trade_journal import _run_paper
        journal,*_=_run_paper(tmp_path/'nse')
        native=SimpleNamespace(reports_journal_snapshot=lambda:journal)
    before=_reports_inventory(tmp_path)
    projection=project(window,native,control,ReportsQuery(view=view))
    expected={row.record_identity for row in projection.records}
    payload=json.loads(export_reports_json(projection))
    assert {row['record_identity'] for row in payload['records']}==expected
    csv_rows=list(csv.DictReader(io.StringIO(export_reports_csv(projection).decode())))
    assert {row['record_identity'] for row in csv_rows if row['row_type']=='RECORD'}==expected
    workbook=export_reports_xlsx(projection,generated_at=NOW)
    sheet=_xlsx_rows(workbook);ids={row[sheet[0].index('Record Identity')] for row in sheet[1:]}
    assert ids==expected
    for row in projection.page_records:
        assert row.instrument in render_reports(_ready(),projection,selected_record_id=row.record_identity)
    if market!='NSE' and projection.records:
        contract_rows=[row for row in projection.records if row.market=='MCX']
        for row in contract_rows:
            assert row.contract_family==market.value
            facts=dict(row.source_facts)
            assert facts['selected_contract']==plan.contract_symbol and facts['expiry']==plan.expiry
            assert row.pnl is None and facts['monetary_multiplier']=='UNKNOWN'
            assert facts['lots']==str(position.lots)
            assert row.entry==(Decimal('103.25') if view is ReportView.LIVE else Decimal('101'))
    assert projection.overview.net_pnl is None
    assert _reports_inventory(tmp_path)==before


@pytest.mark.parametrize('family',list(McxFamily))
def test_mcx_plan_only_waiting_active_and_closed_are_distinct(tmp_path,family):
    window,native,_=history(tmp_path/'history',choices=())
    control,position,instrument,plan=fixture(tmp_path/'mcx',family)
    waiting=project(window,native,control).records[0]
    assert waiting.status=='PAPER_ARMED' and waiting.entry is None and not waiting.completed
    assert dict(waiting.source_facts)['selected_contract']==plan.contract_symbol
    # A separately retained plan has no fictional position/fill.
    from kronos.swing.v1.native_active_trade_lifecycle import ActiveTradeLifecycleService, LocalActiveTradeLifecycleStore
    control.lifecycle=ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(tmp_path/'empty-lifecycle'))
    plan_only=project(window,native,control).records[0]
    assert plan_only.status=='ADVISORY_PLAN_ONLY' and plan_only.family is ReportFamily.NONE
    assert plan_only.entry is plan_only.exit is plan_only.pnl is None
    assert not plan_only.completed


@pytest.mark.parametrize('family',list(McxFamily))
def test_exact_contract_changed_or_missing_plan_withholds_authority_without_repair(tmp_path,family):
    window,native,_=history(tmp_path/'history')
    control,position,instrument,plan=fixture(tmp_path/'mcx',family,active=True)
    path=next(control.plans.root.glob('*/*/*.json'))
    data=json.loads(path.read_bytes());data['record']['receipt_integrity_sha256']='f'*64
    path.write_text(json.dumps(data))
    before=_reports_inventory(tmp_path)
    with pytest.raises(ValueError):project(window,native,control)
    assert _reports_inventory(tmp_path)==before


@pytest.mark.parametrize('route',ROUTES)
def test_unsupported_swing_filters_and_duplicates_are_rejected_write_free(
    tmp_path,compatibility_reports_server,route):
    before=_reports_inventory(tmp_path)
    for suffix in ('?exit_reason=STOP_LOSS','?completeness=COMPLETE','?product=SWING&product=SWING','?invented=true'):
        assert _reports_get(compatibility_reports_server,route+suffix)[0]==400
    assert _reports_inventory(tmp_path)==before


def test_changed_source_during_extraction_withholds_mixed_response(compatibility_reports_server,monkeypatch):
    import kronos.application.swing_reports as reader
    original=reader.read_swing_reports_sources
    calls=[]
    def changing(*args):
        value=original(*args);calls.append(value)
        return value if len(calls)==1 else replace(value,v1=(object(),))
    monkeypatch.setattr(reader,'read_swing_reports_sources',changing)
    assert _reports_get(compatibility_reports_server,'/reports')[0]==503
    assert len(calls)==2


def test_v2_changed_relationship_digest_is_not_an_optional_absence(tmp_path):
    from tests.unit.swing.v1.test_observation_research_ledger_v2 import _selected_history_service
    service,paper,track=_selected_history_service(tmp_path)
    window=SimpleNamespace(observation_research_snapshot=service.v1.snapshot,
                           _observation_research=service.v1,_observation_research_v2=service,
                           reports_position_facts=lambda:(WebSocketPresentationState.IDLE,{}), reports_generation=lambda:0)
    native=SimpleNamespace(reports_journal_snapshot=lambda:_empty_journal(tmp_path/'journal'))
    first=project(window,native)
    assert first.records[0].family is ReportFamily.PAPER_OBSERVATION
    assert first.records[0].entry is first.records[0].exit is first.records[0].pnl is None
    assert dict(first.records[0].source_facts)['observation_entry_reference'] != 'UNAVAILABLE'
    path=next((service.store.root/'links').glob('*.json'))
    data=json.loads(path.read_text());data['link']['source_integrity_sha256']='f'*64
    path.write_text(json.dumps(data))
    before=_reports_inventory(tmp_path)
    with pytest.raises(ValueError):project(window,native)
    assert _reports_inventory(tmp_path)==before


def test_ignored_step33_record_is_decision_history_without_trade_facts(tmp_path):
    from tests.unit.swing.v1.test_native_sponsor_decision import _go
    from tests.unit.swing.v1.test_native_trade_construction import _ready as readiness
    from tests.unit.swing.v1.test_native_trade_journal import _empty_lifecycle
    from kronos.swing.v1.native_trade_journal import TradeJournalService,LocalTradeJournalStore
    result,plan,*_=_go(SponsorTradeChoice.IGNORE)
    ready,_=readiness()
    journal=TradeJournalService(LocalTradeJournalStore(tmp_path/'journal'))
    snapshot=journal.reconcile((plan,),(ready,),(result,),_empty_lifecycle())
    window,native,_=history(tmp_path/'history',choices=())
    native.reports_journal_snapshot=lambda:snapshot
    projection=project(window,native)
    row=projection.records[0]
    assert row.population_kind=='STEP33_IGNORED_OPPORTUNITY'
    assert not row.completed and row.entry is row.exit is row.pnl is None
    assert projection.overview.completed_records==projection.overview.paper_positions==0


def seed_live_attestation(control,position,plan,root):
    from hashlib import sha256
    from kronos.swing.v1.mcx_live_attestation import LocalMcxLiveFillAttestationStore, McxLiveFillAttestation
    from kronos.swing.v1.mcx_broker_fill_evidence import LocalMcxBrokerFillEvidenceStore, McxBrokerFillCapture
    original=b'ISOLATED SPONSOR FILL RECORD - NO BROKER AUTHORITY'
    fill=McxLiveFillAttestation.create(
        plan,contract_symbol=plan.contract_symbol,expiry=plan.expiry,lots=position.lots,
        provider_order_quantity=None,entry_outcome=None,
        fill_price=position.actual_entry,fill_at=position.entry_timestamp,
        broker_evidence_id='ISOLATED-FILL',broker_evidence_sha256=sha256(original).hexdigest(),
        attested_at=position.entry_timestamp,v1_manual=True)
    control.live_attestations=LocalMcxLiveFillAttestationStore(root/'attestations')
    control.live_attestations.retain(fill)
    control.broker_evidence=LocalMcxBrokerFillEvidenceStore(root/'bytes')
    capture=McxBrokerFillCapture.from_attestation(position.position_id,fill,original)
    control.broker_evidence.capture(capture,original)


@pytest.mark.parametrize('family',list(McxFamily))
@pytest.mark.parametrize('route',ROUTES)
def test_exact_contract_mcx_gets_and_invalid_evidence_are_write_free(
    tmp_path,compatibility_reports_server,monkeypatch,family,route):
    server=compatibility_reports_server
    control,position,instrument,plan=fixture(tmp_path/'mcx',family,active=True)
    monkeypatch.setattr(server,'mcx_v1_control',control)
    # The legacy server builder and MCX builder reuse a synthetic position ID.
    # Canonical MCX uses its own actual NativeReview owner, not that foreign
    # cached NSE Step-33 record. Contradictory IDs are tested separately.
    monkeypatch.setattr(server,'native_review',control.native_review)
    project(server.trade_window, server.native_review, control)
    before=_reports_inventory(tmp_path)
    status,body=_reports_get(server,route+'?product=SWING')
    assert status==200
    assert _reports_inventory(tmp_path)==before
    path=next(control.plans.root.glob('*/*/*.json'))
    data=json.loads(path.read_text());data['record']['expiry']='2099-01-01'
    path.write_text(json.dumps(data))
    before=_reports_inventory(tmp_path)
    status,body=_reports_get(server,route+'?product=SWING')
    assert status==503
    assert _reports_inventory(tmp_path)==before


@pytest.mark.parametrize('family',list(McxFamily))
def test_missing_or_altered_manual_live_attestation_is_explicit(tmp_path,family):
    window,native,_=history(tmp_path/'history',choices=())
    control,position,instrument,plan=fixture(tmp_path/'mcx',family,live=True)
    seed_live_attestation(control,position,plan,tmp_path/'live')
    row=project(window,native,control).records[0]
    assert 'SPONSOR_DIRECTED_OUTSIDE_MODEL' in dict(row.source_facts)['live_attestations']
    path=control.live_attestations._path(plan.trade_plan_id)
    data=json.loads(path.read_text());data['fill_price']='999'
    path.write_text(json.dumps(data))
    before=_reports_inventory(tmp_path)
    with pytest.raises(ValueError):project(window,native,control)
    assert _reports_inventory(tmp_path)==before


def test_retained_step33_corruption_is_not_concealed_by_readable_cache(
    tmp_path,compatibility_reports_server):
    server=compatibility_reports_server
    assert server.native_review.journal_current_snapshot().records
    path=next(server.native_review._trade_journal.store.root.glob('*.json'))
    data=json.loads(path.read_text());data['record']['trade_plan_sha256']='f'*64
    path.write_text(json.dumps(data))
    before=_reports_inventory(tmp_path)
    for route in ROUTES:
        assert _reports_get(server,route)[0]==503
    assert _reports_inventory(tmp_path)==before


def test_valid_literal_mcx_history_is_disclosed_without_a_family_assignment(tmp_path):
    from dataclasses import asdict
    from kronos.swing.v1.sponsor_observation_decision import _values_digest
    completed,observation=_green(tmp_path/'original')
    original=_record(completed,observation,SponsorTradeChoice.IGNORE,
                     SponsorActivationDisposition.NOT_APPLICABLE_IGNORE)
    def seal(record,**changes):
        fields=asdict(record)|changes|{'integrity_sha256':''}
        return type(record)(**(fields|{'integrity_sha256':_values_digest(fields)}))
    snapshot=seal(original.snapshot,canonical_instrument='MCX')
    decision=seal(original.decision,canonical_instrument='MCX',snapshot_sha256=snapshot.integrity_sha256)
    result=type(original)(snapshot,decision,original.activation)
    v1=_service(tmp_path/'generic',result)
    ledger=ObservationResearchLedgerV2Service(LocalObservationResearchLedgerV2Store(tmp_path/'v2'),
                                            v1,LocalPaperObservationTrackStore(tmp_path/'paper'))
    window=SimpleNamespace(observation_research_snapshot=v1.snapshot,_observation_research=v1,
                           _observation_research_v2=ledger,reports_generation=lambda:0,
                           reports_position_facts=lambda:(WebSocketPresentationState.IDLE,{}))
    native=SimpleNamespace(reports_journal_snapshot=lambda:_empty_journal(tmp_path/'journal'))
    before=_reports_inventory(tmp_path)
    projection=project(window,native)
    row=projection.records[0]
    assert row.instrument=='MCX' and row.market=='UNRESOLVED' and row.contract_family=='UNAVAILABLE'
    payload=json.loads(export_reports_json(projection))
    assert payload['coverage']['markets']=={'NSE':0,'MCX':0,'UNRESOLVED':1}
    assert set(payload['coverage']['families'].values())=={0}
    assert 'UNRESOLVED' in render_reports(_ready(),projection)
    assert _reports_inventory(tmp_path)==before


@pytest.mark.parametrize('family',list(McxFamily))
def test_mcx_factual_closure_and_restart_keep_old_contract_without_current_run(tmp_path,family):
    from tests.unit.swing.v1.test_mcx_contract_lifecycle import _wire_monitor
    from kronos.swing.v1.native_active_trade_lifecycle import ActiveTradeLifecycleService
    control,position,instrument,plan=fixture(tmp_path/'mcx',family,active=True)
    clock=[START]
    monitor,capability,hub=_wire_monitor(control.lifecycle,control.bound.bindings,instrument,clock)
    control.native_review._active_lifecycle_monitoring=monitor
    window,native,_=history(tmp_path/'history',choices=())
    try:
        monitor.attach(position.position_id,capability,instrument)
        clock[0]+=timedelta(minutes=1);capability.tick(103)
        tick, _ = monitor.latest_mcx_observation(position.position_id)
        schedule = monitor._calendar.schedule('MCX', START.date(), observed_at=clock[0])
        closure=control.bound.manual_paper_exit_at_cmp(position.position_id,tick,schedule)
        before=_reports_inventory(tmp_path)
        projection=project(window,native,control)
        row=projection.records[0]
        assert row.completed and row.status=='CLOSED'
        assert row.entry==Decimal('101') and row.exit==closure.actual_exit==Decimal('103')
        assert row.pnl is None
        assert dict(row.source_facts)['closure_sha256']==closure.integrity_hash
        assert dict(row.source_facts)['selected_contract']==instrument.trading_symbol
        retained=ActiveTradeLifecycleService(control.lifecycle.store)
        control.lifecycle=retained
        from kronos.swing.v1.mcx_contract_lifecycle import McxContractBoundLifecycle
        control.bound=McxContractBoundLifecycle(retained,control.bound.bindings)
        assert project(window,native,control)==projection
        assert _reports_inventory(tmp_path)==before
    finally:monitor.close()


def test_generation_change_rejects_even_when_a_snapshot_returns_to_previous_values(tmp_path):
    window,native,_=history(tmp_path)
    observed=iter((0,1))
    window.reports_generation=lambda:next(observed)
    before=_reports_inventory(tmp_path)
    with pytest.raises(ValueError,match='GENERATION_CHANGED'):
        project(window,native)
    assert _reports_inventory(tmp_path)==before


@pytest.mark.parametrize('text',['=SUM(1,2)','+CMD','@formula','-formula'])
def test_swing_csv_and_xlsx_text_is_formula_safe_without_changing_numeric_negative(tmp_path,text):
    from kronos.browser.reports import _project_records
    from tests.unit.browser.test_browser_reports import _record as operational_fixture
    from kronos.swing.v1.observation_research_ledger_v2 import ObservationMode
    initial=project_historical_reports((operational_fixture('CANBK',ObservationMode.PAPER),),
                                       _empty_journal(tmp_path),ReportsQuery(),
                                       governed_current_trading_date=NOW.date())
    row=replace(initial.records[0],instrument=text,pnl=Decimal('-125'))
    projection=_project_records((row,),ReportsQuery(),NOW.date(),())
    exported=list(csv.DictReader(io.StringIO(export_reports_csv(projection).decode())))[0]
    assert exported['instrument']=="'"+text and exported['pnl']=='-125'
    workbook=export_reports_xlsx(projection,generated_at=NOW)
    with ZipFile(io.BytesIO(workbook)) as archive:
        assert b'<f' not in archive.read('xl/worksheets/sheet1.xml')
    assert _xlsx_rows(workbook)[1][2]==text
    assert _xlsx_rows(workbook)[1][8]=='-125'



@pytest.mark.parametrize('route',ROUTES)
def test_conflicting_quick_and_explicit_dates_do_not_silently_override_filters(
    compatibility_reports_server,route):
    assert _reports_get(compatibility_reports_server,
                        route+'?quick=TODAY&from=2026-09-01')[0]==400


def test_all_exports_keep_full_population_while_html_pages_are_bounded(tmp_path):
    from kronos.browser.reports import _project_records
    window,native,_=history(tmp_path,tuple(SponsorTradeChoice))
    original=project(window,native)
    pages=[]
    for page in (1,2,3):
        current=_project_records(original.records,ReportsQuery(page=page,page_size=1),
                                 NOW.date(),original.coverage)
        assert current.page_count==3 and len(current.page_records)==1
        pages.extend(current.page_records)
        assert len(json.loads(export_reports_json(current))['records'])==3
        assert len(list(csv.DictReader(io.StringIO(export_reports_csv(current).decode()))))==3
        assert len(_xlsx_rows(export_reports_xlsx(current,generated_at=NOW)))==4
    assert tuple(pages)==original.records
    assert _project_records(original.records,ReportsQuery(page=4,page_size=1),
                            NOW.date(),original.coverage).page_records==()


@pytest.mark.parametrize('filter_values',[
    {'from_date':NOW.date(),'to_date':NOW.date()},
    {'from_date':NOW.date()+timedelta(days=1)},
    {'instrument':'can'}, {'status':'blocked'},
    {'view':ReportView.PAPER_OBSERVATIONS},
])
def test_filtered_populations_and_valid_empty_coverage_match_all_exports(tmp_path,filter_values):
    window,native,_=history(tmp_path,tuple(SponsorTradeChoice))
    projection=project(window,native,query=ReportsQuery(**filter_values))
    data=json.loads(export_reports_json(projection))
    ids={record.record_identity for record in projection.records}
    assert {row['record_identity'] for row in data['records']}==ids
    csv_rows=list(csv.DictReader(io.StringIO(export_reports_csv(projection).decode())))
    assert {row['record_identity'] for row in csv_rows if row['row_type']=='RECORD'}==ids
    workbook=export_reports_xlsx(projection,generated_at=NOW)
    sheet=_xlsx_rows(workbook)
    assert {row[sheet[0].index('Record Identity')] for row in sheet[1:]}==ids
    if not ids:
        assert data['coverage']['filtered_population']=='VALID_EMPTY'
        assert csv_rows[0]['row_type']=='COVERAGE'
        assert 'VALID_EMPTY' in render_reports(_ready(),projection)
    with ZipFile(io.BytesIO(workbook)) as archive:
        assert json.dumps(data['coverage'],sort_keys=True) in archive.read('xl/worksheets/sheet2.xml').decode().replace('&quot;','"')


def test_duplicate_step33_identity_rejects_instead_of_ticker_based_dedup(tmp_path):
    from tests.unit.swing.v1.test_native_trade_journal import _run_paper
    from kronos.swing.v1.native_trade_journal import _record
    from dataclasses import asdict
    window,native,_=history(tmp_path/'history',choices=())
    snapshot,*_=_run_paper(tmp_path/'journal')
    record=snapshot.records[0]
    values=asdict(record);values.pop('integrity_hash');values['journal_record_id']='ANOTHER-JOURNAL-RECORD'
    other=_record(values)
    native.reports_journal_snapshot=lambda:replace(snapshot,records=(record,other))
    with pytest.raises(ReportsEvidenceUnavailable,match='AMBIGUOUS_STEP33'):
        project(window,native)


def test_missing_governed_date_and_unreadable_source_are_unavailable_not_empty(
    compatibility_reports_server,monkeypatch):
    server=compatibility_reports_server
    monkeypatch.setattr(server.application,'current_swing_trading_date',lambda:None)
    for route in ROUTES:
        assert _reports_get(server,route)[0]==503


def test_ist_decision_date_does_not_invent_current_day_completion(tmp_path):
    window,native,_=history(tmp_path,tuple(SponsorTradeChoice))
    projection=project(window,native)
    for row in projection.records:
        assert row.record_date==row.relevant_timestamp.astimezone(
            __import__('zoneinfo').ZoneInfo('Asia/Kolkata')).date()
        assert not row.completed
        assert dict(row.source_facts)['timestamp_kind']=='DECISION'
    assert projection.overview.completed_records==0


def test_conflicting_nse_step33_and_mcx_position_identity_withholds_report(
    tmp_path,compatibility_reports_server,monkeypatch):
    control,*_=fixture(tmp_path/'mcx',McxFamily.COPPER,active=True)
    server=compatibility_reports_server
    monkeypatch.setattr(server,'mcx_v1_control',control)
    before=_reports_inventory(tmp_path)
    assert _reports_get(server,'/reports')[0]==503
    assert _reports_inventory(tmp_path)==before


def test_exact_step33_relationship_counts_once_and_changed_binding_rejects(tmp_path):
    from dataclasses import asdict
    from tests.unit.swing.v1.test_native_sponsor_decision import _go
    from tests.unit.swing.v1.test_native_trade_construction import _ready as readiness
    from tests.unit.swing.v1.test_native_trade_journal import _empty_lifecycle
    from kronos.swing.v1.native_trade_journal import _record, TradeJournalService, LocalTradeJournalStore
    window,native,sources=history(tmp_path/'history',choices=(SponsorTradeChoice.IGNORE,))
    decision,plan,*_=_go(SponsorTradeChoice.IGNORE)
    ready,_=readiness()
    journal=TradeJournalService(LocalTradeJournalStore(tmp_path/'journal')).reconcile(
        (plan,),(ready,),(decision,),_empty_lifecycle())
    source=sources[0]
    values=asdict(journal.records[0]);values.pop('integrity_hash')
    # Explicit isolated immutable counterpart. It remains an ignored decision,
    # with no position, fill or economics; joining never promotes a blocked entry.
    values.update(sponsor_decision_id=source.record.decision_identity,
                  native_run_identity=source.record.native_run_identity,
                  native_assessment_sha256=source.record.native_assessment_sha256,
                  instrument=source.record.canonical_instrument,
                  direction=source.source.snapshot.direction,
                  trade_plan_id=source.source.snapshot.conventional_trade_plan_identity or plan.trade_plan_id,
                  trade_plan_sha256=source.source.snapshot.conventional_trade_plan_sha256 or plan.integrity_hash)
    counterpart=_record(values)
    native.reports_journal_snapshot=lambda:replace(journal,records=(counterpart,))
    projection=project(window,native)
    assert len(projection.records)==1
    assert projection.records[0].record_identity==source.record.record_identity
    assert projection.overview.paper_positions==projection.overview.completed_records==0
    facts=dict(projection.records[0].source_facts)
    assert facts['step33']==counterpart.journal_record_id
    assert projection.records[0].entry is projection.records[0].exit is None
    values['native_assessment_sha256']='f'*64
    wrong=_record(values)
    native.reports_journal_snapshot=lambda:replace(journal,records=(wrong,))
    with pytest.raises(ReportsEvidenceUnavailable,match='STEP33_BINDING_INVALID'):
        project(window,native)


def test_v1_only_objective_history_is_not_erased_by_optional_sponsor_absence(tmp_path):
    from kronos.swing.v1.observation_research_ledger import ObservationLinkKind
    window,native,sources=history(tmp_path/'history',counterparts=False)
    source=sources[0]
    # Owning immutable link builder validates the original run and assessment.
    from kronos.swing.v1.observation_research_ledger import _values_digest, ObservationResearchLinkV1
    values=dict(link_identity='ISOLATED-OBJECTIVE-LINK',record_identity=source.record.record_identity,
                kind=ObservationLinkKind.OBJECTIVE_MODEL_OUTCOME,
                native_run_identity=source.record.native_run_identity,
                canonical_instrument=source.record.canonical_instrument,
                native_assessment_sha256=source.record.native_assessment_sha256,
                trade_plan_identity=source.source.snapshot.conventional_trade_plan_identity,
                trade_plan_sha256=source.source.snapshot.conventional_trade_plan_sha256,
                source_contract_identity='KRONOS-SWING-OBJECTIVE-MODEL-TRADE-V1',
                source_contract_version='1',source_record_identity='ISOLATED-MODEL-OUTCOME',
                source_integrity_sha256='a'*64,source_state='MODEL_TRADE_CLOSED',
                source_timestamp=NOW,sponsor_position_identity=None,integrity_sha256='')
    objective=ObservationResearchLinkV1(**(values|{'integrity_sha256':_values_digest(values)}))
    linked=replace(source,links=(objective,))
    window.observation_research_snapshot=lambda:(linked,)
    projection=project(window,native)
    row=projection.records[0]
    assert row.relationship_state=='VALID_V1_ONLY_V2_ABSENT'
    assert row.objective_outcome=='MODEL_TRADE_CLOSED'
    assert row.entry is row.exit is row.pnl is None
    assert not row.completed and projection.overview.paper_positions==0


def test_retained_nse_lifecycle_change_is_not_hidden_by_readable_cache(tmp_path):
    from tests.unit.swing.v1.test_native_trade_journal import _run_paper
    from kronos.application.swing_native_review import NativeReviewWorkflow
    from kronos.swing.v1.native_review import NativeReviewEvidenceStore
    snapshot,journal,lifecycle,*_=_run_paper(tmp_path/'nse')
    native=NativeReviewWorkflow(NativeReviewEvidenceStore(tmp_path/'native'),
                               trade_journal_service=journal,active_lifecycle_service=lifecycle)
    assert native.reports_journal_snapshot().records==snapshot.records
    path=next((tmp_path/'nse'/'lifecycle').glob('*/position.json'))
    value=json.loads(path.read_text());value['record']['actual_entry']='999'
    path.write_text(json.dumps(value))
    before=_reports_inventory(tmp_path)
    with pytest.raises(ValueError):native.reports_journal_snapshot()
    assert _reports_inventory(tmp_path)==before


@pytest.mark.parametrize('route',ROUTES)
def test_default_combined_report_withholds_missing_mcx_owner_not_partial_empty(
    tmp_path,compatibility_reports_server,monkeypatch,route):
    server=compatibility_reports_server
    monkeypatch.setattr(server,'mcx_v1_control',None)
    before=_reports_inventory(tmp_path)
    code,body=_reports_get(server,route)
    assert code==503 and b'not empty' in body
    assert _reports_inventory(tmp_path)==before


@pytest.mark.parametrize('market',['NSE',*list(McxFamily)])
def test_notification_dismissal_cannot_change_reports_population_or_factual_exports(tmp_path,market):
    """Presentation dismissal never deletes the exact retained historical fact."""
    from tests.unit.application.test_swing_ux10 import ux10
    from tests.unit.browser.test_browser_notification_centre import _centre, NOW as CENTRE_NOW
    from kronos.application.notifications import NotificationWorkspaceSnapshot
    window,native,_=history(tmp_path/'sources'/'history',choices=())
    control=None
    if market=='NSE':
        from tests.unit.swing.v1.test_native_trade_journal import _run_paper
        snapshot,_,lifecycle,*_=_run_paper(tmp_path/'sources'/'nse')
        native.reports_journal_snapshot=lambda:snapshot
        position,=lifecycle.snapshot().positions
    else:
        control,position,_,_=fixture(tmp_path/'sources'/'mcx',market,active=True)
    notifications=ux10(tmp_path/'notifications')
    centre=_centre(tmp_path/'centre',[CENTRE_NOW+timedelta(days=10)])
    event=notifications.observe_active_trade_monitoring_activation(position)
    card,=centre.synchronize(NotificationWorkspaceSnapshot(()),notifications.snapshot(),
                            current_run_identity=None,websocket_state='IDLE').records
    assert notifications.evidence(event.notification_id)['position_identity']==position.position_id
    before=project(window,native,control)
    assert len(before.records)==1
    row,=before.records
    assert dict(row.source_facts)['position']==position.position_id
    exports=lambda p:(export_reports_json(p),export_reports_csv(p),export_reports_xlsx(p,generated_at=NOW))
    before_exports=exports(before)
    source_bytes=_reports_inventory(tmp_path/'sources')
    centre.dismiss(card.notification_identity,card.integrity_sha256)
    assert centre.synchronize(NotificationWorkspaceSnapshot(()),notifications.snapshot(),
                              current_run_identity=None,websocket_state='IDLE').visible==()
    after=project(window,native,control)
    assert after==before and exports(after)==before_exports
    assert _reports_inventory(tmp_path/'sources')==source_bytes
