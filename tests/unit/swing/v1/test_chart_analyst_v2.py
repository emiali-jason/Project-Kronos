import json
from dataclasses import replace
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path

import pytest

from kronos.integrations import openai_chart_analyst as adapter
from kronos.integrations.openai_chart_analyst import (
    OpenAIChartAnalystV2Config,
    OpenAIChartAnalystV2Provider,
    OpenAITransportTimeout,
)
from kronos.application.swing_v1_review import ChartAnalysisState, SwingV1ReviewWorkflow
from kronos.swing.v1.chart_analyst_v2 import (
    CHART_ANALYST_V2_EVIDENCE_FAMILIES,
    CHART_ANALYST_V2_QUESTION_SET_ID,
    CHART_ANALYST_V2_QUESTION_SET_VERSION,
    CHART_ANALYST_V2_TIMEFRAMES,
    ChartAnalystProduct,
    ChartAnalystV2Error,
    ChartAnalystV2FailureCode,
    ChartAnalystV2Request,
    ChartAnalystV2Response,
    ChartAnalystV2Thesis,
    chart_analyst_v2_provider_schema,
    chart_analyst_v2_response_from_dict,
    chart_analyst_v2_response_to_dict,
)
from kronos.swing.v1.chart_analyst_v2_store import LocalChartAnalystV2Store
from kronos.swing.v1.chart_analyst_v2_integrity import (
    ChartAnalystV2IntegrityFailureCode,
    ChartAnalystV2OutputIntegrityError,
    validate_chart_analyst_v2_output_integrity,
)
from kronos.swing.v1.evidence_store import LocalTradingViewEvidenceStore
from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.tradingview import ChartTimeframe
from tests.fixtures.swing_v1_chart_analyst_v2 import SPONSOR_REVIEWED_V2_CASES


_NOW = datetime(2026, 8, 13, 9, 15, tzinfo=UTC)
_IMAGE = b"\x89PNG\r\n\x1a\nnormal-four-pane-chart"
_PARENT_RUN = "SWING-RUN-00000000000000000000000000000002"


class _Transport:
    def __init__(self, *results: object) -> None:
        self.results = list(results)
        self.calls: list[tuple[dict[str, object], float]] = []

    def create_response(
        self,
        payload: dict[str, object],
        *,
        timeout_seconds: float,
    ) -> dict[str, object]:
        self.calls.append((payload, timeout_seconds))
        result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        assert type(result) is dict
        return result


class _ManualV2Provider:
    provider_identity = "OPENAI_CHART_ANALYST_V2_PROVIDER"

    def __init__(self) -> None:
        self.calls: list[ChartAnalystV2Request] = []
        self.responses: dict[tuple[str, str, str], ChartAnalystV2Response] = {}

    def analyze(self, request: ChartAnalystV2Request) -> ChartAnalystV2Response:
        self.calls.append(request)
        response = ChartAnalystV2Response(
            provider_identity=self.provider_identity,
            model_identity="gpt-test",
            request_timestamp=request.request_timestamp,
            run_identity=request.run_identity,
            swing_analysis_run_identity=request.swing_analysis_run_identity,
            analysis=_analysis(request),
        )
        self.responses[(request.run_identity, request.instrument, request.image_sha256)] = response
        return response

    def retained_response(
        self,
        *,
        run_identity: str,
        swing_analysis_run_identity: str,
        instrument: str,
        image_sha256: str,
    ) -> ChartAnalystV2Response | None:
        return self.responses.get((run_identity, instrument, image_sha256))


def _request(run: str = "RUN-1") -> ChartAnalystV2Request:
    return ChartAnalystV2Request(
        run_identity=run,
        instrument="NAUKRI",
        product=ChartAnalystProduct.NSE,
        observation_boundary=_NOW,
        request_timestamp=_NOW,
        image_sha256=sha256(_IMAGE).hexdigest(),
        content_type="image/png",
        original_image=_IMAGE,
        thesis=ChartAnalystV2Thesis(
            direction=V1Direction.LONG,
            setup="PULLBACK_CONTINUATION",
        ),
    )


def _analysis(request: ChartAnalystV2Request | None = None) -> dict[str, object]:
    bound = request or _request()
    value = _schema_value(chart_analyst_v2_provider_schema())
    assert type(value) is dict
    value.update({
        "instrument": bound.instrument,
        "product": bound.product.value,
        "image_sha256": bound.image_sha256,
    })
    return value


