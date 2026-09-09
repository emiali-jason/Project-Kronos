"""WO-07C frozen visual questions; observations convey no trading authority."""
from dataclasses import dataclass

from kronos.intraday.review import ObservationStatus, ReviewError, ReviewFailure, ReviewQuestion

VERSION = "2.0.0"
NSE_QUESTION_SET = "KRONOS-INTRADAY-CHART-ANALYST-QUESTION-SET-V2"
NSE_ANSWER_SCHEMA = "KRONOS-INTRADAY-CHART-ANALYST-ANSWER-PACK-V2"
NSE_BATCH_ANSWER_SCHEMA = "KRONOS-INTRADAY-CHART-ANALYST-BATCH-ANSWER-PACK-V2"
MCX_QUESTION_SET = "KRONOS-INTRADAY-MCX-PAIRED-QUESTION-SET-V2"
MCX_ANSWER_SCHEMA = "KRONOS-INTRADAY-MCX-PAIRED-ANSWER-PACK-V2"
NSE_TIMEFRAMES = ("1D", "1H", "15M", "5M")
MCX_TIMEFRAMES = ("1D", "4H", "15M", "5M")
BOUNDARY = (
    "Use independently visible evidence only within the qualified completed-panel boundary. "
    "Do not copy expected identity into observed identity. Machine orientation is not visual proof. "
    "Do not calculate indicators, geometry, volume, scores, Entry, Stop, Target or R:R; "
    "do not recommend trades or judge internal hashes, source integrity or policy. "
    "Do not use future/forming evidence or opinion overlays. Missing evidence is not neutral evidence."
)
CONTEXT = ("SUPPORTIVE", "OPPOSING", "MIXED", "UNCLEAR")
STRUCTURE = ("CLEAN_DIRECTIONAL_STRUCTURE", "MIXED_STRUCTURE", "CONGESTED_STRUCTURE", "UNCLEAR")
BASE = ("CLEAR_BASE_OR_CONSOLIDATION", "WEAK_OR_MIXED_BASE", "NO_CLEAR_BASE", "UNCLEAR")
FOLLOW = ("CLEAR_FOLLOW_THROUGH", "WEAK_OR_STALLING", "FAILED_OR_RETURNED_THROUGH", "MIXED", "UNCLEAR")
PROGRESSION = ("ORDERLY", "MIXED", "DISORDERLY", "NO_CLEAR_PULLBACK_OR_PROGRESSION", "UNCLEAR")
LEVEL = ("CLEAN_INTERACTION", "REPEATED_OR_CONGESTED_INTERACTION", "CLEAR_REJECTION", "CLEAR_ACCEPTANCE", "NO_CLEAR_INTERACTION", "UNCLEAR", "NOT_OBSERVABLE")
ACCEPTANCE = ("CLEAR_ACCEPTANCE", "CLEAR_REJECTION", "CLEAR_RETEST_HOLD", "CLEAR_RETURN_THROUGH", "MIXED", "NO_CLEAR_STATE", "UNCLEAR", "NOT_OBSERVABLE")
ESCAPE = ("NONE", "MATERIAL_OBSERVATION")
STRUCTURAL_ANCHOR_RULE = "Use only a clearly observable structure in temporally qualified evidence. If its anchor or correspondence cannot be established, report NOT_OBSERVABLE or UNCLEAR. Do not invent a break threshold."
ANCHOR_RULE = "Use only an explicitly supplied governed level/zone and qualified visible anchor; otherwise report NOT_OBSERVABLE or unavailable. Never invent a barrier."


def _nse(number, wording, answers, timeframes, instruction=None):
    return ReviewQuestion(f"Q{number}", wording, answers, timeframes,
                          conditional_instruction=instruction, constraints=(BOUNDARY,))


