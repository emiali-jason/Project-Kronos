"""Versioned, deterministic NSE research interpretation of admitted owner facts.

This module does not admit sources, fetch data, retain records or confer Native,
visual-review, execution or live-price authority.  The public engine validates
the complete immutable source envelope before calling ``derive_thesis``.
"""
from __future__ import annotations

import math

from kronos.swing.v1.mtf_facts import (
    CompletedOneHourAtrFact, CompletedTimeframeBar, CompletedTimeframeFact,
    OneHourAtrAvailability,
)


METHOD_VERSION = "KRONOS-NSE-LOCAL-RESEARCH-1.0"


def method_parameters() -> dict:
    """Return fresh parameter material; none is a calibrated probability."""
    return {
        "version": METHOD_VERSION,
        "classification": "EXPLICIT_UNCALIBRATED_RESEARCH_HEURISTIC",
        "ma_periods": [20, 50, 200],
        "ma_change_lookback_completed_bars": 5,
        "momentum_lookback_completed_bars": 5,
        "minimum_directional_domains": 2,
        "minimum_directional_vote_magnitude": 2,
        "directional_domains": ["trend", "momentum", "structure"],
        "trend_votes": ["close_vs_sma20", "close_vs_sma50", "sma20_vs_sma50"],
        "trend_minimum_vote_magnitude": 2,
        "momentum_policy": "FIVE_BAR_RETURN_AND_NET_AVAILABLE_FIVE_BAR_MA_CHANGE_AGREE",
        "structure_policy": "REPORT_RADIUS_1_AND_2_SEPARATELY_REQUIRE_AGREEMENT_FOR_STRUCTURE_VOTE",
        "structure_breach_policy": "COMPLETED_CLOSE_BEYOND_LATEST_PROTECTIVE_PIVOT_WITHHOLDS_SEQUENCE_DIRECTION_NOT_OPPOSITE_TREND",
        "frame_breach_veto": "WITHHOLD_FRAME_DIRECTION_THAT_STILL_SUPPORTS_A_BREACHED_PIVOT_SEQUENCE",
        "candle_and_volume_directional_votes": 0,
        "horizons": [
            {"identity": "SHORT", "trading_sessions": [1, 3],
             "frames": ["4H", "1H"], "scenario_timeframe": "1H"},
            {"identity": "MEDIUM", "trading_sessions": [4, 10],
             "frames": ["1D", "4H"], "scenario_timeframe": "4H"},
            {"identity": "LONGER", "trading_sessions": [11, 20],
             "frames": ["1W", "1D"], "scenario_timeframe": "1D"},
        ],
        "horizon_policy": "BOTH_FRAME_DIRECTIONS_MUST_AGREE",
        "overall_anchor": "MEDIUM",
        "reject_native_policy": "ALL_THREE_AVAILABLE_HORIZONS_OPPOSE_NATIVE",
        "entry_zone_structural_distance_fraction": 0.10,
        "entry_zone_same_timeframe_latest_range_fraction": 0.25,
        "one_hour_entry_zone_atr_fraction": 0.25,
        "one_hour_immediate_max_sma20_extension_atr": 2.0,
        "atr_unit_policy": "COMPLETED_1H_ONLY_NEVER_RESCALED_TO_HIGHER_TIMEFRAMES",
        "pivot_proximity_formula": "100_TIMES_COMPLETED_CLOSE_MINUS_PIVOT_DIVIDED_BY_POSITIVE_PIVOT",
        "risk_reward_geometry_watch_below": 1.0,
        "stop_policy": "EXACT_OBSERVED_PIVOT_PRICE_NO_INVENTED_BUFFER",
        "target_policy": "NEAREST_OBSERVED_OPPOSING_PIVOT_BEYOND_ENTIRE_ENTRY_ZONE",
        "level_ordering": "STRICT_WHOLE_ENTRY_ZONE",
        "scenario_kinds": ["IMMEDIATE", "PULLBACK", "BREAKOUT", "ALTERNATIVE"],
        "scenario_directions": ["LONG", "SHORT"],
        "scenario_ranking": "CONSERVATIVE_GEOMETRY_WITHIN_SAME_HORIZON_DIRECTION_AND_RADIUS_ONLY",
        "conviction_policy": "QUALITATIVE_COVERAGE_AND_AGREEMENT_NOT_WIN_PROBABILITY",
        "no_live_price_or_execution_authority": True,
    }


