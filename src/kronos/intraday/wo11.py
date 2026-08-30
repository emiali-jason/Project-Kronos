"""Immutable zero-discretion contracts for Intraday WO-11 publication."""

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
from kronos.intraday.wo10 import (
    WO10_STATE_PRECEDENCE,
    Wo10BatchResult,
    Wo10OperationOutcome,
    Wo10OperationProvenance,
    Wo10PolicyBinding,
    Wo10ReasonCode,
    Wo10ReconciliationRequest,
    Wo10ReconciliationResult,
    Wo10State,
)


WO11_PUBLICATION_IDENTITY = "KRONOS-INTRADAY-WO11-PROMOTION-PUBLICATION-V1"
WO11_CONTRACT_VERSION = "1.0.0"
WO11_REQUEST_IDENTITY = "KRONOS-INTRADAY-WO11-PROMOTION-PUBLICATION-REQUEST-V1"
WO11_MEMBER_IDENTITY = "KRONOS-INTRADAY-WO11-PROMOTION-MEMBER-V1"
WO11_POINTER_IDENTITY = "KRONOS-INTRADAY-CURRENT-WO11-PROMOTION-POINTER-V1"
WO11_OPERATION_IDENTITY = "KRONOS-INTRADAY-WO11-OPERATION-PROVENANCE-V1"
WO11_HANDOFF_IDENTITY = "KRONOS-INTRADAY-WO11-DOWNSTREAM-HANDOFF-REFERENCE-V1"


class Wo11ContractError(ValueError):
    """Sanitized WO-11 contract or binding failure."""


class Wo11DownstreamEligibility(StrEnum):
    ELIGIBLE_FOR_DOWNSTREAM_HANDOFF = "ELIGIBLE_FOR_DOWNSTREAM_HANDOFF"
    NOT_ELIGIBLE_FOR_DOWNSTREAM_HANDOFF = "NOT_ELIGIBLE_FOR_DOWNSTREAM_HANDOFF"


class Wo11OperationStage(StrEnum):
    REQUEST_VALIDATION = "REQUEST_VALIDATION"
    WO10_BATCH_RELOAD = "WO10_BATCH_RELOAD"
    WO10_RESULT_VALIDATION = "WO10_RESULT_VALIDATION"
    COLLATION = "COLLATION"
    ELIGIBILITY_DERIVATION = "ELIGIBILITY_DERIVATION"
    PUBLICATION_PERSISTENCE = "PUBLICATION_PERSISTENCE"
    POINTER_PUBLICATION = "POINTER_PUBLICATION"


class Wo11OperationOutcome(StrEnum):
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class Wo11SourceBatchBinding:
    market_family: IntradayMarketFamily
    batch_identity: str
    batch_integrity: str
    request_identity: str
    request_integrity: str
    operation_identity: str
    operation_integrity: str
    policy: Wo10PolicyBinding
    probables_run_identity: str
    probables_run_integrity: str
    published_population: int

    def __post_init__(self) -> None:
        if (
            type(self.market_family) is not IntradayMarketFamily
            or not _texts((
                self.batch_identity,
                self.batch_integrity,
                self.request_identity,
                self.request_integrity,
                self.operation_identity,
                self.operation_integrity,
                self.probables_run_identity,
                self.probables_run_integrity,
            ))
            or type(self.policy) is not Wo10PolicyBinding
            or self.policy.supported_market_family is not self.market_family
            or type(self.published_population) is not int
            or self.published_population < 1
        ):
            raise Wo11ContractError("WO11_SOURCE_BATCH_BINDING_INVALID")


