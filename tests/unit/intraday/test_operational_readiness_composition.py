from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from hashlib import sha256

import pytest

from kronos.application.intraday_wo16 import IntradayWo16PersistenceApplication
from kronos.instrument.runtime import create_canonical_instrument
from kronos.intraday.operational_readiness import (
    WoBClassificationBasis,
    WoBReviewClassification,
    WoBSourceBoundary,
    create_source_artifact_reference,
)
from kronos.intraday.operational_readiness_composition import (
    WoBAdaptedSource,
    WoBCompositionAnchor,
    WoBCompositionError,
    WoBCompositionRequest,
    adapt_domain_001_source,
    adapt_domain_008_source,
    adapt_probables_source,
    adapt_promotion_source,
    adapt_wo13_source,
    adapt_wo14_source,
    adapt_wo15_source,
    adapt_wo16_source,
    adapt_wo17_source,
    publish_operational_review,
    reconstruct_operational_review,
    restore_operational_review,
)
from kronos.intraday.operational_readiness_persistence import WoBStore
from kronos.intraday.probables_v2_persistence import (
    create_current_probables_v2_pointer,
)
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo14 import Wo14ObservationState
from kronos.intraday.wo15 import Wo15TimingState
from kronos.intraday.wo16 import Wo16SponsorDecision
from kronos.intraday.wo16_persistence import Wo16Store
from kronos.intraday.wo17_lifecycle import create_wo17_lifecycle_machine
from kronos.validation.kr370 import Kr370AnalyticalClassification

from .test_probables_v2 import _opening_inputs, _run
from .test_wo13_contracts import _artifacts, _mcx_artifacts
from .test_wo16_application import _request as _wo16_request
from .test_wo16_contracts import _chain
from .test_wo17_lifecycle import _active
from .test_wo17_persistence import (
    _application as _wo17_application,
    _paper_closed,
    _request as _wo17_request,
)


def _anchor() -> WoBCompositionAnchor:
    return WoBCompositionAnchor(
        candidate_identity="INTRADAY-PROBABLE-TEST",
        opportunity_identity="INTRADAY-OPPORTUNITY-TEST",
        analysis_run_identity="INTRADAY-PROBABLES-RUN-TEST",
        canonical_subject_identity="NSE-EQ-TEST",
        market_family=IntradayMarketFamily.NSE_EQUITY,
        canonical_instrument_identity="NSE-EQ-TEST",
        active_contract_identity=None,
    )


def _source(
    boundary: WoBSourceBoundary,
    *,
    basis: WoBClassificationBasis = WoBClassificationBasis.CURRENT_VALID_SOURCE,
    state: str = "AVAILABLE",
    reason: str | None = None,
    anchor: WoBCompositionAnchor | None = None,
    minute: int = 0,
) -> WoBAdaptedSource:
    anchor = anchor or _anchor()
    reference = create_source_artifact_reference(
        source_boundary=boundary,
        artifact_identity=f"ARTIFACT-{boundary.value}-{minute}",
        artifact_schema_identity=f"SCHEMA-{boundary.value}",
        artifact_schema_version="1.0.0",
        source_policy_identity=f"POLICY-{boundary.value}",
        source_policy_version="1.0.0",
        source_integrity_identity=f"INTEGRITY-{boundary.value}-{minute}",
        candidate_identity=anchor.candidate_identity,
        analysis_run_identity=anchor.analysis_run_identity,
        canonical_instrument_identity=anchor.canonical_instrument_identity,
        active_contract_identity=anchor.active_contract_identity,
        exact_source_state=state,
        exact_source_reason=reason,
        bounded_diagnostic=None,
        observed_at=_boundary() + timedelta(minutes=minute),
        current_at_review_boundary=True,
        superseded=False,
        currentness_required=True,
    )
    return WoBAdaptedSource(reference, basis)


def _boundary():  # type: ignore[no-untyped-def]
    return _opening_inputs()[0].analysis_boundary


def _foundation(anchor: WoBCompositionAnchor | None = None):  # type: ignore[no-untyped-def]
    anchor = anchor or _anchor()
    return (
        _source(WoBSourceBoundary.DOMAIN_001_INSTRUMENT, anchor=anchor),
        _source(WoBSourceBoundary.DOMAIN_008_SESSION, anchor=anchor),
        _source(
            WoBSourceBoundary.PROBABLES,
            anchor=anchor,
            state="LONG_PROBABLE",
        ),
    )


