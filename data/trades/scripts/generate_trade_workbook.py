#!/usr/bin/env python3
"""Validate KRONOS trade CSV files and rebuild the generated workbook.

CSV files are the source of truth. The XLSX workbook is generated review output.
This script intentionally uses only the Python standard library so the trade
database can be rebuilt on a clean machine.
"""

from __future__ import annotations

import argparse
import csv
import posixpath
import re
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence
from xml.sax.saxutils import escape


SCHEMA_VERSION = "1.0"
REPO_ROOT = Path(__file__).resolve().parents[3]
TRADE_DIR = REPO_ROOT / "data" / "trades"
WORKBOOK_PATH = TRADE_DIR / "KRONOS_TRADE_LEDGER.xlsx"
SCREENSHOT_ROOTS = [
    "assets/validation/entries/",
    "assets/validation/exits/",
    "assets/validation/observations/",
]

FIXED_ZIP_TIME = (2000, 1, 1, 0, 0, 0)


TRADE_HEADERS = [
    "schema_version",
    "trade_id",
    "trade_source",
    "status",
    "trade_date",
    "instrument",
    "market",
    "timeframe",
    "direction",
    "setup_type",
    "entry_price",
    "stop_loss",
    "target_price",
    "exit_price",
    "risk_points",
    "reward_points",
    "planned_r_multiple",
    "actual_r_multiple",
    "result",
    "source_observation_id",
    "primary_screenshot_id",
    "review_id",
    "screenshot_path",
    "ev_kr300_trend_stage",
    "ev_kr310_trend_quality",
    "ev_kr315_compression",
    "ev_kr320_acceptance",
    "ev_kr330_momentum",
    "ev_kr335_price_action",
    "ev_kr340_review_readiness",
    "ev_kr345_relative_intelligence",
    "confidence_snapshot",
    "notes",
    "created_at",
    "updated_at",
]

OBSERVATION_HEADERS = [
    "schema_version",
    "observation_id",
    "observation_date",
    "instrument",
    "market",
    "timeframe",
    "observation_type",
    "observation_source",
    "linked_trade_id",
    "primary_screenshot_id",
    "screenshot_path",
    "ev_kr300_trend_stage",
    "ev_kr310_trend_quality",
    "ev_kr315_compression",
    "ev_kr320_acceptance",
    "ev_kr330_momentum",
    "ev_kr335_price_action",
    "ev_kr340_review_readiness",
    "ev_kr345_relative_intelligence",
    "summary",
    "action_required",
    "created_at",
    "updated_at",
]

SCREENSHOT_HEADERS = [
    "schema_version",
    "screenshot_id",
    "capture_date",
    "instrument",
    "market",
    "timeframe",
    "screenshot_path",
    "linked_observation_id",
    "linked_trade_id",
    "source_chart_layout",
    "notes",
    "created_at",
]

DAILY_REVIEW_HEADERS = [
    "schema_version",
    "review_id",
    "review_date",
    "market_session",
    "instruments_reviewed",
    "observations_created",
    "trades_created",
    "open_trades_reviewed",
    "closed_trades_reviewed",
    "key_lessons",
    "follow_up_required",
    "created_at",
    "updated_at",
]


@dataclass(frozen=True)
class CsvSpec:
    filename: str
    sheet_name: str
    headers: Sequence[str]


CSV_SPECS = [
    CsvSpec("KRONOS_TRADE_LEDGER.csv", "Trade Ledger", TRADE_HEADERS),
    CsvSpec("KRONOS_OBSERVATION_LEDGER.csv", "Observations", OBSERVATION_HEADERS),
    CsvSpec("KRONOS_SCREENSHOT_INDEX.csv", "Screenshots", SCREENSHOT_HEADERS),
    CsvSpec("KRONOS_DAILY_REVIEW.csv", "Daily Review", DAILY_REVIEW_HEADERS),
]

ID_PATTERNS = {
    "trade_id": re.compile(r"^KR-TRD-\d{8}-\d{3}$"),
    "linked_trade_id": re.compile(r"^KR-TRD-\d{8}-\d{3}$"),
    "observation_id": re.compile(r"^KR-OBS-\d{8}-\d{3}$"),
    "source_observation_id": re.compile(r"^KR-OBS-\d{8}-\d{3}$"),
    "linked_observation_id": re.compile(r"^KR-OBS-\d{8}-\d{3}$"),
    "screenshot_id": re.compile(r"^KR-SCR-\d{8}-\d{3}$"),
    "primary_screenshot_id": re.compile(r"^KR-SCR-\d{8}-\d{3}$"),
    "review_id": re.compile(r"^KR-REV-\d{8}$"),
}

