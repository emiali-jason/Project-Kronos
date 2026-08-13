from dataclasses import replace
from datetime import datetime
from hashlib import sha256
import json
from threading import Event, Thread
from zoneinfo import ZoneInfo

import pytest

from kronos.application.swing_v1_review import (
    ChartAnalysisState,
    SwingV1ReviewWorkflow,
)
from kronos.integrations.openai_chart_analyst import (
    OpenAIChartAnalystConfig,
    OpenAIChartEvidenceProvider,
    OpenAITransportTimeout,
)
from kronos.swing.v1.chart_evidence import (
    CHART_EVIDENCE_SCHEMA_V1_ID,
    CHART_QUESTION_SET_V1_ID,
    MANUAL_CHART_EVIDENCE_PROVIDER_ID,
    OPENAI_CHART_EVIDENCE_PROVIDER_ID,
    BarrierChartEvidence,
    BarrierPresence,
    BarrierRelativeLocation,
    CandleAcceptanceState,
    CandleChartEvidence,
    ChartEvidenceAvailability,
    ChartEvidenceProvider,
    ChartEvidenceProviderError,
    ChartEvidenceProviderFailureCode,
    ChartEvidenceRequest,
    ChartEvidenceResponse,
    ChartQuestionId,
    ChartThesisContext,
    CrisscrossBehaviour,
    IdentityConsistency,
    IdentityEvidence,
    LevelInteraction,
    LevelSignificance,
    ManualChartEvidenceProvider,
    MovingAverageChartEvidence,
    MovingAverageInteraction,
    MovingAverageSlope,
    ParticipationState,
    PineChartEvidence,
    PriceRelationship,
    PriceStructureEvidence,
    PriceStructureValue,
    ReferenceLevelChartEvidence,
    ReferenceLevelIdentity,
    TernaryVisibleState,
    VolumeChartEvidence,
    VolumeTrend,
    chart_evidence_provider_schema,
    chart_evidence_response_from_dict,
    chart_evidence_response_to_dict,
    chart_revision,
    response_to_observations,
)
from kronos.swing.v1.chart_validation import (
    SWING_V1_CHART_VALIDATION_INSTRUMENTS,
    compare_manual_and_ai_chart_evidence,
)
from kronos.swing.v1.layer2 import (
    ExtractionProvenance,
    ObservationCategory,
    OptionsOIBarrierAvailability,
    build_layer2_review_record,
    extract_tradingview_evidence,
    layer2_record_from_dict,
    layer2_record_to_dict,
)
from kronos.swing.v1.evidence_store import (
    LocalTradingViewEvidenceStore,
    StoredChartAnalysisState,
)
from kronos.swing.v1.models import V1Direction, V1Setup
from kronos.swing.v1.tradingview import (
    ChartTimeframe,
    TRADINGVIEW_CHART_TEMPLATE_ID,
    build_tradingview_review_requirements,
)
from tests.unit.swing.v1.test_swing_v1_slice3 import _classified_run


_NOW = datetime(2026, 8, 12, 16, 30, tzinfo=ZoneInfo("Asia/Kolkata"))
_IMAGE = b"\x89PNG\r\n\x1a\nchart-evidence"


def _request() -> ChartEvidenceRequest:
    run = _classified_run({("NAUKRI", V1Setup.PULLBACK_CONTINUATION)})
    requirement = build_tradingview_review_requirements(run)[0]
    return ChartEvidenceRequest(
        run_identity=requirement.run_identity,
        canonical_instrument=requirement.canonical_instrument,
        timeframe=ChartTimeframe.DAILY,
        observation_boundary=requirement.observation_boundary,
        chart_template_identity=TRADINGVIEW_CHART_TEMPLATE_ID,
        question_set_identity=CHART_QUESTION_SET_V1_ID,
        request_timestamp=_NOW,
        source_image_sha256=sha256(_IMAGE).hexdigest(),
        content_type="image/png",
        original_image=_IMAGE,
        thesis_context=ChartThesisContext(
            V1Direction.LONG,
            "PULLBACK_CONTINUATION",
            "BULLISH_HH_HL",
            "UP",
            "ABOVE",
            "POLICY_UNRESOLVED_NO_THRESHOLD",
        ),
    )


