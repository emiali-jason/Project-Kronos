"""One bounded process owner for CPU-heavy Swing analysis publication."""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass, replace
from datetime import datetime
import gzip
from hashlib import sha256
import multiprocessing
import os
from pathlib import Path
import pickle
import re
import sys
import tempfile
from threading import Lock
import time

MAX_REQUEST_BYTES = 1024 * 1024
MAX_RESPONSE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_PROVIDER_BYTES = 768 * 1024 * 1024
MAX_RESULT_BYTES = 128 * 1024 * 1024
MAX_DECODED_RESULT_BYTES = 512 * 1024 * 1024
MAX_PROVIDER_CALLS = 512
WORKER_TIMEOUT_SECONDS = 240.0
TERMINATION_SECONDS = 5.0
UNKNOWN = "UNKNOWN"
_SAFE_TEXT = re.compile(r"[A-Z0-9&._ -]{1,96}")
_SAFE_CLASS = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,79}")
_FAILURE_OPERATIONS = frozenset(
    {UNKNOWN, "WORKER", "INSTRUMENTS", "HISTORICAL", "PROGRESS", "CLOCK",
     "PREPARED", "COMMIT_READY", "DONE"}
)
_EXIT_CLASSIFICATIONS = frozenset(
    {
        UNKNOWN,
        "WORKER_REPORTED_FAILURE",
        "PARENT_PROVIDER_FAILURE",
        "PARENT_FAILURE",
        "ABNORMAL_EXIT",
        "TIMEOUT",
        "STALE",
        "COMPLETION_FAILURE",
        "CLEANUP_FAILURE",
    }
)


class SwingAnalysisProcessError(RuntimeError):
    """A bounded worker failed before durable completion."""

    def __init__(self, failure, *, diagnostic=None) -> None:
        super().__init__(failure)
        self.diagnostic = diagnostic


class SwingAnalysisProcessCleanupError(SwingAnalysisProcessError):
    """The worker has not proved process termination."""


class SwingAnalysisProcessCompletionError(SwingAnalysisProcessError):
    """Publication completed but its result could not be installed safely."""


@dataclass(frozen=True, slots=True)
class SwingAnalysisFailureEnvelope:
    """Sanitized current-process failure evidence; never durable publication data."""

    operation: str = UNKNOWN
    exchange: str = UNKNOWN
    instrument: str = UNKNOWN
    provider_failure_code: str = UNKNOWN
    exception_class: str = UNKNOWN
    worker_pid: int | str = UNKNOWN
    worker_exit_classification: str = UNKNOWN
    worker_exit_code: int | str = UNKNOWN
    provider_call_count: int = 0
    provider_response_bytes: int = 0

    def __post_init__(self) -> None:
        if (
            self.operation not in _FAILURE_OPERATIONS
            or not _safe_evidence_text(self.exchange)
            or not _safe_evidence_text(self.instrument)
            or not _safe_evidence_text(self.provider_failure_code)
            or not _SAFE_CLASS.fullmatch(self.exception_class)
            or (
                self.worker_pid != UNKNOWN
                and (type(self.worker_pid) is not int or self.worker_pid <= 0)
            )
            or self.worker_exit_classification not in _EXIT_CLASSIFICATIONS
            or (
                self.worker_exit_code != UNKNOWN
                and type(self.worker_exit_code) is not int
            )
            or type(self.provider_call_count) is not int
            or self.provider_call_count < 0
            or type(self.provider_response_bytes) is not int
            or self.provider_response_bytes < 0
        ):
            raise ValueError("SWING_ANALYSIS_FAILURE_ENVELOPE_INVALID")

    def projection(self) -> dict[str, int | str]:
        return {
            "operation": self.operation,
            "exchange": self.exchange,
            "instrument": self.instrument,
            "provider_failure_code": self.provider_failure_code,
            "exception_class": self.exception_class,
            "worker_pid": self.worker_pid,
            "worker_exit_classification": self.worker_exit_classification,
            "worker_exit_code": self.worker_exit_code,
            "provider_call_count": self.provider_call_count,
            "provider_response_bytes": self.provider_response_bytes,
        }


@dataclass(frozen=True, slots=True)
class _PublicationSpec:
    publication_root: Path
    mtf_root: Path
    native_root: Path
    relative_root: Path
    provenance_root: Path
    calendar_root: Path


@dataclass(frozen=True, slots=True)
class SwingAnalysisProcessResult:
    completed: object
    committed: object
    provider_call_count: int
    provider_response_bytes: int
    result_bytes: int
    decoded_result_bytes: int
    worker_peak_rss_bytes: int


