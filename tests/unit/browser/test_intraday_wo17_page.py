from __future__ import annotations

from kronos.browser.intraday_views import render_intraday_wo17
from kronos.browser.intraday_wo17_control import operation_document
from tests.unit.browser.test_intraday_wo17_control import _control, _post
from tests.unit.browser.test_product_route_isolation import _snapshot


def test_empty_wo17_page_is_inert_and_responsive(tmp_path) -> None:
    control, _, _ = _control(tmp_path)

    page = render_intraday_wo17(_snapshot(), control.status_document())

    assert "FACTUAL POSITION EVIDENCE AND READ-ONLY MONITORING ONLY" in page
    assert "NOT_YET_RUN" in page
    assert "NO BROKER ORDER, BROKER FILL, QUANTITY, FEES" in page
    assert 'href="/intraday/wo17"' in page
    assert 'action="/control/intraday-wo17"' not in page
    assert "@media(max-width:760px)" in page


def test_loaded_page_projects_upstream_position_lineage_and_no_economics(tmp_path) -> None:
    control, _, request = _control(tmp_path)
    assert _post(control, operation_document(request)).status.value == 200

    page = render_intraday_wo17(_snapshot(), control.status_document())

    lineage = request.snapshot.lineage
    for expected in (
        lineage.canonical_subject_identity,
        lineage.wo13_trade_plan_identity,
        lineage.wo14_observation_identity,
        lineage.wo15_handoff_identity,
        lineage.wo16_decision_identity,
        lineage.session_identity,
        "WO-13 Trade Plan",
        "WO-14 Advisory Risk Observation",
        "WO-15 Timing Handoff",
        "WO-16 Decision and Admission",
        "Position Evidence",
        "Lifecycle Observation",
        "Immutable Lifecycle History",
        "UNAVAILABLE",
    ):
        assert expected in page
    assert "Notifications delivered</dt><dd>NO" in page
    assert "Broker order</dt><dd>NONE" in page
    assert "place_order" not in page
