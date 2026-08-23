from __future__ import annotations

from datetime import datetime, timedelta
import inspect
from pathlib import Path

import pytest

from kronos.instrument.semantic_v2 import CanonicalSemanticKind
from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.discovery import (
    CandidateState,
    DiscoveryError,
    DiscoveryFailure,
    DiscoveryReason,
    ExecutionEligibility,
    FactFamily,
    FactRequirement,
    FactualEvaluability,
    MACHINE_FACT_GAP_AUDIT,
    MANDATORY_FACT_FAMILIES,
    METHODOLOGY_STATUS,
    MachineFactAuditStatus,
    MachineFactEvidence,
    MethodologyStatus,
    NATIVE_DISCOVERY_CONTRACT,
    NATIVE_DISCOVERY_MACHINE_FACT_BUNDLE,
    NATIVE_DISCOVERY_REASON,
    NATIVE_DISCOVERY_RESULT,
    NATIVE_DISCOVERY_VERSION,
    OPTIONAL_TELEMETRY_FACT_FAMILIES,
    STRUCTURAL_TIMEFRAMES,
    create_discovery_result,
    create_discovery_scope_run,
    create_machine_fact_bundle,
    discovery_run_bytes,
)
from kronos.intraday.discovery_persistence import NativeDiscoveryStore
from kronos.intraday.reconciliation import (
    Availability,
    AvailabilityDimensions,
    ReconciliationReason,
    ReconciliationState,
    create_reconciliation_member,
    create_reconciliation_publication,
)
from kronos.intraday.reconciliation_persistence import IntradayReconciliationStore
from kronos.intraday.universe import IntradayMarketFamily


ROOT = Path(__file__).resolve().parents[3]
RECONCILIATION_IDENTITY = (
    "KRONOS-INTRADAY-CANONICAL-RUNTIME-RECONCILIATION-V1"
)
OBSERVED = datetime.fromisoformat("2026-08-23T10:00:00+05:30")
SESSION = "DOMAIN-008-NSE-MCX-SESSION"
SESSION_BOUNDARY = "DOMAIN-008-SESSION-BOUNDARY-2026-08-23"


@pytest.fixture(scope="module")
def reconciliation():
    return IntradayReconciliationStore(ROOT / "data" / "intraday").load(
        publication_identity=RECONCILIATION_IDENTITY,
        publication_version="1.0.0",
    )


@pytest.fixture(scope="module")
def scope_run(reconciliation):
    return _scope_run(reconciliation)


def test_contract_identities_and_exact_governed_publications(
    reconciliation, scope_run
) -> None:
    assert (NATIVE_DISCOVERY_CONTRACT, NATIVE_DISCOVERY_VERSION) == (
        "KRONOS-INTRADAY-NATIVE-DISCOVERY-V0",
        "0.1.0",
    )
    assert NATIVE_DISCOVERY_RESULT == "KRONOS-INTRADAY-NATIVE-DISCOVERY-RESULT-V0"
    assert NATIVE_DISCOVERY_REASON == "KRONOS-INTRADAY-NATIVE-DISCOVERY-REASON-V0"
    assert scope_run.universe_identity == "KRONOS-INTRADAY-NATIVE-UNIVERSE-V1"
    assert scope_run.universe_version == "1.0.0"
    assert scope_run.reconciliation_identity == RECONCILIATION_IDENTITY
    assert scope_run.reconciliation_version == "1.0.0"
    assert scope_run.reconciliation_integrity_identity == reconciliation.integrity_identity


def test_current_run_accounts_all_98_as_93_plus_5(scope_run) -> None:
    accounting = scope_run.accounting
    assert accounting.universe_members == len(scope_run.results) == 98
    assert accounting.factually_evaluable == 93
    assert accounting.prerequisite_unavailable == 5
    assert accounting.evaluated == 0
    assert accounting.candidate_results == 0
    assert accounting.factual_failures == 0
    assert accounting.other_governed_unavailable == 0


