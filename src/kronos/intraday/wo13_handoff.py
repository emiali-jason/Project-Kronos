"""Exact current WO-12 V2 to Intraday WO-13 Step-31 handoff.

The seam admits analytical state only.  It calculates no geometry and owns no
Risk, 5M timing, Sponsor, execution, or broker authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import date, datetime
from enum import StrEnum
from hashlib import sha256
import json
from typing import Mapping, Sequence

from kronos.instrument.active_derivative import ActiveDerivativeBindingArtifact
from kronos.intraday.completed_evidence import IntradayAnalysisPhase
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.mcx_commissioning import (
    McxCommissioningState,
    McxCommissioningPublication,
)
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo10_evidence import Wo10EvidenceSnapshot
from kronos.intraday.wo10_policies import Wo10McxPolicyEvidence
from kronos.intraday.wo12_k5_foundation import (
    Wo12SetupFamily,
    Wo12StructuralOriginFact,
)
from kronos.intraday.wo12_v2 import (
    CurrentWo12PointerV2,
    Wo12EvidenceV2,
    Wo12RequestV2,
    Wo12ResultV2,
    Wo13EligibilityRecordV2,
    Wo13EligibilityV2,
)
from kronos.validation.kr370 import Kr370AnalyticalClassification


WO13_CONTRACT_VERSION = "1.0.0"
WO13_HANDOFF_IDENTITY = "KRONOS-INTRADAY-WO13-STEP31-HANDOFF-V1"
WO13_POLICY_IDENTITY = "KRONOS-INTRADAY-WO13-STEP31-TRADE-CONSTRUCTION-POLICY-V1"
WO13_POLICY_VERSION = "1.0.0"
WO13_POLICY_CHECKSUM = (
    "c5ea70a5af50af251088785a58a39da4e824b5cc6058c11c98e880fce0fb0e6b"
)
WO13_AUTHORITY = "TRADE_CONSTRUCTION_ONLY"


class Wo13SetupFamily(StrEnum):
    INTRADAY_PULLBACK_CONTINUATION = "INTRADAY_PULLBACK_CONTINUATION"
    INTRADAY_RANGE_BREAKOUT = "INTRADAY_RANGE_BREAKOUT"


class Wo13HandoffFailure(StrEnum):
    WO12_NOT_NOW = "WO12_NOT_NOW"
    WO12_NOT_CURRENT = "WO12_NOT_CURRENT"
    WO12_SUPERSEDED = "WO12_SUPERSEDED"
    WO12_INTEGRITY_INVALID = "WO12_INTEGRITY_INVALID"
    DIRECTION_MISMATCH = "DIRECTION_MISMATCH"
    SETUP_FAMILY_MISMATCH = "SETUP_FAMILY_MISMATCH"
    SUBJECT_MISMATCH = "SUBJECT_MISMATCH"
    MARKET_FAMILY_MISMATCH = "MARKET_FAMILY_MISMATCH"
    ANALYSIS_BOUNDARY_MISMATCH = "ANALYSIS_BOUNDARY_MISMATCH"
    POLICY_MISMATCH = "POLICY_MISMATCH"
    INSTRUMENT_IDENTITY_MISMATCH = "INSTRUMENT_IDENTITY_MISMATCH"
    MCX_ACTIVE_CONTRACT_MISMATCH = "MCX_ACTIVE_CONTRACT_MISMATCH"
    MCX_ROLL_LINEAGE_MISMATCH = "MCX_ROLL_LINEAGE_MISMATCH"
    SOURCE_EVIDENCE_INVALID = "SOURCE_EVIDENCE_INVALID"


class Wo13HandoffRejected(ValueError):
    """Sanitized exact-boundary rejection."""

    def __init__(self, failure: Wo13HandoffFailure) -> None:
        if type(failure) is not Wo13HandoffFailure:
            raise ValueError("WO13_HANDOFF_FAILURE_INVALID")
        self.failure = failure
        super().__init__(failure.value)


@dataclass(frozen=True, slots=True)
class Wo13Step31Handoff:
    handoff_identity: str
    handoff_integrity: str
    wo12_pointer_identity: str
    wo12_pointer_integrity: str
    wo12_request_identity: str
    wo12_request_integrity: str
    wo12_evidence_identity: str
    wo12_evidence_integrity: str
    wo12_result_identity: str
    wo12_result_integrity: str
    wo12_eligibility_identity: str
    wo12_eligibility_integrity: str
    wo12_classification: Kr370AnalyticalClassification
    wo12_policy_identity: str
    wo12_policy_version: str
    wo12_policy_checksum: str
    wo11_publication_identity: str
    wo11_publication_integrity: str
    wo11_member_identity: str
    wo11_member_integrity: str
    wo11_handoff_identity: str
    wo11_handoff_integrity: str
    wo10_result_identity: str
    wo10_result_integrity: str
    wo10_evidence_identity: str
    wo10_evidence_integrity: str
    wo10_policy_identity: str
    wo10_policy_version: str
    wo10_policy_checksum: str
    probables_run_identity: str
    probables_run_integrity: str
    probable_result_identity: str
    probable_result_integrity: str
    canonical_subject_identity: str
    market_family: IntradayMarketFamily
    inherited_direction: SemanticDirection
    setup_family: Wo13SetupFamily
    setup_evidence_identity: str
    setup_evidence_integrity: str
    analysis_boundary: datetime
    phase: IntradayAnalysisPhase
    instrument_identity: str
    instrument_lineage_integrity: str
    actual_contract_identity: str | None
    provider_symbol: str | None
    active_binding_identity: str | None
    active_binding_integrity: str | None
    active_binding_supersedes: str | None
    contract_expiry: date | None
    commissioning_publication_identity: str | None
    commissioning_publication_integrity: str | None
    commissioning_state: McxCommissioningState | None
    roll_lineage_identity: str | None
    tick_size: str | None
    lot_size: int | None
    source_identities: tuple[str, ...]
    source_integrities: tuple[str, ...]
    predecessor_trade_plan_identity: str | None = None
    schema_identity: str = WO13_HANDOFF_IDENTITY
    schema_version: str = WO13_CONTRACT_VERSION
    authority: str = "ELIGIBILITY_HANDOFF_ONLY"
    geometry_authority: bool = False
    risk_authority: bool = False
    entry_timing_authority: bool = False
    sponsor_decision_authority: bool = False
    execution_authority: bool = False
    broker_authority: bool = False

    def __post_init__(self) -> None:
        values = _without(self, "handoff_identity", "handoff_integrity")
        expected_direction = (
            SemanticDirection.LONG
            if self.wo12_classification is Kr370AnalyticalClassification.BUY_NOW
            else SemanticDirection.SHORT
        )
        mcx = self.market_family is IntradayMarketFamily.MCX
        mcx_values = (
            self.actual_contract_identity,
            self.provider_symbol,
            self.active_binding_identity,
            self.active_binding_integrity,
            self.contract_expiry,
            self.commissioning_publication_identity,
            self.commissioning_publication_integrity,
            self.commissioning_state,
            self.roll_lineage_identity,
            self.tick_size,
            self.lot_size,
        )
        if (
            self.wo12_classification not in {
                Kr370AnalyticalClassification.BUY_NOW,
                Kr370AnalyticalClassification.SELL_NOW,
            }
            or self.inherited_direction is not expected_direction
            or type(self.setup_family) is not Wo13SetupFamily
            or type(self.market_family) is not IntradayMarketFamily
            or not _aware(self.analysis_boundary)
            or type(self.phase) is not IntradayAnalysisPhase
            or not _texts((
                self.wo12_pointer_identity, self.wo12_pointer_integrity,
                self.wo12_request_identity, self.wo12_request_integrity,
                self.wo12_evidence_identity, self.wo12_evidence_integrity,
                self.wo12_result_identity, self.wo12_result_integrity,
                self.wo12_eligibility_identity, self.wo12_eligibility_integrity,
                self.wo12_policy_identity, self.wo12_policy_version,
                self.wo12_policy_checksum, self.wo11_publication_identity,
                self.wo11_publication_integrity, self.wo11_member_identity,
                self.wo11_member_integrity, self.wo11_handoff_identity,
                self.wo11_handoff_integrity, self.wo10_result_identity,
                self.wo10_result_integrity, self.wo10_evidence_identity,
                self.wo10_evidence_integrity, self.wo10_policy_identity,
                self.wo10_policy_version, self.wo10_policy_checksum,
                self.probables_run_identity, self.probables_run_integrity,
                self.probable_result_identity, self.probable_result_integrity,
                self.canonical_subject_identity, self.setup_evidence_identity,
                self.setup_evidence_integrity, self.instrument_identity,
                self.instrument_lineage_integrity,
            ))
            or len(self.source_identities) != len(self.source_integrities)
            or not _texts(self.source_identities)
            or not _texts(self.source_integrities)
            or len(set(self.source_identities)) != len(self.source_identities)
            or (mcx and any(item is None for item in mcx_values))
            or (not mcx and any(item is not None for item in mcx_values))
            or (mcx and self.commissioning_state is not McxCommissioningState.COMMISSIONED)
            or self.predecessor_trade_plan_identity is not None
            and not _text(self.predecessor_trade_plan_identity)
            or self.schema_identity != WO13_HANDOFF_IDENTITY
            or self.schema_version != WO13_CONTRACT_VERSION
            or self.authority != "ELIGIBILITY_HANDOFF_ONLY"
            or any((self.geometry_authority, self.risk_authority,
                    self.entry_timing_authority, self.sponsor_decision_authority,
                    self.execution_authority, self.broker_authority))
            or self.handoff_identity != _identity("INTRADAY-WO13-HANDOFF-", values)
            or self.handoff_integrity
            != _identity("INTEGRITY-INTRADAY-WO13-HANDOFF-", values)
        ):
            raise ValueError("WO13_HANDOFF_INVALID")


def create_wo13_step31_handoff(
    *,
    current_pointer: CurrentWo12PointerV2,
    request: Wo12RequestV2,
    evidence: Wo12EvidenceV2,
    result: Wo12ResultV2,
    eligibility: Wo13EligibilityRecordV2,
    wo10_snapshot: Wo10EvidenceSnapshot,
    setup_evidence: Wo12StructuralOriginFact,
    mcx_evidence: Wo10McxPolicyEvidence | None = None,
    predecessor_trade_plan_identity: str | None = None,
) -> Wo13Step31Handoff:
    """Create one immutable exact-current handoff; never resolve by latest."""

    _require_integrity(current_pointer, request, evidence, result, eligibility)
    _require_integrity(wo10_snapshot, setup_evidence)
    _validate_wo12_chain(current_pointer, request, evidence, result, eligibility)
    handoff = request.handoff
    if result.classification not in {
        Kr370AnalyticalClassification.BUY_NOW,
        Kr370AnalyticalClassification.SELL_NOW,
    } or eligibility.eligibility is not Wo13EligibilityV2.ELIGIBLE_FOR_WO13_STEP31:
        raise Wo13HandoffRejected(Wo13HandoffFailure.WO12_NOT_NOW)
    expected_direction = (
        SemanticDirection.LONG
        if result.classification is Kr370AnalyticalClassification.BUY_NOW
        else SemanticDirection.SHORT
    )
    if any(item is not expected_direction for item in (
        handoff.inherited_direction, evidence.inherited_direction,
        result.inherited_direction, eligibility.inherited_direction,
        wo10_snapshot.inherited_direction, setup_evidence.inherited_direction,
    )):
        raise Wo13HandoffRejected(Wo13HandoffFailure.DIRECTION_MISMATCH)
    if any(item != result.canonical_subject_identity for item in (
        handoff.canonical_subject_identity, evidence.canonical_subject_identity,
        eligibility.canonical_subject_identity,
        wo10_snapshot.canonical_subject_identity,
        setup_evidence.canonical_subject_identity,
    )):
        raise Wo13HandoffRejected(Wo13HandoffFailure.SUBJECT_MISMATCH)
    if any(item is not result.market_family for item in (
        handoff.market_family, evidence.market_family,
        wo10_snapshot.market_family, setup_evidence.market_family,
    )):
        raise Wo13HandoffRejected(Wo13HandoffFailure.MARKET_FAMILY_MISMATCH)
    if any(item != result.analysis_boundary for item in (
        handoff.analysis_boundary, evidence.analysis_boundary,
        eligibility.analysis_boundary, wo10_snapshot.analysis_boundary,
        setup_evidence.analysis_boundary,
    )) or wo10_snapshot.persisted_phase is not result.phase:
        raise Wo13HandoffRejected(Wo13HandoffFailure.ANALYSIS_BOUNDARY_MISMATCH)
    if setup_evidence.setup_family.value not in tuple(item.value for item in Wo13SetupFamily):
        raise Wo13HandoffRejected(Wo13HandoffFailure.SETUP_FAMILY_MISMATCH)
    setup_family = Wo13SetupFamily(setup_evidence.setup_family.value)
    if (
        wo10_snapshot.snapshot_identity != handoff.wo10_evidence_identity
        or wo10_snapshot.snapshot_integrity != handoff.wo10_evidence_integrity
        or wo10_snapshot.probables_run_identity != handoff.probables_run_identity
        or wo10_snapshot.probables_run_integrity != handoff.probables_run_integrity
        or wo10_snapshot.probable_result_identity != handoff.probable_result_identity
        or wo10_snapshot.probable_result_integrity != handoff.probable_result_integrity
        or wo10_snapshot.policy != handoff.wo10_policy
    ):
        raise Wo13HandoffRejected(Wo13HandoffFailure.SOURCE_EVIDENCE_INVALID)

    mcx = _mcx_bindings(result, wo10_snapshot, mcx_evidence)
    pairs: list[tuple[object, object]] = [
        (current_pointer.pointer_identity, current_pointer.pointer_integrity),
        (request.request_identity, request.request_integrity),
        (request.handoff.handoff_identity, request.handoff.handoff_integrity),
        (evidence.evidence_identity, evidence.evidence_integrity),
        (result.result_identity, result.result_integrity),
        (eligibility.eligibility_identity, eligibility.eligibility_integrity),
        (wo10_snapshot.snapshot_identity, wo10_snapshot.snapshot_integrity),
        (setup_evidence.fact_identity, setup_evidence.fact_integrity),
        *zip(evidence.source_identities, evidence.source_integrities, strict=True),
    ]
    pairs.extend(
        (item.evidence_identity, item.evidence_integrity)
        for item in wo10_snapshot.source_references
    )
    if mcx_evidence is not None:
        pairs.append((mcx_evidence.evidence_identity, mcx_evidence.integrity_identity))
    ordered = _unique_pairs(pairs)
    values = {
        "wo12_pointer_identity": current_pointer.pointer_identity,
        "wo12_pointer_integrity": current_pointer.pointer_integrity,
        "wo12_request_identity": request.request_identity,
        "wo12_request_integrity": request.request_integrity,
        "wo12_evidence_identity": evidence.evidence_identity,
        "wo12_evidence_integrity": evidence.evidence_integrity,
        "wo12_result_identity": result.result_identity,
        "wo12_result_integrity": result.result_integrity,
        "wo12_eligibility_identity": eligibility.eligibility_identity,
        "wo12_eligibility_integrity": eligibility.eligibility_integrity,
        "wo12_classification": result.classification,
        "wo12_policy_identity": request.policy.policy_identity,
        "wo12_policy_version": request.policy.policy_version,
        "wo12_policy_checksum": request.policy.policy_checksum,
        "wo11_publication_identity": handoff.wo11_publication_identity,
        "wo11_publication_integrity": handoff.wo11_publication_integrity,
        "wo11_member_identity": handoff.wo11_member_identity,
        "wo11_member_integrity": handoff.wo11_member_integrity,
        "wo11_handoff_identity": handoff.wo11_handoff_identity,
        "wo11_handoff_integrity": handoff.wo11_handoff_integrity,
        "wo10_result_identity": handoff.wo10_result_identity,
        "wo10_result_integrity": handoff.wo10_result_integrity,
        "wo10_evidence_identity": handoff.wo10_evidence_identity,
        "wo10_evidence_integrity": handoff.wo10_evidence_integrity,
        "wo10_policy_identity": handoff.wo10_policy.policy_identity,
        "wo10_policy_version": handoff.wo10_policy.policy_version,
        "wo10_policy_checksum": handoff.wo10_policy.policy_checksum,
        "probables_run_identity": handoff.probables_run_identity,
        "probables_run_integrity": handoff.probables_run_integrity,
        "probable_result_identity": handoff.probable_result_identity,
        "probable_result_integrity": handoff.probable_result_integrity,
        "canonical_subject_identity": result.canonical_subject_identity,
        "market_family": result.market_family,
        "inherited_direction": result.inherited_direction,
        "setup_family": setup_family,
        "setup_evidence_identity": setup_evidence.fact_identity,
        "setup_evidence_integrity": setup_evidence.fact_integrity,
        "analysis_boundary": result.analysis_boundary,
        "phase": result.phase,
        "instrument_identity": wo10_snapshot.source_mapping_identity,
        "instrument_lineage_integrity": wo10_snapshot.snapshot_integrity,
        **mcx,
        "source_identities": tuple(item[0] for item in ordered),
        "source_integrities": tuple(item[1] for item in ordered),
        "predecessor_trade_plan_identity": predecessor_trade_plan_identity,
        "schema_identity": WO13_HANDOFF_IDENTITY,
        "schema_version": WO13_CONTRACT_VERSION,
        "authority": "ELIGIBILITY_HANDOFF_ONLY",
        "geometry_authority": False,
        "risk_authority": False,
        "entry_timing_authority": False,
        "sponsor_decision_authority": False,
        "execution_authority": False,
        "broker_authority": False,
    }
    return Wo13Step31Handoff(
        handoff_identity=_identity("INTRADAY-WO13-HANDOFF-", values),
        handoff_integrity=_identity("INTEGRITY-INTRADAY-WO13-HANDOFF-", values),
        **values,
    )


def _validate_wo12_chain(
    pointer: CurrentWo12PointerV2,
    request: Wo12RequestV2,
    evidence: Wo12EvidenceV2,
    result: Wo12ResultV2,
    eligibility: Wo13EligibilityRecordV2,
) -> None:
    pointer_fields = (
        pointer.request_identity == request.request_identity,
        pointer.request_integrity == request.request_integrity,
        pointer.result_identity == result.result_identity,
        pointer.result_integrity == result.result_integrity,
        pointer.eligibility_identity == eligibility.eligibility_identity,
        pointer.eligibility_integrity == eligibility.eligibility_integrity,
    )
    if not all(pointer_fields):
        historical = (
            pointer.request_identity != request.request_identity
            or pointer.result_identity != result.result_identity
        )
        raise Wo13HandoffRejected(
            Wo13HandoffFailure.WO12_SUPERSEDED
            if historical else Wo13HandoffFailure.WO12_NOT_CURRENT
        )
    if (
        evidence.request_identity != request.request_identity
        or evidence.request_integrity != request.request_integrity
        or result.request_identity != request.request_identity
        or result.request_integrity != request.request_integrity
        or result.evidence_identity != evidence.evidence_identity
        or result.evidence_integrity != evidence.evidence_integrity
        or eligibility.wo12_result_identity != result.result_identity
        or eligibility.wo12_result_integrity != result.result_integrity
        or result.policy != request.policy
    ):
        raise Wo13HandoffRejected(Wo13HandoffFailure.WO12_INTEGRITY_INVALID)


def _mcx_bindings(
    result: Wo12ResultV2,
    snapshot: Wo10EvidenceSnapshot,
    evidence: Wo10McxPolicyEvidence | None,
) -> dict[str, object]:
    empty = {
        "actual_contract_identity": None, "provider_symbol": None,
        "active_binding_identity": None, "active_binding_integrity": None,
        "active_binding_supersedes": None, "contract_expiry": None,
        "commissioning_publication_identity": None,
        "commissioning_publication_integrity": None,
        "commissioning_state": None, "roll_lineage_identity": None,
        "tick_size": None, "lot_size": None,
    }
    if result.market_family is not IntradayMarketFamily.MCX:
        if evidence is not None:
            raise Wo13HandoffRejected(Wo13HandoffFailure.MARKET_FAMILY_MISMATCH)
        return empty
    if evidence is None:
        raise Wo13HandoffRejected(Wo13HandoffFailure.MCX_ACTIVE_CONTRACT_MISMATCH)
    _require_integrity(evidence)
    active = evidence.active_derivative_binding
    publication = evidence.commissioning_publication
    location = evidence.structural_location
    extension = snapshot.family_extension
    if (
        type(active) is not ActiveDerivativeBindingArtifact
        or type(publication) is not McxCommissioningPublication
        or location is None
        or evidence.snapshot != snapshot
        or active.canonical_subject_id != result.canonical_subject_identity
        or active.observation_boundary != result.analysis_boundary
        or extension.actual_contract is None
        or extension.actual_contract.evidence_identity != active.binding_identity
        or extension.actual_contract.evidence_integrity != active.integrity_identity
        or active.active_binding.derivative_contract_id != location.actual_contract_identity
    ):
        raise Wo13HandoffRejected(Wo13HandoffFailure.MCX_ACTIVE_CONTRACT_MISMATCH)
    if (
        extension.roll_history is None
        or extension.roll_history.evidence_identity != location.roll_lineage_identity
    ):
        raise Wo13HandoffRejected(Wo13HandoffFailure.MCX_ROLL_LINEAGE_MISMATCH)
    commissioned = publication.subject(result.canonical_subject_identity)
    if (
        commissioned.state is not McxCommissioningState.COMMISSIONED
        or extension.commissioning_publication is None
        or extension.commissioning_publication.evidence_identity
        != publication.publication_identity
        or extension.commissioning_publication.evidence_integrity
        != publication.integrity_identity
    ):
        raise Wo13HandoffRejected(Wo13HandoffFailure.MCX_ACTIVE_CONTRACT_MISMATCH)
    return {
        "actual_contract_identity": active.active_binding.derivative_contract_id,
        "provider_symbol": active.provider_symbol,
        "active_binding_identity": active.binding_identity,
        "active_binding_integrity": active.integrity_identity,
        "active_binding_supersedes": active.active_binding.supersedes,
        "contract_expiry": active.contract_expiry,
        "commissioning_publication_identity": publication.publication_identity,
        "commissioning_publication_integrity": publication.integrity_identity,
        "commissioning_state": commissioned.state,
        "roll_lineage_identity": location.roll_lineage_identity,
        "tick_size": str(active.tick_size),
        "lot_size": active.lot_size,
    }


def _require_integrity(*values: object) -> None:
    try:
        if any(replace(value) != value for value in values):
            raise ValueError
    except Exception as exc:
        raise Wo13HandoffRejected(
            Wo13HandoffFailure.WO12_INTEGRITY_INVALID
        ) from exc


def _unique_pairs(pairs: Sequence[tuple[object, object]]) -> tuple[tuple[str, str], ...]:
    retained: dict[str, str] = {}
    for identity, integrity in pairs:
        if not _texts((identity, integrity)):
            raise Wo13HandoffRejected(Wo13HandoffFailure.SOURCE_EVIDENCE_INVALID)
        identity = str(identity)
        integrity = str(integrity)
        if identity in retained and retained[identity] != integrity:
            raise Wo13HandoffRejected(Wo13HandoffFailure.SOURCE_EVIDENCE_INVALID)
        retained[identity] = integrity
    return tuple(sorted(retained.items()))


def _without(value: object, *names: str) -> dict[str, object]:
    return {key: item for key, item in asdict(value).items() if key not in names}


def _identity(prefix: str, value: object) -> str:
    material = json.dumps(
        _normalize(value), sort_keys=True, separators=(",", ":")
    ).encode()
    return prefix + sha256(material).hexdigest().upper()


def _normalize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _normalize(asdict(value))
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    return value


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


def _texts(values: Sequence[object]) -> bool:
    return bool(values) and all(_text(item) for item in values)


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


__all__ = [
    "WO13_AUTHORITY", "WO13_CONTRACT_VERSION", "WO13_HANDOFF_IDENTITY",
    "WO13_POLICY_CHECKSUM", "WO13_POLICY_IDENTITY", "WO13_POLICY_VERSION",
    "Wo13HandoffFailure", "Wo13HandoffRejected", "Wo13SetupFamily",
    "Wo13Step31Handoff", "create_wo13_step31_handoff",
]
