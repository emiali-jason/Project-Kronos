"""Pure Sponsor views of the existing WO12 projection; no new evidence owner."""
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from kronos.application.intraday_research import OPPORTUNITY_COLUMNS, TRACK_COLUMNS, EVENT_COLUMNS
from kronos.application.intraday_opportunity_journey import JOURNEY_COLUMNS

VERSION = "2.4.0"
IST = ZoneInfo("Asia/Kolkata")


def monthly_path(root, month):
    date = datetime.strptime(month, "%Y_%m")
    return root / str(date.year) / (date.strftime("%Y-%m — %B") + ".xlsx")


def _rows(columns, values):
    return tuple(dict(zip(columns, row, strict=True)) for row in values)


def sponsor_sheets(projection):
    """Only reshape governed values; retain their original denominator and truth."""
    journey = _rows(JOURNEY_COLUMNS, projection.journey)
    opportunities = _rows(OPPORTUNITY_COLUMNS, projection.opportunities)
    tracks = _rows(TRACK_COLUMNS, projection.tracks)
    counts = Counter(row["EOD Match"] for row in journey)
    summary = (
        ("Month", projection.year_month.replace("_", "-")),
        ("Evidence projection at", projection.generated_at.astimezone(IST).isoformat()),
        ("Considered opportunity / methodology cohorts", len(journey)),
        ("Evaluated", counts["MATCHED"] + counts["NOT_MATCHED"]),
        ("Matched direction", counts["MATCHED"]),
        ("Not matched direction", counts["NOT_MATCHED"]),
        ("Not evaluable", counts["NOT_EVALUABLE"]),
        ("Meaning", "Terminal direction relative to original Assessment Price; not profitability"),
        ("PAPER quantity", "1 model lot"),
        ("Observation exposure", "Zero — counterfactual"),
        ("Net profitability", "NOT_EVALUABLE — no governed charges/net result"),
    )
    for threshold in (3, 4, 5):
        flags = [row[f'False Advance {threshold}'] for row in journey
                 if row[f'False Advance {threshold}'] in {'YES', 'NO'}]
        summary += ((f'False advances at {threshold}/5', flags.count('YES') if flags else
            'NOT_EVALUABLE — no evaluable advance retained'),)
    daily = Counter((row["Trading Date"], row["EOD Match"]) for row in journey)
    days = sorted({row["Trading Date"] for row in journey})
    daily_rows = tuple((day, sum(daily[day, state] for state in ("MATCHED", "NOT_MATCHED", "NOT_EVALUABLE")),
                        daily[day, "MATCHED"], daily[day, "NOT_MATCHED"], daily[day, "NOT_EVALUABLE"]) for day in days)
    audit = tuple((row["opportunity_id"], row["canonical_subject_identity"], row["research_date"],
                   row["probable_state"], row["wo09_highest_satisfied_count"], row["wo12_progression_currentness"])
                  for row in opportunities)
    def select(columns, rows):
        from kronos.intraday.sponsor_presentation import security_name
        return tuple(tuple(security_name(str(row[column])) if column == "Security" else row.get(column, "NOT_EVALUABLE") for column in columns) for row in rows)
    attention_columns = ("Opportunity ID", "Security", "Trading Date", "Direction", "Initial Count",
        "Initial WO09", "Final WO09", "WO09 Currentness", "Assessment Price", "WO08 Version", "Exact MCX Contract", "Consideration Identity")
    journey_columns = ("Opportunity ID", "Security", "Trading Date", "Direction", "Identified At", "Assessment Price",
        "First 4 of 5 At", "First 5 of 5 At", "Entry Met", "Entry First Met At", "Target Met", "Target First Met At",
        "Stop Met", "Stop First Met At", "Paper Class", "Paper State", "Chronology Coverage", "EOD Match", "EOD Reason", "Consideration Identity")
    track_columns = ("opportunity_id", "truth_class", "direction", "future_trading_symbol", "model_lots", "state",
        "entry_at", "entry_price", "exit_at", "exit_price", "exit_reason", "terminal_status", "points", "model_r",
        "gross_model_result", "monitoring_complete")
    prediction_columns = ("Opportunity ID", "Security", "Trading Date", "Direction", "Assessment Price",
        "Terminal 5M At", "Terminal 5M Price", "Directional Move Pct", "EOD Match", "EOD Reason", "WO08 Version", "Consideration Identity")
    false_columns = ("Opportunity ID", "Security", "Trading Date", "Direction", "EOD Match",
        "False Advance 3", "False Advance 4", "False Advance 5")
    return (
        ("Monthly Summary", ("Metric", "Value"), summary),
        ("Daily Summary", ("Date", "Considered cohorts", "Matched", "Not matched", "Not evaluable"), daily_rows),
        ("Analysis Funnel", ("Opportunity ID", "Security", "Date", "Probables", "Highest retained score", "Pointer currentness"), audit),
        *((name, attention_columns, select(attention_columns, (r for r in journey if r["Initial Count"] == count)))
          for name, count in (("Near Ready", 3), ("Ready", 4), ("Now", 5))),
        ("Opportunity Journey", journey_columns, select(journey_columns, journey)),
        ("PAPER Positions", tuple(c.replace('_', ' ').title() for c in track_columns), select(track_columns, (r for r in tracks if r["truth_class"] == "PAPER_POSITION"))),
        ("Observations", tuple(c.replace('_', ' ').title() for c in track_columns), select(track_columns, (r for r in tracks if r["truth_class"] == "PAPER_OBSERVATION"))),
        ("Prediction Performance", prediction_columns, select(prediction_columns, journey)),
        ("False Advances", false_columns, select(false_columns, (r for r in journey if any(r[c] == "YES" for c in false_columns[-3:])))),
    )