def _composition(
    *sources: WoBAdaptedSource,
    anchor: WoBCompositionAnchor | None = None,
    minute: int = 10,
    required: tuple[WoBSourceBoundary, ...] = (),
) -> WoBCompositionRequest:
    return WoBCompositionRequest(
        anchor=anchor or _anchor(),
        review_boundary=_boundary() + timedelta(minutes=minute),
        created_at=_boundary() + timedelta(minutes=minute, seconds=1),
        sources=sources or _foundation(anchor),
        required_missing_boundaries=required,
        provenance=("ADR-0029", "WO-B2-TEST"),
    )


def _items(snapshot):  # type: ignore[no-untyped-def]
    return {item.source_boundary: item for item in snapshot.review_items}


def test_candidate_only_composition_preserves_expected_absence_and_next_stage() -> None:
    snapshot = reconstruct_operational_review(_composition(*_foundation()))
    items = _items(snapshot)
    assert items[WoBSourceBoundary.PROBABLES].review_classification is WoBReviewClassification.AVAILABLE
    assert items[WoBSourceBoundary.ANALYTICAL_PROMOTION].review_classification is WoBReviewClassification.NOT_REACHED
    assert items[WoBSourceBoundary.ANALYTICAL_PROMOTION].next_governed_stage == "ANALYTICAL_PROMOTION"
    assert items[WoBSourceBoundary.WO17_POSITION_MONITORING].exact_source_state == "NOT_REACHED"
    assert not hasattr(snapshot, "trade_ready")


@pytest.mark.parametrize(
    "last_boundary",
    (
        WoBSourceBoundary.ANALYTICAL_PROMOTION,
        WoBSourceBoundary.WO13_TRADE_PLAN,
        WoBSourceBoundary.WO14_RISK_OBSERVATION,
        WoBSourceBoundary.WO15_TIMING_HANDOFF,
        WoBSourceBoundary.WO16_SPONSOR_LIFECYCLE,
        WoBSourceBoundary.WO17_POSITION_MONITORING,
    ),
)
def test_each_reached_stage_composes_without_fabricating_later_stages(
    last_boundary,
) -> None:  # type: ignore[no-untyped-def]
    stages = (
        _source(WoBSourceBoundary.ANALYTICAL_PROMOTION, state="BUY_NOW"),
        _source(WoBSourceBoundary.WO13_TRADE_PLAN, state="GEOMETRY_COMPLETE"),
        _source(WoBSourceBoundary.WO14_RISK_OBSERVATION, state="RISK_OBSERVED"),
        _source(WoBSourceBoundary.WO15_TIMING_HANDOFF, state="TIMING_QUALIFIED"),
        _source(
            WoBSourceBoundary.WO16_SPONSOR_LIFECYCLE,
            state="PAPER.PENDING_POSITION_EVIDENCE",
        ),
        _source(
            WoBSourceBoundary.WO17_POSITION_MONITORING,
            state="PAPER_ACTIVE",
        ),
    )
    index = next(
        index
        for index, item in enumerate(stages)
        if item.reference.source_boundary is last_boundary
    )
    snapshot = reconstruct_operational_review(
        _composition(*_foundation(), *stages[: index + 1])
    )
    items = _items(snapshot)
    assert items[last_boundary].review_classification is WoBReviewClassification.AVAILABLE
    assert all(
        item.review_classification is WoBReviewClassification.NOT_REACHED
        for item in snapshot.review_items
        if item.source_boundary in {
            source.reference.source_boundary for source in stages[index + 1 :]
        }
    )


