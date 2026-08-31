"""Current Intraday WO-12 V2 four-criterion KR-370 contracts."""

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
from kronos.intraday.wo12 import (
    Wo12ContractError,
    Wo12Handoff,
    Wo12HardGate,
    Wo12OperationOutcome,
    Wo12OperationStage,
)
from kronos.intraday.wo12_facts import (
    Wo12CprAcceptanceFact,
    Wo12PathClearanceFact,
    Wo12SetupQualityFact,
    adapt_k1,
    adapt_k2,
    adapt_k3,
    adapt_k4,
)
from kronos.intraday.probables_v2 import SemanticQualificationFactV2
from kronos.validation.kr370 import (
    KR370_OWNER_IDENTITY,
    KR370_PROMOTION_AUTHORITY,
    KR370_PROMOTION_CONTRACT_ID,
    KR370_PROMOTION_CONTRACT_VERSION,
    KR370_STATE_FAMILY_IDENTITY,
    Kr370AnalyticalClassification,
    Kr370CriterionState,
)


WO12_V2_CONTRACT_VERSION = "2.0.0"
WO12_V2_POLICY_IDENTITY = "KRONOS-INTRADAY-WO12-KR370-POLICY-V2"
WO12_V2_REQUEST_IDENTITY = "KRONOS-INTRADAY-WO12-KR370-REQUEST-V2"
WO12_V2_CRITERION_IDENTITY = "KRONOS-INTRADAY-WO12-KR370-CRITERION-V2"
WO12_V2_EVIDENCE_IDENTITY = "KRONOS-INTRADAY-WO12-KR370-EVIDENCE-V2"
WO12_V2_RESULT_IDENTITY = "KRONOS-INTRADAY-WO12-KR370-RESULT-V2"
WO12_V2_WO13_ELIGIBILITY_IDENTITY = (
    "KRONOS-INTRADAY-WO12-WO13-ELIGIBILITY-V2"
)
WO12_V2_POINTER_IDENTITY = "KRONOS-INTRADAY-CURRENT-WO12-KR370-POINTER-V2"
WO12_V2_OPERATION_IDENTITY = (
    "KRONOS-INTRADAY-WO12-KR370-OPERATION-PROVENANCE-V2"
)
WO12_V2_EXTENSION_AUTHORITY = "SUPPORTING_RESEARCH_TELEMETRY_WO15_ONLY"
WO12_V2_FIVE_MINUTE_AUTHORITY = "NONE_WO15_KR380_ONLY"


class Wo12CriterionIdentityV2(StrEnum):
    K1_15M_DIRECTIONAL_PROGRESSION = "K1_15M_DIRECTIONAL_PROGRESSION"
    K2_15M_CPR_ACCEPTANCE = "K2_15M_CPR_ACCEPTANCE"
    K3_15M_IMMEDIATE_PATH_CLEARANCE = "K3_15M_IMMEDIATE_PATH_CLEARANCE"
    K4_15M_SETUP_QUALITY = "K4_15M_SETUP_QUALITY"


class Wo13EligibilityV2(StrEnum):
    ELIGIBLE_FOR_WO13_STEP31 = "ELIGIBLE_FOR_WO13_STEP31"
    NOT_ELIGIBLE_FOR_WO13_STEP31 = "NOT_ELIGIBLE_FOR_WO13_STEP31"


