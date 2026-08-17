"""Immutable Native-Discovery Review binding and bounded Layer-2 reconciliation."""

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

from kronos.swing.run_identity import is_swing_analysis_run_id
from kronos.swing.v1.layer2 import ReadinessAssessment, ReadinessState
from kronos.swing.v1.models import PivotKind, V1Direction
from kronos.swing.v1.mtf_facts import (
    CompletedTimeframeFact,
    FactualTimeframe,
    SameRunMtfFactSnapshot,
)
from kronos.swing.v1.native_discovery import (
    Native1DState,
    Native1HState,
    Native1WState,
    Native4HState,
    NativeContextKind,
    NativeDiscoveryRun,
    NativeDiscoveryStatus,
    NativeInstrumentDiscovery,
    NativeOpportunityIdentity,
    NativeProductPath,
)
from kronos.swing.v1.pine_evidence import (
    McxPineEvidenceExtension,
    PineLayer2EvidenceHandoff,
    PineProduct,
    ReferenceMarket,
)


NATIVE_REVIEW_SCHEMA = "KRONOS-SWING-V1-NATIVE-REVIEW-V1"
NATIVE_REVIEW_AUTHORITY = "NATIVE_PROBABLE_REVIEW_INPUT"
MCX_REFERENCE_AUTHORITY = "REFERENCE_ONLY_NO_DISCOVERY_TRADE_OR_EXECUTION_AUTHORITY"
DEFAULT_NATIVE_REVIEW_EVIDENCE_ROOT = (
    Path.home()
    / "Library"
    / "Application Support"
    / "KRONOS"
    / "evidence"
    / "swing-v1"
    / "native-review"
)


class NativeLayer2EvidenceState(StrEnum):
    SUPPORTS_NATIVE_THESIS = "SUPPORTS_NATIVE_THESIS"
    CONTRADICTS_NATIVE_THESIS = "CONTRADICTS_NATIVE_THESIS"
    MIXED = "MIXED"
    UNAVAILABLE = "UNAVAILABLE"


class McxReferenceStatus(StrEnum):
    REQUIRED = "REQUIRED"
    RECEIVED = "RECEIVED"
    ANALYZED = "ANALYZED"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID = "INVALID"


class McxReferenceEvidenceState(StrEnum):
    SUPPORTS = "SUPPORTS"
    NEUTRAL = "NEUTRAL"
    CONTRADICTS = "CONTRADICTS"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID = "INVALID"


@dataclass(frozen=True, slots=True)
class McxReferenceRequirement:
    native_run_identity: str
    native_assessment_sha256: str
    mcx_canonical_instrument: str
    direction: V1Direction
    opportunity_identity: NativeOpportunityIdentity
    product_path: NativeProductPath
    operative_anchor_identity: str
    operative_anchor_price: float
    operative_anchor_boundary: datetime
    provider_provenance: tuple[str, ...]
    reference_subject_identity: str
    reference_market: ReferenceMarket
    reference_symbol: str
    requirement_sha256: str
    authority: str = MCX_REFERENCE_AUTHORITY

    def __post_init__(self) -> None:
        if (
            not is_swing_analysis_run_id(self.native_run_identity)
            or re.fullmatch(r"[0-9a-f]{64}", self.native_assessment_sha256) is None
            or self.mcx_canonical_instrument not in MCX_REFERENCE_MAPPINGS
            or self.direction not in {V1Direction.LONG, V1Direction.SHORT}
            or type(self.opportunity_identity) is not NativeOpportunityIdentity
            or self.product_path is not NativeProductPath.MCX
            or not self.operative_anchor_identity
            or type(self.operative_anchor_price) is not float
            or not math.isfinite(self.operative_anchor_price)
            or not _aware(self.operative_anchor_boundary)
            or not self.provider_provenance
            or not self.reference_subject_identity
            or type(self.reference_market) is not ReferenceMarket
            or not self.reference_symbol
            or re.fullmatch(r"[0-9a-f]{64}", self.requirement_sha256) is None
            or self.authority != MCX_REFERENCE_AUTHORITY
            or (
                self.reference_subject_identity,
                self.reference_market,
                self.reference_symbol,
            ) != MCX_REFERENCE_MAPPINGS[self.mcx_canonical_instrument]
        ):
            raise ValueError("MCX_REFERENCE_REQUIREMENT_INVALID")


