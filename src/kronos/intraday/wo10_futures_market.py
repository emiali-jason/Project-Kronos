"""Futures selection, full-quote snapshots and conservative basis mapping."""
from datetime import date
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from zoneinfo import ZoneInfo

from kronos.provider.instrument_master import ProviderInstrumentSnapshot, ProviderAcquisitionOutcome
from kronos.provider.contracts.full_quote import FullQuote
from kronos.instrument.runtime import RuntimeInstrument, ProviderBindingStatus, InstrumentFreshness
from kronos.instrument.active_derivative import ActiveDerivativeBindingArtifact
from kronos.intraday.wo14 import Wo14InstrumentEconomics
from kronos.market.schedule import MarketSessionFact, MarketSessionState
from kronos.intraday.wo10_futures_contract import record, require, number, moment, fresh, normalize

SELECTOR = "WO10_EXACT_FUTURE_SELECTOR_V1"
FRESHNESS = "WO10_MARKET_AND_DECISION_FRESHNESS_V1"


def require_session(session, now, *, exchange=None):
    if type(session) is not MarketSessionFact:
        raise ValueError("WO10_DOMAIN008_SESSION_REQUIRED")
    session.__post_init__()
    if (session.state is not MarketSessionState.OPEN or session.observed_at != now
            or exchange is not None and session.exchange != exchange
            or session.trading_date != now.astimezone(ZoneInfo("Asia/Kolkata")).date()
            or not session.active_window.opens_at <= now < session.active_window.closes_at):
        raise ValueError("WO10_SESSION_NOT_OPEN")