_POLICY_DOCUMENT = {
    "contract": KR370_PROMOTION_CONTRACT_ID,
    "contract_version": KR370_PROMOTION_CONTRACT_VERSION,
    "state_family": KR370_STATE_FAMILY_IDENTITY,
    "criteria": tuple(item.value for item in Wo12CriterionIdentityV2),
    "criterion_states": tuple(item.value for item in Kr370CriterionState),
    "hard_gates": tuple(item.value for item in Wo12HardGate),
    "timeframe": "15M",
    "five_minute_authority": WO12_V2_FIVE_MINUTE_AUTHORITY,
    "extension_authority": WO12_V2_EXTENSION_AUTHORITY,
    "authority": KR370_PROMOTION_AUTHORITY,
}
WO12_V2_POLICY_CHECKSUM = sha256(json.dumps(
    _POLICY_DOCUMENT, sort_keys=True, separators=(",", ":")
).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class Wo12PolicyBindingV2:
    policy_identity: str = WO12_V2_POLICY_IDENTITY
    policy_version: str = WO12_V2_CONTRACT_VERSION
    policy_checksum: str = WO12_V2_POLICY_CHECKSUM
    common_contract_identity: str = KR370_PROMOTION_CONTRACT_ID
    common_contract_version: str = KR370_PROMOTION_CONTRACT_VERSION
    state_family_identity: str = KR370_STATE_FAMILY_IDENTITY
    owner_identity: str = KR370_OWNER_IDENTITY
    authority: str = KR370_PROMOTION_AUTHORITY
    extension_authority: str = WO12_V2_EXTENSION_AUTHORITY
    five_minute_authority: str = WO12_V2_FIVE_MINUTE_AUTHORITY

    def __post_init__(self) -> None:
        if self != Wo12PolicyBindingV2.__new_defaults__():
            raise Wo12ContractError("WO12_V2_POLICY_BINDING_INVALID")

    @classmethod
    def __new_defaults__(cls) -> Wo12PolicyBindingV2:
        value = object.__new__(cls)
        for name, expected in (
            ("policy_identity", WO12_V2_POLICY_IDENTITY),
            ("policy_version", WO12_V2_CONTRACT_VERSION),
            ("policy_checksum", WO12_V2_POLICY_CHECKSUM),
            ("common_contract_identity", KR370_PROMOTION_CONTRACT_ID),
            ("common_contract_version", KR370_PROMOTION_CONTRACT_VERSION),
            ("state_family_identity", KR370_STATE_FAMILY_IDENTITY),
            ("owner_identity", KR370_OWNER_IDENTITY),
            ("authority", KR370_PROMOTION_AUTHORITY),
            ("extension_authority", WO12_V2_EXTENSION_AUTHORITY),
            ("five_minute_authority", WO12_V2_FIVE_MINUTE_AUTHORITY),
        ):
            object.__setattr__(value, name, expected)
        return value


@dataclass(frozen=True, slots=True)
class Wo12RequestV2:
    request_identity: str
    request_integrity: str
    handoff: Wo12Handoff
    policy: Wo12PolicyBindingV2
    requested_at: datetime
    sponsor_operation_identity: str
    provenance: tuple[str, ...]
    schema_identity: str = WO12_V2_REQUEST_IDENTITY
    schema_version: str = WO12_V2_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "request_identity", "request_integrity")
        if (
            type(self.handoff) is not Wo12Handoff
            or type(self.policy) is not Wo12PolicyBindingV2
            or not _aware(self.requested_at)
            or not _text(self.sponsor_operation_identity)
            or not _texts(self.provenance)
            or self.schema_identity != WO12_V2_REQUEST_IDENTITY
            or self.schema_version != WO12_V2_CONTRACT_VERSION
            or self.request_identity != _identity("INTRADAY-WO12-REQUEST-V2-", values)
            or self.request_integrity
            != _identity("INTEGRITY-INTRADAY-WO12-REQUEST-V2-", values)
        ):
            raise Wo12ContractError("WO12_V2_REQUEST_INVALID")


def create_wo12_request_v2(
    *,
    handoff: Wo12Handoff,
    requested_at: datetime,
    sponsor_operation_identity: str,
    provenance: tuple[str, ...],
) -> Wo12RequestV2:
    values = {
        "handoff": handoff,
        "policy": Wo12PolicyBindingV2(),
        "requested_at": requested_at,
        "sponsor_operation_identity": sponsor_operation_identity,
        "provenance": provenance,
        "schema_identity": WO12_V2_REQUEST_IDENTITY,
        "schema_version": WO12_V2_CONTRACT_VERSION,
    }
    return Wo12RequestV2(
        request_identity=_identity("INTRADAY-WO12-REQUEST-V2-", values),
        request_integrity=_identity("INTEGRITY-INTRADAY-WO12-REQUEST-V2-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo12CriterionResultV2:
    identity: Wo12CriterionIdentityV2
    state: Kr370CriterionState
    reason: str
    evidence_identities: tuple[str, ...]
    evidence_integrities: tuple[str, ...]
    schema_identity: str = WO12_V2_CRITERION_IDENTITY
    schema_version: str = WO12_V2_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            type(self.identity) is not Wo12CriterionIdentityV2
            or type(self.state) is not Kr370CriterionState
            or not _code(self.reason)
            or not _texts(self.evidence_identities)
            or not _texts(self.evidence_integrities)
            or len(self.evidence_identities) != len(self.evidence_integrities)
            or self.schema_identity != WO12_V2_CRITERION_IDENTITY
            or self.schema_version != WO12_V2_CONTRACT_VERSION
        ):
            raise Wo12ContractError("WO12_V2_CRITERION_INVALID")


@dataclass(frozen=True, slots=True)
class Wo12EvidenceInputsV2:
    fifteen_minute_structure: SemanticQualificationFactV2
    cpr_acceptance: Wo12CprAcceptanceFact
    path_clearance: Wo12PathClearanceFact
    setup_quality: Wo12SetupQualityFact
    governing_15m_structure_failed: bool = False
    authoritative_directional_conflict: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.fifteen_minute_structure) is not SemanticQualificationFactV2
            or type(self.cpr_acceptance) is not Wo12CprAcceptanceFact
            or type(self.path_clearance) is not Wo12PathClearanceFact
            or type(self.setup_quality) is not Wo12SetupQualityFact
            or type(self.governing_15m_structure_failed) is not bool
            or type(self.authoritative_directional_conflict) is not bool
        ):
            raise Wo12ContractError("WO12_V2_EVIDENCE_INPUTS_INVALID")


