from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path

import pytest

from kronos.instrument.runtime import (
    RuntimeInstrumentRegistry,
    create_canonical_instrument,
    create_provider_assertion,
    create_provider_binding_directive,
    publish_runtime_instruments,
)
from kronos.intraday.universe import (
    CanonicalResolutionState,
    DEFAULT_INTRADAY_NATIVE_UNIVERSE_PATH,
    EXPECTED_NATIVE_MEMBER_COUNT,
    INTRADAY_NATIVE_UNIVERSE_IDENTITY,
    IntradayMarketFamily,
    IntradayUniverseError,
    IntradayUniverseFailure,
    load_intraday_universe_publication,
    parse_intraday_universe_publication,
    resolve_intraday_universe,
    seal_intraday_universe_document,
)
from kronos.intraday.universe_persistence import IntradayUniversePublicationStore


OBSERVED = datetime(2026, 8, 22, 12, tzinfo=timezone(timedelta(hours=5, minutes=30)))
EQUITIES = """ADANIENT ADANIGREEN ADANIPORTS ALKEM APOLLOHOSP ASIANPAINT AXISBANK BAJAJFINSV BAJAJ_AUTO BAJFINANCE BDL BEL BHARATFORG BHARTIARTL BHEL BPCL BSE CANBK CDSL CIPLA COALINDIA COFORGE CONCOR CUMMINSIND DIVISLAB DIXON DRREDDY EICHERMOT ETERNAL FEDERALBNK HAL HCLTECH HDFCAMC HDFCBANK HDFCLIFE HEROMOTOCO HINDALCO HINDPETRO HINDUNILVR ICICIBANK IDEA INDHOTEL INDIANB INDIGO INFY IOC ITC JIOFIN JUBLFOOD KAYNES KOTAKBANK LICI LT LUPIN M&M MARUTI MAXHEALTH MAZDOCK MCX MOTHERSON MUTHOOTFIN NAUKRI NTPC PAYTM PERSISTENT PNB POLICYBZR POWERGRID POWERINDIA RBLBANK RECLTD RELIANCE RVNL SAIL SBICARD SBIN SHRIRAMFIN SRF SUNPHARMA TATAPOWER TATASTEEL TCS TECHM TITAN TMPV TRENT UPL VBL VEDL WIPRO YESBANK""".split()


def _publication():
    return load_intraday_universe_publication()


def _source_document() -> dict[str, object]:
    document = json.loads(DEFAULT_INTRADAY_NATIVE_UNIVERSE_PATH.read_bytes())
    document.pop("integrity_identity")
    for item in document["members"]:
        item.pop("membership_identity")
    return document


def _registry(*, canonical_id: str = "RELIANCE", bound: bool = True) -> RuntimeInstrumentRegistry:
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    end = datetime(2026, 12, 31, tzinfo=timezone.utc)
    canonical = create_canonical_instrument(
        canonical_instrument_id=canonical_id,
        exchange="NSE",
        segment="NSE",
        instrument_type="EQ",
        canonical_tick_size=Decimal("0.1"),
        canonical_lot_size=1,
        canonical_source_identity="TEST-CANONICAL",
        source_boundary=start,
        valid_through=end,
    )
    assertions = ()
    directives = ()
    if bound:
        assertions = (
            create_provider_assertion(
                provider="KITE",
                provider_symbol=canonical_id,
                provider_instrument_token=1,
                exchange="NSE",
                segment="NSE",
                instrument_type="EQ",
                asserted_tick_size=Decimal("0.1"),
                asserted_lot_size=1,
                binding_source_identity="TEST-PROVIDER",
                source_boundary=start,
                valid_through=end,
            ),
        )
        directives = (
            create_provider_binding_directive(
                canonical_instrument_id=canonical_id,
                provider="KITE",
                provider_symbol=canonical_id,
                directive_source_identity="TEST-DIRECTIVE",
            ),
        )
    return publish_runtime_instruments(
        canonical_instruments=(canonical,),
        provider_assertions=assertions,
        binding_directives=directives,
        observed_at=OBSERVED,
    )


def test_exact_universe_count_is_98() -> None:
    assert len(_publication().members) == EXPECTED_NATIVE_MEMBER_COUNT == 98


