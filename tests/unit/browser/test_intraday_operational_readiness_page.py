from __future__ import annotations

from datetime import timedelta
from copy import deepcopy
from html import escape

import pytest

from tests.unit.application.test_intraday_operational_readiness import (
    SAFE_FALLBACK,
    UNSAFE_FAILURE_INPUTS,
)

from kronos.application.intraday_operational_readiness import (
    IntradayOperationalReadinessRuntimeService,
)
from kronos.application.intraday_runtime import create_intraday_workstation
from kronos.browser.intraday_operational_readiness import (
    IntradayOperationalReadinessProjection,
    WO_B_PRODUCT_ROUTE,
)
from kronos.browser.intraday_routes import IntradayBrowserRoutes
from kronos.browser.product_routes import BrowserGetRequest
from kronos.browser.intraday_views import render_intraday_operational_readiness
from kronos.intraday.operational_readiness_persistence import WoBStore
from tests.unit.browser.test_product_route_isolation import _snapshot
from tests.unit.intraday.test_operational_readiness_composition import (
    _boundary,
    _composition,
    _foundation,
)


class _Loader:
    def current_requests(self, observed_at):  # type: ignore[no-untyped-def]
        del observed_at
        return (_composition(*_foundation()),)


def _routes(tmp_path):  # type: ignore[no-untyped-def]
    store = WoBStore((tmp_path / "wo-b").resolve())
    service = IntradayOperationalReadinessRuntimeService(
        loader=_Loader(),
        store=store,
        clock=lambda: _boundary() + timedelta(minutes=20),
    )
    return IntradayBrowserRoutes(
        create_intraday_workstation(),
        operational_readiness=IntradayOperationalReadinessProjection(service),
    ), store


def _get(routes, path):  # type: ignore[no-untyped-def]
    response = routes.handle_get(BrowserGetRequest(path, {}), _snapshot)
    assert response is not None and response.status.value == 200
    return response.body


def test_operational_review_route_preserves_source_and_review_truth(tmp_path) -> None:  # type: ignore[no-untyped-def]
    routes, store = _routes(tmp_path)
    before = store.root.exists()
    body = _get(routes, WO_B_PRODUCT_ROUTE)

    assert "Operational Readiness Review" in body
    assert "READ-ONLY CROSS-DOMAIN COMPOSITION" in body
    assert "PROBABLES" in body
    assert "LONG_PROBABLE" in body
    assert "AVAILABLE" in body
    assert "ANALYTICAL_PROMOTION" in body
    assert "Exact identities and currentness" in body
    assert "NO GLOBAL READINESS" in body
    assert "PLACE ORDER" not in body
    assert "Sponsor Decision" not in body
    assert store.root.exists() is before


def test_intraday_main_integrates_read_only_review_summary(tmp_path) -> None:  # type: ignore[no-untyped-def]
    routes, store = _routes(tmp_path)
    body = _get(routes, "/intraday")
    assert 'href="/intraday/operational-review"' in body
    assert "Current admitted opportunities reviewed" in body
    assert not store.root.exists()


def test_no_wo_b_post_or_duplicate_sponsor_control(tmp_path) -> None:  # type: ignore[no-untyped-def]
    routes, _ = _routes(tmp_path)
    body = _get(routes, WO_B_PRODUCT_ROUTE)
    assert routes.owns_post("/control/intraday-operational-review") is False
    assert "data-choice=" not in body
    assert "SPONSOR ATTENTION AVAILABLE" not in body


@pytest.mark.parametrize("raw", UNSAFE_FAILURE_INPUTS)
def test_unknown_exception_cannot_reach_status_or_browser(tmp_path, raw) -> None:  # type: ignore[no-untyped-def]
    class FailedLoader:
        def current_requests(self, observed_at):
            raise RuntimeError(raw)

    service = IntradayOperationalReadinessRuntimeService(
        loader=FailedLoader(), store=WoBStore((tmp_path / "wo-b").resolve()), clock=_boundary,
    )
    document = service.status_document()
    assert document["restoration_state"] == "UNAVAILABLE"
    assert document["failure_reason"] == SAFE_FALLBACK
    routes = IntradayBrowserRoutes(
        create_intraday_workstation(),
        operational_readiness=IntradayOperationalReadinessProjection(service),
    )
    body = _get(routes, WO_B_PRODUCT_ROUTE)
    assert SAFE_FALLBACK in body
    assert raw not in body
    assert raw not in str(document)
    for marker in ("TEST_ONLY", "/Users/example", "example.invalid", "Traceback", "private diagnostic"):
        assert marker not in body
        assert marker not in str(document)
    assert not service.store.root.exists()
    assert "SPONSOR ATTENTION AVAILABLE" not in body