NSE_QUESTIONS = (
    _nse(1, "What broader completed 1D visual context is visible relative to the proposed Intraday direction?", CONTEXT, ("1D",)),
    _nse(2, "How clearly organized is the surrounding completed 1H price structure?", STRUCTURE, ("1H",)),
    _nse(3, "Does completed 15M evidence show an organized base or consolidation relevant to the current move?", BASE, ("15M",)),
    _nse(4, "What does permitted completed 15M evidence show about establishment, follow-through or failure of the visible move?", FOLLOW, ("15M",)),
    _nse(5, "How orderly is the permitted completed 5M pullback or progression within the current move?", PROGRESSION, ("5M",)),
    _nse(6, "How does permitted completed price action interact with the supplied governed level or zone?", LEVEL, ("15M", "5M"), ANCHOR_RULE),
    _nse(7, "What visible structural space exists in the proposed direction before the next clearly relevant obstacle?", ("CLEAR_SPACE", "LIMITED_SPACE", "OBSTACLE_CLOSE", "UNCLEAR", "NOT_OBSERVABLE"), NSE_TIMEFRAMES,
         "Describe visual space only; do not calculate a Target, Stop, Entry, R:R or profit forecast."),
    _nse(8, "Relative to the most recent clearly visible base or structure, is permitted completed price action visibly extended?", ("NOT_VISIBLY_EXTENDED", "VISIBLY_EXTENDED", "MIXED", "UNCLEAR"), ("15M", "5M")),
    _nse(9, "At the relevant governed structure or level, what acceptance, rejection, retest-hold or return-through is visible?", ACCEPTANCE, ("15M", "5M"), ANCHOR_RULE),
    _nse(10, "Is there a material visible condition not adequately represented by Q1-Q9?", ESCAPE, NSE_TIMEFRAMES,
         "NONE requires a null explanation. MATERIAL_OBSERVATION requires why_not_covered_elsewhere; do not repeat Q1-Q9."),
)


@dataclass(frozen=True, slots=True)
class PairedVisualQuestion:
    question_id: str
    wording: str
    allowed_answers: tuple[str, ...]
    timeframe_scope: tuple[str, ...]
    side: str
    authority: str = "VISUAL_EVIDENCE_ONLY"
    conditional_instruction: str | None = None
    constraints: tuple[str, ...] = (BOUNDARY,)


def _paired(identity, wording, answers, scope, instruction=None):
    side = {"R": "INTERNATIONAL_REFERENCE", "M": "NATIVE_MCX", "X": "CROSS_MARKET"}[identity[0]]
    return PairedVisualQuestion(identity, wording, answers, scope, side,
                               conditional_instruction=instruction)


MCX_QUESTIONS = (
    _paired("R1", "What broader completed 1D international benchmark context is visible relative to the proposed direction?", CONTEXT, ("1D",)),
    _paired("R2", "How organized is the completed 4H international benchmark structure?", STRUCTURE, ("4H",)),
    _paired("R3", "What completed 15M benchmark base or consolidation is visible?", BASE, ("15M",)),
    _paired("R4", "How orderly is the completed 5M benchmark progression, pullback or follow-through?", PROGRESSION, ("5M",)),
    _paired("R5", "What benchmark location, acceptance or rejection is visible at the supplied lawful structure?", ACCEPTANCE, ("4H", "15M", "5M"), STRUCTURAL_ANCHOR_RULE),
    _paired("M1", "What broader completed 1D native MCX context is visible relative to the proposed direction?", CONTEXT, ("1D",)),
    _paired("M2", "How organized is the completed 4H native MCX structure?", STRUCTURE, ("4H",)),
    _paired("M3", "What does completed 15M native setup context show about follow-through, stalling or failure?", FOLLOW, ("15M",)),
    _paired("M4", "How orderly is the permitted completed 5M native MCX pullback or progression?", PROGRESSION, ("5M",)),
    _paired("M5", "How does native MCX interact with the supplied governed level through acceptance, rejection, retest or return-through?", ACCEPTANCE, ("15M", "5M"), ANCHOR_RULE),
    _paired("X1", "Does native MCX structure confirm, partially confirm or conflict with the international benchmark structure?", ("CONFIRMS_REFERENCE", "PARTIAL_CONFIRMATION", "CONFLICTS_WITH_REFERENCE", "UNCLEAR"), MCX_TIMEFRAMES),
    _paired("X2", "Within comparable permitted evidence, is the benchmark apparently leading, moving with MCX, or is MCX leading or diverging?", ("REFERENCE_LEADING", "MOVING_TOGETHER", "MCX_LEADING_OR_DIVERGING", "UNCLEAR", "NOT_OBSERVABLE"), MCX_TIMEFRAMES,
            "Visual contemporaneous observation only, not measured latency or causality. Insufficient timing correspondence is NOT_OBSERVABLE."),
    _paired("X3", "Where a lawful structural break or acceptance exists, does corresponding benchmark behaviour confirm native MCX behaviour?", ("CONFIRMED", "PARTIALLY_CONFIRMED", "NOT_CONFIRMED", "CONFLICTING", "NOT_OBSERVABLE", "UNCLEAR"), MCX_TIMEFRAMES, STRUCTURAL_ANCHOR_RULE),
    _paired("X4", "Is there material visible structural disagreement between the benchmark and native MCX?", ("NO_MATERIAL_DIVERGENCE_VISIBLE", "PARTIAL_DIVERGENCE", "MATERIAL_DIVERGENCE", "UNCLEAR", "NOT_OBSERVABLE"), MCX_TIMEFRAMES,
            "Currency, basis, contract timing and sessions may differ. Divergence is not a trade rejection or proof either market is wrong."),
    _paired("X5", "Is there a material native/reference observation not represented by R1-R5, M1-M5 or X1-X4?", ESCAPE, MCX_TIMEFRAMES,
            "NONE requires a null explanation. MATERIAL_OBSERVATION requires why_not_covered_elsewhere; do not repeat earlier observations."),
)


