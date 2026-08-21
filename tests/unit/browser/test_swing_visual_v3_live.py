from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta, timezone
from enum import StrEnum
import json
from pathlib import Path
from threading import Thread

from pypdf import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import pytest

from kronos.application.swing_native_review import NativeReviewWorkflow
from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.application.swing_visual_v3 import SwingVisualV3ReviewCycle
from kronos.application.swing_visual_v3_live import SwingVisualV3LiveWorkflow
from kronos.application.swing_v1_review import SwingV1ReviewWorkflow
from kronos.browser.server import create_browser_server
from kronos.configuration.pdf_visual_review import PdfVisualReviewConfiguration
from kronos.swing.v1.evidence_store import LocalTradingViewEvidenceStore
from kronos.swing.v1.analytical_promotion import (
    KR370_PROMOTION_CONTRACT_ID,
)
from kronos.swing.v1.native_readiness_v3 import NativeLayer2ReadinessV3Store
from kronos.swing.v1.native_review import NativeReviewEvidenceStore
from kronos.swing.v1.pdf_visual_review import (
    BEGIN_GOVERNED_ANSWER_DATA,
    END_GOVERNED_ANSWER_DATA,
    PdfReviewTransportError,
)
from kronos.swing.v1.pdf_visual_review_v3_live import (
    VisualV3PdfRecordStore,
    VisualV3PdfReviewTransport,
    _complete_response_example,
    _pack_from_dict,
    _validate_answer,
)
from kronos.swing.v1.visual_evidence_v3 import (
    LocalVisualEvidenceV3Store,
    VISUAL_EVIDENCE_V3_ANSWER_SCHEMA,
    VISUAL_EVIDENCE_V3_LEGACY_ANSWER_SCHEMA,
    VISUAL_QUESTION_SET_V3_ID,
    VISUAL_QUESTION_SET_V3_LEGACY_VERSION,
    VISUAL_QUESTION_SET_V3_VERSION,
)
from tests.unit.application.test_swing_opportunities import _Provider, _ready
from tests.unit.browser.test_browser_server import _request as _browser_request
from tests.unit.swing.v1.test_native_review import _evidence_run
from tests.unit.swing.v1.test_pdf_visual_review import NOW, _workflow
from tests.unit.swing.v1.test_visual_evidence_v3 import _response


def _live(tmp_path: Path) -> tuple[NativeReviewWorkflow, object, SwingVisualV3LiveWorkflow]:
    native, _ = _workflow(tmp_path / "native")
    facts = _evidence_run()[0]
    cycle = SwingVisualV3ReviewCycle(
        LocalVisualEvidenceV3Store((tmp_path / "visual-v3").resolve()),
        NativeLayer2ReadinessV3Store((tmp_path / "readiness-v3").resolve()),
    )
    configuration = PdfVisualReviewConfiguration(
        tmp_path / "V3 QUESTIONS", tmp_path / "V3 ANSWERS"
    )
    live = SwingVisualV3LiveWorkflow(
        cycle,
        VisualV3PdfReviewTransport(
            configuration,
            VisualV3PdfRecordStore((tmp_path / "v3-pdf-records").resolve()),
            clock=lambda: NOW,
        ),
        clock=lambda: NOW,
    )
    return native, facts, live


def _payload(live: SwingVisualV3LiveWorkflow, native, facts, record):  # type: ignore[no-untyped-def]
    prepared, _ = live._prepare_for_record(  # noqa: SLF001 - exact live Pack proof
        native.snapshot(), facts, native.original_chart_bytes, record
    )
    candidates = []
    for requests in prepared:
        instrument = requests[0].requirement.canonical_instrument
        candidates.append({
            "canonical_instrument": instrument,
            "observed_chart_instrument": instrument,
            "chart_revision_sha256": requests[0].chart_revision_sha256,
            "responses": [_primitive(_response(request)) for request in requests],
        })
    return {
        "schema": VISUAL_EVIDENCE_V3_ANSWER_SCHEMA,
        "manifest": {
            "review_pack_id": record.review_pack_id,
            "native_run_identity": record.native_run_identity,
            "question_set_identity": VISUAL_QUESTION_SET_V3_ID,
            "question_set_version": VISUAL_QUESTION_SET_V3_VERSION,
            "answer_schema": VISUAL_EVIDENCE_V3_ANSWER_SCHEMA,
            "candidate_population": [
                {
                    "canonical_instrument": item.canonical_instrument,
                    "chart_revision_sha256": item.chart_revisions[0][1],
                }
                for item in record.candidate_packs
            ],
        },
        "candidates": candidates,
    }