def _schema_value(schema: object) -> object:
    assert type(schema) is dict
    if "const" in schema:
        return schema["const"]
    if "anyOf" in schema:
        choices = schema["anyOf"]
        assert type(choices) is list
        string_choice = next(
            (item for item in choices if type(item) is dict and item.get("type") == "string"),
            None,
        )
        return _schema_value(string_choice or choices[0])
    if schema.get("type") == "object":
        return {
            key: _schema_value(child)
            for key, child in schema["properties"].items()
        }
    if schema.get("type") == "string":
        choices = schema.get("enum")
        if type(choices) is list:
            if "UNDETERMINABLE" in choices:
                return "UNDETERMINABLE"
            if "UNREADABLE" in choices:
                return "UNREADABLE"
            return choices[0]
        if schema.get("pattern"):
            return "0" * 64
        return "UNREADABLE"
    if schema.get("type") == "number":
        return 1.0
    if schema.get("type") == "null":
        return None
    raise AssertionError(schema)


def _completed(request: ChartAnalystV2Request | None = None) -> dict[str, object]:
    return _completed_with_analysis(_analysis(request))


def _completed_with_analysis(analysis: dict[str, object]) -> dict[str, object]:
    return {
        "status": "completed",
        "usage": {"input_tokens": 1000, "output_tokens": 500, "total_tokens": 1500},
        "output": [{
            "type": "message",
            "content": [{"type": "output_text", "text": json.dumps(analysis)}],
        }],
    }


def _output_integrity_fixtures() -> dict[str, object]:
    path = (
        Path(__file__).parents[3]
        / "fixtures"
        / "swing"
        / "v1"
        / "chart_analyst_v2_output_integrity.json"
    )
    value = json.loads(path.read_text(encoding="utf-8"))
    assert type(value) is dict
    return value


def test_frozen_v2_identity_has_exact_twenty_families_and_four_panes() -> None:
    assert CHART_ANALYST_V2_QUESTION_SET_ID == "KRONOS-SWING-V1-CHART-ANALYST-V2"
    assert CHART_ANALYST_V2_QUESTION_SET_VERSION == "2.0"
    assert len(CHART_ANALYST_V2_EVIDENCE_FAMILIES) == 20
    assert CHART_ANALYST_V2_TIMEFRAMES == ("1W", "1D", "4H", "1H")
    schema = chart_analyst_v2_provider_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]["timeframes"]["properties"]) == set(
        CHART_ANALYST_V2_TIMEFRAMES
    )


def test_sponsor_reviewed_case_distinctions_are_validation_only() -> None:
    assert SPONSOR_REVIEWED_V2_CASES == {
        "NAUKRI": "bullish impulse + tight digestion / continuation developing",
        "TITAN": "bullish impulse + deeper orderly pullback / early recovery",
        "POWERGRID": "bearish thesis + stalled downside progress",
        "HINDUNILVR": "bearish continuation + pause near lows",
        "MCX Gold": "bullish/recovery structure + consolidation near highs + Commodity context",
    }


def test_response_is_strict_fail_closed_and_round_trips() -> None:
    request = _request()
    response = ChartAnalystV2Response(
        provider_identity="OPENAI_CHART_ANALYST_V2_PROVIDER",
        model_identity="gpt-test",
        request_timestamp=_NOW,
        run_identity=request.run_identity,
        analysis=_analysis(request),
    )
    response.validate_binding(request)
    assert chart_analyst_v2_response_from_dict(
        chart_analyst_v2_response_to_dict(response)
    ) == response
    assert all(
        item["market_structure"]["structure"] == "UNDETERMINABLE"
        for item in response.analysis["timeframes"].values()
    )

    malformed = _analysis(request)
    del malformed["timeframes"]["1W"]["volume_participation"]
    with pytest.raises(ValueError, match="CHART_ANALYST_V2_RESPONSE_INVALID"):
        replace(response, analysis=malformed)


def test_outbound_request_contains_only_approved_variable_inputs() -> None:
    request = _request("PRIVATE-RUN-MUST-STAY-LOCAL")
    payload = adapter._responses_v2_payload(request, "gpt-test")
    serialized = json.dumps(payload)
    assert request.instrument in serialized
    assert request.product.value in serialized
    assert request.image_sha256 in serialized
    assert request.thesis.setup in serialized
    assert request.thesis.direction.value in serialized
    assert request.run_identity not in serialized
    assert request.observation_boundary.isoformat() not in serialized
    assert "api_key" not in serialized.lower()
    assert "account" not in serialized.lower()
    assert len(payload["input"][0]["content"]) == 2
    assert payload["input"][0]["content"][1]["type"] == "input_image"
    assert payload["max_output_tokens"] == 12_000
    assert payload["text"]["format"]["strict"] is True


