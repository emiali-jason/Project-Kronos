"""Governed, externally inert Kite authentication dependency composition."""

from __future__ import annotations

import secrets
import webbrowser
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any

from kronos.configuration.apple_keychain import (
    AppleKeychainCredentialSource,
    AppleKeychainIntendedPrincipalResolver,
    SubprocessRequest,
    SubprocessRunner,
    run_security_subprocess,
)
from kronos.configuration.settings import GovernedProviderAuthenticationConfiguration
from kronos.provider.adapters.kite.authentication import (
    create_kite_authentication_adapter,
)
from kronos.provider.adapters.kite.navigation import KiteLoginNavigator
from kronos.provider.callbacks.loopback import (
    LoopbackAuthenticationCallbackListener,
    ServerFactory,
    create_standard_library_server,
)
from kronos.provider.kite.adapter.kite_provider import KiteProvider
from kronos.provider.kite.auth.kite_authentication import KiteAuthentication
from kronos.provider.kite.live_activation import (
    CoordinatedActivationValues,
    DurableConsumptionRecord,
    LiveActivationContext,
    MonotonicLifecycleDeadline,
    ProvenConsumption,
    RemainingBudget,
    ReviewedActivationCapability,
)
from kronos.provider.models.authentication import (
    GovernedAuthenticationOperation,
    SanitizedOperationLedger,
)
from kronos.provider.services.provider_authentication import ProviderAuthenticationService


_LIVE_DEPENDENCY_SET_REF = "CAR017-LIVE-COMPOSITION-DEPENDENCY-SET-V1"
_API_SECRET_ACCOUNT_PREFIX = "api-secret:"
_INTENDED_PRINCIPAL_ACCOUNT_PREFIX = "intended-principal:"

Clock = Callable[[], datetime]
IdentityFactory = Callable[[], str]
BudgetSupplier = Callable[[], RemainingBudget]


class LiveCompositionFailure(StrEnum):
    """Sanitized composition failures containing no activation material."""

    INVALID_ACTIVATION = "INVALID_ACTIVATION"
    INCOMPLETE_COMPOSITION = "INCOMPLETE_COMPOSITION"
    CONFIGURATION_MISMATCH = "CONFIGURATION_MISMATCH"
    DEADLINE_EXHAUSTED = "DEADLINE_EXHAUSTED"
    DEPENDENCY_CONSTRUCTION_FAILED = "DEPENDENCY_CONSTRUCTION_FAILED"


class LiveCompositionError(RuntimeError):
    """Controlled composition failure with no raw exception retention."""

    def __init__(self, failure: LiveCompositionFailure) -> None:
        self.failure = failure
        super().__init__(failure.value)


class OperationLedgerRecorder:
    """Mutable local holder around the immutable sanitized Stage 1 ledger."""

    __slots__ = ("__ledger",)

    def __init__(self, ledger: SanitizedOperationLedger | None = None) -> None:
        if ledger is not None and type(ledger) is not SanitizedOperationLedger:
            raise LiveCompositionError(LiveCompositionFailure.INVALID_ACTIVATION)
        self.__ledger = ledger or SanitizedOperationLedger.empty()

    def record(self, operation: GovernedAuthenticationOperation) -> None:
        self.__ledger = self.__ledger.record(operation)

    def snapshot(self) -> SanitizedOperationLedger:
        return self.__ledger

    def adopt(self, ledger: SanitizedOperationLedger) -> None:
        if type(ledger) is not SanitizedOperationLedger:
            raise LiveCompositionError(LiveCompositionFailure.INVALID_ACTIVATION)
        self.__ledger = ledger

    def __repr__(self) -> str:
        return "<OperationLedgerRecorder sanitized>"


class GovernedKiteAuthenticationRuntime:
    """Single runtime facade that adds governed counts and blocks availability."""

    __slots__ = ("__provider", "__recorder")

    def __init__(
        self,
        provider: KiteProvider,
        *,
        recorder: OperationLedgerRecorder,
    ) -> None:
        self.__provider = provider
        self.__recorder = recorder

    def begin_login(self) -> object:
        return self.__provider.begin_login()

    def complete_callback(self, attempt: object) -> object:
        return self.__provider.complete_callback(attempt)  # type: ignore[arg-type]

    def cancel_authentication_attempt(self, attempt: object) -> object:
        return self.__provider.cancel_authentication_attempt(attempt)  # type: ignore[arg-type]

    def session_status(self) -> object:
        return self.__provider.session_status()

    def authentication_attempt_status(self, attempt: object) -> object:
        return self.__provider.authentication_attempt_status(attempt)  # type: ignore[arg-type]

    def current_context(self) -> object:
        return self.__provider.current_context()

    def authenticated_read_only_capability(self) -> object:
        return self.__provider.authenticated_read_only_capability()

    def verify_provider_availability(self) -> object:
        raise LiveCompositionError(LiveCompositionFailure.INVALID_ACTIVATION)

    def end_kronos_session(self) -> None:
        self.__provider.end_kronos_session()

    def cleanup_local(self) -> None:
        """Perform idempotent local-only cleanup through the authoritative path."""

        self.__provider.end_kronos_session()

    def operation_ledger(self) -> SanitizedOperationLedger:
        return self.__recorder.snapshot()

    def __repr__(self) -> str:
        return "<GovernedKiteAuthenticationRuntime sanitized>"