def test_all_cash_and_indices_are_factually_evaluable(reconciliation, scope_run) -> None:
    expected = {
        item.sponsor_label
        for item in reconciliation.members
        if item.market_family
        in {IntradayMarketFamily.NSE_EQUITY, IntradayMarketFamily.NSE_INDEX}
    }
    actual = {
        item.sponsor_label
        for item in scope_run.results
        if item.evaluability is FactualEvaluability.FACTUALLY_EVALUABLE
    }
    assert len(expected) == 93
    assert actual == expected
    assert scope_run.lookup("NIFTY").canonical_identity == "NSE-INDEX-NIFTY"
    assert scope_run.lookup("BANKNIFTY").canonical_identity == "NSE-INDEX-BANKNIFTY"


@pytest.mark.parametrize(
    ("label", "reason"),
    (
        ("GOLDM", DiscoveryReason.ACTIVE_DERIVATIVE_BINDING_UNAVAILABLE),
        ("SILVERM", DiscoveryReason.ACTIVE_DERIVATIVE_BINDING_UNAVAILABLE),
        ("COPPER", DiscoveryReason.ACTIVE_DERIVATIVE_BINDING_UNAVAILABLE),
        ("NATGAS", DiscoveryReason.PROVIDER_CONTRACT_UNAVAILABLE),
        ("CRUDE", DiscoveryReason.PROVIDER_CONTRACT_UNAVAILABLE),
    ),
)
def test_exact_unavailable_member_reason_without_candidate_judgement(
    scope_run, label, reason
) -> None:
    item = scope_run.lookup(label)
    assert item.evaluability is FactualEvaluability.PREREQUISITE_UNAVAILABLE
    assert item.candidate_state is CandidateState.NOT_EVALUATED_DUE_TO_PREREQUISITE
    assert item.reasons == (reason,)
    assert item.machine_fact_bundle_identity is None
    assert item.execution_eligibility is ExecutionEligibility.NOT_ESTABLISHED


def test_unavailable_members_remain_present_and_are_not_candidate_rejections(
    scope_run,
) -> None:
    unavailable = tuple(
        item
        for item in scope_run.results
        if item.evaluability is FactualEvaluability.PREREQUISITE_UNAVAILABLE
    )
    assert len(unavailable) == 5
    assert all(item.candidate_state is not CandidateState.CANDIDATE_NOT_ADMITTED for item in unavailable)
    assert not hasattr(CandidateState, "NO_SETUP")
    assert not hasattr(scope_run.lookup("GOLDM"), "direction")


def test_structural_timeframes_are_exact_and_do_not_include_swing_frames() -> None:
    assert tuple(item.value for item in STRUCTURAL_TIMEFRAMES) == (
        "1D",
        "1H",
        "15M",
        "5M",
    )
    assert "1W" not in {item.value for item in STRUCTURAL_TIMEFRAMES}
    assert "4H" not in {item.value for item in STRUCTURAL_TIMEFRAMES}


def test_complete_mandatory_machine_fact_bundle_is_deterministic(reconciliation) -> None:
    first = _bundle(reconciliation)
    second = _bundle(reconciliation)
    assert first == second
    assert first.bundle_identity.startswith("INTRADAY-DISCOVERY-FACT-BUNDLE-")
    assert {item.family for item in first.evidence} == set(MANDATORY_FACT_FAMILIES)


def test_missing_mandatory_fact_fails_closed(reconciliation) -> None:
    evidence = _mandatory_evidence()[:-1]
    with pytest.raises(DiscoveryError) as raised:
        _bundle(reconciliation, evidence=evidence)
    assert raised.value.failure is DiscoveryFailure.MACHINE_FACT_BUNDLE_INCOMPLETE


def test_incomplete_candle_cannot_enter_structural_authority() -> None:
    with pytest.raises(DiscoveryError) as raised:
        MachineFactEvidence(
            family=FactFamily.GOVERNED_COMPLETED_OHLCV,
            requirement=FactRequirement.MANDATORY,
            evidence_identity="INCOMPLETE-5M",
            fact_version="1.0.0",
            observed_at=OBSERVED,
            timeframe=IntradayTimeframe.FIVE_MINUTES,
            completed_candle=False,
        )
    assert raised.value.failure is DiscoveryFailure.INCOMPLETE_CANDLE_NOT_AUTHORIZED