def _answer_pdf(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = canvas.Canvas(str(path), pagesize=A4)
    y = A4[1] - 30
    document.setFont("Courier", 3.8)
    lines = [
        BEGIN_GOVERNED_ANSWER_DATA,
        *json.dumps(payload, indent=1, sort_keys=True).splitlines(),
        END_GOVERNED_ANSWER_DATA,
    ]
    for line in lines:
        if y < 24:
            document.showPage()
            document.setFont("Courier", 3.8)
            y = A4[1] - 30
        document.drawString(16, y, line)
        y -= 4.5
    document.save()


def _primitive(value: object) -> object:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "__dataclass_fields__"):
        return _primitive(asdict(value))
    if isinstance(value, dict):
        return {str(key): _primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_primitive(item) for item in value]
    return value


def test_new_live_cycle_generates_only_v3_pack_with_exact_machine_bindings(
    tmp_path: Path,
) -> None:
    native, facts, live = _live(tmp_path)
    record = live.generate(
        native.snapshot(), facts, native.original_chart_bytes
    )

    assert record.question_set_identity == VISUAL_QUESTION_SET_V3_ID
    assert record.question_set_version == VISUAL_QUESTION_SET_V3_VERSION
    assert record.answer_schema == VISUAL_EVIDENCE_V3_ANSWER_SCHEMA
    assert Path(record.question_path).is_file()
    assert native.snapshot().review_pack_record is None
    assert all(len(item.machine_fact_bindings) == 4 for item in record.candidate_packs)


def test_v3_question_pack_publishes_exact_complete_answer_contract(
    tmp_path: Path,
) -> None:
    native, facts, live = _live(tmp_path)
    record = live.generate(native.snapshot(), facts, native.original_chart_bytes)
    text = "\n".join(
        page.extract_text() or "" for page in PdfReader(record.question_path).pages
    )
    contract = text.split("Exact V3 Observation Contract", 1)[1]
    compact_contract = " ".join(contract.split())
    exact_questions = (
        "VISUAL_CHART_VALIDATION",
        "CPR_VISUAL_RELATIONSHIP",
        "VISUAL_SUPPORT_RESISTANCE_GAP",
        "GOVERNED_REFERENCE_VISUAL_CONTEXT",
        "PRICE_ACTION_QUALITY",
        "VISUAL_OBSTACLE_EVIDENCE",
        "MATURITY_AND_CHASE_CONTEXT",
        "PINE_VISIBLE_EVIDENCE",
        "VISUAL_COMPONENT_CLUSTERING",
        "VISUAL_FACTS_NOT_CAPTURED_BY_KRONOS",
    )

    positions = [contract.index(f'"{item}"') for item in exact_questions]
    assert positions == sorted(positions)
    assert '"qualitative_result_field": "finding"' in contract
    assert '"observation":' not in contract
    assert '"presence"' in contract
    assert all(item in contract for item in (
        "PRESENT", "NOT_PRESENT", "NOT_IDENTIFIABLE",
        "ABOVE", "INSIDE", "BELOW", "NOT_OBSERVABLE",
        "HOLD", "RECLAIM", "REJECTION", "BREAK", "NONE",
        "ABOVE_REFERENCE_RANGE", "INSIDE_REFERENCE_RANGE",
        "BELOW_REFERENCE_RANGE", "INTERACTING_WITH_REFERENCE_HIGH",
        "INTERACTING_WITH_REFERENCE_LOW",
        "CLUSTERED", "NOT_CLUSTERED", "PARTIAL_COMPONENT_IDENTITY",
        "STRUCTURAL_PIVOT", "OPERATIVE_ANCHOR", "RANGE_BOUNDARY",
        "BREAK_BOUNDARY",
    ))
    assert "CLUSTERED_REQUIRES_AT_LEAST_TWO_UNIQUE_COMPONENTS" in contract
    assert '"classification_field": "setup_quality"' in contract
    assert "Native direction:" in text
    assert all(item in contract for item in (
        "CLEAN_DIRECTIONAL", "HEALTHY_CONSOLIDATION", "HEALTHY_COMPRESSION",
        "ORDERLY_PULLBACK", "MESSY_CHOPPY", "CONFLICTING", "NOT_OBSERVABLE",
    ))
    assert "CLASSIFY_RELATIVE_TO_SUPPLIED_NATIVE_DIRECTION" in contract
    assert "VOLUME_IS_SUPPORTING_ONLY_NOT_CLASSIFICATION_AUTHORITY" in contract
    assert "point_price" in contract
    assert "zone_low/zone_high" in contract
    assert "When Q10 finding is NONE" in compact_contract
    assert "why_not_covered_elsewhere must be null" in compact_contract
    assert "never generic PDH/PDL" in compact_contract
    assert "never a numerical Confluence Zone" in compact_contract
    assert "must not provide or infer machine CP, BC, TC" in compact_contract
    assert (
        "must not provide, convert, round, or independently generate "
        "request_timestamp"
    ) in compact_contract
    assert "CPR_CONTEXT" not in contract
    assert "GOVERNED_REFERENCE_STRUCTURE_CONTEXT" not in contract
    assert "VISUAL_CONFLUENCE" not in contract


