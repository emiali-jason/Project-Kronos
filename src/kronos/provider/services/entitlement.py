"""Provider-owned orchestration for canonical EDD-003."""

from dataclasses import replace
from datetime import datetime

from kronos.provider.models.context import ContextReuseEligibility, ContextValidity
from kronos.provider.models.entitlement import (
    AccountContinuity,
    EntitlementAssessmentOutcome,
    EntitlementAssessmentOutcomeKind,
    EntitlementAssessmentProvenance,
    EntitlementAssessmentReason,
    EntitlementAssessmentRequest,
    EntitlementAssessmentResult,
    EntitlementAuditEvidence,
    EntitlementCurrentness,
    EntitlementEvidenceIssue,
    EntitlementGuiProjection,
    EntitlementIndeterminate,
    ProviderEntitlementAssessmentRecord,
    ProviderEntitlementEvidence,
    ProviderEntitlementEvidenceItem,
    ProviderEntitlementIdentifier,
    ProviderReportedEntitlement,
)


_IDENTIFIER_FAMILY = tuple(ProviderEntitlementIdentifier)
_SENSITIVE_MARKERS = (
    "api_secret",
    "request_token",
    "access_token",
    "refresh_token",
    "public_token",
    "authorization_header",
    "authorization:",
    "bearer ",
    "checksum",
    "credential",
)
_ACTIVITY_FAILURES = frozenset(
    {
        EntitlementAssessmentReason.PROFILE_UNAVAILABLE,
        EntitlementAssessmentReason.PROVIDER_OPERATIONAL_FAILURE,
        EntitlementAssessmentReason.MALFORMED_PROFILE,
        EntitlementAssessmentReason.INSUFFICIENT_EVIDENCE,
        EntitlementAssessmentReason.ACCOUNT_CONTINUITY_MISMATCH,
        EntitlementAssessmentReason.ACCOUNT_CONTINUITY_UNDETERMINED,
        EntitlementAssessmentReason.SECURITY_BOUNDARY_VIOLATION,
        EntitlementAssessmentReason.EVIDENCE_UNSAFE_TO_PUBLISH,
        EntitlementAssessmentReason.EXCLUDED_FIELD_DISPOSAL_FAILURE,
        EntitlementAssessmentReason.EVIDENCE_MISMATCH,
        EntitlementAssessmentReason.PRIOR_RECORD_MISMATCH,
        EntitlementAssessmentReason.EVIDENCE_PROCESSING_FAILURE,
    }
)


class _ActivityFailure(RuntimeError):
    def __init__(self, reason: EntitlementAssessmentReason) -> None:
        self.reason = reason
        super().__init__(reason.value)