def _send(connection, value, limit):
    payload = _payload(value, limit)
    connection.send_bytes(payload)
    return len(payload)


def _payload(value, limit):
    payload = pickle.dumps(value, protocol=5)
    if len(payload) > limit:
        raise RuntimeError("SWING_ANALYSIS_WORKER_TRANSFER_CAPACITY")
    return payload


def _receive(connection, limit):
    payload = connection.recv_bytes(limit)
    return pickle.loads(payload), len(payload)


def _safe_failure(error):
    value = str(error)
    if re.fullmatch(r"[A-Z][A-Z0-9_]{0,95}", value or ""):
        return value
    return "SWING_ANALYSIS_WORKER_FAILED"


def _safe_evidence_text(value):
    return isinstance(value, str) and (
        value == UNKNOWN or _SAFE_TEXT.fullmatch(value) is not None
    )


def _safe_exception_class(error):
    value = type(error).__name__
    return value if _SAFE_CLASS.fullmatch(value) else UNKNOWN


def _safe_provider_failure_code(error):
    from kronos.provider.contracts.instrument import InstrumentResolutionError
    from kronos.provider.contracts.market_data import HistoricalDataError
    from kronos.provider.exceptions.connectivity import ProviderConnectivityError

    if isinstance(error, ProviderConnectivityError):
        candidate = error.code.value
    elif isinstance(error, (InstrumentResolutionError, HistoricalDataError)):
        candidate = error.failure.value
    else:
        return UNKNOWN
    return candidate if _safe_evidence_text(candidate) else UNKNOWN


def _operation_context(operation, value):
    from kronos.provider.contracts.market_data import HistoricalCandleRequest

    exchange = UNKNOWN
    instrument = UNKNOWN
    if operation == "INSTRUMENTS" and isinstance(value, str):
        exchange = value if _safe_evidence_text(value) else UNKNOWN
    elif operation == "HISTORICAL" and type(value) is HistoricalCandleRequest:
        candidate_exchange = value.instrument.exchange
        candidate_instrument = value.instrument.name or value.instrument.trading_symbol
        exchange = (
            candidate_exchange
            if _safe_evidence_text(candidate_exchange)
            else UNKNOWN
        )
        instrument = (
            candidate_instrument
            if _safe_evidence_text(candidate_instrument)
            else UNKNOWN
        )
    return exchange, instrument


def _failure_envelope(
    error,
    *,
    operation=UNKNOWN,
    value=None,
    worker_pid=UNKNOWN,
    worker_exit_classification=UNKNOWN,
    worker_exit_code=UNKNOWN,
    provider_call_count=0,
    provider_response_bytes=0,
):
    exchange, instrument = _operation_context(operation, value)
    return SwingAnalysisFailureEnvelope(
        operation=operation if operation in _FAILURE_OPERATIONS else UNKNOWN,
        exchange=exchange,
        instrument=instrument,
        provider_failure_code=_safe_provider_failure_code(error),
        exception_class=_safe_exception_class(error),
        worker_pid=worker_pid if type(worker_pid) is int and worker_pid > 0 else UNKNOWN,
        worker_exit_classification=worker_exit_classification,
        worker_exit_code=(
            worker_exit_code if type(worker_exit_code) is int else UNKNOWN
        ),
        provider_call_count=provider_call_count,
        provider_response_bytes=provider_response_bytes,
    )


def _merge_failure_envelope(
    envelope,
    *,
    worker_pid,
    worker_exit_classification,
    worker_exit_code=UNKNOWN,
    provider_call_count,
    provider_response_bytes,
):
    if type(envelope) is not SwingAnalysisFailureEnvelope:
        envelope = SwingAnalysisFailureEnvelope()
    return replace(
        envelope,
        worker_pid=(
            worker_pid if type(worker_pid) is int and worker_pid > 0 else UNKNOWN
        ),
        worker_exit_classification=worker_exit_classification,
        worker_exit_code=(
            worker_exit_code if type(worker_exit_code) is int else UNKNOWN
        ),
        provider_call_count=provider_call_count,
        provider_response_bytes=provider_response_bytes,
    )


def _digest_file(path):
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _rss_bytes(value, platform=sys.platform):
    measured = int(value)
    return measured if platform == "darwin" else measured * 1024