@pytest.mark.parametrize(
    ("basis", "expected"),
    (
        (WoBClassificationBasis.CURRENT_VALID_SOURCE, WoBReviewClassification.AVAILABLE),
        (WoBClassificationBasis.SOURCE_WAITING, WoBReviewClassification.WAITING),
        (WoBClassificationBasis.SOURCE_BLOCKED, WoBReviewClassification.BLOCKED),
        (WoBClassificationBasis.SOURCE_UNAVAILABLE, WoBReviewClassification.UNAVAILABLE),
        (WoBClassificationBasis.SOURCE_TERMINAL, WoBReviewClassification.TERMINAL),
    ),
)
def test_exact_source_classifications_are_not_collapsed(basis, expected) -> None:  # type: ignore[no-untyped-def]
    source = _source(
        WoBSourceBoundary.ANALYTICAL_PROMOTION,
        basis=basis,
        state="SOURCE_OWNED_STATE",
        reason="SOURCE_OWNED_REASON",
    )
    snapshot = reconstruct_operational_review(
        _composition(*_foundation(), source)
    )
    item = _items(snapshot)[WoBSourceBoundary.ANALYTICAL_PROMOTION]
    assert item.review_classification is expected
    assert item.exact_source_state == "SOURCE_OWNED_STATE"
    assert item.exact_source_reason == "SOURCE_OWNED_REASON"


def test_required_missing_source_is_unavailable_not_not_reached() -> None:
    snapshot = reconstruct_operational_review(_composition(
        *_foundation(),
        required=(WoBSourceBoundary.ANALYTICAL_PROMOTION,),
    ))
    item = _items(snapshot)[WoBSourceBoundary.ANALYTICAL_PROMOTION]
    assert item.review_classification is WoBReviewClassification.UNAVAILABLE
    assert item.source_reference_identity is None
    assert item.exact_source_reason == "WO_B_REQUIRED_SOURCE_MISSING"


def test_multi_domain_risk_and_timing_truths_remain_independent() -> None:
    promotion = _source(WoBSourceBoundary.ANALYTICAL_PROMOTION, state="BUY_NOW")
    plan = _source(WoBSourceBoundary.WO13_TRADE_PLAN, state="GEOMETRY_COMPLETE")
    risk = _source(
        WoBSourceBoundary.WO14_RISK_OBSERVATION,
        basis=WoBClassificationBasis.SOURCE_UNAVAILABLE,
        state="RISK_UNAVAILABLE",
        reason="CAPITAL_REFERENCE_UNAVAILABLE",
    )
    timing = _source(
        WoBSourceBoundary.WO15_TIMING_HANDOFF,
        state="TIMING_QUALIFIED",
    )
    snapshot = reconstruct_operational_review(
        _composition(*_foundation(), promotion, plan, risk, timing)
    )
    items = _items(snapshot)
    assert items[WoBSourceBoundary.WO14_RISK_OBSERVATION].review_classification is WoBReviewClassification.UNAVAILABLE
    assert items[WoBSourceBoundary.WO15_TIMING_HANDOFF].review_classification is WoBReviewClassification.AVAILABLE
    assert items[WoBSourceBoundary.WO16_SPONSOR_LIFECYCLE].review_classification is WoBReviewClassification.NOT_REACHED


@pytest.mark.parametrize("field", ("candidate", "run", "instrument", "contract"))
def test_cross_source_identity_and_contract_mismatches_fail_closed(field) -> None:  # type: ignore[no-untyped-def]
    anchor = _anchor()
    values = {
        "candidate_identity": anchor.candidate_identity,
        "opportunity_identity": anchor.opportunity_identity,
        "analysis_run_identity": anchor.analysis_run_identity,
        "canonical_subject_identity": anchor.canonical_subject_identity,
        "market_family": anchor.market_family,
        "canonical_instrument_identity": anchor.canonical_instrument_identity,
        "active_contract_identity": anchor.active_contract_identity,
    }
    if field == "candidate":
        values["candidate_identity"] = "FOREIGN-CANDIDATE"
    elif field == "run":
        values["analysis_run_identity"] = "FOREIGN-RUN"
    elif field == "instrument":
        values["canonical_instrument_identity"] = "FOREIGN-INSTRUMENT"
    else:
        values["market_family"] = IntradayMarketFamily.MCX
        values["active_contract_identity"] = "FOREIGN-CONTRACT"
    foreign = WoBCompositionAnchor(**values)
    with pytest.raises(WoBCompositionError, match="WO_B_CROSS_SOURCE_BINDING_MISMATCH"):
        reconstruct_operational_review(_composition(*_foundation(), anchor=foreign))


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("current_at_review_boundary", False),
        ("superseded", True),
        ("reference_integrity", "CORRUPT-INTEGRITY"),
        ("source_policy_identity", "FOREIGN-POLICY"),
    ),
)
def test_stale_superseded_corrupt_and_foreign_policy_sources_fail_closed(
    field, value
) -> None:  # type: ignore[no-untyped-def]
    source = _source(WoBSourceBoundary.ANALYTICAL_PROMOTION)
    object.__setattr__(source.reference, field, value)
    with pytest.raises(WoBCompositionError, match="WO_B_ADAPTED_SOURCE_INVALID"):
        _composition(*_foundation(), source)