def test_mobile_css_is_bounded_and_page_has_no_script(tmp_path) -> None:  # type: ignore[no-untyped-def]
    routes, _ = _routes(tmp_path)
    body = _get(routes, WO_B_PRODUCT_ROUTE)
    assert "@media(max-width:760px)" in body
    assert ".app,.sidebar,.main,.topbar,.content,.wo-b-card{width:100%;min-width:0;max-width:100%}" in body
    assert ".nav{grid-template-columns:repeat(2,minmax(0,1fr))}" in body
    assert ".topbar,.wo-b-card .panel-head{align-items:flex-start;flex-direction:column}" in body
    assert ".wo-b-card .table-wrap{width:100%;max-width:100%;overflow-x:auto}" in body
    assert "fetch('/control/intraday-operational-review'" not in body


def _failure_status(state="UNAVAILABLE", reason="WO_B_DOMAIN_001_BINDING_UNAVAILABLE", persisted=False):  # type: ignore[no-untyped-def]
    return {
        "restoration_state": state,
        "failure_reason": reason,
        "reviews": (),
        "latest_failures": ({
            "candidate_identity": "INTRADAY-CANDIDATE-TEST",
            "stage": "COMPOSITION",
            "reason": "WO_B_PREVIOUS_SOURCE_INVALID",
            "failed_at": "2026-09-04T12:00:00+05:30",
        },) if persisted else (),
    }


@pytest.mark.parametrize("state", ("UNAVAILABLE", "CORRUPT"))
def test_current_failure_reason_visible_without_persisted_failure(state) -> None:  # type: ignore[no-untyped-def]
    body = render_intraday_operational_readiness(_snapshot(), _failure_status(state))
    assert "Current review failure" in body
    assert state in body
    assert "WO_B_DOMAIN_001_BINDING_UNAVAILABLE" in body
    assert "Latest persisted WO-B failure" not in body


@pytest.mark.parametrize("same_reason", (False, True))
def test_current_and_persisted_failures_have_distinct_provenance(same_reason) -> None:  # type: ignore[no-untyped-def]
    status = _failure_status(persisted=True)
    if same_reason:
        status["latest_failures"][0]["reason"] = status["failure_reason"]
    before = deepcopy(status)
    body = render_intraday_operational_readiness(_snapshot(), status)
    assert body.count("<strong>Current review failure</strong>") == 1
    assert body.count("Latest persisted WO-B failure") == 1
    assert "WO_B_DOMAIN_001_BINDING_UNAVAILABLE" in body
    assert status["latest_failures"][0]["reason"] in body
    assert "2026-09-04T12:00:00+05:30" in body
    assert status == before


def test_persisted_failure_does_not_become_current_failure() -> None:
    body = render_intraday_operational_readiness(
        _snapshot(), _failure_status("AVAILABLE", None, persisted=True)
    )
    assert "Latest persisted WO-B failure" in body
    assert "WO_B_PREVIOUS_SOURCE_INVALID" in body
    assert "Current review failure" not in body


@pytest.mark.parametrize("state", ("AVAILABLE", "RESTORED"))
@pytest.mark.parametrize("omit_reason", (False, True))
def test_healthy_projection_does_not_invent_current_failure(state, omit_reason) -> None:  # type: ignore[no-untyped-def]
    status = _failure_status(state, None)
    if omit_reason:
        del status["failure_reason"]
    body = render_intraday_operational_readiness(_snapshot(), status)
    assert "Current review failure" not in body
    assert "Latest persisted WO-B failure" not in body


def test_current_failure_reason_is_html_escaped() -> None:
    reason = 'WO_B_INVALID_<img src=x onerror="alert(1)">&\'DETAIL'
    body = render_intraday_operational_readiness(_snapshot(), _failure_status(reason=reason))
    assert escape(reason) in body
    assert reason not in body


def test_current_failure_get_is_inert_and_exposes_original_blocker(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls = []

    class FailedLoader:
        def current_requests(self, observed_at):  # type: ignore[no-untyped-def]
            calls.append(observed_at)
            raise ValueError("WO_B_DOMAIN_001_BINDING_UNAVAILABLE")

    store = WoBStore((tmp_path / "wo-b").resolve())
    service = IntradayOperationalReadinessRuntimeService(
        loader=FailedLoader(), store=store, clock=_boundary,
    )
    routes = IntradayBrowserRoutes(
        create_intraday_workstation(),
        operational_readiness=IntradayOperationalReadinessProjection(service),
    )
    import kronos.application.intraday_operational_readiness as application

    def forbidden(*args, **kwargs):  # type: ignore[no-untyped-def]
        pytest.fail("Browser failure projection must not publish or reconstruct")

    monkeypatch.setattr(application, "publish_operational_review", forbidden)
    monkeypatch.setattr(application, "reconstruct_operational_review", forbidden)
    monkeypatch.setattr(service, "rebuild", forbidden)
    before = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    body = _get(routes, WO_B_PRODUCT_ROUTE)
    after = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert "WO_B_DOMAIN_001_BINDING_UNAVAILABLE" in body
    assert "Current review failure" in body
    assert "Latest persisted WO-B failure" not in body
    assert len(calls) == 1
    assert before == after
    assert not store.root.exists()
    assert not routes.owns_post("/control/intraday-operational-review")
    assert "data-choice=" not in body