SHEET_ORDER = [
    "Dashboard",
    "Trade Ledger",
    "Open Trades",
    "Closed Trades",
    "Daily Review",
    "Observations",
    "Screenshots",
    "Lists",
    "Instructions",
]


class ValidationError(Exception):
    """Raised when the trade database fails validation."""


def read_csv_spec(spec: CsvSpec) -> List[Dict[str, str]]:
    path = TRADE_DIR / spec.filename
    if not path.exists():
        raise ValidationError(f"Missing required CSV: {path}")

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        actual_headers = reader.fieldnames or []
        if list(actual_headers) != list(spec.headers):
            raise ValidationError(
                f"{spec.filename} headers do not match the required schema.\n"
                f"Expected: {', '.join(spec.headers)}\n"
                f"Actual:   {', '.join(actual_headers)}"
            )
        return [normalize_row(row, spec.headers) for row in reader]


def normalize_row(row: Dict[str, str], headers: Sequence[str]) -> Dict[str, str]:
    return {header: (row.get(header) or "").strip() for header in headers}


def validate_schema_versions(filename: str, rows: Sequence[Dict[str, str]]) -> None:
    for index, row in enumerate(rows, start=2):
        value = row.get("schema_version", "")
        if value and value != SCHEMA_VERSION:
            raise ValidationError(
                f"{filename} row {index}: schema_version must be {SCHEMA_VERSION!r}, got {value!r}"
            )


def validate_ids(filename: str, rows: Sequence[Dict[str, str]]) -> None:
    for index, row in enumerate(rows, start=2):
        for field, pattern in ID_PATTERNS.items():
            if field not in row:
                continue
            value = row.get(field, "")
            if value and not pattern.fullmatch(value):
                raise ValidationError(
                    f"{filename} row {index}: {field} has invalid ID {value!r}"
                )


def validate_duplicate_ids(filename: str, rows: Sequence[Dict[str, str]]) -> None:
    seen: Dict[str, int] = {}
    primary_id_fields = ("trade_id", "observation_id", "screenshot_id", "review_id")
    for index, row in enumerate(rows, start=2):
        for field in primary_id_fields:
            if field not in row:
                continue
            value = row.get(field, "")
            if not value:
                continue
            duplicate_key = f"{field}:{value}"
            if duplicate_key in seen:
                raise ValidationError(
                    f"{filename} row {index}: duplicate {field} {value!r}; first seen on row {seen[duplicate_key]}"
                )
            seen[duplicate_key] = index


def validate_screenshot_paths(filename: str, rows: Sequence[Dict[str, str]]) -> None:
    for index, row in enumerate(rows, start=2):
        value = row.get("screenshot_path", "")
        if not value:
            continue
        if Path(value).is_absolute():
            raise ValidationError(
                f"{filename} row {index}: screenshot_path must be repository-relative"
            )
        normalized = posixpath.normpath(value).replace("\\", "/")
        if normalized.startswith("../") or normalized == "..":
            raise ValidationError(
                f"{filename} row {index}: screenshot_path must not escape the repository"
            )
        if not any(normalized.startswith(root) for root in SCREENSHOT_ROOTS):
            raise ValidationError(
                f"{filename} row {index}: screenshot_path must begin with one of: {', '.join(SCREENSHOT_ROOTS)}"
            )


def validate_database(csv_data: Dict[str, List[Dict[str, str]]]) -> None:
    for spec in CSV_SPECS:
        rows = csv_data[spec.sheet_name]
        validate_schema_versions(spec.filename, rows)
        validate_ids(spec.filename, rows)
        validate_duplicate_ids(spec.filename, rows)
        validate_screenshot_paths(spec.filename, rows)


def rows_to_table(headers: Sequence[str], rows: Sequence[Dict[str, str]]) -> List[List[str]]:
    return [list(headers)] + [[row.get(header, "") for header in headers] for row in rows]