def select_future(master, handoff, session, *, now, underlying=None, active_mcx=None, economics=None):
    require_session(session, now, exchange="MCX" if handoff.market_family == "MCX" else "NSE")
    if type(master) is not ProviderInstrumentSnapshot:
        raise ValueError("WO10_COMPLETE_DAILY_MASTER_REQUIRED")
    master.__post_init__()
    if (master.acquisition_outcome is not ProviderAcquisitionOutcome.COMPLETE
            or master.acquired_at.astimezone(ZoneInfo("Asia/Kolkata")).date() != session.trading_date
            or master.acquired_at > now):
        raise ValueError("WO10_MASTER_STALE_OR_INCOMPLETE")
    if session.schedule.session_id != handoff.session_identity:
        raise ValueError("WO10_SESSION_LINEAGE_MISMATCH")
    subject = handoff.canonical_subject_identity
    if subject.endswith("NATGAS"):
        raise ValueError("WO10_NATGAS_HELD")
    under_record = None
    active = None
    monetary_reason = None
    if handoff.market_family == "MCX":
        if type(active_mcx) is not ActiveDerivativeBindingArtifact:
            raise ValueError("WO10_MCX_ACTIVE_AUTHORITY_REQUIRED")
        active_mcx.__post_init__()
        if (active_mcx.canonical_subject_id != subject
                or active_mcx.provider_snapshot_identity != master.snapshot_identity
                or active_mcx.provider_snapshot_integrity_identity != master.integrity_identity
                or active_mcx.active_binding.derivative_contract_id != handoff.exact_mcx_contract_identity
                or active_mcx.binding_identity != handoff.exact_mcx_roll_lineage
                or not active_mcx.active_binding.active_at(now)):
            raise ValueError("WO10_MCX_CONTRACT_LINEAGE_MISMATCH")
        selected = [x for x in master.records if x.provider_record_identity == active_mcx.provider_record_identity]
        multiplier = None
        monetary_reason = "MCX_EXACT_MONETARY_ECONOMICS_UNAVAILABLE"
        if economics is not None:
            if type(economics) is not Wo14InstrumentEconomics:
                raise ValueError("WO10_MCX_ECONOMICS_INVALID")
            economics.__post_init__()
            if (economics.actual_contract_identity != handoff.exact_mcx_contract_identity
                    or economics.roll_lineage_identity != handoff.exact_mcx_roll_lineage
                    or economics.canonical_subject_identity != subject
                    or economics.instrument_identity != handoff.exact_mcx_contract_identity):
                raise ValueError("WO10_MCX_CONTRACT_LINEAGE_MISMATCH")
            if (economics.observed_at > now or economics.observed_at.astimezone(ZoneInfo("Asia/Kolkata")).date() != session.trading_date):
                monetary_reason = "MCX_MONETARY_ECONOMICS_STALE"
            elif economics.tick_value is not None and economics.tick_value != economics.tick_size * economics.lot_size * economics.contract_multiplier:
                monetary_reason = "MCX_MONETARY_ECONOMICS_INCONSISTENT"
            else:
                multiplier = economics.contract_multiplier
                monetary_reason = None
        active = active_mcx
    else:
        if type(underlying) is not RuntimeInstrument:
            raise ValueError("WO10_CANONICAL_UNDERLYING_REQUIRED")
        underlying.__post_init__()
        if (underlying.canonical.canonical_instrument_id != subject
                or underlying.canonical_freshness is not InstrumentFreshness.CURRENT
                or underlying.binding_status is not ProviderBindingStatus.BOUND
                or not underlying.canonical.source_boundary <= now <= underlying.canonical.valid_through
                or not underlying.provider_binding.source_boundary <= now <= underlying.provider_binding.valid_through):
            raise ValueError("WO10_UNDERLYING_BINDING_INVALID")
        binding = underlying.provider_binding
        rows = [x for x in master.records if x.provider_instrument_token == binding.provider_instrument_token
                and x.provider == binding.provider and x.trading_symbol == binding.provider_symbol and x.exchange == "NSE"]
        if len(rows) != 1:
            raise ValueError("WO10_UNDERLYING_MASTER_CONFLICT")
        under_record = rows[0]
        # Index future family names are exact commissioned catalogue identities.
        family = {"NSE-INDEX-NIFTY": "NIFTY", "NSE-INDEX-BANKNIFTY": "BANKNIFTY"}.get(subject, under_record.trading_symbol)
        candidates = [x for x in master.records if x.exchange == "NFO" and x.segment == "NFO-FUT"
                      and x.instrument_type == "FUT" and x.name == family and x.expiry is not None
                      and x.expiry > session.trading_date]
        if not candidates:
            raise ValueError("WO10_FUTURE_NOT_FOUND")
        expiry = min(x.expiry for x in candidates)
        selected = [x for x in candidates if x.expiry == expiry]
        multiplier = Decimal(1)  # INR per quoted point per NSE contract unit.
    if len(selected) != 1:
        raise ValueError("WO10_MINIMUM_EXPIRY_CONFLICT")
    future = selected[0]
    future.__post_init__()
    if (future.expiry is None
            or (future.expiry <= session.trading_date if active is None else future.expiry < session.trading_date)
            or future.lot_size <= 0 or future.tick_size <= 0 or future.instrument_type != "FUT"
            or future.segment not in {"NFO-FUT", "MCX-FUT"}
            or active is not None and (future.lot_size != active.lot_size or future.tick_size != active.tick_size)):
        raise ValueError("WO10_FUTURE_ECONOMICS_INVALID")
    if active is not None and economics is not None and (economics.lot_size != future.lot_size or economics.tick_size != future.tick_size):
        multiplier, monetary_reason = None, "MCX_MONETARY_ECONOMICS_INCONSISTENT"
    monetary = dict(currency="INR", multiplier=multiplier, lot_size=future.lot_size, tick_size=future.tick_size,
        rupees_per_quoted_point=None if multiplier is None else multiplier * future.lot_size,
        tick_monetary_value=None if multiplier is None else multiplier * future.lot_size * future.tick_size,
        quotation_unit="INR_PER_UNDERLYING_UNIT" if active is None else "NOT_ESTABLISHED",
        contract_unit="UNDERLYING_UNITS" if active is None else "NOT_ESTABLISHED",
        contract_identity=future.provider_record_identity, roll_identity=None if active is None else active.binding_identity,
        source_identity=master.snapshot_identity if active is None else None if economics is None else economics.economics_identity,
        source_integrity=master.integrity_identity if active is None else None if economics is None else economics.economics_integrity,
        version="NSE_LINEAR_FUTURE_INR_V1" if active is None else None if economics is None else economics.economics_version,
        reason=monetary_reason)
    contract = record("WO10_FUTURE_CONTRACT_V1", subject=subject, direction=handoff.direction,
                      session_identity=handoff.session_identity, trading_date=session.trading_date,
                      master_identity=master.snapshot_identity, master_integrity=master.integrity_identity,
                      selector_policy=SELECTOR, underlying=under_record, future=future,
                      multiplier=multiplier, active_mcx=active, economics=economics, monetary_economics=monetary, monetary_reason=monetary_reason,
                      handoff_identity=handoff.handoff_identity, readiness_identity=handoff.readiness_identity,
                      domain008=session, selected_at=now)
    return contract, tuple(x for x in (under_record, future) if x is not None)


