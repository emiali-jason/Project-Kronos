"""Provider Access and Provider Context orchestration."""

from collections.abc import Sequence

from kronos.configuration.principals import PrincipalBindingResult
from kronos.provider.contracts.access import AuthenticationActivity
from kronos.provider.exceptions.access import (
    ProviderAccessPreconditionCode,
    ProviderAccessPreconditionError,
)
from kronos.provider.models.access import (
    ProviderAvailability,
    ProviderOperationalAvailability,
    ProviderUsability,
    ProviderUsabilityState,
)
from kronos.provider.models.configuration import ConfigurationBoundaryInput
from kronos.provider.models.context import (
    AuthenticatedProviderContext,
    AuthenticationOutcome,
    ContextLifecycleReason,
    ContextReuseEligibility,
    ContextValidity,
    ProviderAuditEvidence,
    ProviderEvidenceKind,
    ProviderProvenance,
)


class ProviderContextService:
    """Own the bounded Provider Context lifecycle for one Provider."""

    __slots__ = (
        "__activity",
        "__availability",
        "__context",
        "__evidence",
        "__provider",
    )

    def __init__(
        self,
        provider: str,
        authentication_activity: AuthenticationActivity,
    ) -> None:
        if not provider.strip():
            raise ValueError("provider is required")
        self.__provider = provider
        self.__activity = authentication_activity
        self.__availability = ProviderAvailability(
            operational=ProviderOperationalAvailability.NOT_ESTABLISHED,
        )
        self.__context: AuthenticatedProviderContext | None = None
        self.__evidence: list[ProviderAuditEvidence] = []

    def authenticate(self, configuration: ConfigurationBoundaryInput) -> AuthenticationOutcome:
        """Run one activity and represent exactly one Authentication Outcome."""

        if configuration.runtime.provider != self.__provider:
            raise ProviderAccessPreconditionError(
                ProviderAccessPreconditionCode.PROVIDER_MISMATCH
            )
        if not configuration.usable:
            raise ProviderAccessPreconditionError(
                ProviderAccessPreconditionCode.CONFIGURATION_INELIGIBLE
            )

        outcome = self.__activity(configuration)
        if not isinstance(outcome, AuthenticationOutcome):
            raise TypeError("authentication activity must return AuthenticationOutcome")

        self.__record(
            ProviderAuditEvidence(
                kind=ProviderEvidenceKind.AUTHENTICATION_ACTIVITY,
                provenance=outcome.provenance,
            )
        )
        self.__record(
            ProviderAuditEvidence(
                kind=ProviderEvidenceKind.AUTHENTICATION_OUTCOME,
                provenance=outcome.provenance,
                outcome=outcome.kind,
                reason=outcome.reason,
            )
        )

        if outcome.succeeded:
            # Exchange or legacy Authentication Success is not sufficient to
            # publish context. Only adopt_authenticated_context() accepts the
            # matched projection created by ProviderAuthenticationService.
            self.__availability = ProviderAvailability(
                operational=ProviderOperationalAvailability.NOT_ESTABLISHED
            )
        elif (
            outcome.reason
            is ContextLifecycleReason.PROVIDER_OPERATIONALLY_UNAVAILABLE
        ):
            self.__availability = ProviderAvailability(
                operational=ProviderOperationalAvailability.UNAVAILABLE,
                reason=outcome.reason.value,
            )
        else:
            self.__availability = ProviderAvailability(
                operational=ProviderOperationalAvailability.AVAILABLE,
                reason=outcome.reason.value if outcome.reason is not None else None,
            )

        return outcome

    def adopt_authenticated_context(
        self,
        context: AuthenticatedProviderContext,
    ) -> None:
        """Adopt only an already-bound canonical context projection."""

        if self.__context is not None:
            raise RuntimeError("PROVIDER_CONTEXT_ALREADY_PRESENT")
        if (
            context.provider != self.__provider
            or context.validity is not ContextValidity.VALID
            or context.reuse_eligibility is not ContextReuseEligibility.ELIGIBLE
            or context.binding_result is not PrincipalBindingResult.MATCHED
            or context.attempt_id is None
        ):
            raise ValueError("MATCHED_AUTHENTICATED_CONTEXT_REQUIRED")

        provenance = context.provenance or ProviderProvenance(
            provider=context.provider,
            activity_id=context.attempt_id,
        )
        self.__context = AuthenticatedProviderContext(
            validity=context.validity,
            reuse_eligibility=context.reuse_eligibility,
            provider=context.provider,
            context_id=context.context_id,
            provenance=provenance,
            valid_until=context.valid_until,
            attempt_id=context.attempt_id,
            binding_result=context.binding_result,
        )
        self.__record(
            ProviderAuditEvidence(
                kind=ProviderEvidenceKind.CONTEXT_ESTABLISHED,
                provenance=provenance,
                context_id=context.context_id,
            )
        )

    def current_context(self) -> AuthenticatedProviderContext | None:
        """Return the current read-only context, if one is present."""

        return self.__context

    def invalidate_context(
        self,
        reason: ContextLifecycleReason = ContextLifecycleReason.CONTEXT_NO_LONGER_VALID,
    ) -> ProviderAuditEvidence | None:
        """Represent Provider-owned Context Invalidation."""

        context = self.__context
        if context is None:
            return None
        self.__context = AuthenticatedProviderContext(
            validity=ContextValidity.INVALID,
            reuse_eligibility=ContextReuseEligibility.INELIGIBLE,
            provider=context.provider,
            context_id=context.context_id,
            provenance=context.provenance,
            valid_until=context.valid_until,
        )
        self.__record(
            ProviderAuditEvidence(
                kind=ProviderEvidenceKind.CONTEXT_VALIDITY_CHANGED,
                provenance=context.provenance,
                context_id=context.context_id,
                reason=reason,
            )
        )
        evidence = ProviderAuditEvidence(
            kind=ProviderEvidenceKind.CONTEXT_INVALIDATED,
            provenance=context.provenance,
            context_id=context.context_id,
            reason=reason,
        )
        self.__record(evidence)
        return evidence

    def terminate_context(
        self,
        reason: ContextLifecycleReason = ContextLifecycleReason.EXPLICIT_TERMINATION,
    ) -> ProviderAuditEvidence | None:
        """Represent Provider-owned Context Termination."""

        context = self.__context
        if context is None:
            return None
        self.__context = AuthenticatedProviderContext(
            validity=ContextValidity.TERMINATED,
            reuse_eligibility=ContextReuseEligibility.INELIGIBLE,
            provider=context.provider,
            context_id=context.context_id,
            provenance=context.provenance,
            valid_until=context.valid_until,
        )
        self.__record(
            ProviderAuditEvidence(
                kind=ProviderEvidenceKind.CONTEXT_VALIDITY_CHANGED,
                provenance=context.provenance,
                context_id=context.context_id,
                reason=reason,
            )
        )
        evidence = ProviderAuditEvidence(
            kind=ProviderEvidenceKind.CONTEXT_TERMINATED,
            provenance=context.provenance,
            context_id=context.context_id,
            reason=reason,
        )
        self.__record(evidence)
        return evidence

    def availability(self) -> ProviderAvailability:
        """Return availability relevant to this context boundary only."""

        return self.__availability

    def usability(self, configuration: ConfigurationBoundaryInput) -> ProviderUsability:
        """Represent whether eligible Configuration can be used for access."""

        context = self.__context
        usable = (
            configuration.runtime.provider == self.__provider
            and configuration.usable
            and context is not None
            and context.validity is ContextValidity.VALID
            and self.__availability.operational
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

    def evidence(self) -> Sequence[ProviderAuditEvidence]:
        """Return immutable-by-convention evidence history."""

        return tuple(self.__evidence)

    def __record(self, evidence: ProviderAuditEvidence) -> None:
        self.__evidence.append(evidence)
