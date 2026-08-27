from __future__ import annotations

from datetime import timedelta
from hashlib import sha256
from pathlib import Path

import pytest

from kronos.browser.intraday_routes import IntradayBrowserRoutes
from kronos.browser.product_routes import BrowserGetRequest
from kronos.intraday.probables import ProbableState
from tests.unit.browser.test_intraday_review import _Workstation
from tests.unit.browser.test_product_route_isolation import _snapshot
from tests.unit.intraday.test_historical_semantic import BOUNDARY
from tests.unit.intraday.test_probables import _member, _run
from tests.unit.intraday.test_review import _application
from tests.unit.intraday.test_wo11_full_pipeline_qualification import (
    _complete_current_cycle,
    _reconciliation,
)


def _tree_fingerprint(root: Path) -> str:
    digest = sha256()
    for item in sorted(path for path in root.rglob("*") if path.is_file()):
        digest.update(str(item.relative_to(root)).encode())
        digest.update(b"\0")
        digest.update(item.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


@pytest.mark.parametrize(
    ("answers", "statuses", "expected"),
    (
        (
            {},
            {},
            ("REVIEW COMPLETE", "ANALYTICALLY READY", "PROMOTED"),
        ),
        (
            {"Q2": "OPPOSING"},
            {},
            (
                "REVIEW COMPLETE",
                "NOT READY",
                "NOT PROMOTED",
                "CORE_VISUAL_1H_NOT_SUPPORTIVE",
                "BLOCKING",
            ),
        ),
        (
            {"Q9": "REJECTION_AGAINST_DIRECTION"},
            {},
            (
                "REVIEW REQUIRED",
                "NOT READY",
                "NOT PROMOTED",
                "LOCAL_REJECTION_AGAINST_DIRECTION",
            ),
        ),
        (
            {},
            {"Q2": "UNAVAILABLE"},
            (
                "REVIEW INCOMPLETE",
                "NOT READY",
                "NOT PROMOTED",
                "CORE_VISUAL_EVIDENCE_INCOMPLETE",
            ),
        ),
        (
            {"Q3": "MATERIAL_OVERLAP"},
            {},
            (
                "REVIEW COMPLETE",
                "ANALYTICALLY READY",
                "PROMOTED",
                "ONE_HOUR_MATERIAL_OVERLAP",
                "ADVERSE_NON_BLOCKING",
            ),
        ),
        (
            {"Q7": "PRESENT", "Q8": "VISIBLY_EXTENDED"},
            {},
            (
                "REVIEW COMPLETE",
                "ANALYTICALLY READY",
                "PROMOTED",
                "INFORMATIONAL",
                "VISIBLY EXTENDED",
            ),
        ),
    ),
)
def test_wo11_browser_projects_each_analytical_state_without_side_effects(
    tmp_path: Path,
    answers: dict[str, str],
    statuses: dict[str, str],
    expected: tuple[str, ...],
) -> None:
    run = _run((_member("WIPRO"),))
    current = [run]
    review = _application(tmp_path, current)
    reconciliation = _reconciliation(tmp_path, current, review)
    _complete_current_cycle(
        review,
        reconciliation,
        run.results[0],
        chart_red=111,
        answers=answers,
        statuses=statuses,
    )
    routes = IntradayBrowserRoutes(
        _Workstation(), review=review, reconciliation=reconciliation
    )
    before_review = _tree_fingerprint(review.store.root)
    before_reconciliation = _tree_fingerprint(reconciliation.store.root)
    before_snapshot = reconciliation.snapshot()

    response = routes.handle_get(BrowserGetRequest("/intraday/review", {}), _snapshot)

    assert response is not None and response.status.value == 200
    for text in expected:
        assert text in response.body
    assert "WIPRO" in response.body and "LONG" in response.body
    assert "NO ENTRY, TRADE, RISK OR BROKER AUTHORITY" in response.body
    assert "ENTRY PRICE" not in response.body.upper()
    assert "STOP PRICE" not in response.body.upper()
    assert "TARGET PRICE" not in response.body.upper()
    assert _tree_fingerprint(review.store.root) == before_review
    assert _tree_fingerprint(reconciliation.store.root) == before_reconciliation
    after_snapshot = reconciliation.snapshot()
    assert after_snapshot == before_snapshot
    assert (
        after_snapshot.provider_calls
        == after_snapshot.discovery_operations
        == after_snapshot.probables_operations
        == after_snapshot.chart_analyst_calls
        == after_snapshot.answer_imports
        == 0
    )


def test_wo11_browser_current_view_never_resurrects_historical_promotion(
    tmp_path: Path,
) -> None:
    run_a = _run((_member("WIPRO"),))
    current = [run_a]
    review = _application(tmp_path, current)
    reconciliation = _reconciliation(tmp_path, current, review)
    *_, historical = _complete_current_cycle(
        review,
        reconciliation,
        run_a.results[0],
        chart_red=112,
    )

    boundary_b = BOUNDARY + timedelta(minutes=5)
    run_b = _run(
        (_member("WIPRO", boundary=boundary_b, narrow=False),),
        boundary=boundary_b,
    )
    current[0] = run_b
    assert run_b.results[0].state is ProbableState.NOT_ADMITTED
    routes = IntradayBrowserRoutes(
        _Workstation(), review=review, reconciliation=reconciliation
    )
    response = routes.handle_get(BrowserGetRequest("/intraday/review", {}), _snapshot)

    assert response is not None and response.status.value == 200
    assert "Zero current Review candidates" in response.body
    assert historical.run_identity not in response.body
    assert historical.promotion.promotion_identity not in response.body
    assert reconciliation.store.load_run(historical.run_identity) == historical


def test_wo11_review_controls_remain_responsive_and_candidate_bound(
    tmp_path: Path,
) -> None:
    run = _run((_member("WIPRO"), _member("LICI")))
    current = [run]
    review = _application(tmp_path, current)
    reconciliation = _reconciliation(tmp_path, current, review)
    for candidate in review.snapshot().candidates:
        review.start_review(candidate.probable_result_identity)
    routes = IntradayBrowserRoutes(
        _Workstation(), review=review, reconciliation=reconciliation
    )
    response = routes.handle_get(BrowserGetRequest("/intraday/review", {}), _snapshot)

    assert response is not None and response.status.value == 200
    assert "@media(max-width:760px)" in response.body
    assert ".intraday-review-list{grid-template-columns:1fr}" in response.body
    assert ".intraday-review-toolbar{align-items:stretch;flex-direction:column}" in response.body
    assert response.body.count('class="intraday-drop" role="button" tabindex="0"') == 2
    for candidate in review.snapshot().candidates:
        assert candidate.cycle_identity is not None
        assert response.body.count(
            "/intraday/review/chart?cycle=" + candidate.cycle_identity
        ) == 1
