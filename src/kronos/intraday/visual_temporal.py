"""Independent visible contradiction evidence; no endpoint reconstruction or I/O."""
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from zoneinfo import ZoneInfo
from kronos.intraday.validation import ValidationState
from kronos.intraday.contracts import CandleCompletion


class TemporalCompatibility(StrEnum):
    CONFIRMED_COMPATIBLE = "CONFIRMED_COMPATIBLE"
    VISIBLY_CONTRADICTED = "VISIBLY_CONTRADICTED"
    INSUFFICIENT_VISUAL_EVIDENCE = "INSUFFICIENT_VISUAL_EVIDENCE"


@dataclass(frozen=True, slots=True)
class VisualTemporalContext:
    context_sufficient: bool | None
    visible_labels: tuple[str, ...]
    later_evidence: str
    forming_evidence: str
    forming_excluded: bool | None
    excluded_forming_date: date | None
    other_contradiction: str
    basis: str | None
    exclusion_basis: str | None

    def __post_init__(self):
        text = lambda v: type(v) is str and bool(v) and v == v.strip() and len(v) <= 2000
        if (any(v is not None and type(v) is not bool for v in (self.context_sufficient, self.forming_excluded))
            or type(self.visible_labels) is not tuple or len(self.visible_labels) > 16
            or any(not text(v) for v in self.visible_labels)
            or len(set(self.visible_labels)) != len(self.visible_labels)
            or any(v not in {"PRESENT", "ABSENT", "UNKNOWN"} for v in
                   (self.later_evidence, self.forming_evidence, self.other_contradiction))
            or any(v is not None and not text(v) for v in (self.basis, self.exclusion_basis))
            or self.excluded_forming_date is not None and type(self.excluded_forming_date) is not date):
            raise ValueError("VISUAL_TEMPORAL_CONTEXT_INVALID")


def from_document(raw):
    if type(raw) is not dict:
        raise ValueError("VISUAL_TEMPORAL_CONTEXT_INVALID")
    data = dict(raw)
    if type(data.get("visible_labels")) is not list:
        raise ValueError("VISUAL_TEMPORAL_CONTEXT_INVALID")
    data["visible_labels"] = tuple(data["visible_labels"])
    if data.get("excluded_forming_date") is not None:
        data["excluded_forming_date"] = date.fromisoformat(data["excluded_forming_date"])
    return VisualTemporalContext(**data)


def compare_visible_time(expected, observed, *, received_at, machine_context):
    """Machine schedule is used for comparison only; observations never change.

    The Analyst's findings remain independently supplied, like identity/content
    observations. This function cannot read pixels or verify prose by inference.
    """
    S = ValidationState
    c = observed.temporal_context
    # A reference without an independent calendar cannot acquire an invented
    # date/timezone relationship. Its explicit visual findings and any aware
    # observed timestamps still reject contradictions.
    # Exchange timezone is machine authority. Observed timezone is a raw display
    # label, not an IANA identity that must equal the exchange configuration.
    zone = ZoneInfo(machine_context[2]) if machine_context else expected.analysis_boundary.tzinfo
    boundary_day = expected.analysis_boundary.astimezone(zone).date()
    dates = (observed.trading_date, c.excluded_forming_date)
    if machine_context and any(d is not None and d > boundary_day for d in dates):
        return S.NOT_VALIDATED, "VISIBLE_DATE_AFTER_REVIEW_BOUNDARY"
    if c.later_evidence == "PRESENT" or c.other_contradiction == "PRESENT":
        return S.NOT_VALIDATED, "VISIBLE_TEMPORAL_CONTRADICTION"
    if any(t is not None and t > expected.analysis_boundary for t in
           (observed.candle_start, observed.candle_end, observed.latest_visible_end)):
        return S.NOT_VALIDATED, "VISIBLE_EVIDENCE_AFTER_ANALYSIS_BOUNDARY"
    if (observed.candle_start is not None and observed.candle_end is not None
        and observed.candle_start >= observed.candle_end
        or observed.candle_end is not None and observed.captured_at is not None
        and observed.candle_end > observed.captured_at
        or observed.captured_at is not None and observed.captured_at > received_at):
        return S.NOT_VALIDATED, "VISIBLE_TIME_CHRONOLOGY_CONTRADICTION"
    if observed.completion is CandleCompletion.INCOMPLETE:
        return S.NOT_VALIDATED, "QUALIFIED_CANDLE_VISIBLY_FORMING"
    if machine_context:
        day, session, timezone, frame, start, end = machine_context
        if observed.trading_date is not None and observed.trading_date < day:
            return S.NOT_VALIDATED, "VISIBLE_DATE_STALE_FOR_SELECTED_CONTEXT"
        if observed.trading_date is not None and observed.trading_date > day:
            return S.NOT_VALIDATED, "VISIBLE_DATE_AFTER_SELECTED_COMPLETED_CONTEXT"
        # Exact observed bar endpoints, when independently supplied, still bind
        # to that selected source. They are no longer required to exist.
        if (observed.candle_start is not None and observed.candle_start != start
            or observed.candle_end is not None and observed.candle_end != end
            or observed.latest_visible_end is not None and observed.latest_visible_end != end
            or observed.captured_at is not None and observed.captured_at < end):
            return S.NOT_VALIDATED, "VISIBLE_SELECTED_CONTEXT_MISMATCH"
    if c.forming_evidence == "PRESENT" and c.forming_excluded is not True:
        return S.NOT_VALIDATED, "PROHIBITED_VISIBLE_FORMING_EVIDENCE"
    if (c.context_sufficient is not True or not c.visible_labels or not c.basis
        or c.later_evidence != "ABSENT" or c.other_contradiction != "ABSENT"
        or c.forming_evidence == "UNKNOWN" or observed.entire_panel_observed is not True):
        return S.UNVERIFIABLE, "INSUFFICIENT_VISUAL_TEMPORAL_CONTEXT"
    if c.forming_evidence == "PRESENT":
        if not c.exclusion_basis or c.excluded_forming_date != boundary_day:
            return S.UNVERIFIABLE, "FORMING_EXCLUSION_NOT_ESTABLISHED"
    elif c.forming_excluded is not False or c.excluded_forming_date is not None or c.exclusion_basis is not None:
        return S.UNVERIFIABLE, "INCONSISTENT_FORMING_SCOPE"
    return S.VALIDATED, "VISIBLE_TEMPORAL_CONTEXT_COMPATIBLE"
