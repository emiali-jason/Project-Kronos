from __future__ import annotations

from kronos.browser.intraday_views import render_intraday_wo16
from kronos.browser.intraday_wo16_control import operation_document
from tests.unit.browser.test_intraday_wo16_control import _control, _post
from tests.unit.browser.test_product_route_isolation import _snapshot


def test_empty_page_is_read_only_and_responsive(tmp_path) -> None:
    control, _, _ = _control(tmp_path)

    page = render_intraday_wo16(_snapshot(), control.status_document())

    assert "WO-16 SPONSOR DECISION" in page
    assert "NOT_YET_RUN" in page
    assert "PAPER · LIVE · IGNORE" in page
    assert "NO POSITION, FILL, QUANTITY, EXECUTION OR BROKER AUTHORITY" in page
    assert 'href="/intraday/wo16"' in page
    assert 'action="/control/intraday-wo16"' not in page
    assert "data-choice=\"PAPER\"" not in page
    assert "@media(max-width:760px)" in page


def test_loaded_page_separates_all_governed_evidence_and_history(tmp_path) -> None:
    control, _, request = _control(tmp_path)
    assert _post(control, operation_document(request)).status.value == 200

    page = render_intraday_wo16(_snapshot(), control.status_document())

    for expected in (
        request.wo13_trade_plan.canonical_subject_identity,
        request.wo13_trade_plan.trade_plan_identity,
        request.wo14_observation.observation_identity,
        request.wo15_timing_handoff.handoff_identity,
        request.domain_008_session_fact.schedule.session_id,
        "WO-13 Trade Plan",
        "WO-14 Risk Observation — ADVISORY ONLY",
        "WO-15 Timing Handoff",
        "WO-16 Sponsor Decision",
        "Lifecycle Admission",
        "Immutable Decision History",
        "PENDING_POSITION_EVIDENCE",
        "Broker order placed",
        "Realised R",
        "UNAVAILABLE",
    ):
        assert expected in page
    assert "RISK APPROVED" not in page
    assert "RISK REJECTED" not in page
    assert "place_order" not in page


def test_mcx_and_latest_failure_are_distinct_projections(tmp_path) -> None:
    control, _, request = _control(tmp_path, mcx=True)
    assert _post(control, operation_document(request)).status.value == 200
    bad = operation_document(request)
    bad["request"]["choice"] = "LIVE"
    _post(control, bad)

    page = render_intraday_wo16(_snapshot(), control.status_document())

    assert request.wo13_trade_plan.actual_contract_identity in page
    assert request.wo13_source_handoff.roll_lineage_identity in page
    assert "Last Operation Failure" in page
    assert "WO16_REQUEST_INVALID" in page
    assert "Immutable Decision History" in page


def test_corrupt_restoration_is_sanitized_and_inert(tmp_path) -> None:
    control, store, request = _control(tmp_path)
    assert _post(control, operation_document(request)).status.value == 200
    alias = next((store.root / "current").glob("CURRENT-*.json"))
    alias.write_text("{}", encoding="utf-8")
    restarted = type(control)(
        control.application,
        control._restoration_service,  # noqa: SLF001
        wo13_store=control._wo13_store,  # noqa: SLF001
        wo14_store=control._wo14_store,  # noqa: SLF001
        wo15_store=control._wo15_store,  # noqa: SLF001
    )

    page = render_intraday_wo16(_snapshot(), restarted.status_document())

    assert "CORRUPT" in page
    assert "WO16_RESTORATION_FAILED" in page
    assert str(tmp_path) not in page
