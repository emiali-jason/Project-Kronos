"""Deterministic Sponsor-facing historical Reports projection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
import csv
import io
import json
from xml.sax.saxutils import escape as xml_escape
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo
from zoneinfo import ZoneInfo

from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.native_trade_journal import (
    JournalRecordType,
    TradeJournalSnapshot,
)
from kronos.swing.v1.observation_research_ledger_v2 import (
    ObservationMode,
    ObservationOperationalHandoffV2,
    ObservationOperationalRoute,
)


_IST = ZoneInfo("Asia/Kolkata")
REPORTS_EXPORT_SCHEMA = "KRONOS-SPONSOR-HISTORICAL-REPORTS-V1"
REPORTS_AUTHORITY = "FACTUAL_HISTORY_ONLY_NO_RESEARCH_TRADING_OR_BROKER_AUTHORITY"


class ReportProduct(StrEnum):
    SWING = "SWING"
    INTRADAY = "INTRADAY"


class ReportView(StrEnum):
    OVERVIEW = "OVERVIEW"
    PAPER = "PAPER"
    LIVE = "LIVE"
    PAPER_OBSERVATIONS = "PAPER_OBSERVATIONS"
    ALL_RECORDS = "ALL_RECORDS"


class ReportFamily(StrEnum):
    PAPER = "PAPER"
    LIVE = "LIVE"
    PAPER_OBSERVATION = "PAPER_OBSERVATION"
    NONE = "NONE"
    DO_NOTHING = "DO_NOTHING"


@dataclass(frozen=True, slots=True)
class ReportsQuery:
    product: ReportProduct = ReportProduct.SWING
    view: ReportView = ReportView.OVERVIEW
    from_date: date | None = None
    to_date: date | None = None
    instrument: str = ""
    direction: V1Direction | None = None
    status: str = ""
    page: int = 1
    page_size: int = 25
    exit_reason: str = ""
    completeness: str = ""

    def __post_init__(self) -> None:
        if (
            type(self.product) is not ReportProduct
            or type(self.view) is not ReportView
            or (self.from_date is not None and type(self.from_date) is not date)
            or (self.to_date is not None and type(self.to_date) is not date)
            or (
                self.from_date is not None and self.to_date is not None
                and self.from_date > self.to_date
            )
            or type(self.instrument) is not str
            or len(self.instrument) > 80
            or self.direction not in {None, V1Direction.LONG, V1Direction.SHORT}
            or self.exit_reason not in {"", "STOP_LOSS", "TARGET", "SPONSOR_EXIT"}
            or self.completeness not in {"", "COMPLETE", "INCOMPLETE", "UNAVAILABLE"}
            or type(self.status) is not str
            or len(self.status) > 80
            or type(self.page) is not int or self.page < 1
            or type(self.page_size) is not int or not 1 <= self.page_size <= 100
        ):
            raise ValueError("REPORTS_QUERY_INVALID")


@dataclass(frozen=True, slots=True)
class HistoricalReportRecord:
    record_identity: str
    decision_identity: str
    record_date: date
    relevant_timestamp: datetime
    instrument: str
    direction: V1Direction
    family: ReportFamily
    status: str
    entry: Decimal | None
    exit: Decimal | None
    pnl: Decimal | None
    target: Decimal | None
    stop: Decimal | None
    sponsor_position_outcome: str
    paper_track_outcome: str
    objective_outcome: str
    step31_severity: str
    risk_state: str
    activation_disposition: str
    source_contract_identity: str
    source_contract_version: str
    intraday_facts: str | None = None
    paper_history_representation: str = "NOT_APPLICABLE"
    paper_raw_detail_availability: str = "NOT_APPLICABLE"
    paper_first_observation_at: datetime | None = None
    paper_last_observation_at: datetime | None = None
    paper_fact_count: int | None = None
    paper_source_count: int | None = None
    paper_consolidation_identity: str | None = None
    paper_history_detail_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ReportsOverview:
    records: int
    paper_positions: int
    live_positions: int
    paper_observations: int
    completed_records: int
    net_pnl: Decimal | None
    win_rate: None = None
    average_r: None = None
    max_drawdown: None = None
    daily_pnl: None = None
    effectiveness: None = None


@dataclass(frozen=True, slots=True)
class HistoricalReportsProjection:
    query: ReportsQuery
    governed_current_trading_date: date | None
    records: tuple[HistoricalReportRecord, ...]
    page_records: tuple[HistoricalReportRecord, ...]
    overview: ReportsOverview
    page_count: int
    total_records: int


def project_historical_reports(
    operational: tuple[ObservationOperationalHandoffV2, ...],
    journal: TradeJournalSnapshot,
    query: ReportsQuery,
    *,
    governed_current_trading_date: date | None,
) -> HistoricalReportsProjection:
    """Project immutable evidence into one filtered, paginated historical book."""

    if query.product is ReportProduct.INTRADAY:
        return HistoricalReportsProjection(
            query, governed_current_trading_date, (), (), _overview(()), 0, 0
        )
    by_decision: dict[str, HistoricalReportRecord] = {}
    for item in operational:
        record = _from_operational(item)
        if record is not None:
            by_decision[record.decision_identity] = record
    for item in journal.records:
        if (
            item.record_type is not JournalRecordType.TRADE
            or item.sponsor_decision_id in by_decision
        ):
            continue
        by_decision[item.sponsor_decision_id] = HistoricalReportRecord(
            record_identity=item.journal_record_id,
            decision_identity=item.sponsor_decision_id,
            record_date=(item.exit_timestamp or item.created_at).astimezone(_IST).date(),
            relevant_timestamp=item.exit_timestamp or item.created_at,
            instrument=item.instrument,
            direction=item.direction,
            family=(
                ReportFamily.PAPER
                if item.mode.value == "PAPER" else ReportFamily.LIVE
            ),
            status="EXITED",
            entry=item.actual_entry,
            exit=item.actual_exit,
            pnl=item.gross_pnl,
            target=item.model_target,
            stop=item.model_stop,
            sponsor_position_outcome=item.exit_reason or item.outcome.value,
            paper_track_outcome="NOT_APPLICABLE",
            objective_outcome="UNAVAILABLE",
            step31_severity="UNAVAILABLE",
            risk_state="UNAVAILABLE",
            activation_disposition="ACTIVATED",
            source_contract_identity=item.contract_identity,
            source_contract_version=item.contract_version,
        )
    ordered = tuple(sorted(
        by_decision.values(),
        key=lambda item: (-item.relevant_timestamp.timestamp(), item.record_identity),
    ))
    filtered = tuple(item for item in ordered if _matches(item, query))
    total = len(filtered)
    page_count = (total + query.page_size - 1) // query.page_size
    start = (query.page - 1) * query.page_size
    page_records = filtered[start:start + query.page_size]
    return HistoricalReportsProjection(
        query, governed_current_trading_date, filtered, page_records,
        _overview(filtered), page_count, total,
    )


def export_reports_json(projection: HistoricalReportsProjection) -> bytes:
    return (json.dumps({
        "schema": REPORTS_EXPORT_SCHEMA,
        "authority": REPORTS_AUTHORITY,
        "product": projection.query.product.value,
        "filters": _filters(projection.query),
        "records": [_export_record(item) for item in projection.records],
    }, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def export_reports_csv(projection: HistoricalReportsProjection) -> bytes:
    target = io.StringIO()
    fields = INTRADAY_FIELDS if projection.query.product is ReportProduct.INTRADAY else tuple(_export_record_fields())
    writer = csv.DictWriter(target, fieldnames=fields)
    writer.writeheader()
    writer.writerows(
        {key: _safe_csv(value) for key, value in _intraday_values(item).items()}
        if item.intraday_facts is not None else _export_record(item)
        for item in projection.records)
    return target.getvalue().encode("utf-8")


def export_reports_xlsx(
    projection: HistoricalReportsProjection,
    *,
    generated_at: datetime | None = None,
) -> bytes:
    """Export the exact filtered Swing projection as a formula-free XLSX."""

    if type(projection) is not HistoricalReportsProjection:
        raise TypeError("REPORTS_EXCEL_PROJECTION_INVALID")
    created = datetime.now(UTC) if generated_at is None else generated_at
    if created.tzinfo is None or created.utcoffset() is None:
        raise ValueError("REPORTS_EXCEL_TIMESTAMP_INVALID")

    report_rows: tuple[tuple[object, ...], ...] = (
        INTRADAY_FIELDS if projection.query.product is ReportProduct.INTRADAY else _xlsx_headers(),
        *tuple(tuple(_intraday_values(item).values()) if item.intraday_facts is not None
               else _xlsx_record(item) for item in projection.records),
    )
    filters = _filters(projection.query)
    summary_rows: tuple[tuple[object, ...], ...] = (
        ("KRONOS HISTORICAL REPORT", "FACTUAL HISTORY ONLY"),
        ("Product", projection.query.product.value),
        ("Report View", projection.query.view.value.replace("_", " ")),
        ("Generated At", _xlsx_timestamp(created)),
        ("From", filters["from"] or "ALL"),
        ("To", filters["to"] or "ALL"),
        ("Instrument Filter", filters["instrument"] or "ALL"),
        ("Direction Filter", filters["direction"] or "ALL"),
        ("Status / Outcome Filter", filters["status"] or "ALL"),
        ("Record Count", len(projection.records)),
        (
            "Net P/L",
            (
                "UNAVAILABLE"
                if projection.overview.net_pnl is None
                else projection.overview.net_pnl
            ),
        ),
        ("Authority", REPORTS_AUTHORITY),
    )

    target = io.BytesIO()
    with ZipFile(target, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        _xlsx_write(archive, "[Content_Types].xml", _xlsx_content_types())
        _xlsx_write(archive, "_rels/.rels", _xlsx_package_relationships())
        _xlsx_write(archive, "docProps/app.xml", _xlsx_app_properties())
        _xlsx_write(
            archive, "docProps/core.xml", _xlsx_core_properties(created)
        )
        _xlsx_write(archive, "xl/workbook.xml", _xlsx_workbook())
        _xlsx_write(
            archive, "xl/_rels/workbook.xml.rels", _xlsx_workbook_relationships()
        )
        _xlsx_write(archive, "xl/styles.xml", _xlsx_styles(wrap=projection.query.product is ReportProduct.INTRADAY))
        _xlsx_write(
            archive,
            "xl/worksheets/sheet1.xml",
            _xlsx_sheet(report_rows, header=True, auto_filter=True,
                        fitted=projection.query.product is ReportProduct.INTRADAY),
        )
        _xlsx_write(
            archive,
            "xl/worksheets/sheet2.xml",
            _xlsx_sheet(summary_rows, header=False, auto_filter=False,
                        fitted=projection.query.product is ReportProduct.INTRADAY),
        )
    return target.getvalue()


def reports_excel_filename(
    projection: HistoricalReportsProjection,
    generated_at: datetime,
) -> str:
    if (
        type(projection) is not HistoricalReportsProjection
        or generated_at.tzinfo is None
        or generated_at.utcoffset() is None
    ):
        raise ValueError("REPORTS_EXCEL_FILENAME_INVALID")
    timestamp = generated_at.astimezone(_IST).strftime("%Y%m%d_%H%M%S")
    kind = "FACTUAL_REPORT" if projection.query.product is ReportProduct.INTRADAY else "REPORT"
    return f"KRONOS_{projection.query.product.value}_{kind}_{timestamp}_IST.xlsx"


def _from_operational(
    item: ObservationOperationalHandoffV2,
) -> HistoricalReportRecord | None:
    if item.operational_route is ObservationOperationalRoute.ACTIVE:
        return None
    observation = item.mode is ObservationMode.PAPER_OBSERVATION
    if observation:
        if item.paper_track_identity is None:
            return None
        family = ReportFamily.PAPER_OBSERVATION
    elif (
        item.mode in {ObservationMode.PAPER, ObservationMode.LIVE}
        and item.sponsor_position_identity is not None
        and item.activation_disposition.value == "ACTIVATED"
    ):
        family = ReportFamily(item.mode.value)
    else:
        return None
    relevant = item.completion_timestamp or item.decision_timestamp
    return HistoricalReportRecord(
        record_identity=(item.paper_track_identity or item.sponsor_position_identity or item.decision_identity),
        decision_identity=item.decision_identity,
        record_date=relevant.astimezone(_IST).date(),
        relevant_timestamp=relevant,
        instrument=item.instrument,
        direction=item.direction,
        family=family,
        status=(
            "COMPLETE" if observation and item.paper_track_state == "COMPLETE"
            else "OUTCOME NOT ESTABLISHED" if observation
            else "EXITED"
        ),
        entry=item.entry,
        exit=None if observation else item.exit,
        pnl=None if observation else item.position_gross_pnl,
        target=item.target,
        stop=item.stop,
        sponsor_position_outcome=(
            "NOT_APPLICABLE" if observation
            else "CLOSED" if item.exit is not None else "UNAVAILABLE"
        ),
        paper_track_outcome=(
            item.paper_track_outcome if observation else "NOT_APPLICABLE"
        ),
        objective_outcome=item.objective_outcome,
        step31_severity=item.step31_severity.value,
        risk_state=item.risk_state,
        activation_disposition=item.activation_disposition.value,
        source_contract_identity=item.projection_contract_identity,
        source_contract_version=item.projection_contract_version,
        paper_history_representation=item.paper_history_representation if observation else "NOT_APPLICABLE",
        paper_raw_detail_availability=item.paper_raw_detail_availability if observation else "NOT_APPLICABLE",
        paper_first_observation_at=item.paper_first_observation_at if observation else None,
        paper_last_observation_at=item.paper_last_observation_at if observation else None,
        paper_fact_count=item.paper_fact_count if observation else None,
        paper_source_count=item.paper_source_count if observation else None,
        paper_consolidation_identity=item.paper_consolidation_identity if observation else None,
        paper_history_detail_reason=item.paper_history_detail_reason if observation else None,
    )


def _matches(item: HistoricalReportRecord, query: ReportsQuery) -> bool:
    family = {
        ReportView.PAPER: ReportFamily.PAPER,
        ReportView.LIVE: ReportFamily.LIVE,
        ReportView.PAPER_OBSERVATIONS: ReportFamily.PAPER_OBSERVATION,
    }.get(query.view)
    return (
        (family is None or item.family is family)
        and (query.from_date is None or item.record_date >= query.from_date)
        and (query.to_date is None or item.record_date <= query.to_date)
        and (not query.instrument or query.instrument.casefold() in item.instrument.casefold())
        and (query.direction is None or item.direction is query.direction)
        and (not query.status or query.status.casefold() in (
            item.status + " " + item.sponsor_position_outcome + " "
            + item.paper_track_outcome
        ).casefold())
    )


def _overview(records: tuple[HistoricalReportRecord, ...]) -> ReportsOverview:
    positions = tuple(
        item for item in records
        if item.family in {ReportFamily.PAPER, ReportFamily.LIVE}
    )
    net_pnl = (
        None if not positions or any(item.pnl is None for item in positions)
        else sum((item.pnl for item in positions if item.pnl is not None), Decimal("0"))
    )
    return ReportsOverview(
        records=len(records),
        paper_positions=sum(item.family is ReportFamily.PAPER for item in records),
        live_positions=sum(item.family is ReportFamily.LIVE for item in records),
        paper_observations=sum(
            item.family is ReportFamily.PAPER_OBSERVATION for item in records
        ),
        completed_records=len(records),
        net_pnl=net_pnl,
    )


def _filters(query: ReportsQuery) -> dict[str, object]:
    return {
        "view": query.view.value,
        "from": None if query.from_date is None else query.from_date.isoformat(),
        "to": None if query.to_date is None else query.to_date.isoformat(),
        "instrument": query.instrument,
        "direction": None if query.direction is None else query.direction.value,
        "status": query.status,
        **({"exit_reason": query.exit_reason, "completeness": query.completeness}
           if query.product is ReportProduct.INTRADAY else {}),
    }


def _export_record(item: HistoricalReportRecord) -> dict[str, object]:
    if item.intraday_facts is not None:
        return json.loads(item.intraday_facts)
    return {
        "record_identity": item.record_identity,
        "decision_identity": item.decision_identity,
        "evidence_family": item.family.value,
        "record_date": item.record_date.isoformat(),
        "timestamp": item.relevant_timestamp.isoformat(),
        "instrument": item.instrument,
        "direction": item.direction.value,
        "status": item.status,
        "entry": _value(item.entry),
        "exit": _value(item.exit),
        "pnl": "UNAVAILABLE" if item.family is ReportFamily.PAPER_OBSERVATION else _value(item.pnl),
        "target": _value(item.target),
        "stop": _value(item.stop),
        "sponsor_position_outcome": item.sponsor_position_outcome,
        "paper_track_outcome": item.paper_track_outcome,
        "objective_outcome": item.objective_outcome,
        "step31_severity": item.step31_severity,
        "risk_state": item.risk_state,
        "source_contract_identity": item.source_contract_identity,
        "source_contract_version": item.source_contract_version,
        "paper_history_representation": item.paper_history_representation,
        "paper_raw_detail_availability": item.paper_raw_detail_availability,
        "paper_first_observation_at": "UNAVAILABLE" if item.paper_first_observation_at is None else item.paper_first_observation_at.isoformat(),
        "paper_last_observation_at": "UNAVAILABLE" if item.paper_last_observation_at is None else item.paper_last_observation_at.isoformat(),
        "paper_fact_count": "UNAVAILABLE" if item.paper_fact_count is None else item.paper_fact_count,
        "paper_source_count": "UNAVAILABLE" if item.paper_source_count is None else item.paper_source_count,
        "paper_consolidation_identity": item.paper_consolidation_identity or "UNAVAILABLE",
        "paper_history_detail_reason": item.paper_history_detail_reason or "NONE",
    }


def _export_record_fields() -> tuple[str, ...]:
    return (
        "record_identity", "decision_identity", "evidence_family", "record_date",
        "timestamp", "instrument", "direction", "status", "entry", "exit",
        "pnl", "target", "stop", "sponsor_position_outcome",
        "paper_track_outcome", "objective_outcome", "step31_severity",
        "risk_state", "source_contract_identity", "source_contract_version",
        "paper_history_representation", "paper_raw_detail_availability",
        "paper_first_observation_at", "paper_last_observation_at", "paper_fact_count",
        "paper_source_count", "paper_consolidation_identity", "paper_history_detail_reason",
    )


def _value(value: Decimal | None) -> str:
    return "UNAVAILABLE" if value is None else str(value)


def _xlsx_headers() -> tuple[str, ...]:
    return (
        "Date",
        "Completed / Exited At",
        "Instrument",
        "Direction",
        "Family",
        "Status",
        "Entry / Observation Entry",
        "Exit",
        "P/L",
        "Target",
        "SL",
        "Sponsor Position Outcome",
        "Paper Track Outcome",
        "Objective Outcome",
        "Step-31 Severity",
        "Risk at Decision",
        "Activation Disposition",
        "Record Identity",
        "Decision Identity",
        "Source Contract",
        "Source Contract Version",
    )


def _xlsx_record(item: HistoricalReportRecord) -> tuple[object, ...]:
    family = {
        ReportFamily.PAPER: "PAPER POSITION",
        ReportFamily.LIVE: "LIVE POSITION",
        ReportFamily.PAPER_OBSERVATION: "PAPER OBSERVATION",
    }[item.family]
    return (
        item.record_date.isoformat(),
        _xlsx_timestamp(item.relevant_timestamp),
        item.instrument,
        item.direction.value,
        family,
        item.status,
        _xlsx_value(item.entry),
        _xlsx_value(item.exit),
        (
            "UNAVAILABLE"
            if item.family is ReportFamily.PAPER_OBSERVATION
            else _xlsx_value(item.pnl)
        ),
        _xlsx_value(item.target),
        _xlsx_value(item.stop),
        item.sponsor_position_outcome,
        item.paper_track_outcome,
        item.objective_outcome,
        item.step31_severity,
        item.risk_state,
        item.activation_disposition,
        item.record_identity,
        item.decision_identity,
        item.source_contract_identity,
        item.source_contract_version,
    )


def _xlsx_value(value: Decimal | None) -> Decimal | str:
    return "UNAVAILABLE" if value is None else value


def _xlsx_timestamp(value: datetime) -> str:
    return value.astimezone(_IST).strftime("%Y-%m-%d %H:%M:%S IST")


def _xlsx_write(archive: ZipFile, name: str, value: str) -> None:
    info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    archive.writestr(info, value.encode("utf-8"))


def _xlsx_sheet(
    rows: tuple[tuple[object, ...], ...],
    *,
    header: bool,
    auto_filter: bool,
    fitted: bool = False,
) -> str:
    maximum = max((len(row) for row in rows), default=1)
    fitted_widths = tuple(
        34 if not header and index == 0 else 90 if not header else
        34 if index == 0 else 48 if "identit" in str(rows[0][index]) or "checksum" in str(rows[0][index])
        else max(18, min(36, len(str(rows[0][index])) + 3)) for index in range(maximum))
    xml_rows = []
    for row_number, row in enumerate(rows, start=1):
        cells = "".join(
            _xlsx_cell(_xlsx_column(column) + str(row_number), value, header and row_number == 1, wrap=fitted)
            for column, value in enumerate(row, start=1)
        )
        import math
        lines = max((math.ceil(len(str(value)) / max(1, fitted_widths[index] - 3)) for index, value in enumerate(row)), default=1)
        height = f' ht="{max(24, lines * 15 + 6)}" customHeight="1"' if fitted else ''
        xml_rows.append(f'<row r="{row_number}"{height}>{cells}</row>')
    end = f"{_xlsx_column(maximum)}{max(1, len(rows))}"
    widths = "".join(
        f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
        for index, width in enumerate(
            fitted_widths if fitted else (12, 23, 18, 11, 20, 24, 20, 14, 14, 14, 14, 25, 25, 25,
             18, 20, 22, 30, 30, 34, 18)[:maximum],
            start=1,
        )
    )
    filter_xml = f'<autoFilter ref="A1:{end}"/>' if auto_filter else ""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<dimension ref="A1:{end}"/><sheetViews><sheetView workbookViewId="0">'
        + ('<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>' if header else '')
        + '</sheetView></sheetViews><sheetFormatPr defaultRowHeight="15"/>'
        f'<cols>{widths}</cols><sheetData>{"".join(xml_rows)}</sheetData>{filter_xml}'
        '</worksheet>'
    )


def _xlsx_cell(reference: str, value: object, header: bool, *, wrap: bool = False) -> str:
    style = (' s="3"' if header else ' s="2"') if wrap else (' s="1"' if header else "")
    if type(value) is int or type(value) is Decimal:
        return f'<c r="{reference}"{style}><v>{xml_escape(str(value))}</v></c>'
    # inlineStr makes all Sponsor-facing text literal, including = + - @ prefixes.
    text = _xlsx_safe_text(str(value))
    return (
        f'<c r="{reference}" t="inlineStr"{style}><is><t xml:space="preserve">'
        f'{xml_escape(text)}</t></is></c>'
    )


def _xlsx_safe_text(value: str) -> str:
    return "".join(
        character for character in value
        if character in "\t\n\r" or ord(character) >= 32
    )


def _xlsx_column(index: int) -> str:
    value = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        value = chr(65 + remainder) + value
    return value


def _xlsx_content_types() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        '</Types>'
    )


def _xlsx_package_relationships() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        '</Relationships>'
    )


def _xlsx_workbook() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="REPORT" sheetId="1" r:id="rId1"/>'
        '<sheet name="SUMMARY" sheetId="2" r:id="rId2"/></sheets>'
        '<calcPr calcId="0" calcMode="manual"/></workbook>'
    )


def _xlsx_workbook_relationships() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        '</Relationships>'
    )


def _xlsx_styles(*, wrap: bool = False) -> str:
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="2"><font><sz val="10"/><name val="Aptos"/></font>'
        '<font><b/><color rgb="FFFFFFFF"/><sz val="10"/><name val="Aptos"/></font></fonts>'
        '<fills count="3"><fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FF0C4F83"/><bgColor indexed="64"/></patternFill></fill></fills>'
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/></cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        '</styleSheet>'
    )

    if wrap:
        extra = ('<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1">'
                 '<alignment vertical="top" wrapText="1"/></xf>'
                 '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1">'
                 '<alignment vertical="center" wrapText="1"/></xf>')
        xml = xml.replace('<cellXfs count="2">', '<cellXfs count="4">').replace('</cellXfs>', extra + '</cellXfs>')
    return xml


def _xlsx_core_properties(created: datetime) -> str:
    timestamp = created.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<dc:creator>KRONOS</dc:creator><cp:lastModifiedBy>KRONOS</cp:lastModifiedBy>'
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{timestamp}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{timestamp}</dcterms:modified>'
        '<dc:title>KRONOS Historical Report</dc:title></cp:coreProperties>'
    )


def _xlsx_app_properties() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        '<Application>KRONOS</Application><DocSecurity>0</DocSecurity>'
        '<HeadingPairs><vt:vector size="2" baseType="variant"><vt:variant><vt:lpstr>Worksheets</vt:lpstr></vt:variant>'
        '<vt:variant><vt:i4>2</vt:i4></vt:variant></vt:vector></HeadingPairs>'
        '<TitlesOfParts><vt:vector size="2" baseType="lpstr"><vt:lpstr>REPORT</vt:lpstr>'
        '<vt:lpstr>SUMMARY</vt:lpstr></vt:vector></TitlesOfParts></Properties>'
    )



__all__ = [
    "HistoricalReportRecord", "HistoricalReportsProjection", "ReportFamily",
    "ReportProduct", "ReportsOverview", "ReportsQuery", "ReportView",
    "export_reports_csv", "export_reports_json", "export_reports_xlsx",
    "project_historical_reports", "reports_excel_filename",
]


# Same Reports projection, pagination and export infrastructure, exact Intraday binding.
INTRADAY_FIELDS = (
    "opportunity_id", "opportunity_identity", "record_identity", "decision_identity",
    "track_identity", "source_lifecycle_identity", "truth_class", "decision", "decision_at",
    "trading_date", "session_identity", "subject", "direction", "market_family", "contract",
    "expiry", "setup_family", "highest_readiness", "model_lots", "entry", "entry_at",
    "stop", "target", "planned_rr", "exit", "exit_at", "exit_reason", "terminal_status",
    "status", "terminal", "points", "model_r", "mfe", "mae", "gross_model_result",
    "monitoring", "completeness", "gap_count", "source_identities", "policy_identity",
    "policy_version", "policy_checksum",
)
INTRADAY_NUMBERS = frozenset({"entry", "stop", "target", "planned_rr", "exit", "points",
                             "model_r", "mfe", "mae", "gross_model_result"})


def _safe_csv(value):
    # Numeric negatives remain numeric. Text prefixes cannot become formulas.
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
        return "'" + value
    return value


def _intraday_values(item):
    values = json.loads(item.intraday_facts)
    return {key: (Decimal(str(values[key])) if key in INTRADAY_NUMBERS and values[key] is not None
                  else " | ".join(values[key]) if isinstance(values[key], list) else "UNAVAILABLE" if values[key] is None else values[key])
            for key in INTRADAY_FIELDS}


def project_intraday_reports(rows, query, *, governed_current_trading_date=None):
    from kronos.intraday.wo16_reports import POLICY_IDENTITY, POLICY_VERSION, POLICY_CHECKSUM
    from kronos.application.intraday_journal import _instant
    if query.product is not ReportProduct.INTRADAY:
        raise ValueError("INTRADAY_REPORT_PRODUCT_REQUIRED")
    records = []
    for row in rows:
        d = row.data
        future, geometry, metric = d["future"] or {}, d["future_geometry"] or {}, d["metrics"] or {}
        entry, exited, observed = d["entry"] or {}, d["exit"] or {}, d["observation"] or {}
        completion = "UNAVAILABLE" if metric.get("complete") is None else "COMPLETE" if metric["complete"] else "INCOMPLETE"
        values = {key: d.get(key) for key in INTRADAY_FIELDS}
        values.update(record_identity=row.identity, source_lifecycle_identity=observed.get("source_lifecycle_identity"),
            contract=future.get("tradingsymbol") or future.get("trading_symbol"), expiry=future.get("expiry"),
            entry=entry.get("price"), entry_at=entry.get("at"), exit=exited.get("price"), exit_at=exited.get("at"),
            stop=geometry.get("stop"), target=geometry.get("target"),
            **{key: metric.get(key) for key in ("points", "model_r", "mfe", "mae", "gross_model_result")},
            completeness=completion, gap_count=observed.get("gap_count"), policy_identity=POLICY_IDENTITY,
            policy_version=POLICY_VERSION, policy_checksum=POLICY_CHECKSUM)
        relevant = _instant(exited.get("at") or entry.get("at") or d["decision_at"])
        trading_date = date.fromisoformat(d["trading_date"]) if d["trading_date"] else relevant.astimezone(_IST).date()
        family = {"PAPER_POSITION": ReportFamily.PAPER, "PAPER_OBSERVATION": ReportFamily.PAPER_OBSERVATION,
                  "NONE": ReportFamily.NONE, "DO_NOTHING": ReportFamily.DO_NOTHING}[d["truth_class"]]
        if query.view is ReportView.LIVE or (query.view is ReportView.PAPER and family is not ReportFamily.PAPER):
            continue
        if query.view is ReportView.PAPER_OBSERVATIONS and family is not ReportFamily.PAPER_OBSERVATION:
            continue
        if query.from_date and trading_date < query.from_date or query.to_date and trading_date > query.to_date:
            continue
        if query.direction and d["direction"] != query.direction.value:
            continue
        if query.instrument.casefold() not in " ".join(str(values[k] or "") for k in ("opportunity_id", "subject", "contract")).casefold():
            continue
        if query.status and query.status not in {d["status"], d["terminal_status"], d["exit_reason"], d["truth_class"]}:
            continue
        if query.exit_reason and query.exit_reason != d["exit_reason"]:
            continue
        if query.completeness and query.completeness != completion:
            continue
        def number(key):
            return None if values[key] is None else Decimal(str(values[key]))
        records.append(HistoricalReportRecord(row.identity, d["decision_identity"], trading_date, relevant,
            d["subject"], V1Direction(d["direction"]), family, d["status"], number("entry"), number("exit"),
            number("gross_model_result"), number("target"), number("stop"), d["exit_reason"] or "UNAVAILABLE",
            d["terminal_status"] or "UNAVAILABLE", "UNAVAILABLE", "UNAVAILABLE", "UNAVAILABLE",
            d["decision"], POLICY_IDENTITY, POLICY_VERSION, json.dumps(values, sort_keys=True)))
    records = tuple(sorted(records, key=lambda r: (-r.relevant_timestamp.timestamp(), r.record_identity)))
    total = len(records)
    overview = ReportsOverview(total, sum(r.family is ReportFamily.PAPER for r in records), 0,
        sum(r.family is ReportFamily.PAPER_OBSERVATION for r in records),
        sum(json.loads(r.intraday_facts)["terminal"] for r in records), None)
    start = (query.page - 1) * query.page_size
    return HistoricalReportsProjection(query, governed_current_trading_date, records,
        records[start:start + query.page_size], overview, (total + query.page_size - 1) // query.page_size, total)
