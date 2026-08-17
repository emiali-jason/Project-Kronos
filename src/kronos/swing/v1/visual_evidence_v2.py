"""Frozen ten-question visual evidence V2 contract for Native Swing Review.

This module extracts governed observations only.  It deliberately contains no
Discovery, reconciliation, Readiness, trade-construction, risk, or execution
authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
from threading import RLock
from typing import Protocol, runtime_checkable

from kronos.swing.v1.mtf_facts import FactualTimeframe
from kronos.swing.v1.native_review import (
    NativeReviewRequirement,
    NativeReviewTimeframeFacts,
)


VISUAL_QUESTION_SET_V2_ID = "SWING-V1-VISUAL-QUESTION-SET-V2"
VISUAL_QUESTION_SET_V2_VERSION = "2.0"
VISUAL_EVIDENCE_V2_SCHEMA = "KRONOS-SWING-V1-VISUAL-EVIDENCE-V2"
VISUAL_EVIDENCE_V2_AUTHORITY = "OBSERVATION_ONLY_NO_ANALYTICAL_CONSEQUENCE"
OPENAI_VISUAL_EVIDENCE_V2_PROVIDER_ID = "OPENAI_VISUAL_EVIDENCE_V2_PROVIDER"
DEFAULT_VISUAL_EVIDENCE_V2_ROOT = (
    Path.home() / "Library" / "Application Support" / "KRONOS" / "evidence"
    / "swing-v1" / "visual-v2"
)
DEFAULT_VISUAL_EVIDENCE_V2_DIAGNOSTIC_ROOT = (
    DEFAULT_VISUAL_EVIDENCE_V2_ROOT.parent / "visual-v2-diagnostics"
)
VISUAL_EVIDENCE_V2_PROVIDER_SCHEMA_VERSION = "2.0"


class VisualEvidenceV2ValidationStage(StrEnum):
    STRUCTURED_OUTPUT_DECODING = "STRUCTURED_OUTPUT_DECODING"
    JSON_PARSING = "JSON_PARSING"
    TRANSPORT_TO_DOMAIN_ADAPTER = "TRANSPORT_TO_DOMAIN_ADAPTER"
    FROZEN_DOMAIN_INVARIANT = "FROZEN_DOMAIN_INVARIANT"
    TIMEFRAME_ROUTING = "TIMEFRAME_ROUTING"
    PERSISTENCE_BINDING = "PERSISTENCE_BINDING"


@dataclass(frozen=True, slots=True)
class VisualEvidenceV2ValidationDiagnostic:
    native_run_identity: str
    canonical_instrument: str
    timeframe: VisualTimeframe
    chart_revision_sha256: str
    model_identity: str
    attempt: int
    api_request_completed: bool
    input_tokens: int
    output_tokens: int
    total_tokens: int
    response_status: str
    validation_stage: VisualEvidenceV2ValidationStage
    validation_error_code: str
    structural_path: str
    expected_constraint: str
    received_shape: str
    retry_disposition: str
    recorded_at: datetime

    def __post_init__(self) -> None:
        if (
            not self.native_run_identity
            or not self.canonical_instrument
            or type(self.timeframe) is not VisualTimeframe
            or re.fullmatch(r"[0-9a-f]{64}", self.chart_revision_sha256) is None
            or not _text(self.model_identity, 128)
            or type(self.attempt) is not int or self.attempt < 1
            or type(self.api_request_completed) is not bool
            or any(type(value) is not int or value < 0 for value in (
                self.input_tokens, self.output_tokens, self.total_tokens,
            ))
            or not _safe_diagnostic_text(self.response_status, 64)
            or type(self.validation_stage) is not VisualEvidenceV2ValidationStage
            or not _safe_diagnostic_text(self.validation_error_code, 128)
            or not _safe_diagnostic_text(self.structural_path, 256)
            or not _safe_diagnostic_text(self.expected_constraint, 512)
            or not _safe_diagnostic_text(self.received_shape, 512)
            or self.retry_disposition not in {"RETRY", "FAILED_FINAL"}
            or not _aware(self.recorded_at)
        ):
            raise ValueError("VISUAL_V2_VALIDATION_DIAGNOSTIC_INVALID")


@dataclass(frozen=True, slots=True)
class VisualEvidenceV2ProviderDiagnostic:
    http_status: int
    error_type: str | None
    error_code: str | None
    rejected_parameter: str | None
    provider_message: str | None
    model_identity: str
    timeframe: VisualTimeframe
    schema_identity: str
    schema_version: str
    request_timestamp: datetime

    def __post_init__(self) -> None:
        optional = (
            self.error_type,
            self.error_code,
            self.rejected_parameter,
            self.provider_message,
        )
        if (
            type(self.http_status) is not int
            or not 400 <= self.http_status <= 599
            or any(
                value is not None and not _safe_diagnostic_text(value, maximum)
                for value, maximum in zip(optional, (128, 128, 256, 512), strict=True)
            )
            or not _text(self.model_identity, 128)
            or type(self.timeframe) is not VisualTimeframe
            or self.schema_identity != VISUAL_EVIDENCE_V2_SCHEMA
            or self.schema_version != VISUAL_EVIDENCE_V2_PROVIDER_SCHEMA_VERSION
            or not _aware(self.request_timestamp)
        ):
            raise ValueError("VISUAL_V2_PROVIDER_DIAGNOSTIC_INVALID")


class LocalVisualEvidenceV2DiagnosticStore:
    """Persist only allowlisted structural failure metadata, never model prose."""

    def __init__(self, root: Path = DEFAULT_VISUAL_EVIDENCE_V2_DIAGNOSTIC_ROOT) -> None:
        if not isinstance(root, Path):
            raise TypeError("VISUAL_V2_DIAGNOSTIC_STORE_INVALID")
        self.root = root
        self._lock = RLock()

    def retain(self, diagnostic: VisualEvidenceV2ValidationDiagnostic) -> None:
        if type(diagnostic) is not VisualEvidenceV2ValidationDiagnostic:
            raise TypeError("VISUAL_V2_DIAGNOSTIC_INVALID")
        path = (
            self.root / _safe(diagnostic.native_run_identity)
            / _safe(diagnostic.canonical_instrument)
            / diagnostic.timeframe.value
            / diagnostic.chart_revision_sha256
            / (
                f"attempt-{diagnostic.attempt}-"
                f"{diagnostic.recorded_at.strftime('%Y%m%dT%H%M%S%fZ')}.json"
            )
        )
        payload = _primitive(asdict(diagnostic))
        if type(payload) is not dict:
            raise AssertionError("VISUAL_V2_DIAGNOSTIC_SERIALIZATION_INVALID")
        with self._lock:
            if path.exists() and _read(path) != payload:
                raise ValueError("VISUAL_V2_DIAGNOSTIC_IMMUTABLE")
            _atomic_json(path, payload)

    def retain_provider_error(
        self, diagnostic: VisualEvidenceV2ProviderDiagnostic,
    ) -> None:
        if type(diagnostic) is not VisualEvidenceV2ProviderDiagnostic:
            raise TypeError("VISUAL_V2_PROVIDER_DIAGNOSTIC_INVALID")
        payload = _primitive(asdict(diagnostic))
        if type(payload) is not dict:
            raise AssertionError("VISUAL_V2_PROVIDER_DIAGNOSTIC_SERIALIZATION_INVALID")
        digest = sha256(_canonical(payload)).hexdigest()
        path = (
            self.root / "provider-errors"
            / f"{diagnostic.request_timestamp.strftime('%Y%m%dT%H%M%S%fZ')}-{digest}.json"
        )
        with self._lock:
            if path.exists() and _read(path) != payload:
                raise ValueError("VISUAL_V2_PROVIDER_DIAGNOSTIC_IMMUTABLE")
            _atomic_json(path, payload)

    def load_provider_errors(
        self,
    ) -> tuple[VisualEvidenceV2ProviderDiagnostic, ...]:
        directory = self.root / "provider-errors"
        if not directory.exists():
            return ()
        with self._lock:
            return tuple(
                _provider_diagnostic_from_dict(_read(path))
                for path in sorted(directory.glob("*.json"))
            )

    def load_for_run(
        self, native_run_identity: str,
    ) -> tuple[VisualEvidenceV2ValidationDiagnostic, ...]:
        if not native_run_identity:
            raise ValueError("VISUAL_V2_DIAGNOSTIC_RUN_INVALID")
        directory = self.root / _safe(native_run_identity)
        if not directory.exists():
            return ()
        with self._lock:
            values = tuple(
                _diagnostic_from_dict(_read(path))
                for path in sorted(directory.glob("*/*/*/attempt-*.json"))
            )
        return tuple(sorted(values, key=lambda item: (
            item.canonical_instrument, item.timeframe.value,
            item.chart_revision_sha256, item.attempt,
        )))


class VisualQuestionV2(StrEnum):
    VISUAL_CHART_VALIDATION = "VISUAL_CHART_VALIDATION"
    CPR_CONTEXT = "CPR_CONTEXT"
    VISUAL_SUPPORT_RESISTANCE_GAP = "VISUAL_SUPPORT_RESISTANCE_GAP"
    PDH_PDL_REFERENCE_CONTEXT = "PDH_PDL_REFERENCE_CONTEXT"
    PRICE_ACTION_QUALITY = "PRICE_ACTION_QUALITY"
    VISUAL_OBSTACLE_EVIDENCE = "VISUAL_OBSTACLE_EVIDENCE"
    MATURITY_AND_CHASE_CONTEXT = "MATURITY_AND_CHASE_CONTEXT"
    PINE_VISIBLE_EVIDENCE = "PINE_VISIBLE_EVIDENCE"
    VISUAL_CONFLUENCE = "VISUAL_CONFLUENCE"
    VISUAL_FACTS_NOT_CAPTURED_BY_KRONOS = "VISUAL_FACTS_NOT_CAPTURED_BY_KRONOS"


FROZEN_VISUAL_QUESTION_SET_V2 = tuple(VisualQuestionV2)

VISUAL_QUESTION_SEMANTICS_V2: dict[VisualQuestionV2, str] = {
    VisualQuestionV2.VISUAL_CHART_VALIDATION: "Validate visible chart identity, timeframe, readability, and revision.",
    VisualQuestionV2.CPR_CONTEXT: "Extract only visibly displayed CPR context.",
    VisualQuestionV2.VISUAL_SUPPORT_RESISTANCE_GAP: "Extract material visible support/resistance absent from supplied deterministic evidence.",
    VisualQuestionV2.PDH_PDL_REFERENCE_CONTEXT: "Extract visibly displayed prior-day high/low reference context where applicable.",
    VisualQuestionV2.PRICE_ACTION_QUALITY: "Describe bounded visible price-action quality without analytical consequence.",
    VisualQuestionV2.VISUAL_OBSTACLE_EVIDENCE: "Extract factual visible obstacle category and readable level or zone.",
    VisualQuestionV2.MATURITY_AND_CHASE_CONTEXT: "Describe visible maturity, extension, or chase context without consequence.",
    VisualQuestionV2.PINE_VISIBLE_EVIDENCE: "Transcribe only what the visible Pine panel displays.",
    VisualQuestionV2.VISUAL_CONFLUENCE: "Report visible component evidence and readable clustering without scoring.",
    VisualQuestionV2.VISUAL_FACTS_NOT_CAPTURED_BY_KRONOS: "Strict escape hatch for clear material facts not covered by Q1-Q9 or supplied facts; NONE is valid.",
}


class VisualTimeframe(StrEnum):
    WEEKLY = "1W"
    DAILY = "1D"
    FOUR_HOUR = "4H"
    ONE_HOUR = "1H"


class VisualQuestionRouting(StrEnum):
    YES = "YES"
    IF_APPLICABLE = "IF_APPLICABLE"
    USUALLY_NO = "USUALLY_NO"
    IF_RELEVANT = "IF_RELEVANT"
    CONTEXTUAL = "CONTEXTUAL"
    IF_SHOWN = "IF_SHOWN"
    ESCAPE_HATCH = "ESCAPE_HATCH"
    NO = "NO"


class VisualObservationStatus(StrEnum):
    OBSERVED = "OBSERVED"
    NOT_VISIBLE = "NOT_VISIBLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID = "INVALID"


class VisualLevelAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    LEVEL_UNAVAILABLE = "LEVEL_UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class VisualEvidenceSubjectKind(StrEnum):
    NATIVE = "NATIVE_ANALYTICAL_SUBJECT"
    REFERENCE = "REFERENCE_EVIDENCE_SUBJECT"


VISUAL_TIMEFRAME_ROUTING: dict[
    VisualQuestionV2, dict[VisualTimeframe, VisualQuestionRouting]
] = {
    VisualQuestionV2.VISUAL_CHART_VALIDATION: dict.fromkeys(VisualTimeframe, VisualQuestionRouting.YES),
    VisualQuestionV2.CPR_CONTEXT: {
        VisualTimeframe.WEEKLY: VisualQuestionRouting.IF_APPLICABLE,
        VisualTimeframe.DAILY: VisualQuestionRouting.YES,
        VisualTimeframe.FOUR_HOUR: VisualQuestionRouting.YES,
        VisualTimeframe.ONE_HOUR: VisualQuestionRouting.YES,
    },
    VisualQuestionV2.VISUAL_SUPPORT_RESISTANCE_GAP: dict.fromkeys(VisualTimeframe, VisualQuestionRouting.YES),
    VisualQuestionV2.PDH_PDL_REFERENCE_CONTEXT: {
        VisualTimeframe.WEEKLY: VisualQuestionRouting.NO,
        VisualTimeframe.DAILY: VisualQuestionRouting.USUALLY_NO,
        VisualTimeframe.FOUR_HOUR: VisualQuestionRouting.IF_RELEVANT,
        VisualTimeframe.ONE_HOUR: VisualQuestionRouting.YES,
    },
    VisualQuestionV2.PRICE_ACTION_QUALITY: {
        VisualTimeframe.WEEKLY: VisualQuestionRouting.CONTEXTUAL,
        VisualTimeframe.DAILY: VisualQuestionRouting.YES,
        VisualTimeframe.FOUR_HOUR: VisualQuestionRouting.YES,
        VisualTimeframe.ONE_HOUR: VisualQuestionRouting.YES,
    },
    VisualQuestionV2.VISUAL_OBSTACLE_EVIDENCE: dict.fromkeys(VisualTimeframe, VisualQuestionRouting.YES),
    VisualQuestionV2.MATURITY_AND_CHASE_CONTEXT: dict.fromkeys(VisualTimeframe, VisualQuestionRouting.YES),
    VisualQuestionV2.PINE_VISIBLE_EVIDENCE: dict.fromkeys(VisualTimeframe, VisualQuestionRouting.IF_SHOWN),
    VisualQuestionV2.VISUAL_CONFLUENCE: dict.fromkeys(VisualTimeframe, VisualQuestionRouting.YES),
    VisualQuestionV2.VISUAL_FACTS_NOT_CAPTURED_BY_KRONOS: dict.fromkeys(VisualTimeframe, VisualQuestionRouting.ESCAPE_HATCH),
}


@dataclass(frozen=True, slots=True)
class VisualDeterministicContext:
    timeframe_facts: NativeReviewTimeframeFacts
    deterministic_range_low: float | None
    deterministic_range_high: float | None
    known_break_boundary: float | None
    known_reference_levels: tuple[tuple[str, float, float | None], ...]

    def __post_init__(self) -> None:
        numeric = (
            self.deterministic_range_low, self.deterministic_range_high,
            self.known_break_boundary,
        )
        if (
            type(self.timeframe_facts) is not NativeReviewTimeframeFacts
            or any(item is not None and not _number(item) for item in numeric)
            or ((self.deterministic_range_low is None) != (self.deterministic_range_high is None))
            or (
                self.deterministic_range_low is not None
                and self.deterministic_range_high is not None
                and self.deterministic_range_low > self.deterministic_range_high
            )
            or type(self.known_reference_levels) is not tuple
            or any(
                not identity or not _number(low)
                or (high is not None and (not _number(high) or low > high))
                for identity, low, high in self.known_reference_levels
            )
        ):
            raise ValueError("VISUAL_V2_DETERMINISTIC_CONTEXT_INVALID")


@dataclass(frozen=True, slots=True)
class VisualEvidenceV2Request:
    requirement: NativeReviewRequirement
    subject_kind: VisualEvidenceSubjectKind
    subject_identity: str
    reference_market: str | None
    reference_symbol: str | None
    timeframe: VisualTimeframe
    observation_boundary: datetime
    chart_identity: str
    chart_revision_sha256: str
    content_type: str
    original_image: bytes
    request_timestamp: datetime
    deterministic_context: VisualDeterministicContext
    routing: tuple[tuple[VisualQuestionV2, VisualQuestionRouting], ...]
    question_set_identity: str = VISUAL_QUESTION_SET_V2_ID
    question_set_version: str = VISUAL_QUESTION_SET_V2_VERSION

    def __post_init__(self) -> None:
        reference = self.requirement.mcx_reference
        native = self.subject_kind is VisualEvidenceSubjectKind.NATIVE
        if (
            type(self.requirement) is not NativeReviewRequirement
            or type(self.subject_kind) is not VisualEvidenceSubjectKind
            or not self.subject_identity
            or type(self.timeframe) is not VisualTimeframe
            or not _aware(self.observation_boundary)
            or not self.chart_identity
            or re.fullmatch(r"[0-9a-f]{64}", self.chart_revision_sha256) is None
            or self.content_type not in {"image/png", "image/jpeg", "image/webp"}
            or type(self.original_image) is not bytes
            or not self.original_image
            or sha256(self.original_image).hexdigest() != self.chart_revision_sha256
            or not _aware(self.request_timestamp)
            or type(self.deterministic_context) is not VisualDeterministicContext
            or self.routing != visual_question_routing(self.timeframe)
            or self.question_set_identity != VISUAL_QUESTION_SET_V2_ID
            or self.question_set_version != VISUAL_QUESTION_SET_V2_VERSION
            or (
                native and (
                    self.subject_identity != self.requirement.canonical_instrument
                    or self.reference_market is not None
                    or self.reference_symbol is not None
                )
            )
            or (
                not native and (
                    reference is None
                    or self.subject_identity != reference.reference_subject_identity
                    or self.reference_market != reference.reference_market.value
                    or self.reference_symbol != reference.reference_symbol
                )
            )
        ):
            raise ValueError("VISUAL_V2_REQUEST_INVALID")


@dataclass(frozen=True, slots=True)
class VisualEvidenceV2Observation:
    question_id: VisualQuestionV2
    timeframe: VisualTimeframe
    observation_status: VisualObservationStatus
    observation: str
    level_availability: VisualLevelAvailability
    price: float | None
    zone_low: float | None
    zone_high: float | None
    visible_basis: str
    source_chart_identity: str
    source_chart_revision: str
    confidence_in_extraction: str
    ambiguity_reason: str
    provenance: tuple[str, ...]
    why_not_covered_elsewhere: str | None = None

    def __post_init__(self) -> None:
        observed = self.observation_status is VisualObservationStatus.OBSERVED
        level = self.level_availability is VisualLevelAvailability.AVAILABLE
        exact = self.price is not None
        zone = self.zone_low is not None or self.zone_high is not None
        q10 = self.question_id is VisualQuestionV2.VISUAL_FACTS_NOT_CAPTURED_BY_KRONOS
        q3_negative = (
            self.question_id is VisualQuestionV2.VISUAL_SUPPORT_RESISTANCE_GAP
            and observed
            and self.observation == "NONE"
        )
        if (
            type(self.question_id) is not VisualQuestionV2
            or type(self.timeframe) is not VisualTimeframe
            or type(self.observation_status) is not VisualObservationStatus
            or not _text(self.observation, 512)
            or type(self.level_availability) is not VisualLevelAvailability
            or any(item is not None and not _number(item) for item in (self.price, self.zone_low, self.zone_high))
            or ((self.zone_low is None) != (self.zone_high is None))
            or (self.zone_low is not None and self.zone_high is not None and self.zone_low > self.zone_high)
            or (level and exact == zone)
            or (not level and (exact or zone))
            or not _text(self.visible_basis, 512)
            or not _text(self.source_chart_identity, 256)
            or re.fullmatch(r"[0-9a-f]{64}", self.source_chart_revision) is None
            or not _text(self.confidence_in_extraction, 64)
            or type(self.ambiguity_reason) is not str
            or len(self.ambiguity_reason) > 512
            or type(self.provenance) is not tuple
            or not self.provenance
            or any(not _text(item, 256) for item in self.provenance)
            or (q10 and self.observation != "NONE" and not _text(self.why_not_covered_elsewhere, 512))
            or (q10 and self.observation == "NONE" and self.why_not_covered_elsewhere is not None)
            or (not q10 and self.why_not_covered_elsewhere is not None)
            or (
                q3_negative
                and self.level_availability
                is not VisualLevelAvailability.NOT_APPLICABLE
            )
            or (q3_negative and (exact or zone))
            or (not observed and self.level_availability is VisualLevelAvailability.AVAILABLE)
            or (
                self.observation_status in {
                    VisualObservationStatus.PARTIAL,
                    VisualObservationStatus.UNAVAILABLE,
                    VisualObservationStatus.INVALID,
                }
                and not self.ambiguity_reason.strip()
            )
            or _contains_prohibited_consequence(self)
        ):
            raise ValueError("VISUAL_V2_OBSERVATION_INVALID")


@dataclass(frozen=True, slots=True)
class VisualEvidenceV2Response:
    provider_identity: str
    model_identity: str
    request_timestamp: datetime
    native_run_identity: str
    native_assessment_sha256: str
    native_canonical_instrument: str
    subject_kind: VisualEvidenceSubjectKind
    subject_identity: str
    reference_market: str | None
    reference_symbol: str | None
    timeframe: VisualTimeframe
    observation_boundary: datetime
    chart_identity: str
    chart_revision_sha256: str
    observations: tuple[VisualEvidenceV2Observation, ...]
    source_provenance: tuple[str, ...]
    question_set_identity: str = VISUAL_QUESTION_SET_V2_ID
    question_set_version: str = VISUAL_QUESTION_SET_V2_VERSION
    schema: str = VISUAL_EVIDENCE_V2_SCHEMA
    authority: str = VISUAL_EVIDENCE_V2_AUTHORITY

    def __post_init__(self) -> None:
        if (
            not _text(self.provider_identity, 128)
            or not _text(self.model_identity, 128)
            or not _aware(self.request_timestamp)
            or not self.native_run_identity
            or re.fullmatch(r"[0-9a-f]{64}", self.native_assessment_sha256) is None
            or not self.native_canonical_instrument
            or type(self.subject_kind) is not VisualEvidenceSubjectKind
            or not self.subject_identity
            or type(self.timeframe) is not VisualTimeframe
            or not _aware(self.observation_boundary)
            or not self.chart_identity
            or re.fullmatch(r"[0-9a-f]{64}", self.chart_revision_sha256) is None
            or type(self.observations) is not tuple
            or tuple(item.question_id for item in self.observations) != FROZEN_VISUAL_QUESTION_SET_V2
            or any(item.timeframe is not self.timeframe for item in self.observations)
            or any(item.source_chart_identity != self.chart_identity for item in self.observations)
            or any(item.source_chart_revision != self.chart_revision_sha256 for item in self.observations)
            or not self.source_provenance
            or self.question_set_identity != VISUAL_QUESTION_SET_V2_ID
            or self.question_set_version != VISUAL_QUESTION_SET_V2_VERSION
            or self.schema != VISUAL_EVIDENCE_V2_SCHEMA
            or self.authority != VISUAL_EVIDENCE_V2_AUTHORITY
        ):
            raise ValueError("VISUAL_V2_RESPONSE_INVALID")

    @property
    def evidence_sha256(self) -> str:
        return sha256(_canonical(visual_evidence_v2_response_to_dict(self))).hexdigest()

    def validate_binding(self, request: VisualEvidenceV2Request) -> None:
        if (
            type(request) is not VisualEvidenceV2Request
            or self.request_timestamp != request.request_timestamp
            or self.native_run_identity != request.requirement.native_run_identity
            or self.native_assessment_sha256 != request.requirement.thesis.native_assessment_sha256
            or self.native_canonical_instrument != request.requirement.canonical_instrument
            or self.subject_kind is not request.subject_kind
            or self.subject_identity != request.subject_identity
            or self.reference_market != request.reference_market
            or self.reference_symbol != request.reference_symbol
            or self.timeframe is not request.timeframe
            or self.observation_boundary != request.observation_boundary
            or self.chart_identity != request.chart_identity
            or self.chart_revision_sha256 != request.chart_revision_sha256
        ):
            raise ValueError("VISUAL_V2_BINDING_INVALID")
        _validate_routing(request, self)
        _validate_q3_gap(request, self)


@runtime_checkable
class VisualEvidenceV2Provider(Protocol):
    @property
    def provider_identity(self) -> str: ...

    def analyze(self, request: VisualEvidenceV2Request) -> VisualEvidenceV2Response: ...


def visual_question_routing(
    timeframe: VisualTimeframe,
) -> tuple[tuple[VisualQuestionV2, VisualQuestionRouting], ...]:
    if type(timeframe) is not VisualTimeframe:
        raise ValueError("VISUAL_V2_TIMEFRAME_INVALID")
    return tuple((question, VISUAL_TIMEFRAME_ROUTING[question][timeframe]) for question in VisualQuestionV2)


def build_visual_evidence_v2_request(
    requirement: NativeReviewRequirement,
    *,
    timeframe: VisualTimeframe,
    observation_boundary: datetime,
    chart_identity: str,
    content_type: str,
    original_image: bytes,
    request_timestamp: datetime,
    subject_kind: VisualEvidenceSubjectKind = VisualEvidenceSubjectKind.NATIVE,
    deterministic_range: tuple[float, float] | None = None,
    known_break_boundary: float | None = None,
    known_reference_levels: tuple[tuple[str, float, float | None], ...] = (),
) -> VisualEvidenceV2Request:
    if type(requirement) is not NativeReviewRequirement:
        raise ValueError("VISUAL_V2_REQUIREMENT_INVALID")
    fact = next(
        item for item in requirement.thesis.timeframe_facts
        if item.timeframe is _FACTUAL_TIMEFRAME[timeframe]
    )
    reference = requirement.mcx_reference
    native = subject_kind is VisualEvidenceSubjectKind.NATIVE
    return VisualEvidenceV2Request(
        requirement=requirement,
        subject_kind=subject_kind,
        subject_identity=(
            requirement.canonical_instrument if native
            else reference.reference_subject_identity if reference else ""
        ),
        reference_market=None if native or reference is None else reference.reference_market.value,
        reference_symbol=None if native or reference is None else reference.reference_symbol,
        timeframe=timeframe,
        observation_boundary=observation_boundary,
        chart_identity=chart_identity,
        chart_revision_sha256=sha256(original_image).hexdigest(),
        content_type=content_type,
        original_image=original_image,
        request_timestamp=request_timestamp,
        deterministic_context=VisualDeterministicContext(
            fact,
            None if deterministic_range is None else deterministic_range[0],
            None if deterministic_range is None else deterministic_range[1],
            known_break_boundary,
            known_reference_levels,
        ),
        routing=visual_question_routing(timeframe),
    )


class LocalVisualEvidenceV2Store:
    """Immutable integrity-checked evidence store; no credentials or chart bytes."""

    def __init__(self, root: Path = DEFAULT_VISUAL_EVIDENCE_V2_ROOT) -> None:
        root = Path(root).expanduser()
        if not root.is_absolute():
            raise ValueError("VISUAL_V2_STORE_INVALID")
        self._root = root
        self._lock = RLock()

    def retain(
        self, request: VisualEvidenceV2Request, response: VisualEvidenceV2Response
    ) -> Path:
        response.validate_binding(request)
        path = self._path(response)
        payload = {
            "schema": VISUAL_EVIDENCE_V2_SCHEMA,
            "evidence_sha256": response.evidence_sha256,
            "response": visual_evidence_v2_response_to_dict(response),
        }
        with self._lock:
            if path.exists():
                if _read(path) != payload:
                    raise ValueError("VISUAL_V2_EVIDENCE_IMMUTABLE")
                return path
            _atomic_json(path, payload)
        return path

    def load(self, request: VisualEvidenceV2Request) -> VisualEvidenceV2Response:
        identity = _safe(request.subject_identity)
        directory = (
            self._root / request.requirement.native_run_identity / identity
            / request.timeframe.value
        )
        candidates = sorted(directory.glob(
            f"{request.chart_revision_sha256}--*.json"
        ), reverse=True)
        legacy_path = directory / f"{request.chart_revision_sha256}.json"
        if legacy_path.exists():
            candidates.append(legacy_path)
        for path in candidates:
            if not path.exists():
                continue
            payload = _read(path)
            response = visual_evidence_v2_response_from_dict(payload.get("response"))
            if payload.get("evidence_sha256") != response.evidence_sha256:
                raise ValueError("VISUAL_V2_EVIDENCE_INTEGRITY_INVALID")
            try:
                response.validate_binding(request)
            except ValueError:
                continue
            return response
        raise ValueError("VISUAL_V2_EVIDENCE_UNAVAILABLE")

    def load_for_requirements(
        self,
        requirements: tuple[NativeReviewRequirement, ...],
        *,
        review_pack_id: str | None = None,
    ) -> tuple[VisualEvidenceV2Response, ...]:
        if not requirements:
            return ()
        run_identity = requirements[0].native_run_identity
        if any(item.native_run_identity != run_identity for item in requirements):
            raise ValueError("VISUAL_V2_RESTART_BINDING_INVALID")
        expected = {
            (item.canonical_instrument, item.thesis.native_assessment_sha256): item
            for item in requirements
        }
        root = self._root / run_identity
        if not root.exists():
            return ()
        results = []
        for path in sorted(root.glob("*/*/*.json")):
            payload = _read(path)
            response = visual_evidence_v2_response_from_dict(payload.get("response"))
            if (
                payload.get("evidence_sha256") != response.evidence_sha256
                or (response.native_canonical_instrument, response.native_assessment_sha256)
                not in expected
                or response.native_run_identity != run_identity
                or not (
                    path.name == f"{response.chart_revision_sha256}.json"
                    or path.name.startswith(
                        f"{response.chart_revision_sha256}--"
                    )
                )
            ):
                raise ValueError("VISUAL_V2_RESTART_BINDING_INVALID")
            if (
                review_pack_id is not None
                and review_pack_id not in response.source_provenance
            ):
                continue
            results.append(response)
        selected: dict[tuple[str, str, str], VisualEvidenceV2Response] = {}
        for response in results:
            key = (
                response.subject_identity,
                response.timeframe.value,
                response.chart_revision_sha256,
            )
            current = selected.get(key)
            if current is None or (
                response.request_timestamp,
                response.evidence_sha256,
            ) > (
                current.request_timestamp,
                current.evidence_sha256,
            ):
                selected[key] = response
        return tuple(selected[key] for key in sorted(selected))

    def _path(self, response: VisualEvidenceV2Response) -> Path:
        return (
            self._root / response.native_run_identity / _safe(response.subject_identity)
            / response.timeframe.value
            / (
                f"{response.chart_revision_sha256}--"
                f"{_response_request_identity(response)}.json"
            )
        )


def _response_request_identity(response: VisualEvidenceV2Response) -> str:
    return sha256(_canonical({
        "native_run_identity": response.native_run_identity,
        "native_assessment_sha256": response.native_assessment_sha256,
        "native_canonical_instrument": response.native_canonical_instrument,
        "subject_kind": response.subject_kind.value,
        "subject_identity": response.subject_identity,
        "reference_market": response.reference_market,
        "reference_symbol": response.reference_symbol,
        "timeframe": response.timeframe.value,
        "observation_boundary": response.observation_boundary.isoformat(),
        "chart_identity": response.chart_identity,
        "chart_revision_sha256": response.chart_revision_sha256,
        "request_timestamp": response.request_timestamp.isoformat(),
        "source_provenance": response.source_provenance,
    })).hexdigest()


def visual_evidence_v2_provider_schema() -> dict[str, object]:
    non_q10 = tuple(
        item.value
        for item in VisualQuestionV2
        if item is not VisualQuestionV2.VISUAL_FACTS_NOT_CAPTURED_BY_KRONOS
    )
    question_variants = (
        (
            {"type": "string", "enum": list(non_q10)},
            {"type": "string", "minLength": 1, "maxLength": 512},
            {"type": "null"},
        ),
        (
            {
                "type": "string",
                "const": VisualQuestionV2.VISUAL_FACTS_NOT_CAPTURED_BY_KRONOS.value,
            },
            {"type": "string", "const": "NONE"},
            {"type": "null"},
        ),
        (
            {
                "type": "string",
                "const": VisualQuestionV2.VISUAL_FACTS_NOT_CAPTURED_BY_KRONOS.value,
            },
            {
                "type": "string",
                "minLength": 1,
                "maxLength": 512,
            },
            {
                "type": "string", "minLength": 1, "maxLength": 512,
            },
        ),
    )
    evidence_variants = (
        # An available point and an available zone are mutually exclusive.
        (
            {"type": "string", "const": VisualObservationStatus.OBSERVED.value},
            {"type": "string", "const": VisualLevelAvailability.AVAILABLE.value},
            {"type": "number", "minimum": 0.0},
            {"type": "null"}, {"type": "null"},
            {"type": "string", "maxLength": 512},
        ),
        (
            {"type": "string", "const": VisualObservationStatus.OBSERVED.value},
            {"type": "string", "const": VisualLevelAvailability.AVAILABLE.value},
            {"type": "null"},
            {"type": "number", "minimum": 0.0},
            {"type": "number", "minimum": 0.0},
            {"type": "string", "maxLength": 512},
        ),
        # Non-numeric observations cannot manufacture a point or zone.
        (
            {"type": "string", "const": VisualObservationStatus.OBSERVED.value},
            {
                "type": "string",
                "enum": [
                    VisualLevelAvailability.LEVEL_UNAVAILABLE.value,
                    VisualLevelAvailability.NOT_APPLICABLE.value,
                ],
            },
            {"type": "null"}, {"type": "null"}, {"type": "null"},
            {"type": "string", "maxLength": 512},
        ),
        (
            {
                "type": "string",
                "enum": [
                    VisualObservationStatus.NOT_VISIBLE.value,
                    VisualObservationStatus.NOT_APPLICABLE.value,
                ],
            },
            {
                "type": "string",
                "enum": [
                    VisualLevelAvailability.LEVEL_UNAVAILABLE.value,
                    VisualLevelAvailability.NOT_APPLICABLE.value,
                ],
            },
            {"type": "null"}, {"type": "null"}, {"type": "null"},
            {"type": "string", "maxLength": 512},
        ),
        # Partial, unavailable, and invalid evidence must explain its ambiguity.
        (
            {
                "type": "string",
                "enum": [
                    VisualObservationStatus.PARTIAL.value,
                    VisualObservationStatus.UNAVAILABLE.value,
                    VisualObservationStatus.INVALID.value,
                ],
            },
            {
                "type": "string",
                "enum": [
                    VisualLevelAvailability.LEVEL_UNAVAILABLE.value,
                    VisualLevelAvailability.NOT_APPLICABLE.value,
                ],
            },
            {"type": "null"}, {"type": "null"}, {"type": "null"},
            {
                "type": "string", "minLength": 1, "maxLength": 512,
            },
        ),
    )

    def observation_variant(
        question_id: dict[str, object],
        observation: dict[str, object],
        why: dict[str, object],
        status: dict[str, object],
        availability: dict[str, object],
        price: dict[str, object],
        zone_low: dict[str, object],
        zone_high: dict[str, object],
        ambiguity: dict[str, object],
    ) -> dict[str, object]:
        return {
            "type": "object",
            "properties": {
                "question_id": question_id,
                "observation_status": status,
                "observation": observation,
                "level_availability": availability,
                "price": price,
                "zone_low": zone_low,
                "zone_high": zone_high,
                "visible_basis": {
                    "type": "string", "minLength": 1, "maxLength": 512,
                },
                "confidence_in_extraction": {
                    "type": "string", "minLength": 1, "maxLength": 64,
                },
                "ambiguity_reason": ambiguity,
                "why_not_covered_elsewhere": why,
            },
            "required": [
                "question_id", "observation_status", "observation",
                "level_availability", "price", "zone_low", "zone_high",
                "visible_basis", "confidence_in_extraction", "ambiguity_reason",
                "why_not_covered_elsewhere",
            ],
            "additionalProperties": False,
        }
    observation_variants = [
        observation_variant(
            question_id, observation, why,
            status, availability, price, zone_low, zone_high, ambiguity,
        )
        for question_id, observation, why in question_variants
        for status, availability, price, zone_low, zone_high, ambiguity
        in evidence_variants
    ]
    return {
        "type": "object",
        "properties": {
            "observations": {
                "type": "array", "minItems": 10, "maxItems": 10,
                "items": {"anyOf": observation_variants},
            }
        },
        "required": ["observations"],
        "additionalProperties": False,
    }


def validate_visual_evidence_v2_provider_value(value: object) -> None:
    """Validate decoded provider output against the strict provider schema."""

    _validate_provider_schema_value(value, visual_evidence_v2_provider_schema())


def visual_evidence_v2_response_to_dict(response: VisualEvidenceV2Response) -> dict[str, object]:
    return _primitive(asdict(response))


def visual_evidence_v2_response_from_dict(value: object) -> VisualEvidenceV2Response:
    if type(value) is not dict:
        raise ValueError("VISUAL_V2_RESPONSE_INVALID")
    try:
        observations = tuple(
            VisualEvidenceV2Observation(
                question_id=VisualQuestionV2(item["question_id"]),
                timeframe=VisualTimeframe(item["timeframe"]),
                observation_status=VisualObservationStatus(item["observation_status"]),
                observation=item["observation"],
                level_availability=VisualLevelAvailability(item["level_availability"]),
                price=item["price"], zone_low=item["zone_low"], zone_high=item["zone_high"],
                visible_basis=item["visible_basis"],
                source_chart_identity=item["source_chart_identity"],
                source_chart_revision=item["source_chart_revision"],
                confidence_in_extraction=item["confidence_in_extraction"],
                ambiguity_reason=item["ambiguity_reason"],
                provenance=tuple(item["provenance"]),
                why_not_covered_elsewhere=item["why_not_covered_elsewhere"],
            ) for item in value["observations"]
        )
        return VisualEvidenceV2Response(
            provider_identity=value["provider_identity"], model_identity=value["model_identity"],
            request_timestamp=datetime.fromisoformat(value["request_timestamp"]),
            native_run_identity=value["native_run_identity"],
            native_assessment_sha256=value["native_assessment_sha256"],
            native_canonical_instrument=value["native_canonical_instrument"],
            subject_kind=VisualEvidenceSubjectKind(value["subject_kind"]),
            subject_identity=value["subject_identity"], reference_market=value["reference_market"],
            reference_symbol=value["reference_symbol"], timeframe=VisualTimeframe(value["timeframe"]),
            observation_boundary=datetime.fromisoformat(value["observation_boundary"]),
            chart_identity=value["chart_identity"], chart_revision_sha256=value["chart_revision_sha256"],
            observations=observations, source_provenance=tuple(value["source_provenance"]),
            question_set_identity=value["question_set_identity"],
            question_set_version=value["question_set_version"], schema=value["schema"],
            authority=value["authority"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("VISUAL_V2_RESPONSE_INVALID") from error


def _validate_routing(request: VisualEvidenceV2Request, response: VisualEvidenceV2Response) -> None:
    routing = dict(request.routing)
    for item in response.observations:
        if routing[item.question_id] is VisualQuestionRouting.NO and item.observation_status is not VisualObservationStatus.NOT_APPLICABLE:
            raise ValueError("VISUAL_V2_ROUTING_INVALID")


def _validate_q3_gap(request: VisualEvidenceV2Request, response: VisualEvidenceV2Response) -> None:
    item = next(obs for obs in response.observations if obs.question_id is VisualQuestionV2.VISUAL_SUPPORT_RESISTANCE_GAP)
    if item.observation_status is not VisualObservationStatus.OBSERVED:
        return
    candidate = (item.price, item.zone_low, item.zone_high)
    for _, low, high in request.deterministic_context.known_reference_levels:
        known = (low, low if high is None else high)
        if candidate[0] is not None and known[0] <= candidate[0] <= known[1]:
            raise ValueError("VISUAL_V2_Q3_DUPLICATES_DETERMINISTIC_EVIDENCE")
        if candidate[1] is not None and candidate[2] is not None and not (
            candidate[2] < known[0] or candidate[1] > known[1]
        ):
            raise ValueError("VISUAL_V2_Q3_DUPLICATES_DETERMINISTIC_EVIDENCE")


_PROHIBITED_CONSEQUENCES = (
    "CLEAR_AIR", "NO_CLEAR_AIR", "PATH_CLEAR", "PATH_BLOCKED",
    "MATERIAL_BARRIER", "ACCEPT", "DISCARD", "BUY", "SELL",
    "ENTRY_ZONE", "RISK_REWARD", "POSITION_SIZE", "BROKER_ORDER",
)


def _contains_prohibited_consequence(item: VisualEvidenceV2Observation) -> bool:
    material = " ".join(filter(None, (
        item.observation, item.visible_basis, item.ambiguity_reason,
        item.why_not_covered_elsewhere,
    ))).upper()
    normalized = re.sub(r"[^A-Z]+", "_", material).strip("_")
    return any(
        re.search(rf"(?:^|_){re.escape(token)}(?:_|$)", normalized) is not None
        for token in _PROHIBITED_CONSEQUENCES
    )


_FACTUAL_TIMEFRAME = {
    VisualTimeframe.WEEKLY: FactualTimeframe.WEEKLY,
    VisualTimeframe.DAILY: FactualTimeframe.DAILY,
    VisualTimeframe.FOUR_HOUR: FactualTimeframe.FOUR_HOUR,
    VisualTimeframe.ONE_HOUR: FactualTimeframe.ONE_HOUR,
}


def _primitive(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_primitive(item) for item in value]
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _safe(value: str) -> str:
    return re.sub(r"[^A-Z0-9._&-]+", "-", value.upper())


def _read(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("VISUAL_V2_EVIDENCE_UNAVAILABLE") from error
    if type(value) is not dict:
        raise ValueError("VISUAL_V2_EVIDENCE_INVALID")
    return value


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _number(value: object) -> bool:
    return type(value) is float and math.isfinite(value) and value >= 0.0


def _validate_provider_schema_value(value: object, schema: object) -> None:
    if type(schema) is not dict:
        raise TypeError("VISUAL_V2_PROVIDER_SCHEMA_INVALID")
    alternatives = schema.get("anyOf")
    if type(alternatives) is list:
        if not any(_provider_schema_candidate_valid(value, item) for item in alternatives):
            raise ValueError("VISUAL_V2_PROVIDER_SCHEMA_VALUE_INVALID")
        return
    expected = schema.get("type")
    if expected == "object":
        if type(value) is not dict:
            raise TypeError("VISUAL_V2_PROVIDER_SCHEMA_VALUE_INVALID")
        properties = schema.get("properties")
        required = schema.get("required")
        if type(properties) is not dict or type(required) is not list:
            raise TypeError("VISUAL_V2_PROVIDER_SCHEMA_INVALID")
        if set(value) != set(required) or set(value) != set(properties):
            raise ValueError("VISUAL_V2_PROVIDER_SCHEMA_VALUE_INVALID")
        for key, child_schema in properties.items():
            _validate_provider_schema_value(value[key], child_schema)
        return
    if expected == "array":
        if type(value) is not list:
            raise TypeError("VISUAL_V2_PROVIDER_SCHEMA_VALUE_INVALID")
        minimum = schema.get("minItems", 0)
        maximum = schema.get("maxItems", 10_000)
        if type(minimum) is not int or type(maximum) is not int:
            raise TypeError("VISUAL_V2_PROVIDER_SCHEMA_INVALID")
        if not minimum <= len(value) <= maximum:
            raise ValueError("VISUAL_V2_PROVIDER_SCHEMA_VALUE_INVALID")
        for item in value:
            _validate_provider_schema_value(item, schema.get("items"))
        return
    if expected == "string":
        if type(value) is not str:
            raise TypeError("VISUAL_V2_PROVIDER_SCHEMA_VALUE_INVALID")
        if "const" in schema and value != schema["const"]:
            raise ValueError("VISUAL_V2_PROVIDER_SCHEMA_VALUE_INVALID")
        if "enum" in schema and value not in schema["enum"]:
            raise ValueError("VISUAL_V2_PROVIDER_SCHEMA_VALUE_INVALID")
        minimum = schema.get("minLength", 0)
        maximum = schema.get("maxLength", 10_000)
        if type(minimum) is not int or type(maximum) is not int:
            raise TypeError("VISUAL_V2_PROVIDER_SCHEMA_INVALID")
        if not minimum <= len(value) <= maximum:
            raise ValueError("VISUAL_V2_PROVIDER_SCHEMA_VALUE_INVALID")
        pattern = schema.get("pattern")
        if pattern is not None and (
            type(pattern) is not str or re.fullmatch(pattern, value) is None
        ):
            raise ValueError("VISUAL_V2_PROVIDER_SCHEMA_VALUE_INVALID")
        return
    if expected == "number":
        if type(value) not in {int, float} or not math.isfinite(float(value)):
            raise TypeError("VISUAL_V2_PROVIDER_SCHEMA_VALUE_INVALID")
        minimum = schema.get("minimum")
        if minimum is not None and (
            type(minimum) not in {int, float} or float(value) < float(minimum)
        ):
            raise ValueError("VISUAL_V2_PROVIDER_SCHEMA_VALUE_INVALID")
        return
    if expected == "null":
        if value is not None:
            raise TypeError("VISUAL_V2_PROVIDER_SCHEMA_VALUE_INVALID")
        return
    raise TypeError("VISUAL_V2_PROVIDER_SCHEMA_INVALID")


def _provider_schema_candidate_valid(value: object, schema: object) -> bool:
    try:
        _validate_provider_schema_value(value, schema)
    except (TypeError, ValueError):
        return False
    return True


def _text(value: object, maximum: int) -> bool:
    return type(value) is str and bool(value.strip()) and len(value) <= maximum


def _safe_diagnostic_text(value: object, maximum: int) -> bool:
    return (
        type(value) is str
        and bool(value)
        and len(value) <= maximum
        and "\n" not in value
        and "\r" not in value
    )


def _diagnostic_from_dict(
    value: dict[str, object],
) -> VisualEvidenceV2ValidationDiagnostic:
    try:
        return VisualEvidenceV2ValidationDiagnostic(
            native_run_identity=value["native_run_identity"],
            canonical_instrument=value["canonical_instrument"],
            timeframe=VisualTimeframe(value["timeframe"]),
            chart_revision_sha256=value["chart_revision_sha256"],
            model_identity=value["model_identity"],
            attempt=value["attempt"],
            api_request_completed=value["api_request_completed"],
            input_tokens=value["input_tokens"],
            output_tokens=value["output_tokens"],
            total_tokens=value["total_tokens"],
            response_status=value["response_status"],
            validation_stage=VisualEvidenceV2ValidationStage(
                value["validation_stage"]
            ),
            validation_error_code=value["validation_error_code"],
            structural_path=value["structural_path"],
            expected_constraint=value["expected_constraint"],
            received_shape=value["received_shape"],
            retry_disposition=value["retry_disposition"],
            recorded_at=datetime.fromisoformat(value["recorded_at"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("VISUAL_V2_DIAGNOSTIC_INVALID") from error


def _provider_diagnostic_from_dict(
    value: dict[str, object],
) -> VisualEvidenceV2ProviderDiagnostic:
    try:
        return VisualEvidenceV2ProviderDiagnostic(
            http_status=value["http_status"],
            error_type=value["error_type"],
            error_code=value["error_code"],
            rejected_parameter=value["rejected_parameter"],
            provider_message=value["provider_message"],
            model_identity=value["model_identity"],
            timeframe=VisualTimeframe(value["timeframe"]),
            schema_identity=value["schema_identity"],
            schema_version=value["schema_version"],
            request_timestamp=datetime.fromisoformat(value["request_timestamp"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("VISUAL_V2_PROVIDER_DIAGNOSTIC_INVALID") from error


__all__ = [
    "DEFAULT_VISUAL_EVIDENCE_V2_DIAGNOSTIC_ROOT",
    "DEFAULT_VISUAL_EVIDENCE_V2_ROOT", "FROZEN_VISUAL_QUESTION_SET_V2",
    "LocalVisualEvidenceV2DiagnosticStore",
    "LocalVisualEvidenceV2Store", "OPENAI_VISUAL_EVIDENCE_V2_PROVIDER_ID",
    "VISUAL_EVIDENCE_V2_AUTHORITY", "VISUAL_EVIDENCE_V2_SCHEMA",
    "VISUAL_EVIDENCE_V2_PROVIDER_SCHEMA_VERSION",
    "VISUAL_QUESTION_SET_V2_ID", "VISUAL_QUESTION_SET_V2_VERSION",
    "VISUAL_QUESTION_SEMANTICS_V2",
    "VisualDeterministicContext", "VisualEvidenceSubjectKind",
    "VisualEvidenceV2Observation", "VisualEvidenceV2Provider",
    "VisualEvidenceV2ProviderDiagnostic",
    "VisualEvidenceV2Request", "VisualEvidenceV2Response",
    "VisualEvidenceV2ValidationDiagnostic", "VisualEvidenceV2ValidationStage",
    "VisualLevelAvailability", "VisualObservationStatus", "VisualQuestionRouting",
    "VisualQuestionV2", "VisualTimeframe", "build_visual_evidence_v2_request",
    "validate_visual_evidence_v2_provider_value",
    "visual_evidence_v2_provider_schema", "visual_evidence_v2_response_from_dict",
    "visual_evidence_v2_response_to_dict", "visual_question_routing",
]
