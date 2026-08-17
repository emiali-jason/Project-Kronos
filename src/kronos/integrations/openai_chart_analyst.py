"""OpenAI Responses vision adapter for provider-neutral chart evidence."""

from __future__ import annotations

from base64 import b64encode
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import math
import os
import re
import socket
from threading import RLock
from time import monotonic
from typing import Callable, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from kronos.configuration.credentials import SecureCredentialSource
from kronos.swing.v1.chart_evidence import (
    CHART_EVIDENCE_SCHEMA_V1_ID,
    CHART_QUESTION_SET_V1_ID,
    FROZEN_CHART_QUESTION_SET_V1,
    OPENAI_CHART_EVIDENCE_PROVIDER_ID,
    ChartEvidenceProviderError,
    ChartEvidenceProviderFailureCode,
    ChartEvidenceRequest,
    ChartEvidenceResponse,
    chart_evidence_provider_schema,
    chart_evidence_response_from_dict,
)
from kronos.swing.v1.chart_analyst_v2 import (
    CHART_ANALYST_V2_EVIDENCE_FAMILIES,
    CHART_ANALYST_V2_QUESTION_SET_ID,
    CHART_ANALYST_V2_QUESTION_SET_VERSION,
    OPENAI_CHART_ANALYST_V2_PROVIDER_ID,
    ChartAnalystV2Error,
    ChartAnalystV2FailureCode,
    ChartAnalystV2Request,
    ChartAnalystV2Response,
    canonical_chart_analyst_v2_json,
    chart_analyst_v2_provider_schema,
)
from kronos.swing.v1.chart_analyst_v2_integrity import (
    ChartAnalystV2OutputIntegrityError,
    validate_chart_analyst_v2_output_integrity,
)
from kronos.swing.v1.chart_analyst_v2_store import (
    ChartAnalystV2CacheKey,
    ChartAnalystV2TelemetryEvent,
    LocalChartAnalystV2Store,
)
from kronos.swing.v1.visual_evidence_v2 import (
    FROZEN_VISUAL_QUESTION_SET_V2,
    LocalVisualEvidenceV2DiagnosticStore,
    OPENAI_VISUAL_EVIDENCE_V2_PROVIDER_ID,
    VISUAL_QUESTION_SET_V2_ID,
    VISUAL_QUESTION_SET_V2_VERSION,
    VisualEvidenceV2Observation,
    VisualEvidenceV2ProviderDiagnostic,
    VisualEvidenceV2Request,
    VisualEvidenceV2Response,
    VisualEvidenceV2ValidationDiagnostic,
    VisualEvidenceV2ValidationStage,
    VisualLevelAvailability,
    VisualObservationStatus,
    VisualQuestionV2,
    VISUAL_EVIDENCE_V2_PROVIDER_SCHEMA_VERSION,
    VISUAL_EVIDENCE_V2_SCHEMA,
    validate_visual_evidence_v2_provider_value,
    visual_evidence_v2_provider_schema,
)


_OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
_MAX_RESPONSE_BYTES = 4 * 1024 * 1024
_CONNECTION_PROBE_IMAGE = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAIAAAD8GO2jAAAAKUlEQVR4nO3NQQkAAAgE"
    "sAtkZLtqCh/CYP+lek5FIBAIBAKBQCAQfAkWBpccaiEwqQAAAAAASUVORK5CYII="
)


@dataclass(frozen=True, slots=True)
class OpenAIChartAnalystConfig:
    enabled: bool = False
    model_identity: str = "gpt-5.6"
    request_timeout_seconds: float = 45.0
    maximum_retries: int = 1
    question_set_identity: str = CHART_QUESTION_SET_V1_ID

    def __post_init__(self) -> None:
        if (
            type(self.enabled) is not bool
            or not self.model_identity
            or len(self.model_identity) > 128
            or type(self.request_timeout_seconds) is not float
            or not 1.0 <= self.request_timeout_seconds <= 180.0
            or type(self.maximum_retries) is not int
            or not 0 <= self.maximum_retries <= 2
            or self.question_set_identity != CHART_QUESTION_SET_V1_ID
        ):
            raise ValueError("OPENAI_CHART_ANALYST_CONFIG_INVALID")

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> OpenAIChartAnalystConfig:
        values = os.environ if environment is None else environment
        enabled = values.get("KRONOS_CHART_ANALYST_ENABLED", "false").strip().lower()
        if enabled not in {"true", "false"}:
            raise ValueError("OPENAI_CHART_ANALYST_CONFIG_INVALID")
        try:
            return cls(
                enabled=enabled == "true",
                model_identity=values.get("KRONOS_CHART_ANALYST_MODEL", "gpt-5.6"),
                request_timeout_seconds=float(values.get("KRONOS_CHART_ANALYST_TIMEOUT_SECONDS", "45")),
                maximum_retries=int(values.get("KRONOS_CHART_ANALYST_MAXIMUM_RETRIES", "1")),
                question_set_identity=values.get("KRONOS_CHART_ANALYST_QUESTION_SET", CHART_QUESTION_SET_V1_ID),
            )
        except (TypeError, ValueError) as error:
            raise ValueError("OPENAI_CHART_ANALYST_CONFIG_INVALID") from error


@dataclass(frozen=True, slots=True)
class ChartAnalystRequestAudit:
    request_timestamp: datetime
    run_identity: str
    canonical_instrument: str
    source_image_sha256: str
    attempt: int
    outcome: str


class OpenAITransportTimeout(TimeoutError):
    pass


class OpenAITransportUnavailable(RuntimeError):
    pass


class OpenAIProviderRequestRejected(OpenAITransportUnavailable):
    """Allowlisted provider error metadata; request content is never retained."""

    def __init__(
        self,
        *,
        http_status: int,
        error_type: str | None,
        error_code: str | None,
        rejected_parameter: str | None,
        provider_message: str | None,
    ) -> None:
        super().__init__("OPENAI_PROVIDER_REQUEST_REJECTED")
        self.http_status = http_status
        self.error_type = error_type
        self.error_code = error_code
        self.rejected_parameter = rejected_parameter
        self.provider_message = provider_message


class OpenAIResponsesTransport(Protocol):
    def create_response(
        self,
        payload: dict[str, object],
        *,
        timeout_seconds: float,
    ) -> dict[str, object]: ...


class _UnavailableOpenAIResponsesTransport:
    def create_response(
        self,
        _payload: dict[str, object],
        *,
        timeout_seconds: float,
    ) -> dict[str, object]:
        del timeout_seconds
        raise OpenAITransportUnavailable("OPENAI_CREDENTIAL_BOUNDARY_REQUIRED")


class UrllibOpenAIResponsesTransport:
    """Minimal HTTPS transport using one Configuration-owned secret lease."""

    __slots__ = ("_credential_ref", "_credential_source")

    def __init__(
        self,
        *,
        credential_source: SecureCredentialSource,
        credential_ref: str,
    ) -> None:
        if not credential_ref or not hasattr(credential_source, "acquire"):
            raise TypeError("OPENAI_TRANSPORT_CREDENTIAL_DEPENDENCY_INVALID")
        self._credential_source = credential_source
        self._credential_ref = credential_ref

    def create_response(
        self,
        payload: dict[str, object],
        *,
        timeout_seconds: float,
    ) -> dict[str, object]:
        try:
            lease = self._credential_source.acquire(self._credential_ref)
        except Exception:
            raise OpenAITransportUnavailable("OPENAI_CREDENTIAL_UNAVAILABLE") from None
        try:
            return lease.reveal_for_call(
                lambda api_key: _send_response_request(
                    payload,
                    timeout_seconds=timeout_seconds,
                    api_key=api_key,
                )
            )
        except OpenAITransportTimeout:
            raise
        except OpenAIProviderRequestRejected:
            raise
        except OpenAITransportUnavailable:
            raise
        except Exception:
            raise OpenAITransportUnavailable("OPENAI_RESPONSE_UNAVAILABLE") from None
        finally:
            lease.close()

    def __repr__(self) -> str:
        return "<UrllibOpenAIResponsesTransport redacted>"

    __str__ = __repr__

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("OPENAI_TRANSPORT_SERIALIZATION_PROHIBITED")


