from dataclasses import fields, replace
from datetime import UTC, datetime, timedelta
import inspect
from types import SimpleNamespace

import pytest

from kronos.application import swing_opportunities as app
from kronos.configuration.principals import PrincipalBindingResult
from kronos.market.calendar import MarketCalendarPublisher
from kronos.provider.contracts.provider_authentication import ReadOnlyProviderOperation
from kronos.provider.models.authentication import AuthenticationAttemptState
from kronos.provider.contracts.market_data import HistoricalCandle
from kronos.swing.daily_data import build_swing_daily_dataset
from kronos.swing.market_assessment import assess_swing_market
from kronos.swing.run_provenance import LocalSwingRunProvenanceStore
from kronos.swing.trade_plan import TradePlanFailure, TradePlanStatus
from kronos.swing.universe import enabled_swing_phase1_universe
from kronos.swing.zero import SwingSetup
from kronos.swing.v1.shadow_mtf import ShadowMtfRun
from kronos.swing.v1.mtf_facts import MtfFactEvidenceStore
from kronos.swing.v1.native_discovery import (
    NativeDiscoveryEvidenceStore,
    discover_native_mtf,
)
from tests.unit.browser.test_browser_shadow_validation import _assessment as _shadow_assessment
from tests.unit.application.test_swing_mtf_facts import _build as _mtf_fact_fixture
from tests.unit.swing.test_swing_candidate_ranking import _plan
from tests.unit.swing.test_swing_candidate_validation import (
    _candles as _stage4_candles,
    _instrument as _stage4_instrument,
)
from tests.unit.swing.test_swing_top_opportunity import _selection


NOW = datetime(2026, 8, 11, 4, 30, tzinfo=UTC)


class _Capability:
    operations = frozenset(ReadOnlyProviderOperation)

    def __init__(self) -> None:
        self.active = True


class _Provider:
    def __init__(self, capability: object | None = None) -> None:
        self.capability = capability or _Capability()
        self.attempt = object()
        self.ended = False

    def begin_login(self):  # type: ignore[no-untyped-def]
        return self.attempt

    def complete_callback(self, attempt):  # type: ignore[no-untyped-def]
        assert attempt is self.attempt
        return SimpleNamespace(
            state=AuthenticationAttemptState.SUCCEEDED,
            binding_result=PrincipalBindingResult.MATCHED,
        )

    def authenticated_read_only_capability(self):  # type: ignore[no-untyped-def]
        return self.capability

    def end_kronos_session(self) -> None:
        self.ended = True
        if isinstance(self.capability, _Capability):
            self.capability.active = False


def _immediate(operation, _name):  # type: ignore[no-untyped-def]
    operation()


def _completed(workspace, evidence=None):  # type: ignore[no-untyped-def]
    return SimpleNamespace(workspace=workspace, evidence=evidence or object())


def _ready(*opportunities: app.OpportunitySnapshot) -> app.BrowserWorkspaceSnapshot:
    eligible_plans = tuple(_eligible(opportunity) for opportunity in opportunities)
    return app.BrowserWorkspaceSnapshot(
        app.ProviderConnectionState.CONNECTED,
        app.AnalysisState.READY,
        98,
        observation_boundary=NOW,
        completed_at=NOW,
        qualified_count=len(opportunities),
        actionable_count=len(opportunities),
        attention_eligible_count=len(opportunities),
        opportunities=tuple(opportunities),
        eligible_plans=eligible_plans,
    )


def _real_completed(monkeypatch) -> app.CompletedSwingAnalysis:  # type: ignore[no-untyped-def]
    def historical(request):  # type: ignore[no-untyped-def]
        candles = _stage4_candles(request.instrument.name)
        first = candles[0]
        prefix = tuple(
            HistoricalCandle(
                timestamp=first.timestamp - timedelta(days=offset),
                open=first.open,
                high=first.high,
                low=first.low,
                close=first.close,
                volume=first.volume,
            )
            for offset in range(5, 0, -1)
        )
        return prefix + candles

    dataset = build_swing_daily_dataset(
        enabled_swing_phase1_universe(),
        resolve_instrument=lambda member: _stage4_instrument(
            member.canonical_identity
        ),
        historical_candles=historical,
        now=datetime(2026, 8, 8, 12, 0, tzinfo=NOW.tzinfo),
    )
    market = assess_swing_market(dataset)

    class Instruments:
        def __init__(self, _capability) -> None:  # type: ignore[no-untyped-def]
            pass

        def retrieve(self, _exchange):  # type: ignore[no-untyped-def]
            return ()

    class MarketData:
        def __init__(self, _capability) -> None:  # type: ignore[no-untyped-def]
            pass

    monkeypatch.setattr(app, "KiteInstrumentProvider", Instruments)
    monkeypatch.setattr(app, "KiteMarketDataProvider", MarketData)
    monkeypatch.setattr(app, "build_swing_daily_dataset", lambda *_a, **_k: dataset)
    monkeypatch.setattr(app, "assess_swing_market", lambda _dataset: market)
    return app.build_completed_swing_analysis(
        _Capability(),
        analysis_run_identity="ANALYSIS-000001",
        now=NOW,
        pace=lambda: None,
    )