def test_published_complete_response_example_passes_actual_v3_answer_validator(
    tmp_path: Path,
) -> None:
    native, facts, live = _live(tmp_path)
    record = live.generate(native.snapshot(), facts, native.original_chart_bytes)
    prepared, _ = live._prepare_for_record(  # noqa: SLF001 - exact Pack proof
        native.snapshot(), facts, native.original_chart_bytes, record
    )
    payload = {
        "schema": VISUAL_EVIDENCE_V3_ANSWER_SCHEMA,
        "manifest": {
            "review_pack_id": record.review_pack_id,
            "native_run_identity": record.native_run_identity,
            "question_set_identity": VISUAL_QUESTION_SET_V3_ID,
            "question_set_version": VISUAL_QUESTION_SET_V3_VERSION,
            "answer_schema": VISUAL_EVIDENCE_V3_ANSWER_SCHEMA,
            "candidate_population": [
                {
                    "canonical_instrument": item.canonical_instrument,
                    "chart_revision_sha256": item.chart_revisions[0][1],
                }
                for item in record.candidate_packs
            ],
        },
        "candidates": [
            {
                "canonical_instrument": requests[0].requirement.canonical_instrument,
                "observed_chart_instrument": requests[0].requirement.canonical_instrument,
                "chart_revision_sha256": requests[0].chart_revision_sha256,
                "responses": [
                    _complete_response_example(request) for request in requests
                ],
            }
            for requests in prepared
        ],
    }

    assert all(
        "request_timestamp" not in response
        for candidate in payload["candidates"]
        for response in candidate["responses"]
    )

    validated = _validate_answer(record, prepared, payload)

    assert len(validated) == len(record.candidate_packs)
    assert all(len(item.responses) == 4 for item in validated)
    assert all(
        len(response.observations) == 10
        for item in validated for response in item.responses
    )


@pytest.mark.parametrize("mutation", ("missing", "unknown"))
def test_new_q5_setup_quality_fails_closed_when_missing_or_unknown(
    tmp_path: Path, mutation: str
) -> None:
    native, facts, live = _live(tmp_path)
    record = live.generate(native.snapshot(), facts, native.original_chart_bytes)
    prepared, _ = live._prepare_for_record(  # noqa: SLF001
        native.snapshot(), facts, native.original_chart_bytes, record
    )
    payload = _payload(live, native, facts, record)
    q5 = payload["candidates"][0]["responses"][0]["observations"][4]
    if mutation == "missing":
        del q5["setup_quality"]
    else:
        q5["setup_quality"] = "GOOD"

    with pytest.raises(PdfReviewTransportError, match="ANSWER_FORMAT_INVALID"):
        _validate_answer(record, prepared, payload)


