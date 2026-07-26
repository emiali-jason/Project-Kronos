"""Provider-neutral meanings for canonical EDD-003 entitlement assessment."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from kronos.provider.models.context import ContextReuseEligibility, ContextValidity


class ProviderEntitlementIdentifier(StrEnum):
    """The closed ADR-008 Provider Entitlement identifier family."""

    EXCHANGE = "EXCHANGE_ENTITLEMENT"
    PRODUCT = "PRODUCT_ENTITLEMENT"
    ORDER_TYPE = "ORDER_TYPE_ENTITLEMENT"


class EntitlementAssessmentOutcomeKind(StrEnum):
    """The only outcomes of request processing or assessment activity."""

    COMPLETED = "ASSESSMENT_COMPLETED"
    NOT_PERFORMED = "ASSESSMENT_NOT_PERFORMED"
    FAILED = "ASSESSMENT_FAILED"


class EntitlementAssessmentReason(StrEnum):
    """Stable non-sensitive request, failure and indeterminacy causes."""

    INVALID_REQUEST = "INVALID_REQUEST"
    PROVIDER_MISMATCH = "PROVIDER_MISMATCH"
    IDENTIFIER_FAMILY_MISMATCH = "IDENTIFIER_FAMILY_MISMATCH"
    CONTEXT_MISSING = "CONTEXT_MISSING"
    CONTEXT_INVALID = "CONTEXT_INVALID"
    CONTEXT_REUSE_INELIGIBLE = "CONTEXT_REUSE_INELIGIBLE"
    EXPECTED_ACCOUNT_CONTEXT_MISSING = "EXPECTED_ACCOUNT_CONTEXT_MISSING"
    CONFIGURATION_CONTEXT_MISMATCH = "CONFIGURATION_CONTEXT_MISMATCH"
    UNAPPROVED_EVIDENCE_SOURCE = "UNAPPROVED_EVIDENCE_SOURCE"
    MISSING_ASSESSMENT_AUTHORITY = "MISSING_ASSESSMENT_AUTHORITY"
    SECURITY_CONTAINMENT_UNAVAILABLE = "SECURITY_CONTAINMENT_UNAVAILABLE"
    DUPLICATE_ASSESSMENT_ID = "DUPLICATE_ASSESSMENT_ID"
    PROFILE_UNAVAILABLE = "PROFILE_UNAVAILABLE"
    PROVIDER_OPERATIONAL_FAILURE = "PROVIDER_OPERATIONAL_FAILURE"
    MALFORMED_PROFILE = "MALFORMED_PROFILE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    ACCOUNT_CONTINUITY_MISMATCH = "ACCOUNT_CONTINUITY_MISMATCH"
    ACCOUNT_CONTINUITY_UNDETERMINED = "ACCOUNT_CONTINUITY_UNDETERMINED"
    UNRECOGNIZED_PROVIDER_VOCABULARY = "UNRECOGNIZED_PROVIDER_VOCABULARY"
    SECURITY_BOUNDARY_VIOLATION = "SECURITY_BOUNDARY_VIOLATION"
    EVIDENCE_UNSAFE_TO_PUBLISH = "EVIDENCE_UNSAFE_TO_PUBLISH"
    EXCLUDED_FIELD_DISPOSAL_FAILURE = "EXCLUDED_FIELD_DISPOSAL_FAILURE"
    EVIDENCE_MISMATCH = "EVIDENCE_MISMATCH"
    PRIOR_RECORD_MISMATCH = "PRIOR_RECORD_MISMATCH"
    EVIDENCE_PROCESSING_FAILURE = "EVIDENCE_PROCESSING_FAILURE"


class AccountContinuity(StrEnum):
    """Provider-owned continuity of one protected account context."""

    MATCHED = "MATCHED"
    MISMATCHED = "MISMATCHED"
    UNDETERMINED = "UNDETERMINED"


class EntitlementCurrentness(StrEnum):
    """Current applicability of one immutable assessment record."""

    CURRENT = "CURRENT"
    STALE = "STALE"
    SUPERSEDED = "SUPERSEDED"
    UNDETERMINED = "UNDETERMINED"


@dataclass(frozen=True, slots=True)
class EntitlementAssessmentRequest:
    """Immutable input submitted to pre-boundary request processing."""

    assessment_id: str
    provider: str
    provider_context_reference: str
    context_validity: ContextValidity
    context_reuse_eligibility: ContextReuseEligibility
    expected_account_context_reference: str
    entitlement_identifiers: tuple[ProviderEntitlementIdentifier | str, ...]
    evidence_source_reference: str
    assessment_authority_reference: str
    configuration_approval_context_reference: str
    assessment_time: datetime
    authorization_context_reference: str
    operating_environment_reference: str
    lifecycle_boundary_reference: str
    sensitive_classification_reference: str
    security_containment_available: bool
    prior_record_id: str | None = None
    supersession_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderEntitlementEvidenceItem:
    """One minimized provider-neutral positive evidence item."""

    identifier: ProviderEntitlementIdentifier
    reported_value: str

    def __post_init__(self) -> None:
        _require_text(self.reported_value, "reported value")


@dataclass(frozen=True, slots=True)
class EntitlementEvidenceIssue:
    """Minimized adapter evidence requiring bounded indeterminate treatment."""

    identifier: ProviderEntitlementIdentifier | None
    cause: EntitlementAssessmentReason
    evidence_source_reference: str
    evidence_time: datetime

    def __post_init__(self) -> None:
        _require_text(self.evidence_source_reference, "evidence source reference")
        _require_aware_time(self.evidence_time, "evidence time")


@dataclass(frozen=True, slots=True)
class EntitlementIndeterminate:
    """Published bounded indeterminacy from one assessment record."""

    identifier: ProviderEntitlementIdentifier | None
    cause: EntitlementAssessmentReason
    evidence_source_reference: str
    evidence_time: datetime
    record_reference: str
    currentness: EntitlementCurrentness
    provenance_reference: str

    def __post_init__(self) -> None:
        _require_text(self.evidence_source_reference, "evidence source reference")
        _require_text(self.record_reference, "record reference")
        _require_text(self.provenance_reference, "provenance reference")
        _require_aware_time(self.evidence_time, "evidence time")


@dataclass(frozen=True, slots=True)
class ProviderEntitlementEvidence:
    """Minimized output of adapter-private profile translation."""

    provider: str
    evidence_source_reference: str
    evidence_time: datetime
    account_continuity: AccountContinuity
    items: tuple[ProviderEntitlementEvidenceItem, ...]
    issues: tuple[EntitlementEvidenceIssue, ...]
    provider_api_basis: str
    sdk_version_basis: str
    adapter_revision_basis: str
    excluded_fields_disposed: bool
    security_check_passed: bool
    fatal_reason: EntitlementAssessmentReason | None = None

    def __post_init__(self) -> None:
        _require_text(self.provider, "provider")
        _require_text(self.evidence_source_reference, "evidence source reference")
        _require_text(self.provider_api_basis, "provider API basis")
        _require_text(self.sdk_version_basis, "SDK version basis")
        _require_text(self.adapter_revision_basis, "adapter revision basis")
        _require_aware_time(self.evidence_time, "evidence time")


@dataclass(frozen=True, slots=True)
class ProviderReportedEntitlement:
    """Positive account-scoped entitlement explicitly reported by a Provider."""

    identifier: ProviderEntitlementIdentifier
    reported_value: str
    provider: str
    protected_account_context_reference: str
    evidence_source_reference: str
    evidence_time: datetime
    record_reference: str
    currentness: EntitlementCurrentness
    provenance_reference: str

    def __post_init__(self) -> None:
        _require_text(self.reported_value, "reported value")
        _require_text(self.provider, "provider")
        _require_text(
            self.protected_account_context_reference,
            "protected account context reference",
        )
        _require_text(self.evidence_source_reference, "evidence source reference")
        _require_text(self.record_reference, "record reference")
        _require_text(self.provenance_reference, "provenance reference")
        _require_aware_time(self.evidence_time, "evidence time")


@dataclass(frozen=True, slots=True)
class EntitlementAssessmentOutcome:
    """One provider-neutral outcome for one processed request."""

    kind: EntitlementAssessmentOutcomeKind
    assessment_id: str
    reason: EntitlementAssessmentReason | None = None

    def __post_init__(self) -> None:
        _require_text(self.assessment_id, "assessment id")


@dataclass(frozen=True, slots=True)
class EntitlementAssessmentProvenance:
    """Non-sensitive authority and evidence lineage for one assessment."""

    assessment_id: str
    record_id: str
    provenance_reference: str
    provider: str
    provider_context_reference: str
    protected_account_context_reference: str
    entitlement_identifiers: tuple[ProviderEntitlementIdentifier, ...]
    evidence_source_reference: str
    provider_api_basis: str
    sdk_version_basis: str
    adapter_revision_basis: str
    assessment_authority_reference: str
    configuration_approval_context_reference: str
    evidence_time: datetime | None
    assessment_time: datetime
    outcome: EntitlementAssessmentOutcomeKind
    account_continuity: AccountContinuity
    currentness: EntitlementCurrentness
    prior_record_id: str | None
    supersedes_record_id: str | None
    supersession_reason: str | None
    failure_reason: EntitlementAssessmentReason | None


@dataclass(frozen=True, slots=True)
class ProviderEntitlementAssessmentRecord:
    """Immutable result of one Entitlement Assessment Activity that began."""

    record_id: str
    assessment_id: str
    provider: str
    provider_context_reference: str
    protected_account_context_reference: str
    entitlement_identifiers: tuple[ProviderEntitlementIdentifier, ...]
    entitlements: tuple[ProviderReportedEntitlement, ...]
    indeterminate: tuple[EntitlementIndeterminate, ...]
    account_continuity: AccountContinuity
    outcome: EntitlementAssessmentOutcomeKind
    evidence_source_reference: str
    evidence_time: datetime | None
    assessment_time: datetime
    currentness: EntitlementCurrentness
    assessment_authority_reference: str
    configuration_approval_context_reference: str
    prior_record_id: str | None
    supersedes_record_id: str | None
    supersession_reason: str | None
    reason: EntitlementAssessmentReason | None
    provenance: EntitlementAssessmentProvenance
    audit_reference: str

    def __post_init__(self) -> None:
        if self.outcome is EntitlementAssessmentOutcomeKind.NOT_PERFORMED:
            raise ValueError("ASSESSMENT_NOT_PERFORMED cannot create a record")
        _require_text(self.record_id, "record id")
        _require_text(self.audit_reference, "audit reference")
        _require_aware_time(self.assessment_time, "assessment time")


@dataclass(frozen=True, slots=True)
class EntitlementAssessmentResult:
    """Return container preserving pre-boundary and activity cardinality."""

    outcome: EntitlementAssessmentOutcome
    record: ProviderEntitlementAssessmentRecord | None

    def __post_init__(self) -> None:
        not_performed = (
            self.outcome.kind is EntitlementAssessmentOutcomeKind.NOT_PERFORMED
        )
        if not_performed and self.record is not None:
            raise ValueError("ASSESSMENT_NOT_PERFORMED must not contain a record")
        if not not_performed and self.record is None:
            raise ValueError("a begun Entitlement Assessment requires one record")
        if self.record is not None and self.record.outcome is not self.outcome.kind:
            raise ValueError("outcome and record must describe the same activity")


@dataclass(frozen=True, slots=True)
class EntitlementAuditEvidence:
    """Non-sensitive evidence that request processing or assessment occurred."""

    audit_reference: str
    assessment_id: str
    provider: str
    outcome: EntitlementAssessmentOutcomeKind
    record_id: str | None
    reason: EntitlementAssessmentReason | None
    account_continuity: AccountContinuity | None
    positive_entitlement_count: int
    indeterminate_count: int
    sensitive_data_check_passed: bool
    supersession_established: bool


@dataclass(frozen=True, slots=True)
class EntitlementGuiProjection:
    """Read-only, non-authoritative GUI readiness projection."""

    provider: str
    protected_account_context_reference: str
    entitlements: tuple[ProviderReportedEntitlement, ...]
    indeterminate: tuple[EntitlementIndeterminate, ...]
    outcome: EntitlementAssessmentOutcomeKind
    assessment_time: datetime
    currentness: EntitlementCurrentness
    superseded: bool
    failure_reason: EntitlementAssessmentReason | None
    provenance_reference: str


def _require_text(value: str | None, name: str) -> None:
    if value is None or not value.strip():
        raise ValueError(f"{name} is required")


def _require_aware_time(value: datetime | None, name: str) -> None:
    if value is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
