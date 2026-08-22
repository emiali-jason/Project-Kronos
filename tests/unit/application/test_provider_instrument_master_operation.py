from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace

import pytest

from kronos.application.provider_instrument_master_operation import (
    P1ContextAvailability,
    P1OperationalFailure,
    P1OperationalStage,
    P1OperationalState,
    ProviderInstrumentMasterOperationalComposition,
    p1_operational_result_document,
)
from kronos.intraday.universe import (
    IntradayMarketFamily,
    load_intraday_universe_publication,
)
from kronos.provider.contracts.instrument_master import (
    KITE_INSTRUMENT_MASTER_DATASET,
    KITE_INSTRUMENT_MASTER_OPERATION,
    ProviderInstrumentDiagnosticPhase,
    ProviderInstrumentFieldFamily,
    ProviderInstrumentMasterSourceRecord,
    ProviderInstrumentValidationRule,
    ProviderInstrumentValueClassification,
    provider_instrument_schema_error,
)
from kronos.provider.instrument_master_persistence import (
    ProviderInstrumentSnapshotStore,
)


NOW = datetime(2026, 8, 22, 13, 30, tzinfo=timezone.utc)
RUN_1 = "KRONOS-P1-OPERATION-TEST-0001"
RUN_2 = "KRONOS-P1-OPERATION-TEST-0002"


class _Runtime:
    provider_identity = "KITE"
    authenticated_context_identity = "AUTH-CONTEXT-OPAQUE-1"

    def __init__(
        self,
        records: tuple[ProviderInstrumentMasterSourceRecord, ...],
        *,
        lifecycle: str = "ACTIVE",
        operation_available: bool = True,
        failure: Exception | None = None,
        entered: Event | None = None,
        release: Event | None = None,
    ) -> None:
        self.records = records
        self.lifecycle = lifecycle
        self.operation_available = operation_available
        self.failure = failure
        self.entered = entered
        self.release = release
        self.calls: list[str] = []

    @property
    def lifecycle_state(self):  # type: ignore[no-untyped-def]
        return SimpleNamespace(value=self.lifecycle)

    @property
    def provider_instrument_master_operation_available(self) -> bool:
        return self.operation_available

    def acquire_provider_instrument_master_records(
        self,
        *,
        operation_identity: str,
    ) -> tuple[ProviderInstrumentMasterSourceRecord, ...]:
        self.calls.append(operation_identity)
        if self.entered is not None:
            self.entered.set()
        if self.release is not None:
            assert self.release.wait(timeout=3)
        if self.failure is not None:
            raise self.failure
        return self.records


def _composition(tmp_path: Path, runtime: _Runtime):  # type: ignore[no-untyped-def]
    return ProviderInstrumentMasterOperationalComposition(
        runtime,
        store=ProviderInstrumentSnapshotStore(tmp_path.resolve()),
        universe=load_intraday_universe_publication(),
        clock=lambda: NOW,
    )


def _record(
    token: int,
    symbol: str,
    *,
    exchange: str = "NSE",
    segment: str = "NSE",
    name: str | None = None,
    instrument_type: str = "EQ",
    expiry: date | None = None,
    lot: int = 1,
    tick: str = "0.05",
) -> ProviderInstrumentMasterSourceRecord:
    return ProviderInstrumentMasterSourceRecord(
        provider="KITE",
        provider_instrument_token=token,
        exchange_token=token // 256,
        trading_symbol=symbol,
        name=symbol if name is None else name,
        last_price=Decimal("0"),
        expiry=expiry,
        strike=Decimal("0"),
        tick_size=Decimal(tick),
        lot_size=lot,
        instrument_type=instrument_type,
        segment=segment,
        exchange=exchange,
    )


def _complete_records() -> tuple[ProviderInstrumentMasterSourceRecord, ...]:
    universe = load_intraday_universe_publication()
    records: list[ProviderInstrumentMasterSourceRecord] = []
    token = 1000
    for member in universe.members:
        token += 1
        if member.market_family is IntradayMarketFamily.NSE_EQUITY:
            symbol = (
                "BAJAJ-AUTO"
                if member.sponsor_label == "BAJAJ_AUTO"
                else member.sponsor_label
            )
            records.append(_record(token, symbol, name=member.sponsor_label))
        elif member.market_family is IntradayMarketFamily.NSE_INDEX:
            symbol = {
                "NIFTY": "NIFTY 50",
                "BANKNIFTY": "NIFTY BANK",
            }[member.sponsor_label]
            records.append(_record(token, symbol, segment="INDICES", name=symbol))
        else:
            for offset, expiry in enumerate(
                (date(2026, 8, 28), date(2026, 9, 28))
            ):
                records.append(_record(
                    token * 10 + offset,
                    f"{member.sponsor_label}{expiry:%y%b}FUT".upper(),
                    exchange="MCX",
                    segment="MCX-FUT",
                    name=member.sponsor_label,
                    instrument_type="FUT",
                    expiry=expiry,
                    lot=100,
                    tick="1",
                ))
    records.append(_record(999999, "PROVIDER-ONLY", exchange="BSE", segment="BSE"))
    return tuple(records)


