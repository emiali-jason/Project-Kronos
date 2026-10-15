"""Theta-owned summary, drill-down and bounded manual chart/Answer actions."""

import base64
import binascii
from datetime import date
from html import escape
from http import HTTPStatus
import json
from urllib.parse import parse_qs, urlencode
from zoneinfo import ZoneInfo

from kronos.browser.product_routes import BrowserRouteResponse
from kronos.browser.views import render_browser_page
from kronos.browser.theta_charts import CHART_STYLES, chart_controls
from kronos.browser.theta_theme import THEME_STYLES, OUTLOOK_STYLES, commodity_symbol
from kronos.browser.theta_detail import DETAIL_STYLES, render_detail
from kronos.theta.contracts import SUBJECTS, ThetaError, keys, parse, require, stamp
from kronos.theta.workflow import CHART_ROLES, ThetaWorkflow


EXPLANATIONS = {
    "THETA_TARGET_AND_METHODOLOGY_NOT_ESTABLISHED": "Charts are retained. Exact E1/E2 option targets, exchange-defined futures/settlement mapping and applicable methodology must be supplied through the commissioned owner boundary before Question generation. No targets have been guessed.",
    "THETA_QUESTION_SUPERSEDED": "This Question is no longer selected for every requested commodity. Generate/use the current Question; the old evidence is not overwritten.",
    "THETA_ANSWER_INCOMPLETE": "The Answer must include both E1 and E2 for every requested commodity. No partial pack was published.",
    "THETA_ANSWER_CONFLICT": "Different bytes already exist for this Question. The original accepted Answer remains immutable.",
    "THETA_ANSWER_EXPIRED": "The option expiry has passed. This late Answer cannot become a prospective forecast.",
    "THETA_INTEGRITY_INVALID": "Retained evidence failed its integrity checks. No older forecast is substituted.",
    "THETA_LOCAL_FILE_UNAVAILABLE": "The exact expected local Answer file is missing or unsafe. Check the displayed filename and intake directory. Symlinks are not accepted.",
    "THETA_CHART_BINDING_STALE": "The selected chart/cycle changed. Refresh and verify the intended role before retrying. No older evidence is substituted.",
    "THETA_MACRO_REQUIRED": "The shared Global Macro composite is required for this Question Pack. It remains supporting evidence, not a forecast subject.",
    "THETA_CHART_REQUIRED": "The selected commodity chart is missing or has no qualified revision. No Question was created for it.",
    "THETA_IMMUTABLE_CONFLICT": "A conflicting output already exists. It was not overwritten and the new Question was not selected.",
    "THETA_SYNTHETIC_AUTHORITY_FORBIDDEN": "Synthetic targets cannot commission a genuine Question Pack.",
    "THETA_SPONSOR_OPERATION_BUSY": "A Theta workflow action is already running. Its retained result will remain authoritative; refresh before retrying.",
    "THETA_SPONSOR_INPUT_STATE_STALE": "The chart or Macro state changed after this page was loaded. Refresh and verify the six cards before creating a pack.",
    "THETA_SPONSOR_BATCH_STALE": "The displayed Question batch is no longer current. No Answer was imported or assessed.",
    "THETA_SPONSOR_WORKFLOW_UNAVAILABLE": "The governed V3 Question, intake and assessment composition is not available in this runtime.",
}

