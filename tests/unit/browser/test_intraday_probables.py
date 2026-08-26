from dataclasses import replace
from http import HTTPStatus
from pathlib import Path

from kronos.application.intraday_discovery import IntradayDiscoveryApplication
from kronos.application.intraday_probables import IntradayProbablesApplication
from kronos.browser.intraday_routes import IntradayBrowserRoutes
from kronos.browser.product_routes import BrowserGetRequest
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.probables import FactualSourceKind
from kronos.intraday.probables_persistence import ProbablesStore
from tests.unit.browser.test_product_route_isolation import _snapshot
from tests.unit.intraday.test_discovery_runtime import BOUNDARY, _publications, _service
from tests.unit.intraday.test_probables import SESSION, _member


def test_browser_projects_probables_without_provider_calls(tmp_path: Path) -> None:
    service, source, discovery_store, _ = _service(tmp_path / "discovery")
    universe, reconciliation = _publications()
    probables = IntradayProbablesApplication(
        store=ProbablesStore((tmp_path / "probables").resolve())
    )
    application = IntradayDiscoveryApplication(
        universe=universe,
        reconciliation=reconciliation,
        store=discovery_store,
        service=service,
        probables=probables,
    )
    discovery_run = application.run_discovery(BOUNDARY)
    reliance = next(
        item
        for item in discovery_run.results
        if item.canonical_identity == "RELIANCE"
    )
    evidence = replace(
        _member(boundary=BOUNDARY.observation_boundary),
        universe_member_identity=reliance.universe_member_identity,
        source_run_identity=discovery_run.run_identity,
        source_member_identity=reliance.persistence_identity,
    )
    second = next(
        item
        for item in discovery_run.results
        if item.canonical_identity != "RELIANCE" and item.machine_fact_bundle_identity
    )
    short_evidence = replace(
        _member(
            subject=second.canonical_identity,
            boundary=BOUNDARY.observation_boundary,
            hourly=SemanticDirection.SHORT,
            fifteen=SemanticDirection.SHORT,
        ),
        universe_member_identity=second.universe_member_identity,
        source_run_identity=discovery_run.run_identity,
        source_member_identity=second.persistence_identity,
    )
    probables.refresh_analysis(
        source_kind=FactualSourceKind.NATIVE_DISCOVERY,
        source_run_identity=discovery_run.run_identity,
        universe_identity=universe.publication_identity,
        universe_version=universe.publication_version,
        reconciliation_identity=reconciliation.publication_identity,
        reconciliation_version=reconciliation.publication_version,
        market_session_identity=SESSION,
        observation_boundary=BOUNDARY.observation_boundary,
        member_evidence=(evidence, short_evidence),
        unavailable_members=(),
        provenance=("SYNTHETIC-TEST-FIXTURE",),
    )
    before = tuple(source.labels)
    routes = IntradayBrowserRoutes(application)
    main = routes.handle_get(BrowserGetRequest("/intraday", {}), _snapshot)
    detail = routes.handle_get(
        BrowserGetRequest("/intraday/evidence/RELIANCE", {}), _snapshot
    )

    assert main is not None and main.status is HTTPStatus.OK
    assert detail is not None and detail.status is HTTPStatus.OK
    assert "Intraday Opportunities — Native Discovery" in main.body
    assert "Native Discovery — governed facts, complete accounting, no trading authority." in main.body
    assert 'class="tabs intraday-tabs"' in main.body
    for tab in ("Opportunities", "Review", "Trade Candidates", "Active", "Closed"):
        assert tab in main.body
    assert "Refresh Analysis" in main.body
    assert "Market analysis" in main.body and "IST" in main.body
    assert "V0 Probables methodology" in main.body
    assert "Long Probables" in main.body
    assert "Short Probables" in main.body
    assert "Not Admitted" in main.body and "Unavailable" in main.body
    assert 'class="panels intraday-market-panels"' in main.body
    assert "EQUITIES + INDICES" in main.body
    assert "COMMODITIES (MCX)" in main.body
    assert "current Probables" in main.body
    assert "direction direction-long" in main.body
    assert "direction direction-short" in main.body
    assert "1H regime" in main.body
    assert "15M structure" in main.body
    assert "Coherence" in main.body and "Participation" in main.body
    assert "Analysis Context" in main.body
    assert "Observation Boundary" in main.body
    assert "Completed 1D" in main.body and "Completed 5M" in main.body
    assert "intraday-analysis-context-detail{display:flex" in main.body
    assert "font-size:8px" in main.body
    assert "Current Probables triage" not in main.body
    assert "linear-gradient(135deg,#071a12,#0b271a)" not in main.body
    assert "Probable means selected for deeper review only" in main.body
    assert "KRONOS-INTRADAY-PROBABLES-METHODOLOGY-V1" in detail.body
    assert "Narrow CPR fact" in detail.body
    assert "1H fact" in detail.body and "15M fact" in detail.body
    assert "PLACE ORDER" not in main.body + detail.body
    assert tuple(source.labels) == before


def test_browser_get_does_not_create_probables_run(tmp_path: Path) -> None:
    service, _, discovery_store, _ = _service(tmp_path / "discovery")
    universe, reconciliation = _publications()
    probables = IntradayProbablesApplication(
        store=ProbablesStore((tmp_path / "probables").resolve())
    )
    application = IntradayDiscoveryApplication(
        universe=universe,
        reconciliation=reconciliation,
        store=discovery_store,
        service=service,
        probables=probables,
    )
    routes = IntradayBrowserRoutes(application)

    first = routes.handle_get(BrowserGetRequest("/intraday", {}), _snapshot)
    second = routes.handle_get(BrowserGetRequest("/intraday", {}), _snapshot)

    assert first is not None and second is not None
    assert probables.snapshot().run is None
    assert "Browser refresh does not create an analytical run" in first.body
    assert "Intraday Opportunities — Native Discovery" in first.body
    assert "Refresh Analysis" in first.body
    assert "Analysis Context" in first.body
    assert first.body == second.body