def test_exact_91_equity_list_is_retained() -> None:
    actual = [m.sponsor_label for m in _publication().members if m.market_family is IntradayMarketFamily.NSE_EQUITY]
    assert actual == EQUITIES
    assert len(actual) == 91


@pytest.mark.parametrize("label", ["NIFTY", "BANKNIFTY"])
def test_required_index_is_retained(label: str) -> None:
    member = next(m for m in _publication().members if m.sponsor_label == label)
    assert member.market_family is IntradayMarketFamily.NSE_INDEX


def test_exact_five_mcx_subjects_are_retained() -> None:
    assert [m.sponsor_label for m in _publication().members if m.market_family is IntradayMarketFamily.MCX] == ["GOLDM", "SILVERM", "COPPER", "NATGAS", "CRUDE"]


def test_ampersand_sponsor_spelling_is_not_normalized() -> None:
    assert _publication().contains("M&M")
    assert not _publication().contains("MANDM")


def test_reliance_is_one_member_not_universe_owner() -> None:
    publication = _publication()
    assert sum(m.sponsor_label == "RELIANCE" for m in publication.members) == 1
    assert publication.product_identity == "INTRADAY"


def test_provider_presence_cannot_enlarge_membership() -> None:
    resolution = resolve_intraday_universe(publication=_publication(), runtime_registry=_registry(canonical_id="KITEONLY"), observed_at=OBSERVED)
    assert len(resolution.members) == 98
    assert all(m.sponsor_label != "KITEONLY" for m in resolution.members)


def test_canonical_nonmember_cannot_enter() -> None:
    resolution = resolve_intraday_universe(publication=_publication(), runtime_registry=_registry(canonical_id="CANONICALONLY"), observed_at=OBSERVED)
    with pytest.raises(ValueError, match="INTRADAY_NATIVE_MEMBER_UNAVAILABLE"):
        resolution.lookup("CANONICALONLY")


def test_swing_only_member_cannot_enter_without_publication_membership() -> None:
    assert not _publication().contains("CRUDEOIL")


@pytest.mark.parametrize("label", ["COMEX_GOLD", "COMEX_SILVER", "COMEX_COPPER", "NYMEX_NATURAL_GAS", "NYMEX_CRUDE_OIL"])
def test_reference_subject_cannot_enter_native_membership(label: str) -> None:
    assert not _publication().contains(label)


def test_duplicate_sponsor_membership_is_rejected() -> None:
    source = _source_document()
    source["members"][-1] = dict(source["members"][0])
    with pytest.raises(IntradayUniverseError, match="PUBLICATION_INVALID"):
        parse_intraday_universe_publication(seal_intraday_universe_document(source))


def test_duplicate_canonical_membership_is_rejected() -> None:
    source = _source_document()
    source["members"][0]["canonical_instrument_id"] = "RELIANCE"
    with pytest.raises(IntradayUniverseError, match="PUBLICATION_INVALID"):
        parse_intraday_universe_publication(seal_intraday_universe_document(source))


def test_wrong_product_identity_is_rejected() -> None:
    source = _source_document()
    source["product_identity"] = "SWING"
    with pytest.raises(IntradayUniverseError, match="PUBLICATION_INVALID"):
        seal_intraday_universe_document(source)


def test_invalid_market_family_is_rejected() -> None:
    source = _source_document()
    source["members"][0]["market_family"] = "UNKNOWN"
    with pytest.raises(IntradayUniverseError, match="PUBLICATION_INVALID"):
        parse_intraday_universe_publication(seal_intraday_universe_document(source))


def test_tampered_publication_is_rejected() -> None:
    document = json.loads(DEFAULT_INTRADAY_NATIVE_UNIVERSE_PATH.read_bytes())
    document["members"][0]["sponsor_label"] = "TAMPERED"
    with pytest.raises(IntradayUniverseError) as failure:
        parse_intraday_universe_publication(json.dumps(document).encode())
    assert failure.value.failure is IntradayUniverseFailure.INTEGRITY_MISMATCH


def test_stale_publication_is_rejected() -> None:
    with pytest.raises(IntradayUniverseError) as failure:
        _publication().require_current(datetime(2026, 8, 21, tzinfo=timezone.utc))
    assert failure.value.failure is IntradayUniverseFailure.PUBLICATION_STALE


