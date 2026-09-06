"""Intraday-owned, formula-free current operational snapshot XLSX."""

from __future__ import annotations

from datetime import UTC, datetime
import io
from xml.sax.saxutils import escape as xml_escape
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo
from zoneinfo import ZoneInfo

from kronos.application.intraday_statistics import (
    CANDIDATE_COLUMNS,
    STAGE_COLUMNS,
    SUMMARY_COLUMNS,
    IntradayStatisticsProjection,
)


INTRADAY_STATISTICS_EXPORT_ROUTE = "/reports/export.xlsx"
INTRADAY_XLSX_MIME = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
MAX_INTRADAY_WORKBOOK_BYTES = 8 * 1024 * 1024

_IST = ZoneInfo("Asia/Kolkata")
_SHEETS = ("SUMMARY", "CURRENT CANDIDATES", "STAGE STATUS")
_SUMMARY_WIDTHS = (32, 18, 18, 42, 42, 20, 24, 24)
_CANDIDATE_WIDTHS = (
    18, 30, 16, 12, 22, 42, 46, 24, 28, 42, 20, 42, 44, 24, 20, 44,
    18, 68, 20, 28, 44, 42, 42, 20, 44, 22, 44, 22, 38, 38, 28, 44, 44,
)
_STAGE_WIDTHS = (
    18, 30, 44, 12, 46, 44, 24, 30, 28, 36, 20, 30, 28, 44, 44, 42,
    20, 42, 20, 24, 24, 16,
)


