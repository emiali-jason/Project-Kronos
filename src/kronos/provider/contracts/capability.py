"""Provider-neutral contract for canonical EDD-002 capability assessment."""

from collections.abc import Sequence
from typing import Protocol

from kronos.provider.models.capability import (
    CapabilityAssessmentRecord,
    CapabilityAssessmentRequest,
    CapabilityAssessmentResult,
    CapabilityAuditEvidence,
    CapabilityEvidence,
    CapabilityGuiProjection,
    CapabilityIdentifier,
    CapabilityLimitation,
)


class ProviderCapabilityAssessment(Protocol):
    """Bounded Provider-owned assessment contract."""

    def assess(
        self,
        request: CapabilityAssessmentRequest,
        evidence: Sequence[CapabilityEvidence],
        limitations: Sequence[CapabilityLimitation] = (),
    ) -> CapabilityAssessmentResult:
        """Process one request and, if eligible, perform one assessment."""

    def current_record(
        self,
        capability_identifier: CapabilityIdentifier,
    ) -> CapabilityAssessmentRecord | None:
        """Return the current completed record for one capability."""

    def records(self) -> tuple[CapabilityAssessmentRecord, ...]:
        """Return immutable assessment history."""

    def audit_evidence(self) -> tuple[CapabilityAuditEvidence, ...]:
        """Return immutable non-sensitive audit evidence."""

    def gui_projection(
        self,
        record: CapabilityAssessmentRecord,
    ) -> CapabilityGuiProjection:
        """Project one record without adding authority."""