def test_stage_lineage_and_terminal_boundaries_fail_closed() -> None:
    with pytest.raises(WoBCompositionError, match="WO_B_SOURCE_STAGE_LINEAGE_INCOMPLETE"):
        reconstruct_operational_review(_composition(
            *_foundation(),
            _source(WoBSourceBoundary.WO13_TRADE_PLAN),
        ))
    terminal = _source(
        WoBSourceBoundary.ANALYTICAL_PROMOTION,
        basis=WoBClassificationBasis.SOURCE_TERMINAL,
        state="NO_SETUP",
    )
    plan = _source(WoBSourceBoundary.WO13_TRADE_PLAN)
    with pytest.raises(WoBCompositionError, match="WO_B_SOURCE_AFTER_TERMINAL_PROHIBITED"):
        reconstruct_operational_review(_composition(*_foundation(), terminal, plan))


def test_publish_replay_newer_projection_and_failure_preservation(tmp_path) -> None:
    store = WoBStore((tmp_path / "wo-b").resolve())
    first_request = _composition(*_foundation())
    first = publish_operational_review(first_request, store=store)
    before = _fingerprints(store.root)
    replay = publish_operational_review(first_request, store=store)
    assert replay.replayed and replay.pointer == first.pointer
    assert _fingerprints(store.root) == before

    newer = publish_operational_review(
        _composition(*_foundation(), minute=20), store=store
    )
    assert newer.pointer.review_boundary > first.pointer.review_boundary
    current = restore_operational_review(_anchor().candidate_identity, store=store)
    assert current.pointer == newer.pointer

    broken = _composition(
        *_foundation(),
        _source(WoBSourceBoundary.WO13_TRADE_PLAN),
        minute=30,
    )
    with pytest.raises(WoBCompositionError):
        publish_operational_review(broken, store=store)
    restored = restore_operational_review(_anchor().candidate_identity, store=store)
    assert restored.pointer == newer.pointer
    assert restored.latest_failure is not None


def test_real_probables_and_domain_adapters_bind_current_source_contracts() -> None:
    selection, _, _, _, mapping = _opening_inputs()
    run = _run(mapping)
    result = run.results[0]
    pointer = create_current_probables_v2_pointer(run)
    anchor, probable = adapt_probables_source(
        run=run,
        result=result,
        current_pointer=pointer,
        canonical_instrument_identity=result.canonical_subject_identity,
        active_contract_identity=None,
    )
    instrument = create_canonical_instrument(
        canonical_instrument_id=anchor.canonical_instrument_identity,
        exchange="NSE",
        segment="EQ",
        instrument_type="EQ",
        canonical_tick_size=None,
        canonical_lot_size=None,
        canonical_source_identity="DOMAIN-001-TEST",
        source_boundary=selection.analysis_boundary - timedelta(days=1),
        valid_through=selection.analysis_boundary + timedelta(days=1),
    )
    identity = adapt_domain_001_source(
        anchor=anchor,
        instrument=instrument,
        review_boundary=selection.analysis_boundary,
    )
    assert probable.reference.artifact_identity == result.result_identity
    assert probable.reference.analysis_run_identity == run.run_identity
    assert identity.reference.source_integrity_identity == instrument.integrity_identity
    object.__setattr__(pointer, "run_identity", "INTRADAY-PROBABLES-V2-RUN-FOREIGN")
    with pytest.raises(WoBCompositionError, match="WO_B_PROBABLES_POINTER_INVALID"):
        adapt_probables_source(
            run=run,
            result=result,
            current_pointer=pointer,
            canonical_instrument_identity=result.canonical_subject_identity,
            active_contract_identity=None,
        )