def _sign(value: float) -> int:
    return (value > 0.0) - (value < 0.0)


def _direction(value: int) -> str:
    return "LONG" if value > 0 else "SHORT" if value < 0 else "NEUTRAL"


def _vote(direction: str) -> int:
    return 1 if direction == "LONG" else -1 if direction == "SHORT" else 0


def _finite(value: float) -> float | None:
    return value if math.isfinite(value) else None


def _ratio(numerator: float, denominator: float) -> float | None:
    if denominator <= 0.0 or not math.isfinite(numerator):
        return None
    return _finite(numerator / denominator)


def _change(current: float | None, prior: float | None) -> float | None:
    if current is None or prior is None:
        return None
    ratio = _ratio(current - prior, prior)
    return None if ratio is None else _finite(ratio * 100.0)


def _measurement(value, citations: list[str], reason: str) -> dict:
    return {"value": value, "state": "AVAILABLE" if value is not None else "UNAVAILABLE",
            "reason": None if value is not None else reason, "citations": citations}


def _pivot_citation(timeframe: str, radius: int, kind: str, index: int) -> str:
    return f"frames.{timeframe}.structure.radius_{radius}.{kind}[{index}].value"


def _pivot_record(pivot, timeframe: str, radius: int, kind: str, index: int,
                  close: float) -> dict:
    citation = _pivot_citation(timeframe, radius, kind, index)
    return {"value": pivot.value, "timestamp": pivot.timestamp.isoformat(),
            "candle_index": pivot.candle_index,
            "citations": [citation],
            "close_distance_percent": _measurement(_change(close, pivot.value),
                [f"frames.{timeframe}.close", citation], "POSITIVE_PIVOT_REFERENCE_REQUIRED"),
            "classification": "OBSERVED_HISTORICAL_PIVOT_NOT_CONFIRMED_LIVE_LEVEL"}


def _structure(fact: CompletedTimeframeFact) -> dict:
    rows = []
    for series in fact.structural_measurements:
        highs, lows = series.swing_highs, series.swing_lows
        citations = []
        sequence_direction = "UNKNOWN"
        breach = None
        if len(highs) < 2 or len(lows) < 2:
            direction, reason = "UNKNOWN", "TWO_COMPLETED_PIVOTS_PER_SIDE_UNAVAILABLE"
        else:
            high_delta = highs[-1].value - highs[-2].value
            low_delta = lows[-1].value - lows[-2].value
            direction = (
                "LONG" if high_delta > 0.0 and low_delta > 0.0 else
                "SHORT" if high_delta < 0.0 and low_delta < 0.0 else "NEUTRAL"
            )
            reason = {"LONG": "HIGHER_HIGH_AND_HIGHER_LOW", "SHORT": "LOWER_HIGH_AND_LOWER_LOW",
                      "NEUTRAL": "MIXED_OR_EQUAL_COMPLETED_PIVOT_STRUCTURE"}[direction]
            sequence_direction = direction
            citations = [_pivot_citation(fact.timeframe.value, series.radius, kind, idx)
                         for kind, values in (("highs", highs), ("lows", lows))
                         for idx in (len(values) - 2, len(values) - 1)]
            if direction == "LONG" and fact.close < lows[-1].value:
                direction, breach = "NEUTRAL", "BULLISH_SEQUENCE_LATEST_LOW_BREACHED_BY_COMPLETED_CLOSE"
            elif direction == "SHORT" and fact.close > highs[-1].value:
                direction, breach = "NEUTRAL", "BEARISH_SEQUENCE_LATEST_HIGH_BREACHED_BY_COMPLETED_CLOSE"
            if breach is not None:
                reason = breach
                citations.append(f"frames.{fact.timeframe.value}.close")
        rows.append({"radius": series.radius, "definition_identity": series.definition_identity,
                     "direction": direction, "reason": reason, "citations": citations,
                     "pivot_sequence_direction": sequence_direction, "completed_close_breach": breach,
                     "close_vs_latest_high": None if not highs else _sign(fact.close - highs[-1].value),
                     "close_vs_latest_low": None if not lows else _sign(fact.close - lows[-1].value),
                     "latest_high": None if not highs else _pivot_record(
                         highs[-1], fact.timeframe.value, series.radius, "highs", len(highs) - 1, fact.close),
                     "latest_low": None if not lows else _pivot_record(
                         lows[-1], fact.timeframe.value, series.radius, "lows", len(lows) - 1, fact.close)})
    directions = [row["direction"] for row in rows]
    missing = "UNKNOWN" in directions
    conflict = not missing and len(set(directions)) != 1
    return {"alternatives": rows,
            "direction": "UNKNOWN" if missing else "NEUTRAL" if conflict else directions[0],
            "conflict": conflict,
            "reason": "STRUCTURAL_RADIUS_EVIDENCE_INCOMPLETE" if missing else
                      "STRUCTURAL_RADIUS_DISAGREEMENT" if conflict else "STRUCTURAL_RADII_AGREE",
            "citations": [item for row in rows for item in row["citations"]]}