def test_completed_analysis_requires_same_immutable_daily_and_shadow_run(monkeypatch) -> None:
    completed = _real_completed(monkeypatch)
    base = _shadow_assessment()
    assessments = tuple(
        replace(
            base,
            run_identity=completed.evidence.swing_analysis_run_identity,
            canonical_instrument=f"INSTRUMENT {index}",
        )
        for index in range(98)
    )
    shadow = ShadowMtfRun(
        completed.evidence.swing_analysis_run_identity,
        base.provider_source_identity,
        assessments,
    )
    assert app.CompletedSwingAnalysis(
        completed.workspace,
        completed.evidence,
        shadow,
    ).shadow_run is shadow
    wrong_run_identity = "SWING-RUN-FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF"
    wrong_shadow = ShadowMtfRun(
        wrong_run_identity,
        base.provider_source_identity,
        tuple(replace(item, run_identity=wrong_run_identity) for item in assessments),
    )
    with pytest.raises(ValueError, match="COMPLETED_SWING_ANALYSIS_INVALID"):
        app.CompletedSwingAnalysis(
            completed.workspace,
            completed.evidence,
            wrong_shadow,
        )


def _eligible(
    opportunity: app.OpportunitySnapshot,
    *,
    selected: bool = True,
) -> app.EligiblePlanSnapshot:
    return app.EligiblePlanSnapshot(
        stage8_rank=opportunity.position,
        opportunity=opportunity,
        selection_status="SELECTED" if selected else "NOT SELECTED",
        selection_reason=(
            "Selected by existing Stage-9 policy."
            if selected
            else "Attention eligible; not selected because the global Top Opportunity limit is 2."
        ),
        top_position=opportunity.position if selected else None,
    )


def _opportunity(position: int = 1) -> app.OpportunitySnapshot:
    return app.OpportunitySnapshot(
        position=position,
        panel=app.MarketPanel.EQUITIES_INDICES,
        instrument="HDFCBANK",
        direction="SHORT",
        setup="CONSOLIDATION_BREAKOUT",
        state="QUALIFIED",
        entry=728.2,
        entry_condition="A subsequent session trades BELOW Entry",
        stop=736.0,
        thesis_invalidation=("Completed Daily Close >= range low",),
        target_1=706.1,
        risk=7.8,
        reward=22.1,
        risk_reward=2.8333,
        why="Breakout qualified.",
        evidence_for=("Range break",),
        evidence_against_or_risks=("Close back inside range",),
        next_required_event="Subsequent session trades below Entry",
        observation_boundary=NOW,
        swing_zero_policy="SWING-ZERO-V0-CLASSIFICATION-POLICY",
        trade_plan_policy="SWING-PHASE1-V0-TRADE-PLAN-POLICY",
        ranking_policy="SWING-PHASE1-V0-CANDIDATE-RANKING-POLICY",
        top_opportunity_policy="SWING-PHASE1-V0-TOP-OPPORTUNITY-POLICY",
    )


def test_initial_state_is_disconnected_and_not_run() -> None:
    service = app.SwingOpportunitiesApplication(_Provider)
    assert service.snapshot() == app.BrowserWorkspaceSnapshot(
        app.ProviderConnectionState.DISCONNECTED,
        app.AnalysisState.NOT_RUN,
        98,
    )


