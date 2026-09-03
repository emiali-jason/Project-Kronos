"""Append-only persistence and fail-closed restoration for WO-17 Slice 5.

The store persists only immutable outputs of the published Slice 1--4 engines.
It owns no market-data acquisition, lifecycle calculation, notification
delivery, broker action, or economic calculation.
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
from typing import TYPE_CHECKING, Mapping, Sequence
from uuid import uuid4
from zoneinfo import ZoneInfo

from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo17 import (
    WO17_CONTRACT_VERSION,
    WO17_POLICY_CHECKSUM,
    WO17_POLICY_IDENTITY,
    WO17_POLICY_VERSION,
    Wo17ContractError,
    Wo17UpstreamSnapshot,
    canonical_document_bytes,
)
from kronos.intraday.wo17_closure import (
    Wo17ClosureMachine,
    Wo17ClosureState,
    Wo17LiveExitAttestation,
)
from kronos.intraday.wo17_lifecycle import Wo17LifecycleMachine
from kronos.intraday.wo17_position import (
    Wo17PositionMachine,
    Wo17PositionState,
    Wo17PreEntryInvalidationFact,
)

if TYPE_CHECKING:
    from kronos.application.intraday_wo17 import Wo17OperationRequest


DEFAULT_WO17_ROOT = (
    Path.home()
    / "Library"
    / "Application Support"
    / "KRONOS"
    / "evidence"
    / "intraday-v1"
    / "wo17-position-evidence-active-lifecycle-monitoring-v1"
)

WO17_OPERATION_PROVENANCE_IDENTITY = (
    "KRONOS-INTRADAY-WO17-OPERATION-PROVENANCE-V1"
)
WO17_INVALID_OPERATION_IDENTITY = (
    "KRONOS-INTRADAY-WO17-INVALID-OPERATION-PROVENANCE-V1"
)
WO17_CURRENT_POINTER_IDENTITY = "KRONOS-INTRADAY-WO17-CURRENT-POINTER-V1"
WO17_SUCCESSOR_LINEAGE_IDENTITY = "KRONOS-INTRADAY-WO17-SUCCESSOR-LINEAGE-V1"


class Wo17PersistenceError(Wo17ContractError):
    """Sanitized persistence or restoration failure."""


class Wo17OperationStage(StrEnum):
    REQUEST_VALIDATION = "REQUEST_VALIDATION"
    REPLAY_VALIDATION = "REPLAY_VALIDATION"
    LINEAGE_VALIDATION = "LINEAGE_VALIDATION"
    CARDINALITY_VALIDATION = "CARDINALITY_VALIDATION"
    PERSISTENCE = "PERSISTENCE"
    POINTER_PUBLICATION = "POINTER_PUBLICATION"
    RESTORATION = "RESTORATION"


class Wo17OperationOutcome(StrEnum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Wo17RestorationState(StrEnum):
    NOT_YET_RUN = "NOT_YET_RUN"
    LOADED = "LOADED"
    CORRUPT = "CORRUPT"


@dataclass(frozen=True, slots=True)
class Wo17SuccessorLineage:
    lineage_identity: str
    lineage_integrity: str
    canonical_subject_identity: str
    predecessor_pointer_identity: str
    predecessor_pointer_integrity: str
    predecessor_position_identity: str
    predecessor_closure_identity: str
    successor_snapshot_identity: str
    successor_snapshot_integrity: str
    successor_position_state_identity: str
    successor_position_state_integrity: str
    established_at: datetime
    reason: str = "PRIOR_POSITION_CLOSED"
    schema_identity: str = WO17_SUCCESSOR_LINEAGE_IDENTITY
    schema_version: str = WO17_CONTRACT_VERSION
    automatic_reactivation: bool = False
    automatic_contract_migration: bool = False

    def __post_init__(self) -> None:
        values = _without(self, "lineage_identity", "lineage_integrity")
        if (
            not _texts(
                (
                    self.canonical_subject_identity,
                    self.predecessor_pointer_identity,
                    self.predecessor_pointer_integrity,
                    self.predecessor_position_identity,
                    self.predecessor_closure_identity,
                    self.successor_snapshot_identity,
                    self.successor_snapshot_integrity,
                    self.successor_position_state_identity,
                    self.successor_position_state_integrity,
                )
            )
            or self.reason != "PRIOR_POSITION_CLOSED"
            or not _aware(self.established_at)
            or self.schema_identity != WO17_SUCCESSOR_LINEAGE_IDENTITY
            or self.schema_version != WO17_CONTRACT_VERSION
            or self.automatic_reactivation
            or self.automatic_contract_migration
            or self.lineage_identity
            != _identity("INTRADAY-WO17-SUCCESSOR-", values)
            or self.lineage_integrity
            != _identity("INTEGRITY-INTRADAY-WO17-SUCCESSOR-", values)
        ):
            raise Wo17PersistenceError("WO17_SUCCESSOR_LINEAGE_INVALID")


@dataclass(frozen=True, slots=True)
class Wo17OperationProvenance:
    operation_identity: str
    operation_integrity: str
    request_identity: str
    request_integrity: str
    canonical_subject_identity: str
    stage: Wo17OperationStage
    outcome: Wo17OperationOutcome
    started_at: datetime
    completed_at: datetime | None
    failed_at: datetime | None
    upstream_snapshot_identity: str | None
    position_state_identity: str | None
    lifecycle_state_identity: str | None
    closure_state_identity: str | None
    failure_reason: str | None
    provenance: tuple[str, ...]
    schema_identity: str = WO17_OPERATION_PROVENANCE_IDENTITY
    schema_version: str = WO17_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "operation_identity", "operation_integrity")
        completed = self.outcome is Wo17OperationOutcome.COMPLETED
        failed = self.outcome is Wo17OperationOutcome.FAILED
        required_completed = (
            self.upstream_snapshot_identity,
            self.position_state_identity,
        )
        if (
            not _texts(
                (
                    self.request_identity,
                    self.request_integrity,
                    self.canonical_subject_identity,
                    *self.provenance,
                )
            )
            or type(self.stage) is not Wo17OperationStage
            or type(self.outcome) is not Wo17OperationOutcome
            or not _aware(self.started_at)
            or completed != (self.completed_at is not None)
            or failed != (self.failed_at is not None)
            or failed != (self.failure_reason is not None)
            or self.completed_at is not None
            and not _aware(self.completed_at)
            or self.failed_at is not None
            and not _aware(self.failed_at)
            or completed != _texts(required_completed)
            or failed
            and any(
                value is not None
                for value in (
                    *required_completed,
                    self.lifecycle_state_identity,
                    self.closure_state_identity,
                )
            )
            or self.failure_reason is not None
            and not _code(self.failure_reason)
            or self.schema_identity != WO17_OPERATION_PROVENANCE_IDENTITY
            or self.schema_version != WO17_CONTRACT_VERSION
            or self.operation_identity
            != _identity("INTRADAY-WO17-OPERATION-", values)
            or self.operation_integrity
            != _identity("INTEGRITY-INTRADAY-WO17-OPERATION-", values)
        ):
            raise Wo17PersistenceError("WO17_OPERATION_PROVENANCE_INVALID")


@dataclass(frozen=True, slots=True)
class Wo17InvalidOperationProvenance:
    invalid_identity: str
    invalid_integrity: str
    request_identity: str
    request_integrity: str
    canonical_subject_identity: str
    stage: Wo17OperationStage
    reason: str
    source_identities: tuple[str, ...]
    failed_at: datetime
    schema_identity: str = WO17_INVALID_OPERATION_IDENTITY
    schema_version: str = WO17_CONTRACT_VERSION

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
            or type(self.stage) is not Wo17OperationStage
            or not _code(self.reason)
            or not _aware(self.failed_at)
            or self.schema_identity != WO17_INVALID_OPERATION_IDENTITY
            or self.schema_version != WO17_CONTRACT_VERSION
            or self.invalid_identity
            != _identity("INTRADAY-WO17-INVALID-", values)
            or self.invalid_integrity
            != _identity("INTEGRITY-INTRADAY-WO17-INVALID-", values)
        ):
            raise Wo17PersistenceError("WO17_INVALID_OPERATION_INVALID")


@dataclass(frozen=True, slots=True)
class CurrentWo17Pointer:
    pointer_identity: str
    pointer_integrity: str
    canonical_subject_identity: str
    market_family: IntradayMarketFamily
    instrument_identity: str
    actual_contract_identity: str | None
    contract_expiry: date | None
    roll_lineage_identity: str | None
    entry_session_identity: str
    entry_trading_date: date
    upstream_snapshot_identity: str
    upstream_snapshot_integrity: str
    upstream_lineage_identity: str
    upstream_lineage_integrity: str
    request_identity: str
    request_integrity: str
    position_identity: str
    position_integrity: str
    position_state_identity: str
    position_state_integrity: str
    position_state: Wo17PositionState
    lifecycle_state_identity: str | None
    lifecycle_state_integrity: str | None
    monitoring_availability: str
    closure_state_identity: str | None
    closure_state_integrity: str | None
    closure_identity: str | None
    closure_integrity: str | None
    closure_state: Wo17ClosureState | None
    operation_identity: str
    operation_integrity: str
    predecessor_pointer_identity: str | None
    predecessor_pointer_integrity: str | None
    successor_lineage_identity: str | None
    successor_lineage_integrity: str | None
    successor_sequence: int
    published_at: datetime
    policy_identity: str = WO17_POLICY_IDENTITY
    policy_version: str = WO17_POLICY_VERSION
    policy_checksum: str = WO17_POLICY_CHECKSUM
    schema_identity: str = WO17_CURRENT_POINTER_IDENTITY
    schema_version: str = WO17_CONTRACT_VERSION
    provider_acquisition_authority: bool = False
    broker_order_authority: bool = False
    notification_delivery_authority: bool = False
    economics_authority: bool = False

    def __post_init__(self) -> None:
        values = _without(self, "pointer_identity", "pointer_integrity")
        mcx = self.market_family is IntradayMarketFamily.MCX
        mcx_values = (
            self.actual_contract_identity,
            self.contract_expiry,
            self.roll_lineage_identity,
        )
        lifecycle_pair = (
            self.lifecycle_state_identity,
            self.lifecycle_state_integrity,
        )
        closure_pairs = (
            self.closure_state_identity,
            self.closure_state_integrity,
        )
        closure_record_pair = (self.closure_identity, self.closure_integrity)
        predecessor_pair = (
            self.predecessor_pointer_identity,
            self.predecessor_pointer_integrity,
        )
        successor_pair = (
            self.successor_lineage_identity,
            self.successor_lineage_integrity,
        )
        if (
            not _texts(
                (
                    self.canonical_subject_identity,
                    self.instrument_identity,
                    self.entry_session_identity,
                    self.upstream_snapshot_identity,
                    self.upstream_snapshot_integrity,
                    self.upstream_lineage_identity,
                    self.upstream_lineage_integrity,
                    self.request_identity,
                    self.request_integrity,
                    self.position_identity,
                    self.position_integrity,
                    self.position_state_identity,
                    self.position_state_integrity,
                    self.monitoring_availability,
                    self.operation_identity,
                    self.operation_integrity,
                )
            )
            or type(self.market_family) is not IntradayMarketFamily
            or type(self.entry_trading_date) is not date
            or type(self.position_state) is not Wo17PositionState
            or mcx != all(value is not None for value in mcx_values)
            or not mcx and any(value is not None for value in mcx_values)
            or not (_all_none(lifecycle_pair) or _texts(lifecycle_pair))
            or not (_all_none(closure_pairs) or _texts(closure_pairs))
            or not (_all_none(closure_record_pair) or _texts(closure_record_pair))
            or not (_all_none(predecessor_pair) or _texts(predecessor_pair))
            or not (_all_none(successor_pair) or _texts(successor_pair))
            or (self.closure_state is None) != _all_none(closure_pairs)
            or (
                self.closure_state in {None, Wo17ClosureState.ACTIVE}
                and not _all_none(closure_record_pair)
            )
            or (
                self.closure_state
                in {Wo17ClosureState.PAPER_CLOSED, Wo17ClosureState.LIVE_CLOSED}
                and not _texts(closure_record_pair)
            )
            or self.closure_state is not None
            and type(self.closure_state) is not Wo17ClosureState
            or type(self.successor_sequence) is not int
            or self.successor_sequence < 0
            or (self.successor_sequence == 0) != _all_none(predecessor_pair)
            or not _aware(self.published_at)
            or self.policy_identity != WO17_POLICY_IDENTITY
            or self.policy_version != WO17_POLICY_VERSION
            or self.policy_checksum != WO17_POLICY_CHECKSUM
            or self.schema_identity != WO17_CURRENT_POINTER_IDENTITY
            or self.schema_version != WO17_CONTRACT_VERSION
            or any(
                (
                    self.provider_acquisition_authority,
                    self.broker_order_authority,
                    self.notification_delivery_authority,
                    self.economics_authority,
                )
            )
            or self.pointer_identity != _identity("CURRENT-INTRADAY-WO17-", values)
            or self.pointer_integrity
            != _identity("INTEGRITY-CURRENT-INTRADAY-WO17-", values)
        ):
            raise Wo17PersistenceError("WO17_CURRENT_POINTER_INVALID")

    @property
    def non_closed(self) -> bool:
        return self.closure_state in {None, Wo17ClosureState.ACTIVE}


@dataclass(frozen=True, slots=True)
class RestoredWo17State:
    pointer: CurrentWo17Pointer
    request: Wo17OperationRequest
    snapshot: Wo17UpstreamSnapshot
    position: Wo17PositionMachine
    lifecycle: Wo17LifecycleMachine | None
    closure: Wo17ClosureMachine | None
    live_exit_attestation: Wo17LiveExitAttestation | None
    pre_entry_invalidation: Wo17PreEntryInvalidationFact | None
    operation: Wo17OperationProvenance
    successor: Wo17SuccessorLineage | None
    latest_failure: Wo17InvalidOperationProvenance | None
    history: tuple[CurrentWo17Pointer, ...]


def create_wo17_operation_provenance(
    *,
    request: Wo17OperationRequest,
    stage: Wo17OperationStage,
    outcome: Wo17OperationOutcome,
    started_at: datetime,
    completed_at: datetime | None = None,
    failed_at: datetime | None = None,
    failure_reason: str | None = None,
    provenance: tuple[str, ...] = ("ADR-0027", "WO-17-SLICE-5"),
) -> Wo17OperationProvenance:
    completed = outcome is Wo17OperationOutcome.COMPLETED
    values = {
        "request_identity": request.request_identity,
        "request_integrity": request.request_integrity,
        "canonical_subject_identity": request.canonical_subject_identity,
        "stage": stage,
        "outcome": outcome,
        "started_at": started_at,
        "completed_at": completed_at,
        "failed_at": failed_at,
        "upstream_snapshot_identity": (
            request.snapshot.snapshot_identity if completed else None
        ),
        "position_state_identity": (
            request.position.state_identity if completed else None
        ),
        "lifecycle_state_identity": (
            None
            if not completed or request.lifecycle is None
            else request.lifecycle.state_identity
        ),
        "closure_state_identity": (
            None
            if not completed or request.closure is None
            else request.closure.state_identity
        ),
        "failure_reason": failure_reason,
        "provenance": provenance,
        "schema_identity": WO17_OPERATION_PROVENANCE_IDENTITY,
        "schema_version": WO17_CONTRACT_VERSION,
    }
    return Wo17OperationProvenance(
        operation_identity=_identity("INTRADAY-WO17-OPERATION-", values),
        operation_integrity=_identity(
            "INTEGRITY-INTRADAY-WO17-OPERATION-", values
        ),
        **values,
    )


def create_wo17_invalid_operation(
    *,
    request: Wo17OperationRequest,
    stage: Wo17OperationStage,
    reason: str,
    failed_at: datetime,
) -> Wo17InvalidOperationProvenance:
    values = {
        "request_identity": request.request_identity,
        "request_integrity": request.request_integrity,
        "canonical_subject_identity": request.canonical_subject_identity,
        "stage": stage,
        "reason": reason,
        "source_identities": (
            request.snapshot.snapshot_identity,
            request.position.state_identity,
            *(
                ()
                if request.lifecycle is None
                else (request.lifecycle.state_identity,)
            ),
            *(() if request.closure is None else (request.closure.state_identity,)),
        ),
        "failed_at": failed_at,
        "schema_identity": WO17_INVALID_OPERATION_IDENTITY,
        "schema_version": WO17_CONTRACT_VERSION,
    }
    return Wo17InvalidOperationProvenance(
        invalid_identity=_identity("INTRADAY-WO17-INVALID-", values),
        invalid_integrity=_identity("INTEGRITY-INTRADAY-WO17-INVALID-", values),
        **values,
    )


def create_current_wo17_pointer(
    *,
    request: Wo17OperationRequest,
    operation: Wo17OperationProvenance,
    predecessor: CurrentWo17Pointer | None,
    successor: Wo17SuccessorLineage | None,
    published_at: datetime,
) -> CurrentWo17Pointer:
    lineage = request.snapshot.lineage
    evidence = request.position.position_evidence
    position_identity = (
        request.position.state_identity
        if evidence is None
        else evidence.position_identity
    )
    position_integrity = (
        request.position.state_integrity
        if evidence is None
        else evidence.position_integrity
    )
    closure_record = None if request.closure is None else request.closure.closure
    values = {
        "canonical_subject_identity": request.canonical_subject_identity,
        "market_family": lineage.market_family,
        "instrument_identity": lineage.instrument_identity,
        "actual_contract_identity": lineage.actual_contract_identity,
        "contract_expiry": lineage.contract_expiry,
        "roll_lineage_identity": lineage.roll_lineage_identity,
        "entry_session_identity": lineage.session_identity,
        "entry_trading_date": lineage.trading_date,
        "upstream_snapshot_identity": request.snapshot.snapshot_identity,
        "upstream_snapshot_integrity": request.snapshot.snapshot_integrity,
        "upstream_lineage_identity": lineage.lineage_identity,
        "upstream_lineage_integrity": lineage.lineage_integrity,
        "request_identity": request.request_identity,
        "request_integrity": request.request_integrity,
        "position_identity": position_identity,
        "position_integrity": position_integrity,
        "position_state_identity": request.position.state_identity,
        "position_state_integrity": request.position.state_integrity,
        "position_state": request.position.state,
        "lifecycle_state_identity": (
            None if request.lifecycle is None else request.lifecycle.state_identity
        ),
        "lifecycle_state_integrity": (
            None if request.lifecycle is None else request.lifecycle.state_integrity
        ),
        "monitoring_availability": (
            "NOT_APPLICABLE"
            if request.lifecycle is None
            else request.lifecycle.monitoring_availability.value
        ),
        "closure_state_identity": (
            None if request.closure is None else request.closure.state_identity
        ),
        "closure_state_integrity": (
            None if request.closure is None else request.closure.state_integrity
        ),
        "closure_identity": (
            None if closure_record is None else closure_record.closure_identity
        ),
        "closure_integrity": (
            None if closure_record is None else closure_record.closure_integrity
        ),
        "closure_state": (
            None if request.closure is None else request.closure.closure_state
        ),
        "operation_identity": operation.operation_identity,
        "operation_integrity": operation.operation_integrity,
        "predecessor_pointer_identity": (
            None if predecessor is None else predecessor.pointer_identity
        ),
        "predecessor_pointer_integrity": (
            None if predecessor is None else predecessor.pointer_integrity
        ),
        "successor_lineage_identity": (
            None if successor is None else successor.lineage_identity
        ),
        "successor_lineage_integrity": (
            None if successor is None else successor.lineage_integrity
        ),
        "successor_sequence": (
            0 if predecessor is None else predecessor.successor_sequence + 1
        ),
        "published_at": published_at,
        "policy_identity": WO17_POLICY_IDENTITY,
        "policy_version": WO17_POLICY_VERSION,
        "policy_checksum": WO17_POLICY_CHECKSUM,
        "schema_identity": WO17_CURRENT_POINTER_IDENTITY,
        "schema_version": WO17_CONTRACT_VERSION,
        "provider_acquisition_authority": False,
        "broker_order_authority": False,
        "notification_delivery_authority": False,
        "economics_authority": False,
    }
    return CurrentWo17Pointer(
        pointer_identity=_identity("CURRENT-INTRADAY-WO17-", values),
        pointer_integrity=_identity(
            "INTEGRITY-CURRENT-INTRADAY-WO17-", values
        ),
        **values,
    )


def create_wo17_successor_lineage(
    *,
    predecessor: CurrentWo17Pointer,
    request: Wo17OperationRequest,
    established_at: datetime,
) -> Wo17SuccessorLineage:
    if predecessor.closure_identity is None or predecessor.non_closed:
        raise Wo17PersistenceError("WO17_SUCCESSOR_PREDECESSOR_NOT_CLOSED")
    values = {
        "canonical_subject_identity": request.canonical_subject_identity,
        "predecessor_pointer_identity": predecessor.pointer_identity,
        "predecessor_pointer_integrity": predecessor.pointer_integrity,
        "predecessor_position_identity": predecessor.position_identity,
        "predecessor_closure_identity": predecessor.closure_identity,
        "successor_snapshot_identity": request.snapshot.snapshot_identity,
        "successor_snapshot_integrity": request.snapshot.snapshot_integrity,
        "successor_position_state_identity": request.position.state_identity,
        "successor_position_state_integrity": request.position.state_integrity,
        "established_at": established_at,
        "reason": "PRIOR_POSITION_CLOSED",
        "schema_identity": WO17_SUCCESSOR_LINEAGE_IDENTITY,
        "schema_version": WO17_CONTRACT_VERSION,
        "automatic_reactivation": False,
        "automatic_contract_migration": False,
    }
    return Wo17SuccessorLineage(
        lineage_identity=_identity("INTRADAY-WO17-SUCCESSOR-", values),
        lineage_integrity=_identity("INTEGRITY-INTRADAY-WO17-SUCCESSOR-", values),
        **values,
    )


class Wo17Store:
    """Product-local append-only graph store with atomic subject aliases."""

    _FAMILIES = frozenset(
        {
            "requests",
            "upstream-lineages",
            "upstream-snapshots",
            "position-states",
            "positions",
            "entry-observations",
            "live-entry-attestations",
            "pre-entry-invalidations",
            "lifecycle-states",
            "lifecycle-observations",
            "lifecycle-assessments",
            "session-end-facts",
            "closure-states",
            "live-exit-attestations",
            "closures",
            "events",
            "operations",
            "invalid",
            "successors",
            "current-snapshots",
        }
    )

    def __init__(self, root: Path = DEFAULT_WO17_ROOT) -> None:
        if not isinstance(root, Path) or not root.is_absolute() or root == Path("/"):
            raise ValueError("WO17_STORE_ROOT_INVALID")
        self._root = root
        self._lock = RLock()

    @property
    def root(self) -> Path:
        return self._root

    def retain_request(self, value: Wo17OperationRequest) -> Path:
        from kronos.application.intraday_wo17 import Wo17OperationRequest

        if type(value) is not Wo17OperationRequest:
            raise Wo17PersistenceError("WO17_REQUEST_INVALID")
        return self._retain("requests", value.request_identity, value)

    def retain_graph(self, request: Wo17OperationRequest) -> None:
        """Retain every immutable artifact reachable from one exact request."""

        self.retain_request(request)
        snapshot = request.snapshot
        self._retain("upstream-lineages", snapshot.lineage.lineage_identity, snapshot.lineage)
        self._retain("upstream-snapshots", snapshot.snapshot_identity, snapshot)
        position = request.position
        self._retain("position-states", position.state_identity, position)
        if position.position_evidence is not None:
            self._retain("positions", position.position_evidence.position_identity, position.position_evidence)
        for item in position.observations:
            self._retain("entry-observations", item.observation_identity, item)
        if position.live_attestation is not None:
            self._retain("live-entry-attestations", position.live_attestation.attestation_identity, position.live_attestation)
        if request.pre_entry_invalidation is not None:
            self._retain("pre-entry-invalidations", request.pre_entry_invalidation.fact_identity, request.pre_entry_invalidation)
        if request.lifecycle is not None:
            lifecycle = request.lifecycle
            self._retain("lifecycle-states", lifecycle.state_identity, lifecycle)
            for item in lifecycle.observations:
                self._retain("lifecycle-observations", item.observation_identity, item)
            for item in lifecycle.assessments:
                self._retain("lifecycle-assessments", item.assessment_identity, item)
            if lifecycle.session_end_fact is not None:
                self._retain("session-end-facts", lifecycle.session_end_fact.fact_identity, lifecycle.session_end_fact)
        if request.live_exit_attestation is not None:
            self._retain("live-exit-attestations", request.live_exit_attestation.attestation_identity, request.live_exit_attestation)
        if request.closure is not None:
            closure = request.closure
            self._retain("closure-states", closure.state_identity, closure)
            for item in closure.events:
                self._retain("events", item.event_identity, item)
            if closure.closure is not None:
                self._retain("closures", closure.closure.closure_identity, closure.closure)

    def retain_operation(self, value: Wo17OperationProvenance) -> Path:
        return self._retain("operations", value.operation_identity, value)

    def retain_invalid(self, value: Wo17InvalidOperationProvenance) -> Path:
        return self._retain("invalid", value.invalid_identity, value)

    def retain_pointer_snapshot(self, value: CurrentWo17Pointer) -> Path:
        return self._retain("current-snapshots", value.pointer_identity, value)

    def retain_successor(self, value: Wo17SuccessorLineage) -> Path:
        return self._retain("successors", value.lineage_identity, value)

    def load_request(self, identity: str) -> Wo17OperationRequest:
        value = self._load("requests", identity)
        from kronos.application.intraday_wo17 import Wo17OperationRequest

        if type(value) is not Wo17OperationRequest:
            raise Wo17PersistenceError("WO17_ARTIFACT_INTEGRITY_INVALID")
        return value

    def load_snapshot(self, identity: str) -> Wo17UpstreamSnapshot:
        value = self._load("upstream-snapshots", identity)
        if type(value) is not Wo17UpstreamSnapshot:
            raise Wo17PersistenceError("WO17_ARTIFACT_INTEGRITY_INVALID")
        return value

    def load_position_state(self, identity: str) -> Wo17PositionMachine:
        value = self._load("position-states", identity)
        if type(value) is not Wo17PositionMachine:
            raise Wo17PersistenceError("WO17_ARTIFACT_INTEGRITY_INVALID")
        return value

    def load_lifecycle_state(self, identity: str) -> Wo17LifecycleMachine:
        value = self._load("lifecycle-states", identity)
        if type(value) is not Wo17LifecycleMachine:
            raise Wo17PersistenceError("WO17_ARTIFACT_INTEGRITY_INVALID")
        return value

    def load_closure_state(self, identity: str) -> Wo17ClosureMachine:
        value = self._load("closure-states", identity)
        if type(value) is not Wo17ClosureMachine:
            raise Wo17PersistenceError("WO17_ARTIFACT_INTEGRITY_INVALID")
        return value

    def load_operation(self, identity: str) -> Wo17OperationProvenance:
        value = self._load("operations", identity)
        if type(value) is not Wo17OperationProvenance:
            raise Wo17PersistenceError("WO17_ARTIFACT_INTEGRITY_INVALID")
        return value

    def load_pointer_snapshot(self, identity: str) -> CurrentWo17Pointer:
        value = self._load("current-snapshots", identity)
        if type(value) is not CurrentWo17Pointer:
            raise Wo17PersistenceError("WO17_ARTIFACT_INTEGRITY_INVALID")
        return value

    def load_successor(self, identity: str) -> Wo17SuccessorLineage:
        value = self._load("successors", identity)
        if type(value) is not Wo17SuccessorLineage:
            raise Wo17PersistenceError("WO17_ARTIFACT_INTEGRITY_INVALID")
        return value

    def publish_current(self, value: CurrentWo17Pointer) -> Path:
        if type(value) is not CurrentWo17Pointer:
            raise Wo17PersistenceError("WO17_CURRENT_POINTER_INVALID")
        path = self._current_path(value.canonical_subject_identity)
        with self._lock:
            self.retain_pointer_snapshot(value)
            self.restore_pointer(value)
            previous = _read(path) if path.exists() else None
            try:
                _replace_atomic(path, _artifact_bytes(value))
                if self.load_current(value.canonical_subject_identity) != value:
                    raise Wo17PersistenceError("WO17_CURRENT_ALIAS_PUBLICATION_INVALID")
            except Exception:
                if previous is None:
                    path.unlink(missing_ok=True)
                else:
                    _replace_atomic(path, previous)
                raise
        return path

    def publish_latest_failure(self, value: Wo17InvalidOperationProvenance) -> Path:
        if type(value) is not Wo17InvalidOperationProvenance:
            raise Wo17PersistenceError("WO17_INVALID_OPERATION_INVALID")
        path = self._failure_path(value.canonical_subject_identity)
        with self._lock:
            self.retain_invalid(value)
            _replace_atomic(path, _artifact_bytes(value))
        return path

    def load_current(self, subject: str) -> CurrentWo17Pointer | None:
        path = self._current_path(subject)
        if not path.exists():
            return None
        value = _artifact_from_bytes(_read(path))
        if type(value) is not CurrentWo17Pointer or value.canonical_subject_identity != subject:
            raise Wo17PersistenceError("WO17_CURRENT_POINTER_INTEGRITY_INVALID")
        return value

    def load_latest_failure(self, subject: str) -> Wo17InvalidOperationProvenance | None:
        path = self._failure_path(subject)
        if not path.exists():
            return None
        value = _artifact_from_bytes(_read(path))
        if type(value) is not Wo17InvalidOperationProvenance or value.canonical_subject_identity != subject:
            raise Wo17PersistenceError("WO17_FAILURE_POINTER_INTEGRITY_INVALID")
        return value

    def current_subjects(self) -> tuple[str, ...]:
        directory = self._root / "current"
        if not directory.exists():
            return ()
        subjects: set[str] = set()
        for path in sorted(directory.glob("CURRENT-WO17-*.json")):
            value = _artifact_from_bytes(_read(path))
            if type(value) is not CurrentWo17Pointer or path != self._current_path(value.canonical_subject_identity):
                raise Wo17PersistenceError("WO17_CURRENT_ALIAS_INVALID")
            subjects.add(value.canonical_subject_identity)
        return tuple(sorted(subjects))

    def failure_subjects(self) -> tuple[str, ...]:
        directory = self._root / "current"
        if not directory.exists():
            return ()
        subjects: set[str] = set()
        for path in sorted(directory.glob("LATEST-FAILURE-WO17-*.json")):
            value = _artifact_from_bytes(_read(path))
            if type(value) is not Wo17InvalidOperationProvenance or path != self._failure_path(value.canonical_subject_identity):
                raise Wo17PersistenceError("WO17_FAILURE_ALIAS_INVALID")
            subjects.add(value.canonical_subject_identity)
        return tuple(sorted(subjects))

    def restore_current(self, subject: str) -> RestoredWo17State | None:
        pointer = self.load_current(subject)
        return None if pointer is None else self.restore_pointer(pointer)

    def restore_pointer(self, pointer: CurrentWo17Pointer) -> RestoredWo17State:
        if type(pointer) is not CurrentWo17Pointer:
            raise Wo17PersistenceError("WO17_CURRENT_POINTER_INVALID")
        request = self.load_request(pointer.request_identity)
        snapshot = self.load_snapshot(pointer.upstream_snapshot_identity)
        position = self.load_position_state(pointer.position_state_identity)
        lifecycle = None if pointer.lifecycle_state_identity is None else self._load("lifecycle-states", pointer.lifecycle_state_identity)
        closure = None if pointer.closure_state_identity is None else self._load("closure-states", pointer.closure_state_identity)
        operation = self.load_operation(pointer.operation_identity)
        successor = None if pointer.successor_lineage_identity is None else self.load_successor(pointer.successor_lineage_identity)
        latest = self.load_latest_failure(pointer.canonical_subject_identity)
        history = self._history(pointer.canonical_subject_identity)
        if (
            type(snapshot) is not Wo17UpstreamSnapshot
            or type(position) is not Wo17PositionMachine
            or lifecycle is not None and type(lifecycle) is not Wo17LifecycleMachine
            or closure is not None and type(closure) is not Wo17ClosureMachine
            or type(operation) is not Wo17OperationProvenance
            or request.snapshot != snapshot
            or request.position != position
            or request.lifecycle != lifecycle
            or request.closure != closure
            or request.request_integrity != pointer.request_integrity
            or snapshot.snapshot_integrity != pointer.upstream_snapshot_integrity
            or snapshot.lineage.lineage_identity != pointer.upstream_lineage_identity
            or snapshot.lineage.lineage_integrity != pointer.upstream_lineage_integrity
            or position.state_integrity != pointer.position_state_integrity
            or position.state is not pointer.position_state
            or operation.operation_integrity != pointer.operation_integrity
            or operation.outcome is not Wo17OperationOutcome.COMPLETED
            or operation.stage is not Wo17OperationStage.POINTER_PUBLICATION
            or operation.request_identity != request.request_identity
            or operation.request_integrity != request.request_integrity
            or operation.canonical_subject_identity != pointer.canonical_subject_identity
            or operation.upstream_snapshot_identity != snapshot.snapshot_identity
            or operation.position_state_identity != position.state_identity
            or (None if successor is None else successor.lineage_integrity) != pointer.successor_lineage_integrity
            or successor is not None
            and (
                successor.predecessor_pointer_identity != pointer.predecessor_pointer_identity
                or successor.successor_snapshot_identity != snapshot.snapshot_identity
                or successor.successor_position_state_identity != position.state_identity
            )
            or (None if lifecycle is None else lifecycle.state_integrity) != pointer.lifecycle_state_integrity
            or (None if closure is None else closure.state_integrity) != pointer.closure_state_integrity
            or pointer not in history
        ):
            raise Wo17PersistenceError("WO17_RESTORATION_BINDING_INVALID")
        _validate_graph(request)
        self._validate_reachable_artifacts(request)
        return RestoredWo17State(
            pointer,
            request,
            snapshot,
            position,
            lifecycle,
            closure,
            request.live_exit_attestation,
            request.pre_entry_invalidation,
            operation,
            successor,
            latest,
            history,
        )

    def find_completed_request(self, identity: str) -> RestoredWo17State | None:
        if not _component(identity):
            raise Wo17PersistenceError("WO17_ARTIFACT_PATH_INVALID")
        matches: list[RestoredWo17State] = []
        directory = self._root / "current-snapshots"
        if not directory.exists():
            return None
        for path in sorted(directory.glob("*.json")):
            pointer = _artifact_from_bytes(_read(path))
            if type(pointer) is not CurrentWo17Pointer:
                raise Wo17PersistenceError("WO17_ARTIFACT_INTEGRITY_INVALID")
            if pointer.request_identity == identity:
                matches.append(self.restore_pointer(pointer))
        if not matches:
            return None
        first = matches[0]
        if any(item.request != first.request for item in matches[1:]):
            raise Wo17PersistenceError("WO17_REPLAY_HISTORY_CONFLICT")
        return first

    def restore_all(self) -> tuple[RestoredWo17State, ...]:
        restored: list[RestoredWo17State] = []
        for subject in self.current_subjects():
            item = self.restore_current(subject)
            if item is None:
                raise Wo17PersistenceError("WO17_CURRENT_POINTER_UNAVAILABLE")
            restored.append(item)
        return tuple(restored)

    def _validate_reachable_artifacts(self, request: Wo17OperationRequest) -> None:
        snapshot = request.snapshot
        if self._load("upstream-lineages", snapshot.lineage.lineage_identity) != snapshot.lineage:
            raise Wo17PersistenceError("WO17_RESTORATION_BINDING_INVALID")
        position = request.position
        if position.position_evidence is not None and self._load("positions", position.position_evidence.position_identity) != position.position_evidence:
            raise Wo17PersistenceError("WO17_RESTORATION_BINDING_INVALID")
        for item in position.observations:
            if self._load("entry-observations", item.observation_identity) != item:
                raise Wo17PersistenceError("WO17_RESTORATION_BINDING_INVALID")
        if position.live_attestation is not None and self._load("live-entry-attestations", position.live_attestation.attestation_identity) != position.live_attestation:
            raise Wo17PersistenceError("WO17_RESTORATION_BINDING_INVALID")
        if request.pre_entry_invalidation is not None and self._load("pre-entry-invalidations", request.pre_entry_invalidation.fact_identity) != request.pre_entry_invalidation:
            raise Wo17PersistenceError("WO17_RESTORATION_BINDING_INVALID")
        if request.lifecycle is not None:
            for item in request.lifecycle.observations:
                if self._load("lifecycle-observations", item.observation_identity) != item:
                    raise Wo17PersistenceError("WO17_RESTORATION_BINDING_INVALID")
            for item in request.lifecycle.assessments:
                if self._load("lifecycle-assessments", item.assessment_identity) != item:
                    raise Wo17PersistenceError("WO17_RESTORATION_BINDING_INVALID")
            fact = request.lifecycle.session_end_fact
            if fact is not None and self._load("session-end-facts", fact.fact_identity) != fact:
                raise Wo17PersistenceError("WO17_RESTORATION_BINDING_INVALID")
        if request.live_exit_attestation is not None and self._load("live-exit-attestations", request.live_exit_attestation.attestation_identity) != request.live_exit_attestation:
            raise Wo17PersistenceError("WO17_RESTORATION_BINDING_INVALID")
        if request.closure is not None:
            for item in request.closure.events:
                if self._load("events", item.event_identity) != item:
                    raise Wo17PersistenceError("WO17_RESTORATION_BINDING_INVALID")
            item = request.closure.closure
            if item is not None and self._load("closures", item.closure_identity) != item:
                raise Wo17PersistenceError("WO17_RESTORATION_BINDING_INVALID")

    def _history(self, subject: str) -> tuple[CurrentWo17Pointer, ...]:
        directory = self._root / "current-snapshots"
        if not directory.exists():
            return ()
        values: dict[str, CurrentWo17Pointer] = {}
        for path in sorted(directory.glob("*.json")):
            pointer = _artifact_from_bytes(_read(path))
            if type(pointer) is not CurrentWo17Pointer:
                raise Wo17PersistenceError("WO17_ARTIFACT_INTEGRITY_INVALID")
            if pointer.canonical_subject_identity == subject:
                values[pointer.pointer_identity] = pointer
        return tuple(sorted(values.values(), key=lambda item: (item.published_at, item.pointer_identity)))

    def _retain(self, family: str, identity: str, value: object) -> Path:
        path = self._path(family, identity)
        encoded = _artifact_bytes(value)
        with self._lock:
            if path.exists():
                if _read(path) != encoded:
                    raise Wo17PersistenceError("WO17_IMMUTABLE_CONFLICT")
            else:
                _write_new_atomic(path, encoded)
        return path

    def _load(self, family: str, identity: str) -> object:
        return _artifact_from_bytes(_read(self._path(family, identity)))

    def _path(self, family: str, identity: str) -> Path:
        if family not in self._FAMILIES or not _component(identity):
            raise Wo17PersistenceError("WO17_ARTIFACT_PATH_INVALID")
        return self._root / family / f"{identity}.json"

    def _current_path(self, subject: str) -> Path:
        return self._alias_path("CURRENT", subject)

    def _failure_path(self, subject: str) -> Path:
        return self._alias_path("LATEST-FAILURE", subject)

    def _alias_path(self, family: str, subject: str) -> Path:
        if not _component(subject):
            raise Wo17PersistenceError("WO17_ARTIFACT_PATH_INVALID")
        digest = sha256(subject.encode("utf-8")).hexdigest().upper()
        return self._root / "current" / f"{family}-WO17-{digest}.json"


def _validate_graph(request: Wo17OperationRequest) -> None:
    snapshot = request.snapshot
    position = request.position
    lineage = snapshot.lineage
    try:
        snapshot.__post_init__()
        position.__post_init__()
        if request.lifecycle is not None:
            request.lifecycle.__post_init__()
        if request.closure is not None:
            request.closure.__post_init__()
        if request.live_exit_attestation is not None:
            request.live_exit_attestation.__post_init__()
        if request.pre_entry_invalidation is not None:
            request.pre_entry_invalidation.__post_init__()
    except (AttributeError, TypeError, ValueError) as error:
        raise Wo17PersistenceError("WO17_GRAPH_CONTRACT_INVALID") from error
    if (
        position.upstream_snapshot != snapshot
        or request.canonical_subject_identity != lineage.canonical_subject_identity
        or request.lifecycle is not None and request.lifecycle.position != position
        or request.closure is not None and request.closure.position != position
        or request.closure is not None
        and request.closure.closure is not None
        and request.closure.closure.position_identity
        != request.closure.position.position_evidence.position_identity  # type: ignore[union-attr]
        or request.live_exit_attestation is not None
        and (
            request.closure is None
            or request.closure.closure is None
            or request.closure.closure.live_exit_attestation_identity
            != request.live_exit_attestation.attestation_identity
        )
        or request.pre_entry_invalidation is not None
        and request.pre_entry_invalidation.upstream_snapshot_identity
        != snapshot.snapshot_identity
    ):
        raise Wo17PersistenceError("WO17_GRAPH_LINEAGE_INVALID")


_ALLOWED_CODEC_MODULES = frozenset(
    {
        "kronos.application.intraday_wo17",
        "kronos.intraday.historical_semantic",
        "kronos.intraday.universe",
        "kronos.intraday.wo13_handoff",
        "kronos.intraday.wo14",
        "kronos.intraday.wo15",
        "kronos.intraday.wo16",
        "kronos.intraday.wo17",
        "kronos.intraday.wo17_closure",
        "kronos.intraday.wo17_lifecycle",
        "kronos.intraday.wo17_persistence",
        "kronos.intraday.wo17_position",
    }
)


def _type_key(value: type) -> str:
    return f"{value.__module__}:{value.__qualname__}"


def _resolve_type(key: object) -> type:
    if type(key) is not str or ":" not in key:
        raise Wo17PersistenceError("WO17_CODEC_TYPE_INVALID")
    module_name, qualname = key.split(":", 1)
    if module_name not in _ALLOWED_CODEC_MODULES or "." in qualname:
        raise Wo17PersistenceError("WO17_CODEC_TYPE_INVALID")
    value = getattr(import_module(module_name), qualname, None)
    if not isinstance(value, type):
        raise Wo17PersistenceError("WO17_CODEC_TYPE_INVALID")
    return value


def _artifact_bytes(value: object) -> bytes:
    core = {
        "artifact_type": _type_key(type(value)),
        "artifact_identity": _artifact_identity(value),
        "artifact": _to_wire(value),
    }
    return _encode({**core, "document_integrity": sha256(_encode(core)).hexdigest()}) + b"\n"


def _artifact_from_bytes(encoded: bytes) -> object:
    try:
        document = json.loads(encoded)
        core = {key: document[key] for key in ("artifact_type", "artifact_identity", "artifact")}
        if set(document) != {*core, "document_integrity"} or document["document_integrity"] != sha256(_encode(core)).hexdigest():
            raise ValueError
        value = _from_wire(document["artifact"])
        if _type_key(type(value)) != document["artifact_type"] or _artifact_identity(value) != document["artifact_identity"]:
            raise ValueError
        value.__post_init__()  # type: ignore[attr-defined]
        return value
    except (AttributeError, KeyError, TypeError, ValueError, json.JSONDecodeError, Wo17ContractError) as error:
        raise Wo17PersistenceError("WO17_ARTIFACT_INTEGRITY_INVALID") from error


def _artifact_identity(value: object) -> str:
    for name in (
        "request_identity", "lineage_identity", "snapshot_identity",
        "state_identity", "position_identity", "observation_identity",
        "attestation_identity", "fact_identity", "assessment_identity",
        "closure_identity", "event_identity", "operation_identity",
        "invalid_identity", "pointer_identity",
    ):
        identity = getattr(value, name, None)
        if type(identity) is str:
            return identity
    raise Wo17PersistenceError("WO17_ARTIFACT_IDENTITY_INVALID")


def _to_wire(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {"__dataclass__": _type_key(type(value)), "fields": {item.name: _to_wire(getattr(value, item.name)) for item in fields(value)}}
    if isinstance(value, StrEnum):
        return {"__enum__": _type_key(type(value)), "value": value.value}
    if isinstance(value, datetime):
        if not _aware(value):
            raise Wo17PersistenceError("WO17_TIMESTAMP_TIMEZONE_REQUIRED")
        return {"__datetime__": value.isoformat(), "zone": getattr(value.tzinfo, "key", None)}
    if isinstance(value, date):
        return {"__date__": value.isoformat()}
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise Wo17PersistenceError("WO17_DECIMAL_INVALID")
        return {"__decimal__": format(value, "f")}
    if isinstance(value, tuple):
        return {"__tuple__": [_to_wire(item) for item in value]}
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise Wo17PersistenceError("WO17_ARTIFACT_ENCODING_INVALID")
        return {key: _to_wire(item) for key, item in value.items()}
    if value is None or type(value) in {str, int, bool}:
        return value
    raise Wo17PersistenceError("WO17_ARTIFACT_ENCODING_INVALID")


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
        enum = _resolve_type(value["__enum__"])
        if not issubclass(enum, StrEnum):
            raise ValueError
        return enum(value["value"])
    if set(value) == {"__dataclass__", "fields"}:
        cls = _resolve_type(value["__dataclass__"])
        raw = value["fields"]
        if not is_dataclass(cls) or type(raw) is not dict:
            raise ValueError
        expected = {item.name for item in fields(cls)}
        if set(raw) != expected:
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
                raise Wo17PersistenceError("WO17_IMMUTABLE_CONFLICT")
    finally:
        temporary.unlink(missing_ok=True)


def _replace_atomic(path: Path, encoded: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    try:
        temporary.write_bytes(encoded)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _read(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise Wo17PersistenceError("WO17_ARTIFACT_UNAVAILABLE") from error


def _encode(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _without(value: object, *names: str) -> dict[str, object]:
    return {item.name: getattr(value, item.name) for item in fields(value) if item.name not in names}


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(canonical_document_bytes(value)).hexdigest().upper()


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _texts(values: Sequence[object]) -> bool:
    return bool(values) and all(type(value) is str and bool(value.strip()) for value in values)


def _all_none(values: Sequence[object]) -> bool:
    return all(value is None for value in values)


def _code(value: object) -> bool:
    return type(value) is str and 2 < len(value) <= 128 and all(item.isupper() or item.isdigit() or item == "_" for item in value)


def _component(value: object) -> bool:
    return type(value) is str and 2 < len(value) <= 256 and all(item.isalnum() or item in "-_.:" for item in value)


__all__ = [name for name in globals() if name.startswith(("WO17_", "Wo17", "Current", "Restored", "DEFAULT_", "create_"))]
