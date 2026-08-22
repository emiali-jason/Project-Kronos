from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from kronos.application.intraday_provider_commissioning import (
    CommissioningResolutionStatus,
    create_intraday_provider_commissioning_manifest,
)
from kronos.intraday.universe import (
    EXPECTED_NATIVE_MEMBER_COUNT,
    IntradayMarketFamily,
    load_intraday_universe_publication,
)
from kronos.provider.contracts.instrument_master import (
    KITE_INSTRUMENT_MASTER_DATASET,
    KITE_INSTRUMENT_MASTER_OPERATION,
    ProviderInstrumentDiagnosticPhase,
    ProviderInstrumentFieldFamily,
    ProviderInstrumentMasterError,
    ProviderInstrumentMasterFailure,
    ProviderInstrumentMasterSourceRecord,
    ProviderInstrumentValidationRule,
    ProviderInstrumentValueClassification,
)
from kronos.provider.instrument_master import (
    ProviderAcquisitionOutcome,
    ProviderInstrumentMasterAcquisitionService,
    create_provider_instrument_snapshot,
    encode_provider_instrument_snapshot,
    parse_provider_instrument_snapshot,
)
from kronos.provider.instrument_master_persistence import ProviderInstrumentSnapshotStore


NOW = datetime(2026, 8, 22, 8, 30, tzinfo=timezone.utc)