class OpenAIChartAnalystCapabilityProbe:
    """One bounded synthetic vision probe that cannot invoke Swing analysis."""

    __slots__ = ("_model_identity", "_timeout_seconds", "_transport")

    def __init__(
        self,
        *,
        transport: OpenAIResponsesTransport,
        model_identity: str,
        timeout_seconds: float = 15.0,
    ) -> None:
        if (
            not hasattr(transport, "create_response")
            or not model_identity
            or type(timeout_seconds) is not float
            or not 1.0 <= timeout_seconds <= 30.0
        ):
            raise TypeError("OPENAI_CAPABILITY_PROBE_DEPENDENCY_INVALID")
        self._transport = transport
        self._model_identity = model_identity
        self._timeout_seconds = timeout_seconds

    def test_connection(self) -> bool:
        try:
            raw = self._transport.create_response(
                _connection_probe_payload(self._model_identity),
                timeout_seconds=self._timeout_seconds,
            )
        except Exception:
            return False
        return _valid_connection_probe_response(raw)

    def __repr__(self) -> str:
        return "<OpenAIChartAnalystCapabilityProbe redacted>"

    __str__ = __repr__

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("OPENAI_CAPABILITY_PROBE_SERIALIZATION_PROHIBITED")


def _send_response_request(
    payload: dict[str, object],
    *,
    timeout_seconds: float,
    api_key: str,
) -> dict[str, object]:
    if not api_key:
        raise OpenAITransportUnavailable("OPENAI_CREDENTIAL_UNAVAILABLE")
    request = Request(
        _OPENAI_RESPONSES_URL,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
        if len(raw) > _MAX_RESPONSE_BYTES:
            raise OpenAITransportUnavailable("OPENAI_RESPONSE_INVALID")
        result = json.loads(raw.decode("utf-8"))
    except (TimeoutError, socket.timeout):
        raise OpenAITransportTimeout("OPENAI_RESPONSE_TIMEOUT") from None
    except HTTPError as error:
        raise _sanitized_provider_rejection(error) from None
    except (URLError, OSError, ValueError):
        raise OpenAITransportUnavailable("OPENAI_RESPONSE_UNAVAILABLE") from None
    if type(result) is not dict:
        raise OpenAITransportUnavailable("OPENAI_RESPONSE_INVALID")
    return result


def _sanitized_provider_rejection(error: HTTPError) -> OpenAIProviderRequestRejected:
    try:
        raw = error.read(64 * 1024 + 1)
        value = json.loads(raw[: 64 * 1024].decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        value = None
    detail = value.get("error") if type(value) is dict else None
    if type(detail) is not dict:
        detail = {}
    return OpenAIProviderRequestRejected(
        http_status=int(error.code),
        error_type=_safe_provider_error_text(detail.get("type"), 128),
        error_code=_safe_provider_error_text(detail.get("code"), 128),
        rejected_parameter=_safe_provider_error_text(detail.get("param"), 256),
        provider_message=_safe_provider_error_text(detail.get("message"), 512),
    )


def _safe_provider_error_text(value: object, maximum: int) -> str | None:
    if type(value) is not str:
        return None
    text = " ".join(value.split())
    text = re.sub(r"(?i)bearer\s+\S+", "Bearer [REDACTED]", text)
    text = re.sub(r"\bsk-[A-Za-z0-9_-]+", "[REDACTED]", text)
    text = re.sub(r"data:image/[^,\s]+,[A-Za-z0-9+/=_-]+", "[REDACTED_IMAGE]", text)
    return text[:maximum] or None


def _connection_probe_payload(model_identity: str) -> dict[str, object]:
    return {
        "model": model_identity,
        "store": False,
        "max_output_tokens": 64,
        "instructions": (
            "This is a capability-only connection probe. Inspect the synthetic "
            "solid-colour image and return only the required schema. Do not provide "
            "trading, market, instrument, readiness, or chart analysis."
        ),
        "input": [{
            "role": "user",
            "content": [
                {"type": "input_text", "text": "Confirm that image input is available."},
                {"type": "input_image", "image_url": _CONNECTION_PROBE_IMAGE, "detail": "low"},
            ],
        }],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "kronos_chart_analyst_connection_probe",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "capability": {"type": "string", "enum": ["CONNECTED"]},
                    },
                    "required": ["capability"],
                    "additionalProperties": False,
                },
            }
        },
    }


def _valid_connection_probe_response(raw: object) -> bool:
    if type(raw) is not dict or raw.get("status") != "completed":
        return False
    output = raw.get("output")
    if type(output) is not list:
        return False
    texts: list[str] = []
    for item in output:
        if type(item) is not dict or item.get("type") != "message":
            continue
        content = item.get("content")
        if type(content) is not list:
            continue
        for part in content:
            if (
                type(part) is dict
                and part.get("type") == "output_text"
                and type(part.get("text")) is str
            ):
                texts.append(part["text"])
    if len(texts) != 1:
        return False
    try:
        decoded = json.loads(texts[0])
    except (TypeError, ValueError):
        return False
    return decoded == {"capability": "CONNECTED"}


class OpenAIChartEvidenceProvider:
    def __init__(
        self,
        config: OpenAIChartAnalystConfig,
        *,
        transport: OpenAIResponsesTransport | None = None,
    ) -> None:
        if type(config) is not OpenAIChartAnalystConfig:
            raise TypeError("OPENAI_CHART_ANALYST_DEPENDENCY_INVALID")
        self._config = config
        self._transport = transport or _UnavailableOpenAIResponsesTransport()
        self._lock = RLock()
        self._audits: list[ChartAnalystRequestAudit] = []

    @property
    def provider_identity(self) -> str:
        return OPENAI_CHART_EVIDENCE_PROVIDER_ID

    @property
    def request_count(self) -> int:
        with self._lock:
            return len(self._audits)

    def request_audit(self) -> tuple[ChartAnalystRequestAudit, ...]:
        with self._lock:
            return tuple(self._audits)

    def analyze(self, request: ChartEvidenceRequest) -> ChartEvidenceResponse:
        if type(request) is not ChartEvidenceRequest:
            raise ValueError("CHART_EVIDENCE_REQUEST_INVALID")
        if not self._config.enabled:
            raise ChartEvidenceProviderError(ChartEvidenceProviderFailureCode.DISABLED)
        if request.question_set_identity != self._config.question_set_identity:
            raise ChartEvidenceProviderError(ChartEvidenceProviderFailureCode.INVALID_SCHEMA)

        provider_payload = _responses_payload(request, self._config.model_identity)
        maximum_attempts = self._config.maximum_retries + 1
        for attempt in range(1, maximum_attempts + 1):
            try:
                raw = self._transport.create_response(
                    provider_payload,
                    timeout_seconds=self._config.request_timeout_seconds,
                )
                response = _decode_response(raw, request, self._config.model_identity)
                response.validate_binding(request)
                response.require_usable_context()
            except OpenAITransportTimeout as error:
                self._record(request, attempt, ChartEvidenceProviderFailureCode.TIMEOUT.value)
                if attempt == maximum_attempts:
                    raise ChartEvidenceProviderError(ChartEvidenceProviderFailureCode.TIMEOUT) from error
            except OpenAITransportUnavailable as error:
                self._record(request, attempt, ChartEvidenceProviderFailureCode.UNAVAILABLE.value)
                if attempt == maximum_attempts:
                    raise ChartEvidenceProviderError(ChartEvidenceProviderFailureCode.UNAVAILABLE) from error
            except ChartEvidenceProviderError as error:
                self._record(request, attempt, error.code.value)
                raise
            else:
                self._record(request, attempt, "COMPLETED")
                return response
        raise AssertionError("OPENAI_CHART_ANALYST_RETRY_STATE_INVALID")

    def _record(self, request: ChartEvidenceRequest, attempt: int, outcome: str) -> None:
        with self._lock:
            self._audits.append(ChartAnalystRequestAudit(
                request_timestamp=request.request_timestamp,
                run_identity=request.run_identity,
                canonical_instrument=request.canonical_instrument,
                source_image_sha256=request.source_image_sha256,
                attempt=attempt,
                outcome=outcome,
            ))