@pytest.mark.parametrize(
    ("satisfied", "classification", "basis"),
    (
        (4, Kr370AnalyticalClassification.BUY_NOW, WoBClassificationBasis.CURRENT_VALID_SOURCE),
        (3, Kr370AnalyticalClassification.BUY_READY, WoBClassificationBasis.SOURCE_BLOCKED),
        (2, Kr370AnalyticalClassification.POTENTIAL_BUY_SETUP, WoBClassificationBasis.SOURCE_BLOCKED),
        (1, Kr370AnalyticalClassification.NO_SETUP, WoBClassificationBasis.SOURCE_BLOCKED),
    ),
)
def test_real_promotion_adapter_preserves_classification_and_eligibility(
    tmp_path, satisfied, classification, basis
) -> None:  # type: ignore[no-untyped-def]
    pointer, request, _, result, _, _, _ = _artifacts(
        tmp_path / str(satisfied), satisfied=satisfied
    )
    handoff = request.handoff
    anchor = WoBCompositionAnchor(
        candidate_identity=handoff.probable_result_identity,
        opportunity_identity=handoff.wo11_member_identity,
        analysis_run_identity=handoff.probables_run_identity,
        canonical_subject_identity=handoff.canonical_subject_identity,
        market_family=handoff.market_family,
        canonical_instrument_identity="NSE-EQ-PROMOTION-TEST",
        active_contract_identity=None,
    )
    source = adapt_promotion_source(
        anchor=anchor,
        handoff=handoff,
        result=result,
        current_pointer=pointer,
    )
    assert source.reference.exact_source_state == classification.value
    assert source.classification_basis is basis


def test_real_wo13_through_wo16_adapters_preserve_owner_states(tmp_path) -> None:
    chain = _chain(tmp_path / "chain")
    plan = chain["plan"]
    anchor = WoBCompositionAnchor(
        candidate_identity="CHAIN-CANDIDATE",
        opportunity_identity="CHAIN-OPPORTUNITY",
        analysis_run_identity="CHAIN-RUN",
        canonical_subject_identity=plan.canonical_subject_identity,
        market_family=plan.market_family,
        canonical_instrument_identity=plan.instrument_identity,
        active_contract_identity=plan.actual_contract_identity,
    )
    plan_source = adapt_wo13_source(
        anchor=anchor, plan=plan, current_pointer=chain["pointer13"]
    )
    risk_source = adapt_wo14_source(
        anchor=anchor,
        observation=chain["observation14"],
        current_pointer=chain["pointer14"],
        trade_plan=plan,
    )
    timing_source = adapt_wo15_source(
        anchor=anchor,
        current_pointer=chain["pointer15"],
        handoff=chain["handoff15"],
    )
    session_source = adapt_domain_008_source(anchor=anchor, fact=chain["fact"])
    store = Wo16Store((tmp_path / "wo16").resolve())
    execution = IntradayWo16PersistenceApplication(store=store).execute(
        _wo16_request(chain, Wo16SponsorDecision.PAPER)
    )
    restored = store.restore_current(plan.canonical_subject_identity)
    assert restored is not None
    sponsor_source = adapt_wo16_source(
        anchor=anchor,
        snapshot=restored.snapshot,
        decision=restored.decision,
        admission=restored.admission,
        current_pointer=restored.pointer,
    )
    assert plan_source.reference.exact_source_state == "GEOMETRY_COMPLETE"
    assert risk_source.reference.exact_source_state in {
        state.value for state in Wo14ObservationState
    }
    assert timing_source.reference.exact_source_state == Wo15TimingState.TIMING_QUALIFIED.value
    assert session_source.reference.exact_source_state == "OPEN"
    assert sponsor_source.reference.exact_source_state == "PAPER.PENDING_POSITION_EVIDENCE"
    assert execution.execution.admission == restored.admission
    with pytest.raises(WoBCompositionError, match="WO_B_WO15_HANDOFF_REQUIRED"):
        adapt_wo15_source(
            anchor=anchor,
            current_pointer=chain["pointer15"],
        )


