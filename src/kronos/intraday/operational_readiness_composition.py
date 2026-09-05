"""Deterministic WO-B2 composition over already-published producer facts.

The module validates immutable producer artifacts supplied by product-local
readers.  It never invokes a producer, obtains Provider data, or mutates an
upstream domain.  Pure reconstruction is kept separate from the explicit
WO-B current-projection publication operation.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from hashlib import sha256
import json
from typing import Iterable, Mapping

from kronos.instrument.active_derivative import ActiveDerivativeBindingArtifact
from kronos.instrument.runtime import CanonicalInstrument
from kronos.instrument.semantic_v2 import (
    AnalyticalSubjectV2,
    DirectListedInstrumentV2,
    InstrumentSemanticPublicationV2,
)
from kronos.intraday.operational_readiness import (
    WoBClassificationBasis,
    WoBContractError,
    WoBOperationalReviewSnapshot,
    WoBSourceArtifactReference,
    WoBSourceBoundary,
    create_operational_review_snapshot,
    create_review_item,
    create_source_artifact_reference,
)
from kronos.intraday.operational_readiness_persistence import (
    CurrentWoBPointer,
    RestoredWoBState,
    WoBFailureStage,
    WoBPersistenceError,
    WoBReviewFailure,
    WoBStore,
    create_wo_b_failure,
    wo_b_exception_reason,
)
from kronos.intraday.probables import ProbableState
from kronos.intraday.probables_v2 import ProbableMemberResultV2, ProbablesRunV2
from kronos.intraday.probables_v2_persistence import CurrentProbablesV2Pointer
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo12 import Wo12Handoff
from kronos.intraday.wo12_v2 import CurrentWo12PointerV2, Wo12ResultV2
from kronos.intraday.wo13 import (
    CurrentWo13Pointer,
    Wo13GeometryAvailability,
    Wo13TradePlan,
)
from kronos.intraday.wo14 import (
    CurrentWo14Pointer,
    Wo14ObservationState,
    Wo14RiskObservation,
)
from kronos.intraday.wo15 import Wo15TimingState
from kronos.intraday.wo15_handoff import Wo15TimingHandoff
from kronos.intraday.wo15_persistence import CurrentWo15Pointer
from kronos.intraday.wo16 import (
    Wo16LifecycleAdmissionDisposition,
    Wo16LifecycleAdmissionRecord,
    Wo16SponsorDecision,
    Wo16SponsorDecisionRecord,
    Wo16SponsorDecisionSnapshot,
)
from kronos.intraday.wo16_persistence import CurrentWo16Pointer
from kronos.intraday.wo17_closure import Wo17ClosureState
from kronos.intraday.wo17_lifecycle import Wo17LifecycleMachine
from kronos.intraday.wo17_persistence import CurrentWo17Pointer
from kronos.intraday.wo17_position import Wo17PositionMachine, Wo17PositionState
from kronos.market.schedule import MarketSessionFact, MarketSessionState
from kronos.validation.kr370 import Kr370AnalyticalClassification


class WoBCompositionError(WoBContractError):
    """Sanitized composition or source-binding rejection."""


@dataclass(frozen=True, slots=True)
class WoBCompositionAnchor:
    candidate_identity: str
    opportunity_identity: str | None
    analysis_run_identity: str
    canonical_subject_identity: str
    market_family: IntradayMarketFamily
    canonical_instrument_identity: str
    active_contract_identity: str | None

    def __post_init__(self) -> None:
        mcx = self.market_family is IntradayMarketFamily.MCX
        if (
            not all(
                _text(value)
                for value in (
                    self.candidate_identity,
                    self.analysis_run_identity,
                    self.canonical_subject_identity,
                    self.canonical_instrument_identity,
                )
            )
            or not _optional_text(self.opportunity_identity)
            or type(self.market_family) is not IntradayMarketFamily
            or mcx != (self.active_contract_identity is not None)
            or not _optional_text(self.active_contract_identity)
        ):
            raise WoBCompositionError("WO_B_COMPOSITION_ANCHOR_INVALID")


@dataclass(frozen=True, slots=True)
class WoBAdaptedSource:
    reference: WoBSourceArtifactReference
    classification_basis: WoBClassificationBasis

    def __post_init__(self) -> None:
        if type(self.reference) is WoBSourceArtifactReference:
            _revalidate(
                self.reference,
                WoBSourceArtifactReference,
                "WO_B_SOURCE_REFERENCE_INVALID",
            )
        if (
            type(self.reference) is not WoBSourceArtifactReference
            or type(self.classification_basis) is not WoBClassificationBasis
            or self.classification_basis
            is WoBClassificationBasis.EXPECTED_DOWNSTREAM_ABSENCE
        ):
            raise WoBCompositionError("WO_B_ADAPTED_SOURCE_INVALID")


@dataclass(frozen=True, slots=True)
class WoBCompositionRequest:
    anchor: WoBCompositionAnchor
    review_boundary: datetime
    created_at: datetime
    sources: tuple[WoBAdaptedSource, ...]
    required_missing_boundaries: tuple[WoBSourceBoundary, ...] = ()
    provenance: tuple[str, ...] = ("ADR-0029", "WO-B2")

    def __post_init__(self) -> None:
        if type(self.anchor) is WoBCompositionAnchor:
            _revalidate(
                self.anchor,
                WoBCompositionAnchor,
                "WO_B_COMPOSITION_ANCHOR_INVALID",
            )
        for item in self.sources:
            if type(item) is WoBAdaptedSource:
                _revalidate(
                    item,
                    WoBAdaptedSource,
                    "WO_B_ADAPTED_SOURCE_INVALID",
                )
        boundaries = tuple(item.reference.source_boundary for item in self.sources)
        if (
            type(self.anchor) is not WoBCompositionAnchor
            or not _aware(self.review_boundary)
            or not _aware(self.created_at)
            or self.created_at < self.review_boundary
            or any(type(item) is not WoBAdaptedSource for item in self.sources)
            or len(boundaries) != len(set(boundaries))
            or any(type(item) is not WoBSourceBoundary for item in self.required_missing_boundaries)
            or len(self.required_missing_boundaries)
            != len(set(self.required_missing_boundaries))
            or set(boundaries).intersection(self.required_missing_boundaries)
            or not self.provenance
            or not all(_text(item) for item in self.provenance)
        ):
            raise WoBCompositionError("WO_B_COMPOSITION_REQUEST_INVALID")


@dataclass(frozen=True, slots=True)
class WoBPublishedComposition:
    snapshot: WoBOperationalReviewSnapshot
    pointer: CurrentWoBPointer
    replayed: bool


_REVIEW_ORDER = (
    WoBSourceBoundary.DOMAIN_001_INSTRUMENT,
    WoBSourceBoundary.DOMAIN_008_SESSION,
    WoBSourceBoundary.PROBABLES,
    WoBSourceBoundary.ANALYTICAL_PROMOTION,
    WoBSourceBoundary.WO13_TRADE_PLAN,
    WoBSourceBoundary.WO14_RISK_OBSERVATION,
    WoBSourceBoundary.WO15_TIMING_HANDOFF,
    WoBSourceBoundary.WO16_SPONSOR_LIFECYCLE,
    WoBSourceBoundary.WO17_POSITION_MONITORING,
)

_PIPELINE_ORDER = _REVIEW_ORDER[2:]


def adapt_probables_source(
    *,
    run: ProbablesRunV2,
    result: ProbableMemberResultV2,
    current_pointer: CurrentProbablesV2Pointer,
    canonical_instrument_identity: str,
    active_contract_identity: str | None,
    opportunity_identity: str | None = None,
) -> tuple[WoBCompositionAnchor, WoBAdaptedSource]:
    _revalidate(run, ProbablesRunV2, "WO_B_PROBABLES_SOURCE_INVALID")
    _revalidate(result, ProbableMemberResultV2, "WO_B_PROBABLES_SOURCE_INVALID")
    _revalidate(
        current_pointer,
        CurrentProbablesV2Pointer,
        "WO_B_PROBABLES_POINTER_INVALID",
    )
    retained = next(
        (item for item in run.results if item.result_identity == result.result_identity),
        None,
    )
    if (
        retained != result
        or current_pointer.run_identity != run.run_identity
        or current_pointer.source_discovery_run_identity
        != run.source_discovery_run_identity
        or current_pointer.analysis_boundary != run.analysis_boundary
        or result.source_discovery_run_identity != run.source_discovery_run_identity
        or result.market_session_identity != run.market_session_identity
        or result.analysis_boundary != run.analysis_boundary
    ):
        raise WoBCompositionError("WO_B_PROBABLES_CURRENT_BINDING_MISMATCH")
    family = _market_family_for_subject(result.canonical_subject_identity)
    contract = active_contract_identity if family is IntradayMarketFamily.MCX else None
    if family is not IntradayMarketFamily.MCX and active_contract_identity is not None:
        raise WoBCompositionError("WO_B_NSE_CONTRACT_LINEAGE_PROHIBITED")
    anchor = WoBCompositionAnchor(
        candidate_identity=result.result_identity,
        opportunity_identity=opportunity_identity,
        analysis_run_identity=run.run_identity,
        canonical_subject_identity=result.canonical_subject_identity,
        market_family=family,
        canonical_instrument_identity=canonical_instrument_identity,
        active_contract_identity=contract,
    )
    basis = {
        ProbableState.LONG_PROBABLE: WoBClassificationBasis.CURRENT_VALID_SOURCE,
        ProbableState.SHORT_PROBABLE: WoBClassificationBasis.CURRENT_VALID_SOURCE,
        ProbableState.NOT_ADMITTED: WoBClassificationBasis.SOURCE_BLOCKED,
        ProbableState.UNAVAILABLE: WoBClassificationBasis.SOURCE_UNAVAILABLE,
    }[result.state]
    reason = _joined_codes(item.value for item in result.reasons)
    return anchor, _adapted(
        anchor=anchor,
        boundary=WoBSourceBoundary.PROBABLES,
        artifact_identity=result.result_identity,
        schema_identity=result.schema_identity,
        schema_version=result.schema_version,
        policy_identity=result.methodology_identity,
        policy_version=result.methodology_version,
        integrity=result.integrity_identity,
        state=result.state.value,
        reason=reason,
        diagnostic=result.phase.value if result.phase is not None else None,
        observed_at=result.analysis_boundary,
        basis=basis,
    )


def adapt_promotion_source(
    *,
    anchor: WoBCompositionAnchor,
    handoff: Wo12Handoff,
    result: Wo12ResultV2,
    current_pointer: CurrentWo12PointerV2,
) -> WoBAdaptedSource:
    _revalidate(handoff, Wo12Handoff, "WO_B_PROMOTION_SOURCE_INVALID")
    _revalidate(result, Wo12ResultV2, "WO_B_PROMOTION_SOURCE_INVALID")
    _revalidate(current_pointer, CurrentWo12PointerV2, "WO_B_PROMOTION_POINTER_INVALID")
    if (
        result.handoff_identity != handoff.handoff_identity
        or result.handoff_integrity != handoff.handoff_integrity
        or handoff.probables_run_identity != anchor.analysis_run_identity
        or handoff.probable_result_identity != anchor.candidate_identity
        or handoff.canonical_subject_identity != anchor.canonical_subject_identity
        or handoff.market_family is not anchor.market_family
        or current_pointer.result_identity != result.result_identity
        or current_pointer.result_integrity != result.result_integrity
        or current_pointer.request_identity != result.request_identity
    ):
        raise WoBCompositionError("WO_B_PROMOTION_LINEAGE_MISMATCH")
    classification = result.classification
    basis = (
        WoBClassificationBasis.CURRENT_VALID_SOURCE
        if classification
        in {Kr370AnalyticalClassification.BUY_NOW, Kr370AnalyticalClassification.SELL_NOW}
        else WoBClassificationBasis.SOURCE_BLOCKED
    )
    reason = _joined_codes(item.value for item in result.hard_gates) or None
    return _adapted(
        anchor=anchor,
        boundary=WoBSourceBoundary.ANALYTICAL_PROMOTION,
        artifact_identity=result.result_identity,
        schema_identity=result.schema_identity,
        schema_version=result.schema_version,
        policy_identity=result.policy.policy_identity,
        policy_version=result.policy.policy_version,
        integrity=result.result_integrity,
        state=classification.value,
        reason=reason,
        diagnostic=f"SATISFIED_{result.satisfied_count}",
        observed_at=result.created_at,
        basis=basis,
    )


def adapt_wo13_source(
    *, anchor: WoBCompositionAnchor, plan: Wo13TradePlan,
    current_pointer: CurrentWo13Pointer,
) -> WoBAdaptedSource:
    _revalidate(plan, Wo13TradePlan, "WO_B_WO13_SOURCE_INVALID")
    _revalidate(current_pointer, CurrentWo13Pointer, "WO_B_WO13_POINTER_INVALID")
    if (
        current_pointer.trade_plan_identity != plan.trade_plan_identity
        or current_pointer.trade_plan_integrity != plan.trade_plan_integrity
        or current_pointer.source_wo12_result_identity != plan.source_wo12_result_identity
        or plan.canonical_subject_identity != anchor.canonical_subject_identity
        or plan.market_family is not anchor.market_family
        or plan.instrument_identity != anchor.canonical_instrument_identity
        or plan.actual_contract_identity != anchor.active_contract_identity
        or current_pointer.canonical_subject_identity
        != plan.canonical_subject_identity
        or current_pointer.market_family is not plan.market_family
        or current_pointer.direction is not plan.direction
        or current_pointer.setup_family is not plan.setup_family
        or current_pointer.analysis_boundary != plan.analysis_boundary
        or current_pointer.policy != plan.policy
        or plan.supersession is not None
        or current_pointer.supersession_lineage_identity is not None
    ):
        raise WoBCompositionError("WO_B_WO13_CURRENT_BINDING_MISMATCH")
    basis = (
        WoBClassificationBasis.CURRENT_VALID_SOURCE
        if plan.geometry_availability is Wo13GeometryAvailability.GEOMETRY_COMPLETE
        else WoBClassificationBasis.SOURCE_UNAVAILABLE
    )
    return _adapted(
        anchor=anchor, boundary=WoBSourceBoundary.WO13_TRADE_PLAN,
        artifact_identity=plan.trade_plan_identity,
        schema_identity=plan.schema_identity, schema_version=plan.schema_version,
        policy_identity=plan.policy.policy_identity,
        policy_version=plan.policy.policy_version, integrity=plan.trade_plan_integrity,
        state=plan.geometry_availability.value,
        reason=_joined_codes(item.value for item in plan.warnings) or None,
        diagnostic=plan.setup_family.value, observed_at=current_pointer.published_at,
        basis=basis,
    )


def adapt_wo14_source(
    *, anchor: WoBCompositionAnchor, observation: Wo14RiskObservation,
    current_pointer: CurrentWo14Pointer, trade_plan: Wo13TradePlan,
) -> WoBAdaptedSource:
    _revalidate(observation, Wo14RiskObservation, "WO_B_WO14_SOURCE_INVALID")
    _revalidate(current_pointer, CurrentWo14Pointer, "WO_B_WO14_POINTER_INVALID")
    if (
        current_pointer.observation_identity != observation.observation_identity
        or current_pointer.observation_integrity != observation.observation_integrity
        or current_pointer.trade_plan_identity != trade_plan.trade_plan_identity
        or current_pointer.trade_plan_integrity != trade_plan.trade_plan_integrity
        or observation.plan_binding.trade_plan_identity != trade_plan.trade_plan_identity
        or observation.plan_binding.trade_plan_integrity != trade_plan.trade_plan_integrity
        or current_pointer.canonical_subject_identity != anchor.canonical_subject_identity
        or current_pointer.market_family is not anchor.market_family
        or current_pointer.state is not observation.state
        or current_pointer.policy != observation.policy
        or current_pointer.supersession_lineage_identity is not None
    ):
        raise WoBCompositionError("WO_B_WO14_CURRENT_BINDING_MISMATCH")
    basis = (
        WoBClassificationBasis.SOURCE_UNAVAILABLE
        if observation.state is Wo14ObservationState.RISK_UNAVAILABLE
        else WoBClassificationBasis.CURRENT_VALID_SOURCE
    )
    return _adapted(
        anchor=anchor, boundary=WoBSourceBoundary.WO14_RISK_OBSERVATION,
        artifact_identity=observation.observation_identity,
        schema_identity=observation.schema_identity,
        schema_version=observation.schema_version,
        policy_identity=observation.policy.policy_identity,
        policy_version=observation.policy.policy_version,
        integrity=observation.observation_integrity, state=observation.state.value,
        reason=_joined_codes(observation.unavailable_reasons) or None,
        diagnostic=observation.alert_severity.value,
        observed_at=current_pointer.published_at, basis=basis,
    )


def adapt_wo15_source(
    *, anchor: WoBCompositionAnchor, current_pointer: CurrentWo15Pointer,
    handoff: Wo15TimingHandoff | None = None,
) -> WoBAdaptedSource:
    _revalidate(current_pointer, CurrentWo15Pointer, "WO_B_WO15_POINTER_INVALID")
    if handoff is not None:
        _revalidate(handoff, Wo15TimingHandoff, "WO_B_WO15_SOURCE_INVALID")
    if (
        current_pointer.canonical_subject_identity != anchor.canonical_subject_identity
        or current_pointer.market_family is not anchor.market_family
        or current_pointer.instrument_identity != anchor.canonical_instrument_identity
        or current_pointer.actual_contract_identity != anchor.active_contract_identity
        or current_pointer.supersession_lineage_identity is not None
        or handoff is not None
        and (
            current_pointer.timing_handoff_identity != handoff.handoff_identity
            or current_pointer.timing_handoff_integrity != handoff.handoff_integrity
            or handoff.wo13_trade_plan_identity != current_pointer.wo13_trade_plan_identity
        )
    ):
        raise WoBCompositionError("WO_B_WO15_CURRENT_BINDING_MISMATCH")
    state = current_pointer.timing_state
    if state is Wo15TimingState.TIMING_QUALIFIED and handoff is None:
        raise WoBCompositionError("WO_B_WO15_HANDOFF_REQUIRED")
    basis = {
        Wo15TimingState.TIMING_NOT_EVALUATED: WoBClassificationBasis.SOURCE_WAITING,
        Wo15TimingState.TIMING_WAITING: WoBClassificationBasis.SOURCE_WAITING,
        Wo15TimingState.TIMING_QUALIFIED: WoBClassificationBasis.CURRENT_VALID_SOURCE,
        Wo15TimingState.TIMING_FAILED: WoBClassificationBasis.SOURCE_TERMINAL,
        Wo15TimingState.TIMING_EXPIRED: WoBClassificationBasis.SOURCE_TERMINAL,
        Wo15TimingState.TIMING_UNAVAILABLE: WoBClassificationBasis.SOURCE_UNAVAILABLE,
    }[state]
    reason = handoff.transition_cause if handoff is not None else None
    return _adapted(
        anchor=anchor, boundary=WoBSourceBoundary.WO15_TIMING_HANDOFF,
        artifact_identity=(handoff.handoff_identity if handoff else current_pointer.timing_result_identity),
        schema_identity=(handoff.schema_identity if handoff else current_pointer.schema_identity),
        schema_version=(handoff.schema_version if handoff else current_pointer.schema_version),
        policy_identity=current_pointer.policy.policy_identity,
        policy_version=current_pointer.policy.policy_version,
        integrity=(handoff.handoff_integrity if handoff else current_pointer.timing_result_integrity),
        state=state.value, reason=_source_code(reason),
        diagnostic=None, observed_at=current_pointer.published_at, basis=basis,
    )


def adapt_wo16_source(
    *, anchor: WoBCompositionAnchor, snapshot: Wo16SponsorDecisionSnapshot,
    decision: Wo16SponsorDecisionRecord, admission: Wo16LifecycleAdmissionRecord,
    current_pointer: CurrentWo16Pointer,
) -> WoBAdaptedSource:
    for value, expected in (
        (snapshot, Wo16SponsorDecisionSnapshot),
        (decision, Wo16SponsorDecisionRecord),
        (admission, Wo16LifecycleAdmissionRecord),
        (current_pointer, CurrentWo16Pointer),
    ):
        _revalidate(value, expected, "WO_B_WO16_SOURCE_INVALID")
    if (
        current_pointer.snapshot_identity != snapshot.snapshot_identity
        or current_pointer.decision_identity != decision.decision_identity
        or current_pointer.admission_identity != admission.admission_identity
        or decision.snapshot_identity != snapshot.snapshot_identity
        or admission.decision_identity != decision.decision_identity
        or current_pointer.canonical_subject_identity != anchor.canonical_subject_identity
        or current_pointer.instrument_identity != anchor.canonical_instrument_identity
        or current_pointer.actual_contract_identity != anchor.active_contract_identity
    ):
        raise WoBCompositionError("WO_B_WO16_CURRENT_BINDING_MISMATCH")
    terminal = (
        decision.choice is Wo16SponsorDecision.IGNORE
        and admission.disposition
        is Wo16LifecycleAdmissionDisposition.NOT_APPLICABLE_IGNORE
    )
    basis = (
        WoBClassificationBasis.SOURCE_TERMINAL
        if terminal else WoBClassificationBasis.CURRENT_VALID_SOURCE
    )
    return _adapted(
        anchor=anchor, boundary=WoBSourceBoundary.WO16_SPONSOR_LIFECYCLE,
        artifact_identity=current_pointer.pointer_identity,
        schema_identity=current_pointer.schema_identity,
        schema_version=current_pointer.schema_version,
        policy_identity=current_pointer.policy.policy_identity,
        policy_version=current_pointer.policy.policy_version,
        integrity=current_pointer.pointer_integrity,
        state=f"{decision.choice.value}.{admission.disposition.value}",
        reason=admission.reason.value, diagnostic=None,
        observed_at=current_pointer.published_at, basis=basis,
    )


def adapt_wo17_source(
    *, anchor: WoBCompositionAnchor, current_pointer: CurrentWo17Pointer,
    position: Wo17PositionMachine | None = None,
    lifecycle: Wo17LifecycleMachine | None = None,
) -> WoBAdaptedSource:
    _revalidate(current_pointer, CurrentWo17Pointer, "WO_B_WO17_POINTER_INVALID")
    if position is not None:
        _revalidate(position, Wo17PositionMachine, "WO_B_WO17_SOURCE_INVALID")
    if lifecycle is not None:
        _revalidate(lifecycle, Wo17LifecycleMachine, "WO_B_WO17_SOURCE_INVALID")
    if (
        current_pointer.canonical_subject_identity != anchor.canonical_subject_identity
        or current_pointer.instrument_identity != anchor.canonical_instrument_identity
        or current_pointer.actual_contract_identity != anchor.active_contract_identity
        or position is not None
        and (
            current_pointer.position_state_identity != position.state_identity
            or current_pointer.position_state_integrity != position.state_integrity
            or current_pointer.position_state is not position.state
        )
        or lifecycle is not None
        and (
            current_pointer.lifecycle_state_identity != lifecycle.state_identity
            or current_pointer.lifecycle_state_integrity != lifecycle.state_integrity
        )
    ):
        raise WoBCompositionError("WO_B_WO17_CURRENT_BINDING_MISMATCH")
    state = current_pointer.position_state
    closed = current_pointer.closure_state in {
        Wo17ClosureState.PAPER_CLOSED,
        Wo17ClosureState.LIVE_CLOSED,
    }
    basis = (
        WoBClassificationBasis.SOURCE_TERMINAL
        if closed or state in {
            Wo17PositionState.ENTRY_INVALIDATED_BEFORE_POSITION,
            Wo17PositionState.ENTRY_WINDOW_EXPIRED,
        }
        else WoBClassificationBasis.SOURCE_WAITING
        if state in {
            Wo17PositionState.PAPER_ARMED,
            Wo17PositionState.LIVE_AWAITING_SPONSOR_ENTRY_EVIDENCE,
        }
        else WoBClassificationBasis.CURRENT_VALID_SOURCE
    )
    monitoring = _source_code(current_pointer.monitoring_availability)
    if lifecycle is not None:
        monitoring = lifecycle.monitoring_availability.value
    return _adapted(
        anchor=anchor, boundary=WoBSourceBoundary.WO17_POSITION_MONITORING,
        artifact_identity=current_pointer.pointer_identity,
        schema_identity=current_pointer.schema_identity,
        schema_version=current_pointer.schema_version,
        policy_identity=current_pointer.policy_identity,
        policy_version=current_pointer.policy_version,
        integrity=current_pointer.pointer_integrity, state=state.value,
        reason=monitoring, diagnostic=_source_code(current_pointer.closure_state),
        observed_at=current_pointer.published_at, basis=basis,
    )


def adapt_domain_001_source(
    *, anchor: WoBCompositionAnchor,
    instrument: CanonicalInstrument | None = None,
    active_derivative: ActiveDerivativeBindingArtifact | None = None,
    review_boundary: datetime,
) -> WoBAdaptedSource:
    if anchor.market_family is IntradayMarketFamily.MCX:
        _revalidate(
            active_derivative,
            ActiveDerivativeBindingArtifact,
            "WO_B_DOMAIN_001_BINDING_INVALID",
        )
        if active_derivative is None:
            raise WoBCompositionError("WO_B_DOMAIN_001_BINDING_INVALID")
        if (
            active_derivative.canonical_subject_id != anchor.canonical_subject_identity
            or active_derivative.active_binding.derivative_contract_id
            != anchor.active_contract_identity
            or active_derivative.provider_symbol != anchor.canonical_instrument_identity
            or not (
                active_derivative.observation_boundary
                <= review_boundary
                <= active_derivative.expiry_eligibility_boundary
            )
        ):
            raise WoBCompositionError("WO_B_DOMAIN_001_BINDING_MISMATCH")
        return _adapted(
            anchor=anchor, boundary=WoBSourceBoundary.DOMAIN_001_INSTRUMENT,
            artifact_identity=active_derivative.binding_identity,
            schema_identity=active_derivative.artifact_identity,
            schema_version=active_derivative.artifact_version,
            policy_identity=active_derivative.selection_rule_identity,
            policy_version=active_derivative.selection_rule_version,
            integrity=active_derivative.integrity_identity,
            state="ACTIVE_DERIVATIVE_BOUND", reason=None,
            diagnostic=active_derivative.provider_contract_family,
            observed_at=active_derivative.observation_boundary,
            basis=WoBClassificationBasis.CURRENT_VALID_SOURCE,
        )
    _revalidate(instrument, CanonicalInstrument, "WO_B_DOMAIN_001_BINDING_INVALID")
    if instrument is None:
        raise WoBCompositionError("WO_B_DOMAIN_001_BINDING_INVALID")
    if (
        instrument.canonical_instrument_id != anchor.canonical_instrument_identity
        or anchor.active_contract_identity is not None
        or not instrument.source_boundary <= review_boundary <= instrument.valid_through
    ):
        raise WoBCompositionError("WO_B_DOMAIN_001_BINDING_MISMATCH")
    return _adapted(
        anchor=anchor, boundary=WoBSourceBoundary.DOMAIN_001_INSTRUMENT,
        artifact_identity=instrument.canonical_instrument_id,
        schema_identity=instrument.schema_identity, schema_version="1.0.0",
        policy_identity=instrument.canonical_source_identity,
        policy_version="1.0.0", integrity=instrument.integrity_identity,
        state="CANONICAL_INSTRUMENT_CURRENT", reason=None,
        diagnostic=None, observed_at=instrument.source_boundary,
        basis=WoBClassificationBasis.CURRENT_VALID_SOURCE,
    )


def adapt_domain_001_v2_source(
    *,
    anchor: WoBCompositionAnchor,
    publication: InstrumentSemanticPublicationV2,
    semantic_object: DirectListedInstrumentV2 | AnalyticalSubjectV2,
    review_boundary: datetime,
) -> WoBAdaptedSource:
    """Bind an NSE candidate to the exact current DOMAIN-001 V2 object."""

    _revalidate(
        publication,
        InstrumentSemanticPublicationV2,
        "WO_B_DOMAIN_001_PUBLICATION_INVALID",
    )
    if type(semantic_object) not in {DirectListedInstrumentV2, AnalyticalSubjectV2}:
        raise WoBCompositionError("WO_B_DOMAIN_001_BINDING_INVALID")
    _revalidate(
        semantic_object,
        type(semantic_object),
        "WO_B_DOMAIN_001_BINDING_INVALID",
    )
    if (
        anchor.market_family is IntradayMarketFamily.MCX
        or anchor.active_contract_identity is not None
        or semantic_object.canonical_id != anchor.canonical_subject_identity
        or semantic_object.canonical_id != anchor.canonical_instrument_identity
        or semantic_object.exchange != "NSE"
        or semantic_object not in publication.semantic_objects
        or not publication.effective_from <= review_boundary <= publication.effective_through
        or not semantic_object.valid_from <= review_boundary <= semantic_object.valid_through
    ):
        raise WoBCompositionError("WO_B_DOMAIN_001_BINDING_MISMATCH")
    return _adapted(
        anchor=anchor,
        boundary=WoBSourceBoundary.DOMAIN_001_INSTRUMENT,
        artifact_identity=semantic_object.canonical_id,
        schema_identity=publication.schema_identity,
        schema_version=publication.publication_version,
        policy_identity=publication.publication_identity,
        policy_version=publication.publication_version,
        integrity=semantic_object.integrity_identity,
        state="CANONICAL_INSTRUMENT_CURRENT",
        reason=None,
        diagnostic=semantic_object.semantic_kind.value,
        observed_at=publication.effective_from,
        basis=WoBClassificationBasis.CURRENT_VALID_SOURCE,
    )


def adapt_domain_008_source(
    *, anchor: WoBCompositionAnchor, fact: MarketSessionFact,
) -> WoBAdaptedSource:
    _revalidate(fact, MarketSessionFact, "WO_B_DOMAIN_008_SESSION_INVALID")
    schedule = fact.schedule
    if schedule is None:
        raise WoBCompositionError("WO_B_DOMAIN_008_SCHEDULE_UNAVAILABLE")
    if anchor.market_family is IntradayMarketFamily.MCX:
        expected_exchange = "MCX"
    else:
        expected_exchange = "NSE"
    if schedule.exchange != expected_exchange or fact.exchange != expected_exchange:
        raise WoBCompositionError("WO_B_DOMAIN_008_SESSION_MISMATCH")
    if fact.state is MarketSessionState.UNAVAILABLE:
        basis = WoBClassificationBasis.SOURCE_UNAVAILABLE
    elif fact.state in {
        MarketSessionState.BEFORE_SESSION,
        MarketSessionState.BETWEEN_WINDOWS,
    }:
        basis = WoBClassificationBasis.SOURCE_WAITING
    elif fact.state in {
        MarketSessionState.NON_TRADING_DAY,
        MarketSessionState.SESSION_ENDED,
    }:
        basis = WoBClassificationBasis.SOURCE_TERMINAL
    else:
        basis = WoBClassificationBasis.CURRENT_VALID_SOURCE
    digest = _session_integrity(fact)
    return _adapted(
        anchor=anchor, boundary=WoBSourceBoundary.DOMAIN_008_SESSION,
        artifact_identity=f"DOMAIN-008-SESSION-{digest.upper()}",
        schema_identity=schedule.schema_identity,
        schema_version="1.0.0", policy_identity=schedule.source_identity,
        policy_version=schedule.source_version, integrity=digest,
        state=fact.state.value, reason=None,
        diagnostic="SESSION_END" if fact.session_end else None,
        observed_at=fact.observed_at, basis=basis,
    )


def reconstruct_operational_review(
    request: WoBCompositionRequest,
) -> WoBOperationalReviewSnapshot:
    _revalidate(
        request,
        WoBCompositionRequest,
        "WO_B_COMPOSITION_REQUEST_INVALID",
    )
    source_by_boundary = {
        item.reference.source_boundary: item for item in request.sources
    }
    for source in request.sources:
        _validate_anchor(request.anchor, source.reference, request.review_boundary)
    if not {
        WoBSourceBoundary.DOMAIN_001_INSTRUMENT,
        WoBSourceBoundary.DOMAIN_008_SESSION,
        WoBSourceBoundary.PROBABLES,
    }.issubset(source_by_boundary):
        raise WoBCompositionError("WO_B_REQUIRED_FOUNDATION_SOURCE_MISSING")
    _validate_stage_dependencies(source_by_boundary)

    unresolved = _next_attention_boundary(
        source_by_boundary, set(request.required_missing_boundaries)
    )
    items = []
    for boundary in _REVIEW_ORDER:
        source = source_by_boundary.get(boundary)
        next_stage = boundary.value if boundary is unresolved else None
        if source is not None:
            items.append(create_review_item(
                source_boundary=boundary,
                classification_basis=source.classification_basis,
                source_reference=source.reference,
                next_governed_stage=next_stage,
            ))
        elif boundary in request.required_missing_boundaries:
            items.append(create_review_item(
                source_boundary=boundary,
                classification_basis=WoBClassificationBasis.SOURCE_UNAVAILABLE,
                missing_source_reason="WO_B_REQUIRED_SOURCE_MISSING",
                missing_source_diagnostic=f"MISSING_{boundary.value}",
                next_governed_stage=next_stage,
            ))
        else:
            items.append(create_review_item(
                source_boundary=boundary,
                classification_basis=(
                    WoBClassificationBasis.EXPECTED_DOWNSTREAM_ABSENCE
                ),
                next_governed_stage=next_stage,
            ))
    references = tuple(
        source_by_boundary[boundary].reference
        for boundary in _REVIEW_ORDER
        if boundary in source_by_boundary
    )
    return create_operational_review_snapshot(
        review_boundary=request.review_boundary,
        created_at=request.created_at,
        candidate_identity=request.anchor.candidate_identity,
        opportunity_identity=request.anchor.opportunity_identity,
        analysis_run_lineage=(request.anchor.analysis_run_identity,),
        canonical_subject_identity=request.anchor.canonical_subject_identity,
        market_family=request.anchor.market_family,
        canonical_instrument_identity=request.anchor.canonical_instrument_identity,
        active_contract_identity=request.anchor.active_contract_identity,
        source_artifact_references=references,
        review_items=tuple(items),
        provenance=request.provenance,
    )


def publish_operational_review(
    request: WoBCompositionRequest,
    *, store: WoBStore,
) -> WoBPublishedComposition:
    _revalidate(
        request,
        WoBCompositionRequest,
        "WO_B_COMPOSITION_REQUEST_INVALID",
    )
    if type(store) is not WoBStore:
        raise WoBCompositionError("WO_B_STORE_INVALID")
    previous = None
    try:
        previous = store.load_current(request.anchor.candidate_identity)
        snapshot = reconstruct_operational_review(request)
        pointer = store.publish_current(snapshot)
    except (WoBContractError, WoBPersistenceError) as error:
        failure = _failure_for(request, error)
        store.publish_latest_failure(failure)
        raise WoBCompositionError(failure.reason) from error
    return WoBPublishedComposition(
        snapshot=snapshot,
        pointer=pointer,
        replayed=(
            previous is not None
            and previous.review_snapshot_identity == snapshot.review_snapshot_identity
        ),
    )


def restore_operational_review(
    candidate_identity: str, *, store: WoBStore
) -> RestoredWoBState:
    """Restore only WO-B artifacts; never reconstruct producer domains."""
    return store.restore_current(candidate_identity)


def _adapted(
    *, anchor: WoBCompositionAnchor, boundary: WoBSourceBoundary,
    artifact_identity: str, schema_identity: str, schema_version: str,
    policy_identity: str, policy_version: str, integrity: str, state: str,
    reason: str | None, diagnostic: str | None, observed_at: datetime,
    basis: WoBClassificationBasis,
) -> WoBAdaptedSource:
    reference = create_source_artifact_reference(
        source_boundary=boundary,
        artifact_identity=artifact_identity,
        artifact_schema_identity=schema_identity,
        artifact_schema_version=schema_version,
        source_policy_identity=policy_identity,
        source_policy_version=policy_version,
        source_integrity_identity=integrity,
        candidate_identity=anchor.candidate_identity,
        analysis_run_identity=anchor.analysis_run_identity,
        canonical_instrument_identity=anchor.canonical_instrument_identity,
        active_contract_identity=anchor.active_contract_identity,
        exact_source_state=_source_code(state),
        exact_source_reason=_source_code(reason),
        bounded_diagnostic=_source_code(diagnostic),
        observed_at=observed_at,
        current_at_review_boundary=True,
        superseded=False,
        currentness_required=True,
    )
    return WoBAdaptedSource(reference=reference, classification_basis=basis)


def _validate_anchor(
    anchor: WoBCompositionAnchor,
    reference: WoBSourceArtifactReference,
    review_boundary: datetime,
) -> None:
    if (
        reference.candidate_identity != anchor.candidate_identity
        or reference.analysis_run_identity != anchor.analysis_run_identity
        or reference.canonical_instrument_identity
        != anchor.canonical_instrument_identity
        or reference.active_contract_identity != anchor.active_contract_identity
        or reference.observed_at > review_boundary
        or not reference.current_at_review_boundary
        or reference.superseded
    ):
        raise WoBCompositionError("WO_B_CROSS_SOURCE_BINDING_MISMATCH")


def _validate_stage_dependencies(
    sources: Mapping[WoBSourceBoundary, WoBAdaptedSource],
) -> None:
    present = set(sources)
    requirements = {
        WoBSourceBoundary.ANALYTICAL_PROMOTION: {WoBSourceBoundary.PROBABLES},
        WoBSourceBoundary.WO13_TRADE_PLAN: {WoBSourceBoundary.ANALYTICAL_PROMOTION},
        WoBSourceBoundary.WO14_RISK_OBSERVATION: {WoBSourceBoundary.WO13_TRADE_PLAN},
        WoBSourceBoundary.WO15_TIMING_HANDOFF: {WoBSourceBoundary.WO13_TRADE_PLAN},
        WoBSourceBoundary.WO16_SPONSOR_LIFECYCLE: {
            WoBSourceBoundary.WO13_TRADE_PLAN,
            WoBSourceBoundary.WO14_RISK_OBSERVATION,
            WoBSourceBoundary.WO15_TIMING_HANDOFF,
        },
        WoBSourceBoundary.WO17_POSITION_MONITORING: {
            WoBSourceBoundary.WO16_SPONSOR_LIFECYCLE,
        },
    }
    if any(boundary in present and not required.issubset(present)
           for boundary, required in requirements.items()):
        raise WoBCompositionError("WO_B_SOURCE_STAGE_LINEAGE_INCOMPLETE")
    terminal_seen = False
    for boundary in _PIPELINE_ORDER:
        source = sources.get(boundary)
        if source is None:
            continue
        if terminal_seen:
            raise WoBCompositionError("WO_B_SOURCE_AFTER_TERMINAL_PROHIBITED")
        terminal_seen = (
            source.classification_basis is WoBClassificationBasis.SOURCE_TERMINAL
        )


def _next_attention_boundary(
    sources: Mapping[WoBSourceBoundary, WoBAdaptedSource],
    required_missing: set[WoBSourceBoundary],
) -> WoBSourceBoundary | None:
    for boundary in _REVIEW_ORDER:
        source = sources.get(boundary)
        if boundary in required_missing:
            return boundary
        if source is None:
            return boundary
        if source.classification_basis in {
            WoBClassificationBasis.SOURCE_WAITING,
            WoBClassificationBasis.SOURCE_BLOCKED,
            WoBClassificationBasis.SOURCE_UNAVAILABLE,
        }:
            return boundary
        if source.classification_basis is WoBClassificationBasis.SOURCE_TERMINAL:
            return None
    return None


def _failure_for(
    request: WoBCompositionRequest, error: Exception
) -> WoBReviewFailure:
    reason = wo_b_exception_reason(error)
    stage = (
        WoBFailureStage.POINTER_PUBLICATION
        if reason.startswith("WO_B_CURRENT_")
        else WoBFailureStage.SOURCE_BINDING
    )
    identities = tuple(
        item.reference.artifact_identity for item in request.sources
    )
    return create_wo_b_failure(
        candidate_identity=request.anchor.candidate_identity,
        analysis_run_identity=request.anchor.analysis_run_identity,
        stage=stage,
        reason=reason,
        failed_at=request.created_at,
        source_identities=identities,
    )


def _revalidate(value: object, expected: type, failure: str) -> None:
    if type(value) is not expected:
        raise WoBCompositionError(failure)
    try:
        replace(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise WoBCompositionError(failure) from error


def _market_family_for_subject(subject: str) -> IntradayMarketFamily:
    if subject.startswith("MCX-SUBJECT-"):
        return IntradayMarketFamily.MCX
    if subject.startswith("NSE-INDEX-"):
        return IntradayMarketFamily.NSE_INDEX
    if subject.startswith("NSE-EQ-"):
        return IntradayMarketFamily.NSE_EQUITY
    raise WoBCompositionError("WO_B_CANONICAL_SUBJECT_FAMILY_UNAVAILABLE")


def _session_integrity(fact: MarketSessionFact) -> str:
    schedule = fact.schedule
    if schedule is None:
        raise WoBCompositionError("WO_B_DOMAIN_008_SCHEDULE_UNAVAILABLE")
    document = {
        "exchange": fact.exchange,
        "trading_date": fact.trading_date.isoformat(),
        "observed_at": fact.observed_at.isoformat(),
        "availability": fact.availability,
        "state": fact.state.value,
        "session_id": schedule.session_id,
        "source_identity": schedule.source_identity,
        "source_version": schedule.source_version,
        "windows": [
            [window.opens_at.isoformat(), window.closes_at.isoformat()]
            for window in schedule.windows
        ],
    }
    return sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _joined_codes(values: Iterable[object]) -> str | None:
    retained = tuple(values)
    if not retained:
        return None
    return _source_code(".".join(str(item) for item in retained))


def _source_code(value: object) -> str | None:
    if value is None:
        return None
    if hasattr(value, "value"):
        value = value.value
    if (
        type(value) is not str
        or not 0 < len(value) <= 160
        or any(
            not (
                character.isupper()
                or character.isdigit()
                or character in "_-.:"
            )
            for character in value
        )
    ):
        raise WoBCompositionError("WO_B_SOURCE_CODE_INVALID")
    return value


def _safe_code(value: object) -> str | None:
    if value is None:
        return None
    if hasattr(value, "value"):
        value = value.value
    if type(value) is not str:
        return None
    normalized = "".join(
        character if character.isupper() or character.isdigit()
        or character in "_-.:" else "_"
        for character in value.upper()
    )[:160]
    return normalized or None


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _text(value: object) -> bool:
    return type(value) is str and bool(value.strip())


def _optional_text(value: object) -> bool:
    return value is None or _text(value)


__all__ = [
    name
    for name in globals()
    if name.startswith(("WoB", "adapt_", "publish_", "reconstruct_", "restore_"))
]
