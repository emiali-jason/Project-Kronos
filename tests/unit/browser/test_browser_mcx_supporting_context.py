from datetime import UTC, date, datetime
from pathlib import Path
from threading import Thread

from kronos.application.swing_mcx_supporting_context import (
    McxContextFailureStatus, McxContextFamilyStatus, McxContextSlotStatus,
    McxSupportingContextSnapshot,
)
from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.browser.server import create_browser_server
from kronos.browser.views import _mcx_context_details, _mcx_context_strip
from kronos.swing.v1.mcx_supporting_context import (
    ContextAvailability, McxContextFamily, McxContextSlot,
)
from tests.unit.application.test_swing_opportunities import _Provider, _ready
from tests.unit.browser.test_browser_server import _request, _request_bytes
from tests.unit.swing.v1.test_mcx_supporting_context import (
    PNG, _answer, _payload, _transport,
)


def _snapshot() -> McxSupportingContextSnapshot:
    family = tuple(McxContextFamilyStatus(item, ContextAvailability.NOT_PROVIDED, None, None, False) for item in McxContextFamily)
    return McxSupportingContextSnapshot(date(2026, 8, 24), True, tuple(McxContextSlotStatus(slot, family, None, None) for slot in McxContextSlot))


def test_review_uses_compact_supporting_only_strip_and_four_paste_targets() -> None:
    html = _mcx_context_strip(_snapshot())
    assert html.count('class="mcx-context-strip"') == 1
    assert "MCX CONTEXT · SUPPORTING ONLY" in html
    assert html.count("CREATE PDF") == 2
    assert html.count("UPLOAD ANSWER") == 2
    assert html.count('class="chart-paste-target"') == 4
    assert html.count('class="chart-file"') == 4
    assert html.count("Click, then paste") == 4
    assert html.count("METALS CONTEXT") == 2
    assert html.count("ENERGY CONTEXT") == 2
    assert "mcx-context-file" not in html
    assert "TAILWIND" not in html and "HEADWIND" not in html


def test_received_image_renders_preview_replace_remove_and_secondary_file_fallback() -> None:
    digest = "a" * 64
    families = tuple(
        McxContextFamilyStatus(
            family, ContextAvailability.NOT_PROVIDED, None, None, True, digest,
        )
        for family in McxContextFamily
    )
    snapshot = McxSupportingContextSnapshot(
        date(2026, 8, 24), True,
        tuple(
            McxContextSlotStatus(slot, families, None, None)
            for slot in McxContextSlot
        ),
    )
    html = _mcx_context_strip(snapshot)
    assert html.count("Image received") == 4
    assert html.count('class="replace-chart"') == 4
    assert html.count(">Remove</button>") == 4
    assert html.count("/swing/mcx-context/image-preview?") == 4
    assert html.count("Choose File") == 4


def test_panel_failure_renders_bounded_sponsor_safe_diagnostic() -> None:
    families = tuple(
        McxContextFamilyStatus(
            family, ContextAvailability.NOT_PROVIDED, None, None, False,
        )
        for family in McxContextFamily
    )
    failure = McxContextFailureStatus(
        "MCX_CONTEXT_PANEL_INVALID_INCOMPLETE",
        McxContextFamily.METALS,
        "M1",
        "IDENTITY",
        "US Dollar Index Futures / DXY",
        "Gold Futures",
    )
    snapshot = McxSupportingContextSnapshot(
        date(2026, 8, 24), True,
        (
            McxContextSlotStatus(
                McxContextSlot.MORNING, families, None, failure,
            ),
            McxContextSlotStatus(
                McxContextSlot.EVENING, families, None, None,
            ),
        ),
    )
    html = _mcx_context_strip(snapshot)
    assert "MCX CONTEXT INVALID" in html
    assert "METALS · M1 · IDENTITY MISMATCH" in html
    assert "Expected: US Dollar Index Futures / DXY" in html
    assert "Observed: Gold Futures" in html
    assert "sha256" not in html.lower()
    assert "/Users/" not in html


