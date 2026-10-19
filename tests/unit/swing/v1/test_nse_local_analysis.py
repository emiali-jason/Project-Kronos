"""LOCAL-01 synthetic, retained-source-only engine qualification.

No test fixture is market evidence, a Chart Analyst Answer or a trading plan.
The canonical owner classes and unchanged SW-FAST-02 fixture are reused.
"""
from copy import deepcopy
from dataclasses import FrozenInstanceError, asdict, replace
from datetime import timedelta
from hashlib import sha256
import builtins
import json
import os
from pathlib import Path
import socket
import subprocess
import urllib.request

import pytest

from kronos.swing.v1.models import PivotCandidate, PivotKind, V1Direction
from kronos.swing.v1.mtf_facts import (
    CompletedTimeframeBar,
    FactualMovingAverageFacts,
    FactualPivotSeries,
    FactualTimeframe,
    FactualVolumeFacts,
    OneHourAtrAvailability,
    _json_value,
    one_hour_atr_integrity_sha256,
)
from kronos.swing.v1.native_review import _primitive, build_native_review_requirements
from kronos.swing.v1.nse_local_analysis import (
    LocalAnalysisInput,
    LocalAnalysisResult,
    analyze_local,
    build_local_input,
    decode_input,
    validate_result,
)
from kronos.swing.v1.nse_technical_summary import build_nse_technical_summary
from tests.unit.swing.v1.test_nse_technical_summary import _inputs, _numbers


PUBLICATION = "a" * 64


