import json
from urllib.request import Request

import pytest

from kronos.configuration.credentials import OneUseSecretLease
from kronos.integrations.openai_chart_analyst import (
    OpenAIChartAnalystCapabilityProbe,
    OpenAITransportUnavailable,
    UrllibOpenAIResponsesTransport,
)


class _Source:
    def __init__(self, value: str | BaseException) -> None:
        self.value = value
        self.calls: list[str] = []
        self.lease: OneUseSecretLease | None = None

    def acquire(self, reference: str) -> OneUseSecretLease:
        self.calls.append(reference)
        if isinstance(self.value, BaseException):
            raise self.value
        self.lease = OneUseSecretLease(self.value)
        return self.lease


class _HTTPResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = json.dumps(payload).encode("utf-8")
        self.read_limits: list[int] = []

    def __enter__(self) -> "_HTTPResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, limit: int) -> bytes:
        self.read_limits.append(limit)
        return self.payload


class _Transport:
    def __init__(self, result: dict[str, object] | BaseException) -> None:
        self.result = result
        self.calls: list[tuple[dict[str, object], float]] = []

    def create_response(
        self,
        payload: dict[str, object],
        *,
        timeout_seconds: float,
    ) -> dict[str, object]:
        self.calls.append((payload, timeout_seconds))
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


def _completed_probe() -> dict[str, object]:
    return {
        "status": "completed",
        "output": [{
            "type": "message",
            "content": [{
                "type": "output_text",
                "text": json.dumps({"capability": "CONNECTED"}),
            }],
        }],
    }


def test_transport_uses_one_secret_lease_and_never_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api_key = "fake-openai-key-value"
    source = _Source(api_key)
    response = _HTTPResponse(_completed_probe())
    observed: list[Request] = []

    def fake_urlopen(request: Request, *, timeout: float) -> _HTTPResponse:
        assert timeout == 7.0
        observed.append(request)
        return response

    monkeypatch.setenv("OPENAI_API_KEY", "ignored-environment-value")
    monkeypatch.setattr(
        "kronos.integrations.openai_chart_analyst.urlopen",
        fake_urlopen,
    )
    transport = UrllibOpenAIResponsesTransport(
        credential_source=source,
        credential_ref="chart-analyst-primary",
    )

    result = transport.create_response(
        {"model": "gpt-test", "store": False, "input": "probe"},
        timeout_seconds=7.0,
    )

    assert result == _completed_probe()
    assert source.calls == ["chart-analyst-primary"]
    assert source.lease is not None and source.lease.closed
    assert observed[0].get_header("Authorization") == f"Bearer {api_key}"
    assert response.read_limits == [4 * 1024 * 1024 + 1]
    assert api_key not in repr(transport)


def test_transport_failure_is_sanitized_and_does_not_fall_back_to_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api_key = "fake-openai-key-value"
    monkeypatch.setenv("OPENAI_API_KEY", api_key)
    transport = UrllibOpenAIResponsesTransport(
        credential_source=_Source(RuntimeError(api_key)),
        credential_ref="chart-analyst-primary",
    )

    with pytest.raises(OpenAITransportUnavailable) as caught:
        transport.create_response({}, timeout_seconds=7.0)

    assert str(caught.value) == "OPENAI_CREDENTIAL_UNAVAILABLE"
    assert api_key not in str(caught.value)


def test_capability_probe_is_one_synthetic_non_swing_vision_request() -> None:
    transport = _Transport(_completed_probe())
    probe = OpenAIChartAnalystCapabilityProbe(
        transport=transport,
        model_identity="gpt-test",
        timeout_seconds=9.0,
    )

    assert probe.test_connection() is True
    assert len(transport.calls) == 1
    payload, timeout = transport.calls[0]
    serialized = json.dumps(payload)
    assert timeout == 9.0
    assert payload["model"] == "gpt-test"
    assert payload["store"] is False
    assert payload["max_output_tokens"] == 64
    assert payload["text"]["format"]["strict"] is True
    assert payload["input"][0]["content"][1]["image_url"].startswith(
        "data:image/png;base64,"
    )
    assert "SWING-V1-CHART-QUESTION-SET-V1" not in serialized
    assert "canonical_instrument" not in serialized
    assert "observation_boundary" not in serialized
    assert "source_image_sha256" not in serialized
    assert "question_set_identity" not in serialized
    assert "TradingView" not in serialized


def test_capability_probe_fails_closed_without_exposing_provider_details() -> None:
    transport = _Transport(RuntimeError("authorization bearer fake-sensitive"))
    probe = OpenAIChartAnalystCapabilityProbe(
        transport=transport,
        model_identity="gpt-test",
    )

    assert probe.test_connection() is False
    assert repr(probe) == "<OpenAIChartAnalystCapabilityProbe redacted>"