STYLES = """
.theta-panel{border:1px solid var(--line);border-radius:10px;padding:18px;margin:14px 0;background:var(--panel)}
.theta-summary{width:100%;border-collapse:collapse}.theta-summary th,.theta-summary td{padding:12px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
.theta-muted{color:var(--muted);font-size:12px}.theta-detail p{white-space:pre-wrap;overflow-wrap:anywhere}.theta-original{max-width:100%;height:auto}
.theta-form{display:flex;gap:10px;flex-wrap:wrap;align-items:end}.theta-form label{display:grid;gap:6px;font-size:12px}.theta-form input,.theta-form select{max-width:100%;padding:8px}
.theta-id{font-family:monospace;overflow-wrap:anywhere;font-size:11px}.theta-range{display:block;white-space:nowrap;font-size:23px;font-weight:800;letter-spacing:-.02em}.theta-actions{display:flex;gap:12px;flex-wrap:wrap;margin:10px 0}
.theta-tabs{padding:0;margin-bottom:20px}.theta-tabs a{min-width:130px;text-align:center;font-weight:800}.theta-confidence{font-size:17px;color:var(--green);margin:5px 0}.theta-expiry{display:block;color:var(--muted);font-size:12px;margin-top:8px}
.theta-summary th{font-size:11px;color:var(--muted);font-weight:700}.theta-summary td{padding:18px 8px}.theta-subject{font-size:16px;font-weight:800;color:var(--blue)}.theta-current{font-size:11px;color:var(--green)}
.theta-empty{text-align:center;padding:52px 20px}.theta-empty h2{font-size:20px}.theta-start{display:inline-block;padding:12px 18px;background:#0c3554;border:1px solid #285c81;border-radius:7px;margin-top:12px;font-weight:800}
.theta-sandbox{font-size:11px;color:#f6d997;margin:0 0 18px;border-left:3px solid #8c7333;padding:7px 10px}.theta-notice{font-size:12px}.theta-pack-controls summary{cursor:pointer;font-weight:700}
.theta-workflow-actions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:18px 0}.theta-workflow-actions form{margin:0}.theta-workflow-actions button{width:100%;min-height:48px}.theta-operation-table{width:100%;border-collapse:collapse;font-size:12px}.theta-operation-table th,.theta-operation-table td{padding:9px 7px;border-bottom:1px solid var(--line);text-align:left}.theta-operation-result{border-top:1px solid var(--line);padding-top:12px;margin-top:14px}.theta-operation-result h3{margin:0 0 8px}.theta-reason{max-width:320px;overflow-wrap:anywhere}
@media(max-width:900px){.theta-summary{font-size:11px}.theta-summary th,.theta-summary td{padding:7px 4px}.theta-range{white-space:normal;font-size:20px}}
@media(max-width:700px){.theta-workflow-actions{grid-template-columns:1fr}.theta-operation-table{font-size:10px}}
"""


def e(value):
    return escape(str(value), quote=True)


def link(path, **query):
    return e(path + "?" + urlencode(query))