def test_one_call_is_cached_and_rebound_to_later_run(tmp_path) -> None:  # type: ignore[no-untyped-def]
    request = _request()
    transport = _Transport(_completed(request))
    store = LocalChartAnalystV2Store(tmp_path)
    provider = OpenAIChartAnalystV2Provider(
        OpenAIChartAnalystV2Config(enabled=True, model_identity="gpt-test"),
        store=store,
        transport=transport,
    )

    first = provider.analyze(request)
    second_request = _request("RUN-2")
    second = provider.analyze(second_request)

    assert len(transport.calls) == 1
    assert provider.request_count == 1
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.run_identity == "RUN-2"
    second.validate_binding(second_request)
    summary = store.cost_summary(date(2026, 8, 13))
    assert summary.api_attempt_count == 1
    assert summary.cache_hit_count == 1
    assert summary.average_cost_per_chart_usd == 0.02
    assert summary.average_cost_per_probable_usd == 0.02
    assert summary.daily_api_cost_usd == 0.02


def test_schema_or_transport_failure_retries_once_only(tmp_path) -> None:  # type: ignore[no-untyped-def]
    request = _request()
    malformed = {"status": "completed", "output": []}
    transport = _Transport(malformed, _completed(request))
    provider = OpenAIChartAnalystV2Provider(
        OpenAIChartAnalystV2Config(enabled=True, model_identity="gpt-test"),
        store=LocalChartAnalystV2Store(tmp_path),
        transport=transport,
    )
    assert provider.analyze(request).instrument == "NAUKRI"
    assert len(transport.calls) == 2

    failed = OpenAIChartAnalystV2Provider(
        OpenAIChartAnalystV2Config(enabled=True, model_identity="gpt-test"),
        store=LocalChartAnalystV2Store(tmp_path / "failed"),
        transport=_Transport(OpenAITransportTimeout(), OpenAITransportTimeout()),
    )
    with pytest.raises(ChartAnalystV2Error) as caught:
        failed.analyze(request)
    assert caught.value.code is ChartAnalystV2FailureCode.TIMEOUT
    assert failed.request_count == 2


def test_frozen_output_integrity_defects_fail_closed_without_remapping() -> None:
    fixtures = _output_integrity_fixtures()
    defects = fixtures["observed_defects"]
    assert type(defects) is dict

    sbin = _analysis()
    sbin_defect = defects["SBIN"]
    assert type(sbin_defect) is dict
    sbin["timeframes"]["1H"]["pine_workstation"]["quality"] = sbin_defect["raw_value"]
    sbin_report = validate_chart_analyst_v2_output_integrity(sbin)
    assert sbin_report.accepted is False
    assert len(sbin_report.failures) == 1
    assert sbin_report.failures[0].raw_value == "Bullish"
    assert sbin_report.failures[0].normalized_value == ("Bullish",)
    assert sbin_report.failures[0].failure_code is (
        ChartAnalystV2IntegrityFailureCode.INVALID_TRANSCRIPTION
    )
    assert sbin_report.failures[0].failure_reason == (
        "PINE_FIELD_SEMANTIC_DISPLACEMENT"
    )
    with pytest.raises(ChartAnalystV2OutputIntegrityError):
        ChartAnalystV2Response(
            provider_identity="OPENAI_CHART_ANALYST_V2_PROVIDER",
            model_identity="gpt-test",
            request_timestamp=_NOW,
            run_identity="RUN-1",
            analysis=sbin,
        )

    bdl = _analysis()
    bdl_defect = defects["BDL"]
    assert type(bdl_defect) is dict
    bdl["thesis_behaviour"]["thesis_behaviour_reason"] = bdl_defect["raw_value"]
    bdl_report = validate_chart_analyst_v2_output_integrity(bdl)
    assert bdl_report.accepted is False
    assert len(bdl_report.failures) == 1
    assert len(bdl_report.failures[0].raw_value) == 256
    assert bdl_report.failures[0].failure_code is (
        ChartAnalystV2IntegrityFailureCode.INVALID_INCOMPLETE_TEXT
    )
    assert bdl_report.failures[0].failure_reason == "TEXT_ENDS_WITH_INCOMPLETE_MARKER"