@dataclass(frozen=True, slots=True)
class VisualObservationV2:
    """Seven-field common observation for explicitly versioned NSE/MCX Answers."""
    question_id: str
    observation_status: ObservationStatus
    answer: str | None
    visible_timeframes: tuple[str, ...]
    visible_basis: str | None
    status_detail: str | None
    why_not_covered_elsewhere: str | None

    def __post_init__(self):
        question = next((q for q in NSE_QUESTIONS + MCX_QUESTIONS if q.question_id == self.question_id), None)
        def text(value):return type(value) is str and bool(value) and value == value.strip() and len(value) <= 2000
        def invalid():raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
        if question is None or type(self.observation_status) is not ObservationStatus:
            invalid()
        if type(self.visible_timeframes) is not tuple or any(t not in question.timeframe_scope for t in self.visible_timeframes):
            invalid()
        if tuple(t for t in question.timeframe_scope if t in self.visible_timeframes) != self.visible_timeframes:
            invalid()
        for value in (self.visible_basis, self.status_detail, self.why_not_covered_elsewhere):
            if value is not None and not text(value):invalid()
        present = self.observation_status in (ObservationStatus.OBSERVED, ObservationStatus.PARTIAL)
        if present:
            if self.answer not in question.allowed_answers or not text(self.visible_basis) or not self.visible_timeframes:invalid()
            if self.observation_status is ObservationStatus.OBSERVED and self.visible_timeframes != question.timeframe_scope:invalid()
            if self.observation_status is ObservationStatus.PARTIAL and not text(self.status_detail):invalid()
        elif (self.answer is not None or self.visible_timeframes or self.visible_basis is not None
              or self.observation_status is not ObservationStatus.NOT_APPLICABLE and not text(self.status_detail)):
            invalid()
        if self.question_id in ("Q10", "X5") and self.answer == "MATERIAL_OBSERVATION":
            if not text(self.why_not_covered_elsewhere):invalid()
        elif self.why_not_covered_elsewhere is not None:
            invalid()


def require_question_content(observations, panels):
    """Question-required overlays stay separate from core panel validation."""
    from kronos.intraday.chart_input import content_projection, ContentRequirement
    from kronos.intraday.validation import FactObservability
    for observation in observations:
        if type(observation) is not VisualObservationV2:
            continue  # historical V1 follows its existing governed path
        anchored = observation.question_id in {"Q6", "Q9", "M5"}
        if not anchored or observation.answer in {None, "UNCLEAR", "NOT_OBSERVABLE"}:
            continue
        roles = {"REFERENCE"} if observation.question_id.startswith("R") else {"REFERENCE", "NATIVE"} if observation.question_id.startswith("X") else {"NATIVE"}
        needed = {(role, t) for role in roles for t in observation.visible_timeframes}
        found = {(p.role, p.timeframe) for p in panels if (p.role, p.timeframe) in needed
                 and all(state is FactObservability.EXACT for _, requirement, state in content_projection(p, ("factual_levels",))
                         if requirement is ContentRequirement.QUESTION_REQUIRED)}
        if found != needed:
            raise ReviewError(ReviewFailure.CHART_CORRESPONDENCE_UNVERIFIABLE)