class ThetaBrowserRoutes:
    def __init__(self, workflow=None, sponsor_workflow=None):
        self.workflow = ThetaWorkflow() if workflow is None else workflow
        if sponsor_workflow is not None:
            require(getattr(sponsor_workflow, "workflow", None) is self.workflow,
                    "THETA_SPONSOR_WORKFLOW_CONFIGURATION_INVALID")
        self.sponsor_workflow = sponsor_workflow

    def owns_post(self, path):
        return path in {"/theta-earners/chart", "/theta-earners/question", "/theta-earners/import"}

    def _page(self, snapshot_provider, body, *, detail=False, view="OUTLOOK", outlook=False):
        navigation = '<nav class="tabs theta-tabs" aria-label="Theta views">' + ''.join(
            f'<a class="{"active" if name == view else ""}"'
            + (' aria-current="page"' if name == view else '')
            + f' href="{path}">{name}</a>'
            for name, path in (("OUTLOOK", "/theta-earners"), ("NEW ANALYSIS", "/theta-earners/new-analysis"))) + '</nav>'
        return BrowserRouteResponse(render_browser_page(
            title="Theta Earners" if not detail else "Theta Earners — Retained Analysis",
            subtitle="External Chart Analyst evidence · Exact E1/E2 expiry ranges · No trading authority",
            snapshot=snapshot_provider(), active_nav="Theta Earners", active_tab="",
            body='<div class="theta-theme">' + navigation + body + '</div>',
            extra_styles=STYLES + (CHART_STYLES if view == "NEW ANALYSIS" else "") + THEME_STYLES + (DETAIL_STYLES if detail else "") + (OUTLOOK_STYLES if outlook else ""),
            back_link='<a href="/theta-earners">← BACK TO OUTLOOK</a>' if detail else ""))

    def _summary(self, snapshot_provider, notice=""):
        if self.sponsor_workflow is not None:
            return self._v3_outlook(snapshot_provider)
        unavailable = False
        try:
            rows = self.workflow.summary()
        except (OSError, ValueError, KeyError, TypeError):
            unavailable = True
            rows = []
        current = [r for r in rows if r["status"] == "ACCEPTED_EXTERNAL_EVIDENCE" and len(r["forecasts"]) == 2]
        if not current:
            body = '<section class="theta-panel theta-empty"><h2>NO CURRENT THETA ANALYSIS AVAILABLE</h2>'
            if unavailable:
                body += '<p class="theta-muted">Current analysis could not be verified.</p>'
            body += '<a class="theta-start" href="/theta-earners/new-analysis">START NEW ANALYSIS</a></section>'
        else:
            body = '<section class="theta-panel" data-theta-forecast><h2>Current outlook</h2><table class="theta-summary"><thead><tr><th>Commodity</th><th>E1 · NEXT OPTION EXPIRY</th><th>E2 · SECOND-NEXT OPTION EXPIRY</th><th>Analysis</th></tr></thead><tbody>'
            by_subject = {row["subject"]: row for row in current}
            for subject in SUBJECTS:
                row = by_subject.get(subject)
                if row is None:
                    body += f'<tr><td class="theta-subject">{subject}</td><td colspan="3" class="theta-muted">No current forecast</td></tr>'
                    continue
                name = f'<a class="theta-subject" href="{link("/theta-earners/detail", question=row["question_id"], subject=subject)}">{commodity_symbol(subject)}<span>{subject}</span><span class="theta-drill-arrow" aria-hidden="true">→</span></a>'
                cells = ''
                for horizon in ("E1", "E2"):
                    forecast = next(f for f in row["forecasts"] if f["target"]["horizon"] == horizon)
                    exact_date = forecast["target"]["option_expiry"]
                    calendar_date = date.fromisoformat(exact_date)
                    cells += (f'<td><strong class="theta-range">{e(forecast["lower"])} – {e(forecast["upper"])}</strong>'
                        f'<div class="theta-confidence">Confidence: {e(forecast["confidence_pct"])}%</div>'
                        f'<time class="theta-expiry" datetime="{calendar_date.isoformat()}" title="{e(exact_date)}">{calendar_date.strftime("%d %b %Y")}</time></td>')
                exact_time = row["analyzed_at"]
                local_time = stamp(exact_time).astimezone(ZoneInfo("Asia/Kolkata"))
                body += (f'<tr><td>{name}</td>{cells}<td><span class="theta-current">Current</span><br>'
                    f'<time class="theta-muted" datetime="{e(exact_time)}" title="{e(exact_time)}">{local_time.strftime("%d %b %Y")}<br>{local_time.strftime("%I:%M %p")} IST</time></td></tr>')
            body += '</tbody></table><p class="theta-muted">External Analyst’s terminal range-containment confidence; not a calibrated KRONOS, profitability or no-touch probability.</p></section>'
        return self._page(snapshot_provider, body)

    def _v3_outlook(self, snapshot_provider):
        try:
            rows = self.sponsor_workflow.outlook()
        except (OSError, KeyError, TypeError, ValueError):
            rows = [{"subject": s, "evidence": None, "currentness": "UNAVAILABLE",
                     "reason": "EVIDENCE_UNVERIFIABLE"} for s in SUBJECTS]
        body = ''
        if self.workflow.qualification_mode or any(
                r["evidence"] and r["evidence"]["question"]["synthetic"] for r in rows):
            body += '<p class="theta-sandbox">SYNTHETIC — NOT FOR GENUINE FORECASTING</p>'
        if not any(r["evidence"] for r in rows):
            body += ('<section class="theta-panel theta-empty"><h2>NO CURRENT THETA ANALYSIS AVAILABLE</h2>'
                     '<a class="theta-start" href="/theta-earners/new-analysis">START NEW ANALYSIS</a></section>')
        body += ('<section class="theta-panel theta-outlook"><h2>Current outlook</h2>'
                 '<p class="theta-muted">ASTRA FORECAST · exact accepted E1 / E2 ranges</p>'
                 '<table class="theta-summary"><thead><tr><th>Commodity</th>'
                 '<th>E1 · NEXT OPTION EXPIRY</th><th>E2 · SECOND-NEXT OPTION EXPIRY</th>'
                 '<th>Analysis</th></tr></thead><tbody>')
        reasons = {"NO_CURRENT_ACCEPTED_ANSWER": "No current accepted Answer",
                   "NO_ACCEPTED_ANSWER": "Awaiting accepted Answer",
                   "QUESTION_STALE": "Chart, target or authority binding is stale",
                   "ANSWER_STALE": "Accepted evidence is stale",
                   "QUESTION_SUPERSEDED": "Question superseded",
                   "ANSWER_SUPERSEDED": "Accepted evidence superseded",
                   "QUESTION_HISTORICAL": "Historical Question only",
                   "ANSWER_HISTORICAL": "Historical accepted evidence only",
                   "THETA_V3_RANGE": "Answer rejected: range or confidence failed validation",
                   "EVIDENCE_UNVERIFIABLE": "Retained evidence could not be verified"}
        for row in rows:
            subject, evidence = row["subject"], row["evidence"]
            mark = commodity_symbol(subject) + f'<span>{subject}</span>'
            if evidence is None:
                body += (f'<tr data-theta-subject="{subject}"><td><span class="theta-subject theta-outlook-subject">{mark}</span></td>'
                         '<td colspan="2" class="theta-muted">CURRENT FORECAST UNAVAILABLE<br>'
                         f'{e(reasons.get(row["reason"], "Answer unavailable · " + row["reason"]))}</td>'
                         f'<td class="theta-muted">Question: {e(row["currentness"])}</td></tr>')
                continue
            answer, question = evidence["answer"], evidence["question"]
            detail_url = link("/theta-earners/detail", question=question["question_id"], subject=subject)
            name = (f'<a class="theta-subject" href="{detail_url}">'
                    + mark + '<span class="theta-drill-arrow" aria-hidden="true">→</span></a>')
            cells = ''
            for horizon in ("E1", "E2"):
                forecast = answer["forecasts"][horizon]
                exact_date = question["targets"][horizon]["option_expiry"]
                expiry = date.fromisoformat(exact_date)
                assessment = row["assessment"]
                state = "NOT_EVALUABLE" if assessment is None else assessment["horizons"][horizon]["result"]
                cells += (f'<td data-theta-horizon="{horizon}"><strong class="theta-range">{e(forecast["lower"])} – {e(forecast["upper"])}</strong>'
                          f'<div class="theta-confidence">Confidence: {e(forecast["confidence_pct"])}%</div>'
                          f'<time class="theta-expiry" datetime="{e(exact_date)}" title="{e(exact_date)}">{expiry.strftime("%d %b %Y")}</time>'
                          '<div class="theta-documentary">'
                          f'<strong class="theta-assessment-badge" data-state="{e(state)}" aria-label="KRONOS documentary assessment: {e(state)}">{e(state)}</strong>'
                          + ('<small>Retained assessment unavailable</small>' if assessment is None else '') + '</div></td>')
            exact_time = answer["analyzed_at"]
            local = stamp(exact_time).astimezone(ZoneInfo("Asia/Kolkata"))
            body += (f'<tr data-theta-subject="{subject}"><td>{name}</td>{cells}<td class="theta-analysis">'
                     '<span class="theta-outlook-state">ACCEPTED · CURRENT</span><br>'
                     f'<time class="theta-muted" datetime="{e(exact_time)}" title="{e(exact_time)}">{local.strftime("%d %b %Y")}<br>{local.strftime("%I:%M %p")} IST</time>'
                     f'<a class="theta-view-details" href="{detail_url}" aria-label="View Details for {subject}">View Details →</a></td></tr>')
        body += ('</tbody></table><p class="theta-muted theta-outlook-explanation">Confidence is Astra’s stated terminal-range-containment confidence. '
                 'It is not KRONOS calibrated probability, profitability probability, OTM probability, no-touch probability or trade probability.</p>'
                 '<p class="theta-muted">DOCUMENTED / LIMITED / NOT_EVALUABLE describe the retained KRONOS DOCUMENTARY ASSESSMENT. '
                 'LIMITED means documentary limitation. NOT_EVALUABLE means the governed assessment could not be established. '
                 'Neither alters Astra’s accepted range or confidence.</p></section>')
        return self._page(snapshot_provider, body, outlook=True)

    def _operation_panel(self, status):
        available = status is not None
        selected = None if status is None else status["selected_question_pack"]
        input_state = "" if status is None else status["input_state_sha256"]
        current_batch = selected is not None and selected["current"]
        batch_id = "" if selected is None else selected["batch_id"]
        body = ('<section class="theta-panel" data-theta-manual><h2>Question Pack and Astra Answer</h2>'
                '<p class="theta-muted">One pack commissions five independently bound Questions. '
                'One import consumes the exact combined Answer file. Nothing runs merely because a file appears.</p>'
                '<div class="theta-workflow-actions">'
                '<form method="post" action="/theta-earners/question" data-theta-workflow-form>'
                f'<input type="hidden" name="input_state_sha256" value="{e(input_state)}">'
                f'<button class="theta-workflow-primary" type="submit"{"" if available else " disabled"}>'
                'CREATE THETA QUESTION PACK</button></form>'
                '<form method="post" action="/theta-earners/import" data-theta-workflow-form>'
                f'<input type="hidden" name="question_batch_id" value="{e(batch_id)}">'
                f'<button class="theta-workflow-primary" type="submit"{"" if current_batch else " disabled"}>'
                'IMPORT ASTRA ANSWERS</button></form></div>')
        if not available:
            body += ('<p class="theta-muted">QUESTION PACK: NOT CREATED · ASTRA ANSWER: AWAITING</p>'
                     '<p class="theta-muted">V3 WORKFLOW: NOT ENROLLED IN THIS RUNTIME</p></section>')
            return body
        question_operation = status["question_operation"]
        if question_operation is None:
            body += '<p class="theta-muted">QUESTION PACK: NOT CREATED</p>'
        else:
            result = question_operation["result"]
            state = "QUESTION PACK READY" if selected and selected["current"] and selected["batch_id"] == result["batch_id"] else "QUESTION INPUTS CHANGED — HISTORICAL PACK RETAINED"
            body += (f'<div class="theta-operation-result"><h3>{e(state)} · 5 / 5</h3>'
                     f'<p class="theta-id">Batch: {e(result["batch_id"])}</p>'
                     f'<p>{e(result["filename"])}</p><div class="theta-actions">'
                     f'<a href="{link("/theta-earners/question-pack", question=result["batch_id"], kind="zip")}">OPEN QUESTION PACK</a>'
                     '</div></div>')
        imported = status["import_operation"]
        if imported is None:
            body += '<p class="theta-muted">ANSWER ACCEPTANCE: AWAITING · ASSESSMENT STATUS: AWAITING</p>'
        else:
            result = imported["result"]
            intake, assessments = result["intake"], result["assessments"]
            accepted = sum(row["receipt_id"] is not None for row in intake["children"].values())
            body += (f'<div class="theta-operation-result"><h3>PACKAGE = {e(intake["package_status"])} · {accepted} / 5</h3>'
                     '<table class="theta-operation-table"><thead><tr><th>Commodity</th><th>Answer acceptance</th>'
                     '<th>Currentness</th><th>E1 assessment</th><th>E2 assessment</th><th>Reason</th></tr></thead><tbody>')
            for subject in SUBJECTS:
                child, assessed = intake["children"][subject], assessments[subject]
                body += (f'<tr><td>{e(subject)}</td><td>{e(child["status"])}</td>'
                         f'<td>{e(child["currentness"])}</td>'
                         f'<td>{e("NOT ASSESSED" if assessed is None else assessed["E1"])}</td>'
                         f'<td>{e("NOT ASSESSED" if assessed is None else assessed["E2"])}</td>'
                         f'<td class="theta-reason">{e(child["reason"] or (None if assessed is None else assessed["reason"]) or "—")}</td></tr>')
            body += ('</tbody></table><p class="theta-muted">DOCUMENTED / LIMITED / NOT_EVALUABLE are documentary states, '
                     'not forecast acceptance, market direction or trading signals.</p></div>')
        return body + '</section>' + self._workflow_script()

    @staticmethod
    def _workflow_script():
        return r'''<script>(()=>{for(const form of document.querySelectorAll('[data-theta-workflow-form]'))form.addEventListener('submit',()=>{for(const button of document.querySelectorAll('.theta-workflow-primary')){button.disabled=true;button.setAttribute('aria-busy','true');}});})();</script>'''

    def _analysis(self, snapshot_provider, notice="", generation=None):
        try:
            workspace = self.workflow.chart_workspace()
            rows = self.workflow.summary()
        except (OSError, ValueError, KeyError, TypeError):
            workspace = None
            rows = [{"subject": s, "status": "INTEGRITY_INVALID / NOT_EVALUABLE",
                     "forecasts": []} for s in SUBJECTS]
        body = ''
        if notice:
            body += '<p class="theta-notice" role="status">' + e(notice) + '</p>'
        try:
            status = None if self.sponsor_workflow is None else self.sponsor_workflow.restore_status()
        except (OSError, ValueError, KeyError, TypeError):
            status = None
            body += '<p class="theta-notice" role="alert">Retained V3 workflow status could not be verified. No action has run.</p>'
        body += (chart_controls(workspace, rows, status) if workspace is not None else
                 '<section class="theta-panel" role="alert">CHART EVIDENCE INVALID / UNAVAILABLE. No fallback chart or upload binding is supplied.</section>')
        if generation:
            for subject, state in generation["states"].items():
                if state["status"] == "READY":
                    body += (f'<p class="theta-notice">{e(subject)}: QUESTION PACK READY · '
                             f'<a href="{link("/theta-earners/question-pack", question=state["question_id"], kind="zip")}">'
                             'OPEN QUESTION PACK</a></p>')
                else:
                    message = EXPLANATIONS.get(state["failure"],
                        "Question generation blocked; no authority was guessed and no failed pack was selected.")
                    body += f'<p class="theta-notice">{e(subject)}: {e(message)}</p>'
        body += self._operation_panel(status)
        return self._page(snapshot_provider, body, view="NEW ANALYSIS")

    def handle_get(self, request, snapshot_provider):
        if request.path not in {"/theta-earners", "/theta-earners/new-analysis", "/theta-earners/detail", "/theta-earners/question-pack", "/theta-earners/answer", "/theta-earners/chart-preview", "/theta-earners/detail-chart"}:
            return None
        try:
            if request.path == "/theta-earners":
                require(not request.query)
                return self._summary(snapshot_provider)
            if request.path == "/theta-earners/new-analysis":
                require(not request.query)
                return self._analysis(snapshot_provider)
            if request.path == "/theta-earners/detail-chart":
                require(self.sponsor_workflow is not None
                        and set(request.query) == {"question", "subject", "role"}
                        and all(len(v) == 1 for v in request.query.values()))
                media_type, original = self.sponsor_workflow.detail_chart(
                    request.query["question"][0], request.query["subject"][0], request.query["role"][0])
                return BrowserRouteResponse(original, content_type=media_type)
            if request.path.endswith("/chart-preview"):
                require(set(request.query) == {"subject", "cycle", "revision"}
                        and all(len(v) == 1 for v in request.query.values()))
                media_type, binary = self.workflow.preview_chart(
                    subject=request.query["subject"][0], cycle_id=request.query["cycle"][0],
                    revision_id=request.query["revision"][0])
                return BrowserRouteResponse(binary, content_type=media_type)
            allowed = {"question", "subject"} if request.path.endswith("/detail") else {"question", "kind"} if request.path.endswith("/question-pack") else {"question"}
            require(set(request.query) == allowed and all(len(v) == 1 for v in request.query.values()))
            identity = request.query["question"][0]
            if request.path.endswith("/question-pack"):
                kind = request.query["kind"][0]
                if identity.startswith("TEB-"):
                    require(self.sponsor_workflow is not None and kind == "zip",
                            "THETA_SPONSOR_WORKFLOW_UNAVAILABLE")
                    filename, payload = self.sponsor_workflow.question_pack(identity)
                    return BrowserRouteResponse(payload, content_type="application/zip",
                                                filename=filename)
                payload = self.workflow.transport(identity, kind)
                return BrowserRouteResponse(payload, content_type={"pdf":"application/pdf","zip":"application/zip","template":"application/json"}[kind],
                                            filename=None if kind=='pdf' else self.workflow.transport_filename(identity,kind))
            if (identity.startswith("TEQ-") and self.sponsor_workflow is not None
                    and self.sponsor_workflow.intake._optional("questions", identity + ".json") is not None):
                if request.path.endswith("/answer"):
                    q = self.sponsor_workflow.intake._get("questions", identity + ".json")
                    evidence = self.sponsor_workflow.retained_answer(identity, q["binding"]["subject"])
                    return BrowserRouteResponse(evidence["raw"], content_type="application/json",
                                                filename=identity + "_ANSWERS.json")
                evidence = self.sponsor_workflow.detail(identity, request.query["subject"][0])
                return self._page(snapshot_provider, self._v3_detail_body(evidence), detail=True)
            detail = self.workflow.detail(identity)
            if request.path.endswith("/answer"):
                raw = self.workflow.chart_bytes(detail["receipt"]["answer_sha256"])
                return BrowserRouteResponse(raw, content_type="application/json", filename=identity + "_ANSWERS.json")
            subject = request.query["subject"][0]
            require(subject in detail["question"]["subjects"])
            return self._page(snapshot_provider, self._detail_body(detail, subject), detail=True)
        except (OSError, ValueError, KeyError, TypeError, StopIteration):
            return BrowserRouteResponse("Theta evidence unavailable or invalid; no fallback forecast is shown.", HTTPStatus.CONFLICT, "text/plain; charset=utf-8")

    def _v3_detail_body(self, evidence):
        """Pure TE-07 rendering; accepted bytes/assessment are already restored."""
        return render_detail(evidence)

    def _detail_body(self, detail, subject):
        question, answer, receipt = detail["question"], detail["answer"], detail["receipt"]
        # Only the authorized temporal correction: historical V1 wording stays exact.
        analysis_label = "Analysis completed" if question.get("schema_version") == "2.0.0" else "Analysis T0"
        state = "SELECTED PROSPECTIVE EVIDENCE" if subject in detail["current_subjects"] else "HISTORICAL ONLY / NOT CURRENT"
        body = f'<section class="theta-panel theta-detail"><h2>{commodity_symbol(subject)}{e(subject)} · {state}</h2><p>The following is retained external Analyst evidence, not a second KRONOS opinion. Classification labels are Analyst assertions; KRONOS verifies structure and byte integrity, not research truth or authorship.</p><p>Analyst: {e(answer["analyst"]["identity"])} · Model: {e(answer["analyst"]["model"])}</p><p>Provenance: {e(answer["analyst"]["provenance"])}</p><p>{analysis_label}: {e(answer["analyzed_at"])}<br>Information cutoff: {e(answer["information_cutoff"])}</p><p class="theta-id">Question: {e(question["question_id"])}<br>Answer: {e(answer["answer_id"])}<br>Original bytes SHA-256: {e(receipt["answer_sha256"])}<br>Accepted: {e(receipt["accepted_at"])}</p><a href="{link("/theta-earners/answer", question=question["question_id"])}">Download exact original Answer</a></section>'
        for forecast in answer["forecasts"]:
            if forecast["target"]["subject"] != subject:
                continue
            outcome = "NOT_YET_EXERCISED" if self.workflow.now() < stamp(forecast["target"]["expires_at"]) else "NOT_EVALUABLE"
            body += f'<section class="theta-panel theta-detail"><h2>{e(forecast["target"]["horizon"])} · {e(forecast["target"]["option_expiry"])}</h2><h3>Range: {e(forecast["lower"])} – {e(forecast["upper"])} · Confidence: {e(forecast["confidence_pct"])}%</h3><p>Analyst-stated terminal containment confidence only. Calibration: NOT_ESTABLISHED. Terminal outcome: {outcome} / no outcome evaluated on this page.</p>'
            for key, value in forecast["target"].items():
                body += f'<p class="theta-id">{e(key)}: {e(value)}</p>'
            for name, statement in forecast["analysis"].items():
                body += f'<h3>{e(name.replace("_", " "))} · {e(statement["classification"])}</h3><p>{e(statement["text"])}</p>'
            body += '<h3>Sources</h3>'
            for source in forecast["sources"]:
                availability = ' · Available: ' + e(source['available_at']) if question.get('schema_version') == '2.0.0' else ''
                body += f'<p><a href="{e(source["url"])}" rel="noopener noreferrer">{e(source["title"])}</a><br>{e(source["evidence"])}<br>Published: {e(source["published_at"] or "NOT_ESTABLISHED")}{availability} · Accessed: {e(source["accessed_at"])}</p>'
            body += '</section>'
        chart = next(c for c in question["charts"] if c["subject"] == subject)
        binary = self.workflow.chart_bytes(chart["sha256"])
        body += f'<section class="theta-panel"><h2>Exact original supplied chart</h2><p>Sponsor-declared label: {e(chart["label"])} · Cutoff: {e(chart["information_cutoff"])}</p><p class="theta-id">{e(chart["sha256"])}</p><img class="theta-original" alt="Original Sponsor-supplied chart" src="data:{e(chart["media_type"])};base64,{base64.b64encode(binary).decode("ascii")}"></section>'
        return body

    def handle_post(self, request, snapshot_provider):
        if not self.owns_post(request.path):
            return None
        try:
            if request.path.endswith("/chart"):
                if request.content_type in {"image/png", "image/jpeg"}:
                    require(set(request.query) == {"subject", "cycle", "revision"}
                            and all(len(v) == 1 for v in request.query.values()))
                    subject = request.query["subject"][0]
                    require(subject in CHART_ROLES)
                    identity = self.workflow.intake_chart(subject=subject,
                        label="Sponsor card-attested TradingView composite — " + subject,
                        media_type=request.content_type, information_cutoff=self.workflow.now().isoformat(),
                        payload=request.body, expected_cycle_id=request.query["cycle"][0],
                        expected_revision_id=None if request.query["revision"][0] == "MISSING" else request.query["revision"][0],
                        cutoff_basis="INTAKE_RECEIPT_NOT_CHART_TIME")
                else:
                    require(not request.query and request.content_type == "application/json"
                            and len(request.body) <= 24 * 1024 * 1024)
                    # Preserve the existing declared-cutoff intake contract.
                    value = parse(request.body, maximum=24 * 1024 * 1024)
                    keys(value, {"subject", "label", "information_cutoff", "media_type", "chart_base64"})
                    binary = base64.b64decode(value.pop("chart_base64"), validate=True)
                    subject = value["subject"]
                    identity = self.workflow.intake_chart(**value, payload=binary)
                card = next(c for c in self.workflow.chart_workspace()["cards"] if c["subject"] == subject)
                require(card["chart_id"] == identity, "THETA_CHART_BINDING_STALE")
                return BrowserRouteResponse(json.dumps({"outcome": "CHART_RECEIVED", "chart_id": identity,
                    "revision_id": card["revision_id"], "cycle_id": card["cycle_id"],
                    "sha256": card["chart"]["sha256"]}), content_type="application/json")
            require(not request.query)
            require(request.content_type == "application/x-www-form-urlencoded" and len(request.body) <= 4096)
            value = parse_qs(request.body.decode("utf-8"), strict_parsing=True)
            if request.path.endswith("/question"):
                if self.sponsor_workflow is not None:
                    require(set(value) == {"input_state_sha256"}
                            and len(value["input_state_sha256"]) == 1)
                    operation = self.sponsor_workflow.create_question_pack(
                        value["input_state_sha256"][0])
                    require(operation["result"]["complete"] is True)
                    return BrowserRouteResponse("", HTTPStatus.SEE_OTHER,
                        location="/theta-earners/new-analysis")
                require(set(value) == {"subject"})
                generation = self.workflow.commission_questions(tuple(value["subject"]))
                count = sum(v['status']=='READY' for v in generation['states'].values())
                notice = f"Question generation: {count} / {len(generation['states'])} requested commodities ready. Independent identities retained."
                response = self._analysis(snapshot_provider,notice,generation)
                return BrowserRouteResponse(response.body,HTTPStatus.OK if count else HTTPStatus.CONFLICT)
            else:
                if self.sponsor_workflow is not None:
                    require(set(value) == {"question_batch_id"}
                            and len(value["question_batch_id"]) == 1)
                    operation = self.sponsor_workflow.import_astra_answers(
                        value["question_batch_id"][0])
                    intake = operation["result"]["intake"]
                    accepted = sum(row["receipt_id"] is not None
                                   for row in intake["children"].values())
                    notice = (f'ASTRA ANSWER PACKAGE {intake["package_status"]} · '
                              f'{accepted} / 5 accepted. Assessment remains separate.')
                    if accepted:
                        return BrowserRouteResponse("", HTTPStatus.SEE_OTHER,
                            location="/theta-earners/new-analysis")
                    response = self._analysis(snapshot_provider, notice)
                    return BrowserRouteResponse(response.body, HTTPStatus.CONFLICT)
                require(set(value) == {"question"} and len(value["question"]) == 1)
                self.workflow.import_answer(value["question"][0])
                notice = "Exact external Answer accepted; both horizons retained without analytical changes."
            return self._analysis(snapshot_provider, notice)
        except (OSError, ValueError, KeyError, TypeError, binascii.Error):
            import sys
            error = sys.exception()
            code = str(error) if type(error) is ThetaError else "THETA_LOCAL_FILE_UNAVAILABLE" if isinstance(error, OSError) else "THETA_REQUEST_REJECTED"
            notice = EXPLANATIONS.get(code, "The request failed validation. No evidence was accepted or replaced.")
            if request.path.endswith("/chart"):
                return BrowserRouteResponse(json.dumps({"failure": code}), HTTPStatus.CONFLICT, "application/json")
            response = self._analysis(snapshot_provider, notice)
            return BrowserRouteResponse(response.body, HTTPStatus.CONFLICT)
