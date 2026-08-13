"""Shadow-only Chart Analyst V2 integration into the existing V1 Layer-2 chain."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from kronos.swing.universe import SwingUniverseAssetClass
from kronos.swing.v1.chart_analyst_v2 import (
    CHART_ANALYST_V2_QUESTION_SET_ID,
    CHART_ANALYST_V2_QUESTION_SET_VERSION,
    OPENAI_CHART_ANALYST_V2_PROVIDER_ID,
    ChartAnalystProduct,
    ChartAnalystV2Response,
    chart_analyst_v2_response_from_dict,
    chart_analyst_v2_response_to_dict,
)
from kronos.swing.v1.chart_analyst_v2_integrity import (
    validate_chart_analyst_v2_output_integrity,
)
from kronos.swing.v1.layer2 import (
    ChartRevisionIdentity,
    EvidenceReconciliationState,
    ExtractedChartObservation,
    ExtractionProvenance,
    Layer2ReviewRecord,
    ObservationCategory,
    ReadinessAssessment,
    ReadinessState,
    TradingViewStructuredEvidence,
    build_layer2_review_record,
    context_incomplete_readiness,
    layer2_record_from_dict,
    layer2_record_to_dict,
)
from kronos.swing.v1.models import (
    EvidenceAvailability,
    ProbableClassification,
    V1Direction,
    V1Layer1Assessment,
)
from kronos.swing.v1.policies import SWING_V1_LAYER2_V2_INTEGRATION_POLICY_ID
from kronos.swing.v1.tradingview import (
    ChartTimeframe,
    TradingViewReviewRequirement,
)


CHART_ANALYST_V2_LAYER2_SCHEMA_ID = "KRONOS_SWING_V1_CHART_ANALYST_V2_LAYER2_V1"
CHART_ANALYST_V2_OPERATIONAL_AUTHORITY = "SHADOW / VALIDATION ONLY"


class ChartAnalystV2Layer2State(StrEnum):
    SHADOW_COMPLETE = "SHADOW_COMPLETE"
    CONTEXT_INCOMPLETE = "CONTEXT_INCOMPLETE"


class KronosLayer2ReconciliationState(StrEnum):
    AGREE = "AGREE"
    COMPATIBLE_PARTIAL = "COMPATIBLE_PARTIAL"
    CONTRADICT = "CONTRADICT"
    CONTEXT_INCOMPLETE = "CONTEXT_INCOMPLETE"


@dataclass(frozen=True, slots=True)
class Layer1ThesisProvenance:
    assessment_identity: str
    setup: str
    direction: V1Direction
    structural_consensus: str
    sma20_direction: str
    price_vs_sma20: str
    volume_interpretation: str

    def __post_init__(self) -> None:
        if (
            not self.assessment_identity
            or not self.setup
            or type(self.direction) is not V1Direction
            or not self.structural_consensus
            or not self.sma20_direction
            or not self.price_vs_sma20
            or not self.volume_interpretation
        ):
            raise ValueError("V1_LAYER2_LAYER1_THESIS_PROVENANCE_INVALID")


@dataclass(frozen=True, slots=True)
class ChartAnalystV2Layer2Record:
    state: ChartAnalystV2Layer2State
    response: ChartAnalystV2Response
    layer1_theses: tuple[Layer1ThesisProvenance, ...]
    reconciliation: KronosLayer2ReconciliationState
    contradictions: tuple[str, ...]
    missing_required_evidence: tuple[str, ...]
    readiness: ReadinessAssessment
    layer2_record: Layer2ReviewRecord | None
    integrity_validation: str = "PASSED"
    operational_authority: str = CHART_ANALYST_V2_OPERATIONAL_AUTHORITY
    policy_identity: str = SWING_V1_LAYER2_V2_INTEGRATION_POLICY_ID

    def __post_init__(self) -> None:
        complete = self.state is ChartAnalystV2Layer2State.SHADOW_COMPLETE
        if (
            type(self.state) is not ChartAnalystV2Layer2State
            or type(self.response) is not ChartAnalystV2Response
            or not self.layer1_theses
            or any(type(item) is not Layer1ThesisProvenance for item in self.layer1_theses)
            or type(self.reconciliation) is not KronosLayer2ReconciliationState
            or type(self.contradictions) is not tuple
            or len(set(self.contradictions)) != len(self.contradictions)
            or type(self.missing_required_evidence) is not tuple
            or len(set(self.missing_required_evidence)) != len(self.missing_required_evidence)
            or type(self.readiness) is not ReadinessAssessment
            or (self.layer2_record is not None and type(self.layer2_record) is not Layer2ReviewRecord)
            or self.integrity_validation != "PASSED"
            or self.operational_authority != CHART_ANALYST_V2_OPERATIONAL_AUTHORITY
            or self.policy_identity != SWING_V1_LAYER2_V2_INTEGRATION_POLICY_ID
            or complete != (self.layer2_record is not None)
            or complete == bool(self.missing_required_evidence)
            or (
                complete
                and (
                    self.reconciliation is KronosLayer2ReconciliationState.CONTEXT_INCOMPLETE
                    or self.readiness != self.layer2_record.readiness
                )
            )
            or (
                not complete
                and (
                    self.reconciliation is not KronosLayer2ReconciliationState.CONTEXT_INCOMPLETE
                    or self.readiness.state is not ReadinessState.CONTEXT_INCOMPLETE
                )
            )
            or self.readiness.run_identity != self.response.run_identity
            or self.readiness.canonical_instrument != self.response.instrument
        ):
            raise ValueError("V1_CHART_ANALYST_V2_LAYER2_RECORD_INVALID")


def integrate_chart_analyst_v2_layer2(
    requirement: TradingViewReviewRequirement,
    assessments: tuple[V1Layer1Assessment, ...],
    response: ChartAnalystV2Response,
    *,
    source_image_sha256: str,
) -> ChartAnalystV2Layer2Record:
    """Bind and normalize V2 evidence before replaying existing KRONOS policy."""

    _validate_input_eligibility(
        requirement,
        assessments,
        response,
        source_image_sha256=source_image_sha256,
    )
    theses = _layer1_theses(requirement, assessments)
    observations, missing, pine_reconciliation = _normalize_observations(
        requirement,
        assessments[0],
        response,
    )
    if missing:
        return ChartAnalystV2Layer2Record(
            state=ChartAnalystV2Layer2State.CONTEXT_INCOMPLETE,
            response=response,
            layer1_theses=theses,
            reconciliation=KronosLayer2ReconciliationState.CONTEXT_INCOMPLETE,
            contradictions=(),
            missing_required_evidence=missing,
            readiness=context_incomplete_readiness(requirement, missing),
            layer2_record=None,
        )
    structured = TradingViewStructuredEvidence(
        run_identity=requirement.run_identity,
        canonical_instrument=requirement.canonical_instrument,
        observation_boundary=requirement.observation_boundary,
        chart_template_identity=requirement.chart_template_identity,
        observations=observations,
        source_revisions=(
            ChartRevisionIdentity(ChartTimeframe.DAILY, source_image_sha256),
        ),
    )
    layer2 = build_layer2_review_record(requirement, assessments, structured)
    reconciliation, contradictions = _kronos_reconciliation(
        layer2,
        pine_reconciliation,
    )
    return ChartAnalystV2Layer2Record(
        state=ChartAnalystV2Layer2State.SHADOW_COMPLETE,
        response=response,
        layer1_theses=theses,
        reconciliation=reconciliation,
        contradictions=contradictions,
        missing_required_evidence=(),
        readiness=layer2.readiness,
        layer2_record=layer2,
    )


def chart_analyst_v2_layer2_record_to_dict(
    record: ChartAnalystV2Layer2Record,
) -> dict[str, object]:
    if type(record) is not ChartAnalystV2Layer2Record:
        raise TypeError("V1_CHART_ANALYST_V2_LAYER2_RECORD_INVALID")
    return {
        "schema": CHART_ANALYST_V2_LAYER2_SCHEMA_ID,
        "state": record.state.value,
        "response": chart_analyst_v2_response_to_dict(record.response),
        "layer1_theses": [
            {
                "assessment_identity": item.assessment_identity,
                "setup": item.setup,
                "direction": item.direction.value,
                "structural_consensus": item.structural_consensus,
                "sma20_direction": item.sma20_direction,
                "price_vs_sma20": item.price_vs_sma20,
                "volume_interpretation": item.volume_interpretation,
            }
            for item in record.layer1_theses
        ],
        "integrity_validation": record.integrity_validation,
        "reconciliation": record.reconciliation.value,
        "contradictions": list(record.contradictions),
        "missing_required_evidence": list(record.missing_required_evidence),
        "readiness": _readiness_to_dict(record.readiness),
        "layer2_record": (
            layer2_record_to_dict(record.layer2_record)
            if record.layer2_record is not None
            else None
        ),
        "raw_output_provenance": {
            "run_identity": record.response.run_identity,
            "swing_analysis_run_identity": record.response.swing_analysis_run_identity,
            "instrument": record.response.instrument,
            "image_sha256": record.response.image_sha256,
            "question_set_id": CHART_ANALYST_V2_QUESTION_SET_ID,
            "question_set_version": CHART_ANALYST_V2_QUESTION_SET_VERSION,
            "model_identity": record.response.model_identity,
            "integrity_sidecar_schema": (
                "KRONOS_SWING_V1_CHART_ANALYST_V2_OUTPUT_INTEGRITY_V1"
            ),
        },
        "operational_authority": record.operational_authority,
        "production_authority": "NONE",
        "openai_readiness_authority": "NONE",
        "pine_readiness_authority": "NONE",
        "trade_construction": "NOT_IMPLEMENTED",
        "ranking": "NOT_PERFORMED",
        "policy_identity": record.policy_identity,
    }


def chart_analyst_v2_layer2_record_from_dict(
    payload: object,
) -> ChartAnalystV2Layer2Record:
    if type(payload) is not dict or payload.get("schema") != CHART_ANALYST_V2_LAYER2_SCHEMA_ID:
        raise ValueError("V1_CHART_ANALYST_V2_LAYER2_DESERIALIZATION_INVALID")
    try:
        record = ChartAnalystV2Layer2Record(
            state=ChartAnalystV2Layer2State(payload["state"]),
            response=chart_analyst_v2_response_from_dict(payload["response"]),
            layer1_theses=tuple(
                Layer1ThesisProvenance(
                    assessment_identity=item["assessment_identity"],
                    setup=item["setup"],
                    direction=V1Direction(item["direction"]),
                    structural_consensus=item["structural_consensus"],
                    sma20_direction=item["sma20_direction"],
                    price_vs_sma20=item["price_vs_sma20"],
                    volume_interpretation=item["volume_interpretation"],
                )
                for item in payload["layer1_theses"]
            ),
            reconciliation=KronosLayer2ReconciliationState(payload["reconciliation"]),
            contradictions=tuple(payload["contradictions"]),
            missing_required_evidence=tuple(payload["missing_required_evidence"]),
            readiness=_readiness_from_dict(payload["readiness"]),
            layer2_record=(
                layer2_record_from_dict(payload["layer2_record"])
                if payload["layer2_record"] is not None
                else None
            ),
            integrity_validation=payload["integrity_validation"],
            operational_authority=payload["operational_authority"],
            policy_identity=payload["policy_identity"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("V1_CHART_ANALYST_V2_LAYER2_DESERIALIZATION_INVALID") from error
    expected_keys = {
        "schema", "state", "response", "layer1_theses", "integrity_validation",
        "reconciliation", "contradictions", "missing_required_evidence",
        "readiness", "layer2_record", "raw_output_provenance",
        "operational_authority", "production_authority",
        "openai_readiness_authority", "pine_readiness_authority",
        "trade_construction", "ranking", "policy_identity",
    }
    if (
        set(payload) != expected_keys
        or payload["production_authority"] != "NONE"
        or payload["openai_readiness_authority"] != "NONE"
        or payload["pine_readiness_authority"] != "NONE"
        or payload["trade_construction"] != "NOT_IMPLEMENTED"
        or payload["ranking"] != "NOT_PERFORMED"
        or payload["raw_output_provenance"] != chart_analyst_v2_layer2_record_to_dict(record)["raw_output_provenance"]
    ):
        raise ValueError("V1_CHART_ANALYST_V2_LAYER2_DESERIALIZATION_INVALID")
    return record


def _validate_input_eligibility(
    requirement: TradingViewReviewRequirement,
    assessments: tuple[V1Layer1Assessment, ...],
    response: ChartAnalystV2Response,
    *,
    source_image_sha256: str,
) -> None:
    if (
        type(requirement) is not TradingViewReviewRequirement
        or type(response) is not ChartAnalystV2Response
        or not assessments
        or any(type(item) is not V1Layer1Assessment for item in assessments)
        or response.provider_identity != OPENAI_CHART_ANALYST_V2_PROVIDER_ID
        or response.run_identity != requirement.run_identity
        or response.swing_analysis_run_identity != requirement.swing_analysis_run_identity
        or response.instrument != requirement.canonical_instrument
        or response.image_sha256 != source_image_sha256
        or response.analysis["question_set_id"] != CHART_ANALYST_V2_QUESTION_SET_ID
        or response.analysis["question_set_version"] != CHART_ANALYST_V2_QUESTION_SET_VERSION
        or any(
            item.canonical_identity != requirement.canonical_instrument
            or item.observation_boundary != requirement.observation_boundary
            or item.classification is not ProbableClassification.PROBABLE_CANDIDATE
            for item in assessments
        )
    ):
        raise ValueError("V1_CHART_ANALYST_V2_LAYER2_BINDING_INVALID")
    expected_product = (
        ChartAnalystProduct.MCX
        if all(item.asset_class is SwingUniverseAssetClass.MCX_COMMODITY for item in assessments)
        else ChartAnalystProduct.NSE
        if all(item.asset_class is not SwingUniverseAssetClass.MCX_COMMODITY for item in assessments)
        else None
    )
    expected_links = {
        (item.setup.value, item.direction) for item in assessments
    }
    requirement_links = {
        (item.setup.value, item.direction) for item in requirement.probable_setups
    }
    integrity = validate_chart_analyst_v2_output_integrity(response.analysis)
    if (
        response.product is not expected_product
        or expected_links != requirement_links
        or not integrity.accepted
    ):
        raise ValueError("V1_CHART_ANALYST_V2_LAYER2_ELIGIBILITY_INVALID")


def _layer1_theses(
    requirement: TradingViewReviewRequirement,
    assessments: tuple[V1Layer1Assessment, ...],
) -> tuple[Layer1ThesisProvenance, ...]:
    values = []
    for link in requirement.probable_setups:
        assessment = next(
            item for item in assessments
            if item.setup is link.setup and item.direction is link.direction
        )
        values.append(Layer1ThesisProvenance(
            assessment_identity=link.assessment_identity,
            setup=assessment.setup.value,
            direction=assessment.direction,
            structural_consensus=(
                assessment.structural.consensus.value
                if assessment.structural.consensus is not None
                else "UNAVAILABLE"
            ),
            sma20_direction=assessment.moving_average.sma20_direction or "UNAVAILABLE",
            price_vs_sma20=assessment.moving_average.price_vs_sma20 or "UNAVAILABLE",
            volume_interpretation=assessment.volume.policy_interpretation,
        ))
    return tuple(values)


def _normalize_observations(
    requirement: TradingViewReviewRequirement,
    assessment: V1Layer1Assessment,
    response: ChartAnalystV2Response,
) -> tuple[
    tuple[ExtractedChartObservation, ...],
    tuple[str, ...],
    EvidenceReconciliationState,
]:
    analysis = response.analysis
    missing: list[str] = []
    for timeframe, presence in analysis["expected_timeframes_present"].items():
        if presence != "YES":
            missing.append(f"TIMEFRAME_{timeframe}_UNDETERMINABLE")
    if analysis["overall_image_readability"] == "POOR":
        missing.append("OVERALL_IMAGE_READABILITY_POOR")
    daily = analysis["timeframes"]["1D"]
    if daily["readability"] == "POOR":
        missing.append("1D_READABILITY_POOR")
    base = {
        "run_identity": requirement.run_identity,
        "canonical_instrument": requirement.canonical_instrument,
        "observation_boundary": requirement.observation_boundary,
        "timeframe": ChartTimeframe.DAILY,
        "chart_template_identity": requirement.chart_template_identity,
        "source_screenshot_sha256": response.image_sha256,
        "extraction_provenance": ExtractionProvenance.AI_CHART_ANALYST,
    }
    observations: list[ExtractedChartObservation] = []

    structure = _structure_value(daily["market_structure"])
    if structure is None:
        missing.append("1D_PRICE_STRUCTURE_UNDETERMINABLE")
        observations.append(_unavailable(base, ObservationCategory.PRICE_STRUCTURE, "TRADINGVIEW_STRUCTURE"))
    else:
        observations.append(_observation(base, ObservationCategory.PRICE_STRUCTURE, "TRADINGVIEW_STRUCTURE", structure))

    for indicator in ("SMA20", "SMA50", "SMA200"):
        value = _moving_average_value(daily["moving_averages"][indicator])
        category = ObservationCategory(indicator)
        if value is None:
            missing.append(f"1D_{indicator}_UNDETERMINABLE")
            observations.append(_unavailable(base, category, indicator))
        else:
            observations.append(_observation(
                base,
                category,
                indicator,
                value,
                correlation_key=f"1D.{indicator}",
            ))

    candle = _candle_value(daily)
    if candle is None:
        missing.append("1D_CANDLE_CONTEXT_UNDETERMINABLE")
        observations.append(_unavailable(base, ObservationCategory.CANDLE_BEHAVIOUR, "CANDLE_CONTEXT"))
    else:
        observations.append(_observation(base, ObservationCategory.CANDLE_BEHAVIOUR, "CANDLE_CONTEXT", candle))

    volume = _volume_value(daily["volume_participation"])
    if volume is None:
        missing.append("1D_VOLUME_CONTEXT_UNDETERMINABLE")
        observations.append(_unavailable(base, ObservationCategory.VOLUME_CONTEXT, "VOLUME_CONTEXT"))
    else:
        observations.append(_observation(base, ObservationCategory.VOLUME_CONTEXT, "VOLUME_CONTEXT", volume))

    observations.extend(_level_observations(base, daily["support_resistance_barriers"]))

    development = _price_development_value(daily, analysis["overall_observation"])
    if development is None:
        missing.append("1D_PRICE_DEVELOPMENT_UNDETERMINABLE")
        observations.append(_unavailable(base, ObservationCategory.PRICE_DEVELOPMENT, "PRICE_DEVELOPMENT"))
    else:
        observations.append(_observation(base, ObservationCategory.PRICE_DEVELOPMENT, "PRICE_DEVELOPMENT", development))

    pine_text, pine_reconciliation = _pine_value(
        assessment.direction,
        response.analysis,
    )
    if pine_text is None:
        observations.append(_unavailable(base, ObservationCategory.PINE, "PINE_DISPLAY"))
    else:
        observations.append(_observation(base, ObservationCategory.PINE, "PINE_DISPLAY", pine_text))
    return tuple(observations), tuple(dict.fromkeys(missing)), pine_reconciliation


def _structure_value(value: dict[str, object]) -> str | None:
    bullish = value["higher_highs_visible"] == "YES" and value["higher_lows_visible"] == "YES"
    bearish = value["lower_highs_visible"] == "YES" and value["lower_lows_visible"] == "YES"
    if bullish and not bearish:
        return "HH_HL"
    if bearish and not bullish:
        return "LH_LL"
    if value["structure"] in {"MIXED", "RANGE"} or (bullish and bearish):
        return "MIXED_UNCLEAR"
    return None


def _moving_average_value(value: dict[str, str]) -> str | None:
    if "UNDETERMINABLE" in value.values():
        return None
    interaction = {
        "SUPPORT": "SUPPORT",
        "RESISTANCE": "REJECTION",
        "NEUTRAL": "NONE",
    }[value["role"]]
    return "|".join((value["slope"], value["price_relation"], interaction, "UNCLEAR"))


def _candle_value(daily: dict[str, object]) -> str | None:
    break_retest = daily["breakout_breakdown_retest"]
    if break_retest["retest_state"] == "HELD":
        return "RETEST_HELD"
    if break_retest["retest_state"] == "FAILED" or break_retest["break_state"] == "FAILED":
        return "FAILED_BREAK"
    if break_retest["retest_state"] == "DEVELOPING":
        return "RETEST_DEVELOPING"
    if break_retest["returned_inside_range"] == "YES":
        return "CLOSE_BACK_INSIDE_RANGE"
    if break_retest["close_beyond_structure"] == "YES":
        return "ACCEPTED_OUTSIDE_STRUCTURE"
    acceptance = daily["candlestick_evidence"]["candle_acceptance"]
    return {
        "ACCEPTED": "ACCEPTANCE",
        "REJECTED": "REJECTION",
        "TESTING": "INDECISION",
        "MIXED": "INDECISION",
    }.get(acceptance)


def _volume_value(value: dict[str, str]) -> str | None:
    if value["volume_context"] == "UNDETERMINABLE":
        return None
    if value["volume_context"] == "WEAK":
        return "WEAK_PARTICIPATION"
    if value["volume_context"] == "MIXED":
        return "QUALITATIVE_MIXED"
    if value["volume_during_pullback"] == "CONTRACTING":
        return "COUNTERTREND_PARTICIPATION_QUIETER"
    if value["volume_on_break"] == "SUPPORTIVE":
        return "BREAK_PARTICIPATION_INCREASED"
    if value["volume_with_impulse"] == "EXPANDING":
        return "RESUMPTION_PARTICIPATION_SIZEABLE"
    return "QUALITATIVE_MIXED"


def _level_observations(
    base: dict[str, object],
    value: dict[str, object],
) -> tuple[ExtractedChartObservation, ...]:
    references: list[ExtractedChartObservation] = []
    structural: list[ExtractedChartObservation] = []
    support = value["nearest_visible_support"]
    resistance = value["nearest_visible_resistance"]
    if type(support) in {int, float}:
        references.append(_observation(
            base, ObservationCategory.REFERENCE_LEVELS, "VISIBLE_SUPPORT",
            "SUPPORT|PARTIAL", price=float(support),
            correlation_key="1D.VISIBLE_BARRIER.BELOW",
        ))
    if type(resistance) in {int, float}:
        references.append(_observation(
            base, ObservationCategory.REFERENCE_LEVELS, "VISIBLE_RESISTANCE",
            "RESISTANCE|PARTIAL", price=float(resistance),
            correlation_key="1D.VISIBLE_BARRIER.ABOVE",
        ))
    direction = value["barrier_direction"]
    if value["major_swing_barrier_present"] == "YES":
        if direction in {"ABOVE_PRICE", "BOTH"}:
            structural.append(_observation(
                base, ObservationCategory.STRUCTURAL_LEVELS, "SWING_HIGH",
                "RESISTANCE|MAJOR",
                price=float(resistance) if type(resistance) in {int, float} else None,
                correlation_key="1D.VISIBLE_BARRIER.ABOVE",
            ))
        if direction in {"BELOW_PRICE", "BOTH"}:
            structural.append(_observation(
                base, ObservationCategory.STRUCTURAL_LEVELS, "SWING_LOW",
                "SUPPORT|MAJOR",
                price=float(support) if type(support) in {int, float} else None,
                correlation_key="1D.VISIBLE_BARRIER.BELOW",
            ))
    if not references:
        references.append(
            _available_no_level(base, ObservationCategory.REFERENCE_LEVELS)
            if support == "NONE" and resistance == "NONE"
            and value["ma_or_reference_barrier_present"] == "NO"
            else _unavailable(base, ObservationCategory.REFERENCE_LEVELS, "UNAVAILABLE")
        )
    if not structural:
        structural.append(
            _available_no_level(base, ObservationCategory.STRUCTURAL_LEVELS)
            if value["major_swing_barrier_present"] == "NO"
            else _unavailable(base, ObservationCategory.STRUCTURAL_LEVELS, "UNAVAILABLE")
        )
    return tuple((*references, *structural))


def _price_development_value(
    daily: dict[str, object],
    overall: dict[str, str],
) -> str | None:
    break_retest = daily["breakout_breakdown_retest"]
    maturity = daily["maturity_extension_chase_risk"]["move_maturity"]
    weakening = daily["weakening_failure_evidence"]
    if (
        overall["setup_phase"] == "FAILED"
        or daily["post_impulse_behaviour"] == "FAILED_IMPULSE"
        or daily["post_impulse_progress"] == "FAILED"
        or break_retest["break_state"] == "FAILED"
    ):
        return "SETUP_INVALIDATED"
    if overall["setup_phase"] == "EXTENDED" or maturity in {"EXTENDED", "EXHAUSTION_RISK"}:
        return "EXTENDED_FROM_STRUCTURE"
    if break_retest["retest_state"] == "DEVELOPING":
        return "RETEST_DEVELOPING"
    if (
        daily["pullback"]["pullback_present"] == "YES"
        and daily["post_impulse_behaviour"] in {"SHALLOW_PULLBACK", "ORDERLY_PULLBACK"}
    ):
        return "ORDERLY_PULLBACK_DEVELOPING"
    if (
        weakening not in {"NONE", "UNDETERMINABLE"}
        or daily["post_impulse_progress"] in {"STALLING", "REVERSING"}
        or daily["post_impulse_behaviour"] in {"DEEP_PULLBACK", "DESTRUCTIVE_PULLBACK"}
    ):
        return "WEAKENING_FOLLOW_THROUGH"
    if (
        overall["setup_visually_exists"] == "YES"
        and daily["resumption_evidence"] == "STRONG"
        and daily["continuation_pattern"]["continuation_status"] == "CONFIRMED"
    ):
        return "READY_CONTEXT"
    return None


def _pine_value(
    direction: V1Direction,
    analysis: dict[str, object],
) -> tuple[str | None, EvidenceReconciliationState]:
    report = validate_chart_analyst_v2_output_integrity(analysis)
    check = next(
        item for item in report.checks
        if item.field_path == "timeframes.1D.pine_workstation.trend"
    )
    unavailable = {"-", "--", "—", "N/A", "NA", "NONE", "NOT_PRESENT", "UNAVAILABLE", "UNDETERMINABLE", "UNREADABLE"}
    values = tuple(item.upper() for item in check.normalized_value if item.upper() not in unavailable)
    if not values:
        return None, EvidenceReconciliationState.UNAVAILABLE
    expected = "BULLISH" if direction is V1Direction.LONG else "BEARISH"
    opposite = "BEARISH" if direction is V1Direction.LONG else "BULLISH"
    state = (
        EvidenceReconciliationState.SUPPORTS
        if all(item == expected for item in values)
        else EvidenceReconciliationState.CONTRADICTS
        if all(item == opposite for item in values)
        else EvidenceReconciliationState.MIXED
    )
    display_values = "/".join(values)
    return f"DISPLAY:VALIDATED PINE WORKSTATION; TREND {display_values}", state


def _kronos_reconciliation(
    layer2: Layer2ReviewRecord,
    pine: EvidenceReconciliationState,
) -> tuple[KronosLayer2ReconciliationState, tuple[str, ...]]:
    dimensions = (
        ("STRUCTURE", layer2.structure_reconciliation),
        ("SMA20", layer2.sma20_reconciliation),
        ("VOLUME", layer2.volume_reconciliation),
        ("PINE_TREND", pine),
    )
    contradictions = tuple(
        f"{name}_CONTRADICTS_LAYER1"
        for name, state in dimensions
        if state is EvidenceReconciliationState.CONTRADICTS
    )
    if contradictions:
        return KronosLayer2ReconciliationState.CONTRADICT, contradictions
    if all(state is EvidenceReconciliationState.SUPPORTS for _, state in dimensions):
        return KronosLayer2ReconciliationState.AGREE, ()
    return KronosLayer2ReconciliationState.COMPATIBLE_PARTIAL, ()


def _observation(
    base: dict[str, object],
    category: ObservationCategory,
    semantic_identity: str,
    evidence_value: str,
    *,
    price: float | None = None,
    correlation_key: str | None = None,
) -> ExtractedChartObservation:
    return ExtractedChartObservation(
        **base,
        category=category,
        semantic_identity=semantic_identity,
        evidence_value=evidence_value,
        availability=EvidenceAvailability.AVAILABLE,
        price=price,
        correlation_key=correlation_key,
    )


def _unavailable(
    base: dict[str, object],
    category: ObservationCategory,
    semantic_identity: str,
) -> ExtractedChartObservation:
    return ExtractedChartObservation(
        **base,
        category=category,
        semantic_identity=semantic_identity,
        evidence_value="UNAVAILABLE",
        availability=EvidenceAvailability.UNAVAILABLE,
    )


def _available_no_level(
    base: dict[str, object],
    category: ObservationCategory,
) -> ExtractedChartObservation:
    return _observation(
        base,
        category,
        "UNAVAILABLE",
        "VISIBLE_NOT_RELEVANT|PARTIAL",
    )


def _readiness_to_dict(value: ReadinessAssessment) -> dict[str, object]:
    return {
        "run_identity": value.run_identity,
        "canonical_instrument": value.canonical_instrument,
        "observation_boundary": value.observation_boundary.isoformat(),
        "probable_assessment_identities": list(value.probable_assessment_identities),
        "state": value.state.value,
        "primary_reason": value.primary_reason,
        "supporting_evidence": list(value.supporting_evidence),
        "contradicting_evidence": list(value.contradicting_evidence),
        "unresolved_evidence": list(value.unresolved_evidence),
        "provenance": list(value.provenance),
        "policy_identity": value.policy_identity,
        "policy_status": value.policy_status,
    }


def _readiness_from_dict(value: object) -> ReadinessAssessment:
    if type(value) is not dict:
        raise ValueError("V1_CHART_ANALYST_V2_READINESS_INVALID")
    return ReadinessAssessment(
        run_identity=value["run_identity"],
        canonical_instrument=value["canonical_instrument"],
        observation_boundary=datetime.fromisoformat(value["observation_boundary"]),
        probable_assessment_identities=tuple(value["probable_assessment_identities"]),
        state=ReadinessState(value["state"]),
        primary_reason=value["primary_reason"],
        supporting_evidence=tuple(value["supporting_evidence"]),
        contradicting_evidence=tuple(value["contradicting_evidence"]),
        unresolved_evidence=tuple(value["unresolved_evidence"]),
        provenance=tuple(value["provenance"]),
        policy_identity=value["policy_identity"],
        policy_status=value["policy_status"],
    )


__all__ = [
    "CHART_ANALYST_V2_LAYER2_SCHEMA_ID",
    "CHART_ANALYST_V2_OPERATIONAL_AUTHORITY",
    "ChartAnalystV2Layer2Record",
    "ChartAnalystV2Layer2State",
    "KronosLayer2ReconciliationState",
    "Layer1ThesisProvenance",
    "chart_analyst_v2_layer2_record_from_dict",
    "chart_analyst_v2_layer2_record_to_dict",
    "integrate_chart_analyst_v2_layer2",
]
