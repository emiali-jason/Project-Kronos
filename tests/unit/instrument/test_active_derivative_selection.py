from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from kronos.instrument.active_derivative import (
    ACTIVE_DERIVATIVE_FAMILY_MAPPINGS,
    ActiveDerivativeSelectionFailure,
    GovernedActiveDerivativeResolver,
    active_derivative_binding_bytes,
    parse_active_derivative_binding,
)
from kronos.instrument.active_derivative_persistence import ActiveDerivativeBindingStore
from kronos.instrument.semantic_v2 import DerivativeContractV2
from kronos.instrument.semantic_v2_persistence import (
    DEFAULT_INSTRUMENT_SEMANTIC_V2_ROOT,
    InstrumentSemanticV2Store,
)
from kronos.market.calendar import MarketCalendarPublisher
from kronos.provider.contracts.instrument_master import (
    KITE_INSTRUMENT_MASTER_DATASET,
    KITE_INSTRUMENT_MASTER_OPERATION,
    ProviderInstrumentMasterSourceRecord,
)
from kronos.provider.instrument_master import (
    ProviderAcquisitionOutcome,
    create_provider_instrument_snapshot,
)


IST = ZoneInfo("Asia/Kolkata")
CATALOGUE = InstrumentSemanticV2Store(DEFAULT_INSTRUMENT_SEMANTIC_V2_ROOT).load(
    publication_identity="KRONOS-CANONICAL-INSTRUMENT-CATALOGUE-V2",
    publication_version="1.2.0",
)
FAMILY_BY_SUBJECT = {
    subject: family for _, subject, family in ACTIVE_DERIVATIVE_FAMILY_MAPPINGS
}


def _rows(
    *,
    omit_family: str | None = None,
    wrong_natgas_alias: bool = False,
) -> tuple[ProviderInstrumentMasterSourceRecord, ...]:
    rows = []
    token = 100_000
    for contract in CATALOGUE.semantic_objects:
        if type(contract) is not DerivativeContractV2:
            continue
        family = FAMILY_BY_SUBJECT.get(contract.parent_subject_id)
        if family is None or family == omit_family:
            continue
        geometry = contract.geometry[0]
        token += 1
        rows.append(ProviderInstrumentMasterSourceRecord(
            provider="KITE",
            provider_instrument_token=token,
            exchange_token=token + 1_000_000,
            trading_symbol=contract.canonical_symbol,
            name=("NATGAS" if wrong_natgas_alias and family == "NATURALGAS" else family),
            last_price=Decimal("0"),
            expiry=contract.expiry,
            strike=Decimal("0"),
            tick_size=geometry.tick_size,
            lot_size=geometry.lot_size,
            instrument_type="FUT",
            segment="MCX-FUT",
            exchange="MCX",
        ))
    return tuple(rows)


def _snapshot(
    boundary: datetime,
    *,
    rows: tuple[ProviderInstrumentMasterSourceRecord, ...] | None = None,
):  # type: ignore[no-untyped-def]
    records = _rows() if rows is None else rows
    return create_provider_instrument_snapshot(
        records=records,
        provider="KITE",
        dataset_identity=KITE_INSTRUMENT_MASTER_DATASET,
        operation_identity=KITE_INSTRUMENT_MASTER_OPERATION,
        source_boundary=boundary,
        request_started_at=boundary,
        response_received_at=boundary,
        acquired_at=boundary,
        acquisition_effective_at=boundary,
        authenticated_context_identity="TEST-SHARED-CONTEXT",
        authorized_operation_identity=KITE_INSTRUMENT_MASTER_OPERATION,
        component_identities=("TEST-COMPLETE-MCX-MASTER",),
        acquisition_outcome=ProviderAcquisitionOutcome.COMPLETE,
        provenance=("ADR-0017", "WO-06MCX-R-TEST"),
    )


def _resolve(boundary: datetime, *, rows=None, previous=None):  # type: ignore[no-untyped-def]
    return GovernedActiveDerivativeResolver(
        catalogue=CATALOGUE,
        provider_snapshot=_snapshot(boundary, rows=rows),
        calendar_publisher=MarketCalendarPublisher(),
    ).resolve_all(boundary, previous_bindings=previous)


