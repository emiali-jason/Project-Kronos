"""Projection and explicit Sponsor choice; Browser owns no numerical policy."""
from html import escape
from uuid import uuid4

from kronos.intraday.wo10_futures_contract import normalize

CONSTRUCTION_CONTROL_ROUTE = "/control/intraday-futures/construction"

RISK_PREVIEW_ROUTE = "/control/intraday-futures/risk-preview"

FUTURES_ROUTE = "/intraday/futures"
FUTURES_CONTROL_ROUTE = "/control/intraday-futures/selection"


class IntradayFuturesControl:
    def __init__(self, application, session_source, lifecycle_control=None):
        self.application = application
        self.session_source = session_source
        self.lifecycle_control = lifecycle_control

    def status_document(self):
        cards = []
        for comparison in self.application.restore():
            c = comparison.data
            if self.application.store.current(c["subject"]) != comparison:
                continue
            now = self.application.clock()
            state = self.application.decision_state(comparison, now=now, session=self.session_source(c["subject"], now))
            if state == "SUPERSEDED":
                continue
            records = {name: self.application.store.load(c[name + "_identity"]).data
                       for name in ("plan", "snapshot", "expression", "risk_fact", "advisory")}
            records["advisory"] = self.application.preview_risk(comparison.identity).data
            # Provider tokens belong to retained evidence, never Sponsor projection.
            records = _redact(records)
            cards.append(dict(comparison_identity=comparison.identity, subject=c["subject"], direction=c["direction"],
                              state=state, action_identity=str(uuid4()), records=records,
                              option_buy=c["option_buy"], option_sell=c["option_sell"]))
        # Current WO-09 remains the population authority, including when structure
        # has never been selected. GET performs no construction or persistence.
        from kronos.intraday.wo09_readiness import CurrentnessState, ReadinessState, HardGate
        represented = {c["subject"] for c in cards}
        unavailable = self.application.store.records("WO10_CONSTRUCTION_UNAVAILABLE_V1")
        for pointer, readiness in self.application.wo09.restore_current():
            if (pointer.currentness is not CurrentnessState.CURRENT or readiness.currentness is not CurrentnessState.CURRENT
                    or readiness.satisfied_count != 5 or readiness.outstanding_count != 0 or readiness.hard_gate is not HardGate.NONE
                    or readiness.readiness_state not in {ReadinessState.BUY_NOW, ReadinessState.SELL_NOW}
                    or readiness.canonical_subject_identity == "MCX-NATGAS"
                    or readiness.canonical_subject_identity in represented):
                continue
            retained = [r for r in unavailable if r.data["readiness_identity"] == readiness.readiness_identity
                        and r.data["pointer_integrity"] == pointer.integrity_identity]
            # Ordering chooses a display event only; it confers no source authority.
            result = max(retained, key=lambda r: (r.data["created_at"], r.identity)) if retained else None
            handoffs = []
            for path in self.application.wo09.handoffs.glob("*.json"):
                h = self.application.wo09.load_handoff(path.stem)
                if h.readiness_identity == readiness.readiness_identity and h.current_pointer_integrity == pointer.integrity_identity:
                    handoffs.append(h)
            h = handoffs[0] if len(handoffs) == 1 else None
            actionable = False
            if h is not None:
                try:
                    self.application._intake(h, self.application.clock())
                    actionable = True
                except ValueError:
                    pass
            loader = self.application.structural_loader
            commissioned = False
            structural_reason = "STRUCTURAL_CONSTRUCTION_AUTHORITY_NOT_ESTABLISHED"
            native_evidence = None
            if loader is not None and h is not None:
                try:
                    native = loader.load(h, now=self.application.clock())
                    native_evidence = native.data
                    commissioned = native.data.get("result", "PULLBACK") == "PULLBACK"
                    if not commissioned:
                        structural_reason = "; ".join(native.data["reasons"])
                except (ValueError, OSError, KeyError, TypeError) as error:
                    structural_reason = str(error) if isinstance(error, ValueError) else structural_reason
            cards.append(dict(subject=readiness.canonical_subject_identity, direction=readiness.direction,
                readiness_state=readiness.readiness_state.value, readiness_identity=readiness.readiness_identity,
                state=result.data["state"] if result else "CONSTRUCTION_PENDING" if commissioned else "TRADE_PLAN_UNAVAILABLE",
                reason=result.data["reason"] if result else structural_reason if not commissioned else "EXPLICIT_CONSTRUCTION_REQUIRED",
                records={"native_structural_selection": native_evidence} if result is None else {"plan": self.application.store.load(result.data["plan_identity"]).data},
                comparison_identity=None, handoff_identity=h.handoff_identity if actionable else None,
                action_identity=str(uuid4()), option_buy="NOT_COMMISSIONED_V1", option_sell="NOT_COMMISSIONED_V1"))
        selections = self.application.store.records("WO10_SPONSOR_SELECTION_V1")
        for card in cards:
            selected = [s for s in selections if s.data["comparison_identity"] == card["comparison_identity"]]
            card["selection_state"] = ("FUTURE_SELECTED" if selected[0].data["choice"] == "SELECTED_FUTURE" else "NONE_SELECTED") if len(selected) == 1 else "SPONSOR_SELECTION_PENDING"
            card["selected_lots"] = selected[0].data["sponsor_selected_lots"] if len(selected) == 1 else None
            if len(selected) == 1 and card["comparison_identity"] is not None:
                card["records"]["advisory"] = selected[0].data["advisory_risk"]
        status = {"cards": cards, "calculations": 0, "provider_calls": 0}
        return self.lifecycle_control.enrich(status) if self.lifecycle_control else status

    def construct_document(self, payload):
        if type(payload) is not dict or set(payload) != {"handoff_identity", "request_identity"}:
            return {"outcome": "REJECTED", "reason": "WO10_SPONSOR_REQUEST_INVALID"}
        try:
            result = self.application.construct_current(**payload)
            return {"outcome": "RETAINED", "result_identity": result.identity,
                    "state": result.data.get("state", result.data.get("executability")), "reason": result.data.get("reason")}
        except (ValueError, KeyError, OSError, TypeError):
            return {"outcome": "REJECTED", "reason": "WO10_CONSTRUCTION_NOT_PERMITTED"}

    def preview_document(self, payload):
        if type(payload) is not dict or set(payload) != {"comparison_identity", "lots"}:
            return {"outcome": "REJECTED", "reason": "WO10_SPONSOR_REQUEST_INVALID"}
        try:
            advisory = self.application.preview_risk(payload["comparison_identity"], lots=payload["lots"])
            return {"outcome": "PREVIEW", "advisory": advisory.data, "persisted": False}
        except (ValueError, KeyError, OSError, TypeError):
            return {"outcome": "REJECTED", "reason": "WO10_RISK_PREVIEW_INVALID"}

    def execute_document(self, payload):
        if (type(payload) is not dict or set(payload) != {"comparison_identity", "choice", "lots", "action_identity"}):
            return {"outcome":"REJECTED", "reason":"WO10_SPONSOR_REQUEST_INVALID"}
        try:
            comparison = self.application.store.load(payload["comparison_identity"])
            session = self.session_source(comparison.data["subject"], self.application.clock())
            selection = self.application.select(payload["comparison_identity"], choice=payload["choice"],
                                                lots=payload["lots"], action_identity=payload["action_identity"], session=session)
            return {"outcome":"RETAINED", "selection_identity":selection.identity, "advisory":selection.data["advisory_risk"]}
        except (ValueError, KeyError, OSError):
            return {"outcome":"REJECTED", "reason":"WO10_SELECTION_NOT_PERMITTED"}


