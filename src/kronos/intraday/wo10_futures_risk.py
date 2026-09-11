"""ADR-0042: monetary facts and optional Sponsor reference, never admission."""
from kronos.intraday.wo10_futures_contract import record, require, number, moment

REFERENCE_FIELDS = frozenset({"currency", "risk_reference_amount", "source_identity", "effective_at", "expires_at"})


def risk_configuration(**values):
    """Explicit optional reference. Identity and integrity are content-derived."""
    if set(values) != REFERENCE_FIELDS:
        raise ValueError("WO10_RISK_REFERENCE_FIELDS_INVALID")
    if (values["currency"] != "INR" or type(values["source_identity"]) is not str
            or not values["source_identity"].strip()
            or moment(values["expires_at"]) <= moment(values["effective_at"])):
        raise ValueError("WO10_RISK_REFERENCE_INVALID")
    if number(values["risk_reference_amount"]) < 0:
        raise ValueError("WO10_RISK_REFERENCE_INVALID")
    return record("WO10_RISK_REFERENCE_V1", **values)


def risk_advisory(fact, configuration, *, now, lots=None, reference_unavailable_reason=None, economics_unavailable_reason=None):
    f = require(fact, "WO10_RISK_FACT_V1")
    if lots is not None and (type(lots) is not int or lots <= 0):
        raise ValueError("WO10_POSITIVE_WHOLE_LOTS_REQUIRED")
    amount = reference_lots = selected = difference = percentage = None
    reasons = list(f["reasons"])
    if reference_unavailable_reason:
        configuration = None
        reasons.append(reference_unavailable_reason)
    if economics_unavailable_reason:
        reasons.append(economics_unavailable_reason)
    config_id = None
    if configuration is None:
        reasons.append("RISK_REFERENCE_NOT_CONFIGURED")
    else:
        try:
            c = require(configuration, "WO10_RISK_REFERENCE_V1")
            if risk_configuration(**c) != configuration:
                raise ValueError("WO10_RISK_REFERENCE_INVALID")
            config_id = configuration.identity
            if not moment(c["effective_at"]) <= moment(now) < moment(c["expires_at"]):
                reasons.append("RISK_REFERENCE_STALE")
            else:
                amount = number(c["risk_reference_amount"])
        except (ValueError, TypeError, KeyError):
            reasons.append("RISK_REFERENCE_INVALID")
    risk = None if economics_unavailable_reason or f["risk_per_lot"] is None else number(f["risk_per_lot"], positive=True)
    if risk is not None:
        if amount is not None:
            reference_lots = int(amount // risk)
        if lots is not None:
            selected = risk * lots
    if selected is not None and amount is not None:
        difference = selected - amount
        if amount == 0:
            reasons.append("ZERO_REFERENCE_PERCENTAGE_UNDEFINED")
        else:
            percentage = difference / amount * 100
    state = ("RISK_FACT_UNAVAILABLE" if risk is None else
             "REFERENCE_NOT_CONFIGURED" if amount is None else
             "QUANTITY_NOT_SELECTED" if lots is None else
             "ABOVE_REFERENCE" if selected > amount else "WITHIN_REFERENCE")
    return record("WO10_RISK_ADVISORY_V1", risk_fact_identity=fact.identity,
        reference_identity=config_id, risk_per_lot=risk, reward_per_lot=None if risk is None else f["reward_per_lot"],
        risk_reference_amount=amount, risk_reference_lots=reference_lots,
        sponsor_selected_lots=lots, selected_monetary_risk=selected,
        difference_from_risk_reference=difference, percentage_difference_from_risk_reference=percentage,
        risk_warning_state=state, reasons=reasons, evaluated_at=now, authority="ADVISORY_ONLY_NO_VETO")


def assess_risk(expression, configuration, *, now):
    e = require(expression, "WO10_FUTURE_EXPRESSION_V1")
    risk = reward = None
    reasons = []
    try:
        distance = number(e["risk_distance"], positive=True)
        reward_distance = number(e["reward_distance"], positive=True)
        if e["multiplier"] is None:
            reasons.append(e.get("monetary_reason") or "EXACT_MONETARY_ECONOMICS_UNAVAILABLE")
        else:
            multiplier = number(e["multiplier"], positive=True)
            lots = e["future"]["lot_size"]
            if type(lots) is not int or lots <= 0:
                raise ValueError("WO10_CONTRACT_LOT_INVALID")
            risk, reward = distance * lots * multiplier, reward_distance * lots * multiplier
    except (ValueError, TypeError, KeyError):
        reasons.append("INVALID_RISK_GEOMETRY_OR_ECONOMICS")
    fact = record("WO10_RISK_FACT_V1", expression_identity=expression.identity,
        risk_per_unit=e["risk_distance"], reward_per_unit=e["reward_distance"],
        risk_per_lot=risk, reward_per_lot=reward, model_rr=e["model_rr"],
        economics=e.get("monetary_economics"), reasons=reasons,
        state="AVAILABLE" if risk is not None else "RISK_FACT_UNAVAILABLE", evaluated_at=now)
    return fact, risk_advisory(fact, configuration, now=now)