def test_current_incomplete_candle_is_observation_only() -> None:
    item = MachineFactEvidence(
        family=FactFamily.CURRENT_INCOMPLETE_CANDLE,
        requirement=FactRequirement.NOT_AUTHORIZED_FOR_CONSEQUENCE,
        evidence_identity="CURRENT-INCOMPLETE-5M",
        fact_version="1.0.0",
        observed_at=OBSERVED,
        timeframe=IntradayTimeframe.FIVE_MINUTES,
        completed_candle=False,
    )
    assert item.requirement is FactRequirement.NOT_AUTHORIZED_FOR_CONSEQUENCE


def test_optional_telemetry_absence_does_not_invalidate_bundle(reconciliation) -> None:
    bundle = _bundle(reconciliation)
    assert not ({item.family for item in bundle.evidence} & set(OPTIONAL_TELEMETRY_FACT_FAMILIES))


def test_stale_machine_evidence_fails_closed(reconciliation) -> None:
    stale = list(_mandatory_evidence())
    stale[0] = MachineFactEvidence(
        family=stale[0].family,
        requirement=stale[0].requirement,
        evidence_identity=stale[0].evidence_identity,
        fact_version=stale[0].fact_version,
        observed_at=OBSERVED - timedelta(minutes=1),
        timeframe=stale[0].timeframe,
        completed_candle=stale[0].completed_candle,
    )
    with pytest.raises(DiscoveryError) as raised:
        _bundle(reconciliation, evidence=tuple(stale))
    assert raised.value.failure is DiscoveryFailure.SOURCE_STALE


def test_candidate_and_run_identities_are_deterministic(reconciliation, scope_run) -> None:
    assert _scope_run(reconciliation) == scope_run
    bundle = _bundle(reconciliation)
    candidate = _candidate(scope_run, bundle.bundle_identity)
    assert candidate == _candidate(scope_run, bundle.bundle_identity)
    assert candidate.result_identity.startswith("INTRADAY-DISCOVERY-RESULT-")


def test_visual_validation_has_no_discovery_input_seam() -> None:
    parameters = inspect.signature(create_discovery_result).parameters
    assert "visual_answer" not in parameters
    assert "chart_analyst" not in parameters


@pytest.mark.parametrize(
    ("expected_field", "failure"),
    (
        ("universe", DiscoveryFailure.UNIVERSE_VERSION_UNAVAILABLE),
        ("reconciliation", DiscoveryFailure.RECONCILIATION_VERSION_UNAVAILABLE),
    ),
)
def test_stale_governing_versions_are_rejected(
    reconciliation, expected_field, failure
) -> None:
    arguments = _scope_arguments(reconciliation)
    arguments[f"expected_{expected_field}_version"] = "9.9.9"
    with pytest.raises(DiscoveryError) as raised:
        create_discovery_scope_run(**arguments)
    assert raised.value.failure is failure


def test_market_session_boundary_is_mandatory(reconciliation) -> None:
    arguments = _scope_arguments(reconciliation)
    arguments["market_session_boundary_identity"] = ""
    with pytest.raises(DiscoveryError) as raised:
        create_discovery_scope_run(**arguments)
    assert raised.value.failure is DiscoveryFailure.MARKET_SESSION_UNAVAILABLE


def test_immutable_persistence_restart_and_explicit_identity(scope_run, tmp_path) -> None:
    store = NativeDiscoveryStore(tmp_path.resolve())
    path = store.retain_run(scope_run)
    assert store.retain_run(scope_run) == path
    restarted = NativeDiscoveryStore(tmp_path.resolve())
    assert restarted.load_run(run_identity=scope_run.run_identity) == scope_run
    result = scope_run.lookup("RELIANCE")
    assert restarted.load_result(persistence_identity=result.persistence_identity) == result
    with pytest.raises(DiscoveryError) as raised:
        restarted.load_run(run_identity="INTRADAY-DISCOVERY-RUN-missing")
    assert raised.value.failure is DiscoveryFailure.PUBLICATION_UNAVAILABLE


