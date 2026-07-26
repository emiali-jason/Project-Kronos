"""Provider-owned orchestration for canonical EDD-002."""

from collections.abc import Mapping, Sequence
from datetime import datetime

from kronos.provider.models.capability import (
    CapabilityAssessmentOutcome,
    CapabilityAssessmentOutcomeKind,
    CapabilityAssessmentProvenance,
    CapabilityAssessmentReason,
    CapabilityAssessmentRecord,
    CapabilityAssessmentRequest,
    CapabilityAssessmentResult,
    CapabilityAuditEvidence,
    CapabilityEvidence,
    CapabilityGuiProjection,
    CapabilityIdentifier,
    CapabilityLimitation,
    EvidenceAssertion,
    EvidenceClass,
    EvidenceCurrentness,
    ImplementationDisposition,
    ImplementationDispositionEvidence,
    ProviderSupport,
)


_INITIAL_EVIDENCE_CLASSES = frozenset(
    {
        EvidenceClass.OFFICIAL_PROVIDER_DOCUMENTATION,
        EvidenceClass.APPROVED_ADAPTER_LOCKED_SDK_COMPATIBILITY,
    }
)
_SENSITIVE_MARKERS = (
    "api_secret",
    "request_token",
    "access_token",
    "refresh_token",
    "authorization_header",
    "authorization:_bearer",
    "bearer_token",
    "checksum",
    "credential",
)
_DISPLAY_NAMES = {
    CapabilityIdentifier.INSTRUMENT_REFERENCE: "Instrument Reference Capability",
    CapabilityIdentifier.FULL_QUOTE_SNAPSHOT: "Full Quote Snapshot Capability",
    CapabilityIdentifier.OHLC_SNAPSHOT: "OHLC Snapshot Capability",
    CapabilityIdentifier.LTP_SNAPSHOT: "LTP Snapshot Capability",
    CapabilityIdentifier.HISTORICAL_OBSERVATION: (
        "Historical Observation Capability"
    ),
    CapabilityIdentifier.LIVE_OBSERVATION_STREAMING: (
        "Live Observation Streaming Capability"
    ),
}


class _ActivityFailure(RuntimeError):
    def __init__(self, reason: CapabilityAssessmentReason) -> None:
        self.reason = reason
        super().__init__(reason.value)