def test_valid_pine_vocabularies_and_complete_required_text_pass() -> None:
    fixtures = _output_integrity_fixtures()
    valid = fixtures["valid_transcriptions"]
    complete = fixtures["valid_required_text"]
    assert type(valid) is dict and type(complete) is str
    analysis = _analysis()
    for timeframe in CHART_ANALYST_V2_TIMEFRAMES:
        analysis["timeframes"][timeframe]["pine_workstation"].update(valid)
    analysis["multi_timeframe"]["key_timeframe_contradiction"] = complete
    analysis["pine_vs_chart"]["contradiction_reason"] = complete
    analysis["thesis_behaviour"]["thesis_behaviour_reason"] = complete
    analysis["next_observable_event"]["what_needs_to_happen_next"] = complete
    analysis["overall_observation"]["most_material_positive_evidence"] = complete
    analysis["overall_observation"]["most_material_negative_evidence"] = complete

    report = validate_chart_analyst_v2_output_integrity(analysis)

    assert report.accepted is True
    assert report.failures == ()
    assert len(report.checks) == 42

    invalid_nse_decision = _analysis()
    invalid_nse_decision["timeframes"]["1H"]["pine_workstation"]["decision"] = "BUY NOW"
    invalid_report = validate_chart_analyst_v2_output_integrity(invalid_nse_decision)
    assert invalid_report.accepted is False
    assert invalid_report.failures[0].failure_code is (
        ChartAnalystV2IntegrityFailureCode.INVALID_TRANSCRIPTION
    )


def test_integrity_failure_retries_once_and_retains_raw_audits(tmp_path) -> None:  # type: ignore[no-untyped-def]
    fixtures = _output_integrity_fixtures()["observed_defects"]
    assert type(fixtures) is dict
    request = _request()
    sbin = _analysis(request)
    sbin["timeframes"]["1H"]["pine_workstation"]["quality"] = fixtures["SBIN"]["raw_value"]
    transport = _Transport(_completed_with_analysis(sbin), _completed(request))
    store = LocalChartAnalystV2Store(tmp_path)
    provider = OpenAIChartAnalystV2Provider(
        OpenAIChartAnalystV2Config(enabled=True, model_identity="gpt-test"),
        store=store,
        transport=transport,
    )

    response = provider.analyze(request)

    assert response.instrument == request.instrument
    assert len(transport.calls) == 2
    audits = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (tmp_path / "integrity-audits").rglob("*.json")
    ]
    assert len(audits) == 2
    rejected = next(item for item in audits if item["binding"]["attempt"] == 1)
    accepted = next(item for item in audits if item["binding"]["attempt"] == 2)
    assert rejected["integrity"]["validation_result"] == "REJECTED"
    assert rejected["raw_transcription"]["timeframes"]["1H"]["pine_workstation"]["quality"] == "Bullish"
    issue = next(
        check for check in rejected["integrity"]["checks"]
        if check["field_path"] == "timeframes.1H.pine_workstation.quality"
    )
    assert issue["raw_value"] == "Bullish"
    assert issue["normalized_value"] == ["Bullish"]
    assert issue["failure_code"] == "INVALID_TRANSCRIPTION"
    assert issue["failure_reason"] == "PINE_FIELD_SEMANTIC_DISPLACEMENT"
    assert accepted["integrity"]["validation_result"] == "ACCEPTED"


def test_incomplete_text_fails_after_one_retry_and_is_not_accepted(tmp_path) -> None:  # type: ignore[no-untyped-def]
    fixtures = _output_integrity_fixtures()["observed_defects"]
    assert type(fixtures) is dict
    request = _request()
    bdl = _analysis(request)
    raw_reason = fixtures["BDL"]["raw_value"]
    bdl["thesis_behaviour"]["thesis_behaviour_reason"] = raw_reason
    store = LocalChartAnalystV2Store(tmp_path)
    provider = OpenAIChartAnalystV2Provider(
        OpenAIChartAnalystV2Config(enabled=True, model_identity="gpt-test"),
        store=store,
        transport=_Transport(
            _completed_with_analysis(bdl),
            _completed_with_analysis(bdl),
        ),
    )

    with pytest.raises(ChartAnalystV2Error) as caught:
        provider.analyze(request)

    assert caught.value.code is ChartAnalystV2FailureCode.INVALID_SCHEMA
    assert provider.request_count == 2
    assert list((tmp_path / "cache").rglob("*.json")) == []
    assert list((tmp_path / "runs").rglob("*.json")) == []
    audits = sorted((tmp_path / "integrity-audits").rglob("*.json"))
    assert len(audits) == 2
    for path in audits:
        retained = json.loads(path.read_text(encoding="utf-8"))
        assert retained["raw_model_output"]
        assert retained["raw_transcription"]["thesis_behaviour"]["thesis_behaviour_reason"] == raw_reason
        assert retained["integrity"]["validation_result"] == "REJECTED"