def _redact(value):
    if isinstance(value, dict):
        return {k: _redact(v) for k,v in value.items() if k not in {"provider_instrument_token", "exchange_token"}}
    if isinstance(value, (tuple,list)):
        return [_redact(v) for v in value]
    return value


def render_futures(snapshot, status):
    from kronos.browser.views import render_browser_page
    import json
    from kronos.browser.intraday_lifecycle_control import actions_html, SCRIPT
    cards = []
    for card in status["cards"]:
        if card["comparison_identity"] is None:
            button = (f"<form class='future-construction' data-handoff='{escape(card['handoff_identity'])}' data-request='{escape(card['action_identity'])}'>"
                      "<button>CHECK TRADE CONSTRUCTION</button><output></output></form>") if card["handoff_identity"] else "<p>Exact current handoff is required for a new construction check.</p>"
            detail = escape(json.dumps(card["records"], indent=2))
            cards.append(f"<article><h2>{escape(card['subject'])} · {escape(card['direction'])}</h2>"
                f"<p>{escape(card['readiness_state'].replace('_', ' '))} · 5/5</p>"
                f"<h3>{escape(card['state'].replace('_', ' '))}</h3><p>{escape(card['reason'])}</p>"
                f"{button}<details><summary>VIEW ANALYSIS DETAILS</summary><pre>{detail}</pre></details></article>")
            continue
        r=card["records"]; p=r["plan"]; e=r["expression"]; s=r["snapshot"]; f=r["risk_fact"]; advisory=r["advisory"]
        future_quotes = [q for q in s["quotes"] if q["provider_record_identity"] == s["contract"]["future"]["provider_record_identity"]]
        depth = ({"bids": future_quotes[0]["bids"], "asks": future_quotes[0]["asks"]}
                 if len(future_quotes) == 1 else "NOT_ESTABLISHED")
        facts = [("Canonical Entry / Stop / Target", f"{p['entry']} / {p['stop']} / {p['target']}"),
                 ("Invalidation", p['invalidation_reference']), ("Canonical R:R", p['model_rr']), ("Exact Future", e['future']['trading_symbol']),
                 ("Expiry", e['future']['expiry']), ("Future price",s['future_price']),
                 ("Bid / Ask / Spread",f"{s['bid']} / {s['ask']} / {s['spread']}"),
                 ("Volume / OI / ΔOI",f"{s['volume']} / {s['oi']} / {s['delta_oi']}"),
                 ("Basis",s['basis'] if s['basis'] is not None else s['basis_state']),
                 ("Future Entry / Stop / Target",f"{e['entry']} / {e['stop']} / {e['target']}"),
                 ("Risk / Reward per lot",f"{advisory['risk_per_lot']} / {advisory['reward_per_lot']}"),
                 ("Future R:R",e['model_rr']), ("Risk reference",advisory['risk_reference_amount']),
                 ("Risk-reference lots (advisory)",advisory['risk_reference_lots']),
                 ("Sponsor-selected lots",advisory['sponsor_selected_lots']), ("Selected monetary Risk",advisory['selected_monetary_risk']),
                 ("Risk warning",advisory['risk_warning_state']),
                 ("Decision availability",card['state']), ("Selection",card.get('selection_state', 'SPONSOR_SELECTION_PENDING')),
                 ("Depth",depth)]
        fact_html=''.join(f"<dt>{escape(k)}</dt><dd>{escape(str(v))}</dd>" for k,v in facts)
        sections={"A. WHAT WO-09 PROMOTED":p['wo09'], "B. CANONICAL TRADE CONSTRUCTION":p,
                  "C. FUTURES CONTRACT & MARKET SNAPSHOT":s, "D. BASIS / FUTURES MAPPING":e,
                  "E. ADVISORY RISK & SPONSOR QUANTITY":{"facts":f,"advisory":advisory},
                  "F. EXECUTABILITY / FRESHNESS":{"state":card['state'],'snapshot':s['received_at']},
                  "G. PROS & CONS":{"pros":e['pros'],'cons':e['cons']},
                  "H. SPONSOR SELECTION":{"quantity":"POSITIVE_WHOLE_LOTS", "choices":["SELECTED_FUTURE","NONE"]},
                  "I. TECHNICAL EVIDENCE":{"comparison":card['comparison_identity']}}
        details=''.join(f"<h3>{escape(k)}</h3><pre>{escape(json.dumps(v,indent=2))}</pre>" for k,v in sections.items())
        disabled = '' if card['state']=='EXECUTABLE' else ' disabled'
        lots_value = card.get('selected_lots') or ''
        cards.append(f"<article><h2>{escape(card['subject'])} · {escape(card['direction'])}</h2><p>{'BUY NOW' if card['direction'] == 'LONG' else 'SELL NOW'} · 5/5</p><dl>{fact_html}</dl>"
                     f"<p>Pros: {escape(', '.join(e['pros']))}</p><p>Cons: {escape(', '.join(e['cons']))}</p>"
                     "<p>OPTION BUY / OPTION SELL: NOT_COMMISSIONED_V1</p>"
                     f"<form class='future-selection' data-comparison='{escape(card['comparison_identity'])}' data-action='{card['action_identity']}'>"
                     f"<label>Whole lots <input name='lots' type='number' min='1' step='1' value='{lots_value}'{disabled}></label>"
                     f"<div class='risk-preview' aria-live='polite'>{render_risk_warning(advisory)}</div>"
                     f"<button name='choice' value='SELECTED_FUTURE'{disabled}>SELECT FUTURE</button>"
                     "<button name='choice' value='NONE'>NONE</button><output></output></form>"
                     f"{actions_html(card)}<details><summary>VIEW ANALYSIS DETAILS</summary>{details}</details></article>")
    script = SCRIPT + """<script>
    function showRisk(form,a){const box=form.querySelector('.risk-preview');box.className='risk-preview';
      const above=a.risk_warning_state==='ABOVE_REFERENCE'; if(above)box.classList.add('risk-above');
      const label=above?'ABOVE RISK REFERENCE':a.risk_warning_state.replaceAll('_',' ');
      box.textContent=label+' · Risk per lot ₹'+a.risk_per_lot+' · Reference ₹'+a.risk_reference_amount+
        ' · Selected lots '+a.sponsor_selected_lots+' · Selected Risk ₹'+a.selected_monetary_risk+
        (above?' · Excess ₹'+a.difference_from_risk_reference+' · '+(a.percentage_difference_from_risk_reference===null?'Percentage unavailable (zero reference)':a.percentage_difference_from_risk_reference+'% excess'):'')+
        ' · Advisory only; quantity is the Sponsor choice.';}
    document.querySelectorAll('.future-selection').forEach(form=>{let revision=0;
      form.elements.lots.addEventListener('input',async()=>{const own=++revision;try{
        const response=await fetch('/control/intraday-futures/risk-preview',{method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({comparison_identity:form.dataset.comparison,lots:Number(form.elements.lots.value)})});
        const result=await response.json();if(own!==revision)return;
        if(result.outcome==='PREVIEW')showRisk(form,result.advisory);else form.querySelector('.risk-preview').textContent='Enter a positive whole-lot quantity.';
      }catch(e){if(own===revision)form.querySelector('.risk-preview').textContent='Risk preview unavailable. Selection retains a fresh advisory result.';}});
    });
    document.querySelectorAll('.future-selection').forEach(form=>form.addEventListener('submit',async event=>{
    event.preventDefault();const choice=event.submitter.value;const response=await fetch('/control/intraday-futures/selection',{
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({comparison_identity:form.dataset.comparison,
    action_identity:form.dataset.action,choice:choice,lots:choice==='NONE'?null:Number(form.elements.lots.value)})});
    const result=await response.json();if(result.advisory)showRisk(form,result.advisory);
    form.querySelector('output').textContent=JSON.stringify(result);}));</script>"""
    script += """<script>document.querySelectorAll('.future-construction').forEach(form=>form.addEventListener('submit',async event=>{
    event.preventDefault();const response=await fetch('/control/intraday-futures/construction',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({handoff_identity:form.dataset.handoff,request_identity:form.dataset.request})});
    form.querySelector('output').textContent=JSON.stringify(await response.json());}));</script>"""
    from kronos.browser.intraday_views import _intraday_tabs, _INTRADAY_CSS
    return render_browser_page(title="Intraday — Trade Candidates", subtitle="Persisted thesis, Risk and Sponsor choice",
                               snapshot=snapshot,active_nav="Intraday",active_tab="",body=_intraday_tabs(False, active="trade-candidates") + (''.join(cards) or '<p>No current lawful 5/5 Trade Candidates.</p>') + script, extra_styles=_INTRADAY_CSS + ".risk-above{color:#a40000;background:#fff0f0;border:2px solid #a40000;padding:12px;font-weight:bold}")


