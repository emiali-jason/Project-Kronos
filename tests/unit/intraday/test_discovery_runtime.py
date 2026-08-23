from datetime import datetime, timedelta
from decimal import Decimal
from dataclasses import replace
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from kronos.application.intraday_workstation import IntradayEvidenceBundle
from kronos.instrument.runtime import (
    create_canonical_instrument,
    create_provider_assertion,
    create_provider_binding_directive,
    publish_runtime_instruments,
)
from kronos.intraday.discovery import (
    CandidateState,
    DiscoveryError,
    DiscoveryFailure,
    DiscoveryReason,
    ExecutionEligibility,
    FactFamily,
    FactRequirement,
    FactualEvaluability,
    MachineFactEvidence,
    STRUCTURAL_TIMEFRAMES,
    create_machine_fact_bundle,
)
from kronos.intraday.discovery_persistence import NativeDiscoveryStore
from kronos.intraday.discovery_runtime import (
    DiscoveryFactAcquisition,
    DiscoveryMemberFactError,
    DiscoveryRunBoundary,
    IntradayNativeDiscoveryService,
    assemble_machine_fact_bundle,
)
from kronos.intraday.reconciliation import (
    Availability,
    RECONCILIATION_IDENTITY,
    RECONCILIATION_VERSION,
    ReconciliationState,
    create_reconciliation_member,
    create_reconciliation_publication,
)
from kronos.intraday.reconciliation_persistence import IntradayReconciliationStore
from kronos.intraday.universe import (
    IntradayMarketFamily,
    load_intraday_universe_publication,
)
from kronos.intraday.composition import compose_core_slice1_facts
from kronos.intraday.candles import expected_candle_boundaries
from kronos.intraday.contracts import SourceProvenance
from kronos.intraday.persistence import LocalIntradayFactualEvidenceStore
from kronos.provider.contracts.market_data import HistoricalCandle
from tests.unit.intraday.test_composition import (
    DAY,
    OBSERVED,
    _calendar,
)