def test_conflicting_duplicate_and_tamper_are_rejected(scope_run, tmp_path) -> None:
    store = NativeDiscoveryStore(tmp_path.resolve())
    path = store.retain_run(scope_run)
    path.write_bytes(discovery_run_bytes(scope_run).replace(b'"NIFTY"', b'"ALTER"', 1))
    with pytest.raises(DiscoveryError) as raised:
        store.retain_run(scope_run)
    assert raised.value.failure is DiscoveryFailure.PERSISTENCE_CONFLICT
    with pytest.raises(DiscoveryError) as raised:
        store.load_run(run_identity=scope_run.run_identity)
    assert raised.value.failure is DiscoveryFailure.INTEGRITY_INVALID


def test_later_run_preserves_historical_run(reconciliation, tmp_path) -> None:
    store = NativeDiscoveryStore(tmp_path.resolve())
    first = _scope_run(reconciliation)
    second = create_discovery_scope_run(
        **{
            **_scope_arguments(reconciliation),
            "observation_boundary": OBSERVED + timedelta(minutes=5),
        }
    )
    first_path = store.retain_run(first)
    first_bytes = first_path.read_bytes()
    second_path = store.retain_run(second)
    assert first_path != second_path
    assert first_path.read_bytes() == first_bytes
    assert store.load_run(run_identity=first.run_identity) == first


def test_future_recovered_mcx_becomes_evaluable_without_discovery_redesign(
    reconciliation,
) -> None:
    successor = _successor_reconciliation(reconciliation, recovered_label="GOLDM")
    run = _scope_run(successor)
    assert run.accounting.universe_members == 98
    assert run.accounting.factually_evaluable == 94
    assert run.accounting.prerequisite_unavailable == 4
    assert run.lookup("GOLDM").evaluability is FactualEvaluability.FACTUALLY_EVALUABLE


def test_future_successor_universe_is_not_capacity_bound(reconciliation) -> None:
    successor = _successor_reconciliation(reconciliation, extra_label="FINNIFTY")
    run = _scope_run(successor)
    assert run.accounting.universe_members == 99
    assert run.accounting.factually_evaluable == 94
    assert run.lookup("FINNIFTY").evaluability is FactualEvaluability.FACTUALLY_EVALUABLE
    assert len(reconciliation.members) == 98


def test_machine_fact_gap_audit_has_no_missing_mandatory_fact() -> None:
    audit = dict(MACHINE_FACT_GAP_AUDIT)
    assert all(audit[family] is MachineFactAuditStatus.AVAILABLE for family in MANDATORY_FACT_FAMILIES)
    assert MachineFactAuditStatus.MISSING_REQUIRED_FOR_DISCOVERY not in audit.values()


def test_methodology_remains_deferred_without_swing_defaults() -> None:
    status = dict(METHODOLOGY_STATUS)
    assert status["ATR"] is MethodologyStatus.DEFERRED_PENDING_EVIDENCE
    assert status["SMA20"] is MethodologyStatus.DEFERRED_PENDING_EVIDENCE
    assert status["SMA50"] is MethodologyStatus.DEFERRED_PENDING_EVIDENCE
    assert status["SMA200"] is MethodologyStatus.DEFERRED_PENDING_EVIDENCE
    assert status["VOLUME_THRESHOLD"] is MethodologyStatus.DEFERRED_PENDING_EVIDENCE
    assert status["PATH_CLEARANCE_ARITHMETIC"] is MethodologyStatus.DEFERRED_PENDING_EVIDENCE
    assert status["NORMALIZED_EXTENSION"] is MethodologyStatus.DEFERRED_PENDING_EVIDENCE


def test_all_results_leave_execution_eligibility_downstream(scope_run) -> None:
    assert all(
        item.execution_eligibility is ExecutionEligibility.NOT_ESTABLISHED
        for item in scope_run.results
    )