def _frame(summary_row: dict, fact: CompletedTimeframeFact,
           history: tuple[CompletedTimeframeBar, ...], atr: CompletedOneHourAtrFact | None,
           parameters: dict) -> dict:
    tf, values = fact.timeframe.value, summary_row["values"]
    prefix = f"frames.{tf}"
    distances, changes, missing, metrics = {}, {}, [], {}
    for period in parameters["ma_periods"]:
        name = f"sma{period}"
        prior_name = f"prior_sma{period}_5bars"
        distances[name] = _measurement(_change(fact.close, values[name]),
            [f"{prefix}.close", f"{prefix}.{name}"], f"{name.upper()}_MISSING_OR_NONPOSITIVE")
        changes[name] = _measurement(_change(values[name], values[prior_name]),
            [f"{prefix}.{name}", f"{prefix}.{prior_name}"], f"{name.upper()}_HISTORY_MISSING_OR_NONPOSITIVE")
        metrics[f"close_vs_{name}_percent"] = distances[name]
        metrics[f"{name}_change_5bars_percent"] = changes[name]
    sma20, sma50 = values["sma20"], values["sma50"]
    if sma20 is None or sma50 is None or min(sma20, sma50) <= 0.0:
        trend = {"direction": "UNKNOWN", "reason": "SMA20_AND_SMA50_REQUIRED", "votes": None}
    else:
        votes = [_sign(fact.close - sma20), _sign(fact.close - sma50), _sign(sma20 - sma50)]
        total = sum(votes)
        trend = {"direction": _direction(total) if abs(total) >= parameters["trend_minimum_vote_magnitude"] else "NEUTRAL",
                 "reason": "CLOSE_AND_MOVING_AVERAGE_ALIGNMENT", "votes": votes}
    trend["citations"] = [f"{prefix}.{name}" for name in ("close", "sma20", "sma50")]
    lookback = parameters["momentum_lookback_completed_bars"]
    momentum_percent = (_change(history[-1].close, history[-lookback-1].close)
                        if len(history) > lookback else None)
    momentum_citations = ([f"history.{tf}[{len(history)-lookback-1}].close",
                          f"history.{tf}[{len(history)-1}].close"]
                         if len(history) > lookback else [])
    metrics["return_5_completed_bars_percent"] = _measurement(momentum_percent, momentum_citations,
                                                              "SIX_COMPLETED_BARS_AND_POSITIVE_REFERENCE_REQUIRED")
    slopes = [item["value"] for item in changes.values() if item["value"] is not None]
    slope_vote = sum(_sign(value) for value in slopes)
    if momentum_percent is None or not slopes:
        momentum = {"direction": "UNKNOWN", "reason": "PRICE_RETURN_AND_MA_CHANGE_REQUIRED"}
    else:
        agrees = _sign(momentum_percent) == _sign(slope_vote)
        momentum = {"direction": _direction(_sign(momentum_percent)) if agrees else "NEUTRAL",
                    "reason": "PRICE_RETURN_AND_MA_CHANGE_AGREE" if agrees else "PRICE_RETURN_AND_MA_CHANGE_CONFLICT"}
    momentum["citations"] = momentum_citations + [citation for item in changes.values()
                                                 if item["value"] is not None for citation in item["citations"]]
    structure = _structure(fact)
    domains = {"trend": trend, "momentum": momentum, "structure": structure}
    available = [row for row in domains.values() if row["direction"] != "UNKNOWN"]
    total_vote = sum(_vote(row["direction"]) for row in available)
    direction = ("UNKNOWN" if len(available) < parameters["minimum_directional_domains"] else
                 _direction(total_vote) if abs(total_vote) >= parameters["minimum_directional_vote_magnitude"] else "NEUTRAL")
    # A protective-level break invalidates that measured structural hypothesis;
    # it does not prove an opposite trend.  Separately derived trend/momentum can
    # support the opposite direction, but cannot silently restore the broken one.
    breached_directions = {row["pivot_sequence_direction"] for row in structure["alternatives"]
                           if row["completed_close_breach"] is not None}
    direction_reason = "DOMAIN_COVERAGE_AND_AGREEMENT"
    if direction in breached_directions:
        direction, direction_reason = "NEUTRAL", "PROTECTIVE_STRUCTURE_BREACH_CONTRADICTS_DIRECTION"
    volume_ratio = _ratio(float(fact.volume), values["prior_20_volume_mean"]) if values["prior_20_volume_mean"] is not None else None
    metrics["volume_reference_ratio"] = _measurement(volume_ratio,
        [f"{prefix}.volume", f"{prefix}.prior_20_volume_mean"], "POSITIVE_PRIOR_20_VOLUME_REFERENCE_REQUIRED")
    candle_return = _change(fact.close, fact.open)
    metrics["candle_body_percent"] = _measurement(candle_return, [f"{prefix}.open", f"{prefix}.close"], "POSITIVE_OPEN_REQUIRED")
    range_percent = _ratio(fact.high - fact.low, fact.close)
    range_percent = None if range_percent is None else _finite(range_percent * 100.0)
    metrics["completed_bar_range_percent"] = _measurement(range_percent,
        [f"{prefix}.high", f"{prefix}.low", f"{prefix}.close"], "POSITIVE_CLOSE_REQUIRED")
    atr_value = (atr.value if tf == "1H" and atr is not None
                 and atr.availability is OneHourAtrAvailability.AVAILABLE else None)
    extension = (_ratio(fact.close - sma20, atr_value)
                 if atr_value is not None and sma20 is not None else None)
    metrics["close_sma20_distance_in_1h_atr"] = _measurement(extension,
        [f"{prefix}.close", f"{prefix}.sma20", "atr.1H.value"] if tf == "1H" else [],
        "ONE_HOUR_ONLY" if tf != "1H" else "POSITIVE_COMPLETED_1H_ATR_AND_SMA20_REQUIRED")
    for alternative in structure["alternatives"]:
        for side in ("latest_high", "latest_low"):
            pivot = alternative[side]
            if pivot is not None:
                distance = (_ratio(fact.close - pivot["value"], atr_value)
                            if atr_value is not None else None)
                pivot["close_distance_in_1h_atr"] = _measurement(distance,
                    [f"{prefix}.close", *pivot["citations"], "atr.1H.value"] if tf == "1H" else [],
                    "ONE_HOUR_ONLY" if tf != "1H" else "POSITIVE_COMPLETED_1H_ATR_REQUIRED")
    contradictions = []
    signed_domains = {_vote(row["direction"]) for row in domains.values()} - {0}
    if len(signed_domains) > 1:
        contradictions.append("DIRECTIONAL_DOMAINS_DISAGREE")
    if structure["conflict"]:
        contradictions.append("STRUCTURAL_RADIUS_DISAGREEMENT")
    contradictions.extend(row["completed_close_breach"] for row in structure["alternatives"]
                          if row["completed_close_breach"] is not None)
    if momentum["reason"] == "PRICE_RETURN_AND_MA_CHANGE_CONFLICT":
        contradictions.append(momentum["reason"])
    if direction in ("LONG", "SHORT") and values["sma200"] is not None and (
            _sign(fact.close - values["sma200"]) == -_vote(direction)):
        contradictions.append("SMA200_LONGER_TREND_OPPOSES_FRAME_DIRECTION")
    if direction in ("LONG", "SHORT") and _sign(fact.close - fact.open) == -_vote(direction):
        contradictions.append("LATEST_COMPLETED_CANDLE_OPPOSES_FRAME_DIRECTION")
    if extension is not None and abs(extension) > parameters["one_hour_immediate_max_sma20_extension_atr"]:
        contradictions.append("ONE_HOUR_EXTENSION_EXCEEDS_RESEARCH_IMMEDIATE_LIMIT")
    for name, row in metrics.items():
        if row["state"] == "UNAVAILABLE" and row["reason"] != "ONE_HOUR_ONLY":
            missing.append({"metric": name, "reason": row["reason"]})
    for name, row in domains.items():
        if row["direction"] == "UNKNOWN":
            missing.append({"domain": name, "reason": row["reason"]})
    return {"timeframe": tf, "direction": direction, "direction_reason": direction_reason, "domains": domains,
            "domain_vote_sum": total_vote, "available_directional_domains": len(available),
            "vote_limitation": "CORRELATED_HEURISTIC_EVIDENCE_NOT_PROBABILITY",
            "metrics": metrics, "candle_direction": _direction(_sign(fact.close - fact.open)),
            "volume_participation": "UNKNOWN" if volume_ratio is None else
                "ABOVE_REFERENCE" if volume_ratio > 1.0 else "BELOW_REFERENCE" if volume_ratio < 1.0 else "AT_REFERENCE",
            "volume_limitation": "PARTICIPATION_IS_NOT_DIRECTION_OR_INDEPENDENT_CONFIRMATION",
            "source_timestamp": fact.source_timestamp.isoformat(),
            "completed_boundary": fact.observation_boundary.isoformat(),
            "contradictions": contradictions, "missing": missing,
            "visual_conclusions": {question: "UNKNOWN" for question in ("Q3", "Q5", "Q10")}}