def summary_document(projection):
    if projection.workbook_version == '2.2.0':
        return {"month": projection.year_month, "metrics": {"Prediction results": "NOT_EVALUABLE — historical workbook predates governed Opportunity Journey"},
            "false_advance_rows": None, "projection_identity": projection.projection_identity}
    sheets = sponsor_sheets(projection)
    return {"month": projection.year_month, "metrics": dict(sheets[0][2]),
            "false_advance_rows": len(sheets[-1][2]), "projection_identity": projection.projection_identity}


def metric_coverage(tracks):
    """Coverage is a retained metric fact, independent of closure/terminal state."""
    if len(tracks) != 1:
        return 'UNAVAILABLE'
    value = tracks[0]['monitoring_complete']
    return 'COMPLETE' if value is True else 'INCOMPLETE' if value is False else 'UNAVAILABLE'


def filtered_sheet(projection, name, *, search="", direction="", status="", start=None, end=None, truth="", completion=""):
    if truth or completion:
        from dataclasses import replace
        tracks = _rows(TRACK_COLUMNS, projection.tracks)
        selected = []
        for row in projection.journey:
            value = dict(zip(JOURNEY_COLUMNS, row, strict=True))
            references = set(str(value['Lifecycle References']).split('; '))
            matching = tuple(t for t in tracks if t['source_current_identity'] in references
                and t['truth_class'] == value['Paper Class'])
            coverage = metric_coverage(matching)
            if (not truth or value['Paper Class'] == truth) and (not completion or completion == coverage):
                selected.append(row)
        projection = replace(projection, journey=tuple(selected))
    sheet = next(s for s in sponsor_sheets(projection) if s[0] == name)
    columns, rows = sheet[1:]
    result = []
    for row in rows:
        values = dict(zip(columns, row, strict=True))
        if search.casefold() not in " ".join(str(v) for v in row).casefold():
            continue
        if direction and values.get("Direction", values.get("direction")) != direction:
            continue
        if status and status not in {str(values.get(c)) for c in ("EOD Match", "Paper State", "state", "Final WO09")}:
            continue
        day = values.get("Trading Date")
        if day is not None:
            day = datetime.fromisoformat(str(day)).date()
            if (start and day < start) or (end and day > end):
                continue
        result.append(row)
    return name, columns, tuple(result)
