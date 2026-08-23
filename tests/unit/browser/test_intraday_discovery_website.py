import inspect
from http import HTTPStatus
from pathlib import Path

from kronos.browser import intraday_views
from kronos.browser.intraday_routes import IntradayBrowserRoutes
from kronos.browser.product_routes import BrowserGetRequest
from tests.unit.application.test_intraday_discovery import _application
from tests.unit.browser.test_product_route_isolation import _snapshot
from tests.unit.intraday.test_discovery_runtime import BOUNDARY


def _get(routes, path):  # type: ignore[no-untyped-def]
    response = routes.handle_get(BrowserGetRequest(path, {}), _snapshot)
    assert response is not None
    assert response.status is HTTPStatus.OK
    return response.body


def test_intraday_main_page_is_compact_multi_instrument_factual_triage(
    tmp_path: Path,
) -> None:
    app, _, _, _, _ = _application(tmp_path)
    body = _get(IntradayBrowserRoutes(app), "/intraday")

    assert "INTRADAY · NATIVE DISCOVERY" in body
    assert "NO SUCCESSFUL DISCOVERY RUN AVAILABLE" in body
    assert ">98<" in body
    assert ">93<" in body
    assert ">5<" in body
    assert "Candidate-admission methodology is not yet commissioned" in body
    assert "stable canonical ordering only" in body
    assert body.count("/intraday/evidence/") == 15
    assert "GOLDM" in body and "Active Derivative Binding Unavailable" in body
    assert "NATGAS" in body and "Provider Contract Unavailable" in body
    assert "font-size:17px" in body
    assert "#071a12" in body
    assert "PLACE ORDER" not in body


def test_intraday_main_and_details_project_successful_run_without_fake_candidates(
    tmp_path: Path,
) -> None:
    app, _, _, _, _ = _application(tmp_path)
    app.run_discovery(BOUNDARY)
    routes = IntradayBrowserRoutes(app)

    main = _get(routes, "/intraday")
    reliance = _get(routes, "/intraday/evidence/RELIANCE")
    nifty = _get(routes, "/intraday/evidence/NIFTY")
    banknifty = _get(routes, "/intraday/evidence/BANKNIFTY")

    assert "LAST SUCCESSFUL ANALYSIS ·" in main
    assert "Machine facts complete" in main and ">93<" in main
    assert "Candidate Admitted" not in main
    for body, identity in ((reliance, "RELIANCE"), (nifty, "NIFTY"), (banknifty, "BANKNIFTY")):
        assert identity in body
        assert "Timeframe completeness / evidence" in body
        assert all(timeframe in body for timeframe in ("1D", "1H", "15M", "5M"))
        assert "NOT ESTABLISHED" in body
        assert "Previous Session / PDH / PDL" in body
        assert "Classic Pivots / CPR" in body


def test_current_failure_is_separate_from_last_successful_analysis(tmp_path: Path) -> None:
    app, _, _, _, _ = _application(tmp_path)
    run = app.run_discovery(BOUNDARY)
    app.record_failure("SOURCE_STALE")

    body = _get(IntradayBrowserRoutes(app), "/intraday")

    assert "CURRENT RUN FAILURE" in body
    assert "Source Stale" in body
    assert "LAST SUCCESSFUL ANALYSIS ·" in body
    assert app.snapshot().last_successful_run_identity == run.run_identity


def test_publication_stale_uses_bounded_sponsor_safe_explanation(tmp_path: Path) -> None:
    app, _, _, _, _ = _application(tmp_path)
    app.record_failure("PUBLICATION_STALE")

    body = _get(IntradayBrowserRoutes(app), "/intraday")

    assert (
        "Discovery could not run because the selected observation boundary "
        "predates the active Intraday universe publication."
    ) in body
    assert "Traceback" not in body
    assert "access_token" not in body
    assert "Provider Token" not in body


def test_browser_is_derivative_and_contains_no_discovery_calculations() -> None:
    source = inspect.getsource(intraday_views)

    assert "create_discovery_result(" not in source
    assert "create_machine_fact_bundle(" not in source
    assert "classic_pivots(" not in source
    assert "build_structural_evidence(" not in source
    assert "place_order" not in source
    assert "kronos.swing" not in source