class ProviderCapabilityAssessmentService:
    """Assess governed evidence without executing a Provider capability."""

    __slots__ = (
        "__audit",
        "__approved_assessment_authorities",
        "__approved_evidence_references",
        "__current_records",
        "__implementation_evidence",
        "__provider",
        "__records",
        "__seen_assessment_ids",
        "__unidentified_request_count",
    )

    def __init__(
        self,
        provider: str,
        implementation_evidence: Mapping[
            CapabilityIdentifier,
            ImplementationDispositionEvidence,
        ],
        approved_assessment_authorities: frozenset[str],
        approved_evidence_references: Mapping[
            CapabilityIdentifier,
            frozenset[str],
        ],
    ) -> None:
        if not provider.strip():
            raise ValueError("provider is required")
        expected = set(CapabilityIdentifier)
        if set(implementation_evidence) != expected:
            raise ValueError(
                "implementation evidence is required for every Capability Identifier"
            )
        for identifier, item in implementation_evidence.items():
            if item.capability_identifier is not identifier:
                raise ValueError("implementation evidence identifier mismatch")
            if _implementation_evidence_contains_sensitive_material(item):
                raise ValueError(
                    "implementation evidence must remain non-sensitive"
                )
        if not approved_assessment_authorities or any(
            not authority.strip()
            for authority in approved_assessment_authorities
        ):
            raise ValueError("approved assessment authority is required")
        if set(approved_evidence_references) != expected or any(
            not references
            for references in approved_evidence_references.values()
        ):
            raise ValueError(
                "approved evidence references are required for every "
                "Capability Identifier"
            )

        self.__provider = provider
        self.__implementation_evidence = dict(implementation_evidence)
        self.__approved_assessment_authorities = (
            approved_assessment_authorities
        )
        self.__approved_evidence_references = {
            identifier: frozenset(references)
            for identifier, references in approved_evidence_references.items()
        }
        self.__records: list[CapabilityAssessmentRecord] = []
        self.__current_records: dict[
            CapabilityIdentifier,
            CapabilityAssessmentRecord,
        ] = {}
        self.__audit: list[CapabilityAuditEvidence] = []
        self.__seen_assessment_ids: set[str] = set()
        self.__unidentified_request_count = 0

    def assess(
        self,
        request: CapabilityAssessmentRequest,
        evidence: Sequence[CapabilityEvidence],
        limitations: Sequence[CapabilityLimitation] = (),
    ) -> CapabilityAssessmentResult:
        """Process one request and perform one assessment only if eligible."""

        outcome_id = self.__outcome_assessment_id(request.assessment_id)
        eligibility = self.__request_ineligibility(
            request,
            evidence,
            limitations,
        )
        if eligibility is not None:
            return self.__not_performed(
                outcome_id,
                request.provider,
                request.capability_identifier,
                eligibility,
            )

        identifier = CapabilityIdentifier(request.capability_identifier)
        assessment_id = request.assessment_id.strip()
        self.__seen_assessment_ids.add(assessment_id)
        implementation = self.__implementation_evidence[identifier]
        validated_evidence: tuple[CapabilityEvidence, ...] = ()

        try:
            validated_evidence = self.__validate_evidence(
                request,
                identifier,
                evidence,
            )
            validated_limitations = self.__validate_limitations(
                request,
                identifier,
                validated_evidence,
                limitations,
            )
            support, reason = self.__determine_support(validated_evidence)
            if (
                support is ProviderSupport.UNSUPPORTED
                and implementation.disposition
                is ImplementationDisposition.IMPLEMENTED
            ):
                reason = CapabilityAssessmentReason.GOVERNANCE_CONFLICT
            supersedes = self.__supersession_target(request, identifier)
            outcome_kind = CapabilityAssessmentOutcomeKind.COMPLETED
        except _ActivityFailure as failure:
            validated_limitations = ()
            support = ProviderSupport.UNDETERMINED
            reason = failure.reason
            supersedes = None
            outcome_kind = CapabilityAssessmentOutcomeKind.FAILED

        outcome = CapabilityAssessmentOutcome(
            kind=outcome_kind,
            assessment_id=assessment_id,
            reason=reason,
        )
        record = self.__record(
            request=request,
            identifier=identifier,
            outcome=outcome,
            support=support,
            implementation=implementation,
            evidence=validated_evidence,
            limitations=validated_limitations,
            supersedes_record_id=supersedes,
        )
        self.__records.append(record)
        if outcome.kind is CapabilityAssessmentOutcomeKind.COMPLETED:
            self.__current_records[identifier] = record
        self.__audit.append(
            CapabilityAuditEvidence(
                audit_reference=record.audit_reference,
                assessment_id=assessment_id,
                provider=self.__provider,
                capability_identifier=identifier,
                outcome=outcome.kind,
                record_id=record.record_id,
                reason=outcome.reason,
                determination_rules_applied=True,
                sensitive_data_check_passed=True,
                supersession_established=(
                    record.supersedes_record_id is not None
                ),
            )
        )
        return CapabilityAssessmentResult(outcome=outcome, record=record)

    def current_record(
        self,
        capability_identifier: CapabilityIdentifier,
    ) -> CapabilityAssessmentRecord | None:
        """Return the current completed record for one capability."""

        return self.__current_records.get(capability_identifier)

    def records(self) -> tuple[CapabilityAssessmentRecord, ...]:
        """Return immutable completed and failed assessment history."""

        return tuple(self.__records)

    def audit_evidence(self) -> tuple[CapabilityAuditEvidence, ...]:
        """Return immutable non-sensitive audit evidence."""

        return tuple(self.__audit)

    def gui_projection(
        self,
        record: CapabilityAssessmentRecord,
    ) -> CapabilityGuiProjection:
        """Create one informational, read-only projection."""

        if record.provider != self.__provider or record not in self.__records:
            raise ValueError("record does not belong to this Provider assessment")
        return CapabilityGuiProjection(
            provider=record.provider,
            capability_identifier=record.capability_identifier,
            display_name=_DISPLAY_NAMES[record.capability_identifier],
            provider_support=record.provider_support,
            implementation_disposition=record.implementation_disposition,
            evidence_classes=tuple(
                dict.fromkeys(item.evidence_class for item in record.evidence)
            ),
            determination_time=record.assessment_time,
            evidence_currentness=tuple(
                item.currentness for item in record.evidence
            ),
            superseded=any(
                item.supersedes_record_id == record.record_id
                for item in self.__records
            ),
            limitations=record.limitations,
            provenance_reference=record.record_id,
        )

    def __request_ineligibility(
        self,
        request: CapabilityAssessmentRequest,
        evidence: Sequence[CapabilityEvidence],
        limitations: Sequence[CapabilityLimitation],
    ) -> CapabilityAssessmentReason | None:
        if (
            not isinstance(request.assessment_id, str)
            or not request.assessment_id.strip()
        ):
            return CapabilityAssessmentReason.MISSING_PREREQUISITE
        if request.assessment_id in self.__seen_assessment_ids:
            return CapabilityAssessmentReason.DUPLICATE_ASSESSMENT_ID
        if not isinstance(request.provider, str) or request.provider != self.__provider:
            return CapabilityAssessmentReason.INVALID_REQUEST
        try:
            identifier = CapabilityIdentifier(request.capability_identifier)
        except (TypeError, ValueError):
            return CapabilityAssessmentReason.UNKNOWN_CAPABILITY_IDENTIFIER

        if not request.requested_evidence_classes:
            return CapabilityAssessmentReason.MISSING_PREREQUISITE
        try:
            requested_classes = tuple(
                EvidenceClass(item) for item in request.requested_evidence_classes
            )
        except (TypeError, ValueError):
            return CapabilityAssessmentReason.UNAUTHORIZED_EVIDENCE_CLASS
        if not set(requested_classes).issubset(_INITIAL_EVIDENCE_CLASSES):
            return CapabilityAssessmentReason.UNAUTHORIZED_EVIDENCE_CLASS
        if request.provider_context_reference is not None:
            return CapabilityAssessmentReason.UNAUTHORIZED_EVIDENCE_CLASS
        if request.prior_record_id is not None and (
            request.supersession_reason is None
            or not request.supersession_reason.strip()
        ):
            return CapabilityAssessmentReason.MISSING_PREREQUISITE
        if request.prior_record_id is None and request.supersession_reason is not None:
            return CapabilityAssessmentReason.INVALID_REQUEST
        if not request.evidence_references:
            return CapabilityAssessmentReason.MISSING_PREREQUISITE
        if (
            not isinstance(request.assessment_authority_reference, str)
            or not request.assessment_authority_reference.strip()
            or not isinstance(request.compatibility_basis, str)
            or not request.compatibility_basis.strip()
            or not isinstance(request.assessment_time, datetime)
            or request.assessment_time.utcoffset() is None
        ):
            return CapabilityAssessmentReason.MISSING_PREREQUISITE

        strings = (
            request.assessment_id,
            request.provider,
            request.assessment_authority_reference,
            request.compatibility_basis,
            *request.evidence_references,
        )
        if request.prior_record_id is not None:
            strings += (request.prior_record_id,)
        if request.supersession_reason is not None:
            strings += (request.supersession_reason,)
        if any(
            not isinstance(value, str)
            or not value.strip()
            or _contains_sensitive_marker(value)
            for value in strings
        ):
            return CapabilityAssessmentReason.SENSITIVE_INPUT
        if (
            request.assessment_authority_reference
            not in self.__approved_assessment_authorities
        ):
            return CapabilityAssessmentReason.MISSING_PREREQUISITE
        if not set(request.evidence_references).issubset(
            self.__approved_evidence_references[identifier]
        ):
            return CapabilityAssessmentReason.UNAPPROVED_EVIDENCE_SOURCE
        if any(_evidence_contains_sensitive_material(item) for item in evidence):
            return CapabilityAssessmentReason.SENSITIVE_INPUT
        if any(
            _limitation_contains_sensitive_material(item)
            for item in limitations
        ):
            return CapabilityAssessmentReason.SENSITIVE_INPUT
        return None

    def __validate_evidence(
        self,
        request: CapabilityAssessmentRequest,
        identifier: CapabilityIdentifier,
        evidence: Sequence[CapabilityEvidence],
    ) -> tuple[CapabilityEvidence, ...]:
        requested_classes = {
            EvidenceClass(item) for item in request.requested_evidence_classes
        }
        requested_references = set(request.evidence_references)
        validated: list[CapabilityEvidence] = []
        for item in evidence:
            if not isinstance(item, CapabilityEvidence):
                raise _ActivityFailure(
                    CapabilityAssessmentReason.EVIDENCE_PROCESSING_FAILURE
                )
            if (
                item.provider != self.__provider
                or item.capability_identifier is not identifier
                or item.evidence_class not in requested_classes
                or item.source_reference not in requested_references
                or item.provider_api_basis != request.compatibility_basis
            ):
                raise _ActivityFailure(
                    CapabilityAssessmentReason.EVIDENCE_MISMATCH
                )
            validated.append(item)
        return tuple(validated)

    def __validate_limitations(
        self,
        request: CapabilityAssessmentRequest,
        identifier: CapabilityIdentifier,
        evidence: Sequence[CapabilityEvidence],
        limitations: Sequence[CapabilityLimitation],
    ) -> tuple[CapabilityLimitation, ...]:
        evidence_ids = {item.evidence_id for item in evidence}
        validated: list[CapabilityLimitation] = []
        for limitation in limitations:
            if (
                not isinstance(limitation, CapabilityLimitation)
                or limitation.provider != self.__provider
                or limitation.capability_identifier is not identifier
                or limitation.source_evidence_id not in evidence_ids
                or limitation.provider_api_basis != request.compatibility_basis
            ):
                raise _ActivityFailure(
                    CapabilityAssessmentReason.LIMITATION_MISMATCH
                )
            validated.append(limitation)
        return tuple(validated)

    def __determine_support(
        self,
        evidence: Sequence[CapabilityEvidence],
    ) -> tuple[ProviderSupport, CapabilityAssessmentReason | None]:
        current_documentation = tuple(
            item
            for item in evidence
            if item.evidence_class
            is EvidenceClass.OFFICIAL_PROVIDER_DOCUMENTATION
            and item.currentness is EvidenceCurrentness.CURRENT
        )
        supports = any(
            item.assertion is EvidenceAssertion.SUPPORTS
            for item in current_documentation
        )
        does_not_support = any(
            item.assertion
            in {EvidenceAssertion.DOES_NOT_SUPPORT, EvidenceAssertion.WITHDRAWN}
            for item in current_documentation
        )
        conflicts = any(
            item.assertion is EvidenceAssertion.CONFLICT for item in evidence
        ) or (supports and does_not_support)

        if conflicts:
            return (
                ProviderSupport.UNDETERMINED,
                CapabilityAssessmentReason.EVIDENCE_CONFLICT,
            )
        if does_not_support:
            return ProviderSupport.UNSUPPORTED, None
        if supports:
            return ProviderSupport.SUPPORTED, None
        if any(
            item.currentness is EvidenceCurrentness.STALE for item in evidence
        ):
            return (
                ProviderSupport.UNDETERMINED,
                CapabilityAssessmentReason.EVIDENCE_STALE,
            )
        if any(
            item.currentness is EvidenceCurrentness.UNDETERMINED
            for item in evidence
        ):
            return (
                ProviderSupport.UNDETERMINED,
                CapabilityAssessmentReason.EVIDENCE_CURRENTNESS_UNDETERMINED,
            )
        return (
            ProviderSupport.UNDETERMINED,
            CapabilityAssessmentReason.EVIDENCE_ABSENT,
        )

    def __supersession_target(
        self,
        request: CapabilityAssessmentRequest,
        identifier: CapabilityIdentifier,
    ) -> str | None:
        prior_id = request.prior_record_id
        if prior_id is None:
            return None
        prior = next(
            (record for record in self.__records if record.record_id == prior_id),
            None,
        )
        if (
            prior is None
            or self.__current_records.get(identifier) is not prior
            or prior.provider != self.__provider
            or prior.capability_identifier is not identifier
            or prior.outcome is not CapabilityAssessmentOutcomeKind.COMPLETED
        ):
            raise _ActivityFailure(
                CapabilityAssessmentReason.PRIOR_RECORD_MISMATCH
            )
        return prior.record_id

    def __record(
        self,
        *,
        request: CapabilityAssessmentRequest,
        identifier: CapabilityIdentifier,
        outcome: CapabilityAssessmentOutcome,
        support: ProviderSupport,
        implementation: ImplementationDispositionEvidence,
        evidence: tuple[CapabilityEvidence, ...],
        limitations: tuple[CapabilityLimitation, ...],
        supersedes_record_id: str | None,
    ) -> CapabilityAssessmentRecord:
        record_id = f"{outcome.assessment_id}:record"
        audit_reference = f"{outcome.assessment_id}:audit"
        sdk_versions = tuple(
            dict.fromkeys(
                (
                    *(
                        item.sdk_version_basis
                        for item in evidence
                        if item.sdk_version_basis is not None
                    ),
                    *(
                        (implementation.dependency_basis,)
                        if implementation.dependency_basis is not None
                        else ()
                    ),
                )
            )
        )
        adapter_revisions = tuple(
            dict.fromkeys(
                item.adapter_revision_basis
                for item in evidence
                if item.adapter_revision_basis is not None
            )
        )
        provenance = CapabilityAssessmentProvenance(
            assessment_id=outcome.assessment_id,
            record_id=record_id,
            provider=self.__provider,
            capability_identifier=identifier,
            assessment_authority_reference=(
                request.assessment_authority_reference
            ),
            evidence_ids=tuple(item.evidence_id for item in evidence),
            evidence_references=request.evidence_references,
            evidence_classes=tuple(
                EvidenceClass(item)
                for item in request.requested_evidence_classes
            ),
            provider_api_basis=request.compatibility_basis,
            sdk_version_basis=sdk_versions,
            adapter_revision_basis=adapter_revisions,
            assessment_time=request.assessment_time,
            provider_support=support,
            implementation_disposition=implementation.disposition,
            implementation_authority_reference=(
                implementation.authority_reference
            ),
            implementation_reason=implementation.reason,
            evidence_currentness=tuple(
                item.currentness for item in evidence
            ),
            repository_revision=implementation.repository_revision,
            supersedes_record_id=supersedes_record_id,
            supersession_reason=request.supersession_reason,
            failure_reason=outcome.reason,
        )
        return CapabilityAssessmentRecord(
            record_id=record_id,
            assessment_id=outcome.assessment_id,
            provider=self.__provider,
            capability_identifier=identifier,
            outcome=outcome.kind,
            provider_support=support,
            implementation_disposition=implementation.disposition,
            implementation_evidence=implementation,
            evidence=evidence,
            evidence_references=request.evidence_references,
            evidence_classes=tuple(
                EvidenceClass(item)
                for item in request.requested_evidence_classes
            ),
            provider_api_basis=request.compatibility_basis,
            sdk_version_basis=sdk_versions,
            adapter_revision_basis=adapter_revisions,
            limitations=limitations,
            assessment_time=request.assessment_time,
            prior_record_id=request.prior_record_id,
            supersedes_record_id=supersedes_record_id,
            supersession_reason=request.supersession_reason,
            reason=outcome.reason,
            provenance=provenance,
            audit_reference=audit_reference,
        )

    def __not_performed(
        self,
        assessment_id: str,
        provider: object,
        capability: object,
        reason: CapabilityAssessmentReason,
    ) -> CapabilityAssessmentResult:
        outcome = CapabilityAssessmentOutcome(
            kind=CapabilityAssessmentOutcomeKind.NOT_PERFORMED,
            assessment_id=assessment_id,
            reason=reason,
        )
        try:
            identifier = CapabilityIdentifier(capability)
        except (TypeError, ValueError):
            identifier = None
        safe_provider = (
            provider
            if isinstance(provider, str)
            and provider.strip()
            and not _contains_sensitive_marker(provider)
            else self.__provider
        )
        self.__audit.append(
            CapabilityAuditEvidence(
                audit_reference=f"{assessment_id}:audit",
                assessment_id=assessment_id,
                provider=safe_provider,
                capability_identifier=identifier,
                outcome=outcome.kind,
                record_id=None,
                reason=reason,
                determination_rules_applied=False,
                sensitive_data_check_passed=(
                    reason is not CapabilityAssessmentReason.SENSITIVE_INPUT
                ),
                supersession_established=False,
            )
        )
        return CapabilityAssessmentResult(outcome=outcome, record=None)

    def __outcome_assessment_id(self, submitted: object) -> str:
        if (
            isinstance(submitted, str)
            and submitted.strip()
            and not _contains_sensitive_marker(submitted)
        ):
            return submitted.strip()
        self.__unidentified_request_count += 1
        return f"UNIDENTIFIED_REQUEST_{self.__unidentified_request_count}"


