"""Mandatory R3 usability checks using disposable, synthetic retained owners.

These exercise real GET dispatch and prepared evidence. They neither read live
market stores nor establish that a currently deployed page has fresh evidence.
"""
from dataclasses import replace
from threading import Thread

import pytest

from tests.unit.browser.test_browser_server import _request
from tests.unit.browser.test_swing_review_intake_binding import (
    native_intake, _inventory, _page_load_population, _page_load_server,
)


@pytest.mark.parametrize("native_intake", ["NSE"], indirect=True)
def test_missing_review_evidence_does_not_hide_current_native_opportunities(
    native_intake, tmp_path, monkeypatch,
):
    state, _, _ = _page_load_population(native_intake, tmp_path)
    server = _page_load_server(native_intake, state)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    before = _inventory(tmp_path)
    try:
        projection = native_intake._page_publication.page.projection
        assert projection["workspace"]["nse"] == 10
        assert projection["workspace"]["mcx"] == 2
        assert all(row["evidence"] == "MISSING" and not row["question_ready"]
                   for row in projection["rows"])
        monkeypatch.setattr(native_intake, "prepare_page_state",
            lambda: pytest.fail("GET attempted evidence reconstruction"))
        monkeypatch.setattr(native_intake.native_review, "refresh",
            lambda *a, **k: pytest.fail("GET attempted a new Review"))
        for route in ("/swing/opportunities", "/swing/nse-review", "/swing/mcx-review"):
            status, _, body = _request(server, "GET", route)
            assert status == 200
            assert "Swing page unavailable" not in body
            if route == "/swing/opportunities":
                for name in ("DRREDDY", "GOLDM", "CRUDEOIL"):
                    assert name in body
                assert "VIEW NSE REVIEW" in body and "VIEW MCX REVIEW" in body
            elif route == "/swing/nse-review":
                assert "DRREDDY" in body
                assert 'focus=GOLDM' not in body
            else:
                assert "GOLDM" in body and "CRUDEOIL" in body
                assert 'focus=DRREDDY' not in body
        assert _inventory(tmp_path) == before
    finally:
        server.shutdown(); thread.join(5); server.server_close()
        assert not thread.is_alive()


@pytest.mark.parametrize("native_intake", ["NSE"], indirect=True)
@pytest.mark.parametrize("fault", ["publication", "run", "missing_native", "reconciliation"])
def test_genuinely_changed_authority_is_not_relabelled_as_current_native(
    native_intake, tmp_path, fault,
):
    state, _, _ = _page_load_population(native_intake, tmp_path)
    server = _page_load_server(native_intake, state)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    before = _inventory(tmp_path)
    try:
        if fault == "publication":
            state["control"]["current_manifest"]["sha256"] = "b" * 64
        elif fault == "run":
            state["facts"] = replace(state["facts"], run_identity="SWING-RUN-" + "E" * 32)
        elif fault == "missing_native":
            state["native"] = None
        else:
            # A broad reconciliation failure is not a proven admission.
            native_intake._page_publication = replace(
                native_intake._page_publication, reconciliation_failure=True)
        for route in ("/swing/opportunities", "/swing/nse-review", "/swing/mcx-review"):
            status, _, body = _request(server, "GET", route)
            assert status == 409
            assert body == "Swing page unavailable. Reason: REVIEW_BINDING_STALE"
            assert "BINDING CURRENT" not in body
            assert "Refresh Local Analysis" not in body
            assert "New analysis in progress" not in body
        assert _inventory(tmp_path) == before
    finally:
        server.shutdown(); thread.join(5); server.server_close()
        assert not thread.is_alive()


@pytest.mark.parametrize("native_intake", ["NSE"], indirect=True)
def test_absent_preparation_is_truthful_and_explicit_fresh_preparation_recovers(
    native_intake, tmp_path, monkeypatch,
):
    state, _, _ = _page_load_population(native_intake, tmp_path)
    server = _page_load_server(native_intake, state)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        native_intake._page_publication = replace(native_intake._page_publication,
            page=None, failure="SWING_PAGE_PREPARATION_MISSING")
        before = _inventory(tmp_path)
        with monkeypatch.context() as scoped:
            scoped.setattr(native_intake, "prepare_page_state",
                lambda: pytest.fail("Unavailable GET attempted automatic repair"))
            status, _, body = _request(server, "GET", "/swing/opportunities")
        assert status == 409
        assert body == "Swing page unavailable. Reason: SWING_PAGE_PREPARATION_MISSING"
        assert _inventory(tmp_path) == before
        # A separate explicit owner preparation establishes current evidence.
        # No GET manufactures it and no historical Question/Answer is reused.
        assert native_intake.prepare_page_state()
        after_preparation = _inventory(tmp_path)
        status, _, body = _request(server, "GET", "/swing/opportunities")
        assert status == 200 and "VIEW NSE REVIEW" in body
        assert "Swing page unavailable" not in body
        assert _inventory(tmp_path) == after_preparation
    finally:
        server.shutdown(); thread.join(5); server.server_close()
        assert not thread.is_alive()