def _responses_payload(request: ChartEvidenceRequest, model_identity: str) -> dict[str, object]:
    questions = ", ".join(item.value for item in FROZEN_CHART_QUESTION_SET_V1)
    context = request.thesis_context
    prompt = "\n".join((
        f"Question set: {CHART_QUESTION_SET_V1_ID}.",
        f"Instrument expected: {request.canonical_instrument}.",
        f"Timeframe expected: {request.timeframe.value}.",
        f"Template expected: {request.chart_template_identity}.",
        f"Observation boundary: {request.observation_boundary.isoformat()}.",
        "Layer-1 context is supplied only for factual contradiction checks:",
        f"setup={context.setup}; direction={context.direction.value}; structure={context.layer1_structure}; "
        f"sma20_slope={context.layer1_sma20_slope}; price_vs_sma20={context.layer1_price_vs_sma20}; "
        f"volume={context.layer1_volume_context}.",
        f"Answer every fixed domain: {questions}.",
    ))
    instructions = (
        "You are the KRONOS Chart Evidence Analyst. Interpret only facts visibly supported by the supplied "
        "TradingView chart and template metadata. Never recommend or decide BUY, SELL, LONG, SHORT, READY, "
        "WAIT, INVALIDATED, entry, stop, target, risk/reward, ranking, or trade viability. Do not infer a moving "
        "average solely from colour. Do not fabricate prices or volume values. Use UNDETERMINABLE or UNAVAILABLE "
        "when the image cannot safely support a field. Pine text is transcription only. Return only the strict schema."
    )
    data_url = f"data:{request.content_type};base64,{b64encode(request.original_image).decode('ascii')}"
    return {
        "model": model_identity,
        "store": False,
        "instructions": instructions,
        "input": [{
            "role": "user",
            "content": [
                {"type": "input_text", "text": prompt},
                {"type": "input_image", "image_url": data_url, "detail": "original"},
            ],
        }],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "kronos_swing_v1_chart_evidence",
                "strict": True,
                "schema": chart_evidence_provider_schema(),
            }
        },
    }


def _decode_response(
    raw: dict[str, object],
    request: ChartEvidenceRequest,
    model_identity: str,
) -> ChartEvidenceResponse:
    if raw.get("status") != "completed":
        raise ChartEvidenceProviderError(ChartEvidenceProviderFailureCode.INCOMPLETE)
    output = raw.get("output")
    if type(output) is not list:
        raise ChartEvidenceProviderError(ChartEvidenceProviderFailureCode.INVALID_SCHEMA)
    output_text: str | None = None
    for item in output:
        if type(item) is not dict or item.get("type") != "message":
            continue
        content = item.get("content")
        if type(content) is not list:
            continue
        for part in content:
            if type(part) is not dict:
                continue
            if part.get("type") == "refusal":
                raise ChartEvidenceProviderError(ChartEvidenceProviderFailureCode.REFUSAL)
            if part.get("type") == "output_text" and type(part.get("text")) is str:
                output_text = part["text"]
    if output_text is None:
        raise ChartEvidenceProviderError(ChartEvidenceProviderFailureCode.INVALID_SCHEMA)
    try:
        provider_result = json.loads(output_text)
    except (TypeError, ValueError) as error:
        raise ChartEvidenceProviderError(ChartEvidenceProviderFailureCode.INVALID_SCHEMA) from error
    if type(provider_result) is not dict:
        raise ChartEvidenceProviderError(ChartEvidenceProviderFailureCode.INVALID_SCHEMA)
    enriched: dict[str, object] = {
        "schema_identity": CHART_EVIDENCE_SCHEMA_V1_ID,
        "provider_identity": OPENAI_CHART_EVIDENCE_PROVIDER_ID,
        "model_identity": model_identity,
        "question_set_identity": request.question_set_identity,
        "request_timestamp": request.request_timestamp.isoformat(),
        "run_identity": request.run_identity,
        "canonical_instrument": request.canonical_instrument,
        "timeframe": request.timeframe.value,
        "observation_boundary": request.observation_boundary.isoformat(),
        "chart_template_identity": request.chart_template_identity,
        "source_image_sha256": request.source_image_sha256,
        **provider_result,
    }
    try:
        return chart_evidence_response_from_dict(enriched)
    except ValueError as error:
        raise ChartEvidenceProviderError(ChartEvidenceProviderFailureCode.INVALID_SCHEMA) from error


@dataclass(frozen=True, slots=True)
class OpenAIChartAnalystV2Config:
    """Bounded 4E configuration; total attempts can never exceed two."""

    enabled: bool = False
    model_identity: str = "gpt-5.6"
    request_timeout_seconds: float = 90.0
    maximum_retries: int = 1
    input_cost_per_million_usd: float = 5.0
    output_cost_per_million_usd: float = 30.0
    question_set_id: str = CHART_ANALYST_V2_QUESTION_SET_ID
    question_set_version: str = CHART_ANALYST_V2_QUESTION_SET_VERSION

    def __post_init__(self) -> None:
        if (
            type(self.enabled) is not bool
            or not self.model_identity
            or len(self.model_identity) > 128
            or type(self.request_timeout_seconds) is not float
            or not 1.0 <= self.request_timeout_seconds <= 180.0
            or type(self.maximum_retries) is not int
            or not 0 <= self.maximum_retries <= 1
            or type(self.input_cost_per_million_usd) is not float
            or self.input_cost_per_million_usd < 0.0
            or type(self.output_cost_per_million_usd) is not float
            or self.output_cost_per_million_usd < 0.0
            or self.question_set_id != CHART_ANALYST_V2_QUESTION_SET_ID
            or self.question_set_version != CHART_ANALYST_V2_QUESTION_SET_VERSION
        ):
            raise ValueError("OPENAI_CHART_ANALYST_V2_CONFIG_INVALID")

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> OpenAIChartAnalystV2Config:
        values = os.environ if environment is None else environment
        try:
            return cls(
                enabled=True,
                model_identity=values.get("KRONOS_CHART_ANALYST_MODEL", "gpt-5.6"),
                request_timeout_seconds=float(
                    values.get("KRONOS_CHART_ANALYST_TIMEOUT_SECONDS", "90")
                ),
                maximum_retries=int(
                    values.get("KRONOS_CHART_ANALYST_MAXIMUM_RETRIES", "1")
                ),
                input_cost_per_million_usd=float(
                    values.get("KRONOS_CHART_ANALYST_INPUT_COST_PER_MILLION_USD", "5")
                ),
                output_cost_per_million_usd=float(
                    values.get("KRONOS_CHART_ANALYST_OUTPUT_COST_PER_MILLION_USD", "30")
                ),
                question_set_id=values.get(
                    "KRONOS_CHART_ANALYST_QUESTION_SET",
                    CHART_ANALYST_V2_QUESTION_SET_ID,
                ),
                question_set_version=values.get(
                    "KRONOS_CHART_ANALYST_QUESTION_SET_VERSION",
                    CHART_ANALYST_V2_QUESTION_SET_VERSION,
                ),
            )
        except (TypeError, ValueError) as error:
            raise ValueError("OPENAI_CHART_ANALYST_V2_CONFIG_INVALID") from error


