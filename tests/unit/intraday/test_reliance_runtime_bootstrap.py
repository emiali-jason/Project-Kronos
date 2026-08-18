from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from kronos.application import intraday_reliance_bootstrap as bootstrap_module
from kronos.application.intraday_reliance_bootstrap import (
    PRESENTATION_SELECTION_POLICY,
    RelianceBootstrapAvailability,
    RelianceBootstrapStage,
    RelianceIntradayBootstrap,
    RelianceIntradayRuntimeWorkstation,
)
from kronos.browser.intraday_views import render_intraday_triage
from kronos.instrument.runtime import create_provider_assertion
from kronos.intraday.contracts import IntradayTimeframe
from kronos.market.calendar import MarketCalendarPublisher
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.market_data import (
    HistoricalCandle,
    HistoricalDataError,
    HistoricalDataFailure,
    HistoricalInterval,
)
from kronos.provider.runtime import ProviderRuntimeAccessError, ProviderRuntimeFailure


IST = ZoneInfo("Asia/Kolkata")
OBSERVED = datetime(2026, 8, 19, 10, 17, tzinfo=IST)
VALID = datetime(2026, 12, 31, 23, 59, tzinfo=IST)


class _Lease:
    valid_through = VALID

    def __init__(self, *, omit_five: bool = False) -> None:
        self.released = False
        self.omit_five = omit_five

    def instrument_assertions(self, exchange, *, source_boundary, valid_through):  # type: ignore[no-untyped-def]
        assert exchange == "NSE"
        return (create_provider_assertion(
            provider="KITE", provider_symbol="RELIANCE",
            provider_instrument_token=738561, exchange="NSE", segment="NSE",
            instrument_type="EQ", asserted_tick_size=Decimal("0.1"),
            asserted_lot_size=1, binding_source_identity="KITE-INSTRUMENT-MASTER",
            source_boundary=source_boundary, valid_through=valid_through,
        ),)

    def instrument_records(self, exchange):  # type: ignore[no-untyped-def]
        return (InstrumentRecord(
            "KITE", exchange, "NSE", "RELIANCE", "Reliance Industries Limited",
            "EQ", None, Decimal("0.1"), 1,
        ),)

    def historical_candles(self, request):  # type: ignore[no-untyped-def]
        if request.interval is HistoricalInterval.DAY:
            return (
                HistoricalCandle(datetime(2026, 8, 18, 0, 0, tzinfo=IST), 1400.0, 1425.0, 1390.0, 1410.0, 1_000_000),
                HistoricalCandle(datetime(2026, 8, 19, 0, 0, tzinfo=IST), 1412.0, 1420.0, 1408.0, 1418.0, 500_000),
            )
        minutes = {
            HistoricalInterval.SIXTY_MINUTE: 60,
            HistoricalInterval.FIFTEEN_MINUTE: 15,
            HistoricalInterval.FIVE_MINUTE: 5,
        }[request.interval]
        values = []
        cursor = datetime(2026, 8, 19, 9, 15, tzinfo=IST)
        index = 0
        while cursor <= OBSERVED:
            if not (
                self.omit_five
                and request.interval is HistoricalInterval.FIVE_MINUTE
                and cursor == datetime(2026, 8, 19, 9, 55, tzinfo=IST)
            ):
                base = 1410.0 + index
                values.append(HistoricalCandle(
                    cursor, base, base + 2, base - 1, base + 1, 1000 + index * 100
                ))
            cursor += timedelta(minutes=minutes)
            index += 1
        return tuple(values)

    def release(self) -> None:
        self.released = True


def test_reliance_real_path_builds_all_factual_layers_and_restarts(tmp_path: Path) -> None:
    lease = _Lease()
    result = RelianceIntradayBootstrap(
        acquire_lease=lambda: lease,
        calendar_publisher=MarketCalendarPublisher(),
        evidence_root=tmp_path,
        clock=lambda: OBSERVED,
    ).run()

    assert result.availability is RelianceBootstrapAvailability.AVAILABLE
    assert result.restart_verified is True
    assert lease.released is True
    instrument = result.registry.require_consumable("RELIANCE")
    assert instrument.provider_binding is not None
    assert instrument.provider_binding.provider_instrument_token == 738561
    assert result.bundle is not None
    assert result.bundle.slice1e_context is not None
    previous = result.bundle.slice1e_context.previous_session
    assert (previous.pdh, previous.pdl, previous.close) == (
        Decimal("1425.0"), Decimal("1390.0"), Decimal("1410.0")
    )
    assert tuple(
        item.reconciliation.timeframe for item in result.bundle.composition.evidence
    ) == tuple(IntradayTimeframe)
    assert len(result.bundle.structural_evidence) == 4
    assert len(result.bundle.shadow_telemetry) == 1
    assert len(result.retrievals) == 4
    assert result.comparison_pack is not None
    assert result.comparison_pack.canonical_instrument_id == "RELIANCE"
    assert tuple(name for name, _ in result.comparison_pack.levels) == (
        "P", "R1", "R2", "R3", "R4", "S1", "S2", "S3", "S4"
    )
    assert result.comparison_pack.five_minute_telemetry.timeframe is IntradayTimeframe.FIVE_MINUTES
    assert "738561" not in repr(result)
    assert PRESENTATION_SELECTION_POLICY.endswith("PRESENTATION_ONLY_V1")
    encoded = b"".join(path.read_bytes() for path in tmp_path.rglob("*.json"))
    assert b"access_token" not in encoded
    assert b"api_secret" not in encoded


