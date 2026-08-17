from copy import deepcopy
from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

from kronos.integrations.openai_chart_analyst import (
    OpenAIProviderRequestRejected,
    OpenAIVisualEvidenceV2Config,
    OpenAIVisualEvidenceV2Provider,
)
from kronos.swing.v1.chart_analyst_v2 import ChartAnalystV2Error
from kronos.swing.v1.visual_evidence_v2 import (
    LocalVisualEvidenceV2DiagnosticStore,
    VisualEvidenceV2ValidationStage,
    VisualQuestionV2,
    VisualTimeframe,
)
from tests.unit.swing.v1.test_visual_evidence_v2 import (
    _Transport,
    _raw,
    _request,
    _response,
)


NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)


class _RejectedTransport:
    def create_response(self, _payload, *, timeout_seconds):  # type: ignore[no-untyped-def]
        del timeout_seconds
        raise OpenAIProviderRequestRejected(
            http_status=400,
            error_type="invalid_request_error",
            error_code="invalid_json_schema",
            rejected_parameter="text.format.schema.properties.observations.items",
            provider_message="Unsupported schema pattern",
        )


def _provider(
    tmp_path: Path,
    raw: dict[str, object],
    *,
    retries: int = 0,
) -> tuple[OpenAIVisualEvidenceV2Provider, LocalVisualEvidenceV2DiagnosticStore]:
    store = LocalVisualEvidenceV2DiagnosticStore(tmp_path / "diagnostics")
    return (
        OpenAIVisualEvidenceV2Provider(
            OpenAIVisualEvidenceV2Config(
                enabled=True,
                model_identity="gpt-5.6-sol",
                maximum_retries=retries,
            ),
            transport=_Transport(raw),
            diagnostic_store=store,
            clock=lambda: NOW,
        ),
        store,
    )


def _failed(
    tmp_path: Path,
    raw: dict[str, object],
    request=None,  # type: ignore[no-untyped-def]
    *,
    retries: int = 0,
):  # type: ignore[no-untyped-def]
    request = request or _request()
    provider, store = _provider(tmp_path, raw, retries=retries)
    with pytest.raises(ChartAnalystV2Error):
        provider.analyze(request)
    return store.load_for_run(request.requirement.native_run_identity)


def test_valid_v2_response_is_unchanged_and_records_no_diagnostic(tmp_path: Path) -> None:
    request = _request()
    provider, store = _provider(tmp_path, _raw(_response(request)))

    result = provider.analyze(request)

    assert len(result.observations) == 10
    assert store.load_for_run(request.requirement.native_run_identity) == ()


@pytest.mark.parametrize(
    ("mutate", "code", "path"),
    (
        (
            lambda values: values[0].update(observation_status="NOT_A_STATUS"),
            "V2_ENUM_INVALID",
            "observations[0].observation_status",
        ),
        (
            lambda values: values[1].update(
                observation_status="OBSERVED", level_availability="AVAILABLE",
                price=None, zone_low=None, zone_high=None,
            ),
            "V2_LEVEL_AVAILABILITY_INCONSISTENT",
            "observations[1]",
        ),
        (
            lambda values: values[1].update(
                observation_status="OBSERVED", level_availability="AVAILABLE",
                price=100.0, zone_low=99.0, zone_high=101.0,
            ),
            "V2_PRICE_ZONE_EXCLUSIVITY_INVALID",
            "observations[1]",
        ),
        (
            lambda values: values[9].update(why_not_covered_elsewhere="EXTRA"),
            "V2_Q10_NONE_SEMANTICS_INVALID",
            "observations[9].why_not_covered_elsewhere",
        ),
        (
            lambda values: values[2].update(
                observation_status="PARTIAL", ambiguity_reason="",
            ),
            "V2_AMBIGUITY_REASON_REQUIRED",
            "observations[2].ambiguity_reason",
        ),
    ),
)
def test_exact_safe_domain_failure_is_retained(
    tmp_path: Path, mutate, code: str, path: str,  # type: ignore[no-untyped-def]
) -> None:
    request = _request()
    raw = deepcopy(_raw(_response(request)))
    values = json.loads(raw["output"][0]["content"][0]["text"])
    mutate(values["observations"])
    raw["output"][0]["content"][0]["text"] = json.dumps(values)

    records = _failed(tmp_path, raw, request)

    assert len(records) == 1
    assert records[0].validation_error_code == code
    assert records[0].structural_path == path
    assert records[0].validation_stage in {
        VisualEvidenceV2ValidationStage.TRANSPORT_TO_DOMAIN_ADAPTER,
        VisualEvidenceV2ValidationStage.FROZEN_DOMAIN_INVARIANT,
    }


def test_wrong_timeframe_routing_is_distinguished(tmp_path: Path) -> None:
    request = _request(timeframe=VisualTimeframe.WEEKLY)
    raw = deepcopy(_raw(_response(request)))
    values = json.loads(raw["output"][0]["content"][0]["text"])
    q4 = next(
        item for item in values["observations"]
        if item["question_id"] == VisualQuestionV2.PDH_PDL_REFERENCE_CONTEXT.value
    )
    q4["observation_status"] = "OBSERVED"
    raw["output"][0]["content"][0]["text"] = json.dumps(values)

    records = _failed(tmp_path, raw, request)

    assert records[0].validation_stage is VisualEvidenceV2ValidationStage.TIMEFRAME_ROUTING
    assert records[0].validation_error_code == "VISUAL_V2_ROUTING_INVALID"