class OpenAIChartAnalystV2Provider:
    """One-screenshot/one-call Chart Analyst with bounded retry and cache."""

    def __init__(
        self,
        config: OpenAIChartAnalystV2Config,
        *,
        store: LocalChartAnalystV2Store,
        transport: OpenAIResponsesTransport | None = None,
        monotonic_clock: Callable[[], float] = monotonic,
        activation_probe: Callable[[], bool] | None = None,
    ) -> None:
        if (
            type(config) is not OpenAIChartAnalystV2Config
            or type(store) is not LocalChartAnalystV2Store
            or not callable(monotonic_clock)
            or (activation_probe is not None and not callable(activation_probe))
        ):
            raise TypeError("OPENAI_CHART_ANALYST_V2_DEPENDENCY_INVALID")
        self._config = config
        self._store = store
        self._transport = transport or _UnavailableOpenAIResponsesTransport()
        self._monotonic = monotonic_clock
        self._activation_probe = activation_probe
        self._lock = RLock()
        self._request_count = 0

    @property
    def provider_identity(self) -> str:
        return OPENAI_CHART_ANALYST_V2_PROVIDER_ID

    @property
    def request_count(self) -> int:
        with self._lock:
            return self._request_count

    @property
    def configuration_ready(self) -> bool:
        """Confirm the configured model and frozen question-set contract exist."""

        return bool(
            self._config.model_identity
            and self._config.question_set_id == CHART_ANALYST_V2_QUESTION_SET_ID
            and self._config.question_set_version
            == CHART_ANALYST_V2_QUESTION_SET_VERSION
        )

    @property
    def model_configured(self) -> bool:
        return bool(self._config.model_identity)

    @property
    def question_set_available(self) -> bool:
        return (
            self._config.question_set_id == CHART_ANALYST_V2_QUESTION_SET_ID
            and self._config.question_set_version
            == CHART_ANALYST_V2_QUESTION_SET_VERSION
        )

    def retained_response(
        self,
        *,
        run_identity: str,
        swing_analysis_run_identity: str,
        instrument: str,
        image_sha256: str,
    ) -> ChartAnalystV2Response | None:
        return self._store.run_response(
            run_identity=run_identity,
            swing_analysis_run_identity=swing_analysis_run_identity,
            instrument=instrument,
            image_sha256=image_sha256,
        )

    def analyze(self, request: ChartAnalystV2Request) -> ChartAnalystV2Response:
        if type(request) is not ChartAnalystV2Request:
            raise ValueError("CHART_ANALYST_V2_REQUEST_INVALID")
        enabled = (
            self._activation_probe()
            if self._activation_probe is not None
            else self._config.enabled
        )
        if enabled is not True:
            raise ChartAnalystV2Error(ChartAnalystV2FailureCode.DISABLED)
        if (
            request.question_set_id != self._config.question_set_id
            or request.question_set_version != self._config.question_set_version
        ):
            raise ChartAnalystV2Error(ChartAnalystV2FailureCode.INVALID_SCHEMA)

        cache_key = ChartAnalystV2CacheKey(
            image_sha256=request.image_sha256,
            question_set_id=request.question_set_id,
            question_set_version=request.question_set_version,
            model_identity=self._config.model_identity,
            instrument=request.instrument,
            product=request.product,
        )
        cached = self._store.cached_response(
            cache_key,
            run_identity=request.run_identity,
            swing_analysis_run_identity=request.swing_analysis_run_identity,
            request_timestamp=request.request_timestamp,
        )
        if cached is not None:
            cached.validate_binding(request)
            self._store.retain_run_binding(cached)
            self._record_v2_telemetry(
                request,
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                estimated_cost_usd=0.0,
                latency_ms=0,
                retry_count=0,
                cache_hit=True,
                outcome="CACHE_HIT",
            )
            return cached

        payload = _responses_v2_payload(request, self._config.model_identity)
        maximum_attempts = self._config.maximum_retries + 1
        for attempt in range(1, maximum_attempts + 1):
            started = self._monotonic()
            with self._lock:
                self._request_count += 1
            raw: dict[str, object] = {}
            try:
                raw = self._transport.create_response(
                    payload,
                    timeout_seconds=self._config.request_timeout_seconds,
                )
                raw_output_text, raw_analysis = _extract_v2_analysis(raw)
                try:
                    canonical_chart_analyst_v2_json(raw_analysis)
                except (TypeError, ValueError) as error:
                    raise ChartAnalystV2Error(
                        ChartAnalystV2FailureCode.INVALID_SCHEMA
                    ) from error
                integrity = validate_chart_analyst_v2_output_integrity(raw_analysis)
                self._store.retain_output_integrity_audit(
                    request=request,
                    model_identity=self._config.model_identity,
                    attempt=attempt,
                    raw_model_output=raw_output_text,
                    raw_transcription=raw_analysis,
                    report=integrity,
                )
                if not integrity.accepted:
                    raise ChartAnalystV2OutputIntegrityError(integrity)
                response = ChartAnalystV2Response(
                    provider_identity=OPENAI_CHART_ANALYST_V2_PROVIDER_ID,
                    model_identity=self._config.model_identity,
                    request_timestamp=request.request_timestamp,
                    run_identity=request.run_identity,
                    swing_analysis_run_identity=request.swing_analysis_run_identity,
                    analysis=raw_analysis,
                    cache_hit=False,
                )
                response.validate_binding(request)
            except OpenAITransportTimeout as error:
                code = ChartAnalystV2FailureCode.TIMEOUT
                retryable = True
                failure: BaseException = error
            except OpenAITransportUnavailable as error:
                code = ChartAnalystV2FailureCode.UNAVAILABLE
                retryable = True
                failure = error
            except ChartAnalystV2OutputIntegrityError as error:
                code = ChartAnalystV2FailureCode.INVALID_SCHEMA
                retryable = True
                failure = error
            except ChartAnalystV2Error as error:
                code = error.code
                retryable = code in {
                    ChartAnalystV2FailureCode.INCOMPLETE,
                    ChartAnalystV2FailureCode.INVALID_SCHEMA,
                }
                failure = error
            else:
                input_tokens, output_tokens, total_tokens = _v2_usage(raw)
                self._record_v2_telemetry(
                    request,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                    estimated_cost_usd=self._estimate_cost(input_tokens, output_tokens),
                    latency_ms=_latency_ms(started, self._monotonic()),
                    retry_count=attempt - 1,
                    cache_hit=False,
                    outcome="COMPLETED",
                )
                self._store.retain_success(cache_key, response)
                self._store.retain_run_binding(response)
                return response

            input_tokens, output_tokens, total_tokens = _v2_usage(raw)
            self._record_v2_telemetry(
                request,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                estimated_cost_usd=self._estimate_cost(input_tokens, output_tokens),
                latency_ms=_latency_ms(started, self._monotonic()),
                retry_count=attempt - 1,
                cache_hit=False,
                outcome=code.value,
            )
            if not retryable or attempt == maximum_attempts:
                raise ChartAnalystV2Error(code) from failure
        raise AssertionError("OPENAI_CHART_ANALYST_V2_RETRY_STATE_INVALID")

    def _estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return round(
            (
                input_tokens * self._config.input_cost_per_million_usd
                + output_tokens * self._config.output_cost_per_million_usd
            )
            / 1_000_000,
            8,
        )

    def _record_v2_telemetry(
        self,
        request: ChartAnalystV2Request,
        *,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
        estimated_cost_usd: float,
        latency_ms: int,
        retry_count: int,
        cache_hit: bool,
        outcome: str,
    ) -> None:
        self._store.record_telemetry(ChartAnalystV2TelemetryEvent(
            timestamp=request.request_timestamp,
            model=self._config.model_identity,
            instrument=request.instrument,
            product=request.product,
            image_hash=request.image_sha256,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=estimated_cost_usd,
            latency_ms=latency_ms,
            retry_count=retry_count,
            cache_hit=cache_hit,
            question_set_version=request.question_set_version,
            outcome=outcome,
        ))


