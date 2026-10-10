"""Append-only persistence and atomic current pointers for Intraday WO-09."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from threading import Lock, get_ident, local

from kronos.intraday.visual_reconciliation_v2 import VisualReconciliationOutcome
from kronos.intraday.wo09_readiness import (
    AttentionState, CriterionId, CriterionSnapshot, CriterionState, CurrentnessState,
    HardGate, Monitorability, NextWoHandoff, ReadinessRecord, ReadinessState,
    RequirementRecord, artifact_bytes, create_next_wo_handoff,
)
from kronos.intraday.wo09_machine_readiness import MachineReadinessRecord, SCHEMA_IDENTITY as MACHINE_SCHEMA
from kronos.intraday.wo09_watch import WatchState, Wo09Watch
from kronos.application.intraday_wo09_notifications import Wo09NotificationSource, Wo09NotificationState


DEFAULT_ROOT = Path.home() / "Library" / "Application Support" / "KRONOS" / "evidence" / "intraday" / "wo09-readiness-v1"
POINTER_SCHEMA = "KRONOS-INTRADAY-WO-09-CURRENT-POINTER-V1"


class Wo09PersistenceError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CurrentPointer:
    canonical_subject_identity: str
    readiness_identity: str
    readiness_integrity: str
    currentness: CurrentnessState
    superseded_readiness_identity: str | None
    updated_at: datetime
    integrity_identity: str
    schema_identity: str = POINTER_SCHEMA
    schema_version: str = "1.0.0"

    def __post_init__(self) -> None:
        values = {
            "canonical_subject_identity": self.canonical_subject_identity,
            "readiness_identity": self.readiness_identity,
            "readiness_integrity": self.readiness_integrity,
            "currentness": self.currentness,
            "superseded_readiness_identity": self.superseded_readiness_identity,
            "updated_at": self.updated_at,
            "schema_identity": self.schema_identity,
            "schema_version": self.schema_version,
        }
        if (
            not self.canonical_subject_identity or not self.readiness_identity
            or not self.readiness_integrity or self.updated_at.tzinfo is None
            or type(self.currentness) is not CurrentnessState
            or self.schema_identity != POINTER_SCHEMA or self.schema_version != "1.0.0"
            or self.integrity_identity != _identity("INTEGRITY-INTRADAY-WO09-POINTER-", values)
        ):
            raise ValueError("WO09_CURRENT_POINTER_INVALID")


@dataclass(frozen=True, slots=True)
class Wo09PublicationExpectation:
    """Observed predecessor only; this is never analytical authorization."""
    root_key: Path
    canonical_subject_identity: str
    pointer: CurrentPointer | None


class Wo09PublicationConflict(Wo09PersistenceError):
    failure_stage = "PUBLICATION_CONFLICT"
    failure_reason = "WO09_PUBLICATION_EXPECTATION_CHANGED"

    def __init__(self):
        super().__init__(self.failure_reason)


class Wo09MutationReentry(Wo09PersistenceError):
    def __init__(self):
        super().__init__("WO09_MUTATION_REENTRY_NOT_PERMITTED")


# PROCESS_LOCAL. Strong references prevent controller replacement while a waiter
# exists. The registry mutex is released before waiting on a subject controller.
_MUTATION_CONTROLLERS = {}
_MUTATION_REGISTRY_LOCK = Lock()
_ACTIVE_MUTATION = local()


class _Wo09Mutation:
    """One fixed owner/thread-bound effect inside one outer transaction."""
    def __init__(self, owner, expected):
        self._owner, self._expected = owner, expected
        self._thread = get_ident()
        self._closed = False
        self._used = False
        self._notices = []

    @property
    def notices(self):
        return tuple(self._notices)

    def _begin(self, subject):
        if (self._closed or self._thread != get_ident()
                or getattr(_ACTIVE_MUTATION, "token", None) is not self
                or self._used or subject != self._expected.canonical_subject_identity
                or self._owner.root.resolve() != self._expected.root_key):
            raise Wo09PersistenceError("WO09_MUTATION_TOKEN_INVALID")
        self._owner._compare(self._expected)
        self._used = True  # A failed write cannot be retried through this token.

    def retain_readiness(self, record, requirements):
        self._begin(record.canonical_subject_identity)
        result, notice = self._owner._retain_readiness(record, requirements)
        if notice is not None:
            self._notices.append(self._owner._capture_notice(*notice))
        return result

    def mark_currentness(self, subject, state, *, updated_at):
        self._begin(subject)
        result = self._owner._mark_currentness(subject, state, updated_at=updated_at)
        self._notices.append(self._owner._capture_notice("CURRENTNESS", subject))
        return result

    def retain_handoff(self, handoff):
        self._begin(handoff.canonical_subject_identity)
        self._owner._retain_handoff(handoff)


class Wo09Store:
    def __init__(self, root: Path = DEFAULT_ROOT) -> None:
        self.root = Path(root)
        self.readiness = root / "readiness"
        self.requirements = root / "requirements"
        self.handoffs = root / "handoffs"
        self.current = root / "current"
        self.watches = root / "watches"
        self.notifications = root / "notifications"

    def _validated_pointer(self, subject):
        pointer = self.load_pointer(subject)
        if pointer is not None:
            readiness = self.load_readiness(pointer.readiness_identity)
            if (pointer.canonical_subject_identity != subject
                    or readiness.canonical_subject_identity != subject
                    or readiness.integrity_identity != pointer.readiness_integrity):
                raise Wo09PersistenceError("WO09_RESTORATION_INTEGRITY_MISMATCH")
        return pointer

    def expectation(self, subject: str) -> Wo09PublicationExpectation:
        if type(subject) is not str or not subject:
            raise Wo09PersistenceError("WO09_PUBLICATION_SUBJECT_INVALID")
        return Wo09PublicationExpectation(self.root.resolve(), subject, self._validated_pointer(subject))

    def _check_expectation(self, expected):
        if (type(expected) is not Wo09PublicationExpectation
                or expected.root_key != self.root.resolve()
                or type(expected.canonical_subject_identity) is not str
                or not expected.canonical_subject_identity
                or expected.pointer is not None and type(expected.pointer) is not CurrentPointer):
            raise Wo09PersistenceError("WO09_PUBLICATION_EXPECTATION_INVALID")
        if expected.pointer is not None:
            expected.pointer.__post_init__()
            if expected.pointer.canonical_subject_identity != expected.canonical_subject_identity:
                raise Wo09PersistenceError("WO09_PUBLICATION_EXPECTATION_INVALID")

    def _compare(self, expected):
        self._check_expectation(expected)
        # Corruption is checked before equality and remains an integrity failure.
        if self._validated_pointer(expected.canonical_subject_identity) != expected.pointer:
            raise Wo09PublicationConflict()

    @contextmanager
    def transaction(self, *, expected: Wo09PublicationExpectation):
        if getattr(_ACTIVE_MUTATION, "token", None) is not None:
            raise Wo09MutationReentry()
        self._check_expectation(expected)
        key = (expected.root_key, expected.canonical_subject_identity)
        with _MUTATION_REGISTRY_LOCK:
            controller = _MUTATION_CONTROLLERS.setdefault(key, Lock())
        with controller:
            token = _Wo09Mutation(self, expected)
            _ACTIVE_MUTATION.token = token
            try:
                self._compare(expected)
                yield token
            finally:
                token._closed = True
                _ACTIVE_MUTATION.token = None

    def _capture_notice(self, kind, identity):
        # Ephemeral committed reference, not a persisted schema or permission.
        return (kind, identity, tuple(
            (attribute, getattr(self, attribute, None), failure)
            for attribute, failure in (
                ("notification_listener", "NOTIFICATION_PROJECTION_UNAVAILABLE"),
                ("journal_listener", "JOURNAL_PROJECTION_UNAVAILABLE"),
            )
        ))

    def notify_publication(self, notices):
        """Dispatch captured committed references after all owner guards release."""
        for kind, identity, callbacks in notices:
            for attribute, listener, failure in callbacks:
                if listener is not None:
                    try:
                        listener(kind, identity)
                    except Exception:
                        setattr(self, attribute.replace("listener", "failure"), failure)

    def retain(self, record: ReadinessRecord, requirements: tuple[RequirementRecord, ...],
               *, expected: Wo09PublicationExpectation) -> CurrentPointer:
        with self.transaction(expected=expected) as mutation:
            result = mutation.retain_readiness(record, requirements)
        self.notify_publication(mutation.notices)
        return result

    def _retain_readiness(self, record, requirements):
        if type(record) not in {ReadinessRecord, MachineReadinessRecord} or len(requirements) != 5:
            raise Wo09PersistenceError("WO09_PERSISTENCE_INPUT_INVALID")
        record.__post_init__()
        if tuple(item.criterion.criterion_id for item in requirements) != tuple(CriterionId):
            raise Wo09PersistenceError("WO09_REQUIREMENT_SET_INVALID")
        for requirement in requirements:
            requirement.__post_init__()
            if requirement.readiness_identity != record.readiness_identity:
                raise Wo09PersistenceError("WO09_REQUIREMENT_SET_INVALID")
        self._retain(self.readiness / f"{record.readiness_identity}.json", artifact_bytes(record))
        for requirement in requirements:
            self._retain(self.requirements / f"{requirement.requirement_identity}.json", artifact_bytes(requirement))
        prior = self.load_pointer(record.canonical_subject_identity)
        if prior is not None and prior.readiness_identity == record.readiness_identity:
            if prior.readiness_integrity != record.integrity_identity:
                raise Wo09PersistenceError("WO09_CURRENT_POINTER_CONFLICT")
            return prior, None
        if prior is not None and record.created_at <= prior.updated_at:
            raise Wo09PersistenceError("WO09_NON_FORWARD_SUPERSESSION")
        pointer = create_pointer(record, currentness=CurrentnessState.CURRENT,
            superseded=None if prior is None else prior.readiness_identity, updated_at=record.created_at)
        self._atomic(self.current / f"{_safe(record.canonical_subject_identity)}.json", artifact_bytes(pointer))
        return pointer, ("READINESS", record.readiness_identity)

    def retain_handoff(self, handoff: NextWoHandoff, *, expected: Wo09PublicationExpectation) -> None:
        with self.transaction(expected=expected) as mutation:
            mutation.retain_handoff(handoff)

    def _retain_handoff(self, handoff):
        if type(handoff) is not NextWoHandoff:
            raise Wo09PersistenceError("WO09_HANDOFF_PERSISTENCE_INPUT_INVALID")
        handoff.__post_init__()
        pointer = self._validated_pointer(handoff.canonical_subject_identity)
        if pointer is None:
            raise Wo09PersistenceError("WO09_HANDOFF_CURRENT_POINTER_REQUIRED")
        readiness = self.load_readiness(pointer.readiness_identity)
        bound = create_next_wo_handoff(readiness, created_at=handoff.created_at,
            current_readiness_identity=pointer.readiness_identity,
            current_pointer_integrity=pointer.integrity_identity,
            currentness=pointer.currentness, superseded_readiness_identity=pointer.superseded_readiness_identity,
            first_five_of_five_at=handoff.first_five_of_five_at)
        if bound != handoff:
            raise Wo09PersistenceError("WO09_HANDOFF_SOURCE_BINDING_INVALID")
        self._retain(self.handoffs / f"{handoff.handoff_identity}.json", artifact_bytes(handoff))

    def load_handoff(self, identity: str) -> NextWoHandoff:
        return _handoff(json.loads((self.handoffs / f"{identity}.json").read_text()))

    def retain_watch(self, watch: Wo09Watch) -> None:
        if type(watch) is not Wo09Watch:
            raise Wo09PersistenceError("WO09_WATCH_PERSISTENCE_INPUT_INVALID")
        self._retain(self.watches / f"{watch.watch_identity}-{watch.integrity_identity}.json", artifact_bytes(watch))

    def load_watches(self, readiness_identity: str | None = None) -> tuple[Wo09Watch, ...]:
        latest: dict[str, Wo09Watch] = {}
        for path in sorted(self.watches.glob("*.json")):
            item = _watch(json.loads(path.read_text()))
            if readiness_identity is None or item.readiness_identity == readiness_identity:
                prior = latest.get(item.watch_identity)
                if prior is None or (item.last_transition_at, item.integrity_identity) > (prior.last_transition_at, prior.integrity_identity):
                    latest[item.watch_identity] = item
        return tuple(sorted(latest.values(), key=lambda item: item.watch_identity))

    def retain_notification(self, source: Wo09NotificationSource) -> None:
        if type(source) is not Wo09NotificationSource:
            raise Wo09PersistenceError("WO09_NOTIFICATION_PERSISTENCE_INPUT_INVALID")
        self._retain(self.notifications / f"{source.source_identity}-{source.source_integrity}.json", artifact_bytes(source))

    def load_notifications(self) -> tuple[Wo09NotificationSource, ...]:
        latest: dict[str, Wo09NotificationSource] = {}
        for path in sorted(self.notifications.glob("*.json")):
            item = _notification(json.loads(path.read_text()))
            prior = latest.get(item.canonical_subject_identity)
            if prior is None or (item.created_at, item.source_identity) > (prior.created_at, prior.source_identity):
                latest[item.canonical_subject_identity] = item
        return tuple(sorted(latest.values(), key=lambda item: item.source_identity))

    def mark_currentness(self, subject: str, state: CurrentnessState, *, updated_at: datetime,
                         expected: Wo09PublicationExpectation) -> CurrentPointer:
        with self.transaction(expected=expected) as mutation:
            result = mutation.mark_currentness(subject, state, updated_at=updated_at)
        self.notify_publication(mutation.notices)
        return result

    def _mark_currentness(self, subject: str, state: CurrentnessState, *, updated_at: datetime) -> CurrentPointer:
        prior = self.load_pointer(subject)
        if prior is None:
            raise Wo09PersistenceError("WO09_CURRENT_POINTER_NOT_FOUND")
        if (
            state is CurrentnessState.CURRENT
            or updated_at.tzinfo is None
            or updated_at <= prior.updated_at
        ):
            raise Wo09PersistenceError("WO09_CURRENTNESS_TRANSITION_INVALID")
        record = self.load_readiness(prior.readiness_identity)
        pointer = create_pointer(record, currentness=state,
                                 superseded=prior.superseded_readiness_identity,
                                 updated_at=updated_at)
        self._atomic(self.current / f"{_safe(subject)}.json", artifact_bytes(pointer))
        return pointer

    def load_readiness(self, identity: str) -> ReadinessRecord:
        return _readiness(json.loads((self.readiness / f"{identity}.json").read_text()))

    def load_requirements(self, readiness_identity: str) -> tuple[RequirementRecord, ...]:
        values = []
        for path in sorted(self.requirements.glob("*.json")):
            item = _requirement(json.loads(path.read_text()))
            if item.readiness_identity == readiness_identity:
                values.append(item)
        return tuple(sorted(values, key=lambda item: item.criterion.criterion_id.value))

    def load_pointer(self, subject: str) -> CurrentPointer | None:
        path = self.current / f"{_safe(subject)}.json"
        return None if not path.exists() else _pointer(json.loads(path.read_text()))

    def restore_current(self) -> tuple[tuple[CurrentPointer, ReadinessRecord], ...]:
        restored = []
        for path in sorted(self.current.glob("*.json")):
            pointer = _pointer(json.loads(path.read_text()))
            record = self.load_readiness(pointer.readiness_identity)
            if record.integrity_identity != pointer.readiness_integrity:
                raise Wo09PersistenceError("WO09_RESTORATION_INTEGRITY_MISMATCH")
            restored.append((pointer, record))
        return tuple(restored)

    @staticmethod
    def _retain(path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("xb") as target:
                target.write(payload); target.flush(); os.fsync(target.fileno())
            os.chmod(path, 0o600)
        except FileExistsError:
            if path.read_bytes() != payload:
                raise Wo09PersistenceError("WO09_IMMUTABILITY_CONFLICT")

    @staticmethod
    def _atomic(path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as target:
            target.write(payload); target.flush(); os.fsync(target.fileno()); name = target.name
        os.chmod(name, 0o600)
        os.replace(name, path)


def create_pointer(record: ReadinessRecord, *, currentness: CurrentnessState,
                   superseded: str | None, updated_at: datetime) -> CurrentPointer:
    values = {
        "canonical_subject_identity": record.canonical_subject_identity,
        "readiness_identity": record.readiness_identity,
        "readiness_integrity": record.integrity_identity,
        "currentness": currentness,
        "superseded_readiness_identity": superseded,
        "updated_at": updated_at,
        "schema_identity": POINTER_SCHEMA,
        "schema_version": "1.0.0",
    }
    return CurrentPointer(integrity_identity=_identity("INTEGRITY-INTRADAY-WO09-POINTER-", values), **values)


def _criterion(value: dict[str, object]) -> CriterionSnapshot:
    return CriterionSnapshot(
        criterion_id=CriterionId(value["criterion_id"]), category=str(value["category"]),
        state=CriterionState(value["state"]), current_value=value.get("current_value"),
        required_value=value.get("required_value"), gap=str(value["gap"]), unit=value.get("unit"),
        authority=str(value["authority"]), source_evidence_identity=str(value["source_evidence_identity"]),
        observation_boundary=datetime.fromisoformat(str(value["observation_boundary"])),
        monitorability=tuple(Monitorability(item) for item in value["monitorability"]),
        next_reassessment_trigger=str(value["next_reassessment_trigger"]),
        reason_codes=tuple(value.get("reason_codes", ())),
    )


def _readiness(value: dict[str, object]) -> ReadinessRecord:
    data = dict(value)
    machine = data.get("schema_identity") == MACHINE_SCHEMA
    if not machine:
        data["wo07f_outcome"] = VisualReconciliationOutcome(data["wo07f_outcome"])
    data.update(
        criteria=tuple(_criterion(item) for item in data["criteria"]),
        hard_gate=HardGate(data["hard_gate"]), readiness_state=ReadinessState(data["readiness_state"]),
        attention_state=AttentionState(data["attention_state"]), currentness=CurrentnessState(data["currentness"]),
        analysis_boundary=datetime.fromisoformat(data["analysis_boundary"]),
        created_at=datetime.fromisoformat(data["created_at"]),
        machine_evidence_identities=tuple(data["machine_evidence_identities"]),
        source_provenance=tuple(data["source_provenance"]),
    )
    return MachineReadinessRecord(**data) if machine else ReadinessRecord(**data)


def _requirement(value: dict[str, object]) -> RequirementRecord:
    data = dict(value)
    data.update(criterion=_criterion(data["criterion"]),
                last_transition_at=datetime.fromisoformat(data["last_transition_at"]),
                lifecycle_state=CurrentnessState(data["lifecycle_state"]))
    return RequirementRecord(**data)


def _pointer(value: dict[str, object]) -> CurrentPointer:
    data = dict(value)
    data.update(currentness=CurrentnessState(data["currentness"]),
                updated_at=datetime.fromisoformat(data["updated_at"]))
    return CurrentPointer(**data)


def _handoff(value: dict[str, object]) -> NextWoHandoff:
    data = dict(value)
    data.update(
        currentness=CurrentnessState(data["currentness"]),
        wo07f_outcome=VisualReconciliationOutcome(data["wo07f_outcome"]),
        criteria=tuple(_criterion(item) for item in data["criteria"]),
        hard_gate=HardGate(data["hard_gate"]),
        readiness_state=ReadinessState(data["readiness_state"]),
        analysis_boundary=datetime.fromisoformat(data["analysis_boundary"]),
        created_at=datetime.fromisoformat(data["created_at"]),
        first_five_of_five_at=(
            None if data["first_five_of_five_at"] is None
            else datetime.fromisoformat(data["first_five_of_five_at"])
        ),
        machine_evidence_identities=tuple(data["machine_evidence_identities"]),
    )
    return NextWoHandoff(**data)


def _watch(value: dict[str, object]) -> Wo09Watch:
    data = dict(value)
    data.update(criterion_id=CriterionId(data["criterion_id"]), state=WatchState(data["state"]),
                activated_at=datetime.fromisoformat(data["activated_at"]),
                last_transition_at=datetime.fromisoformat(data["last_transition_at"]))
    return Wo09Watch(**data)


def _notification(value: dict[str, object]) -> Wo09NotificationSource:
    data = dict(value)
    data.update(readiness_state=ReadinessState(data["readiness_state"]),
                state=Wo09NotificationState(data["state"]),
                created_at=datetime.fromisoformat(data["created_at"]))
    return Wo09NotificationSource(**data)


def _safe(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(artifact_bytes(value)).hexdigest().upper()


__all__ = ["CurrentPointer", "Wo09PersistenceError", "Wo09Store", "create_pointer"]
