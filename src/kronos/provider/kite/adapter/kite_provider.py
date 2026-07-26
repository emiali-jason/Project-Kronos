"""Kite implementation of the EDD-001 Provider Access boundary."""

from datetime import datetime
from typing import Protocol

from kronos.provider.adapters.kite.authentication import KiteContextEvidence
from kronos.provider.contracts.authentication import AuthenticationProvider
from kronos.provider.contracts.context import ProviderContext
from kronos.provider.contracts.provider import Provider
from kronos.provider.exceptions.connectivity import ProviderConnectivityError
from kronos.provider.models.access import (
    ProviderAvailability,
    ProviderOperationalAvailability,
    ProviderUsability,
    ProviderUsabilityState,
)
from kronos.provider.models.configuration import ConfigurationBoundaryInput
from kronos.provider.models.context import (
    AuthenticationOutcome,
    AuthenticatedProviderContext,
    ContextLifecycleReason,
    ContextValidity,
    ProviderAuditEvidence,
    ProviderEvidenceKind,
)


class _KiteAuthenticationBoundary(AuthenticationProvider, Protocol):
    def operational_availability(self) -> ProviderOperationalAvailability: ...

    def context_evidence(self) -> KiteContextEvidence: ...

    def terminate_authenticated_context(self) -> None: ...

    def context_expired(self, valid_until: datetime | None) -> bool: ...


class KiteProvider(Provider):
    """Orchestrate Kite access without absorbing authentication mechanics."""

    def __init__(
        self,
        authentication: _KiteAuthenticationBoundary,
        context: ProviderContext,
    ) -> None:
        self._authentication = authentication
        self._context = context
        self._evidence: list[ProviderAuditEvidence] = []

    def authenticate(
        self,
        configuration: ConfigurationBoundaryInput,
    ) -> AuthenticationOutcome:
        outcome = self._authentication.authenticate(configuration)
        provenance = outcome.provenance
        self._evidence.append(
            ProviderAuditEvidence(
                kind=ProviderEvidenceKind.AUTHENTICATION_ACTIVITY,
                provenance=provenance,
            )
        )
        self._evidence.append(
            ProviderAuditEvidence(
                kind=ProviderEvidenceKind.AUTHENTICATION_OUTCOME,
                provenance=provenance,
                outcome=outcome.kind,
                reason=outcome.reason,
            )
        )
        if outcome.succeeded:
            context = self._context.establish(outcome)
            self._evidence.append(
                ProviderAuditEvidence(
                    kind=ProviderEvidenceKind.CONTEXT_ESTABLISHED,
                    provenance=provenance,
                    context_id=context.context_id,
                    outcome=outcome.kind,
                )
            )
        return outcome

    def current_context(self) -> AuthenticatedProviderContext | None:
        self._invalidate_documented_expiry()
        return self._context.current()

    def validate_context(self) -> ProviderAuditEvidence | None:
        """Apply current authoritative provider evidence to Context Validity."""

        self._invalidate_documented_expiry()
        current = self._context.current()
        if current is None or current.validity is not ContextValidity.VALID:
            return None
        evidence = self._authentication.context_evidence()
        if evidence is KiteContextEvidence.INVALID:
            return self.invalidate_context(ContextLifecycleReason.INVALID_PROVIDER_TOKEN)
        return None

    def invalidate_context(
        self,
        reason: ContextLifecycleReason = ContextLifecycleReason.CONTEXT_NO_LONGER_VALID,
    ) -> ProviderAuditEvidence | None:
        current = self._context.current()
        if current is None or current.provenance is None:
            self._context.invalidate()
            return None
        self._context.invalidate()
        self._evidence.append(
            ProviderAuditEvidence(
                kind=ProviderEvidenceKind.CONTEXT_VALIDITY_CHANGED,
                provenance=current.provenance,
                context_id=current.context_id,
                reason=reason,
            )
        )
        evidence = ProviderAuditEvidence(
            kind=ProviderEvidenceKind.CONTEXT_INVALIDATED,
            provenance=current.provenance,
            context_id=current.context_id,
            reason=reason,
        )
        self._evidence.append(evidence)
        return evidence

    def terminate_context(
        self,
        reason: ContextLifecycleReason = ContextLifecycleReason.EXPLICIT_TERMINATION,
    ) -> ProviderAuditEvidence | None:
        current = self._context.current()
        if current is None or current.provenance is None:
            return None
        try:
            self._authentication.terminate_authenticated_context()
        except ProviderConnectivityError:
            return self.invalidate_context(
                ContextLifecycleReason.CONTEXT_NO_LONGER_VALID
            )

        self._context.terminate()
        self._evidence.append(
            ProviderAuditEvidence(
                kind=ProviderEvidenceKind.CONTEXT_VALIDITY_CHANGED,
                provenance=current.provenance,
                context_id=current.context_id,
                reason=reason,
            )
        )
        evidence = ProviderAuditEvidence(
            kind=ProviderEvidenceKind.CONTEXT_TERMINATED,
            provenance=current.provenance,
            context_id=current.context_id,
            reason=reason,
        )
        self._evidence.append(evidence)
        return evidence

    def context_reuse_eligible(self) -> bool:
        self._invalidate_documented_expiry()
        return self._context.reuse_eligible()

    def availability(self) -> ProviderAvailability:
        return ProviderAvailability(
            operational=self._authentication.operational_availability()
        )

    def usability(self, configuration: ConfigurationBoundaryInput) -> ProviderUsability:
        self._invalidate_documented_expiry()
        context = self._context.current()
        usable = (
            configuration.runtime.provider.upper() == "KITE"
            and configuration.usable
            and context is not None
            and context.validity is ContextValidity.VALID
            and self._authentication.operational_availability()
            is ProviderOperationalAvailability.AVAILABLE
        )
        return ProviderUsability(
            state=(
                ProviderUsabilityState.USABLE
                if usable
                else ProviderUsabilityState.UNUSABLE
            ),
            reason=None if usable else "PROVIDER_CONTEXT_NOT_USABLE",
        )

    def evidence(self) -> tuple[ProviderAuditEvidence, ...]:
        self._invalidate_documented_expiry()
        return tuple(self._evidence)

    def _invalidate_documented_expiry(self) -> None:
        current = self._context.current()
        if (
            current is not None
            and current.validity is ContextValidity.VALID
            and self._authentication.context_expired(current.valid_until)
        ):
            self.invalidate_context(ContextLifecycleReason.CONTEXT_EXPIRED)
