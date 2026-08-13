"""Durable, append-only local storage for Sponsor TradingView evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, is_dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from threading import RLock
from typing import Callable
from uuid import uuid4

from kronos.swing.v1.tradingview import (
    ChartTimeframe,
    TRADINGVIEW_RETENTION_CLASS,
    TRADINGVIEW_UPLOAD_SOURCE,
    TradingViewReviewRequirement,
    TradingViewReviewStatus,
    missing_timeframes,
    pending_layer2_evidence,
)
from kronos.swing.v1.chart_evidence import (
    ChartEvidenceProviderFailureCode,
    ChartEvidenceResponse,
    chart_evidence_response_from_dict,
    chart_evidence_response_to_dict,
)
from kronos.swing.v1.chart_analyst_v2_layer2 import (
    CHART_ANALYST_V2_LAYER2_SCHEMA_ID,
    ChartAnalystV2Layer2Record,
    chart_analyst_v2_layer2_record_from_dict,
    chart_analyst_v2_layer2_record_to_dict,
)
from kronos.swing.v1.layer2 import (
    Layer2ReviewRecord,
    layer2_record_from_dict,
    layer2_record_to_dict,
)
import kronos.swing.v1.models as v1_models
from kronos.swing.v1.models import V1Layer1Run
from kronos.swing.universe import SwingUniverseAssetClass
from kronos.swing.run_identity import (
    LEGACY_UNBOUND_SWING_RUN_ID,
    is_swing_analysis_run_id,
    is_swing_run_binding,
)


DEFAULT_V1_EVIDENCE_ROOT = (
    Path.home() / "Library" / "Application Support" / "KRONOS" / "evidence" / "swing-v1"
)
_MAX_CHART_BYTES = 25 * 1024 * 1024
_CONTENT_TYPES = {
    "image/png": (".png", b"\x89PNG\r\n\x1a\n"),
    "image/jpeg": (".jpg", b"\xff\xd8\xff"),
    "image/webp": (".webp", b"RIFF"),
}
_V1_REVIEW_RUN_SCHEMA_ID = "KRONOS_SWING_V1_REVIEW_RUN_V1"
_V1_REVIEW_TYPES = {
    name: value
    for name, value in vars(v1_models).items()
    if isinstance(value, type)
    and (
        is_dataclass(value)
        or issubclass(value, StrEnum)
    )
}
_V1_REVIEW_TYPES[SwingUniverseAssetClass.__name__] = SwingUniverseAssetClass


class TradingViewEvidenceStoreError(ValueError):
    """Typed boundary failure with no uploaded data in the message."""


class StoredChartAnalysisState(StrEnum):
    COMPLETE = "COMPLETE"
    CONTEXT_INCOMPLETE = "CONTEXT_INCOMPLETE"
    CHART_ANALYSIS_UNAVAILABLE = "CHART_ANALYSIS_UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class StoredChartAnalysis:
    state: StoredChartAnalysisState
    source_image_hashes: tuple[str, ...]
    provider_request_count: int
    responses: tuple[ChartEvidenceResponse, ...]
    layer2_record: Layer2ReviewRecord | None
    failure_code: ChartEvidenceProviderFailureCode | None

    def __post_init__(self) -> None:
        if (
            type(self.state) is not StoredChartAnalysisState
            or type(self.source_image_hashes) is not tuple
            or not self.source_image_hashes
            or len(set(self.source_image_hashes)) != len(self.source_image_hashes)
            or any(re.fullmatch(r"[0-9a-f]{64}", item) is None for item in self.source_image_hashes)
            or type(self.provider_request_count) is not int
            or self.provider_request_count < 0
            or type(self.responses) is not tuple
            or any(type(item) is not ChartEvidenceResponse for item in self.responses)
            or (
                self.layer2_record is not None
                and type(self.layer2_record) is not Layer2ReviewRecord
            )
            or (
                self.failure_code is not None
                and type(self.failure_code) is not ChartEvidenceProviderFailureCode
            )
            or (
                self.state is StoredChartAnalysisState.COMPLETE
                and (self.layer2_record is None or self.failure_code is not None)
            )
            or (
                self.state is not StoredChartAnalysisState.COMPLETE
                and (self.layer2_record is not None or self.failure_code is None)
            )
        ):
            raise ValueError("TRADINGVIEW_STORED_CHART_ANALYSIS_INVALID")


@dataclass(frozen=True, slots=True)
class StoredChartRevision:
    run_identity: str
    canonical_instrument: str
    observation_boundary: datetime
    timeframe: ChartTimeframe
    upload_timestamp: datetime
    chart_template_identity: str
    source: str
    retention_class: str
    revision: int
    sha256: str
    byte_count: int
    content_type: str
    relative_path: str
    swing_analysis_run_identity: str = LEGACY_UNBOUND_SWING_RUN_ID

    def __post_init__(self) -> None:
        if (
            not self.run_identity
            or not is_swing_run_binding(self.swing_analysis_run_identity)
            or not self.canonical_instrument
            or self.observation_boundary.tzinfo is None
            or self.observation_boundary.utcoffset() is None
            or type(self.timeframe) is not ChartTimeframe
            or self.upload_timestamp.tzinfo is None
            or self.upload_timestamp.utcoffset() is None
            or self.source != TRADINGVIEW_UPLOAD_SOURCE
            or self.retention_class != TRADINGVIEW_RETENTION_CLASS
            or type(self.revision) is not int
            or self.revision < 1
            or re.fullmatch(r"[0-9a-f]{64}", self.sha256) is None
            or type(self.byte_count) is not int
            or self.byte_count < 1
            or self.content_type not in _CONTENT_TYPES
            or Path(self.relative_path).is_absolute()
            or ".." in Path(self.relative_path).parts
        ):
            raise ValueError("TRADINGVIEW_STORED_REVISION_INVALID")


@dataclass(frozen=True, slots=True)
class TradingViewEvidencePackage:
    requirement: TradingViewReviewRequirement
    revisions: tuple[StoredChartRevision, ...]
    active_revisions: tuple[StoredChartRevision, ...]
    missing_required_timeframes: tuple[ChartTimeframe, ...]
    context_status: TradingViewReviewStatus
    structured_evidence_path: str

    def __post_init__(self) -> None:
        active_timeframes = {item.timeframe for item in self.active_revisions}
        expected_missing = missing_timeframes(self.requirement, active_timeframes)
        expected_status = (
            TradingViewReviewStatus.TRADINGVIEW_CONTEXT_RECEIVED
            if not expected_missing
            else TradingViewReviewStatus.CONTEXT_INCOMPLETE
            if self.active_revisions
            else TradingViewReviewStatus.TRADINGVIEW_REVIEW_REQUIRED
        )
        if (
            type(self.requirement) is not TradingViewReviewRequirement
            or type(self.revisions) is not tuple
            or any(type(item) is not StoredChartRevision for item in self.revisions)
            or type(self.active_revisions) is not tuple
            or any(type(item) is not StoredChartRevision for item in self.active_revisions)
            or len(active_timeframes) != len(self.active_revisions)
            or any(item not in self.revisions for item in self.active_revisions)
            or self.missing_required_timeframes != expected_missing
            or self.context_status is not expected_status
            or Path(self.structured_evidence_path).is_absolute()
            or ".." in Path(self.structured_evidence_path).parts
        ):
            raise ValueError("TRADINGVIEW_EVIDENCE_PACKAGE_INVALID")


class LocalTradingViewEvidenceStore:
    """Run-scoped storage with atomic metadata writes and preserved revisions."""

    def __init__(
        self,
        root: Path = DEFAULT_V1_EVIDENCE_ROOT,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        root = Path(root).expanduser()
        private_tmp = Path("/private/tmp")
        if (
            not root.is_absolute()
            or root == private_tmp
            or private_tmp in root.parents
            or not callable(clock)
        ):
            raise ValueError("TRADINGVIEW_EVIDENCE_ROOT_INVALID")
        self._root = root
        self._clock = clock
        self._lock = RLock()

    @property
    def root(self) -> Path:
        return self._root

    def retain_review_run(
        self,
        run: V1Layer1Run,
        *,
        swing_analysis_run_identity: str,
    ) -> None:
        """Retain the selected immutable Layer-1 review population across restarts."""

        if (
            type(run) is not V1Layer1Run
            or not is_swing_analysis_run_id(swing_analysis_run_identity)
        ):
            raise TradingViewEvidenceStoreError("V1_REVIEW_RUN_INVALID")
        payload = {
            "schema": _V1_REVIEW_RUN_SCHEMA_ID,
            "swing_analysis_run_identity": swing_analysis_run_identity,
            "layer1_run": _encode_v1_review_value(run),
        }
        path = self._review_run_path(swing_analysis_run_identity)
        with self._lock:
            if path.exists():
                recovered_parent, recovered_run = self._read_review_run(path)
                if (
                    recovered_parent != swing_analysis_run_identity
                    or recovered_run != run
                ):
                    raise TradingViewEvidenceStoreError(
                        "V1_REVIEW_RUN_IMMUTABLE"
                    )
            else:
                self._atomic_json(path, payload)
            self._atomic_json(
                self._root / "review-runs" / "active-review.json",
                {
                    "schema": _V1_REVIEW_RUN_SCHEMA_ID,
                    "swing_analysis_run_identity": (
                        swing_analysis_run_identity
                    ),
                },
            )

    def latest_review_run(self) -> tuple[str, V1Layer1Run] | None:
        pointer = self._root / "review-runs" / "active-review.json"
        with self._lock:
            if not pointer.exists():
                return None
            try:
                payload = json.loads(pointer.read_text(encoding="utf-8"))
                parent = payload["swing_analysis_run_identity"]
            except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
                raise TradingViewEvidenceStoreError(
                    "V1_REVIEW_RUN_INVALID"
                ) from error
            if (
                set(payload) != {"schema", "swing_analysis_run_identity"}
                or payload["schema"] != _V1_REVIEW_RUN_SCHEMA_ID
                or not is_swing_analysis_run_id(parent)
            ):
                raise TradingViewEvidenceStoreError("V1_REVIEW_RUN_INVALID")
            return self._read_review_run(self._review_run_path(parent))

    def _review_run_path(self, swing_analysis_run_identity: str) -> Path:
        return (
            self._root
            / "review-runs"
            / swing_analysis_run_identity
            / "layer1-review.json"
        )

    @staticmethod
    def _read_review_run(path: Path) -> tuple[str, V1Layer1Run]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            parent = payload["swing_analysis_run_identity"]
            run = _decode_v1_review_value(payload["layer1_run"])
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise TradingViewEvidenceStoreError("V1_REVIEW_RUN_INVALID") from error
        if (
            set(payload)
            != {"schema", "swing_analysis_run_identity", "layer1_run"}
            or payload["schema"] != _V1_REVIEW_RUN_SCHEMA_ID
            or not is_swing_analysis_run_id(parent)
            or type(run) is not V1Layer1Run
        ):
            raise TradingViewEvidenceStoreError("V1_REVIEW_RUN_INVALID")
        return parent, run

    def has_legacy_evidence(
        self,
        requirements: tuple[TradingViewReviewRequirement, ...],
    ) -> bool:
        """Detect retained pre-parent-binding charts without mutating them."""

        if type(requirements) is not tuple or any(
            type(item) is not TradingViewReviewRequirement
            or item.swing_analysis_run_identity != LEGACY_UNBOUND_SWING_RUN_ID
            for item in requirements
        ):
            raise TradingViewEvidenceStoreError("TRADINGVIEW_REQUIREMENT_INVALID")
        with self._lock:
            return any(
                (self._requirement_directory(item) / "manifest.json").exists()
                for item in requirements
            )

    def package_for(
        self,
        requirement: TradingViewReviewRequirement,
    ) -> TradingViewEvidencePackage:
        if type(requirement) is not TradingViewReviewRequirement:
            raise TradingViewEvidenceStoreError("TRADINGVIEW_REQUIREMENT_INVALID")
        with self._lock:
            directory = self._requirement_directory(requirement)
            manifest_path = directory / "manifest.json"
            if not manifest_path.exists():
                return TradingViewEvidencePackage(
                    requirement,
                    (),
                    (),
                    requirement.required_timeframes,
                    TradingViewReviewStatus.TRADINGVIEW_REVIEW_REQUIRED,
                    str(self._relative(directory / "structured-evidence.json")),
                )
            manifest = self._read_manifest(manifest_path, requirement)
            revisions = tuple(_revision_from_json(item) for item in manifest["revisions"])
            if any(
                item.run_identity != requirement.run_identity
                or item.swing_analysis_run_identity
                != requirement.swing_analysis_run_identity
                or item.canonical_instrument != requirement.canonical_instrument
                or item.observation_boundary != requirement.observation_boundary
                or item.chart_template_identity != requirement.chart_template_identity
                or item.timeframe not in requirement.required_timeframes
                for item in revisions
            ):
                raise TradingViewEvidenceStoreError(
                    "TRADINGVIEW_MANIFEST_BINDING_MISMATCH"
                )
            for revision in revisions:
                self.original_bytes(revision)
            bindings = self._active_revision_bindings(manifest, revisions, requirement)
            active_revisions = tuple(
                revision
                for timeframe in requirement.required_timeframes
                for revision in revisions
                if revision.timeframe is timeframe
                and revision.sha256 == bindings[timeframe.value]
            )
            received = {item.timeframe for item in active_revisions}
            missing = missing_timeframes(requirement, received)
            status = (
                TradingViewReviewStatus.TRADINGVIEW_CONTEXT_RECEIVED
                if not missing
                else TradingViewReviewStatus.CONTEXT_INCOMPLETE
                if active_revisions
                else TradingViewReviewStatus.TRADINGVIEW_REVIEW_REQUIRED
            )
            return TradingViewEvidencePackage(
                requirement,
                revisions,
                active_revisions,
                missing,
                status,
                str(self._relative(directory / "structured-evidence.json")),
            )

    def retain_upload(
        self,
        requirement: TradingViewReviewRequirement,
        *,
        selected_instrument: str,
        selected_timeframe: ChartTimeframe,
        content_type: str,
        original_bytes: bytes,
    ) -> StoredChartRevision:
        """Validate the selected slot, then append an immutable original revision."""

        if type(requirement) is not TradingViewReviewRequirement:
            raise TradingViewEvidenceStoreError("TRADINGVIEW_REQUIREMENT_INVALID")
        if selected_instrument != requirement.canonical_instrument:
            raise TradingViewEvidenceStoreError("TRADINGVIEW_INSTRUMENT_BINDING_MISMATCH")
        if type(selected_timeframe) is not ChartTimeframe:
            raise TradingViewEvidenceStoreError("TRADINGVIEW_TIMEFRAME_INVALID")
        if selected_timeframe not in requirement.required_timeframes:
            raise TradingViewEvidenceStoreError("TRADINGVIEW_TIMEFRAME_NOT_REQUESTED")
        if type(original_bytes) is not bytes or not 0 < len(original_bytes) <= _MAX_CHART_BYTES:
            raise TradingViewEvidenceStoreError("TRADINGVIEW_CHART_SIZE_INVALID")
        suffix, magic = _CONTENT_TYPES.get(content_type, (None, None))
        if suffix is None or not original_bytes.startswith(magic):
            raise TradingViewEvidenceStoreError("TRADINGVIEW_CHART_CONTENT_INVALID")
        if content_type == "image/webp" and original_bytes[8:12] != b"WEBP":
            raise TradingViewEvidenceStoreError("TRADINGVIEW_CHART_CONTENT_INVALID")

        with self._lock:
            directory = self._requirement_directory(requirement)
            directory.mkdir(parents=True, exist_ok=True)
            manifest_path = directory / "manifest.json"
            if manifest_path.exists():
                manifest = self._read_manifest(manifest_path, requirement)
            else:
                manifest = self._new_manifest(requirement)
                self._write_structured_evidence(directory, requirement)
            digest = sha256(original_bytes).hexdigest()
            same_timeframe = tuple(
                item for item in manifest["revisions"]
                if item["timeframe"] == selected_timeframe.value
            )
            duplicate = next(
                (item for item in same_timeframe if item["sha256"] == digest),
                None,
            )
            bindings = self._active_revision_bindings(
                manifest,
                tuple(_revision_from_json(item) for item in manifest["revisions"]),
                requirement,
            )
            if duplicate is not None:
                if bindings[selected_timeframe.value] == digest:
                    raise TradingViewEvidenceStoreError("TRADINGVIEW_DUPLICATE_UPLOAD")
                bindings[selected_timeframe.value] = digest
                manifest["active_revision_sha256_by_timeframe"] = bindings
                self._atomic_json(manifest_path, manifest)
                return _revision_from_json(duplicate)
            revision_number = len(same_timeframe) + 1
            upload_timestamp = self._aware_now()
            relative_path = self._relative(
                directory
                / selected_timeframe.value.lower().replace("h", "-hour")
                / f"r{revision_number:04d}-original{suffix}"
            )
            destination = self._root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            self._atomic_write(destination, original_bytes)
            revision = StoredChartRevision(
                run_identity=requirement.run_identity,
                canonical_instrument=requirement.canonical_instrument,
                observation_boundary=requirement.observation_boundary,
                timeframe=selected_timeframe,
                upload_timestamp=upload_timestamp,
                chart_template_identity=requirement.chart_template_identity,
                source=TRADINGVIEW_UPLOAD_SOURCE,
                retention_class=TRADINGVIEW_RETENTION_CLASS,
                revision=revision_number,
                sha256=digest,
                byte_count=len(original_bytes),
                content_type=content_type,
                relative_path=str(relative_path),
                swing_analysis_run_identity=(
                    requirement.swing_analysis_run_identity
                ),
            )
            manifest["revisions"].append(_revision_to_json(revision))
            bindings[selected_timeframe.value] = digest
            manifest["active_revision_sha256_by_timeframe"] = bindings
            self._atomic_json(manifest_path, manifest)
            return revision

    def remove_active_chart(
        self,
        requirement: TradingViewReviewRequirement,
        *,
        selected_instrument: str,
        selected_timeframe: ChartTimeframe,
    ) -> None:
        """Withdraw one active slot without deleting its retained revisions."""

        if type(requirement) is not TradingViewReviewRequirement:
            raise TradingViewEvidenceStoreError("TRADINGVIEW_REQUIREMENT_INVALID")
        if selected_instrument != requirement.canonical_instrument:
            raise TradingViewEvidenceStoreError("TRADINGVIEW_INSTRUMENT_BINDING_MISMATCH")
        if type(selected_timeframe) is not ChartTimeframe:
            raise TradingViewEvidenceStoreError("TRADINGVIEW_TIMEFRAME_INVALID")
        if selected_timeframe not in requirement.required_timeframes:
            raise TradingViewEvidenceStoreError("TRADINGVIEW_TIMEFRAME_NOT_REQUESTED")
        with self._lock:
            manifest_path = self._requirement_directory(requirement) / "manifest.json"
            if not manifest_path.exists():
                raise TradingViewEvidenceStoreError("TRADINGVIEW_CHART_NOT_RECEIVED")
            manifest = self._read_manifest(manifest_path, requirement)
            revisions = tuple(
                _revision_from_json(item) for item in manifest["revisions"]
            )
            bindings = self._active_revision_bindings(
                manifest,
                revisions,
                requirement,
            )
            if bindings[selected_timeframe.value] is None:
                raise TradingViewEvidenceStoreError("TRADINGVIEW_CHART_NOT_RECEIVED")
            bindings[selected_timeframe.value] = None
            manifest["active_revision_sha256_by_timeframe"] = bindings
            self._atomic_json(manifest_path, manifest)

    def original_bytes(self, revision: StoredChartRevision) -> bytes:
        if type(revision) is not StoredChartRevision:
            raise TradingViewEvidenceStoreError("TRADINGVIEW_REVISION_INVALID")
        path = self._root / revision.relative_path
        payload = path.read_bytes()
        if sha256(payload).hexdigest() != revision.sha256:
            raise TradingViewEvidenceStoreError("TRADINGVIEW_EVIDENCE_INTEGRITY_FAILURE")
        return payload

    def retain_chart_analysis(
        self,
        requirement: TradingViewReviewRequirement,
        analysis: StoredChartAnalysis,
    ) -> None:
        """Atomically retain provider outputs and deterministic Layer-2 result."""

        if (
            type(requirement) is not TradingViewReviewRequirement
            or type(analysis) is not StoredChartAnalysis
        ):
            raise TradingViewEvidenceStoreError("TRADINGVIEW_CHART_ANALYSIS_INVALID")
        if any(
            response.run_identity != requirement.run_identity
            or response.canonical_instrument != requirement.canonical_instrument
            or response.observation_boundary != requirement.observation_boundary
            or response.chart_template_identity != requirement.chart_template_identity
            or response.timeframe not in requirement.required_timeframes
            for response in analysis.responses
        ):
            raise TradingViewEvidenceStoreError(
                "TRADINGVIEW_CHART_ANALYSIS_BINDING_MISMATCH"
            )
        package = self.package_for(requirement)
        latest_hashes = {item.sha256 for item in package.active_revisions}
        response_hashes = {item.source_image_sha256 for item in analysis.responses}
        if (
            set(analysis.source_image_hashes) != latest_hashes
            or not response_hashes.issubset(latest_hashes)
            or (
                analysis.state is StoredChartAnalysisState.COMPLETE
                and (
                    response_hashes != latest_hashes
                    or {item.timeframe for item in analysis.responses}
                    != set(requirement.required_timeframes)
                )
            )
        ):
            raise TradingViewEvidenceStoreError(
                "TRADINGVIEW_CHART_ANALYSIS_BINDING_MISMATCH"
            )
        if (
            analysis.layer2_record is not None
            and (
                analysis.layer2_record.structured_evidence.run_identity
                != requirement.run_identity
                or analysis.layer2_record.structured_evidence.canonical_instrument
                != requirement.canonical_instrument
            )
        ):
            raise TradingViewEvidenceStoreError(
                "TRADINGVIEW_CHART_ANALYSIS_BINDING_MISMATCH"
            )
        payload: dict[str, object] = {
            "schema": "KRONOS_SWING_V1_CHART_ANALYSIS_RETENTION_V1",
            "state": analysis.state.value,
            "source_image_hashes": list(analysis.source_image_hashes),
            "provider_request_count": analysis.provider_request_count,
            "failure_code": (
                analysis.failure_code.value if analysis.failure_code else None
            ),
            "provider_results": [
                chart_evidence_response_to_dict(item) for item in analysis.responses
            ],
            "layer2_record": (
                layer2_record_to_dict(analysis.layer2_record)
                if analysis.layer2_record is not None
                else None
            ),
            "final_trade_construction": "NOT_IMPLEMENTED",
            "final_risk_reward": "NOT_CALCULATED",
            "ranking": "NOT_PERFORMED",
        }
        directory = self._requirement_directory(requirement)
        with self._lock:
            directory.mkdir(parents=True, exist_ok=True)
            self._atomic_json(directory / "structured-evidence.json", payload)

    def chart_analysis_for(
        self,
        requirement: TradingViewReviewRequirement,
    ) -> StoredChartAnalysis | None:
        if type(requirement) is not TradingViewReviewRequirement:
            raise TradingViewEvidenceStoreError("TRADINGVIEW_REQUIREMENT_INVALID")
        path = self._requirement_directory(requirement) / "structured-evidence.json"
        with self._lock:
            if not path.exists():
                return None
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as error:
                raise TradingViewEvidenceStoreError(
                    "TRADINGVIEW_CHART_ANALYSIS_INVALID"
                ) from error
            if payload.get("schema") != "KRONOS_SWING_V1_CHART_ANALYSIS_RETENTION_V1":
                return None
            try:
                analysis = StoredChartAnalysis(
                    state=StoredChartAnalysisState(payload["state"]),
                    source_image_hashes=tuple(payload["source_image_hashes"]),
                    provider_request_count=payload["provider_request_count"],
                    responses=tuple(
                        chart_evidence_response_from_dict(item)
                        for item in payload["provider_results"]
                    ),
                    layer2_record=(
                        layer2_record_from_dict(payload["layer2_record"])
                        if payload["layer2_record"] is not None
                        else None
                    ),
                    failure_code=(
                        ChartEvidenceProviderFailureCode(payload["failure_code"])
                        if payload["failure_code"] is not None
                        else None
                    ),
                )
            except (KeyError, TypeError, ValueError) as error:
                raise TradingViewEvidenceStoreError(
                    "TRADINGVIEW_CHART_ANALYSIS_INVALID"
                ) from error
            if any(
                response.run_identity != requirement.run_identity
                or response.canonical_instrument != requirement.canonical_instrument
                or response.observation_boundary != requirement.observation_boundary
                or response.chart_template_identity != requirement.chart_template_identity
                for response in analysis.responses
            ):
                raise TradingViewEvidenceStoreError(
                    "TRADINGVIEW_CHART_ANALYSIS_BINDING_MISMATCH"
                )
            if not {
                item.source_image_sha256 for item in analysis.responses
            }.issubset(set(analysis.source_image_hashes)):
                raise TradingViewEvidenceStoreError(
                    "TRADINGVIEW_CHART_ANALYSIS_BINDING_MISMATCH"
                )
            return analysis

    def retain_chart_analyst_v2_layer2(
        self,
        requirement: TradingViewReviewRequirement,
        record: ChartAnalystV2Layer2Record,
    ) -> None:
        """Retain the complete 4F shadow chain against one immutable image."""

        if (
            type(requirement) is not TradingViewReviewRequirement
            or type(record) is not ChartAnalystV2Layer2Record
        ):
            raise TradingViewEvidenceStoreError(
                "TRADINGVIEW_CHART_ANALYST_V2_LAYER2_INVALID"
            )
        package = self.package_for(requirement)
        active_hashes = {item.sha256 for item in package.active_revisions}
        if (
            len(active_hashes) != 1
            or record.response.run_identity != requirement.run_identity
            or record.response.swing_analysis_run_identity
            != requirement.swing_analysis_run_identity
            or record.response.instrument != requirement.canonical_instrument
            or record.response.image_sha256 not in active_hashes
            or record.readiness.observation_boundary
            != requirement.observation_boundary
        ):
            raise TradingViewEvidenceStoreError(
                "TRADINGVIEW_CHART_ANALYST_V2_LAYER2_BINDING_MISMATCH"
            )
        directory = self._requirement_directory(requirement)
        with self._lock:
            directory.mkdir(parents=True, exist_ok=True)
            self._atomic_json(
                directory / "structured-evidence.json",
                chart_analyst_v2_layer2_record_to_dict(record),
            )

    def chart_analyst_v2_layer2_for(
        self,
        requirement: TradingViewReviewRequirement,
    ) -> ChartAnalystV2Layer2Record | None:
        if type(requirement) is not TradingViewReviewRequirement:
            raise TradingViewEvidenceStoreError("TRADINGVIEW_REQUIREMENT_INVALID")
        path = self._requirement_directory(requirement) / "structured-evidence.json"
        with self._lock:
            if not path.exists():
                return None
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as error:
                raise TradingViewEvidenceStoreError(
                    "TRADINGVIEW_CHART_ANALYST_V2_LAYER2_INVALID"
                ) from error
            if payload.get("schema") != CHART_ANALYST_V2_LAYER2_SCHEMA_ID:
                return None
            try:
                record = chart_analyst_v2_layer2_record_from_dict(payload)
            except (TypeError, ValueError) as error:
                raise TradingViewEvidenceStoreError(
                    "TRADINGVIEW_CHART_ANALYST_V2_LAYER2_INVALID"
                ) from error
        package = self.package_for(requirement)
        active_hashes = {item.sha256 for item in package.active_revisions}
        if active_hashes != {record.response.image_sha256}:
            return None
        if (
            record.response.run_identity != requirement.run_identity
            or record.response.swing_analysis_run_identity
            != requirement.swing_analysis_run_identity
            or record.response.instrument != requirement.canonical_instrument
            or record.readiness.observation_boundary
            != requirement.observation_boundary
        ):
            raise TradingViewEvidenceStoreError(
                "TRADINGVIEW_CHART_ANALYST_V2_LAYER2_BINDING_MISMATCH"
            )
        return record

    def _requirement_directory(self, requirement: TradingViewReviewRequirement) -> Path:
        identity_material = requirement.run_identity
        if requirement.swing_analysis_run_identity != LEGACY_UNBOUND_SWING_RUN_ID:
            identity_material = (
                f"{requirement.swing_analysis_run_identity}\x1f{requirement.run_identity}"
            )
        run_hash = sha256(identity_material.encode("utf-8")).hexdigest()[:16]
        instrument = re.sub(r"[^A-Z0-9._&-]+", "-", requirement.canonical_instrument.upper())
        if not instrument:
            raise TradingViewEvidenceStoreError("TRADINGVIEW_INSTRUMENT_INVALID")
        date = requirement.observation_boundary.date().isoformat()
        return self._root / "runs" / date / run_hash / instrument / "tradingview"

    def _new_manifest(self, requirement: TradingViewReviewRequirement) -> dict[str, object]:
        return {
            "schema": "KRONOS_SWING_V1_TRADINGVIEW_MANIFEST_V1",
            "swing_analysis_run_identity": requirement.swing_analysis_run_identity,
            "run_identity": requirement.run_identity,
            "canonical_instrument": requirement.canonical_instrument,
            "observation_boundary": requirement.observation_boundary.isoformat(),
            "chart_template_identity": requirement.chart_template_identity,
            "required_timeframes": [item.value for item in requirement.required_timeframes],
            "probable_assessment_identities": [
                item.assessment_identity for item in requirement.probable_setups
            ],
            "retention_class": TRADINGVIEW_RETENTION_CLASS,
            "pruning": "MANUAL_ONLY",
            "active_revision_sha256_by_timeframe": {
                item.value: None for item in requirement.required_timeframes
            },
            "revisions": [],
        }

    def _read_manifest(
        self,
        path: Path,
        requirement: TradingViewReviewRequirement,
    ) -> dict[str, object]:
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise TradingViewEvidenceStoreError("TRADINGVIEW_MANIFEST_INVALID") from error
        expected = self._new_manifest(requirement)
        if (
            "swing_analysis_run_identity" not in manifest
            and requirement.swing_analysis_run_identity
            == LEGACY_UNBOUND_SWING_RUN_ID
        ):
            manifest["swing_analysis_run_identity"] = (
                LEGACY_UNBOUND_SWING_RUN_ID
            )
        for field in (
            "schema",
            "swing_analysis_run_identity",
            "run_identity",
            "canonical_instrument",
            "observation_boundary",
            "chart_template_identity",
            "required_timeframes",
            "probable_assessment_identities",
            "retention_class",
            "pruning",
        ):
            if manifest.get(field) != expected[field]:
                raise TradingViewEvidenceStoreError("TRADINGVIEW_MANIFEST_BINDING_MISMATCH")
        if type(manifest.get("revisions")) is not list:
            raise TradingViewEvidenceStoreError("TRADINGVIEW_MANIFEST_INVALID")
        return manifest

    @staticmethod
    def _active_revision_bindings(
        manifest: dict[str, object],
        revisions: tuple[StoredChartRevision, ...],
        requirement: TradingViewReviewRequirement,
    ) -> dict[str, str | None]:
        raw = manifest.get("active_revision_sha256_by_timeframe")
        if raw is None:
            bindings: dict[str, str | None] = {
                item.value: None for item in requirement.required_timeframes
            }
            for revision in revisions:
                bindings[revision.timeframe.value] = revision.sha256
            return bindings
        if type(raw) is not dict or set(raw) != {
            item.value for item in requirement.required_timeframes
        }:
            raise TradingViewEvidenceStoreError("TRADINGVIEW_MANIFEST_INVALID")
        bindings = {}
        for timeframe in requirement.required_timeframes:
            digest = raw[timeframe.value]
            if digest is not None and (
                type(digest) is not str
                or not any(
                    item.timeframe is timeframe and item.sha256 == digest
                    for item in revisions
                )
            ):
                raise TradingViewEvidenceStoreError(
                    "TRADINGVIEW_MANIFEST_BINDING_MISMATCH"
                )
            bindings[timeframe.value] = digest
        return bindings

    def _write_structured_evidence(
        self,
        directory: Path,
        requirement: TradingViewReviewRequirement,
    ) -> None:
        evidence = pending_layer2_evidence(requirement)
        payload = _jsonable(asdict(evidence))
        payload["schema"] = "KRONOS_SWING_V1_LAYER2_EVIDENCE_V1"
        payload["extraction_status"] = "DEFERRED_TO_SLICE_4"
        payload["extraction_reason"] = (
            "NO_APPROVED_DETERMINISTIC_IMAGE_TO_STRUCTURED_EVIDENCE_BOUNDARY"
        )
        self._atomic_json(directory / "structured-evidence.json", payload)

    def _aware_now(self) -> datetime:
        now = self._clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise TradingViewEvidenceStoreError("TRADINGVIEW_UPLOAD_CLOCK_INVALID")
        return now

    def _relative(self, path: Path) -> Path:
        try:
            return path.relative_to(self._root)
        except ValueError as error:
            raise TradingViewEvidenceStoreError("TRADINGVIEW_PATH_ESCAPE") from error

    @staticmethod
    def _atomic_write(path: Path, payload: bytes) -> None:
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()

    def _atomic_json(self, path: Path, payload: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self._atomic_write(path, serialized)


def _revision_to_json(revision: StoredChartRevision) -> dict[str, object]:
    return {
        "swing_analysis_run_identity": revision.swing_analysis_run_identity,
        "run_identity": revision.run_identity,
        "canonical_instrument": revision.canonical_instrument,
        "observation_boundary": revision.observation_boundary.isoformat(),
        "timeframe": revision.timeframe.value,
        "upload_timestamp": revision.upload_timestamp.isoformat(),
        "chart_template_identity": revision.chart_template_identity,
        "source": revision.source,
        "retention_class": revision.retention_class,
        "revision": revision.revision,
        "sha256": revision.sha256,
        "byte_count": revision.byte_count,
        "content_type": revision.content_type,
        "relative_path": revision.relative_path,
    }


def _revision_from_json(payload: object) -> StoredChartRevision:
    if type(payload) is not dict:
        raise TradingViewEvidenceStoreError("TRADINGVIEW_MANIFEST_INVALID")
    try:
        return StoredChartRevision(
            swing_analysis_run_identity=payload.get(
                "swing_analysis_run_identity",
                LEGACY_UNBOUND_SWING_RUN_ID,
            ),
            run_identity=payload["run_identity"],
            canonical_instrument=payload["canonical_instrument"],
            observation_boundary=datetime.fromisoformat(payload["observation_boundary"]),
            timeframe=ChartTimeframe(payload["timeframe"]),
            upload_timestamp=datetime.fromisoformat(payload["upload_timestamp"]),
            chart_template_identity=payload["chart_template_identity"],
            source=payload["source"],
            retention_class=payload["retention_class"],
            revision=payload["revision"],
            sha256=payload["sha256"],
            byte_count=payload["byte_count"],
            content_type=payload["content_type"],
            relative_path=payload["relative_path"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise TradingViewEvidenceStoreError("TRADINGVIEW_MANIFEST_INVALID") from error


def _jsonable(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def _encode_v1_review_value(value: object) -> object:
    if isinstance(value, datetime):
        return {"$datetime": value.isoformat()}
    if isinstance(value, StrEnum):
        return {"$enum": type(value).__name__, "value": value.value}
    if is_dataclass(value) and type(value).__name__ in _V1_REVIEW_TYPES:
        return {
            "$type": type(value).__name__,
            "fields": {
                field.name: _encode_v1_review_value(getattr(value, field.name))
                for field in fields(value)
            },
        }
    if type(value) is tuple:
        return {"$tuple": [_encode_v1_review_value(item) for item in value]}
    if value is None or type(value) in {str, int, float, bool}:
        return value
    raise TypeError("V1_REVIEW_RUN_SERIALIZATION_INVALID")


def _decode_v1_review_value(value: object) -> object:
    if type(value) is not dict:
        if value is None or type(value) in {str, int, float, bool}:
            return value
        raise ValueError("V1_REVIEW_RUN_DESERIALIZATION_INVALID")
    if set(value) == {"$datetime"}:
        return datetime.fromisoformat(value["$datetime"])
    if set(value) == {"$enum", "value"}:
        enum_type = _V1_REVIEW_TYPES.get(value["$enum"])
        if not isinstance(enum_type, type) or not issubclass(enum_type, StrEnum):
            raise ValueError("V1_REVIEW_RUN_DESERIALIZATION_INVALID")
        return enum_type(value["value"])
    if set(value) == {"$tuple"} and type(value["$tuple"]) is list:
        return tuple(_decode_v1_review_value(item) for item in value["$tuple"])
    if set(value) == {"$type", "fields"} and type(value["fields"]) is dict:
        data_type = _V1_REVIEW_TYPES.get(value["$type"])
        if not isinstance(data_type, type) or not is_dataclass(data_type):
            raise ValueError("V1_REVIEW_RUN_DESERIALIZATION_INVALID")
        expected_fields = tuple(field.name for field in fields(data_type))
        if set(value["fields"]) != set(expected_fields):
            raise ValueError("V1_REVIEW_RUN_DESERIALIZATION_INVALID")
        return data_type(**{
            name: _decode_v1_review_value(value["fields"][name])
            for name in expected_fields
        })
    raise ValueError("V1_REVIEW_RUN_DESERIALIZATION_INVALID")


__all__ = [
    "DEFAULT_V1_EVIDENCE_ROOT",
    "LocalTradingViewEvidenceStore",
    "StoredChartRevision",
    "StoredChartAnalysis",
    "StoredChartAnalysisState",
    "TradingViewEvidencePackage",
    "TradingViewEvidenceStoreError",
]
