"""Sponsor asymmetric authority: real application gate, isolated source fixtures."""
from dataclasses import asdict, replace
from datetime import timedelta
import json
import pytest
from kronos.intraday.chart_input import ChartInputObservation, ObservedChartPanel, CORE_CONTENT
from kronos.intraday.contracts import IntradayTimeframe, CandleCompletion
from kronos.intraday.validation import ValidationState, FactObservability
from kronos.intraday.mcx_history import create_retained_mcx_candles
from kronos.intraday.review import ReviewError
from kronos.intraday.review_mcx_paired import MCX_REFERENCE_RELATIONSHIPS, artifact_bytes
from kronos.intraday.review_mcx_paired_answer import answer_artifact_from_bytes
from kronos.intraday.review_mcx_paired_persistence import IntradayMcxPairedReviewStore
from kronos.instrument.visual_identity import VisualIdentityResolver, create_visual_identity_publication
from kronos.provider.contracts.market_data import HistoricalCandle
from .test_review_v2_paired_generic import synthetic_commissioning
from .test_review_v2_paired_intake import paired_fixture, complete_paired
from .test_review_mcx_paired import _resolver
from .test_review import _png
from .test_probables_v2 import _schedule, PREVIOUS_DAY
from .chart_input_fixtures import configure_fixture_calendar


def fixture(tmp_path, family="GOLDM", *, retain_observation=True):
    app, cycle, metadata = paired_fixture(tmp_path, family=family)
    configure_fixture_calendar(app)
    chart = app.upload_chart(cycle.cycle_identity, media_type="image/png", payload=_png(88), paired_metadata=metadata)
    bundle, _, _ = app._paired.restore(cycle, chart)
    binding = app._paired.bindings.load(binding_identity=metadata["native_binding_identity"])
    schedule = _schedule(PREVIOUS_DAY, "MCX")
    rows = create_retained_mcx_candles(active_binding=binding, timeframe=IntradayTimeframe.ONE_HOUR,
        schedule=schedule, candles=tuple(HistoricalCandle(schedule.windows[0].opens_at+timedelta(hours=i),
            100.0+i, 102.0+i, 99.0+i, 101.0+i, 100+i) for i in range(6)),
        observation_boundary=cycle.analysis_boundary, source_operation_identity="WO07B-MCX-ISOLATED")
    app._chart_input.native_history.retain_many(rows)
    ref = bundle.reference_relationship
    first = app._paired.native_resolver.publication
    second = _resolver(ref.reference_analytical_subject_identity, ref.governed_visible_identity, cycle.analysis_boundary).publication
    app._paired.native_resolver = VisualIdentityResolver(create_visual_identity_publication(
        canonical_subject_identities=tuple(sorted({r.canonical_subject_identity for r in first.relationships+second.relationships})),
        publication_identity=first.publication_identity, publication_version=first.publication_version,
        effective_from=first.effective_from, effective_through=first.effective_through,
        source_identities=first.source_identities, provenance=first.provenance,
        relationships=first.relationships+second.relationships, supersedes=None, schema_identity=first.schema_identity))
    expectations = app._chart_input.expectations(cycle, chart, bundle)
    panels=[]
    for e in expectations:
        source=e.source; sched=e.schedule
        native=e.role=="NATIVE"
        start=(source.derived_start if e.timeframe=="4H" else source.candle_start) if native else None
        end=(source.derived_end if e.timeframe=="4H" else source.candle_end) if native else None
        panels.append(ObservedChartPanel(e.role,e.timeframe,"TEST-EXACT-NATIVE-SERIES" if native else ref.governed_visible_identity,
            e.venue,None if native else "TEST-LISTED-"+family,e.currency,None,
            sched.trading_date if native else None,sched.session_type if native else None,sched.timezone if native else None,
            start,end,CandleCompletion.COMPLETE if native else None,chart.received_at,end,True,False,
            tuple((key,FactObservability.EXACT) for key in CORE_CONTENT)))
    receipt=ChartInputObservation(chart.chart_revision_identity,chart.payload_sha256,cycle.cycle_identity,
        cycle.probables_run_identity,cycle.probable_result_identity,"ISOLATED-INDEPENDENT-OBSERVATION",chart.received_at,tuple(panels))
    if retain_observation:
        app.review_store.retain_chart_input(receipt)
    result=app.create_individual_question_transport(cycle.cycle_identity)
    complete_paired(app,result,reference="TEST-LISTED-"+family)
    return app,cycle,chart,bundle,receipt,result,rows


