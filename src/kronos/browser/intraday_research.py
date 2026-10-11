"""Deterministic versioned six/seven-sheet WO-12 workbooks and Sponsor controls."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from html import escape
from io import BytesIO
import json
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape, quoteattr
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from kronos.application.intraday_research import (
    ANALYSIS_COLUMNS, EVENT_COLUMNS, Formula, METADATA_COLUMNS, OPPORTUNITY_COLUMNS,
    QUALITY_COLUMNS, ResearchProjection, TRACK_COLUMNS,
)
from kronos.intraday.wo12_research_contract import SHEETS, WORKBOOK_VERSION, JOURNEY_WORKBOOK_VERSION
from kronos.application.intraday_opportunity_journey import JOURNEY_COLUMNS


RESEARCH_ROUTE = "/intraday/research"
RESEARCH_UPDATE_ROUTE = "/control/intraday/research/update"
RESEARCH_OPEN_ROUTE = "/intraday/research/monthly.xlsx"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_WORKBOOK_BYTES = 16 * 1024 * 1024

def _widths(columns):
    return tuple(46 if "identity" in column else 38 if column == "metric" else
                 28 if column.endswith("_at") else
                 34 if column in {"detail", "inclusion_rule", "reason"} else 22
                 for column in columns)


_SHEET_DEFINITIONS = tuple(
    (name, columns, _widths(columns)) for name, columns in (
        ("Opportunities", OPPORTUNITY_COLUMNS), ("Tracks", TRACK_COLUMNS),
        ("Events", EVENT_COLUMNS), ("Analysis", ANALYSIS_COLUMNS),
        ("Data_Quality", QUALITY_COLUMNS), ("Metadata", METADATA_COLUMNS),
    )
)


def _definitions(projection):
    if projection.workbook_version == WORKBOOK_VERSION:
        if projection.journey:
            raise ValueError("WO12_LEGACY_JOURNEY_NOT_SUPPORTED")
        return _SHEET_DEFINITIONS
    if projection.workbook_version != JOURNEY_WORKBOOK_VERSION:
        raise ValueError("WO12_WORKBOOK_VERSION_UNSUPPORTED")
    widths = tuple(45 if c.endswith('Contract') else 34 if c.endswith(' At') else 46 if 'Identity' in c or 'References' in c
        else 48 if c in {'Original Reasons', 'Chronology Coverage', 'Measurement Authority'}
        else 28 if c == 'Opportunity ID' else 24 for c in JOURNEY_COLUMNS)
    return _SHEET_DEFINITIONS + (("Opportunity_Journey", JOURNEY_COLUMNS, widths),)


def _payloads(projection):
    rows = (projection.opportunities, projection.tracks, projection.events,
        projection.analysis, projection.data_quality, projection.metadata)
    return rows + (projection.journey,) if projection.workbook_version == JOURNEY_WORKBOOK_VERSION else rows


def export_research_workbook(projection: ResearchProjection) -> bytes:
    if type(projection) is not ResearchProjection:
        raise TypeError("WO12_RESEARCH_PROJECTION_REQUIRED")
    definitions = _definitions(projection)
    names = tuple(d[0] for d in definitions)
    payloads = _payloads(projection)
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        _write(archive, "[Content_Types].xml", _content_types(len(names)))
        _write(archive, "_rels/.rels", _package_relationships())
        _write(archive, "docProps/core.xml", _core_properties(projection.generated_at))
        _write(archive, "docProps/app.xml", _app_properties(names))
        _write(archive, "xl/workbook.xml", _workbook(names))
        _write(archive, "xl/_rels/workbook.xml.rels", _workbook_relationships(len(names)))
        _write(archive, "xl/styles.xml", _journey_styles() if len(names) == 7 else _styles())
        for index, ((name, columns, widths), rows) in enumerate(zip(definitions, payloads, strict=True), start=1):
            all_rows = (columns, *rows)
            _write(archive, f"xl/worksheets/sheet{index}.xml", _sheet(all_rows, widths, table_id=index, journey=index == 7))
            _write(archive, f"xl/worksheets/_rels/sheet{index}.xml.rels", _sheet_relationship(index))
            _write(archive, f"xl/tables/table{index}.xml", _table(index, name, columns, len(all_rows)))
    result = output.getvalue()
    if len(result) > MAX_WORKBOOK_BYTES:
        raise ValueError("WO12_RESEARCH_WORKBOOK_SIZE_INVALID")
    _validate_package(result, projection)
    return result


def validate_research_workbook(payload: bytes, projection: ResearchProjection) -> None:
    if type(projection) is not ResearchProjection:
        raise TypeError("WO12_RESEARCH_PROJECTION_REQUIRED")
    _validate_package(payload, projection)


class IntradayResearchControl:
    def __init__(self, application) -> None:
        self.application = application

    def status_document(self):
        return self.application.status_document()

    def update_document(self, payload):
        try:
            if type(payload) is not dict or set(payload) != {"operation_identity"}:
                raise ValueError("WO12_UPDATE_REQUEST_INVALID")
            result = self.application.update(operation_identity=payload["operation_identity"])
            return {"outcome": result.outcome, "receipt_identity": result.receipt_identity,
                    "workbook_path": str(result.workbook_path), "workbook_sha256": result.workbook_sha256,
                    "workbook_bytes": result.workbook_bytes, "projection_identity": result.projection_identity,
                    "idempotent": result.idempotent}
        except (ValueError, TypeError, KeyError, OSError, RuntimeError) as error:
            reason = str(error) if isinstance(error, ValueError) and str(error).startswith("WO12_") else "WO12_RESEARCH_UPDATE_FAILED"
            return {"outcome": "REJECTED", "reason": reason, "idempotent": False}


def render_research(snapshot, status):
    from kronos.browser.intraday_views import _INTRADAY_CSS, _intraday_tabs
    from kronos.browser.views import render_browser_page
    receipt = status["receipt_identity"]
    open_control = (f'<a class="button" href="{RESEARCH_OPEN_ROUTE}?month={escape(status["current_month"])}">OPEN MONTHLY EXCEL</a>'
                    if receipt and status["workbook_verified"] else "<span>Monthly workbook not yet verified.</span>")
    body = (_intraday_tabs(False, active="opportunities") + "<h2>RESEARCH / ANALYSIS DETAILS</h2>"
            "<p>Monthly local research ledger. Research authority only; no trading authority.</p>"
            f"<p>Canonical folder: <code>{escape(status['publication_root'])}</code></p>"
            '<form id="research-update"><button>UPDATE RESEARCH</button><output></output></form>'
            f"<p>{open_control}</p><details><summary>Technical Evidence</summary>"
            f"<pre>{escape(json.dumps(status, indent=2))}</pre></details>" + _SCRIPT)
    return render_browser_page(title="Intraday — Research", subtitle="Local monthly research publication",
                               snapshot=snapshot, active_nav="Intraday", active_tab="", body=body,
                               extra_styles=_INTRADAY_CSS)


_SCRIPT = """<script>
document.getElementById('research-update').addEventListener('submit',async event=>{
 event.preventDefault();const output=event.currentTarget.querySelector('output');
 const operation_identity=crypto.randomUUID();
 try{const response=await fetch('/control/intraday/research/update',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({operation_identity})});
 const result=await response.json();output.textContent=result.reason||result.outcome;if(['PUBLISHED','ALREADY_UP_TO_DATE'].includes(result.outcome))location.reload();}
 catch(error){output.textContent='Research update result unavailable. Check Technical Evidence before retrying.';}
});</script>"""


def _write(archive, name, value):
    info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)); info.compress_type = ZIP_DEFLATED; info.external_attr = 0o600 << 16
    archive.writestr(info, value.encode("utf-8"))


def _sheet(rows, widths, *, table_id, journey=False):
    if not rows or any(len(row) != len(rows[0]) for row in rows) or len(widths) != len(rows[0]):
        raise ValueError("WO12_WORKBOOK_COLUMNS_INVALID")
    xml_rows = []
    for row_index, row in enumerate(rows, 1):
        cells = "".join(_cell(f"{_column(column)}{row_index}", value, header=row_index == 1)
                        for column, value in enumerate(row, 1))
        if journey and row_index == 1:
            cells = cells.replace(' s="1"', ' s="2"')
        height = ' ht="32" customHeight="1"' if journey and row_index == 1 else ""
        xml_rows.append(f'<row r="{row_index}"{height}>{cells}</row>')
    end = f"{_column(len(rows[0]))}{len(rows)}"
    cols = "".join(f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
                   for index, width in enumerate(widths, 1))
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<dimension ref="A1:{end}"/><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
            f'<sheetFormatPr defaultRowHeight="15"/><cols>{cols}</cols><sheetData>{"".join(xml_rows)}</sheetData>'
            f'<autoFilter ref="A1:{end}"/><tableParts count="1"><tablePart r:id="rId1"/></tableParts></worksheet>')


def _cell(reference, value, *, header):
    style = ' s="1"' if header else ""
    if type(value) is Formula:
        formula = xml_escape(value.expression)
        cached = "" if value.cached is None else xml_escape(str(value.cached))
        return f'<c r="{reference}"{style}><f>{formula}</f><v>{cached}</v></c>'
    if value is None:
        return f'<c r="{reference}"{style}/>'
    if type(value) is bool:
        return f'<c r="{reference}" t="b"{style}><v>{1 if value else 0}</v></c>'
    if type(value) in {int, float, Decimal}:
        return f'<c r="{reference}"{style}><v>{value}</v></c>'
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None: raise ValueError("WO12_AWARE_TIMESTAMP_REQUIRED")
        value = value.astimezone(timezone.utc).isoformat()
    safe = "".join(char for char in str(value) if char in "\t\n\r" or ord(char) >= 32)
    return f'<c r="{reference}" t="inlineStr"{style}><is><t xml:space="preserve">{xml_escape(safe)}</t></is></c>'


def _table(index, name, columns, row_count):
    end = f"{_column(len(columns))}{row_count}"
    table_name = "DataQuality" if name == "Data_Quality" else name
    entries = "".join(f'<tableColumn id="{column}" name={quoteattr(title)}/>' for column, title in enumerate(columns, 1))
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<table xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            f'id="{index}" name="{table_name}" displayName="{table_name}" ref="A1:{end}" totalsRowShown="0">'
            f'<autoFilter ref="A1:{end}"/><tableColumns count="{len(columns)}">{entries}</tableColumns>'
            '<tableStyleInfo name="TableStyleMedium2" showFirstColumn="0" showLastColumn="0" showRowStripes="1" showColumnStripes="0"/></table>')


def _sheet_relationship(index):
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/table" Target="../tables/table{index}.xml"/>'
            '</Relationships>')


def _content_types(count=6):
    sheets = "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1, count + 1))
    tables = "".join(f'<Override PartName="/xl/tables/table{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.table+xml"/>' for i in range(1, count + 1))
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>' + sheets + tables +
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
            '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>')


def _package_relationships():
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
            '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>')


def _workbook(names=SHEETS):
    sheets = "".join(f'<sheet name="{name}" sheetId="{index}" r:id="rId{index}"/>' for index, name in enumerate(names, 1))
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheets>{sheets}</sheets><calcPr calcId="191029" calcMode="auto" fullCalcOnLoad="1"/></workbook>')


def _workbook_relationships(count=6):
    sheets = "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1, count + 1))
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + sheets +
            f'<Relationship Id="rId{count + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')


def _styles():
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="2"><font><sz val="10"/><name val="Aptos"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="10"/><name val="Aptos"/></font></fonts>'
            '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF0C4F83"/></patternFill></fill></fills>'
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/></cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')


def _journey_styles():
    # Keep legacy styles byte-identical; only the new header uses added style 2.
    return _styles().replace('<cellXfs count="2">', '<cellXfs count="3">').replace(
        '</cellXfs>', '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment wrapText="1" vertical="center"/></xf></cellXfs>')


def _core_properties(created):
    stamp = created.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            '<dc:creator>KRONOS</dc:creator><cp:lastModifiedBy>KRONOS</cp:lastModifiedBy>'
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{stamp}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">{stamp}</dcterms:modified>'
            '<dc:title>KRONOS Intraday Monthly Research Ledger</dc:title></cp:coreProperties>')


def _app_properties(names=SHEETS):
    titles = "".join(f"<vt:lpstr>{name}</vt:lpstr>" for name in names)
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
            f'<Application>KRONOS</Application><DocSecurity>0</DocSecurity><HeadingPairs><vt:vector size="2" baseType="variant"><vt:variant><vt:lpstr>Worksheets</vt:lpstr></vt:variant><vt:variant><vt:i4>{len(names)}</vt:i4></vt:variant></vt:vector></HeadingPairs>'
            f'<TitlesOfParts><vt:vector size="{len(names)}" baseType="lpstr">{titles}</vt:vector></TitlesOfParts></Properties>')


def _column(index):
    value = ""
    while index:
        index, remainder = divmod(index - 1, 26); value = chr(65 + remainder) + value
    return value


def _validate_package(payload, projection=None):
    definitions = _SHEET_DEFINITIONS if projection is None else _definitions(projection)
    sheet_names = tuple(d[0] for d in definitions)
    with ZipFile(BytesIO(payload)) as archive:
        names = set(archive.namelist())
        required = {"xl/workbook.xml", "xl/styles.xml", *{f"xl/worksheets/sheet{i}.xml" for i in range(1, len(definitions) + 1)}, *{f"xl/tables/table{i}.xml" for i in range(1, len(definitions) + 1)}}
        if not required <= names or any("vbaProject" in name or "externalLinks" in name for name in names):
            raise ValueError("WO12_RESEARCH_WORKBOOK_PACKAGE_INVALID")
        workbook = archive.read("xl/workbook.xml").decode()
        if any(f'name="{name}"' not in workbook for name in sheet_names):
            raise ValueError("WO12_RESEARCH_WORKBOOK_SCHEMA_INVALID")
        if projection is not None:
            rows = _payloads(projection)
            for index, ((name, columns, _), values) in enumerate(zip(definitions, rows, strict=True), 1):
                table = archive.read(f"xl/tables/table{index}.xml").decode()
                end = f"{_column(len(columns))}{len(values) + 1}"
                exact_columns = "".join(
                    f'<tableColumn id="{number}" name={quoteattr(title)}/>'
                    for number, title in enumerate(columns, 1))
                if (f'ref="A1:{end}"' not in table
                        or f'<tableColumns count="{len(columns)}">{exact_columns}</tableColumns>' not in table):
                    raise ValueError("WO12_RESEARCH_WORKBOOK_CONTENT_INVALID")
                sheet = archive.read(f"xl/worksheets/sheet{index}.xml").decode()
                if index != 4 and "<f>" in sheet:
                    raise ValueError("WO12_RESEARCH_WORKBOOK_FORMULA_SCOPE_INVALID")


__all__ = ["IntradayResearchControl", "MAX_WORKBOOK_BYTES", "RESEARCH_OPEN_ROUTE", "RESEARCH_ROUTE", "RESEARCH_UPDATE_ROUTE", "XLSX_MIME", "export_research_workbook", "render_research", "validate_research_workbook"]
