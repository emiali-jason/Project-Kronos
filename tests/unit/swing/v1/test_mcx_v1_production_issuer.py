"""Isolated production-adapter tests; no fixture grants runtime authority."""

from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from kronos.provider.contracts.market_data import HistoricalCandle
from kronos.swing.v1.mcx_kr380_issuer import McxKr380Rejected
from kronos.swing.v1 import mcx_v1_production_issuer as issuer
from kronos.swing.v1.mcx_trade_plan import MCX_V1_ADVISORY_AUTHORITY


START = datetime(2026, 9, 29, 18, 0, tzinfo=ZoneInfo("Asia/Kolkata"))


def _production_fixture(tmp_path, monkeypatch):
    """Real stores/provider adapter; isolated authoritative read/owner seams."""
    from contextlib import nullcontext
    from dataclasses import asdict
    from datetime import date
    from types import SimpleNamespace
    from tests.unit.swing.v1.test_mcx_kr380_issuer import _v1_fixture
    from kronos.provider.contracts.instrument import InstrumentRecord
    from kronos.provider.contracts.provider_authentication import ReadOnlyProviderOperation
    from kronos.swing.v1.mcx_v1_advisory import LocalMcxV1AdvisoryStore
    read = _v1_fixture()
    instrument = InstrumentRecord("KITE", "MCX", "MCX-FUT",
        read.plan.contract_symbol, read.plan.family.value, "FUT",
        date.fromisoformat(read.plan.expiry), Decimal("1"), 1)
    # Rebind the exact plan hash after this fixture's normalized contract changes.
    from kronos.swing.v1.mcx_trade_plan import _digest as plan_digest
    fields = asdict(read.plan)
    fields["normalized_instrument_sha256"] = issuer.mcx_digest(asdict(instrument))
    fields["integrity_hash"] = ""
    fields["trade_plan_id"] = ""
    fields["trade_plan_id"] = "MCX-TRADE-PLAN-" + plan_digest(fields)
    fields["integrity_hash"] = plan_digest(fields)
    plan = type(read.plan)(**fields)
    risk = replace(read.risk, candidate_id=plan.trade_plan_id,
                   candidate_digest=plan.integrity_hash)
    bound = SimpleNamespace(
        run_identity=plan.native_run_identity, derivative_symbol=plan.contract_symbol,
        derivative_expiry=plan.expiry, family=plan.family,
        manifest_sha256=plan.manifest_sha256, assessment_sha256=plan.assessment_sha256,
        receipt_identity="receipt", receipt_integrity_sha256=plan.receipt_integrity_sha256,
        promotion_identity="v2", promotion_integrity_sha256=plan.promotion_integrity_sha256,
        request_bound_lineage_sha256="a"*64)
    owner = SimpleNamespace(prepared=SimpleNamespace(bound=bound),
                            fence=SimpleNamespace(check=lambda: None),
                            final_fence=nullcontext)
    monkeypatch.setattr(issuer, "McxOwnerSelectedHandoff", SimpleNamespace)
    match = SimpleNamespace(provider_instrument_token=read.authority.provider_token,
                            snapshot_file_sha256="b"*64)
    monkeypatch.setattr(issuer, "read_retained_mcx_master_match", lambda *a, **k: match)
    from dataclasses import dataclass
    @dataclass
    class Snapshot:
        identity: str = "isolated-retained-snapshot"
    snapshot = Snapshot()
    mtf = issuer.MtfFactEvidenceStore(tmp_path / "mtf")
    monkeypatch.setattr(mtf, "load", lambda _run: snapshot)
    hours = tuple(HistoricalCandle(c.opened_at, float(c.open), float(c.high),
                    float(c.low), float(c.close), 1)
                  for c in (read.previous, read.current))
    source = (issuer.mcx_digest(asdict(snapshot)), "c"*64, "d"*64, *hours)
    calls = []
    def completed(*a, **kw):
        calls.append(kw["evaluated_at"])
        return source
    monkeypatch.setattr(issuer, "_read_completed_source", completed)
    capability = SimpleNamespace(active=True,
        operations=(ReadOnlyProviderOperation.HISTORICAL_DATA,),
        historical_candles=lambda _request: (_ for _ in ()).throw(
            AssertionError("fixture seam must not acquire production data")))
    kwargs = dict(plan=plan, risk=risk, instrument=instrument,
        master=issuer.ProviderInstrumentSnapshotStore(tmp_path / "master"),
        provider=issuer.KiteMarketDataProvider(capability), mtf=mtf,
        schedule=read.schedule, owner=owner, current_plan=lambda: plan,
        monitoring_binding_identity="position-1", evaluated_at=read.current.closed_at,
        store=LocalMcxV1AdvisoryStore(tmp_path / "advisories"))
    kwargs["clock"] = lambda: kwargs["evaluated_at"]
    return kwargs, source, calls


