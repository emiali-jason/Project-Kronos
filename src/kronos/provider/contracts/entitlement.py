"""Provider-neutral contract for canonical EDD-003 entitlement assessment."""

from typing import Protocol

from kronos.provider.models.entitlement import (
    EntitlementAssessmentRequest,
    EntitlementAssessmentResult,
    EntitlementAuditEvidence,
    EntitlementCurrentness,
    EntitlementGuiProjection,
    ProviderEntitlementAssessmentRecord,
    ProviderEntitlementEvidence,
)


class ProviderEntitlementAssessment(Protocol):
    """Structural contract implemented by a Provider-owned assessment service."""

    def assess(
        self,
        request: EntitlementAssessmentRequest,
        evidence: ProviderEntitlementEvidence | None,
    ) -> EntitlementAssessmentResult:
        """Process one request and, if eligible, perform one assessment."""

        ...

    def current_record(self) -> ProviderEntitlementAssessmentRecord | None:
        """Return the latest applicable completed record."""

        ...

    def record_currentness(self, record_id: str) -> EntitlementCurrentness:
        """Return non-destructively derived currentness for one record."""

        ...

    def context_became_ineligible(
        self,
        provider_context_reference: str,
    ) -> None:
        """Consume EDD-001 invalidation or termination for currentness."""

        ...

    def records(self) -> tuple[ProviderEntitlementAssessmentRecord, ...]:
        """Return immutable assessment history."""

        ...

    def audit_evidence(self) -> tuple[EntitlementAuditEvidence, ...]:
        """Return immutable non-sensitive audit evidence."""

        ...

    def gui_projection(
        self,
        record: ProviderEntitlementAssessmentRecord,
    ) -> EntitlementGuiProjection:
        """Project one record without adding authority."""

        ...