def test_exact_five_family_mapping_and_current_bindings_are_token_free(
    tmp_path: Path,
) -> None:
    boundary = datetime(2026, 8, 26, 10, 0, tzinfo=IST)
    resolved = _resolve(boundary)

    assert ACTIVE_DERIVATIVE_FAMILY_MAPPINGS == (
        ("GOLDM", "MCX-SUBJECT-GOLDM", "GOLDM"),
        ("SILVERM", "MCX-SUBJECT-SILVERM", "SILVERM"),
        ("COPPER", "MCX-SUBJECT-COPPER", "COPPER"),
        ("NATGAS", "MCX-SUBJECT-NATGAS", "NATURALGAS"),
        ("CRUDE", "MCX-SUBJECT-CRUDE", "CRUDEOIL"),
    )
    assert len(resolved.successful_bindings) == 5
    store = ActiveDerivativeBindingStore(tmp_path.resolve())
    for binding in resolved.successful_bindings:
        encoded = active_derivative_binding_bytes(binding)
        assert b"instrument_token" not in encoded
        assert b"provider_instrument_token" not in encoded
        assert parse_active_derivative_binding(encoded) == binding
        store.retain(binding)
        assert store.load(binding_identity=binding.binding_identity) == binding
        assert store.load_current(
            canonical_subject_id=binding.canonical_subject_id
        ) == binding


def test_no_fuzzy_alias_and_no_provider_order_tiebreak() -> None:
    boundary = datetime(2026, 8, 26, 10, 0, tzinfo=IST)
    wrong_alias = _resolve(
        boundary,
        rows=_rows(wrong_natgas_alias=True),
    ).for_subject("NATGAS")
    assert wrong_alias.binding is None
    assert wrong_alias.failure is ActiveDerivativeSelectionFailure.PROVIDER_CONTRACT_UNAVAILABLE

    rows = list(_rows())
    copper = next(
        item for item in rows
        if item.name == "COPPER" and item.trading_symbol == "COPPER26AUGFUT"
    )
    rows.append(ProviderInstrumentMasterSourceRecord(
        provider=copper.provider,
        provider_instrument_token=9_999_999,
        exchange_token=8_888_888,
        trading_symbol=copper.trading_symbol,
        name=copper.name,
        last_price=copper.last_price,
        expiry=copper.expiry,
        strike=copper.strike,
        tick_size=copper.tick_size,
        lot_size=copper.lot_size,
        instrument_type=copper.instrument_type,
        segment=copper.segment,
        exchange=copper.exchange,
    ))
    ambiguous = _resolve(boundary, rows=tuple(rows)).for_subject("COPPER")
    assert ambiguous.binding is None
    assert ambiguous.failure is ActiveDerivativeSelectionFailure.ACTIVE_BINDING_AMBIGUOUS
    assert ambiguous.accounting.minimum_expiry_candidate_count == 2


def test_candidate_filter_rejects_options_wrong_exchange_family_and_expired() -> None:
    boundary = datetime(2026, 8, 26, 10, 0, tzinfo=IST)
    rows = list(_rows())
    template = next(item for item in rows if item.name == "COPPER")
    variants = (
        ("MCX", "MCX-OPT", "OPT", "COPPER", template.expiry),
        ("NFO", "NFO-FUT", "FUT", "COPPER", template.expiry),
        ("MCX", "MCX-FUT", "FUT", "COPPERMINI", template.expiry),
        ("MCX", "MCX-FUT", "FUT", "COPPER", boundary.date() - timedelta(days=1)),
    )
    for ordinal, (exchange, segment, kind, name, expiry) in enumerate(variants, 1):
        rows.append(ProviderInstrumentMasterSourceRecord(
            provider="KITE",
            provider_instrument_token=7_000_000 + ordinal,
            exchange_token=8_000_000 + ordinal,
            trading_symbol=f"REJECTED{ordinal}",
            name=name,
            last_price=Decimal("0"),
            expiry=expiry,
            strike=Decimal("0"),
            tick_size=template.tick_size,
            lot_size=template.lot_size,
            instrument_type=kind,
            segment=segment,
            exchange=exchange,
        ))
    copper = _resolve(boundary, rows=tuple(rows)).for_subject("COPPER")
    assert copper.binding is not None
    assert copper.binding.provider_symbol == "COPPER26AUGFUT"
    assert copper.accounting.expired_candidate_count == 1