def _response(
    request: ChartEvidenceRequest | None = None,
    *,
    provider: str = MANUAL_CHART_EVIDENCE_PROVIDER_ID,
) -> ChartEvidenceResponse:
    request = request or _request()
    instrument_identity = IdentityEvidence(
        ChartEvidenceAvailability.AVAILABLE,
        request.canonical_instrument,
        IdentityConsistency.CONSISTENT,
    )
    timeframe_identity = IdentityEvidence(
        ChartEvidenceAvailability.AVAILABLE,
        request.timeframe.value,
        IdentityConsistency.CONSISTENT,
    )
    template_identity = IdentityEvidence(
        ChartEvidenceAvailability.AVAILABLE,
        request.chart_template_identity,
        IdentityConsistency.CONSISTENT,
    )
    return ChartEvidenceResponse(
        schema_identity=CHART_EVIDENCE_SCHEMA_V1_ID,
        provider_identity=provider,
        model_identity="SPONSOR_REVIEWED_V1" if provider == MANUAL_CHART_EVIDENCE_PROVIDER_ID else "gpt-test-snapshot",
        question_set_identity=CHART_QUESTION_SET_V1_ID,
        request_timestamp=request.request_timestamp,
        run_identity=request.run_identity,
        canonical_instrument=request.canonical_instrument,
        timeframe=request.timeframe,
        observation_boundary=request.observation_boundary,
        chart_template_identity=request.chart_template_identity,
        source_image_sha256=request.source_image_sha256,
        instrument_identity=instrument_identity,
        timeframe_identity=timeframe_identity,
        template_identity=template_identity,
        price_structure=PriceStructureEvidence(
            ChartEvidenceAvailability.AVAILABLE,
            PriceStructureValue.HH_HL,
            (100.0,),
            (90.0,),
            TernaryVisibleState.NO,
            TernaryVisibleState.NO,
            TernaryVisibleState.NO,
        ),
        moving_averages=(
            MovingAverageChartEvidence(
                "SMA20",
                ChartEvidenceAvailability.AVAILABLE,
                MovingAverageSlope.RISING,
                PriceRelationship.ABOVE,
                MovingAverageInteraction.SUPPORT,
                CrisscrossBehaviour.CLEAN_SEPARATION,
            ),
            MovingAverageChartEvidence(
                "SMA50",
                ChartEvidenceAvailability.AVAILABLE,
                MovingAverageSlope.RISING,
                PriceRelationship.ABOVE,
                MovingAverageInteraction.SUPPORT,
                CrisscrossBehaviour.CLEAN_SEPARATION,
            ),
            MovingAverageChartEvidence(
                "SMA200",
                ChartEvidenceAvailability.AVAILABLE,
                MovingAverageSlope.FLAT,
                PriceRelationship.ABOVE,
                MovingAverageInteraction.NONE,
                CrisscrossBehaviour.LIMITED,
            ),
        ),
        candle=CandleChartEvidence(
            ChartEvidenceAvailability.AVAILABLE,
            CandleAcceptanceState.RETEST_HELD,
        ),
        volume=VolumeChartEvidence(
            ChartEvidenceAvailability.AVAILABLE,
            VolumeTrend.INCREASING,
            ParticipationState.SIZEABLE,
            ParticipationState.QUIETER,
            ParticipationState.NOT_APPLICABLE,
        ),
        reference_levels=(
            ReferenceLevelChartEvidence(
                ReferenceLevelIdentity.PDH,
                ChartEvidenceAvailability.AVAILABLE,
                LevelInteraction.SUPPORT,
                LevelSignificance.PARTIAL,
                95.0,
                None,
                None,
            ),
        ),
        barriers=(
            BarrierChartEvidence(
                BarrierPresence.YES,
                ReferenceLevelIdentity.VISIBLE_SUPPORT,
                LevelInteraction.SUPPORT,
                LevelSignificance.PARTIAL,
                BarrierRelativeLocation.BELOW_PRICE,
                "STRUCTURAL_LEVEL",
                92.0,
            ),
        ),
        pine=PineChartEvidence(
            ChartEvidenceAvailability.AVAILABLE,
            "Visible context only",
        ),
        contradictions=(),
        undeterminable_questions=(),
    )


