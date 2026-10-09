"""Retained historical fixture graphs, not prospective first-five authority."""
from threading import RLock
from kronos.intraday.wo09_readiness import create_next_wo_handoff
from kronos.application.intraday_evidence_currentness import IntradayPublicationBoundary


def historical_handoff(store, readiness, *, created_at, first_five_of_five_at=None):
    pointer = store.load_pointer(readiness.canonical_subject_identity)
    h = create_next_wo_handoff(readiness, created_at=created_at,
        current_readiness_identity=pointer.readiness_identity,
        current_pointer_integrity=pointer.integrity_identity,
        currentness=pointer.currentness,
        superseded_readiness_identity=pointer.superseded_readiness_identity,
        first_five_of_five_at=first_five_of_five_at)
    store.retain_handoff(h, expected=store.expectation(readiness.canonical_subject_identity))
    return h


def lifecycle_boundary(futures):
    # Explicit test owner. This is not canonical wiring or proof that unmodified
    # Wo09Store writers participate in the lock. The escape test demonstrates it.
    lock = RLock()
    def read(action, identity):
        h = futures.store.load(identity)
        subject = h.data['selection']['comparison']['subject']
        p = futures.wo09.load_pointer(subject)
        c = futures.store.current(subject)
        return (('WO09', None if p is None else p.integrity_identity),
                ('WO10', None if c is None else c.identity))
    return IntradayPublicationBoundary(scope=lambda:lock, read=read,
                                        assess=lambda action, identity:True)


