"""Intraday-only Sponsor reporting UI, consuming the WO12 owning projection."""
from datetime import date, datetime
from decimal import Decimal
import re
from zoneinfo import ZoneInfo
from html import escape
from urllib.parse import urlencode
import csv
import io
import json

from kronos.application.intraday_sponsor_reporting import filtered_sheet, summary_document, metric_coverage

SECTIONS = {"OPPORTUNITY_HISTORY": "Opportunity Journey", "PREDICTION_PERFORMANCE": "Prediction Performance",
            "FALSE_ADVANCES": "False Advances", "LIFECYCLE_HISTORY": "Lifecycle History"}


def render_portfolio_context(attention, observations, *, search="", direction=""):
    from kronos.intraday.sponsor_presentation import security_name
    body = '<section><h2>READY — operational attention</h2><p>4/5 opportunities only; attention is not position exposure.</p>'
    if attention is None or attention.ready is None:
        body += '<p>Current attention source unavailable.</p>'
    else:
        rows = tuple(r for r in attention.opportunities if r['status'] == 'Ready'
            and search.casefold() in str(r).casefold() and (not direction or r['direction'] == direction))
        for row in rows:
            monitor = row.get('monitoring') or {}
            body += '<article><h3>' + escape(row['security'] + ' · ' + row['direction']) + '</h3><p>READY · 4/5 · Waiting for: ' + escape(str(row['waiting']))
            body += '</p><p>Monitoring: ' + escape(str(monitor.get('state', 'UNAVAILABLE'))) + ' · ' + escape(str(monitor.get('reason', 'Monitoring authority unavailable'))) + '</p></article>'
        if not rows:
            body += '<p>No matching current READY opportunities.</p>'
    body += '</section><section><h2>Paper Observations — zero exposure</h2><p>Counterfactual, exactly one model lot; not a position.</p>'
    selected = tuple(r for r in observations if search.casefold() in str(r).casefold() and (not direction or r['direction'] == direction))
    for row in selected:
        entry = row['entry'] or {}
        body += '<article><h3>' + escape(security_name(row['subject']) + ' · ' + row['direction']) + '</h3><p>' + escape(str(row['state'])) + ' · Model entry: ' + escape(str(entry.get('price', 'NOT_EVALUABLE'))) + ' · ' + escape(str(entry.get('at', 'NOT_EVALUABLE'))) + '</p><p>Opportunity: ' + escape(row['opportunity_id']) + '</p></article>'
    if not selected:
        body += '<p>No matching active Paper Observations in the validated book.</p>'
    return body + '</section><h2>Entered PAPER positions — model exposure</h2>'


class ReportFilterError(ValueError):
    """Invalid Sponsor input, distinct from missing/unverifiable publication."""


def validate_filters(query):
    try:
        value = lambda key: query.get(key, [''])[0]
        if (any(len(v) != 1 for v in query.values())
                or (value('month') and not re.fullmatch(r'\d{4}_(0[1-9]|1[0-2])', value('month')))
                or value('direction') not in {'', 'LONG', 'SHORT'}
                or value('truth') not in {'', 'PAPER_POSITION', 'PAPER_OBSERVATION'}
                or value('completion') not in {'', 'COMPLETE', 'INCOMPLETE', 'UNAVAILABLE'}):
            raise ValueError
        start = date.fromisoformat(value('from')) if value('from') else None
        end = date.fromisoformat(value('to')) if value('to') else None
        if start and end and start > end:
            raise ValueError
        return dict(search=value('search'), direction=value('direction'), status=value('status'),
            start=start, end=end, truth=value('truth'), completion=value('completion'))
    except (ValueError, TypeError, IndexError) as error:
        raise ReportFilterError('INTRADAY_REPORT_FILTER_INVALID') from error