def build_dashboard(csv_data: Dict[str, List[Dict[str, str]]]) -> List[List[str]]:
    trades = csv_data["Trade Ledger"]
    observations = csv_data["Observations"]
    screenshots = csv_data["Screenshots"]
    reviews = csv_data["Daily Review"]
    open_trades = filter_trades(trades, {"open", "active"})
    closed_trades = filter_trades(trades, {"closed"})

    return [
        ["Metric", "Value"],
        ["Total Trades", str(len(trades))],
        ["Open Trades", str(len(open_trades))],
        ["Closed Trades", str(len(closed_trades))],
        ["Observations", str(len(observations))],
        ["Screenshots", str(len(screenshots))],
        ["Daily Reviews", str(len(reviews))],
        ["CSV Source Of Truth", "Yes"],
        ["Workbook Generated From CSV", "Yes"],
    ]


def filter_trades(trades: Sequence[Dict[str, str]], statuses: Iterable[str]) -> List[Dict[str, str]]:
    allowed = {status.lower() for status in statuses}
    return [trade for trade in trades if trade.get("status", "").lower() in allowed]


def build_lists() -> List[List[str]]:
    return [
        ["List", "Allowed / Suggested Values"],
        ["schema_version", SCHEMA_VERSION],
        ["trade status", "planned, open, active, closed, cancelled"],
        ["direction", "long, short"],
        ["result", "win, loss, breakeven, cancelled"],
        ["market", "MCX, NSE"],
        ["timeframe", "D, 240, 60"],
        ["trade_source", "ChatGPT Screenshot Review, Weekly Review, Manual Backtest, Approved Research Note"],
        ["screenshot roots", ", ".join(SCREENSHOT_ROOTS)],
    ]


def build_instructions() -> List[List[str]]:
    return [
        ["Instruction", "Details"],
        ["Source of truth", "Edit CSV files, not this workbook."],
        ["No fictional trades", "Only approved paper trades may be recorded."],
        ["No trading decisions", "Codex records approved data only."],
        ["Screenshot paths", f"Use repository-relative paths under: {', '.join(SCREENSHOT_ROOTS)}."],
        ["Regenerate workbook", "Run: python3 data/trades/scripts/generate_trade_workbook.py"],
        ["Validate only", "Run: python3 data/trades/scripts/generate_trade_workbook.py --check"],
        ["Generated workbook", "This XLSX is disposable review output rebuilt from CSV files."],
    ]


def build_workbook_tables(csv_data: Dict[str, List[Dict[str, str]]]) -> Dict[str, List[List[str]]]:
    trades = csv_data["Trade Ledger"]
    open_trades = filter_trades(trades, {"open", "active"})
    closed_trades = filter_trades(trades, {"closed"})

    return {
        "Dashboard": build_dashboard(csv_data),
        "Trade Ledger": rows_to_table(TRADE_HEADERS, trades),
        "Open Trades": rows_to_table(TRADE_HEADERS, open_trades),
        "Closed Trades": rows_to_table(TRADE_HEADERS, closed_trades),
        "Daily Review": rows_to_table(DAILY_REVIEW_HEADERS, csv_data["Daily Review"]),
        "Observations": rows_to_table(OBSERVATION_HEADERS, csv_data["Observations"]),
        "Screenshots": rows_to_table(SCREENSHOT_HEADERS, csv_data["Screenshots"]),
        "Lists": build_lists(),
        "Instructions": build_instructions(),
    }


def column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def cell_xml(row_index: int, col_index: int, value: str, header: bool) -> str:
    ref = f"{column_name(col_index)}{row_index}"
    style = ' s="1"' if header else ""
    safe = escape(value or "")
    return f'<c r="{ref}"{style} t="inlineStr"><is><t>{safe}</t></is></c>'


def sheet_xml(rows: Sequence[Sequence[str]]) -> str:
    max_cols = max((len(row) for row in rows), default=1)
    max_rows = max(len(rows), 1)
    last_cell = f"{column_name(max_cols)}{max_rows}"

    cols = "".join(
        f'<col min="{index}" max="{index}" width="18" customWidth="1"/>'
        for index in range(1, max_cols + 1)
    )
    row_xml = []
    for row_index, row in enumerate(rows, start=1):
        cells = "".join(
            cell_xml(row_index, col_index, str(value), row_index == 1)
            for col_index, value in enumerate(row, start=1)
        )
        row_xml.append(f'<row r="{row_index}">{cells}</row>')

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheetViews><sheetView workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        '</sheetView></sheetViews>'
        f'<cols>{cols}</cols>'
        f'<sheetData>{"".join(row_xml)}</sheetData>'
        f'<autoFilter ref="A1:{last_cell}"/>'
        '</worksheet>'
    )