def assemble_wo12_criteria_v2(
    handoff: Wo12Handoff,
    inputs: Wo12EvidenceInputsV2,
) -> tuple[Wo12CriterionResultV2, ...]:
    if type(handoff) is not Wo12Handoff or type(inputs) is not Wo12EvidenceInputsV2:
        raise Wo12ContractError("WO12_V2_EVIDENCE_INPUTS_INVALID")
    legacy = (
        adapt_k1(handoff, inputs.fifteen_minute_structure),
        adapt_k2(handoff, inputs.cpr_acceptance),
        adapt_k3(handoff, inputs.path_clearance),
        adapt_k4(handoff, inputs.setup_quality),
    )
    return tuple(Wo12CriterionResultV2(
        identity=Wo12CriterionIdentityV2(item.identity.value),
        state=item.state,
        reason=item.reason,
        evidence_identities=item.evidence_identities,
        evidence_integrities=item.evidence_integrities,
    ) for item in legacy)


@dataclass(frozen=True, slots=True)
class Wo12EvidenceV2:
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
    criteria: tuple[Wo12CriterionResultV2, ...]
    exact_binding_valid: bool
    governing_15m_structure_failed: bool
    authoritative_directional_conflict: bool
    source_identities: tuple[str, ...]
    source_integrities: tuple[str, ...]
    schema_identity: str = WO12_V2_EVIDENCE_IDENTITY
    schema_version: str = WO12_V2_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "evidence_identity", "evidence_integrity")
        if (
            not _texts((self.request_identity, self.request_integrity,
                        self.handoff_identity, self.handoff_integrity,
                        self.canonical_subject_identity))
            or type(self.market_family) is not IntradayMarketFamily
            or self.inherited_direction not in {SemanticDirection.LONG, SemanticDirection.SHORT}
            or not _aware(self.analysis_boundary)
            or type(self.phase) is not IntradayAnalysisPhase
            or tuple(item.identity for item in self.criteria) != tuple(Wo12CriterionIdentityV2)
            or any(type(item) is not Wo12CriterionResultV2 for item in self.criteria)
            or type(self.exact_binding_valid) is not bool
            or type(self.governing_15m_structure_failed) is not bool
            or type(self.authoritative_directional_conflict) is not bool
            or not _texts(self.source_identities)
            or not _texts(self.source_integrities)
            or len(self.source_identities) != len(self.source_integrities)
            or self.schema_identity != WO12_V2_EVIDENCE_IDENTITY
            or self.schema_version != WO12_V2_CONTRACT_VERSION
            or self.evidence_identity != _identity("INTRADAY-WO12-EVIDENCE-V2-", values)
            or self.evidence_integrity != _identity("INTEGRITY-INTRADAY-WO12-EVIDENCE-V2-", values)
        ):
            raise Wo12ContractError("WO12_V2_EVIDENCE_INVALID")


