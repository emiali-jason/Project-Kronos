"""Kite provider-owned authenticated context implementation."""

from typing import Optional

from kronos.provider.models.context import (
    AuthenticatedProviderContext,
    AuthenticationOutcome,
    ContextReuseEligibility,
    ContextValidity,
)


class KiteProviderContext:
    """Own bounded context establishment and lifecycle meanings for Kite."""

    def __init__(self) -> None:
        self._current: Optional[AuthenticatedProviderContext] = None

    def establish(self, outcome: AuthenticationOutcome) -> AuthenticatedProviderContext:
        if not outcome.succeeded:
            raise ValueError("only Authentication Success may establish context")
        context = AuthenticatedProviderContext(
            validity=ContextValidity.VALID,
            reuse_eligibility=ContextReuseEligibility.ELIGIBLE,
            provider=outcome.provenance.provider,
            context_id=outcome.provenance.activity_id,
            provenance=outcome.provenance,
            valid_until=outcome.valid_until,
        )
        self._current = context
        return context

    def current(self) -> Optional[AuthenticatedProviderContext]:
        return self._current

    def invalidate(self) -> None:
        if self._current is None:
            return
        self._current = AuthenticatedProviderContext(
            validity=ContextValidity.INVALID,
            reuse_eligibility=ContextReuseEligibility.INELIGIBLE,
            provider=self._current.provider,
            context_id=self._current.context_id,
            provenance=self._current.provenance,
            valid_until=self._current.valid_until,
        )

    def terminate(self) -> None:
        if self._current is None:
            return
        self._current = AuthenticatedProviderContext(
            validity=ContextValidity.TERMINATED,
            reuse_eligibility=ContextReuseEligibility.INELIGIBLE,
            provider=self._current.provider,
            context_id=self._current.context_id,
            provenance=self._current.provenance,
            valid_until=self._current.valid_until,
        )

    def reuse_eligible(self) -> bool:
        context = self._current
        return bool(
            context is not None
            and context.validity is ContextValidity.VALID
            and context.reuse_eligibility is ContextReuseEligibility.ELIGIBLE
        )