def test_live_monitoring_rejects_concurrency_without_workspace_mutation(
    monkeypatch,
) -> None:
    pending = []

    def runner(operation, name):  # type: ignore[no-untyped-def]
        if name == "kronos-browser-auth":
            operation()
        else:
            pending.append(operation)

    service = app.SwingOpportunitiesApplication(_Provider, background_runner=runner)
    assert service.connect_provider()
    before = service.snapshot()
    assert service.test_live_monitoring("RELIANCE")
    assert service.live_monitoring_result().state is app.LiveMonitoringTestState.TESTING
    assert service.test_live_monitoring("RELIANCE") is False
    assert service.live_monitoring_result().state is app.LiveMonitoringTestState.TESTING
    assert service.run_analysis() is False
    assert service.disconnect_provider() is False
    assert service.snapshot() == before

    monkeypatch.setattr(
        app,
        "run_live_monitoring_e2e",
        lambda *_a, **_k: app.LiveMonitoringTestResult(
            app.LiveMonitoringTestState.CONNECTED_NO_DATA,
            "RELIANCE",
            safe_reason="NO_LIVE_MARKET_DATA",
        ),
    )
    assert len(pending) == 1
    pending.pop()()
    assert (
        service.live_monitoring_result().state
        is app.LiveMonitoringTestState.CONNECTED_NO_DATA
    )
    assert service.snapshot() == before


def test_authentication_retains_exact_provider_and_capability_in_same_process(
    monkeypatch,
) -> None:
    provider = _Provider()
    received: list[object] = []
    completed = _ready(_opportunity())
    monkeypatch.setattr(
        app,
        "build_completed_swing_analysis",
        lambda capability, **_kwargs: (
            received.append(capability) or _completed(completed)
        ),
    )
    service = app.SwingOpportunitiesApplication(
        lambda: provider,
        clock=lambda: NOW,
        background_runner=_immediate,
    )
    assert service.connect_provider()
    assert service.snapshot().provider_state is app.ProviderConnectionState.CONNECTED
    assert service.run_analysis()
    assert received == [provider.capability]
    assert service.snapshot() == completed


def test_failed_authentication_is_sanitized() -> None:
    service = app.SwingOpportunitiesApplication(
        lambda: (_ for _ in ()).throw(RuntimeError("secret provider detail")),
        background_runner=_immediate,
    )
    assert service.connect_provider()
    snapshot = service.snapshot()
    assert snapshot.provider_state is app.ProviderConnectionState.ERROR
    assert snapshot.provider_failure == "PROVIDER_CONNECTION_FAILED"
    assert "secret provider detail" not in repr(snapshot)


def test_concurrent_analysis_is_rejected_and_publication_is_atomic(monkeypatch) -> None:
    queued: list[callable] = []
    provider = _Provider()
    service = app.SwingOpportunitiesApplication(
        lambda: provider,
        clock=lambda: NOW,
        background_runner=lambda operation, _name: queued.append(operation),
    )
    service.connect_provider()
    queued.pop(0)()
    completed = _ready(_opportunity())
    monkeypatch.setattr(
        app,
        "build_completed_swing_analysis",
        lambda *_a, **_k: _completed(completed),
    )
    assert service.run_analysis()
    assert service.snapshot().analysis_state is app.AnalysisState.RUNNING
    assert service.snapshot().opportunities == ()
    assert service.run_analysis() is False
    queued.pop(0)()
    assert service.snapshot() == completed


@pytest.mark.parametrize("stage", tuple(app.AnalysisStage))
def test_each_analysis_stage_retains_only_sanitized_failure_context(
    monkeypatch,
    stage: app.AnalysisStage,
) -> None:
    provider = _Provider()
    previous = _ready(_opportunity())

    class ProviderPayloadFailure(RuntimeError):
        pass

    def fail(_capability, *, progress_observer, **_kwargs):  # type: ignore[no-untyped-def]
        progress_observer(app.AnalysisProgress(
            stage=stage,
            canonical_instrument="RELIANCE" if stage is app.AnalysisStage.TRADE_PLAN else None,
            completed_instrument_count=98,
            observation_boundary=NOW,
            provider_capability_active=True,
        ))
        raise ProviderPayloadFailure("access_token=forbidden-provider-payload")

    monkeypatch.setattr(app, "build_completed_swing_analysis", fail)
    service = app.SwingOpportunitiesApplication(
        lambda: provider,
        clock=lambda: NOW,
        background_runner=_immediate,
        initial_snapshot=previous,
    )
    service._SwingOpportunitiesApplication__provider = provider

    assert service.run_analysis()
    diagnostic = service.analysis_diagnostic()
    assert diagnostic is not None
    assert diagnostic.failing_stage is stage
    assert diagnostic.exception_class == "ProviderPayloadFailure"
    assert diagnostic.sanitized_summary == "SANITIZED_FAILURE"
    assert "forbidden" not in repr(diagnostic).lower()
    assert service.snapshot().analysis_state is app.AnalysisState.ERROR
    assert service.snapshot().analysis_failure == "SWING_ANALYSIS_FAILED"
    assert service.snapshot().opportunities == previous.opportunities