class ProviderEntitlementAssessmentService:
    """Assess minimized account evidence without creating operational authority."""

    __slots__ = (
        "__approved_assessment_authorities",
        "__approved_configuration_contexts",
        "__approved_evidence_sources",
        "__audit",
        "__latest_completed_record_id",
        "__provider",
        "__records",
        "__seen_assessment_ids",
        "__stale_context_references",
        "__superseded_record_ids",
        "__unidentified_request_count",
    )

    def __init__(
        self,
        provider: str,
        approved_assessment_authorities: frozenset[str],
        approved_evidence_sources: frozenset[str],
        approved_configuration_contexts: frozenset[str],
    ) -> None:
        if not provider.strip():
            raise ValueError("provider is required")
        for values, name in (
            (approved_assessment_authorities, "assessment authority"),
            (approved_evidence_sources, "evidence source"),
            (approved_configuration_contexts, "configuration context"),
        ):
            if not values or any(not value.strip() for value in values):
                raise ValueError(f"approved {name} is required")
            if any(_contains_sensitive_material(value) for value in values):
                raise ValueError(f"approved {name} must remain non-sensitive")

        self.__provider = provider
        self.__approved_assessment_authorities = (
            approved_assessment_authorities
        )
        self.__approved_evidence_sources = approved_evidence_sources
        self.__approved_configuration_contexts = (
            approved_configuration_contexts
        )
        self.__records: list[ProviderEntitlementAssessmentRecord] = []
        self.__audit: list[EntitlementAuditEvidence] = []
        self.__seen_assessment_ids: set[str] = set()
        self.__superseded_record_ids: set[str] = set()
        self.__stale_context_references: set[str] = set()
        self.__latest_completed_record_id: str | None = None
        self.__unidentified_request_count = 0

    def assess(
        self,
        request: EntitlementAssessmentRequest,
        evidence: ProviderEntitlementEvidence | None,
    ) -> EntitlementAssessmentResult:
        """Process one request and perform one activity only when eligible."""

        assessment_id = self.__outcome_assessment_id(request.assessment_id)
        try:
            ineligibility = self.__request_ineligibility(request)
        except Exception:
            ineligibility = EntitlementAssessmentReason.INVALID_REQUEST
        if ineligibility is not None:
            return self.__not_performed(
                assessment_id,
                self.__safe_provider(request.provider),
                ineligibility,
            )

        assessment_id = request.assessment_id.strip()
        self.__seen_assessment_ids.add(assessment_id)
        entitlements: tuple[ProviderReportedEntitlement, ...] = ()
        indeterminate: tuple[EntitlementIndeterminate, ...] = ()
        evidence_time = None
        account_continuity = AccountContinuity.UNDETERMINED
        provider_api_basis = "NOT_ESTABLISHED"
        sdk_version_basis = "NOT_ESTABLISHED"
        adapter_revision_basis = "NOT_ESTABLISHED"
        supersedes_record_id = None

        try:
            validated = self.__accept_evidence(request, evidence)
            evidence_time = validated.evidence_time
            account_continuity = validated.account_continuity
            provider_api_basis = validated.provider_api_basis
            sdk_version_basis = validated.sdk_version_basis
            adapter_revision_basis = validated.adapter_revision_basis
            self.__validate_accepted_evidence(validated)
            supersedes_record_id = self.__supersession_target(request)
            record_id = f"{assessment_id}:record"
            provenance_reference = f"{assessment_id}:provenance"
            entitlements = self.__positive_entitlements(
                request,
                validated.items,
                record_id,
                provenance_reference,
                evidence_time,
            )
            indeterminate = self.__indeterminate_entries(
                validated.issues,
                record_id,
                provenance_reference,
            )
            outcome_kind = EntitlementAssessmentOutcomeKind.COMPLETED
            reason = None
            currentness = EntitlementCurrentness.CURRENT
        except _ActivityFailure as failure:
            outcome_kind = EntitlementAssessmentOutcomeKind.FAILED
            reason = failure.reason
            currentness = EntitlementCurrentness.UNDETERMINED
            record_id = f"{assessment_id}:record"
            provenance_reference = f"{assessment_id}:provenance"
            indeterminate = (
                EntitlementIndeterminate(
                    identifier=None,
                    cause=reason,
                    evidence_source_reference=request.evidence_source_reference,
                    evidence_time=evidence_time or request.assessment_time,
                    record_reference=record_id,
                    currentness=currentness,
                    provenance_reference=provenance_reference,
                ),
            )
        except Exception:
            outcome_kind = EntitlementAssessmentOutcomeKind.FAILED
            reason = EntitlementAssessmentReason.EVIDENCE_PROCESSING_FAILURE
            currentness = EntitlementCurrentness.UNDETERMINED
            record_id = f"{assessment_id}:record"
            provenance_reference = f"{assessment_id}:provenance"
            indeterminate = (
                EntitlementIndeterminate(
                    identifier=None,
                    cause=reason,
                    evidence_source_reference=request.evidence_source_reference,
                    evidence_time=evidence_time or request.assessment_time,
                    record_reference=record_id,
                    currentness=currentness,
                    provenance_reference=provenance_reference,
                ),
            )

        outcome = EntitlementAssessmentOutcome(
            kind=outcome_kind,
            assessment_id=assessment_id,
            reason=reason,
        )
        record = self.__record(
            request=request,
            outcome=outcome,
            entitlements=entitlements,
            indeterminate=indeterminate,
            account_continuity=account_continuity,
            currentness=currentness,
            evidence_time=evidence_time,
            provider_api_basis=provider_api_basis,
            sdk_version_basis=sdk_version_basis,
            adapter_revision_basis=adapter_revision_basis,
            supersedes_record_id=supersedes_record_id,
        )
        self.__records.append(record)

        if outcome.kind is EntitlementAssessmentOutcomeKind.COMPLETED:
            if supersedes_record_id is not None:
                self.__superseded_record_ids.add(supersedes_record_id)
            self.__latest_completed_record_id = record.record_id

        self.__audit.append(
            EntitlementAuditEvidence(
                audit_reference=record.audit_reference,
                assessment_id=assessment_id,
                provider=self.__provider,
                outcome=outcome.kind,
                record_id=record.record_id,
                reason=outcome.reason,
                account_continuity=record.account_continuity,
                positive_entitlement_count=len(record.entitlements),
                indeterminate_count=len(record.indeterminate),
                sensitive_data_check_passed=(
                    outcome.reason
                    not in {
                        EntitlementAssessmentReason.SECURITY_BOUNDARY_VIOLATION,
                        EntitlementAssessmentReason.EVIDENCE_UNSAFE_TO_PUBLISH,
                        EntitlementAssessmentReason.EXCLUDED_FIELD_DISPOSAL_FAILURE,
                    }
                ),
                supersession_established=(
                    record.supersedes_record_id is not None
                ),
            )
        )
        return EntitlementAssessmentResult(outcome=outcome, record=record)

    def current_record(self) -> ProviderEntitlementAssessmentRecord | None:
        """Return the current completed record, when operationally applicable."""

        record_id = self.__latest_completed_record_id
        if record_id is None:
            return None
        record = self.__find_record(record_id)
        if (
            record is None
            or self.record_currentness(record_id)
            is not EntitlementCurrentness.CURRENT
        ):
            return None
        return record

    def record_currentness(self, record_id: str) -> EntitlementCurrentness:
        """Derive lifecycle currentness without mutating the immutable record."""

        record = self.__find_record(record_id)
        if record is None:
            raise LookupError("unknown entitlement assessment record")
        if record_id in self.__superseded_record_ids:
            return EntitlementCurrentness.SUPERSEDED
        if (
            record.provider_context_reference
            in self.__stale_context_references
        ):
            return EntitlementCurrentness.STALE
        return record.currentness

    def context_became_ineligible(self, provider_context_reference: str) -> None:
        """Consume EDD-001 invalidation or termination without mutating history."""

        if not provider_context_reference.strip():
            raise ValueError("provider context reference is required")
        self.__stale_context_references.add(provider_context_reference)

    def records(self) -> tuple[ProviderEntitlementAssessmentRecord, ...]:
        """Return immutable completed and failed assessment history."""

        return tuple(self.__records)

    def audit_evidence(self) -> tuple[EntitlementAuditEvidence, ...]:
        """Return immutable non-sensitive audit evidence."""

        return tuple(self.__audit)

    def gui_projection(
        self,
        record: ProviderEntitlementAssessmentRecord,
    ) -> EntitlementGuiProjection:
        """Project one record without creating entitlement or authority."""

        known = self.__find_record(record.record_id)
        if known is not record:
            raise ValueError("record is not owned by this assessment service")
        currentness = self.record_currentness(record.record_id)
        entitlements = tuple(
            replace(item, currentness=currentness)
            for item in record.entitlements
        )
        indeterminate = tuple(
            replace(item, currentness=currentness)
            for item in record.indeterminate
        )
        return EntitlementGuiProjection(
            provider=record.provider,
            protected_account_context_reference=(
                record.protected_account_context_reference
            ),
            entitlements=entitlements,
            indeterminate=indeterminate,
            outcome=record.outcome,
            assessment_time=record.assessment_time,
            currentness=currentness,
            superseded=currentness is EntitlementCurrentness.SUPERSEDED,
            failure_reason=record.reason,
            provenance_reference=record.provenance.provenance_reference,
        )

    def __request_ineligibility(
        self,
        request: EntitlementAssessmentRequest,
    ) -> EntitlementAssessmentReason | None:
        text_values = (
            request.assessment_id,
            request.provider,
            request.provider_context_reference,
            request.expected_account_context_reference,
            request.evidence_source_reference,
            request.assessment_authority_reference,
            request.configuration_approval_context_reference,
            request.authorization_context_reference,
            request.operating_environment_reference,
            request.lifecycle_boundary_reference,
            request.sensitive_classification_reference,
            request.prior_record_id or "",
            request.supersession_reason or "",
        )
        if any(_contains_sensitive_material(value) for value in text_values):
            return EntitlementAssessmentReason.SECURITY_BOUNDARY_VIOLATION
        if not request.assessment_id.strip():
            return EntitlementAssessmentReason.INVALID_REQUEST
        if request.assessment_id in self.__seen_assessment_ids:
            return EntitlementAssessmentReason.DUPLICATE_ASSESSMENT_ID
        if request.provider != self.__provider:
            return EntitlementAssessmentReason.PROVIDER_MISMATCH
        if (
            not isinstance(request.entitlement_identifiers, tuple)
            or tuple(request.entitlement_identifiers) != _IDENTIFIER_FAMILY
        ):
            return EntitlementAssessmentReason.IDENTIFIER_FAMILY_MISMATCH
        if not request.provider_context_reference.strip():
            return EntitlementAssessmentReason.CONTEXT_MISSING
        if request.context_validity is not ContextValidity.VALID:
            return EntitlementAssessmentReason.CONTEXT_INVALID
        if (
            request.context_reuse_eligibility
            is not ContextReuseEligibility.ELIGIBLE
        ):
            return EntitlementAssessmentReason.CONTEXT_REUSE_INELIGIBLE
        if not request.expected_account_context_reference.strip():
            return EntitlementAssessmentReason.EXPECTED_ACCOUNT_CONTEXT_MISSING
        if (
            request.configuration_approval_context_reference
            not in self.__approved_configuration_contexts
        ):
            return EntitlementAssessmentReason.CONFIGURATION_CONTEXT_MISMATCH
        if (
            request.evidence_source_reference
            not in self.__approved_evidence_sources
        ):
            return EntitlementAssessmentReason.UNAPPROVED_EVIDENCE_SOURCE
        if (
            request.assessment_authority_reference
            not in self.__approved_assessment_authorities
        ):
            return EntitlementAssessmentReason.MISSING_ASSESSMENT_AUTHORITY
        if (
            not isinstance(request.assessment_time, datetime)
            or request.assessment_time.utcoffset() is None
        ):
            return EntitlementAssessmentReason.INVALID_REQUEST
        required_context = (
            request.authorization_context_reference,
            request.operating_environment_reference,
            request.lifecycle_boundary_reference,
            request.sensitive_classification_reference,
        )
        if any(not value.strip() for value in required_context):
            return EntitlementAssessmentReason.INVALID_REQUEST
        if not request.security_containment_available:
            return EntitlementAssessmentReason.SECURITY_CONTAINMENT_UNAVAILABLE
        return None

    def __accept_evidence(
        self,
        request: EntitlementAssessmentRequest,
        evidence: ProviderEntitlementEvidence | None,
    ) -> ProviderEntitlementEvidence:
        """Accept only evidence whose provenance is safe to preserve."""

        if evidence is None:
            raise _ActivityFailure(
                EntitlementAssessmentReason.PROFILE_UNAVAILABLE
            )
        if (
            evidence.provider != self.__provider
            or evidence.evidence_source_reference
            != request.evidence_source_reference
            or evidence.evidence_time > request.assessment_time
        ):
            raise _ActivityFailure(
                EntitlementAssessmentReason.EVIDENCE_MISMATCH
            )
        return evidence

    def __validate_accepted_evidence(
        self,
        evidence: ProviderEntitlementEvidence,
    ) -> None:
        """Validate accepted evidence after capturing its safe provenance."""

        if evidence.fatal_reason is not None:
            if evidence.fatal_reason not in _ACTIVITY_FAILURES:
                raise _ActivityFailure(
                    EntitlementAssessmentReason.EVIDENCE_PROCESSING_FAILURE
                )
            raise _ActivityFailure(evidence.fatal_reason)
        if not evidence.excluded_fields_disposed:
            raise _ActivityFailure(
                EntitlementAssessmentReason.EXCLUDED_FIELD_DISPOSAL_FAILURE
            )
        if not evidence.security_check_passed:
            raise _ActivityFailure(
                EntitlementAssessmentReason.SECURITY_BOUNDARY_VIOLATION
            )
        if evidence.account_continuity is AccountContinuity.MISMATCHED:
            raise _ActivityFailure(
                EntitlementAssessmentReason.ACCOUNT_CONTINUITY_MISMATCH
            )
        if evidence.account_continuity is AccountContinuity.UNDETERMINED:
            raise _ActivityFailure(
                EntitlementAssessmentReason.ACCOUNT_CONTINUITY_UNDETERMINED
            )
        for item in evidence.items:
            if (
                item.identifier not in _IDENTIFIER_FAMILY
                or _contains_sensitive_material(item.reported_value)
            ):
                raise _ActivityFailure(
                    EntitlementAssessmentReason.EVIDENCE_UNSAFE_TO_PUBLISH
                )
        for issue in evidence.issues:
            if (
                issue.identifier is not None
                and issue.identifier not in _IDENTIFIER_FAMILY
            ):
                raise _ActivityFailure(
                    EntitlementAssessmentReason.EVIDENCE_MISMATCH
                )
            if (
                issue.evidence_source_reference
                != evidence.evidence_source_reference
                or issue.evidence_time != evidence.evidence_time
            ):
                raise _ActivityFailure(
                    EntitlementAssessmentReason.EVIDENCE_MISMATCH
                )

    def __supersession_target(
        self,
        request: EntitlementAssessmentRequest,
    ) -> str | None:
        current_id = self.__latest_completed_record_id
        prior_id = request.prior_record_id
        if current_id is None:
            if prior_id is not None:
                raise _ActivityFailure(
                    EntitlementAssessmentReason.PRIOR_RECORD_MISMATCH
                )
            return None
        if (
            prior_id != current_id
            or request.supersession_reason is None
            or not request.supersession_reason.strip()
        ):
            raise _ActivityFailure(
                EntitlementAssessmentReason.PRIOR_RECORD_MISMATCH
            )
        prior = self.__find_record(prior_id)
        if (
            prior is None
            or prior.provider != self.__provider
            or prior.protected_account_context_reference
            != request.expected_account_context_reference
            or prior.outcome is not EntitlementAssessmentOutcomeKind.COMPLETED
            or self.record_currentness(prior.record_id)
            is EntitlementCurrentness.SUPERSEDED
        ):
            raise _ActivityFailure(
                EntitlementAssessmentReason.PRIOR_RECORD_MISMATCH
            )
        return prior.record_id

    def __positive_entitlements(
        self,
        request: EntitlementAssessmentRequest,
        items: tuple[ProviderEntitlementEvidenceItem, ...],
        record_id: str,
        provenance_reference: str,
        evidence_time: datetime,
    ) -> tuple[ProviderReportedEntitlement, ...]:
        distinct = tuple(
            dict.fromkeys((item.identifier, item.reported_value) for item in items)
        )
        return tuple(
            ProviderReportedEntitlement(
                identifier=identifier,
                reported_value=value,
                provider=self.__provider,
                protected_account_context_reference=(
                    request.expected_account_context_reference
                ),
                evidence_source_reference=request.evidence_source_reference,
                evidence_time=evidence_time,
                record_reference=record_id,
                currentness=EntitlementCurrentness.CURRENT,
                provenance_reference=provenance_reference,
            )
            for identifier, value in distinct
        )

    @staticmethod
    def __indeterminate_entries(
        issues: tuple[EntitlementEvidenceIssue, ...],
        record_id: str,
        provenance_reference: str,
    ) -> tuple[EntitlementIndeterminate, ...]:
        return tuple(
            EntitlementIndeterminate(
                identifier=issue.identifier,
                cause=issue.cause,
                evidence_source_reference=issue.evidence_source_reference,
                evidence_time=issue.evidence_time,
                record_reference=record_id,
                currentness=EntitlementCurrentness.CURRENT,
                provenance_reference=provenance_reference,
            )
            for issue in issues
        )

    def __record(
        self,
        *,
        request: EntitlementAssessmentRequest,
        outcome: EntitlementAssessmentOutcome,
        entitlements: tuple[ProviderReportedEntitlement, ...],
        indeterminate: tuple[EntitlementIndeterminate, ...],
        account_continuity: AccountContinuity,
        currentness: EntitlementCurrentness,
        evidence_time: datetime | None,
        provider_api_basis: str,
        sdk_version_basis: str,
        adapter_revision_basis: str,
        supersedes_record_id: str | None,
    ) -> ProviderEntitlementAssessmentRecord:
        record_id = f"{outcome.assessment_id}:record"
        audit_reference = f"{outcome.assessment_id}:audit"
        provenance = EntitlementAssessmentProvenance(
            assessment_id=outcome.assessment_id,
            record_id=record_id,
            provenance_reference=f"{outcome.assessment_id}:provenance",
            provider=self.__provider,
            provider_context_reference=request.provider_context_reference,
            protected_account_context_reference=(
                request.expected_account_context_reference
            ),
            entitlement_identifiers=_IDENTIFIER_FAMILY,
            evidence_source_reference=request.evidence_source_reference,
            provider_api_basis=provider_api_basis,
            sdk_version_basis=sdk_version_basis,
            adapter_revision_basis=adapter_revision_basis,
            assessment_authority_reference=(
                request.assessment_authority_reference
            ),
            configuration_approval_context_reference=(
                request.configuration_approval_context_reference
            ),
            evidence_time=evidence_time,
            assessment_time=request.assessment_time,
            outcome=outcome.kind,
            account_continuity=account_continuity,
            currentness=currentness,
            prior_record_id=request.prior_record_id,
            supersedes_record_id=supersedes_record_id,
            supersession_reason=(
                request.supersession_reason
                if supersedes_record_id is not None
                else None
            ),
            failure_reason=outcome.reason,
        )
        return ProviderEntitlementAssessmentRecord(
            record_id=record_id,
            assessment_id=outcome.assessment_id,
            provider=self.__provider,
            provider_context_reference=request.provider_context_reference,
            protected_account_context_reference=(
                request.expected_account_context_reference
            ),
            entitlement_identifiers=_IDENTIFIER_FAMILY,
            entitlements=entitlements,
            indeterminate=indeterminate,
            account_continuity=account_continuity,
            outcome=outcome.kind,
            evidence_source_reference=request.evidence_source_reference,
            evidence_time=evidence_time,
            assessment_time=request.assessment_time,
            currentness=currentness,
            assessment_authority_reference=(
                request.assessment_authority_reference
            ),
            configuration_approval_context_reference=(
                request.configuration_approval_context_reference
            ),
            prior_record_id=request.prior_record_id,
            supersedes_record_id=supersedes_record_id,
            supersession_reason=provenance.supersession_reason,
            reason=outcome.reason,
            provenance=provenance,
            audit_reference=audit_reference,
        )

    def __not_performed(
        self,
        assessment_id: str,
        provider: str,
        reason: EntitlementAssessmentReason,
    ) -> EntitlementAssessmentResult:
        outcome = EntitlementAssessmentOutcome(
            kind=EntitlementAssessmentOutcomeKind.NOT_PERFORMED,
            assessment_id=assessment_id,
            reason=reason,
        )
        self.__audit.append(
            EntitlementAuditEvidence(
                audit_reference=f"{assessment_id}:request-audit",
                assessment_id=assessment_id,
                provider=provider,
                outcome=outcome.kind,
                record_id=None,
                reason=reason,
                account_continuity=None,
                positive_entitlement_count=0,
                indeterminate_count=0,
                sensitive_data_check_passed=(
                    reason
                    is not EntitlementAssessmentReason.SECURITY_BOUNDARY_VIOLATION
                ),
                supersession_established=False,
            )
        )
        return EntitlementAssessmentResult(outcome=outcome, record=None)

    def __outcome_assessment_id(self, submitted: object) -> str:
        if (
            isinstance(submitted, str)
            and submitted.strip()
            and not _contains_sensitive_material(submitted)
        ):
            return submitted.strip()
        self.__unidentified_request_count += 1
        return f"unidentified-entitlement-request-{self.__unidentified_request_count}"

    def __safe_provider(self, submitted: object) -> str:
        if (
            isinstance(submitted, str)
            and submitted.strip()
            and not _contains_sensitive_material(submitted)
        ):
            return submitted
        return self.__provider

    def __find_record(
        self,
        record_id: str,
    ) -> ProviderEntitlementAssessmentRecord | None:
        return next(
            (record for record in self.__records if record.record_id == record_id),
            None,
        )


def _contains_sensitive_material(value: object) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.casefold().replace("-", "_")
    return any(marker in normalized for marker in _SENSITIVE_MARKERS)