def report_sheet(application, section, query):
    filters = validate_filters(query)
    month = query.get("month", [""])[0] or application.clock().astimezone(ZoneInfo("Asia/Kolkata")).strftime("%Y_%m")
    # The owning immutable receipt is the boundary; no composition on GET.
    from kronos.browser.intraday_research import read_published_projection
    projection = read_published_projection(application, month)
    if projection.workbook_version == '2.2.0' and section != 'LIFECYCLE_HISTORY':
        raise ValueError('WO12_HISTORICAL_JOURNEY_UNAVAILABLE')
    if section == "LIFECYCLE_HISTORY":
        from kronos.application.intraday_research import EVENT_COLUMNS
        rows = []
        for row in projection.events:
            d = dict(zip(EVENT_COLUMNS, row, strict=True))
            if d["source_schema"] != "WO11_EVENT_V1":
                continue
            if filters['truth'] and d['truth_class'] != filters['truth']:
                continue
            if filters['completion']:
                from kronos.application.intraday_research import TRACK_COLUMNS
                tracks = [dict(zip(TRACK_COLUMNS, t, strict=True)) for t in projection.tracks
                    if t[TRACK_COLUMNS.index('opportunity_identity')] == d['opportunity_identity']
                    and t[TRACK_COLUMNS.index('truth_class')] == d['truth_class']]
                coverage = metric_coverage(tracks)
                if coverage != filters['completion']:
                    continue
            if filters["search"].casefold() not in str(row).casefold() or (filters["status"] and d["state"] != filters["status"]):
                continue
            day = datetime.fromisoformat(str(d["event_at"])).date()
            if (filters["start"] and day < filters["start"]) or (filters["end"] and day > filters["end"]):
                continue
            if filters["direction"]:
                from kronos.application.intraday_research import TRACK_COLUMNS
                tracks = [dict(zip(TRACK_COLUMNS, t, strict=True)) for t in projection.tracks]
                if not any(t["opportunity_identity"] == d["opportunity_identity"] and t["direction"] == filters["direction"] for t in tracks):
                    continue
            rows.append(row)
        sheet = ("Lifecycle History", EVENT_COLUMNS, tuple(rows))
    else:
        sheet = filtered_sheet(projection, SECTIONS[section], **filters)
    return projection, sheet


def render_table(sheet):
    name, columns, rows = sheet
    body = ''.join('<tr>' + ''.join('<td>' + escape('NOT_EVALUABLE' if v is None else str(v)) + '</td>' for v in row) + '</tr>' for row in rows)
    return '<h2>' + escape(name) + '</h2><p>' + str(len(rows)) + ' retained rows</p>' + (
        '<div style="overflow-x:auto"><table><thead><tr>' + ''.join('<th>' + escape(c) + '</th>' for c in columns)
        + '</tr></thead><tbody>' + body + '</tbody></table></div>' if rows else
        '<p>No matching retained evidence. Missing lifecycle coverage is not proof that an event did not occur.</p>')


def navigation(query=None):
    query = query or {}
    values = {k: v[0] for k, v in query.items() if k in {'month', 'from', 'to', 'search', 'direction', 'status', 'truth', 'completion'}}
    return '<nav class="reports-views">' + ''.join('<a class="button" href="/reports?' + escape(urlencode(
        values | dict(product='INTRADAY', section=s))) + '">' + label.replace('_', ' ').title() + '</a>'
        for s, label in SECTIONS.items()) + '</nav>'


def render_unavailable(snapshot):
    from kronos.browser.views import render_browser_page
    return render_browser_page(title='Intraday Reports', subtitle='Monthly research publication unavailable.',
        snapshot=snapshot, active_nav='Reports', active_tab='', body=navigation()
        + '<h2>Monthly research not available</h2><p>A matching verified monthly publication is required. '
        'Missing or unverifiable publication is not an empty research population.</p>'
        '<p><a class="button" href="/intraday/research">Research / explicit UPDATE RESEARCH</a></p>'
        '<p><a class="button" href="/reports?product=INTRADAY">Factual PAPER and Observation history</a></p>')


