"""Provider-neutral meanings for canonical EDD-002 capability assessment."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class CapabilityIdentifier(StrEnum):
    """The closed ADR-007 Provider Capability identifier set."""

    INSTRUMENT_REFERENCE = "INSTRUMENT_REFERENCE_CAPABILITY"
    FULL_QUOTE_SNAPSHOT = "FULL_QUOTE_SNAPSHOT_CAPABILITY"
    OHLC_SNAPSHOT = "OHLC_SNAPSHOT_CAPABILITY"
    LTP_SNAPSHOT = "LTP_SNAPSHOT_CAPABILITY"
    HISTORICAL_OBSERVATION = "HISTORICAL_OBSERVATION_CAPABILITY"
    LIVE_OBSERVATION_STREAMING = "LIVE_OBSERVATION_STREAMING_CAPABILITY"


class EvidenceClass(StrEnum):
    """The closed EDD-002 evidence hierarchy."""

    OFFICIAL_PROVIDER_DOCUMENTATION = "OFFICIAL_PROVIDER_DOCUMENTATION"
    APPROVED_ADAPTER_LOCKED_SDK_COMPATIBILITY = (
        "APPROVED_ADAPTER_LOCKED_SDK_COMPATIBILITY"
    )
    AUTHORIZED_PROVIDER_ENDPOINT_EVIDENCE = (
        "AUTHORIZED_PROVIDER_ENDPOINT_EVIDENCE"
    )
    LATER_AUTHORIZED_RUNTIME_EVIDENCE = "LATER_AUTHORIZED_RUNTIME_EVIDENCE"


class EvidenceAssertion(StrEnum):
    """Provider-neutral assertion carried by one approved evidence item."""

    SUPPORTS = "SUPPORTS"
    DOES_NOT_SUPPORT = "DOES_NOT_SUPPORT"
    WITHDRAWN = "WITHDRAWN"
    COMPATIBLE = "COMPATIBLE"
    LIMITATION = "LIMITATION"
    OBSERVED_BEHAVIOUR = "OBSERVED_BEHAVIOUR"
    CONFLICT = "CONFLICT"


class EvidenceCurrentness(StrEnum):
    """Currentness of one evidence item."""

    CURRENT = "CURRENT"
    STALE = "STALE"
    UNDETERMINED = "CURRENTNESS_UNDETERMINED"


class EvidenceScope(StrEnum):
    """Whether evidence is Provider-wide or context-specific."""

    PROVIDER_WIDE = "PROVIDER_WIDE"
    CONTEXT_SPECIFIC = "CONTEXT_SPECIFIC"


class ProviderSupport(StrEnum):
    """Provider-support determination independent of implementation."""

    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    UNDETERMINED = "UNDETERMINED"


class ImplementationDisposition(StrEnum):
    """KRONOS implementation disposition independent of Provider support."""

    IMPLEMENTED = "IMPLEMENTED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    DEFERRED = "DEFERRED"


class CapabilityAssessmentOutcomeKind(StrEnum):
    """The only outcomes of request processing or assessment activity."""

    COMPLETED = "ASSESSMENT_COMPLETED"
    NOT_PERFORMED = "ASSESSMENT_NOT_PERFORMED"
    FAILED = "ASSESSMENT_FAILED"


class CapabilityAssessmentReason(StrEnum):
    """Stable non-sensitive request, failure and indeterminacy reasons."""

    UNKNOWN_CAPABILITY_IDENTIFIER = "UNKNOWN_CAPABILITY_IDENTIFIER"
    INVALID_REQUEST = "INVALID_REQUEST"
    MISSING_PREREQUISITE = "MISSING_PREREQUISITE"
    UNAUTHORIZED_EVIDENCE_CLASS = "UNAUTHORIZED_EVIDENCE_CLASS"
    UNAPPROVED_EVIDENCE_SOURCE = "UNAPPROVED_EVIDENCE_SOURCE"
    SENSITIVE_INPUT = "SENSITIVE_INPUT"
    DUPLICATE_ASSESSMENT_ID = "DUPLICATE_ASSESSMENT_ID"
    EVIDENCE_MISMATCH = "EVIDENCE_MISMATCH"
    LIMITATION_MISMATCH = "LIMITATION_MISMATCH"
    PRIOR_RECORD_MISMATCH = "PRIOR_RECORD_MISMATCH"
    EVIDENCE_PROCESSING_FAILURE = "EVIDENCE_PROCESSING_FAILURE"
    EVIDENCE_ABSENT = "EVIDENCE_ABSENT"
    EVIDENCE_STALE = "EVIDENCE_STALE"
    EVIDENCE_CONFLICT = "EVIDENCE_CONFLICT"
    EVIDENCE_CURRENTNESS_UNDETERMINED = "EVIDENCE_CURRENTNESS_UNDETERMINED"
    GOVERNANCE_CONFLICT = "GOVERNANCE_CONFLICT"


class LimitationCategory(StrEnum):
    """Approved EDD-002 limitation categories."""

    REQUEST_SIZE = "request-size"
    SUBSCRIPTION_COUNT = "subscription-count"
    CONNECTION_COUNT = "connection-count"
    INTERVAL_SUPPORT = "interval-support"
    DATA_CURRENTNESS = "data-currentness"
    PROVIDER_SCOPE = "provider-scope"
    COMPATIBILITY = "compatibility"
    OTHER_DOCUMENTED_TECHNICAL_CONSTRAINT = "other-documented-technical-constraint"


@dataclass(frozen=True, slots=True)
class CapabilityAssessmentRequest:
    """Immutable input submitted to pre-boundary request processing."""

    assessment_id: str
    provider: str
    capability_identifier: CapabilityIdentifier | str
    requested_evidence_classes: tuple[EvidenceClass | str, ...]
    evidence_references: tuple[str, ...]
    assessment_authority_reference: str
    compatibility_basis: str
    assessment_time: datetime
    prior_record_id: str | None = None
    supersession_reason: str | None = None
    provider_context_reference: str | None = None


@dataclass(frozen=True, slots=True)
class CapabilityEvidence:
    """Immutable, non-sensitive evidence bounded to one capability."""

    evidence_id: str
    evidence_class: EvidenceClass
    provider: str
    capability_identifier: CapabilityIdentifier
    source_reference: str
    assertion: EvidenceAssertion
    provider_api_basis: str
    currentness: EvidenceCurrentness
    scope: EvidenceScope
    evidence_time: datetime | None = None
    sdk_version_basis: str | None = None
    adapter_revision_basis: str | None = None
    authorization_reference: str | None = None
    integrity_reference: str | None = None
    supersedes_evidence_id: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.evidence_id, "evidence id")
        _require_text(self.provider, "provider")
        _require_text(self.source_reference, "source reference")
        _require_text(self.provider_api_basis, "provider API basis")
        _require_aware_time(self.evidence_time, "evidence time")


@dataclass(frozen=True, slots=True)
class ImplementationDispositionEvidence:
    """Approved repository evidence for one implementation disposition."""

    capability_identifier: CapabilityIdentifier
    disposition: ImplementationDisposition
    authority_reference: str
    contract_reference: str | None = None
    adapter_reference: str | None = None
    repository_revision: str | None = None
    dependency_basis: str | None = None
    boundary_verified: bool = False
    reason: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.authority_reference, "authority reference")
        if self.disposition is ImplementationDisposition.IMPLEMENTED:
            required = (
                self.contract_reference,
                self.adapter_reference,
                self.repository_revision,
                self.dependency_basis,
            )
            if not self.boundary_verified or any(not value for value in required):
                raise ValueError(
                    "IMPLEMENTED requires contract, adapter, revision, dependency "
                    "and boundary-verification evidence"
                )
        if self.disposition is ImplementationDisposition.DEFERRED:
            _require_text(self.reason, "deferral reason")


@dataclass(frozen=True, slots=True)
class CapabilityLimitation:
    """One sourced descriptive limitation without operational authority."""

    limitation_id: str
    capability_identifier: CapabilityIdentifier
    provider: str
    category: LimitationCategory
    description: str
    source_evidence_id: str
    provider_api_basis: str
    currentness: EvidenceCurrentness
    determination_time: datetime

    def __post_init__(self) -> None:
        _require_text(self.limitation_id, "limitation id")
        _require_text(self.provider, "provider")
        _require_text(self.description, "limitation description")
        _require_text(self.source_evidence_id, "source evidence id")
        _require_text(self.provider_api_basis, "provider API basis")
        _require_aware_time(self.determination_time, "determination time")


@dataclass(frozen=True, slots=True)
class CapabilityAssessmentOutcome:
    """One provider-neutral outcome for one processed request."""

    kind: CapabilityAssessmentOutcomeKind
    assessment_id: str
    reason: CapabilityAssessmentReason | None = None

    def __post_init__(self) -> None:
        _require_text(self.assessment_id, "assessment id")


@dataclass(frozen=True, slots=True)
class CapabilityAssessmentProvenance:
    """Non-sensitive authority and evidence lineage for one record."""

    assessment_id: str
    record_id: str
    provider: str
    capability_identifier: CapabilityIdentifier
    assessment_authority_reference: str
    evidence_ids: tuple[str, ...]
    evidence_references: tuple[str, ...]
    evidence_classes: tuple[EvidenceClass, ...]
    provider_api_basis: str
    sdk_version_basis: tuple[str, ...]
    adapter_revision_basis: tuple[str, ...]
    assessment_time: datetime
    provider_support: ProviderSupport
    implementation_disposition: ImplementationDisposition
    implementation_authority_reference: str
    implementation_reason: str | None
    evidence_currentness: tuple[EvidenceCurrentness, ...]
    repository_revision: str | None
    supersedes_record_id: str | None
    supersession_reason: str | None
    failure_reason: CapabilityAssessmentReason | None


@dataclass(frozen=True, slots=True)
class CapabilityAssessmentRecord:
    """Immutable result of one Capability Assessment Activity that began."""

    record_id: str
    assessment_id: str
    provider: str
    capability_identifier: CapabilityIdentifier
    outcome: CapabilityAssessmentOutcomeKind
    provider_support: ProviderSupport
    implementation_disposition: ImplementationDisposition
    implementation_evidence: ImplementationDispositionEvidence
    evidence: tuple[CapabilityEvidence, ...]
    evidence_references: tuple[str, ...]
    evidence_classes: tuple[EvidenceClass, ...]
    provider_api_basis: str
    sdk_version_basis: tuple[str, ...]
    adapter_revision_basis: tuple[str, ...]
    limitations: tuple[CapabilityLimitation, ...]
    assessment_time: datetime
    prior_record_id: str | None
    supersedes_record_id: str | None
    supersession_reason: str | None
    reason: CapabilityAssessmentReason | None
    provenance: CapabilityAssessmentProvenance
    audit_reference: str

    def __post_init__(self) -> None:
        if self.outcome is CapabilityAssessmentOutcomeKind.NOT_PERFORMED:
            raise ValueError("ASSESSMENT_NOT_PERFORMED cannot create a record")
        _require_text(self.record_id, "record id")
        _require_text(self.audit_reference, "audit reference")
        _require_aware_time(self.assessment_time, "assessment time")


@dataclass(frozen=True, slots=True)
class CapabilityAssessmentResult:
    """Return container preserving pre-boundary and in-boundary cardinality."""

    outcome: CapabilityAssessmentOutcome
    record: CapabilityAssessmentRecord | None

    def __post_init__(self) -> None:
        not_performed = (
            self.outcome.kind is CapabilityAssessmentOutcomeKind.NOT_PERFORMED
        )
        if not_performed and self.record is not None:
            raise ValueError("ASSESSMENT_NOT_PERFORMED must not contain a record")
        if not not_performed and self.record is None:
            raise ValueError("a begun Capability Assessment requires one record")
        if self.record is not None and self.record.outcome is not self.outcome.kind:
            raise ValueError("outcome and record must describe the same activity")


@dataclass(frozen=True, slots=True)
class CapabilityAuditEvidence:
    """Non-sensitive evidence that request processing or assessment occurred."""

    audit_reference: str
    assessment_id: str
    provider: str
    capability_identifier: CapabilityIdentifier | None
    outcome: CapabilityAssessmentOutcomeKind
    record_id: str | None
    reason: CapabilityAssessmentReason | None
    determination_rules_applied: bool
    sensitive_data_check_passed: bool
    supersession_established: bool


@dataclass(frozen=True, slots=True)
class CapabilityGuiProjection:
    """Read-only, non-authoritative GUI readiness projection."""

    provider: str
    capability_identifier: CapabilityIdentifier
    display_name: str
    provider_support: ProviderSupport
    implementation_disposition: ImplementationDisposition
    evidence_classes: tuple[EvidenceClass, ...]
    determination_time: datetime
    evidence_currentness: tuple[EvidenceCurrentness, ...]
    superseded: bool
    limitations: tuple[CapabilityLimitation, ...]
    provenance_reference: str


def _require_text(value: str | None, name: str) -> None:
    if value is None or not value.strip():
        raise ValueError(f"{name} is required")


def _require_aware_time(value: datetime | None, name: str) -> None:
    if value is not None and value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
