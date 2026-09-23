"""Durable application ownership for Swing V3 bulk Answer imports.

The records in this module are runtime/work-control state.  Accepted analytical
evidence remains owned by :mod:`kronos.swing.v1.review_evidence_store`.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import fcntl
from hashlib import sha256
import os
from pathlib import Path
import re
from threading import Event, RLock, Thread
import tempfile
from typing import Callable

from kronos.swing.v1.review_evidence_binding import (
    ReviewEvidenceError,
    canonical,
    strict_json,
)


BULK_IMPORT_SCHEMA = "KRONOS-SWING-V3-BULK-ANSWER-IMPORT-V1"
BULK_IMPORT_VERSION = "1.0"
DEFAULT_BULK_IMPORT_ROOT = (
    Path.home() / "Library" / "Application Support" / "KRONOS"
    / "runtime" / "swing-bulk-import-v1"
)
_BATCH_PREFIX = "SWING-BULK-ANSWER-"
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_IDENTITY = re.compile(r"SWING-BULK-ANSWER-[0-9A-F]{64}\Z")
_TERMINAL = {"VALIDATION_FAILED", "COMPLETED", "COMPLETED_WITH_FAILURE", "FAILED"}
_BATCH_STATES = {
    "ADMITTED", "VALIDATING", "VALIDATION_FAILED", "ACCEPTING", "ACCEPTED",
    "DOWNSTREAM_RUNNING", "COMPLETED", "COMPLETED_WITH_FAILURE", "FAILED",
}
_CANDIDATE_STATES = {"QUEUED", "RUNNING", "SUCCEEDED", "FAILED"}
_SAFE_FAILURES = {
    "REVIEW_ACCEPTANCE_INCOMPLETE", "REVIEW_ANSWER_IDENTITY_CONFLICT",
    "REVIEW_ARTIFACT_DIGEST_MISMATCH", "REVIEW_BINDING_STALE",
    "REVIEW_CONTRACT_UNSUPPORTED", "REVIEW_PRECONDITION_INVALID",
    "REVIEW_PREDECESSOR_INVALID", "REVIEW_PUBLICATION_CONFLICT",
    "REVIEW_REQUEST_MISMATCH", "REVIEW_DOWNSTREAM_PROCESSING_FAILED",
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _hash(payload: bytes) -> str:
    return sha256(payload).hexdigest()


def _failure(error: BaseException) -> str:
    value = str(error)
    return value if value in _SAFE_FAILURES else "REVIEW_INTAKE_UNAVAILABLE"


def _closed(value: object, fields: set[str], reason: str) -> dict:
    if type(value) is not dict or set(value) != fields:
        raise ValueError(reason)
    return value


class SwingBulkImportStore:
    """Exact local store for staged bytes and attributable batch progress."""

    _FIELDS = {
        "schema", "version", "batch_identity", "request_identity",
        "review_pack_identity", "answer_sha256", "answer_relative_path",
        "extracted_sha256", "extracted_relative_path",
        "market", "expected", "received_at", "state", "transitions",
        "timings", "commit_identity", "candidates", "failure",
        "integrity_sha256",
    }

    def __init__(self, root: Path = DEFAULT_BULK_IMPORT_ROOT) -> None:
        root = Path(root).expanduser()
        if not root.is_absolute() or root == Path("/"):
            raise ValueError("SWING_BULK_IMPORT_ROOT_INVALID")
        self.root = root
        self._lock = RLock()
        for relative in ("batches", "answers", "extracted", "requests", "leases"):
            path = root / relative
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
            try:
                os.chmod(path, 0o700)
            except OSError:
                pass

    @staticmethod
    def batch_identity(request_identity: str, review_pack_identity: str,
                       answer_sha256: str) -> str:
        if not all(type(value) is str and value for value in (
                request_identity, review_pack_identity)) or _DIGEST.fullmatch(
                    answer_sha256) is None:
            raise ValueError("SWING_BULK_IMPORT_IDENTITY_INVALID")
        material = canonical([
            BULK_IMPORT_SCHEMA, BULK_IMPORT_VERSION, request_identity,
            review_pack_identity, answer_sha256,
        ])
        return _BATCH_PREFIX + _hash(material).upper()

    @staticmethod
    def _request_key(request_identity: str, review_pack_identity: str) -> str:
        return _hash(canonical([BULK_IMPORT_SCHEMA, request_identity,
                                review_pack_identity]))

    def _batch_path(self, identity: str) -> Path:
        if _IDENTITY.fullmatch(identity) is None:
            raise ValueError("SWING_BULK_IMPORT_IDENTITY_INVALID")
        return self.root / "batches" / (identity + ".json")

    def _atomic(self, path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".prepared-",
                                         delete=False) as stream:
            pending = Path(stream.name)
            os.chmod(pending, 0o600)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.replace(pending, path)
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            pending.unlink(missing_ok=True)

    def _immutable(self, path: Path, payload: bytes) -> None:
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            if path.is_symlink() or path.read_bytes() != payload:
                raise ValueError("SWING_BULK_IMPORT_CONFLICT")
            return
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())

    @staticmethod
    def _sealed(value: dict) -> bytes:
        body = {key: item for key, item in value.items()
                if key != "integrity_sha256"}
        body["integrity_sha256"] = _hash(canonical(body))
        return canonical(body)

    @classmethod
    def _validate(cls, payload: bytes) -> dict:
        value = _closed(strict_json(payload), cls._FIELDS,
                        "SWING_BULK_IMPORT_RECORD_INVALID")
        if (value["schema"] != BULK_IMPORT_SCHEMA
                or value["version"] != BULK_IMPORT_VERSION
                or _IDENTITY.fullmatch(value["batch_identity"]) is None
                or value["state"] not in _BATCH_STATES
                or _DIGEST.fullmatch(value["answer_sha256"]) is None
                or type(value["transitions"]) is not list
                or not value["transitions"]
                or type(value["timings"]) is not dict
                or type(value["candidates"]) is not list):
            raise ValueError("SWING_BULK_IMPORT_RECORD_INVALID")
        expected = _hash(canonical({key: item for key, item in value.items()
                                    if key != "integrity_sha256"}))
        if value["integrity_sha256"] != expected:
            raise ValueError("SWING_BULK_IMPORT_RECORD_INVALID")
        for transition in value["transitions"]:
            _closed(transition, {"state", "recorded_at", "reason"},
                    "SWING_BULK_IMPORT_RECORD_INVALID")
            if transition["state"] not in _BATCH_STATES:
                raise ValueError("SWING_BULK_IMPORT_RECORD_INVALID")
        for candidate in value["candidates"]:
            _closed(candidate, {
                "canonical_instrument", "receipt_identity", "attempt_identity",
                "state", "transitions", "downstream_state", "failure",
                "v2_retained_at",
            }, "SWING_BULK_IMPORT_RECORD_INVALID")
            if (candidate["state"] not in _CANDIDATE_STATES
                    or type(candidate["transitions"]) is not list
                    or not candidate["transitions"]):
                raise ValueError("SWING_BULK_IMPORT_RECORD_INVALID")
            for transition in candidate["transitions"]:
                _closed(transition, {"state", "recorded_at", "reason"},
                        "SWING_BULK_IMPORT_RECORD_INVALID")
                if transition["state"] not in _CANDIDATE_STATES:
                    raise ValueError("SWING_BULK_IMPORT_RECORD_INVALID")
        return value

    def admit(self, *, request_identity: str, review_pack_identity: str,
              answer: bytes, market: str, expected: dict, received_at: str) -> tuple[dict, bool]:
        if (type(answer) is not bytes or not answer.startswith(b"%PDF-")
                or not 0 < len(answer) <= 128 * 1024 * 1024
                or market not in {"NSE", "MCX"} or type(expected) is not dict
                or not expected):
            raise ValueError("SWING_BULK_IMPORT_ADMISSION_INVALID")
        answer_hash = _hash(answer)
        identity = self.batch_identity(request_identity, review_pack_identity,
                                       answer_hash)
        request_key = self._request_key(request_identity, review_pack_identity)
        pointer_path = self.root / "requests" / (request_key + ".json")
        answer_path = self.root / "answers" / (identity + ".pdf")
        record_path = self._batch_path(identity)
        lock_path = self.root / ".admission.lock"
        lock_path.touch(mode=0o600, exist_ok=True)
        descriptor = os.open(lock_path, os.O_RDWR | os.O_NOFOLLOW)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            with self._lock:
                if pointer_path.exists():
                    pointer = _closed(strict_json(pointer_path.read_bytes()),
                        {"batch_identity", "answer_sha256", "integrity_sha256"},
                        "SWING_BULK_IMPORT_RECORD_INVALID")
                    body = {key: item for key, item in pointer.items()
                            if key != "integrity_sha256"}
                    if pointer["integrity_sha256"] != _hash(canonical(body)):
                        raise ValueError("SWING_BULK_IMPORT_RECORD_INVALID")
                    if (pointer["batch_identity"] != identity
                            or pointer["answer_sha256"] != answer_hash):
                        raise ReviewEvidenceError("REVIEW_ANSWER_IDENTITY_CONFLICT")
                    record = self.load(identity)
                    if answer_path.read_bytes() != answer:
                        raise ValueError("SWING_BULK_IMPORT_CONFLICT")
                    return record, False
                self._immutable(answer_path, answer)
                record = {
                    "schema": BULK_IMPORT_SCHEMA,
                    "version": BULK_IMPORT_VERSION,
                    "batch_identity": identity,
                    "request_identity": request_identity,
                    "review_pack_identity": review_pack_identity,
                    "answer_sha256": answer_hash,
                    "answer_relative_path": str(answer_path.relative_to(self.root)),
                    "extracted_sha256": None,
                    "extracted_relative_path": None,
                    "market": market,
                    "expected": deepcopy(expected),
                    "received_at": received_at,
                    "state": "ADMITTED",
                    "transitions": [{"state": "ADMITTED", "recorded_at": received_at,
                                     "reason": None}],
                    "timings": {"request_admitted_at": received_at},
                    "commit_identity": None,
                    "candidates": [],
                    "failure": None,
                }
                self._atomic(record_path, self._sealed(record))
                pointer = {"batch_identity": identity,
                           "answer_sha256": answer_hash}
                pointer["integrity_sha256"] = _hash(canonical(pointer))
                self._immutable(pointer_path, canonical(pointer))
                return self.load(identity), True
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def existing_expected(self, market: str, expected: dict) -> dict | None:
        """Resolve the unique retained batch for one exact mutation fence."""
        if (market not in {"NSE", "MCX"} or type(expected) is not dict
                or not expected):
            raise ValueError("SWING_BULK_IMPORT_ADMISSION_INVALID")
        matches = []
        for path in sorted((self.root / "batches").glob(_BATCH_PREFIX + "*.json")):
            record = self.load(path.stem)
            if record["market"] == market and record["expected"] == expected:
                matches.append(record)
        if len(matches) > 1:
            raise ValueError("SWING_BULK_IMPORT_RECORD_INVALID")
        return None if not matches else matches[0]

    def exact_existing(self, market: str, expected: dict, answer: bytes) -> dict | None:
        """Resolve an exact admitted request without reopening its mutation fence."""
        if (type(answer) is not bytes or not answer.startswith(b"%PDF-")
                or not 0 < len(answer) <= 128 * 1024 * 1024):
            raise ValueError("SWING_BULK_IMPORT_ADMISSION_INVALID")
        record = self.existing_expected(market, expected)
        return (record if record is not None
                and record["answer_sha256"] == _hash(answer) else None)

    def load(self, identity: str) -> dict:
        path = self._batch_path(identity)
        payload = path.read_bytes()
        value = self._validate(payload)
        if value["batch_identity"] != identity:
            raise ValueError("SWING_BULK_IMPORT_RECORD_INVALID")
        answer = self.root / value["answer_relative_path"]
        if (answer.is_symlink() or not answer.is_file()
                or _hash(answer.read_bytes()) != value["answer_sha256"]):
            raise ValueError("SWING_BULK_IMPORT_STAGED_ANSWER_INVALID")
        if (value["extracted_sha256"] is None) != (value["extracted_relative_path"] is None):
            raise ValueError("SWING_BULK_IMPORT_RECORD_INVALID")
        if value["extracted_sha256"] is not None:
            if _DIGEST.fullmatch(value["extracted_sha256"]) is None:
                raise ValueError("SWING_BULK_IMPORT_RECORD_INVALID")
            extracted = self.root / value["extracted_relative_path"]
            if (extracted.is_symlink() or not extracted.is_file()
                    or _hash(extracted.read_bytes()) != value["extracted_sha256"]):
                raise ValueError("SWING_BULK_IMPORT_EXTRACTED_ANSWER_INVALID")
        return value

    def answer(self, record: dict) -> bytes:
        validated = self.load(record["batch_identity"])
        return (self.root / validated["answer_relative_path"]).read_bytes()

    def extracted(self, record: dict) -> bytes | None:
        validated = self.load(record["batch_identity"])
        relative = validated["extracted_relative_path"]
        if relative is not None:
            return (self.root / relative).read_bytes()
        orphan = self.root / "extracted" / (record["batch_identity"] + ".json")
        if orphan.is_file() and not orphan.is_symlink():
            payload = orphan.read_bytes()
            self.retain_extracted(record["batch_identity"], payload)
            return payload
        return None

    def retain_extracted(self, identity: str, payload: bytes) -> dict:
        if type(payload) is not bytes or not payload:
            raise ValueError("SWING_BULK_IMPORT_EXTRACTED_ANSWER_INVALID")
        digest = _hash(payload)
        path = self.root / "extracted" / (identity + ".json")
        self._immutable(path, payload)

        def mutate(value):
            if value["extracted_sha256"] not in {None, digest}:
                raise ValueError("SWING_BULK_IMPORT_EXTRACTED_ANSWER_INVALID")
            value["extracted_sha256"] = digest
            value["extracted_relative_path"] = str(path.relative_to(self.root))

        return self.update(identity, mutate)

    def list_incomplete(self) -> tuple[str, ...]:
        values = []
        for path in sorted((self.root / "batches").glob(_BATCH_PREFIX + "*.json")):
            record = self.load(path.stem)
            retry_pending = (
                record["state"] == "COMPLETED_WITH_FAILURE"
                and any(item["state"] == "QUEUED" for item in record["candidates"])
            )
            if record["state"] not in _TERMINAL or retry_pending:
                values.append((record["received_at"], record["batch_identity"]))
        return tuple(identity for _, identity in sorted(values))

    def latest(self) -> dict | None:
        values = [self.load(path.stem) for path in
                  sorted((self.root / "batches").glob(_BATCH_PREFIX + "*.json"))]
        return None if not values else max(values, key=lambda item: item["received_at"])

    def update(self, identity: str, mutate: Callable[[dict], None]) -> dict:
        with self._lock:
            value = self.load(identity)
            mutate(value)
            self._atomic(self._batch_path(identity), self._sealed(value))
            return self.load(identity)

    def transition(self, identity: str, state: str, *, reason: str | None = None,
                   timings: dict | None = None) -> dict:
        if state not in _BATCH_STATES:
            raise ValueError("SWING_BULK_IMPORT_STATE_INVALID")
        def mutate(value):
            if value["state"] != state:
                at = _now()
                value["state"] = state
                value["transitions"].append({"state": state, "recorded_at": at,
                                             "reason": reason})
            if timings:
                value["timings"].update(timings)
            value["failure"] = reason
        return self.update(identity, mutate)

    def acceptance(self, identity: str, commit) -> dict:
        def mutate(value):
            candidates = []
            for receipt in commit.receipts:
                instrument = receipt.binding.value["canonical_instrument"]
                attempt = _hash(canonical([identity, commit.identity,
                                           receipt.receipt_id, instrument]))
                candidates.append({
                    "canonical_instrument": instrument,
                    "receipt_identity": receipt.receipt_id,
                    "attempt_identity": attempt,
                    "state": "QUEUED",
                    "transitions": [{"state": "QUEUED", "recorded_at": _now(),
                                     "reason": None}],
                    "downstream_state": None,
                    "failure": None,
                    "v2_retained_at": None,
                })
            value["commit_identity"] = commit.identity
            value["candidates"] = candidates
            value["state"] = "ACCEPTED"
            at = _now()
            value["transitions"].append({"state": "ACCEPTED", "recorded_at": at,
                                         "reason": None})
            value["timings"]["acceptance_committed_at"] = at
            value["failure"] = None
        return self.update(identity, mutate)

    def candidate(self, identity: str, receipt_identity: str, state: str, *,
                  downstream_state: str | None = None, reason: str | None = None,
                  v2_retained: bool = False) -> dict:
        if state not in _CANDIDATE_STATES:
            raise ValueError("SWING_BULK_IMPORT_STATE_INVALID")
        def mutate(value):
            matches = [item for item in value["candidates"]
                       if item["receipt_identity"] == receipt_identity]
            if len(matches) != 1:
                raise ValueError("SWING_BULK_IMPORT_RECORD_INVALID")
            item = matches[0]
            at = _now()
            if item["state"] != state:
                item["state"] = state
                item["transitions"].append({"state": state, "recorded_at": at,
                                             "reason": reason})
            item["downstream_state"] = downstream_state
            item["failure"] = reason
            if v2_retained:
                item["v2_retained_at"] = at
            value["timings"]["candidate:" + item["canonical_instrument"]
                             + ":" + state.lower()] = at
        return self.update(identity, mutate)

    def lease(self, identity: str):
        path = self.root / "leases" / (identity + ".lock")
        path.touch(mode=0o600, exist_ok=True)
        descriptor = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(descriptor)
            return None
        return descriptor


class SwingBulkImportOwner:
    """One tracked runtime worker over durable admitted batch records."""

    def __init__(self, store: SwingBulkImportStore, intake, *,
                 clock: Callable[[], str] = _now,
                 completion: Callable[[], None] | None = None) -> None:
        if (type(store) is not SwingBulkImportStore or not callable(clock)
                or not callable(getattr(intake, "bulk_admission", None))
                or not callable(getattr(intake, "accept_answer", None))
                or not callable(getattr(intake, "handoff", None))
                or (completion is not None and not callable(completion))):
            raise TypeError("SWING_BULK_IMPORT_OWNER_INVALID")
        self.store = store
        self.intake = intake
        self._clock = clock
        self._completion = completion
        self._wake = Event()
        self._stop = Event()
        self._thread: Thread | None = None
        self._status_lock = RLock()
        self._active_identity: str | None = None

    def start(self) -> None:
        if self._thread is not None:
            raise ValueError("SWING_BULK_IMPORT_WORKER_ALREADY_STARTED")
        self._thread = Thread(target=self._run, name="kronos-swing-bulk-import",
                              daemon=True)
        self._thread.start()
        self._wake.set()

    def close(self) -> None:
        self._stop.set()
        self._wake.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=30)
            if thread.is_alive():
                raise RuntimeError("SWING_BULK_IMPORT_WORKER_DID_NOT_STOP")

    def admit(self, market: str, expected: dict, answer: bytes) -> tuple[dict, bool]:
        existing = self.store.exact_existing(market, expected, answer)
        if existing is not None:
            return existing, False
        descriptor = self.intake.bulk_admission(market, expected)
        record, created = self.store.admit(
            request_identity=descriptor["request_identity"],
            review_pack_identity=descriptor["review_pack_identity"],
            answer=answer, market=market, expected=expected,
            received_at=self._clock(),
        )
        self._wake.set()
        return record, created

    def admit_from_directory(self, market: str, expected: dict) -> tuple[dict, bool]:
        existing = self.store.existing_expected(market, expected)
        if existing is not None:
            answer = self.intake.answer_bytes_for_review_pack(
                existing["review_pack_identity"]
            )
            if _hash(answer) != existing["answer_sha256"]:
                raise ReviewEvidenceError("REVIEW_ANSWER_IDENTITY_CONFLICT")
            return existing, False
        return self.admit(market, expected,
                          self.intake.answer_bytes_from_directory(market, expected))

    def status(self, identity: str | None = None) -> dict | None:
        value = self.store.latest() if identity is None else self.store.load(identity)
        return None if value is None else deepcopy(value)

    def presentation(self, identity: str | None = None) -> dict | None:
        value = self.status(identity)
        if value is None:
            return None
        return {
            "batch_identity": value["batch_identity"],
            "request_identity": value["request_identity"],
            "review_pack_identity": value["review_pack_identity"],
            "received_at": value["received_at"],
            "state": value["state"],
            "failure": value["failure"],
            "timings": value["timings"],
            "candidates": [{
                "canonical_instrument": item["canonical_instrument"],
                "state": item["state"],
                "downstream_state": item["downstream_state"],
                "failure": item["failure"],
                "transitions": item["transitions"],
            } for item in value["candidates"]],
            "status_location": "/swing/v1/bulk-import-status?batch="
                               + value["batch_identity"],
        }

    def retry_candidate(self, identity: str, canonical_instrument: str) -> dict:
        """Explicit governed retry; never invoked by refresh or startup."""
        def mutate(value):
            if value["state"] != "COMPLETED_WITH_FAILURE":
                raise ValueError("SWING_BULK_IMPORT_RETRY_NOT_AVAILABLE")
            matches = [item for item in value["candidates"]
                       if item["canonical_instrument"] == canonical_instrument]
            if len(matches) != 1 or matches[0]["state"] != "FAILED":
                raise ValueError("SWING_BULK_IMPORT_RETRY_NOT_AVAILABLE")
            item = matches[0]
            at = self._clock()
            item["state"] = "QUEUED"
            item["failure"] = None
            item["attempt_identity"] = _hash(canonical([
                identity, item["receipt_identity"], len(item["transitions"]),
                "GOVERNED_RETRY",
            ]))
            item["transitions"].append({"state": "QUEUED", "recorded_at": at,
                                         "reason": "GOVERNED_RETRY"})
            value["timings"]["retry_requested_at"] = at
        result = self.store.update(identity, mutate)
        self._wake.set()
        return result

    def work_status(self) -> dict:
        thread = self._thread
        latest = self.status()
        with self._status_lock:
            active = self._active_identity
        return {
            "state": ("STOPPED" if thread is None or not thread.is_alive() else
                      "PROCESSING" if active is not None else "IDLE"),
            "owned_workers": int(thread is not None and thread.is_alive()),
            "batch_active": active is not None,
            "latest_batch_identity": None if latest is None else latest["batch_identity"],
            "latest_batch_state": None if latest is None else latest["state"],
        }

    def _run(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(0.5)
            self._wake.clear()
            if self._stop.is_set():
                break
            try:
                identities = self.store.list_incomplete()
            except (OSError, ValueError):
                continue
            for identity in identities:
                if self._stop.is_set():
                    break
                try:
                    self._process(identity)
                except (OSError, TypeError, ValueError) as error:
                    try:
                        current = self.store.load(identity)
                        if current["state"] not in _TERMINAL:
                            self.store.transition(identity, "FAILED",
                                reason=_failure(error),
                                timings={"failed_at": self._clock()})
                    except (OSError, TypeError, ValueError):
                        pass

    def _phase(self, identity: str, name: str) -> None:
        at = self._clock()
        self.store.update(identity, lambda value: value["timings"].__setitem__(name, at))

    def _process(self, identity: str) -> None:
        descriptor = self.store.lease(identity)
        if descriptor is None:
            return
        with self._status_lock:
            self._active_identity = identity
        try:
            record = self.store.load(identity)
            if record["state"] in _TERMINAL and not (
                    record["state"] == "COMPLETED_WITH_FAILURE"
                    and any(item["state"] == "QUEUED" for item in record["candidates"])):
                return
            commit = None
            if record["state"] in {"ADMITTED", "VALIDATING", "ACCEPTING"}:
                if record["state"] == "ADMITTED":
                    record = self.store.transition(identity, "VALIDATING",
                        timings={"validation_started_at": self._clock()})
                acceptance_started = record["state"] == "ACCEPTING"
                extracted = self.store.extracted(record)
                if extracted is None:
                    self._phase(identity, "extraction_started_at")
                    try:
                        extracted = self.intake.extract_answer(self.store.answer(record))
                        self.store.retain_extracted(identity, extracted)
                    except (OSError, TypeError, ValueError) as error:
                        self.store.transition(identity, "VALIDATION_FAILED",
                            reason=_failure(error), timings={"failed_at": self._clock()})
                        return
                    self._phase(identity, "extraction_completed_at")
                def observe(phase: str) -> None:
                    nonlocal acceptance_started
                    self._phase(identity, phase)
                    if phase == "acceptance_started_at":
                        acceptance_started = True
                        self.store.transition(identity, "ACCEPTING")
                try:
                    commit = self.intake.accept_answer(
                        record["market"], record["expected"],
                        self.store.answer(record), extracted_answer=extracted,
                        phase_observer=observe)
                except (OSError, TypeError, ValueError) as error:
                    state = "FAILED" if acceptance_started else "VALIDATION_FAILED"
                    self.store.transition(identity, state, reason=_failure(error),
                        timings={"failed_at": self._clock()})
                    return
                record = self.store.acceptance(identity, commit)
            if commit is None:
                commit = self.intake.store.load_acceptance(record["commit_identity"])
            if record["state"] == "ACCEPTED":
                record = self.store.transition(identity, "DOWNSTREAM_RUNNING",
                    timings={"downstream_started_at": self._clock()})
            for candidate in record["candidates"]:
                if candidate["state"] == "SUCCEEDED":
                    continue
                if candidate["state"] == "FAILED":
                    continue
                receipt = next((item for item in commit.receipts
                                if item.receipt_id == candidate["receipt_identity"]), None)
                if receipt is None:
                    self.store.candidate(identity, candidate["receipt_identity"], "FAILED",
                        reason="REVIEW_ACCEPTANCE_INCOMPLETE")
                    continue
                self.store.candidate(identity, receipt.receipt_id, "RUNNING")
                try:
                    attempt = self.intake.handoff(commit, receipt)
                    downstream = None if attempt is None else attempt.value["state"]
                    if downstream not in {"SUCCEEDED", "UNSUPPORTED_CONTRACT"}:
                        raise ValueError("REVIEW_DOWNSTREAM_PROCESSING_FAILED")
                    self.store.candidate(identity, receipt.receipt_id, "SUCCEEDED",
                        downstream_state=downstream, v2_retained=True)
                except (OSError, TypeError, ValueError) as error:
                    self.store.candidate(identity, receipt.receipt_id, "FAILED",
                        reason=_failure(error))
            record = self.store.load(identity)
            failed = any(item["state"] == "FAILED" for item in record["candidates"])
            complete = bool(record["candidates"]) and all(
                item["state"] in {"SUCCEEDED", "FAILED"}
                for item in record["candidates"])
            if complete:
                self.store.transition(identity,
                    "COMPLETED_WITH_FAILURE" if failed else "COMPLETED",
                    timings={"batch_completed_at": self._clock()})
                if self._completion is not None:
                    self._completion()
        finally:
            with self._status_lock:
                self._active_identity = None
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)


__all__ = [
    "BULK_IMPORT_SCHEMA", "BULK_IMPORT_VERSION", "DEFAULT_BULK_IMPORT_ROOT",
    "SwingBulkImportOwner", "SwingBulkImportStore",
]