def test_kronos_binds_exact_request_timestamp_without_changing_answer_evidence(
    tmp_path: Path,
) -> None:
    native, facts, live = _live(tmp_path)
    record = live.generate(native.snapshot(), facts, native.original_chart_bytes)
    prepared, _ = live._prepare_for_record(  # noqa: SLF001 - exact Pack proof
        native.snapshot(), facts, native.original_chart_bytes, record
    )
    governed_timestamp = datetime(
        2026, 8, 16, 15, 35, 30, 5_914, tzinfo=UTC
    )
    governed = tuple(
        tuple(replace(request, request_timestamp=governed_timestamp) for request in requests)
        for requests in prepared
    )
    analyst_timestamps = (
        governed_timestamp.astimezone(
            timezone(timedelta(hours=5, minutes=30))
        ).isoformat(),
        governed_timestamp.replace(microsecond=0).isoformat(),
        "2099-01-01T00:00:00+00:00",
    )

    for analyst_timestamp in analyst_timestamps:
        payload = _payload(live, native, facts, record)
        for candidate in payload["candidates"]:
            for response in candidate["responses"]:
                response["request_timestamp"] = analyst_timestamp
        observations_before = deepcopy([
            response["observations"]
            for candidate in payload["candidates"]
            for response in candidate["responses"]
        ])

        validated = _validate_answer(record, governed, payload)

        responses = [
            response
            for candidate in validated
            for response in candidate.responses
        ]
        assert all(
            response.request_timestamp == governed_timestamp
            for response in responses
        )
        assert [_primitive(response.observations) for response in responses] == (
            observations_before
        )


def test_timestamp_ownership_does_not_weaken_other_answer_bindings(
    tmp_path: Path,
) -> None:
    native, facts, live = _live(tmp_path)
    record = live.generate(native.snapshot(), facts, native.original_chart_bytes)
    prepared, _ = live._prepare_for_record(  # noqa: SLF001 - exact Pack proof
        native.snapshot(), facts, native.original_chart_bytes, record
    )
    cases = (
        (
            lambda value: value["manifest"].__setitem__(
                "native_run_identity", "SWING-RUN-" + "F" * 32
            ),
            "ANSWER_VERSION_MISMATCH",
        ),
        (
            lambda value: value["candidates"][0].__setitem__(
                "canonical_instrument", "SBIN"
            ),
            "CHART_IDENTITY_MISMATCH",
        ),
        (
            lambda value: value["candidates"][0]["responses"][0].__setitem__(
                "chart_revision_sha256", "0" * 64
            ),
            "ANSWER_VERSION_MISMATCH",
        ),
        (
            lambda value: value["candidates"][0]["responses"][0].__setitem__(
                "timeframe", "1D"
            ),
            "ANSWER_VERSION_MISMATCH",
        ),
    )

    for mutate, reason in cases:
        payload = _payload(live, native, facts, record)
        mutate(payload)
        with pytest.raises(PdfReviewTransportError, match=reason):
            _validate_answer(record, prepared, payload)


def test_v3_record_restores_historical_question_path_after_new_path_cutover(
    tmp_path: Path,
) -> None:
    native, facts, live = _live(tmp_path)
    record = live.generate(native.snapshot(), facts, native.original_chart_bytes)
    historical_path = Path(record.question_path)
    new_configuration = PdfVisualReviewConfiguration(
        tmp_path / "SWING" / "KRONOS QUESTIONS",
        tmp_path / "SWING" / "CHATGPT ANSWERS",
    )
    restored_transport = VisualV3PdfReviewTransport(
        new_configuration,
        VisualV3PdfRecordStore((tmp_path / "v3-pdf-records").resolve()),
        clock=lambda: NOW,
    )

    restored = restored_transport.record_store.load_current()

    assert restored == record
    assert Path(restored.question_path) == historical_path
    assert historical_path.is_file()
    assert not new_configuration.question_directory.exists()


def test_historical_v3_3_0_pack_restores_under_its_original_contract(
    tmp_path: Path,
) -> None:
    native, facts, live = _live(tmp_path)
    current = live.generate(native.snapshot(), facts, native.original_chart_bytes)
    candidates = tuple(
        replace(
            item,
            question_set_version=VISUAL_QUESTION_SET_V3_LEGACY_VERSION,
        )
        for item in current.candidate_packs
    )
    historical = replace(
        current,
        candidate_packs=candidates,
        question_set_version=VISUAL_QUESTION_SET_V3_LEGACY_VERSION,
        answer_schema=VISUAL_EVIDENCE_V3_LEGACY_ANSWER_SCHEMA,
    )

    restored = _pack_from_dict(_primitive(historical))
    prepared, _ = live._prepare_for_record(  # noqa: SLF001
        native.snapshot(), facts, native.original_chart_bytes, restored
    )

    assert restored == historical
    assert restored.question_set_version == "3.0"
    assert all(
        request.question_set_version == "3.0"
        for requests in prepared for request in requests
    )