def create_wo12_evidence_v2(
    *,
    request: Wo12RequestV2,
    criteria: Sequence[Wo12CriterionResultV2],
    exact_binding_valid: bool,
    governing_15m_structure_failed: bool,
    authoritative_directional_conflict: bool,
) -> Wo12EvidenceV2:
    retained = tuple(criteria)
    if type(request) is not Wo12RequestV2:
        raise Wo12ContractError("WO12_V2_EVIDENCE_INPUT_INVALID")
    pairs = tuple(
        pair
        for item in retained
        for pair in zip(item.evidence_identities, item.evidence_integrities, strict=True)
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
        "source_identities": tuple(item[0] for item in pairs),
        "source_integrities": tuple(item[1] for item in pairs),
        "schema_identity": WO12_V2_EVIDENCE_IDENTITY,
        "schema_version": WO12_V2_CONTRACT_VERSION,
    }
    return Wo12EvidenceV2(
        evidence_identity=_identity("INTRADAY-WO12-EVIDENCE-V2-", values),
        evidence_integrity=_identity("INTEGRITY-INTRADAY-WO12-EVIDENCE-V2-", values),
        **values,
    )


def classify_wo12_v2(
    direction: SemanticDirection,
    criteria: Sequence[Wo12CriterionResultV2],
) -> tuple[Kr370AnalyticalClassification, int, int]:
    retained = tuple(criteria)
    if (
        direction not in {SemanticDirection.LONG, SemanticDirection.SHORT}
        or tuple(item.identity for item in retained) != tuple(Wo12CriterionIdentityV2)
        or any(type(item.state) is not Kr370CriterionState for item in retained)
        or any(item.state is Kr370CriterionState.UNAVAILABLE for item in retained)
    ):
        raise Wo12ContractError("WO12_V2_CLASSIFICATION_INPUT_INVALID")
    satisfied = sum(item.state is Kr370CriterionState.SATISFIED for item in retained)
    if satisfied == 4:
        state = Kr370AnalyticalClassification.BUY_NOW if direction is SemanticDirection.LONG else Kr370AnalyticalClassification.SELL_NOW
    elif satisfied == 3:
        state = Kr370AnalyticalClassification.BUY_READY if direction is SemanticDirection.LONG else Kr370AnalyticalClassification.SELL_READY
    elif satisfied == 2:
        state = Kr370AnalyticalClassification.POTENTIAL_BUY_SETUP if direction is SemanticDirection.LONG else Kr370AnalyticalClassification.POTENTIAL_SELL_SETUP
    else:
        state = Kr370AnalyticalClassification.NO_SETUP
    return state, satisfied, 4 - satisfied


@dataclass(frozen=True, slots=True)
class Wo12ResultV2:
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
    criteria: tuple[Wo12CriterionResultV2, ...]
    satisfied_count: int
    unavailable_criteria: tuple[Wo12CriterionIdentityV2, ...]
    hard_gates: tuple[Wo12HardGate, ...]
    classification: Kr370AnalyticalClassification
    policy: Wo12PolicyBindingV2
    created_at: datetime
    provenance: tuple[str, ...]
    owner_identity: str = KR370_OWNER_IDENTITY
    state_family_identity: str = KR370_STATE_FAMILY_IDENTITY
    common_contract_identity: str = KR370_PROMOTION_CONTRACT_ID
    common_contract_version: str = KR370_PROMOTION_CONTRACT_VERSION
    authority: str = KR370_PROMOTION_AUTHORITY
    schema_identity: str = WO12_V2_RESULT_IDENTITY
    schema_version: str = WO12_V2_CONTRACT_VERSION
    entry_authority: bool = False
    geometry_authority: bool = False
    risk_authority: bool = False
    sponsor_decision_authority: bool = False
    entry_timing_authority: bool = False
    execution_authority: bool = False
    broker_authority: bool = False

    def __post_init__(self) -> None:
        values = _without(self, "result_identity", "result_integrity")
        unavailable = tuple(item.identity for item in self.criteria if item.state is Kr370CriterionState.UNAVAILABLE)
        expected = None
        if not self.hard_gates and not unavailable:
            expected = classify_wo12_v2(self.inherited_direction, self.criteria)[0]
        if (
            tuple(item.identity for item in self.criteria) != tuple(Wo12CriterionIdentityV2)
            or self.satisfied_count != sum(item.state is Kr370CriterionState.SATISFIED for item in self.criteria)
            or self.unavailable_criteria != unavailable
            or any(type(item) is not Wo12HardGate for item in self.hard_gates)
            or (Wo12HardGate.MANDATORY_K_UNAVAILABLE in self.hard_gates) is not bool(unavailable)
            or self.classification is not (Kr370AnalyticalClassification.NO_SETUP if self.hard_gates else expected)
            or type(self.policy) is not Wo12PolicyBindingV2
            or not _aware(self.created_at)
            or not _texts(self.provenance)
            or self.owner_identity != KR370_OWNER_IDENTITY
            or self.state_family_identity != KR370_STATE_FAMILY_IDENTITY
            or self.common_contract_identity != KR370_PROMOTION_CONTRACT_ID
            or self.common_contract_version != KR370_PROMOTION_CONTRACT_VERSION
            or self.authority != KR370_PROMOTION_AUTHORITY
            or self.schema_identity != WO12_V2_RESULT_IDENTITY
            or self.schema_version != WO12_V2_CONTRACT_VERSION
            or any((self.entry_authority, self.geometry_authority, self.risk_authority,
                    self.sponsor_decision_authority, self.entry_timing_authority,
                    self.execution_authority, self.broker_authority))
            or self.result_identity != _identity("INTRADAY-WO12-RESULT-V2-", values)
            or self.result_integrity != _identity("INTEGRITY-INTRADAY-WO12-RESULT-V2-", values)
        ):
            raise Wo12ContractError("WO12_V2_RESULT_INVALID")