NOW = datetime(2026, 8, 23, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
BOUNDARY = DiscoveryRunBoundary(
    NOW,
    "NSE-CAPITAL-MARKET-2026-08-23",
    "DOMAIN-008:NSE:2026-08-23:12:00:00+05:30",
)


class _Facts:
    def __init__(self, reconciliation, failures=()):  # type: ignore[no-untyped-def]
        self.reconciliation = reconciliation
        self.failures = frozenset(failures)
        self.labels: list[str] = []

    def acquire(self, *, member, boundary):  # type: ignore[no-untyped-def]
        self.labels.append(member.sponsor_label)
        if member.sponsor_label in self.failures:
            raise DiscoveryMemberFactError(DiscoveryReason.SOURCE_STALE)
        return DiscoveryFactAcquisition(
            member.universe_member_identity,
            member.canonical_identity,
            _bundle(member, boundary, self.reconciliation),
        )


def _publications():  # type: ignore[no-untyped-def]
    universe = load_intraday_universe_publication()
    reconciliation = IntradayReconciliationStore().load(
        publication_identity=RECONCILIATION_IDENTITY,
        publication_version=RECONCILIATION_VERSION,
    )
    return universe, reconciliation


def _bundle(member, boundary, reconciliation):  # type: ignore[no-untyped-def]
    evidence = [MachineFactEvidence(
        FactFamily.MARKET_SESSION_BOUNDARY,
        FactRequirement.MANDATORY,
        "DOMAIN-008-SESSION-EVIDENCE",
        "1.0.0",
        boundary.observation_boundary,
        None,
        None,
    )]
    for timeframe in STRUCTURAL_TIMEFRAMES:
        identity = f"{member.sponsor_label}-{timeframe.value}-EVIDENCE"
        evidence.extend((
            MachineFactEvidence(
                FactFamily.GOVERNED_COMPLETED_OHLCV,
                FactRequirement.MANDATORY,
                identity,
                "1.0.0",
                boundary.observation_boundary,
                timeframe,
                True,
            ),
            MachineFactEvidence(
                FactFamily.CANDLE_COMPLETENESS_RECONCILIATION,
                FactRequirement.MANDATORY,
                identity,
                "1.0.0",
                boundary.observation_boundary,
                timeframe,
                True,
            ),
        ))
    return create_machine_fact_bundle(
        canonical_identity=member.canonical_identity,
        universe_identity=reconciliation.universe_identity,
        universe_version=reconciliation.universe_version,
        reconciliation_identity=reconciliation.publication_identity,
        reconciliation_version=reconciliation.publication_version,
        market_session_identity=boundary.market_session_identity,
        market_session_boundary_identity=boundary.market_session_boundary_identity,
        observation_boundary=boundary.observation_boundary,
        evidence=tuple(evidence),
        source_identities=("DOMAIN-006:KITE:HISTORICAL",),
        provenance=("CONTROLLED-FIXTURE",),
    )


def _service(tmp_path: Path, failures=()):  # type: ignore[no-untyped-def]
    universe, reconciliation = _publications()
    source = _Facts(reconciliation, failures)
    store = NativeDiscoveryStore(tmp_path)
    return (
        IntradayNativeDiscoveryService(
            universe=universe,
            reconciliation=reconciliation,
            factual_source=source,
            store=store,
        ),
        source,
        store,
        reconciliation,
    )


def test_current_98_member_run_preserves_93_5_and_no_fake_candidates(
    tmp_path: Path,
) -> None:
    service, source, store, reconciliation = _service(tmp_path)

    execution = service.execute(BOUNDARY)
    run = execution.run

    assert run.accounting.universe_members == 98
    assert execution.pre_evaluable_count == 93
    assert run.accounting.factually_evaluable == 93
    assert run.accounting.prerequisite_unavailable == 5
    assert run.accounting.factual_failures == 0
    assert run.accounting.evaluated == run.accounting.candidate_results == 0
    assert len(run.results) == 98
    assert len(execution.bundles) == 93
    assert execution.timeframe_fact_requests == 93 * 4
    assert execution.source_operation_count == 93
    assert len(source.labels) == len(set(source.labels)) == 93
    assert sum(
        member.market_family is IntradayMarketFamily.NSE_EQUITY
        and member.sponsor_label in source.labels
        for member in reconciliation.members
    ) == 91
    assert {"NIFTY", "BANKNIFTY"}.issubset(source.labels)
    assert all(
        result.execution_eligibility is ExecutionEligibility.NOT_ESTABLISHED
        and result.candidate_state not in {
            CandidateState.CANDIDATE_ADMITTED,
            CandidateState.CANDIDATE_NOT_ADMITTED,
        }
        for result in run.results
    )
    assert store.load_run(run_identity=run.run_identity) == run
    assert all(
        store.load_bundle(bundle_identity=item.bundle_identity) == item
        for item in execution.bundles
    )


def test_exact_five_prerequisites_are_not_candidate_rejections(tmp_path: Path) -> None:
    service, _, _, _ = _service(tmp_path)
    run = service.execute(BOUNDARY).run

    expected = {
        "GOLDM": DiscoveryReason.ACTIVE_DERIVATIVE_BINDING_UNAVAILABLE,
        "SILVERM": DiscoveryReason.ACTIVE_DERIVATIVE_BINDING_UNAVAILABLE,
        "COPPER": DiscoveryReason.ACTIVE_DERIVATIVE_BINDING_UNAVAILABLE,
        "NATGAS": DiscoveryReason.PROVIDER_CONTRACT_UNAVAILABLE,
        "CRUDE": DiscoveryReason.PROVIDER_CONTRACT_UNAVAILABLE,
    }
    for label, reason in expected.items():
        result = run.lookup(label)
        assert result.evaluability is FactualEvaluability.PREREQUISITE_UNAVAILABLE
        assert result.candidate_state is CandidateState.NOT_EVALUATED_DUE_TO_PREREQUISITE
        assert result.reasons == (reason,)


def test_one_member_factual_failure_isolated_and_run_remains_complete(
    tmp_path: Path,
) -> None:
    service, source, _, _ = _service(tmp_path, failures=("RELIANCE",))

    run = service.execute(BOUNDARY).run

    assert len(source.labels) == 93
    assert len(run.results) == 98
    assert run.accounting.factually_evaluable == 92
    assert run.accounting.factual_failures == 1
    failed = run.lookup("RELIANCE")
    assert failed.evaluability is FactualEvaluability.FACTUAL_FAILURE
    assert failed.candidate_state is CandidateState.NOT_EVALUATED_DUE_TO_FACTUAL_FAILURE
    assert failed.reasons == (DiscoveryReason.SOURCE_STALE,)
    assert run.lookup("NIFTY").machine_fact_bundle_identity is not None


def test_identical_inputs_are_deterministic_and_idempotent(tmp_path: Path) -> None:
    service, _, store, _ = _service(tmp_path)

    first = service.execute(BOUNDARY)
    second = service.execute(BOUNDARY)

    assert first.run == second.run
    assert first.bundles == second.bundles
    assert store.load_run(run_identity=first.run.run_identity) == first.run


def test_incomplete_structural_candle_is_rejected() -> None:
    with pytest.raises(
        DiscoveryError,
        match=DiscoveryFailure.INCOMPLETE_CANDLE_NOT_AUTHORIZED.value,
    ):
        MachineFactEvidence(
            FactFamily.GOVERNED_COMPLETED_OHLCV,
            FactRequirement.MANDATORY,
            "INCOMPLETE",
            "1.0.0",
            NOW,
            STRUCTURAL_TIMEFRAMES[-1],
            False,
        )


def test_conflicting_immutable_bundle_is_rejected(tmp_path: Path) -> None:
    service, _, store, _ = _service(tmp_path)
    execution = service.execute(BOUNDARY)
    bundle = execution.bundles[0]
    store.bundle_path(bundle.bundle_identity).write_text("{}\n", encoding="utf-8")

    with pytest.raises(
        DiscoveryError,
        match=DiscoveryFailure.PERSISTENCE_CONFLICT.value,
    ):
        store.retain_bundle(bundle)


def test_existing_slice1_facts_adapt_to_mandatory_bundle_without_incomplete_candle(
    tmp_path: Path,
) -> None:
    _, reconciliation = _publications()
    calendar = _calendar()
    member = reconciliation.lookup("NIFTY")
    observed = datetime(2026, 8, 17, 16, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    canonical = create_canonical_instrument(
        canonical_instrument_id=member.canonical_identity,
        exchange="NSE",
        segment="INDICES",
        instrument_type="EQ",
        canonical_tick_size=Decimal("0.05"),
        canonical_lot_size=1,
        canonical_source_identity="KRONOS-CANONICAL-INSTRUMENT-CATALOGUE-V2",
        source_boundary=OBSERVED - timedelta(days=1),
        valid_through=observed + timedelta(days=1),
    )
    assertion = create_provider_assertion(
        provider="KITE",
        provider_symbol="NIFTY 50",
        provider_instrument_token=256265,
        exchange="NSE",
        segment="INDICES",
        instrument_type="EQ",
        asserted_tick_size=Decimal("0.05"),
        asserted_lot_size=1,
        binding_source_identity="KITE-INSTRUMENT-MASTER-20260817",
        source_boundary=OBSERVED - timedelta(hours=1),
        valid_through=observed + timedelta(days=1),
    )
    directive = create_provider_binding_directive(
        canonical_instrument_id=member.canonical_identity,
        provider="KITE",
        provider_symbol="NIFTY 50",
        directive_source_identity="GOVERNED-PROVIDER-BINDINGS-V2",
    )
    registry = publish_runtime_instruments(
        canonical_instruments=(canonical,),
        provider_assertions=(assertion,),
        binding_directives=(directive,),
        observed_at=observed,
    )
    schedule = calendar.schedule_for("NSE", DAY)
    assert schedule is not None
    candles = {}
    provenance = {}
    for timeframe in STRUCTURAL_TIMEFRAMES:
        timestamps = (
            (datetime(2026, 8, 17, 0, 0, tzinfo=ZoneInfo("Asia/Kolkata")),)
            if timeframe is STRUCTURAL_TIMEFRAMES[0]
            else tuple(item.start for item in expected_candle_boundaries(schedule, timeframe))
        )
        candles[timeframe] = tuple(
            HistoricalCandle(timestamp, 100.0, 102.0, 99.0, 101.0, 1000)
            for timestamp in timestamps
        )
        provenance[timeframe] = SourceProvenance(
            "KITE",
            f"KITE-HISTORICAL:NIFTY:{timeframe.value}:{DAY}",
            observed,
            "KITE-HISTORICAL-V1",
        )
    composition = compose_core_slice1_facts(
        instrument_registry=registry,
        canonical_instrument_id=member.canonical_identity,
        calendar_source=calendar,
        exchange="NSE",
        trading_date=DAY,
        observed_at=observed,
        run_created_at=observed,
        provider_candles=candles,
        provenance=provenance,
        evidence_store=LocalIntradayFactualEvidenceStore(tmp_path / "facts"),
    )
    schedule = composition.market_session.schedule
    assert schedule is not None
    boundary = DiscoveryRunBoundary(
        observed,
        schedule.session_id,
        f"DOMAIN-008:{schedule.session_id}:{observed.isoformat()}",
    )

    bundle = assemble_machine_fact_bundle(
        member=member,
        boundary=boundary,
        evidence=IntradayEvidenceBundle(composition),
        universe_identity=reconciliation.universe_identity,
        universe_version=reconciliation.universe_version,
        reconciliation_identity=reconciliation.publication_identity,
        reconciliation_version=reconciliation.publication_version,
    )

    assert sum(
        item.family is FactFamily.GOVERNED_COMPLETED_OHLCV
        for item in bundle.evidence
    ) == 4
    assert sum(
        item.family is FactFamily.CANDLE_COMPLETENESS_RECONCILIATION
        for item in bundle.evidence
    ) == 4
    assert all(
        item.completed_candle is True
        for item in bundle.evidence
        if item.timeframe is not None
    )
    assert all(
        item.family is not FactFamily.CURRENT_INCOMPLETE_CANDLE
        for item in bundle.evidence
    )
    assert all("256265" not in value for value in bundle.source_identities)


def test_future_governed_mcx_recovery_uses_same_generic_runtime(tmp_path: Path) -> None:
    universe, current = _publications()
    goldm = current.lookup("GOLDM")
    recovered = create_reconciliation_member(
        sponsor_label=goldm.sponsor_label,
        universe_member_identity=goldm.universe_member_identity,
        market_family=goldm.market_family,
        canonical_identity=goldm.canonical_identity,
        semantic_type=goldm.semantic_type,
        exchange=goldm.exchange,
        provider_symbol="GOLDM-GOVERNED-CONTRACT",
        provider_directive_identities=("GOLDM-GOVERNED-DIRECTIVE",),
        provider_record_identities=("GOLDM-GOVERNED-PROVIDER-RECORD",),
        derivative_contract_identities=("GOLDM-GOVERNED-CONTRACT",),
        dimensions=replace(
            goldm.dimensions,
            provider_mapping=Availability.AVAILABLE,
            provider_fact=Availability.AVAILABLE,
            active_derivative_binding=Availability.AVAILABLE,
            runtime_contract_availability=Availability.AVAILABLE,
            machine_fact_consumability=Availability.AVAILABLE,
        ),
        state=ReconciliationState.FULLY_RECONCILED_FOR_CURRENT_FACTUAL_PATH,
        reasons=current.lookup("NIFTY").reasons,
    )
    members = tuple(recovered if item.sponsor_label == "GOLDM" else item for item in current.members)
    successor = create_reconciliation_publication(
        publication_version=current.publication_version,
        universe_identity=current.universe_identity,
        universe_version=current.universe_version,
        universe_integrity_identity=current.universe_integrity_identity,
        catalogue_identity=current.catalogue_identity,
        catalogue_version=current.catalogue_version,
        catalogue_integrity_identity=current.catalogue_integrity_identity,
        provider_snapshot_identity=current.provider_snapshot_identity,
        provider_snapshot_integrity_identity=current.provider_snapshot_integrity_identity,
        commissioning_manifest_identity="SYNTHETIC-GOVERNED-MCX-RECOVERY",
        effective_boundary=current.effective_boundary,
        provider_evidence_boundary=current.provider_evidence_boundary,
        supersedes=current.integrity_identity,
        source_identities=("SYNTHETIC-GOVERNED-MCX-RECOVERY",),
        provenance=("CONTROLLED-WO-05-SYNTHETIC-PROOF",),
        members=members,
    )
    source = _Facts(successor)
    service = IntradayNativeDiscoveryService(
        universe=universe,
        reconciliation=successor,
        factual_source=source,
        store=NativeDiscoveryStore(tmp_path),
    )

    run = service.execute(BOUNDARY).run

    assert run.accounting.factually_evaluable == 94
    assert run.accounting.prerequisite_unavailable == 4
    assert run.lookup("GOLDM").machine_fact_bundle_identity is not None
    assert "GOLDM" in source.labels
