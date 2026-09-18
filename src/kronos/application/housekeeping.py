"""Bounded cleanup of explicitly disposable application-owned artifacts.

Canonical composition owns the bounded scheduler.  Standalone construction
remains disabled unless an owning composition explicitly activates it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256
import fcntl
import json
import os
from pathlib import Path
import stat
from threading import Event, Lock, Thread
import time
from typing import Callable, Iterable

from kronos.intraday.wo12_research_contract import ResearchRecord, digest


DEFAULT_INTERVAL_SECONDS = 6 * 60 * 60
DEFAULT_SHUTDOWN_WAIT_SECONDS = 0.25
_READ_CHUNK_BYTES = 64 * 1024


class HousekeepingArtifactClass(StrEnum):
    SWING_REVIEW_PREPARATION = "SWING_REVIEW_PREPARATION"
    SWING_REVIEW_POINTER_PREPARATION = "SWING_REVIEW_POINTER_PREPARATION"
    INTRADAY_RESEARCH_STAGED_WORKBOOK = "INTRADAY_RESEARCH_STAGED_WORKBOOK"
    INTRADAY_RESEARCH_EMPTY_STAGE_DIRECTORY = "INTRADAY_RESEARCH_EMPTY_STAGE_DIRECTORY"


@dataclass(frozen=True, slots=True)
class HousekeepingLimits:
    max_removed_files: int = 32
    max_removed_bytes: int = 64 * 1024 * 1024
    max_examined_entries: int = 256
    max_reference_entries: int = 4096
    max_reference_bytes: int = 128 * 1024 * 1024
    max_elapsed_seconds: float = 0.5
    max_diagnostics: int = 8

    def __post_init__(self) -> None:
        values = (
            self.max_removed_files,
            self.max_removed_bytes,
            self.max_examined_entries,
            self.max_reference_entries,
            self.max_reference_bytes,
            self.max_elapsed_seconds,
            self.max_diagnostics,
        )
        if any(type(value) not in {int, float} or value <= 0 for value in values):
            raise ValueError("HOUSEKEEPING_LIMIT_INVALID")


@dataclass(frozen=True, slots=True)
class HousekeepingResult:
    outcome: str
    examined_entries: int = 0
    reference_entries: int = 0
    reference_bytes: int = 0
    removed_files: int = 0
    removed_directories: int = 0
    removed_bytes: int = 0
    physically_reclaimed_bytes: int = 0
    skipped_entries: int = 0
    elapsed_ms: int = 0
    diagnostics: tuple[str, ...] = ()

    def document(self) -> dict[str, object]:
        return {
            "outcome": self.outcome,
            "examined_entries": self.examined_entries,
            "reference_entries": self.reference_entries,
            "reference_bytes": self.reference_bytes,
            "removed_files": self.removed_files,
            "removed_directories": self.removed_directories,
            "removed_bytes": self.removed_bytes,
            "physically_reclaimed_bytes": self.physically_reclaimed_bytes,
            "skipped_entries": self.skipped_entries,
            "elapsed_ms": self.elapsed_ms,
            "diagnostics": list(self.diagnostics),
        }


@dataclass(slots=True)
class _Budget:
    limits: HousekeepingLimits
    clock: Callable[[], float]
    started: float
    examined_entries: int = 0
    reference_entries: int = 0
    reference_bytes: int = 0
    removed_files: int = 0
    removed_directories: int = 0
    removed_bytes: int = 0
    physically_reclaimed_bytes: int = 0
    skipped_entries: int = 0
    saturated: bool = False
    diagnostics: list[str] = field(default_factory=list)

    def diagnostic(self, code: str) -> None:
        self.skipped_entries += 1
        if code not in self.diagnostics and len(self.diagnostics) < self.limits.max_diagnostics:
            self.diagnostics.append(code)

    def expired(self) -> bool:
        if self.clock() - self.started >= self.limits.max_elapsed_seconds:
            self.saturated = True
            self.diagnostic("PASS_ELAPSED_LIMIT")
            return True
        return False

    def examine(self) -> bool:
        if self.examined_entries >= self.limits.max_examined_entries:
            self.saturated = True
            self.diagnostic("PASS_ENTRY_LIMIT")
            return False
        self.examined_entries += 1
        return not self.expired()

    def reference(self, size: int) -> bool:
        if self.reference_entries >= self.limits.max_reference_entries:
            self.saturated = True
            self.diagnostic("REFERENCE_ENTRY_LIMIT")
            return False
        if size < 0 or self.reference_bytes + size > self.limits.max_reference_bytes:
            self.saturated = True
            self.diagnostic("REFERENCE_BYTE_LIMIT")
            return False
        self.reference_entries += 1
        self.reference_bytes += size
        return not self.expired()

    def may_remove(self, size: int) -> bool:
        if self.removed_files >= self.limits.max_removed_files:
            self.saturated = True
            self.diagnostic("REMOVAL_FILE_LIMIT")
            return False
        if size < 0 or self.removed_bytes + size > self.limits.max_removed_bytes:
            self.saturated = True
            self.diagnostic("REMOVAL_BYTE_LIMIT")
            return False
        return not self.expired()

    def result(self, outcome: str | None = None) -> HousekeepingResult:
        elapsed = max(0, int((self.clock() - self.started) * 1000))
        if outcome is None:
            if self.saturated:
                outcome = "LIMIT_REACHED"
            elif self.skipped_entries:
                outcome = "COMPLETED_WITH_SKIPS"
            else:
                outcome = "COMPLETED"
        return HousekeepingResult(
            outcome=outcome,
            examined_entries=self.examined_entries,
            reference_entries=self.reference_entries,
            reference_bytes=self.reference_bytes,
            removed_files=self.removed_files,
            removed_directories=self.removed_directories,
            removed_bytes=self.removed_bytes,
            physically_reclaimed_bytes=self.physically_reclaimed_bytes,
            skipped_entries=self.skipped_entries,
            elapsed_ms=elapsed,
            diagnostics=tuple(self.diagnostics),
        )


_REVIEW_DIRECTORIES = (
    "",
    "acceptance-commits",
    "acceptance-current",
    "chart-images",
    "chart-selections",
    "downstream-attempts",
    "downstream-current",
    "question-pdfs",
    "receipts",
    "request-mappings",
    "request-publications",
)


@dataclass(frozen=True, slots=True)
class _ReviewPreparationScope:
    root: Path

    def clean(self, owner: "BoundedHousekeeping", budget: _Budget) -> None:
        root = self.root.absolute()
        if not root.exists():
            return
        try:
            if _has_symlink_component(root) or not root.is_dir():
                budget.diagnostic("SWING_REVIEW_ROOT_UNSAFE")
                return
            descriptor = os.open(root / "intake.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        except OSError:
            budget.diagnostic("SWING_REVIEW_LOCK_UNAVAILABLE")
            return
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                budget.diagnostic("SWING_REVIEW_LOCK_UNSAFE")
                return
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                budget.diagnostic("SWING_REVIEW_OWNER_BUSY")
                return
            for relative in _REVIEW_DIRECTORIES:
                if budget.saturated:
                    return
                directory = root if not relative else root / relative
                try:
                    directory_stat = directory.lstat()
                except FileNotFoundError:
                    continue
                except OSError:
                    budget.diagnostic("SWING_REVIEW_DIRECTORY_UNAVAILABLE")
                    continue
                if not stat.S_ISDIR(directory_stat.st_mode) or directory.is_symlink():
                    budget.diagnostic("SWING_REVIEW_DIRECTORY_UNSAFE")
                    continue
                try:
                    with os.scandir(directory) as entries:
                        for entry in entries:
                            if not budget.examine():
                                return
                            if not entry.name.startswith(".prepared-"):
                                continue
                            artifact_class = (
                                HousekeepingArtifactClass.SWING_REVIEW_POINTER_PREPARATION
                                if entry.name.startswith(".prepared-pointer-")
                                else HousekeepingArtifactClass.SWING_REVIEW_PREPARATION
                            )
                            owner._remove_file(
                                Path(entry.path), artifact_class, budget,
                                unsafe_code="SWING_REVIEW_PREPARATION_UNSAFE",
                                failure_code="SWING_REVIEW_PREPARATION_REMOVE_FAILED",
                            )
                            if budget.saturated:
                                return
                except OSError:
                    budget.diagnostic("SWING_REVIEW_DIRECTORY_SCAN_FAILED")
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)


@dataclass(frozen=True, slots=True)
class _IntradayResearchStagingScope:
    store: object
    publication_root: Path

    def clean(self, owner: "BoundedHousekeeping", budget: _Budget) -> None:
        root = Path(self.store.root).absolute()
        if not root.exists():
            return
        if _has_symlink_component(root) or not root.is_dir():
            budget.diagnostic("INTRADAY_RESEARCH_ROOT_UNSAFE")
            return
        try:
            with self.store.transaction():
                eligible, failures, certain = self._references(budget)
                if not certain or budget.saturated:
                    return
                for operation_hash in failures:
                    eligible.pop(operation_hash, None)
                self._staging(owner, budget, eligible, failures)
        except ValueError as error:
            if str(error) == "WO12_RESEARCH_UPDATE_BUSY":
                budget.diagnostic("INTRADAY_RESEARCH_OWNER_BUSY")
            else:
                budget.diagnostic("INTRADAY_RESEARCH_REFERENCE_UNCERTAIN")
        except OSError:
            budget.diagnostic("INTRADAY_RESEARCH_SCOPE_UNAVAILABLE")

    def _references(self, budget: _Budget) -> tuple[dict[str, "_PublicationProof"], set[str], bool]:
        records_root = Path(self.store.root) / "records"
        receipts: dict[str, ResearchRecord] = {}
        references: dict[str, str] = {}
        failures: set[str] = set()
        if records_root.exists():
            try:
                root_stat = records_root.lstat()
                if (not stat.S_ISDIR(root_stat.st_mode)
                        or _has_symlink_component(records_root)):
                    budget.diagnostic("INTRADAY_RESEARCH_RECORDS_UNSAFE")
                    return {}, set(), False
                with os.scandir(records_root) as entries:
                    for entry in entries:
                        if not budget.reference(0):
                            return {}, set(), False
                        if not entry.name.endswith(".json"):
                            continue
                        prefixes = (
                            "WO12_LOCAL_PUBLICATION_RECEIPT_V1-",
                            "WO12_RESEARCH_UPDATE_V1-",
                            "WO12_LOCAL_PUBLICATION_FAILURE_V1-",
                        )
                        if not entry.name.startswith(prefixes):
                            continue
                        try:
                            file_stat = entry.stat(follow_symlinks=False)
                        except OSError:
                            budget.diagnostic("INTRADAY_RESEARCH_REFERENCE_UNCERTAIN")
                            return {}, set(), False
                        if not stat.S_ISREG(file_stat.st_mode) or not budget.reference(file_stat.st_size):
                            budget.diagnostic("INTRADAY_RESEARCH_REFERENCE_UNCERTAIN")
                            return {}, set(), False
                        item = _read_record(Path(entry.path), file_stat)
                        if entry.name != item.identity + ".json":
                            raise ValueError("WO12_RECORD_PATH_MISMATCH")
                        data = item.data
                        if item.schema == "WO12_LOCAL_PUBLICATION_RECEIPT_V1":
                            receipts[item.identity] = item
                            _bind_reference(references, str(data["operation_identity"]), item.identity)
                        elif item.schema == "WO12_RESEARCH_UPDATE_V1":
                            _bind_reference(references, str(data["operation_identity"]), str(data["receipt_identity"]))
                        else:
                            failures.add(digest(str(data["operation_identity"])))
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                budget.diagnostic("INTRADAY_RESEARCH_REFERENCE_UNCERTAIN")
                return {}, set(), False

        eligible: dict[str, _PublicationProof] = {}
        verified_receipts: dict[str, _PublicationProof | None] = {}
        for operation_identity, receipt_identity in references.items():
            if budget.expired():
                return {}, failures, False
            receipt = receipts.get(receipt_identity)
            if receipt is None:
                budget.diagnostic("INTRADAY_RESEARCH_INCOMPLETE_RECOVERY")
                continue
            if receipt_identity not in verified_receipts:
                verified_receipts[receipt_identity] = self._verified_current(receipt, budget)
            verified = verified_receipts[receipt_identity]
            if verified is None:
                budget.diagnostic("INTRADAY_RESEARCH_CURRENT_UNVERIFIED")
                continue
            key = digest(operation_identity)
            if key in eligible and eligible[key] != verified:
                budget.diagnostic("INTRADAY_RESEARCH_REFERENCE_CONFLICT")
                return {}, failures, False
            eligible[key] = verified
        return eligible, failures, True

    def _verified_current(self, receipt: ResearchRecord, budget: _Budget) -> "_PublicationProof | None":
        data = receipt.data
        try:
            year_month = str(data["year_month"])
            current = Path(self.store.root) / "current" / f"{year_month}.json"
            if _has_symlink_component(current.parent):
                return None
            current_stat = current.lstat()
            if not stat.S_ISREG(current_stat.st_mode) or current.is_symlink() or not budget.reference(current_stat.st_size):
                return None
            pointer = _read_record(current, current_stat)
            if pointer != receipt:
                return None
            filename = str(data["workbook_filename"])
            publication_root = self.publication_root.absolute()
            target = Path(str(data["workbook_path"]))
            if not target.is_absolute():
                return None
            if target != publication_root / filename or target.parent != publication_root:
                return None
            if _has_symlink_component(publication_root):
                return None
            root_stat = publication_root.lstat()
            target_stat = target.lstat()
            if (publication_root.is_symlink() or target.is_symlink()
                    or not stat.S_ISDIR(root_stat.st_mode) or not stat.S_ISREG(target_stat.st_mode)):
                return None
            expected_size = int(data["workbook_bytes"])
            expected_hash = str(data["workbook_sha256"])
            if target_stat.st_size != expected_size:
                return None
            actual_hash = _hash_file(target, target_stat, budget)
            if actual_hash != expected_hash:
                return None
            return _PublicationProof(receipt, filename, expected_hash, expected_size)
        except (OSError, KeyError, TypeError, ValueError):
            return None

    def _staging(
        self,
        owner: "BoundedHousekeeping",
        budget: _Budget,
        eligible: dict[str, "_PublicationProof"],
        failures: set[str],
    ) -> None:
        staging = Path(self.store.root) / "staging"
        if not staging.exists():
            return
        try:
            staging_stat = staging.lstat()
            if not stat.S_ISDIR(staging_stat.st_mode) or _has_symlink_component(staging):
                budget.diagnostic("INTRADAY_RESEARCH_STAGING_UNSAFE")
                return
            with os.scandir(staging) as entries:
                for entry in entries:
                    if not budget.examine():
                        return
                    name = entry.name
                    try:
                        directory_stat = entry.stat(follow_symlinks=False)
                    except OSError:
                        budget.diagnostic("INTRADAY_RESEARCH_STAGE_UNSAFE")
                        continue
                    if (len(name) != 64 or any(value not in "0123456789abcdef" for value in name)
                            or not stat.S_ISDIR(directory_stat.st_mode)):
                        budget.diagnostic("INTRADAY_RESEARCH_STAGE_UNSAFE")
                        continue
                    if name in failures:
                        budget.diagnostic("INTRADAY_RESEARCH_FAILED_CLEANUP_OWNED")
                        continue
                    expected = eligible.get(name)
                    if expected is None:
                        budget.diagnostic("INTRADAY_RESEARCH_INCOMPLETE_RECOVERY")
                        continue
                    self._stage_directory(owner, budget, Path(entry.path), directory_stat, expected)
                    if budget.saturated:
                        return
        except OSError:
            budget.diagnostic("INTRADAY_RESEARCH_STAGING_SCAN_FAILED")

    def _stage_directory(
        self,
        owner: "BoundedHousekeeping",
        budget: _Budget,
        directory: Path,
        directory_stat: os.stat_result,
        expected: "_PublicationProof",
    ) -> None:
        filename = expected.filename
        try:
            with os.scandir(directory) as entries:
                contents = []
                for entry in entries:
                    if not budget.examine():
                        return
                    contents.append(entry.name)
                    if len(contents) > 1:
                        budget.diagnostic("INTRADAY_RESEARCH_STAGE_CONTENT_UNCERTAIN")
                        return
        except OSError:
            budget.diagnostic("INTRADAY_RESEARCH_STAGE_SCAN_FAILED")
            return
        if not contents:
            owner._remove_directory(directory, directory_stat, budget)
            return
        if contents != [filename]:
            budget.diagnostic("INTRADAY_RESEARCH_STAGE_CONTENT_UNCERTAIN")
            return
        staged = directory / filename
        try:
            staged_stat = staged.lstat()
            if (not stat.S_ISREG(staged_stat.st_mode) or staged.is_symlink()
                    or staged_stat.st_size != expected.size
                    or _hash_file(staged, staged_stat, budget) != expected.sha256):
                budget.diagnostic("INTRADAY_RESEARCH_STAGE_MISMATCH")
                return
        except OSError:
            budget.diagnostic("INTRADAY_RESEARCH_STAGE_UNSAFE")
            return
        # Re-read the current pointer and canonical workbook after examining
        # the staged candidate.  The owner lock excludes legitimate writers;
        # this final check also fails closed on out-of-contract mutation.
        if self._verified_current(expected.receipt, budget) != expected:
            budget.diagnostic("INTRADAY_RESEARCH_REFERENCE_CHANGED")
            return
        removed = owner._remove_file(
            staged,
            HousekeepingArtifactClass.INTRADAY_RESEARCH_STAGED_WORKBOOK,
            budget,
            unsafe_code="INTRADAY_RESEARCH_STAGE_UNSAFE",
            failure_code="INTRADAY_RESEARCH_STAGE_REMOVE_FAILED",
            expected=staged_stat,
        )
        if removed:
            try:
                directory_stat = directory.lstat()
            except OSError:
                budget.diagnostic("INTRADAY_RESEARCH_STAGE_DIRECTORY_REMOVE_FAILED")
                return
            owner._remove_directory(directory, directory_stat, budget)


@dataclass(frozen=True, slots=True)
class _PublicationProof:
    receipt: ResearchRecord
    filename: str
    sha256: str
    size: int


def _bind_reference(references: dict[str, str], operation_identity: str, receipt_identity: str) -> None:
    if operation_identity in references and references[operation_identity] != receipt_identity:
        raise ValueError("WO12_OPERATION_IDENTITY_CONFLICT")
    references[operation_identity] = receipt_identity


def _stat_identity(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (value.st_dev, value.st_ino, value.st_mode, value.st_size, value.st_mtime_ns, value.st_nlink)


def _has_symlink_component(path: Path) -> bool:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            if current.is_symlink():
                return True
        except OSError:
            return True
    return False


def _read_record(path: Path, expected: os.stat_result) -> ResearchRecord:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        actual = os.fstat(descriptor)
        if _stat_identity(actual) != _stat_identity(expected) or not stat.S_ISREG(actual.st_mode):
            raise ValueError("HOUSEKEEPING_REFERENCE_CHANGED")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            value = json.loads(stream.read())
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return ResearchRecord(**value)


def _hash_file(path: Path, expected: os.stat_result, budget: _Budget) -> str | None:
    if not budget.reference(expected.st_size):
        return None
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        actual = os.fstat(descriptor)
        if _stat_identity(actual) != _stat_identity(expected) or not stat.S_ISREG(actual.st_mode):
            return None
        result = sha256()
        while True:
            chunk = os.read(descriptor, _READ_CHUNK_BYTES)
            if not chunk:
                break
            result.update(chunk)
            if budget.expired():
                return None
        if _stat_identity(os.fstat(descriptor)) != _stat_identity(expected):
            return None
        return result.hexdigest()
    finally:
        os.close(descriptor)


def review_preparation_scope(store: object) -> _ReviewPreparationScope:
    return _ReviewPreparationScope(Path(store.root))


def intraday_research_staging_scope(application: object) -> _IntradayResearchStagingScope:
    return _IntradayResearchStagingScope(application.store, Path(application.publication_root))


class BoundedHousekeeping:
    """Single non-overlapping bounded pass over explicitly supplied scopes."""

    def __init__(
        self,
        scopes: Iterable[object],
        *,
        limits: HousekeepingLimits | None = None,
        interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
        production_activation: bool = False,
        clock: Callable[[], float] = time.monotonic,
        background_runner: Callable[[Callable[[], None]], None] | None = None,
        unlink: Callable[[Path], None] = os.unlink,
        rmdir: Callable[[Path], None] = os.rmdir,
    ) -> None:
        self.scopes = tuple(scopes)
        if not self.scopes:
            raise ValueError("HOUSEKEEPING_SCOPE_REQUIRED")
        if type(interval_seconds) is not int or interval_seconds <= 0:
            raise ValueError("HOUSEKEEPING_INTERVAL_INVALID")
        self.limits = limits or HousekeepingLimits()
        self.interval_seconds = interval_seconds
        self.production_activation = bool(production_activation)
        self._clock = clock
        self._unlink = unlink
        self._rmdir = rmdir
        self._pass_lock = Lock()
        self._state_lock = Lock()
        self._background_runner = background_runner or self._thread_runner
        now = self._clock()
        self._next_due = now + interval_seconds
        self._periodic_pending = False
        self._worker_running = False
        self._worker_generation = 0
        self._active_worker_generation: int | None = None
        self._owned_workers = 0
        self._shutdown_requested = False
        self._last_trigger = "NOT_DUE"
        self._last_failure: str | None = None
        self._last_result: HousekeepingResult | None = None
        self._worker_done = Event()
        self._worker_done.set()
        self._pass_done = Event()
        self._pass_done.set()

    @staticmethod
    def _thread_runner(callback: Callable[[], None]) -> None:
        Thread(target=callback, name="kronos-housekeeping", daemon=True).start()

    def run_once(self) -> HousekeepingResult:
        with self._state_lock:
            if self._shutdown_requested:
                return HousekeepingResult(outcome="SHUTDOWN")
        started = self._clock()
        if not self._pass_lock.acquire(blocking=False):
            return HousekeepingResult(outcome="OVERLAP_SKIPPED")
        self._pass_done.clear()
        budget = _Budget(self.limits, self._clock, started)
        try:
            for scope in self.scopes:
                if budget.expired():
                    break
                scope.clean(self, budget)
                if budget.saturated:
                    break
            result = budget.result()
            with self._state_lock:
                self._last_result = result
            return result
        finally:
            self._pass_lock.release()
            self._pass_done.set()

    def trigger_periodic(self, *, now: float | None = None) -> str:
        observed = self._clock() if now is None else now
        with self._state_lock:
            if self._shutdown_requested:
                self._last_trigger = "SHUTDOWN"
                return "SHUTDOWN"
            if not self.production_activation:
                self._last_trigger = "DISABLED"
                return "DISABLED"
            if self._periodic_pending:
                self._last_trigger = "PENDING"
                return "PENDING"
            if observed < self._next_due:
                self._last_trigger = "NOT_DUE"
                return "NOT_DUE"
            self._periodic_pending = True
            self._worker_generation += 1
            generation = self._worker_generation
            self._active_worker_generation = generation
            self._owned_workers = 1
            self._worker_running = False
            self._worker_done.clear()
            self._last_trigger = "SCHEDULED"
            scheduled = observed
        try:
            self._background_runner(
                lambda: self._periodic_run(scheduled, generation)
            )
        except Exception:
            with self._state_lock:
                if self._active_worker_generation == generation:
                    self._periodic_pending = False
                    self._active_worker_generation = None
                    self._owned_workers = 0
                    self._next_due = max(
                        scheduled + self.interval_seconds,
                        self._clock() + self.interval_seconds,
                    )
                    self._last_trigger = "FAILED"
                    self._last_failure = "HOUSEKEEPING_SCHEDULE_FAILED"
                    self._worker_done.set()
            return "FAILED"
        return "SCHEDULED"

    def _periodic_run(self, scheduled: float, generation: int) -> None:
        with self._state_lock:
            if self._active_worker_generation != generation:
                return
            if self._shutdown_requested:
                self._finish_worker_locked(generation)
                return
            self._worker_running = True
        try:
            self.run_once()
        except Exception:
            with self._state_lock:
                if self._active_worker_generation == generation:
                    self._last_failure = "HOUSEKEEPING_PASS_FAILED"
        finally:
            with self._state_lock:
                if self._active_worker_generation == generation:
                    if not self._shutdown_requested:
                        self._next_due = max(
                            scheduled + self.interval_seconds,
                            self._clock() + self.interval_seconds,
                        )
                    self._finish_worker_locked(generation)

    def _finish_worker_locked(self, generation: int) -> None:
        if self._active_worker_generation != generation:
            return
        self._periodic_pending = False
        self._worker_running = False
        self._active_worker_generation = None
        self._owned_workers = 0
        self._worker_done.set()

    def record_trigger_failure(self) -> None:
        """Expose a composition-level trigger failure without raising in serve_forever."""

        with self._state_lock:
            self._last_trigger = "FAILED"
            self._last_failure = "HOUSEKEEPING_TRIGGER_UNAVAILABLE"
            self._next_due = max(
                self._next_due,
                self._clock() + self.interval_seconds,
            )

    def shutdown(
        self, *, timeout_seconds: float = DEFAULT_SHUTDOWN_WAIT_SECONDS
    ) -> dict[str, object]:
        """Fence new work and wait a bounded time for an already owned pass."""

        if type(timeout_seconds) not in {int, float} or timeout_seconds < 0:
            raise ValueError("HOUSEKEEPING_SHUTDOWN_TIMEOUT_INVALID")
        with self._state_lock:
            self._shutdown_requested = True
            self._last_trigger = "SHUTDOWN"
            worker_owned = self._owned_workers > 0
        deadline = time.monotonic() + float(timeout_seconds)
        if worker_owned:
            self._worker_done.wait(max(0.0, deadline - time.monotonic()))
        if self._pass_lock.locked():
            self._pass_done.wait(max(0.0, deadline - time.monotonic()))
        return self.status_document()

    def status_document(self) -> dict[str, object]:
        with self._state_lock:
            last = None if self._last_result is None else self._last_result.document()
            pending = self._periodic_pending
            next_due = self._next_due
            shutdown = self._shutdown_requested
            owned = self._owned_workers
            running = self._worker_running
            generation = self._active_worker_generation
            last_trigger = self._last_trigger
            last_failure = self._last_failure
        pass_active = self._pass_lock.locked()
        if shutdown:
            lifecycle = "SHUTDOWN_PENDING" if owned or pass_active else "STOPPED"
        elif not self.production_activation:
            lifecycle = "DISABLED"
        elif running:
            lifecycle = "RUNNING"
        elif owned:
            lifecycle = "SCHEDULED"
        else:
            lifecycle = "IDLE"
        return {
            "production_activation": self.production_activation,
            "interval_seconds": self.interval_seconds,
            "lifecycle_state": lifecycle,
            "shutdown_requested": shutdown,
            "owned_workers": owned,
            "worker_generation": generation,
            "pass_active": pass_active,
            "periodic_pending": pending,
            "next_due_monotonic": next_due,
            "last_trigger": last_trigger,
            "last_failure": last_failure,
            "last_result": last,
        }

    def _remove_file(
        self,
        path: Path,
        artifact_class: HousekeepingArtifactClass,
        budget: _Budget,
        *,
        unsafe_code: str,
        failure_code: str,
        expected: os.stat_result | None = None,
    ) -> bool:
        del artifact_class  # The call site is the allowlist; paths never become policy.
        try:
            before = path.lstat() if expected is None else expected
        except OSError:
            budget.diagnostic(unsafe_code)
            return False
        if not stat.S_ISREG(before.st_mode) or path.is_symlink() or not budget.may_remove(before.st_size):
            budget.diagnostic(unsafe_code if not stat.S_ISREG(before.st_mode) or path.is_symlink()
                              else "REMOVAL_CAPACITY_REFUSED")
            return False
        try:
            current = path.lstat()
            if _stat_identity(current) != _stat_identity(before):
                budget.diagnostic("ARTIFACT_CHANGED_BEFORE_REMOVAL")
                return False
            self._unlink(path)
        except OSError:
            budget.diagnostic(failure_code)
            return False
        budget.removed_files += 1
        budget.removed_bytes += before.st_size
        if before.st_nlink == 1:
            budget.physically_reclaimed_bytes += before.st_blocks * 512
        return True

    def _remove_directory(
        self,
        path: Path,
        expected: os.stat_result,
        budget: _Budget,
    ) -> bool:
        if budget.expired():
            return False
        try:
            current = path.lstat()
            if (_stat_identity(current) != _stat_identity(expected)
                    or not stat.S_ISDIR(current.st_mode) or path.is_symlink()):
                budget.diagnostic("INTRADAY_RESEARCH_STAGE_CHANGED")
                return False
            with os.scandir(path) as entries:
                if next(entries, None) is not None:
                    budget.diagnostic("INTRADAY_RESEARCH_STAGE_NOT_EMPTY")
                    return False
            self._rmdir(path)
        except OSError:
            budget.diagnostic("INTRADAY_RESEARCH_STAGE_DIRECTORY_REMOVE_FAILED")
            return False
        budget.removed_directories += 1
        return True


__all__ = [
    "BoundedHousekeeping",
    "DEFAULT_INTERVAL_SECONDS",
    "DEFAULT_SHUTDOWN_WAIT_SECONDS",
    "HousekeepingArtifactClass",
    "HousekeepingLimits",
    "HousekeepingResult",
    "intraday_research_staging_scope",
    "review_preparation_scope",
]