@dataclass(frozen=True, slots=True)
class OpenAIVisualEvidenceV2Config:
    enabled: bool = False
    model_identity: str = "gpt-5.6"
    request_timeout_seconds: float = 90.0
    maximum_retries: int = 1
    question_set_identity: str = VISUAL_QUESTION_SET_V2_ID
    question_set_version: str = VISUAL_QUESTION_SET_V2_VERSION

    def __post_init__(self) -> None:
        if (
            type(self.enabled) is not bool
            or not self.model_identity
            or len(self.model_identity) > 128
            or type(self.request_timeout_seconds) is not float
            or not 1.0 <= self.request_timeout_seconds <= 180.0
            or type(self.maximum_retries) is not int
            or not 0 <= self.maximum_retries <= 2
            or self.question_set_identity != VISUAL_QUESTION_SET_V2_ID
            or self.question_set_version != VISUAL_QUESTION_SET_V2_VERSION
        ):
            raise ValueError("OPENAI_VISUAL_V2_CONFIG_INVALID")


class _VisualV2ValidationFailure(ValueError):
    def __init__(
        self,
        stage: VisualEvidenceV2ValidationStage,
        code: str,
        path: str,
        expected: str,
        received_shape: str,
    ) -> None:
        super().__init__(code)
        self.stage = stage
        self.code = code
        self.path = path
        self.expected = expected
        self.received_shape = received_shape