def render_risk_warning(advisory):
    above = advisory['risk_warning_state'] == 'ABOVE_REFERENCE'
    title = 'ABOVE RISK REFERENCE' if above else advisory['risk_warning_state'].replace('_', ' ')
    fields = [('Risk per lot', advisory['risk_per_lot']), ('Risk reference', advisory['risk_reference_amount']),
              ('Sponsor-selected lots', advisory['sponsor_selected_lots']), ('Selected monetary Risk', advisory['selected_monetary_risk'])]
    if above:
        fields += [('₹ excess', advisory['difference_from_risk_reference']), ('% excess', advisory['percentage_difference_from_risk_reference'] if advisory['percentage_difference_from_risk_reference'] is not None else 'NOT_ESTABLISHED (zero reference)')]
    detail = ' · '.join(escape(k) + ': ' + escape(str(v)) for k,v in fields)
    reasons = escape('; '.join(advisory['reasons']))
    css = 'risk-above' if above else 'risk-advisory'
    return f"<div class='{css}'><strong>{title}</strong><p>{detail}</p><p>{reasons}</p><p>Advisory only; quantity is the Sponsor choice.</p></div>"


def domain008_session(publisher, subject, now, *, contract=None):
    """Use the current subject/family calendar without inventing trading hours."""
    from datetime import date
    from zoneinfo import ZoneInfo
    from kronos.market.schedule import (MarketDaySchedule, MarketWindow, TradingDayStatus,
                                       MarketSessionService, InMemoryMarketScheduleSource)
    day = now.astimezone(ZoneInfo("Asia/Kolkata")).date()
    exchange = "MCX" if subject.startswith("MCX-") else "NSE"
    if exchange == "MCX":
        if contract is None:
            raise ValueError("WO10_EXACT_MCX_SESSION_REQUIRED")
        profile = publisher.mcx_contract_session_profile(contract_family=contract["name"],
                    contract_expiry=date.fromisoformat(contract["expiry"]), trading_date=day, observed_at=now)
        schedule = profile.continuous_trading
    else:
        profile = publisher.instrument_session_profile("NSE", day, canonical_instrument_id=subject, observed_at=now)
        schedule = None if profile is None else profile.continuous_trading
    schedules = ()
    if schedule is not None:
        schedule.__post_init__()
        schedules = (MarketDaySchedule(exchange, day, schedule.session_identity, schedule.timezone,
                     TradingDayStatus.TRADING, tuple(MarketWindow(w.window_open, w.window_close) for w in schedule.windows),
                     schedule.identity, schedule.calendar_version),)
    return MarketSessionService(InMemoryMarketScheduleSource(schedules)).facts(exchange=exchange, trading_date=day, observed_at=now)