def _canonical(body):
    return json.dumps(body, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def _rehash_input(body):
    encoded = _canonical(body)
    return _canonical({"identity": sha256(encoded.encode()).hexdigest(), "evidence": body})


def _rehash_result(body):
    encoded = _canonical(body)
    return LocalAnalysisResult(encoded, sha256(encoded.encode()).hexdigest())


def _case(*, native_direction=V1Direction.LONG, directions=None,
          missing=(), no_pivots=False, no_atr=False, zero_atr=False):
    """Clearly synthetic exact-source fixtures; never acquire market data."""
    requirement, native, facts = deepcopy(_inputs())
    instrument = facts.instrument(requirement.canonical_instrument)
    directions = directions or ("LONG",) * 4
    frames = []
    for fact, direction in zip(instrument.timeframes, directions):
        bullish = direction == "LONG"
        moving = FactualMovingAverageFacts(
            205,
            None if "ma" in missing else (95.0 if bullish else 105.0),
            None if "ma" in missing else (90.0 if bullish else 110.0),
            None if "ma" in missing else (85.0 if bullish else 115.0),
            None if "history" in missing or "ma" in missing else (93.0 if bullish else 107.0),
            None if "history" in missing or "ma" in missing else (88.0 if bullish else 112.0),
            None if "history" in missing or "ma" in missing else (83.0 if bullish else 117.0),
        )
        high_values = (120.0, 130.0) if bullish else (130.0, 110.0)
        low_values = (70.0, 90.0) if bullish else (70.0, 60.0)
        structures = tuple(FactualPivotSeries(
            f"FRACTAL_UNIQUE_EXTREME_RADIUS_{radius}", radius,
            () if no_pivots else tuple(PivotCandidate(
                PivotKind.HIGH, index,
                fact.source_timestamp - timedelta(days=8-index), value,
            ) for index, value in enumerate(high_values)),
            () if no_pivots else tuple(PivotCandidate(
                PivotKind.LOW, index+2,
                fact.source_timestamp - timedelta(days=6-index), value,
            ) for index, value in enumerate(low_values)),
        ) for radius in (1, 2))
        frames.append(replace(fact,
            open=98.0 if bullish else 102.0, high=105.0, low=95.0,
            close=100.0, volume=200,
            moving_averages=moving,
            volume_facts=FactualVolumeFacts(200, None if "volume" in missing else 100.0),
            structural_measurements=structures,
        ))
    atr = deepcopy(instrument.one_hour_atr)
    if no_atr:
        atr = None
    elif atr is not None:
        object.__setattr__(atr, "value", 0.0 if zero_atr else 2.0)
        object.__setattr__(atr, "integrity_sha256", one_hour_atr_integrity_sha256(atr))
    instrument = replace(instrument, timeframes=tuple(frames), one_hour_atr=atr,
                         completed_series=())
    facts = replace(facts, instruments=tuple(
        instrument if item.canonical_instrument == instrument.canonical_instrument else item
        for item in facts.instruments))
    native = replace(native, assessments=tuple(
        replace(item, direction=native_direction)
        if item.canonical_instrument == instrument.canonical_instrument else item
        for item in native.assessments))
    requirement = build_native_review_requirements(native, facts)[0]
    return requirement, native, facts


def _built(**kwargs):
    return build_local_input(*_case(**kwargs), PUBLICATION)


def _analysis(**kwargs):
    source = _built(**kwargs)
    return source, analyze_local(source, expected_source=source.binding)


def test_owner_bound_input_round_trip_and_result_are_exactly_deterministic():
    arguments = _case()
    before = deepcopy(arguments)
    source = build_local_input(*arguments, PUBLICATION)
    restored = decode_input(source.to_json())
    assert restored == source
    assert source.identity == sha256(source.evidence_json.encode()).hexdigest()
    first = analyze_local(source, expected_source=source.binding)
    second = analyze_local(restored, expected_source=source.binding)
    assert first == second
    assert first.to_json() == second.to_json()
    assert first.identity == sha256(first.payload_json.encode()).hexdigest()
    assert arguments == before
    validate_result(first, restored, expected_source=source.binding)


def test_input_and_output_are_frozen_and_returned_dicts_are_detached():
    source, result = _analysis()
    with pytest.raises(FrozenInstanceError):
        source.identity = "f" * 64
    with pytest.raises(FrozenInstanceError):
        result.identity = "f" * 64
    source_copy = source.to_dict()
    source_copy["binding"]["instrument"] = "FOREIGN"
    result_copy = result.to_dict()
    result_copy["thesis"] = {}
    assert source.to_dict()["binding"]["instrument"] != "FOREIGN"
    assert result.to_dict()["thesis"]


def test_sw_fast_02_owner_summary_is_preserved_exactly():
    args = _case()
    original = build_nse_technical_summary(*args, PUBLICATION)
    source = build_local_input(*args, PUBLICATION)
    result = analyze_local(source, expected_source=source.binding)
    assert source.to_dict()["summary"] == original
    assert result.to_dict()["summary"] == original
    assert result.to_dict()["visual"] == {"Q3": "UNKNOWN", "Q5": "UNKNOWN", "Q10": "UNKNOWN"}
    assert result.to_dict()["authority"] == "RESEARCH_ONLY_NO_ADMISSION_OR_EXECUTION"
    assert result.to_dict()["currentness"] == "SOURCE_MATCH_AT_CALL_NOT_LIVE_CERTIFICATION"
    assert not {"readiness", "receipt", "position", "win_probability", "confirmation"} & result.to_dict().keys()


@pytest.mark.parametrize("field", [
    "input_sha256", "run_identity", "publication_sha256", "instrument",
    "assessment_sha256", "requirement_sha256", "provider_source_identity", "information_cutoff",
])
def test_independently_supplied_current_source_must_match_every_binding(field):
    source = _built()
    changed_value = {
        "input_sha256": "f" * 64,
        "run_identity": "SWING-RUN-" + "F" * 32,
        "publication_sha256": "f" * 64,
        "instrument": "FOREIGN",
        "assessment_sha256": "f" * 64,
        "requirement_sha256": "f" * 64,
        "provider_source_identity": "KITE-MTF-FACTS-" + "f" * 64,
        "information_cutoff": "2026-08-15T23:59:00+05:30",
    }[field]
    changed = replace(source.binding, **{field: changed_value})
    with pytest.raises(ValueError):
        analyze_local(source, expected_source=changed)


def test_caller_current_source_is_mandatory_not_assumed_from_input_hash():
    with pytest.raises(TypeError):
        analyze_local(_built())


@pytest.mark.parametrize("changed", ["run", "provider", "assessment", "requirement", "instrument", "direction", "timeframe", "publication"])
def test_cross_source_or_subject_owner_bindings_fail_closed(changed):
    requirement, native, facts = deepcopy(_inputs())
    publication = PUBLICATION
    if changed == "run":
        object.__setattr__(facts, "run_identity", "SWING-RUN-" + "F" * 32)
    elif changed == "provider":
        object.__setattr__(facts, "provider_source_identity", "KITE-MTF-FACTS-" + "f" * 64)
    elif changed == "assessment":
        requirement = replace(requirement, thesis=replace(requirement.thesis, native_assessment_sha256="f" * 64))
    elif changed == "requirement":
        requirement = replace(requirement, requirement_sha256="f" * 64)
    elif changed == "instrument":
        requirement = replace(requirement, thesis=replace(requirement.thesis, canonical_instrument="FOREIGN"))
    elif changed == "direction":
        requirement = replace(requirement, thesis=replace(requirement.thesis, direction=V1Direction.SHORT))
    elif changed == "timeframe":
        object.__setattr__(facts.instrument(requirement.canonical_instrument).timeframes[0], "timeframe", FactualTimeframe.DAILY)
    else:
        publication = "not-a-digest"
    with pytest.raises(ValueError):
        build_local_input(requirement, native, facts, publication)


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -float("inf"), True, -1.0])
def test_invalid_source_numeric_values_are_not_disguised_as_missing(invalid):
    requirement, native, facts = deepcopy(_inputs())
    fact = facts.instrument(requirement.canonical_instrument).timeframes[0]
    object.__setattr__(fact, "close", invalid)
    with pytest.raises(ValueError):
        build_local_input(requirement, native, facts, PUBLICATION)


@pytest.mark.parametrize("field", ["observed_at", "source_timestamp", "observation_boundary"])
def test_owner_timestamps_cannot_be_naive_or_future_to_admitted_cutoff(field):
    requirement, native, facts = deepcopy(_inputs())
    if field == "observed_at":
        object.__setattr__(facts, field, facts.observed_at.replace(tzinfo=None))
    else:
        fact = facts.instrument(requirement.canonical_instrument).timeframes[0]
        object.__setattr__(fact, field, facts.observed_at + timedelta(days=1))
    with pytest.raises((ValueError, TypeError)):
        build_local_input(requirement, native, facts, PUBLICATION)


