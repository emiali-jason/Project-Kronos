from datetime import UTC, date, datetime
from threading import Thread

from kronos.application.swing_mcx_supporting_context import (
    McxContextFamilyStatus, McxContextSlotStatus, McxSupportingContextSnapshot,
)
from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.browser.server import create_browser_server
from kronos.browser.views import _mcx_context_details, _mcx_context_strip
from kronos.swing.v1.mcx_supporting_context import (
    ContextAvailability, McxContextFamily, McxContextSlot,
)
from tests.unit.application.test_swing_opportunities import _Provider, _ready
from tests.unit.browser.test_browser_server import _request
from tests.unit.swing.v1.test_mcx_supporting_context import (
    PNG, _answer, _payload, _transport,
)


def _snapshot() -> McxSupportingContextSnapshot:
    family = tuple(McxContextFamilyStatus(item, ContextAvailability.NOT_PROVIDED, None, None, False) for item in McxContextFamily)
    return McxSupportingContextSnapshot(date(2026, 8, 24), True, tuple(McxContextSlotStatus(slot, family, None, None) for slot in McxContextSlot))


def test_review_uses_one_thin_supporting_only_strip_and_four_image_bindings() -> None:
    html = _mcx_context_strip(_snapshot())
    assert html.count('class="mcx-context-strip"') == 1
    assert "MCX CONTEXT · SUPPORTING ONLY" in html
    assert html.count("CREATE PDF") == 2
    assert html.count("UPLOAD ANSWER") == 2
    assert html.count('class="mcx-context-file"') == 4
    assert "TAILWIND" not in html and "HEADWIND" not in html


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
        for family in ("METALS", "ENERGY"):
            status, response, _ = _request(
                server, "POST",
                f"/swing/mcx-context/image?slot=MORNING&family={family}",
                headers=headers, body=PNG,
            )
            assert status == 303 and response["Location"] == "/swing/v1-review"
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