def _horizon(parameter: dict, by_timeframe: dict[str, dict]) -> dict:
    frames = [by_timeframe[tf] for tf in parameter["frames"]]
    directions = [frame["direction"] for frame in frames]
    if "UNKNOWN" in directions:
        direction, reason = "UNKNOWN", "HORIZON_DIRECTIONAL_EVIDENCE_INCOMPLETE"
    elif len(set(directions)) == 1 and directions[0] in ("LONG", "SHORT"):
        direction, reason = directions[0], "BOTH_HORIZON_FRAMES_AGREE"
    else:
        direction, reason = "NEUTRAL", "HORIZON_FRAMES_MIXED_OR_NON_DIRECTIONAL"
    contradictions = [{"timeframe": frame["timeframe"], "reason": reason}
                      for frame in frames for reason in frame["contradictions"]]
    return {**parameter, "direction": direction, "reason": reason,
            "frame_directions": [{"timeframe": f["timeframe"], "direction": f["direction"]} for f in frames],
            "contradictions": contradictions,
            "limitations": ["RESEARCH_HORIZON_NOT_FORECAST_OR_VALIDATED_HOLDING_PERIOD",
                            "NO_CHANGE_TO_EXISTING_WO12_HORIZONS"]}


def _scenario(fact: CompletedTimeframeFact, frame: dict, series, horizon: dict,
              direction: str, kind: str, atr: CompletedOneHourAtrFact | None,
              parameters: dict) -> dict:
    tf, radius, sign = fact.timeframe.value, series.radius, _vote(direction)
    result = {"horizon": horizon["identity"], "timeframe": tf, "structural_radius": radius,
              "structural_definition": series.definition_identity, "direction": direction,
              "kind": kind, "state": "UNAVAILABLE", "reason": None,
              "entry_zone": None, "stop_reference": None, "target_zone": None,
              "risk_reward": None, "activation": [], "source_citations": [],
              "geometry_rank": None,
              "research_suitability": "WITHHELD", "horizon_alignment":
                  "ALIGNED" if horizon["direction"] == direction else
                  "OPPOSED" if horizon["direction"] in ("LONG", "SHORT") else "UNRESOLVED",
              "limitations": ["HYPOTHETICAL_RESEARCH_GEOMETRY_NOT_AN_ORDER_OR_CURRENT_QUOTE",
                              "OBSERVED_PIVOTS_ARE_NOT_PROVEN_FUTURE_SUPPORT_OR_RESISTANCE",
                              "NO_FILL_HIT_PROBABILITY_PNL_COST_OR_EXECUTION_AUTHORITY",
                              "PIVOT_RADII_ARE_ALTERNATIVES_NOT_INDEPENDENT_CONFIRMATIONS"]}

    def absent(reason: str) -> dict:
        result["reason"] = reason
        return result

    # Retain each unique observed level with every original coordinate.
    def levels(pivots, name):
        grouped = {}
        for index, pivot in enumerate(pivots):
            grouped.setdefault(pivot.value, []).append(_pivot_citation(tf, radius, name, index))
        return [{"value": value, "citations": citations} for value, citations in sorted(grouped.items())]

    highs, lows = levels(series.swing_highs, "highs"), levels(series.swing_lows, "lows")
    supportive, opposing = (lows, highs) if direction == "LONG" else (highs, lows)
    below = sorted((level for level in supportive if sign * (fact.close - level["value"]) > 0.0),
                   key=lambda level: sign * (fact.close - level["value"]))
    ahead = sorted((level for level in opposing if sign * (level["value"] - fact.close) > 0.0),
                   key=lambda level: sign * (level["value"] - fact.close))
    if not below:
        return absent("NO_OBSERVED_STRUCTURAL_INVALIDATION_BEHIND_PRICE")
    if fact.high <= fact.low:
        return absent("ZERO_SAME_TIMEFRAME_COMPLETED_RANGE")
    atr_value = None
    if tf == "1H":
        if atr is None or atr.availability is not OneHourAtrAvailability.AVAILABLE or atr.value is None or atr.value <= 0.0:
            return absent("POSITIVE_COMPLETED_1H_ATR_REQUIRED_FOR_SHORT_SCENARIO")
        atr_value = atr.value
    stop = below[0]
    anchor = {"value": fact.close, "citations": [f"frames.{tf}.close"]}
    if kind == "PULLBACK":
        if len(below) < 2:
            return absent("SECOND_DISTINCT_OBSERVED_INVALIDATION_REQUIRED_FOR_PULLBACK")
        anchor, stop = below[0], below[1]
    elif kind in ("BREAKOUT", "ALTERNATIVE"):
        if not ahead:
            return absent("NO_OBSERVED_BREAKOUT_REFERENCE_AHEAD")
        anchor = ahead[0]
        if kind == "ALTERNATIVE" and horizon["direction"] == direction:
            return absent("ALTERNATIVE_RESERVED_FOR_NONALIGNED_DIRECTIONAL_HYPOTHESIS")
    if kind == "IMMEDIATE" and tf == "1H":
        extension = frame["metrics"]["close_sma20_distance_in_1h_atr"]["value"]
        if extension is None:
            return absent("ONE_HOUR_EXTENSION_UNAVAILABLE_FOR_IMMEDIATE_HYPOTHESIS")
        if abs(extension) > parameters["one_hour_immediate_max_sma20_extension_atr"]:
            return absent("ONE_HOUR_EXTENSION_EXCEEDS_RESEARCH_IMMEDIATE_LIMIT")
    structural_distance = sign * (anchor["value"] - stop["value"])
    width = min(structural_distance * parameters["entry_zone_structural_distance_fraction"],
                (fact.high - fact.low) * parameters["entry_zone_same_timeframe_latest_range_fraction"])
    if atr_value is not None:
        width = min(width, atr_value * parameters["one_hour_entry_zone_atr_fraction"])
    if not math.isfinite(width) or width <= 0.0:
        return absent("POSITIVE_FINITE_ENTRY_WIDTH_UNAVAILABLE")
    other = anchor["value"] + sign * width * (-1 if kind == "IMMEDIATE" else 1)
    lower, upper = sorted((anchor["value"], other))
    if not all(math.isfinite(value) and value > 0.0 for value in (lower, upper, stop["value"])):
        return absent("ENTRY_OR_INVALIDATION_NOT_POSITIVE_FINITE")
    worst_entry, best_entry = (upper, lower) if direction == "LONG" else (lower, upper)
    if sign * (best_entry - stop["value"]) <= 0.0:
        return absent("INVALIDATION_NOT_BEHIND_ENTIRE_ENTRY_ZONE")
    target_candidates = sorted((level for level in opposing if sign * (level["value"] - worst_entry) > 0.0),
                               key=lambda level: sign * (level["value"] - worst_entry))
    if not target_candidates:
        return absent("NO_OBSERVED_TARGET_BEYOND_ENTIRE_ENTRY_ZONE")
    target = target_candidates[0]
    risks = [sign * (entry - stop["value"]) for entry in (lower, upper)]
    rewards = [sign * (target["value"] - entry) for entry in (lower, upper)]
    if not all(math.isfinite(value) and value > 0.0 for value in risks + rewards):
        return absent("NONPOSITIVE_OR_NONFINITE_WHOLE_ZONE_GEOMETRY")
    conservative = _ratio(min(rewards), max(risks))
    if conservative is None or conservative <= 0.0:
        return absent("REWARD_RISK_NOT_POSITIVE_FINITE")
    width_citations = [f"frames.{tf}.high", f"frames.{tf}.low"]
    if atr_value is not None:
        width_citations.append("atr.1H.value")
    entry_citations = anchor["citations"] + stop["citations"] + width_citations
    activation = ["FUTURE_INDEPENDENT_CURRENTNESS_AND_PRICE_CHECK_REQUIRED",
                  "NO_ACTIVATION_IS_ESTABLISHED_BY_THIS_RETAINED_ASSESSMENT"]
    activation.append({
        "IMMEDIATE": "ONLY_IF_FUTURE_PRICE_IS_INSIDE_THE_COMPLETED_CLOSE_REFERENCE_ZONE",
        "PULLBACK": "ONLY_AFTER_FUTURE_RETEST_AND_HOLD_OF_THE_OBSERVED_PIVOT_ZONE",
        "BREAKOUT": "ONLY_AFTER_FUTURE_COMPLETED_CLOSE_THROUGH_AND_RETEST_OF_OBSERVED_TRIGGER",
        "ALTERNATIVE": "ONLY_IF_FUTURE_OPPOSITE_HYPOTHESIS_FAILS_AND_COMPLETED_BREAK_RETEST_CONFIRMS_THIS_DIRECTION",
    }[kind])
    result.update(state="AVAILABLE", reason="OBSERVED_LEVELS_SUPPORT_HYPOTHETICAL_GEOMETRY",
        entry_zone={"low": lower, "high": upper, "citations": entry_citations,
                    "formula": "ANCHOR_PLUS_OR_MINUS_MIN_0.10_STRUCTURAL_DISTANCE_0.25_SAME_TIMEFRAME_RANGE_AND_1H_ONLY_0.25_ATR"},
        stop_reference={**stop, "meaning": "STRUCTURAL_INVALIDATION_REFERENCE_NO_ORDER_BUFFER"},
        target_zone={"low": target["value"], "high": target["value"], "citations": target["citations"],
                     "meaning": "DEGENERATE_ZONE_AT_EXACT_OBSERVED_PIVOT_NO_PROJECTED_TARGET"},
        risk_reward={"minimum_risk": min(risks), "maximum_risk": max(risks),
                     "minimum_reward": min(rewards), "maximum_reward": max(rewards),
                     "conservative_ratio": conservative,
                     "formula": "MINIMUM_REWARD_OVER_ENTIRE_ENTRY_ZONE_DIVIDED_BY_MAXIMUM_RISK"},
        activation=activation, source_citations=sorted(set(entry_citations + stop["citations"] + target["citations"])),
        research_suitability="WATCH_GEOMETRY" if conservative < parameters["risk_reward_geometry_watch_below"] else "HYPOTHETICAL_GEOMETRY_ONLY")
    return result


