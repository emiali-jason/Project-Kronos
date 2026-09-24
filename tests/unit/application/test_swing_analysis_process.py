from contextlib import nullcontext
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from kronos.application import swing_analysis_process as process
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.market_data import (
    HistoricalCandleRequest,
    HistoricalDataError,
    HistoricalDataFailure,
    HistoricalInterval,
)
from kronos.provider.exceptions.connectivity import (
    ProviderConnectivityError,
    ProviderErrorCode,
)


def _execute(owner, **overrides):
    arguments = {
        "generation": 7,
        "analysis_run_identity": "ANALYSIS-000007",
        "swing_run_identity": "SWING-RUN-00000000000000000000000000000007",
        "run_created_at": object(),
        "now": object(),
        "pace": lambda: None,
        "progress_observer": lambda _value: None,
        "completion_clock": lambda: object(),
        "authorize_commit": lambda _reference, _completed_at: True,
        "is_current": lambda: True,
        "commit_scope": nullcontext,
        "install_result": lambda _result: True,
    }
    arguments.update(overrides)
    return owner.execute(object(), object(), object(), object(), **arguments)


def test_owner_has_one_worker_no_queue_and_releases_completed_generation(
    monkeypatch,
) -> None:
    owner = process.SwingAnalysisProcessOwner(timeout_seconds=12)
    expected = process.SwingAnalysisProcessResult(
        object(), object(), 99, 1234, 5678, 8000, 9012
    )

    def run(*_args, **kwargs):
        state = owner.status()
        assert state["state"] == "STARTING"
        assert state["owned_workers"] == 1
        assert state["queued_jobs"] == state["maximum_queued_jobs"] == 0
        with pytest.raises(process.SwingAnalysisProcessError, match="CAPACITY"):
            _execute(owner, generation=8)
        kwargs["status_update"]("RUNNING", 12345, None)
        assert kwargs["install_result"](expected)
        return expected

    monkeypatch.setattr(process, "_run_worker", run)
    assert _execute(owner) is expected
    completed = owner.status()
    assert completed["state"] == "COMPLETED"
    assert completed["owned_workers"] == 1
    assert completed["last_provider_calls"] == 99
    assert completed["last_provider_response_bytes"] == 1234
    assert completed["last_result_bytes"] == 5678
    assert completed["last_decoded_result_bytes"] == 8000
    assert completed["last_worker_peak_rss_bytes"] == 9012
    owner.release(7)
    assert owner.status()["state"] == "IDLE"
    assert owner.status()["owned_workers"] == 0


def test_unproved_cleanup_remains_owned_and_refuses_retry(monkeypatch) -> None:
    owner = process.SwingAnalysisProcessOwner()
    monkeypatch.setattr(
        process,
        "_run_worker",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            process.SwingAnalysisProcessCleanupError(
                "SWING_ANALYSIS_WORKER_CLEANUP_FAILED"
            )
        ),
    )
    with pytest.raises(process.SwingAnalysisProcessCleanupError):
        _execute(owner)
    owner.release(7)
    status = owner.status()
    assert status["state"] == "CLEANUP_FAILED"
    assert status["failure"] == "SWING_ANALYSIS_WORKER_CLEANUP_FAILED"
    assert status["failure_diagnostic"] == {
        "operation": "UNKNOWN",
        "exchange": "UNKNOWN",
        "instrument": "UNKNOWN",
        "provider_failure_code": "UNKNOWN",
        "exception_class": "SwingAnalysisProcessCleanupError",
        "worker_pid": "UNKNOWN",
        "worker_exit_classification": "CLEANUP_FAILURE",
        "worker_exit_code": "UNKNOWN",
        "provider_call_count": 0,
        "provider_response_bytes": 0,
    }
    assert status["owned_workers"] == 1
    with pytest.raises(process.SwingAnalysisProcessError, match="CAPACITY"):
        _execute(owner, generation=8)


def test_completion_failure_is_visible_after_proved_worker_exit(monkeypatch) -> None:
    owner = process.SwingAnalysisProcessOwner()
    monkeypatch.setattr(
        process,
        "_run_worker",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            process.SwingAnalysisProcessCompletionError(
                "SWING_ANALYSIS_WORKER_RESULT_INVALID"
            )
        ),
    )
    with pytest.raises(process.SwingAnalysisProcessCompletionError):
        _execute(owner)
    owner.release(7)
    status = owner.status()
    assert status["state"] == "COMPLETION_FAILED"
    assert status["owned_workers"] == 0
    assert status["failure"] == "SWING_ANALYSIS_WORKER_RESULT_INVALID"
    assert status["failure_diagnostic"]["worker_exit_classification"] == (
        "COMPLETION_FAILURE"
    )