@pytest.mark.parametrize("mutation", [
    "extra", "missing", "wrong_version", "wrong_contract", "unknown_frame",
    "duplicate_frame", "reverse_frames", "fabricated_summary", "wrong_summary_instrument",
    "missing_evidence", "cross_frame_history", "future_cutoff", "naive_cutoff",
])
def test_self_consistently_rehashed_invalid_input_remains_rejected(mutation):
    body = _built().to_dict()
    if mutation == "extra":
        body["new_authority"] = True
    elif mutation == "missing":
        del body["information_cutoff"]
    elif mutation == "wrong_version":
        body["version"] = "99"
    elif mutation == "wrong_contract":
        body["contract"] = "FOREIGN"
    elif mutation == "unknown_frame":
        body["summary"]["frames"][0]["timeframe"] = "1M"
    elif mutation == "duplicate_frame":
        body["summary"]["frames"][1] = deepcopy(body["summary"]["frames"][0])
    elif mutation == "reverse_frames":
        body["summary"]["frames"].reverse()
    elif mutation == "fabricated_summary":
        body["summary"]["frames"][0]["values"]["close"] += 10.0
    elif mutation == "wrong_summary_instrument":
        body["summary"]["binding"]["instrument"] = "FOREIGN"
    elif mutation == "missing_evidence":
        body["source_evidence"] = {}
    elif mutation == "cross_frame_history":
        body["source_evidence"]["completed_series"][0]["bars"] = deepcopy(
            body["source_evidence"]["completed_series"][1]["bars"])
    elif mutation == "future_cutoff":
        body["information_cutoff"] = "2000-01-01T00:00:00+05:30"
    else:
        body["information_cutoff"] = "2026-08-14T23:59:00"
    with pytest.raises(ValueError):
        decode_input(_rehash_input(body))


def test_duplicate_json_keys_and_bad_digest_are_rejected():
    source = _built()
    raw = source.to_json()
    with pytest.raises(ValueError):
        decode_input(raw[:-1] + ',"identity":"' + source.identity + '"}')
    body = json.loads(raw)
    body["identity"] = "f" * 64
    with pytest.raises(ValueError):
        decode_input(_canonical(body))


@pytest.mark.parametrize("mutation", [
    "insufficient_sma_sample", "volume_source_disagreement", "future_pivot",
    "negative_pivot", "reversed_pivots", "future_bar", "wrong_bar_provider",
    "wrong_bar_session", "changed_latest_bar", "repeated_bar", "extra_source_field",
])
def test_rehashed_owner_evidence_still_obeys_temporal_and_derivation_rules(mutation):
    body = _built().to_dict()
    source = body["source_evidence"]
    if mutation == "insufficient_sma_sample":
        source["timeframes"][0]["moving_averages"]["completed_count"] = 1
    elif mutation == "volume_source_disagreement":
        source["timeframes"][0]["volume_facts"]["current"] += 1
    elif mutation == "future_pivot":
        source["timeframes"][0]["structural_measurements"][0]["swing_highs"][0]["timestamp"] = "2099-01-01T00:00:00+05:30"
    elif mutation == "negative_pivot":
        source["timeframes"][0]["structural_measurements"][0]["swing_lows"][0]["value"] = -1.0
    elif mutation == "reversed_pivots":
        source["timeframes"][0]["structural_measurements"][0]["swing_lows"].reverse()
    elif mutation == "future_bar":
        source["completed_series"][0]["bars"][0]["observation_boundary"] = "2099-01-01T00:00:00+05:30"
    elif mutation == "wrong_bar_provider":
        source["completed_series"][0]["bars"][0]["source_provider_identity"] = "FOREIGN"
    elif mutation == "wrong_bar_session":
        source["completed_series"][0]["bars"][0]["session_identity"] = "FOREIGN"
    elif mutation == "changed_latest_bar":
        source["completed_series"][0]["bars"][0]["close"] += 1.0
    elif mutation == "repeated_bar":
        source["completed_series"][0]["bars"] *= 2
    else:
        source["timeframes"][0]["secret_authority"] = True
    with pytest.raises(ValueError):
        decode_input(_rehash_input(body))


@pytest.mark.parametrize("mutation", ["opinion", "binding", "source_hash", "method", "authority", "summary", "extra"])
def test_rehashed_output_tampering_cannot_pass_deterministic_validation(mutation):
    source, result = _analysis()
    body = result.to_dict()
    if mutation == "opinion":
        body["thesis"]["overall"]["direction"] = "FOREIGN"
    elif mutation == "binding":
        body["binding"]["instrument"] = "FOREIGN"
    elif mutation == "source_hash":
        body["input_sha256"] = "f" * 64
    elif mutation == "method":
        body["method_version"] = "99"
    elif mutation == "authority":
        body["authority"] = "TRADING_PERMITTED"
    elif mutation == "summary":
        body["summary"]["frames"][0]["values"]["close"] += 1.0
    else:
        body["new_authority"] = True
    with pytest.raises(ValueError):
        validate_result(_rehash_result(body), source, expected_source=source.binding)