def test_successful_analysis_clears_stale_diagnostic(monkeypatch) -> None:
    provider = _Provider()
    service = app.SwingOpportunitiesApplication(
        lambda: provider,
        clock=lambda: NOW,
        background_runner=_immediate,
    )
    assert service.connect_provider()

    monkeypatch.setattr(
        app,
        "build_completed_swing_analysis",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("FIRST_SAFE_FAILURE")),
    )
    assert service.run_analysis()
    first = service.analysis_diagnostic()
    assert first is not None and first.attempt_id == "ANALYSIS-000001"

    completed = _ready(_opportunity())
    monkeypatch.setattr(
        app,
        "build_completed_swing_analysis",
        lambda *_a, **_k: _completed(completed),
    )
    assert service.run_analysis()
    assert service.analysis_diagnostic() is None
    assert service.snapshot() == completed


def test_successful_analysis_atomically_retains_same_run_mtf_facts(
    monkeypatch,
    tmp_path,
) -> None:
    completed = _real_completed(monkeypatch)
    facts, _ = _mtf_fact_fixture()
    facts = replace(
        facts,
        run_identity=completed.evidence.swing_analysis_run_identity,
    )
    completed = replace(completed, mtf_fact_snapshot=facts)
    store = MtfFactEvidenceStore(tmp_path)
    service = app.SwingOpportunitiesApplication(
        _Provider,
        clock=lambda: NOW,
        background_runner=_immediate,
        mtf_fact_evidence_store=store,
    )
    assert service.connect_provider()
    monkeypatch.setattr(
        app,
        "build_completed_swing_analysis",
        lambda *_a, **_k: completed,
    )

    assert service.run_analysis()
    assert service.snapshot() == completed.workspace
    assert service.mtf_fact_snapshot() == facts
    assert store.load(facts.run_identity) == facts


def test_successful_analysis_atomically_retains_native_discovery(
    monkeypatch,
    tmp_path,
) -> None:
    completed = _real_completed(monkeypatch)
    facts, _ = _mtf_fact_fixture()
    facts = replace(
        facts,
        run_identity=completed.evidence.swing_analysis_run_identity,
    )
    native = discover_native_mtf(facts)
    completed = replace(
        completed,
        mtf_fact_snapshot=facts,
        native_discovery_run=native,
    )
    store = NativeDiscoveryEvidenceStore(tmp_path)
    service = app.SwingOpportunitiesApplication(
        _Provider,
        clock=lambda: NOW,
        background_runner=_immediate,
        native_discovery_evidence_store=store,
    )
    assert service.connect_provider()
    monkeypatch.setattr(
        app,
        "build_completed_swing_analysis",
        lambda *_a, **_k: completed,
    )

    assert service.run_analysis()
    assert service.native_discovery_run() == native
    assert store.load(native.run_identity) == native
    projected_snapshot, projected_discovery = service.opportunities_projection()
    assert projected_snapshot == service.snapshot()
    assert projected_discovery == native

    successful_completed_at = projected_snapshot.completed_at
    monkeypatch.setattr(
        app,
        "build_completed_swing_analysis",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("SAFE_FAILURE")),
    )

    assert service.run_analysis()
    failed_snapshot, retained_discovery = service.opportunities_projection()
    assert failed_snapshot.analysis_state is app.AnalysisState.ERROR
    assert failed_snapshot.completed_at == successful_completed_at
    assert retained_discovery == native


def test_native_discovery_is_recovered_for_last_successful_run(
    monkeypatch,
    tmp_path,
) -> None:
    completed = _real_completed(monkeypatch)
    facts, _ = _mtf_fact_fixture()
    run_id = completed.evidence.swing_analysis_run_identity
    facts = replace(facts, run_identity=run_id)
    native = discover_native_mtf(facts)
    provenance_store = LocalSwingRunProvenanceStore(tmp_path / "runs")
    native_store = NativeDiscoveryEvidenceStore(tmp_path / "native")
    provenance_store.retain(app.SwingAnalysisRunProvenance(
        run_id=run_id,
        run_created_at=completed.evidence.run_created_at,
        analysis_boundary=completed.evidence.observation_boundary,
        market_data_snapshot_identity=completed.evidence.market_data_snapshot_identity,
        successful_completed_at=NOW,
    ))
    native_store.retain(native)

    service = app.SwingOpportunitiesApplication(
        _Provider,
        run_provenance_store=provenance_store,
        native_discovery_evidence_store=native_store,
    )

    assert service.snapshot().swing_analysis_run_identity == run_id
    assert service.native_discovery_run() == native
    assert service.opportunities_projection() == (service.snapshot(), native)