@pytest.mark.parametrize("relationship",MCX_REFERENCE_RELATIONSHIPS,ids=lambda r:r.canonical_mcx_subject_identity)
def test_five_family_fresh_import_restoration_and_replay(tmp_path,synthetic_commissioning,relationship):
    family=relationship.canonical_mcx_subject_identity.removeprefix("MCX-SUBJECT-")
    app,cycle,chart,bundle,receipt,result,rows=fixture(tmp_path,family)
    comparison=app._chart_input.evaluate(cycle,chart,bundle=bundle,resolver=app._paired.native_resolver)
    assert len(comparison)==8
    for p in comparison:
        if p.role=="REFERENCE":
            assert p.overall is ValidationState.UNVERIFIABLE
            assert p.temporal is ValidationState.UNVERIFIABLE
            assert p.independent_correspondence=="NOT_INDEPENDENTLY_ESTABLISHED"
            assert p.authority=="SUPPORTING_VISUAL_CONTEXT_ONLY" and p.source_identity is None
        else:
            assert p.overall is ValidationState.VALIDATED and p.source_identity
    outcome=app.import_expected_answer(cycle.cycle_identity)
    assert (outcome.imported_count,outcome.rejected_count)==(1,0), outcome
    pack=app._paired.retained(cycle,chart)[3]
    evidence=app._paired.store.load_evidence_for_pack(pack.review_pack_identity)
    assert evidence.reference_independent_correspondence=="NOT_INDEPENDENTLY_ESTABLISHED"
    assert evidence.reference_role=="SUPPORTING_VISUAL_CONTEXT_ONLY"
    assert evidence.reference_resolution is None
    assert evidence.reference_constituent_relationship=="NOT_ESTABLISHED"
    assert len(evidence.chart_correspondence)==8
    encoded=artifact_bytes(evidence)
    assert answer_artifact_from_bytes(encoded)==evidence
    assert IntradayMcxPairedReviewStore(app._paired.store.root).load_evidence_for_pack(pack.review_pack_identity)==evidence
    before={p:p.read_bytes() for p in app._paired.store.root.rglob('*') if p.is_file()}
    assert app.import_expected_answer(cycle.cycle_identity).already_imported_count==1
    assert all(p.read_bytes()==v for p,v in before.items())
    from kronos.application.intraday_review_v2 import IntradayReviewV2Application
    restored=IntradayReviewV2Application(probables_store=app.probables_store,
        review_store=app.review_store,transport=app._transport,clock=app._clock)
    restored._paired.native_resolver=app._paired.native_resolver
    configure_fixture_calendar(restored)
    assert restored._chart_input.expectations(cycle,chart,bundle)==app._chart_input.expectations(cycle,chart,bundle)
    assert restored.import_expected_answer(cycle.cycle_identity).already_imported_count==1
    assert restored.current_reconciliation().requests==()
    assert evidence.authority=='INDEPENDENT_VISUAL_OBSERVATION_ONLY'
    four=next(x.source for x in app._chart_input.expectations(cycle,chart,bundle) if x.role=='NATIVE' and x.timeframe=='4H')
    assert (four.open,four.high,four.low,four.close,four.volume)==(100.0,105.0,99.0,104.0,406)
    assert four.actual_duration==timedelta(hours=4)
    assert rows[0].candle_identity in four.provenance
    assert bundle.native_identity_binding.actual_derivative_contract_identity in four.provenance


@pytest.mark.parametrize("mutation",["missing","duplicate","future","tampered","wrong_record","wrong_session"])
def test_native_four_hour_source_never_bypassed(tmp_path,synthetic_commissioning,mutation):
    app,cycle,chart,bundle,receipt,result,rows=fixture(tmp_path)
    store=app._chart_input.native_history
    path=store.path_for(rows[0])
    if mutation=='missing':path.unlink()
    elif mutation=='duplicate':path.with_name('duplicate.json').write_bytes(path.read_bytes())
    else:
        doc=json.loads(path.read_bytes()); doc=doc.get('artifact',doc)
        if mutation=='future': doc['observation_boundary']=(cycle.analysis_boundary+timedelta(days=1)).isoformat()
        elif mutation=='wrong_record':doc['provider_record_identity']='PROVIDER-INSTRUMENT-RECORD-FOREIGN'
        elif mutation=='wrong_session':doc['domain008_session_identity']='WRONG_SESSION'
        else:doc['close']='999'
        path.write_text(json.dumps(doc))
    outcome=app.import_expected_answer(cycle.cycle_identity)
    assert outcome.imported_count==0 and outcome.rejected_count==1


