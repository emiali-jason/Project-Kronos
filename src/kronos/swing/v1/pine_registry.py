"""Product-scoped authority registry for Swing V1 Pine publishers.

The registry is explicit local authority.  Webhook arrival, source identity, or
historical authority never changes it.  All operations return a new immutable
registry and leave historical evidence untouched.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
import re

from kronos.swing.v1.pine_evidence import (
    PINE_EVIDENCE_CONTRACT_ID,
    PINE_EVIDENCE_CONTRACT_VERSION,
    PineCompatibilityClass,
    PineEvidenceEnvelope,
    PineProduct,
    PinePublisherRole,
)


def _text(value: object) -> bool:
    return type(value) is str and bool(value.strip())


def _sha(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None


class PineApprovalStatus(StrEnum):
    VALIDATION_PENDING = "VALIDATION_PENDING"
    VALIDATED = "VALIDATED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class PineRegistryAuthority(StrEnum):
    AUTHORITATIVE = "AUTHORITATIVE"
    SHADOW_ONLY = "SHADOW_ONLY"
    REJECTED_UNKNOWN_PUBLISHER = "REJECTED_UNKNOWN_PUBLISHER"
    REJECTED_INACTIVE_PRODUCTION = "REJECTED_INACTIVE_PRODUCTION"
    REJECTED_WRONG_PRODUCT = "REJECTED_WRONG_PRODUCT"
    REJECTED_NOT_YET_EFFECTIVE = "REJECTED_NOT_YET_EFFECTIVE"


class PineRegistryOperation(StrEnum):
    PROMOTION = "PROMOTION"
    ROLLBACK = "ROLLBACK"


@dataclass(frozen=True, slots=True)
class ApprovedPineRegistryEntry:
    registry_entry_id: str
    publisher_registry_id: str
    product: PineProduct
    publisher_role: PinePublisherRole
    pine_identity: str
    pine_version: str
    pine_build: str
    pine_source_sha256: str
    evidence_contract_id: str
    evidence_contract_version: str
    compatibility_class: PineCompatibilityClass
    approval_status: PineApprovalStatus
    approved_at: datetime | None
    effective_from: datetime | None
    supersedes: str | None
    superseded_by: str | None
    rollback_parent: str | None
    validation_reference: str
    is_active_for_authority: bool
    promotion_source: str | None = None

    def __post_init__(self) -> None:
        approval_timing_required = self.approval_status in {
            PineApprovalStatus.APPROVED,
            PineApprovalStatus.SUPERSEDED,
        }
        if (
            not _text(self.registry_entry_id)
            or not _text(self.publisher_registry_id)
            or type(self.product) is not PineProduct
            or type(self.publisher_role) is not PinePublisherRole
            or any(
                not _text(item)
                for item in (self.pine_identity, self.pine_version, self.pine_build)
            )
            or not _sha(self.pine_source_sha256)
            or self.evidence_contract_id != PINE_EVIDENCE_CONTRACT_ID
            or self.evidence_contract_version != PINE_EVIDENCE_CONTRACT_VERSION
            or type(self.compatibility_class) is not PineCompatibilityClass
            or type(self.approval_status) is not PineApprovalStatus
            or (self.approved_at is not None and not _aware(self.approved_at))
            or (self.effective_from is not None and not _aware(self.effective_from))
            or any(
                item is not None and not _text(item)
                for item in (
                    self.supersedes,
                    self.superseded_by,
                    self.rollback_parent,
                    self.promotion_source,
                )
            )
            or not _text(self.validation_reference)
            or type(self.is_active_for_authority) is not bool
            or (approval_timing_required != (self.approved_at is not None))
            or (approval_timing_required != (self.effective_from is not None))
            or (
                approval_timing_required
                and self.approved_at is not None
                and self.effective_from is not None
                and self.approved_at > self.effective_from
            )
            or (
                self.publisher_role is PinePublisherRole.CANDIDATE
                and self.is_active_for_authority
            )
            or (
                self.is_active_for_authority
                and (
                    self.publisher_role is not PinePublisherRole.PRODUCTION
                    or self.approval_status is not PineApprovalStatus.APPROVED
                )
            )
        ):
            raise ValueError("APPROVED_PINE_REGISTRY_ENTRY_INVALID")

    def matches(self, envelope: PineEvidenceEnvelope) -> bool:
        producer = envelope.producer
        return (
            self.product is envelope.product
            and self.publisher_registry_id == producer.publisher_registry_id
            and self.publisher_role is producer.publisher_role
            and self.pine_identity == producer.pine_identity
            and self.pine_version == producer.pine_version
            and self.pine_build == producer.pine_build
            and self.pine_source_sha256 == producer.pine_source_sha256
            and self.evidence_contract_id == producer.evidence_contract_id
            and self.evidence_contract_version == producer.evidence_contract_version
            and self.compatibility_class is producer.compatibility_class
        )


@dataclass(frozen=True, slots=True)
class PineRegistryTransition:
    operation: PineRegistryOperation
    product: PineProduct
    from_entry_id: str
    to_entry_id: str
    occurred_at: datetime
    validation_reference: str
    candidate_entry_id: str | None = None

    def __post_init__(self) -> None:
        if (
            type(self.operation) is not PineRegistryOperation
            or type(self.product) is not PineProduct
            or not _text(self.from_entry_id)
            or not _text(self.to_entry_id)
            or self.from_entry_id == self.to_entry_id
            or not _aware(self.occurred_at)
            or not _text(self.validation_reference)
            or (
                self.candidate_entry_id is not None
                and not _text(self.candidate_entry_id)
            )
        ):
            raise ValueError("PINE_REGISTRY_TRANSITION_INVALID")


@dataclass(frozen=True, slots=True)
class ApprovedPineRegistry:
    registry_id: str
    product: PineProduct
    entries: tuple[ApprovedPineRegistryEntry, ...]
    transitions: tuple[PineRegistryTransition, ...] = ()

    def __post_init__(self) -> None:
        if (
            not _text(self.registry_id)
            or type(self.product) is not PineProduct
            or type(self.entries) is not tuple
            or not self.entries
            or any(
                type(item) is not ApprovedPineRegistryEntry
                or item.product is not self.product
                or item.publisher_registry_id != self.registry_id
                for item in self.entries
            )
            or len({item.registry_entry_id for item in self.entries})
            != len(self.entries)
            or len(
                {
                    (
                        item.publisher_role,
                        item.pine_identity,
                        item.pine_version,
                        item.pine_build,
                        item.pine_source_sha256,
                        item.evidence_contract_id,
                        item.evidence_contract_version,
                        item.compatibility_class,
                    )
                    for item in self.entries
                }
            )
            != len(self.entries)
            or sum(item.is_active_for_authority for item in self.entries) > 1
            or type(self.transitions) is not tuple
            or any(
                type(item) is not PineRegistryTransition
                or item.product is not self.product
                for item in self.transitions
            )
        ):
            raise ValueError("APPROVED_PINE_REGISTRY_INVALID")
        ids = {item.registry_entry_id for item in self.entries}
        if any(
            reference is not None and reference not in ids
            for item in self.entries
            for reference in (
                item.supersedes,
                item.superseded_by,
                item.rollback_parent,
                item.promotion_source,
            )
        ):
            raise ValueError("APPROVED_PINE_REGISTRY_LINEAGE_INVALID")

    def entry(self, registry_entry_id: str) -> ApprovedPineRegistryEntry:
        for item in self.entries:
            if item.registry_entry_id == registry_entry_id:
                return item
        raise KeyError("PINE_REGISTRY_ENTRY_UNKNOWN")

    def authority_for(self, envelope: PineEvidenceEnvelope) -> PineRegistryAuthority:
        if envelope.product is not self.product:
            return PineRegistryAuthority.REJECTED_WRONG_PRODUCT
        matching = tuple(item for item in self.entries if item.matches(envelope))
        if not matching:
            return PineRegistryAuthority.REJECTED_UNKNOWN_PUBLISHER
        entry = matching[0]
        if entry.publisher_role is PinePublisherRole.CANDIDATE:
            return PineRegistryAuthority.SHADOW_ONLY
        if not entry.is_active_for_authority:
            return PineRegistryAuthority.REJECTED_INACTIVE_PRODUCTION
        if (
            entry.approval_status is not PineApprovalStatus.APPROVED
            or entry.effective_from is None
        ):
            return PineRegistryAuthority.REJECTED_INACTIVE_PRODUCTION
        if envelope.observation_boundary.evaluated_ts < entry.effective_from:
            return PineRegistryAuthority.REJECTED_NOT_YET_EFFECTIVE
        return PineRegistryAuthority.AUTHORITATIVE

    def authoritative_entry(
        self, envelope: PineEvidenceEnvelope
    ) -> ApprovedPineRegistryEntry | None:
        if self.authority_for(envelope) is not PineRegistryAuthority.AUTHORITATIVE:
            return None
        return next(item for item in self.entries if item.matches(envelope))

    def promote(
        self,
        *,
        candidate_entry_id: str,
        current_production_entry_id: str,
        production_entry_id: str,
        approved_at: datetime,
        effective_from: datetime,
        validation_reference: str,
    ) -> ApprovedPineRegistry:
        candidate = self.entry(candidate_entry_id)
        current = self.entry(current_production_entry_id)
        if (
            candidate.publisher_role is not PinePublisherRole.CANDIDATE
            or candidate.approval_status is not PineApprovalStatus.VALIDATED
            or current.publisher_role is not PinePublisherRole.PRODUCTION
            or not current.is_active_for_authority
            or any(item.registry_entry_id == production_entry_id for item in self.entries)
            or not _aware(approved_at)
            or not _aware(effective_from)
            or approved_at > effective_from
            or not _text(validation_reference)
        ):
            raise ValueError("PINE_REGISTRY_PROMOTION_INVALID")
        promoted = ApprovedPineRegistryEntry(
            registry_entry_id=production_entry_id,
            publisher_registry_id=self.registry_id,
            product=self.product,
            publisher_role=PinePublisherRole.PRODUCTION,
            pine_identity=candidate.pine_identity,
            pine_version=candidate.pine_version,
            pine_build=candidate.pine_build,
            pine_source_sha256=candidate.pine_source_sha256,
            evidence_contract_id=candidate.evidence_contract_id,
            evidence_contract_version=candidate.evidence_contract_version,
            compatibility_class=candidate.compatibility_class,
            approval_status=PineApprovalStatus.APPROVED,
            approved_at=approved_at,
            effective_from=effective_from,
            supersedes=current.registry_entry_id,
            superseded_by=None,
            rollback_parent=current.registry_entry_id,
            validation_reference=validation_reference,
            is_active_for_authority=True,
            promotion_source=candidate.registry_entry_id,
        )
        updated_entries = tuple(
            replace(
                item,
                approval_status=PineApprovalStatus.SUPERSEDED,
                superseded_by=promoted.registry_entry_id,
                is_active_for_authority=False,
            )
            if item.registry_entry_id == current.registry_entry_id
            else item
            for item in self.entries
        )
        transition = PineRegistryTransition(
            operation=PineRegistryOperation.PROMOTION,
            product=self.product,
            from_entry_id=current.registry_entry_id,
            to_entry_id=promoted.registry_entry_id,
            occurred_at=approved_at,
            validation_reference=validation_reference,
            candidate_entry_id=candidate.registry_entry_id,
        )
        return ApprovedPineRegistry(
            registry_id=self.registry_id,
            product=self.product,
            entries=(*updated_entries, promoted),
            transitions=(*self.transitions, transition),
        )

    def rollback(
        self,
        *,
        current_production_entry_id: str,
        rollback_entry_id: str,
        approved_at: datetime,
        effective_from: datetime,
        validation_reference: str,
    ) -> ApprovedPineRegistry:
        current = self.entry(current_production_entry_id)
        target = self.entry(rollback_entry_id)
        if (
            current.publisher_role is not PinePublisherRole.PRODUCTION
            or not current.is_active_for_authority
            or current.rollback_parent != target.registry_entry_id
            or target.publisher_role is not PinePublisherRole.PRODUCTION
            or target.pine_source_sha256 == current.pine_source_sha256
            or not _aware(approved_at)
            or not _aware(effective_from)
            or approved_at > effective_from
            or not _text(validation_reference)
        ):
            raise ValueError("PINE_REGISTRY_ROLLBACK_INVALID")
        updated: list[ApprovedPineRegistryEntry] = []
        for item in self.entries:
            if item.registry_entry_id == current.registry_entry_id:
                updated.append(
                    replace(
                        item,
                        approval_status=PineApprovalStatus.SUPERSEDED,
                        is_active_for_authority=False,
                    )
                )
            elif item.registry_entry_id == target.registry_entry_id:
                updated.append(
                    replace(
                        item,
                        approval_status=PineApprovalStatus.APPROVED,
                        approved_at=approved_at,
                        effective_from=effective_from,
                        is_active_for_authority=True,
                    )
                )
            else:
                updated.append(item)
        transition = PineRegistryTransition(
            operation=PineRegistryOperation.ROLLBACK,
            product=self.product,
            from_entry_id=current.registry_entry_id,
            to_entry_id=target.registry_entry_id,
            occurred_at=approved_at,
            validation_reference=validation_reference,
        )
        return ApprovedPineRegistry(
            registry_id=self.registry_id,
            product=self.product,
            entries=tuple(updated),
            transitions=(*self.transitions, transition),
        )


__all__ = [
    "ApprovedPineRegistry",
    "ApprovedPineRegistryEntry",
    "PineApprovalStatus",
    "PineRegistryAuthority",
    "PineRegistryOperation",
    "PineRegistryTransition",
]