@dataclass(frozen=True, slots=True)
class McxReferenceResult:
    requirement: McxReferenceRequirement
    status: McxReferenceStatus
    evidence_state: McxReferenceEvidenceState
    chart_revision_sha256: str | None
    reference_evidence_sha256: str | None
    observation_boundaries: tuple[tuple[str, datetime], ...]
    source_provenance: tuple[str, ...]
    binding_status: str
    reason: str

    def __post_init__(self) -> None:
        has_evidence = self.status in {
            McxReferenceStatus.RECEIVED, McxReferenceStatus.ANALYZED,
            McxReferenceStatus.INVALID,
        }
        if (
            type(self.requirement) is not McxReferenceRequirement
            or type(self.status) is not McxReferenceStatus
            or type(self.evidence_state) is not McxReferenceEvidenceState
            or (self.chart_revision_sha256 is not None and re.fullmatch(r"[0-9a-f]{64}", self.chart_revision_sha256) is None)
            or (self.reference_evidence_sha256 is not None and re.fullmatch(r"[0-9a-f]{64}", self.reference_evidence_sha256) is None)
            or (has_evidence and (self.chart_revision_sha256 is None or self.reference_evidence_sha256 is None))
            or type(self.observation_boundaries) is not tuple
            or any(not name or not _aware(boundary) for name, boundary in self.observation_boundaries)
            or type(self.source_provenance) is not tuple
            or not self.binding_status
            or not self.reason
            or (self.status is McxReferenceStatus.UNAVAILABLE and self.evidence_state is not McxReferenceEvidenceState.UNAVAILABLE)
            or (self.status is McxReferenceStatus.INVALID and self.evidence_state is not McxReferenceEvidenceState.INVALID)
        ):
            raise ValueError("MCX_REFERENCE_RESULT_INVALID")


MCX_REFERENCE_MAPPINGS: dict[str, tuple[str, ReferenceMarket, str]] = {
    "GOLDM": ("COMEX Gold", ReferenceMarket.COMEX, "COMEX:GC1!"),
    "SILVERM": ("COMEX Silver", ReferenceMarket.COMEX, "COMEX:SI1!"),
    "COPPER": ("COMEX Copper", ReferenceMarket.COMEX, "COMEX:HG1!"),
    "CRUDEOIL": ("NYMEX Crude Oil", ReferenceMarket.NYMEX, "NYMEX:CL1!"),
    "NATURALGAS": ("NYMEX Natural Gas", ReferenceMarket.NYMEX, "NYMEX:NG1!"),
}


@dataclass(frozen=True, slots=True)
class NativeReviewPivot:
    timeframe: FactualTimeframe
    radius: int
    kind: PivotKind
    timestamp: datetime
    price: float

    def __post_init__(self) -> None:
        if (
            type(self.timeframe) is not FactualTimeframe
            or self.radius not in {1, 2}
            or type(self.kind) is not PivotKind
            or not _aware(self.timestamp)
            or type(self.price) is not float
            or not math.isfinite(self.price)
            or self.price < 0.0
        ):
            raise ValueError("NATIVE_REVIEW_PIVOT_INVALID")


@dataclass(frozen=True, slots=True)
class NativeReviewTimeframeFacts:
    timeframe: FactualTimeframe
    observation_boundary: datetime
    source_timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    sma20: float | None
    sma50: float | None
    sma200: float | None
    prior_sma20_5bars: float | None
    prior_sma50_5bars: float | None
    prior_sma200_5bars: float | None
    prior_20_volume_mean: float | None
    pivots: tuple[NativeReviewPivot, ...]
    calendar_identity: str
    calendar_version: str
    session_identity: str
    provider_identity: str
    provenance: tuple[str, ...]

    def __post_init__(self) -> None:
        numbers = (
            self.open, self.high, self.low, self.close, self.sma20, self.sma50,
            self.sma200, self.prior_sma20_5bars, self.prior_sma50_5bars,
            self.prior_sma200_5bars, self.prior_20_volume_mean,
        )
        if (
            type(self.timeframe) is not FactualTimeframe
            or not _aware(self.observation_boundary)
            or not _aware(self.source_timestamp)
            or any(
                item is not None
                and (type(item) is not float or not math.isfinite(item) or item < 0.0)
                for item in numbers
            )
            or type(self.volume) is not int
            or self.volume < 0
            or type(self.pivots) is not tuple
            or any(item.timeframe is not self.timeframe for item in self.pivots)
            or not all((self.calendar_identity, self.calendar_version,
                        self.session_identity, self.provider_identity))
            or not self.provenance
        ):
            raise ValueError("NATIVE_REVIEW_TIMEFRAME_FACTS_INVALID")