def test_absent_actual_context_fails_even_when_presentation_claims_connected(
    tmp_path: Path,
) -> None:
    runtime = _Runtime(_complete_records(), lifecycle="ABSENT")
    composition = _composition(tmp_path, runtime)
    restored_presentation_state = "CONNECTED"

    result = composition.run(operation_identity=RUN_1)

    assert restored_presentation_state == "CONNECTED"
    assert result.state is P1OperationalState.FAILED
    assert result.context_availability is P1ContextAvailability.CONTEXT_UNAVAILABLE
    assert result.stage is P1OperationalStage.CONTEXT_VERIFICATION
    assert result.failure is P1OperationalFailure.CONTEXT_UNAVAILABLE
    assert runtime.calls == []


def test_active_shared_context_runs_one_unfiltered_persist_reload_and_manifest(
    tmp_path: Path,
) -> None:
    records = _complete_records()
    runtime = _Runtime(records)
    composition = _composition(tmp_path, runtime)
    swing_state = {"provider": "CONNECTED", "analysis": "NOT RUN"}
    intraday_state = {"availability": "UNCHANGED"}

    result = composition.run(operation_identity=RUN_1)
    document = p1_operational_result_document(result)

    assert result.state is P1OperationalState.COMPLETE
    assert result.stage is P1OperationalStage.COMPLETE
    assert result.provider == "KITE"
    assert result.dataset_identity == KITE_INSTRUMENT_MASTER_DATASET
    assert result.record_count == len(records)
    assert result.component_request_count == 1
    assert result.reload_verified
    assert result.commissioning_member_count == 98
    assert runtime.calls == [KITE_INSTRUMENT_MASTER_OPERATION]
    assert ("BSE", 1) in result.exchange_counts
    assert dict(result.commissioning_status_counts) == {
        "MULTIPLE_PROVIDER_CONTRACT_RECORDS": 5,
        "PROVIDER_INDEX_RECORD_CANDIDATE": 2,
        "UNIQUE_PROVIDER_RECORD": 91,
    }
    assert swing_state == {"provider": "CONNECTED", "analysis": "NOT RUN"}
    assert intraday_state == {"availability": "UNCHANGED"}
    assert "provider_instrument_token" not in json.dumps(document)
    assert "canonical" not in json.dumps(document).lower()
    assert "execution_eligibility" not in json.dumps(document)
    assert all(
        member["status"] != "ACTIVE_CONTRACT_SELECTED"
        for member in document["commissioning_members"]  # type: ignore[index]
    )


def test_same_identity_is_idempotent_and_distinct_identity_is_future_snapshot(
    tmp_path: Path,
) -> None:
    runtime = _Runtime(_complete_records())
    composition = _composition(tmp_path, runtime)

    first = composition.run(operation_identity=RUN_1)
    repeated = composition.run(operation_identity=RUN_1)
    second = composition.run(operation_identity=RUN_2)

    assert repeated is first
    assert first.snapshot_identity != second.snapshot_identity
    assert runtime.calls == [
        KITE_INSTRUMENT_MASTER_OPERATION,
        KITE_INSTRUMENT_MASTER_OPERATION,
    ]


def test_concurrent_invocation_is_rejected_without_second_acquisition(
    tmp_path: Path,
) -> None:
    entered = Event()
    release = Event()
    runtime = _Runtime(_complete_records(), entered=entered, release=release)
    composition = _composition(tmp_path, runtime)
    completed: list[object] = []
    thread = Thread(
        target=lambda: completed.append(
            composition.run(operation_identity=RUN_1)
        )
    )
    thread.start()
    assert entered.wait(timeout=3)

    duplicate = composition.run(operation_identity=RUN_1)
    rejected = composition.run(operation_identity=RUN_2)
    release.set()
    thread.join(timeout=3)

    assert duplicate.failure is P1OperationalFailure.ACQUISITION_ALREADY_RUNNING
    assert rejected.failure is P1OperationalFailure.ACQUISITION_ALREADY_RUNNING
    assert len(completed) == 1
    assert composition.result(RUN_1) is completed[0]
    assert runtime.calls == [KITE_INSTRUMENT_MASTER_OPERATION]