def build_snapshot(contract, quotes, *, operation_identity, request_identity, received_at, session, baseline=None):
    c = require(contract, "WO10_FUTURE_CONTRACT_V1")
    require_session(session, received_at, exchange="MCX" if c["active_mcx"] else "NSE")
    if not operation_identity or not request_identity or len(set(q.provider_record_identity for q in quotes)) != len(quotes):
        raise ValueError("WO10_QUOTE_REQUEST_BINDING_INVALID")
    required = [x for x in (c["underlying"], c["future"]) if x is not None]
    if any(type(q) is not FullQuote for q in quotes):
        raise ValueError("WO10_FULL_QUOTE_REQUIRED")
    ids = {x["provider_record_identity"]: x for x in required}
    for q in quotes:
        q.__post_init__()
        expected = ids.get(q.provider_record_identity)
        if expected is None or any(getattr(q, k) != expected[k] for k in ("provider", "exchange", "trading_symbol", "provider_instrument_token")):
            raise ValueError("WO10_QUOTE_CONTRACT_MISMATCH")
    by_id = {q.provider_record_identity: q for q in quotes}
    reasons = []
    if set(by_id) != set(ids):
        reasons.append("REQUIRED_QUOTE_MISSING")
    times = [q.exchange_timestamp for q in quotes]
    if any(t is None or not fresh(t, received_at, 30) for t in times):
        reasons.append("QUOTE_STALE_OR_TIMESTAMP_UNAVAILABLE")
    valid_times = [t for t in times if t is not None]
    if valid_times and (max(valid_times) - min(valid_times)).total_seconds() > 5:
        reasons.append("CROSS_LEG_SKEW_EXCEEDED")
    if any(q.last_price is None or q.last_price <= 0 for q in quotes):
        reasons.append("ACTIONABLE_PRICE_UNAVAILABLE")
    fq = by_id.get(c["future"]["provider_record_identity"])
    uq = None if c["underlying"] is None else by_id.get(c["underlying"]["provider_record_identity"])
    bid = fq.bids[0].price if fq and fq.bids else None
    ask = fq.asks[0].price if fq and fq.asks else None
    if bid is None or ask is None or bid <= 0 or ask <= 0:
        reasons.append("POSITIVE_BID_ASK_REQUIRED")
    elif bid > ask:
        reasons.append("CROSSED_MARKET")
    basis = None if uq is None or fq is None or uq.last_price is None or fq.last_price is None else fq.last_price - uq.last_price
    baseline_key = dict(contract_record=c["future"]["provider_record_identity"],
                        provider=c["future"]["provider"], master_identity=c["master_identity"],
                        session_identity=c["session_identity"])
    delta = None
    current_oi = fq is not None and fq.oi is not None and fq.exchange_timestamp is not None and fresh(fq.exchange_timestamp, received_at, 30)
    if baseline is not None:
        b = require(baseline, "SESSION_FIRST_OBSERVED_OI_BASELINE_V1")
        if b["key"] != baseline_key:
            raise ValueError("WO10_OI_BASELINE_LINEAGE_MISMATCH")
        if current_oi and moment(b["observed_at"]) < received_at:
            delta = fq.oi - b["oi"]
    new_baseline = None
    if baseline is None and current_oi:
        new_baseline = record("SESSION_FIRST_OBSERVED_OI_BASELINE_V1", key=baseline_key,
                              oi=fq.oi, observed_at=received_at, request_identity=request_identity)
    bound_baseline = baseline or new_baseline
    state = "EXECUTABLE"
    if reasons:
        state = "STALE" if "QUOTE_STALE_OR_TIMESTAMP_UNAVAILABLE" in reasons else "MARKET_NOT_EXECUTABLE"
        if "REQUIRED_QUOTE_MISSING" in reasons:
            state = "UNAVAILABLE"
    snap = record("WO10_FUTURES_MARKET_SNAPSHOT_V1", contract_identity=contract.identity,
                  contract=c, operation_identity=operation_identity, request_identity=request_identity,
                  received_at=received_at, session=session, quotes=quotes, basis=basis,
                  basis_state="NOT_APPLICABLE" if c["underlying"] is None else "AVAILABLE" if basis is not None else "UNAVAILABLE",
                  future_price=None if fq is None else fq.last_price, bid=bid, ask=ask,
                  spread=None if bid is None or ask is None else ask-bid,
                  spread_percentage=None if bid is None or ask is None or ask <= 0 else (ask-bid)/ask*100,
                  volume=None if fq is None else fq.volume, oi=None if fq is None else fq.oi,
                  delta_oi=delta, delta_oi_reason=None if delta is not None else "DELTA_OI_SESSION_BASELINE_UNAVAILABLE",
                  baseline_identity=None if bound_baseline is None else bound_baseline.identity,
                  baseline_integrity=None if bound_baseline is None else bound_baseline.integrity,
                  baseline_observed_at=None if bound_baseline is None else bound_baseline.data["observed_at"],
                  freshness_policy=FRESHNESS, state=state, reasons=reasons)
    return snap, new_baseline