def _validate_result(
    completed,
    committed,
    token,
    analysis_run_identity,
    prepared_reference,
):
    from kronos.application.swing_opportunities import CompletedSwingAnalysis
    from kronos.swing.run_publication import CommittedRun

    if (
        type(completed) is not CompletedSwingAnalysis
        or type(committed) is not CommittedRun
        or committed.reference != prepared_reference
        or committed.manifest.get("generation") != token.generation
        or committed.manifest.get("run_id") != token.run_id
        or committed.manifest.get("predecessor_manifest")
        != token.predecessor_manifest
        or completed.evidence.analysis_run_identity != analysis_run_identity
        or completed.evidence.swing_analysis_run_identity != token.run_id
        or completed.workspace.analysis_run_identity != analysis_run_identity
        or completed.workspace.swing_analysis_run_identity != token.run_id
        or completed.workspace.completed_at
        != committed.provenance.successful_completed_at
        or completed.evidence.observation_boundary
        != committed.provenance.analysis_boundary
        or completed.evidence.market_data_snapshot_identity
        != committed.provenance.market_data_snapshot_identity
        or committed.mtf.run_identity != token.run_id
        or committed.native.run_identity != token.run_id
        or committed.relative.run_identity != token.run_id
    ):
        raise ValueError("SWING_ANALYSIS_WORKER_RESULT_INVALID")


class _BoundedWriter:
    def __init__(self, stream, limit):
        self._stream = stream
        self._limit = limit
        self.size = 0

    def write(self, value):
        if self.size + len(value) > self._limit:
            raise RuntimeError("SWING_ANALYSIS_WORKER_RESULT_CAPACITY")
        written = self._stream.write(value)
        self.size += written
        return written


class _BoundedReader:
    def __init__(self, stream, limit):
        self._stream = stream
        self._limit = limit
        self.size = 0

    def _retain(self, value):
        self.size += len(value)
        if self.size > self._limit:
            raise RuntimeError("SWING_ANALYSIS_WORKER_RESULT_CAPACITY")
        return value

    def read(self, size=-1):
        return self._retain(self._stream.read(size))

    def readline(self, size=-1):
        return self._retain(self._stream.readline(size))


class _ProviderProxy:
    active = True

    def __init__(self, connection):
        from kronos.provider.contracts.provider_authentication import ReadOnlyProviderOperation

        self.operations = frozenset(
            {
                ReadOnlyProviderOperation.INSTRUMENTS,
                ReadOnlyProviderOperation.HISTORICAL_DATA,
            }
        )
        self._connection = connection
        self.last_operation = UNKNOWN
        self.last_value = None

    def _call(self, operation, value):
        self.last_operation = operation
        self.last_value = value
        _send(self._connection, (operation, value), MAX_REQUEST_BYTES)
        response, _ = _receive(self._connection, MAX_RESPONSE_BYTES)
        if response[0] != "OK":
            raise RuntimeError(response[1])
        return response[1]

    def instrument_records(self, exchange):
        return self._call("INSTRUMENTS", exchange)

    def historical_candles(self, request):
        return self._call("HISTORICAL", request)


def _publication(spec):
    from kronos.swing.run_publication import SwingRunPublication
    from kronos.swing.run_provenance import LocalSwingRunProvenanceStore
    from kronos.swing.v1.mtf_facts import MtfFactEvidenceStore
    from kronos.swing.v1.native_discovery import NativeDiscoveryEvidenceStore
    from kronos.swing.v1.relative_context import RelativeContextEvidenceStore

    return SwingRunPublication(
        spec.publication_root,
        mtf_store=MtfFactEvidenceStore(spec.mtf_root),
        native_store=NativeDiscoveryEvidenceStore(spec.native_root),
        relative_store=RelativeContextEvidenceStore(spec.relative_root),
        provenance_store=LocalSwingRunProvenanceStore(spec.provenance_root),
    )