def render_report(snapshot, application, section, query):
    from kronos.browser.views import render_browser_page
    projection, sheet = report_sheet(application, section, query)
    export_query = {k: v[0] for k, v in query.items()} | dict(product='INTRADAY', section=section)
    controls = '<form method="get"><input type="hidden" name="product" value="INTRADAY"><input type="hidden" name="section" value="' + section + '">'
    for name, label, kind in [('month', 'Month (YYYY_MM)', 'text'), ('search', 'Security / opportunity', 'text'),
        ('direction', 'Direction', 'text'), ('status', 'Status / outcome', 'text'),
        ('truth', 'PAPER_POSITION / PAPER_OBSERVATION', 'text'), ('completion', 'Metric coverage: COMPLETE / INCOMPLETE / UNAVAILABLE', 'text'),
        ('from', 'From', 'date'), ('to', 'To', 'date')]:
        value = query.get(name, [projection.year_month if name == 'month' else ''])[0]
        controls += '<label>' + label + '<input type="' + kind + '" name="' + name + '" value="' + escape(value) + '"></label>'
    controls += '<button>Apply</button></form>'
    exports = ''.join('<a class="button" href="/reports/export.' + suffix + '?' + escape(urlencode(export_query)) + '">' + suffix.upper() + '</a>' for suffix in ('csv', 'json', 'xlsx'))
    body = '<a class="button" href="/reports?product=INTRADAY">Overview / PAPER / Observations</a>' + navigation(query) + controls + exports
    body += '<p>Retained monthly evidence · ' + escape(projection.year_month.replace('_', '-')) + '. Historical progression is not current eligibility.</p>'
    body += '<p>MATCHED means terminal direction relative to original Assessment Price, not profitability. PAPER and counterfactual Observation remain separate.</p>'
    body += render_table(sheet) + '<details><summary>Technical evidence</summary>' + escape(projection.projection_identity) + '</details>'
    return render_browser_page(title='Intraday Reports', subtitle='Opportunities, model lifecycle and directional research.',
        snapshot=snapshot, active_nav='Reports', active_tab='', body=body)


def export_sheet(sheet, suffix):
    name, columns, rows = sheet
    if suffix == 'json':
        return json.dumps(dict(sheet=name, authority='WO12_READ_ONLY_PROJECTION', columns=columns,
            rows=rows, missing='NOT_EVALUABLE'), default=str).encode()
    if suffix == 'csv':
        output = io.StringIO(); writer = csv.writer(output)
        def safe(v):
            text = 'NOT_EVALUABLE' if v is None else str(v)
            return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) and not isinstance(v, (int, float, Decimal)) else text
        writer.writerow(columns); writer.writerows(tuple(safe(v) for v in row) for row in rows)
        return output.getvalue().encode()
    from kronos.browser.intraday_research import _write, _content_types, _package_relationships, _core_properties, _app_properties, _workbook, _workbook_relationships, _styles, _sheet, _sheet_relationship, _table
    from zipfile import ZipFile, ZIP_DEFLATED
    output = io.BytesIO()
    with ZipFile(output, 'w', compression=ZIP_DEFLATED) as archive:
        for path, value in (('[Content_Types].xml', _content_types(1)), ('_rels/.rels', _package_relationships()),
            ('docProps/core.xml', _core_properties(datetime.now().astimezone())), ('docProps/app.xml', _app_properties((name,))),
            ('xl/workbook.xml', _workbook((name,))), ('xl/_rels/workbook.xml.rels', _workbook_relationships(1)),
            ('xl/styles.xml', _styles()), ('xl/worksheets/sheet1.xml', _sheet((columns, *rows), (28,)*len(columns), table_id=1)),
            ('xl/worksheets/_rels/sheet1.xml.rels', _sheet_relationship(1)), ('xl/tables/table1.xml', _table(1, name, columns, len(rows)+1))):
            _write(archive, path, value)
    return output.getvalue()