def test_engine_execution_has_no_file_network_subprocess_or_provider_acquisition(monkeypatch):
    # Build owner fixture before fencing: fixtures reuse calendar files; the
    # engine consumes only already-retained, caller-supplied typed facts.
    arguments = _case()
    calls = []

    def denied(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("LOCAL_ENGINE_FORBIDDEN_IO")

    with monkeypatch.context() as guard:
        guard.setattr(builtins, "open", denied)
        guard.setattr(os, "open", denied)
        guard.setattr(Path, "open", denied)
        guard.setattr(Path, "read_text", denied)
        guard.setattr(Path, "read_bytes", denied)
        guard.setattr(socket, "socket", denied)
        guard.setattr(socket, "create_connection", denied)
        guard.setattr(urllib.request, "urlopen", denied)
        guard.setattr(subprocess, "Popen", denied)
        source = build_local_input(*arguments, PUBLICATION)
        restored = decode_input(source.to_json())
        result = analyze_local(restored, expected_source=source.binding)
        validate_result(result, source, expected_source=source.binding)
    assert calls == []


@pytest.mark.parametrize("direction", [V1Direction.LONG, V1Direction.SHORT])
def test_directional_analysis_is_symmetric_and_can_support_native(direction):
    source, result = _analysis(native_direction=direction, directions=(direction.value,) * 4)
    thesis = result.to_dict()["thesis"]
    assert thesis["overall"]["direction"] == direction.value
    assert thesis["overall"]["disposition"] == "SUPPORT"
    assert len(thesis["horizons"]) == 3
    assert {row["direction"] for row in thesis["horizons"]} == {direction.value}
    assert result.to_dict()["binding"]["direction"] == direction.value
    assert source.to_dict()["summary"]["binding"]["direction"] == direction.value


@pytest.mark.parametrize("native_direction,independent_direction", [
    (V1Direction.LONG, "SHORT"), (V1Direction.SHORT, "LONG"),
])
def test_strong_independent_opposition_rejects_native_without_rewriting_it(native_direction, independent_direction):
    source, result = _analysis(native_direction=native_direction,
                              directions=(independent_direction,) * 4)
    thesis = result.to_dict()["thesis"]
    assert thesis["overall"]["disposition"] == "REJECT"
    assert thesis["overall"]["direction"] == independent_direction
    assert source.to_dict()["binding"]["direction"] == native_direction.value
    assert result.to_dict()["binding"]["direction"] == native_direction.value


def test_disagreeing_timeframes_are_retained_as_distinct_horizon_findings():
    _, result = _analysis(directions=("SHORT", "SHORT", "LONG", "LONG"))
    thesis = result.to_dict()["thesis"]
    assert len(thesis["horizons"]) == 3
    assert len({row["direction"] for row in thesis["horizons"]}) > 1
    assert thesis["overall"]["disposition"] in {"CHALLENGE", "WAIT"}
    assert thesis["overall"]["reason"]


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
def test_all_scenario_styles_are_examined_and_any_available_geometry_is_signed(direction):
    _, result = _analysis(native_direction=V1Direction(direction), directions=(direction,) * 4)
    scenarios = result.to_dict()["thesis"]["scenarios"]
    assert {row["kind"] for row in scenarios} == {"IMMEDIATE", "PULLBACK", "BREAKOUT", "ALTERNATIVE"}
    assert {row["direction"] for row in scenarios} == {"LONG", "SHORT"}
    assert {row["structural_radius"] for row in scenarios} == {1, 2}
    available = [row for row in scenarios if row["state"] == "AVAILABLE"]
    assert available
    assert {row["kind"] for row in available} == {"IMMEDIATE", "PULLBACK", "BREAKOUT", "ALTERNATIVE"}
    for row in scenarios:
        assert row["limitations"]
        if row["state"] == "UNAVAILABLE":
            assert row["reason"]
            assert row["entry_zone"] is None
            assert row["stop_reference"] is None
            assert row["target_zone"] is None
            assert row["risk_reward"] is None
            continue
        assert row["state"] == "AVAILABLE"
        assert row["activation"]
        entry, stop, target, rr = row["entry_zone"], row["stop_reference"], row["target_zone"], row["risk_reward"]
        assert row["source_citations"] and entry["citations"] and stop["citations"] and target["citations"]
        assert 0 < entry["low"] <= entry["high"]
        assert 0 < target["low"] <= target["high"]
        if row["direction"] == "LONG":
            assert 0 < stop["value"] < entry["low"] <= entry["high"] < target["low"]
            risks = (entry["low"] - stop["value"], entry["high"] - stop["value"])
            rewards = (target["low"] - entry["high"], target["high"] - entry["low"])
        else:
            assert 0 < target["high"] < entry["low"] <= entry["high"] < stop["value"]
            risks = (stop["value"] - entry["high"], stop["value"] - entry["low"])
            rewards = (entry["low"] - target["high"], entry["high"] - target["low"])
        assert rr["minimum_risk"] == pytest.approx(risks[0])
        assert rr["maximum_risk"] == pytest.approx(risks[1])
        assert rr["minimum_reward"] == pytest.approx(rewards[0])
        assert rr["maximum_reward"] == pytest.approx(rewards[1])
        assert rr["conservative_ratio"] == pytest.approx(rewards[0] / risks[1])
        assert rr["conservative_ratio"] > 0


def test_missing_structure_abstains_from_scenarios_instead_of_inventing_levels():
    _, result = _analysis(no_pivots=True)
    scenarios = result.to_dict()["thesis"]["scenarios"]
    assert scenarios
    assert all(row["state"] == "UNAVAILABLE" for row in scenarios)
    assert all(row["entry_zone"] is None and row["target_zone"] is None for row in scenarios)


@pytest.mark.parametrize("missing", [("ma",), ("history",), ("volume",), ("ma", "history", "volume")])
def test_missing_facts_are_explicit_and_not_an_affirmative_native_rejection(missing):
    _, result = _analysis(missing=missing, no_pivots=True, no_atr=True)
    body = result.to_dict()
    assert body["summary"]["coverage"] == "PARTIAL"
    assert body["thesis"]["overall"]["disposition"] != "REJECT"
    assert body["thesis"]["limitations"]
    assert all(row["state"] == "UNAVAILABLE" for row in body["thesis"]["scenarios"])


@pytest.mark.parametrize("atr_args", [{"no_atr": True}, {"zero_atr": True}])
def test_missing_or_zero_atr_does_not_create_nonfinite_ratios(atr_args):
    source, result = _analysis(**atr_args)
    serialized = result.to_json()
    assert "NaN" not in serialized and "Infinity" not in serialized
    validate_result(result, source, expected_source=source.binding)
    assert result.to_dict()["thesis"]["limitations"]


def test_zero_price_and_reference_denominators_do_not_become_fabricated_geometry():
    args = _numbers(zero=True)
    requirement, native, facts = deepcopy(args)
    instrument = facts.instrument(requirement.canonical_instrument)
    frames = tuple(replace(fact,
        moving_averages=replace(fact.moving_averages, completed_count=205),
        volume_facts=replace(fact.volume_facts, current=0),
        structural_measurements=tuple(replace(series, swing_highs=(), swing_lows=())
                                     for series in fact.structural_measurements),
    ) for fact in instrument.timeframes)
    instrument = replace(instrument, timeframes=frames)
    facts = replace(facts, instruments=tuple(
        instrument if item.canonical_instrument == instrument.canonical_instrument else item
        for item in facts.instruments))
    requirement = build_native_review_requirements(native, facts)[0]
    source = build_local_input(requirement, native, facts, PUBLICATION)
    result = analyze_local(source, expected_source=source.binding)
    assert "NaN" not in result.to_json() and "Infinity" not in result.to_json()
    assert all(row["state"] == "UNAVAILABLE" for row in result.to_dict()["thesis"]["scenarios"])


def test_factual_metric_formulas_and_hourly_atr_units_are_exact():
    _, result = _analysis()
    frames = result.to_dict()["thesis"]["frame_assessments"]
    for frame in frames:
        metrics = frame["metrics"]
        assert metrics["close_vs_sma20_percent"]["value"] == pytest.approx(100 * (100 - 95) / 95)
        assert metrics["close_vs_sma50_percent"]["value"] == pytest.approx(100 * (100 - 90) / 90)
        assert metrics["close_vs_sma200_percent"]["value"] == pytest.approx(100 * (100 - 85) / 85)
        assert metrics["sma20_change_5bars_percent"]["value"] == pytest.approx(100 * (95 - 93) / 93)
        assert metrics["volume_reference_ratio"]["value"] == 2.0
        assert metrics["candle_body_percent"]["value"] == pytest.approx(100 * (100 - 98) / 98)
        assert metrics["completed_bar_range_percent"]["value"] == 10.0
        hourly = metrics["close_sma20_distance_in_1h_atr"]
        if frame["timeframe"] == "1H":
            assert hourly["value"] == 2.5
            assert "ONE_HOUR_EXTENSION_EXCEEDS_RESEARCH_IMMEDIATE_LIMIT" in frame["contradictions"]
        else:
            assert hourly["value"] is None
            assert hourly["reason"] == "ONE_HOUR_ONLY"
        assert metrics["return_5_completed_bars_percent"]["state"] == "UNAVAILABLE"
        assert frame["visual_conclusions"] == {"Q3": "UNKNOWN", "Q5": "UNKNOWN", "Q10": "UNKNOWN"}
        for structure in frame["domains"]["structure"]["alternatives"]:
            for name, price in (("latest_low", 90.0), ("latest_high", 130.0)):
                pivot = structure[name]
                assert pivot["close_distance_percent"]["value"] == pytest.approx(100 * (100 - price) / price)
                normalized = pivot["close_distance_in_1h_atr"]
                if frame["timeframe"] == "1H":
                    assert normalized["value"] == (100 - price) / 2.0
                else:
                    assert normalized["value"] is None and normalized["reason"] == "ONE_HOUR_ONLY"


def _with_history(*, falling=False):
    requirement, native, facts = _case()
    instrument = facts.instrument(requirement.canonical_instrument)
    retained = []
    for frame in instrument.timeframes:
        latest = CompletedTimeframeBar.from_fact(frame)
        for index in range(6):
            if index == 5:
                retained.append(latest)
                continue
            offset = timedelta(days=5-index)
            close = 110.0 - index * 2.0 if falling else 90.0 + index * 2.0
            retained.append(replace(latest,
                observation_boundary=latest.observation_boundary - offset,
                source_timestamp=latest.source_timestamp - offset,
                source_market_data_boundary=latest.source_market_data_boundary - offset,
                open=close-1.0, high=close+2.0, low=close-2.0, close=close))
    instrument = replace(instrument, completed_series=tuple(retained))
    facts = replace(facts, instruments=tuple(
        instrument if item.canonical_instrument == instrument.canonical_instrument else item
        for item in facts.instruments))
    return requirement, native, facts


@pytest.mark.parametrize("falling", [False, True])
def test_retained_five_bar_return_and_ma_momentum_agreement_are_distinct(falling):
    source = build_local_input(*_with_history(falling=falling), PUBLICATION)
    result = analyze_local(source, expected_source=source.binding)
    for frame in result.to_dict()["thesis"]["frame_assessments"]:
        prior = 110.0 if falling else 90.0
        metric = frame["metrics"]["return_5_completed_bars_percent"]
        assert metric["value"] == pytest.approx(100 * (100 - prior) / prior)
        assert len(metric["citations"]) == 2
        momentum = frame["domains"]["momentum"]
        assert momentum["direction"] == ("NEUTRAL" if falling else "LONG")
        assert momentum["reason"] == ("PRICE_RETURN_AND_MA_CHANGE_CONFLICT" if falling else "PRICE_RETURN_AND_MA_CHANGE_AGREE")
        if falling:
            assert "PRICE_RETURN_AND_MA_CHANGE_CONFLICT" in frame["contradictions"]


def test_consumed_history_changes_input_identity_even_when_latest_owner_identity_is_unchanged():
    source = build_local_input(*_with_history(), PUBLICATION)
    body = source.to_dict()
    earlier = body["source_evidence"]["completed_series"][0]["bars"][0]
    earlier["close"] += 0.5
    changed = decode_input(_rehash_input(body))
    assert changed.identity != source.identity
    assert changed.to_dict()["binding"] == source.to_dict()["binding"]
    with pytest.raises(ValueError, match="NSE_LOCAL_SOURCE_STALE"):
        analyze_local(changed, expected_source=source.binding)


def test_horizon_session_ranges_preserve_existing_wo12_observation_contract():
    _, result = _analysis()
    horizons = result.to_dict()["thesis"]["horizons"]
    assert {row["identity"]: row["trading_sessions"] for row in horizons} == {
        "SHORT": [1, 3], "MEDIUM": [4, 10], "LONGER": [11, 20],
    }
    assert all("NO_CHANGE_TO_EXISTING_WO12_HORIZONS" in row["limitations"] for row in horizons)
    assert "win_probability" not in result.to_json()


def test_opposing_pivot_definitions_remain_visible_without_silent_preference():
    requirement, native, facts = _case()
    instrument = facts.instrument(requirement.canonical_instrument)
    frames = []
    for frame in instrument.timeframes:
        first, second = frame.structural_measurements
        changed = replace(second,
            swing_highs=tuple(replace(pivot, value=value)
                             for pivot, value in zip(second.swing_highs, (130.0, 110.0))),
            swing_lows=tuple(replace(pivot, value=value)
                            for pivot, value in zip(second.swing_lows, (70.0, 60.0))))
        frames.append(replace(frame, structural_measurements=(first, changed)))
    instrument = replace(instrument, timeframes=tuple(frames))
    facts = replace(facts, instruments=tuple(
        instrument if item.canonical_instrument == instrument.canonical_instrument else item
        for item in facts.instruments))
    requirement = build_native_review_requirements(native, facts)[0]
    source = build_local_input(requirement, native, facts, PUBLICATION)
    result = analyze_local(source, expected_source=source.binding)
    for frame in result.to_dict()["thesis"]["frame_assessments"]:
        structure = frame["domains"]["structure"]
        assert structure["conflict"] is True
        assert structure["direction"] == "NEUTRAL"
        assert [row["direction"] for row in structure["alternatives"]] == ["LONG", "SHORT"]
        assert "STRUCTURAL_RADIUS_DISAGREEMENT" in frame["contradictions"]


@pytest.mark.parametrize("direction,equal", [("LONG", False), ("SHORT", False), ("LONG", True), ("SHORT", True)])
def test_completed_close_structural_breach_is_distinct_from_historical_pivot_sequence(direction, equal):
    requirement, native, facts = _case(directions=(direction,) * 4)
    instrument = facts.instrument(requirement.canonical_instrument)
    frames = []
    for frame in instrument.timeframes:
        series_rows = []
        for series in frame.structural_measurements:
            if direction == "LONG":
                lows = (*series.swing_lows[:-1], replace(series.swing_lows[-1], value=100.0 if equal else 110.0))
                series_rows.append(replace(series, swing_lows=lows))
            else:
                highs = (*series.swing_highs[:-1], replace(series.swing_highs[-1], value=100.0 if equal else 90.0))
                series_rows.append(replace(series, swing_highs=highs))
        frames.append(replace(frame, structural_measurements=tuple(series_rows)))
    instrument = replace(instrument, timeframes=tuple(frames))
    facts = replace(facts, instruments=tuple(
        instrument if item.canonical_instrument == instrument.canonical_instrument else item
        for item in facts.instruments))
    requirement = build_native_review_requirements(native, facts)[0]
    source = build_local_input(requirement, native, facts, PUBLICATION)
    result = analyze_local(source, expected_source=source.binding)
    reason = ("BULLISH_SEQUENCE_LATEST_LOW_BREACHED_BY_COMPLETED_CLOSE" if direction == "LONG"
              else "BEARISH_SEQUENCE_LATEST_HIGH_BREACHED_BY_COMPLETED_CLOSE")
    for frame in result.to_dict()["thesis"]["frame_assessments"]:
        structure = frame["domains"]["structure"]
        # Breaching a prior swing invalidates that sequence's directional vote;
        # the breach alone cannot certify a complete opposite trend.
        assert structure["direction"] == (direction if equal else "NEUTRAL")
        for row in structure["alternatives"]:
            assert row["pivot_sequence_direction"] == direction
            assert row["completed_close_breach"] == (None if equal else reason)


def test_trend_and_momentum_cannot_overrule_their_breached_protective_structure():
    requirement, native, facts = _with_history()
    instrument = facts.instrument(requirement.canonical_instrument)
    frames = tuple(replace(frame, structural_measurements=tuple(
        replace(series, swing_lows=(*series.swing_lows[:-1], replace(series.swing_lows[-1], value=110.0)))
        for series in frame.structural_measurements)) for frame in instrument.timeframes)
    instrument = replace(instrument, timeframes=frames)
    facts = replace(facts, instruments=tuple(
        instrument if item.canonical_instrument == instrument.canonical_instrument else item
        for item in facts.instruments))
    requirement = build_native_review_requirements(native, facts)[0]
    source = build_local_input(requirement, native, facts, PUBLICATION)
    result = analyze_local(source, expected_source=source.binding)
    for frame in result.to_dict()["thesis"]["frame_assessments"]:
        assert frame["domains"]["trend"]["direction"] == "LONG"
        assert frame["domains"]["momentum"]["direction"] == "LONG"
        assert frame["domains"]["structure"]["direction"] == "NEUTRAL"
        assert frame["direction"] == "NEUTRAL"
        assert frame["direction_reason"] == "PROTECTIVE_STRUCTURE_BREACH_CONTRADICTS_DIRECTION"


def test_canonical_atr_analysis_boundary_is_preserved_without_invented_lower_bound():
    from kronos.application.swing_mtf_facts import _one_hour_atr_fact
    from kronos.provider.contracts.market_data import HistoricalCandle

    requirement, native, facts = _full_history()
    instrument = facts.instrument(requirement.canonical_instrument)
    hourly = instrument.fact(FactualTimeframe.ONE_HOUR)
    candles = tuple(HistoricalCandle(bar.source_timestamp, bar.open, bar.high,
        bar.low, bar.close, bar.volume)
        for bar in instrument.completed_bars(FactualTimeframe.ONE_HOUR))
    # The actual owner accepts a supplied day anchor earlier than the completed
    # hourly observation. Retain its calculated value and exact source bindings.
    atr = _one_hour_atr_fact(run_identity=facts.run_identity,
        canonical_instrument=instrument.canonical_instrument,
        analysis_boundary=hourly.observation_boundary.replace(
            hour=0, minute=0, second=0, microsecond=0),
        one_hour_fact=hourly, completed_hourly=candles)
    assert atr.value == instrument.one_hour_atr.value
    instrument = replace(instrument, one_hour_atr=atr)
    facts = replace(facts, instruments=tuple(
        instrument if item.canonical_instrument == instrument.canonical_instrument else item
        for item in facts.instruments))
    requirement = build_native_review_requirements(native, facts)[0]
    assert atr.analysis_boundary < atr.observation_boundary
    source = build_local_input(requirement, native, facts, PUBLICATION)
    assert source.to_dict()["summary"]["atr"]["analysis_boundary"] == atr.analysis_boundary.isoformat()
    assert source.to_dict()["summary"]["atr"]["observed_boundary"] == atr.observation_boundary.isoformat()
    result = analyze_local(source, expected_source=source.binding)
    validate_result(result, source, expected_source=source.binding)


@pytest.mark.parametrize("field", ["analysis_boundary", "observation_boundary", "source_market_data_boundary"])
def test_atr_future_cutoff_or_wrong_exact_completed_binding_still_fails(field):
    requirement, native, facts = deepcopy(_inputs())
    atr = facts.instrument(requirement.canonical_instrument).one_hour_atr
    replacement = facts.observed_at + timedelta(days=1) if field == "analysis_boundary" else getattr(atr, field) - timedelta(days=1)
    object.__setattr__(atr, field, replacement)
    object.__setattr__(atr, "integrity_sha256", one_hour_atr_integrity_sha256(atr))
    with pytest.raises(ValueError):
        build_local_input(requirement, native, facts, PUBLICATION)


def _full_history():
    """Use existing owner arithmetic on 205 labelled synthetic retained bars."""
    from kronos.application.swing_mtf_facts import (
        _moving_average_facts, _one_hour_atr_fact, _volume_facts,
    )
    from kronos.provider.contracts.market_data import HistoricalCandle

    requirement, native, facts = _case()
    instrument = facts.instrument(requirement.canonical_instrument)
    retained, frames, candles_by_timeframe = [], [], {}
    for frame in instrument.timeframes:
        latest = CompletedTimeframeBar.from_fact(frame)
        bars = []
        for index in range(205):
            if index == 204:
                bars.append(latest)
            else:
                offset = timedelta(days=204-index)
                close = 80.0 + index * 0.1
                bars.append(replace(latest,
                    observation_boundary=latest.observation_boundary-offset,
                    source_timestamp=latest.source_timestamp-offset,
                    source_market_data_boundary=latest.source_market_data_boundary-offset,
                    open=close-1.0, high=close+2.0, low=close-2.0, close=close))
        candles = tuple(HistoricalCandle(bar.source_timestamp, bar.open, bar.high,
            bar.low, bar.close, bar.volume) for bar in bars)
        candles_by_timeframe[frame.timeframe] = candles
        frames.append(replace(frame, moving_averages=_moving_average_facts(candles),
                              volume_facts=_volume_facts(candles)))
        retained.extend(bars)
    atr = _one_hour_atr_fact(run_identity=facts.run_identity,
        canonical_instrument=instrument.canonical_instrument,
        analysis_boundary=instrument.one_hour_atr.analysis_boundary,
        one_hour_fact=frames[-1],
        completed_hourly=candles_by_timeframe[FactualTimeframe.ONE_HOUR])
    instrument = replace(instrument, timeframes=tuple(frames), one_hour_atr=atr,
                         completed_series=tuple(retained))
    facts = replace(facts, instruments=tuple(
        instrument if item.canonical_instrument == instrument.canonical_instrument else item
        for item in facts.instruments))
    return build_native_review_requirements(native, facts)[0], native, facts


def test_full_retained_history_agrees_with_existing_owner_ma_volume_and_arithmetic_atr():
    requirement, native, facts = _full_history()
    source = build_local_input(requirement, native, facts, PUBLICATION)
    assert all(len(row["bars"]) == 205 for row in source.to_dict()["source_evidence"]["completed_series"])
    result = analyze_local(source, expected_source=source.binding)
    assert result.to_dict()["summary"] == build_nse_technical_summary(requirement, native, facts, PUBLICATION)
    validate_result(result, source, expected_source=source.binding)


@pytest.mark.parametrize("field", [
    "sma20", "sma50", "sma200", "prior_sma20_5bars", "prior_sma50_5bars",
    "prior_sma200_5bars", "volume_reference", "atr", "sample_count",
])
def test_rebound_rehashed_indicator_forgery_is_rejected_against_exact_retained_history(field):
    requirement, native, facts = _full_history()
    original = build_local_input(requirement, native, facts, PUBLICATION)
    instrument = facts.instrument(requirement.canonical_instrument)
    frames = list(instrument.timeframes)
    atr = instrument.one_hour_atr
    if field == "atr":
        atr = deepcopy(atr)
        object.__setattr__(atr, "value", atr.value + 1.0)
        object.__setattr__(atr, "integrity_sha256", one_hour_atr_integrity_sha256(atr))
    elif field == "volume_reference":
        frames[0] = replace(frames[0], volume_facts=replace(frames[0].volume_facts,
            prior_20_mean=frames[0].volume_facts.prior_20_mean + 1.0))
    elif field == "sample_count":
        frames[0] = replace(frames[0], moving_averages=replace(frames[0].moving_averages,
            completed_count=204, prior_sma200_5bars=None))
    else:
        frames[0] = replace(frames[0], moving_averages=replace(frames[0].moving_averages,
            **{field: getattr(frames[0].moving_averages, field) + 1.0}))
    instrument = replace(instrument, timeframes=tuple(frames), one_hour_atr=atr)
    facts = replace(facts, instruments=tuple(
        instrument if item.canonical_instrument == instrument.canonical_instrument else item
        for item in facts.instruments))
    requirement = build_native_review_requirements(native, facts)[0]
    summary = build_nse_technical_summary(requirement, native, facts, PUBLICATION)
    body = original.to_dict()
    body["binding"] = summary["binding"]
    body["summary"] = summary
    body["source_evidence"]["thesis"] = _primitive(requirement.thesis)
    body["source_evidence"]["timeframes"] = [_json_value(asdict(frame)) for frame in frames]
    body["source_evidence"]["atr"] = _json_value(asdict(atr))
    # Every digest, requirement, latest fact and summary agrees with the forged
    # indicator. Only comparison with exact retained historical candles exposes it.
    with pytest.raises(ValueError):
        decode_input(_rehash_input(body))


def test_available_history_does_not_fill_unavailable_owner_indicators():
    requirement, native, facts = _full_history()
    instrument = facts.instrument(requirement.canonical_instrument)
    frames = tuple(replace(frame,
        moving_averages=FactualMovingAverageFacts(205, None, None, None, None, None, None),
        volume_facts=FactualVolumeFacts(frame.volume, None)) for frame in instrument.timeframes)
    atr = deepcopy(instrument.one_hour_atr)
    object.__setattr__(atr, "value", None)
    object.__setattr__(atr, "availability", OneHourAtrAvailability.UNAVAILABLE)
    object.__setattr__(atr, "unavailable_reason", "RETAINED_OWNER_UNAVAILABLE")
    object.__setattr__(atr, "integrity_sha256", one_hour_atr_integrity_sha256(atr))
    instrument = replace(instrument, timeframes=frames, one_hour_atr=atr)
    facts = replace(facts, instruments=tuple(
        instrument if item.canonical_instrument == instrument.canonical_instrument else item
        for item in facts.instruments))
    requirement = build_native_review_requirements(native, facts)[0]
    source = build_local_input(requirement, native, facts, PUBLICATION)
    result = analyze_local(source, expected_source=source.binding)
    assert result.to_dict()["summary"]["atr"]["value"] is None
    for frame in result.to_dict()["thesis"]["frame_assessments"]:
        assert frame["metrics"]["close_vs_sma20_percent"]["value"] is None
        assert frame["metrics"]["volume_reference_ratio"]["value"] is None
        assert frame["metrics"]["return_5_completed_bars_percent"]["value"] is not None


def test_every_emitted_citation_resolves_to_exact_immutable_input_value():
    source = build_local_input(*_full_history(), PUBLICATION)
    result = analyze_local(source, expected_source=source.binding)
    payload = result.to_dict()
    source_references = payload["source_references"]
    references = set()

    def collect(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"citations", "source_citations"}:
                    references.update(child)
                else:
                    collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(payload["thesis"])
    assert references
    for reference in references:
        retained = source_references[reference]
        pointer = retained["input_pointer"]
        assert pointer.startswith("/")
        value = source.to_dict()
        for segment in pointer[1:].split("/"):
            key = segment.replace("~1", "/").replace("~0", "~")
            value = value[int(key)] if isinstance(value, list) else value[key]
        assert value == retained["value"]
        if reference.startswith(("frames.", "history.")):
            assert retained["timeframe"] == reference.split(".")[1].split("[")[0]
        else:
            assert reference == "atr.1H.value" and retained["timeframe"] == "1H"
