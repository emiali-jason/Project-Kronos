from __future__ import annotations

from pathlib import Path

from kronos.application.intraday_wo15 import IntradayWo15RestorationService
from kronos.browser.intraday_views import render_intraday_wo15
from kronos.browser.intraday_wo15_control import IntradayWo15OperationalControl
from tests.unit.browser.test_intraday_wo15_control import _control
from tests.unit.browser.test_product_route_isolation import _snapshot


def _base_status(state: str) -> dict[str, object]:
    return {
        "control_identity": "KRONOS-INTRADAY-WO15-SPONSOR-CONTROL-V1",
        "control_version": "1.0.0",
        "runtime_loaded": True,
        "restoration_state": "LOADED",
        "operation_state": "IDLE",
        "current_timing": {
            "canonical_subject_identity": "NSE-EQ-RELIANCE",
            "market_family": "NSE_EQUITY",
            "direction": "LONG",
            "setup_family": "INTRADAY_PULLBACK_CONTINUATION",
            "instrument_identity": "KITE-NSE-RELIANCE",
            "actual_contract_identity": None,
            "roll_lineage_identity": None,
            "wo13_trade_plan_identity": "INTRADAY-WO13-PLAN-1",
            "wo13_trade_plan_integrity": "INTEGRITY-WO13-1",
            "entry_reference": "100",
            "session_identity": "NSE-20260902-REGULAR",
            "calendar_identity": "KRONOS-NSE-CALENDAR-V1",
            "calendar_version": "1.0.0",
            "timing_result": {
                "result_identity": "INTRADAY-WO15-RESULT-1",
                "prior_state": "TIMING_NOT_EVALUATED",
                "current_state": state,
                "cause": "FIRST_COMPLETED_5M_EVALUATION",
                "qualification_path": "PULLBACK_CONTINUATION_ACCEPTANCE",
                "observation_boundary": "2026-09-02T10:05:00+05:30",
                "timing_cycle_id": "INTRADAY-WO15-CYCLE-1",
                "cycle_evaluation": None,
                "policy": {
                    "policy_identity": "KRONOS-INTRADAY-WO15-ENTRY-TIMING-V1",
                    "policy_version": "1.0.0",
                    "policy_checksum": "d36386a98e2f1b78e5b70d0c27079c056951fd76a5b70ec2e9fa1bc1615a3f26",
                },
            },
            "telemetry": None,
            "timing_handoff": None,
            "operation": {
                "operation_identity": "INTRADAY-WO15-OPERATION-1",
                "outcome": "COMPLETED",
            },
            "current_pointer": {
                "pointer_identity": "CURRENT-INTRADAY-WO15-1",
                "supersession_lineage_identity": None,
            },
        },
        "timing_history": [],
        "last_operation": None,
        "latest_persisted_failure": None,
    }


def test_page_has_exact_timing_only_language_and_no_decision_controls() -> None:
    page = render_intraday_wo15(_snapshot(), _base_status("TIMING_WAITING"))

    assert "WO-15 COMPLETED-5M ENTRY TIMING" in page
    assert "TIMING EVIDENCE ONLY" in page
    assert "NO SPONSOR, PAPER, LIVE, POSITION, EXECUTION OR BROKER AUTHORITY" in page
    assert "WO-15C Advisory Research Telemetry" in page
    assert "RISK OBSERVATION ONLY" in page
    assert 'href="/intraday/wo15"' in page
    assert "@media(max-width:760px)" in page
    assert "PAPER/LIVE/IGNORE" not in page
    assert "RISK APPROVED" not in page
    assert "RISK REJECTED" not in page
    assert "place_order" not in page
    assert 'action="/control/intraday-wo15"' not in page
    assert "PAPER action" not in page and "LIVE action" not in page


def test_all_governed_visual_states_render_without_reclassification() -> None:
    for state in (
        "TIMING_NOT_EVALUATED",
        "TIMING_WAITING",
        "TIMING_QUALIFIED",
        "TIMING_FAILED",
        "TIMING_EXPIRED",
        "TIMING_UNAVAILABLE",
    ):
        page = render_intraday_wo15(_snapshot(), _base_status(state))
        assert state in page
        assert "FAVOURABLE" not in page
        assert "UNFAVOURABLE" not in page

    empty = render_intraday_wo15(_snapshot(), {
        **_base_status("TIMING_WAITING"),
        "restoration_state": "NOT_YET_RUN",
        "current_timing": None,
    })
    corrupt = render_intraday_wo15(_snapshot(), {
        **_base_status("TIMING_WAITING"),
        "restoration_state": "CORRUPT",
        "current_timing": None,
    })
    assert "NOT_YET_RUN" in empty
    assert "CORRUPT" in corrupt