def test_reliance_bootstrap_fails_closed_without_authentication(tmp_path: Path) -> None:
    def unavailable():  # type: ignore[no-untyped-def]
        raise RuntimeError("access_token=provider secret must not escape")

    result = RelianceIntradayBootstrap(
        acquire_lease=unavailable, evidence_root=tmp_path, clock=lambda: OBSERVED
    ).run()

    assert result.availability is RelianceBootstrapAvailability.UNAVAILABLE
    assert result.stage is RelianceBootstrapStage.LEASE_ACQUISITION
    assert result.failure_code == "LEASE_ACQUISITION_FAILED"
    assert "access_token" not in repr(result)
    assert result.registry is not None
    assert result.registry.lookup("RELIANCE").provider_binding is None


def test_missing_completed_five_minute_candle_is_data_incomplete(tmp_path: Path) -> None:
    result = RelianceIntradayBootstrap(
        acquire_lease=lambda: _Lease(omit_five=True),
        evidence_root=tmp_path,
        clock=lambda: OBSERVED,
    ).run()
    assert result.availability is RelianceBootstrapAvailability.DATA_INCOMPLETE
    assert result.stage is RelianceBootstrapStage.RECONCILIATION
    assert result.failure_code == "DATA_INCOMPLETE"
    assert result.bundle is None


def test_post_cas_reliance_missing_auction_period_is_not_data_incomplete(
    tmp_path: Path,
) -> None:
    observed = datetime(2026, 8, 18, 19, 10, tzinfo=IST)

    class _PostCloseLease(_Lease):
        def historical_candles(self, request):  # type: ignore[no-untyped-def]
            if request.interval is HistoricalInterval.DAY:
                return (
                    HistoricalCandle(
                        datetime(2026, 8, 17, 0, 0, tzinfo=IST),
                        1400.0, 1425.0, 1390.0, 1410.0, 1_000_000,
                    ),
                    HistoricalCandle(
                        datetime(2026, 8, 18, 0, 0, tzinfo=IST),
                        1412.0, 1420.0, 1408.0, 1418.0, 500_000,
                    ),
                )
            minutes = {
                HistoricalInterval.SIXTY_MINUTE: 60,
                HistoricalInterval.FIFTEEN_MINUTE: 15,
                HistoricalInterval.FIVE_MINUTE: 5,
            }[request.interval]
            values = []
            cursor = datetime(2026, 8, 18, 9, 15, tzinfo=IST)
            end = datetime(2026, 8, 18, 15, 15, tzinfo=IST)
            while cursor < end:
                values.append(HistoricalCandle(
                    cursor, 1410.0, 1412.0, 1409.0, 1411.0, 1000
                ))
                cursor += timedelta(minutes=minutes)
            return tuple(values)

    result = RelianceIntradayBootstrap(
        acquire_lease=lambda: _PostCloseLease(),
        evidence_root=tmp_path,
        clock=lambda: observed,
    ).run()

    assert result.availability is RelianceBootstrapAvailability.AVAILABLE
    assert result.failure_code == ""
    assert result.bundle is not None
    reconciliations = {
        item.reconciliation.timeframe: item.reconciliation
        for item in result.bundle.composition.evidence
    }
    assert len(reconciliations[IntradayTimeframe.ONE_HOUR].expected_boundaries) == 6
    assert len(reconciliations[IntradayTimeframe.FIFTEEN_MINUTES].expected_boundaries) == 24
    assert len(reconciliations[IntradayTimeframe.FIVE_MINUTES].expected_boundaries) == 72
    assert all(not item.missing_boundaries for item in reconciliations.values())


def test_reliance_runtime_projects_compact_presentation_only_triage(tmp_path: Path) -> None:
    workstation = RelianceIntradayRuntimeWorkstation(RelianceIntradayBootstrap(
        acquire_lease=lambda: _Lease(), evidence_root=tmp_path, clock=lambda: OBSERVED
    ))

    rendered = render_intraday_triage(workstation.snapshot("RELIANCE"))

    assert "RELIANCE" in rendered
    assert "PRESENTATION SELECTION ONLY" in rendered
    assert "15M" in rendered and "5M" in rendered
    assert "DETAILED EVIDENCE →" in rendered
    assert "Classic Pivots" not in rendered
    assert "Provider Token" not in rendered


