"""Immutable MCX Native + international-reference visual Review contracts.

This module is a visual-evidence foundation.  It deliberately contains no
cross-market synthesis, promotion, trading, Risk, or execution consequence.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import json
import re
from typing import Mapping

from kronos.instrument.active_derivative import ActiveDerivativeBindingArtifact
from kronos.intraday.mcx_commissioning import (
    McxCommissioningState,
    load_mcx_commissioning_publication,
)
from kronos.intraday.review import ReviewError, ReviewFailure
from kronos.intraday.review_v2 import ReviewCycleV2


MCX_PAIRED_CONTRACT_VERSION = "1.0.0"
MCX_PAIRED_CHART_REVISION_IDENTITY = "KRONOS-INTRADAY-MCX-PAIRED-CHART-REVISION-V1"
MCX_PAIRED_CHART_BUNDLE_IDENTITY = "KRONOS-INTRADAY-MCX-PAIRED-CHART-BUNDLE-V1"
MCX_PAIRED_REVIEW_PACK_IDENTITY = "KRONOS-INTRADAY-MCX-PAIRED-REVIEW-PACK-V1"
MCX_PAIRED_QUESTION_SET_IDENTITY = (
    "KRONOS-INTRADAY-MCX-REFERENCE-CHART-ANALYST-QUESTION-SET-V1"
)
MCX_PAIRED_QUESTION_SET_VERSION = "1.0.0"
MCX_PAIRED_IMPORTED_EVIDENCE_IDENTITY = (
    "KRONOS-INTRADAY-MCX-PAIRED-IMPORTED-VISUAL-EVIDENCE-V1"
)
MCX_PAIRED_ARCHITECTURE_IDENTITY = (
    "KRONOS-INTRADAY-WO-10-E-I-M-FROZEN-ARCHITECTURE-V1"
)
MCX_PAIRED_ARCHITECTURE_VERSION = "1.0.0"
MCX_PAIRED_VISUAL_TIMEFRAMES = ("1D", "4H", "15M", "5M")
NATIVE_MACHINE_REGIME_TIMEFRAME = "1H"
VISUAL_4H_AUTHORITY = "HIGHER_ORDER_VISUAL_CONTEXT_ONLY"
MCX_MACHINE_RSI_AUTHORITY = "EXTERNAL_CANONICAL_NUMERICAL_AUTHORITY"
REFERENCE_RSI_AUTHORITY = "VISUAL_CONTEXT_ONLY"
PAIRED_REVIEW_AUTHORITY = "INDEPENDENT_VISUAL_OBSERVATION_ONLY"


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


def _texts(values: tuple[object, ...]) -> bool:
    return bool(values) and all(_text(item) for item in values)


class ReferenceVenue(StrEnum):
    COMEX = "COMEX"
    NYMEX = "NYMEX"


class ReferenceSeriesKind(StrEnum):
    CONTINUOUS = "CONTINUOUS"
    LISTED_CONTRACT = "LISTED_CONTRACT"


class ChartSide(StrEnum):
    NATIVE_MCX = "NATIVE_MCX"
    INTERNATIONAL_REFERENCE = "INTERNATIONAL_REFERENCE"


@dataclass(frozen=True, slots=True)
class McxReferenceRelationship:
    canonical_mcx_subject_identity: str
    reference_analytical_subject_identity: str
    reference_name: str
    venue: ReferenceVenue
    governed_visible_identity: str
    series_kind: ReferenceSeriesKind

    def __post_init__(self) -> None:
        if (
            not self.canonical_mcx_subject_identity.startswith("MCX-SUBJECT-")
            or not self.reference_analytical_subject_identity.startswith("REFERENCE-SUBJECT-")
            or not _texts((self.reference_name, self.governed_visible_identity))
            or type(self.venue) is not ReferenceVenue
            or type(self.series_kind) is not ReferenceSeriesKind
            or self.series_kind is ReferenceSeriesKind.CONTINUOUS
            and not self.governed_visible_identity.endswith("1!")
        ):
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)


MCX_REFERENCE_RELATIONSHIPS = (
    McxReferenceRelationship("MCX-SUBJECT-GOLDM", "REFERENCE-SUBJECT-COMEX-GOLD", "COMEX Gold", ReferenceVenue.COMEX, "COMEX:GC1!", ReferenceSeriesKind.CONTINUOUS),
    McxReferenceRelationship("MCX-SUBJECT-SILVERM", "REFERENCE-SUBJECT-COMEX-SILVER", "COMEX Silver", ReferenceVenue.COMEX, "COMEX:SI1!", ReferenceSeriesKind.CONTINUOUS),
    McxReferenceRelationship("MCX-SUBJECT-COPPER", "REFERENCE-SUBJECT-COMEX-COPPER", "COMEX Copper", ReferenceVenue.COMEX, "COMEX:HG1!", ReferenceSeriesKind.CONTINUOUS),
    McxReferenceRelationship("MCX-SUBJECT-CRUDE", "REFERENCE-SUBJECT-NYMEX-CRUDE-OIL", "NYMEX Crude Oil", ReferenceVenue.NYMEX, "NYMEX:CL1!", ReferenceSeriesKind.CONTINUOUS),
    McxReferenceRelationship("MCX-SUBJECT-NATGAS", "REFERENCE-SUBJECT-NYMEX-NATURAL-GAS", "NYMEX Natural Gas", ReferenceVenue.NYMEX, "NYMEX:NG1!", ReferenceSeriesKind.CONTINUOUS),
)


def relationship_for_subject(subject_identity: str) -> McxReferenceRelationship:
    matches = tuple(item for item in MCX_REFERENCE_RELATIONSHIPS if item.canonical_mcx_subject_identity == subject_identity)
    if len(matches) != 1:
        raise ReviewError(ReviewFailure.NOT_ELIGIBLE)
    return matches[0]


@dataclass(frozen=True, slots=True)
class McxNativeIdentityBinding:
    canonical_subject_identity: str
    actual_derivative_contract_identity: str
    provider_symbol: str
    active_binding_identity: str
    active_binding_integrity_identity: str
    active_binding_supersedes: str | None
    contract_expiry: str
    commissioning_publication_identity: str
    commissioning_publication_integrity_identity: str
    commissioning_state: McxCommissioningState
    roll_history_identity: str
    observation_boundary: datetime

    def __post_init__(self) -> None:
        if (
            not self.canonical_subject_identity.startswith("MCX-SUBJECT-")
            or not _texts((self.actual_derivative_contract_identity, self.provider_symbol,
                           self.active_binding_identity, self.active_binding_integrity_identity,
                           self.contract_expiry, self.commissioning_publication_identity,
                           self.commissioning_publication_integrity_identity,
                           self.roll_history_identity))
            or type(self.commissioning_state) is not McxCommissioningState
            or not _aware(self.observation_boundary)
            or self.active_binding_supersedes is not None and not _text(self.active_binding_supersedes)
        ):
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)


def bind_native_identity(
    cycle: ReviewCycleV2,
    active_binding: ActiveDerivativeBindingArtifact,
    *,
    roll_history_identity: str,
) -> McxNativeIdentityBinding:
    if (
        type(cycle) is not ReviewCycleV2
        or type(active_binding) is not ActiveDerivativeBindingArtifact
        or cycle.canonical_subject_identity != active_binding.canonical_subject_id
        or cycle.analysis_boundary != active_binding.observation_boundary
        or cycle.mcx_commissioning is None
        or not _text(roll_history_identity)
    ):
        raise ReviewError(ReviewFailure.NOT_ELIGIBLE)
    publication = load_mcx_commissioning_publication()
    entry = publication.subject(cycle.canonical_subject_identity)
    if entry.state is not McxCommissioningState.COMMISSIONED:
        raise ReviewError(ReviewFailure.NOT_ELIGIBLE)
    return McxNativeIdentityBinding(
        canonical_subject_identity=cycle.canonical_subject_identity,
        actual_derivative_contract_identity=active_binding.active_binding.derivative_contract_id,
        provider_symbol=active_binding.provider_symbol,
        active_binding_identity=active_binding.binding_identity,
        active_binding_integrity_identity=active_binding.integrity_identity,
        active_binding_supersedes=active_binding.active_binding.supersedes,
        contract_expiry=active_binding.contract_expiry.isoformat(),
        commissioning_publication_identity=publication.publication_identity,
        commissioning_publication_integrity_identity=publication.integrity_identity,
        commissioning_state=entry.state,
        roll_history_identity=roll_history_identity,
        observation_boundary=cycle.analysis_boundary,
    )


@dataclass(frozen=True, slots=True)
class UsdinrEvidenceBinding:
    evidence_identity: str
    timeframe: str
    observation_boundary: datetime
    integrity_identity: str
    authority: str = "CURRENCY_TRANSLATION_CONTEXT_ONLY"

    def __post_init__(self) -> None:
        if (
            not _texts((self.evidence_identity, self.timeframe, self.integrity_identity))
            or not _aware(self.observation_boundary)
            or self.authority != "CURRENCY_TRANSLATION_CONTEXT_ONLY"
        ):
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)


@dataclass(frozen=True, slots=True)
class McxPairedChartRevision:
    chart_revision_identity: str
    chart_artifact_identity: str
    side: ChartSide
    review_cycle_identity: str
    expected_subject_identity: str
    expected_visible_identity: str
    venue: str
    series_kind: ReferenceSeriesKind | None
    listed_contract_identity: str | None
    observation_boundary: datetime
    payload_sha256: str
    media_type: str
    byte_count: int
    timeframes: tuple[str, ...]
    revision_ordinal: int
    received_at: datetime
    integrity_identity: str
    schema_identity: str = MCX_PAIRED_CHART_REVISION_IDENTITY
    schema_version: str = MCX_PAIRED_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "chart_revision_identity", "integrity_identity")
        reference = self.side is ChartSide.INTERNATIONAL_REFERENCE
        if (
            type(self.side) is not ChartSide
            or not _texts((self.chart_artifact_identity, self.review_cycle_identity,
                           self.expected_subject_identity, self.expected_visible_identity,
                           self.venue))
            or not _aware(self.observation_boundary) or not _aware(self.received_at)
            or not _sha(self.payload_sha256)
            or self.media_type not in {"image/png", "image/jpeg"}
            or type(self.byte_count) is not int or self.byte_count < 1
            or self.timeframes != MCX_PAIRED_VISUAL_TIMEFRAMES
            or type(self.revision_ordinal) is not int or self.revision_ordinal < 1
            or reference != (self.series_kind is not None)
            or not reference and self.listed_contract_identity is not None
            or reference and self.series_kind is ReferenceSeriesKind.LISTED_CONTRACT
            and not _text(self.listed_contract_identity)
            or reference and self.series_kind is ReferenceSeriesKind.CONTINUOUS
            and self.listed_contract_identity is not None
            or self.schema_identity != MCX_PAIRED_CHART_REVISION_IDENTITY
            or self.schema_version != MCX_PAIRED_CONTRACT_VERSION
            or self.chart_revision_identity != _identity("INTRADAY-MCX-PAIRED-CHART-REVISION-", values)
            or self.integrity_identity != _identity("INTEGRITY-INTRADAY-MCX-PAIRED-CHART-REVISION-", values)
        ):
            raise ReviewError(ReviewFailure.CHART_INVALID)


def create_paired_chart_revision(*, payload: bytes, **fields: object) -> McxPairedChartRevision:
    if type(payload) is not bytes or not payload:
        raise ReviewError(ReviewFailure.CHART_INVALID)
    values = dict(fields)
    values.setdefault("payload_sha256", sha256(payload).hexdigest())
    values.setdefault("byte_count", len(payload))
    values.setdefault("timeframes", MCX_PAIRED_VISUAL_TIMEFRAMES)
    values.setdefault("schema_identity", MCX_PAIRED_CHART_REVISION_IDENTITY)
    values.setdefault("schema_version", MCX_PAIRED_CONTRACT_VERSION)
    values.setdefault("chart_artifact_identity", _identity("INTRADAY-MCX-PAIRED-CHART-ARTIFACT-", {"payload_sha256": values["payload_sha256"], "media_type": values.get("media_type")}))
    return McxPairedChartRevision(
        chart_revision_identity=_identity("INTRADAY-MCX-PAIRED-CHART-REVISION-", values),
        integrity_identity=_identity("INTEGRITY-INTRADAY-MCX-PAIRED-CHART-REVISION-", values),
        **values,  # type: ignore[arg-type]
    )


@dataclass(frozen=True, slots=True)
class McxPairedChartBundle:
    bundle_identity: str
    review_cycle_identity: str
    probables_run_identity: str
    probable_result_identity: str
    canonical_mcx_subject_identity: str
    direction: str
    phase: str
    analysis_boundary: datetime
    native_identity_binding: McxNativeIdentityBinding
    reference_relationship: McxReferenceRelationship
    native_chart_revision_identity: str
    native_chart_payload_sha256: str
    reference_chart_revision_identity: str
    reference_chart_payload_sha256: str
    usdinr_evidence: UsdinrEvidenceBinding | None
    architecture_identity: str
    architecture_version: str
    integrity_identity: str
    schema_identity: str = MCX_PAIRED_CHART_BUNDLE_IDENTITY
    schema_version: str = MCX_PAIRED_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "bundle_identity", "integrity_identity")
        if (
            not _texts((self.review_cycle_identity, self.probables_run_identity,
                        self.probable_result_identity, self.canonical_mcx_subject_identity,
                        self.direction, self.phase, self.native_chart_revision_identity,
                        self.reference_chart_revision_identity))
            or self.direction not in {"LONG", "SHORT"}
            or not _aware(self.analysis_boundary)
            or type(self.native_identity_binding) is not McxNativeIdentityBinding
            or type(self.reference_relationship) is not McxReferenceRelationship
            or self.native_identity_binding.canonical_subject_identity != self.canonical_mcx_subject_identity
            or self.reference_relationship.canonical_mcx_subject_identity != self.canonical_mcx_subject_identity
            or not _sha(self.native_chart_payload_sha256) or not _sha(self.reference_chart_payload_sha256)
            or self.usdinr_evidence is not None and type(self.usdinr_evidence) is not UsdinrEvidenceBinding
            or self.architecture_identity != MCX_PAIRED_ARCHITECTURE_IDENTITY
            or self.architecture_version != MCX_PAIRED_ARCHITECTURE_VERSION
            or self.schema_identity != MCX_PAIRED_CHART_BUNDLE_IDENTITY
            or self.schema_version != MCX_PAIRED_CONTRACT_VERSION
            or self.bundle_identity != _identity("INTRADAY-MCX-PAIRED-CHART-BUNDLE-", values)
            or self.integrity_identity != _identity("INTEGRITY-INTRADAY-MCX-PAIRED-CHART-BUNDLE-", values)
        ):
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)


def create_paired_chart_bundle(
    *, cycle: ReviewCycleV2, native_binding: McxNativeIdentityBinding,
    native_chart: McxPairedChartRevision, reference_chart: McxPairedChartRevision,
    reference_relationship: McxReferenceRelationship,
    usdinr_evidence: UsdinrEvidenceBinding | None = None,
) -> McxPairedChartBundle:
    if (
        type(cycle) is not ReviewCycleV2
        or native_chart.side is not ChartSide.NATIVE_MCX
        or reference_chart.side is not ChartSide.INTERNATIONAL_REFERENCE
        or native_chart.review_cycle_identity != cycle.cycle_identity
        or reference_chart.review_cycle_identity != cycle.cycle_identity
        or native_chart.expected_subject_identity != cycle.canonical_subject_identity
        or reference_chart.expected_subject_identity != reference_relationship.reference_analytical_subject_identity
        or reference_chart.expected_visible_identity != reference_relationship.governed_visible_identity
        or reference_chart.series_kind is not reference_relationship.series_kind
        or native_binding.canonical_subject_identity != cycle.canonical_subject_identity
        or reference_relationship.canonical_mcx_subject_identity != cycle.canonical_subject_identity
        or native_chart.observation_boundary != cycle.analysis_boundary
        or reference_chart.observation_boundary != cycle.analysis_boundary
    ):
        raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
    values = {
        "review_cycle_identity": cycle.cycle_identity,
        "probables_run_identity": cycle.probables_run_identity,
        "probable_result_identity": cycle.probable_result_identity,
        "canonical_mcx_subject_identity": cycle.canonical_subject_identity,
        "direction": cycle.direction,
        "phase": cycle.phase.value,
        "analysis_boundary": cycle.analysis_boundary,
        "native_identity_binding": native_binding,
        "reference_relationship": reference_relationship,
        "native_chart_revision_identity": native_chart.chart_revision_identity,
        "native_chart_payload_sha256": native_chart.payload_sha256,
        "reference_chart_revision_identity": reference_chart.chart_revision_identity,
        "reference_chart_payload_sha256": reference_chart.payload_sha256,
        "usdinr_evidence": usdinr_evidence,
        "architecture_identity": MCX_PAIRED_ARCHITECTURE_IDENTITY,
        "architecture_version": MCX_PAIRED_ARCHITECTURE_VERSION,
        "schema_identity": MCX_PAIRED_CHART_BUNDLE_IDENTITY,
        "schema_version": MCX_PAIRED_CONTRACT_VERSION,
    }
    return McxPairedChartBundle(
        bundle_identity=_identity("INTRADAY-MCX-PAIRED-CHART-BUNDLE-", values),
        integrity_identity=_identity("INTEGRITY-INTRADAY-MCX-PAIRED-CHART-BUNDLE-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class McxPairedQuestion:
    question_id: str
    side: str
    observation: str
    timeframe: str
    allowed_answers: tuple[str, ...]
    authority: str = PAIRED_REVIEW_AUTHORITY

    def __post_init__(self) -> None:
        if not _texts((self.question_id, self.side, self.observation, self.timeframe, self.authority)) or not _texts(self.allowed_answers):
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)


_DIRECTION = ("BULLISH", "BEARISH", "NEUTRAL", "MIXED", "UNCLEAR", "NOT_VISIBLE")
_CONDITION = ("PRESENT", "ABSENT", "UNCLEAR", "NOT_VISIBLE")
_PROGRESSION = ("ADVANCING", "DECLINING", "BALANCED", "MIXED", "UNCLEAR", "NOT_VISIBLE")
_RAILWAY = ("ORDERED_ALIGNED", "MIXED_TRANSITIONING", "CONVERGING_CRISSCROSSING", "UNCLEAR", "NOT_VISIBLE")
_RSI = ("OVERBOUGHT", "OVERSOLD", "MIDRANGE_NEITHER", "UNCLEAR", "NOT_VISIBLE")

MCX_PAIRED_QUESTIONS = (
    McxPairedQuestion("M01", "NATIVE_MCX", "BROADER_CONTEXT", "1D", _DIRECTION),
    McxPairedQuestion("M02", "NATIVE_MCX", "STRUCTURE", "4H", _DIRECTION),
    McxPairedQuestion("M03", "NATIVE_MCX", "DIRECTIONAL_STRUCTURE", "15M", _DIRECTION),
    McxPairedQuestion("M04", "NATIVE_MCX", "DETERIORATION_OR_FAILED_CONTINUATION", "15M", _CONDITION),
    McxPairedQuestion("M05", "NATIVE_MCX", "PROGRESSION", "5M", _PROGRESSION),
    McxPairedQuestion("M06", "NATIVE_MCX", "VISIBLE_OBSTACLE_OR_LOCATION", "MULTI", _CONDITION),
    McxPairedQuestion("M07", "NATIVE_MCX", "EXTENSION_OR_MATURITY", "MULTI", ("EARLY", "DEVELOPING", "EXTENDED", "UNCLEAR", "NOT_VISIBLE")),
    McxPairedQuestion("M08", "NATIVE_MCX", "ACCEPTANCE_OR_REJECTION", "MULTI", ("ACCEPTANCE", "REJECTION", "NEITHER", "UNCLEAR", "NOT_VISIBLE")),
    McxPairedQuestion("M09", "NATIVE_MCX", "RAILWAY_TRACK_VISUAL_CONDITION", "MULTI", _RAILWAY),
    McxPairedQuestion("M10", "NATIVE_MCX", "RSI_VISUAL_CONDITION", "MULTI", _RSI),
    McxPairedQuestion("R01", "INTERNATIONAL_REFERENCE", "BROADER_CONTEXT", "1D", _DIRECTION),
    McxPairedQuestion("R02", "INTERNATIONAL_REFERENCE", "STRUCTURE", "4H", _DIRECTION),
    McxPairedQuestion("R03", "INTERNATIONAL_REFERENCE", "DIRECTION", "15M", _DIRECTION),
    McxPairedQuestion("R04", "INTERNATIONAL_REFERENCE", "PROGRESSION", "5M", _PROGRESSION),
    McxPairedQuestion("R05", "INTERNATIONAL_REFERENCE", "RAILWAY_TRACK_VISUAL_CONDITION", "MULTI", _RAILWAY),
    McxPairedQuestion("R06", "INTERNATIONAL_REFERENCE", "RSI_VISUAL_CONDITION", "MULTI", _RSI),
    McxPairedQuestion("X01", "ESCAPE_HATCH", "MATERIAL_UNCAPTURED_VISUAL_OBSERVATION", "MULTI", ("NONE", "MATERIAL_OBSERVATION")),
)


@dataclass(frozen=True, slots=True)
class McxPairedReviewPack:
    review_pack_identity: str
    paired_bundle_identity: str
    review_cycle_identity: str
    probables_run_identity: str
    probable_result_identity: str
    canonical_mcx_subject_identity: str
    direction: str
    phase: str
    analysis_boundary: datetime
    native_chart_revision_identity: str
    reference_chart_revision_identity: str
    question_set_identity: str
    question_set_version: str
    questions: tuple[McxPairedQuestion, ...]
    created_at: datetime
    authority: str
    integrity_identity: str
    schema_identity: str = MCX_PAIRED_REVIEW_PACK_IDENTITY
    schema_version: str = MCX_PAIRED_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "review_pack_identity", "integrity_identity")
        if (
            not _texts((self.paired_bundle_identity, self.review_cycle_identity,
                        self.probables_run_identity, self.probable_result_identity,
                        self.canonical_mcx_subject_identity, self.direction, self.phase,
                        self.native_chart_revision_identity, self.reference_chart_revision_identity))
            or self.direction not in {"LONG", "SHORT"}
            or not _aware(self.analysis_boundary) or not _aware(self.created_at)
            or self.question_set_identity != MCX_PAIRED_QUESTION_SET_IDENTITY
            or self.question_set_version != MCX_PAIRED_QUESTION_SET_VERSION
            or self.questions != MCX_PAIRED_QUESTIONS
            or self.authority != PAIRED_REVIEW_AUTHORITY
            or self.schema_identity != MCX_PAIRED_REVIEW_PACK_IDENTITY
            or self.schema_version != MCX_PAIRED_CONTRACT_VERSION
            or self.review_pack_identity != _identity("INTRADAY-MCX-PAIRED-REVIEW-PACK-", values)
            or self.integrity_identity != _identity("INTEGRITY-INTRADAY-MCX-PAIRED-REVIEW-PACK-", values)
        ):
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)


def create_paired_review_pack(bundle: McxPairedChartBundle, *, created_at: datetime) -> McxPairedReviewPack:
    if type(bundle) is not McxPairedChartBundle or not _aware(created_at):
        raise ReviewError(ReviewFailure.INPUT_INVALID)
    values = {
        "paired_bundle_identity": bundle.bundle_identity,
        "review_cycle_identity": bundle.review_cycle_identity,
        "probables_run_identity": bundle.probables_run_identity,
        "probable_result_identity": bundle.probable_result_identity,
        "canonical_mcx_subject_identity": bundle.canonical_mcx_subject_identity,
        "direction": bundle.direction,
        "phase": bundle.phase,
        "analysis_boundary": bundle.analysis_boundary,
        "native_chart_revision_identity": bundle.native_chart_revision_identity,
        "reference_chart_revision_identity": bundle.reference_chart_revision_identity,
        "question_set_identity": MCX_PAIRED_QUESTION_SET_IDENTITY,
        "question_set_version": MCX_PAIRED_QUESTION_SET_VERSION,
        "questions": MCX_PAIRED_QUESTIONS,
        "created_at": created_at,
        "authority": PAIRED_REVIEW_AUTHORITY,
        "schema_identity": MCX_PAIRED_REVIEW_PACK_IDENTITY,
        "schema_version": MCX_PAIRED_CONTRACT_VERSION,
    }
    return McxPairedReviewPack(
        review_pack_identity=_identity("INTRADAY-MCX-PAIRED-REVIEW-PACK-", values),
        integrity_identity=_identity("INTEGRITY-INTRADAY-MCX-PAIRED-REVIEW-PACK-", values),
        **values,
    )


def artifact_bytes(value: object) -> bytes:
    if not is_dataclass(value):
        raise ReviewError(ReviewFailure.INPUT_INVALID)
    return _canonical(_normalize(value)) + b"\n"


def artifact_from_bytes(payload: bytes) -> object:
    try:
        raw = json.loads(payload.decode("utf-8"))
        if type(raw) is not dict:
            raise ValueError
        schema = raw.get("schema_identity")
        values = dict(raw)
        if schema == MCX_PAIRED_CHART_REVISION_IDENTITY:
            values["side"] = ChartSide(values["side"])
            values["series_kind"] = ReferenceSeriesKind(values["series_kind"]) if values["series_kind"] is not None else None
            values["observation_boundary"] = datetime.fromisoformat(values["observation_boundary"])
            values["received_at"] = datetime.fromisoformat(values["received_at"])
            values["timeframes"] = tuple(values["timeframes"])
            value: object = McxPairedChartRevision(**values)
        elif schema == MCX_PAIRED_CHART_BUNDLE_IDENTITY:
            native = values["native_identity_binding"]
            native["commissioning_state"] = McxCommissioningState(native["commissioning_state"])
            native["observation_boundary"] = datetime.fromisoformat(native["observation_boundary"])
            values["native_identity_binding"] = McxNativeIdentityBinding(**native)
            relationship = values["reference_relationship"]
            relationship["venue"] = ReferenceVenue(relationship["venue"])
            relationship["series_kind"] = ReferenceSeriesKind(relationship["series_kind"])
            values["reference_relationship"] = McxReferenceRelationship(**relationship)
            values["analysis_boundary"] = datetime.fromisoformat(values["analysis_boundary"])
            if values["usdinr_evidence"] is not None:
                usd = values["usdinr_evidence"]
                usd["observation_boundary"] = datetime.fromisoformat(usd["observation_boundary"])
                values["usdinr_evidence"] = UsdinrEvidenceBinding(**usd)
            value = McxPairedChartBundle(**values)
        elif schema == MCX_PAIRED_REVIEW_PACK_IDENTITY:
            values["analysis_boundary"] = datetime.fromisoformat(values["analysis_boundary"])
            values["created_at"] = datetime.fromisoformat(values["created_at"])
            values["questions"] = tuple(McxPairedQuestion(
                question_id=item["question_id"], side=item["side"], observation=item["observation"],
                timeframe=item["timeframe"], allowed_answers=tuple(item["allowed_answers"]), authority=item["authority"],
            ) for item in values["questions"])
            value = McxPairedReviewPack(**values)
        else:
            raise ValueError
        if artifact_bytes(value) != payload:
            raise ValueError
        return value
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise ReviewError(ReviewFailure.INTEGRITY_INVALID) from error


def _without(value: object, *names: str) -> dict[str, object]:
    return {name: item for name, item in asdict(value).items() if name not in names}


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(_canonical(_normalize(value))).hexdigest().upper()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _normalize(value: object) -> object:
    if is_dataclass(value):
        return _normalize(asdict(value))
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(name): _normalize(item) for name, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    return value


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _sha(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


__all__ = [name for name in globals() if name.startswith("MCX_") or name in {
    "ChartSide", "ReferenceSeriesKind", "ReferenceVenue", "McxReferenceRelationship",
    "McxNativeIdentityBinding", "UsdinrEvidenceBinding", "McxPairedChartRevision",
    "McxPairedChartBundle", "McxPairedQuestion", "McxPairedReviewPack",
    "relationship_for_subject", "bind_native_identity", "create_paired_chart_revision",
    "create_paired_chart_bundle", "create_paired_review_pack", "artifact_bytes", "artifact_from_bytes",
}]