def test_restart_reload_is_deterministic() -> None:
    first = _publication()
    second = load_intraday_universe_publication(Path(DEFAULT_INTRADAY_NATIVE_UNIVERSE_PATH))
    assert first == second
    assert first.integrity_identity == second.integrity_identity


def test_historical_resolution_uses_explicit_versions(tmp_path: Path) -> None:
    store = IntradayUniversePublicationStore(tmp_path)
    first_source = _source_document()
    first_source["valid_through"] = "2026-08-31T23:59:59+05:30"
    for item in first_source["members"]:
        item["valid_through"] = first_source["valid_through"]
    first = store.retain_source(first_source)
    second_source = _source_document()
    second_source["publication_version"] = "1.1.0"
    second_source["valid_from"] = "2026-09-01T00:00:00+05:30"
    second_source["source_boundary"] = "2026-09-01T00:00:00+05:30"
    second_source["supersedes"] = first.integrity_identity
    for item in second_source["members"]:
        item["valid_from"] = second_source["valid_from"]
    store.retain_source(second_source)
    resolved = store.resolve_at(publication_versions=("1.0.0", "1.1.0"), observed_at=OBSERVED)
    assert resolved.publication_version == "1.0.0"


def test_conflicting_version_write_is_rejected(tmp_path: Path) -> None:
    store = IntradayUniversePublicationStore(tmp_path)
    source = _source_document()
    store.retain_source(source)
    source["provenance"] = ["conflict"]
    with pytest.raises(IntradayUniverseError) as failure:
        store.retain_source(source)
    assert failure.value.failure is IntradayUniverseFailure.VERSION_CONFLICT


def test_missing_canonical_preserves_sponsor_membership() -> None:
    resolution = resolve_intraday_universe(publication=_publication(), runtime_registry=_registry(), observed_at=OBSERVED)
    item = resolution.lookup("ADANIENT")
    assert item.canonical_instrument_id is None
    assert item.canonical_resolution_state is CanonicalResolutionState.CANONICAL_BINDING_UNAVAILABLE
    assert not item.runtime_consumable


def test_missing_provider_binding_preserves_member_but_fails_closed() -> None:
    resolution = resolve_intraday_universe(publication=_publication(), runtime_registry=_registry(bound=False), observed_at=OBSERVED)
    item = resolution.lookup("RELIANCE")
    assert item.canonical_resolution_state is CanonicalResolutionState.PROVIDER_BINDING_UNAVAILABLE
    assert item.runtime_instrument_available
    assert not item.provider_binding_available
    assert not item.runtime_consumable


def test_mixed_ready_and_unavailable_members_resolve_together() -> None:
    resolution = resolve_intraday_universe(publication=_publication(), runtime_registry=_registry(), observed_at=OBSERVED)
    assert resolution.lookup("RELIANCE").canonical_resolution_state is CanonicalResolutionState.CANONICAL_READY
    assert resolution.lookup("NIFTY").canonical_resolution_state is CanonicalResolutionState.CANONICAL_BINDING_UNAVAILABLE
    assert len(resolution.members) == 98


def test_publication_contains_no_execution_or_trading_fields() -> None:
    document = json.loads(DEFAULT_INTRADAY_NATIVE_UNIVERSE_PATH.read_bytes())
    prohibited = {"execution_token", "broker_order_symbol", "current_futures_contract", "entry_permission", "LONG", "SHORT", "READY", "PROBABLE", "TRADEABLE", "ENTRY_ELIGIBLE", "RISK_APPROVED"}
    assert not prohibited.intersection(document)
    assert all(not prohibited.intersection(item) for item in document["members"])


def test_intraday_universe_has_no_swing_implementation_import() -> None:
    source = Path(__file__).parents[3] / "src" / "kronos" / "intraday" / "universe.py"
    assert "kronos.swing" not in source.read_text(encoding="utf-8")


def test_publication_identity_and_version_are_frozen() -> None:
    publication = _publication()
    assert publication.publication_identity == INTRADAY_NATIVE_UNIVERSE_IDENTITY
    assert publication.publication_version == "1.0.0"