@pytest.mark.parametrize("index",range(8))
@pytest.mark.parametrize("change",["identity","venue","future","forming","cropped"])
def test_each_panel_known_contradiction_rejects(tmp_path,synthetic_commissioning,index,change):
    app,cycle,chart,bundle,receipt,result,rows=fixture(tmp_path)
    panel=receipt.panels[index]
    changes={'identity':dict(observed_subject='WRONG_COMMODITY'), 'venue':dict(venue='FOREIGN'),
        'future':dict(latest_visible_end=cycle.analysis_boundary+timedelta(minutes=1)),
        'forming':dict(completion=CandleCompletion.INCOMPLETE), 'cropped':dict(entire_panel_observed=False)}
    altered=replace(receipt,panels=tuple(replace(p,**changes[change]) if i==index else p for i,p in enumerate(receipt.panels)))
    # Replace fixture receipt before import, not any production evidence.
    location=app.review_store.root/'chart-input-observations'/(chart.chart_revision_identity+'.json')
    location.unlink();app.review_store.retain_chart_input(altered)
    outcome=app.import_expected_answer(cycle.cycle_identity)
    assert outcome.imported_count==0 and outcome.rejected_count==1


def test_reference_machine_authority_cannot_be_forged_on_restore(tmp_path,synthetic_commissioning):
    app,cycle,chart,bundle,receipt,result,rows=fixture(tmp_path)
    assert app.import_expected_answer(cycle.cycle_identity).imported_count==1
    pack=app._paired.retained(cycle,chart)[3]
    e=app._paired.store.load_evidence_for_pack(pack.review_pack_identity)
    d=json.loads(artifact_bytes(e));d['chart_correspondence'][0][3]='VALIDATED'
    with pytest.raises(ReviewError):answer_artifact_from_bytes(json.dumps(d).encode())


def test_reference_never_receives_independent_source(tmp_path,synthetic_commissioning):
    from kronos.intraday.chart_input import compare_chart_panel
    app,cycle,chart,bundle,receipt,*_=fixture(tmp_path)
    expected=app._chart_input.expectations(cycle,chart,bundle)
    with pytest.raises(ValueError,match='SUPPORTING_REFERENCE_SOURCE_FORBIDDEN'):
        compare_chart_panel(replace(expected[0],source=expected[4].source),receipt.panels[0],
            resolver=app._paired.native_resolver,received_at=chart.received_at,observed_at=receipt.observed_at)


def rewritten(row, **changes):
    """Legitimate isolated artifact with recalculated contract integrity."""
    from kronos.intraday.mcx_history import RetainedMcxContractCandle, _identity
    values=asdict(row);values.pop('candle_identity');values.pop('integrity_identity')
    values.update(changes)
    return RetainedMcxContractCandle(**values,
        candle_identity=_identity('INTRADAY-MCX-CONTRACT-CANDLE-',values),
        integrity_identity=_identity('INTEGRITY-INTRADAY-MCX-CONTRACT-CANDLE-',values))


@pytest.mark.parametrize('change',['future','provider_record','contract','subject','session','calendar','source','offset'])
def test_valid_integrity_does_not_override_contract_session_or_boundary(tmp_path,synthetic_commissioning,change):
    from kronos.intraday.mcx_history import retained_mcx_candle_bytes
    app,cycle,chart,bundle,receipt,result,rows=fixture(tmp_path)
    r=rows[0]
    edits={'future':dict(observation_boundary=cycle.analysis_boundary+timedelta(seconds=1)),
        'provider_record':dict(provider_record_identity='PROVIDER-INSTRUMENT-RECORD-FOREIGN'),
        'contract':dict(canonical_contract_identity='MCX-FUT-GOLDM-2099-12-31'),
        'subject':dict(canonical_subject_identity='MCX-SUBJECT-COPPER'),
        'session':dict(domain008_session_identity='MCX:FOREIGN'),
        'calendar':dict(calendar_version='FOREIGN'),
        'source':dict(provider_source_identity='FOREIGN_PROVIDER'),
        'offset':dict(source_timestamp=r.source_timestamp+timedelta(minutes=1))}
    changed=rewritten(r,**edits[change]);changed.__post_init__()
    app._chart_input.native_history.path_for(r).write_bytes(retained_mcx_candle_bytes(changed))
    outcome=app.import_expected_answer(cycle.cycle_identity)
    assert outcome.imported_count==0 and outcome.rejected_count==1


