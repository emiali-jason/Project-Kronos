"""Read-only current-state projection for Intraday Statistics / Excel."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from kronos.application.intraday_review_v2 import IntradayReviewV2Snapshot
from kronos.intraday.operational_readiness import (
    WO_B_CONTRACT_VERSION,
    WO_B_PRODUCT_IDENTITY,
    WoBSourceBoundary,
)
from kronos.intraday.probables import ProbableState
from kronos.intraday.probables_v2 import ProbablesRunV2
from kronos.intraday.review_v2 import (
    CURRENT_REVIEW_V2_POINTER_IDENTITY,
    REVIEW_V2_CONTRACT_VERSION,
)


INTRADAY_STATISTICS_SCHEMA_IDENTITY = "KRONOS-INTRADAY-STATISTICS-EXPORT-V1"
INTRADAY_STATISTICS_SCHEMA_VERSION = "1.0.0"
INTRADAY_STATISTICS_AUTHORITY = "DERIVED_PROJECTION"

SUMMARY_COLUMNS = (
    "Metric",
    "Value",
    "State",
    "Source Identity",
    "Source Schema Identity",
    "Source Schema Version",
    "Analysis Boundary",
    "Generated At",
)

CANDIDATE_COLUMNS = (
    "Sponsor Label",
    "Canonical Subject Identity",
    "Market Family",
    "Direction",
    "Probable State",
    "Probable Result Identity",
    "Probables Run Identity",
    "Analysis Boundary",
    "Phase",
    "Methodology Identity",
    "Methodology Version",
    "Methodology Publication Identity",
    "Review Cycle Identity",
    "Review State",
    "Chart State",
    "Chart Revision Identity",
    "Chart Revision Ordinal",
    "Chart Payload SHA-256",
    "Review Pack State",
    "Question Pack State",
    "Question Transport Identity",
    "Question Filename",
    "Expected Answer Filename",
    "Answer State",
    "Answer Pack Identity",
    "Visual Evidence State",
    "Visual Evidence Identity",
    "Visual Identity State",
    "Observed Visible Subject Identity",
    "Resolved Canonical Subject Identity",
    "Next Governed Stage",
    "WO-B Review Snapshot Identity",
    "Active Contract Identity",
)

STAGE_COLUMNS = (
    "Sponsor Label",
    "Canonical Subject Identity",
    "Candidate Identity",
    "Direction",
    "Probables Run Identity",
    "WO-B Review Snapshot Identity",
    "Review Boundary",
    "Source Boundary",
    "Source State",
    "Source Reason",
    "Classification",
    "Classification Basis",
    "Next Governed Stage",
    "Source Reference Identity",
    "Source Artifact Identity",
    "Source Schema Identity",
    "Source Schema Version",
    "Source Policy Identity",
    "Source Policy Version",
    "Observed At",
    "Current At Review Boundary",
    "Superseded",
)

_STAGE_ORDER = (
    WoBSourceBoundary.DOMAIN_001_INSTRUMENT.value,
    WoBSourceBoundary.DOMAIN_008_SESSION.value,
    WoBSourceBoundary.PROBABLES.value,
    WoBSourceBoundary.ANALYTICAL_PROMOTION.value,
    WoBSourceBoundary.WO13_TRADE_PLAN.value,
    WoBSourceBoundary.WO14_RISK_OBSERVATION.value,
    WoBSourceBoundary.WO15_TIMING_HANDOFF.value,
    WoBSourceBoundary.WO16_SPONSOR_LIFECYCLE.value,
    WoBSourceBoundary.WO17_POSITION_MONITORING.value,
)
_ADMITTED = {ProbableState.LONG_PROBABLE, ProbableState.SHORT_PROBABLE}
_UNAVAILABLE = "UNAVAILABLE"


class IntradayStatisticsError(RuntimeError):
    """Bounded projection failure safe for Browser classification."""


@dataclass(frozen=True, slots=True)
class IntradayStatisticsMetric:
    metric: str
    value: int | str
    state: str
    source_identity: str
    source_schema_identity: str
    source_schema_version: str
    analysis_boundary: datetime
    generated_at: datetime


@dataclass(frozen=True, slots=True)
class IntradayStatisticsRow:
    values: tuple[object, ...]

    def __post_init__(self) -> None:
        if not self.values or any(value is None for value in self.values):
            raise ValueError("INTRADAY_STATISTICS_ROW_INVALID")


@dataclass(frozen=True, slots=True)
class IntradayStatisticsProjection:
    probables_run_identity: str
    analysis_boundary: datetime
    generated_at: datetime
    metrics: tuple[IntradayStatisticsMetric, ...]
    candidates: tuple[IntradayStatisticsRow, ...]
    stages: tuple[IntradayStatisticsRow, ...]
    schema_identity: str = INTRADAY_STATISTICS_SCHEMA_IDENTITY
    schema_version: str = INTRADAY_STATISTICS_SCHEMA_VERSION
    authority: str = INTRADAY_STATISTICS_AUTHORITY

    def __post_init__(self) -> None:
        metric_keys = tuple(item.metric for item in self.metrics)
        candidate_keys = tuple(
            (item.values[6], item.values[5]) for item in self.candidates
        )
        stage_keys = tuple(
            (
                item.values[5]
                if item.values[5] != _UNAVAILABLE
                else item.values[2],
                item.values[7],
            )
            for item in self.stages
        )
        if (
            not _text(self.probables_run_identity)
            or not _aware(self.analysis_boundary)
            or not _aware(self.generated_at)
            or len(set(metric_keys)) != len(metric_keys)
            or len(set(candidate_keys)) != len(candidate_keys)
            or len(set(stage_keys)) != len(stage_keys)
            or any(len(item.values) != len(CANDIDATE_COLUMNS) for item in self.candidates)
            or any(len(item.values) != len(STAGE_COLUMNS) for item in self.stages)
            or len(self.stages) != len(self.candidates) * len(_STAGE_ORDER)
            or self.schema_identity != INTRADAY_STATISTICS_SCHEMA_IDENTITY
            or self.schema_version != INTRADAY_STATISTICS_SCHEMA_VERSION
            or self.authority != INTRADAY_STATISTICS_AUTHORITY
        ):
            raise ValueError("INTRADAY_STATISTICS_PROJECTION_INVALID")


class IntradayStatisticsApplication:
    """Load exact current evidence and build one inert export projection."""

    def __init__(
        self,
        *,
        current_probables: Callable[[], ProbablesRunV2 | None],
        current_review: Callable[[], IntradayReviewV2Snapshot],
        operational_readiness: Callable[[], dict[str, object]],
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not all(callable(item) for item in (
            current_probables, current_review, operational_readiness, clock
        )):
            raise ValueError("INTRADAY_STATISTICS_APPLICATION_INVALID")
        self._current_probables = current_probables
        self._current_review = current_review
        self._operational_readiness = operational_readiness
        self._clock = clock

    def project(self) -> IntradayStatisticsProjection:
        generated_at = self._clock()
        if not _aware(generated_at):
            raise IntradayStatisticsError("INTRADAY_STATISTICS_CLOCK_INVALID")
        return project_intraday_statistics(
            self._current_probables(),
            self._current_review(),
            self._operational_readiness(),
            generated_at=generated_at,
        )


def project_intraday_statistics(
    run: ProbablesRunV2 | None,
    review: IntradayReviewV2Snapshot,
    readiness: dict[str, object],
    *,
    generated_at: datetime,
) -> IntradayStatisticsProjection:
    """Join only the exact current lineage and preserve unavailable truth."""

    if run is None:
        raise IntradayStatisticsError("INTRADAY_STATISTICS_CURRENT_PROBABLES_UNAVAILABLE")
    if type(run) is not ProbablesRunV2 or not _aware(generated_at):
        raise IntradayStatisticsError("INTRADAY_STATISTICS_INPUT_INVALID")
    if type(review) is not IntradayReviewV2Snapshot or type(readiness) is not dict:
        raise IntradayStatisticsError("INTRADAY_STATISTICS_INPUT_INVALID")

    admitted = tuple(item for item in run.results if item.state in _ADMITTED)
    if len(admitted) > run.diagnostics.starting_population:
        raise IntradayStatisticsError("INTRADAY_STATISTICS_CARDINALITY_INVALID")
    probable_ids = tuple(item.result_identity for item in admitted)
    if len(set(probable_ids)) != len(probable_ids):
        raise IntradayStatisticsError("INTRADAY_STATISTICS_DUPLICATE_CANDIDATE")

    review_by_result = _review_candidates(review, run, set(probable_ids))
    readiness_by_subject = _readiness_reviews(readiness, run, admitted)

    ordered = tuple(sorted(
        admitted,
        key=lambda item: (
            _sponsor_label(item.canonical_subject_identity).casefold(),
            item.canonical_subject_identity,
            item.result_identity,
        ),
    ))
    candidates = tuple(
        _candidate_row(item, run, review_by_result.get(item.result_identity),
                       readiness_by_subject.get(item.canonical_subject_identity))
        for item in ordered
    )
    stages = tuple(
        row
        for item in ordered
        for row in _stage_rows(
            item,
            run,
            readiness_by_subject.get(item.canonical_subject_identity),
        )
    )
    metrics = _metrics(
        run,
        review,
        readiness,
        stages=stages,
        review_available=review.probables_run_identity is not None,
        generated_at=generated_at,
    )
    return IntradayStatisticsProjection(
        probables_run_identity=run.run_identity,
        analysis_boundary=run.analysis_boundary,
        generated_at=generated_at,
        metrics=metrics,
        candidates=candidates,
        stages=stages,
    )


def _review_candidates(
    review: IntradayReviewV2Snapshot,
    run: ProbablesRunV2,
    probable_ids: set[str],
) -> dict[str, object]:
    if review.probables_run_identity is None:
        if review.current_pointer_identity is not None or review.candidates:
            raise IntradayStatisticsError("INTRADAY_STATISTICS_REVIEW_LINEAGE_INVALID")
        return {}
    if review.probables_run_identity != run.run_identity:
        raise IntradayStatisticsError("INTRADAY_STATISTICS_HISTORICAL_REVIEW_REJECTED")
    by_result = {item.probable_result_identity: item for item in review.candidates}
    if len(by_result) != len(review.candidates):
        raise IntradayStatisticsError("INTRADAY_STATISTICS_DUPLICATE_REVIEW")
    if set(by_result) != probable_ids or any(
        item.analysis_boundary != run.analysis_boundary
        or item.canonical_subject_identity
        != next(
            result.canonical_subject_identity
            for result in run.results
            if result.result_identity == item.probable_result_identity
        )
        for item in review.candidates
    ):
        raise IntradayStatisticsError("INTRADAY_STATISTICS_REVIEW_LINEAGE_INVALID")
    return by_result


def _readiness_reviews(
    readiness: dict[str, object],
    run: ProbablesRunV2,
    admitted: tuple[object, ...],
) -> dict[str, dict[str, object]]:
    raw = readiness.get("reviews", ())
    if type(raw) not in {tuple, list}:
        raise IntradayStatisticsError("INTRADAY_STATISTICS_WO_B_INVALID")
    allowed = {item.canonical_subject_identity for item in admitted}
    by_subject: dict[str, dict[str, object]] = {}
    for item in raw:
        if type(item) is not dict:
            raise IntradayStatisticsError("INTRADAY_STATISTICS_WO_B_INVALID")
        subject = item.get("canonical_subject_identity")
        if (
            type(subject) is not str
            or subject not in allowed
            or item.get("analysis_run_identity") != run.run_identity
            or subject in by_subject
        ):
            raise IntradayStatisticsError("INTRADAY_STATISTICS_WO_B_LINEAGE_INVALID")
        by_subject[subject] = item
    return by_subject


def _candidate_row(item, run, review, readiness) -> IntradayStatisticsRow:  # type: ignore[no-untyped-def]
    unavailable = _UNAVAILABLE
    market_family = (
        readiness.get("market_family")
        if readiness is not None
        else _market_family(item.canonical_subject_identity)
    )
    active_contract = None if readiness is None else readiness.get("active_contract_identity")
    return IntradayStatisticsRow((
        _sponsor_label(item.canonical_subject_identity),
        item.canonical_subject_identity,
        _available(market_family),
        item.direction.value,
        item.state.value,
        item.result_identity,
        run.run_identity,
        run.analysis_boundary,
        unavailable if item.phase is None else item.phase.value,
        item.methodology_identity,
        item.methodology_version,
        item.methodology_publication_identity,
        unavailable if review is None else review.cycle_identity,
        unavailable if review is None else review.review_state,
        unavailable if review is None else review.chart_state,
        unavailable if review is None else _available(review.chart_revision_identity),
        unavailable if review is None else _available(review.chart_revision_ordinal),
        unavailable if review is None else _available(review.chart_payload_sha256),
        unavailable if review is None else review.review_pack_state,
        unavailable if review is None else review.question_pack_state,
        unavailable if review is None else _available(review.question_transport_identity),
        unavailable if review is None else _available(review.question_filename),
        unavailable if review is None else _available(review.expected_answer_filename),
        unavailable if review is None else review.answer_state,
        unavailable if review is None else _available(review.answer_pack_identity),
        unavailable if review is None else review.visual_evidence_state,
        unavailable if review is None else _available(review.visual_evidence_identity),
        unavailable if review is None else review.visual_identity_state,
        unavailable if review is None else _available(review.observed_visible_subject_identity),
        unavailable if review is None else _available(review.resolved_canonical_subject_identity),
        unavailable if readiness is None else _available(readiness.get("next_governed_stage")),
        unavailable if readiness is None else _available(readiness.get("review_snapshot_identity")),
        (
            "NOT_APPLICABLE"
            if market_family != "MCX"
            else _available(active_contract)
        ),
    ))


def _stage_rows(item, run, readiness) -> tuple[IntradayStatisticsRow, ...]:  # type: ignore[no-untyped-def]
    if readiness is None:
        return tuple(
            IntradayStatisticsRow((
                _sponsor_label(item.canonical_subject_identity),
                item.canonical_subject_identity,
                item.result_identity,
                item.direction.value,
                run.run_identity,
                _UNAVAILABLE,
                _UNAVAILABLE,
                boundary,
                _UNAVAILABLE,
                "WO_B_REVIEW_UNAVAILABLE",
                _UNAVAILABLE,
                _UNAVAILABLE,
                _UNAVAILABLE,
                _UNAVAILABLE,
                _UNAVAILABLE,
                _UNAVAILABLE,
                _UNAVAILABLE,
                _UNAVAILABLE,
                _UNAVAILABLE,
                _UNAVAILABLE,
                _UNAVAILABLE,
                _UNAVAILABLE,
            ))
            for boundary in _STAGE_ORDER
        )
    raw_items = readiness.get("items", ())
    raw_refs = readiness.get("source_references", ())
    if type(raw_items) not in {tuple, list} or type(raw_refs) not in {tuple, list}:
        raise IntradayStatisticsError("INTRADAY_STATISTICS_WO_B_INVALID")
    items = _unique_by_boundary(raw_items, "INTRADAY_STATISTICS_DUPLICATE_STAGE")
    refs = _unique_by_boundary(raw_refs, "INTRADAY_STATISTICS_DUPLICATE_SOURCE")
    unknown = (set(items) | set(refs)).difference(_STAGE_ORDER)
    if unknown:
        raise IntradayStatisticsError("INTRADAY_STATISTICS_WO_B_INVALID")
    rows = []
    for boundary in _STAGE_ORDER:
        stage = items.get(boundary)
        reference = refs.get(boundary)
        schema_identity, schema_version = _split_binding(
            None if reference is None else reference.get("schema")
        )
        policy_identity, policy_version = _split_binding(
            None if reference is None else reference.get("policy")
        )
        rows.append(IntradayStatisticsRow((
            _sponsor_label(item.canonical_subject_identity),
            item.canonical_subject_identity,
            _available(readiness.get("candidate_identity")),
            item.direction.value,
            run.run_identity,
            _available(readiness.get("review_snapshot_identity")),
            _available(readiness.get("review_boundary")),
            boundary,
            _UNAVAILABLE if stage is None else _available(stage.get("source_state")),
            _UNAVAILABLE if stage is None else _available(stage.get("source_reason")),
            _UNAVAILABLE if stage is None else _available(stage.get("classification")),
            _UNAVAILABLE if stage is None else _available(stage.get("classification_basis")),
            _UNAVAILABLE if stage is None else _available(stage.get("next_governed_stage")),
            _UNAVAILABLE if stage is None else _available(stage.get("source_reference_identity")),
            _UNAVAILABLE if reference is None else _available(reference.get("artifact_identity")),
            schema_identity,
            schema_version,
            policy_identity,
            policy_version,
            _UNAVAILABLE if reference is None else _available(reference.get("observed_at")),
            _UNAVAILABLE if reference is None else _boolean(reference.get("current")),
            _UNAVAILABLE if reference is None else _boolean(reference.get("superseded")),
        )))
    return tuple(rows)


def _metrics(
    run: ProbablesRunV2,
    review: IntradayReviewV2Snapshot,
    readiness: dict[str, object],
    *,
    stages: tuple[IntradayStatisticsRow, ...],
    review_available: bool,
    generated_at: datetime,
) -> tuple[IntradayStatisticsMetric, ...]:
    diagnostics = run.diagnostics
    probable_values = (
        ("Starting Population", diagnostics.starting_population),
        ("Evaluable Population", diagnostics.evaluable_count),
        ("Unavailable Population", diagnostics.unavailable_count),
        ("Admitted Probables", diagnostics.total_probables),
        ("LONG", diagnostics.long_probables),
        ("SHORT", diagnostics.short_probables),
        ("Not Admitted", diagnostics.not_admitted_count),
        ("Conflicting", diagnostics.conflicting_count),
    )
    review_values = (
        ("Review Cycles", len(review.candidates)),
        ("Charts Ready", sum(item.chart_state == "CHART_READY" for item in review.candidates)),
        ("Review Packs Ready", sum(item.review_pack_state == "READY" for item in review.candidates)),
        ("Question Packs Created", sum(item.question_pack_state == "CREATED" for item in review.candidates)),
        ("Question Packs Transport Ready", sum(item.question_pack_state == "TRANSPORT_READY" for item in review.candidates)),
        ("Answers Imported", sum(item.answer_state == "IMPORTED" for item in review.candidates)),
        ("Answers Not Imported", sum(item.answer_state == "NOT_IMPORTED" for item in review.candidates)),
        ("Visual Evidence Ready", sum(item.visual_evidence_state == "READY" for item in review.candidates)),
        ("Visual Evidence Absent", sum(item.visual_evidence_state == "ABSENT" for item in review.candidates)),
    )
    raw_reviews = readiness.get("reviews", ())
    stage_values = {state: 0 for state in (
        "AVAILABLE", "TERMINAL", "NOT_REACHED", "WAITING", "BLOCKED", "UNAVAILABLE"
    )}
    readiness_available = type(raw_reviews) in {tuple, list} and bool(raw_reviews)
    if type(raw_reviews) not in {tuple, list}:
        raise IntradayStatisticsError("INTRADAY_STATISTICS_WO_B_INVALID")
    if readiness_available:
        for stage in stages:
            classification = stage.values[10]
            if classification == _UNAVAILABLE:
                classification = "UNAVAILABLE"
            if classification not in stage_values:
                raise IntradayStatisticsError("INTRADAY_STATISTICS_WO_B_INVALID")
            stage_values[classification] += 1

    metrics = []
    for name, value in probable_values:
        metrics.append(_metric(
            name, value, "AVAILABLE", run.run_identity, run.schema_identity,
            run.schema_version, run, generated_at,
        ))
    review_source = _available(review.current_pointer_identity)
    for name, value in review_values:
        metrics.append(_metric(
            name,
            value if review_available else _UNAVAILABLE,
            "AVAILABLE" if review_available else _UNAVAILABLE,
            review_source,
            CURRENT_REVIEW_V2_POINTER_IDENTITY,
            REVIEW_V2_CONTRACT_VERSION,
            run,
            generated_at,
        ))
    readiness_source = _available(readiness.get("product_identity"))
    for state in ("AVAILABLE", "TERMINAL", "NOT_REACHED", "WAITING", "BLOCKED", "UNAVAILABLE"):
        metrics.append(_metric(
            f"WO-B {state}",
            stage_values[state] if readiness_available else "NOT_REACHED",
            "AVAILABLE" if readiness_available else "NOT_REACHED",
            readiness_source,
            WO_B_PRODUCT_IDENTITY,
            WO_B_CONTRACT_VERSION,
            run,
            generated_at,
        ))
    return tuple(metrics)


def _metric(name, value, state, source, schema, version, run, generated):  # type: ignore[no-untyped-def]
    return IntradayStatisticsMetric(
        name, value, state, source, schema, version,
        run.analysis_boundary, generated,
    )


def _unique_by_boundary(values: object, failure: str) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for value in values:  # type: ignore[union-attr]
        if type(value) is not dict or type(value.get("source_boundary")) is not str:
            raise IntradayStatisticsError("INTRADAY_STATISTICS_WO_B_INVALID")
        boundary = value["source_boundary"]
        if boundary in result:
            raise IntradayStatisticsError(failure)
        result[boundary] = value
    return result


def _split_binding(value: object) -> tuple[str, str]:
    if type(value) is not str or " / " not in value:
        return _UNAVAILABLE, _UNAVAILABLE
    identity, version = value.rsplit(" / ", 1)
    if not identity or not version:
        return _UNAVAILABLE, _UNAVAILABLE
    return identity, version


def _available(value: object) -> object:
    return _UNAVAILABLE if value is None or value == "" else value


def _boolean(value: object) -> str:
    if type(value) is bool:
        return "TRUE" if value else "FALSE"
    return _UNAVAILABLE


def _market_family(subject: str) -> str:
    if subject.startswith("MCX-SUBJECT-"):
        return "MCX"
    if subject.startswith("NSE-INDEX-"):
        return "NSE_INDEX"
    if subject.startswith("NSE-EQ-"):
        return "NSE_EQUITY"
    return _UNAVAILABLE


def _sponsor_label(subject: str) -> str:
    for prefix in ("NSE-EQ-", "NSE-INDEX-", "MCX-SUBJECT-"):
        if subject.startswith(prefix):
            return subject.removeprefix(prefix)
    return subject


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


__all__ = [
    "CANDIDATE_COLUMNS",
    "INTRADAY_STATISTICS_AUTHORITY",
    "INTRADAY_STATISTICS_SCHEMA_IDENTITY",
    "INTRADAY_STATISTICS_SCHEMA_VERSION",
    "STAGE_COLUMNS",
    "SUMMARY_COLUMNS",
    "IntradayStatisticsApplication",
    "IntradayStatisticsError",
    "IntradayStatisticsMetric",
    "IntradayStatisticsProjection",
    "IntradayStatisticsRow",
    "project_intraday_statistics",
]