def test_production_adapter_separate_advisory_replay_and_currentness(tmp_path, monkeypatch):
    from kronos.swing.v1.mcx_v1_advisory import McxV1AdvisoryOutcome, LocalMcxV1AdvisoryStore
    from kronos.swing.v1.native_entry_timing import Kr380EntryOutcomeV2
    args, source, calls = _production_fixture(tmp_path, monkeypatch)
    first = issuer.issue_v1_production_signal(**args)
    assert type(first) is McxV1AdvisoryOutcome
    assert not isinstance(first, Kr380EntryOutcomeV2)
    assert first.intrabar_trade_continuity == "UNVERIFIED"
    assert first.broker_authority == "NONE"
    assert len(calls) == 3
    args["evaluated_at"] += timedelta(seconds=10)
    assert issuer.issue_v1_production_signal(**args) == first
    assert LocalMcxV1AdvisoryStore(args["store"].root).load_for_plan(
        args["plan"].trade_plan_id) == first
    before = {p: p.read_bytes() for p in args["store"].root.rglob("*") if p.is_file()}
    args["current_plan"] = lambda: None
    with pytest.raises(McxKr380Rejected, match="CURRENT_REVIEW_CHANGED"):
        issuer.issue_v1_production_signal(**args)
    assert {p: p.read_bytes() for p in before} == before


def test_production_adapter_advances_to_later_completed_pair(tmp_path, monkeypatch):
    args, source, calls = _production_fixture(tmp_path, monkeypatch)
    first, second = source[-2:]
    pre_cross = (args["plan"].entry - args["instrument"].tick_size
                 if args["plan"].native_direction.value == "LONG" else
                 args["plan"].entry + args["instrument"].tick_size)
    second = replace(second, open=float(pre_cross), high=float(pre_cross),
                     low=float(pre_cross), close=float(pre_cross))
    third = HistoricalCandle(
        second.timestamp + timedelta(hours=1), float(pre_cross),
        float(max(pre_cross, args["plan"].entry)),
        float(min(pre_cross, args["plan"].entry)),
        float(args["plan"].entry), 1)
    advanced = (*source[:3], first, second, third)
    monkeypatch.setattr(issuer, "_read_completed_source", lambda *a, **k: advanced)
    args["evaluated_at"] = third.timestamp + timedelta(hours=1)
    args["clock"] = lambda: args["evaluated_at"]

    outcome = issuer.issue_v1_production_signal(**args)

    assert outcome.source_sequence == (1, 2)
    assert outcome.observation_boundary == third.timestamp + timedelta(hours=1)
    assert outcome.occurred_at == outcome.observation_boundary
    assert outcome.source_observation_ids == (
        "MCX-1H-P-" + issuer.mcx_digest(issuer.asdict(second)),
        "MCX-1H-C-" + issuer.mcx_digest(issuer.asdict(third)),
    )


def test_advisory_store_concurrent_replay_never_replaces_identity(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from kronos.swing.v1.mcx_v1_advisory import LocalMcxV1AdvisoryStore, McxV1AdvisoryOutcome
    from dataclasses import asdict
    args, _, _ = _production_fixture(tmp_path, monkeypatch)
    record = issuer.issue_v1_production_signal(**args)
    root = tmp_path / "shared-advisory"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(lambda _: LocalMcxV1AdvisoryStore(root).retain_current(record), range(2)))
    assert results == (None, None)
    fields = asdict(record)
    fields.pop("integrity_sha256")
    fields["confirmed_at"] += timedelta(seconds=1)
    changed = McxV1AdvisoryOutcome.create(**fields)
    with pytest.raises(ValueError, match="REPLAY_CONFLICT"):
        LocalMcxV1AdvisoryStore(root).retain_current(changed)
    assert LocalMcxV1AdvisoryStore(root).load_for_plan(record.trade_plan_id) == record
    assert len(tuple(root.iterdir())) == 1


@pytest.mark.parametrize("change", ["revision", "opening_gap", "wick", "partial", "commit"])
def test_production_adapter_rejects_changes_before_writes(tmp_path, monkeypatch, change):
    args, source, _ = _production_fixture(tmp_path, monkeypatch)
    if change == "revision":
        values = iter((source, (*source[:2], "e"*64, *source[3:])))
        monkeypatch.setattr(issuer, "_read_completed_source", lambda *a, **k: next(values))
    elif change in {"opening_gap", "wick"}:
        current = replace(source[-1], **({"open": float(args["plan"].entry)}
                         if change == "opening_gap" else {"close": source[-2].close}))
        monkeypatch.setattr(issuer, "_read_completed_source",
                            lambda *a, **k: (*source[:-1], current))
    elif change == "partial":
        monkeypatch.setattr(issuer, "_read_completed_source",
            lambda *a, **k: (_ for _ in ()).throw(McxKr380Rejected("PARTIAL_1H")))
    else:
        plans = iter((args["plan"], None))
        args["current_plan"] = lambda: next(plans)
    with pytest.raises(McxKr380Rejected):
        issuer.issue_v1_production_signal(**args)
    assert not args["store"].root.exists()