class OpenAIVisualEvidenceV2Provider:
    """Ten-question observation-only adapter using the governed transport."""

    def __init__(
        self,
        config: OpenAIVisualEvidenceV2Config,
        *,
        transport: OpenAIResponsesTransport | None = None,
        diagnostic_store: LocalVisualEvidenceV2DiagnosticStore | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if (
            type(config) is not OpenAIVisualEvidenceV2Config
            or (
                diagnostic_store is not None
                and type(diagnostic_store) is not LocalVisualEvidenceV2DiagnosticStore
            )
            or not callable(clock)
        ):
            raise TypeError("OPENAI_VISUAL_V2_DEPENDENCY_INVALID")
        self._config = config
        self._transport = transport or _UnavailableOpenAIResponsesTransport()
        self._lock = RLock()
        self._request_count = 0
        self._diagnostic_store = diagnostic_store
        self._clock = clock

    @property
    def provider_identity(self) -> str:
        return OPENAI_VISUAL_EVIDENCE_V2_PROVIDER_ID

    @property
    def request_count(self) -> int:
        with self._lock:
            return self._request_count

    def analyze(self, request: VisualEvidenceV2Request) -> VisualEvidenceV2Response:
        if type(request) is not VisualEvidenceV2Request:
            raise ValueError("VISUAL_V2_REQUEST_INVALID")
        if not self._config.enabled:
            raise ChartAnalystV2Error(ChartAnalystV2FailureCode.DISABLED)
        payload = _visual_v2_payload(request, self._config.model_identity)
        maximum_attempts = self._config.maximum_retries + 1
        for attempt in range(1, maximum_attempts + 1):
            with self._lock:
                self._request_count += 1
            raw: dict[str, object] | None = None
            try:
                raw = self._transport.create_response(
                    payload, timeout_seconds=self._config.request_timeout_seconds
                )
                response = _decode_visual_v2(raw, request, self._config.model_identity)
                try:
                    response.validate_binding(request)
                except ValueError as error:
                    code = str(error)
                    stage = (
                        VisualEvidenceV2ValidationStage.TIMEFRAME_ROUTING
                        if code in {
                            "VISUAL_V2_ROUTING_INVALID",
                            "VISUAL_V2_Q3_DUPLICATES_DETERMINISTIC_EVIDENCE",
                        }
                        else VisualEvidenceV2ValidationStage.PERSISTENCE_BINDING
                    )
                    raise _VisualV2ValidationFailure(
                        stage,
                        code,
                        "response.binding",
                        "response exactly bound to request and frozen routing",
                        "binding or routing mismatch",
                    ) from error
                return response
            except (OpenAITransportTimeout, OpenAITransportUnavailable) as error:
                if (
                    isinstance(error, OpenAIProviderRequestRejected)
                    and self._diagnostic_store is not None
                ):
                    self._diagnostic_store.retain_provider_error(
                        VisualEvidenceV2ProviderDiagnostic(
                            http_status=error.http_status,
                            error_type=error.error_type,
                            error_code=error.error_code,
                            rejected_parameter=error.rejected_parameter,
                            provider_message=error.provider_message,
                            model_identity=self._config.model_identity,
                            timeframe=request.timeframe,
                            schema_identity=VISUAL_EVIDENCE_V2_SCHEMA,
                            schema_version=VISUAL_EVIDENCE_V2_PROVIDER_SCHEMA_VERSION,
                            request_timestamp=request.request_timestamp,
                        )
                    )
                if attempt == maximum_attempts:
                    code = (
                        ChartAnalystV2FailureCode.TIMEOUT
                        if isinstance(error, OpenAITransportTimeout)
                        else ChartAnalystV2FailureCode.UNAVAILABLE
                    )
                    raise ChartAnalystV2Error(code) from error
            except (KeyError, TypeError, ValueError, ChartAnalystV2Error) as error:
                if isinstance(error, ChartAnalystV2Error) and error.code is ChartAnalystV2FailureCode.REFUSAL:
                    raise
                diagnostic_error = (
                    error
                    if isinstance(error, _VisualV2ValidationFailure)
                    else _diagnose_rejected_visual_v2(raw, request, error)
                )
                if diagnostic_error is not None:
                    self._retain_visual_v2_diagnostic(
                        request,
                        raw,
                        diagnostic_error,
                        attempt=attempt,
                        retry=attempt < maximum_attempts,
                    )
                if attempt == maximum_attempts:
                    raise ChartAnalystV2Error(
                        ChartAnalystV2FailureCode.INVALID_SCHEMA
                    ) from (diagnostic_error or error)
        raise AssertionError("OPENAI_VISUAL_V2_RETRY_STATE_INVALID")

    def _retain_visual_v2_diagnostic(
        self,
        request: VisualEvidenceV2Request,
        raw: dict[str, object] | None,
        error: _VisualV2ValidationFailure,
        *,
        attempt: int,
        retry: bool,
    ) -> None:
        if self._diagnostic_store is None:
            return
        recorded_at = self._clock()
        if recorded_at.tzinfo is None or recorded_at.utcoffset() is None:
            raise ValueError("OPENAI_VISUAL_V2_CLOCK_INVALID")
        input_tokens, output_tokens, total_tokens = (
            _v2_usage(raw) if raw is not None else (0, 0, 0)
        )
        status = raw.get("status") if raw is not None else "NOT_COMPLETED"
        response_status = status if type(status) is str and status else "UNKNOWN"
        self._diagnostic_store.retain(VisualEvidenceV2ValidationDiagnostic(
            native_run_identity=request.requirement.native_run_identity,
            canonical_instrument=request.requirement.canonical_instrument,
            timeframe=request.timeframe,
            chart_revision_sha256=request.chart_revision_sha256,
            model_identity=self._config.model_identity,
            attempt=attempt,
            api_request_completed=raw is not None,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            response_status=response_status[:64],
            validation_stage=error.stage,
            validation_error_code=error.code,
            structural_path=error.path,
            expected_constraint=error.expected,
            received_shape=error.received_shape,
            retry_disposition="RETRY" if retry else "FAILED_FINAL",
            recorded_at=recorded_at,
        ))


def _visual_v2_payload(
    request: VisualEvidenceV2Request,
    model_identity: str,
) -> dict[str, object]:
    facts = request.deterministic_context.timeframe_facts
    pivots = ", ".join(
        f"r{item.radius}:{item.kind.value}:{item.timestamp.isoformat()}:{item.price:g}"
        for item in facts.pivots
    ) or "NONE"
    references = ", ".join(
        f"{identity}:{low:g}" if high is None else f"{identity}:{low:g}-{high:g}"
        for identity, low, high in request.deterministic_context.known_reference_levels
    ) or "NONE"
    deterministic_range = (
        "NONE"
        if request.deterministic_context.deterministic_range_low is None
        else (
            f"{request.deterministic_context.deterministic_range_low:g}-"
            f"{request.deterministic_context.deterministic_range_high:g}"
        )
    )
    routing = ", ".join(f"{question.value}={route.value}" for question, route in request.routing)
    prompt = "\n".join((
        f"Question set: {VISUAL_QUESTION_SET_V2_ID} version {VISUAL_QUESTION_SET_V2_VERSION}.",
        f"Evidence subject: {request.subject_identity} ({request.subject_kind.value}).",
        f"Native instrument: {request.requirement.canonical_instrument}.",
        f"Expected timeframe: {request.timeframe.value}.",
        f"Completed observation boundary: {request.observation_boundary.isoformat()}.",
        f"Native opportunity orientation only: direction={request.requirement.thesis.direction.value}; "
        f"opportunity={request.requirement.thesis.opportunity_identity.value}.",
        f"Completed close={facts.close:g}; SMA20={facts.sma20}; SMA50={facts.sma50}; SMA200={facts.sma200}.",
        f"Completed volume={facts.volume}; prior-20 volume mean={facts.prior_20_volume_mean}.",
        f"Deterministic pivots already represented: {pivots}.",
        f"Deterministic range already represented: {deterministic_range}; "
        f"known break boundary={request.deterministic_context.known_break_boundary}.",
        f"Deterministic references already represented: {references}.",
        f"Operative anchor already represented: {request.requirement.thesis.operative_anchor_identity} "
        f"at {request.requirement.thesis.operative_anchor_price:g}.",
        f"Question routing: {routing}.",
        "Independently extract only requested visible evidence not already represented by supplied facts.",
    ))
    instructions = (
        "You are the bounded KRONOS Visual Evidence V2 extractor. Return factual visual observations only. "
        "Do not determine validity, tradability, Readiness, ACCEPT, WAIT, DISCARD, contradiction, material "
        "barrier, Clear-Air, entry, stop, invalidation, target, risk/reward, position size, execution, or broker "
        "state. Do not infer or approximate unreadable numeric values; use LEVEL_UNAVAILABLE. Q3 reports only "
        "material support/resistance missing from supplied deterministic references. Q8 transcribes visible Pine "
        "only. Q10 is NONE unless clearly visible material evidence cannot fit Q1-Q9. Return exactly ten ordered "
        "observations using the strict schema. Extraction confidence describes reading confidence only."
    )
    data_url = f"data:{request.content_type};base64,{b64encode(request.original_image).decode('ascii')}"
    return {
        "model": model_identity,
        "store": False,
        "max_output_tokens": 8_000,
        "instructions": instructions,
        "input": [{"role": "user", "content": [
            {"type": "input_text", "text": prompt},
            {"type": "input_image", "image_url": data_url, "detail": "original"},
        ]}],
        "text": {"format": {
            "type": "json_schema", "name": "kronos_swing_visual_evidence_v2",
            "strict": True, "schema": visual_evidence_v2_provider_schema(),
        }},
    }


def _decode_visual_v2(
    raw: dict[str, object],
    request: VisualEvidenceV2Request,
    model_identity: str,
) -> VisualEvidenceV2Response:
    text, value = _extract_v2_analysis(raw)
    del text
    validate_visual_evidence_v2_provider_value(value)
    if set(value) != {"observations"} or type(value["observations"]) is not list:
        raise ValueError("VISUAL_V2_SCHEMA_INVALID")
    expected_fields = {
        "question_id", "observation_status", "observation",
        "level_availability", "price", "zone_low", "zone_high",
        "visible_basis", "confidence_in_extraction", "ambiguity_reason",
        "why_not_covered_elsewhere",
    }
    if any(type(item) is not dict or set(item) != expected_fields for item in value["observations"]):
        raise ValueError("VISUAL_V2_SCHEMA_INVALID")
    observations = tuple(
        VisualEvidenceV2Observation(
            question_id=VisualQuestionV2(item["question_id"]),
            timeframe=request.timeframe,
            observation_status=VisualObservationStatus(item["observation_status"]),
            observation=item["observation"],
            level_availability=VisualLevelAvailability(item["level_availability"]),
            price=item["price"], zone_low=item["zone_low"], zone_high=item["zone_high"],
            visible_basis=item["visible_basis"],
            source_chart_identity=request.chart_identity,
            source_chart_revision=request.chart_revision_sha256,
            confidence_in_extraction=item["confidence_in_extraction"],
            ambiguity_reason=item["ambiguity_reason"],
            provenance=(OPENAI_VISUAL_EVIDENCE_V2_PROVIDER_ID, model_identity, VISUAL_QUESTION_SET_V2_ID),
            why_not_covered_elsewhere=item["why_not_covered_elsewhere"],
        )
        for item in value["observations"]
    )
    return VisualEvidenceV2Response(
        provider_identity=OPENAI_VISUAL_EVIDENCE_V2_PROVIDER_ID,
        model_identity=model_identity,
        request_timestamp=request.request_timestamp,
        native_run_identity=request.requirement.native_run_identity,
        native_assessment_sha256=request.requirement.thesis.native_assessment_sha256,
        native_canonical_instrument=request.requirement.canonical_instrument,
        subject_kind=request.subject_kind,
        subject_identity=request.subject_identity,
        reference_market=request.reference_market,
        reference_symbol=request.reference_symbol,
        timeframe=request.timeframe,
        observation_boundary=request.observation_boundary,
        chart_identity=request.chart_identity,
        chart_revision_sha256=request.chart_revision_sha256,
        observations=observations,
        source_provenance=(OPENAI_VISUAL_EVIDENCE_V2_PROVIDER_ID, model_identity),
    )


def _responses_v2_payload(
    request: ChartAnalystV2Request,
    model_identity: str,
) -> dict[str, object]:
    fixed_families = ", ".join(CHART_ANALYST_V2_EVIDENCE_FAMILIES)
    prompt = "\n".join((
        f"Question set: {request.question_set_id} version {request.question_set_version}.",
        f"Expected instrument: {request.instrument}.",
        f"Product: {request.product.value}.",
        f"Image SHA-256 binding: {request.image_sha256}.",
        "Expected panes: 1W, 1D, 4H, 1H.",
        f"Layer-1 hypothesis only: setup={request.thesis.setup}; direction={request.thesis.direction.value}.",
        f"Return every fixed evidence family: {fixed_families}.",
    ))
    instructions = (
        "You are the bounded KRONOS Swing Chart Analyst V2. Analyze each visible 1W, 1D, 4H, and 1H "
        "pane independently before cross-timeframe synthesis. Transcribe readable Pine workstation fields "
        "exactly. Use UNREADABLE or NOT_PRESENT for Pine fields as applicable; never reconstruct unreadable "
        "Pine text from chart appearance. Use UNDETERMINABLE whenever visible evidence is unclear. Do not "
        "guess numeric levels, ratios, or thresholds. Do not recommend or decide BUY, SELL, LONG, SHORT, "
        "Readiness, entry, stop, target, risk/reward, ranking, LIVE, PAPER, IGNORE, or execution. The next "
        "observable event must be a short factual market event, never an instruction. Return only strict JSON."
    )
    data_url = (
        f"data:{request.content_type};base64,"
        f"{b64encode(request.original_image).decode('ascii')}"
    )
    return {
        "model": model_identity,
        "store": False,
        "max_output_tokens": 12_000,
        "instructions": instructions,
        "input": [{
            "role": "user",
            "content": [
                {"type": "input_text", "text": prompt},
                {"type": "input_image", "image_url": data_url, "detail": "original"},
            ],
        }],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "kronos_swing_v1_chart_analyst_v2",
                "strict": True,
                "schema": chart_analyst_v2_provider_schema(),
            }
        },
    }


