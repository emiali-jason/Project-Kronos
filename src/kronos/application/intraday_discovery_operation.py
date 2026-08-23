"""WO-05A explicit operation boundary for Intraday Native Discovery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
import json
from threading import RLock
from typing import Callable

from kronos.application.intraday_discovery import IntradayDiscoveryApplication
from kronos.intraday.discovery import DiscoveryError, DiscoveryFailure
from kronos.intraday.discovery_persistence import NativeDiscoveryStore
from kronos.intraday.discovery_runtime import (
    DiscoveryRunBoundary,
    IntradayNativeDiscoveryService,
)
from kronos.intraday.discovery_source import (
    ProviderDiscoveryFactualSource,
    governed_market_session_identities,
)
from kronos.intraday.reconciliation import Availability, ReconciliationPublication
from kronos.intraday.universe import (
    IntradayUniverseError,
    IntradayUniverseFailure,
    IntradayUniversePublication,
)
from kronos.market.calendar import MarketCalendarPublisher
from kronos.provider.runtime import (
    ProviderRuntimeAccessError,
    ProviderRuntimeFailure,
    ReadOnlyProviderLease,
    SharedAuthenticatedProviderRuntime,
    SharedProviderRuntimeLifecycle,
)


DISCOVERY_OPERATION_SERVICE_IDENTITY = (
    "KRONOS-INTRADAY-DISCOVERY-OPERATION-SERVICE-V0"
)
DISCOVERY_OPERATION_SERVICE_VERSION = "0.1.0"


class DiscoveryOperationState(StrEnum):
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    CONFLICT = "CONFLICT"


class DiscoveryOperationStage(StrEnum):
    CONTEXT_VERIFICATION = "CONTEXT_VERIFICATION"
    LEASE_ACQUISITION = "LEASE_ACQUISITION"
    UNIVERSE_RESOLUTION = "UNIVERSE_RESOLUTION"
    RECONCILIATION_RESOLUTION = "RECONCILIATION_RESOLUTION"
    OBSERVATION_BOUNDARY = "OBSERVATION_BOUNDARY"
    FACTUAL_SOURCE_ACQUISITION = "FACTUAL_SOURCE_ACQUISITION"
    MACHINE_FACT_ASSEMBLY = "MACHINE_FACT_ASSEMBLY"
    DISCOVERY_RUN_CONSTRUCTION = "DISCOVERY_RUN_CONSTRUCTION"
    PERSISTENCE = "PERSISTENCE"
    APPLICATION_SNAPSHOT = "APPLICATION_SNAPSHOT"
    COMPLETE = "COMPLETE"


class DiscoveryOperationFailure(StrEnum):
    CONTEXT_UNAVAILABLE = "CONTEXT_UNAVAILABLE"
    CONTEXT_EXPIRED = "CONTEXT_EXPIRED"
    OPERATION_UNAVAILABLE = "OPERATION_UNAVAILABLE"
    LEASE_UNAVAILABLE = "LEASE_UNAVAILABLE"
    UNIVERSE_VERSION_UNAVAILABLE = "UNIVERSE_VERSION_UNAVAILABLE"
    RECONCILIATION_VERSION_UNAVAILABLE = "RECONCILIATION_VERSION_UNAVAILABLE"
    CANONICAL_IDENTITY_UNAVAILABLE = "CANONICAL_IDENTITY_UNAVAILABLE"
    MACHINE_FACT_PREREQUISITE_UNAVAILABLE = (
        "MACHINE_FACT_PREREQUISITE_UNAVAILABLE"
    )
    PUBLICATION_STALE = "PUBLICATION_STALE"
    PUBLICATION_UNAVAILABLE = "PUBLICATION_UNAVAILABLE"
    MARKET_SESSION_UNAVAILABLE = "MARKET_SESSION_UNAVAILABLE"
    OBSERVATION_BOUNDARY_INVALID = "OBSERVATION_BOUNDARY_INVALID"
    PROVIDER_ACQUISITION_FAILURE = "PROVIDER_ACQUISITION_FAILURE"
    MANDATORY_TIMEFRAME_UNAVAILABLE = "MANDATORY_TIMEFRAME_UNAVAILABLE"
    INCOMPLETE_CANDLE_UNAUTHORIZED = "INCOMPLETE_CANDLE_UNAUTHORIZED"
    INCOMPLETE_CANDLE_NOT_AUTHORIZED = "INCOMPLETE_CANDLE_NOT_AUTHORIZED"
    SOURCE_STALE = "SOURCE_STALE"
    MACHINE_FACT_BUNDLE_INCOMPLETE = "MACHINE_FACT_BUNDLE_INCOMPLETE"
    INTEGRITY_INVALID = "INTEGRITY_INVALID"
    FACT_RECONCILIATION_FAILURE = "FACT_RECONCILIATION_FAILURE"
    BUNDLE_INTEGRITY_FAILURE = "BUNDLE_INTEGRITY_FAILURE"
    RUN_INTEGRITY_FAILURE = "RUN_INTEGRITY_FAILURE"
    PERSISTENCE_CONFLICT = "PERSISTENCE_CONFLICT"
    PERSISTENCE_FAILURE = "PERSISTENCE_FAILURE"
    SNAPSHOT_UPDATE_FAILURE = "SNAPSHOT_UPDATE_FAILURE"
    OPERATION_CONFLICT = "OPERATION_CONFLICT"


@dataclass(frozen=True, slots=True)
class DiscoveryOperationRequest:
    operation_identity: str
    observation_boundary: datetime
    requested_at: datetime

    def __post_init__(self) -> None:
        if (
            not self.operation_identity.startswith(
                "KRONOS-INTRADAY-DISCOVERY-OPERATION-"
            )
            or not _aware(self.observation_boundary)
            or not _aware(self.requested_at)
            or self.requested_at > self.observation_boundary
        ):
            raise ValueError("DISCOVERY_OPERATION_REQUEST_INVALID")


def create_discovery_operation_request(
    *,
    observation_boundary: datetime,
    request_identity: str,
    requested_at: datetime | None = None,
) -> DiscoveryOperationRequest:
    created = requested_at or observation_boundary
    if not _aware(observation_boundary) or not _aware(created) or not _text(request_identity):
        raise ValueError("DISCOVERY_OPERATION_REQUEST_INVALID")
    identity = _identity({
        "observation_boundary": observation_boundary,
        "request_identity": request_identity,
    })
    return DiscoveryOperationRequest(identity, observation_boundary, created)


@dataclass(frozen=True, slots=True)
class DiscoveryOperationResult:
    operation_identity: str
    state: DiscoveryOperationState
    context_state: str
    stage: DiscoveryOperationStage
    observation_boundary: datetime
    universe_count: int
    pre_evaluable_count: int
    prerequisite_unavailable_count: int
    machine_fact_successes: int
    machine_fact_failures: int
    historical_request_count: int
    run_identity: str | None
    persistence_complete: bool
    snapshot_updated: bool
    failure: DiscoveryOperationFailure | None
    completed_at: datetime

    def __post_init__(self) -> None:
        if (
            not self.operation_identity.startswith(
                "KRONOS-INTRADAY-DISCOVERY-OPERATION-"
            )
            or type(self.state) is not DiscoveryOperationState
            or not _text(self.context_state)
            or type(self.stage) is not DiscoveryOperationStage
            or not _aware(self.observation_boundary)
            or not _aware(self.completed_at)
            or any(type(value) is not int or value < 0 for value in (
                self.universe_count,
                self.pre_evaluable_count,
                self.prerequisite_unavailable_count,
                self.machine_fact_successes,
                self.machine_fact_failures,
                self.historical_request_count,
            ))
            or (self.run_identity is not None and not _text(self.run_identity))
            or type(self.persistence_complete) is not bool
            or type(self.snapshot_updated) is not bool
            or (self.failure is not None and type(self.failure) is not DiscoveryOperationFailure)
        ):
            raise ValueError("DISCOVERY_OPERATION_RESULT_INVALID")


FactualSourceFactory = Callable[
    [ReadOnlyProviderLease], ProviderDiscoveryFactualSource
]


class IntradayDiscoveryOperationService:
    """Serialize one explicit operation over the existing shared context."""

    def __init__(
        self,
        *,
        provider_runtime: SharedAuthenticatedProviderRuntime,
        acquire_lease: Callable[[], ReadOnlyProviderLease],
        universe: IntradayUniversePublication,
        reconciliation: ReconciliationPublication,
        application: IntradayDiscoveryApplication,
        store: NativeDiscoveryStore,
        calendar_publisher: MarketCalendarPublisher,
        factual_source_factory: FactualSourceFactory,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        if (
            type(provider_runtime) is not SharedAuthenticatedProviderRuntime
            or not callable(acquire_lease)
            or type(universe) is not IntradayUniversePublication
            or type(reconciliation) is not ReconciliationPublication
            or type(application) is not IntradayDiscoveryApplication
            or type(store) is not NativeDiscoveryStore
            or type(calendar_publisher) is not MarketCalendarPublisher
            or not callable(factual_source_factory)
            or not callable(clock)
        ):
            raise ValueError("DISCOVERY_OPERATION_DEPENDENCY_INVALID")
        self._runtime = provider_runtime
        self._acquire_lease = acquire_lease
        self._universe = universe
        self._reconciliation = reconciliation
        self._application = application
        self._store = store
        self._calendar = calendar_publisher
        self._source_factory = factual_source_factory
        self._clock = clock
        self._lock = RLock()
        self._active_identity: str | None = None
        self._results: dict[str, DiscoveryOperationResult] = {}

    @property
    def operation_available(self) -> bool:
        return self._runtime.lifecycle_state is SharedProviderRuntimeLifecycle.ACTIVE

    @property
    def actual_context_state(self) -> str:
        return self._runtime.lifecycle_state.value

    @property
    def active_operation_identity(self) -> str | None:
        """Expose only the sanitized identity of current bounded work."""

        with self._lock:
            return self._active_identity

    @property
    def last_result(self) -> DiscoveryOperationResult | None:
        with self._lock:
            return next(reversed(self._results.values()), None)

    def result_for(self, operation_identity: str) -> DiscoveryOperationResult | None:
        with self._lock:
            return self._results.get(operation_identity)

    def execute(self, request: DiscoveryOperationRequest) -> DiscoveryOperationResult:
        if type(request) is not DiscoveryOperationRequest:
            raise ValueError("DISCOVERY_OPERATION_REQUEST_INVALID")
        with self._lock:
            completed = self._results.get(request.operation_identity)
            if completed is not None:
                return completed
            if self._active_identity is not None:
                return self._conflict(request)
            self._active_identity = request.operation_identity

        lease: ReadOnlyProviderLease | None = None
        stage = DiscoveryOperationStage.CONTEXT_VERIFICATION
        try:
            lifecycle = self._runtime.lifecycle_state
            if lifecycle is not SharedProviderRuntimeLifecycle.ACTIVE:
                failure = (
                    DiscoveryOperationFailure.CONTEXT_EXPIRED
                    if lifecycle is SharedProviderRuntimeLifecycle.EXPIRED
                    else DiscoveryOperationFailure.CONTEXT_UNAVAILABLE
                )
                return self._finish(request, stage=stage, failure=failure)
            stage = DiscoveryOperationStage.LEASE_ACQUISITION
            lease = self._acquire_lease()
            if not lease.active:
                return self._finish(
                    request,
                    stage=stage,
                    failure=DiscoveryOperationFailure.LEASE_UNAVAILABLE,
                )
            stage = DiscoveryOperationStage.UNIVERSE_RESOLUTION
            self._universe.require_current(request.observation_boundary)
            stage = DiscoveryOperationStage.RECONCILIATION_RESOLUTION
            if (
                self._reconciliation.universe_identity
                != self._universe.publication_identity
                or self._reconciliation.universe_version
                != self._universe.publication_version
                or self._reconciliation.universe_integrity_identity
                != self._universe.integrity_identity
            ):
                return self._finish(
                    request,
                    stage=stage,
                    failure=DiscoveryOperationFailure.PUBLICATION_STALE,
                )
            stage = DiscoveryOperationStage.OBSERVATION_BOUNDARY
            boundary = self._boundary(request.observation_boundary)
            stage = DiscoveryOperationStage.FACTUAL_SOURCE_ACQUISITION
            source = self._source_factory(lease)
            service = IntradayNativeDiscoveryService(
                universe=self._universe,
                reconciliation=self._reconciliation,
                factual_source=source,
                store=self._store,
            )
            stage = DiscoveryOperationStage.DISCOVERY_RUN_CONSTRUCTION
            execution = service.execute(boundary)
            stage = DiscoveryOperationStage.PERSISTENCE
            if self._store.load_run(run_identity=execution.run.run_identity) != execution.run:
                return self._finish(
                    request,
                    stage=stage,
                    failure=DiscoveryOperationFailure.PERSISTENCE_FAILURE,
                )
            stage = DiscoveryOperationStage.APPLICATION_SNAPSHOT
            self._application.accept_completed_execution(execution)
            return self._finish(
                request,
                stage=DiscoveryOperationStage.COMPLETE,
                execution=execution,
                historical_request_count=source.historical_request_count,
            )
        except ProviderRuntimeAccessError as error:
            failure = (
                DiscoveryOperationFailure.CONTEXT_EXPIRED
                if error.failure is ProviderRuntimeFailure.CONTEXT_EXPIRED
                else DiscoveryOperationFailure.LEASE_UNAVAILABLE
            )
            return self._finish(request, stage=stage, failure=failure)
        except IntradayUniverseError as error:
            failure = (
                DiscoveryOperationFailure.PUBLICATION_STALE
                if error.failure is IntradayUniverseFailure.PUBLICATION_STALE
                else DiscoveryOperationFailure.OPERATION_UNAVAILABLE
            )
            return self._finish(request, stage=stage, failure=failure)
        except DiscoveryError as error:
            return self._finish(
                request,
                stage=stage,
                failure=DiscoveryOperationFailure(error.failure.value),
            )
        except Exception:
            failure = {
                DiscoveryOperationStage.OBSERVATION_BOUNDARY:
                    DiscoveryOperationFailure.MARKET_SESSION_UNAVAILABLE,
                DiscoveryOperationStage.FACTUAL_SOURCE_ACQUISITION:
                    DiscoveryOperationFailure.PROVIDER_ACQUISITION_FAILURE,
                DiscoveryOperationStage.DISCOVERY_RUN_CONSTRUCTION:
                    DiscoveryOperationFailure.RUN_INTEGRITY_FAILURE,
                DiscoveryOperationStage.PERSISTENCE:
                    DiscoveryOperationFailure.PERSISTENCE_FAILURE,
                DiscoveryOperationStage.APPLICATION_SNAPSHOT:
                    DiscoveryOperationFailure.SNAPSHOT_UPDATE_FAILURE,
            }.get(stage, DiscoveryOperationFailure.OPERATION_UNAVAILABLE)
            return self._finish(request, stage=stage, failure=failure)
        finally:
            if lease is not None:
                lease.release()
            with self._lock:
                if self._active_identity == request.operation_identity:
                    self._active_identity = None

    def _boundary(self, observed_at: datetime) -> DiscoveryRunBoundary:
        session_identity, boundary_identity = governed_market_session_identities(
            calendar_publisher=self._calendar,
            reconciliation=self._reconciliation,
            observed_at=observed_at,
        )
        return DiscoveryRunBoundary(
            observation_boundary=observed_at,
            market_session_identity=session_identity,
            market_session_boundary_identity=boundary_identity,
        )

    def _finish(
        self,
        request: DiscoveryOperationRequest,
        *,
        stage: DiscoveryOperationStage,
        failure: DiscoveryOperationFailure | None = None,
        execution=None,
        historical_request_count: int = 0,
    ) -> DiscoveryOperationResult:
        result = DiscoveryOperationResult(
            operation_identity=request.operation_identity,
            state=(
                DiscoveryOperationState.COMPLETE
                if failure is None
                else DiscoveryOperationState.FAILED
            ),
            context_state=self._runtime.lifecycle_state.value,
            stage=stage,
            observation_boundary=request.observation_boundary,
            universe_count=len(self._universe.members),
            pre_evaluable_count=sum(
                item.dimensions.machine_fact_consumability is Availability.AVAILABLE
                for item in self._reconciliation.members
            ),
            prerequisite_unavailable_count=sum(
                item.dimensions.machine_fact_consumability is Availability.UNAVAILABLE
                for item in self._reconciliation.members
            ),
            machine_fact_successes=(0 if execution is None else len(execution.bundles)),
            machine_fact_failures=(
                0 if execution is None else execution.run.accounting.factual_failures
            ),
            historical_request_count=historical_request_count,
            run_identity=None if execution is None else execution.run.run_identity,
            persistence_complete=execution is not None,
            snapshot_updated=execution is not None,
            failure=failure,
            completed_at=self._clock(),
        )
        with self._lock:
            self._results[request.operation_identity] = result
        if failure is not None:
            self._application.record_failure(failure.value)
        return result

    def _conflict(self, request: DiscoveryOperationRequest) -> DiscoveryOperationResult:
        pre_evaluable = sum(
            item.dimensions.machine_fact_consumability is Availability.AVAILABLE
            for item in self._reconciliation.members
        )
        return DiscoveryOperationResult(
            operation_identity=request.operation_identity,
            state=DiscoveryOperationState.CONFLICT,
            context_state=self._runtime.lifecycle_state.value,
            stage=DiscoveryOperationStage.CONTEXT_VERIFICATION,
            observation_boundary=request.observation_boundary,
            universe_count=len(self._universe.members),
            pre_evaluable_count=pre_evaluable,
            prerequisite_unavailable_count=(
                len(self._reconciliation.members) - pre_evaluable
            ),
            machine_fact_successes=0,
            machine_fact_failures=0,
            historical_request_count=0,
            run_identity=None,
            persistence_complete=False,
            snapshot_updated=False,
            failure=DiscoveryOperationFailure.OPERATION_CONFLICT,
            completed_at=self._clock(),
        )


def _identity(payload: object) -> str:
    encoded = json.dumps(
        payload,
        default=lambda value: value.isoformat() if isinstance(value, datetime) else str(value),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return "KRONOS-INTRADAY-DISCOVERY-OPERATION-" + sha256(encoded).hexdigest()


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


__all__ = [
    "DISCOVERY_OPERATION_SERVICE_IDENTITY",
    "DISCOVERY_OPERATION_SERVICE_VERSION",
    "DiscoveryOperationFailure",
    "DiscoveryOperationRequest",
    "DiscoveryOperationResult",
    "DiscoveryOperationStage",
    "DiscoveryOperationState",
    "IntradayDiscoveryOperationService",
    "create_discovery_operation_request",
]
