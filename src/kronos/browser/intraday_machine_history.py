"""Limited historical GET navigation; never current work or producer authority."""
from html import escape
from http import HTTPStatus
import json
import re
from urllib.parse import urlencode

from kronos.application.intraday_machine_history import MachineHistoryError, RUN
from kronos.browser.product_routes import BrowserRouteResponse

MACHINE_HISTORY_ROUTE = '/intraday/review/machine-history'


def _link(values, label):
    return '<a href="' + escape(MACHINE_HISTORY_ROUTE + '?' + urlencode(values), quote=True) + '">' + escape(label) + '</a>'


def _page_query(query):
    allowed = {'run', 'page', 'page_size', 'population', 'assessment', 'readiness'}
    if (type(query) is not dict or set(query) - allowed
            or any(type(v) is not list or len(v) != 1 or type(v[0]) is not str
                   or not 1 <= len(v[0]) <= 160 for v in query.values())):
        raise MachineHistoryError('MACHINE_HISTORY_QUERY_INVALID', 400)
    values = {k: v[0] for k, v in query.items()}
    for k, default in [('page', '1'), ('page_size', '25')]:
        v = values.get(k, default)
        if re.fullmatch(r'[1-9][0-9]?', v) is None:
            raise MachineHistoryError('MACHINE_HISTORY_PAGE_INVALID', 400)
        values[k] = int(v)
    return values


def history_response(reader, query, snapshot_provider):
    if reader is None:
        return BrowserRouteResponse('Machine assessment history is not configured. Historical evidence has not been changed.',
            status=HTTPStatus.SERVICE_UNAVAILABLE, content_type='text/plain; charset=utf-8')
    try:
        document = reader.page(**_page_query(query))
    except MachineHistoryError as error:
        if error.reason == 'MACHINE_HISTORY_POPULATION_CHANGED':
            run = query.get('run', [None])[0]
            if type(run) is str and RUN.fullmatch(run):
                # Only the exact validated run survives; no stale page/token.
                from kronos.browser.views import render_browser_page
                body = ('<section><h2>Historical population changed</h2>'
                    '<p>Historical evidence only — no authority for new work.</p>'
                    '<p>MACHINE_HISTORY_POPULATION_CHANGED. No evidence was repaired. '
                    'No automatic reload or retry occurred.</p>'
                    + _link({'run': run}, 'Reload selected run explicitly') + '</section>')
                return BrowserRouteResponse(render_browser_page(
                    title='Intraday — Historical selection conflict',
                    subtitle='Historical only · explicit reload required',
                    snapshot=snapshot_provider(), active_nav='Intraday',
                    active_tab='Review', body=body), status=HTTPStatus.CONFLICT)
        return BrowserRouteResponse('Historical evidence unavailable · ' + error.reason
            + '. Reload explicitly; no pointer or evidence was repaired.',
            status=HTTPStatus(error.status), content_type='text/plain; charset=utf-8')
    return BrowserRouteResponse(render_machine_history(snapshot_provider(), document),
        status=HTTPStatus(document['readiness_http_status']))