class _GovernedListener:
    __slots__ = ("__budget", "__listener")

    def __init__(
        self,
        listener: LoopbackAuthenticationCallbackListener,
        budget: BudgetSupplier,
    ) -> None:
        self.__listener = listener
        self.__budget = budget

    def start(self) -> None:
        _require_budget(self.__budget)
        self.__listener.start()

    def readiness(self) -> object:
        return self.__listener.readiness()

    def receive_once(self, *, deadline: datetime) -> object:
        seconds = _require_budget(self.__budget)
        bounded = min(deadline, datetime.now(deadline.tzinfo) + timedelta(seconds=seconds))
        return self.__listener.receive_once(deadline=bounded)

    def close(self) -> None:
        self.__listener.close()


def compose_kite_authentication(
    activation: object,
    *,
    proven_consumption: ProvenConsumption,
    activation_capability: object,
    activation_values: CoordinatedActivationValues,
    configuration: GovernedProviderAuthenticationConfiguration,
    operation_recorder: OperationLedgerRecorder,
    remaining_budget: BudgetSupplier,
    security_runner: SubprocessRunner = run_security_subprocess,
    browser_opener: Callable[[str], bool] = webbrowser.open,
    server_factory: ServerFactory = create_standard_library_server,
    adapter_factory: Callable[..., Any] = create_kite_authentication_adapter,
    credential_source_factory: Callable[..., Any] = AppleKeychainCredentialSource,
    intended_principal_resolver_factory: Callable[..., Any] = (
        AppleKeychainIntendedPrincipalResolver
    ),
    navigator_factory: Callable[..., Any] = KiteLoginNavigator,
    service_factory: Callable[..., Any] = ProviderAuthenticationService,
    clock: Clock | None = None,
    identity_factory: IdentityFactory | None = None,
) -> GovernedKiteAuthenticationRuntime:
    """Wire the sole Kite path after exact pre-factory validation."""

    dependencies = (
        security_runner,
        browser_opener,
        server_factory,
        adapter_factory,
        credential_source_factory,
        intended_principal_resolver_factory,
        navigator_factory,
        service_factory,
        remaining_budget,
    )
    if any(not callable(dependency) for dependency in dependencies):
        raise LiveCompositionError(LiveCompositionFailure.INCOMPLETE_COMPOSITION)
    if (
        type(activation) is not LiveActivationContext
        or type(activation_capability) is not ReviewedActivationCapability
        or type(activation_values) is not CoordinatedActivationValues
        or type(operation_recorder) is not OperationLedgerRecorder
        or type(proven_consumption) is not ProvenConsumption
        or type(proven_consumption.record) is not DurableConsumptionRecord
        or type(proven_consumption.deadline) is not MonotonicLifecycleDeadline
        or type(proven_consumption.ledger) is not SanitizedOperationLedger
        or not activation._matches_capability(activation_capability)  # type: ignore[attr-defined]
        or not activation._matches_values(activation_values)  # type: ignore[attr-defined]
        or operation_recorder.snapshot() is not proven_consumption.ledger
        or proven_consumption.record.coordinated_activation_identity
        != activation.coordinated_activation_identity  # type: ignore[attr-defined]
        or proven_consumption.record.coordinated_governance_publication_sha
        != activation.coordinated_governance_publication_sha  # type: ignore[attr-defined]
    ):
        raise LiveCompositionError(LiveCompositionFailure.INVALID_ACTIVATION)
    if (
        type(configuration) is not GovernedProviderAuthenticationConfiguration
        or configuration.provider_identity != activation_values.provider_identity
        or configuration.provider_configuration_ref
        != activation_values.provider_configuration_ref
        or configuration.application_registration_ref
        != activation_values.application_registration_ref
        or configuration.authentication.provider
        != activation_values.operational_provider
        or configuration.authentication.redirect_uri != activation_values.redirect_url
        or configuration.authentication.credential_ref != activation_values.credential_ref
        or configuration.authentication.intended_registration_ref
        != activation_values.intended_principal_registration_ref
        or activation_values.composition_dependency_set_ref
        != _LIVE_DEPENDENCY_SET_REF
    ):
        raise LiveCompositionError(LiveCompositionFailure.CONFIGURATION_MISMATCH)

    real_dependencies = (
        security_runner is run_security_subprocess,
        browser_opener is webbrowser.open,
        server_factory is create_standard_library_server,
        adapter_factory is create_kite_authentication_adapter,
        credential_source_factory is AppleKeychainCredentialSource,
        intended_principal_resolver_factory is AppleKeychainIntendedPrincipalResolver,
    )
    if any(real_dependencies) and not activation._is_live_capable():  # type: ignore[attr-defined]
        raise LiveCompositionError(LiveCompositionFailure.INVALID_ACTIVATION)
    _require_budget(remaining_budget)

    effective_clock = clock or _utc_now
    effective_identity_factory = identity_factory or _new_attempt_identity
    try:
        governed_runner = _governed_security_runner(
            security_runner,
            operation_recorder,
            remaining_budget,
        )
        credential_source = credential_source_factory(
            provider=configuration.authentication.provider,
            runner=governed_runner,
        )
        principal_resolver = intended_principal_resolver_factory(
            provider=configuration.authentication.provider,
            runner=governed_runner,
        )
        navigator = navigator_factory(
            opener=_governed_browser_opener(
                browser_opener,
                operation_recorder,
                remaining_budget,
            )
        )

        def governed_server_factory(session: object) -> object:
            _before_operation(
                GovernedAuthenticationOperation.LISTENER_BIND,
                operation_recorder,
                remaining_budget,
            )
            return server_factory(session)  # type: ignore[arg-type]

        def listener_factory() -> _GovernedListener:
            _before_operation(
                GovernedAuthenticationOperation.LISTENER_CONSTRUCTION,
                operation_recorder,
                remaining_budget,
            )
            return _GovernedListener(
                LoopbackAuthenticationCallbackListener(
                    server_factory=governed_server_factory,
                    clock=effective_clock,
                ),
                remaining_budget,
            )

        def governed_adapter_factory(api_key: str) -> object:
            _require_budget(remaining_budget)
            return adapter_factory(
                api_key,
                operation_recorder=operation_recorder.record,
                remaining_budget=remaining_budget,
            )

        service = service_factory(
            configuration.authentication,
            credential_source=credential_source,
            principal_resolver=principal_resolver,
            adapter_factory=governed_adapter_factory,
            listener_factory=listener_factory,
            navigator=navigator,
            clock=effective_clock,
            identity_factory=effective_identity_factory,
            proven_consumption=proven_consumption,
            remaining_budget=remaining_budget,
            operation_recorder=operation_recorder,
            attempt_lifetime=timedelta(
                seconds=(
                    activation.authentication_attempt_timeout_seconds  # type: ignore[attr-defined]
                )
            ),
        )
        provider = KiteProvider(KiteAuthentication(service, clock=effective_clock))
        return GovernedKiteAuthenticationRuntime(
            provider,
            recorder=operation_recorder,
        )
    except LiveCompositionError:
        raise
    except Exception:
        raise LiveCompositionError(
            LiveCompositionFailure.DEPENDENCY_CONSTRUCTION_FAILED
        ) from None


