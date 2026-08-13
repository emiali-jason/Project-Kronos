"""Durable cache, run binding, and sanitized cost telemetry for Chart Analyst V2."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import date, datetime
from hashlib import sha256
import json
from pathlib import Path
import re
from threading import RLock
from uuid import uuid4

from kronos.swing.v1.chart_analyst_v2 import (
    CHART_ANALYST_V2_QUESTION_SET_ID,
    CHART_ANALYST_V2_QUESTION_SET_VERSION,
    ChartAnalystProduct,
    ChartAnalystV2Request,
    ChartAnalystV2Response,
    chart_analyst_v2_response_from_dict,
    chart_analyst_v2_response_to_dict,
)
from kronos.swing.v1.chart_analyst_v2_integrity import (
    ChartAnalystV2IntegrityReport,
    chart_analyst_v2_integrity_report_to_dict,
)


DEFAULT_CHART_ANALYST_V2_ROOT = (
    Path.home()
    / "Library"
    / "Application Support"
    / "KRONOS"
    / "evidence"
    / "swing-v1"
    / "chart-analyst-v2"
)


@dataclass(frozen=True, slots=True)
class ChartAnalystV2CacheKey:
    image_sha256: str
    question_set_id: str
    question_set_version: str
    model_identity: str
    instrument: str
    product: ChartAnalystProduct

    def __post_init__(self) -> None:
        if (
            re.fullmatch(r"[0-9a-f]{64}", self.image_sha256) is None
            or self.question_set_id != CHART_ANALYST_V2_QUESTION_SET_ID
            or self.question_set_version != CHART_ANALYST_V2_QUESTION_SET_VERSION
            or not self.model_identity
            or len(self.model_identity) > 128
            or not self.instrument
            or len(self.instrument) > 128
            or type(self.product) is not ChartAnalystProduct
        ):
            raise ValueError("CHART_ANALYST_V2_CACHE_KEY_INVALID")

    @property
    def identity(self) -> str:
        serialized = json.dumps(
            {
                "image_sha256": self.image_sha256,
                "question_set_id": self.question_set_id,
                "question_set_version": self.question_set_version,
                "model_identity": self.model_identity,
                "instrument": self.instrument,
                "product": self.product.value,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(serialized.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ChartAnalystV2TelemetryEvent:
    timestamp: datetime
    model: str
    instrument: str
    product: ChartAnalystProduct
    image_hash: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    latency_ms: int
    retry_count: int
    cache_hit: bool
    question_set_version: str
    outcome: str

    def __post_init__(self) -> None:
        if (
            self.timestamp.tzinfo is None
            or self.timestamp.utcoffset() is None
            or not self.model
            or not self.instrument
            or type(self.product) is not ChartAnalystProduct
            or re.fullmatch(r"[0-9a-f]{64}", self.image_hash) is None
            or any(
                type(value) is not int or value < 0
                for value in (
                    self.input_tokens,
                    self.output_tokens,
                    self.total_tokens,
                    self.latency_ms,
                    self.retry_count,
                )
            )
            or self.total_tokens < self.input_tokens + self.output_tokens
            or type(self.estimated_cost_usd) is not float
            or self.estimated_cost_usd < 0.0
            or type(self.cache_hit) is not bool
            or self.question_set_version != CHART_ANALYST_V2_QUESTION_SET_VERSION
            or not self.outcome
            or len(self.outcome) > 128
        ):
            raise ValueError("CHART_ANALYST_V2_TELEMETRY_INVALID")


@dataclass(frozen=True, slots=True)
class ChartAnalystV2CostSummary:
    average_cost_per_chart_usd: float
    average_cost_per_probable_usd: float
    daily_api_cost_usd: float
    api_attempt_count: int
    cache_hit_count: int


class LocalChartAnalystV2Store:
    """Local evidence store that never receives or retains provider credentials."""

    def __init__(self, root: Path = DEFAULT_CHART_ANALYST_V2_ROOT) -> None:
        if not isinstance(root, Path):
            raise TypeError("CHART_ANALYST_V2_STORE_ROOT_INVALID")
        self._root = root
        self._lock = RLock()

    @property
    def root(self) -> Path:
        return self._root

    def cached_response(
        self,
        key: ChartAnalystV2CacheKey,
        *,
        run_identity: str,
        swing_analysis_run_identity: str,
        request_timestamp: datetime,
    ) -> ChartAnalystV2Response | None:
        if type(key) is not ChartAnalystV2CacheKey:
            raise TypeError("CHART_ANALYST_V2_CACHE_KEY_INVALID")
        path = self._cache_path(key)
        with self._lock:
            if not path.exists():
                return None
            try:
                envelope = json.loads(path.read_text(encoding="utf-8"))
                if (
                    type(envelope) is not dict
                    or envelope.get("schema") != "KRONOS_SWING_V1_CHART_ANALYST_V2_CACHE_V1"
                    or envelope.get("cache_key_identity") != key.identity
                ):
                    return None
                cached = chart_analyst_v2_response_from_dict(envelope["response"])
            except (OSError, KeyError, TypeError, ValueError):
                return None
        if (
            cached.model_identity != key.model_identity
            or cached.instrument != key.instrument
            or cached.product is not key.product
            or cached.image_sha256 != key.image_sha256
        ):
            return None
        return replace(
            cached,
            run_identity=run_identity,
            swing_analysis_run_identity=swing_analysis_run_identity,
            request_timestamp=request_timestamp,
            cache_hit=True,
        )

    def retain_success(
        self,
        key: ChartAnalystV2CacheKey,
        response: ChartAnalystV2Response,
    ) -> None:
        if type(key) is not ChartAnalystV2CacheKey or type(response) is not ChartAnalystV2Response:
            raise TypeError("CHART_ANALYST_V2_CACHE_VALUE_INVALID")
        if (
            response.cache_hit
            or response.model_identity != key.model_identity
            or response.instrument != key.instrument
            or response.product is not key.product
            or response.image_sha256 != key.image_sha256
        ):
            raise ValueError("CHART_ANALYST_V2_CACHE_BINDING_INVALID")
        payload = {
            "schema": "KRONOS_SWING_V1_CHART_ANALYST_V2_CACHE_V1",
            "cache_key_identity": key.identity,
            "cache_dimensions": {
                "image_sha256": key.image_sha256,
                "question_set_id": key.question_set_id,
                "question_set_version": key.question_set_version,
                "model_identity": key.model_identity,
                "instrument": key.instrument,
                "product": key.product.value,
            },
            "response": chart_analyst_v2_response_to_dict(response),
        }
        with self._lock:
            self._atomic_json(self._cache_path(key), payload)

    def retain_run_binding(self, response: ChartAnalystV2Response) -> Path:
        if type(response) is not ChartAnalystV2Response:
            raise TypeError("CHART_ANALYST_V2_RESPONSE_INVALID")
        run_hash = sha256(
            (
                response.swing_analysis_run_identity
                + "\x1f"
                + response.run_identity
            ).encode("utf-8")
        ).hexdigest()[:16]
        instrument = re.sub(r"[^A-Z0-9._&-]+", "-", response.instrument.upper())
        path = (
            self._root
            / "runs"
            / run_hash
            / instrument
            / f"{response.image_sha256}.json"
        )
        payload = {
            "schema": "KRONOS_SWING_V1_CHART_ANALYST_V2_RUN_BINDING_V1",
            "response": chart_analyst_v2_response_to_dict(response),
            "readiness": "NOT_IMPLEMENTED_IN_4E",
            "trade_construction": "NOT_IMPLEMENTED",
            "ranking": "NOT_PERFORMED",
        }
        with self._lock:
            self._atomic_json(path, payload)
        return path

    def retain_output_integrity_audit(
        self,
        *,
        request: ChartAnalystV2Request,
        model_identity: str,
        attempt: int,
        raw_model_output: str,
        raw_transcription: dict[str, object],
        report: ChartAnalystV2IntegrityReport,
    ) -> Path:
        """Retain untouched provider output beside deterministic validation."""

        if (
            type(request) is not ChartAnalystV2Request
            or not model_identity
            or len(model_identity) > 128
            or type(attempt) is not int
            or attempt not in {1, 2}
            or type(raw_model_output) is not str
            or not raw_model_output
            or type(raw_transcription) is not dict
            or type(report) is not ChartAnalystV2IntegrityReport
        ):
            raise TypeError("CHART_ANALYST_V2_INTEGRITY_AUDIT_INVALID")
        run_hash = sha256(
            (
                request.swing_analysis_run_identity
                + "\x1f"
                + request.run_identity
            ).encode("utf-8")
        ).hexdigest()[:16]
        instrument = re.sub(r"[^A-Z0-9._&-]+", "-", request.instrument.upper())
        path = (
            self._root
            / "integrity-audits"
            / run_hash
            / instrument
            / request.image_sha256
            / (
                request.request_timestamp.strftime("%Y%m%dT%H%M%S%f%z")
                + f"-attempt-{attempt}-{uuid4().hex}.json"
            )
        )
        payload = {
            "schema": "KRONOS_SWING_V1_CHART_ANALYST_V2_OUTPUT_INTEGRITY_V1",
            "binding": {
                "run_identity": request.run_identity,
                "swing_analysis_run_identity": request.swing_analysis_run_identity,
                "instrument": request.instrument,
                "product": request.product.value,
                "image_sha256": request.image_sha256,
                "question_set_id": request.question_set_id,
                "question_set_version": request.question_set_version,
                "model_identity": model_identity,
                "attempt": attempt,
            },
            "raw_model_output": raw_model_output,
            "raw_transcription": raw_transcription,
            "integrity": chart_analyst_v2_integrity_report_to_dict(report),
        }
        with self._lock:
            self._atomic_json(path, payload)
        return path

    def run_response(
        self,
        *,
        run_identity: str,
        swing_analysis_run_identity: str,
        instrument: str,
        image_sha256: str,
    ) -> ChartAnalystV2Response | None:
        if (
            not run_identity
            or not swing_analysis_run_identity
            or not instrument
            or re.fullmatch(r"[0-9a-f]{64}", image_sha256) is None
        ):
            raise ValueError("CHART_ANALYST_V2_RUN_BINDING_INVALID")
        run_hash = sha256(
            (swing_analysis_run_identity + "\x1f" + run_identity).encode("utf-8")
        ).hexdigest()[:16]
        safe_instrument = re.sub(r"[^A-Z0-9._&-]+", "-", instrument.upper())
        path = self._root / "runs" / run_hash / safe_instrument / f"{image_sha256}.json"
        with self._lock:
            if not path.exists():
                return None
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if (
                    payload.get("schema")
                    != "KRONOS_SWING_V1_CHART_ANALYST_V2_RUN_BINDING_V1"
                ):
                    return None
                response = chart_analyst_v2_response_from_dict(payload["response"])
            except (OSError, KeyError, TypeError, ValueError):
                return None
        if (
            response.run_identity != run_identity
            or response.swing_analysis_run_identity
            != swing_analysis_run_identity
            or response.instrument != instrument
            or response.image_sha256 != image_sha256
        ):
            return None
        return response

    def record_telemetry(self, event: ChartAnalystV2TelemetryEvent) -> None:
        if type(event) is not ChartAnalystV2TelemetryEvent:
            raise TypeError("CHART_ANALYST_V2_TELEMETRY_INVALID")
        payload = asdict(event)
        payload["timestamp"] = event.timestamp.isoformat()
        payload["product"] = event.product.value
        line = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
        path = self._root / "telemetry" / "attempts.jsonl"
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as target:
                target.write(line)

    def cost_summary(self, day: date) -> ChartAnalystV2CostSummary:
        if type(day) is not date:
            raise TypeError("CHART_ANALYST_V2_TELEMETRY_DATE_INVALID")
        path = self._root / "telemetry" / "attempts.jsonl"
        with self._lock:
            if not path.exists():
                events: tuple[dict[str, object], ...] = ()
            else:
                try:
                    events = tuple(
                        json.loads(line)
                        for line in path.read_text(encoding="utf-8").splitlines()
                        if line
                    )
                except (OSError, ValueError) as error:
                    raise ValueError("CHART_ANALYST_V2_TELEMETRY_INVALID") from error
        attempts = tuple(item for item in events if item.get("cache_hit") is False)
        costs = tuple(float(item["estimated_cost_usd"]) for item in attempts)
        chart_count = len({str(item["image_hash"]) for item in attempts})
        daily = sum(
            float(item["estimated_cost_usd"])
            for item in attempts
            if str(item.get("timestamp", "")).startswith(day.isoformat())
        )
        average = sum(costs) / chart_count if chart_count else 0.0
        return ChartAnalystV2CostSummary(
            average_cost_per_chart_usd=average,
            average_cost_per_probable_usd=average,
            daily_api_cost_usd=daily,
            api_attempt_count=len(attempts),
            cache_hit_count=sum(item.get("cache_hit") is True for item in events),
        )

    def _cache_path(self, key: ChartAnalystV2CacheKey) -> Path:
        return self._root / "cache" / key.identity[:2] / f"{key.identity}.json"

    @staticmethod
    def _atomic_json(path: Path, payload: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_text(
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


__all__ = [
    "DEFAULT_CHART_ANALYST_V2_ROOT",
    "ChartAnalystV2CacheKey",
    "ChartAnalystV2CostSummary",
    "ChartAnalystV2TelemetryEvent",
    "LocalChartAnalystV2Store",
]
