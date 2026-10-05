"""Six-sheet Swing WO-12 XLSX projection using the qualified local XLSX primitives.

The imported primitives package XML and tables only; Intraday research policy,
rows, denominators and authority do not cross into Swing.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from kronos.browser.intraday_research import (
    MAX_WORKBOOK_BYTES, _app_properties, _column, _content_types,
    _core_properties, _package_relationships, _sheet,
    _sheet_relationship, _styles, _table, _widths, _workbook,
    _workbook_relationships, _write,
)


SHEETS = ("Opportunities", "Tracks", "Events", "Analysis", "Data_Quality", "Metadata")
OPPORTUNITY_COLUMNS = (
    "opportunity_identity", "origin_month", "market", "instrument", "exact_contract_identity",
    "expiry", "direction", "admitted_at", "origin_source_identity", "origin_source_version",
    "decision", "activation_disposition", "decision_source_identity",
    "four_of_five_at", "five_of_five_at",
    "origin_reference_price", "origin_price_observation_identity", "authority",
)
TRACK_COLUMNS = (
    "opportunity_identity", "track_kind", "truth_class", "track_identity",
    "milestone_identity", "market", "exact_contract_identity",
    "direction", "readiness_score", "readiness_state", "milestone_at",
    "milestone_reference_price", "price_observation_identity", "price_received_at",
    "horizon_sessions", "due_session_identity", "status", "reason", "actual_close",
    "raw_change_pct", "direction_adjusted_pct", "candle_favourable_pct",
    "candle_adverse_pct", "excursion_authority", "lifecycle_state",
    "entry_price", "exit_price", "source_gross_pnl", "sponsor_attested",
)
EVENT_COLUMNS = ("opportunity_identity", "event_type", "event_identity", "occurred_at", "source_identity")
ANALYSIS_COLUMNS = (
    "market", "readiness_score", "direction", "horizon_sessions", "opportunities",
    "milestones", "eligible", "pending", "unavailable", "expiry_limited",
    "with_prediction", "against_prediction", "unchanged", "success_rate",
    "always_up_same_sample_rate", "mean_direction_adjusted_pct", "median_direction_adjusted_pct",
    "min_direction_adjusted_pct", "max_direction_adjusted_pct", "inclusion_rule",
)
QUALITY_COLUMNS = ("opportunity_identity", "milestone_identity", "horizon_sessions", "quality_code", "detail")
METADATA_COLUMNS = ("key", "value")
COLUMNS = (OPPORTUNITY_COLUMNS, TRACK_COLUMNS, EVENT_COLUMNS,
           ANALYSIS_COLUMNS, QUALITY_COLUMNS, METADATA_COLUMNS)


@dataclass(frozen=True, slots=True)
class SwingResearchProjection:
    year_month: str
    generated_at: datetime
    projection_identity: str
    opportunities: tuple[tuple[object, ...], ...]
    tracks: tuple[tuple[object, ...], ...]
    events: tuple[tuple[object, ...], ...]
    analysis: tuple[tuple[object, ...], ...]
    data_quality: tuple[tuple[object, ...], ...]
    metadata: tuple[tuple[object, ...], ...]

    @property
    def rows(self) -> tuple[tuple[tuple[object, ...], ...], ...]:
        return (self.opportunities, self.tracks, self.events,
                self.analysis, self.data_quality, self.metadata)


def export_swing_research_workbook(projection: SwingResearchProjection) -> bytes:
    if type(projection) is not SwingResearchProjection:
        raise TypeError("SWING_WO12_PROJECTION_REQUIRED")
    if any(any(len(row) != len(columns) for row in rows)
           for columns, rows in zip(COLUMNS, projection.rows, strict=True)):
        raise ValueError("SWING_WO12_WORKBOOK_COLUMNS_INVALID")
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        _write(archive, "[Content_Types].xml", _content_types())
        _write(archive, "_rels/.rels", _package_relationships())
        _write(archive, "docProps/core.xml", _core_properties(projection.generated_at).replace(
            "KRONOS Intraday Monthly Research Ledger", "KRONOS Swing Monthly Research Ledger"))
        _write(archive, "docProps/app.xml", _app_properties())
        _write(archive, "xl/workbook.xml", _workbook())
        _write(archive, "xl/_rels/workbook.xml.rels", _workbook_relationships())
        _write(archive, "xl/styles.xml", _styles())
        for index, (name, columns, rows) in enumerate(zip(SHEETS, COLUMNS, projection.rows, strict=True), 1):
            all_rows = (columns, *rows)
            _write(archive, f"xl/worksheets/sheet{index}.xml",
                   _sheet(all_rows, _widths(columns), table_id=index))
            _write(archive, f"xl/worksheets/_rels/sheet{index}.xml.rels", _sheet_relationship(index))
            _write(archive, f"xl/tables/table{index}.xml", _table(index, name, columns, len(all_rows)))
    payload = output.getvalue()
    if len(payload) > MAX_WORKBOOK_BYTES:
        raise ValueError("SWING_WO12_WORKBOOK_SIZE_INVALID")
    validate_swing_research_workbook(payload, projection)
    return payload


def validate_swing_research_workbook(payload: bytes,
                                     projection: SwingResearchProjection) -> None:
    if type(projection) is not SwingResearchProjection:
        raise TypeError("SWING_WO12_PROJECTION_REQUIRED")
    with ZipFile(BytesIO(payload)) as archive:
        names = set(archive.namelist())
        required = {"xl/workbook.xml", "xl/styles.xml",
                    *{f"xl/worksheets/sheet{i}.xml" for i in range(1, 7)},
                    *{f"xl/tables/table{i}.xml" for i in range(1, 7)}}
        if (not required <= names or any("vbaProject" in name or "externalLinks" in name
                                         or name.startswith("xl/media/") for name in names)):
            raise ValueError("SWING_WO12_WORKBOOK_PACKAGE_INVALID")
        workbook = archive.read("xl/workbook.xml").decode()
        if any(f'name="{name}"' not in workbook for name in SHEETS):
            raise ValueError("SWING_WO12_WORKBOOK_SCHEMA_INVALID")
        for index, (columns, rows) in enumerate(zip(COLUMNS, projection.rows, strict=True), 1):
            end = f"{_column(len(columns))}{len(rows) + 1}"
            sheet = archive.read(f"xl/worksheets/sheet{index}.xml").decode()
            table = archive.read(f"xl/tables/table{index}.xml").decode()
            if (f'ref="A1:{end}"' not in table or f'<dimension ref="A1:{end}"' not in sheet
                    or "<f>" in sheet or '<pane ySplit="1"' not in sheet
                    or "<autoFilter" not in sheet):
                raise ValueError("SWING_WO12_WORKBOOK_CONTENT_INVALID")
            for column in columns:
                if f'name="{column}"' not in table:
                    raise ValueError("SWING_WO12_WORKBOOK_CONTENT_INVALID")