def render_machine_history(snapshot, document):
    from kronos.browser.views import render_browser_page
    from kronos.browser.intraday_views import _status_time, _INTRADAY_CSS
    from kronos.browser.intraday_wo08 import _duration_text, HISTORY_ROUTE
    body = ('<section class="machine-history"><h2>Machine Assessment History</h2>'
        '<p><strong>Historical evidence — no authority for new work.</strong></p>'
        '<p>Recent-five Analysis navigation and exact selected-run evidence only. '
        'This is not a complete historical READY/NOW catalogue.</p>'
        '<p><a href="/intraday/review">Current Review — separate eligibility</a> · '
        '<a href="' + HISTORY_ROUTE + '">Existing visual history</a></p><h3>Recent retained Analysis attempts</h3>')
    recent = document['recent']
    if recent['unavailable']:
        body += '<p>Recent Analysis navigation unavailable · ' + escape(recent['unavailable']) + '. No empty history is inferred.</p>'
    elif not recent['entries']:
        body += '<p>No attempts in the existing prepared recent-five selection.</p>'
    body += '<ol>'
    for row in recent['entries']:
        run = row.get('run_identity')
        label = (_status_time(row.get('boundary') or row.get('completed_at')) + ' · '
                 + str(row.get('result') or 'Result unavailable') + ' · '
                 + _duration_text(row.get('duration_microseconds')))
        body += '<li>' + escape(label)
        body += (' · ' + _link({'run': run}, 'View complete selected-run assessments')
                 if type(run) is str and RUN.fullmatch(run) else ' · No retained resulting run linked')
        body += '</li>'
    body += '</ol>'
    if document['run_identity'] is not None:
        run, page, size, total = (document[k] for k in ('run_identity', 'page', 'page_size', 'total'))
        body += '<h3>Selected retained run</h3><p>' + escape(run) + '</p>'
        body += '<p>Original Analysis boundary: ' + escape(_status_time(document['rows'][0]['analysis_boundary'])) + '</p>'
        if document['selected_outside_recent_five']:
            body += '<p>Exact selection is outside the current recent-five window, or that window is unavailable. It is not a newly discovered historical catalogue entry.</p>'
        body += ('<p>Complete validated assessment population: ' + str(total)
            + '. Page ' + str(page) + ' · displaying ' + str((page-1)*size+1) + '–'
            + str(min(page*size, total)) + '. Original manifest member order; no ranking.</p>')
        body += ('<form method="get" action="' + MACHINE_HISTORY_ROUTE + '">'
            '<input type="hidden" name="run" value="' + escape(run, quote=True) + '">'
            '<label for="history-page-size">Rows per page</label><select id="history-page-size" name="page_size">'
            + ''.join('<option value="' + str(n) + '"' + (' selected' if size == n else '') + '>'
                + str(n) + '</option>' for n in sorted({25, 50, size}))
            + '</select><button type="submit">Reload with selected page size</button></form>')
        base = dict(run=run, page_size=size, population=document['population'])
        body += '<nav aria-label="Historical assessment pages">'
        if page > 1:
            body += _link(dict(base, page=page-1), 'Previous page') + ' · '
        if page*size < total:
            body += _link(dict(base, page=page+1), 'Next page') + ' · '
        body += _link(dict(run=run), 'Reload selected run explicitly') + '</nav>'
        body += ('<div class="history-table" role="region" aria-label="Historical assessment table" tabindex="0"><table><caption>Selected-run historical assessments</caption>'
            '<thead><tr><th>Security / exact contract</th><th>Original direction</th>'
            '<th>Original assessment</th><th>Assessment Price</th><th>Original readiness evidence</th></tr></thead><tbody>')
        for row in document['rows']:
            body += ('<tr><td>' + escape(str(row['subject'])) + '<br>'
                + escape(str(row.get('exact_mcx_contract_identity') or '')) + '</td><td>'
                + escape(str(row['direction'] or 'Unavailable')) + '</td><td>'
                + escape(str(row['disposition'])) + '</td><td>'
                + escape(row['assessment_price'] or 'Assessment Price not retained')
                + '</td><td>Original readiness not linked</td></tr><tr><td colspan="5"><details><summary>Retained evidence · '
                + escape(str(row['subject'])) + '</summary><pre>'
                + escape(json.dumps(row, indent=2, default=str)) + '</pre>')
            # This GET form supplies a known retained identity; no discovery/derivation.
            body += '<form method="get" action="' + MACHINE_HISTORY_ROUTE + '">'
            for key, value in dict(base, page=page, assessment=row['identity']).items():
                body += '<input type="hidden" name="' + key + '" value="' + escape(str(value), quote=True) + '">'
            label = 'history-readiness-' + row['identity']
            body += ('<label for="' + label + '">Known exact retained readiness identity</label>'
                '<input id="' + label + '" name="readiness" required maxlength="160" autocomplete="off">'
                '<button type="submit">Read exact historical readiness</button></form>'
                '<p>Notification/delivery and historical monitoring evidence are not linked in this limited view.</p></details></td></tr>')
        body += '</tbody></table></div>'
        if document['readiness_detail'] is not None:
            detail = document['readiness_detail']
            body += '<h3>Exact historical readiness evidence</h3><p>' + escape(detail['state']) + '</p>'
            body += ('<p>Original CURRENT, criteria/counts and first-five, if retained, describe this exact historical record only. '
                'They do not establish present eligibility, handoff, publication, notification delivery or monitoring.</p>'
                '<p>Missing exact evidence is not reconstructed. Required proof not established means absent or unequal proof; no readiness values are exposed in either case.</p><pre>'
                + escape(json.dumps(detail, indent=2, default=str)) + '</pre>')
    body += '</section>'
    return render_browser_page(title='Intraday — Machine Assessment History',
        subtitle='Dated retained evidence · historical only · no new-work authority',
        snapshot=snapshot, active_nav='Intraday', active_tab='Review', body=body,
        extra_styles=_INTRADAY_CSS + '.machine-history{min-width:0;overflow-wrap:anywhere}'
        '.machine-history :focus-visible{outline:2px solid #59c7ff;outline-offset:3px}'
        '.machine-history pre{white-space:pre-wrap;overflow-wrap:anywhere}'
        '.machine-history .history-table{overflow-x:auto}.machine-history table{width:100%;min-width:720px}'
        '.machine-history th,.machine-history td{padding:8px;text-align:left;vertical-align:top}'
        '.machine-history input{max-width:100%;box-sizing:border-box}')