def derive_thesis(summary: dict, frames: tuple[CompletedTimeframeFact, ...],
                  history: dict[str, tuple[CompletedTimeframeBar, ...]],
                  atr: CompletedOneHourAtrFact | None, native_direction: str) -> dict:
    """Derive research only from already validated, exact-source-bound facts."""
    parameters = method_parameters()
    assessments = [_frame(row, fact, history[fact.timeframe.value], atr, parameters)
                   for row, fact in zip(summary["frames"], frames)]
    by_timeframe = {row["timeframe"]: row for row in assessments}
    horizons = [_horizon(parameter, by_timeframe) for parameter in parameters["horizons"]]
    medium = next(row for row in horizons if row["identity"] == "MEDIUM")
    directions = [row["direction"] for row in horizons]
    opposite = "SHORT" if native_direction == "LONG" else "LONG"
    if all(direction == "UNKNOWN" for direction in directions):
        disposition, direction, reason = "INSUFFICIENT_EVIDENCE", "UNKNOWN", "ALL_HORIZONS_UNAVAILABLE"
    elif all(direction == opposite for direction in directions):
        disposition, direction, reason = "REJECT", opposite, "ALL_THREE_HORIZONS_OPPOSE_NATIVE"
    elif medium["direction"] == opposite:
        disposition, direction, reason = "CHALLENGE", opposite, "MEDIUM_HORIZON_OPPOSES_NATIVE"
    elif medium["direction"] == native_direction:
        disposition, direction, reason = "SUPPORT", native_direction, "MEDIUM_HORIZON_SUPPORTS_NATIVE"
    else:
        disposition, direction, reason = "WAIT", medium["direction"], "MEDIUM_HORIZON_MIXED_OR_UNAVAILABLE"
    contradictions = [{"timeframe": row["timeframe"], "reason": reason}
                      for row in assessments for reason in row["contradictions"]]
    if len(set(directions) - {"UNKNOWN", "NEUTRAL"}) > 1:
        contradictions.append({"timeframe": "MULTI_HORIZON", "reason": "HORIZON_DIRECTIONAL_DISAGREEMENT"})
    if direction not in ("LONG", "SHORT"):
        conviction = "UNAVAILABLE" if disposition == "INSUFFICIENT_EVIDENCE" else "LOW"
    elif all(item == direction for item in directions) and not contradictions and all(
            row["available_directional_domains"] == 3 for row in assessments):
        conviction = "HIGH"
    elif directions.count(direction) >= 2 and not contradictions:
        conviction = "MODERATE"
    else:
        conviction = "LOW"
    scenario_frames = {fact.timeframe.value: fact for fact in frames}
    scenarios = []
    for horizon in horizons:
        fact = scenario_frames[horizon["scenario_timeframe"]]
        for series in fact.structural_measurements:
            for scenario_direction in parameters["scenario_directions"]:
                group = []
                for kind in parameters["scenario_kinds"]:
                    group.append(_scenario(fact, by_timeframe[fact.timeframe.value], series,
                                           horizon, scenario_direction, kind, atr, parameters))
                available = sorted((row for row in group if row["state"] == "AVAILABLE"),
                                   key=lambda row: (-row["risk_reward"]["conservative_ratio"],
                                                    parameters["scenario_kinds"].index(row["kind"])))
                for rank, row in enumerate(available, 1):
                    row["geometry_rank"] = rank
                    row["limitations"].append("GEOMETRY_RANK_DOES_NOT_RANK_ACTIVATION_LIKELIHOOD_OR_EXPECTED_RETURN")
                scenarios.extend(group)
    hypotheses = []
    for hypothesis in parameters["scenario_directions"]:
        opposite_hypothesis = "SHORT" if hypothesis == "LONG" else "LONG"
        hypotheses.append({"direction": hypothesis,
            "supporting_domains": [{"timeframe": row["timeframe"], "domain": name,
                "citations": domain["citations"]} for row in assessments
                for name, domain in row["domains"].items() if domain["direction"] == hypothesis],
            "opposing_domains": [{"timeframe": row["timeframe"], "domain": name,
                "citations": domain["citations"]} for row in assessments
                for name, domain in row["domains"].items() if domain["direction"] == opposite_hypothesis],
            "supporting_horizons": [row["identity"] for row in horizons if row["direction"] == hypothesis],
            "opposing_horizons": [row["identity"] for row in horizons if row["direction"] == opposite_hypothesis],
            "limitations": ["EXAMINED_INDEPENDENTLY_OF_NATIVE_PROPOSED_DIRECTION",
                            "MISSING_OR_NEUTRAL_DOMAINS_DO_NOT_SUPPORT_EITHER_SIDE"]})
    return {"method_version": METHOD_VERSION, "parameters": parameters,
            "frame_assessments": assessments, "horizons": horizons,
            "overall": {"disposition": disposition, "direction": direction,
                        "native_direction": native_direction, "conviction": conviction,
                        "reason": reason, "contradictions": contradictions,
                        "supporting_domains": [{"timeframe": row["timeframe"], "domain": name,
                            "citations": domain["citations"]} for row in assessments
                            for name, domain in row["domains"].items()
                            if direction in ("LONG", "SHORT") and domain["direction"] == direction],
                        "opposing_domains": [{"timeframe": row["timeframe"], "domain": name,
                            "citations": domain["citations"]} for row in assessments
                            for name, domain in row["domains"].items()
                            if direction in ("LONG", "SHORT") and domain["direction"] == ("SHORT" if direction == "LONG" else "LONG")]},
            "directional_hypotheses": hypotheses, "scenarios": scenarios,
            "limitations": ["LOCAL_RESEARCH_HEURISTICS_NOT_CALIBRATED_WIN_PROBABILITIES",
                            "NO_NATIVE_KR370_K4_V2_VISUAL_OR_TRADING_AUTHORITY",
                            "NO_PROVIDER_QUOTE_CURRENTNESS_EXECUTION_OR_FILL_CERTIFICATION",
                            "SOURCE_CURRENTNESS_IS_THE_CALLING_OWNER_BOUNDARY",
                            "Q3_Q5_Q10_INDEPENDENT_VISUAL_CONCLUSIONS_REMAIN_UNKNOWN",
                            "SCENARIO_LEVELS_ABSTAIN_WHEN_OBSERVED_STRUCTURE_IS_INSUFFICIENT"]}


__all__ = ["METHOD_VERSION", "method_parameters", "derive_thesis"]