def test_real_builder_emits_every_component_stage(monkeypatch) -> None:
    stages: list[app.AnalysisStage] = []
    completed_fixture = _real_completed(monkeypatch)
    dataset = completed_fixture.evidence.daily_dataset
    market = completed_fixture.evidence.market_assessment

    class Instruments:
        def __init__(self, _capability) -> None:  # type: ignore[no-untyped-def]
            pass

        def retrieve(self, _exchange):  # type: ignore[no-untyped-def]
            return ()

    class MarketData:
        def __init__(self, _capability) -> None:  # type: ignore[no-untyped-def]
            pass

    monkeypatch.setattr(app, "KiteInstrumentProvider", Instruments)
    monkeypatch.setattr(app, "KiteMarketDataProvider", MarketData)
    monkeypatch.setattr(app, "build_swing_daily_dataset", lambda *_a, **_k: dataset)
    monkeypatch.setattr(app, "assess_swing_market", lambda _dataset: market)

    completed = app.build_completed_swing_analysis(
        _Capability(),
        analysis_run_identity="ANALYSIS-000001",
        now=NOW,
        pace=lambda: None,
        progress_observer=lambda progress: stages.append(progress.stage),
    )
    result = completed.workspace

    assert result.analysis_state is app.AnalysisState.READY
    assert result.analysis_run_identity == completed.evidence.analysis_run_identity
    assert result.run_created_at == NOW
    assert result.run_created_at == completed.evidence.run_created_at
    assert result.observation_boundary == completed.evidence.observation_boundary
    assert result.market_data_snapshot_identity.startswith(
        "SWING-MARKET-DATA-SNAPSHOT-"
    )
    assert (
        result.market_data_snapshot_identity
        == completed.evidence.market_data_snapshot_identity
    )
    assert len(completed.evidence.universe) == 98
    assert len(completed.evidence.instrument_assessments) == 98
    assert len(completed.evidence.assessments) == 196
    assert not hasattr(result, "market_assessment")
    assert tuple(dict.fromkeys(stages)) == (
        app.AnalysisStage.UNIVERSE,
        app.AnalysisStage.DAILY_DATA,
        app.AnalysisStage.MARKET_ASSESSMENT,
        app.AnalysisStage.CANDIDATE_EXTRACTION,
        app.AnalysisStage.TRADE_PLAN,
        app.AnalysisStage.RANKING,
        app.AnalysisStage.TOP_OPPORTUNITY,
        app.AnalysisStage.BROWSER_PROJECTION,
    )
    assert stages.count(app.AnalysisStage.TRADE_PLAN) == 13


def test_production_run_publishes_factual_mtf_without_invoking_shadow_candidate_authority(
    monkeypatch,
) -> None:
    stages: list[app.AnalysisStage] = []
    completed_fixture = _real_completed(monkeypatch)
    dataset = completed_fixture.evidence.daily_dataset
    market = completed_fixture.evidence.market_assessment
    facts, _ = _mtf_fact_fixture()

    class Instruments:
        def __init__(self, _capability) -> None:  # type: ignore[no-untyped-def]
            pass

        def retrieve(self, _exchange):  # type: ignore[no-untyped-def]
            return ()

    class MarketData:
        def __init__(self, _capability) -> None:  # type: ignore[no-untyped-def]
            pass

    def factual(**kwargs):  # type: ignore[no-untyped-def]
        assert kwargs["daily_dataset"] is dataset
        return replace(facts, run_identity=kwargs["run_identity"])

    monkeypatch.setattr(app, "KiteInstrumentProvider", Instruments)
    monkeypatch.setattr(app, "KiteMarketDataProvider", MarketData)
    monkeypatch.setattr(app, "build_swing_daily_dataset", lambda *_a, **_k: dataset)
    monkeypatch.setattr(app, "assess_swing_market", lambda _dataset: market)
    monkeypatch.setattr(app, "build_same_run_mtf_fact_snapshot", factual)

    completed = app.build_completed_swing_analysis(
        _Capability(),
        analysis_run_identity="ANALYSIS-000001",
        now=NOW,
        pace=lambda: None,
        market_calendar_publisher=MarketCalendarPublisher(),
        progress_observer=lambda progress: stages.append(progress.stage),
    )

    assert completed.mtf_fact_snapshot is not None
    assert completed.native_discovery_run is not None
    assert (
        completed.native_discovery_run.run_identity
        == completed.mtf_fact_snapshot.run_identity
    )
    assert completed.shadow_run is None
    assert app.AnalysisStage.MTF_FACTS in stages
    assert app.AnalysisStage.NATIVE_DISCOVERY in stages
    assert app.AnalysisStage.SHADOW_MTF not in stages


