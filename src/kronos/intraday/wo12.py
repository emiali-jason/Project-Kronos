"""Immutable core contracts for Intraday WO-12 KR-370 promotion."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import json
from typing import Mapping, Sequence

from kronos.intraday.completed_evidence import IntradayAnalysisPhase
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo10 import Wo10PolicyBinding, Wo10State
from kronos.intraday.wo11 import (
    Wo11DownstreamEligibility,
    Wo11DownstreamHandoffReference,
    Wo11Member,
    Wo11PromotionPublication,
)
from kronos.validation.kr370 import (
    KR370_OWNER_IDENTITY,
    KR370_PROMOTION_AUTHORITY,
    KR370_PROMOTION_CONTRACT_ID,
    KR370_PROMOTION_CONTRACT_VERSION,
    KR370_STATE_FAMILY_IDENTITY,
    Kr370AnalyticalClassification,
    Kr370CriterionState,
    classify_five_criteria,
)


WO12_CONTRACT_VERSION = "1.0.0"
WO12_POLICY_IDENTITY = "KRONOS-INTRADAY-WO12-KR370-POLICY-V1"
WO12_POLICY_VERSION = "1.0.0"
WO12_HANDOFF_IDENTITY = "KRONOS-INTRADAY-WO11-WO12-HANDOFF-V1"
WO12_REQUEST_IDENTITY = "KRONOS-INTRADAY-WO12-KR370-REQUEST-V1"
WO12_CRITERION_IDENTITY = "KRONOS-INTRADAY-WO12-KR370-CRITERION-V1"
WO12_EVIDENCE_IDENTITY = "KRONOS-INTRADAY-WO12-KR370-EVIDENCE-V1"
WO12_RESULT_IDENTITY = "KRONOS-INTRADAY-WO12-KR370-RESULT-V1"
WO12_WO13_ELIGIBILITY_IDENTITY = "KRONOS-INTRADAY-WO12-WO13-ELIGIBILITY-V1"
WO12_POINTER_IDENTITY = "KRONOS-INTRADAY-CURRENT-WO12-KR370-POINTER-V1"
WO12_OPERATION_IDENTITY = "KRONOS-INTRADAY-WO12-KR370-OPERATION-PROVENANCE-V1"
WO12_MATERIAL_EXTENSION_THRESHOLD = "POLICY_UNRESOLVED"


class Wo12ContractError(ValueError):
    """Sanitized WO-12 contract or exact-binding failure."""


class Wo12CriterionIdentity(StrEnum):
    K1_15M_DIRECTIONAL_PROGRESSION = "K1_15M_DIRECTIONAL_PROGRESSION"
    K2_15M_CPR_ACCEPTANCE = "K2_15M_CPR_ACCEPTANCE"
    K3_15M_IMMEDIATE_PATH_CLEARANCE = "K3_15M_IMMEDIATE_PATH_CLEARANCE"
    K4_15M_SETUP_QUALITY = "K4_15M_SETUP_QUALITY"
    K5_15M_NON_EXTENSION = "K5_15M_NON_EXTENSION"


class Wo12HardGate(StrEnum):
    INVALID_EXACT_EVIDENCE_BINDING = "INVALID_EXACT_EVIDENCE_BINDING"
    MANDATORY_K_UNAVAILABLE = "MANDATORY_K_UNAVAILABLE"
    GOVERNING_15M_STRUCTURE_FAILED = "GOVERNING_15M_STRUCTURE_FAILED"
    AUTHORITATIVE_GOVERNED_DIRECTIONAL_CONFLICT = (
        "AUTHORITATIVE_GOVERNED_DIRECTIONAL_CONFLICT"
    )


class Wo13Eligibility(StrEnum):
    ELIGIBLE_FOR_WO13_STEP31 = "ELIGIBLE_FOR_WO13_STEP31"
    NOT_ELIGIBLE_FOR_WO13_STEP31 = "NOT_ELIGIBLE_FOR_WO13_STEP31"


class Wo12OperationStage(StrEnum):
    REQUEST_VALIDATION = "REQUEST_VALIDATION"
    WO11_WO10_RELOAD = "WO11_WO10_RELOAD"
    EVIDENCE_ASSEMBLY = "EVIDENCE_ASSEMBLY"
    CLASSIFICATION = "CLASSIFICATION"
    PERSISTENCE = "PERSISTENCE"
    POINTER_PUBLICATION = "POINTER_PUBLICATION"


class Wo12OperationOutcome(StrEnum):
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


_POLICY_DOCUMENT = {
    "contract": KR370_PROMOTION_CONTRACT_ID,
    "contract_version": KR370_PROMOTION_CONTRACT_VERSION,
    "state_family": KR370_STATE_FAMILY_IDENTITY,
    "criteria": tuple(item.value for item in Wo12CriterionIdentity),
    "criterion_states": tuple(item.value for item in Kr370CriterionState),
    "hard_gates": tuple(item.value for item in Wo12HardGate),
    "timeframe": "15M",
    "five_minute_authority": "NONE_WO15_KR380_ONLY",
    "material_extension_threshold": WO12_MATERIAL_EXTENSION_THRESHOLD,
    "authority": KR370_PROMOTION_AUTHORITY,
}
WO12_POLICY_CHECKSUM = sha256(json.dumps(
    _POLICY_DOCUMENT, sort_keys=True, separators=(",", ":")
).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class Wo12PolicyBinding:
    policy_identity: str = WO12_POLICY_IDENTITY
    policy_version: str = WO12_POLICY_VERSION
    policy_checksum: str = WO12_POLICY_CHECKSUM
    common_contract_identity: str = KR370_PROMOTION_CONTRACT_ID
    common_contract_version: str = KR370_PROMOTION_CONTRACT_VERSION
    state_family_identity: str = KR370_STATE_FAMILY_IDENTITY
    owner_identity: str = KR370_OWNER_IDENTITY
    authority: str = KR370_PROMOTION_AUTHORITY
    material_extension_threshold: str = WO12_MATERIAL_EXTENSION_THRESHOLD

    def __post_init__(self) -> None:
        if (
            self.policy_identity != WO12_POLICY_IDENTITY
            or self.policy_version != WO12_POLICY_VERSION
            or self.policy_checksum != WO12_POLICY_CHECKSUM
            or self.common_contract_identity != KR370_PROMOTION_CONTRACT_ID
            or self.common_contract_version != KR370_PROMOTION_CONTRACT_VERSION
            or self.state_family_identity != KR370_STATE_FAMILY_IDENTITY
            or self.owner_identity != KR370_OWNER_IDENTITY
            or self.authority != KR370_PROMOTION_AUTHORITY
            or self.material_extension_threshold != WO12_MATERIAL_EXTENSION_THRESHOLD
        ):
            raise Wo12ContractError("WO12_POLICY_BINDING_INVALID")


@dataclass(frozen=True, slots=True)
class Wo12Handoff:
    handoff_identity: str
    handoff_integrity: str
    wo11_publication_identity: str
    wo11_publication_integrity: str
    wo11_member_identity: str
    wo11_member_integrity: str
    wo11_handoff_identity: str
    wo11_handoff_integrity: str
    wo11_downstream_eligibility: Wo11DownstreamEligibility
    wo10_result_identity: str
    wo10_result_integrity: str
    wo10_evidence_identity: str
    wo10_evidence_integrity: str
    wo10_policy: Wo10PolicyBinding
    probables_run_identity: str
    probables_run_integrity: str
    probable_result_identity: str
    probable_result_integrity: str
    canonical_subject_identity: str
    market_family: IntradayMarketFamily
    inherited_direction: SemanticDirection
    analysis_boundary: datetime
    phase: IntradayAnalysisPhase
    source_integrities: tuple[str, ...]
    schema_identity: str = WO12_HANDOFF_IDENTITY
    schema_version: str = WO12_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "handoff_identity", "handoff_integrity")
        if (
            not _texts((
                self.wo11_publication_identity,
                self.wo11_publication_integrity,
                self.wo11_member_identity,
                self.wo11_member_integrity,
                self.wo11_handoff_identity,
                self.wo11_handoff_integrity,
                self.wo10_result_identity,
                self.wo10_result_integrity,
                self.wo10_evidence_identity,
                self.wo10_evidence_integrity,
                self.probables_run_identity,
                self.probables_run_integrity,
                self.probable_result_identity,
                self.probable_result_integrity,
                self.canonical_subject_identity,
            ))
            or self.wo11_downstream_eligibility
            is not Wo11DownstreamEligibility.ELIGIBLE_FOR_DOWNSTREAM_HANDOFF
            or type(self.wo10_policy) is not Wo10PolicyBinding
            or self.wo10_policy.supported_market_family is not self.market_family
            or type(self.market_family) is not IntradayMarketFamily
            or self.inherited_direction not in {
                SemanticDirection.LONG,
                SemanticDirection.SHORT,
            }
            or not _aware(self.analysis_boundary)
            or type(self.phase) is not IntradayAnalysisPhase
            or not _texts(self.source_integrities)
            or len(set(self.source_integrities)) != len(self.source_integrities)
            or self.schema_identity != WO12_HANDOFF_IDENTITY
            or self.schema_version != WO12_CONTRACT_VERSION
            or self.handoff_identity != _identity("INTRADAY-WO12-HANDOFF-V1-", values)
            or self.handoff_integrity
            != _identity("INTEGRITY-INTRADAY-WO12-HANDOFF-V1-", values)
        ):
            raise Wo12ContractError("WO12_HANDOFF_INVALID")


def create_wo12_handoff(
    *,
    publication: Wo11PromotionPublication,
    member: Wo11Member,
    wo11_handoff: Wo11DownstreamHandoffReference,
) -> Wo12Handoff:
    binding = next((
        item for item in publication.member_bindings
        if item.member_identity == member.member_identity
    ), None)
    if (
        type(publication) is not Wo11PromotionPublication
        or type(member) is not Wo11Member
        or type(wo11_handoff) is not Wo11DownstreamHandoffReference
        or binding is None
        or binding.member_integrity != member.member_integrity
        or binding.canonical_subject_identity != member.canonical_subject_identity
        or binding.market_family is not member.market_family
        or member.wo10_state is not Wo10State.PROMOTION_READY
        or member.downstream_eligibility
        is not Wo11DownstreamEligibility.ELIGIBLE_FOR_DOWNSTREAM_HANDOFF
        or wo11_handoff.publication_identity != publication.publication_identity
        or wo11_handoff.publication_integrity != publication.publication_integrity
        or wo11_handoff.member_identity != member.member_identity
        or wo11_handoff.member_integrity != member.member_integrity
        or wo11_handoff.wo10_result_identity != member.wo10_result_identity
        or wo11_handoff.wo10_result_integrity != member.wo10_result_integrity
        or wo11_handoff.canonical_subject_identity != member.canonical_subject_identity
        or wo11_handoff.inherited_direction is not member.inherited_direction
    ):
        raise Wo12ContractError("WO12_HANDOFF_INPUT_INVALID")
    values = {
        "wo11_publication_identity": publication.publication_identity,
        "wo11_publication_integrity": publication.publication_integrity,
        "wo11_member_identity": member.member_identity,
        "wo11_member_integrity": member.member_integrity,
        "wo11_handoff_identity": wo11_handoff.handoff_identity,
        "wo11_handoff_integrity": wo11_handoff.handoff_integrity,
        "wo11_downstream_eligibility": member.downstream_eligibility,
        "wo10_result_identity": member.wo10_result_identity,
        "wo10_result_integrity": member.wo10_result_integrity,
        "wo10_evidence_identity": member.evidence_snapshot_identity,
        "wo10_evidence_integrity": member.evidence_snapshot_integrity,
        "wo10_policy": member.wo10_policy,
        "probables_run_identity": member.source_probables_run_identity,
        "probables_run_integrity": member.source_probables_run_integrity,
        "probable_result_identity": member.source_probable_result_identity,
        "probable_result_integrity": member.source_probable_result_integrity,
        "canonical_subject_identity": member.canonical_subject_identity,
        "market_family": member.market_family,
        "inherited_direction": member.inherited_direction,
        "analysis_boundary": member.analysis_boundary,
        "phase": member.persisted_phase,
        "source_integrities": tuple(sorted({
            publication.publication_integrity,
            member.member_integrity,
            wo11_handoff.handoff_integrity,
            member.wo10_result_integrity,
            member.evidence_snapshot_integrity,
            member.source_probables_run_integrity,
            member.source_probable_result_integrity,
            member.wo10_policy.integrity_identity,
        })),
        "schema_identity": WO12_HANDOFF_IDENTITY,
        "schema_version": WO12_CONTRACT_VERSION,
    }
    return Wo12Handoff(
        handoff_identity=_identity("INTRADAY-WO12-HANDOFF-V1-", values),
        handoff_integrity=_identity("INTEGRITY-INTRADAY-WO12-HANDOFF-V1-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo12Request:
    request_identity: str
    request_integrity: str
    handoff: Wo12Handoff
    policy: Wo12PolicyBinding
    requested_at: datetime
    sponsor_operation_identity: str
    provenance: tuple[str, ...]
    schema_identity: str = WO12_REQUEST_IDENTITY
    schema_version: str = WO12_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "request_identity", "request_integrity")
        if (
            type(self.handoff) is not Wo12Handoff
            or type(self.policy) is not Wo12PolicyBinding
            or not _aware(self.requested_at)
            or not _text(self.sponsor_operation_identity)
            or not _texts(self.provenance)
            or self.schema_identity != WO12_REQUEST_IDENTITY
            or self.schema_version != WO12_CONTRACT_VERSION
            or self.request_identity != _identity("INTRADAY-WO12-REQUEST-V1-", values)
            or self.request_integrity
            != _identity("INTEGRITY-INTRADAY-WO12-REQUEST-V1-", values)
        ):
            raise Wo12ContractError("WO12_REQUEST_INVALID")


def create_wo12_request(
    *,
    handoff: Wo12Handoff,
    requested_at: datetime,
    sponsor_operation_identity: str,
    provenance: tuple[str, ...],
) -> Wo12Request:
    values = {
        "handoff": handoff,
        "policy": Wo12PolicyBinding(),
        "requested_at": requested_at,
        "sponsor_operation_identity": sponsor_operation_identity,
        "provenance": provenance,
        "schema_identity": WO12_REQUEST_IDENTITY,
        "schema_version": WO12_CONTRACT_VERSION,
    }
    return Wo12Request(
        request_identity=_identity("INTRADAY-WO12-REQUEST-V1-", values),
        request_integrity=_identity("INTEGRITY-INTRADAY-WO12-REQUEST-V1-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo12CriterionResult:
    identity: Wo12CriterionIdentity
    state: Kr370CriterionState
    reason: str
    evidence_identities: tuple[str, ...]
    evidence_integrities: tuple[str, ...]
    schema_identity: str = WO12_CRITERION_IDENTITY
    schema_version: str = WO12_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            type(self.identity) is not Wo12CriterionIdentity
            or type(self.state) is not Kr370CriterionState
            or not _code(self.reason)
            or not _texts(self.evidence_identities)
            or not _texts(self.evidence_integrities)
            or len(self.evidence_identities) != len(self.evidence_integrities)
            or self.schema_identity != WO12_CRITERION_IDENTITY
            or self.schema_version != WO12_CONTRACT_VERSION
        ):
            raise Wo12ContractError("WO12_CRITERION_INVALID")


@dataclass(frozen=True, slots=True)
class Wo12Evidence:
    evidence_identity: str
    evidence_integrity: str
    request_identity: str
    request_integrity: str
    handoff_identity: str
    handoff_integrity: str
    canonical_subject_identity: str
    market_family: IntradayMarketFamily
    inherited_direction: SemanticDirection
    analysis_boundary: datetime
    phase: IntradayAnalysisPhase
    criteria: tuple[Wo12CriterionResult, ...]
    exact_binding_valid: bool
    governing_15m_structure_failed: bool
    authoritative_directional_conflict: bool
    extension_measurement_identity: str | None
    extension_measurement_integrity: str | None
    source_identities: tuple[str, ...]
    source_integrities: tuple[str, ...]
    schema_identity: str = WO12_EVIDENCE_IDENTITY
    schema_version: str = WO12_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "evidence_identity", "evidence_integrity")
        if (
            not _texts((
                self.request_identity,
                self.request_integrity,
                self.handoff_identity,
                self.handoff_integrity,
                self.canonical_subject_identity,
            ))
            or type(self.market_family) is not IntradayMarketFamily
            or self.inherited_direction not in {
                SemanticDirection.LONG,
                SemanticDirection.SHORT,
            }
            or not _aware(self.analysis_boundary)
            or type(self.phase) is not IntradayAnalysisPhase
            or tuple(item.identity for item in self.criteria)
            != tuple(Wo12CriterionIdentity)
            or any(type(item) is not Wo12CriterionResult for item in self.criteria)
            or type(self.exact_binding_valid) is not bool
            or type(self.governing_15m_structure_failed) is not bool
            or type(self.authoritative_directional_conflict) is not bool
            or (self.extension_measurement_identity is None)
            != (self.extension_measurement_integrity is None)
            or not _texts(self.source_identities)
            or not _texts(self.source_integrities)
            or len(self.source_identities) != len(self.source_integrities)
            or self.schema_identity != WO12_EVIDENCE_IDENTITY
            or self.schema_version != WO12_CONTRACT_VERSION
            or self.evidence_identity != _identity("INTRADAY-WO12-EVIDENCE-V1-", values)
            or self.evidence_integrity
            != _identity("INTEGRITY-INTRADAY-WO12-EVIDENCE-V1-", values)
        ):
            raise Wo12ContractError("WO12_EVIDENCE_INVALID")


def create_wo12_evidence(
    *,
    request: Wo12Request,
    criteria: Sequence[Wo12CriterionResult],
    exact_binding_valid: bool,
    governing_15m_structure_failed: bool,
    authoritative_directional_conflict: bool,
    extension_measurement_identity: str | None,
    extension_measurement_integrity: str | None,
) -> Wo12Evidence:
    retained = tuple(criteria)
    if type(request) is not Wo12Request:
        raise Wo12ContractError("WO12_EVIDENCE_INPUT_INVALID")
    pairs = tuple(
        (identity, integrity)
        for item in retained
        for identity, integrity in zip(
            item.evidence_identities,
            item.evidence_integrities,
            strict=True,
        )
    )
    values = {
        "request_identity": request.request_identity,
        "request_integrity": request.request_integrity,
        "handoff_identity": request.handoff.handoff_identity,
        "handoff_integrity": request.handoff.handoff_integrity,
        "canonical_subject_identity": request.handoff.canonical_subject_identity,
        "market_family": request.handoff.market_family,
        "inherited_direction": request.handoff.inherited_direction,
        "analysis_boundary": request.handoff.analysis_boundary,
        "phase": request.handoff.phase,
        "criteria": retained,
        "exact_binding_valid": exact_binding_valid,
        "governing_15m_structure_failed": governing_15m_structure_failed,
        "authoritative_directional_conflict": authoritative_directional_conflict,
        "extension_measurement_identity": extension_measurement_identity,
        "extension_measurement_integrity": extension_measurement_integrity,
        "source_identities": tuple(item[0] for item in pairs),
        "source_integrities": tuple(item[1] for item in pairs),
        "schema_identity": WO12_EVIDENCE_IDENTITY,
        "schema_version": WO12_CONTRACT_VERSION,
    }
    return Wo12Evidence(
        evidence_identity=_identity("INTRADAY-WO12-EVIDENCE-V1-", values),
        evidence_integrity=_identity("INTEGRITY-INTRADAY-WO12-EVIDENCE-V1-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo12Result:
    result_identity: str
    result_integrity: str
    request_identity: str
    request_integrity: str
    handoff_identity: str
    handoff_integrity: str
    evidence_identity: str
    evidence_integrity: str
    canonical_subject_identity: str
    market_family: IntradayMarketFamily
    inherited_direction: SemanticDirection
    analysis_boundary: datetime
    phase: IntradayAnalysisPhase
    criteria: tuple[Wo12CriterionResult, ...]
    satisfied_count: int
    unavailable_criteria: tuple[Wo12CriterionIdentity, ...]
    hard_gates: tuple[Wo12HardGate, ...]
    classification: Kr370AnalyticalClassification
    policy: Wo12PolicyBinding
    created_at: datetime
    provenance: tuple[str, ...]
    owner_identity: str = KR370_OWNER_IDENTITY
    state_family_identity: str = KR370_STATE_FAMILY_IDENTITY
    common_contract_identity: str = KR370_PROMOTION_CONTRACT_ID
    common_contract_version: str = KR370_PROMOTION_CONTRACT_VERSION
    authority: str = KR370_PROMOTION_AUTHORITY
    schema_identity: str = WO12_RESULT_IDENTITY
    schema_version: str = WO12_CONTRACT_VERSION
    entry_authority: bool = False
    geometry_authority: bool = False
    risk_authority: bool = False
    sponsor_decision_authority: bool = False
    entry_timing_authority: bool = False
    execution_authority: bool = False
    broker_authority: bool = False

    def __post_init__(self) -> None:
        values = _without(self, "result_identity", "result_integrity")
        unavailable = tuple(
            item.identity for item in self.criteria
            if item.state is Kr370CriterionState.UNAVAILABLE
        )
        expected_classification = None
        if not self.hard_gates and not unavailable:
            try:
                expected_classification, _, _ = classify_five_criteria(
                    self.inherited_direction.value,
                    tuple(item.state for item in self.criteria),
                )
            except (AttributeError, ValueError):
                expected_classification = None
        if (
            not _texts((
                self.request_identity,
                self.request_integrity,
                self.handoff_identity,
                self.handoff_integrity,
                self.evidence_identity,
                self.evidence_integrity,
                self.canonical_subject_identity,
            ))
            or type(self.market_family) is not IntradayMarketFamily
            or self.inherited_direction not in {
                SemanticDirection.LONG,
                SemanticDirection.SHORT,
            }
            or not _aware(self.analysis_boundary)
            or type(self.phase) is not IntradayAnalysisPhase
            or tuple(item.identity for item in self.criteria)
            != tuple(Wo12CriterionIdentity)
            or self.satisfied_count
            != sum(item.state is Kr370CriterionState.SATISFIED for item in self.criteria)
            or self.unavailable_criteria != unavailable
            or any(type(item) is not Wo12HardGate for item in self.hard_gates)
            or tuple(sorted(set(self.hard_gates), key=tuple(Wo12HardGate).index))
            != self.hard_gates
            or (
                (Wo12HardGate.MANDATORY_K_UNAVAILABLE in self.hard_gates)
                is not bool(unavailable)
            )
            or type(self.classification) is not Kr370AnalyticalClassification
            or (
                self.classification
                is not (
                    Kr370AnalyticalClassification.NO_SETUP
                    if self.hard_gates
                    else expected_classification
                )
            )
            or type(self.policy) is not Wo12PolicyBinding
            or not _aware(self.created_at)
            or not _texts(self.provenance)
            or self.owner_identity != KR370_OWNER_IDENTITY
            or self.state_family_identity != KR370_STATE_FAMILY_IDENTITY
            or self.common_contract_identity != KR370_PROMOTION_CONTRACT_ID
            or self.common_contract_version != KR370_PROMOTION_CONTRACT_VERSION
            or self.authority != KR370_PROMOTION_AUTHORITY
            or self.schema_identity != WO12_RESULT_IDENTITY
            or self.schema_version != WO12_CONTRACT_VERSION
            or any((
                self.entry_authority,
                self.geometry_authority,
                self.risk_authority,
                self.sponsor_decision_authority,
                self.entry_timing_authority,
                self.execution_authority,
                self.broker_authority,
            ))
            or self.result_identity != _identity("INTRADAY-WO12-RESULT-V1-", values)
            or self.result_integrity
            != _identity("INTEGRITY-INTRADAY-WO12-RESULT-V1-", values)
        ):
            raise Wo12ContractError("WO12_RESULT_INVALID")


def classify_wo12(
    direction: SemanticDirection,
    criteria: Sequence[Wo12CriterionResult],
) -> tuple[Kr370AnalyticalClassification, int, int]:
    retained = tuple(criteria)
    if (
        direction not in {SemanticDirection.LONG, SemanticDirection.SHORT}
        or tuple(item.identity for item in retained) != tuple(Wo12CriterionIdentity)
    ):
        raise Wo12ContractError("WO12_CLASSIFICATION_INPUT_INVALID")
    try:
        return classify_five_criteria(
            direction.value,
            tuple(item.state for item in retained),
        )
    except ValueError as error:
        raise Wo12ContractError("WO12_CLASSIFICATION_INPUT_INVALID") from error


def create_wo12_result(
    *,
    request: Wo12Request,
    evidence: Wo12Evidence,
    created_at: datetime,
    provenance: tuple[str, ...],
) -> Wo12Result:
    if (
        type(request) is not Wo12Request
        or type(evidence) is not Wo12Evidence
        or evidence.request_identity != request.request_identity
        or evidence.request_integrity != request.request_integrity
        or evidence.handoff_identity != request.handoff.handoff_identity
        or evidence.handoff_integrity != request.handoff.handoff_integrity
        or evidence.canonical_subject_identity != request.handoff.canonical_subject_identity
        or evidence.market_family is not request.handoff.market_family
        or evidence.inherited_direction is not request.handoff.inherited_direction
        or evidence.analysis_boundary != request.handoff.analysis_boundary
        or evidence.phase is not request.handoff.phase
        or not _aware(created_at)
        or not _texts(provenance)
    ):
        raise Wo12ContractError("WO12_RESULT_INPUT_INVALID")
    gates: list[Wo12HardGate] = []
    if not evidence.exact_binding_valid:
        gates.append(Wo12HardGate.INVALID_EXACT_EVIDENCE_BINDING)
    unavailable = tuple(
        item.identity for item in evidence.criteria
        if item.state is Kr370CriterionState.UNAVAILABLE
    )
    if unavailable:
        gates.append(Wo12HardGate.MANDATORY_K_UNAVAILABLE)
    if evidence.governing_15m_structure_failed:
        gates.append(Wo12HardGate.GOVERNING_15M_STRUCTURE_FAILED)
    if evidence.authoritative_directional_conflict:
        gates.append(Wo12HardGate.AUTHORITATIVE_GOVERNED_DIRECTIONAL_CONFLICT)
    if gates:
        classification = Kr370AnalyticalClassification.NO_SETUP
        satisfied = sum(
            item.state is Kr370CriterionState.SATISFIED for item in evidence.criteria
        )
    else:
        classification, satisfied, _ = classify_wo12(
            evidence.inherited_direction,
            evidence.criteria,
        )
    values = {
        "request_identity": request.request_identity,
        "request_integrity": request.request_integrity,
        "handoff_identity": request.handoff.handoff_identity,
        "handoff_integrity": request.handoff.handoff_integrity,
        "evidence_identity": evidence.evidence_identity,
        "evidence_integrity": evidence.evidence_integrity,
        "canonical_subject_identity": evidence.canonical_subject_identity,
        "market_family": evidence.market_family,
        "inherited_direction": evidence.inherited_direction,
        "analysis_boundary": evidence.analysis_boundary,
        "phase": evidence.phase,
        "criteria": evidence.criteria,
        "satisfied_count": satisfied,
        "unavailable_criteria": unavailable,
        "hard_gates": tuple(gates),
        "classification": classification,
        "policy": request.policy,
        "created_at": created_at,
        "provenance": provenance,
        "owner_identity": KR370_OWNER_IDENTITY,
        "state_family_identity": KR370_STATE_FAMILY_IDENTITY,
        "common_contract_identity": KR370_PROMOTION_CONTRACT_ID,
        "common_contract_version": KR370_PROMOTION_CONTRACT_VERSION,
        "authority": KR370_PROMOTION_AUTHORITY,
        "schema_identity": WO12_RESULT_IDENTITY,
        "schema_version": WO12_CONTRACT_VERSION,
        "entry_authority": False,
        "geometry_authority": False,
        "risk_authority": False,
        "sponsor_decision_authority": False,
        "entry_timing_authority": False,
        "execution_authority": False,
        "broker_authority": False,
    }
    return Wo12Result(
        result_identity=_identity("INTRADAY-WO12-RESULT-V1-", values),
        result_integrity=_identity("INTEGRITY-INTRADAY-WO12-RESULT-V1-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo13EligibilityRecord:
    eligibility_identity: str
    eligibility_integrity: str
    wo12_result_identity: str
    wo12_result_integrity: str
    canonical_subject_identity: str
    inherited_direction: SemanticDirection
    classification: Kr370AnalyticalClassification
    eligibility: Wo13Eligibility
    analysis_boundary: datetime
    provenance: tuple[str, ...]
    schema_identity: str = WO12_WO13_ELIGIBILITY_IDENTITY
    schema_version: str = WO12_CONTRACT_VERSION
    geometry_authority: bool = False
    risk_authority: bool = False
    execution_authority: bool = False
    broker_authority: bool = False

    def __post_init__(self) -> None:
        values = _without(self, "eligibility_identity", "eligibility_integrity")
        expected = (
            Wo13Eligibility.ELIGIBLE_FOR_WO13_STEP31
            if self.classification in {
                Kr370AnalyticalClassification.BUY_NOW,
                Kr370AnalyticalClassification.SELL_NOW,
            }
            else Wo13Eligibility.NOT_ELIGIBLE_FOR_WO13_STEP31
        )
        direction_valid = (
            self.classification
            in {
                Kr370AnalyticalClassification.BUY_NOW,
                Kr370AnalyticalClassification.BUY_READY,
                Kr370AnalyticalClassification.POTENTIAL_BUY_SETUP,
            }
            and self.inherited_direction is SemanticDirection.LONG
        ) or (
            self.classification
            in {
                Kr370AnalyticalClassification.SELL_NOW,
                Kr370AnalyticalClassification.SELL_READY,
                Kr370AnalyticalClassification.POTENTIAL_SELL_SETUP,
            }
            and self.inherited_direction is SemanticDirection.SHORT
        ) or self.classification is Kr370AnalyticalClassification.NO_SETUP
        if (
            not _texts((
                self.wo12_result_identity,
                self.wo12_result_integrity,
                self.canonical_subject_identity,
            ))
            or self.inherited_direction not in {
                SemanticDirection.LONG,
                SemanticDirection.SHORT,
            }
            or type(self.classification) is not Kr370AnalyticalClassification
            or not direction_valid
            or self.eligibility is not expected
            or not _aware(self.analysis_boundary)
            or not _texts(self.provenance)
            or self.schema_identity != WO12_WO13_ELIGIBILITY_IDENTITY
            or self.schema_version != WO12_CONTRACT_VERSION
            or any((
                self.geometry_authority,
                self.risk_authority,
                self.execution_authority,
                self.broker_authority,
            ))
            or self.eligibility_identity
            != _identity("INTRADAY-WO13-ELIGIBILITY-V1-", values)
            or self.eligibility_integrity
            != _identity("INTEGRITY-INTRADAY-WO13-ELIGIBILITY-V1-", values)
        ):
            raise Wo12ContractError("WO13_ELIGIBILITY_INVALID")


def create_wo13_eligibility(
    result: Wo12Result,
    *,
    provenance: tuple[str, ...],
) -> Wo13EligibilityRecord:
    if type(result) is not Wo12Result or not _texts(provenance):
        raise Wo12ContractError("WO13_ELIGIBILITY_INPUT_INVALID")
    values = {
        "wo12_result_identity": result.result_identity,
        "wo12_result_integrity": result.result_integrity,
        "canonical_subject_identity": result.canonical_subject_identity,
        "inherited_direction": result.inherited_direction,
        "classification": result.classification,
        "eligibility": (
            Wo13Eligibility.ELIGIBLE_FOR_WO13_STEP31
            if result.classification in {
                Kr370AnalyticalClassification.BUY_NOW,
                Kr370AnalyticalClassification.SELL_NOW,
            }
            else Wo13Eligibility.NOT_ELIGIBLE_FOR_WO13_STEP31
        ),
        "analysis_boundary": result.analysis_boundary,
        "provenance": provenance,
        "schema_identity": WO12_WO13_ELIGIBILITY_IDENTITY,
        "schema_version": WO12_CONTRACT_VERSION,
        "geometry_authority": False,
        "risk_authority": False,
        "execution_authority": False,
        "broker_authority": False,
    }
    return Wo13EligibilityRecord(
        eligibility_identity=_identity("INTRADAY-WO13-ELIGIBILITY-V1-", values),
        eligibility_integrity=_identity(
            "INTEGRITY-INTRADAY-WO13-ELIGIBILITY-V1-", values
        ),
        **values,
    )


@dataclass(frozen=True, slots=True)
class CurrentWo12Pointer:
    pointer_identity: str
    pointer_integrity: str
    request_identity: str
    request_integrity: str
    result_identity: str
    result_integrity: str
    eligibility_identity: str
    eligibility_integrity: str
    schema_identity: str = WO12_POINTER_IDENTITY
    schema_version: str = WO12_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "pointer_identity", "pointer_integrity")
        if (
            not _texts((
                self.request_identity,
                self.request_integrity,
                self.result_identity,
                self.result_integrity,
                self.eligibility_identity,
                self.eligibility_integrity,
            ))
            or self.schema_identity != WO12_POINTER_IDENTITY
            or self.schema_version != WO12_CONTRACT_VERSION
            or self.pointer_identity != _identity("CURRENT-INTRADAY-WO12-V1-", values)
            or self.pointer_integrity
            != _identity("INTEGRITY-CURRENT-INTRADAY-WO12-V1-", values)
        ):
            raise Wo12ContractError("WO12_POINTER_INVALID")


def create_current_wo12_pointer(
    request: Wo12Request,
    result: Wo12Result,
    eligibility: Wo13EligibilityRecord,
) -> CurrentWo12Pointer:
    if (
        type(request) is not Wo12Request
        or type(result) is not Wo12Result
        or type(eligibility) is not Wo13EligibilityRecord
        or result.request_identity != request.request_identity
        or result.request_integrity != request.request_integrity
        or eligibility.wo12_result_identity != result.result_identity
        or eligibility.wo12_result_integrity != result.result_integrity
    ):
        raise Wo12ContractError("WO12_POINTER_INPUT_INVALID")
    values = {
        "request_identity": request.request_identity,
        "request_integrity": request.request_integrity,
        "result_identity": result.result_identity,
        "result_integrity": result.result_integrity,
        "eligibility_identity": eligibility.eligibility_identity,
        "eligibility_integrity": eligibility.eligibility_integrity,
        "schema_identity": WO12_POINTER_IDENTITY,
        "schema_version": WO12_CONTRACT_VERSION,
    }
    return CurrentWo12Pointer(
        pointer_identity=_identity("CURRENT-INTRADAY-WO12-V1-", values),
        pointer_integrity=_identity("INTEGRITY-CURRENT-INTRADAY-WO12-V1-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo12OperationProvenance:
    operation_identity: str
    operation_integrity: str
    request_identity: str
    request_integrity: str
    stage: Wo12OperationStage
    outcome: Wo12OperationOutcome
    started_at: datetime
    completed_at: datetime | None
    failed_at: datetime | None
    result_identity: str | None
    failure_reason: str | None
    provenance: tuple[str, ...]
    schema_identity: str = WO12_OPERATION_IDENTITY
    schema_version: str = WO12_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "operation_identity", "operation_integrity")
        completed = self.outcome is Wo12OperationOutcome.COMPLETED
        failed = self.outcome is Wo12OperationOutcome.FAILED
        if (
            not _texts((self.request_identity, self.request_integrity))
            or type(self.stage) is not Wo12OperationStage
            or type(self.outcome) is not Wo12OperationOutcome
            or not _aware(self.started_at)
            or (self.completed_at is not None and not _aware(self.completed_at))
            or (self.failed_at is not None and not _aware(self.failed_at))
            or completed != (self.completed_at is not None)
            or completed != (self.result_identity is not None)
            or failed != (self.failed_at is not None)
            or failed != (self.failure_reason is not None)
            or not _texts(self.provenance)
            or self.schema_identity != WO12_OPERATION_IDENTITY
            or self.schema_version != WO12_CONTRACT_VERSION
            or self.operation_identity != _identity("INTRADAY-WO12-OPERATION-V1-", values)
            or self.operation_integrity
            != _identity("INTEGRITY-INTRADAY-WO12-OPERATION-V1-", values)
        ):
            raise Wo12ContractError("WO12_OPERATION_INVALID")


def create_wo12_operation_provenance(
    *,
    request: Wo12Request,
    stage: Wo12OperationStage,
    outcome: Wo12OperationOutcome,
    started_at: datetime,
    completed_at: datetime | None = None,
    failed_at: datetime | None = None,
    result: Wo12Result | None = None,
    failure_reason: str | None = None,
    provenance: tuple[str, ...],
) -> Wo12OperationProvenance:
    values = {
        "request_identity": request.request_identity,
        "request_integrity": request.request_integrity,
        "stage": stage,
        "outcome": outcome,
        "started_at": started_at,
        "completed_at": completed_at,
        "failed_at": failed_at,
        "result_identity": None if result is None else result.result_identity,
        "failure_reason": failure_reason,
        "provenance": provenance,
        "schema_identity": WO12_OPERATION_IDENTITY,
        "schema_version": WO12_CONTRACT_VERSION,
    }
    return Wo12OperationProvenance(
        operation_identity=_identity("INTRADAY-WO12-OPERATION-V1-", values),
        operation_integrity=_identity("INTEGRITY-INTRADAY-WO12-OPERATION-V1-", values),
        **values,
    )


def _without(value: object, *names: str) -> dict[str, object]:
    return {name: item for name, item in asdict(value).items() if name not in names}


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(json.dumps(
        _normalize(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()).hexdigest().upper()


def _normalize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _normalize(asdict(value))
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(name): _normalize(item) for name, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    return value


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


def _texts(values: Sequence[object]) -> bool:
    retained = tuple(values)
    return bool(retained) and all(_text(item) for item in retained)


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _code(value: object) -> bool:
    return _text(value) and str(value).replace("_", "").isalnum() and str(value).upper() == value


__all__ = [
    name for name in globals()
    if name.startswith("WO12_")
    or name.startswith("Wo12")
    or name.startswith("Wo13")
    or name.startswith("CurrentWo12")
    or name.startswith("create_wo12")
    or name.startswith("create_wo13")
    or name == "classify_wo12"
]