def _worker(
    connection,
    spec,
    token,
    analysis_run_identity,
    swing_run_identity,
    run_created_at,
    now,
    result_path,
):
    proxy = None
    try:
        import resource
        from kronos.application.swing_opportunities import build_completed_swing_analysis
        from kronos.market.calendar import MarketCalendarPublisher
        from kronos.swing.run_provenance import SwingAnalysisRunProvenance

        publication = _publication(spec)
        predecessor = publication._load(token.predecessor_manifest)
        proxy = _ProviderProxy(connection)

        def observe(progress):
            _send(connection, ("PROGRESS", progress), MAX_REQUEST_BYTES)
            response, _ = _receive(connection, MAX_RESPONSE_BYTES)
            if response[0] != "OK":
                raise RuntimeError(response[1])

        def completion_clock():
            _send(connection, ("CLOCK", None), MAX_REQUEST_BYTES)
            response, _ = _receive(connection, MAX_RESPONSE_BYTES)
            if response[0] != "OK":
                raise RuntimeError(response[1])
            return response[1]

        completed = build_completed_swing_analysis(
            proxy,
            analysis_run_identity=analysis_run_identity,
            swing_analysis_run_identity=swing_run_identity,
            run_created_at=run_created_at,
            now=now,
            pace=lambda: None,
            progress_observer=observe,
            market_calendar_publisher=MarketCalendarPublisher(spec.calendar_root),
            committed_predecessor=predecessor,
            prepare_publication=True,
            completion_clock=completion_clock,
        )
        del predecessor
        contribution = completed.continuity_contribution
        successful_completed_at = (
            contribution.rows[0].last_analysis_checked
            if contribution is not None
            else completion_clock()
        )
        completed = replace(
            completed,
            workspace=replace(
                completed.workspace,
                completed_at=successful_completed_at,
            ),
        )
        provenance = SwingAnalysisRunProvenance(
            swing_run_identity,
            run_created_at,
            completed.evidence.observation_boundary,
            completed.evidence.market_data_snapshot_identity,
            successful_completed_at,
        )
        reference = publication.prepare(
            token,
            mtf=completed.mtf_fact_snapshot,
            native=completed.native_discovery_run,
            relative=completed.relative_context_run,
            provenance=provenance,
            continuity=completed.continuity_contribution,
        )
        del contribution
        # The committed bundle below owns the exact published analytical
        # artifacts.  The parent installs only workspace/evidence from the
        # completion, so do not transfer or retain a second object graph for
        # those same artifacts during the parent/child handoff.
        install_completed = replace(
            completed,
            mtf_fact_snapshot=None,
            native_discovery_run=None,
            relative_context_run=None,
            continuity_contribution=None,
        )
        del completed
        prepared_result = {}

        def authorize_commit(bundle):
            nonlocal install_completed
            result_path.touch(mode=0o600, exist_ok=False)
            with result_path.open("wb") as stream:
                encoded = _BoundedWriter(stream, MAX_RESULT_BYTES)
                with gzip.GzipFile(
                    fileobj=encoded,
                    mode="wb",
                    compresslevel=1,
                    mtime=0,
                ) as compressed:
                    decoded = _BoundedWriter(
                        compressed, MAX_DECODED_RESULT_BYTES
                    )
                    pickle.dump((install_completed, bundle), decoded, protocol=5)
            install_completed = None
            result_path.chmod(0o400)
            size = encoded.size
            decoded_size = decoded.size
            digest = _digest_file(result_path)
            peak = _rss_bytes(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            prepared_result.update(
                size=size,
                decoded_size=decoded_size,
                digest=digest,
                peak=peak,
            )
            _send(
                connection,
                (
                    "PREPARED",
                    reference,
                    successful_completed_at,
                    size,
                    decoded_size,
                    digest,
                    peak,
                ),
                MAX_REQUEST_BYTES,
            )
            response, _ = _receive(connection, MAX_RESPONSE_BYTES)
            return response[0] == "PRELOADED"

        def commit_ready(_bundle):
            _send(
                connection,
                ("COMMIT_READY", reference, successful_completed_at),
                MAX_REQUEST_BYTES,
            )
            response, _ = _receive(connection, MAX_RESPONSE_BYTES)
            return response[0] == "COMMIT"

        committed = publication.publish(
            token,
            reference,
            successful_completed_at,
            before_commit=authorize_commit,
            commit_ready=commit_ready,
        )
        if committed is None:
            raise RuntimeError("SWING_ANALYSIS_WORKER_STALE")
        peak = _rss_bytes(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        _send(
            connection,
            (
                "DONE",
                prepared_result["size"],
                prepared_result["decoded_size"],
                prepared_result["digest"],
                peak,
            ),
            MAX_REQUEST_BYTES,
        )
    except BaseException as error:
        try:
            envelope = _failure_envelope(
                error,
                operation=(UNKNOWN if proxy is None else proxy.last_operation),
                value=(None if proxy is None else proxy.last_value),
                worker_pid=os.getpid(),
                worker_exit_classification="WORKER_REPORTED_FAILURE",
            )
            _send(
                connection,
                ("ERROR", _safe_failure(error), envelope),
                MAX_REQUEST_BYTES,
            )
        except BaseException:
            pass
        raise
    finally:
        connection.close()


def _run_worker(
    capability,
    publication,
    calendar_publisher,
    token,
    *,
    analysis_run_identity,
    swing_run_identity,
    run_created_at,
    now,
    pace,
    progress_observer,
    completion_clock,
    authorize_commit,
    is_current,
    commit_scope,
    install_result,
    timeout_seconds,
    status_update,
):
    spec = _PublicationSpec(
        publication.root,
        publication.mtf_store._root,
        publication.native_store._root,
        publication.relative_store.root,
        publication.provenance_store.root,
        calendar_publisher._root,
    )
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=True)
    provider_calls = 0
    provider_bytes = 0
    historical_calls = 0
    with tempfile.TemporaryDirectory(prefix="kronos-swing-analysis-") as directory:
        result_path = Path(directory) / "result.pickle"
        process = context.Process(
            target=_worker,
            name="kronos-swing-analysis-process",
            args=(
                child,
                spec,
                token,
                analysis_run_identity,
                swing_run_identity,
                run_created_at,
                now,
                result_path,
            ),
        )
        process.start()
        status_update("RUNNING", process.pid, None)
        child.close()
        deadline = time.monotonic() + timeout_seconds
        done = None
        commit_authorized = False
        prepared_reference = None
        prepared_result = None
        last_operation = UNKNOWN
        last_value = None
        try:
            with ExitStack() as publication_transition:
                while time.monotonic() < deadline:
                    if not commit_authorized and not is_current():
                        break
                    if not parent.poll(0.05):
                        if not process.is_alive():
                            break
                        continue
                    message, _ = _receive(parent, MAX_REQUEST_BYTES)
                    operation = message[0]
                    last_operation = (
                        operation if operation in _FAILURE_OPERATIONS else UNKNOWN
                    )
                    last_value = message[1] if len(message) > 1 else None
                    provider_call = operation in {"INSTRUMENTS", "HISTORICAL"}
                    if provider_call:
                        provider_calls += 1
                        if provider_calls > MAX_PROVIDER_CALLS:
                            raise SwingAnalysisProcessError(
                                "SWING_ANALYSIS_WORKER_PROVIDER_CAPACITY",
                                diagnostic=_failure_envelope(
                                    RuntimeError(
                                        "SWING_ANALYSIS_WORKER_PROVIDER_CAPACITY"
                                    ),
                                    operation=operation,
                                    value=last_value,
                                    worker_pid=process.pid,
                                    worker_exit_classification="PARENT_FAILURE",
                                    provider_call_count=provider_calls,
                                    provider_response_bytes=provider_bytes,
                                ),
                            )
                    if operation == "INSTRUMENTS":
                        try:
                            value = capability.instrument_records(message[1])
                        except BaseException as error:
                            raise SwingAnalysisProcessError(
                                _safe_failure(error),
                                diagnostic=_failure_envelope(
                                    error,
                                    operation=operation,
                                    value=message[1],
                                    worker_pid=process.pid,
                                    worker_exit_classification=(
                                        "PARENT_PROVIDER_FAILURE"
                                    ),
                                    provider_call_count=provider_calls,
                                    provider_response_bytes=provider_bytes,
                                ),
                            ) from error
                    elif operation == "HISTORICAL":
                        if historical_calls:
                            pace()
                        historical_calls += 1
                        try:
                            value = capability.historical_candles(message[1])
                        except BaseException as error:
                            raise SwingAnalysisProcessError(
                                _safe_failure(error),
                                diagnostic=_failure_envelope(
                                    error,
                                    operation=operation,
                                    value=message[1],
                                    worker_pid=process.pid,
                                    worker_exit_classification=(
                                        "PARENT_PROVIDER_FAILURE"
                                    ),
                                    provider_call_count=provider_calls,
                                    provider_response_bytes=provider_bytes,
                                ),
                            ) from error
                    elif operation == "PROGRESS":
                        progress_observer(message[1])
                        value = None
                    elif operation == "CLOCK":
                        value = completion_clock()
                    elif operation == "PREPARED":
                        if commit_authorized:
                            raise RuntimeError(
                                "SWING_ANALYSIS_WORKER_PROTOCOL_INVALID"
                            )
                        status_update("PREPARED", process.pid, None)
                        prepared_reference = message[1]
                        _, _, _, size, decoded_size, digest, peak = message
                        if (
                            not result_path.is_file()
                            or result_path.stat().st_size != size
                            or result_path.stat().st_mode & 0o777 != 0o400
                            or size > MAX_RESULT_BYTES
                            or decoded_size > MAX_DECODED_RESULT_BYTES
                            or _digest_file(result_path) != digest
                        ):
                            raise RuntimeError(
                                "SWING_ANALYSIS_WORKER_RESULT_INVALID"
                            )
                        try:
                            with result_path.open("rb") as stream:
                                with gzip.GzipFile(
                                    fileobj=stream, mode="rb"
                                ) as compressed:
                                    decoded = _BoundedReader(
                                        compressed,
                                        MAX_DECODED_RESULT_BYTES,
                                    )
                                    completed, committed = pickle.load(decoded)
                                    if decoded.read(1) != b"":
                                        raise ValueError(
                                            "SWING_ANALYSIS_WORKER_RESULT_INVALID"
                                        )
                            if decoded.size != decoded_size:
                                raise ValueError(
                                    "SWING_ANALYSIS_WORKER_RESULT_INVALID"
                                )
                            _validate_result(
                                completed,
                                committed,
                                token,
                                analysis_run_identity,
                                prepared_reference,
                            )
                        except BaseException as error:
                            raise RuntimeError(
                                "SWING_ANALYSIS_WORKER_RESULT_INVALID"
                            ) from error
                        prepared_result = SwingAnalysisProcessResult(
                            completed,
                            committed,
                            provider_calls,
                            provider_bytes,
                            size,
                            decoded_size,
                            peak,
                        )
                        _send(parent, ("PRELOADED", None), MAX_RESPONSE_BYTES)
                        continue
                    elif operation == "COMMIT_READY":
                        publication_transition.enter_context(commit_scope())
                        if not authorize_commit(message[1], message[2]):
                            _send(
                                parent,
                                ("ABORT", "SWING_ANALYSIS_WORKER_STALE"),
                                MAX_RESPONSE_BYTES,
                            )
                            break
                        _send(parent, ("COMMIT", None), MAX_RESPONSE_BYTES)
                        commit_authorized = True
                        status_update("COMMITTING", process.pid, None)
                        continue
                    elif operation == "DONE":
                        done = message
                        break
                    elif operation == "ERROR":
                        envelope = _merge_failure_envelope(
                            message[2],
                            worker_pid=process.pid,
                            worker_exit_classification="WORKER_REPORTED_FAILURE",
                            worker_exit_code=process.exitcode,
                            provider_call_count=provider_calls,
                            provider_response_bytes=provider_bytes,
                        )
                        if commit_authorized:
                            raise SwingAnalysisProcessCompletionError(
                                message[1], diagnostic=envelope
                            )
                        raise SwingAnalysisProcessError(
                            message[1], diagnostic=envelope
                        )
                    else:
                        raise RuntimeError(
                            "SWING_ANALYSIS_WORKER_PROTOCOL_INVALID"
                        )
                    payload = _payload(("OK", value), MAX_RESPONSE_BYTES)
                    if (
                        provider_call
                        and provider_bytes + len(payload)
                        > MAX_TOTAL_PROVIDER_BYTES
                    ):
                        raise RuntimeError(
                            "SWING_ANALYSIS_WORKER_TRANSFER_CAPACITY"
                        )
                    parent.send_bytes(payload)
                    if provider_call:
                        provider_bytes += len(payload)
                if done is None:
                    if time.monotonic() >= deadline:
                        failure = "SWING_ANALYSIS_WORKER_TIMEOUT"
                        classification = "TIMEOUT"
                    elif not process.is_alive():
                        failure = "SWING_ANALYSIS_WORKER_FAILED"
                        classification = "ABNORMAL_EXIT"
                    else:
                        failure = "SWING_ANALYSIS_WORKER_STALE"
                        classification = "STALE"
                    envelope = _failure_envelope(
                        RuntimeError(failure),
                        operation=last_operation,
                        value=last_value,
                        worker_pid=process.pid,
                        worker_exit_classification=classification,
                        worker_exit_code=process.exitcode,
                        provider_call_count=provider_calls,
                        provider_response_bytes=provider_bytes,
                    )
                    if commit_authorized:
                        raise SwingAnalysisProcessCompletionError(
                            failure, diagnostic=envelope
                        )
                    raise SwingAnalysisProcessError(
                        failure, diagnostic=envelope
                    )
                _, size, decoded_size, digest, peak = done
                if (
                    prepared_result is None
                    or not result_path.is_file()
                    or result_path.stat().st_size != size
                    or size > MAX_RESULT_BYTES
                    or decoded_size > MAX_DECODED_RESULT_BYTES
                    or prepared_result.result_bytes != size
                    or prepared_result.decoded_result_bytes != decoded_size
                    or digest != _digest_file(result_path)
                    or prepared_result.worker_peak_rss_bytes > peak
                ):
                    raise SwingAnalysisProcessCompletionError(
                        "SWING_ANALYSIS_WORKER_RESULT_INVALID",
                        diagnostic=_failure_envelope(
                            RuntimeError("SWING_ANALYSIS_WORKER_RESULT_INVALID"),
                            operation="DONE",
                            worker_pid=process.pid,
                            worker_exit_classification="COMPLETION_FAILURE",
                            worker_exit_code=process.exitcode,
                            provider_call_count=provider_calls,
                            provider_response_bytes=provider_bytes,
                        ),
                    )
                result = replace(
                    prepared_result,
                    worker_peak_rss_bytes=peak,
                )
                if install_result(result) is not True:
                    raise SwingAnalysisProcessCompletionError(
                        "SWING_ANALYSIS_WORKER_RESULT_NOT_INSTALLED",
                        diagnostic=_failure_envelope(
                            RuntimeError(
                                "SWING_ANALYSIS_WORKER_RESULT_NOT_INSTALLED"
                            ),
                            operation="DONE",
                            worker_pid=process.pid,
                            worker_exit_classification="COMPLETION_FAILURE",
                            worker_exit_code=process.exitcode,
                            provider_call_count=provider_calls,
                            provider_response_bytes=provider_bytes,
                        ),
                    )
                publication_transition.close()
                process.join(TERMINATION_SECONDS)
                if process.is_alive() or process.exitcode != 0:
                    raise SwingAnalysisProcessCleanupError(
                        "SWING_ANALYSIS_WORKER_CLEANUP_FAILED",
                        diagnostic=_failure_envelope(
                            RuntimeError("SWING_ANALYSIS_WORKER_CLEANUP_FAILED"),
                            operation="DONE",
                            worker_pid=process.pid,
                            worker_exit_classification="CLEANUP_FAILURE",
                            worker_exit_code=process.exitcode,
                            provider_call_count=provider_calls,
                            provider_response_bytes=provider_bytes,
                        ),
                    )
                return result
        except SwingAnalysisProcessError:
            raise
        except BaseException as error:
            classification = (
                "COMPLETION_FAILURE" if commit_authorized else "PARENT_FAILURE"
            )
            envelope = _failure_envelope(
                error,
                operation=last_operation,
                value=last_value,
                worker_pid=process.pid,
                worker_exit_classification=classification,
                worker_exit_code=process.exitcode,
                provider_call_count=provider_calls,
                provider_response_bytes=provider_bytes,
            )
            failure = _safe_failure(error)
            if commit_authorized:
                raise SwingAnalysisProcessCompletionError(
                    failure, diagnostic=envelope
                ) from error
            raise SwingAnalysisProcessError(
                failure, diagnostic=envelope
            ) from error
        finally:
            parent.close()
            if process.is_alive():
                process.terminate()
                process.join(TERMINATION_SECONDS)
            if process.is_alive():
                raise SwingAnalysisProcessCleanupError(
                    "SWING_ANALYSIS_WORKER_CLEANUP_FAILED",
                    diagnostic=_failure_envelope(
                        RuntimeError("SWING_ANALYSIS_WORKER_CLEANUP_FAILED"),
                        operation=last_operation,
                        value=last_value,
                        worker_pid=process.pid,
                        worker_exit_classification="CLEANUP_FAILURE",
                        worker_exit_code=process.exitcode,
                        provider_call_count=provider_calls,
                        provider_response_bytes=provider_bytes,
                    ),
                )


class SwingAnalysisProcessOwner:
    """Admit no queue and own one spawned analysis generation to termination."""

    def __init__(self, *, timeout_seconds: float = WORKER_TIMEOUT_SECONDS) -> None:
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not 1.0 <= timeout_seconds <= WORKER_TIMEOUT_SECONDS
        ):
            raise ValueError("SWING_ANALYSIS_WORKER_TIMEOUT_INVALID")
        self._timeout_seconds = float(timeout_seconds)
        self._lock = Lock()
        self._active = False
        self._state = "IDLE"
        self._pid = None
        self._generation = None
        self._failure = None
        self._failure_diagnostic = None
        self._last_provider_calls = 0
        self._last_provider_bytes = 0
        self._last_result_bytes = 0
        self._last_decoded_result_bytes = 0
        self._last_worker_peak_rss_bytes = 0

    def status(self):
        """Return compact ownership facts without polling or joining a worker."""

        with self._lock:
            return {
                "state": self._state,
                "pid": self._pid,
                "generation": self._generation,
                "failure": self._failure,
                "failure_diagnostic": (
                    None
                    if self._failure_diagnostic is None
                    else self._failure_diagnostic.projection()
                ),
                "owned_workers": int(self._active),
                "maximum_owned_workers": 1,
                "queued_jobs": 0,
                "maximum_queued_jobs": 0,
                "maximum_provider_calls": MAX_PROVIDER_CALLS,
                "maximum_provider_response_bytes": MAX_TOTAL_PROVIDER_BYTES,
                "maximum_result_bytes": MAX_RESULT_BYTES,
                "maximum_decoded_result_bytes": MAX_DECODED_RESULT_BYTES,
                "deadline_seconds": self._timeout_seconds,
                "last_provider_calls": self._last_provider_calls,
                "last_provider_response_bytes": self._last_provider_bytes,
                "last_result_bytes": self._last_result_bytes,
                "last_decoded_result_bytes": self._last_decoded_result_bytes,
                "last_worker_peak_rss_bytes": self._last_worker_peak_rss_bytes,
            }

    def execute(
        self,
        capability,
        publication,
        calendar_publisher,
        token,
        *,
        generation,
        analysis_run_identity,
        swing_run_identity,
        run_created_at,
        now,
        pace,
        progress_observer,
        completion_clock,
        authorize_commit,
        is_current,
        commit_scope,
        install_result,
    ) -> SwingAnalysisProcessResult:
        """Run one generation; the parent retains Provider and commit authority."""

        with self._lock:
            if self._active:
                raise SwingAnalysisProcessError("SWING_ANALYSIS_WORKER_CAPACITY")
            self._active = True
            self._state = "STARTING"
            self._pid = None
            self._generation = generation
            self._failure = None
            self._failure_diagnostic = None

        def update(state, pid, failure):
            with self._lock:
                if self._generation == generation:
                    self._state = state
                    self._pid = pid
                    self._failure = failure

        def retain_failure(state, pid, failure, error, classification):
            diagnostic = getattr(error, "diagnostic", None)
            if type(diagnostic) is not SwingAnalysisFailureEnvelope:
                diagnostic = _failure_envelope(
                    error,
                    worker_pid=self._pid,
                    worker_exit_classification=classification,
                )
            with self._lock:
                if self._generation == generation:
                    self._state = state
                    self._pid = pid
                    self._failure = failure
                    self._failure_diagnostic = diagnostic
                    self._last_provider_calls = diagnostic.provider_call_count
                    self._last_provider_bytes = diagnostic.provider_response_bytes

        try:
            result = _run_worker(
                capability,
                publication,
                calendar_publisher,
                token,
                analysis_run_identity=analysis_run_identity,
                swing_run_identity=swing_run_identity,
                run_created_at=run_created_at,
                now=now,
                pace=pace,
                progress_observer=progress_observer,
                completion_clock=completion_clock,
                authorize_commit=authorize_commit,
                is_current=is_current,
                commit_scope=commit_scope,
                install_result=install_result,
                timeout_seconds=self._timeout_seconds,
                status_update=update,
            )
        except SwingAnalysisProcessCleanupError as error:
            retain_failure(
                "CLEANUP_FAILED",
                self._pid,
                "SWING_ANALYSIS_WORKER_CLEANUP_FAILED",
                error,
                "CLEANUP_FAILURE",
            )
            raise
        except SwingAnalysisProcessCompletionError as error:
            retain_failure(
                "COMPLETION_FAILED",
                None,
                "SWING_ANALYSIS_WORKER_RESULT_INVALID",
                error,
                "COMPLETION_FAILURE",
            )
            raise
        except BaseException as error:
            failure = _safe_failure(error)
            retain_failure("FAILED", None, failure, error, "PARENT_FAILURE")
            raise SwingAnalysisProcessError(
                failure,
                diagnostic=self._failure_diagnostic,
            ) from error
        with self._lock:
            self._state = "COMPLETED"
            self._pid = None
            self._failure = None
            self._failure_diagnostic = None
            self._last_provider_calls = result.provider_call_count
            self._last_provider_bytes = result.provider_response_bytes
            self._last_result_bytes = result.result_bytes
            self._last_decoded_result_bytes = result.decoded_result_bytes
            self._last_worker_peak_rss_bytes = result.worker_peak_rss_bytes
        return result

    def release(self, generation) -> None:
        """Release completed ownership after the application installs the result."""

        with self._lock:
            if self._generation != generation:
                return
            if self._state == "CLEANUP_FAILED":
                return
            self._active = False
            self._generation = None
            if self._state == "COMPLETED":
                self._state = "IDLE"