def create_wo12_result_v2(
    *, request: Wo12RequestV2, evidence: Wo12EvidenceV2,
    created_at: datetime, provenance: tuple[str, ...],
) -> Wo12ResultV2:
    if (
        type(request) is not Wo12RequestV2 or type(evidence) is not Wo12EvidenceV2
        or evidence.request_identity != request.request_identity
        or evidence.request_integrity != request.request_integrity
        or evidence.handoff_identity != request.handoff.handoff_identity
        or evidence.handoff_integrity != request.handoff.handoff_integrity
        or evidence.inherited_direction is not request.handoff.inherited_direction
        or not _aware(created_at) or not _texts(provenance)
    ):
        raise Wo12ContractError("WO12_V2_RESULT_INPUT_INVALID")
    gates = []
    if not evidence.exact_binding_valid:
        gates.append(Wo12HardGate.INVALID_EXACT_EVIDENCE_BINDING)
    unavailable = tuple(item.identity for item in evidence.criteria if item.state is Kr370CriterionState.UNAVAILABLE)
    if unavailable:
        gates.append(Wo12HardGate.MANDATORY_K_UNAVAILABLE)
    if evidence.governing_15m_structure_failed:
        gates.append(Wo12HardGate.GOVERNING_15M_STRUCTURE_FAILED)
    if evidence.authoritative_directional_conflict:
        gates.append(Wo12HardGate.AUTHORITATIVE_GOVERNED_DIRECTIONAL_CONFLICT)
    satisfied = sum(item.state is Kr370CriterionState.SATISFIED for item in evidence.criteria)
    classification = Kr370AnalyticalClassification.NO_SETUP if gates else classify_wo12_v2(evidence.inherited_direction, evidence.criteria)[0]
    values = {
        "request_identity": request.request_identity, "request_integrity": request.request_integrity,
        "handoff_identity": request.handoff.handoff_identity, "handoff_integrity": request.handoff.handoff_integrity,
        "evidence_identity": evidence.evidence_identity, "evidence_integrity": evidence.evidence_integrity,
        "canonical_subject_identity": evidence.canonical_subject_identity, "market_family": evidence.market_family,
        "inherited_direction": evidence.inherited_direction, "analysis_boundary": evidence.analysis_boundary,
        "phase": evidence.phase, "criteria": evidence.criteria, "satisfied_count": satisfied,
        "unavailable_criteria": unavailable, "hard_gates": tuple(gates), "classification": classification,
        "policy": request.policy, "created_at": created_at, "provenance": provenance,
        "owner_identity": KR370_OWNER_IDENTITY, "state_family_identity": KR370_STATE_FAMILY_IDENTITY,
        "common_contract_identity": KR370_PROMOTION_CONTRACT_ID,
        "common_contract_version": KR370_PROMOTION_CONTRACT_VERSION,
        "authority": KR370_PROMOTION_AUTHORITY, "schema_identity": WO12_V2_RESULT_IDENTITY,
        "schema_version": WO12_V2_CONTRACT_VERSION, "entry_authority": False,
        "geometry_authority": False, "risk_authority": False,
        "sponsor_decision_authority": False, "entry_timing_authority": False,
        "execution_authority": False, "broker_authority": False,
    }
    return Wo12ResultV2(
        result_identity=_identity("INTRADAY-WO12-RESULT-V2-", values),
        result_integrity=_identity("INTEGRITY-INTRADAY-WO12-RESULT-V2-", values), **values,
    )