def test_domain008_expiry_boundary_and_immutable_roll() -> None:
    calendar = MarketCalendarPublisher()
    trading_date = datetime(2026, 8, 31, 12, 0, tzinfo=IST)
    profile = calendar.mcx_contract_session_profile(
        contract_family="COPPER",
        contract_expiry=trading_date.date(),
        trading_date=trading_date.date(),
        observed_at=trading_date,
    )
    cutoff = profile.expiry_eligibility_boundary
    before = _resolve(cutoff - timedelta(microseconds=1)).for_subject("COPPER")
    at = _resolve(cutoff).for_subject("COPPER")
    after = _resolve(cutoff + timedelta(microseconds=1)).for_subject("COPPER")

    assert before.binding is not None and before.binding.provider_symbol == "COPPER26AUGFUT"
    assert at.binding is not None and at.binding.provider_symbol == "COPPER26AUGFUT"
    assert after.binding is not None and after.binding.provider_symbol == "COPPER26SEPFUT"
    assert after.binding.binding_identity != at.binding.binding_identity

    rolled = _resolve(
        cutoff + timedelta(microseconds=1),
        previous={at.binding.canonical_subject_id: at.binding},
    ).for_subject("COPPER")
    assert rolled.binding is not None
    assert rolled.binding.active_binding.supersedes == at.binding.binding_identity
    assert active_derivative_binding_bytes(at.binding) == active_derivative_binding_bytes(
        parse_active_derivative_binding(active_derivative_binding_bytes(at.binding))
    )


@pytest.mark.parametrize(
    ("subject", "family", "expiry", "symbol"),
    (
        ("GOLDM", "GOLDM", datetime(2026, 9, 4, tzinfo=IST).date(), "GOLDM26SEPFUT"),
        ("SILVERM", "SILVERM", datetime(2026, 8, 31, tzinfo=IST).date(), "SILVERM26AUGFUT"),
        ("COPPER", "COPPER", datetime(2026, 8, 31, tzinfo=IST).date(), "COPPER26AUGFUT"),
        ("NATGAS", "NATURALGAS", datetime(2026, 8, 26, tzinfo=IST).date(), "NATURALGAS26AUGFUT"),
        ("CRUDE", "CRUDEOIL", datetime(2026, 9, 21, tzinfo=IST).date(), "CRUDEOIL26SEPFUT"),
    ),
)
def test_each_family_consumes_its_own_inclusive_expiry_boundary(
    subject: str,
    family: str,
    expiry,
    symbol: str,
) -> None:  # type: ignore[no-untyped-def]
    observed = datetime.combine(expiry, datetime.min.time(), IST) + timedelta(hours=12)
    profile = MarketCalendarPublisher().mcx_contract_session_profile(
        contract_family=family,
        contract_expiry=expiry,
        trading_date=expiry,
        observed_at=observed,
    )
    at = _resolve(profile.expiry_eligibility_boundary).for_subject(subject)
    after = _resolve(
        profile.expiry_eligibility_boundary + timedelta(microseconds=1)
    ).for_subject(subject)
    assert at.binding is not None and at.binding.provider_symbol == symbol
    assert after.binding is not None and after.binding.provider_symbol != symbol


@pytest.mark.parametrize(
    ("subject", "family"),
    (("GOLDM", "GOLDM"), ("SILVERM", "SILVERM"), ("COPPER", "COPPER"),
     ("NATGAS", "NATURALGAS"), ("CRUDE", "CRUDEOIL")),
)
def test_missing_exact_family_fails_closed(subject: str, family: str) -> None:
    boundary = datetime(2026, 8, 26, 10, 0, tzinfo=IST)
    outcome = _resolve(boundary, rows=_rows(omit_family=family)).for_subject(subject)
    assert outcome.binding is None
    assert outcome.failure is ActiveDerivativeSelectionFailure.PROVIDER_CONTRACT_UNAVAILABLE