def workbook_xml(sheet_names: Sequence[str]) -> str:
    sheets = "".join(
        f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, name in enumerate(sheet_names, start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets>{sheets}</sheets>'
        '</workbook>'
    )


def workbook_rels_xml(sheet_count: int) -> str:
    rels = []
    for index in range(1, sheet_count + 1):
        rels.append(
            f'<Relationship Id="rId{index}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{index}.xml"/>'
        )
    rels.append(
        f'<Relationship Id="rId{sheet_count + 1}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'{"".join(rels)}'
        '</Relationships>'
    )


def content_types_xml(sheet_count: int) -> str:
    sheet_overrides = "".join(
        '<Override '
        f'PartName="/xl/worksheets/sheet{index}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in range(1, sheet_count + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '<Override PartName="/docProps/core.xml" '
        'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        f'{sheet_overrides}'
        '</Types>'
    )


def styles_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="2">'
        '<font><sz val="11"/><color theme="1"/><name val="Calibri"/></font>'
        '<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>'
        '</fonts>'
        '<fills count="3">'
        '<fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FF1F4E78"/><bgColor indexed="64"/></patternFill></fill>'
        '</fills>'
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="2">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>'
        '</cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        '</styleSheet>'
    )


def root_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        '<Relationship Id="rId2" '
        'Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" '
        'Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" '
        'Target="docProps/app.xml"/>'
        '</Relationships>'
    )


def core_props_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<dc:title>KRONOS Trade Ledger</dc:title>'
        '<dc:creator>Project KRONOS</dc:creator>'
        '<cp:lastModifiedBy>Project KRONOS</cp:lastModifiedBy>'
        '<dcterms:created xsi:type="dcterms:W3CDTF">2000-01-01T00:00:00Z</dcterms:created>'
        '<dcterms:modified xsi:type="dcterms:W3CDTF">2000-01-01T00:00:00Z</dcterms:modified>'
        '</cp:coreProperties>'
    )


def app_props_xml(sheet_names: Sequence[str]) -> str:
    titles = "".join(f'<vt:lpstr>{escape(name)}</vt:lpstr>' for name in sheet_names)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        '<Application>Project KRONOS</Application>'
        '<DocSecurity>0</DocSecurity>'
        '<ScaleCrop>false</ScaleCrop>'
        '<TitlesOfParts>'
        f'<vt:vector size="{len(sheet_names)}" baseType="lpstr">{titles}</vt:vector>'
        '</TitlesOfParts>'
        '<Company>Project KRONOS</Company>'
        '</Properties>'
    )


def write_zip_member(zf: zipfile.ZipFile, name: str, content: str) -> None:
    info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    zf.writestr(info, content.encode("utf-8"))


def write_workbook(tables: Dict[str, List[List[str]]]) -> None:
    sheet_names = SHEET_ORDER
    WORKBOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(WORKBOOK_PATH, "w") as zf:
        write_zip_member(zf, "[Content_Types].xml", content_types_xml(len(sheet_names)))
        write_zip_member(zf, "_rels/.rels", root_rels_xml())
        write_zip_member(zf, "docProps/core.xml", core_props_xml())
        write_zip_member(zf, "docProps/app.xml", app_props_xml(sheet_names))
        write_zip_member(zf, "xl/workbook.xml", workbook_xml(sheet_names))
        write_zip_member(zf, "xl/_rels/workbook.xml.rels", workbook_rels_xml(len(sheet_names)))
        write_zip_member(zf, "xl/styles.xml", styles_xml())
        for index, sheet_name in enumerate(sheet_names, start=1):
            write_zip_member(zf, f"xl/worksheets/sheet{index}.xml", sheet_xml(tables[sheet_name]))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate KRONOS trade CSV files and rebuild the generated workbook."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate CSV files without rebuilding the workbook.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        csv_data = {spec.sheet_name: read_csv_spec(spec) for spec in CSV_SPECS}
        validate_database(csv_data)
        if not args.check:
            write_workbook(build_workbook_tables(csv_data))
    except ValidationError as exc:
        print(f"Validation error: {exc}", file=sys.stderr)
        return 1

    if args.check:
        print("Validation passed: trade CSV files are valid.")
    else:
        print(f"Workbook rebuilt: {WORKBOOK_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
