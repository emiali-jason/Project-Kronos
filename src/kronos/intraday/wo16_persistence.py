"""Immutable product-local persistence for Intraday WO-16 Slice 3.

The store retains the exact Slice-2 request and decision graph.  It performs
no decision evaluation, upstream recalculation, Provider access, runtime
composition, Browser work, position creation, or broker operation.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from importlib import import_module
import json
import os
from pathlib import Path
from threading import RLock
from typing import TYPE_CHECKING, Mapping
from uuid import uuid4
from zoneinfo import ZoneInfo

from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo16 import (
    WO16_CONTRACT_VERSION,
    WO16_CURRENT_DECISION_IDENTITY,
    WO16_INVALID_OPERATION_IDENTITY,
    Wo16ContractError,
    Wo16LifecycleAdmissionRecord,
    Wo16PolicyBinding,
    Wo16SponsorDecisionRecord,
    Wo16SponsorDecisionSnapshot,
    Wo16SuccessorLineage,
    canonical_document_bytes,
)

if TYPE_CHECKING:
    from kronos.application.intraday_wo16 import Wo16OperationRequest


DEFAULT_WO16_ROOT = (
    Path.home()
    / "Library"
    / "Application Support"
    / "KRONOS"
    / "evidence"
    / "intraday-v1"
    / "wo16-sponsor-decision-lifecycle-admission-v1"
)

WO16_OPERATION_PROVENANCE_IDENTITY = (
    "KRONOS-INTRADAY-WO16-OPERATION-PROVENANCE-V1"
)
class Wo16PersistenceError(Wo16ContractError):
    """Sanitized immutable-store or restoration failure."""


class Wo16OperationStage(StrEnum):
    REQUEST_VALIDATION = "REQUEST_VALIDATION"
    REPLAY_VALIDATION = "REPLAY_VALIDATION"
    UPSTREAM_BINDING = "UPSTREAM_BINDING"
    SUCCESSOR_BINDING = "SUCCESSOR_BINDING"
    PERSISTENCE = "PERSISTENCE"
    POINTER_PUBLICATION = "POINTER_PUBLICATION"
    RESTORATION = "RESTORATION"


class Wo16PersistedOperationOutcome(StrEnum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Wo16RestorationState(StrEnum):
    NOT_YET_RUN = "NOT_YET_RUN"
    LOADED = "LOADED"
    CORRUPT = "CORRUPT"


@dataclass(frozen=True, slots=True)
class Wo16OperationProvenance:
    operation_identity: str
    operation_integrity: str
    request_identity: str
    request_integrity: str
    stage: Wo16OperationStage
    outcome: Wo16PersistedOperationOutcome
    started_at: datetime
    completed_at: datetime | None
    failed_at: datetime | None
    snapshot_identity: str | None
    snapshot_integrity: str | None
    decision_identity: str | None
    decision_integrity: str | None
    admission_identity: str | None
    admission_integrity: str | None
    successor_lineage_identity: str | None
    successor_lineage_integrity: str | None
    failure_reason: str | None
    provenance: tuple[str, ...]
    schema_identity: str = WO16_OPERATION_PROVENANCE_IDENTITY
    schema_version: str = WO16_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "operation_identity", "operation_integrity")
        completed = self.outcome is Wo16PersistedOperationOutcome.COMPLETED
        failed = self.outcome is Wo16PersistedOperationOutcome.FAILED
        completed_pairs = (
            self.snapshot_identity,
            self.snapshot_integrity,
            self.decision_identity,
            self.decision_integrity,
            self.admission_identity,
            self.admission_integrity,
        )
        successor_pair = (
            self.successor_lineage_identity,
            self.successor_lineage_integrity,
        )
        if (
            not _texts(
                (
                    self.request_identity,
                    self.request_integrity,
                    *self.provenance,
                )
            )
            or type(self.stage) is not Wo16OperationStage
            or type(self.outcome) is not Wo16PersistedOperationOutcome
            or not _aware(self.started_at)
            or completed != (self.completed_at is not None)
            or failed != (self.failed_at is not None)
            or failed != (self.failure_reason is not None)
            or self.completed_at is not None
            and not _aware(self.completed_at)
            or self.failed_at is not None
            and not _aware(self.failed_at)
            or completed != _texts(completed_pairs)
            or failed and any(value is not None for value in completed_pairs)
            or not (_all_none(successor_pair) or _texts(successor_pair))
            or self.failure_reason is not None
            and not _code(self.failure_reason)
            or self.schema_identity != WO16_OPERATION_PROVENANCE_IDENTITY
            or self.schema_version != WO16_CONTRACT_VERSION
            or self.operation_identity
            != _identity("INTRADAY-WO16-OPERATION-", values)
            or self.operation_integrity
            != _identity("INTEGRITY-INTRADAY-WO16-OPERATION-", values)
        ):
            raise Wo16PersistenceError("WO16_OPERATION_PROVENANCE_INVALID")


@dataclass(frozen=True, slots=True)
class Wo16InvalidOperationProvenance:
    invalid_identity: str
    invalid_integrity: str
    request_identity: str
    request_integrity: str
    stage: Wo16OperationStage
    reason: str
    canonical_subject_identity: str
    source_identities: tuple[str, ...]
    failed_at: datetime
    schema_identity: str = WO16_INVALID_OPERATION_IDENTITY
    schema_version: str = WO16_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "invalid_identity", "invalid_integrity")
        if (
            not _texts(
                (
                    self.request_identity,
                    self.request_integrity,
                    self.canonical_subject_identity,
                    *self.source_identities,
                )
            )
            or type(self.stage) is not Wo16OperationStage
            or not _code(self.reason)
            or not _aware(self.failed_at)
            or self.schema_identity
            != WO16_INVALID_OPERATION_IDENTITY
            or self.schema_version != WO16_CONTRACT_VERSION
            or self.invalid_identity
            != _identity("INTRADAY-WO16-INVALID-", values)
            or self.invalid_integrity
            != _identity("INTEGRITY-INTRADAY-WO16-INVALID-", values)
        ):
            raise Wo16PersistenceError("WO16_INVALID_OPERATION_INVALID")


@dataclass(frozen=True, slots=True)
class CurrentWo16Pointer:
    pointer_identity: str
    pointer_integrity: str
    scope_identity: str
    canonical_subject_identity: str
    market_family: IntradayMarketFamily
    instrument_identity: str
    actual_contract_identity: str | None
    contract_expiry: date | None
    roll_lineage_identity: str | None
    trading_date: date
    session_identity: str
    calendar_identity: str
    calendar_version: str
    wo15_session_binding_identity: str
    wo15_session_binding_integrity: str
    domain_008_session_binding_identity: str
    domain_008_session_binding_integrity: str
    wo13_trade_plan_identity: str
    wo13_trade_plan_integrity: str
    wo14_observation_identity: str
    wo14_observation_integrity: str
    wo15_handoff_identity: str
    wo15_handoff_integrity: str
    request_identity: str
    request_integrity: str
    snapshot_identity: str
    snapshot_integrity: str
    decision_identity: str
    decision_integrity: str
    admission_identity: str
    admission_integrity: str
    operation_identity: str
    operation_integrity: str
    operation_outcome: Wo16PersistedOperationOutcome
    predecessor_decision_identity: str | None
    successor_lineage_identity: str | None
    successor_lineage_integrity: str | None
    policy: Wo16PolicyBinding
    published_at: datetime
    schema_identity: str = WO16_CURRENT_DECISION_IDENTITY
    schema_version: str = WO16_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "pointer_identity", "pointer_integrity")
        mcx = self.market_family is IntradayMarketFamily.MCX
        mcx_values = (
            self.actual_contract_identity,
            self.contract_expiry,
            self.roll_lineage_identity,
        )
        successor_values = (
            self.predecessor_decision_identity,
            self.successor_lineage_identity,
            self.successor_lineage_integrity,
        )
        expected_scope = _scope_identity(
            self.canonical_subject_identity,
            self.instrument_identity,
            self.actual_contract_identity,
            self.session_identity,
        )
        required = (
            self.scope_identity,
            self.canonical_subject_identity,
            self.instrument_identity,
            self.session_identity,
            self.calendar_identity,
            self.calendar_version,
            self.wo15_session_binding_identity,
            self.wo15_session_binding_integrity,
            self.domain_008_session_binding_identity,
            self.domain_008_session_binding_integrity,
            self.wo13_trade_plan_identity,
            self.wo13_trade_plan_integrity,
            self.wo14_observation_identity,
            self.wo14_observation_integrity,
            self.wo15_handoff_identity,
            self.wo15_handoff_integrity,
            self.request_identity,
            self.request_integrity,
            self.snapshot_identity,
            self.snapshot_integrity,
            self.decision_identity,
            self.decision_integrity,
            self.admission_identity,
            self.admission_integrity,
            self.operation_identity,
            self.operation_integrity,
        )
        if (
            not _texts(required)
            or type(self.market_family) is not IntradayMarketFamily
            or type(self.trading_date) is not date
            or mcx != all(value is not None for value in mcx_values)
            or not mcx and any(value is not None for value in mcx_values)
            or not (_all_none(successor_values) or _texts(successor_values))
            or self.operation_outcome
            is not Wo16PersistedOperationOutcome.COMPLETED
            or type(self.policy) is not Wo16PolicyBinding
            or not _aware(self.published_at)
            or self.scope_identity != expected_scope
            or self.schema_identity != WO16_CURRENT_DECISION_IDENTITY
            or self.schema_version != WO16_CONTRACT_VERSION
            or self.pointer_identity
            != _identity("CURRENT-INTRADAY-WO16-", values)
            or self.pointer_integrity
            != _identity("INTEGRITY-CURRENT-INTRADAY-WO16-", values)
        ):
            raise Wo16PersistenceError("WO16_CURRENT_POINTER_INVALID")


@dataclass(frozen=True, slots=True)
class RestoredWo16State:
    pointer: CurrentWo16Pointer
    request: Wo16OperationRequest
    snapshot: Wo16SponsorDecisionSnapshot
    decision: Wo16SponsorDecisionRecord
    admission: Wo16LifecycleAdmissionRecord
    operation: Wo16OperationProvenance
    successor: Wo16SuccessorLineage | None
    latest_failure: Wo16InvalidOperationProvenance | None
    history: tuple[Wo16SponsorDecisionRecord, ...]


def create_wo16_operation_provenance(
    *,
    request: Wo16OperationRequest,
    stage: Wo16OperationStage,
    outcome: Wo16PersistedOperationOutcome,
    started_at: datetime,
    completed_at: datetime | None = None,
    failed_at: datetime | None = None,
    snapshot: Wo16SponsorDecisionSnapshot | None = None,
    decision: Wo16SponsorDecisionRecord | None = None,
    admission: Wo16LifecycleAdmissionRecord | None = None,
    successor: Wo16SuccessorLineage | None = None,
    failure_reason: str | None = None,
    provenance: tuple[str, ...] = ("ADR-0026", "WO-16-SLICE-3"),
) -> Wo16OperationProvenance:
    values = {
        "request_identity": request.request_identity,
        "request_integrity": request.request_integrity,
        "stage": stage,
        "outcome": outcome,
        "started_at": started_at,
        "completed_at": completed_at,
        "failed_at": failed_at,
        "snapshot_identity": (
            None if snapshot is None else snapshot.snapshot_identity
        ),
        "snapshot_integrity": (
            None if snapshot is None else snapshot.snapshot_integrity
        ),
        "decision_identity": (
            None if decision is None else decision.decision_identity
        ),
        "decision_integrity": (
            None if decision is None else decision.decision_integrity
        ),
        "admission_identity": (
            None if admission is None else admission.admission_identity
        ),
        "admission_integrity": (
            None if admission is None else admission.admission_integrity
        ),
        "successor_lineage_identity": (
            None if successor is None else successor.lineage_identity
        ),
        "successor_lineage_integrity": (
            None if successor is None else successor.lineage_integrity
        ),
        "failure_reason": failure_reason,
        "provenance": provenance,
        "schema_identity": WO16_OPERATION_PROVENANCE_IDENTITY,
        "schema_version": WO16_CONTRACT_VERSION,
    }
    return Wo16OperationProvenance(
        operation_identity=_identity("INTRADAY-WO16-OPERATION-", values),
        operation_integrity=_identity(
            "INTEGRITY-INTRADAY-WO16-OPERATION-", values
        ),
        **values,
    )


def create_wo16_invalid_operation(
    *,
    request: Wo16OperationRequest,
    stage: Wo16OperationStage,
    reason: str,
    failed_at: datetime,
) -> Wo16InvalidOperationProvenance:
    values = {
        "request_identity": request.request_identity,
        "request_integrity": request.request_integrity,
        "stage": stage,
        "reason": reason,
        "canonical_subject_identity": (
            request.wo13_trade_plan.canonical_subject_identity
        ),
        "source_identities": (
            request.wo13_trade_plan.trade_plan_identity,
            request.wo14_observation.observation_identity,
            request.wo15_timing_handoff.handoff_identity,
            request.wo15_session.session_identity,
        ),
        "failed_at": failed_at,
        "schema_identity": WO16_INVALID_OPERATION_IDENTITY,
        "schema_version": WO16_CONTRACT_VERSION,
    }
    return Wo16InvalidOperationProvenance(
        invalid_identity=_identity("INTRADAY-WO16-INVALID-", values),
        invalid_integrity=_identity(
            "INTEGRITY-INTRADAY-WO16-INVALID-", values
        ),
        **values,
    )


def create_current_wo16_pointer(
    *,
    request: Wo16OperationRequest,
    snapshot: Wo16SponsorDecisionSnapshot,
    decision: Wo16SponsorDecisionRecord,
    admission: Wo16LifecycleAdmissionRecord,
    operation: Wo16OperationProvenance,
    successor: Wo16SuccessorLineage | None,
    published_at: datetime,
) -> CurrentWo16Pointer:
    lineage = snapshot.upstream_lineage
    trade = lineage.trade_plan
    risk = lineage.risk_observation
    timing = lineage.timing_handoff
    session = lineage.session
    values = {
        "scope_identity": _scope_identity(
            trade.canonical_subject_identity,
            trade.instrument_identity,
            trade.actual_contract_identity,
            session.session_identity,
        ),
        "canonical_subject_identity": trade.canonical_subject_identity,
        "market_family": trade.market_family,
        "instrument_identity": trade.instrument_identity,
        "actual_contract_identity": trade.actual_contract_identity,
        "contract_expiry": trade.contract_expiry,
        "roll_lineage_identity": trade.roll_lineage_identity,
        "trading_date": session.trading_date,
        "session_identity": session.session_identity,
        "calendar_identity": session.calendar_identity,
        "calendar_version": session.calendar_version,
        "wo15_session_binding_identity": session.wo15_session_binding_identity,
        "wo15_session_binding_integrity": session.wo15_session_binding_integrity,
        "domain_008_session_binding_identity": session.binding_identity,
        "domain_008_session_binding_integrity": session.binding_integrity,
        "wo13_trade_plan_identity": trade.trade_plan_identity,
        "wo13_trade_plan_integrity": trade.trade_plan_integrity,
        "wo14_observation_identity": risk.observation_identity,
        "wo14_observation_integrity": risk.observation_integrity,
        "wo15_handoff_identity": timing.handoff_identity,
        "wo15_handoff_integrity": timing.handoff_integrity,
        "request_identity": request.request_identity,
        "request_integrity": request.request_integrity,
        "snapshot_identity": snapshot.snapshot_identity,
        "snapshot_integrity": snapshot.snapshot_integrity,
        "decision_identity": decision.decision_identity,
        "decision_integrity": decision.decision_integrity,
        "admission_identity": admission.admission_identity,
        "admission_integrity": admission.admission_integrity,
        "operation_identity": operation.operation_identity,
        "operation_integrity": operation.operation_integrity,
        "operation_outcome": operation.outcome,
        "predecessor_decision_identity": decision.predecessor_decision_identity,
        "successor_lineage_identity": (
            None if successor is None else successor.lineage_identity
        ),
        "successor_lineage_integrity": (
            None if successor is None else successor.lineage_integrity
        ),
        "policy": snapshot.policy,
        "published_at": published_at,
        "schema_identity": WO16_CURRENT_DECISION_IDENTITY,
        "schema_version": WO16_CONTRACT_VERSION,
    }
    return CurrentWo16Pointer(
        pointer_identity=_identity("CURRENT-INTRADAY-WO16-", values),
        pointer_integrity=_identity(
            "INTEGRITY-CURRENT-INTRADAY-WO16-", values
        ),
        **values,
    )


class Wo16Store:
    """Append-only WO-16 graph store with separate atomic aliases."""

    _FAMILIES = frozenset(
        {
            "requests",
            "snapshots",
            "decisions",
            "admissions",
            "operations",
            "invalid",
            "supersessions",
            "current-snapshots",
        }
    )

    def __init__(self, root: Path = DEFAULT_WO16_ROOT) -> None:
        if (
            not isinstance(root, Path)
            or not root.is_absolute()
            or root == Path("/")
        ):
            raise ValueError("WO16_STORE_ROOT_INVALID")
        self._root = root
        self._lock = RLock()

    @property
    def root(self) -> Path:
        return self._root

    def retain_request(self, value: Wo16OperationRequest) -> Path:
        from kronos.application.intraday_wo16 import Wo16OperationRequest

        if type(value) is not Wo16OperationRequest:
            raise Wo16PersistenceError("WO16_REQUEST_INVALID")
        return self._retain("requests", value.request_identity, value)

    def retain_snapshot(self, value: Wo16SponsorDecisionSnapshot) -> Path:
        return self._retain("snapshots", value.snapshot_identity, value)

    def retain_decision(self, value: Wo16SponsorDecisionRecord) -> Path:
        return self._retain("decisions", value.decision_identity, value)

    def retain_admission(self, value: Wo16LifecycleAdmissionRecord) -> Path:
        return self._retain("admissions", value.admission_identity, value)

    def retain_operation(self, value: Wo16OperationProvenance) -> Path:
        return self._retain("operations", value.operation_identity, value)

    def retain_invalid(self, value: Wo16InvalidOperationProvenance) -> Path:
        return self._retain("invalid", value.invalid_identity, value)

    def retain_successor(self, value: Wo16SuccessorLineage) -> Path:
        return self._retain("supersessions", value.lineage_identity, value)

    def retain_pointer_snapshot(self, value: CurrentWo16Pointer) -> Path:
        return self._retain("current-snapshots", value.pointer_identity, value)

    def load_request(self, identity: str) -> Wo16OperationRequest:
        from kronos.application.intraday_wo16 import Wo16OperationRequest

        return self._load(
            "requests", identity, Wo16OperationRequest, "request_identity"
        )

    def load_snapshot(self, identity: str) -> Wo16SponsorDecisionSnapshot:
        return self._load(
            "snapshots",
            identity,
            Wo16SponsorDecisionSnapshot,
            "snapshot_identity",
        )

    def load_decision(self, identity: str) -> Wo16SponsorDecisionRecord:
        return self._load(
            "decisions", identity, Wo16SponsorDecisionRecord, "decision_identity"
        )

    def load_admission(self, identity: str) -> Wo16LifecycleAdmissionRecord:
        return self._load(
            "admissions",
            identity,
            Wo16LifecycleAdmissionRecord,
            "admission_identity",
        )

    def load_operation(self, identity: str) -> Wo16OperationProvenance:
        return self._load(
            "operations", identity, Wo16OperationProvenance, "operation_identity"
        )

    def load_invalid(self, identity: str) -> Wo16InvalidOperationProvenance:
        return self._load(
            "invalid",
            identity,
            Wo16InvalidOperationProvenance,
            "invalid_identity",
        )

    def load_successor(self, identity: str) -> Wo16SuccessorLineage:
        return self._load(
            "supersessions", identity, Wo16SuccessorLineage, "lineage_identity"
        )

    def load_pointer_snapshot(self, identity: str) -> CurrentWo16Pointer:
        return self._load(
            "current-snapshots", identity, CurrentWo16Pointer, "pointer_identity"
        )

    def publish_current(self, value: CurrentWo16Pointer) -> Path:
        if type(value) is not CurrentWo16Pointer:
            raise Wo16PersistenceError("WO16_CURRENT_POINTER_INVALID")
        path = self._current_path(value.canonical_subject_identity)
        with self._lock:
            self.retain_pointer_snapshot(value)
            restored = self.restore_pointer(value)
            if restored.pointer != value:
                raise Wo16PersistenceError("WO16_PRE_PUBLICATION_RELOAD_INVALID")
            previous = _read(path) if path.exists() else None
            try:
                _replace_atomic(path, _artifact_bytes(value))
                if self.load_current(value.canonical_subject_identity) != value:
                    raise Wo16PersistenceError(
                        "WO16_CURRENT_ALIAS_PUBLICATION_INVALID"
                    )
            except Exception:
                if previous is None:
                    path.unlink(missing_ok=True)
                else:
                    _replace_atomic(path, previous)
                raise
        return path

    def publish_latest_failure(
        self, value: Wo16InvalidOperationProvenance
    ) -> Path:
        if type(value) is not Wo16InvalidOperationProvenance:
            raise Wo16PersistenceError("WO16_INVALID_OPERATION_INVALID")
        path = self._failure_path(value.canonical_subject_identity)
        with self._lock:
            self.retain_invalid(value)
            _replace_atomic(path, _artifact_bytes(value))
        return path

    def load_current(
        self, canonical_subject_identity: str
    ) -> CurrentWo16Pointer | None:
        path = self._current_path(canonical_subject_identity)
        if not path.exists():
            return None
        value = _artifact_from_bytes(_read(path))
        if (
            type(value) is not CurrentWo16Pointer
            or value.canonical_subject_identity != canonical_subject_identity
        ):
            raise Wo16PersistenceError("WO16_CURRENT_POINTER_INTEGRITY_INVALID")
        return value

    def load_latest_failure(
        self, canonical_subject_identity: str
    ) -> Wo16InvalidOperationProvenance | None:
        path = self._failure_path(canonical_subject_identity)
        if not path.exists():
            return None
        value = _artifact_from_bytes(_read(path))
        if (
            type(value) is not Wo16InvalidOperationProvenance
            or value.canonical_subject_identity != canonical_subject_identity
        ):
            raise Wo16PersistenceError("WO16_FAILURE_POINTER_INTEGRITY_INVALID")
        return value

    def current_subjects(self) -> tuple[str, ...]:
        directory = self._root / "current"
        if not directory.exists():
            return ()
        subjects: set[str] = set()
        for path in sorted(directory.glob("CURRENT-*.json")):
            value = _artifact_from_bytes(_read(path))
            if type(value) is not CurrentWo16Pointer:
                raise Wo16PersistenceError(
                    "WO16_CURRENT_POINTER_INTEGRITY_INVALID"
                )
            if path != self._current_path(value.canonical_subject_identity):
                raise Wo16PersistenceError("WO16_CURRENT_ALIAS_INVALID")
            subjects.add(value.canonical_subject_identity)
        return tuple(sorted(subjects))

    def failure_subjects(self) -> tuple[str, ...]:
        directory = self._root / "current"
        if not directory.exists():
            return ()
        subjects: set[str] = set()
        for path in sorted(directory.glob("LATEST-FAILURE-*.json")):
            value = _artifact_from_bytes(_read(path))
            if type(value) is not Wo16InvalidOperationProvenance:
                raise Wo16PersistenceError(
                    "WO16_FAILURE_POINTER_INTEGRITY_INVALID"
                )
            if path != self._failure_path(value.canonical_subject_identity):
                raise Wo16PersistenceError("WO16_FAILURE_ALIAS_INVALID")
            subjects.add(value.canonical_subject_identity)
        return tuple(sorted(subjects))

    def restore_current(
        self, canonical_subject_identity: str
    ) -> RestoredWo16State | None:
        pointer = self.load_current(canonical_subject_identity)
        if pointer is None:
            return None
        return self.restore_pointer(pointer)

    def restore_pointer(self, pointer: CurrentWo16Pointer) -> RestoredWo16State:
        if type(pointer) is not CurrentWo16Pointer:
            raise Wo16PersistenceError("WO16_CURRENT_POINTER_INVALID")
        request = self.load_request(pointer.request_identity)
        snapshot = self.load_snapshot(pointer.snapshot_identity)
        decision = self.load_decision(pointer.decision_identity)
        admission = self.load_admission(pointer.admission_identity)
        operation = self.load_operation(pointer.operation_identity)
        successor = (
            None
            if pointer.successor_lineage_identity is None
            else self.load_successor(pointer.successor_lineage_identity)
        )
        latest_failure = self.load_latest_failure(
            pointer.canonical_subject_identity
        )
        history = self._history(pointer.canonical_subject_identity)
        lineage = snapshot.upstream_lineage
        trade = lineage.trade_plan
        risk = lineage.risk_observation
        timing = lineage.timing_handoff
        session = lineage.session
        if (
            request.request_integrity != pointer.request_integrity
            or request.choice is not decision.choice
            or request.snapshot_timestamp != snapshot.snapshot_timestamp
            or request.decision_timestamp != decision.decision_timestamp
            or request.admission_recorded_at != admission.recorded_at
            or request.policy != pointer.policy
            or request.wo13_trade_plan.trade_plan_identity
            != pointer.wo13_trade_plan_identity
            or request.wo13_trade_plan.trade_plan_integrity
            != pointer.wo13_trade_plan_integrity
            or request.wo14_observation.observation_identity
            != pointer.wo14_observation_identity
            or request.wo14_observation.observation_integrity
            != pointer.wo14_observation_integrity
            or request.wo15_timing_handoff.handoff_identity
            != pointer.wo15_handoff_identity
            or request.wo15_timing_handoff.handoff_integrity
            != pointer.wo15_handoff_integrity
            or request.wo15_session.session_identity
            != pointer.session_identity
            or request.domain_008_session_fact.trading_date
            != pointer.trading_date
            or snapshot.snapshot_integrity != pointer.snapshot_integrity
            or decision.decision_integrity != pointer.decision_integrity
            or admission.admission_integrity != pointer.admission_integrity
            or operation.operation_integrity != pointer.operation_integrity
            or operation.outcome is not Wo16PersistedOperationOutcome.COMPLETED
            or operation.stage is not Wo16OperationStage.POINTER_PUBLICATION
            or operation.started_at != request.domain_008_session_fact.observed_at
            or operation.completed_at != request.admission_recorded_at
            or operation.request_identity != request.request_identity
            or operation.request_integrity != request.request_integrity
            or operation.snapshot_identity != snapshot.snapshot_identity
            or operation.snapshot_integrity != snapshot.snapshot_integrity
            or operation.decision_identity != decision.decision_identity
            or operation.decision_integrity != decision.decision_integrity
            or operation.admission_identity != admission.admission_identity
            or operation.admission_integrity != admission.admission_integrity
            or snapshot.policy != pointer.policy
            or decision.policy != pointer.policy
            or admission.policy != pointer.policy
            or decision.snapshot_identity != snapshot.snapshot_identity
            or decision.snapshot_integrity != snapshot.snapshot_integrity
            or admission.decision_identity != decision.decision_identity
            or admission.decision_integrity != decision.decision_integrity
            or trade.canonical_subject_identity
            != pointer.canonical_subject_identity
            or trade.market_family is not pointer.market_family
            or trade.instrument_identity != pointer.instrument_identity
            or trade.actual_contract_identity
            != pointer.actual_contract_identity
            or trade.contract_expiry != pointer.contract_expiry
            or trade.roll_lineage_identity != pointer.roll_lineage_identity
            or trade.trade_plan_identity != pointer.wo13_trade_plan_identity
            or trade.trade_plan_integrity != pointer.wo13_trade_plan_integrity
            or risk.observation_identity != pointer.wo14_observation_identity
            or risk.observation_integrity != pointer.wo14_observation_integrity
            or timing.handoff_identity != pointer.wo15_handoff_identity
            or timing.handoff_integrity != pointer.wo15_handoff_integrity
            or session.session_identity != pointer.session_identity
            or session.trading_date != pointer.trading_date
            or session.calendar_identity != pointer.calendar_identity
            or session.calendar_version != pointer.calendar_version
            or session.wo15_session_binding_identity
            != pointer.wo15_session_binding_identity
            or session.wo15_session_binding_integrity
            != pointer.wo15_session_binding_integrity
            or session.binding_identity
            != pointer.domain_008_session_binding_identity
            or session.binding_integrity
            != pointer.domain_008_session_binding_integrity
            or successor is None
            and any(
                value is not None
                for value in (
                    pointer.predecessor_decision_identity,
                    pointer.successor_lineage_identity,
                    pointer.successor_lineage_integrity,
                    decision.predecessor_decision_identity,
                    decision.supersession_lineage_identity,
                )
            )
            or successor is not None
            and (
                successor.lineage_integrity
                != pointer.successor_lineage_integrity
                or successor.predecessor_decision_identity
                != pointer.predecessor_decision_identity
                or successor.successor_snapshot_identity
                != snapshot.snapshot_identity
                or successor.successor_snapshot_integrity
                != snapshot.snapshot_integrity
                or decision.predecessor_decision_identity
                != successor.predecessor_decision_identity
                or decision.supersession_lineage_identity
                != successor.lineage_identity
                or operation.successor_lineage_identity
                != successor.lineage_identity
                or operation.successor_lineage_integrity
                != successor.lineage_integrity
            )
            or not history
            or decision not in history
        ):
            raise Wo16PersistenceError("WO16_RESTORATION_BINDING_INVALID")
        return RestoredWo16State(
            pointer,
            request,
            snapshot,
            decision,
            admission,
            operation,
            successor,
            latest_failure,
            history,
        )

    def find_completed_request(
        self, request_identity: str
    ) -> RestoredWo16State | None:
        if not _component(request_identity):
            raise Wo16PersistenceError("WO16_ARTIFACT_PATH_INVALID")
        matches: list[RestoredWo16State] = []
        directory = self._root / "current-snapshots"
        if not directory.exists():
            return None
        for path in sorted(directory.glob("*.json")):
            pointer = _artifact_from_bytes(_read(path))
            if type(pointer) is not CurrentWo16Pointer:
                raise Wo16PersistenceError("WO16_ARTIFACT_INTEGRITY_INVALID")
            if pointer.request_identity == request_identity:
                matches.append(self.restore_pointer(pointer))
        if not matches:
            return None
        first = matches[0]
        if any(item.decision != first.decision for item in matches[1:]):
            raise Wo16PersistenceError("WO16_REPLAY_HISTORY_CONFLICT")
        return first

    def restore_all(self) -> tuple[RestoredWo16State, ...]:
        restored: list[RestoredWo16State] = []
        for subject in self.current_subjects():
            value = self.restore_current(subject)
            if value is None:
                raise Wo16PersistenceError("WO16_CURRENT_POINTER_UNAVAILABLE")
            restored.append(value)
        return tuple(restored)

    def _history(
        self, canonical_subject_identity: str
    ) -> tuple[Wo16SponsorDecisionRecord, ...]:
        directory = self._root / "current-snapshots"
        if not directory.exists():
            return ()
        decisions: dict[str, Wo16SponsorDecisionRecord] = {}
        for path in sorted(directory.glob("*.json")):
            pointer = _artifact_from_bytes(_read(path))
            if type(pointer) is not CurrentWo16Pointer:
                raise Wo16PersistenceError("WO16_ARTIFACT_INTEGRITY_INVALID")
            if pointer.canonical_subject_identity == canonical_subject_identity:
                decision = self.load_decision(pointer.decision_identity)
                decisions[decision.decision_identity] = decision
        return tuple(
            sorted(
                decisions.values(),
                key=lambda item: (item.decision_timestamp, item.decision_identity),
            )
        )

    def _retain(self, family: str, identity: str, value: object) -> Path:
        path = self._path(family, identity)
        encoded = _artifact_bytes(value)
        with self._lock:
            if path.exists():
                if _read(path) != encoded:
                    raise Wo16PersistenceError("WO16_IMMUTABLE_CONFLICT")
            else:
                _write_new_atomic(path, encoded)
        return path

    def _load(
        self, family: str, identity: str, expected: type, identity_name: str
    ):  # type: ignore[no-untyped-def]
        value = _artifact_from_bytes(_read(self._path(family, identity)))
        if type(value) is not expected or getattr(value, identity_name, None) != identity:
            raise Wo16PersistenceError("WO16_ARTIFACT_INTEGRITY_INVALID")
        return value

    def _path(self, family: str, identity: str) -> Path:
        if family not in self._FAMILIES or not _component(identity):
            raise Wo16PersistenceError("WO16_ARTIFACT_PATH_INVALID")
        return self._root / family / f"{identity}.json"

    def _current_path(self, canonical_subject_identity: str) -> Path:
        return self._alias_path("CURRENT", canonical_subject_identity)

    def _failure_path(self, canonical_subject_identity: str) -> Path:
        return self._alias_path("LATEST-FAILURE", canonical_subject_identity)

    def _alias_path(self, family: str, canonical_subject_identity: str) -> Path:
        if not _component(canonical_subject_identity):
            raise Wo16PersistenceError("WO16_ARTIFACT_PATH_INVALID")
        digest = sha256(canonical_subject_identity.encode("utf-8")).hexdigest().upper()
        return self._root / "current" / f"{family}-WO16-{digest}.json"


_ALLOWED_CODEC_MODULES = (
    "kronos.application.intraday_wo16",
    "kronos.intraday.completed_evidence",
    "kronos.intraday.historical_semantic",
    "kronos.intraday.universe",
    "kronos.intraday.wo13",
    "kronos.intraday.wo13_handoff",
    "kronos.intraday.wo14",
    "kronos.intraday.wo15",
    "kronos.intraday.wo15_handoff",
    "kronos.intraday.wo15_persistence",
    "kronos.intraday.wo16",
    "kronos.intraday.wo16_persistence",
    "kronos.market.schedule",
    "kronos.validation.kr370",
)


def _registries() -> tuple[dict[str, type], dict[str, type[StrEnum]]]:
    dataclasses: dict[str, type] = {}
    enums: dict[str, type[StrEnum]] = {}
    for module_name in _ALLOWED_CODEC_MODULES:
        module = import_module(module_name)
        for item in vars(module).values():
            if not isinstance(item, type):
                continue
            if is_dataclass(item):
                prior = dataclasses.setdefault(item.__name__, item)
                if prior is not item:
                    raise Wo16PersistenceError("WO16_CODEC_TYPE_COLLISION")
            if issubclass(item, StrEnum):
                prior_enum = enums.setdefault(item.__name__, item)
                if prior_enum is not item:
                    raise Wo16PersistenceError("WO16_CODEC_TYPE_COLLISION")
    return dataclasses, enums


def _artifact_bytes(value: object) -> bytes:
    core = {
        "artifact_type": type(value).__name__,
        "artifact_identity": _artifact_identity(value),
        "artifact": _to_wire(value),
    }
    return _encode(
        {**core, "document_integrity": sha256(_encode(core)).hexdigest()}
    ) + b"\n"


def _artifact_from_bytes(encoded: bytes) -> object:
    try:
        document = json.loads(encoded)
        core = {
            key: document[key]
            for key in ("artifact_type", "artifact_identity", "artifact")
        }
        if (
            set(document) != {*core, "document_integrity"}
            or document["document_integrity"]
            != sha256(_encode(core)).hexdigest()
        ):
            raise ValueError
        value = _from_wire(document["artifact"])
        if (
            type(value).__name__ != document["artifact_type"]
            or _artifact_identity(value) != document["artifact_identity"]
        ):
            raise ValueError
        return value
    except (
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        Wo16ContractError,
    ) as error:
        raise Wo16PersistenceError("WO16_ARTIFACT_INTEGRITY_INVALID") from error


def _artifact_identity(value: object) -> str:
    for name in (
        "request_identity",
        "snapshot_identity",
        "decision_identity",
        "admission_identity",
        "operation_identity",
        "invalid_identity",
        "lineage_identity",
        "pointer_identity",
    ):
        identity = getattr(value, name, None)
        if type(identity) is str:
            return identity
    raise Wo16PersistenceError("WO16_ARTIFACT_IDENTITY_INVALID")


def _to_wire(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            "__dataclass__": type(value).__name__,
            "fields": {
                item.name: _to_wire(getattr(value, item.name))
                for item in fields(value)
            },
        }
    if isinstance(value, StrEnum):
        return {"__enum__": type(value).__name__, "value": value.value}
    if isinstance(value, datetime):
        return {
            "__datetime__": value.isoformat(),
            "zone": getattr(value.tzinfo, "key", None),
        }
    if isinstance(value, date):
        return {"__date__": value.isoformat()}
    if isinstance(value, Decimal):
        return {"__decimal__": format(value, "f")}
    if isinstance(value, tuple):
        return {"__tuple__": [_to_wire(item) for item in value]}
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise Wo16PersistenceError("WO16_ARTIFACT_ENCODING_INVALID")
        return {key: _to_wire(item) for key, item in value.items()}
    if value is None or type(value) in {str, int, bool}:
        return value
    raise Wo16PersistenceError("WO16_ARTIFACT_ENCODING_INVALID")


def _from_wire(value: object) -> object:
    if type(value) is not dict:
        return value
    if set(value) == {"__datetime__", "zone"}:
        restored = datetime.fromisoformat(value["__datetime__"])
        zone = value["zone"]
        return restored if zone is None else restored.astimezone(ZoneInfo(zone))
    if set(value) == {"__date__"}:
        return date.fromisoformat(value["__date__"])
    if set(value) == {"__decimal__"}:
        return Decimal(value["__decimal__"])
    if set(value) == {"__tuple__"}:
        return tuple(_from_wire(item) for item in value["__tuple__"])
    if set(value) == {"__enum__", "value"}:
        _, enums = _registries()
        enum = enums.get(value["__enum__"])
        if enum is None:
            raise ValueError
        return enum(value["value"])
    if set(value) == {"__dataclass__", "fields"}:
        dataclasses, _ = _registries()
        cls = dataclasses.get(value["__dataclass__"])
        raw = value["fields"]
        if cls is None or type(raw) is not dict:
            raise ValueError
        return cls(**{key: _from_wire(item) for key, item in raw.items()})
    return {key: _from_wire(item) for key, item in value.items()}


def _write_new_atomic(path: Path, encoded: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    try:
        temporary.write_bytes(encoded)
        try:
            os.link(temporary, path)
        except FileExistsError:
            if _read(path) != encoded:
                raise Wo16PersistenceError("WO16_IMMUTABLE_CONFLICT")
    finally:
        if temporary.exists():
            temporary.unlink()


def _replace_atomic(path: Path, encoded: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    try:
        temporary.write_bytes(encoded)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _read(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise Wo16PersistenceError("WO16_ARTIFACT_UNAVAILABLE") from error


def _encode(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _without(value: object, *names: str) -> dict[str, object]:
    return {
        item.name: getattr(value, item.name)
        for item in fields(value)
        if item.name not in names
    }


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(canonical_document_bytes(value)).hexdigest().upper()


def _scope_identity(
    canonical_subject_identity: str,
    instrument_identity: str,
    actual_contract_identity: str | None,
    session_identity: str,
) -> str:
    return _identity(
        "INTRADAY-WO16-SCOPE-",
        {
            "canonical_subject_identity": canonical_subject_identity,
            "instrument_identity": instrument_identity,
            "actual_contract_identity": actual_contract_identity,
            "session_identity": session_identity,
        },
    )


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _text(value: object) -> bool:
    return type(value) is str and bool(value.strip())


def _texts(values: tuple[object, ...]) -> bool:
    return bool(values) and all(_text(value) for value in values)


def _all_none(values: tuple[object, ...]) -> bool:
    return all(value is None for value in values)


def _code(value: object) -> bool:
    return (
        type(value) is str
        and 2 < len(value) <= 128
        and all(
            character.isupper()
            or character.isdigit()
            or character == "_"
            for character in value
        )
    )


def _component(value: object) -> bool:
    return (
        type(value) is str
        and 2 < len(value) <= 256
        and all(item.isalnum() or item in "-_.:" for item in value)
    )


__all__ = [
    "CurrentWo16Pointer",
    "DEFAULT_WO16_ROOT",
    "RestoredWo16State",
    "WO16_OPERATION_PROVENANCE_IDENTITY",
    "Wo16InvalidOperationProvenance",
    "Wo16OperationProvenance",
    "Wo16OperationStage",
    "Wo16PersistedOperationOutcome",
    "Wo16PersistenceError",
    "Wo16RestorationState",
    "Wo16Store",
    "create_current_wo16_pointer",
    "create_wo16_invalid_operation",
    "create_wo16_operation_provenance",
]
