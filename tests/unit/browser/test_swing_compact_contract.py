"""Accepted SW-UX-02 compact navigation and preserved warning contract.

Synthetic retained source fixtures only. No model, Provider or production call.
The contract and exact owner approval are retained in the work-order evidence.
"""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

import pytest

from kronos.browser.views import render_opportunities, _native_opportunity_card
from kronos.browser.swing_v3_presentation import present_visual_v3_review
from kronos.application.swing_refresh_reminder import K5RefreshReminderStore, SwingK5RefreshReminderWorkflow
from tests.unit.application.test_swing_opportunities import _ready
from tests.unit.browser.test_browser_native_review import _evidence_run, _run_with_probables
from tests.unit.swing.v1.test_kr370_step31_handoff import _completed


@pytest.mark.parametrize("market", ["NSE", "MCX"])
@pytest.mark.parametrize("current", [True, False])
def test_compact_market_navigation_uses_only_current_exact_focus(market, current):
    if market == "NSE":
        facts, run, probable = _evidence_run()
    else:
        facts, run = _run_with_probables("GOLDM")
        probable = next(row for row in run.assessments if row.status.value == "PROBABLE")
    requirement = "b" * 64 if market == "NSE" else "c" * 64
    projection = dict(rows=(dict(instrument=probable.canonical_instrument, market=market,
        eligible=True, run_identity=run.run_identity, assessment_sha256=probable.result_sha256,
        requirement_sha256=requirement, direction=probable.direction.value, complete=False,
        question_ready=False, error=None, evidence="MISSING", expected={"candidate": {}}),),
        packages=(), error=None, workspace=dict(run_identity=run.run_identity if current else "SWING-RUN-" + "F" * 32,
            manifest="a" * 64, analysis_time=facts.observed_at, state="CURRENT", population=1,
            eligible=1, excluded=0, nse=int(market == "NSE"), mcx=int(market == "MCX")))
    before = deepcopy(projection)
    page = render_opportunities(_ready(), run, native_intake=projection)
    route = "/swing/" + market.lower() + "-review"
    assert probable.canonical_instrument in page and probable.direction.value in page
    assert ">VIEW " + market + " REVIEW</a>" in page
    if current:
        focus = (route + "?run=" + run.run_identity + "&candidate=" + requirement
            + ("#nse-research-" if market == "NSE" else "#review-candidate-") + requirement)
        assert 'href="' + escape(focus, quote=True) + '"' in page
        assert 'Currentness</span><strong>BINDING CURRENT' in page
    else:
        assert 'href="' + route + '">VIEW ' + market + ' REVIEW' in page
        assert "candidate=" not in page and "REVIEW_BINDING_STALE" in page
        assert "SWING-RUN-" + "F" * 32 not in page
    for forbidden in ('<div class="swing-timeframe-grid">', '<details class="swing-opportunity-details">',
                      'data-upload-url=', 'name="answer_pdf"', 'CREATE ALL NSE REVIEW PDF', 'CREATE ALL MCX REVIEW PDF'):
        assert forbidden not in page
    assert projection == before


@pytest.mark.parametrize("fault", ["none", "run", "assessment", "instrument"])
def test_compact_k5_warning_is_exact_source_bound_and_does_not_schedule(tmp_path, fault):
    completed = _completed(tmp_path, extended=True)
    calls = []
    reminder = SwingK5RefreshReminderWorkflow(K5RefreshReminderStore(tmp_path / "reminders"),
        clock=lambda: datetime(2026, 8, 14, 16, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
        scheduler=lambda delay, operation: calls.append((delay, operation)))
    reminder.synchronize(completed.requirement.native_run_identity, (completed.promotion,),
        {completed.requirement.canonical_instrument: "NSE"})
    presentation = present_visual_v3_review(completed)
    if fault == "run": presentation = replace(presentation, run_identity="SWING-RUN-" + "F" * 32)
    elif fault == "assessment": presentation = replace(presentation, native_assessment_sha256="f" * 64)
    elif fault == "instrument": presentation = replace(presentation, canonical_instrument="FOREIGN")
    _, run, probable = _evidence_run()
    retained = reminder.snapshot(); scheduled = tuple(calls)
    files = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    page = render_opportunities(_ready(), run, visual_v3=(presentation,), refresh_reminders=retained)
    warning = "REFRESH ANALYSIS AFTER NEXT COMPLETED 1H"
    if fault == "none":
        assert warning in page and "REMINDER SET · 17 AUG 10:15 IST" in page
        assert '<div class="wo07-card-warning" role="status">' in page
        # Detailed evidence remains accessible through the retained full
        # renderer while the main dashboard keeps only the warning summary.
        full = _native_opportunity_card(probable, None, visual_v3=(presentation,), refresh_reminders=retained)
        assert warning in full and "1 CRITERION REMAINING" in full
        assert "Waiting for: Extension" in full
    else:
        assert warning not in page and "REMINDER SET" not in page
    assert "WATCHING" not in page and "Next exact condition:" not in page
    assert "1 CRITERION REMAINING" not in page and "Waiting for: Extension" not in page
    assert 'action="/swing/trade-window/construct"' not in page
    assert tuple(calls) == scheduled and reminder.snapshot() == retained
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == files


def test_compact_k5_warning_does_not_invent_a_missing_reminder(tmp_path):
    completed = _completed(tmp_path, extended=True)
    _, run, _ = _evidence_run()
    page = render_opportunities(_ready(), run, visual_v3=(present_visual_v3_review(completed),))
    assert "REFRESH ANALYSIS AFTER NEXT COMPLETED 1H" in page
    assert "REMINDER SET" not in page and "REMINDER SENT" not in page and "WATCHING" not in page


@pytest.mark.parametrize("warning", ["unavailable", "no_setup"])
@pytest.mark.parametrize("fault", ["none", "run", "assessment", "instrument"])
def test_compact_required_status_warnings_remain_exactly_source_bound(tmp_path, warning, fault):
    from tests.unit.browser.test_swing_v3_sponsor_presentation import _sponsor_promotion

    completed = _completed(tmp_path, extended=True)
    promotion = (_sponsor_promotion("NO SETUP", unavailable="Mandatory K5 Evidence Unavailable")
        if warning == "unavailable" else _sponsor_promotion("NO SETUP", hard_gate="V3 1 1H Messy Choppy"))
    presentation = replace(present_visual_v3_review(completed),
        sponsor_status=promotion.classification, kr370=promotion)
    if fault == "run": presentation = replace(presentation, run_identity="SWING-RUN-" + "F" * 32)
    elif fault == "assessment": presentation = replace(presentation, native_assessment_sha256="f" * 64)
    elif fault == "instrument": presentation = replace(presentation, canonical_instrument="FOREIGN")
    _, run, _ = _evidence_run()
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    page = render_opportunities(_ready(), run, visual_v3=(presentation,))
    message = ("Required evidence is unavailable" if warning == "unavailable"
        else "Messy/choppy 1H price action")
    if fault == "none":
        assert message in page and '<div class="wo07-card-warning" role="status">' in page
        assert ('NOT EVALUABLE</span>' if warning == "unavailable" else 'NO SETUP</span>') in page
    else:
        assert message not in page
    assert "V3 1 1H Messy Choppy" not in page and "Mandatory K5 Evidence Unavailable" not in page
    assert 'action="/swing/trade-window/construct"' not in page
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before