def _provider_payload(response: ChartEvidenceResponse) -> dict[str, object]:
    payload = chart_evidence_response_to_dict(response)
    for field in (
        "schema_identity",
        "provider_identity",
        "model_identity",
        "question_set_identity",
        "request_timestamp",
        "run_identity",
        "canonical_instrument",
        "timeframe",
        "observation_boundary",
        "chart_template_identity",
        "source_image_sha256",
    ):
        payload.pop(field)
    return payload


class _Transport:
    def __init__(self, results):  # type: ignore[no-untyped-def]
        self.results = list(results)
        self.payloads = []

    def create_response(self, payload, *, timeout_seconds):  # type: ignore[no-untyped-def]
        self.payloads.append((payload, timeout_seconds))
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _raw_completed(response: ChartEvidenceResponse) -> dict[str, object]:
    return {
        "status": "completed",
        "output": [{
            "type": "message",
            "content": [{
                "type": "output_text",
                "text": json.dumps(_provider_payload(response)),
            }],
        }],
    }


def test_fixed_contract_schema_manual_provider_and_normalization_are_provider_neutral() -> None:
    request = _request()
    response = _response(request)
    provider = ManualChartEvidenceProvider((response,))

    assert isinstance(provider, ChartEvidenceProvider)
    assert provider.analyze(request) == response
    assert tuple(ChartQuestionId) == tuple(ChartQuestionId(item.value) for item in ChartQuestionId)
    schema = chart_evidence_provider_schema()
    assert schema["additionalProperties"] is False
    assert schema["required"] == list(schema["properties"])

    observations = response_to_observations(response)
    assert {item.category for item in observations} == set(ObservationCategory)
    assert all(item.extraction_provenance is ExtractionProvenance.SPONSOR_REVIEWED_MANUAL for item in observations)
    assert not any(hasattr(item, name) for item in observations for name in ("entry", "stop", "target", "risk_reward", "readiness"))
    assert chart_evidence_response_from_dict(chart_evidence_response_to_dict(response)) == response


def test_openai_adapter_uses_strict_vision_payload_attaches_provenance_and_counts_requests() -> None:
    request = _request()
    expected = _response(request, provider=OPENAI_CHART_EVIDENCE_PROVIDER_ID)
    transport = _Transport([_raw_completed(expected)])
    provider = OpenAIChartEvidenceProvider(
        OpenAIChartAnalystConfig(True, "gpt-test-snapshot", 12.0, 0),
        transport=transport,
    )

    actual = provider.analyze(request)

    assert actual.provider_identity == OPENAI_CHART_EVIDENCE_PROVIDER_ID
    assert actual.model_identity == "gpt-test-snapshot"
    assert provider.request_count == 1
    assert provider.request_audit()[0].outcome == "COMPLETED"
    payload, timeout = transport.payloads[0]
    assert timeout == 12.0
    assert payload["store"] is False
    assert payload["text"]["format"]["strict"] is True
    assert payload["input"][0]["content"][1]["image_url"].startswith("data:image/png;base64,")
    assert "OPENAI_API_KEY" not in json.dumps(payload)
    observations = response_to_observations(actual)
    assert all(item.extraction_provenance is ExtractionProvenance.AI_CHART_ANALYST for item in observations)


