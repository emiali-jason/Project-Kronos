from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from kronos.browser.intraday_views import _probable_v2_card
from kronos.intraday.completed_evidence import IntradayAnalysisPhase
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.nifty_relative_context import NiftyRelationship
from kronos.intraday.probables import ProbableState
from kronos.intraday.probables_v2 import ProbableReasonV2


def test_browser_projects_v2_phase_lineage_nifty_and_bounded_result() -> None:
    result = SimpleNamespace(
        canonical_subject_identity="NSE-EQ-RELIANCE",
        methodology_version="2.0.0",
        phase=IntradayAnalysisPhase.OPENING,
        analysis_boundary=datetime(
            2026, 8, 28, 10, 15, tzinfo=ZoneInfo("Asia/Kolkata")
        ),
        nifty_relationship=NiftyRelationship.SUPPORTING,
        state=ProbableState.LONG_PROBABLE,
        direction=SemanticDirection.LONG,
        reasons=(ProbableReasonV2.V2_CONDITIONS_SATISFIED,),
    )
    html = _probable_v2_card(result, "RELIANCE")
    assert "OPENING" in html
    assert "PRIOR-SESSION CONTEXT" in html
    assert "SUPPORTING" in html
    assert "Long Probable" in html
    assert "V2 Conditions Satisfied" in html