def test_typed_lease_failure_is_preserved_and_rendered_without_credentials(
    tmp_path: Path,
) -> None:
    bootstrap = RelianceIntradayBootstrap(
        acquire_lease=lambda: (_ for _ in ()).throw(ProviderRuntimeAccessError(
            ProviderRuntimeFailure.CONTEXT_UNAVAILABLE
        )),
        evidence_root=tmp_path,
        clock=lambda: OBSERVED,
    )
    result = bootstrap.run()
    rendered = render_intraday_triage(
        RelianceIntradayRuntimeWorkstation(bootstrap).snapshot("RELIANCE")
    )

    assert result.stage is RelianceBootstrapStage.LEASE_ACQUISITION
    assert result.failure_code == "CONTEXT_UNAVAILABLE"
    assert "Runtime stage: LEASE_ACQUISITION" in rendered
    assert "Failure: CONTEXT_UNAVAILABLE" in rendered
    assert "Provider Token" not in rendered


def test_provider_assertion_failure_has_exact_stage(tmp_path: Path) -> None:
    class _AssertionFailure(_Lease):
        def instrument_assertions(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            del args, kwargs
            raise RuntimeError("api_secret=must-never-render")

    result = RelianceIntradayBootstrap(
        acquire_lease=lambda: _AssertionFailure(),
        evidence_root=tmp_path,
        clock=lambda: OBSERVED,
    ).run()

    assert result.stage is RelianceBootstrapStage.PROVIDER_ASSERTION
    assert result.failure_code == "PROVIDER_ASSERTION_FAILED"
    assert "api_secret" not in repr(result)


def test_canonical_catalogue_failure_has_exact_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        bootstrap_module,
        "load_canonical_instrument_catalogue",
        lambda: (_ for _ in ()).throw(RuntimeError("request_token=hidden")),
    )

    result = RelianceIntradayBootstrap(
        acquire_lease=lambda: _Lease(), evidence_root=tmp_path, clock=lambda: OBSERVED
    ).run()

    assert result.stage is RelianceBootstrapStage.CANONICAL_CATALOGUE
    assert result.failure_code == "CANONICAL_CATALOGUE_FAILED"
    assert result.registry is None
    assert "request_token" not in repr(result)


def test_runtime_instrument_failure_has_exact_stage(tmp_path: Path) -> None:
    class _NoAssertions(_Lease):
        def instrument_assertions(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            del args, kwargs
            return ()

    result = RelianceIntradayBootstrap(
        acquire_lease=lambda: _NoAssertions(), evidence_root=tmp_path,
        clock=lambda: OBSERVED,
    ).run()

    assert result.stage is RelianceBootstrapStage.RUNTIME_INSTRUMENT
    assert result.failure_code == "RUNTIME_INSTRUMENT_FAILED"


def test_market_schedule_failure_has_exact_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        bootstrap_module.CurrentMarketCalendarScheduleSource,
        "schedule_for",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("hidden")),
    )
    result = RelianceIntradayBootstrap(
        acquire_lease=lambda: _Lease(), evidence_root=tmp_path, clock=lambda: OBSERVED
    ).run()

    assert result.stage is RelianceBootstrapStage.MARKET_SCHEDULE
    assert result.failure_code == "MARKET_SCHEDULE_FAILED"


def test_typed_historical_retrieval_failure_is_preserved(tmp_path: Path) -> None:
    class _HistoricalFailure(_Lease):
        def historical_candles(self, request):  # type: ignore[no-untyped-def]
            del request
            raise HistoricalDataError(HistoricalDataFailure.PROVIDER_FAILURE)

    result = RelianceIntradayBootstrap(
        acquire_lease=lambda: _HistoricalFailure(), evidence_root=tmp_path,
        clock=lambda: OBSERVED,
    ).run()

    assert result.stage is RelianceBootstrapStage.HISTORICAL_RETRIEVAL
    assert result.failure_code == "PROVIDER_FAILURE"


def test_persistence_failure_has_exact_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_store(root):  # type: ignore[no-untyped-def]
        del root
        raise RuntimeError("filesystem credential path hidden")

    monkeypatch.setattr(bootstrap_module, "LocalIntradayFactualEvidenceStore", fail_store)
    result = RelianceIntradayBootstrap(
        acquire_lease=lambda: _Lease(), evidence_root=tmp_path, clock=lambda: OBSERVED
    ).run()

    assert result.stage is RelianceBootstrapStage.PERSISTENCE
    assert result.failure_code == "PERSISTENCE_FAILED"
    assert "filesystem" not in repr(result)


def test_untyped_provider_instrument_failure_is_stage_specific(tmp_path: Path) -> None:
    class _NoProviderInstrument(_Lease):
        def instrument_records(self, exchange):  # type: ignore[no-untyped-def]
            del exchange
            raise RuntimeError("Authorization: Bearer hidden")

    result = RelianceIntradayBootstrap(
        acquire_lease=lambda: _NoProviderInstrument(), evidence_root=tmp_path,
        clock=lambda: OBSERVED,
    ).run()

    assert result.stage is RelianceBootstrapStage.PROVIDER_INSTRUMENT
    assert result.failure_code == "PROVIDER_INSTRUMENT_FAILED"
    assert "Bearer" not in repr(result)