def governed_graph(tmp_path, mapping, run, facts, *, clock, binding=None):
    """Real disposable producer/Review/Answer graph, synthetic observer only.

    Handoff fixtures test historical persisted storage; they are not proof of
    original first-five provenance or prospective application authorization.
    """
    from datetime import timedelta
    from dataclasses import replace
    from types import SimpleNamespace
    import json
    from kronos.intraday.probables_v2_persistence import ProbablesV2Store
    from kronos.intraday.review_v2_persistence import IntradayReviewV2Store
    from kronos.intraday.review_v2_transport import IntradayReviewV2Transport
    from kronos.application.intraday_review_v2 import IntradayReviewV2Application
    from kronos.instrument.visual_identity import (VisualIdentityResolver, VisualIdentitySourceContext,
        VisualIdentityRelationshipStatus, create_visual_identity_publication, create_visual_identity_relationship,
        VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1)
    from kronos.intraday.review_mcx_paired_persistence import IntradayMcxPairedReviewStore
    from kronos.instrument.active_derivative_persistence import ActiveDerivativeBindingStore
    from kronos.intraday.visual_reconciliation_v2_persistence import VisualReconciliationStore
    from kronos.application.intraday_visual_reconciliation_v2 import IntradayVisualReconciliationV2Application
    from kronos.application import intraday_review_ordered_batch
    from kronos.intraday.wo09_persistence import Wo09Store
    from kronos.intraday.wo10_futures_store import FuturesStore
    from kronos.intraday.wo09_readiness import build_wo09_evidence, evaluate_readiness
    from kronos.market.calendar import MarketCalendarPublisher
    from kronos.market.schedule import MarketSessionWindow
    from tests.unit.intraday.chart_input_fixtures import observe_fixture_uploads
    from tests.unit.intraday.test_review import _png
    from tests.unit.intraday.test_review_v2_individual_inbox import _completed
    subject=mapping.canonical_subject_identity
    probables=ProbablesV2Store((tmp_path/'probables').resolve())
    probables.retain_complete(run=run,mappings=(mapping,))
    review=IntradayReviewV2Store((tmp_path/'review').resolve())
    relationships=(create_visual_identity_relationship(canonical_subject_identity=subject,
        observed_visible_subject_identity=subject,source_context=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
        effective_from=run.analysis_boundary-timedelta(days=1),effective_through=run.analysis_boundary+timedelta(days=1),
        status=VisualIdentityRelationshipStatus.ACTIVE,source_identity='ISOLATED',provenance=('ISOLATED',),supersedes=None),)
    resolver=VisualIdentityResolver(create_visual_identity_publication(canonical_subject_identities=(subject,),
        publication_identity=VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1,publication_version='1.0.0',
        effective_from=run.analysis_boundary-timedelta(days=1),effective_through=run.analysis_boundary+timedelta(days=1),
        source_identities=('ISOLATED',),provenance=('ISOLATED',),relationships=relationships,supersedes=None,
        schema_identity=VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1))
    app=IntradayReviewV2Application(probables_store=probables,review_store=review,
        transport=IntradayReviewV2Transport(question_outbox=(tmp_path/'questions').resolve(),answer_inbox=(tmp_path/'answers').resolve()),
        visual_identity_resolver=resolver,clock=clock)
    if binding is not None:
        app._paired.bindings.retain(binding)
        from tests.unit.intraday.test_review_mcx_paired import _resolver
        app._paired.native_resolver=_resolver(binding.active_binding.derivative_contract_id,
            'ISOLATED-EXACT-NATIVE',run.analysis_boundary)
    class FixtureCalendar:
        def instrument_session_profile(self,exchange,day,*,canonical_instrument_id,observed_at):
            real=MarketCalendarPublisher().instrument_session_profile(exchange,day,
                canonical_instrument_id=subject if exchange=='MCX' else 'NSE-EQ-BDL',observed_at=observed_at)
            if real is None or day not in {facts.current_schedule.trading_date,facts.previous_schedule.trading_date}:return None
            schedule=facts.current_schedule
            def profile_for(day):
                return facts.current_schedule if day==facts.current_schedule.trading_date else facts.previous_schedule
            schedule=profile_for(day)
            fixed=replace(real.continuous_trading,session_identity=schedule.session_id,
                session_open=schedule.windows[0].opens_at,session_close=schedule.windows[-1].closes_at,
                windows=tuple(MarketSessionWindow(schedule.session_id+':WINDOW:'+str(i),i,w.opens_at,w.closes_at)
                    for i,w in enumerate(schedule.windows,1)),calendar_identity=schedule.source_identity,
                source_identity=schedule.source_identity,calendar_version=schedule.source_version)
            return SimpleNamespace(continuous_trading=fixed,closing_auction_session=None)
        def mcx_contract_session_profile(self, *, contract_family, contract_expiry, trading_date, observed_at):
            assert binding is not None
            assert (contract_family,contract_expiry)==(binding.provider_contract_family,binding.contract_expiry)
            return self.instrument_session_profile('MCX',trading_date,
                canonical_instrument_id=subject,observed_at=observed_at)
    calendar=FixtureCalendar();app._chart_input.calendar=calendar
    observe_fixture_uploads(app)
    app.create_eligible_cycles(run)
    cycle=review.load_cycle(app.snapshot().candidates[0].cycle_identity)
    metadata=None if binding is None else app._paired.options(cycle)
    chart=app.upload_chart(cycle.cycle_identity,media_type='image/png',payload=_png(77),paired_metadata=metadata)
    transport=app.create_individual_question_transport(cycle.cycle_identity)
    if binding is None:
        payload=_completed(transport.answer_template_path)
    else:
        # A predeclared synthetic retained observation qualifies the existing
        # exact-contract codec. It is neither empirical chart truth nor an
        # original first-five producer.
        from datetime import timedelta
        from kronos.intraday.mcx_history import create_retained_mcx_candles
        from kronos.intraday.contracts import IntradayTimeframe, CandleCompletion
        from kronos.provider.contracts.market_data import HistoricalCandle
        from kronos.intraday.chart_input import ChartInputObservation,ObservedChartPanel,CORE_CONTENT
        from kronos.intraday.validation import FactObservability
        previous=facts.previous_schedule
        rows=create_retained_mcx_candles(active_binding=binding,timeframe=IntradayTimeframe.ONE_HOUR,
            schedule=previous,candles=tuple(HistoricalCandle(previous.windows[0].opens_at+timedelta(hours=i),
                100.0,104.0,99.0,102.0,100) for i in range(6)),
            observation_boundary=run.analysis_boundary,source_operation_identity='ISOLATED-HISTORY')
        app._chart_input.native_history.retain_many(rows)
        bundle=app._paired.restore(cycle,chart)[0]
        ref=bundle.reference_relationship
        first=app._paired.native_resolver.publication
        second=_resolver(ref.reference_analytical_subject_identity,ref.governed_visible_identity,run.analysis_boundary).publication
        app._paired.native_resolver=VisualIdentityResolver(create_visual_identity_publication(
            canonical_subject_identities=tuple(sorted({x.canonical_subject_identity for x in first.relationships+second.relationships})),
            publication_identity=first.publication_identity,publication_version=first.publication_version,
            effective_from=first.effective_from,effective_through=first.effective_through,
            source_identities=first.source_identities,provenance=first.provenance,
            relationships=first.relationships+second.relationships,supersedes=None,schema_identity=first.schema_identity))
        panels=[]
        for e in app._chart_input.expectations(cycle,chart,bundle):
            native=e.role=='NATIVE';c=e.source;schedule=e.schedule
            assert not native or (c is not None and schedule is not None)
            start=(c.derived_start if e.timeframe=='4H' else c.candle_start) if native else None
            end=(c.derived_end if e.timeframe=='4H' else c.candle_end) if native else None
            panels.append(ObservedChartPanel(e.role,e.timeframe,'ISOLATED-EXACT-NATIVE' if native else ref.governed_visible_identity,
                e.venue,None if native else 'ISOLATED-REFERENCE',e.currency,None,schedule.trading_date if native else None,
                schedule.session_type if native else None,schedule.timezone if native else None,
                start,end,CandleCompletion.COMPLETE if native else None,chart.received_at,end,True,False,
                tuple((key,FactObservability.EXACT) for key in CORE_CONTENT)))
        app.review_store.retain_chart_input(ChartInputObservation(chart.chart_revision_identity,chart.payload_sha256,
            cycle.cycle_identity,cycle.probables_run_identity,cycle.probable_result_identity,
            'ISOLATED-RETAINED-OBSERVER-NOT-PRODUCTION',chart.received_at,tuple(panels)))
        from tests.unit.intraday.test_review_v2_paired_intake import complete_paired
        payload=complete_paired(app,transport,native='ISOLATED-EXACT-NATIVE',reference='ISOLATED-REFERENCE')
    (app._transport.answer_inbox/transport.transport.expected_answer_filename).write_bytes(payload)
    imported=app.import_expected_answer(cycle.cycle_identity)
    assert imported.imported_count==1,imported
    paired=app._paired.store
    bindings=app._paired.bindings
    reconciliation=VisualReconciliationStore((tmp_path/'wo07f').resolve())
    reconciler=IntradayVisualReconciliationV2Application(review=app,review_store=review,paired_store=paired,store=reconciliation,clock=clock)
    outcome=reconciler.reconcile_all_ready()
    assert outcome['success_count']==1,outcome
    visual=(review.load_visual_evidence(app.snapshot().candidates[0].visual_evidence_identity) if binding is None
        else paired.load_evidence(app.snapshot().candidates[0].visual_evidence_identity))
    reconciled=reconciliation.restore_current(cycle.cycle_identity)
    readiness,requirements=evaluate_readiness(reconciled,build_wo09_evidence(reconciled,mapping.semantic_evidence,mapping.completed_evidence,visual,
        exact_mcx_contract_identity=None if binding is None else binding.active_binding.derivative_contract_id,
        exact_mcx_roll_lineage=None if binding is None else binding.binding_identity),created_at=clock())
    wo09=Wo09Store(tmp_path/'wo09');futures=FuturesStore(tmp_path/'futures')
    boundary=IntradayPublicationBoundary(review=review,probables=probables,paired=paired,bindings=bindings,
        reconciliation=reconciliation,ordered_batch=intraday_review_ordered_batch,wo09=wo09,futures=futures,calendar=calendar,clock=clock)
    return SimpleNamespace(boundary=boundary,readiness=readiness,requirements=requirements,
        wo09=wo09,futures=futures,review=app,probables=probables,reconciliation=reconciler)
