"""Immutable WO-B operational-readiness review contracts.

WO-B composes exact source-domain facts for review.  It does not evaluate or
replace those facts and grants no analytical, trading, lifecycle, Provider, or
broker authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, is_dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import json
from typing import Mapping, Sequence

from kronos.intraday.universe import IntradayMarketFamily


WO_B_CONTRACT_VERSION = "1.0.0"
WO_B_PRODUCT_IDENTITY = "KRONOS-INTRADAY-OPERATIONAL-READINESS-REVIEW-V1"
WO_B_POLICY_IDENTITY = (
    "KRONOS-INTRADAY-OPERATIONAL-READINESS-REVIEW-POLICY-V1"
)
WO_B_POLICY_VERSION = "1.0.0"
WO_B_AUTHORITY = "READ_ONLY_CROSS_DOMAIN_COMPOSITION"
WO_B_SOURCE_REFERENCE_IDENTITY = (
    "KRONOS-INTRADAY-OPERATIONAL-READINESS-SOURCE-REFERENCE-V1"
)
WO_B_REVIEW_ITEM_IDENTITY = (
    "KRONOS-INTRADAY-OPERATIONAL-READINESS-REVIEW-ITEM-V1"
)


class WoBContractError(ValueError):
    """Sanitized WO-B contract failure."""


class WoBReviewClassification(StrEnum):
    NOT_REACHED = "NOT_REACHED"
    AVAILABLE = "AVAILABLE"
    WAITING = "WAITING"
    BLOCKED = "BLOCKED"
    UNAVAILABLE = "UNAVAILABLE"
    TERMINAL = "TERMINAL"


class WoBClassificationBasis(StrEnum):
    EXPECTED_DOWNSTREAM_ABSENCE = "EXPECTED_DOWNSTREAM_ABSENCE"
    CURRENT_VALID_SOURCE = "CURRENT_VALID_SOURCE"
    SOURCE_WAITING = "SOURCE_WAITING"
    SOURCE_BLOCKED = "SOURCE_BLOCKED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    SOURCE_TERMINAL = "SOURCE_TERMINAL"


class WoBSourceBoundary(StrEnum):
    PROBABLES = "PROBABLES"
    ANALYTICAL_PROMOTION = "ANALYTICAL_PROMOTION"
    WO13_TRADE_PLAN = "WO13_TRADE_PLAN"
    WO14_RISK_OBSERVATION = "WO14_RISK_OBSERVATION"
    WO15_TIMING_HANDOFF = "WO15_TIMING_HANDOFF"
    WO16_SPONSOR_LIFECYCLE = "WO16_SPONSOR_LIFECYCLE"
    WO17_POSITION_MONITORING = "WO17_POSITION_MONITORING"
    DOMAIN_001_INSTRUMENT = "DOMAIN_001_INSTRUMENT"
    DOMAIN_008_SESSION = "DOMAIN_008_SESSION"


_CLASSIFICATION_BY_BASIS = {
    WoBClassificationBasis.EXPECTED_DOWNSTREAM_ABSENCE:
        WoBReviewClassification.NOT_REACHED,
    WoBClassificationBasis.CURRENT_VALID_SOURCE:
        WoBReviewClassification.AVAILABLE,
    WoBClassificationBasis.SOURCE_WAITING: WoBReviewClassification.WAITING,
    WoBClassificationBasis.SOURCE_BLOCKED: WoBReviewClassification.BLOCKED,
    WoBClassificationBasis.SOURCE_UNAVAILABLE:
        WoBReviewClassification.UNAVAILABLE,
    WoBClassificationBasis.SOURCE_TERMINAL: WoBReviewClassification.TERMINAL,
}


@dataclass(frozen=True, slots=True)
class WoBPolicyBinding:
    policy_identity: str = WO_B_POLICY_IDENTITY
    policy_version: str = WO_B_POLICY_VERSION
    product_identity: str = WO_B_PRODUCT_IDENTITY
    authority: str = WO_B_AUTHORITY
    read_only_cross_domain_composition: bool = True
    exact_identity_integrity_binding: bool = True
    immutable_review_snapshots: bool = True
    current_pointer_is_projection_only: bool = True
    global_trade_ready_boolean: str = "PROHIBITED"
    analytical_authority: bool = False
    discovery_probables_authority: bool = False
    promotion_authority: bool = False
    trade_construction_authority: bool = False
    risk_authority: bool = False
    entry_timing_authority: bool = False
    sponsor_decision_authority: bool = False
    position_authority: bool = False
    lifecycle_mutation_authority: bool = False
    monitoring_event_authority: bool = False
    journal_pnl_outcome_authority: bool = False
    broker_authority: bool = False
    provider_acquisition_authority: bool = False
    notification_delivery_authority: bool = False

    def __post_init__(self) -> None:
        if (
            self.policy_identity != WO_B_POLICY_IDENTITY
            or self.policy_version != WO_B_POLICY_VERSION
            or self.product_identity != WO_B_PRODUCT_IDENTITY
            or self.authority != WO_B_AUTHORITY
            or not all(
                (
                    self.read_only_cross_domain_composition,
                    self.exact_identity_integrity_binding,
                    self.immutable_review_snapshots,
                    self.current_pointer_is_projection_only,
                )
            )
            or self.global_trade_ready_boolean != "PROHIBITED"
            or any(
                value
                for name, value in asdict(self).items()
                if name.endswith("_authority")
            )
        ):
            raise WoBContractError("WO_B_POLICY_BINDING_INVALID")


@dataclass(frozen=True, slots=True)
class WoBSourceArtifactReference:
    reference_identity: str
    reference_integrity: str
    source_boundary: WoBSourceBoundary
    artifact_identity: str
    artifact_schema_identity: str
    artifact_schema_version: str
    source_policy_identity: str
    source_policy_version: str
    source_integrity_identity: str
    candidate_identity: str
    analysis_run_identity: str
    canonical_instrument_identity: str
    active_contract_identity: str | None
    exact_source_state: str
    exact_source_reason: str | None
    bounded_diagnostic: str | None
    observed_at: datetime
    current_at_review_boundary: bool
    superseded: bool
    currentness_required: bool
    schema_identity: str = WO_B_SOURCE_REFERENCE_IDENTITY
    schema_version: str = WO_B_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "reference_identity", "reference_integrity")
        if (
            type(self.source_boundary) is not WoBSourceBoundary
            or not _texts(
                (
                    self.artifact_identity,
                    self.artifact_schema_identity,
                    self.artifact_schema_version,
                    self.source_policy_identity,
                    self.source_policy_version,
                    self.source_integrity_identity,
                    self.candidate_identity,
                    self.analysis_run_identity,
                    self.canonical_instrument_identity,
                    self.exact_source_state,
                )
            )
            or not _optional_text(self.active_contract_identity)
            or not _code(self.exact_source_state)
            or not _optional_code(self.exact_source_reason)
            or not _optional_code(self.bounded_diagnostic)
            or not _aware(self.observed_at)
            or type(self.current_at_review_boundary) is not bool
            or type(self.superseded) is not bool
            or type(self.currentness_required) is not bool
            or self.current_at_review_boundary and self.superseded
            or self.currentness_required
            and (not self.current_at_review_boundary or self.superseded)
            or self.schema_identity != WO_B_SOURCE_REFERENCE_IDENTITY
            or self.schema_version != WO_B_CONTRACT_VERSION
            or self.reference_identity
            != _identity("INTRADAY-WO-B-SOURCE-REFERENCE-", values)
            or self.reference_integrity
            != _identity("INTEGRITY-INTRADAY-WO-B-SOURCE-REFERENCE-", values)
        ):
            raise WoBContractError("WO_B_SOURCE_REFERENCE_INVALID")


@dataclass(frozen=True, slots=True)
class WoBReviewItem:
    review_item_identity: str
    review_item_integrity: str
    source_boundary: WoBSourceBoundary
    review_classification: WoBReviewClassification
    classification_basis: WoBClassificationBasis
    source_reference_identity: str | None
    exact_source_state: str
    exact_source_reason: str | None
    bounded_diagnostic: str | None
    next_governed_stage: str | None
    schema_identity: str = WO_B_REVIEW_ITEM_IDENTITY
    schema_version: str = WO_B_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "review_item_identity", "review_item_integrity")
        not_reached = (
            self.classification_basis
            is WoBClassificationBasis.EXPECTED_DOWNSTREAM_ABSENCE
        )
        if (
            type(self.source_boundary) is not WoBSourceBoundary
            or type(self.review_classification) is not WoBReviewClassification
            or type(self.classification_basis) is not WoBClassificationBasis
            or self.review_classification
            is not _CLASSIFICATION_BY_BASIS[self.classification_basis]
            or not_reached != (self.source_reference_identity is None)
            or not _optional_text(self.source_reference_identity)
            or not _code(self.exact_source_state)
            or not _optional_code(self.exact_source_reason)
            or not _optional_code(self.bounded_diagnostic)
            or not _optional_code(self.next_governed_stage)
            or not_reached and self.exact_source_state != "NOT_REACHED"
            or self.schema_identity != WO_B_REVIEW_ITEM_IDENTITY
            or self.schema_version != WO_B_CONTRACT_VERSION
            or self.review_item_identity
            != _identity("INTRADAY-WO-B-REVIEW-ITEM-", values)
            or self.review_item_integrity
            != _identity("INTEGRITY-INTRADAY-WO-B-REVIEW-ITEM-", values)
        ):
            raise WoBContractError("WO_B_REVIEW_ITEM_INVALID")


@dataclass(frozen=True, slots=True)
class WoBOperationalReviewSnapshot:
    review_snapshot_identity: str
    snapshot_integrity_hash: str
    review_policy_identity: str
    review_policy_version: str
    review_boundary: datetime
    created_at: datetime
    candidate_identity: str
    opportunity_identity: str | None
    analysis_run_lineage: tuple[str, ...]
    canonical_subject_identity: str
    market_family: IntradayMarketFamily
    canonical_instrument_identity: str
    active_contract_identity: str | None
    source_artifact_references: tuple[WoBSourceArtifactReference, ...]
    review_items: tuple[WoBReviewItem, ...]
    policy: WoBPolicyBinding
    provenance: tuple[str, ...]
    schema_identity: str = WO_B_PRODUCT_IDENTITY
    schema_version: str = WO_B_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(
            self, "review_snapshot_identity", "snapshot_integrity_hash"
        )
        mcx = self.market_family is IntradayMarketFamily.MCX
        references = {
            item.reference_identity: item for item in self.source_artifact_references
        }
        boundaries = [item.source_boundary for item in self.review_items]
        reference_ids = [item.reference_identity for item in self.source_artifact_references]
        if (
            self.review_policy_identity != WO_B_POLICY_IDENTITY
            or self.review_policy_version != WO_B_POLICY_VERSION
            or not _aware(self.review_boundary)
            or not _aware(self.created_at)
            or self.created_at < self.review_boundary
            or not _texts(
                (
                    self.candidate_identity,
                    *self.analysis_run_lineage,
                    self.canonical_subject_identity,
                    self.canonical_instrument_identity,
                    *self.provenance,
                )
            )
            or not self.analysis_run_lineage
            or len(self.analysis_run_lineage) != len(set(self.analysis_run_lineage))
            or not _optional_text(self.opportunity_identity)
            or type(self.market_family) is not IntradayMarketFamily
            or mcx != (self.active_contract_identity is not None)
            or not _optional_text(self.active_contract_identity)
            or not self.review_items
            or len(boundaries) != len(set(boundaries))
            or len(reference_ids) != len(set(reference_ids))
            or type(self.policy) is not WoBPolicyBinding
            or self.schema_identity != WO_B_PRODUCT_IDENTITY
            or self.schema_version != WO_B_CONTRACT_VERSION
            or any(not self._reference_matches(item) for item in references.values())
            or any(not self._review_matches(item, references) for item in self.review_items)
            or self.review_snapshot_identity
            != _identity("INTRADAY-WO-B-REVIEW-SNAPSHOT-", values)
            or self.snapshot_integrity_hash != canonical_sha256(values)
        ):
            raise WoBContractError("WO_B_REVIEW_SNAPSHOT_INVALID")

    def _reference_matches(self, item: WoBSourceArtifactReference) -> bool:
        return (
            type(item) is WoBSourceArtifactReference
            and item.candidate_identity == self.candidate_identity
            and item.analysis_run_identity in self.analysis_run_lineage
            and item.canonical_instrument_identity
            == self.canonical_instrument_identity
            and item.active_contract_identity == self.active_contract_identity
            and item.observed_at <= self.review_boundary
        )

    @staticmethod
    def _review_matches(
        item: WoBReviewItem,
        references: Mapping[str, WoBSourceArtifactReference],
    ) -> bool:
        if type(item) is not WoBReviewItem:
            return False
        if item.source_reference_identity is None:
            return item.review_classification is WoBReviewClassification.NOT_REACHED
        reference = references.get(item.source_reference_identity)
        return (
            reference is not None
            and reference.source_boundary is item.source_boundary
            and reference.exact_source_state == item.exact_source_state
            and reference.exact_source_reason == item.exact_source_reason
            and reference.bounded_diagnostic == item.bounded_diagnostic
            and (
                reference.current_at_review_boundary and not reference.superseded
                or item.review_classification
                is WoBReviewClassification.UNAVAILABLE
            )
        )


def create_source_artifact_reference(**values: object) -> WoBSourceArtifactReference:
    values = {
        **values,
        "schema_identity": WO_B_SOURCE_REFERENCE_IDENTITY,
        "schema_version": WO_B_CONTRACT_VERSION,
    }
    return WoBSourceArtifactReference(
        reference_identity=_identity("INTRADAY-WO-B-SOURCE-REFERENCE-", values),
        reference_integrity=_identity(
            "INTEGRITY-INTRADAY-WO-B-SOURCE-REFERENCE-", values
        ),
        **values,  # type: ignore[arg-type]
    )


def create_review_item(
    *,
    source_boundary: WoBSourceBoundary,
    classification_basis: WoBClassificationBasis,
    source_reference: WoBSourceArtifactReference | None = None,
    next_governed_stage: str | None = None,
) -> WoBReviewItem:
    not_reached = (
        classification_basis
        is WoBClassificationBasis.EXPECTED_DOWNSTREAM_ABSENCE
    )
    if not_reached != (source_reference is None):
        raise WoBContractError("WO_B_REVIEW_SOURCE_BINDING_INVALID")
    values = {
        "source_boundary": source_boundary,
        "review_classification": _CLASSIFICATION_BY_BASIS[classification_basis],
        "classification_basis": classification_basis,
        "source_reference_identity": (
            None if source_reference is None else source_reference.reference_identity
        ),
        "exact_source_state": (
            "NOT_REACHED"
            if source_reference is None
            else source_reference.exact_source_state
        ),
        "exact_source_reason": (
            None if source_reference is None else source_reference.exact_source_reason
        ),
        "bounded_diagnostic": (
            None if source_reference is None else source_reference.bounded_diagnostic
        ),
        "next_governed_stage": next_governed_stage,
        "schema_identity": WO_B_REVIEW_ITEM_IDENTITY,
        "schema_version": WO_B_CONTRACT_VERSION,
    }
    return WoBReviewItem(
        review_item_identity=_identity("INTRADAY-WO-B-REVIEW-ITEM-", values),
        review_item_integrity=_identity(
            "INTEGRITY-INTRADAY-WO-B-REVIEW-ITEM-", values
        ),
        **values,
    )


def create_operational_review_snapshot(**values: object) -> WoBOperationalReviewSnapshot:
    values = {
        **values,
        "review_policy_identity": WO_B_POLICY_IDENTITY,
        "review_policy_version": WO_B_POLICY_VERSION,
        "policy": WoBPolicyBinding(),
        "schema_identity": WO_B_PRODUCT_IDENTITY,
        "schema_version": WO_B_CONTRACT_VERSION,
    }
    return WoBOperationalReviewSnapshot(
        review_snapshot_identity=_identity(
            "INTRADAY-WO-B-REVIEW-SNAPSHOT-", values
        ),
        snapshot_integrity_hash=canonical_sha256(values),
        **values,  # type: ignore[arg-type]
    )


def canonical_document_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            _normalize(value), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    except WoBContractError:
        raise
    except (TypeError, ValueError) as error:
        raise WoBContractError("WO_B_CANONICAL_DOCUMENT_INVALID") from error


def canonical_sha256(value: object) -> str:
    return sha256(canonical_document_bytes(value)).hexdigest()


def wo_b_policy_from_dict(payload: Mapping[str, object]) -> WoBPolicyBinding:
    if type(payload) is not dict or set(payload) != {
        item.name for item in fields(WoBPolicyBinding)
    }:
        raise WoBContractError("WO_B_CONTRACT_FIELDS_INVALID")
    try:
        return WoBPolicyBinding(**payload)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise WoBContractError("WO_B_POLICY_BINDING_INVALID") from error


def _without(value: object, *names: str) -> dict[str, object]:
    return {item.name: getattr(value, item.name) for item in fields(value) if item.name not in names}


def _identity(prefix: str, value: object) -> str:
    return prefix + canonical_sha256(value).upper()


def _normalize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _normalize(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        if not _aware(value):
            raise WoBContractError("WO_B_TIMESTAMP_TIMEZONE_REQUIRED")
        return value.isoformat()
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise WoBContractError("WO_B_CANONICAL_KEY_INVALID")
        return {key: _normalize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    if isinstance(value, float):
        raise WoBContractError("WO_B_FLOAT_PROHIBITED")
    if value is None or type(value) in {str, int, bool}:
        return value
    raise WoBContractError("WO_B_CANONICAL_VALUE_INVALID")


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _text(value: object) -> bool:
    return type(value) is str and bool(value.strip())


def _texts(values: Sequence[object]) -> bool:
    return bool(values) and all(_text(value) for value in values)


def _optional_text(value: object) -> bool:
    return value is None or _text(value)


def _code(value: object) -> bool:
    return (
        type(value) is str
        and 0 < len(value) <= 160
        and all(character.isupper() or character.isdigit() or character in "_-.:" for character in value)
    )


def _optional_code(value: object) -> bool:
    return value is None or _code(value)


__all__ = [
    name
    for name in globals()
    if name.startswith(("WO_B_", "WoB", "create_", "canonical_", "wo_b_"))
]