def test_discovery_source_has_no_swing_or_capacity_or_contract_selection() -> None:
    source = (ROOT / "src" / "kronos" / "intraday" / "discovery.py").read_text()
    prohibited = (
        "kronos.swing",
        "KR-370",
        "K1",
        "0.5 ATR",
        ">2 ATR",
        "nearest_expiry",
        "front_month",
        "EXPECTED_MEMBER_COUNT",
        "EXPECTED_EVALUABLE_COUNT",
    )
    assert all(value not in source for value in prohibited)


def _scope_run(reconciliation):
    return create_discovery_scope_run(**_scope_arguments(reconciliation))


def _scope_arguments(reconciliation):
    return {
        "reconciliation": reconciliation,
        "expected_universe_identity": reconciliation.universe_identity,
        "expected_universe_version": reconciliation.universe_version,
        "expected_reconciliation_identity": reconciliation.publication_identity,
        "expected_reconciliation_version": reconciliation.publication_version,
        "market_session_identity": SESSION,
        "market_session_boundary_identity": SESSION_BOUNDARY,
        "observation_boundary": OBSERVED,
    }


def _mandatory_evidence():
    values = [
        MachineFactEvidence(
            family=FactFamily.MARKET_SESSION_BOUNDARY,
            requirement=FactRequirement.MANDATORY,
            evidence_identity="DOMAIN-008-SESSION-FACT",
            fact_version="1.0.0",
            observed_at=OBSERVED,
            timeframe=None,
            completed_candle=None,
        )
    ]
    for family in (
        FactFamily.GOVERNED_COMPLETED_OHLCV,
        FactFamily.CANDLE_COMPLETENESS_RECONCILIATION,
    ):
        for timeframe in STRUCTURAL_TIMEFRAMES:
            values.append(
                MachineFactEvidence(
                    family=family,
                    requirement=FactRequirement.MANDATORY,
                    evidence_identity=f"{family.value}-{timeframe.value}",
                    fact_version="1.0.0",
                    observed_at=OBSERVED,
                    timeframe=timeframe,
                    completed_candle=True,
                )
            )
    return tuple(values)


def _bundle(reconciliation, evidence=None):
    return create_machine_fact_bundle(
        canonical_identity="RELIANCE",
        universe_identity=reconciliation.universe_identity,
        universe_version=reconciliation.universe_version,
        reconciliation_identity=reconciliation.publication_identity,
        reconciliation_version=reconciliation.publication_version,
        market_session_identity=SESSION,
        market_session_boundary_identity=SESSION_BOUNDARY,
        observation_boundary=OBSERVED,
        evidence=_mandatory_evidence() if evidence is None else evidence,
        source_identities=(
            reconciliation.integrity_identity,
            "INTRADAY-FACTUAL-EVIDENCE",
        ),
        provenance=("KRONOS-INTRADAY-WO-03",),
    )


def _candidate(scope_run, bundle_identity):
    reliance = scope_run.lookup("RELIANCE")
    return create_discovery_result(
        run_identity=scope_run.run_identity,
        universe_member_identity=reliance.universe_member_identity,
        sponsor_label=reliance.sponsor_label,
        canonical_identity=reliance.canonical_identity,
        observation_boundary=scope_run.observation_boundary,
        machine_fact_bundle_identity=bundle_identity,
        evaluability=FactualEvaluability.FACTUALLY_EVALUABLE,
        candidate_state=CandidateState.CANDIDATE_ADMITTED,
        reasons=(DiscoveryReason.FACTUAL_PATH_AVAILABLE,),
    )