def create_wo11_source_batch_binding(
    *,
    batch: Wo10BatchResult,
    request: Wo10ReconciliationRequest,
    operation: Wo10OperationProvenance,
) -> Wo11SourceBatchBinding:
    if (
        type(batch) is not Wo10BatchResult
        or type(request) is not Wo10ReconciliationRequest
        or type(operation) is not Wo10OperationProvenance
        or batch.request_identity != request.request_identity
        or batch.request_integrity != request.request_integrity
        or batch.market_family is not request.market_family
        or batch.policy != request.policy
        or operation.outcome is not Wo10OperationOutcome.COMPLETED
        or operation.batch_identity != batch.batch_identity
        or operation.request_identity != request.request_identity
        or operation.request_integrity != request.request_integrity
        or operation.market_family is not request.market_family
        or operation.policy != request.policy
        or operation.probables_run_identity != request.probables_run_identity
        or operation.result_identities
        != tuple(sorted(item.result_identity for item in batch.result_bindings))
    ):
        raise Wo11ContractError("WO11_SOURCE_BATCH_INPUT_INVALID")
    return Wo11SourceBatchBinding(
        market_family=batch.market_family,
        batch_identity=batch.batch_identity,
        batch_integrity=batch.batch_integrity,
        request_identity=request.request_identity,
        request_integrity=request.request_integrity,
        operation_identity=operation.operation_identity,
        operation_integrity=operation.integrity_identity,
        policy=request.policy,
        probables_run_identity=request.probables_run_identity,
        probables_run_integrity=request.probables_run_integrity,
        published_population=batch.published_population,
    )


@dataclass(frozen=True, slots=True)
class Wo11PublicationRequest:
    request_identity: str
    request_integrity: str
    source_batches: tuple[Wo11SourceBatchBinding, ...]
    requested_at: datetime
    sponsor_operation_identity: str
    provenance: tuple[str, ...]
    schema_identity: str = WO11_REQUEST_IDENTITY
    schema_version: str = WO11_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "request_identity", "request_integrity")
        if (
            not self.source_batches
            or any(type(item) is not Wo11SourceBatchBinding for item in self.source_batches)
            or tuple(sorted(self.source_batches, key=_source_key)) != self.source_batches
            or len({item.market_family for item in self.source_batches})
            != len(self.source_batches)
            or not _aware(self.requested_at)
            or not _text(self.sponsor_operation_identity)
            or not _texts(self.provenance)
            or self.schema_identity != WO11_REQUEST_IDENTITY
            or self.schema_version != WO11_CONTRACT_VERSION
            or self.request_identity != _identity("INTRADAY-WO11-REQUEST-V1-", values)
            or self.request_integrity
            != _identity("INTEGRITY-INTRADAY-WO11-REQUEST-V1-", values)
        ):
            raise Wo11ContractError("WO11_REQUEST_INVALID")


