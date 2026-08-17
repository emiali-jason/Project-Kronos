from threading import Thread

from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.application.swing_v1_review import SwingV1ReviewWorkflow
from kronos.browser.server import create_browser_server
from kronos.browser.views import render_mtf_fact_diagnostics
from kronos.swing.v1 import LocalTradingViewEvidenceStore
from kronos.swing.v1.mtf_facts import FactualTimeframe

from tests.unit.application.test_swing_mtf_facts import _build
from tests.unit.application.test_swing_opportunities import _Provider
from tests.unit.browser.test_browser_server import _request
from tests.unit.browser.test_browser_views import _ready


def test_browser_exposes_selected_current_mtf_boundaries_ohlcv_and_provenance() -> None:
    facts, _ = _build()
    html = render_mtf_fact_diagnostics(_ready(), facts)
    reliance = facts.instrument("RELIANCE")
    goldm = facts.instrument("GOLDM")

    assert "CURRENT GOVERNED MTF FACTS" in html
    assert "98 INSTRUMENTS" in html
    assert "FACTUAL ONLY" in html
    assert "NO CANDIDATE AUTHORITY" in html
    assert "QUOTE CONTEXT SEPARATE" in html
    assert "RELIANCE" in html
    assert "GOLDM" in html
    for instrument in (reliance, goldm):
        for timeframe in FactualTimeframe:
            fact = instrument.fact(timeframe)
            assert timeframe.value in html
            assert fact.observation_boundary.isoformat() in html
            assert (
                f"{fact.open:g} / {fact.high:g} / {fact.low:g} / "
                f"{fact.close:g} / {fact.volume}"
            ) in html
            assert fact.calendar_identity in html
            assert fact.session_identity in html
            assert fact.source_provider_identity in html


def test_browser_mtf_diagnostics_has_bounded_unavailable_state() -> None:
    html = render_mtf_fact_diagnostics(_ready(), None)

    assert "Current governed MTF facts are not available for this run." in html


def test_browser_mtf_route_reads_the_application_same_run_snapshot(tmp_path) -> None:
    facts, _ = _build()
    application = SwingOpportunitiesApplication(_Provider, initial_snapshot=_ready())
    application.restore_mtf_fact_snapshot(facts)
    review = SwingV1ReviewWorkflow(LocalTradingViewEvidenceStore(tmp_path))
    server = create_browser_server(application, port=0, v1_review=review)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, body = _request(server, "GET", "/swing/mtf-diagnostics")
        assert status == 200
        assert "CURRENT GOVERNED MTF FACTS" in body
        assert "RELIANCE" in body
        assert "GOLDM" in body
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
