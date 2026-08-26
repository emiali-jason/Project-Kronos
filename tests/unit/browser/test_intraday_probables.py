from dataclasses import replace
from http import HTTPStatus
from pathlib import Path

from kronos.application.intraday_discovery import IntradayDiscoveryApplication
from kronos.application.intraday_probables import IntradayProbablesApplication
from kronos.browser.intraday_routes import IntradayBrowserRoutes
from kronos.browser.product_routes import BrowserGetRequest
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
    probables.refresh_analysis(
        source_kind=FactualSourceKind.NATIVE_DISCOVERY,
        source_run_identity=discovery_run.run_identity,
        universe_identity=universe.publication_identity,
        universe_version=universe.publication_version,
        reconciliation_identity=reconciliation.publication_identity,
        reconciliation_version=reconciliation.publication_version,
        market_session_identity=SESSION,
        observation_boundary=BOUNDARY.observation_boundary,
        member_evidence=(evidence,),
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
    assert "V0 Probables methodology" in main.body
    assert "Long Probables" in main.body
    assert "Long Probable" in main.body
    assert "Not Admitted" in main.body and "Unavailable" in main.body
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
    assert first.body == second.body