def _extract_v2_analysis(
    raw: dict[str, object],
) -> tuple[str, dict[str, object]]:
    if raw.get("status") != "completed":
        raise ChartAnalystV2Error(ChartAnalystV2FailureCode.INCOMPLETE)
    output = raw.get("output")
    if type(output) is not list:
        raise ChartAnalystV2Error(ChartAnalystV2FailureCode.INVALID_SCHEMA)
    texts: list[str] = []
    for item in output:
        if type(item) is not dict or item.get("type") != "message":
            continue
        content = item.get("content")
        if type(content) is not list:
            continue
        for part in content:
            if type(part) is not dict:
                continue
            if part.get("type") == "refusal":
                raise ChartAnalystV2Error(ChartAnalystV2FailureCode.REFUSAL)
            if part.get("type") == "output_text" and type(part.get("text")) is str:
                texts.append(part["text"])
    if len(texts) != 1:
        raise ChartAnalystV2Error(ChartAnalystV2FailureCode.INVALID_SCHEMA)
    try:
        analysis = json.loads(texts[0])
    except (TypeError, ValueError) as error:
        raise ChartAnalystV2Error(ChartAnalystV2FailureCode.INVALID_SCHEMA) from error
    if type(analysis) is not dict:
        raise ChartAnalystV2Error(ChartAnalystV2FailureCode.INVALID_SCHEMA)
    return texts[0], analysis


def _diagnose_rejected_visual_v2(
    raw: dict[str, object] | None,
    request: VisualEvidenceV2Request,
    error: BaseException,
) -> _VisualV2ValidationFailure | None:
    """Classify an already-rejected response without changing acceptance logic."""

    if raw is None:
        return None
    if raw.get("status") != "completed":
        return _visual_failure(
            VisualEvidenceV2ValidationStage.STRUCTURED_OUTPUT_DECODING,
            "V2_RESPONSE_NOT_COMPLETED", "status", "completed",
            _safe_enum_shape(raw.get("status")),
        )
    output = raw.get("output")
    if type(output) is not list:
        return _visual_failure(
            VisualEvidenceV2ValidationStage.STRUCTURED_OUTPUT_DECODING,
            "V2_STRUCTURED_OUTPUT_MISSING", "output", "Responses API output array",
            _safe_structural_shape(output),
        )
    texts: list[str] = []
    for item in output:
        if type(item) is not dict or item.get("type") != "message":
            continue
        content = item.get("content")
        if type(content) is not list:
            continue
        for part in content:
            if (
                type(part) is dict
                and part.get("type") == "output_text"
                and type(part.get("text")) is str
            ):
                texts.append(part["text"])
    if len(texts) != 1:
        return _visual_failure(
            VisualEvidenceV2ValidationStage.STRUCTURED_OUTPUT_DECODING,
            "V2_OUTPUT_TEXT_CARDINALITY_INVALID",
            "output[].content[].output_text",
            "exactly one structured output text",
            f"text count={len(texts)}",
        )
    try:
        value = json.loads(texts[0])
    except (TypeError, ValueError):
        return _visual_failure(
            VisualEvidenceV2ValidationStage.JSON_PARSING,
            "V2_JSON_INVALID", "output_text", "valid JSON object",
            f"string length={len(texts[0])}",
        )
    if type(value) is not dict:
        return _visual_failure(
            VisualEvidenceV2ValidationStage.TRANSPORT_TO_DOMAIN_ADAPTER,
            "V2_JSON_ROOT_INVALID", "$", "JSON object",
            _safe_structural_shape(value),
        )
    if set(value) != {"observations"}:
        return _visual_failure(
            VisualEvidenceV2ValidationStage.TRANSPORT_TO_DOMAIN_ADAPTER,
            "V2_TOP_LEVEL_SHAPE_INVALID", "$",
            "exact object with observations field", _safe_structural_shape(value),
        )
    observations = value["observations"]
    if type(observations) is not list:
        return _visual_failure(
            VisualEvidenceV2ValidationStage.TRANSPORT_TO_DOMAIN_ADAPTER,
            "V2_OBSERVATIONS_TYPE_INVALID", "observations",
            "array of exactly 10 observations", _safe_structural_shape(observations),
        )
    if len(observations) != len(FROZEN_VISUAL_QUESTION_SET_V2):
        return _visual_failure(
            VisualEvidenceV2ValidationStage.FROZEN_DOMAIN_INVARIANT,
            "V2_OBSERVATION_CARDINALITY_INVALID", "observations",
            "exactly 10 ordered observations", f"array length={len(observations)}",
        )
    expected_fields = {
        "question_id", "observation_status", "observation",
        "level_availability", "price", "zone_low", "zone_high",
        "visible_basis", "confidence_in_extraction", "ambiguity_reason",
        "why_not_covered_elsewhere",
    }
    for index, item in enumerate(observations):
        path = f"observations[{index}]"
        if type(item) is not dict or set(item) != expected_fields:
            return _visual_failure(
                VisualEvidenceV2ValidationStage.TRANSPORT_TO_DOMAIN_ADAPTER,
                "V2_OBSERVATION_SHAPE_INVALID", path,
                "exact frozen observation fields", _safe_structural_shape(item),
            )
        diagnosed = _diagnose_visual_v2_observation(item, index)
        if diagnosed is not None:
            return diagnosed
    expected_questions = tuple(item.value for item in FROZEN_VISUAL_QUESTION_SET_V2)
    actual_questions = tuple(item["question_id"] for item in observations)
    if actual_questions != expected_questions:
        mismatch = next(
            index for index, (actual, expected) in enumerate(
                zip(actual_questions, expected_questions, strict=True)
            ) if actual != expected
        )
        return _visual_failure(
            VisualEvidenceV2ValidationStage.FROZEN_DOMAIN_INVARIANT,
            "V2_QUESTION_IDENTITY_ORDER_INVALID",
            f"observations[{mismatch}].question_id",
            expected_questions[mismatch], _safe_enum_shape(actual_questions[mismatch]),
        )
    code = str(error)
    if code in {
        "VISUAL_V2_ROUTING_INVALID",
        "VISUAL_V2_Q3_DUPLICATES_DETERMINISTIC_EVIDENCE",
    }:
        return _visual_failure(
            VisualEvidenceV2ValidationStage.TIMEFRAME_ROUTING,
            code, "observations", "frozen timeframe routing and deterministic gap",
            f"timeframe={request.timeframe.value}",
        )
    return _visual_failure(
        VisualEvidenceV2ValidationStage.FROZEN_DOMAIN_INVARIANT,
        "V2_DOMAIN_INVARIANT_UNCLASSIFIED", "observations",
        "frozen Visual Evidence V2 domain invariants", type(error).__name__,
    )