def test_parent_provider_failures_retain_only_enumerated_bounded_context() -> None:
    instrument_failure = process._failure_envelope(
        ProviderConnectivityError(ProviderErrorCode.NETWORK_TIMEOUT),
        operation="INSTRUMENTS",
        value="NSE",
        worker_pid=43210,
        worker_exit_classification="PARENT_PROVIDER_FAILURE",
        provider_call_count=1,
        provider_response_bytes=0,
    )
    assert instrument_failure.projection() == {
        "operation": "INSTRUMENTS",
        "exchange": "NSE",
        "instrument": "UNKNOWN",
        "provider_failure_code": "NETWORK_TIMEOUT",
        "exception_class": "ProviderConnectivityError",
        "worker_pid": 43210,
        "worker_exit_classification": "PARENT_PROVIDER_FAILURE",
        "worker_exit_code": "UNKNOWN",
        "provider_call_count": 1,
        "provider_response_bytes": 0,
    }

    request = HistoricalCandleRequest(
        instrument=InstrumentRecord(
            provider="KITE",
            exchange="NSE",
            segment="NSE",
            trading_symbol="RELIANCE",
            name="RELIANCE",
            instrument_type="EQ",
            expiry=None,
            tick_size=Decimal("0.05"),
            lot_size=1,
        ),
        start=datetime(2026, 9, 1, tzinfo=UTC),
        end=datetime(2026, 9, 2, tzinfo=UTC),
        interval=HistoricalInterval.DAY,
    )
    historical_failure = process._failure_envelope(
        HistoricalDataError(HistoricalDataFailure.PROVIDER_FAILURE),
        operation="HISTORICAL",
        value=request,
        worker_pid=43211,
        worker_exit_classification="PARENT_PROVIDER_FAILURE",
        provider_call_count=2,
        provider_response_bytes=128,
    )
    assert historical_failure.exchange == "NSE"
    assert historical_failure.instrument == "RELIANCE"
    assert historical_failure.provider_failure_code == "PROVIDER_FAILURE"
    assert historical_failure.provider_call_count == 2
    assert historical_failure.provider_response_bytes == 128


def test_owner_retains_worker_envelope_and_failure_metrics_after_release(
    monkeypatch,
) -> None:
    owner = process.SwingAnalysisProcessOwner()
    diagnostic = process.SwingAnalysisFailureEnvelope(
        operation="HISTORICAL",
        exchange="NSE",
        instrument="RELIANCE",
        provider_failure_code="NETWORK_TIMEOUT",
        exception_class="ProviderConnectivityError",
        worker_pid=44123,
        worker_exit_classification="WORKER_REPORTED_FAILURE",
        worker_exit_code=1,
        provider_call_count=17,
        provider_response_bytes=8192,
    )
    monkeypatch.setattr(
        process,
        "_run_worker",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            process.SwingAnalysisProcessError(
                "SWING_ANALYSIS_WORKER_FAILED", diagnostic=diagnostic
            )
        ),
    )

    with pytest.raises(process.SwingAnalysisProcessError) as failure:
        _execute(owner)
    assert failure.value.diagnostic == diagnostic
    owner.release(7)
    status = owner.status()
    assert status["state"] == "FAILED"
    assert status["owned_workers"] == 0
    assert status["pid"] is None
    assert status["last_provider_calls"] == 17
    assert status["last_provider_response_bytes"] == 8192
    assert status["failure_diagnostic"] == diagnostic.projection()


def test_unknown_failure_details_are_explicit_and_secret_text_is_not_retained() -> None:
    error = RuntimeError("access_token=forbidden raw provider payload")
    diagnostic = process._failure_envelope(
        error,
        operation="WORKER",
        worker_exit_classification="WORKER_REPORTED_FAILURE",
    )
    assert diagnostic.exchange == "UNKNOWN"
    assert diagnostic.instrument == "UNKNOWN"
    assert diagnostic.provider_failure_code == "UNKNOWN"
    assert diagnostic.worker_pid == "UNKNOWN"
    assert diagnostic.worker_exit_code == "UNKNOWN"
    assert "forbidden" not in repr(diagnostic).lower()
    assert "access_token" not in repr(diagnostic).lower()


def test_transfer_and_result_writers_enforce_byte_limits(tmp_path) -> None:
    from io import BytesIO

    with pytest.raises(RuntimeError, match="TRANSFER_CAPACITY"):
        process._payload(b"x" * 100, 10)
    with (tmp_path / "bounded").open("wb") as stream:
        writer = process._BoundedWriter(stream, 4)
        assert writer.write(b"1234") == 4
        with pytest.raises(RuntimeError, match="RESULT_CAPACITY"):
            writer.write(b"5")
    reader = process._BoundedReader(BytesIO(b"12345"), 4)
    assert reader.read(4) == b"1234"
    with pytest.raises(RuntimeError, match="RESULT_CAPACITY"):
        reader.read(1)


def test_owner_rejects_invalid_deadlines_and_reports_fixed_limits() -> None:
    for value in (True, 0, process.WORKER_TIMEOUT_SECONDS + 1):
        with pytest.raises(ValueError, match="TIMEOUT_INVALID"):
            process.SwingAnalysisProcessOwner(timeout_seconds=value)
    status = process.SwingAnalysisProcessOwner().status()
    assert status["maximum_owned_workers"] == 1
    assert status["maximum_queued_jobs"] == 0
    assert status["maximum_provider_calls"] == process.MAX_PROVIDER_CALLS
    assert (
        status["maximum_provider_response_bytes"]
        == process.MAX_TOTAL_PROVIDER_BYTES
    )
    assert status["maximum_result_bytes"] == process.MAX_RESULT_BYTES
    assert (
        status["maximum_decoded_result_bytes"]
        == process.MAX_DECODED_RESULT_BYTES
    )
    assert process._rss_bytes(123, "darwin") == 123
    assert process._rss_bytes(123, "linux") == 123 * 1024


def test_application_requires_the_exact_process_owner_type() -> None:
    from kronos.application.swing_opportunities import SwingOpportunitiesApplication

    with pytest.raises(TypeError, match="BROWSER_APPLICATION_DEPENDENCY_INVALID"):
        SwingOpportunitiesApplication(
            lambda: object(),
            analysis_process_owner=SimpleNamespace(),
        )
    application = SwingOpportunitiesApplication(
        lambda: object(),
        analysis_process_owner=process.SwingAnalysisProcessOwner(),
    )
    assert application.analysis_execution_status()["state"] == "IDLE"