@dataclass(frozen=True, slots=True)
class Wo13EligibilityRecordV2:
    eligibility_identity: str
    eligibility_integrity: str
    wo12_result_identity: str
    wo12_result_integrity: str
    canonical_subject_identity: str
    inherited_direction: SemanticDirection
    classification: Kr370AnalyticalClassification
    eligibility: Wo13EligibilityV2
    analysis_boundary: datetime
    provenance: tuple[str, ...]
    schema_identity: str = WO12_V2_WO13_ELIGIBILITY_IDENTITY
    schema_version: str = WO12_V2_CONTRACT_VERSION
    geometry_authority: bool = False
    risk_authority: bool = False
    execution_authority: bool = False
    broker_authority: bool = False

    def __post_init__(self) -> None:
        values = _without(self, "eligibility_identity", "eligibility_integrity")
        expected = Wo13EligibilityV2.ELIGIBLE_FOR_WO13_STEP31 if self.classification in {Kr370AnalyticalClassification.BUY_NOW, Kr370AnalyticalClassification.SELL_NOW} else Wo13EligibilityV2.NOT_ELIGIBLE_FOR_WO13_STEP31
        if (
            self.eligibility is not expected or not _aware(self.analysis_boundary)
            or not _texts(self.provenance)
            or self.schema_identity != WO12_V2_WO13_ELIGIBILITY_IDENTITY
            or self.schema_version != WO12_V2_CONTRACT_VERSION
            or any((self.geometry_authority, self.risk_authority, self.execution_authority, self.broker_authority))
            or self.eligibility_identity != _identity("INTRADAY-WO13-ELIGIBILITY-V2-", values)
            or self.eligibility_integrity != _identity("INTEGRITY-INTRADAY-WO13-ELIGIBILITY-V2-", values)
        ):
            raise Wo12ContractError("WO13_V2_ELIGIBILITY_INVALID")


def create_wo13_eligibility_v2(result: Wo12ResultV2, *, provenance: tuple[str, ...]) -> Wo13EligibilityRecordV2:
    if type(result) is not Wo12ResultV2:
        raise Wo12ContractError("WO13_V2_ELIGIBILITY_INPUT_INVALID")
    values = {
        "wo12_result_identity": result.result_identity, "wo12_result_integrity": result.result_integrity,
        "canonical_subject_identity": result.canonical_subject_identity,
        "inherited_direction": result.inherited_direction, "classification": result.classification,
        "eligibility": Wo13EligibilityV2.ELIGIBLE_FOR_WO13_STEP31 if result.classification in {Kr370AnalyticalClassification.BUY_NOW, Kr370AnalyticalClassification.SELL_NOW} else Wo13EligibilityV2.NOT_ELIGIBLE_FOR_WO13_STEP31,
        "analysis_boundary": result.analysis_boundary, "provenance": provenance,
        "schema_identity": WO12_V2_WO13_ELIGIBILITY_IDENTITY,
        "schema_version": WO12_V2_CONTRACT_VERSION, "geometry_authority": False,
        "risk_authority": False, "execution_authority": False, "broker_authority": False,
    }
    return Wo13EligibilityRecordV2(
        eligibility_identity=_identity("INTRADAY-WO13-ELIGIBILITY-V2-", values),
        eligibility_integrity=_identity("INTEGRITY-INTRADAY-WO13-ELIGIBILITY-V2-", values), **values,
    )


@dataclass(frozen=True, slots=True)
class CurrentWo12PointerV2:
    pointer_identity: str
    pointer_integrity: str
    request_identity: str
    request_integrity: str
    result_identity: str
    result_integrity: str
    eligibility_identity: str
    eligibility_integrity: str
    schema_identity: str = WO12_V2_POINTER_IDENTITY
    schema_version: str = WO12_V2_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "pointer_identity", "pointer_integrity")
        if (
            not _texts((self.request_identity, self.request_integrity, self.result_identity,
                        self.result_integrity, self.eligibility_identity, self.eligibility_integrity))
            or self.schema_identity != WO12_V2_POINTER_IDENTITY
            or self.schema_version != WO12_V2_CONTRACT_VERSION
            or self.pointer_identity != _identity("CURRENT-INTRADAY-WO12-V2-", values)
            or self.pointer_integrity != _identity("INTEGRITY-CURRENT-INTRADAY-WO12-V2-", values)
        ):
            raise Wo12ContractError("WO12_V2_POINTER_INVALID")