def test_analysis_details_are_absent_for_nse_and_fail_closed_for_mcx() -> None:
    assert _mcx_context_details("SAIL", None) == ""
    html = _mcx_context_details("GOLDM", None)
    assert "NOT AVAILABLE AT ASSESSMENT TIME" in html
    assert "NO KR-370 CONSEQUENCE" in html


def test_review_routes_stage_both_images_create_pack_and_import_answer(tmp_path) -> None:
    workflow, transport, store = _transport(tmp_path)
    server = create_browser_server(
        SwingOpportunitiesApplication(_Provider, initial_snapshot=_ready()),
        port=0,
        mcx_supporting_context=workflow,
    )
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    authority = f"127.0.0.1:{server.server_port}"
    headers = {
        "Host": authority, "Origin": f"http://{authority}",
        "Referer": f"http://{authority}/swing/v1-review",
        "Content-Type": "image/png",
    }
    try:
        status, _, body = _request(server, "GET", "/swing/v1-review")
        assert status == 200 and "MCX CONTEXT · SUPPORTING ONLY" in body
        assert body.count("const acceptedCharts=") == 1
        assert body.count("mcx-context-morning-metals") >= 1
        for family in ("METALS", "ENERGY"):
            status, response, _ = _request(
                server, "POST",
                f"/swing/mcx-context/image?slot=MORNING&family={family}",
                headers=headers, body=PNG,
            )
            assert status == 303 and response["Location"] == "/swing/v1-review"
        metals = transport.store.current_image(
            date(2026, 8, 24), McxContextSlot.MORNING,
            McxContextFamily.METALS,
        )
        assert metals is not None
        preview = (
            "/swing/mcx-context/image-preview?slot=MORNING&family=METALS&sha256="
            + metals.image_sha256
        )
        status, response, body = _request_bytes(server, "GET", preview)
        assert status == 200 and response["Content-Type"] == "image/png"
        assert body == PNG
        empty_headers = dict(headers); empty_headers["Content-Type"] = "application/x-www-form-urlencoded"
        status, _, _ = _request(
            server, "POST", "/swing/mcx-context/question-pack?slot=MORNING",
            headers=empty_headers, body=None,
        )
        assert status == 303
        pack = transport.store.current(date(2026, 8, 24), McxContextSlot.MORNING)
        assert pack is not None
        _answer(transport.configuration.answer_directory / pack.expected_answer_filename, _payload(pack))
        status, _, _ = _request(
            server, "POST", "/swing/mcx-context/answer?slot=MORNING",
            headers=empty_headers, body=None,
        )
        assert status == 303
        assert len(store.records(trading_date=date(2026, 8, 24))) == 2
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3)


def test_review_route_removes_only_the_bound_staged_image(tmp_path) -> None:
    workflow, transport, _ = _transport(tmp_path)
    workflow.stage_image(
        slot=McxContextSlot.MORNING,
        family=McxContextFamily.METALS,
        content_type="image/png",
        payload=PNG,
    )
    retained = transport.store.current_image(
        date(2026, 8, 24), McxContextSlot.MORNING,
        McxContextFamily.METALS,
    )
    assert retained is not None
    server = create_browser_server(
        SwingOpportunitiesApplication(_Provider, initial_snapshot=_ready()),
        port=0,
        mcx_supporting_context=workflow,
    )
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    authority = f"127.0.0.1:{server.server_port}"
    headers = {
        "Host": authority,
        "Origin": f"http://{authority}",
        "Referer": f"http://{authority}/swing/v1-review",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    try:
        status, response, _ = _request(
            server, "POST",
            "/swing/mcx-context/image/remove?slot=MORNING&family=METALS",
            headers=headers,
        )
        assert status == 303 and response["Location"] == "/swing/v1-review"
        assert transport.store.current_image(
            date(2026, 8, 24), McxContextSlot.MORNING,
            McxContextFamily.METALS,
        ) is None
        assert Path(retained.path).read_bytes() == PNG
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3)