def _source(
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


def _snapshot(records: tuple[ProviderInstrumentMasterSourceRecord, ...] | None = None):  # type: ignore[no-untyped-def]
    return create_provider_instrument_snapshot(
        records=records or (
            _source(738561, "RELIANCE", name="RELIANCE INDUSTRIES"),
            _source(123456, "GOLDM26AUGFUT", exchange="MCX", segment="MCX-FUT", name="GOLDM", instrument_type="FUT", expiry=date(2026, 8, 28), lot=100, tick="1"),
            _source(777777, "UNRELATED", exchange="BSE", segment="BSE"),
        ),
        provider="KITE",
        dataset_identity=KITE_INSTRUMENT_MASTER_DATASET,
        operation_identity=KITE_INSTRUMENT_MASTER_OPERATION,
        source_boundary=NOW,
        request_started_at=NOW,
        response_received_at=NOW,
        acquired_at=NOW,
        acquisition_effective_at=NOW,
        authenticated_context_identity="AUTH-CONTEXT-OPAQUE-1",
        authorized_operation_identity=KITE_INSTRUMENT_MASTER_OPERATION,
        component_identities=("KITE-COMPONENT-1",),
        acquisition_outcome=ProviderAcquisitionOutcome.COMPLETE,
        provenance=("ADR-0014", "ADR-009", "WO-P1"),
    )


def test_complete_snapshot_is_deterministic_product_neutral_and_provider_exact() -> None:
    first = _snapshot()
    second = _snapshot(tuple(reversed(tuple(_source_from(item) for item in first.records))))

    assert first == second
    assert first.schema_identity == "KRONOS-PROVIDER-INSTRUMENT-SNAPSHOT-V1"
    assert first.snapshot_version == "1.0.0"
    assert first.requested_scope == "COMPLETE_RETURNED_AUTHORIZED_INSTRUMENT_MASTER_DATASET"
    assert first.record_count == 3
    assert first.exchange_counts == (("BSE", 1), ("MCX", 1), ("NSE", 1))
    assert {item.trading_symbol for item in first.records} == {"RELIANCE", "GOLDM26AUGFUT", "UNRELATED"}
    assert len({item.provider_record_identity for item in first.records}) == 3
    assert first.records[0].provider_instrument_token != int(first.records[0].provider_record_identity[-8:], 16)
    assert "token-redacted" in repr(first.records[0])


@pytest.mark.parametrize("field", ["last_price", "strike", "tick_size"])
def test_malformed_provider_decimal_fails_closed(field: str) -> None:
    values = {
        "provider": "KITE",
        "provider_instrument_token": 1,
        "exchange_token": 2,
        "trading_symbol": "ABC",
        "name": "ABC",
        "last_price": Decimal("0"),
        "expiry": None,
        "strike": Decimal("0"),
        "tick_size": Decimal("0.05"),
        "lot_size": 1,
        "instrument_type": "EQ",
        "segment": "NSE",
        "exchange": "NSE",
    }
    values[field] = "MALFORMED"
    with pytest.raises(ProviderInstrumentMasterError) as captured:
        ProviderInstrumentMasterSourceRecord(**values)  # type: ignore[arg-type]
    assert captured.value.failure is ProviderInstrumentMasterFailure.SNAPSHOT_SCHEMA_INVALID


def test_source_record_construction_has_its_own_sanitized_phase() -> None:
    with pytest.raises(ProviderInstrumentMasterError) as captured:
        _source(1, "")

    diagnostic = captured.value.diagnostic
    assert diagnostic is not None
    assert diagnostic.phase is ProviderInstrumentDiagnosticPhase.SNAPSHOT_CONSTRUCTION
    assert diagnostic.rule is ProviderInstrumentValidationRule.SYMBOL_REQUIRED
    assert diagnostic.field_family is ProviderInstrumentFieldFamily.SYMBOL
    assert diagnostic.value_classification is ProviderInstrumentValueClassification.EMPTY
    assert diagnostic.input_ordinal is None
    assert diagnostic.record_locator is None
    assert diagnostic.affected_count == 1


def test_snapshot_metadata_failure_has_construction_phase() -> None:
    with pytest.raises(ProviderInstrumentMasterError) as captured:
        create_provider_instrument_snapshot(
            records=(_source(1, "ABC"),),
            provider="KITE",
            dataset_identity=KITE_INSTRUMENT_MASTER_DATASET,
            operation_identity=KITE_INSTRUMENT_MASTER_OPERATION,
            source_boundary=NOW,
            request_started_at=NOW,
            response_received_at=NOW,
            acquired_at=NOW,
            acquisition_effective_at=NOW,
            authenticated_context_identity="AUTH-CONTEXT-OPAQUE-1",
            authorized_operation_identity=KITE_INSTRUMENT_MASTER_OPERATION,
            component_identities=("DUPLICATE", "DUPLICATE"),
            acquisition_outcome=ProviderAcquisitionOutcome.COMPLETE,
            provenance=("WO-P1",),
        )

    diagnostic = captured.value.diagnostic
    assert diagnostic is not None
    assert diagnostic.phase is ProviderInstrumentDiagnosticPhase.SNAPSHOT_CONSTRUCTION
    assert diagnostic.rule is ProviderInstrumentValidationRule.SNAPSHOT_METADATA_INVALID
    assert diagnostic.field_family is ProviderInstrumentFieldFamily.SNAPSHOT_METADATA
    assert diagnostic.value_classification is ProviderInstrumentValueClassification.INVALID


def test_record_and_snapshot_integrity_failures_have_validation_phase() -> None:
    snapshot = _snapshot()

    with pytest.raises(ProviderInstrumentMasterError) as record_failure:
        replace(snapshot.records[0], record_integrity_identity="INVALID")
    record_diagnostic = record_failure.value.diagnostic
    assert record_failure.value.failure is (
        ProviderInstrumentMasterFailure.SNAPSHOT_INTEGRITY_INVALID
    )
    assert record_diagnostic is not None
    assert record_diagnostic.phase is ProviderInstrumentDiagnosticPhase.SNAPSHOT_VALIDATION
    assert record_diagnostic.rule is ProviderInstrumentValidationRule.RECORD_IDENTITY_INVALID
    assert record_diagnostic.field_family is ProviderInstrumentFieldFamily.RECORD_IDENTITY
    assert record_diagnostic.input_ordinal == snapshot.records[0].snapshot_ordinal

    with pytest.raises(ProviderInstrumentMasterError) as snapshot_failure:
        replace(snapshot, integrity_identity="INVALID")
    snapshot_diagnostic = snapshot_failure.value.diagnostic
    assert snapshot_failure.value.failure is (
        ProviderInstrumentMasterFailure.SNAPSHOT_INTEGRITY_INVALID
    )
    assert snapshot_diagnostic is not None
    assert snapshot_diagnostic.phase is ProviderInstrumentDiagnosticPhase.SNAPSHOT_VALIDATION
    assert snapshot_diagnostic.rule is ProviderInstrumentValidationRule.INTEGRITY_INVALID
    assert snapshot_diagnostic.field_family is ProviderInstrumentFieldFamily.INTEGRITY


def test_snapshot_round_trip_integrity_and_any_tamper_rejection() -> None:
    snapshot = _snapshot()
    encoded = encode_provider_instrument_snapshot(snapshot)
    assert parse_provider_instrument_snapshot(encoded) == snapshot

    document = json.loads(encoded)
    document["records"][0]["lot_size"] += 1
    tampered = json.dumps(document, ensure_ascii=True, indent=2, sort_keys=True).encode()
    with pytest.raises(ProviderInstrumentMasterError) as captured:
        parse_provider_instrument_snapshot(tampered)
    assert captured.value.failure is ProviderInstrumentMasterFailure.SNAPSHOT_INTEGRITY_INVALID


def test_immutable_store_is_restart_safe_idempotent_and_explicit(tmp_path: Path) -> None:
    snapshot = _snapshot()
    first_store = ProviderInstrumentSnapshotStore(tmp_path.resolve())
    first_path = first_store.retain(snapshot)
    assert first_store.retain(snapshot) == first_path

    restarted = ProviderInstrumentSnapshotStore(tmp_path.resolve())
    assert restarted.load(
        provider="KITE",
        dataset_identity=KITE_INSTRUMENT_MASTER_DATASET,
        snapshot_identity=snapshot.snapshot_identity,
    ) == snapshot
    assert first_path.stat().st_mode & 0o777 == 0o600
    assert not hasattr(restarted, "latest")
    assert not hasattr(restarted, "delete")


def test_conflicting_duplicate_and_persisted_tamper_fail_closed(tmp_path: Path) -> None:
    snapshot = _snapshot()
    store = ProviderInstrumentSnapshotStore(tmp_path.resolve())
    path = store.retain(snapshot)
    path.write_bytes(b"conflicting existing material")
    with pytest.raises(ProviderInstrumentMasterError) as conflict:
        store.retain(snapshot)
    assert conflict.value.failure is ProviderInstrumentMasterFailure.SNAPSHOT_CONFLICT
    with pytest.raises(ProviderInstrumentMasterError):
        store.load(
            provider="KITE",
            dataset_identity=KITE_INSTRUMENT_MASTER_DATASET,
            snapshot_identity=snapshot.snapshot_identity,
        )


class _Runtime:
    provider_identity = "KITE"
    authenticated_context_identity = "AUTH-CONTEXT-OPAQUE-1"

    def __init__(self, records: tuple[ProviderInstrumentMasterSourceRecord, ...], state: str = "ACTIVE") -> None:
        self.records = records
        self.lifecycle_state = SimpleNamespace(value=state)
        self.calls: list[str] = []

    def acquire_provider_instrument_master_records(self, *, operation_identity: str):  # type: ignore[no-untyped-def]
        self.calls.append(operation_identity)
        return self.records


def test_acquisition_uses_one_authorized_consolidated_operation() -> None:
    runtime = _Runtime(tuple(_source_from(item) for item in _snapshot().records))
    service = ProviderInstrumentMasterAcquisitionService(runtime, clock=lambda: NOW)

    result = service.acquire(
        source_boundary=NOW,
        authorized_operation_identity=KITE_INSTRUMENT_MASTER_OPERATION,
        provenance=("WO-P1",),
    )

    assert result.record_count == 3
    assert result.component_request_count == 1
    assert runtime.calls == [KITE_INSTRUMENT_MASTER_OPERATION]


@pytest.mark.parametrize(
    ("state", "operation", "failure"),
    [
        ("ABSENT", KITE_INSTRUMENT_MASTER_OPERATION, ProviderInstrumentMasterFailure.CONTEXT_UNAVAILABLE),
        ("ACTIVE", "UNAUTHORIZED", ProviderInstrumentMasterFailure.OPERATION_UNAUTHORIZED),
    ],
)
def test_context_and_operation_fail_closed(state: str, operation: str, failure: ProviderInstrumentMasterFailure) -> None:
    runtime = _Runtime((_source(1, "ABC"),), state=state)
    service = ProviderInstrumentMasterAcquisitionService(runtime, clock=lambda: NOW)
    with pytest.raises(ProviderInstrumentMasterError) as captured:
        service.acquire(
            source_boundary=NOW,
            authorized_operation_identity=operation,
            provenance=("WO-P1",),
        )
    assert captured.value.failure is failure
    assert runtime.calls == []


def test_98_member_commissioning_is_separate_token_free_and_non_authoritative() -> None:
    universe = load_intraday_universe_publication()
    records: list[ProviderInstrumentMasterSourceRecord] = []
    token = 1000
    for member in universe.members:
        token += 1
        if member.market_family is IntradayMarketFamily.NSE_EQUITY:
            symbol = "BAJAJ-AUTO" if member.sponsor_label == "BAJAJ_AUTO" else member.sponsor_label
            records.append(_source(token, symbol, name=member.sponsor_label))
        elif member.market_family is IntradayMarketFamily.NSE_INDEX:
            symbol = {"NIFTY": "NIFTY 50", "BANKNIFTY": "NIFTY BANK"}[member.sponsor_label]
            records.append(_source(token, symbol, segment="INDICES", name=symbol))
        else:
            for offset, expiry in enumerate((date(2026, 8, 28), date(2026, 9, 28))):
                records.append(_source(token * 10 + offset, f"{member.sponsor_label}{expiry:%y%b}FUT".upper(), exchange="MCX", segment="MCX-FUT", name=member.sponsor_label, instrument_type="FUT", expiry=expiry, lot=100, tick="1"))
    records.append(_source(999999, "PROVIDER_ONLY"))
    snapshot = _snapshot(tuple(records))

    manifest = create_intraday_provider_commissioning_manifest(snapshot=snapshot, universe=universe)

    assert len(manifest.members) == EXPECTED_NATIVE_MEMBER_COUNT
    assert manifest.provider_snapshot_identity == snapshot.snapshot_identity
    assert manifest.intraday_universe_identity == universe.publication_identity
    assert manifest.intraday_universe_version == universe.publication_version
    assert not manifest.canonical_identity_authority
    assert not manifest.execution_eligibility_authority
    assert not manifest.active_contract_selection_authority
    assert all(not item.canonical_identity_established for item in manifest.members)
    assert all(not item.execution_eligibility_established for item in manifest.members)
    assert all(not item.active_contract_selected for item in manifest.members)
    assert all(not hasattr(ref, "provider_instrument_token") for item in manifest.members for ref in item.candidate_records)
    assert not any(item.sponsor_label == "PROVIDER_ONLY" for item in manifest.members)

    assert manifest.members[0].status is CommissioningResolutionStatus.UNIQUE_PROVIDER_RECORD
    assert manifest.members[91].status is CommissioningResolutionStatus.PROVIDER_INDEX_RECORD_CANDIDATE
    assert manifest.members[92].status is CommissioningResolutionStatus.PROVIDER_INDEX_RECORD_CANDIDATE
    for label in ("GOLDM", "SILVERM", "COPPER", "NATGAS", "CRUDE"):
        member = next(item for item in manifest.members if item.sponsor_label == label)
        assert member.status is CommissioningResolutionStatus.MULTIPLE_PROVIDER_CONTRACT_RECORDS
        assert len(member.candidate_records) == 2


def test_commissioning_reports_missing_and_duplicate_without_fuzzy_matching() -> None:
    universe = load_intraday_universe_publication()
    snapshot = _snapshot((
        _source(1, "RELIANCE"),
        _source(2, "RELIANCE"),
        _source(3, "RELIANC"),
    ))
    manifest = create_intraday_provider_commissioning_manifest(snapshot=snapshot, universe=universe)
    reliance = next(item for item in manifest.members if item.sponsor_label == "RELIANCE")
    infy = next(item for item in manifest.members if item.sponsor_label == "INFY")
    assert reliance.status is CommissioningResolutionStatus.MULTIPLE_PROVIDER_RECORDS
    assert len(reliance.candidate_records) == 2
    assert infy.status is CommissioningResolutionStatus.NO_PROVIDER_RECORD


def test_no_secret_sdk_or_product_token_surface() -> None:
    snapshot = _snapshot()
    rendered = repr(snapshot) + repr(snapshot.records)
    assert "738561" not in rendered
    for prohibited in ("access_token", "api_secret", "request_token", "Authorization", "sdk_client", "place_order"):
        assert prohibited not in rendered
        assert not hasattr(snapshot, prohibited)


def _source_from(record):  # type: ignore[no-untyped-def]
    return ProviderInstrumentMasterSourceRecord(
        provider=record.provider,
        provider_instrument_token=record.provider_instrument_token,
        exchange_token=record.exchange_token,
        trading_symbol=record.trading_symbol,
        name=record.name,
        last_price=record.last_price,
        expiry=record.expiry,
        strike=record.strike,
        tick_size=record.tick_size,
        lot_size=record.lot_size,
        instrument_type=record.instrument_type,
        segment=record.segment,
        exchange=record.exchange,
    )