def test_refusal_and_identity_mismatch_do_not_retry(tmp_path) -> None:  # type: ignore[no-untyped-def]
    request = _request()
    refusal = {
        "status": "completed",
        "output": [{"type": "message", "content": [{"type": "refusal"}]}],
    }
    transport = _Transport(refusal, _completed(request))
    provider = OpenAIChartAnalystV2Provider(
        OpenAIChartAnalystV2Config(enabled=True, model_identity="gpt-test"),
        store=LocalChartAnalystV2Store(tmp_path),
        transport=transport,
    )
    with pytest.raises(ChartAnalystV2Error) as caught:
        provider.analyze(request)
    assert caught.value.code is ChartAnalystV2FailureCode.REFUSAL
    assert len(transport.calls) == 1

    wrong = _analysis(request)
    wrong["instrument"] = "TITAN"
    identity_transport = _Transport({
        "status": "completed",
        "output": [{
            "type": "message",
            "content": [{"type": "output_text", "text": json.dumps(wrong)}],
        }],
    })
    mismatched = OpenAIChartAnalystV2Provider(
        OpenAIChartAnalystV2Config(enabled=True, model_identity="gpt-test"),
        store=LocalChartAnalystV2Store(tmp_path / "wrong"),
        transport=identity_transport,
    )
    with pytest.raises(ChartAnalystV2Error) as caught:
        mismatched.analyze(request)
    assert caught.value.code is ChartAnalystV2FailureCode.IDENTITY_MISMATCH
    assert len(identity_transport.calls) == 1


def test_configuration_forbids_more_than_one_retry() -> None:
    with pytest.raises(ValueError, match="OPENAI_CHART_ANALYST_V2_CONFIG_INVALID"):
        OpenAIChartAnalystV2Config(maximum_retries=2)


def test_v2_runtime_configuration_has_no_environment_activation_dependency() -> None:
    disabled_environment = OpenAIChartAnalystV2Config.from_environment({
        "KRONOS_CHART_ANALYST_ENABLED": "false",
    })
    malformed_environment = OpenAIChartAnalystV2Config.from_environment({
        "KRONOS_CHART_ANALYST_ENABLED": "not-a-boolean",
    })

    assert disabled_environment.enabled is True
    assert malformed_environment.enabled is True


def test_v2_provider_uses_dynamic_browser_activation_before_transport(tmp_path) -> None:  # type: ignore[no-untyped-def]
    request = _request()
    transport = _Transport(_completed(request))
    state = {"enabled": False}
    provider = OpenAIChartAnalystV2Provider(
        OpenAIChartAnalystV2Config(enabled=True, model_identity="gpt-test"),
        store=LocalChartAnalystV2Store(tmp_path),
        transport=transport,
        activation_probe=lambda: state["enabled"],
    )

    with pytest.raises(ChartAnalystV2Error) as caught:
        provider.analyze(request)
    assert caught.value.code is ChartAnalystV2FailureCode.DISABLED
    assert transport.calls == []

    state["enabled"] = True
    assert provider.analyze(request).instrument == "NAUKRI"
    assert len(transport.calls) == 1


def test_controlled_workflow_fails_undeterminable_v2_closed_in_4f(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from tests.unit.swing.v1.test_swing_v1_slice3 import _classified_run
    from kronos.swing.v1.models import V1Setup

    provider = _ManualV2Provider()
    workflow = SwingV1ReviewWorkflow(
        LocalTradingViewEvidenceStore(tmp_path, clock=lambda: _NOW),
        chart_analyst_v2_provider=provider,
        clock=lambda: _NOW,
    )
    workflow.publish_layer1(
        _classified_run({("NAUKRI", V1Setup.PULLBACK_CONTINUATION)}),
        swing_analysis_run_identity=_PARENT_RUN,
    )
    workflow.upload(
        instrument="NAUKRI",
        timeframe=ChartTimeframe.DAILY,
        content_type="image/png",
        original_bytes=_IMAGE,
    )

    result = workflow.analyze_chart_context("NAUKRI")

    assert len(provider.calls) == 1
    assert result.state is ChartAnalysisState.CONTEXT_INCOMPLETE
    assert result.response_count == 1
    assert result.readiness is not None
    assert result.readiness.state.value == "CONTEXT_INCOMPLETE"
    assert result.v2_evidence is not None
    assert result.v2_evidence.analysis["timeframes"].keys() == {
        "1W", "1D", "4H", "1H"
    }