def test_four_hour_order_and_remainder_and_repetition_are_truthful(tmp_path,synthetic_commissioning):
    from kronos.application.intraday_mcx_chart_source import native_four_hour
    from types import SimpleNamespace
    app,cycle,chart,bundle,receipt,result,rows=fixture(tmp_path)
    binding=app._paired.bindings.load(binding_identity=bundle.native_identity_binding.active_binding_identity)
    selection=app._paired._selection(cycle)
    def aggregate(values):
        return native_four_hour(cycle=cycle,binding=binding,selection=selection,
            history=SimpleNamespace(load_contract=lambda **kw:values),calendar=app._chart_input.calendar)
    ordered=aggregate(rows)
    assert aggregate(tuple(reversed(rows)))==ordered
    assert ordered[0].derived_end==rows[3].candle_end # shorter session remainder is not a 4H bar
    assert aggregate(rows[1:])[0] is None
    assert aggregate(())[0] is None


@pytest.mark.parametrize('proof',[(), ('bad',), ((None,),), (None,)])
def test_malformed_persisted_correspondence_fails_closed(tmp_path,synthetic_commissioning,proof):
    app,cycle,chart,bundle,receipt,result,rows=fixture(tmp_path)
    assert app.import_expected_answer(cycle.cycle_identity).imported_count==1
    pack=app._paired.retained(cycle,chart)[3]
    evidence=app._paired.store.load_evidence_for_pack(pack.review_pack_identity)
    with pytest.raises(ReviewError):replace(evidence,chart_correspondence=proof)


def test_reference_time_claims_do_not_upgrade_machine_authority(tmp_path,synthetic_commissioning):
    from kronos.intraday.chart_input import compare_chart_panel
    app,cycle,chart,bundle,receipt,*_=fixture(tmp_path)
    e=app._chart_input.expectations(cycle,chart,bundle)[0]
    observed=replace(receipt.panels[0],completion=CandleCompletion.COMPLETE,
        latest_visible_end=cycle.analysis_boundary,candle_end=cycle.analysis_boundary)
    r=compare_chart_panel(e,observed,resolver=app._paired.native_resolver,
        received_at=chart.received_at,observed_at=receipt.observed_at)
    assert r.overall is ValidationState.UNVERIFIABLE
    assert r.temporal is ValidationState.UNVERIFIABLE
    assert r.independent_correspondence=='NOT_INDEPENDENTLY_ESTABLISHED'
    assert r.source_identity is None


@pytest.mark.parametrize('change',['future_start','future_end','reverse','capture_before_end','capture_after_receipt'])
def test_reference_known_time_contradiction_rejects_without_machine_source(tmp_path,synthetic_commissioning,change):
    from kronos.intraday.chart_input import compare_chart_panel
    app,cycle,chart,bundle,receipt,*_=fixture(tmp_path)
    e=app._chart_input.expectations(cycle,chart,bundle)[0];boundary=cycle.analysis_boundary
    edits={'future_start':dict(candle_start=boundary+timedelta(seconds=1)),
        'future_end':dict(candle_end=boundary+timedelta(seconds=1)),
        'reverse':dict(candle_start=boundary,candle_end=boundary-timedelta(minutes=5)),
        'capture_before_end':dict(candle_end=boundary,captured_at=boundary-timedelta(seconds=1)),
        'capture_after_receipt':dict(captured_at=chart.received_at+timedelta(seconds=1))}
    r=compare_chart_panel(e,replace(receipt.panels[0],**edits[change]),resolver=app._paired.native_resolver,
        received_at=chart.received_at,observed_at=receipt.observed_at)
    assert r.overall is ValidationState.NOT_VALIDATED
    assert r.independent_correspondence=='NOT_INDEPENDENTLY_ESTABLISHED' and r.source_identity is None


def test_missing_context_calendar_cannot_fall_back_to_older_source(tmp_path,synthetic_commissioning):
    from types import SimpleNamespace
    app,cycle,chart,bundle,receipt,*_=fixture(tmp_path)
    app._chart_input.calendar=SimpleNamespace(instrument_session_profile=lambda *a,**kw:None)
    assert app.import_expected_answer(cycle.cycle_identity).imported_count==0