def _governed_security_runner(
    runner: SubprocessRunner,
    recorder: OperationLedgerRecorder,
    budget: BudgetSupplier,
) -> SubprocessRunner:
    def run(request: SubprocessRequest) -> object:
        operation = _keychain_operation(request)
        seconds = _require_budget(budget)
        _record_once(recorder, operation)
        bounded_request = replace(
            request,
            timeout_seconds=min(request.timeout_seconds, seconds),
        )
        return runner(bounded_request)

    return run  # type: ignore[return-value]


def _keychain_operation(request: SubprocessRequest) -> GovernedAuthenticationOperation:
    try:
        account = request.argv[-1]
    except Exception:
        raise LiveCompositionError(LiveCompositionFailure.CONFIGURATION_MISMATCH) from None
    if account.startswith(_API_SECRET_ACCOUNT_PREFIX):
        return GovernedAuthenticationOperation.API_SECRET_RETRIEVAL
    if account.startswith(_INTENDED_PRINCIPAL_ACCOUNT_PREFIX):
        return GovernedAuthenticationOperation.INTENDED_PRINCIPAL_RETRIEVAL
    raise LiveCompositionError(LiveCompositionFailure.CONFIGURATION_MISMATCH)


def _governed_browser_opener(
    opener: Callable[[str], bool],
    recorder: OperationLedgerRecorder,
    budget: BudgetSupplier,
) -> Callable[[str], bool]:
    def open_once(url: str) -> bool:
        _before_operation(
            GovernedAuthenticationOperation.BROWSER_LAUNCH,
            recorder,
            budget,
        )
        return opener(url)

    return open_once


def _before_operation(
    operation: GovernedAuthenticationOperation,
    recorder: OperationLedgerRecorder,
    budget: BudgetSupplier,
) -> None:
    _require_budget(budget)
    _record_once(recorder, operation)


def _record_once(
    recorder: OperationLedgerRecorder,
    operation: GovernedAuthenticationOperation,
) -> None:
    try:
        recorder.record(operation)
    except Exception:
        raise LiveCompositionError(LiveCompositionFailure.INVALID_ACTIVATION) from None


def _require_budget(supplier: BudgetSupplier) -> float:
    try:
        budget = supplier()
        if type(budget) is not RemainingBudget:
            raise TypeError
        return budget.require_available()
    except Exception:
        raise LiveCompositionError(LiveCompositionFailure.DEADLINE_EXHAUSTED) from None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_attempt_identity() -> str:
    return secrets.token_hex(16)


__all__ = [
    "GovernedKiteAuthenticationRuntime",
    "LiveCompositionError",
    "LiveCompositionFailure",
    "OperationLedgerRecorder",
    "compose_kite_authentication",
]
