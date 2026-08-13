"""OpenAI Responses vision adapter for provider-neutral chart evidence."""

from __future__ import annotations

from base64 import b64encode
from dataclasses import dataclass
from datetime import datetime
import json
import os
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
    except (HTTPError, URLError, OSError, ValueError):
        raise OpenAITransportUnavailable("OPENAI_RESPONSE_UNAVAILABLE") from None
    if type(result) is not dict:
        raise OpenAITransportUnavailable("OPENAI_RESPONSE_INVALID")
    return result


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
    "OpenAIChartAnalystCapabilityProbe",
    "OpenAIChartEvidenceProvider",
    "OpenAIResponsesTransport",
    "OpenAITransportTimeout",
    "OpenAITransportUnavailable",
    "UrllibOpenAIResponsesTransport",
]