def test_loaded_page_projects_telemetry_handoff_history_and_failure_separately() -> None:
    status = _base_status("TIMING_QUALIFIED")
    current = status["current_timing"]
    current["telemetry"] = {
        "completed_five_minute_close": "101",
        "directional_extension": "1",
        "absolute_extension": "1",
        "atr14": {"availability": "AVAILABLE", "value": "0.5"},
        "normalized_directional_extension": "2",
        "extension_severity": "UNCLASSIFIED",
        "maximum_favourable_extension": "1.5",
        "maximum_adverse_distance": "0.25",
        "maximum_extension_before_qualification": "1",
        "retest_occurred": False,
        "latency": {
            "plan_to_first_evaluation": "300",
            "first_evaluation_to_qualification": "600",
        },
        "research_references": [{"reference_identity": "RESEARCH-REF-1"}],
    }
    current["timing_handoff"] = {
        "handoff_identity": "INTRADAY-WO15-TIMING-HANDOFF-1",
        "handoff_integrity": "INTEGRITY-WO15-HANDOFF-1",
        "current_state": "TIMING_QUALIFIED",
        "predecessor_handoff_identity": None,
        "supersession_lineage_identity": None,
        "research_references": ["RESEARCH-REF-1"],
        "wo14_observation_identity": "INTRADAY-WO14-OBSERVATION-1",
        "sponsor_decision_authority": "NONE",
        "paper_authority": "NONE",
        "live_authority": "NONE",
        "position_authority": "NONE",
        "broker_authority": "NONE",
    }
    status["timing_history"] = [{
        "event": "TIMING_RESULT",
        "boundary": "2026-09-02T10:05:00+05:30",
        "evidence_identity": "INTRADAY-WO15-EVIDENCE-1",
        "timing_cycle_id": "INTRADAY-WO15-CYCLE-1",
    }]
    status["last_operation"] = {
        "outcome": "FAILED",
        "failure_stage": "APPLICATION",
        "failure_reason": "WO15_REQUEST_LINEAGE_MISMATCH",
    }

    page = render_intraday_wo15(_snapshot(), status)

    for expected in (
        "TIMING_QUALIFIED", "101", "UNCLASSIFIED", "RESEARCH-REF-1",
        "INTRADAY-WO15-TIMING-HANDOFF-1", "RISK OBSERVATION ONLY",
        "TIMING_RESULT", "WO15_REQUEST_LINEAGE_MISMATCH",
    ):
        assert expected in page
    assert "NSE-EQ-RELIANCE" in page


def test_real_persisted_page_uses_exact_mcx_contract_and_roll_lineage(tmp_path) -> None:
    control, _, _, request = _control(tmp_path, mcx=True)
    execution = control.application.execute(request)
    restarted = IntradayWo15OperationalControl(
        control.application,
        IntradayWo15RestorationService(store=control.application.store),
    )

    page = render_intraday_wo15(_snapshot(), restarted.status_document())

    assert execution.timing_result.result_identity in page
    assert request.admission.actual_contract_identity in page
    assert request.admission.roll_lineage_identity in page
    assert request.admission.wo13_trade_plan_identity in page
    assert "TIMING_QUALIFIED" in page


def test_corrupt_restoration_layout_exposes_sanitized_state(tmp_path) -> None:
    control, _, store, _ = _control(tmp_path)
    current = store.root / "current" / "CURRENT-INTRADAY-WO15-V1.json"
    current.parent.mkdir(parents=True)
    current.write_text("{}", encoding="utf-8")
    restarted = IntradayWo15OperationalControl(
        control.application,
        IntradayWo15RestorationService(store=store),
    )

    status = restarted.status_document()
    page = render_intraday_wo15(_snapshot(), status)

    assert status["restoration_state"] == "CORRUPT"
    assert status["failure_reason"] == "WO15_RESTORATION_FAILED"
    assert "CORRUPT" in page
    assert str(Path(tmp_path)) not in page