@pytest.mark.parametrize(
    "change", [None, "later", "missing", "reversed", "revised", "partial"])
def test_authenticated_hour_read_has_no_minute_or_trade_sequence_requirement(
    tmp_path, monkeypatch, change,
):
    from dataclasses import asdict, dataclass
    from types import SimpleNamespace
    from kronos.market.calendar import MarketCalendarPublisher
    from kronos.provider.contracts.instrument import InstrumentRecord
    from kronos.provider.contracts.provider_authentication import ReadOnlyProviderOperation
    from kronos.provider.contracts.market_data import HistoricalInterval

    @dataclass
    class Anchor:
        source_timestamp: datetime = START
        observation_boundary: datetime = START + timedelta(hours=1)
        session_identity: str = ""
        open: float = 99.0
        high: float = 99.0
        low: float = 99.0
        close: float = 99.0
        volume: int = 1

    @dataclass
    class Lineage:
        trading_symbol: str
        expiry: str
        normalized_instrument_sha256: str
        completed_1h_sha256: str

    @dataclass
    class Subject:
        canonical_instrument: str
        mcx_request_lineage: Lineage
        anchor: Anchor
        completed_series: tuple = ()

        def fact(self, _timeframe):
            return self.anchor

    @dataclass
    class Snapshot:
        run_identity: str
        instruments: tuple

    from datetime import date
    from kronos.swing.v1.mcx_contract_profile import McxFamily
    instrument = InstrumentRecord("KITE", "MCX", "MCX-FUT", "GOLDM26OCTFUT",
        "GOLDM", "FUT", date(2026, 10, 5), Decimal("1"), 1)
    schedule = MarketCalendarPublisher().schedule("MCX", START.date(), observed_at=START)
    anchor = Anchor(session_identity=schedule.session_identity)
    anchor_sha = issuer.mcx_digest(asdict(anchor))
    lineage = Lineage(instrument.trading_symbol, instrument.expiry.isoformat(),
                      issuer.mcx_digest(asdict(instrument)), anchor_sha)
    snapshot = Snapshot("isolated-run", (Subject("GOLDM", lineage, anchor),))
    plan = SimpleNamespace(native_run_identity=snapshot.run_identity,
        family=McxFamily.GOLDM, completed_one_hour_sha256=anchor_sha,
        observation_boundary=anchor.observation_boundary,
        expiry_session_identity=schedule.session_identity,
        entry_eligibility_boundary=START + timedelta(hours=5))
    store = issuer.MtfFactEvidenceStore(tmp_path / "mtf")
    monkeypatch.setattr(store, "load", lambda _run: snapshot)
    # Exact-run lineage validation has separate owning coverage. This fixture
    # isolates the Provider-hour acquisition and completion boundary.
    monkeypatch.setattr(issuer, "mcx_lineage_matches_completed_facts", lambda *a, **k: True)
    hours = (HistoricalCandle(START, 99., 99., 99., 99., 1),
             HistoricalCandle(START + timedelta(hours=1), 99., 101., 99., 101., 1))
    if change == "missing":
        hours = hours[:1]
    elif change == "reversed":
        hours = tuple(reversed(hours))
    elif change == "revised":
        hours = (replace(hours[0], volume=2), hours[1])
    elif change == "later":
        hours += (HistoricalCandle(
            START + timedelta(hours=2), 101., 102., 100., 102., 1),)
    requests = []
    def historical(request):
        requests.append(request)
        return hours
    provider = issuer.KiteMarketDataProvider(SimpleNamespace(active=True,
        operations=(ReadOnlyProviderOperation.HISTORICAL_DATA,),
        historical_candles=historical))
    now = START + timedelta(hours=2)
    if change == "partial":
        now -= timedelta(seconds=1)
    elif change == "later":
        now += timedelta(hours=1)
    if change not in {None, "later"}:
        with pytest.raises(McxKr380Rejected):
            issuer._read_completed_source(plan, instrument, provider, store,
                                          schedule, evaluated_at=now)
    else:
        result = issuer._read_completed_source(plan, instrument, provider, store,
                                              schedule, evaluated_at=now)
        assert result[3:] == hours
    assert all(r.instrument == instrument and r.interval is HistoricalInterval.SIXTY_MINUTE
               for r in requests)
    assert len(requests) == (0 if change == "partial" else 1)