def test_successful_browser_run_persists_restart_safe_provenance(
    monkeypatch,
    tmp_path,
) -> None:
    completed = _real_completed(monkeypatch)
    store = LocalSwingRunProvenanceStore(tmp_path)
    successful_completion = NOW + timedelta(minutes=7)
    clock_values = iter((NOW, successful_completion))
    monkeypatch.setattr(
        app,
        "build_completed_swing_analysis",
        lambda *_a, **_k: completed,
    )
    service = app.SwingOpportunitiesApplication(
        _Provider,
        clock=lambda: next(clock_values),
        background_runner=_immediate,
        swing_run_identity_factory=lambda: (
            "SWING-RUN-00000000000000000000000000000001"
        ),
        run_provenance_store=store,
    )
    assert service.connect_provider()
    assert service.run_analysis()

    restarted_store = LocalSwingRunProvenanceStore(tmp_path)
    recovered = restarted_store.load(
        "SWING-RUN-00000000000000000000000000000001"
    )
    assert recovered.run_created_at == NOW
    assert recovered.successful_completed_at == successful_completion
    assert recovered.analysis_boundary == completed.evidence.observation_boundary
    assert (
        recovered.market_data_snapshot_identity
        == completed.evidence.market_data_snapshot_identity
    )
    restarted = app.SwingOpportunitiesApplication(
        _Provider,
        run_provenance_store=restarted_store,
    )
    assert restarted.snapshot().completed_at == successful_completion
    assert (
        restarted.snapshot().swing_analysis_run_identity
        == recovered.run_id
    )
    restored = restarted.restore_v1_review_projection(
        completed.evidence.v1_layer1_run,
        recovered,
    )
    assert restored.completed_at == successful_completion


def test_older_review_recovery_does_not_replace_current_successful_run(
    monkeypatch,
) -> None:
    completed = _real_completed(monkeypatch)
    current_run = "SWING-RUN-915BCB97344540B3B708FDCF8335FC7F"
    current_completed_at = NOW + timedelta(hours=2)
    current = replace(
        _ready(),
        swing_analysis_run_identity=current_run,
        run_created_at=NOW + timedelta(hours=1),
        completed_at=current_completed_at,
        market_data_snapshot_identity=(
            "SWING-MARKET-DATA-SNAPSHOT-" + "c" * 64
        ),
    )
    older = app.SwingAnalysisRunProvenance(
        run_id="SWING-RUN-413912F4B30840CAAC8EEFFCADEB666C",
        run_created_at=NOW - timedelta(days=1),
        analysis_boundary=completed.evidence.v1_layer1_run.observation_boundary,
        market_data_snapshot_identity=(
            "SWING-MARKET-DATA-SNAPSHOT-" + "d" * 64
        ),
        successful_completed_at=NOW - timedelta(hours=12),
    )
    service = app.SwingOpportunitiesApplication(
        _Provider,
        initial_snapshot=current,
    )

    restored = service.restore_v1_review_projection(
        completed.evidence.v1_layer1_run,
        older,
    )

    assert restored.swing_analysis_run_identity == current_run
    assert restored.completed_at == current_completed_at
    assert restored.market_data_snapshot_identity == (
        "SWING-MARKET-DATA-SNAPSHOT-" + "c" * 64
    )
    assert restored.v1_layer1_run_identity == (
        completed.evidence.v1_layer1_run.run_identity
    )