def _diagnose_visual_v2_observation(
    item: dict[str, object], index: int,
) -> _VisualV2ValidationFailure | None:
    path = f"observations[{index}]"
    enums = (
        ("question_id", VisualQuestionV2),
        ("observation_status", VisualObservationStatus),
        ("level_availability", VisualLevelAvailability),
    )
    converted: dict[str, object] = {}
    for field, enum_type in enums:
        try:
            converted[field] = enum_type(item[field])
        except (TypeError, ValueError):
            return _visual_failure(
                VisualEvidenceV2ValidationStage.TRANSPORT_TO_DOMAIN_ADAPTER,
                "V2_ENUM_INVALID", f"{path}.{field}",
                f"one of {','.join(value.value for value in enum_type)}",
                _safe_enum_shape(item[field]),
            )
    for field, maximum, nullable in (
        ("observation", 512, False), ("visible_basis", 512, False),
        ("confidence_in_extraction", 64, False),
        ("ambiguity_reason", 512, False),
        ("why_not_covered_elsewhere", 512, True),
    ):
        value = item[field]
        valid = (
            (nullable and value is None)
            or (
                type(value) is str and len(value) <= maximum
                and (bool(value.strip()) or field == "ambiguity_reason")
            )
        )
        if not valid:
            return _visual_failure(
                VisualEvidenceV2ValidationStage.TRANSPORT_TO_DOMAIN_ADAPTER,
                "V2_TEXT_FIELD_INVALID", f"{path}.{field}",
                f"{'nullable ' if nullable else ''}bounded text max {maximum}",
                _safe_structural_shape(value),
            )
    for field in ("price", "zone_low", "zone_high"):
        value = item[field]
        if value is not None and (
            type(value) is not float or not math.isfinite(value) or value < 0.0
        ):
            return _visual_failure(
                VisualEvidenceV2ValidationStage.TRANSPORT_TO_DOMAIN_ADAPTER,
                "V2_NUMERIC_LEVEL_INVALID", f"{path}.{field}",
                "null or finite non-negative number", _safe_structural_shape(value),
            )
    status = converted["observation_status"]
    availability = converted["level_availability"]
    exact = item["price"] is not None
    low, high = item["zone_low"], item["zone_high"]
    zone = low is not None or high is not None
    if (low is None) != (high is None):
        return _visual_level_failure(
            "V2_ZONE_PAIR_INCOMPLETE", path,
            "zone_low and zone_high are both present or both null", item,
        )
    if low is not None and high is not None and low > high:
        return _visual_level_failure(
            "V2_ZONE_ORDER_INVALID", path, "zone_low must not exceed zone_high", item,
        )
    if exact and zone:
        return _visual_level_failure(
            "V2_PRICE_ZONE_EXCLUSIVITY_INVALID", path,
            "price and bounded zone are mutually exclusive", item,
        )
    if availability is VisualLevelAvailability.AVAILABLE and exact == zone:
        return _visual_level_failure(
            "V2_LEVEL_AVAILABILITY_INCONSISTENT", path,
            "AVAILABLE requires exactly one valid point or bounded zone", item,
        )
    if availability is not VisualLevelAvailability.AVAILABLE and (exact or zone):
        return _visual_level_failure(
            "V2_LEVEL_AVAILABILITY_INCONSISTENT", path,
            "non-AVAILABLE level requires no numeric point or zone", item,
        )
    if status is not VisualObservationStatus.OBSERVED and availability is VisualLevelAvailability.AVAILABLE:
        return _visual_level_failure(
            "V2_OBSERVATION_LEVEL_STATUS_INVALID", path,
            "only OBSERVED may publish an AVAILABLE level", item,
        )
    if status in {
        VisualObservationStatus.PARTIAL,
        VisualObservationStatus.UNAVAILABLE,
        VisualObservationStatus.INVALID,
    } and not item["ambiguity_reason"].strip():
        return _visual_failure(
            VisualEvidenceV2ValidationStage.FROZEN_DOMAIN_INVARIANT,
            "V2_AMBIGUITY_REASON_REQUIRED", f"{path}.ambiguity_reason",
            f"non-empty reason when observation_status={status.value}", "empty string",
        )
    question = converted["question_id"]
    why = item["why_not_covered_elsewhere"]
    if question is VisualQuestionV2.VISUAL_FACTS_NOT_CAPTURED_BY_KRONOS:
        if item["observation"] == "NONE" and why is not None:
            return _visual_failure(
                VisualEvidenceV2ValidationStage.FROZEN_DOMAIN_INVARIANT,
                "V2_Q10_NONE_SEMANTICS_INVALID",
                f"{path}.why_not_covered_elsewhere",
                "null when Q10 observation is NONE", _safe_structural_shape(why),
            )
        if item["observation"] != "NONE" and (
            type(why) is not str or not why.strip()
        ):
            return _visual_failure(
                VisualEvidenceV2ValidationStage.FROZEN_DOMAIN_INVARIANT,
                "V2_Q10_WHY_REQUIRED", f"{path}.why_not_covered_elsewhere",
                "non-empty bounded reason when Q10 is not NONE",
                _safe_structural_shape(why),
            )
    elif why is not None:
        return _visual_failure(
            VisualEvidenceV2ValidationStage.FROZEN_DOMAIN_INVARIANT,
            "V2_NON_Q10_WHY_PROHIBITED", f"{path}.why_not_covered_elsewhere",
            "null outside Q10", _safe_structural_shape(why),
        )
    prohibited = _first_visual_prohibited_token(item)
    if prohibited is not None:
        return _visual_failure(
            VisualEvidenceV2ValidationStage.FROZEN_DOMAIN_INVARIANT,
            "V2_PROHIBITED_ANALYTICAL_CONSEQUENCE", path,
            "observation-only content without analytical or execution consequence",
            f"prohibited token={prohibited}",
        )
    return None


def _visual_failure(
    stage: VisualEvidenceV2ValidationStage,
    code: str,
    path: str,
    expected: str,
    received: str,
) -> _VisualV2ValidationFailure:
    return _VisualV2ValidationFailure(stage, code, path, expected, received)


def _visual_level_failure(
    code: str, path: str, expected: str, item: dict[str, object],
) -> _VisualV2ValidationFailure:
    availability = _safe_enum_shape(item.get("level_availability"))
    point = "present" if item.get("price") is not None else "null"
    zone = (
        "present"
        if item.get("zone_low") is not None or item.get("zone_high") is not None
        else "null"
    )
    return _visual_failure(
        VisualEvidenceV2ValidationStage.FROZEN_DOMAIN_INVARIANT,
        code, path, expected,
        f"{availability} + price={point} + zone={zone}",
    )


def _safe_structural_shape(value: object) -> str:
    if value is None:
        return "null"
    if type(value) is dict:
        return f"object keys={','.join(sorted(str(key) for key in value))}"[:512]
    if type(value) is list:
        return f"array length={len(value)}"
    if type(value) is str:
        return f"string length={len(value)}"
    return type(value).__name__


def _safe_enum_shape(value: object) -> str:
    if type(value) is str and re.fullmatch(r"[A-Z0-9_]{1,64}", value):
        return f"enum={value}"
    return _safe_structural_shape(value)


def _first_visual_prohibited_token(item: dict[str, object]) -> str | None:
    material = " ".join(
        value for value in (
            item.get("observation"), item.get("visible_basis"),
            item.get("ambiguity_reason"), item.get("why_not_covered_elsewhere"),
        ) if type(value) is str
    ).upper()
    normalized = re.sub(r"[^A-Z]+", "_", material).strip("_")
    for token in (
        "CLEAR_AIR", "NO_CLEAR_AIR", "PATH_CLEAR", "PATH_BLOCKED",
        "MATERIAL_BARRIER", "ACCEPT", "DISCARD", "BUY", "SELL",
        "ENTRY_ZONE", "RISK_REWARD", "POSITION_SIZE", "BROKER_ORDER",
    ):
        if re.search(rf"(?:^|_){re.escape(token)}(?:_|$)", normalized):
            return token
    return None


def _v2_usage(raw: dict[str, object]) -> tuple[int, int, int]:
    usage = raw.get("usage")
    if type(usage) is not dict:
        return 0, 0, 0
    values = tuple(
        usage.get(key, 0)
        for key in ("input_tokens", "output_tokens", "total_tokens")
    )
    if any(type(item) is not int or item < 0 for item in values):
        return 0, 0, 0
    input_tokens, output_tokens, total_tokens = values
    return input_tokens, output_tokens, max(total_tokens, input_tokens + output_tokens)


def _latency_ms(started: float, finished: float) -> int:
    if type(started) not in {int, float} or type(finished) not in {int, float}:
        return 0
    return max(0, round((finished - started) * 1000))


__all__ = [
    "ChartAnalystRequestAudit",
    "OpenAIChartAnalystConfig",
    "OpenAIChartAnalystV2Config",
    "OpenAIChartAnalystV2Provider",
    "OpenAIProviderRequestRejected",
    "OpenAIVisualEvidenceV2Provider",
    "OpenAIVisualEvidenceV2Config",
    "OpenAIChartAnalystCapabilityProbe",
    "OpenAIChartEvidenceProvider",
    "OpenAIResponsesTransport",
    "OpenAITransportTimeout",
    "OpenAITransportUnavailable",
    "UrllibOpenAIResponsesTransport",
]
