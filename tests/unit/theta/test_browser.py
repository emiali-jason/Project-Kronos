import base64
import json
from urllib.parse import urlencode

from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.browser.product_routes import BrowserGetRequest, BrowserPostRequest, ProductBrowserRoutes
from kronos.browser.theta_routes import ThetaBrowserRoutes
from tests.unit.application.test_swing_opportunities import _Provider
from tests.unit.theta.test_workflow import accepted, chart, workflow


def snapshot():
    return SwingOpportunitiesApplication(_Provider).snapshot()


def test_summary_detail_escape_and_original_answer(workflow, request):
    identity, answer, raw = accepted(workflow)
    routes = ThetaBrowserRoutes(workflow)
    summary = routes.handle_get(BrowserGetRequest("/theta-earners", {}), snapshot)
    assert all(s in summary.body for s in ("GOLDM", "SILVERM", "COPPER", "CRUDEOIL", "NATURALGAS"))
    assert summary.body.count("Confidence: 78.00%") == 10
    detail = routes.handle_get(BrowserGetRequest("/theta-earners/detail", {"question": [identity], "subject": ["COPPER"]}), snapshot)
    assert "SYNTHETIC-MCX-COPPER" in detail.body
    assert "&lt;script&gt;never execute&lt;/script&gt;" in detail.body
    assert "<script>never execute</script>" not in detail.body
    assert "data:image/png;base64," in detail.body
    original = routes.handle_get(BrowserGetRequest("/theta-earners/answer", {"question": [identity]}), snapshot)
    assert original.body == raw
    from tests.unit.theta.conftest import qualification_output
    output = qualification_output(request)
    if output:
        (output / "synthetic-summary.html").write_text(summary.body)
        (output / "synthetic-detail.html").write_text(detail.body)


def test_missing_default_dependency_visible_not_synthetic_success(workflow):
    workflow.authority_provider = None
    routes = ThetaBrowserRoutes(workflow)
    request = BrowserPostRequest("/theta-earners/question", {}, "application/x-www-form-urlencoded",
                                 urlencode({"subject": "COPPER"}).encode())
    response = routes.handle_post(request, snapshot)
    assert response.status == 409 and "No targets have been guessed" in response.body
    assert 'NEW ANALYSIS' in response.body and 'No targets have been guessed' in response.body


def test_chart_post_and_route_isolation(workflow):
    routes = ThetaBrowserRoutes(workflow)
    payload = {"subject": "COPPER", "label": "new <chart>", "media_type": "image/png",
               "information_cutoff": "2026-10-11T10:00:00Z", "chart_base64": base64.b64encode(chart()).decode()}
    response = routes.handle_post(BrowserPostRequest("/theta-earners/chart", {}, "application/json", json.dumps(payload).encode()), snapshot)
    assert response.status == 200 and "TEC-" in response.body
    assert routes.handle_get(BrowserGetRequest("/swing/opportunities", {}), lambda: 1/0) is None
    assert not routes.owns_post("/provider/connect")
    registry = ProductBrowserRoutes((routes,))
    assert registry.dispatch_get(BrowserGetRequest("/theta-earners", {}), snapshot).status == 200


def test_download_and_bad_request_are_bounded(workflow):
    identity, _, _ = accepted(workflow)
    routes = ThetaBrowserRoutes(workflow)
    pdf = routes.handle_get(BrowserGetRequest("/theta-earners/question-pack", {"question": [identity], "kind": ["pdf"]}), snapshot)
    assert pdf.body.startswith(b"%PDF-") and pdf.content_type == "application/pdf"
    invalid = routes.handle_get(BrowserGetRequest("/theta-earners/detail", {"question": ["../../etc/passwd"], "subject": ["COPPER"]}), snapshot)
    assert invalid.status == 409
    assert routes.handle_post(BrowserPostRequest("/theta-earners/chart", {}, "application/json", b"{}"), snapshot).status == 409