def test_successful_analysis_retains_complete_immutable_forensic_evidence(
    monkeypatch,
) -> None:
    completed = _real_completed(monkeypatch)
    evidence = completed.evidence

    assert len(evidence.universe) == 98
    assert evidence.daily_dataset.ready_count == 98
    assert len(evidence.instrument_assessments) == 98
    assert len(evidence.assessments) == 196
    assert len(evidence.analysis_failures) == 0
    assert len(evidence.qualified_candidates) == 12
    assert len(evidence.candidate_validation.audits) == 12
    assert len(evidence.trade_plans) == 12
    assert (
        len(evidence.actionable_plans)
        + len(evidence.not_actionable_plans)
        + len(evidence.invalid_plans)
        == len(evidence.trade_plans)
    )
    assert evidence.actionable_plans == tuple(
        item.trade_plan for item in evidence.ranked_actionable
    )
    assert evidence.attention_eligible == (
        evidence.top_opportunity_selection.attention_eligible
    )
    assert evidence.provisional_selection == (
        evidence.top_opportunity_selection.selected_top_opportunities
    )
    assert evidence.provider_neutral_provenance
    assert completed.workspace.qualified_count == 12
    assert completed.workspace.actionable_count == len(evidence.actionable_plans)
    assert completed.workspace.attention_eligible_count == len(
        evidence.attention_eligible
    )


def test_invalid_trade_plan_is_retained_in_completed_evidence(monkeypatch) -> None:
    production_builder = app.build_trade_plan
    invalidated = False

    def build_with_one_invalid(candidate, candles):  # type: ignore[no-untyped-def]
        nonlocal invalidated
        plan = production_builder(candidate, candles)
        if plan.status is TradePlanStatus.ACTIONABLE and not invalidated:
            invalidated = True
            return replace(
                plan,
                status=TradePlanStatus.INVALID,
                failure=TradePlanFailure.INVALID_STOP_GEOMETRY,
                risk_per_unit=0.0,
                reward_per_unit=0.0,
                risk_reward=None,
            )
        return plan

    monkeypatch.setattr(app, "build_trade_plan", build_with_one_invalid)
    evidence = _real_completed(monkeypatch).evidence

    assert invalidated
    assert len(evidence.invalid_plans) == 1
    assert evidence.invalid_plans[0] in evidence.trade_plans


def test_retained_evidence_is_queryable_without_provider_or_recalculation(
    monkeypatch,
) -> None:
    completed = _real_completed(monkeypatch)
    service = app.SwingOpportunitiesApplication(
        _Provider,
        clock=lambda: NOW,
        background_runner=_immediate,
    )
    assert service.connect_provider()
    monkeypatch.setattr(app, "build_completed_swing_analysis", lambda *_a, **_k: completed)
    assert service.run_analysis()
    evidence = service.completed_analysis_evidence()
    assert evidence is completed.evidence

    monkeypatch.setattr(
        app,
        "build_completed_swing_analysis",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("RECALCULATION")),
    )
    assert len(service.completed_analysis_evidence().assessments) == 196  # type: ignore[union-attr]
    assert service.snapshot().analysis_run_identity == "ANALYSIS-000001"


def test_failed_run_does_not_replace_latest_successful_evidence(monkeypatch) -> None:
    completed = _real_completed(monkeypatch)
    service = app.SwingOpportunitiesApplication(
        _Provider,
        clock=lambda: NOW,
        background_runner=_immediate,
    )
    assert service.connect_provider()
    monkeypatch.setattr(app, "build_completed_swing_analysis", lambda *_a, **_k: completed)
    assert service.run_analysis()
    prior_evidence = service.completed_analysis_evidence()
    prior_opportunities = service.snapshot().opportunities
    prior_completed_at = service.snapshot().completed_at

    monkeypatch.setattr(
        app,
        "build_completed_swing_analysis",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("SAFE_FAILURE")),
    )
    assert service.run_analysis()
    assert service.completed_analysis_evidence() is prior_evidence
    assert service.snapshot().opportunities == prior_opportunities
    assert service.snapshot().completed_at == prior_completed_at
    assert service.snapshot().analysis_state is app.AnalysisState.ERROR


def test_evidence_schema_cannot_retain_provider_credentials_or_internals(
    monkeypatch,
) -> None:
    evidence = _real_completed(monkeypatch).evidence
    forbidden = {
        "api_key", "api_secret", "access_token", "request_token",
        "instrument_token", "kite_client", "raw_payload",
    }
    assert forbidden.isdisjoint(field.name for field in fields(evidence))
    rendered = repr(evidence).lower()
    assert all(name not in rendered for name in forbidden)


def test_analysis_requires_connected_provider() -> None:
    assert app.SwingOpportunitiesApplication(_Provider).run_analysis() is False


def test_close_disposes_provider_locally() -> None:
    provider = _Provider()
    service = app.SwingOpportunitiesApplication(
        lambda: provider,
        background_runner=_immediate,
    )
    service.connect_provider()
    service.close()
    assert provider.ended
    assert service.snapshot().provider_state is app.ProviderConnectionState.DISCONNECTED