def map_future(plan, snapshot):
    p = require(plan, "WO10_CANONICAL_TRADE_PLAN_V1")
    s = require(snapshot, "WO10_FUTURES_MARKET_SNAPSHOT_V1")
    c = s["contract"]
    if (p["wo09"]["handoff_identity"] != c["handoff_identity"] or p["subject"] != c["subject"]
            or p["direction"] != c["direction"] or p["session_identity"] != c["session_identity"]):
        raise ValueError("WO10_PLAN_SNAPSHOT_LINEAGE_MISMATCH")
    values = dict(entry=None, stop=None, target=None, risk_distance=None, reward_distance=None, model_rr=None)
    state, reasons = s["state"], list(s["reasons"])
    if not fresh(p["created_at"], s["received_at"], 300):
        state, reasons = "STALE", ["TRADE_PLAN_STALE"]
    elif p["state"] != "AVAILABLE" or (c["underlying"] is not None and s["basis"] is None):
        state, reasons = "UNAVAILABLE", ["TRADE_PLAN_OR_BASIS_UNAVAILABLE"]
    else:
        tick = number(c["future"]["tick_size"], positive=True)
        basis = Decimal(0) if c["underlying"] is None else number(s["basis"])
        rounding = (ROUND_CEILING, ROUND_FLOOR, ROUND_FLOOR) if p["direction"] == "LONG" else (ROUND_FLOOR, ROUND_CEILING, ROUND_CEILING)
        values.update({k: ((number(p[k], positive=True)+basis)/tick).to_integral_value(rounding=rounding[i])*tick
                       for i, k in enumerate(("entry", "stop", "target"))})
        sign = 1 if p["direction"] == "LONG" else -1
        risk = sign*(values["entry"]-values["stop"])
        reward = sign*(values["target"]-values["entry"])
        if min(values["entry"], values["stop"], values["target"], risk, reward) <= 0:
            state, reasons = "UNAVAILABLE", ["MAPPED_GEOMETRY_INVALID"]
        else:
            values.update(risk_distance=risk, reward_distance=reward, model_rr=reward/risk)
    pros = ["LINEAR_PRICE_EXPOSURE", "NO_OPTION_TIME_DECAY", "DIRECT_FUTURES_EXPRESSION_OF_GOVERNED_THESIS"]
    cons = ["LEVERAGED_LOSS_EXPOSURE", "GAP_EXPOSURE"]
    if c["underlying"] is not None:
        pros.append("BASIS_MAPPED_THESIS"); cons.append("BASIS_RISK")
    return record("WO10_FUTURE_EXPRESSION_V1", plan_identity=plan.identity, snapshot_identity=snapshot.identity,
                  contract_identity=s["contract_identity"], subject=p["subject"], direction=p["direction"],
                  future=c["future"], multiplier=c["multiplier"], monetary_economics=c["monetary_economics"],
                  monetary_reason=c["monetary_reason"], basis=s["basis"], basis_state=s["basis_state"],
                  invalidation_authority="CANONICAL_THESIS", invalidation=p["invalidation"],
                  state=state, reasons=reasons, pros=pros, cons=cons, pros_cons_version="1.0.0", **values)
