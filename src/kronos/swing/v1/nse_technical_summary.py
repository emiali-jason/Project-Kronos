"""Pure explanatory NSE comparisons; no visual, promotion or trading authority."""
from __future__ import annotations

from hashlib import sha256
import json
import math
import re

from kronos.swing.v1.mtf_facts import (
    CompletedOneHourAtrFact, FactualTimeframe, OneHourAtrAvailability,
    SameRunMtfFactSnapshot,
)
from kronos.swing.v1.native_discovery import NativeDiscoveryRun, NativeProductPath
from kronos.swing.v1.native_review import (
    NativeReviewRequirement, _primitive, _timeframe_fact,
)


def _require(condition: bool) -> None:
    if not condition:
        raise ValueError("NSE_TECHNICAL_SOURCE_BINDING_INVALID")


def _number(value, *, integer=False):
    _require(type(value) is (int if integer else float)
             and (integer or math.isfinite(value)) and value >= 0)
    return value


def _relation(left, right, labels, missing):
    if left is None or right is None:
        return {"state": "UNAVAILABLE", "reason": missing}
    return {"state": labels[(left > right) - (left < right) + 1], "reason": None}


def build_nse_technical_summary(requirement, native, facts, publication_sha256):
    """Consume an already eligible requirement; never discover or admit one.

    Exact owner facts and requirement bytes are checked, not analytical rules.
    Currentness remains the caller's existing prepared-response/final fences.
    """
    _require(type(requirement) is NativeReviewRequirement
             and type(native) is NativeDiscoveryRun
             and type(facts) is SameRunMtfFactSnapshot
             and type(publication_sha256) is str
             and re.fullmatch(r"[0-9a-f]{64}", publication_sha256) is not None)
    requirement.__post_init__()
    thesis = requirement.thesis
    thesis.__post_init__()
    _require(thesis.product_path is NativeProductPath.NSE
             and native.run_identity == facts.run_identity == thesis.native_run_identity
             and native.provider_source_identity == facts.provider_source_identity)
    matches = tuple(a for a in native.assessments
                    if a.canonical_instrument == thesis.canonical_instrument)
    _require(len(matches) == 1)
    assessment = matches[0]
    assessment.__post_init__()
    _require(assessment.product_path is NativeProductPath.NSE
             and assessment.run_identity == native.run_identity
             and assessment.provider_source_identity == facts.provider_source_identity
             and assessment.result_sha256 == thesis.native_assessment_sha256
             and assessment.direction is thesis.direction
             and (assessment.weekly_state, assessment.daily_state,
                  assessment.four_hour_state, assessment.one_hour_state)
             == (thesis.weekly_state, thesis.daily_state,
                 thesis.four_hour_state, thesis.one_hour_state))
    # Use the owning serialization and flattening functions, not a new eligibility
    # builder, historical selector or independently reinterpreted numerical source.
    digest = sha256(json.dumps(
        {"thesis": _primitive(thesis), "mcx_reference": None},
        sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()
    _require(digest == requirement.requirement_sha256)
    instrument = facts.instrument(thesis.canonical_instrument)
    _require(instrument.exchange == "NSE"
             and tuple(f.timeframe for f in instrument.timeframes) == tuple(FactualTimeframe))
    frames = []
    contexts = (thesis.weekly_state, thesis.daily_state,
                thesis.four_hour_state, thesis.one_hour_state)
    for fact, retained, context in zip(instrument.timeframes, thesis.timeframe_facts, contexts):
        fact.__post_init__()
        if fact.moving_averages is not None:
            fact.moving_averages.__post_init__()
        if fact.volume_facts is not None:
            fact.volume_facts.__post_init__()
        _require(_timeframe_fact(fact) == retained
                 and fact.observation_boundary <= facts.observed_at)
        values = {name: _number(getattr(retained, name))
                  for name in ("open", "high", "low", "close")}
        values["volume"] = _number(retained.volume, integer=True)
        comparisons = {}
        for period in (20, 50, 200):
            current, prior = getattr(retained, f"sma{period}"), getattr(retained, f"prior_sma{period}_5bars")
            values[f"sma{period}"] = None if current is None else _number(current)
            values[f"prior_sma{period}_5bars"] = None if prior is None else _number(prior)
            comparisons[f"close_sma{period}"] = _relation(
                values["close"], current, ("BELOW", "EQUAL", "ABOVE"), f"SMA{period}_UNAVAILABLE")
            comparisons[f"sma{period}_change"] = _relation(
                current, prior, ("FALLING", "UNCHANGED", "RISING"), f"SMA{period}_HISTORY_UNAVAILABLE")
        mean = retained.prior_20_volume_mean
        values["prior_20_volume_mean"] = None if mean is None else _number(mean)
        comparisons["volume_reference"] = _relation(
            values["volume"], mean, ("BELOW", "EQUAL", "ABOVE"), "VOLUME_REFERENCE_UNAVAILABLE")
        comparisons["candle_direction"] = _relation(
            values["close"], values["open"], ("DOWN", "UNCHANGED", "UP"), "CANDLE_UNAVAILABLE")
        frames.append(dict(timeframe=fact.timeframe.value, context=context.value,
            observed_boundary=fact.observation_boundary.isoformat(),
            source_timestamp=fact.source_timestamp.isoformat(), values=values, comparisons=comparisons,
            calendar_identity=fact.calendar_identity, calendar_version=fact.calendar_version,
            session_identity=fact.session_identity, provider_identity=fact.source_provider_identity,
            provenance=list(fact.provenance),
            visual={q: {"state": "UNKNOWN", "reason": "METHOD_NOT_APPROVED"}
                    for q in ("Q3", "Q5", "Q10")}))
    atr = instrument.one_hour_atr
    atr_view = dict(state="UNAVAILABLE", value=None, reason="ATR14_NOT_RETAINED")
    if atr is not None:
        _require(type(atr) is CompletedOneHourAtrFact)
        atr.__post_init__()
        one_hour = instrument.fact(FactualTimeframe.ONE_HOUR)
        _require(atr.run_identity == facts.run_identity
                 and atr.canonical_instrument == thesis.canonical_instrument
                 and atr.analysis_boundary <= facts.observed_at
                 and atr.observation_boundary == one_hour.observation_boundary
                 and atr.source_market_data_boundary == one_hour.source_market_data_boundary
                 and (atr.calendar_identity, atr.calendar_version, atr.session_identity,
                      atr.source_provider_identity) ==
                     (one_hour.calendar_identity, one_hour.calendar_version, one_hour.session_identity,
                      one_hour.source_provider_identity))
        atr_view = dict(state=atr.availability.value, value=atr.value,
            reason=atr.unavailable_reason, integrity_sha256=atr.integrity_sha256,
            analysis_boundary=atr.analysis_boundary.isoformat(),
            observed_boundary=atr.observation_boundary.isoformat(),
            source_timestamp=atr.source_market_data_boundary.isoformat(),
            provenance=list(atr.provenance))
    missing = sum(v["state"] == "UNAVAILABLE" for f in frames for v in f["comparisons"].values())
    return dict(schema="KRONOS-SWING-NSE-TECHNICAL-SUMMARY-V1", version="1.0",
        authority="FACTUAL_EXPLANATORY_ONLY", independence="NOT_ESTABLISHED",
        binding=dict(run_identity=facts.run_identity, publication_sha256=publication_sha256,
            instrument=thesis.canonical_instrument, direction=thesis.direction.value,
            assessment_sha256=thesis.native_assessment_sha256,
            requirement_sha256=requirement.requirement_sha256,
            provider_source_identity=facts.provider_source_identity),
        analysis_time=facts.observed_at.isoformat(),
        coverage="PARTIAL" if missing or atr_view["state"] != OneHourAtrAvailability.AVAILABLE.value else "COMPLETE",
        frames=frames, atr=atr_view)
