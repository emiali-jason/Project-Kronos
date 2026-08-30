"""Common immutable contracts for Intraday WO-10 analytical reconciliation.

This module defines the product-local Slice-1 protocol only.  It deliberately
contains no family classifier, KR-370 mapping, persistence, or runtime action.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import json
import re
from typing import Mapping, Sequence, TYPE_CHECKING

from kronos.intraday.completed_evidence import IntradayAnalysisPhase
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.probables import ProbableState
from kronos.intraday.probables_v2 import ProbableMemberResultV2, ProbablesRunV2
from kronos.intraday.universe import IntradayMarketFamily

if TYPE_CHECKING:
    from kronos.intraday.wo10_evidence import Wo10EvidenceSnapshot


WO10_STATE_FAMILY_IDENTITY = "KRONOS-INTRADAY-WO10-STATE-FAMILY-V1"
WO10_STATE_FAMILY_VERSION = "1.0.0"
WO10_REQUEST_IDENTITY = "KRONOS-INTRADAY-WO10-RECONCILIATION-REQUEST-V2"
WO10_RESULT_IDENTITY = "KRONOS-INTRADAY-WO10-RECONCILIATION-RESULT-V2"
WO10_BATCH_RESULT_IDENTITY = "KRONOS-INTRADAY-WO10-BATCH-RESULT-V2"
WO10_CURRENT_POINTER_IDENTITY = (
    "KRONOS-INTRADAY-CURRENT-WO10-RECONCILIATION-POINTER-V2"
)
WO10_CONTRACT_VERSION = "2.0.0"
WO10_POLICY_BINDING_IDENTITY = "KRONOS-INTRADAY-WO10-POLICY-BINDING-V1"
WO10_POLICY_BINDING_VERSION = "1.0.0"
WO10_REASON_CODE_IDENTITY = "KRONOS-INTRADAY-WO10-REASON-CODE-V1"
WO10_REASON_CODE_VERSION = "1.0.0"
WO10_OPERATION_PROVENANCE_IDENTITY = (
    "KRONOS-INTRADAY-WO10-OPERATION-PROVENANCE-V1"
)
WO10_OPERATION_PROVENANCE_VERSION = "1.0.0"


class Wo10ContractError(ValueError):
    """Sanitized common WO-10 contract or binding failure."""


class Wo10State(StrEnum):
    CONTEXT_INCOMPLETE = "CONTEXT_INCOMPLETE"
    INVALIDATED = "INVALIDATED"
    WEAKENING = "WEAKENING"
    HELD_BY_CONTRADICTION = "HELD_BY_CONTRADICTION"
    WAIT_SETUP_DEVELOPMENT = "WAIT_SETUP_DEVELOPMENT"
    WAIT_IMMEDIATE_CONFIRMATION = "WAIT_IMMEDIATE_CONFIRMATION"
    PROMOTION_READY = "PROMOTION_READY"


WO10_STATE_PRECEDENCE = tuple(Wo10State)


class Wo10ReasonScope(StrEnum):
    COMMON = "COMMON"
    EQUITY = "EQUITY"
    INDEX = "INDEX"
    MCX = "MCX"


class Wo10OperationStage(StrEnum):
    REQUEST = "REQUEST"
    EVIDENCE = "EVIDENCE"
    POLICY = "POLICY"
    RESULT = "RESULT"
    BATCH_PUBLICATION = "BATCH_PUBLICATION"


class Wo10OperationOutcome(StrEnum):
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class Wo10PolicyBinding:
    policy_identity: str
    policy_version: str
    publication_identity: str
    policy_checksum: str
    supported_market_family: IntradayMarketFamily
    integrity_identity: str
    schema_identity: str = WO10_POLICY_BINDING_IDENTITY
    schema_version: str = WO10_POLICY_BINDING_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "integrity_identity")
        if (
            not _texts((
                self.policy_identity,
                self.policy_version,
                self.publication_identity,
            ))
            or _sha256(self.policy_checksum) is None
            or type(self.supported_market_family) is not IntradayMarketFamily
            or self.schema_identity != WO10_POLICY_BINDING_IDENTITY
            or self.schema_version != WO10_POLICY_BINDING_VERSION
            or self.integrity_identity
            != _identity("INTEGRITY-INTRADAY-WO10-POLICY-", values)
        ):
            raise Wo10ContractError("WO10_POLICY_BINDING_INVALID")

    @property
    def key(self) -> tuple[str, str, str, str, IntradayMarketFamily]:
        return (
            self.policy_identity,
            self.policy_version,
            self.publication_identity,
            self.policy_checksum,
            self.supported_market_family,
        )


def create_wo10_policy_binding(
    *,
    policy_identity: str,
    policy_version: str,
    publication_identity: str,
    policy_checksum: str,
    supported_market_family: IntradayMarketFamily,
) -> Wo10PolicyBinding:
    values = {
        "policy_identity": policy_identity,
        "policy_version": policy_version,
        "publication_identity": publication_identity,
        "policy_checksum": policy_checksum,
        "supported_market_family": supported_market_family,
        "schema_identity": WO10_POLICY_BINDING_IDENTITY,
        "schema_version": WO10_POLICY_BINDING_VERSION,
    }
    return Wo10PolicyBinding(
        integrity_identity=_identity("INTEGRITY-INTRADAY-WO10-POLICY-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo10ReasonCode:
    scope: Wo10ReasonScope
    code: str
    policy_identity: str
    schema_identity: str = WO10_REASON_CODE_IDENTITY
    schema_version: str = WO10_REASON_CODE_VERSION

    def __post_init__(self) -> None:
        prohibited = {
            "BUY_NOW", "SELL_NOW", "BUY_READY", "SELL_READY", "ENTRY",
            "STOP", "SL", "TARGET", "RR", "R_R", "TRADE", "CONSTRUCTION",
            "RISK", "PAPER", "LIVE", "BROKER", "SCORE", "WEIGHT", "RANK",
            "QUOTA",
        }
        tokens = set(self.code.split("_"))
        if (
            type(self.scope) is not Wo10ReasonScope
            or re.fullmatch(r"[A-Z][A-Z0-9_]{2,95}", self.code) is None
            or prohibited.intersection(tokens)
            or self.code in prohibited
            or not _text(self.policy_identity)
            or self.schema_identity != WO10_REASON_CODE_IDENTITY
            or self.schema_version != WO10_REASON_CODE_VERSION
        ):
            raise Wo10ContractError("WO10_REASON_CODE_INVALID")


@dataclass(frozen=True, slots=True)
class Wo10ProbableBindingV2:
    probable_result_identity: str
    probable_result_integrity: str
    canonical_subject_identity: str
    inherited_direction: SemanticDirection
    analysis_boundary: datetime
    persisted_phase: IntradayAnalysisPhase

    def __post_init__(self) -> None:
        if (
            not _texts((
                self.probable_result_identity,
                self.probable_result_integrity,
                self.canonical_subject_identity,
            ))
            or self.inherited_direction
            not in {SemanticDirection.LONG, SemanticDirection.SHORT}
            or not _aware(self.analysis_boundary)
            or type(self.persisted_phase) is not IntradayAnalysisPhase
        ):
            raise Wo10ContractError("WO10_PROBABLE_BINDING_INVALID")


@dataclass(frozen=True, slots=True)
class Wo10ReconciliationRequest:
    request_identity: str
    request_integrity: str
    market_family: IntradayMarketFamily
    probables_run_identity: str
    probables_run_integrity: str
    probable_bindings: tuple[Wo10ProbableBindingV2, ...]
    policy: Wo10PolicyBinding
    requested_at: datetime
    sponsor_operation_identity: str
    provenance: tuple[str, ...]
    schema_identity: str = WO10_REQUEST_IDENTITY
    schema_version: str = WO10_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "request_identity", "request_integrity")
        if (
            type(self.market_family) is not IntradayMarketFamily
            or not _texts((
                self.probables_run_identity,
                self.probables_run_integrity,
                self.sponsor_operation_identity,
            ))
            or not self.probable_bindings
            or any(type(item) is not Wo10ProbableBindingV2 for item in self.probable_bindings)
            or tuple(sorted(
                self.probable_bindings,
                key=lambda item: item.canonical_subject_identity,
            )) != self.probable_bindings
            or len({item.probable_result_identity for item in self.probable_bindings})
            != len(self.probable_bindings)
            or len({item.canonical_subject_identity for item in self.probable_bindings})
            != len(self.probable_bindings)
            or any(
                market_family_for_subject(item.canonical_subject_identity)
                is not self.market_family
                for item in self.probable_bindings
            )
            or type(self.policy) is not Wo10PolicyBinding
            or self.policy.supported_market_family is not self.market_family
            or not _aware(self.requested_at)
            or not _texts(self.provenance)
            or self.schema_identity != WO10_REQUEST_IDENTITY
            or self.schema_version != WO10_CONTRACT_VERSION
            or self.request_identity
            != _identity("INTRADAY-WO10-REQUEST-V2-", values)
            or self.request_integrity
            != _identity("INTEGRITY-INTRADAY-WO10-REQUEST-V2-", values)
        ):
            raise Wo10ContractError("WO10_REQUEST_INVALID")


def create_wo10_reconciliation_request(
    *,
    run: ProbablesRunV2,
    results: Sequence[ProbableMemberResultV2],
    market_family: IntradayMarketFamily,
    policy: Wo10PolicyBinding,
    requested_at: datetime,
    sponsor_operation_identity: str,
    provenance: tuple[str, ...],
) -> Wo10ReconciliationRequest:
    selected = tuple(results)
    if (
        type(run) is not ProbablesRunV2
        or type(market_family) is not IntradayMarketFamily
        or type(policy) is not Wo10PolicyBinding
        or policy.supported_market_family is not market_family
        or not selected
        or any(
            type(item) is not ProbableMemberResultV2
            or item not in run.results
            or item.state not in {ProbableState.LONG_PROBABLE, ProbableState.SHORT_PROBABLE}
            or item.direction not in {SemanticDirection.LONG, SemanticDirection.SHORT}
            or item.phase is None
            or market_family_for_subject(item.canonical_subject_identity)
            is not market_family
            for item in selected
        )
        or not _aware(requested_at)
        or not _text(sponsor_operation_identity)
        or not _texts(provenance)
    ):
        raise Wo10ContractError("WO10_REQUEST_INPUT_INVALID")
    ordered = tuple(sorted(selected, key=lambda item: item.canonical_subject_identity))
    if len({item.result_identity for item in ordered}) != len(ordered):
        raise Wo10ContractError("WO10_REQUEST_POPULATION_INVALID")
    bindings = tuple(Wo10ProbableBindingV2(
        probable_result_identity=item.result_identity,
        probable_result_integrity=item.integrity_identity,
        canonical_subject_identity=item.canonical_subject_identity,
        inherited_direction=item.direction,
        analysis_boundary=item.analysis_boundary,
        persisted_phase=item.phase,
    ) for item in ordered)
    values = {
        "market_family": market_family,
        "probables_run_identity": run.run_identity,
        "probables_run_integrity": run.integrity_identity,
        "probable_bindings": bindings,
        "policy": policy,
        "requested_at": requested_at,
        "sponsor_operation_identity": sponsor_operation_identity,
        "provenance": provenance,
        "schema_identity": WO10_REQUEST_IDENTITY,
        "schema_version": WO10_CONTRACT_VERSION,
    }
    return Wo10ReconciliationRequest(
        request_identity=_identity("INTRADAY-WO10-REQUEST-V2-", values),
        request_integrity=_identity("INTEGRITY-INTRADAY-WO10-REQUEST-V2-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo10ReconciliationResult:
    result_identity: str
    result_integrity: str
    request_identity: str
    request_integrity: str
    market_family: IntradayMarketFamily
    canonical_subject_identity: str
    inherited_direction: SemanticDirection
    policy: Wo10PolicyBinding
    evidence_snapshot_identity: str
    evidence_snapshot_integrity: str
    state: Wo10State
    reasons: tuple[Wo10ReasonCode, ...]
    analysis_boundary: datetime
    persisted_phase: IntradayAnalysisPhase
    provenance: tuple[str, ...]
    schema_identity: str = WO10_RESULT_IDENTITY
    schema_version: str = WO10_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "result_identity", "result_integrity")
        if (
            not _texts((
                self.request_identity,
                self.request_integrity,
                self.canonical_subject_identity,
                self.evidence_snapshot_identity,
                self.evidence_snapshot_integrity,
            ))
            or type(self.market_family) is not IntradayMarketFamily
            or market_family_for_subject(self.canonical_subject_identity)
            is not self.market_family
            or self.inherited_direction
            not in {SemanticDirection.LONG, SemanticDirection.SHORT}
            or type(self.policy) is not Wo10PolicyBinding
            or self.policy.supported_market_family is not self.market_family
            or type(self.state) is not Wo10State
            or not self.reasons
            or any(type(item) is not Wo10ReasonCode for item in self.reasons)
            or tuple(sorted(self.reasons, key=_reason_key)) != self.reasons
            or len({_reason_key(item) for item in self.reasons}) != len(self.reasons)
            or any(not reason_applies_to_family(item, self.market_family) for item in self.reasons)
            or not _aware(self.analysis_boundary)
            or type(self.persisted_phase) is not IntradayAnalysisPhase
            or not _texts(self.provenance)
            or self.schema_identity != WO10_RESULT_IDENTITY
            or self.schema_version != WO10_CONTRACT_VERSION
            or self.result_identity != _identity("INTRADAY-WO10-RESULT-V2-", values)
            or self.result_integrity
            != _identity("INTEGRITY-INTRADAY-WO10-RESULT-V2-", values)
        ):
            raise Wo10ContractError("WO10_RESULT_INVALID")


def create_wo10_reconciliation_result(
    *,
    request: Wo10ReconciliationRequest,
    evidence: Wo10EvidenceSnapshot,
    state: Wo10State,
    reasons: Sequence[Wo10ReasonCode],
    provenance: tuple[str, ...],
) -> Wo10ReconciliationResult:
    from kronos.intraday.wo10_evidence import Wo10EvidenceSnapshot

    retained_reasons = tuple(sorted(tuple(reasons), key=_reason_key))
    binding = next((
        item for item in request.probable_bindings
        if item.probable_result_identity == evidence.probable_result_identity
    ), None)
    if (
        type(request) is not Wo10ReconciliationRequest
        or type(evidence) is not Wo10EvidenceSnapshot
        or type(state) is not Wo10State
        or binding is None
        or evidence.probables_run_identity != request.probables_run_identity
        or evidence.market_family is not request.market_family
        or evidence.canonical_subject_identity != binding.canonical_subject_identity
        or evidence.inherited_direction is not binding.inherited_direction
        or evidence.analysis_boundary != binding.analysis_boundary
        or evidence.persisted_phase is not binding.persisted_phase
        or evidence.policy != request.policy
        or not retained_reasons
        or any(type(item) is not Wo10ReasonCode for item in retained_reasons)
        or not _texts(provenance)
    ):
        raise Wo10ContractError("WO10_RESULT_INPUT_INVALID")
    values = {
        "request_identity": request.request_identity,
        "request_integrity": request.request_integrity,
        "market_family": request.market_family,
        "canonical_subject_identity": evidence.canonical_subject_identity,
        "inherited_direction": evidence.inherited_direction,
        "policy": request.policy,
        "evidence_snapshot_identity": evidence.snapshot_identity,
        "evidence_snapshot_integrity": evidence.snapshot_integrity,
        "state": state,
        "reasons": retained_reasons,
        "analysis_boundary": evidence.analysis_boundary,
        "persisted_phase": evidence.persisted_phase,
        "provenance": provenance,
        "schema_identity": WO10_RESULT_IDENTITY,
        "schema_version": WO10_CONTRACT_VERSION,
    }
    return Wo10ReconciliationResult(
        result_identity=_identity("INTRADAY-WO10-RESULT-V2-", values),
        result_integrity=_identity("INTEGRITY-INTRADAY-WO10-RESULT-V2-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo10StateCount:
    state: Wo10State
    count: int

    def __post_init__(self) -> None:
        if type(self.state) is not Wo10State or type(self.count) is not int or self.count < 0:
            raise Wo10ContractError("WO10_STATE_COUNT_INVALID")


@dataclass(frozen=True, slots=True)
class Wo10ResultBinding:
    canonical_subject_identity: str
    result_identity: str
    result_integrity: str

    def __post_init__(self) -> None:
        if not _texts((
            self.canonical_subject_identity,
            self.result_identity,
            self.result_integrity,
        )):
            raise Wo10ContractError("WO10_RESULT_BINDING_INVALID")


@dataclass(frozen=True, slots=True)
class Wo10BatchResult:
    batch_identity: str
    batch_integrity: str
    request_identity: str
    request_integrity: str
    market_family: IntradayMarketFamily
    policy: Wo10PolicyBinding
    result_bindings: tuple[Wo10ResultBinding, ...]
    requested_population: int
    published_population: int
    state_counts: tuple[Wo10StateCount, ...]
    completed_at: datetime
    provenance: tuple[str, ...]
    schema_identity: str = WO10_BATCH_RESULT_IDENTITY
    schema_version: str = WO10_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "batch_identity", "batch_integrity")
        if (
            not _texts((self.request_identity, self.request_integrity))
            or type(self.market_family) is not IntradayMarketFamily
            or type(self.policy) is not Wo10PolicyBinding
            or self.policy.supported_market_family is not self.market_family
            or not self.result_bindings
            or any(type(item) is not Wo10ResultBinding for item in self.result_bindings)
            or tuple(sorted(
                self.result_bindings,
                key=lambda item: item.canonical_subject_identity,
            )) != self.result_bindings
            or len({item.canonical_subject_identity for item in self.result_bindings})
            != len(self.result_bindings)
            or tuple(item.state for item in self.state_counts) != WO10_STATE_PRECEDENCE
            or any(type(item) is not Wo10StateCount for item in self.state_counts)
            or type(self.requested_population) is not int
            or self.requested_population < 1
            or type(self.published_population) is not int
            or self.published_population != len(self.result_bindings)
            or self.requested_population != self.published_population
            or sum(item.count for item in self.state_counts) != self.published_population
            or not _aware(self.completed_at)
            or not _texts(self.provenance)
            or self.schema_identity != WO10_BATCH_RESULT_IDENTITY
            or self.schema_version != WO10_CONTRACT_VERSION
            or self.batch_identity != _identity("INTRADAY-WO10-BATCH-V2-", values)
            or self.batch_integrity
            != _identity("INTEGRITY-INTRADAY-WO10-BATCH-V2-", values)
        ):
            raise Wo10ContractError("WO10_BATCH_RESULT_INVALID")


def create_wo10_batch_result(
    *,
    request: Wo10ReconciliationRequest,
    results: Sequence[Wo10ReconciliationResult],
    completed_at: datetime,
    provenance: tuple[str, ...],
) -> Wo10BatchResult:
    retained = tuple(results)
    if (
        type(request) is not Wo10ReconciliationRequest
        or not retained
        or any(
            type(item) is not Wo10ReconciliationResult
            or item.request_identity != request.request_identity
            or item.request_integrity != request.request_integrity
            or item.market_family is not request.market_family
            or item.policy != request.policy
            for item in retained
        )
        or not _aware(completed_at)
        or not _texts(provenance)
    ):
        raise Wo10ContractError("WO10_BATCH_INPUT_INVALID")
    ordered = tuple(sorted(retained, key=lambda item: item.canonical_subject_identity))
    requested_subjects = tuple(
        item.canonical_subject_identity for item in request.probable_bindings
    )
    if (
        tuple(item.canonical_subject_identity for item in ordered) != requested_subjects
        or len({item.result_identity for item in ordered}) != len(ordered)
    ):
        raise Wo10ContractError("WO10_BATCH_POPULATION_INVALID")
    result_bindings = tuple(Wo10ResultBinding(
        canonical_subject_identity=item.canonical_subject_identity,
        result_identity=item.result_identity,
        result_integrity=item.result_integrity,
    ) for item in ordered)
    state_counts = tuple(Wo10StateCount(
        state=state,
        count=sum(item.state is state for item in ordered),
    ) for state in WO10_STATE_PRECEDENCE)
    values = {
        "request_identity": request.request_identity,
        "request_integrity": request.request_integrity,
        "market_family": request.market_family,
        "policy": request.policy,
        "result_bindings": result_bindings,
        "requested_population": len(request.probable_bindings),
        "published_population": len(ordered),
        "state_counts": state_counts,
        "completed_at": completed_at,
        "provenance": provenance,
        "schema_identity": WO10_BATCH_RESULT_IDENTITY,
        "schema_version": WO10_CONTRACT_VERSION,
    }
    return Wo10BatchResult(
        batch_identity=_identity("INTRADAY-WO10-BATCH-V2-", values),
        batch_integrity=_identity("INTEGRITY-INTRADAY-WO10-BATCH-V2-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class CurrentWo10ReconciliationPointer:
    pointer_identity: str
    pointer_integrity: str
    probables_run_identity: str
    probables_run_integrity: str
    request_identity: str
    request_integrity: str
    market_family: IntradayMarketFamily
    policy: Wo10PolicyBinding
    batch_identity: str
    batch_integrity: str
    result_bindings: tuple[Wo10ResultBinding, ...]
    schema_identity: str = WO10_CURRENT_POINTER_IDENTITY
    schema_version: str = WO10_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "pointer_identity", "pointer_integrity")
        if (
            not _texts((
                self.probables_run_identity,
                self.probables_run_integrity,
                self.request_identity,
                self.request_integrity,
                self.batch_identity,
                self.batch_integrity,
            ))
            or type(self.market_family) is not IntradayMarketFamily
            or type(self.policy) is not Wo10PolicyBinding
            or self.policy.supported_market_family is not self.market_family
            or not self.result_bindings
            or any(type(item) is not Wo10ResultBinding for item in self.result_bindings)
            or tuple(sorted(
                self.result_bindings,
                key=lambda item: item.canonical_subject_identity,
            )) != self.result_bindings
            or len({item.canonical_subject_identity for item in self.result_bindings})
            != len(self.result_bindings)
            or self.schema_identity != WO10_CURRENT_POINTER_IDENTITY
            or self.schema_version != WO10_CONTRACT_VERSION
            or self.pointer_identity != _identity("CURRENT-INTRADAY-WO10-V2-", values)
            or self.pointer_integrity
            != _identity("INTEGRITY-CURRENT-INTRADAY-WO10-V2-", values)
        ):
            raise Wo10ContractError("WO10_CURRENT_POINTER_INVALID")


def create_current_wo10_pointer(
    request: Wo10ReconciliationRequest,
    batch: Wo10BatchResult,
) -> CurrentWo10ReconciliationPointer:
    if (
        type(request) is not Wo10ReconciliationRequest
        or type(batch) is not Wo10BatchResult
        or batch.request_identity != request.request_identity
        or batch.request_integrity != request.request_integrity
        or batch.market_family is not request.market_family
        or batch.policy != request.policy
    ):
        raise Wo10ContractError("WO10_CURRENT_POINTER_INPUT_INVALID")
    values = {
        "probables_run_identity": request.probables_run_identity,
        "probables_run_integrity": request.probables_run_integrity,
        "request_identity": request.request_identity,
        "request_integrity": request.request_integrity,
        "market_family": request.market_family,
        "policy": request.policy,
        "batch_identity": batch.batch_identity,
        "batch_integrity": batch.batch_integrity,
        "result_bindings": batch.result_bindings,
        "schema_identity": WO10_CURRENT_POINTER_IDENTITY,
        "schema_version": WO10_CONTRACT_VERSION,
    }
    return CurrentWo10ReconciliationPointer(
        pointer_identity=_identity("CURRENT-INTRADAY-WO10-V2-", values),
        pointer_integrity=_identity("INTEGRITY-CURRENT-INTRADAY-WO10-V2-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo10OperationProvenance:
    operation_identity: str
    integrity_identity: str
    request_identity: str
    request_integrity: str
    market_family: IntradayMarketFamily
    stage: Wo10OperationStage
    outcome: Wo10OperationOutcome
    started_at: datetime
    completed_at: datetime | None
    failed_at: datetime | None
    backend_identity: str | None
    process_identity: str | None
    probables_run_identity: str
    policy: Wo10PolicyBinding
    result_identities: tuple[str, ...]
    batch_identity: str | None
    failure_reason: str | None
    provenance: tuple[str, ...]
    schema_identity: str = WO10_OPERATION_PROVENANCE_IDENTITY
    schema_version: str = WO10_OPERATION_PROVENANCE_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "operation_identity", "integrity_identity")
        completed = self.outcome is Wo10OperationOutcome.COMPLETED
        failed = self.outcome is Wo10OperationOutcome.FAILED
        if (
            not _texts((
                self.request_identity,
                self.request_integrity,
                self.probables_run_identity,
            ))
            or type(self.market_family) is not IntradayMarketFamily
            or type(self.stage) is not Wo10OperationStage
            or type(self.outcome) is not Wo10OperationOutcome
            or not _aware(self.started_at)
            or (self.completed_at is not None and not _aware(self.completed_at))
            or (self.failed_at is not None and not _aware(self.failed_at))
            or (self.backend_identity is not None and not _text(self.backend_identity))
            or (self.process_identity is not None and not _text(self.process_identity))
            or type(self.policy) is not Wo10PolicyBinding
            or self.policy.supported_market_family is not self.market_family
            or tuple(sorted(set(self.result_identities))) != self.result_identities
            or (self.batch_identity is not None and not _text(self.batch_identity))
            or (self.failure_reason is not None and not _failure_code(self.failure_reason))
            or completed != (self.completed_at is not None)
            or completed != (self.batch_identity is not None)
            or completed != bool(self.result_identities)
            or failed != (self.failed_at is not None)
            or failed != (self.failure_reason is not None)
            or (failed and (self.completed_at is not None or self.batch_identity is not None))
            or (self.outcome is Wo10OperationOutcome.STARTED and any((
                self.completed_at,
                self.failed_at,
                self.batch_identity,
                self.failure_reason,
                self.result_identities,
            )))
            or not _texts(self.provenance)
            or self.schema_identity != WO10_OPERATION_PROVENANCE_IDENTITY
            or self.schema_version != WO10_OPERATION_PROVENANCE_VERSION
            or self.operation_identity != _identity("INTRADAY-WO10-OPERATION-", values)
            or self.integrity_identity
            != _identity("INTEGRITY-INTRADAY-WO10-OPERATION-", values)
        ):
            raise Wo10ContractError("WO10_OPERATION_PROVENANCE_INVALID")


def create_wo10_operation_provenance(
    *,
    request: Wo10ReconciliationRequest,
    stage: Wo10OperationStage,
    outcome: Wo10OperationOutcome,
    started_at: datetime,
    completed_at: datetime | None = None,
    failed_at: datetime | None = None,
    backend_identity: str | None = None,
    process_identity: str | None = None,
    results: Sequence[Wo10ReconciliationResult] = (),
    batch: Wo10BatchResult | None = None,
    failure_reason: str | None = None,
    provenance: tuple[str, ...],
) -> Wo10OperationProvenance:
    retained = tuple(results)
    if (
        type(request) is not Wo10ReconciliationRequest
        or any(
            type(item) is not Wo10ReconciliationResult
            or item.request_identity != request.request_identity
            for item in retained
        )
        or (batch is not None and (
            type(batch) is not Wo10BatchResult
            or batch.request_identity != request.request_identity
        ))
    ):
        raise Wo10ContractError("WO10_OPERATION_PROVENANCE_INPUT_INVALID")
    result_identities = tuple(sorted(item.result_identity for item in retained))
    values = {
        "request_identity": request.request_identity,
        "request_integrity": request.request_integrity,
        "market_family": request.market_family,
        "stage": stage,
        "outcome": outcome,
        "started_at": started_at,
        "completed_at": completed_at,
        "failed_at": failed_at,
        "backend_identity": backend_identity,
        "process_identity": process_identity,
        "probables_run_identity": request.probables_run_identity,
        "policy": request.policy,
        "result_identities": result_identities,
        "batch_identity": None if batch is None else batch.batch_identity,
        "failure_reason": failure_reason,
        "provenance": provenance,
        "schema_identity": WO10_OPERATION_PROVENANCE_IDENTITY,
        "schema_version": WO10_OPERATION_PROVENANCE_VERSION,
    }
    return Wo10OperationProvenance(
        operation_identity=_identity("INTRADAY-WO10-OPERATION-", values),
        integrity_identity=_identity("INTEGRITY-INTRADAY-WO10-OPERATION-", values),
        **values,
    )


def market_family_for_subject(canonical_subject_identity: str) -> IntradayMarketFamily:
    if canonical_subject_identity.startswith("NSE-EQ-"):
        return IntradayMarketFamily.NSE_EQUITY
    if canonical_subject_identity.startswith("NSE-INDEX-"):
        return IntradayMarketFamily.NSE_INDEX
    if canonical_subject_identity.startswith("MCX-SUBJECT-"):
        return IntradayMarketFamily.MCX
    raise Wo10ContractError("WO10_MARKET_FAMILY_UNKNOWN")


def reason_applies_to_family(
    reason: Wo10ReasonCode,
    family: IntradayMarketFamily,
) -> bool:
    expected = {
        IntradayMarketFamily.NSE_EQUITY: Wo10ReasonScope.EQUITY,
        IntradayMarketFamily.NSE_INDEX: Wo10ReasonScope.INDEX,
        IntradayMarketFamily.MCX: Wo10ReasonScope.MCX,
    }[family]
    return reason.scope in {Wo10ReasonScope.COMMON, expected}


def _reason_key(value: Wo10ReasonCode) -> tuple[str, str, str]:
    return value.scope.value, value.code, value.policy_identity


def _failure_code(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[A-Z][A-Z0-9_]{2,127}", value) is not None


def _sha256(value: object) -> str | None:
    if type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None:
        return value
    return None


def _without(value: object, *names: str) -> dict[str, object]:
    return {name: item for name, item in asdict(value).items() if name not in names}


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(_canonical(_normalize(value))).hexdigest().upper()


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


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
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


__all__ = [
    "WO10_BATCH_RESULT_IDENTITY",
    "WO10_CONTRACT_VERSION",
    "WO10_CURRENT_POINTER_IDENTITY",
    "WO10_OPERATION_PROVENANCE_IDENTITY",
    "WO10_OPERATION_PROVENANCE_VERSION",
    "WO10_POLICY_BINDING_IDENTITY",
    "WO10_POLICY_BINDING_VERSION",
    "WO10_REASON_CODE_IDENTITY",
    "WO10_REASON_CODE_VERSION",
    "WO10_REQUEST_IDENTITY",
    "WO10_RESULT_IDENTITY",
    "WO10_STATE_FAMILY_IDENTITY",
    "WO10_STATE_FAMILY_VERSION",
    "WO10_STATE_PRECEDENCE",
    "CurrentWo10ReconciliationPointer",
    "Wo10BatchResult",
    "Wo10ContractError",
    "Wo10OperationOutcome",
    "Wo10OperationProvenance",
    "Wo10OperationStage",
    "Wo10PolicyBinding",
    "Wo10ProbableBindingV2",
    "Wo10ReasonCode",
    "Wo10ReasonScope",
    "Wo10ReconciliationRequest",
    "Wo10ReconciliationResult",
    "Wo10ResultBinding",
    "Wo10State",
    "Wo10StateCount",
    "create_current_wo10_pointer",
    "create_wo10_batch_result",
    "create_wo10_operation_provenance",
    "create_wo10_policy_binding",
    "create_wo10_reconciliation_request",
    "create_wo10_reconciliation_result",
    "market_family_for_subject",
    "reason_applies_to_family",
]