def create_current_wo12_pointer_v2(request: Wo12RequestV2, result: Wo12ResultV2, eligibility: Wo13EligibilityRecordV2) -> CurrentWo12PointerV2:
    if (
        type(request) is not Wo12RequestV2 or type(result) is not Wo12ResultV2
        or type(eligibility) is not Wo13EligibilityRecordV2
        or result.request_identity != request.request_identity
        or eligibility.wo12_result_identity != result.result_identity
    ):
        raise Wo12ContractError("WO12_V2_POINTER_INPUT_INVALID")
    values = {
        "request_identity": request.request_identity, "request_integrity": request.request_integrity,
        "result_identity": result.result_identity, "result_integrity": result.result_integrity,
        "eligibility_identity": eligibility.eligibility_identity,
        "eligibility_integrity": eligibility.eligibility_integrity,
        "schema_identity": WO12_V2_POINTER_IDENTITY, "schema_version": WO12_V2_CONTRACT_VERSION,
    }
    return CurrentWo12PointerV2(
        pointer_identity=_identity("CURRENT-INTRADAY-WO12-V2-", values),
        pointer_integrity=_identity("INTEGRITY-CURRENT-INTRADAY-WO12-V2-", values), **values,
    )


@dataclass(frozen=True, slots=True)
class Wo12OperationProvenanceV2:
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
    schema_identity: str = WO12_V2_OPERATION_IDENTITY
    schema_version: str = WO12_V2_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "operation_identity", "operation_integrity")
        completed = self.outcome is Wo12OperationOutcome.COMPLETED
        failed = self.outcome is Wo12OperationOutcome.FAILED
        if (
            completed != (self.completed_at is not None) or completed != (self.result_identity is not None)
            or failed != (self.failed_at is not None) or failed != (self.failure_reason is not None)
            or not _texts(self.provenance) or self.schema_identity != WO12_V2_OPERATION_IDENTITY
            or self.schema_version != WO12_V2_CONTRACT_VERSION
            or self.operation_identity != _identity("INTRADAY-WO12-OPERATION-V2-", values)
            or self.operation_integrity != _identity("INTEGRITY-INTRADAY-WO12-OPERATION-V2-", values)
        ):
            raise Wo12ContractError("WO12_V2_OPERATION_INVALID")


def create_wo12_operation_provenance_v2(
    *, request: Wo12RequestV2, stage: Wo12OperationStage,
    outcome: Wo12OperationOutcome, started_at: datetime,
    completed_at: datetime | None = None, failed_at: datetime | None = None,
    result: Wo12ResultV2 | None = None, failure_reason: str | None = None,
    provenance: tuple[str, ...],
) -> Wo12OperationProvenanceV2:
    values = {
        "request_identity": request.request_identity, "request_integrity": request.request_integrity,
        "stage": stage, "outcome": outcome, "started_at": started_at,
        "completed_at": completed_at, "failed_at": failed_at,
        "result_identity": None if result is None else result.result_identity,
        "failure_reason": failure_reason, "provenance": provenance,
        "schema_identity": WO12_V2_OPERATION_IDENTITY, "schema_version": WO12_V2_CONTRACT_VERSION,
    }
    return Wo12OperationProvenanceV2(
        operation_identity=_identity("INTRADAY-WO12-OPERATION-V2-", values),
        operation_integrity=_identity("INTEGRITY-INTRADAY-WO12-OPERATION-V2-", values), **values,
    )


def _without(value: object, *names: str) -> dict[str, object]:
    return {key: item for key, item in asdict(value).items() if key not in names}


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(json.dumps(_normalize(value), sort_keys=True, separators=(",", ":")).encode()).hexdigest().upper()


def _normalize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _normalize(asdict(value))
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
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


def _code(value: object) -> bool:
    return _text(value) and all(item.isupper() or item.isdigit() or item == "_" for item in value)


__all__ = [name for name in globals() if name.startswith("WO12_V2_") or name.startswith("Wo12") or name.startswith("Wo13") or name.startswith("CurrentWo12") or name.startswith("assemble_wo12") or name.startswith("classify_wo12") or name.startswith("create_wo12") or name.startswith("create_wo13") or name.startswith("create_current")]