def _contains_sensitive_marker(value: str) -> bool:
    normalized = value.casefold().replace("-", "_").replace(" ", "_")
    return any(marker in normalized for marker in _SENSITIVE_MARKERS)


def _evidence_contains_sensitive_material(item: object) -> bool:
    if not isinstance(item, CapabilityEvidence):
        return False
    values = (
        item.evidence_id,
        item.source_reference,
        item.provider_api_basis,
        item.sdk_version_basis,
        item.adapter_revision_basis,
        item.authorization_reference,
        item.integrity_reference,
        item.supersedes_evidence_id,
    )
    return any(
        isinstance(value, str) and _contains_sensitive_marker(value)
        for value in values
    )


def _limitation_contains_sensitive_material(item: object) -> bool:
    if not isinstance(item, CapabilityLimitation):
        return False
    return any(
        _contains_sensitive_marker(value)
        for value in (
            item.limitation_id,
            item.description,
            item.source_evidence_id,
            item.provider_api_basis,
        )
    )


def _implementation_evidence_contains_sensitive_material(
    item: ImplementationDispositionEvidence,
) -> bool:
    values = (
        item.authority_reference,
        item.contract_reference,
        item.adapter_reference,
        item.repository_revision,
        item.dependency_basis,
        item.reason,
    )
    return any(
        isinstance(value, str) and _contains_sensitive_marker(value)
        for value in values
    )
