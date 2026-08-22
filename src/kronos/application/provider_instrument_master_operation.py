"""Governed one-shot composition for the DOMAIN-006 P1 commissioning run."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import re
from threading import RLock
from typing import Protocol

from kronos.application.intraday_provider_commissioning import (
    CommissioningProviderRecordReference,
    IntradayProviderCommissioningManifest,
    IntradayProviderCommissioningMember,
    create_intraday_provider_commissioning_manifest,
)
from kronos.intraday.universe import IntradayUniversePublication
from kronos.provider.contracts.instrument_master import (
    KITE_INSTRUMENT_MASTER_DATASET,
    KITE_INSTRUMENT_MASTER_OPERATION,
    ProviderInstrumentDiagnosticPhase,
    ProviderInstrumentMasterError,
    ProviderInstrumentMasterFailure,
    ProviderInstrumentSchemaDiagnostic,
)
from kronos.provider.instrument_master import (
    ProviderInstrumentMasterAcquisitionService,
    ProviderInstrumentSnapshot,
)
from kronos.provider.instrument_master_persistence import (
    ProviderInstrumentSnapshotStore,
)


P1_OPERATION_IDENTITY = re.compile(
    r"KRONOS-P1-OPERATION-[A-Z0-9][A-Z0-9-]{7,80}\Z"
)


class P1ContextAvailability(StrEnum):
    ACTIVE = "ACTIVE"
    CONTEXT_UNAVAILABLE = "CONTEXT_UNAVAILABLE"
    EXPIRED = "EXPIRED"
    OPERATION_UNAVAILABLE = "OPERATION_UNAVAILABLE"


class P1OperationalState(StrEnum):
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class P1OperationalStage(StrEnum):
    CONTEXT_VERIFICATION = "CONTEXT_VERIFICATION"
    LEASE_ACQUISITION = "LEASE_ACQUISITION"
    INSTRUMENT_MASTER_ACQUISITION = "INSTRUMENT_MASTER_ACQUISITION"
    SNAPSHOT_CONSTRUCTION = "SNAPSHOT_CONSTRUCTION"
    SNAPSHOT_VALIDATION = "SNAPSHOT_VALIDATION"
    SNAPSHOT_PERSISTENCE = "SNAPSHOT_PERSISTENCE"
    SNAPSHOT_RELOAD = "SNAPSHOT_RELOAD"
    COMMISSIONING_MANIFEST = "COMMISSIONING_MANIFEST"
    COMPLETE = "COMPLETE"


class P1OperationalFailure(StrEnum):
    CONTEXT_UNAVAILABLE = "CONTEXT_UNAVAILABLE"
    LEASE_ACQUISITION_FAILED = "LEASE_ACQUISITION_FAILED"
    OPERATION_UNAUTHORIZED = "OPERATION_UNAUTHORIZED"
    ACQUISITION_ALREADY_RUNNING = "ACQUISITION_ALREADY_RUNNING"
    PROVIDER_ACQUISITION_FAILED = "PROVIDER_ACQUISITION_FAILED"
    PROVIDER_DATASET_UNAVAILABLE = "PROVIDER_DATASET_UNAVAILABLE"
    SNAPSHOT_SCHEMA_INVALID = "SNAPSHOT_SCHEMA_INVALID"
    DUPLICATE_PROVIDER_RECORD_IDENTITY = "DUPLICATE_PROVIDER_RECORD_IDENTITY"
    SNAPSHOT_INTEGRITY_INVALID = "SNAPSHOT_INTEGRITY_INVALID"
    SNAPSHOT_CONFLICT = "SNAPSHOT_CONFLICT"
    PERSISTENCE_FAILED = "PERSISTENCE_FAILED"
    RELOAD_FAILED = "RELOAD_FAILED"
    COMMISSIONING_MANIFEST_FAILED = "COMMISSIONING_MANIFEST_FAILED"


@dataclass(frozen=True, slots=True)
class P1CandidateEvidence:
    provider_record_identity: str
    provider_symbol: str
    exchange: str
    segment: str
    provider_instrument_type: str
    expiry: str | None
    strike: str | None
    tick_size: str
    lot_size: int


@dataclass(frozen=True, slots=True)
class P1CommissioningMemberEvidence:
    sponsor_label: str
    market_family: str
    status: str
    candidates: tuple[P1CandidateEvidence, ...]


@dataclass(frozen=True, slots=True, repr=False)
class P1OperationalResult:
    operation_identity: str
    state: P1OperationalState
    context_availability: P1ContextAvailability
    stage: P1OperationalStage
    failure: P1OperationalFailure | None
    provider: str | None = None
    dataset_identity: str | None = None
    snapshot_identity: str | None = None
    record_count: int | None = None
    source_boundary: datetime | None = None
    acquired_at: datetime | None = None
    component_request_count: int | None = None
    exchange_counts: tuple[tuple[str, int], ...] = ()
    segment_counts: tuple[tuple[str, int], ...] = ()
    instrument_type_counts: tuple[tuple[str, int], ...] = ()
    snapshot_integrity_identity: str | None = None
    persistence_identity: str | None = None
    reload_verified: bool = False
    commissioning_manifest_identity: str | None = None
    commissioning_member_count: int | None = None
    commissioning_status_counts: tuple[tuple[str, int], ...] = ()
    commissioning_members: tuple[P1CommissioningMemberEvidence, ...] = ()
    diagnostic: ProviderInstrumentSchemaDiagnostic | None = None
    diagnostic_at: datetime | None = None

    def __repr__(self) -> str:
        return (
            "<P1OperationalResult "
            f"operation={self.operation_identity} state={self.state.value} redacted>"
        )


class _SharedRuntime(Protocol):
    @property
    def provider_identity(self) -> str: ...

    @property
    def lifecycle_state(self) -> object: ...

    @property
    def provider_instrument_master_operation_available(self) -> bool: ...

    def acquire_provider_instrument_master_records(
        self,
        *,
        operation_identity: str,
    ) -> object: ...


class ProviderInstrumentMasterOperationalComposition:
    """Coordinate exactly one acquisition per explicit operation identity."""

    __slots__ = (
        "_active_operation",
        "_clock",
        "_lock",
        "_results",
        "_runtime",
        "_store",
        "_universe",
    )

    def __init__(
        self,
        runtime: _SharedRuntime,
        *,
        store: ProviderInstrumentSnapshotStore,
        universe: IntradayUniversePublication,
        clock: Callable[[], datetime],
    ) -> None:
        if (
            not callable(clock)
            or type(store) is not ProviderInstrumentSnapshotStore
            or type(universe) is not IntradayUniversePublication
            or not callable(
                getattr(runtime, "acquire_provider_instrument_master_records", None)
            )
        ):
            raise ValueError("P1_OPERATIONAL_COMPOSITION_DEPENDENCY_INVALID")
        self._runtime = runtime
        self._store = store
        self._universe = universe
        self._clock = clock
        self._lock = RLock()
        self._active_operation: str | None = None
        self._results: dict[str, P1OperationalResult] = {}

    def context_availability(self) -> P1ContextAvailability:
        try:
            lifecycle = getattr(self._runtime.lifecycle_state, "value", "")
        except Exception:
            return P1ContextAvailability.CONTEXT_UNAVAILABLE
        if lifecycle == "ACTIVE":
            try:
                available = (
                    self._runtime.provider_instrument_master_operation_available
                )
            except Exception:
                available = False
            return P1ContextAvailability.ACTIVE if available is True else (
                P1ContextAvailability.OPERATION_UNAVAILABLE
            )
        if lifecycle == "EXPIRED":
            return P1ContextAvailability.EXPIRED
        return P1ContextAvailability.CONTEXT_UNAVAILABLE

    def result(self, operation_identity: str) -> P1OperationalResult | None:
        _require_operation_identity(operation_identity)
        with self._lock:
            return self._results.get(operation_identity)

    def run(self, *, operation_identity: str) -> P1OperationalResult:
        _require_operation_identity(operation_identity)
        with self._lock:
            previous = self._results.get(operation_identity)
            if previous is not None:
                return previous
            if self._active_operation is not None:
                result = _failure_result(
                    operation_identity,
                    context=self.context_availability(),
                    stage=P1OperationalStage.LEASE_ACQUISITION,
                    failure=P1OperationalFailure.ACQUISITION_ALREADY_RUNNING,
                )
                self._results[operation_identity] = result
                return result
            self._active_operation = operation_identity
        try:
            result = self._execute(operation_identity)
        except BaseException:
            with self._lock:
                self._active_operation = None
            raise
        with self._lock:
            self._results[operation_identity] = result
            self._active_operation = None
        return result

    def _execute(self, operation_identity: str) -> P1OperationalResult:
        context = self.context_availability()
        if context is not P1ContextAvailability.ACTIVE:
            failure = (
                P1OperationalFailure.LEASE_ACQUISITION_FAILED
                if context is P1ContextAvailability.OPERATION_UNAVAILABLE
                else P1OperationalFailure.CONTEXT_UNAVAILABLE
            )
            return _failure_result(
                operation_identity,
                context=context,
                stage=P1OperationalStage.CONTEXT_VERIFICATION,
                failure=failure,
            )
        stage = P1OperationalStage.LEASE_ACQUISITION
        try:
            service = ProviderInstrumentMasterAcquisitionService(
                self._runtime,
                clock=self._clock,
            )
            stage = P1OperationalStage.INSTRUMENT_MASTER_ACQUISITION
            source_boundary = self._clock()
            snapshot = service.acquire(
                source_boundary=source_boundary,
                authorized_operation_identity=KITE_INSTRUMENT_MASTER_OPERATION,
                provenance=(
                    "ADR-0014",
                    "ADR-009",
                    "KRONOS-PLATFORM-WO-P1",
                    operation_identity,
                ),
            )
            stage = P1OperationalStage.SNAPSHOT_PERSISTENCE
            self._store.retain(snapshot)
            stage = P1OperationalStage.SNAPSHOT_RELOAD
            reloaded = self._store.load(
                provider=snapshot.provider,
                dataset_identity=snapshot.dataset_identity,
                snapshot_identity=snapshot.snapshot_identity,
            )
            _require_reload_match(snapshot, reloaded)
            stage = P1OperationalStage.COMMISSIONING_MANIFEST
            manifest = create_intraday_provider_commissioning_manifest(
                snapshot=reloaded,
                universe=self._universe,
            )
            return _complete_result(operation_identity, reloaded, manifest)
        except ProviderInstrumentMasterError as error:
            diagnostic = error.diagnostic
            if diagnostic is not None:
                stage = {
                    ProviderInstrumentDiagnosticPhase.PROVIDER_NORMALIZATION: (
                        P1OperationalStage.INSTRUMENT_MASTER_ACQUISITION
                    ),
                    ProviderInstrumentDiagnosticPhase.SNAPSHOT_CONSTRUCTION: (
                        P1OperationalStage.SNAPSHOT_CONSTRUCTION
                    ),
                    ProviderInstrumentDiagnosticPhase.SNAPSHOT_VALIDATION: (
                        P1OperationalStage.SNAPSHOT_VALIDATION
                    ),
                }[diagnostic.phase]
            return _failure_result(
                operation_identity,
                context=context,
                stage=stage,
                failure=_provider_failure(error.failure, stage),
                diagnostic=diagnostic,
                diagnostic_at=(
                    _diagnostic_time(self._clock)
                    if diagnostic is not None
                    else None
                ),
            )
        except Exception:
            return _failure_result(
                operation_identity,
                context=context,
                stage=stage,
                failure=_untyped_failure(stage),
            )


def p1_operational_result_document(result: P1OperationalResult) -> dict[str, object]:
    """Return only the sanitized Browser-safe operational projection."""

    return {
        "operation_identity": result.operation_identity,
        "state": result.state.value,
        "context_availability": result.context_availability.value,
        "stage": result.stage.value,
        "failure": None if result.failure is None else result.failure.value,
        "provider": result.provider,
        "dataset_identity": result.dataset_identity,
        "snapshot_identity": result.snapshot_identity,
        "record_count": result.record_count,
        "source_boundary": _datetime_text(result.source_boundary),
        "acquired_at": _datetime_text(result.acquired_at),
        "component_request_count": result.component_request_count,
        "exchange_counts": [list(item) for item in result.exchange_counts],
        "segment_counts": [list(item) for item in result.segment_counts],
        "instrument_type_counts": [
            list(item) for item in result.instrument_type_counts
        ],
        "snapshot_integrity_identity": result.snapshot_integrity_identity,
        "persistence_identity": result.persistence_identity,
        "reload_verified": result.reload_verified,
        "commissioning_manifest_identity": result.commissioning_manifest_identity,
        "commissioning_member_count": result.commissioning_member_count,
        "commissioning_status_counts": [
            list(item) for item in result.commissioning_status_counts
        ],
        "commissioning_members": [
            {
                "sponsor_label": member.sponsor_label,
                "market_family": member.market_family,
                "status": member.status,
                "candidates": [
                    {
                        "provider_record_identity": candidate.provider_record_identity,
                        "provider_symbol": candidate.provider_symbol,
                        "exchange": candidate.exchange,
                        "segment": candidate.segment,
                        "provider_instrument_type": candidate.provider_instrument_type,
                        "expiry": candidate.expiry,
                        "strike": candidate.strike,
                        "tick_size": candidate.tick_size,
                        "lot_size": candidate.lot_size,
                    }
                    for candidate in member.candidates
                ],
            }
            for member in result.commissioning_members
        ],
        "diagnostic_phase": (
            None if result.diagnostic is None else result.diagnostic.phase.value
        ),
        "validation_rule": (
            None if result.diagnostic is None else result.diagnostic.rule.value
        ),
        "field_family": (
            None
            if result.diagnostic is None
            else result.diagnostic.field_family.value
        ),
        "value_classification": (
            None
            if result.diagnostic is None
            else result.diagnostic.value_classification.value
        ),
        "input_ordinal": (
            None if result.diagnostic is None else result.diagnostic.input_ordinal
        ),
        "record_locator": (
            None if result.diagnostic is None else result.diagnostic.record_locator
        ),
        "affected_count": (
            None if result.diagnostic is None else result.diagnostic.affected_count
        ),
        "diagnostic_at": _datetime_text(result.diagnostic_at),
    }


def _complete_result(
    operation_identity: str,
    snapshot: ProviderInstrumentSnapshot,
    manifest: IntradayProviderCommissioningManifest,
) -> P1OperationalResult:
    return P1OperationalResult(
        operation_identity=operation_identity,
        state=P1OperationalState.COMPLETE,
        context_availability=P1ContextAvailability.ACTIVE,
        stage=P1OperationalStage.COMPLETE,
        failure=None,
        provider=snapshot.provider,
        dataset_identity=snapshot.dataset_identity,
        snapshot_identity=snapshot.snapshot_identity,
        record_count=snapshot.record_count,
        source_boundary=snapshot.source_boundary,
        acquired_at=snapshot.acquired_at,
        component_request_count=snapshot.component_request_count,
        exchange_counts=snapshot.exchange_counts,
        segment_counts=snapshot.segment_counts,
        instrument_type_counts=snapshot.instrument_type_counts,
        snapshot_integrity_identity=snapshot.integrity_identity,
        persistence_identity=snapshot.snapshot_identity,
        reload_verified=True,
        commissioning_manifest_identity=manifest.manifest_identity,
        commissioning_member_count=len(manifest.members),
        commissioning_status_counts=_status_counts(manifest.members),
        commissioning_members=tuple(_member_evidence(item) for item in manifest.members),
    )


def _failure_result(
    operation_identity: str,
    *,
    context: P1ContextAvailability,
    stage: P1OperationalStage,
    failure: P1OperationalFailure,
    diagnostic: ProviderInstrumentSchemaDiagnostic | None = None,
    diagnostic_at: datetime | None = None,
) -> P1OperationalResult:
    return P1OperationalResult(
        operation_identity=operation_identity,
        state=P1OperationalState.FAILED,
        context_availability=context,
        stage=stage,
        failure=failure,
        diagnostic=diagnostic,
        diagnostic_at=diagnostic_at,
    )


def _member_evidence(
    member: IntradayProviderCommissioningMember,
) -> P1CommissioningMemberEvidence:
    return P1CommissioningMemberEvidence(
        sponsor_label=member.sponsor_label,
        market_family=member.market_family.value,
        status=member.status.value,
        candidates=tuple(_candidate_evidence(item) for item in member.candidate_records),
    )


def _candidate_evidence(
    candidate: CommissioningProviderRecordReference,
) -> P1CandidateEvidence:
    return P1CandidateEvidence(
        provider_record_identity=candidate.provider_record_identity,
        provider_symbol=candidate.provider_symbol,
        exchange=candidate.exchange,
        segment=candidate.segment,
        provider_instrument_type=candidate.provider_instrument_type,
        expiry=None if candidate.expiry is None else candidate.expiry.isoformat(),
        strike=None if candidate.strike is None else format(candidate.strike, "f"),
        tick_size=format(candidate.tick_size, "f"),
        lot_size=candidate.lot_size,
    )


def _status_counts(
    members: tuple[IntradayProviderCommissioningMember, ...],
) -> tuple[tuple[str, int], ...]:
    counts: dict[str, int] = {}
    for member in members:
        counts[member.status.value] = counts.get(member.status.value, 0) + 1
    return tuple(sorted(counts.items()))


def _provider_failure(
    failure: ProviderInstrumentMasterFailure,
    stage: P1OperationalStage,
) -> P1OperationalFailure:
    direct = {
        ProviderInstrumentMasterFailure.CONTEXT_UNAVAILABLE: P1OperationalFailure.CONTEXT_UNAVAILABLE,
        ProviderInstrumentMasterFailure.OPERATION_UNAUTHORIZED: P1OperationalFailure.OPERATION_UNAUTHORIZED,
        ProviderInstrumentMasterFailure.PROVIDER_DATASET_UNAVAILABLE: P1OperationalFailure.PROVIDER_DATASET_UNAVAILABLE,
        ProviderInstrumentMasterFailure.PROVIDER_ACQUISITION_FAILED: P1OperationalFailure.PROVIDER_ACQUISITION_FAILED,
        ProviderInstrumentMasterFailure.SNAPSHOT_SCHEMA_INVALID: P1OperationalFailure.SNAPSHOT_SCHEMA_INVALID,
        ProviderInstrumentMasterFailure.DUPLICATE_PROVIDER_RECORD_IDENTITY: P1OperationalFailure.DUPLICATE_PROVIDER_RECORD_IDENTITY,
        ProviderInstrumentMasterFailure.SNAPSHOT_INTEGRITY_INVALID: P1OperationalFailure.SNAPSHOT_INTEGRITY_INVALID,
        ProviderInstrumentMasterFailure.SNAPSHOT_CONFLICT: P1OperationalFailure.SNAPSHOT_CONFLICT,
        ProviderInstrumentMasterFailure.PERSISTENCE_FAILED: P1OperationalFailure.PERSISTENCE_FAILED,
    }
    if stage is P1OperationalStage.SNAPSHOT_RELOAD and failure is ProviderInstrumentMasterFailure.PERSISTENCE_FAILED:
        return P1OperationalFailure.RELOAD_FAILED
    return direct.get(failure, _untyped_failure(stage))


def _untyped_failure(stage: P1OperationalStage) -> P1OperationalFailure:
    if stage is P1OperationalStage.LEASE_ACQUISITION:
        return P1OperationalFailure.LEASE_ACQUISITION_FAILED
    if stage is P1OperationalStage.INSTRUMENT_MASTER_ACQUISITION:
        return P1OperationalFailure.PROVIDER_ACQUISITION_FAILED
    if stage is P1OperationalStage.SNAPSHOT_PERSISTENCE:
        return P1OperationalFailure.PERSISTENCE_FAILED
    if stage is P1OperationalStage.SNAPSHOT_RELOAD:
        return P1OperationalFailure.RELOAD_FAILED
    if stage is P1OperationalStage.COMMISSIONING_MANIFEST:
        return P1OperationalFailure.COMMISSIONING_MANIFEST_FAILED
    return P1OperationalFailure.SNAPSHOT_SCHEMA_INVALID


def _require_reload_match(
    expected: ProviderInstrumentSnapshot,
    observed: ProviderInstrumentSnapshot,
) -> None:
    if (
        observed != expected
        or observed.snapshot_identity != expected.snapshot_identity
        or observed.integrity_identity != expected.integrity_identity
        or observed.record_count != expected.record_count
        or tuple(item.provider_record_identity for item in observed.records)
        != tuple(item.provider_record_identity for item in expected.records)
    ):
        raise ProviderInstrumentMasterError(
            ProviderInstrumentMasterFailure.SNAPSHOT_INTEGRITY_INVALID
        )


def _require_operation_identity(value: object) -> None:
    if not isinstance(value, str) or P1_OPERATION_IDENTITY.fullmatch(value) is None:
        raise ValueError("P1_OPERATION_IDENTITY_INVALID")


def _datetime_text(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _diagnostic_time(clock: Callable[[], datetime]) -> datetime | None:
    try:
        value = clock()
    except Exception:
        return None
    return (
        value
        if isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
        else None
    )


__all__ = [
    "P1ContextAvailability",
    "P1OperationalFailure",
    "P1OperationalResult",
    "P1OperationalStage",
    "P1OperationalState",
    "ProviderInstrumentMasterOperationalComposition",
    "p1_operational_result_document",
]
