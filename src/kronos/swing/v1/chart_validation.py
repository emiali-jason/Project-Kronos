"""Field-level manual-versus-AI validation without tuning provider questions."""

from __future__ import annotations

from dataclasses import dataclass

from kronos.swing.v1.chart_evidence import ChartEvidenceResponse


SWING_V1_CHART_VALIDATION_INSTRUMENTS = (
    "NAUKRI",
    "TITAN",
    "POWERGRID",
    "HINDUNILVR",
    "ADANIENT",
    "NTPC",
    "YESBANK",
)


@dataclass(frozen=True, slots=True)
class ChartEvidenceAgreement:
    instrument: str
    ai_run_count: int
    structure_agreement: bool
    sma20_agreement: bool
    sma50_agreement: bool
    sma200_agreement: bool
    candle_acceptance_agreement: bool
    volume_context_agreement: bool
    barrier_agreement: bool
    pine_transcription_agreement: bool
    undeterminable_discipline: bool
    schema_validity: bool
    run_to_run_consistency: bool

    @property
    def compared_field_count(self) -> int:
        return 9

    @property
    def agreed_field_count(self) -> int:
        return sum((
            self.structure_agreement,
            self.sma20_agreement,
            self.sma50_agreement,
            self.sma200_agreement,
            self.candle_acceptance_agreement,
            self.volume_context_agreement,
            self.barrier_agreement,
            self.pine_transcription_agreement,
            self.undeterminable_discipline,
        ))


def compare_manual_and_ai_chart_evidence(
    manual: ChartEvidenceResponse,
    ai_runs: tuple[ChartEvidenceResponse, ...],
) -> ChartEvidenceAgreement:
    if type(manual) is not ChartEvidenceResponse or not ai_runs or any(
        type(item) is not ChartEvidenceResponse for item in ai_runs
    ):
        raise ValueError("CHART_EVIDENCE_VALIDATION_INPUT_INVALID")
    if manual.canonical_instrument not in SWING_V1_CHART_VALIDATION_INSTRUMENTS:
        raise ValueError("CHART_EVIDENCE_VALIDATION_INSTRUMENT_INVALID")
    binding = (
        manual.run_identity,
        manual.canonical_instrument,
        manual.timeframe,
        manual.observation_boundary,
        manual.chart_template_identity,
        manual.source_image_sha256,
        manual.question_set_identity,
        manual.schema_identity,
    )
    if any(
        (
            item.run_identity,
            item.canonical_instrument,
            item.timeframe,
            item.observation_boundary,
            item.chart_template_identity,
            item.source_image_sha256,
            item.question_set_identity,
            item.schema_identity,
        )
        != binding
        for item in ai_runs
    ):
        raise ValueError("CHART_EVIDENCE_VALIDATION_BINDING_MISMATCH")

    first = ai_runs[0]
    manual_mas = {item.indicator: item for item in manual.moving_averages}
    ai_mas = {item.indicator: item for item in first.moving_averages}
    run_projection = tuple(_evidence_projection(item) for item in ai_runs)
    return ChartEvidenceAgreement(
        instrument=manual.canonical_instrument,
        ai_run_count=len(ai_runs),
        structure_agreement=manual.price_structure == first.price_structure,
        sma20_agreement=manual_mas["SMA20"] == ai_mas["SMA20"],
        sma50_agreement=manual_mas["SMA50"] == ai_mas["SMA50"],
        sma200_agreement=manual_mas["SMA200"] == ai_mas["SMA200"],
        candle_acceptance_agreement=manual.candle == first.candle,
        volume_context_agreement=manual.volume == first.volume,
        barrier_agreement=(manual.barriers, manual.reference_levels)
        == (first.barriers, first.reference_levels),
        pine_transcription_agreement=manual.pine == first.pine,
        undeterminable_discipline=manual.undeterminable_questions
        == first.undeterminable_questions,
        schema_validity=True,
        run_to_run_consistency=len(set(run_projection)) == 1,
    )


def _evidence_projection(response: ChartEvidenceResponse) -> tuple[object, ...]:
    return (
        response.instrument_identity,
        response.timeframe_identity,
        response.template_identity,
        response.price_structure,
        response.moving_averages,
        response.candle,
        response.volume,
        response.reference_levels,
        response.barriers,
        response.pine,
        response.contradictions,
        response.undeterminable_questions,
    )


__all__ = [
    "ChartEvidenceAgreement",
    "SWING_V1_CHART_VALIDATION_INSTRUMENTS",
    "compare_manual_and_ai_chart_evidence",
]