def test_provider_exception_is_stage_sanitized_without_retry_or_secret(
    tmp_path: Path,
) -> None:
    secret = "raw-provider-secret-bearing-exception"
    runtime = _Runtime(_complete_records(), failure=RuntimeError(secret))
    composition = _composition(tmp_path, runtime)

    first = composition.run(operation_identity=RUN_1)
    repeated = composition.run(operation_identity=RUN_1)
    rendered = json.dumps(p1_operational_result_document(first)) + repr(first)

    assert first.failure is P1OperationalFailure.PROVIDER_ACQUISITION_FAILED
    assert first.stage is P1OperationalStage.INSTRUMENT_MASTER_ACQUISITION
    assert repeated is first
    assert runtime.calls == [KITE_INSTRUMENT_MASTER_OPERATION]
    assert secret not in rendered
    assert "traceback" not in rendered.lower()


@pytest.mark.parametrize(
    ("phase", "expected_stage"),
    [
        (
            ProviderInstrumentDiagnosticPhase.PROVIDER_NORMALIZATION,
            P1OperationalStage.INSTRUMENT_MASTER_ACQUISITION,
        ),
        (
            ProviderInstrumentDiagnosticPhase.SNAPSHOT_CONSTRUCTION,
            P1OperationalStage.SNAPSHOT_CONSTRUCTION,
        ),
        (
            ProviderInstrumentDiagnosticPhase.SNAPSHOT_VALIDATION,
            P1OperationalStage.SNAPSHOT_VALIDATION,
        ),
    ],
)
def test_typed_schema_failure_preserves_phase_and_is_cached_without_retry(
    tmp_path: Path,
    phase: ProviderInstrumentDiagnosticPhase,
    expected_stage: P1OperationalStage,
) -> None:
    failure = provider_instrument_schema_error(
        phase=phase,
        rule=ProviderInstrumentValidationRule.SYMBOL_REQUIRED,
        field_family=ProviderInstrumentFieldFamily.SYMBOL,
        value_classification=ProviderInstrumentValueClassification.MISSING,
        input_ordinal=7,
    )
    runtime = _Runtime(_complete_records(), failure=failure)
    composition = _composition(tmp_path, runtime)

    first = composition.run(operation_identity=RUN_1)
    repeated = composition.run(operation_identity=RUN_1)
    document = p1_operational_result_document(first)

    assert repeated is first
    assert runtime.calls == [KITE_INSTRUMENT_MASTER_OPERATION]
    assert first.failure is P1OperationalFailure.SNAPSHOT_SCHEMA_INVALID
    assert first.stage is expected_stage
    assert first.diagnostic is failure.diagnostic
    assert first.diagnostic_at == NOW
    assert document["diagnostic_phase"] == phase.value
    assert document["validation_rule"] == "SYMBOL_REQUIRED"
    assert document["field_family"] == "SYMBOL"
    assert document["value_classification"] == "MISSING"
    assert document["input_ordinal"] == 7
    assert document["affected_count"] == 1
    assert document["record_locator"] == failure.diagnostic.record_locator
    assert document["diagnostic_at"] == NOW.isoformat()