def test_production_server_constructs_explicit_v3_lifecycle_when_not_injected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    native, facts, _ = _live(tmp_path)
    configuration = PdfVisualReviewConfiguration(
        tmp_path / "SERVER V3 QUESTIONS", tmp_path / "SERVER V3 ANSWERS"
    )
    monkeypatch.setattr(
        "kronos.browser.server.load_or_provision_pdf_visual_review_configuration",
        lambda: configuration,
    )
    run = _evidence_run()[1]
    application = SwingOpportunitiesApplication(
        _Provider,
        initial_snapshot=replace(
            _ready(), swing_analysis_run_identity=run.run_identity
        ),
    )
    application.restore_mtf_fact_snapshot(facts)
    application.restore_native_discovery_run(run)
    server = create_browser_server(
        application,
        port=0,
        v1_review=SwingV1ReviewWorkflow(
            LocalTradingViewEvidenceStore(tmp_path / "legacy")
        ),
        native_review=native,
    )
    try:
        assert type(server.visual_v3) is SwingVisualV3ReviewCycle
        assert type(server.visual_v3_live) is SwingVisualV3LiveWorkflow
        assert server.visual_v3_live.cycle is server.visual_v3
        assert server.native_review_version() == "V3"
    finally:
        server.server_close()


def test_v3_answer_persists_v3_evidence_and_readiness_without_v2_store(
    tmp_path: Path,
) -> None:
    native, facts, live = _live(tmp_path)
    record = live.generate(native.snapshot(), facts, native.original_chart_bytes)
    answer = live.transport.configuration.answer_directory / record.expected_answer_filename
    _answer_pdf(answer, _payload(live, native, facts, record))

    imports = live.upload(native.snapshot(), facts, native.original_chart_bytes)

    assert imports[-1].consumed
    assert len(live.cycle.completed_snapshot()) == len(record.candidate_packs)
    assert len(tuple((tmp_path / "visual-v3").rglob("*.json"))) == 4 * len(
        record.candidate_packs
    )
    assert len(tuple((tmp_path / "readiness-v3").rglob("*.json"))) == len(
        record.candidate_packs
    )
    completed = live.cycle.completed_snapshot()
    assert all(
        any(
            evidence.condition_identity == "KR_370_E03_EXTENSION"
            and evidence.timeframe.value == "1H"
            and len(evidence.source_evidence_ids) == 3
            for evidence in item.readiness.conditions.evidence
        )
        for item in completed
    )
    assert not tuple(native.evidence_root.rglob("*visual-v2*"))


def test_v2_answer_is_rejected_for_v3_pack_without_fallback(tmp_path: Path) -> None:
    native, facts, live = _live(tmp_path)
    record = live.generate(native.snapshot(), facts, native.original_chart_bytes)
    payload = _payload(live, native, facts, record)
    payload["schema"] = "KRONOS-SWING-V1-GOVERNED-PDF-ANSWER-V0"
    answer = live.transport.configuration.answer_directory / record.expected_answer_filename
    _answer_pdf(answer, payload)

    with pytest.raises(PdfReviewTransportError, match="ANSWER_VERSION_MISMATCH"):
        live.upload(native.snapshot(), facts, native.original_chart_bytes)
    assert not live.cycle.completed_snapshot()
    assert native.snapshot().review_pack_record is None


def test_v3_answer_is_rejected_for_historical_v2_pack(tmp_path: Path) -> None:
    native, transport = _workflow(tmp_path / "historical-v2")
    record = native.generate_review_pack()
    answer = transport.configuration.answer_directory / record.expected_answer_filename
    _answer_pdf(answer, {
        "schema": VISUAL_EVIDENCE_V3_ANSWER_SCHEMA,
        "manifest": {},
        "candidates": [],
    })

    with pytest.raises(PdfReviewTransportError):
        native.upload_review_answer()
    assert not native.snapshot().readiness_records


def test_wrong_run_machine_snapshot_fails_closed_before_pack_creation(
    tmp_path: Path,
) -> None:
    native, facts, live = _live(tmp_path)
    wrong = object.__new__(type(facts))
    for field in facts.__dataclass_fields__:
        object.__setattr__(wrong, field, getattr(facts, field))
    object.__setattr__(wrong, "run_identity", "SWING-RUN-" + "F" * 32)

    with pytest.raises(PdfReviewTransportError, match="SAME_RUN_BINDING_INVALID"):
        live.generate(native.snapshot(), wrong, native.original_chart_bytes)
    assert live.snapshot(native.snapshot().native_run_identity).review_pack is None