@dataclass(frozen=True, slots=True)
class NativeReviewThesis:
    native_run_identity: str
    native_assessment_sha256: str
    canonical_instrument: str
    direction: V1Direction
    product_path: NativeProductPath
    context_kind: NativeContextKind
    opportunity_identity: NativeOpportunityIdentity
    weekly_state: Native1WState
    daily_state: Native1DState
    four_hour_state: Native4HState
    one_hour_state: Native1HState
    operative_anchor_identity: str
    operative_anchor_price: float
    operative_anchor_boundary: datetime
    timeframe_facts: tuple[NativeReviewTimeframeFacts, ...]
    native_policy_identity: str
    native_policy_version: str
    provider_provenance: tuple[str, ...]
    calendar_provenance: tuple[str, ...]
    authority: str = NATIVE_REVIEW_AUTHORITY

    def __post_init__(self) -> None:
        if (
            not is_swing_analysis_run_id(self.native_run_identity)
            or re.fullmatch(r"[0-9a-f]{64}", self.native_assessment_sha256) is None
            or not self.canonical_instrument
            or self.direction not in {V1Direction.LONG, V1Direction.SHORT}
            or type(self.product_path) is not NativeProductPath
            or type(self.context_kind) is not NativeContextKind
            or type(self.opportunity_identity) is not NativeOpportunityIdentity
            or type(self.weekly_state) is not Native1WState
            or type(self.daily_state) is not Native1DState
            or type(self.four_hour_state) is not Native4HState
            or type(self.one_hour_state) is not Native1HState
            or not self.operative_anchor_identity
            or type(self.operative_anchor_price) is not float
            or not math.isfinite(self.operative_anchor_price)
            or self.operative_anchor_price < 0.0
            or not _aware(self.operative_anchor_boundary)
            or tuple(item.timeframe for item in self.timeframe_facts)
            != tuple(FactualTimeframe)
            or not self.native_policy_identity
            or not self.native_policy_version
            or not self.provider_provenance
            or not self.calendar_provenance
            or self.authority != NATIVE_REVIEW_AUTHORITY
        ):
            raise ValueError("NATIVE_REVIEW_THESIS_INVALID")


@dataclass(frozen=True, slots=True)
class NativeReviewRequirement:
    thesis: NativeReviewThesis
    required_timeframes: tuple[FactualTimeframe, ...]
    requirement_sha256: str
    mcx_reference: McxReferenceRequirement | None = None
    status: str = "NATIVE_REVIEW_REQUIRED"
    schema: str = NATIVE_REVIEW_SCHEMA

    def __post_init__(self) -> None:
        if (
            type(self.thesis) is not NativeReviewThesis
            or self.required_timeframes != tuple(FactualTimeframe)
            or re.fullmatch(r"[0-9a-f]{64}", self.requirement_sha256) is None
            or (
                self.thesis.product_path is NativeProductPath.MCX
                and type(self.mcx_reference) is not McxReferenceRequirement
            )
            or (
                self.thesis.product_path is NativeProductPath.NSE
                and self.mcx_reference is not None
            )
            or self.status != "NATIVE_REVIEW_REQUIRED"
            or self.schema != NATIVE_REVIEW_SCHEMA
        ):
            raise ValueError("NATIVE_REVIEW_REQUIREMENT_INVALID")

    @property
    def canonical_instrument(self) -> str:
        return self.thesis.canonical_instrument

    @property
    def native_run_identity(self) -> str:
        return self.thesis.native_run_identity