def create_wo11_publication_request(
    *,
    source_batches: Sequence[Wo11SourceBatchBinding],
    requested_at: datetime,
    sponsor_operation_identity: str,
    provenance: tuple[str, ...],
) -> Wo11PublicationRequest:
    retained = tuple(sorted(tuple(source_batches), key=_source_key))
    values = {
        "source_batches": retained,
        "requested_at": requested_at,
        "sponsor_operation_identity": sponsor_operation_identity,
        "provenance": provenance,
        "schema_identity": WO11_REQUEST_IDENTITY,
        "schema_version": WO11_CONTRACT_VERSION,
    }
    return Wo11PublicationRequest(
        request_identity=_identity("INTRADAY-WO11-REQUEST-V1-", values),
        request_integrity=_identity("INTEGRITY-INTRADAY-WO11-REQUEST-V1-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo11Member:
    member_identity: str
    member_integrity: str
    canonical_subject_identity: str
    market_family: IntradayMarketFamily
    inherited_direction: SemanticDirection
    wo10_result_identity: str
    wo10_result_integrity: str
    wo10_state: Wo10State
    wo10_reasons: tuple[Wo10ReasonCode, ...]
    wo10_policy: Wo10PolicyBinding
    source_wo10_batch_identity: str
    source_wo10_request_identity: str
    source_probables_run_identity: str
    source_probables_run_integrity: str
    source_probable_result_identity: str
    source_probable_result_integrity: str
    analysis_boundary: datetime
    persisted_phase: IntradayAnalysisPhase
    evidence_snapshot_identity: str
    evidence_snapshot_integrity: str
    downstream_eligibility: Wo11DownstreamEligibility
    provenance: tuple[str, ...]
    schema_identity: str = WO11_MEMBER_IDENTITY
    schema_version: str = WO11_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "member_identity", "member_integrity")
        expected = eligibility_for_state(self.wo10_state)
        if (
            not _texts((
                self.canonical_subject_identity,
                self.wo10_result_identity,
                self.wo10_result_integrity,
                self.source_wo10_batch_identity,
                self.source_wo10_request_identity,
                self.source_probables_run_identity,
                self.source_probables_run_integrity,
                self.source_probable_result_identity,
                self.source_probable_result_integrity,
                self.evidence_snapshot_identity,
                self.evidence_snapshot_integrity,
            ))
            or type(self.market_family) is not IntradayMarketFamily
            or type(self.inherited_direction) is not SemanticDirection
            or self.inherited_direction
            not in {SemanticDirection.LONG, SemanticDirection.SHORT}
            or type(self.wo10_state) is not Wo10State
            or not self.wo10_reasons
            or any(type(item) is not Wo10ReasonCode for item in self.wo10_reasons)
            or type(self.wo10_policy) is not Wo10PolicyBinding
            or self.wo10_policy.supported_market_family is not self.market_family
            or not _aware(self.analysis_boundary)
            or type(self.persisted_phase) is not IntradayAnalysisPhase
            or self.downstream_eligibility is not expected
            or not _texts(self.provenance)
            or self.schema_identity != WO11_MEMBER_IDENTITY
            or self.schema_version != WO11_CONTRACT_VERSION
            or self.member_identity != _identity("INTRADAY-WO11-MEMBER-V1-", values)
            or self.member_integrity
            != _identity("INTEGRITY-INTRADAY-WO11-MEMBER-V1-", values)
        ):
            raise Wo11ContractError("WO11_MEMBER_INVALID")


def create_wo11_member(
    *,
    source: Wo11SourceBatchBinding,
    batch: Wo10BatchResult,
    request: Wo10ReconciliationRequest,
    result: Wo10ReconciliationResult,
    provenance: tuple[str, ...],
) -> Wo11Member:
    probable = next((
        item for item in request.probable_bindings
        if item.canonical_subject_identity == result.canonical_subject_identity
    ), None)
    binding = next((
        item for item in batch.result_bindings
        if item.canonical_subject_identity == result.canonical_subject_identity
    ), None)
    if (
        type(source) is not Wo11SourceBatchBinding
        or type(batch) is not Wo10BatchResult
        or type(request) is not Wo10ReconciliationRequest
        or type(result) is not Wo10ReconciliationResult
        or probable is None
        or binding is None
        or source.market_family is not batch.market_family
        or source.batch_identity != batch.batch_identity
        or source.batch_integrity != batch.batch_integrity
        or source.request_identity != request.request_identity
        or source.request_integrity != request.request_integrity
        or result.result_identity != binding.result_identity
        or result.result_integrity != binding.result_integrity
        or result.request_identity != request.request_identity
        or result.request_integrity != request.request_integrity
        or result.market_family is not batch.market_family
        or result.policy != request.policy
        or result.inherited_direction is not probable.inherited_direction
        or result.analysis_boundary != probable.analysis_boundary
        or result.persisted_phase is not probable.persisted_phase
        or not _texts(provenance)
    ):
        raise Wo11ContractError("WO11_MEMBER_INPUT_INVALID")
    values = {
        "canonical_subject_identity": result.canonical_subject_identity,
        "market_family": result.market_family,
        "inherited_direction": result.inherited_direction,
        "wo10_result_identity": result.result_identity,
        "wo10_result_integrity": result.result_integrity,
        "wo10_state": result.state,
        "wo10_reasons": result.reasons,
        "wo10_policy": result.policy,
        "source_wo10_batch_identity": batch.batch_identity,
        "source_wo10_request_identity": request.request_identity,
        "source_probables_run_identity": request.probables_run_identity,
        "source_probables_run_integrity": request.probables_run_integrity,
        "source_probable_result_identity": probable.probable_result_identity,
        "source_probable_result_integrity": probable.probable_result_integrity,
        "analysis_boundary": result.analysis_boundary,
        "persisted_phase": result.persisted_phase,
        "evidence_snapshot_identity": result.evidence_snapshot_identity,
        "evidence_snapshot_integrity": result.evidence_snapshot_integrity,
        "downstream_eligibility": eligibility_for_state(result.state),
        "provenance": provenance,
        "schema_identity": WO11_MEMBER_IDENTITY,
        "schema_version": WO11_CONTRACT_VERSION,
    }
    return Wo11Member(
        member_identity=_identity("INTRADAY-WO11-MEMBER-V1-", values),
        member_integrity=_identity("INTEGRITY-INTRADAY-WO11-MEMBER-V1-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo11FamilyCount:
    market_family: IntradayMarketFamily
    count: int

    def __post_init__(self) -> None:
        if type(self.market_family) is not IntradayMarketFamily or type(self.count) is not int or self.count < 0:
            raise Wo11ContractError("WO11_FAMILY_COUNT_INVALID")


@dataclass(frozen=True, slots=True)
class Wo11StateCount:
    state: Wo10State
    count: int

    def __post_init__(self) -> None:
        if type(self.state) is not Wo10State or type(self.count) is not int or self.count < 0:
            raise Wo11ContractError("WO11_STATE_COUNT_INVALID")


@dataclass(frozen=True, slots=True)
class Wo11MemberBinding:
    member_identity: str
    member_integrity: str
    canonical_subject_identity: str
    market_family: IntradayMarketFamily

    def __post_init__(self) -> None:
        if not _texts((self.member_identity, self.member_integrity, self.canonical_subject_identity)) or type(self.market_family) is not IntradayMarketFamily:
            raise Wo11ContractError("WO11_MEMBER_BINDING_INVALID")


@dataclass(frozen=True, slots=True)
class Wo11PromotionPublication:
    publication_identity: str
    publication_integrity: str
    request_identity: str
    request_integrity: str
    source_batches: tuple[Wo11SourceBatchBinding, ...]
    member_bindings: tuple[Wo11MemberBinding, ...]
    member_count: int
    family_counts: tuple[Wo11FamilyCount, ...]
    state_counts: tuple[Wo11StateCount, ...]
    eligible_member_identities: tuple[str, ...]
    eligible_count: int
    published_at: datetime
    provenance: tuple[str, ...]
    schema_identity: str = WO11_PUBLICATION_IDENTITY
    schema_version: str = WO11_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "publication_identity", "publication_integrity")
        if (
            not _texts((self.request_identity, self.request_integrity))
            or not self.source_batches
            or tuple(sorted(self.source_batches, key=_source_key)) != self.source_batches
            or len({item.market_family for item in self.source_batches}) != len(self.source_batches)
            or not self.member_bindings
            or tuple(sorted(self.member_bindings, key=_member_binding_key)) != self.member_bindings
            or len({item.member_identity for item in self.member_bindings}) != len(self.member_bindings)
            or len({item.canonical_subject_identity for item in self.member_bindings}) != len(self.member_bindings)
            or self.member_count != len(self.member_bindings)
            or tuple(item.market_family for item in self.family_counts) != tuple(IntradayMarketFamily)
            or sum(item.count for item in self.family_counts) != self.member_count
            or tuple(item.state for item in self.state_counts) != WO10_STATE_PRECEDENCE
            or sum(item.count for item in self.state_counts) != self.member_count
            or tuple(sorted(set(self.eligible_member_identities))) != self.eligible_member_identities
            or any(item not in {binding.member_identity for binding in self.member_bindings} for item in self.eligible_member_identities)
            or self.eligible_count != len(self.eligible_member_identities)
            or not _aware(self.published_at)
            or not _texts(self.provenance)
            or self.schema_identity != WO11_PUBLICATION_IDENTITY
            or self.schema_version != WO11_CONTRACT_VERSION
            or self.publication_identity != _identity("INTRADAY-WO11-PUBLICATION-V1-", values)
            or self.publication_integrity != _identity("INTEGRITY-INTRADAY-WO11-PUBLICATION-V1-", values)
        ):
            raise Wo11ContractError("WO11_PUBLICATION_INVALID")


def create_wo11_publication(
    *,
    request: Wo11PublicationRequest,
    members: Sequence[Wo11Member],
    published_at: datetime,
    provenance: tuple[str, ...],
) -> Wo11PromotionPublication:
    retained = tuple(sorted(tuple(members), key=_member_key))
    if (
        type(request) is not Wo11PublicationRequest
        or not retained
        or any(type(item) is not Wo11Member for item in retained)
        or {item.source_wo10_batch_identity for item in retained}
        != {item.batch_identity for item in request.source_batches}
        or any(
            sum(item.source_wo10_batch_identity == source.batch_identity for item in retained)
            != source.published_population
            for source in request.source_batches
        )
        or len({item.canonical_subject_identity for item in retained}) != len(retained)
        or not _aware(published_at)
        or not _texts(provenance)
    ):
        raise Wo11ContractError("WO11_PUBLICATION_INPUT_INVALID")
    bindings = tuple(Wo11MemberBinding(
        item.member_identity,
        item.member_integrity,
        item.canonical_subject_identity,
        item.market_family,
    ) for item in retained)
    family_counts = tuple(Wo11FamilyCount(
        family, sum(item.market_family is family for item in retained)
    ) for family in IntradayMarketFamily)
    state_counts = tuple(Wo11StateCount(
        state, sum(item.wo10_state is state for item in retained)
    ) for state in WO10_STATE_PRECEDENCE)
    eligible = tuple(sorted(
        item.member_identity for item in retained
        if item.downstream_eligibility
        is Wo11DownstreamEligibility.ELIGIBLE_FOR_DOWNSTREAM_HANDOFF
    ))
    values = {
        "request_identity": request.request_identity,
        "request_integrity": request.request_integrity,
        "source_batches": request.source_batches,
        "member_bindings": bindings,
        "member_count": len(retained),
        "family_counts": family_counts,
        "state_counts": state_counts,
        "eligible_member_identities": eligible,
        "eligible_count": len(eligible),
        "published_at": published_at,
        "provenance": provenance,
        "schema_identity": WO11_PUBLICATION_IDENTITY,
        "schema_version": WO11_CONTRACT_VERSION,
    }
    return Wo11PromotionPublication(
        publication_identity=_identity("INTRADAY-WO11-PUBLICATION-V1-", values),
        publication_integrity=_identity("INTEGRITY-INTRADAY-WO11-PUBLICATION-V1-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class CurrentWo11PromotionPointer:
    pointer_identity: str
    pointer_integrity: str
    publication_identity: str
    publication_integrity: str
    source_batches: tuple[Wo11SourceBatchBinding, ...]
    eligible_member_identities: tuple[str, ...]
    state_counts: tuple[Wo11StateCount, ...]
    schema_identity: str = WO11_POINTER_IDENTITY
    schema_version: str = WO11_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "pointer_identity", "pointer_integrity")
        if (
            not _texts((self.publication_identity, self.publication_integrity))
            or not self.source_batches
            or tuple(sorted(self.source_batches, key=_source_key)) != self.source_batches
            or tuple(sorted(set(self.eligible_member_identities))) != self.eligible_member_identities
            or tuple(item.state for item in self.state_counts) != WO10_STATE_PRECEDENCE
            or self.schema_identity != WO11_POINTER_IDENTITY
            or self.schema_version != WO11_CONTRACT_VERSION
            or self.pointer_identity != _identity("CURRENT-INTRADAY-WO11-V1-", values)
            or self.pointer_integrity != _identity("INTEGRITY-CURRENT-INTRADAY-WO11-V1-", values)
        ):
            raise Wo11ContractError("WO11_POINTER_INVALID")


def create_current_wo11_pointer(publication: Wo11PromotionPublication) -> CurrentWo11PromotionPointer:
    if type(publication) is not Wo11PromotionPublication:
        raise Wo11ContractError("WO11_POINTER_INPUT_INVALID")
    values = {
        "publication_identity": publication.publication_identity,
        "publication_integrity": publication.publication_integrity,
        "source_batches": publication.source_batches,
        "eligible_member_identities": publication.eligible_member_identities,
        "state_counts": publication.state_counts,
        "schema_identity": WO11_POINTER_IDENTITY,
        "schema_version": WO11_CONTRACT_VERSION,
    }
    return CurrentWo11PromotionPointer(
        pointer_identity=_identity("CURRENT-INTRADAY-WO11-V1-", values),
        pointer_integrity=_identity("INTEGRITY-CURRENT-INTRADAY-WO11-V1-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo11DownstreamHandoffReference:
    handoff_identity: str
    handoff_integrity: str
    publication_identity: str
    publication_integrity: str
    member_identity: str
    member_integrity: str
    wo10_result_identity: str
    wo10_result_integrity: str
    canonical_subject_identity: str
    inherited_direction: SemanticDirection
    schema_identity: str = WO11_HANDOFF_IDENTITY
    schema_version: str = WO11_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "handoff_identity", "handoff_integrity")
        if (
            not _texts((
                self.publication_identity,
                self.publication_integrity,
                self.member_identity,
                self.member_integrity,
                self.wo10_result_identity,
                self.wo10_result_integrity,
                self.canonical_subject_identity,
            ))
            or type(self.inherited_direction) is not SemanticDirection
            or self.inherited_direction not in {SemanticDirection.LONG, SemanticDirection.SHORT}
            or self.schema_identity != WO11_HANDOFF_IDENTITY
            or self.schema_version != WO11_CONTRACT_VERSION
            or self.handoff_identity != _identity("INTRADAY-WO11-HANDOFF-V1-", values)
            or self.handoff_integrity != _identity("INTEGRITY-INTRADAY-WO11-HANDOFF-V1-", values)
        ):
            raise Wo11ContractError("WO11_HANDOFF_INVALID")


def create_wo11_handoff_reference(
    publication: Wo11PromotionPublication,
    member: Wo11Member,
) -> Wo11DownstreamHandoffReference:
    binding = next((item for item in publication.member_bindings if item.member_identity == member.member_identity), None)
    if (
        type(publication) is not Wo11PromotionPublication
        or type(member) is not Wo11Member
        or binding is None
        or binding.member_integrity != member.member_integrity
        or member.downstream_eligibility
        is not Wo11DownstreamEligibility.ELIGIBLE_FOR_DOWNSTREAM_HANDOFF
    ):
        raise Wo11ContractError("WO11_HANDOFF_INPUT_INVALID")
    values = {
        "publication_identity": publication.publication_identity,
        "publication_integrity": publication.publication_integrity,
        "member_identity": member.member_identity,
        "member_integrity": member.member_integrity,
        "wo10_result_identity": member.wo10_result_identity,
        "wo10_result_integrity": member.wo10_result_integrity,
        "canonical_subject_identity": member.canonical_subject_identity,
        "inherited_direction": member.inherited_direction,
        "schema_identity": WO11_HANDOFF_IDENTITY,
        "schema_version": WO11_CONTRACT_VERSION,
    }
    return Wo11DownstreamHandoffReference(
        handoff_identity=_identity("INTRADAY-WO11-HANDOFF-V1-", values),
        handoff_integrity=_identity("INTEGRITY-INTRADAY-WO11-HANDOFF-V1-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo11OperationProvenance:
    operation_identity: str
    operation_integrity: str
    request_identity: str
    request_integrity: str
    stage: Wo11OperationStage
    outcome: Wo11OperationOutcome
    started_at: datetime
    completed_at: datetime | None
    failed_at: datetime | None
    publication_identity: str | None
    failure_reason: str | None
    backend_identity: str | None
    process_identity: str | None
    provenance: tuple[str, ...]
    schema_identity: str = WO11_OPERATION_IDENTITY
    schema_version: str = WO11_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "operation_identity", "operation_integrity")
        complete = self.outcome is Wo11OperationOutcome.COMPLETED
        failed = self.outcome is Wo11OperationOutcome.FAILED
        if (
            not _texts((self.request_identity, self.request_integrity))
            or type(self.stage) is not Wo11OperationStage
            or type(self.outcome) is not Wo11OperationOutcome
            or not _aware(self.started_at)
            or (self.completed_at is not None and not _aware(self.completed_at))
            or (self.failed_at is not None and not _aware(self.failed_at))
            or complete != (self.completed_at is not None)
            or complete != (self.publication_identity is not None)
            or failed != (self.failed_at is not None)
            or failed != (self.failure_reason is not None)
            or (self.backend_identity is not None and not _text(self.backend_identity))
            or (self.process_identity is not None and not _text(self.process_identity))
            or not _texts(self.provenance)
            or self.schema_identity != WO11_OPERATION_IDENTITY
            or self.schema_version != WO11_CONTRACT_VERSION
            or self.operation_identity != _identity("INTRADAY-WO11-OPERATION-V1-", values)
            or self.operation_integrity != _identity("INTEGRITY-INTRADAY-WO11-OPERATION-V1-", values)
        ):
            raise Wo11ContractError("WO11_OPERATION_INVALID")


def create_wo11_operation_provenance(
    *,
    request: Wo11PublicationRequest,
    stage: Wo11OperationStage,
    outcome: Wo11OperationOutcome,
    started_at: datetime,
    completed_at: datetime | None = None,
    failed_at: datetime | None = None,
    publication: Wo11PromotionPublication | None = None,
    failure_reason: str | None = None,
    backend_identity: str | None = None,
    process_identity: str | None = None,
    provenance: tuple[str, ...],
) -> Wo11OperationProvenance:
    values = {
        "request_identity": request.request_identity,
        "request_integrity": request.request_integrity,
        "stage": stage,
        "outcome": outcome,
        "started_at": started_at,
        "completed_at": completed_at,
        "failed_at": failed_at,
        "publication_identity": None if publication is None else publication.publication_identity,
        "failure_reason": failure_reason,
        "backend_identity": backend_identity,
        "process_identity": process_identity,
        "provenance": provenance,
        "schema_identity": WO11_OPERATION_IDENTITY,
        "schema_version": WO11_CONTRACT_VERSION,
    }
    return Wo11OperationProvenance(
        operation_identity=_identity("INTRADAY-WO11-OPERATION-V1-", values),
        operation_integrity=_identity("INTEGRITY-INTRADAY-WO11-OPERATION-V1-", values),
        **values,
    )


def eligibility_for_state(state: Wo10State) -> Wo11DownstreamEligibility:
    if type(state) is not Wo10State:
        raise Wo11ContractError("WO11_STATE_INVALID")
    return (
        Wo11DownstreamEligibility.ELIGIBLE_FOR_DOWNSTREAM_HANDOFF
        if state is Wo10State.PROMOTION_READY
        else Wo11DownstreamEligibility.NOT_ELIGIBLE_FOR_DOWNSTREAM_HANDOFF
    )


def _family_order(value: IntradayMarketFamily) -> int:
    return tuple(IntradayMarketFamily).index(value)


def _source_key(value: Wo11SourceBatchBinding) -> int:
    return _family_order(value.market_family)


def _member_key(value: Wo11Member) -> tuple[int, str]:
    return _family_order(value.market_family), value.canonical_subject_identity


def _member_binding_key(value: Wo11MemberBinding) -> tuple[int, str]:
    return _family_order(value.market_family), value.canonical_subject_identity


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


__all__ = [name for name in globals() if name.startswith("WO11_") or name.startswith("Wo11") or name.startswith("CurrentWo11") or name.startswith("create_wo11") or name == "eligibility_for_state"]