def test_production_server_selects_v3_and_restores_exact_completed_cycle(
    tmp_path: Path,
) -> None:
    native, facts, live = _live(tmp_path)
    record = live.generate(native.snapshot(), facts, native.original_chart_bytes)
    answer = live.transport.configuration.answer_directory / record.expected_answer_filename
    _answer_pdf(answer, _payload(live, native, facts, record))
    live.upload(native.snapshot(), facts, native.original_chart_bytes)
    completed_before_restart = live.cycle.completed_snapshot()
    assert completed_before_restart
    assert all(item.promotion is not None for item in completed_before_restart)
    assert all(
        item.promotion.contract_identity == KR370_PROMOTION_CONTRACT_ID
        and not item.promotion.execution_authority
        and not item.promotion.broker_authority
        for item in completed_before_restart
    )
    run = _evidence_run()[1]
    application = SwingOpportunitiesApplication(
        _Provider,
        initial_snapshot=replace(
            _ready(), swing_analysis_run_identity=run.run_identity
        ),
    )
    application.restore_mtf_fact_snapshot(facts)
    application.restore_native_discovery_run(run)
    server = create_browser_server(
        application,
        port=0,
        v1_review=SwingV1ReviewWorkflow(
            LocalTradingViewEvidenceStore(tmp_path / "legacy")
        ),
        native_review=native,
        visual_v3_live=live,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert server.native_review_version() == "V3"
        status, _, opportunities = _browser_request(
            server, "GET", "/swing/opportunities"
        )
        assert status == 200
        assert "1H PDH/PDL" not in opportunities
        assert "Confluence Zone" not in opportunities
        assert "KR-370" in opportunities
        assert any(
            label in opportunities
            for label in (
                "BUY NOW", "SELL NOW", "BUY READY", "SELL READY",
                "POTENTIAL BUY SETUP", "POTENTIAL SELL SETUP", "NO SETUP",
            )
        )
        assert "0 OUTSTANDING" not in opportunities
        assert "0 WATCHABLE" not in opportunities
        status, _, review = _browser_request(server, "GET", "/swing/v1-review")
        assert status == 200
        assert "SWING-V1-VISUAL-QUESTION-SET-V3 3.1" in review
        assert "V3 REVIEW EVIDENCE IMPORTED" in review
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    restored_cycle = SwingVisualV3ReviewCycle(
        LocalVisualEvidenceV3Store((tmp_path / "visual-v3").resolve()),
        NativeLayer2ReadinessV3Store((tmp_path / "readiness-v3").resolve()),
    )
    restored = SwingVisualV3LiveWorkflow(
        restored_cycle,
        VisualV3PdfReviewTransport(
            live.transport.configuration,
            VisualV3PdfRecordStore((tmp_path / "v3-pdf-records").resolve()),
            clock=lambda: NOW,
        ),
        clock=lambda: NOW,
    )
    restored.restore(native.snapshot(), facts, native.original_chart_bytes)
    assert len(restored.cycle.completed_snapshot()) == len(record.candidate_packs)
    assert all(
        item.promotion is not None
        and item.promotion.integrity_sha256
        == next(
            previous.promotion.integrity_sha256
            for previous in completed_before_restart
            if previous.requirement.canonical_instrument
            == item.requirement.canonical_instrument
        )
        for item in restored.cycle.completed_snapshot()
    )


def test_historical_v2_pack_remains_v2_when_no_same_run_v3_pack(
    tmp_path: Path,
) -> None:
    native, facts, live = _live(tmp_path)
    v2_pack = native.generate_review_pack()
    run = _evidence_run()[1]
    application = SwingOpportunitiesApplication(_Provider, initial_snapshot=_ready())
    application.restore_mtf_fact_snapshot(facts)
    application.restore_native_discovery_run(run)
    server = create_browser_server(
        application,
        port=0,
        v1_review=SwingV1ReviewWorkflow(
            LocalTradingViewEvidenceStore(tmp_path / "legacy")
        ),
        native_review=native,
        visual_v3_live=live,
    )
    try:
        assert v2_pack.question_set_identity != VISUAL_QUESTION_SET_V3_ID
        assert server.native_review_version() == "V2"
        assert not server.visual_v3.completed_snapshot()
    finally:
        server.server_close()