def test_typed_diagnostic_and_operational_projection_exclude_injected_secrets(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    forbidden = (
        "access_token=SENSITIVE_ACCESS "
        "api_secret=SENSITIVE_SECRET "
        "request_token=SENSITIVE_REQUEST "
        "Authorization: Bearer SENSITIVE_BEARER "
        "provider_token=738561 provider_symbol=RELIANCE "
        "arbitrary exception text"
    )
    failure = provider_instrument_schema_error(
        phase=ProviderInstrumentDiagnosticPhase.PROVIDER_NORMALIZATION,
        rule=ProviderInstrumentValidationRule.STRIKE_INVALID,
        field_family=ProviderInstrumentFieldFamily.STRIKE,
        value_classification=ProviderInstrumentValueClassification.MALFORMED,
        input_ordinal=3,
    )
    failure.__cause__ = RuntimeError(forbidden)
    runtime = _Runtime(_complete_records(), failure=failure)
    composition = _composition(tmp_path, runtime)

    first = composition.run(operation_identity=RUN_1)
    cached = composition.run(operation_identity=RUN_1)
    rendered = (
        repr(failure)
        + repr(failure.diagnostic)
        + repr(first)
        + repr(cached)
        + json.dumps(p1_operational_result_document(first))
        + caplog.text
    )

    assert cached is first
    assert runtime.calls == [KITE_INSTRUMENT_MASTER_OPERATION]
    for prohibited in (
        "SENSITIVE_ACCESS",
        "SENSITIVE_SECRET",
        "SENSITIVE_REQUEST",
        "SENSITIVE_BEARER",
        "738561",
        "RELIANCE",
        "arbitrary exception text",
        "traceback",
    ):
        assert prohibited.lower() not in rendered.lower()


def test_record_locator_is_deterministic_and_uses_only_safe_context() -> None:
    first = provider_instrument_schema_error(
        phase=ProviderInstrumentDiagnosticPhase.PROVIDER_NORMALIZATION,
        rule=ProviderInstrumentValidationRule.TICK_REQUIRED,
        field_family=ProviderInstrumentFieldFamily.TICK_SIZE,
        value_classification=ProviderInstrumentValueClassification.NULL,
        input_ordinal=9,
    ).diagnostic
    repeated = provider_instrument_schema_error(
        phase=ProviderInstrumentDiagnosticPhase.PROVIDER_NORMALIZATION,
        rule=ProviderInstrumentValidationRule.TICK_REQUIRED,
        field_family=ProviderInstrumentFieldFamily.TICK_SIZE,
        value_classification=ProviderInstrumentValueClassification.NULL,
        input_ordinal=9,
    ).diagnostic
    different_ordinal = provider_instrument_schema_error(
        phase=ProviderInstrumentDiagnosticPhase.PROVIDER_NORMALIZATION,
        rule=ProviderInstrumentValidationRule.TICK_REQUIRED,
        field_family=ProviderInstrumentFieldFamily.TICK_SIZE,
        value_classification=ProviderInstrumentValueClassification.NULL,
        input_ordinal=10,
    ).diagnostic

    assert first is not None and repeated is not None and different_ordinal is not None
    assert first.record_locator == repeated.record_locator
    assert first.record_locator != different_ordinal.record_locator
    assert first.record_locator.startswith("PROVIDER-SCHEMA-LOCATOR-")


def test_exchange_token_subfield_projects_without_raw_identity_value(
    tmp_path: Path,
) -> None:
    failure = provider_instrument_schema_error(
        phase=ProviderInstrumentDiagnosticPhase.PROVIDER_NORMALIZATION,
        rule=ProviderInstrumentValidationRule.PROVIDER_RECORD_IDENTITY_INVALID,
        field_family=ProviderInstrumentFieldFamily.EXCHANGE_TOKEN,
        value_classification=ProviderInstrumentValueClassification.MALFORMED,
        input_ordinal=1,
    )
    failure.__cause__ = RuntimeError("RAW-EXCHANGE-TOKEN-VALUE")
    runtime = _Runtime(_complete_records(), failure=failure)
    composition = _composition(tmp_path, runtime)

    result = composition.run(operation_identity=RUN_1)
    document = p1_operational_result_document(result)

    assert runtime.calls == [KITE_INSTRUMENT_MASTER_OPERATION]
    assert result.stage is P1OperationalStage.INSTRUMENT_MASTER_ACQUISITION
    assert document["field_family"] == "EXCHANGE_TOKEN"
    assert document["value_classification"] == "MALFORMED"
    assert document["input_ordinal"] == 1
    assert "provider_instrument_token" not in json.dumps(document)
    assert "RAW-EXCHANGE-TOKEN-VALUE" not in json.dumps(document)


def test_expired_context_is_unavailable_and_does_not_acquire(tmp_path: Path) -> None:
    runtime = _Runtime(_complete_records(), lifecycle="EXPIRED")
    composition = _composition(tmp_path, runtime)

    result = composition.run(operation_identity=RUN_1)

    assert result.context_availability is P1ContextAvailability.EXPIRED
    assert result.failure is P1OperationalFailure.CONTEXT_UNAVAILABLE
    assert runtime.calls == []


def test_active_context_without_instrument_master_capability_fails_closed(
    tmp_path: Path,
) -> None:
    runtime = _Runtime(_complete_records(), operation_available=False)
    composition = _composition(tmp_path, runtime)

    result = composition.run(operation_identity=RUN_1)

    assert result.context_availability is P1ContextAvailability.OPERATION_UNAVAILABLE
    assert result.failure is P1OperationalFailure.LEASE_ACQUISITION_FAILED
    assert runtime.calls == []


def test_successful_snapshot_reconstructs_after_composition_restart(
    tmp_path: Path,
) -> None:
    runtime = _Runtime(_complete_records())
    composition = _composition(tmp_path, runtime)
    result = composition.run(operation_identity=RUN_1)
    assert result.snapshot_identity is not None

    restarted_store = ProviderInstrumentSnapshotStore(tmp_path.resolve())
    reconstructed = restarted_store.load(
        provider="KITE",
        dataset_identity=KITE_INSTRUMENT_MASTER_DATASET,
        snapshot_identity=result.snapshot_identity,
    )

    assert reconstructed.snapshot_identity == result.snapshot_identity
    assert reconstructed.integrity_identity == result.snapshot_integrity_identity
    assert reconstructed.record_count == result.record_count


def test_operational_composition_retains_the_supplied_single_runtime(
    tmp_path: Path,
) -> None:
    runtime = _Runtime(_complete_records())
    composition = _composition(tmp_path, runtime)

    assert composition._runtime is runtime
    assert composition.context_availability() is P1ContextAvailability.ACTIVE