def test_real_wo17_adapter_preserves_position_and_monitoring_truth(tmp_path) -> None:
    _, position = _active(tmp_path / "source")
    lifecycle = create_wo17_lifecycle_machine(position)
    store, application = _wo17_application(tmp_path / "store")
    application.execute(_wo17_request(position, lifecycle=lifecycle))
    restored = store.restore_current(
        position.upstream_snapshot.lineage.canonical_subject_identity
    )
    assert restored is not None
    lineage = position.upstream_snapshot.lineage
    anchor = WoBCompositionAnchor(
        candidate_identity="WO17-CANDIDATE",
        opportunity_identity="WO17-OPPORTUNITY",
        analysis_run_identity="WO17-RUN",
        canonical_subject_identity=lineage.canonical_subject_identity,
        market_family=lineage.market_family,
        canonical_instrument_identity=lineage.instrument_identity,
        active_contract_identity=lineage.actual_contract_identity,
    )
    source = adapt_wo17_source(
        anchor=anchor,
        current_pointer=restored.pointer,
        position=restored.position,
        lifecycle=restored.lifecycle,
    )
    assert source.reference.exact_source_state == position.state.value
    assert source.reference.exact_source_reason == lifecycle.monitoring_availability.value
    assert source.classification_basis is WoBClassificationBasis.CURRENT_VALID_SOURCE


def test_real_wo17_closed_position_is_authoritative_terminal_state(tmp_path) -> None:
    position, lifecycle, closure = _paper_closed(tmp_path / "source")
    store, application = _wo17_application(tmp_path / "store")
    application.execute(
        _wo17_request(
            position,
            lifecycle=lifecycle,
            closure=closure,
            at=closure.last_transition_at + timedelta(seconds=1),
        )
    )
    restored = store.restore_current(
        position.upstream_snapshot.lineage.canonical_subject_identity
    )
    assert restored is not None
    lineage = position.upstream_snapshot.lineage
    anchor = WoBCompositionAnchor(
        candidate_identity="WO17-CLOSED-CANDIDATE",
        opportunity_identity="WO17-CLOSED-OPPORTUNITY",
        analysis_run_identity="WO17-CLOSED-RUN",
        canonical_subject_identity=lineage.canonical_subject_identity,
        market_family=lineage.market_family,
        canonical_instrument_identity=lineage.instrument_identity,
        active_contract_identity=lineage.actual_contract_identity,
    )
    source = adapt_wo17_source(
        anchor=anchor,
        current_pointer=restored.pointer,
        position=restored.position,
        lifecycle=restored.lifecycle,
    )
    assert source.classification_basis is WoBClassificationBasis.SOURCE_TERMINAL
    assert source.reference.bounded_diagnostic == "PAPER_CLOSED"


def test_mcx_domain_001_adapter_binds_actual_contract_without_roll_bridge(tmp_path) -> None:
    values = _mcx_artifacts(tmp_path)
    active = values[7].active_derivative_binding
    assert active is not None
    anchor = WoBCompositionAnchor(
        candidate_identity="MCX-CANDIDATE",
        opportunity_identity="MCX-OPPORTUNITY",
        analysis_run_identity="MCX-RUN",
        canonical_subject_identity=active.canonical_subject_id,
        market_family=IntradayMarketFamily.MCX,
        canonical_instrument_identity=active.provider_symbol,
        active_contract_identity=active.active_binding.derivative_contract_id,
    )
    source = adapt_domain_001_source(
        anchor=anchor,
        active_derivative=active,
        review_boundary=active.observation_boundary,
    )
    assert source.reference.active_contract_identity == active.active_binding.derivative_contract_id
    assert source.reference.artifact_identity == active.binding_identity
    foreign = replace(anchor, active_contract_identity="MCX-FOREIGN-CONTRACT")
    with pytest.raises(WoBCompositionError, match="WO_B_DOMAIN_001_BINDING_MISMATCH"):
        adapt_domain_001_source(
            anchor=foreign,
            active_derivative=active,
            review_boundary=active.observation_boundary,
        )


def test_authority_and_security_boundaries_are_structurally_absent() -> None:
    request = _composition(*_foundation())
    assert not hasattr(request, "provider")
    assert not hasattr(request, "broker")
    assert not hasattr(request, "sponsor_decision")
    assert not hasattr(request, "trade_ready")
    assert not hasattr(request, "score")


def _fingerprints(root):  # type: ignore[no-untyped-def]
    return {
        str(path.relative_to(root)): sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }
