"""DOMAIN-006 shared authenticated Provider runtime and read-only leases."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from enum import StrEnum
from threading import RLock
from typing import Protocol, TypeVar
from uuid import uuid4

from kronos.configuration.principals import PrincipalBindingResult
from kronos.instrument.runtime import ProviderInstrumentAssertion
from kronos.provider.contracts.instrument import (
    InstrumentRecord,
    InstrumentResolutionError,
    InstrumentResolutionFailure,
)
from kronos.provider.contracts.market_data import (
    HistoricalCandle,
    HistoricalCandleRequest,
    HistoricalDataError,
    HistoricalDataFailure,
    LiveSnapshotError,
    LiveSnapshotFailure,
    LtpSnapshot,
    OhlcSnapshot,
    QuoteSnapshot,
)
from kronos.provider.contracts.monitoring import (
    MonitoringConsumer,
    MonitoringError,
    MonitoringFailure,
    ReadOnlyMonitoringSession,
)
from kronos.provider.contracts.provider_authentication import (
    AuthenticatedReadOnlyProviderCapability,
    ReadOnlyProviderOperation,
)
from kronos.provider.models.authentication import (
    AuthenticatedContextState,
    AuthenticationAttemptState,
    ProviderAvailabilityState,
)


class SharedProviderRuntimeLifecycle(StrEnum):
    """Sanitized lifecycle of one shared authenticated Provider context."""

    ABSENT = "ABSENT"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    ENDING = "ENDING"
    INVALIDATED = "INVALIDATED"
    DISPOSED = "DISPOSED"


class ProviderRuntimeFailure(StrEnum):
    """Sanitized failures exposed at the product access boundary."""

    CONTEXT_UNAVAILABLE = "CONTEXT_UNAVAILABLE"
    CONTEXT_ALREADY_ACTIVE = "CONTEXT_ALREADY_ACTIVE"
    PRINCIPAL_NOT_MATCHED = "PRINCIPAL_NOT_MATCHED"
    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
    OPERATION_NOT_AUTHORIZED = "OPERATION_NOT_AUTHORIZED"
    LEASE_RELEASED = "LEASE_RELEASED"
    CONTEXT_EXPIRED = "CONTEXT_EXPIRED"
    CONTEXT_INVALIDATED = "CONTEXT_INVALIDATED"
    CONTEXT_ENDING = "CONTEXT_ENDING"
    CONTEXT_DISPOSED = "CONTEXT_DISPOSED"


class ProviderRuntimeAccessError(RuntimeError):
    """Fail-closed runtime error retaining no Provider or authentication material."""

    def __init__(self, failure: ProviderRuntimeFailure) -> None:
        self.failure = failure
        super().__init__(failure.value)


class _AuthenticatedRuntime(Protocol):
    def begin_login(self) -> object: ...

    def complete_callback(self, attempt: object) -> object: ...

    def session_status(self) -> object: ...

    def current_context(self) -> object: ...

    def authenticated_read_only_capability(self) -> object: ...

    def end_kronos_session(self) -> None: ...


_Result = TypeVar("_Result")
_Clock = Callable[[], datetime]
_IdentityFactory = Callable[[], str]


class SharedAuthenticatedProviderRuntime:
    """Own exactly one authenticated context and all product lease lifecycle."""

    __slots__ = (
        "__availability",
        "__capability",
        "__clock",
        "__context_identity",
        "__failure",
        "__identity_factory",
        "__leases",
        "__lifecycle",
        "__lock",
        "__principal_binding",
        "__provider",
        "__provider_factory",
        "__provider_identity",
        "__valid_through",
    )

    def __init__(
        self,
        provider_factory: Callable[[], _AuthenticatedRuntime],
        *,
        provider_identity: str,
        clock: _Clock = lambda: datetime.now(timezone.utc),
        identity_factory: _IdentityFactory = (
            lambda: f"PROVIDER-LEASE-{uuid4().hex.upper()}"
        ),
    ) -> None:
        if (
            not callable(provider_factory)
            or not callable(clock)
            or not callable(identity_factory)
            or not _text(provider_identity)
        ):
            raise ValueError("SHARED_PROVIDER_RUNTIME_DEPENDENCY_INVALID")
        self.__provider_factory = provider_factory
        self.__provider_identity = provider_identity
        self.__clock = clock
        self.__identity_factory = identity_factory
        self.__lock = RLock()
        self.__provider: _AuthenticatedRuntime | None = None
        self.__capability: AuthenticatedReadOnlyProviderCapability | None = None
        self.__leases: dict[str, ReadOnlyProviderLease] = {}
        self.__lifecycle = SharedProviderRuntimeLifecycle.ABSENT
        self.__context_identity = ""
        self.__principal_binding: PrincipalBindingResult | None = None
        self.__availability = ProviderAvailabilityState.NOT_VERIFIED
        self.__valid_through: datetime | None = None
        self.__failure = ""

    @property
    def provider_identity(self) -> str:
        return self.__provider_identity

    @property
    def lifecycle_state(self) -> SharedProviderRuntimeLifecycle:
        with self.__lock:
            self.__synchronize_locked()
            return self.__lifecycle

    @property
    def active_lease_count(self) -> int:
        with self.__lock:
            self.__synchronize_locked()
            return len(self.__leases)

    def begin_login(self) -> object:
        """Begin one explicit authentication attempt through the sole runtime."""

        with self.__lock:
            self.__synchronize_locked()
            if self.__lifecycle in {
                SharedProviderRuntimeLifecycle.ACTIVE,
                SharedProviderRuntimeLifecycle.ENDING,
            }:
                raise ProviderRuntimeAccessError(
                    ProviderRuntimeFailure.CONTEXT_ALREADY_ACTIVE
                )
            if self.__provider is None:
                provider = self.__provider_factory()
                if not _runtime(provider):
                    raise ValueError("SHARED_PROVIDER_RUNTIME_DEPENDENCY_INVALID")
                self.__provider = provider
            provider = self.__provider
            self.__lifecycle = SharedProviderRuntimeLifecycle.ABSENT
            self.__failure = ""
        return provider.begin_login()

    def complete_callback(self, attempt: object) -> object:
        """Publish only a matched, active context after callback completion."""

        with self.__lock:
            provider = self.__provider
        if provider is None:
            raise ProviderRuntimeAccessError(
                ProviderRuntimeFailure.CONTEXT_UNAVAILABLE
            )
        outcome = provider.complete_callback(attempt)
        state = getattr(outcome, "state", None)
        binding = getattr(outcome, "binding_result", None)
        capability = provider.authenticated_read_only_capability()
        context = provider.current_context()
        status = provider.session_status()
        context_identity = getattr(context, "context_id", "")
        context_provider = getattr(context, "provider", "")
        valid_through = getattr(context, "valid_until", None)
        active = (
            state is AuthenticationAttemptState.SUCCEEDED
            and binding is PrincipalBindingResult.MATCHED
            and capability is not None
            and getattr(capability, "active", False) is True
            and getattr(status, "context_state", None)
            is AuthenticatedContextState.ACTIVE
            and context is not None
            and _text(context_identity)
            and context_provider == self.__provider_identity
            and _aware(valid_through)
            and self.__now() < valid_through
        )
        with self.__lock:
            if not active:
                self.__capability = None
                self.__principal_binding = binding
                self.__availability = getattr(
                    status,
                    "provider_availability",
                    ProviderAvailabilityState.INDETERMINATE,
                )
                failure = getattr(outcome, "failure_code", None)
                self.__failure = getattr(
                    failure,
                    "value",
                    ProviderRuntimeFailure.PRINCIPAL_NOT_MATCHED.value,
                )
                self.__revoke_locked()
                self.__lifecycle = SharedProviderRuntimeLifecycle.ABSENT
                return outcome
            self.__capability = capability
            self.__context_identity = context_identity
            self.__principal_binding = binding
            self.__availability = getattr(
                status,
                "provider_availability",
                ProviderAvailabilityState.NOT_VERIFIED,
            )
            self.__valid_through = valid_through
            self.__failure = ""
            self.__lifecycle = SharedProviderRuntimeLifecycle.ACTIVE
        return outcome

    def acquire_lease(
        self,
        *,
        consumer_identity: str,
        operations: frozenset[ReadOnlyProviderOperation],
    ) -> "ReadOnlyProviderLease":
        """Issue an independent operation-minimized lease for one product."""

        if (
            not _text(consumer_identity)
            or type(operations) is not frozenset
            or not operations
            or any(type(item) is not ReadOnlyProviderOperation for item in operations)
        ):
            raise ValueError("PROVIDER_RUNTIME_LEASE_REQUEST_INVALID")
        with self.__lock:
            self.__require_active_locked()
            capability = self.__capability
            if capability is None or not operations.issubset(capability.operations):
                raise ProviderRuntimeAccessError(
                    ProviderRuntimeFailure.OPERATION_NOT_AUTHORIZED
                )
            lease_identity = self.__identity_factory()
            if not _text(lease_identity) or lease_identity in self.__leases:
                raise ValueError("PROVIDER_RUNTIME_LEASE_IDENTITY_INVALID")
            lease = ReadOnlyProviderLease(
                self,
                lease_identity=lease_identity,
                consumer_identity=consumer_identity,
                operations=operations,
            )
            self.__leases[lease_identity] = lease
            return lease

    def invalidate(self, sanitized_failure: str = "CONTEXT_INVALIDATED") -> None:
        """Invalidate centrally and revoke every outstanding product lease."""

        if not _text(sanitized_failure):
            raise ValueError("PROVIDER_RUNTIME_FAILURE_INVALID")
        with self.__lock:
            provider = self.__provider
            self.__lifecycle = SharedProviderRuntimeLifecycle.INVALIDATED
            self.__failure = sanitized_failure
            self.__capability = None
            self.__revoke_locked()
            self.__provider = None
        if provider is not None:
            try:
                provider.end_kronos_session()
            except Exception:
                pass

    def end_kronos_session(self) -> None:
        """End the shared context once and revoke every product lease."""

        with self.__lock:
            if self.__lifecycle is SharedProviderRuntimeLifecycle.DISPOSED:
                return
            provider = self.__provider
            self.__lifecycle = SharedProviderRuntimeLifecycle.ENDING
            self.__failure = ProviderRuntimeFailure.CONTEXT_ENDING.value
            self.__capability = None
            self.__revoke_locked()
            self.__provider = None
        try:
            if provider is not None:
                try:
                    provider.end_kronos_session()
                except Exception:
                    pass
        finally:
            with self.__lock:
                self.__lifecycle = SharedProviderRuntimeLifecycle.DISPOSED
                self.__failure = ProviderRuntimeFailure.CONTEXT_DISPOSED.value
                self.__availability = ProviderAvailabilityState.NOT_VERIFIED

    def compatibility_facade(
        self,
        *,
        consumer_identity: str,
        operations: frozenset[ReadOnlyProviderOperation],
    ) -> "ProviderRuntimeCompatibilityFacade":
        return ProviderRuntimeCompatibilityFacade(
            self,
            consumer_identity=consumer_identity,
            operations=operations,
        )

    def __require_active_locked(self) -> None:
        self.__synchronize_locked()
        if self.__lifecycle is SharedProviderRuntimeLifecycle.ACTIVE:
            return
        raise ProviderRuntimeAccessError(_failure_for(self.__lifecycle))

    def __synchronize_locked(self) -> None:
        if self.__lifecycle is not SharedProviderRuntimeLifecycle.ACTIVE:
            return
        provider = self.__provider
        capability = self.__capability
        if provider is None or capability is None:
            self.__expire_locked(SharedProviderRuntimeLifecycle.INVALIDATED)
            return
        try:
            status = provider.session_status()
        except Exception:
            self.__expire_locked(SharedProviderRuntimeLifecycle.INVALIDATED)
            return
        self.__availability = getattr(
            status,
            "provider_availability",
            ProviderAvailabilityState.INDETERMINATE,
        )
        context_state = getattr(status, "context_state", None)
        if context_state is AuthenticatedContextState.EXPIRED:
            self.__expire_locked(SharedProviderRuntimeLifecycle.EXPIRED)
        elif (
            context_state is not AuthenticatedContextState.ACTIVE
            or getattr(capability, "active", False) is not True
        ):
            self.__expire_locked(SharedProviderRuntimeLifecycle.INVALIDATED)
        elif self.__valid_through is not None and self.__now() >= self.__valid_through:
            self.__expire_locked(SharedProviderRuntimeLifecycle.EXPIRED)

    def __expire_locked(self, lifecycle: SharedProviderRuntimeLifecycle) -> None:
        self.__lifecycle = lifecycle
        self.__failure = _failure_for(lifecycle).value
        self.__capability = None
        self.__revoke_locked()

    def __revoke_locked(self) -> None:
        leases = tuple(self.__leases.values())
        self.__leases.clear()
        for lease in leases:
            lease._revoke()

    def __now(self) -> datetime:
        value = self.__clock()
        if not _aware(value):
            raise ValueError("SHARED_PROVIDER_RUNTIME_CLOCK_INVALID")
        return value

    def _lease_active(self, lease_identity: str) -> bool:
        with self.__lock:
            self.__synchronize_locked()
            return (
                self.__lifecycle is SharedProviderRuntimeLifecycle.ACTIVE
                and lease_identity in self.__leases
            )

    def _lease_projection(
        self,
    ) -> tuple[
        str,
        str,
        PrincipalBindingResult | None,
        ProviderAvailabilityState,
        SharedProviderRuntimeLifecycle,
        datetime | None,
        str,
    ]:
        with self.__lock:
            self.__synchronize_locked()
            return (
                self.__provider_identity,
                self.__context_identity,
                self.__principal_binding,
                self.__availability,
                self.__lifecycle,
                self.__valid_through,
                self.__failure,
            )

    def _release(self, lease_identity: str) -> None:
        with self.__lock:
            self.__leases.pop(lease_identity, None)

    def _use(
        self,
        lease_identity: str,
        operation: ReadOnlyProviderOperation,
        call: Callable[[AuthenticatedReadOnlyProviderCapability], _Result],
    ) -> _Result:
        with self.__lock:
            self.__require_active_locked()
            lease = self.__leases.get(lease_identity)
            capability = self.__capability
            if lease is None:
                raise ProviderRuntimeAccessError(
                    ProviderRuntimeFailure.LEASE_RELEASED
                )
            if operation not in lease.operations:
                raise ProviderRuntimeAccessError(
                    ProviderRuntimeFailure.OPERATION_NOT_AUTHORIZED
                )
            if capability is None:
                raise ProviderRuntimeAccessError(
                    ProviderRuntimeFailure.CAPABILITY_UNAVAILABLE
                )
        return call(capability)

    def __repr__(self) -> str:
        return "<SharedAuthenticatedProviderRuntime sanitized>"

    __str__ = __repr__

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("SHARED_PROVIDER_RUNTIME_SERIALIZATION_PROHIBITED")


class ReadOnlyProviderLease:
    """Revocable, non-serializable, structurally read-only product capability."""

    __slots__ = (
        "__consumer_identity",
        "__lease_identity",
        "__operations",
        "__parent",
        "__released",
        "__revoked",
    )

    def __init__(
        self,
        parent: SharedAuthenticatedProviderRuntime,
        *,
        lease_identity: str,
        consumer_identity: str,
        operations: frozenset[ReadOnlyProviderOperation],
    ) -> None:
        self.__parent = parent
        self.__lease_identity = lease_identity
        self.__consumer_identity = consumer_identity
        self.__operations = operations
        self.__released = False
        self.__revoked = False

    @property
    def provider_identity(self) -> str:
        return self.__parent._lease_projection()[0]

    @property
    def authenticated_context_identity(self) -> str:
        return self.__parent._lease_projection()[1]

    @property
    def lease_identity(self) -> str:
        return self.__lease_identity

    @property
    def principal_binding_status(self) -> PrincipalBindingResult | None:
        return self.__parent._lease_projection()[2]

    @property
    def availability(self) -> ProviderAvailabilityState:
        return self.__parent._lease_projection()[3]

    @property
    def lifecycle_state(self) -> SharedProviderRuntimeLifecycle:
        return self.__parent._lease_projection()[4]

    @property
    def valid_through(self) -> datetime | None:
        return self.__parent._lease_projection()[5]

    @property
    def sanitized_failure_state(self) -> str:
        return self.__parent._lease_projection()[6]

    @property
    def operations(self) -> frozenset[ReadOnlyProviderOperation]:
        return self.__operations

    @property
    def active(self) -> bool:
        return (
            not self.__released
            and not self.__revoked
            and self.__parent._lease_active(self.__lease_identity)
        )

    def release(self) -> None:
        if self.__released:
            return
        self.__released = True
        self.__parent._release(self.__lease_identity)

    def instrument_records(self, exchange: str) -> tuple[InstrumentRecord, ...]:
        try:
            return self.__use(
                ReadOnlyProviderOperation.INSTRUMENTS,
                lambda capability: capability.instrument_records(exchange),
            )
        except ProviderRuntimeAccessError:
            raise InstrumentResolutionError(
                InstrumentResolutionFailure.CAPABILITY_UNAVAILABLE
            ) from None

    def instrument_assertions(
        self,
        exchange: str,
        *,
        source_boundary: datetime,
        valid_through: datetime,
    ) -> tuple[ProviderInstrumentAssertion, ...]:
        return self.__use(
            ReadOnlyProviderOperation.INSTRUMENT_ASSERTIONS,
            lambda capability: capability.instrument_assertions(
                exchange,
                source_boundary=source_boundary,
                valid_through=valid_through,
            ),
        )

    def historical_candles(
        self,
        request: HistoricalCandleRequest,
    ) -> tuple[HistoricalCandle, ...]:
        try:
            return self.__use(
                ReadOnlyProviderOperation.HISTORICAL_DATA,
                lambda capability: capability.historical_candles(request),
            )
        except ProviderRuntimeAccessError:
            raise HistoricalDataError(
                HistoricalDataFailure.CAPABILITY_UNAVAILABLE
            ) from None

    def quote(self, instrument: InstrumentRecord) -> QuoteSnapshot:
        return self.__live(ReadOnlyProviderOperation.QUOTE, "quote", instrument)

    def ltp(self, instrument: InstrumentRecord) -> LtpSnapshot:
        return self.__live(ReadOnlyProviderOperation.LTP, "ltp", instrument)

    def ohlc(self, instrument: InstrumentRecord) -> OhlcSnapshot:
        return self.__live(ReadOnlyProviderOperation.OHLC, "ohlc", instrument)

    def open_monitoring_session(
        self,
        consumer: MonitoringConsumer,
    ) -> ReadOnlyMonitoringSession:
        try:
            return self.__use(
                ReadOnlyProviderOperation.MONITORING,
                lambda capability: capability.open_monitoring_session(consumer),
            )
        except ProviderRuntimeAccessError:
            raise MonitoringError(MonitoringFailure.CAPABILITY_UNAVAILABLE) from None

    def _revoke(self) -> None:
        self.__revoked = True

    def __use(
        self,
        operation: ReadOnlyProviderOperation,
        call: Callable[[AuthenticatedReadOnlyProviderCapability], _Result],
    ) -> _Result:
        if self.__released or self.__revoked:
            raise ProviderRuntimeAccessError(
                ProviderRuntimeFailure.LEASE_RELEASED
            )
        return self.__parent._use(self.__lease_identity, operation, call)

    def __live(
        self,
        operation: ReadOnlyProviderOperation,
        method: str,
        instrument: InstrumentRecord,
    ) -> QuoteSnapshot | LtpSnapshot | OhlcSnapshot:
        try:
            return self.__use(
                operation,
                lambda capability: getattr(capability, method)(instrument),
            )
        except ProviderRuntimeAccessError:
            raise LiveSnapshotError(LiveSnapshotFailure.CAPABILITY_UNAVAILABLE) from None

    def __repr__(self) -> str:
        return "<ReadOnlyProviderLease redacted>"

    __str__ = __repr__

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("PROVIDER_RUNTIME_LEASE_SERIALIZATION_PROHIBITED")


class ProviderRuntimeCompatibilityFacade:
    """Preserve a product's legacy runtime interface over one shared context."""

    __slots__ = ("__consumer_identity", "__lease", "__operations", "__runtime")

    def __init__(
        self,
        runtime: SharedAuthenticatedProviderRuntime,
        *,
        consumer_identity: str,
        operations: frozenset[ReadOnlyProviderOperation],
    ) -> None:
        self.__runtime = runtime
        self.__consumer_identity = consumer_identity
        self.__operations = operations
        self.__lease: ReadOnlyProviderLease | None = None

    def begin_login(self) -> object:
        return self.__runtime.begin_login()

    def complete_callback(self, attempt: object) -> object:
        return self.__runtime.complete_callback(attempt)

    def authenticated_read_only_capability(self) -> ReadOnlyProviderLease | None:
        lease = self.__lease
        if lease is not None and lease.active:
            return lease
        if self.__runtime.lifecycle_state is not SharedProviderRuntimeLifecycle.ACTIVE:
            return None
        lease = self.__runtime.acquire_lease(
            consumer_identity=self.__consumer_identity,
            operations=self.__operations,
        )
        self.__lease = lease
        return lease

    def release_product_lease(self) -> None:
        lease = self.__lease
        self.__lease = None
        if lease is not None:
            lease.release()

    def end_kronos_session(self) -> None:
        self.release_product_lease()
        self.__runtime.end_kronos_session()

    def __repr__(self) -> str:
        return "<ProviderRuntimeCompatibilityFacade sanitized>"

    __str__ = __repr__


def _runtime(value: object) -> bool:
    return all(
        callable(getattr(value, member, None))
        for member in (
            "begin_login",
            "complete_callback",
            "session_status",
            "current_context",
            "authenticated_read_only_capability",
            "end_kronos_session",
        )
    )


def _failure_for(
    lifecycle: SharedProviderRuntimeLifecycle,
) -> ProviderRuntimeFailure:
    return {
        SharedProviderRuntimeLifecycle.ABSENT: ProviderRuntimeFailure.CONTEXT_UNAVAILABLE,
        SharedProviderRuntimeLifecycle.ACTIVE: ProviderRuntimeFailure.CAPABILITY_UNAVAILABLE,
        SharedProviderRuntimeLifecycle.EXPIRED: ProviderRuntimeFailure.CONTEXT_EXPIRED,
        SharedProviderRuntimeLifecycle.ENDING: ProviderRuntimeFailure.CONTEXT_ENDING,
        SharedProviderRuntimeLifecycle.INVALIDATED: ProviderRuntimeFailure.CONTEXT_INVALIDATED,
        SharedProviderRuntimeLifecycle.DISPOSED: ProviderRuntimeFailure.CONTEXT_DISPOSED,
    }[lifecycle]


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


__all__ = [
    "ProviderRuntimeAccessError",
    "ProviderRuntimeCompatibilityFacade",
    "ProviderRuntimeFailure",
    "ReadOnlyProviderLease",
    "SharedAuthenticatedProviderRuntime",
    "SharedProviderRuntimeLifecycle",
]
