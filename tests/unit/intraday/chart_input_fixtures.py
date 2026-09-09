"""Synthetic observed panels for transport tests; never real pixel qualification."""
from kronos.intraday.chart_input import ObservedChartPanel, ChartInputObservation, CORE_CONTENT
from kronos.intraday.contracts import CandleCompletion
from kronos.intraday.validation import FactObservability


def fixture_receipt(app, chart, label=None):
    cycle = app.review_store.load_cycle(chart.review_cycle_identity)
    panels = []
    for e in app._chart_input.expectations(cycle, chart):
        source, schedule = e.source, e.schedule
        assert source is not None and schedule is not None
        panels.append(ObservedChartPanel(
            role=e.role, timeframe=e.timeframe,
            observed_subject=label or e.visual_target, venue=e.venue,
            observed_series=None, currency=None, unit=None,
            trading_date=schedule.trading_date, session=schedule.session_type,
            timezone=schedule.timezone, candle_start=source.candle_start,
            candle_end=source.candle_end, completion=CandleCompletion.COMPLETE,
            captured_at=chart.received_at, latest_visible_end=source.candle_end,
            entire_panel_observed=True, opinion_overlays_present=False,
            content=tuple((k, FactObservability.EXACT) for k in CORE_CONTENT),
        ))
    return ChartInputObservation(chart.chart_revision_identity, chart.payload_sha256,
        chart.review_cycle_identity, chart.probables_run_identity, chart.probable_result_identity,
        'WO-07B-SYNTHETIC-INDEPENDENT-OBSERVER-NOT-PRODUCTION', chart.received_at, tuple(panels))


def retain_fixture_receipt(app, chart, label=None):
    value = fixture_receipt(app, chart, label)
    app.review_store.retain_chart_input(value)
    return value


def observe_fixture_uploads(app):
    """Explicit fixture producer, not a bypass of the real correspondence gate."""
    original = app.upload_chart
    def upload(*args, **kwargs):
        chart = original(*args, **kwargs)
        if chart.paired_bundle_identity is None:
            retain_fixture_receipt(app, chart)
        return chart
    app.upload_chart = upload


def configure_fixture_calendar(app):
    # The older transport corpus deliberately uses an explicit 10:00–16:30
    # synthetic session. Reuse its schedule; never substitute production hours.
    from dataclasses import replace
    from types import SimpleNamespace
    from kronos.market.calendar import MarketCalendarPublisher
    from kronos.market.schedule import MarketSessionWindow
    from tests.unit.intraday.test_probables_v2 import _schedule
    class FixtureCalendar:
        def instrument_session_profile(self, exchange, day, *, canonical_instrument_id, observed_at):
            real = MarketCalendarPublisher().instrument_session_profile(
                exchange, day, canonical_instrument_id='NSE-EQ-BDL' if exchange == 'NSE' else canonical_instrument_id,
                observed_at=observed_at)
            if real is None: return None
            schedule = _schedule(day, exchange)
            template = real.continuous_trading
            fixed = replace(template, session_identity=schedule.session_id,
                session_open=schedule.windows[0].opens_at, session_close=schedule.windows[-1].closes_at,
                windows=tuple(MarketSessionWindow(schedule.session_id+':WINDOW:'+str(i), i,
                    w.opens_at, w.closes_at) for i,w in enumerate(schedule.windows,1)),
                calendar_identity=schedule.source_identity, source_identity=schedule.source_identity,
                calendar_version=schedule.source_version)
            return SimpleNamespace(continuous_trading=fixed, closing_auction_session=None)
    app._chart_input.calendar = FixtureCalendar()


def retain_current_fixture_receipts(app, label):
    configure_fixture_calendar(app)
    for member in app.review_store.load_current().cycles:
        pointer = app.review_store.load_current_chart(member.cycle_identity)
        if pointer:
            retain_fixture_receipt(app, app.review_store.load_chart(pointer.chart_revision_identity), label)


def retain_legacy_paired_fixture(app, cycle, chart):
    """Create historical codec evidence to qualify unchanged replay/restoration.

    New operational import must first have been asserted rejected by WO-07B.
    This is an isolated fixture for evidence already imported before the gate.
    """
    bundle, native, reference, pack, transport, _, _ = app._paired.retained(cycle, chart)
    payload = app._transport.read_expected_answer(transport.expected_answer_filename)
    resolver = app._paired.native_resolver
    _, evidence = app._paired.engine.import_answer(payload=payload, pack=pack, bundle=bundle,
        native_chart=native, reference_chart=reference, native_resolver=resolver,
        reference_resolver=resolver, imported_at=app._clock(), supporting_reference_only=True)
    app._paired.store.retain_evidence_pointer(evidence)
    return evidence
