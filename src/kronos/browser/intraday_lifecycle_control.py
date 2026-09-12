"""Sponsor projection only; the application owns all prospective lifecycle facts."""
from html import escape
import json
from uuid import uuid4

LIFECYCLE_ROUTE = "/control/intraday-lifecycle/v1"


class IntradayLifecycleControl:
    def __init__(self, application):
        self.application = application

    def execute_document(self, payload):
        try:
            if type(payload) is not dict:
                raise ValueError("WO11_REQUEST_INVALID")
            if set(payload)=={"handoff_identity","action","action_identity"}:
                result=self.application.action(**payload)
            elif set(payload)=={"claim","action_identity"}:
                result=self.application.close_track(**payload)
            else:
                raise ValueError("WO11_EXACT_ACTION_FIELDS_REQUIRED")
            return dict(outcome="RETAINED",identity=result.identity)
        except (ValueError,TypeError,KeyError,OSError,RuntimeError) as error:
            return dict(outcome="REJECTED",reason=str(error) if isinstance(error,ValueError) and str(error).startswith(("WO11_","LIVE_","NATGAS_")) else "WO11_ACTION_UNAVAILABLE")

    def enrich(self,status):
        tracks={c["comparison_identity"]:c for c in self.application.projection()["cards"]}
        handoffs=self.application.futures.store.records("WO10_SELECTED_TRADE_HANDOFF_V1")
        for card in status["cards"]:
            matches=[h for h in handoffs if h.data["selection"]["comparison_identity"]==card["comparison_identity"]]
            card["lifecycle"] = tracks.get(card["comparison_identity"])
            card["lifecycle_blocker"] = getattr(self.application, "production_blocker", None)
            card["selected_handoff"] = matches[0].identity if len(matches)==1 else None
        return status


def actions_html(card):
    if card.get("lifecycle_blocker"):
        return "<p>PAPER / OBSERVE — currently unavailable.</p>"
    track=card.get("lifecycle")
    if track:
        return f"<section><h3>{escape(track['state'].replace('_',' '))}</h3><p>{escape(track['truth_class'].replace('_',' '))} · 1 LOT</p><a href='/intraday/active'>ACTIVE</a> · <a href='/intraday/closed'>CLOSED</a></section>"
    if not card.get("selected_handoff"):
        return ""
    return (f"<form class='lifecycle-action' data-handoff='{escape(card['selected_handoff'])}' data-action='{uuid4()}'>"
        "<p>Model quantity: exactly 1 lot. Prices are captured from eligible live WebSocket observations.</p>"
        "<button name='action' value='ACTIVATE_PAPER'>ACTIVATE PAPER</button>"
        "<button name='action' value='OBSERVE'>OBSERVE</button><button name='action' value='DO_NOTHING'>DO NOTHING</button>"
        "<p>LIVE — NOT COMMISSIONED</p><output></output></form>")


SCRIPT = """<script>
document.querySelectorAll('.lifecycle-action').forEach(form=>form.addEventListener('submit',async event=>{
 event.preventDefault();const payload=form.dataset.claim?{claim:form.dataset.claim,action_identity:form.dataset.action}:
 {handoff_identity:form.dataset.handoff,action:event.submitter.value,action_identity:form.dataset.action};
 try {const response=await fetch('/control/intraday-lifecycle/v1',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
 const result=await response.json();form.querySelector('output').textContent=result.reason||result.outcome;if(result.outcome==='RETAINED')location.reload();}
 catch(e){form.querySelector('output').textContent='Action result unavailable. Check the retained state before submitting another action.';}
}));</script>"""


def lifecycle_action_label(truth_class):
    return "EXIT PAPER" if truth_class == "PAPER_POSITION" else "STOP OBSERVATION"


def closure_outcome_html(card):
    if card["exit_reason"] is not None:
        return f"<p>EXIT: {escape(card['exit_reason'].replace('_',' '))}</p>"
    if card["terminal_status"] is not None:
        return f"<p>TERMINAL STATUS: {escape(card['terminal_status'].replace('_',' '))}</p>"
    return ""


def render_lifecycle(snapshot,status,*,closed):
    from kronos.browser.intraday_views import _intraday_tabs, _INTRADAY_CSS
    from kronos.browser.views import render_browser_page
    title="CLOSED" if closed else "ACTIVE"
    body=_intraday_tabs(False,active=title.lower())+f"<h2>{title}</h2>"
    for truth,label in (("PAPER_POSITION","PAPER POSITIONS"),("PAPER_OBSERVATION","PAPER OBSERVATIONS — COUNTERFACTUAL")):
        body+=f"<section><h3>{label}</h3>"
        cards=[c for c in status["cards"] if c["truth_class"]==truth and c["terminal"]==closed]
        if not cards:body+="<p>No retained tracks.</p>"
        for c in cards:
            entry="PENDING" if c["entry"] is None else c["entry"]["price"]
            exit_price="UNAVAILABLE" if c["exit"] is None else c["exit"]["price"]
            body+=f"<article><h4>{escape(c['subject'])} · 1 LOT</h4><p>{escape(c['state'].replace('_',' '))}</p><p>Entry {escape(entry)} · Stop {escape(c['stop'])} · Target {escape(c['target'])} · Exit {escape(exit_price)}</p>"
            if closed:
                body+=closure_outcome_html(c)
            m=c["metrics"]
            if m:body+=f"<p>{escape(m['result_label'])}: {escape(str(m['gross_model_result']))} · R {escape(str(m['model_r']))} · MFE {escape(str(m['mfe']))} · MAE {escape(str(m['mae']))} · {escape(m['coverage_label'])}</p>"
            body+=f"<p>Monitoring: {escape(c['monitoring'])}</p>"
            if not closed:body+=f"<form class='lifecycle-action' data-claim='{escape(c['claim'])}' data-action='{uuid4()}'><button>{lifecycle_action_label(truth)}</button><output></output></form>"
            body+="<p>ORIGINAL THESIS INVALIDATION — context only. Post-entry analytical reassessment: NOT COMMISSIONED V1.</p>"
            body+=f"<details><summary>Technical Evidence</summary><pre>{escape(json.dumps(c,indent=2))}</pre></details></article>"
        body+="</section>"
    return render_browser_page(title=f"Intraday — {title}",subtitle="One-lot model lifecycle",snapshot=snapshot,
        active_nav="Intraday",active_tab="",body=body+SCRIPT,extra_styles=_INTRADAY_CSS)