@pytest.mark.parametrize(
    ("raw", "failure"),
    (
        ({"status": "incomplete", "output": []}, ChartEvidenceProviderFailureCode.INCOMPLETE),
        ({"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "no"}]}]}, ChartEvidenceProviderFailureCode.REFUSAL),
        ({"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "{}"}]}]}, ChartEvidenceProviderFailureCode.INVALID_SCHEMA),
    ),
)
def test_openai_adapter_fails_closed_for_incomplete_refusal_and_schema_errors(raw, failure) -> None:  # type: ignore[no-untyped-def]
    provider = OpenAIChartEvidenceProvider(
        OpenAIChartAnalystConfig(True, "gpt-test-snapshot", 12.0, 0),
        transport=_Transport([raw]),
    )
    with pytest.raises(ChartEvidenceProviderError) as caught:
        provider.analyze(_request())
    assert caught.value.code is failure


def test_openai_adapter_retries_only_within_bounded_configuration_and_then_fails_closed() -> None:
    transport = _Transport([OpenAITransportTimeout(), OpenAITransportTimeout()])
    provider = OpenAIChartEvidenceProvider(
        OpenAIChartAnalystConfig(True, "gpt-test-snapshot", 12.0, 1),
        transport=transport,
    )
    with pytest.raises(ChartEvidenceProviderError) as caught:
        provider.analyze(_request())
    assert caught.value.code is ChartEvidenceProviderFailureCode.TIMEOUT
    assert provider.request_count == 2


def test_authoritative_response_parser_rejects_unknown_fields() -> None:
    payload = chart_evidence_response_to_dict(_response())
    payload["readiness"] = "READY"
    with pytest.raises(ValueError, match="SCHEMA_INVALID"):
        chart_evidence_response_from_dict(payload)


def test_undeterminable_critical_evidence_fails_closed() -> None:
    response = replace(
        _response(),
        candle=CandleChartEvidence(
            ChartEvidenceAvailability.UNDETERMINABLE,
            CandleAcceptanceState.UNDETERMINABLE,
        ),
        undeterminable_questions=(ChartQuestionId.CANDLE_ACCEPTANCE,),
    )
    with pytest.raises(ChartEvidenceProviderError) as caught:
        response.require_usable_context()
    assert caught.value.code is ChartEvidenceProviderFailureCode.LOW_CONFIDENCE


def test_observed_identity_value_is_independently_bound_to_request() -> None:
    response = replace(
        _response(),
        instrument_identity=IdentityEvidence(
            ChartEvidenceAvailability.AVAILABLE,
            "TITAN",
            IdentityConsistency.CONSISTENT,
        ),
    )
    with pytest.raises(ChartEvidenceProviderError) as caught:
        response.validate_binding(_request())
    assert caught.value.code is ChartEvidenceProviderFailureCode.IDENTITY_MISMATCH


def test_existing_layer2_reconciliation_barriers_readiness_and_codec_consume_provider_contract() -> None:
    run = _classified_run({("NAUKRI", V1Setup.PULLBACK_CONTINUATION)})
    requirement = build_tradingview_review_requirements(run)[0]
    response = _response(_request())
    extracted = extract_tradingview_evidence(
        requirement,
        (chart_revision(response),),
        response_to_observations(response),
        template_identity=requirement.chart_template_identity,
    )
    assert extracted.evidence is not None
    instrument = next(item for item in run.instruments if item.canonical_identity == "NAUKRI")
    probable = tuple(item for item in instrument.assessments if item.setup is V1Setup.PULLBACK_CONTINUATION)
    record = build_layer2_review_record(requirement, probable, extracted.evidence)

    assert record.barriers
    assert record.options_oi.availability is OptionsOIBarrierAvailability.UNAVAILABLE
    assert record.readiness.state.value in {
        "READY_FOR_TRADE_CONSTRUCTION",
        "WEAKENING",
        "CONTEXT_INCOMPLETE",
    }
    assert layer2_record_from_dict(layer2_record_to_dict(record)) == record
    serialized = json.dumps(layer2_record_to_dict(record))
    assert '"final_trade_construction": "NOT_IMPLEMENTED"' in serialized
    assert '"final_risk_reward": "NOT_CALCULATED"' in serialized
    assert '"ranking": "NOT_PERFORMED"' in serialized


def test_explicit_workflow_analysis_retains_response_and_recovers_after_restart(tmp_path) -> None:  # type: ignore[no-untyped-def]
    run = _classified_run({("NAUKRI", V1Setup.PULLBACK_CONTINUATION)})
    response = _response()
    store = LocalTradingViewEvidenceStore(tmp_path, clock=lambda: _NOW)
    workflow = SwingV1ReviewWorkflow(
        store,
        chart_evidence_provider=ManualChartEvidenceProvider((response,)),
        clock=lambda: _NOW,
    )
    workflow.publish_layer1(run)
    workflow.upload(
        instrument="NAUKRI",
        timeframe=ChartTimeframe.DAILY,
        content_type="image/png",
        original_bytes=_IMAGE,
    )
    assert workflow.snapshot().analysis_for("NAUKRI").state is ChartAnalysisState.READY_TO_ANALYZE

    analyzed = workflow.analyze_chart_context("NAUKRI")

    assert analyzed.state is ChartAnalysisState.ANALYSIS_COMPLETE
    assert analyzed.readiness is not None
    requirement = workflow.snapshot().requirement_for("NAUKRI")
    retained = store.chart_analysis_for(requirement)
    assert retained.state is StoredChartAnalysisState.COMPLETE
    assert retained.provider_request_count == 1
    assert retained.responses == (response,)
    persisted = json.loads((tmp_path / store.package_for(requirement).structured_evidence_path).read_text())
    assert persisted["provider_results"][0]["provider_identity"] == MANUAL_CHART_EVIDENCE_PROVIDER_ID
    assert persisted["final_trade_construction"] == "NOT_IMPLEMENTED"

    restarted = SwingV1ReviewWorkflow(store)
    restored = restarted.publish_layer1(run).analysis_for("NAUKRI")
    assert restored.state is ChartAnalysisState.ANALYSIS_COMPLETE
    assert restored.readiness == analyzed.readiness


def test_workflow_provider_unavailable_is_retained_as_context_incomplete(tmp_path) -> None:  # type: ignore[no-untyped-def]
    run = _classified_run({("NAUKRI", V1Setup.PULLBACK_CONTINUATION)})
    workflow = SwingV1ReviewWorkflow(
        LocalTradingViewEvidenceStore(tmp_path, clock=lambda: _NOW),
        clock=lambda: _NOW,
    )
    workflow.publish_layer1(run)
    workflow.upload(
        instrument="NAUKRI",
        timeframe=ChartTimeframe.DAILY,
        content_type="image/png",
        original_bytes=_IMAGE,
    )

    result = workflow.analyze_chart_context("NAUKRI")

    assert result.state is ChartAnalysisState.CHART_ANALYSIS_UNAVAILABLE
    assert result.readiness.state.value == "CONTEXT_INCOMPLETE"
    assert result.failure_code is ChartEvidenceProviderFailureCode.UNAVAILABLE


def test_explicit_inflight_call_projects_analyzing_state_without_background_calls(tmp_path) -> None:  # type: ignore[no-untyped-def]
    started = Event()
    release = Event()

    class BlockingProvider:
        @property
        def provider_identity(self) -> str:
            return MANUAL_CHART_EVIDENCE_PROVIDER_ID

        def analyze(self, request: ChartEvidenceRequest) -> ChartEvidenceResponse:
            started.set()
            assert release.wait(3)
            return _response(request)

    workflow = SwingV1ReviewWorkflow(
        LocalTradingViewEvidenceStore(tmp_path, clock=lambda: _NOW),
        chart_evidence_provider=BlockingProvider(),
        clock=lambda: _NOW,
    )
    workflow.publish_layer1(_classified_run({("NAUKRI", V1Setup.PULLBACK_CONTINUATION)}))
    workflow.upload(
        instrument="NAUKRI",
        timeframe=ChartTimeframe.DAILY,
        content_type="image/png",
        original_bytes=_IMAGE,
    )
    thread = Thread(target=workflow.analyze_chart_context, args=("NAUKRI",))
    thread.start()
    assert started.wait(3)
    assert workflow.snapshot().analysis_for("NAUKRI").state is ChartAnalysisState.ANALYZING_CHART_CONTEXT
    release.set()
    thread.join(3)
    assert not thread.is_alive()
    assert workflow.snapshot().analysis_for("NAUKRI").state is ChartAnalysisState.ANALYSIS_COMPLETE


@pytest.mark.parametrize(
    "instrument",
    ("NAUKRI", "TITAN", "POWERGRID", "HINDUNILVR", "ADANIENT", "NTPC", "YESBANK"),
)
def test_validation_programme_reference_instruments_use_one_frozen_question_set(instrument: str) -> None:
    assert CHART_QUESTION_SET_V1_ID == "SWING-V1-CHART-QUESTION-SET-V1"
    assert instrument in {"NAUKRI", "TITAN", "POWERGRID", "HINDUNILVR", "ADANIENT", "NTPC", "YESBANK"}


def test_manual_vs_repeated_ai_validation_measures_all_required_fields_without_tuning() -> None:
    manual = _response()
    ai = _response(provider=OPENAI_CHART_EVIDENCE_PROVIDER_ID)
    result = compare_manual_and_ai_chart_evidence(manual, (ai, ai, ai))

    assert SWING_V1_CHART_VALIDATION_INSTRUMENTS == (
        "NAUKRI", "TITAN", "POWERGRID", "HINDUNILVR", "ADANIENT", "NTPC", "YESBANK",
    )
    assert result.ai_run_count == 3
    assert result.compared_field_count == 9
    assert result.agreed_field_count == 9
    assert result.schema_validity is True
    assert result.run_to_run_consistency is True