def _successor_reconciliation(
    reconciliation, *, recovered_label=None, extra_label=None
):
    members = []
    for item in reconciliation.members:
        if item.sponsor_label != recovered_label:
            members.append(item)
            continue
        dimensions = AvailabilityDimensions(
            item.dimensions.product_membership,
            item.dimensions.canonical_identity,
            item.dimensions.canonical_semantics,
            Availability.AVAILABLE,
            Availability.AVAILABLE,
            item.dimensions.effective_geometry,
            Availability.AVAILABLE,
            Availability.AVAILABLE,
            Availability.AVAILABLE,
            Availability.AVAILABLE,
            Availability.AVAILABLE,
            Availability.NOT_ESTABLISHED,
        )
        members.append(
            create_reconciliation_member(
                sponsor_label=item.sponsor_label,
                universe_member_identity=item.universe_member_identity,
                market_family=item.market_family,
                canonical_identity=item.canonical_identity,
                semantic_type=item.semantic_type,
                exchange=item.exchange,
                provider_symbol=item.provider_symbol,
                provider_directive_identities=item.provider_directive_identities,
                provider_record_identities=item.provider_record_identities,
                derivative_contract_identities=item.derivative_contract_identities,
                dimensions=dimensions,
                state=ReconciliationState.FULLY_RECONCILED_FOR_CURRENT_FACTUAL_PATH,
                reasons=(
                    ReconciliationReason.PRODUCT_MEMBERSHIP_AVAILABLE,
                    ReconciliationReason.CANONICAL_IDENTITY_AVAILABLE,
                    ReconciliationReason.MACHINE_FACT_CONSUMABLE,
                    ReconciliationReason.EXECUTION_ELIGIBILITY_NOT_ESTABLISHED,
                ),
            )
        )
    if extra_label is not None:
        members.append(
            create_reconciliation_member(
                sponsor_label=extra_label,
                universe_member_identity=f"SYNTHETIC-MEMBER-{extra_label}",
                market_family=IntradayMarketFamily.NSE_INDEX,
                canonical_identity=f"SYNTHETIC-CANONICAL-{extra_label}",
                semantic_type=CanonicalSemanticKind.ANALYTICAL_SUBJECT,
                exchange="NSE",
                provider_symbol=extra_label,
                provider_directive_identities=(f"SYNTHETIC-DIRECTIVE-{extra_label}",),
                provider_record_identities=(f"SYNTHETIC-RECORD-{extra_label}",),
                derivative_contract_identities=(),
                dimensions=AvailabilityDimensions(
                    Availability.AVAILABLE,
                    Availability.AVAILABLE,
                    Availability.AVAILABLE,
                    Availability.AVAILABLE,
                    Availability.AVAILABLE,
                    Availability.NOT_APPLICABLE,
                    Availability.NOT_APPLICABLE,
                    Availability.NOT_APPLICABLE,
                    Availability.AVAILABLE,
                    Availability.NOT_APPLICABLE,
                    Availability.AVAILABLE,
                    Availability.NOT_ESTABLISHED,
                ),
                state=ReconciliationState.FULLY_RECONCILED_FOR_CURRENT_FACTUAL_PATH,
                reasons=(
                    ReconciliationReason.PRODUCT_MEMBERSHIP_AVAILABLE,
                    ReconciliationReason.CANONICAL_IDENTITY_AVAILABLE,
                    ReconciliationReason.MACHINE_FACT_CONSUMABLE,
                    ReconciliationReason.EXECUTION_ELIGIBILITY_NOT_ESTABLISHED,
                ),
            )
        )
    return create_reconciliation_publication(
        publication_version="2.0.0",
        universe_identity=reconciliation.universe_identity,
        universe_version="2.0.0",
        universe_integrity_identity="SYNTHETIC-SUCCESSOR-UNIVERSE",
        catalogue_identity=reconciliation.catalogue_identity,
        catalogue_version=reconciliation.catalogue_version,
        catalogue_integrity_identity=reconciliation.catalogue_integrity_identity,
        provider_snapshot_identity=reconciliation.provider_snapshot_identity,
        provider_snapshot_integrity_identity=reconciliation.provider_snapshot_integrity_identity,
        commissioning_manifest_identity=reconciliation.commissioning_manifest_identity,
        effective_boundary=reconciliation.effective_boundary,
        provider_evidence_boundary=reconciliation.provider_evidence_boundary,
        supersedes=reconciliation.integrity_identity,
        source_identities=reconciliation.source_identities + ("SYNTHETIC-SUCCESSOR",),
        provenance=reconciliation.provenance,
        members=tuple(members),
    )