def export_intraday_statistics_xlsx(
    projection: IntradayStatisticsProjection,
) -> bytes:
    """Create deterministic bytes for fixed evidence and generation time."""

    if type(projection) is not IntradayStatisticsProjection:
        raise TypeError("INTRADAY_STATISTICS_EXCEL_PROJECTION_INVALID")
    summary_rows = (
        SUMMARY_COLUMNS,
        *tuple((
            item.metric,
            item.value,
            item.state,
            item.source_identity,
            item.source_schema_identity,
            item.source_schema_version,
            item.analysis_boundary,
            item.generated_at,
        ) for item in projection.metrics),
    )
    candidate_rows = (
        CANDIDATE_COLUMNS,
        *tuple(item.values for item in projection.candidates),
    )
    stage_rows = (
        STAGE_COLUMNS,
        *tuple(item.values for item in projection.stages),
    )

    target = io.BytesIO()
    with ZipFile(target, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        _write(archive, "[Content_Types].xml", _content_types())
        _write(archive, "_rels/.rels", _package_relationships())
        _write(archive, "docProps/app.xml", _app_properties())
        _write(
            archive,
            "docProps/core.xml",
            _core_properties(projection.generated_at),
        )
        _write(archive, "xl/workbook.xml", _workbook())
        _write(archive, "xl/_rels/workbook.xml.rels", _workbook_relationships())
        _write(archive, "xl/styles.xml", _styles())
        for index, (rows, widths) in enumerate((
            (summary_rows, _SUMMARY_WIDTHS),
            (candidate_rows, _CANDIDATE_WIDTHS),
            (stage_rows, _STAGE_WIDTHS),
        ), start=1):
            _write(
                archive,
                f"xl/worksheets/sheet{index}.xml",
                _sheet(rows, widths),
            )
    payload = target.getvalue()
    if len(payload) > MAX_INTRADAY_WORKBOOK_BYTES:
        raise ValueError("INTRADAY_STATISTICS_EXCEL_SIZE_INVALID")
    return payload


def intraday_statistics_filename(generated_at: datetime) -> str:
    if not _aware(generated_at):
        raise ValueError("INTRADAY_STATISTICS_EXCEL_FILENAME_INVALID")
    timestamp = generated_at.astimezone(_IST).strftime("%Y%m%d_%H%M%S")
    return f"KRONOS_INTRADAY_REPORT_{timestamp}_IST.xlsx"


def _write(archive: ZipFile, name: str, value: str) -> None:
    info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    archive.writestr(info, value.encode("utf-8"))


def _sheet(rows: tuple[tuple[object, ...], ...], widths: tuple[int, ...]) -> str:
    maximum = max((len(row) for row in rows), default=1)
    if maximum != len(widths):
        raise ValueError("INTRADAY_STATISTICS_EXCEL_COLUMNS_INVALID")
    xml_rows = []
    for row_number, row in enumerate(rows, start=1):
        if len(row) != maximum:
            raise ValueError("INTRADAY_STATISTICS_EXCEL_COLUMNS_INVALID")
        cells = "".join(
            _cell(_column(column) + str(row_number), value, row_number == 1)
            for column, value in enumerate(row, start=1)
        )
        xml_rows.append(f'<row r="{row_number}">{cells}</row>')
    end = f"{_column(maximum)}{max(1, len(rows))}"
    width_xml = "".join(
        f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
        for index, width in enumerate(widths, start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<dimension ref="A1:{end}"/><sheetViews><sheetView workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        '</sheetView></sheetViews><sheetFormatPr defaultRowHeight="15"/>'
        f'<cols>{width_xml}</cols><sheetData>{"".join(xml_rows)}</sheetData>'
        f'<autoFilter ref="A1:{end}"/></worksheet>'
    )


def _cell(reference: str, value: object, header: bool) -> str:
    style = ' s="1"' if header else ""
    if type(value) is int:
        return f'<c r="{reference}"{style}><v>{value}</v></c>'
    text = _safe_text(_display(value))
    return (
        f'<c r="{reference}" t="inlineStr"{style}><is>'
        f'<t xml:space="preserve">{xml_escape(text)}</t></is></c>'
    )


def _display(value: object) -> str:
    if isinstance(value, datetime):
        if not _aware(value):
            raise ValueError("INTRADAY_STATISTICS_EXCEL_TIMESTAMP_INVALID")
        return value.astimezone(_IST).strftime("%Y-%m-%d %H:%M:%S IST")
    return str(value)


def _safe_text(value: str) -> str:
    return "".join(
        character
        for character in value
        if character in "\t\n\r" or ord(character) >= 32
    )


def _column(index: int) -> str:
    value = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        value = chr(65 + remainder) + value
    return value


def _content_types() -> str:
    sheets = "".join(
        '<Override PartName="/xl/worksheets/sheet'
        f'{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in range(1, 4)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        + sheets
        + '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        '</Types>'
    )


def _package_relationships() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        '</Relationships>'
    )


def _workbook() -> str:
    sheets = "".join(
        f'<sheet name="{name}" sheetId="{index}" r:id="rId{index}"/>'
        for index, name in enumerate(_SHEETS, start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets>{sheets}</sheets><calcPr calcId="0" calcMode="manual"/></workbook>'
    )


def _workbook_relationships() -> str:
    sheets = "".join(
        '<Relationship Id="rId'
        f'{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        f'Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, 4)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + sheets
        + '<Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        '</Relationships>'
    )


def _styles() -> str:
    return (
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


def _core_properties(created: datetime) -> str:
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
        '<dc:title>KRONOS Intraday Current Operational Snapshot</dc:title>'
        '</cp:coreProperties>'
    )


def _app_properties() -> str:
    titles = "".join(f"<vt:lpstr>{name}</vt:lpstr>" for name in _SHEETS)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        '<Application>KRONOS</Application><DocSecurity>0</DocSecurity>'
        '<HeadingPairs><vt:vector size="2" baseType="variant"><vt:variant><vt:lpstr>Worksheets</vt:lpstr></vt:variant>'
        '<vt:variant><vt:i4>3</vt:i4></vt:variant></vt:vector></HeadingPairs>'
        f'<TitlesOfParts><vt:vector size="3" baseType="lpstr">{titles}</vt:vector></TitlesOfParts>'
        '</Properties>'
    )


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


__all__ = [
    "INTRADAY_STATISTICS_EXPORT_ROUTE",
    "INTRADAY_XLSX_MIME",
    "MAX_INTRADAY_WORKBOOK_BYTES",
    "export_intraday_statistics_xlsx",
    "intraday_statistics_filename",
]