@pytest.mark.parametrize(
    ("raw_factory", "stage", "code", "path"),
    (
        (
            lambda request: {"status": "completed", "output": []},
            VisualEvidenceV2ValidationStage.STRUCTURED_OUTPUT_DECODING,
            "V2_OUTPUT_TEXT_CARDINALITY_INVALID",
            "output[].content[].output_text",
        ),
        (
            lambda request: {
                "status": "completed",
                "output": [{"type": "message", "content": [
                    {"type": "output_text", "text": "not-json"}
                ]}],
            },
            VisualEvidenceV2ValidationStage.JSON_PARSING,
            "V2_JSON_INVALID",
            "output_text",
        ),
    ),
)
def test_decode_stage_identity_is_retained(
    tmp_path: Path, raw_factory, stage, code: str, path: str,  # type: ignore[no-untyped-def]
) -> None:
    request = _request()

    records = _failed(tmp_path, raw_factory(request), request)

    assert records[0].validation_stage is stage
    assert records[0].validation_error_code == code
    assert records[0].structural_path == path


@pytest.mark.parametrize(
    ("mutate", "code", "path"),
    (
        (
            lambda values: values.__setitem__(
                slice(None), values[:-1]
            ),
            "V2_OBSERVATION_CARDINALITY_INVALID",
            "observations",
        ),
        (
            lambda values: values.__setitem__(
                0, {**values[0], "question_id": values[1]["question_id"]}
            ),
            "V2_QUESTION_IDENTITY_ORDER_INVALID",
            "observations[0].question_id",
        ),
        (
            lambda values: values[4].update(observation="BUY"),
            "V2_PROHIBITED_ANALYTICAL_CONSEQUENCE",
            "observations[4]",
        ),
    ),
)
def test_frozen_identity_cardinality_and_authority_failures_are_identified(
    tmp_path: Path, mutate, code: str, path: str,  # type: ignore[no-untyped-def]
) -> None:
    request = _request()
    raw = deepcopy(_raw(_response(request)))
    values = json.loads(raw["output"][0]["content"][0]["text"])
    mutate(values["observations"])
    raw["output"][0]["content"][0]["text"] = json.dumps(values)

    records = _failed(tmp_path, raw, request)

    assert records[0].validation_error_code == code
    assert records[0].structural_path == path


def test_identical_retry_failure_retains_both_attempts(tmp_path: Path) -> None:
    request = _request()
    raw = deepcopy(_raw(_response(request)))
    values = json.loads(raw["output"][0]["content"][0]["text"])
    values["observations"][0]["observation_status"] = "INVALID_ENUM"
    raw["output"][0]["content"][0]["text"] = json.dumps(values)

    records = _failed(tmp_path, raw, request, retries=1)

    assert [item.attempt for item in records] == [1, 2]
    assert [item.retry_disposition for item in records] == ["RETRY", "FAILED_FINAL"]
    assert len({item.validation_error_code for item in records}) == 1
    assert len({item.structural_path for item in records}) == 1


def test_raw_sensitive_model_text_is_never_persisted(tmp_path: Path) -> None:
    request = _request()
    raw = deepcopy(_raw(_response(request)))
    values = json.loads(raw["output"][0]["content"][0]["text"])
    values["observations"][0].update(
        observation_status="INVALID_ENUM",
        observation="sk-test-sensitive-model-prose",
    )
    raw["output"][0]["content"][0]["text"] = json.dumps(values)

    records = _failed(tmp_path, raw, request)
    persisted = "".join(
        path.read_text(encoding="utf-8")
        for path in (tmp_path / "diagnostics").rglob("*.json")
    )

    assert records[0].received_shape == "enum=INVALID_ENUM"
    assert "sk-test-sensitive-model-prose" not in persisted


def test_provider_rejection_is_retained_as_allowlisted_metadata_only(
    tmp_path: Path,
) -> None:
    request = _request(timeframe=VisualTimeframe.WEEKLY)
    store = LocalVisualEvidenceV2DiagnosticStore(tmp_path / "diagnostics")
    provider = OpenAIVisualEvidenceV2Provider(
        OpenAIVisualEvidenceV2Config(
            enabled=True,
            model_identity="gpt-5.6-sol",
            maximum_retries=0,
        ),
        transport=_RejectedTransport(),
        diagnostic_store=store,
    )

    with pytest.raises(ChartAnalystV2Error):
        provider.analyze(request)

    records = store.load_provider_errors()
    assert len(records) == 1
    assert records[0].http_status == 400
    assert records[0].error_code == "invalid_json_schema"
    assert records[0].timeframe is VisualTimeframe.WEEKLY
    persisted = "".join(
        path.read_text(encoding="utf-8")
        for path in (tmp_path / "diagnostics").rglob("*.json")
    )
    assert "original_image" not in persisted
    assert "Authorization" not in persisted
    assert request.chart_revision_sha256 not in persisted