def test_disconnect_disposes_provider_and_old_capability_fails_closed(monkeypatch) -> None:
    provider = _Provider()
    service = app.SwingOpportunitiesApplication(
        lambda: provider,
        background_runner=_immediate,
    )
    completed = _ready(_opportunity())
    monkeypatch.setattr(
        app,
        "build_completed_swing_analysis",
        lambda *_a, **_k: _completed(completed),
    )
    assert service.connect_provider()
    assert service.run_analysis()
    old_capability = provider.capability

    assert service.disconnect_provider()
    snapshot = service.snapshot()
    assert provider.ended
    assert old_capability.active is False
    assert snapshot.provider_state is app.ProviderConnectionState.DISCONNECTED
    assert snapshot.analysis_state is app.AnalysisState.READY
    assert snapshot.opportunities == (_opportunity(),)
    assert service.run_analysis() is False
    assert service.disconnect_provider() is False


def test_disconnect_is_rejected_while_analysis_is_running() -> None:
    queued: list[callable] = []
    provider = _Provider()
    service = app.SwingOpportunitiesApplication(
        lambda: provider,
        background_runner=lambda operation, _name: queued.append(operation),
    )
    assert service.connect_provider()
    queued.pop(0)()
    assert service.run_analysis()

    assert service.disconnect_provider() is False
    assert provider.ended is False
    assert service.snapshot().provider_state is app.ProviderConnectionState.CONNECTED
    assert service.snapshot().analysis_state is app.AnalysisState.RUNNING


def test_browser_authority_source_exposes_no_order_or_raw_client_path() -> None:
    source = inspect.getsource(app)
    for forbidden in (
        "place_order",
        "modify_order",
        "cancel_order",
        "access_token",
        "api_secret",
        "request_token",
        "instrument_token",
    ):
        assert forbidden not in source


def test_snapshot_rejects_more_than_two_opportunities() -> None:
    with pytest.raises(ValueError, match="BROWSER_WORKSPACE_SNAPSHOT_INVALID"):
        app.BrowserWorkspaceSnapshot(
            app.ProviderConnectionState.CONNECTED,
            app.AnalysisState.READY,
            98,
            opportunities=(_opportunity(1), _opportunity(2), _opportunity(2)),
        )


def test_eligible_projection_uses_existing_selection_and_stage8_order() -> None:
    selection = _selection(
        _plan("HDFCBANK", 3.0),
        _plan("MARUTI", 2.0),
        _plan("POWERINDIA", 1.5),
    )
    selected = {
        item.trade_plan.candidate_identity: item
        for item in selection.selected_top_opportunities
    }
    selected_instruments = {
        item.attention_entry.canonical_identity
        for item in selection.selected_top_opportunities
    }
    projected = tuple(
        app._project_eligible_plan(
            item,
            app.MarketPanel.EQUITIES_INDICES,
            selected.get(item.ranked_plan.trade_plan.candidate_identity),
            item.ranked_plan.canonical_identity in selected_instruments,
        )
        for item in selection.attention_eligible
    )

    assert tuple(item.stage8_rank for item in projected) == (1, 2, 3)
    assert tuple(item.selection_status for item in projected) == (
        "SELECTED",
        "SELECTED",
        "NOT SELECTED",
    )
    assert projected[2].selection_reason == (
        "Attention eligible; not selected because the global Top Opportunity limit is 2."
    )


def test_eligible_projection_uses_existing_same_instrument_grouping_reason() -> None:
    selection = _selection(
        _plan("HDFCBANK", 3.0, setup=SwingSetup.PULLBACK_CONTINUATION),
        _plan("HDFCBANK", 2.0, setup=SwingSetup.CONSOLIDATION_BREAKOUT),
        _plan("MARUTI", 1.5),
    )
    selected = {
        item.trade_plan.candidate_identity: item
        for item in selection.selected_top_opportunities
    }
    selected_instruments = {
        item.attention_entry.canonical_identity
        for item in selection.selected_top_opportunities
    }
    support = selection.attention_eligible[1]
    projected = app._project_eligible_plan(
        support,
        app.MarketPanel.EQUITIES_INDICES,
        selected.get(support.ranked_plan.trade_plan.candidate_identity),
        support.ranked_plan.canonical_identity in selected_instruments,
    )

    assert projected.selection_status == "NOT SELECTED"
    assert projected.selection_reason == (
        "Attention eligible; not selected because its canonical instrument is already "
        "represented by a higher-ranked eligible plan."
    )