@dataclass(frozen=True, slots=True)
class NativeIndependentLayer2Evidence:
    native_run_identity: str
    canonical_instrument: str
    timeframe_states: tuple[tuple[FactualTimeframe, NativeLayer2EvidenceState], ...]
    pine_state: NativeLayer2EvidenceState
    source_provenance: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not is_swing_analysis_run_id(self.native_run_identity)
            or not self.canonical_instrument
            or tuple(item[0] for item in self.timeframe_states) != tuple(FactualTimeframe)
            or any(type(item[1]) is not NativeLayer2EvidenceState for item in self.timeframe_states)
            or type(self.pine_state) is not NativeLayer2EvidenceState
            or not self.source_provenance
        ):
            raise ValueError("NATIVE_LAYER2_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class NativeLayer2ReviewRecord:
    requirement: NativeReviewRequirement
    evidence: NativeIndependentLayer2Evidence
    reconciliation: NativeLayer2EvidenceState
    contradictions: tuple[str, ...]
    readiness: ReadinessAssessment
    mcx_reference_result: McxReferenceResult | None = None
    native_thesis_unchanged: bool = True

    def __post_init__(self) -> None:
        if (
            type(self.requirement) is not NativeReviewRequirement
            or type(self.evidence) is not NativeIndependentLayer2Evidence
            or type(self.reconciliation) is not NativeLayer2EvidenceState
            or type(self.contradictions) is not tuple
            or type(self.readiness) is not ReadinessAssessment
            or (
                self.mcx_reference_result is not None
                and (
                    type(self.mcx_reference_result) is not McxReferenceResult
                    or self.requirement.mcx_reference
                    != self.mcx_reference_result.requirement
                )
            )
            or not self.native_thesis_unchanged
            or self.evidence.native_run_identity != self.requirement.native_run_identity
            or self.evidence.canonical_instrument != self.requirement.canonical_instrument
        ):
            raise ValueError("NATIVE_LAYER2_REVIEW_RECORD_INVALID")


def build_native_review_requirements(
    native_run: NativeDiscoveryRun,
    facts: SameRunMtfFactSnapshot,
) -> tuple[NativeReviewRequirement, ...]:
    """Project only same-run Native Probables; no legacy assessment is created."""

    if (
        type(native_run) is not NativeDiscoveryRun
        or type(facts) is not SameRunMtfFactSnapshot
        or native_run.run_identity != facts.run_identity
        or native_run.provider_source_identity != facts.provider_source_identity
    ):
        raise ValueError("NATIVE_REVIEW_SAME_RUN_BINDING_INVALID")
    values = []
    for assessment in native_run.assessments:
        if assessment.status is not NativeDiscoveryStatus.PROBABLE:
            continue
        if assessment.weekly_state is Native1WState.OPPOSING:
            raise ValueError("NATIVE_REVIEW_OPPOSING_WEEKLY_CONTEXT_REJECTED")
        values.append(_requirement(native_run, assessment, facts))
    return tuple(values)


def reconcile_native_layer2(
    requirement: NativeReviewRequirement,
    evidence: NativeIndependentLayer2Evidence,
    mcx_reference_result: McxReferenceResult | None = None,
) -> NativeLayer2ReviewRecord:
    """Reconcile independent evidence without rerunning or rewriting Discovery."""

    if (
        type(requirement) is not NativeReviewRequirement
        or type(evidence) is not NativeIndependentLayer2Evidence
        or evidence.native_run_identity != requirement.native_run_identity
        or evidence.canonical_instrument != requirement.canonical_instrument
        or (
            mcx_reference_result is not None
            and mcx_reference_result.requirement != requirement.mcx_reference
        )
    ):
        raise ValueError("NATIVE_LAYER2_BINDING_INVALID")
    dimensions = (*evidence.timeframe_states, ("PINE", evidence.pine_state))
    states = tuple(item[1] for item in dimensions)
    reconciliation = (
        NativeLayer2EvidenceState.CONTRADICTS_NATIVE_THESIS
        if NativeLayer2EvidenceState.CONTRADICTS_NATIVE_THESIS in states
        else NativeLayer2EvidenceState.MIXED
        if NativeLayer2EvidenceState.MIXED in states
        else NativeLayer2EvidenceState.SUPPORTS_NATIVE_THESIS
        if NativeLayer2EvidenceState.SUPPORTS_NATIVE_THESIS in states
        else NativeLayer2EvidenceState.UNAVAILABLE
    )
    contradictions = tuple(
        f"{getattr(identity, 'value', identity)}_CONTRADICTS_NATIVE_THESIS"
        for identity, state in dimensions
        if state is NativeLayer2EvidenceState.CONTRADICTS_NATIVE_THESIS
    )
    unresolved = tuple(
        f"{getattr(identity, 'value', identity)}_{state.value}"
        for identity, state in dimensions
        if state in {NativeLayer2EvidenceState.MIXED, NativeLayer2EvidenceState.UNAVAILABLE}
    )
    supporting = tuple(
        f"{getattr(identity, 'value', identity)}_SUPPORTS_NATIVE_THESIS"
        for identity, state in dimensions
        if state is NativeLayer2EvidenceState.SUPPORTS_NATIVE_THESIS
    )
    readiness = ReadinessAssessment(
        run_identity=requirement.native_run_identity,
        canonical_instrument=requirement.canonical_instrument,
        observation_boundary=max(
            item.observation_boundary for item in requirement.thesis.timeframe_facts
        ),
        probable_assessment_identities=(
            requirement.thesis.native_assessment_sha256,
        ),
        state=ReadinessState.CONTEXT_INCOMPLETE,
        primary_reason="NATIVE_LAYER2_REQUIRES_SEPARATE_READINESS_ASSESSMENT",
        supporting_evidence=supporting,
        contradicting_evidence=contradictions,
        unresolved_evidence=unresolved,
        provenance=evidence.source_provenance,
    )
    return NativeLayer2ReviewRecord(
        requirement, evidence, reconciliation, contradictions, readiness,
        mcx_reference_result,
    )


def bind_mcx_reference_evidence(
    requirement: NativeReviewRequirement,
    handoff: PineLayer2EvidenceHandoff,
    *,
    native_run_identity: str,
    mcx_canonical_instrument: str,
    chart_revision_sha256: str,
    expected_chart_revision_sha256: str,
    expected_timeframe: str,
    evidence_state: McxReferenceEvidenceState,
) -> McxReferenceResult:
    """Bind validated reference facts; mismatches become explicit INVALID evidence."""

    reference = requirement.mcx_reference
    if reference is None:
        raise ValueError("MCX_REFERENCE_NOT_REQUIRED")
    extension = handoff.mcx
    valid = (
        type(handoff) is PineLayer2EvidenceHandoff
        and handoff.product is PineProduct.MCX
        and type(extension) is McxPineEvidenceExtension
        and native_run_identity == reference.native_run_identity
        and mcx_canonical_instrument == reference.mcx_canonical_instrument
        and extension.reference_market is reference.reference_market
        and extension.reference_symbol == reference.reference_symbol
        and re.fullmatch(r"[0-9a-f]{64}", chart_revision_sha256) is not None
        and chart_revision_sha256 == expected_chart_revision_sha256
        and handoff.timeframe == expected_timeframe
        and evidence_state not in {
            McxReferenceEvidenceState.UNAVAILABLE,
            McxReferenceEvidenceState.INVALID,
        }
    )
    retained_revision_sha256 = (
        chart_revision_sha256
        if re.fullmatch(r"[0-9a-f]{64}", chart_revision_sha256)
        else sha256(chart_revision_sha256.encode("utf-8")).hexdigest()
    )
    boundaries = ((handoff.timeframe, handoff.observation_boundary.chart_bar_close_ts),)
    provenance = (
        handoff.provenance.publisher,
        handoff.provenance.lineage_identity,
        handoff.provenance.publication_identity,
        *reference.provider_provenance,
    )
    if not valid:
        return McxReferenceResult(
            reference, McxReferenceStatus.INVALID,
            McxReferenceEvidenceState.INVALID,
            retained_revision_sha256,
            handoff.event_id,
            boundaries,
            provenance,
            "INVALID",
            "MCX_REFERENCE_BINDING_INVALID",
        )
    return McxReferenceResult(
        reference, McxReferenceStatus.ANALYZED, evidence_state,
        chart_revision_sha256, handoff.event_id, boundaries, provenance,
        "SAME_RUN_REFERENCE_BOUND", "REFERENCE_EVIDENCE_ANALYZED",
    )


def unavailable_mcx_reference(requirement: NativeReviewRequirement) -> McxReferenceResult:
    if requirement.mcx_reference is None:
        raise ValueError("MCX_REFERENCE_NOT_REQUIRED")
    return McxReferenceResult(
        requirement.mcx_reference,
        McxReferenceStatus.UNAVAILABLE,
        McxReferenceEvidenceState.UNAVAILABLE,
        None,
        None,
        (),
        requirement.mcx_reference.provider_provenance,
        "REQUIREMENT_BOUND_NO_EVIDENCE",
        "REFERENCE_EVIDENCE_UNAVAILABLE",
    )


class NativeReviewEvidenceStore:
    """Atomic, immutable, restart-safe Native Review requirement storage."""

    def __init__(self, root: Path = DEFAULT_NATIVE_REVIEW_EVIDENCE_ROOT) -> None:
        root = Path(root).expanduser()
        if not root.is_absolute():
            raise ValueError("NATIVE_REVIEW_STORE_INVALID")
        self._root = root
        self._lock = RLock()

    @property
    def root(self) -> Path:
        return self._root

    def retain(self, requirements: tuple[NativeReviewRequirement, ...]) -> Path:
        if not requirements or any(type(item) is not NativeReviewRequirement for item in requirements):
            raise ValueError("NATIVE_REVIEW_REQUIREMENTS_INVALID")
        run_identity = requirements[0].native_run_identity
        if any(item.native_run_identity != run_identity for item in requirements):
            raise ValueError("NATIVE_REVIEW_SAME_RUN_BINDING_INVALID")
        path = self._root / "complete-runs" / f"{run_identity}.json"
        payload = {
            "schema": NATIVE_REVIEW_SCHEMA,
            "run_identity": run_identity,
            "requirements": [_primitive(item) for item in requirements],
        }
        with self._lock:
            if path.exists():
                if _read(path) != payload:
                    raise ValueError("NATIVE_REVIEW_REQUIREMENTS_IMMUTABLE")
                return path
            _atomic_json(path, payload)
        return path

    def load(
        self,
        native_run: NativeDiscoveryRun,
        facts: SameRunMtfFactSnapshot,
    ) -> tuple[NativeReviewRequirement, ...]:
        expected = build_native_review_requirements(native_run, facts)
        path = self._root / "complete-runs" / f"{native_run.run_identity}.json"
        payload = _read(path)
        if (
            payload.get("schema") != NATIVE_REVIEW_SCHEMA
            or payload.get("run_identity") != native_run.run_identity
            or payload.get("requirements") != [_primitive(item) for item in expected]
        ):
            raise ValueError("NATIVE_REVIEW_RESTART_INTEGRITY_INVALID")
        return expected

    def retain_reference_result(self, result: McxReferenceResult) -> Path:
        if type(result) is not McxReferenceResult:
            raise ValueError("MCX_REFERENCE_RESULT_INVALID")
        reference = result.requirement
        requirement_path = self._root / "complete-runs" / f"{reference.native_run_identity}.json"
        try:
            payload = _read(requirement_path)
        except ValueError as error:
            raise ValueError("MCX_REFERENCE_ORPHANED_EVIDENCE_REJECTED") from error
        requirements = payload.get("requirements")
        if type(requirements) is not list or not any(
            item.get("mcx_reference", {}).get("requirement_sha256")
            == reference.requirement_sha256
            for item in requirements
            if type(item) is dict and type(item.get("mcx_reference")) is dict
        ):
            raise ValueError("MCX_REFERENCE_ORPHANED_EVIDENCE_REJECTED")
        path = (
            self._root / "reference-results" / reference.native_run_identity
            / (
                f"{reference.mcx_canonical_instrument}--"
                f"{result.reference_evidence_sha256 or reference.requirement_sha256}.json"
            )
        )
        result_payload = {"schema": NATIVE_REVIEW_SCHEMA, "result": _primitive(result)}
        with self._lock:
            if path.exists():
                if _read(path) != result_payload:
                    raise ValueError("MCX_REFERENCE_RESULT_IMMUTABLE")
                return path
            _atomic_json(path, result_payload)
        return path

    def load_reference_results(
        self,
        requirements: tuple[NativeReviewRequirement, ...],
        *,
        review_pack_id: str | None = None,
    ) -> tuple[McxReferenceResult, ...]:
        if not requirements:
            return ()
        expected = {
            item.mcx_reference.mcx_canonical_instrument: item.mcx_reference
            for item in requirements if item.mcx_reference is not None
        }
        root = self._root / "reference-results" / requirements[0].native_run_identity
        if not root.exists():
            return ()
        results = []
        for path in sorted(root.glob("*.json")):
            payload = _read(path)
            result = _reference_result(payload.get("result"), expected)
            if (
                review_pack_id is not None
                and review_pack_id not in result.source_provenance
            ):
                continue
            results.append(result)
        selected: dict[str, McxReferenceResult] = {}
        for result in results:
            instrument = result.requirement.mcx_canonical_instrument
            current = selected.get(instrument)
            if current is not None and current != result:
                raise ValueError("MCX_REFERENCE_RESTART_BINDING_AMBIGUOUS")
            selected[instrument] = result
        return tuple(selected[key] for key in sorted(selected))


def _requirement(
    native_run: NativeDiscoveryRun,
    assessment: NativeInstrumentDiscovery,
    facts: SameRunMtfFactSnapshot,
) -> NativeReviewRequirement:
    if (
        assessment.run_identity != native_run.run_identity
        or assessment.status is not NativeDiscoveryStatus.PROBABLE
        or assessment.context_kind is None
        or assessment.opportunity_identity is None
        or assessment.operative_anchor is None
    ):
        raise ValueError("NATIVE_REVIEW_ASSESSMENT_INELIGIBLE")
    instrument = facts.instrument(assessment.canonical_instrument)
    timeframe_facts = tuple(_timeframe_fact(item) for item in instrument.timeframes)
    thesis = NativeReviewThesis(
        native_run_identity=native_run.run_identity,
        native_assessment_sha256=assessment.result_sha256,
        canonical_instrument=assessment.canonical_instrument,
        direction=assessment.direction,
        product_path=assessment.product_path,
        context_kind=assessment.context_kind,
        opportunity_identity=assessment.opportunity_identity,
        weekly_state=assessment.weekly_state,
        daily_state=assessment.daily_state,
        four_hour_state=assessment.four_hour_state,
        one_hour_state=assessment.one_hour_state,
        operative_anchor_identity=assessment.operative_anchor.anchor_type.value,
        operative_anchor_price=assessment.operative_anchor.price,
        operative_anchor_boundary=assessment.operative_anchor.source_boundary,
        timeframe_facts=timeframe_facts,
        native_policy_identity=assessment.policy_identity,
        native_policy_version=assessment.policy_version,
        provider_provenance=assessment.provider_provenance,
        calendar_provenance=assessment.calendar_provenance,
    )
    reference = _mcx_reference(thesis)
    requirement_digest = sha256(
        json.dumps(
            {"thesis": _primitive(thesis), "mcx_reference": _primitive(reference)},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return NativeReviewRequirement(
        thesis, tuple(FactualTimeframe), requirement_digest, reference
    )


def _mcx_reference(thesis: NativeReviewThesis) -> McxReferenceRequirement | None:
    if thesis.product_path is NativeProductPath.NSE:
        return None
    try:
        subject, market, symbol = MCX_REFERENCE_MAPPINGS[thesis.canonical_instrument]
    except KeyError as error:
        raise ValueError("MCX_REFERENCE_MAPPING_UNAVAILABLE") from error
    material = {
        "native_run_identity": thesis.native_run_identity,
        "native_assessment_sha256": thesis.native_assessment_sha256,
        "mcx_canonical_instrument": thesis.canonical_instrument,
        "direction": thesis.direction.value,
        "opportunity_identity": thesis.opportunity_identity.value,
        "product_path": thesis.product_path.value,
        "operative_anchor_identity": thesis.operative_anchor_identity,
        "operative_anchor_price": thesis.operative_anchor_price,
        "operative_anchor_boundary": thesis.operative_anchor_boundary.isoformat(),
        "provider_provenance": thesis.provider_provenance,
        "reference_subject_identity": subject,
        "reference_market": market.value,
        "reference_symbol": symbol,
    }
    digest = sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return McxReferenceRequirement(
        thesis.native_run_identity, thesis.native_assessment_sha256,
        thesis.canonical_instrument, thesis.direction, thesis.opportunity_identity,
        thesis.product_path, thesis.operative_anchor_identity,
        thesis.operative_anchor_price, thesis.operative_anchor_boundary,
        thesis.provider_provenance, subject, market, symbol, digest,
    )


def _timeframe_fact(fact: CompletedTimeframeFact) -> NativeReviewTimeframeFacts:
    pivots = tuple(
        NativeReviewPivot(fact.timeframe, series.radius, pivot.kind, pivot.timestamp, pivot.value)
        for series in fact.structural_measurements
        for pivot in (*series.swing_highs, *series.swing_lows)
    )
    ma = fact.moving_averages
    volume = fact.volume_facts
    return NativeReviewTimeframeFacts(
        timeframe=fact.timeframe,
        observation_boundary=fact.observation_boundary,
        source_timestamp=fact.source_timestamp,
        open=fact.open,
        high=fact.high,
        low=fact.low,
        close=fact.close,
        volume=fact.volume,
        sma20=None if ma is None else ma.sma20,
        sma50=None if ma is None else ma.sma50,
        sma200=None if ma is None else ma.sma200,
        prior_sma20_5bars=None if ma is None else ma.prior_sma20_5bars,
        prior_sma50_5bars=None if ma is None else ma.prior_sma50_5bars,
        prior_sma200_5bars=None if ma is None else ma.prior_sma200_5bars,
        prior_20_volume_mean=None if volume is None else volume.prior_20_mean,
        pivots=pivots,
        calendar_identity=fact.calendar_identity,
        calendar_version=fact.calendar_version,
        session_identity=fact.session_identity,
        provider_identity=fact.source_provider_identity,
        provenance=fact.provenance,
    )


def _primitive(value: object) -> object:
    if hasattr(value, "__dataclass_fields__"):
        return _primitive(asdict(value))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_primitive(item) for item in value]
    return value


def _read(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("NATIVE_REVIEW_EVIDENCE_UNAVAILABLE") from error
    if type(value) is not dict:
        raise ValueError("NATIVE_REVIEW_EVIDENCE_INVALID")
    return value


def _reference_result(
    value: object,
    expected: dict[str, McxReferenceRequirement],
) -> McxReferenceResult:
    if type(value) is not dict:
        raise ValueError("MCX_REFERENCE_RESULT_INVALID")
    try:
        instrument = value["requirement"]["mcx_canonical_instrument"]
        requirement = expected[instrument]
        if value["requirement"] != _primitive(requirement):
            raise ValueError("MCX_REFERENCE_RESTART_INTEGRITY_INVALID")
        return McxReferenceResult(
            requirement=requirement,
            status=McxReferenceStatus(value["status"]),
            evidence_state=McxReferenceEvidenceState(value["evidence_state"]),
            chart_revision_sha256=value["chart_revision_sha256"],
            reference_evidence_sha256=value["reference_evidence_sha256"],
            observation_boundaries=tuple(
                (name, datetime.fromisoformat(boundary))
                for name, boundary in value["observation_boundaries"]
            ),
            source_provenance=tuple(value["source_provenance"]),
            binding_status=value["binding_status"],
            reason=value["reason"],
        )
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, ValueError) and str(error) == "MCX_REFERENCE_RESTART_INTEGRITY_INVALID":
            raise
        raise ValueError("MCX_REFERENCE_RESULT_INVALID") from error


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(".tmp")
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    with temporary.open("w", encoding="utf-8") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


__all__ = [
    "DEFAULT_NATIVE_REVIEW_EVIDENCE_ROOT",
    "NATIVE_REVIEW_AUTHORITY",
    "NATIVE_REVIEW_SCHEMA",
    "MCX_REFERENCE_AUTHORITY",
    "MCX_REFERENCE_MAPPINGS",
    "McxReferenceEvidenceState",
    "McxReferenceRequirement",
    "McxReferenceResult",
    "McxReferenceStatus",
    "NativeIndependentLayer2Evidence",
    "NativeLayer2EvidenceState",
    "NativeLayer2ReviewRecord",
    "NativeReviewEvidenceStore",
    "NativeReviewRequirement",
    "NativeReviewThesis",
    "NativeReviewTimeframeFacts",
    "build_native_review_requirements",
    "bind_mcx_reference_evidence",
    "reconcile_native_layer2",
    "unavailable_mcx_reference",
]
