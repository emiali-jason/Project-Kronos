"""WO-06B exact source integrity, governed sessions and historical replay."""
from copy import copy
from dataclasses import fields, replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path

import pytest

from kronos.intraday.candles import expected_candle_boundaries
from kronos.intraday.completed_evidence import EvidenceSessionRole, build_completed_evidence_selection
from kronos.intraday.contracts import IntradayTimeframe as TF
from kronos.intraday.historical_semantic import create_governed_historical_candle_payload
from kronos.intraday.market_context import CurrentMarketCalendarScheduleSource
from kronos.intraday.nifty_relative_context import build_nifty_relative_context, NiftyRelationship
from kronos.intraday.opening_semantic import build_opening_semantic_evidence
from kronos.intraday.probables_v2 import build_semantic_qualification_evidence_v2, create_probables_v2_methodology
from kronos.intraday.probables_v2_persistence import _artifact_bytes, _artifact_from_bytes
from kronos.intraday.qualification import PreviousCompletedDailyCandle, create_narrow_cpr_fact
from kronos.intraday.source_binding import SourceBindingError, require_cpr_source_binding
from kronos.market.calendar import MarketCalendarPublisher
from tests.unit.intraday.test_probables_v2 import (
    CURRENT_DAY, PREVIOUS_DAY, IST, OPEN, PROVENANCE, _candle, _schedule,
    _opening_inputs, _later_mapping, _narrow_from_daily,
)
from tests.unit.intraday.test_opening_admission_correction import opening_mapping, run_mapping


def reseal_candle(candle, **changes):
    names = {f.name for f in fields(candle)} - {
        "candle_identity", "integrity_identity", "schema_identity", "schema_version",
        "completion_state", "available_at",
    }
    values = {name: getattr(candle, name) for name in names}
    return create_governed_historical_candle_payload(**(values | changes))


def relative_inputs(subject="NSE-EQ-RELIANCE", direction="LONG"):
    schedule = _schedule(CURRENT_DAY)
    start = datetime.combine(CURRENT_DAY, OPEN, IST)
    boundary = start + timedelta(minutes=15)
    return dict(
        canonical_subject_identity=subject, subject_exchange="NSE", opening_direction=direction,
        analysis_boundary=boundary, subject_schedule=schedule, benchmark_schedule=schedule,
        subject_candle=_candle(subject, schedule, TF.FIFTEEN_MINUTES, start,
            close="103" if direction == "LONG" else "97", observation_boundary=boundary),
        benchmark_candle=_candle("NSE-INDEX-NIFTY", schedule, TF.FIFTEEN_MINUTES, start,
            close="101" if direction == "LONG" else "99", observation_boundary=boundary),
        subject_session_open=Decimal("100"), benchmark_session_open=Decimal("100"),
        provenance=PROVENANCE,
    )


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
@pytest.mark.parametrize("subject", ["NSE-EQ-RELIANCE", "NSE-INDEX-BANKNIFTY", "RELIANCE"])
def test_exact_subject_and_separate_benchmark(direction, subject):
    result = build_nifty_relative_context(**relative_inputs(subject, direction))
    assert result.relationship is NiftyRelationship.SUPPORTING
    assert result.fact.canonical_subject_identity == subject
    assert result.fact.benchmark_identity == "NSE-INDEX-NIFTY"
    assert result.schema_version == result.fact.schema_version == "1.1.0"
    assert _artifact_from_bytes(_artifact_bytes(result)) == result


@pytest.mark.parametrize("actual", ["NSE-EQ-HDFCBANK", "RELIANCE", "nse-eq-reliance", "NSE-INDEX-NIFTY"])
def test_wrong_subject_rejected_even_with_same_values_or_provider_label(actual):
    args = relative_inputs()
    args["subject_candle"] = reseal_candle(args["subject_candle"],
        canonical_subject_identity=actual, provider_source_identity="RELIANCE")
    result = build_nifty_relative_context(**args)
    assert result.relationship is NiftyRelationship.UNAVAILABLE
    assert result.fact.reason.value == "SUBJECT_IDENTITY_INVALID"


@pytest.mark.parametrize("field,value,reason", [
    ("canonical_subject_identity", "NSE-EQ-HDFCBANK", "BENCHMARK_IDENTITY_INVALID"),
    ("provider_source_identity", "NSE-INDEX-NIFTY", None),
])
def test_benchmark_has_independent_canonical_authority(field, value, reason):
    args = relative_inputs()
    args["benchmark_candle"] = reseal_candle(args["benchmark_candle"], **{field:value})
    result = build_nifty_relative_context(**args)
    if reason:
        assert result.fact.reason.value == reason
    else:
        assert result.relationship is NiftyRelationship.SUPPORTING


@pytest.mark.parametrize("field,value", [
    ("canonical_subject_identity", ""), ("candle_identity", "OTHER"),
    ("integrity_identity", "INTEGRITY-OTHER"), ("source_operation_identity", ""),
    ("provenance", ()), ("close", Decimal("999")),
])
def test_missing_or_tampered_candle_provenance_fails_closed(field, value):
    args = relative_inputs()
    bad = copy(args["subject_candle"])
    object.__setattr__(bad, field, value)
    args["subject_candle"] = bad
    result = build_nifty_relative_context(**args)
    assert result.fact.reason.value == "SOURCE_INTEGRITY_INVALID"
    assert result.relationship is NiftyRelationship.UNAVAILABLE


@pytest.mark.parametrize("missing", ["subject_candle", "benchmark_candle", "subject_schedule", "benchmark_schedule"])
def test_missing_required_sources_or_schedule_proof_is_unavailable(missing):
    args = relative_inputs()
    args[missing] = None
    assert build_nifty_relative_context(**args).relationship is NiftyRelationship.UNAVAILABLE


def test_clock_equality_without_exact_schedule_session_binding_rejected():
    args = relative_inputs()
    args["subject_schedule"] = replace(args["subject_schedule"], session_id="OTHER-SESSION")
    assert build_nifty_relative_context(**args).relationship is NiftyRelationship.UNAVAILABLE


def test_caller_supplied_open_cannot_override_source():
    args = relative_inputs()
    args["subject_session_open"] = Decimal("90")
    assert build_nifty_relative_context(**args).relationship is NiftyRelationship.UNAVAILABLE


def test_published_distinct_nse_equity_and_nifty_sessions_are_compatible():
    boundary = datetime(2026, 8, 18, 9, 30, tzinfo=IST)
    args = relative_inputs("RELIANCE")
    for key, symbol, close in [("subject", "RELIANCE", "103"), ("benchmark", "NIFTY", "101")]:
        source = CurrentMarketCalendarScheduleSource(MarketCalendarPublisher(),
            observed_at=boundary, canonical_instrument_id=symbol)
        schedule = source.schedule_for("NSE", boundary.date())
        args[key+"_schedule"] = schedule
        args[key+"_candle"] = _candle("RELIANCE" if key == "subject" else "NSE-INDEX-NIFTY",
            schedule, TF.FIFTEEN_MINUTES, schedule.windows[0].opens_at,
            close=close, observation_boundary=boundary)
    args["analysis_boundary"] = boundary
    assert args["subject_schedule"].session_id != args["benchmark_schedule"].session_id
    assert build_nifty_relative_context(**args).relationship is NiftyRelationship.SUPPORTING


def test_nifty_self_reference_needs_no_benchmark():
    args = relative_inputs("NSE-INDEX-NIFTY")
    args.update(subject_candle=None, benchmark_candle=None, subject_schedule=None, benchmark_schedule=None)
    assert build_nifty_relative_context(**args).relationship is NiftyRelationship.NOT_APPLICABLE


def cpr_for(selection, **changes):
    daily = selection.candles(TF.DAILY, EvidenceSessionRole.PREVIOUS_SESSION_DAILY)[0]
    values = dict(canonical_subject_identity=daily.canonical_subject_identity,
        previous_session_identity=daily.market_session_identity,
        observation_session_identity=selection.current_market_session_identity,
        source_daily_candle_identity=daily.candle_identity, completed_at=daily.available_at,
        observation_boundary=selection.analysis_boundary, high=daily.high, low=daily.low, close=daily.close,
        completed=True, source_integrity_identity=daily.integrity_identity, provenance=PROVENANCE)
    return create_narrow_cpr_fact(PreviousCompletedDailyCandle(**(values | changes)))


@pytest.mark.parametrize("phase", ["OPENING", "STRUCTURE", "ESTABLISHED"])
def test_exact_cpr_source_and_same_session_reuse(phase):
    opening = _opening_inputs()[0]
    selection = opening if phase == "OPENING" else _later_mapping(2, 0, boundary=datetime.combine(CURRENT_DAY,time(10,30),IST)).completed_evidence if phase == "STRUCTURE" else _later_mapping(8, 2, boundary=datetime.combine(CURRENT_DAY,time(12,0),IST)).completed_evidence
    # Identical Daily source identity is required; later fixture uses its own
    # observation envelope, so reuse the early observation on the SAME source.
    fact = cpr_for(selection, observation_boundary=opening.analysis_boundary)
    require_cpr_source_binding(selection, fact)
    if phase != "OPENING":
        evidence = build_semantic_qualification_evidence_v2(selection=selection,
            narrow_cpr_fact=fact, participation_state="AVAILABLE_SUPPORTING_NON_BLOCKING", provenance=PROVENANCE)
        assert evidence.schema_version == "2.1.0"


@pytest.mark.parametrize("changes", [
    {"previous_session_identity":"NSE:2026-08-25:NONSTANDARD"},
    {"previous_session_identity":"NSE:2026-08-31:NONSTANDARD"},
    {"canonical_subject_identity":"NSE-EQ-HDFCBANK"},
    {"observation_session_identity":"OTHER-SESSION"},
    {"source_daily_candle_identity":"OTHER-DAILY-SAME-VALUES"},
    {"source_integrity_identity":"INTEGRITY-OTHER"},
])
@pytest.mark.parametrize("phase", ["OPENING", "STRUCTURE"])
def test_valid_but_wrong_cpr_source_is_not_informational(changes, phase):
    selection = _opening_inputs()[0] if phase == "OPENING" else _later_mapping(2, 0, boundary=datetime.combine(CURRENT_DAY,time(10,30),IST)).completed_evidence
    wrong = cpr_for(selection, **changes)
    assert wrong.narrow_cpr_kgs_v0 == cpr_for(selection).narrow_cpr_kgs_v0
    with pytest.raises(SourceBindingError, match="CPR_SOURCE_BINDING_MISMATCH"):
        require_cpr_source_binding(selection, wrong)


@pytest.mark.parametrize("field,value", [("source_daily_candle_identity", ""),
    ("source_integrity_identity", ""), ("integrity_identity", "INTEGRITY-TAMPERED"),
    ("previous_daily_close", Decimal("999")), ("provenance", ())])
def test_tampered_cpr_or_missing_provenance_rejected(field, value):
    selection = _opening_inputs()[0]
    bad = copy(cpr_for(selection))
    object.__setattr__(bad, field, value)
    with pytest.raises(SourceBindingError, match="CPR_SOURCE_INTEGRITY_INVALID"):
        require_cpr_source_binding(selection, bad)


@pytest.mark.parametrize("builder", ["OPENING", "SEMANTIC"])
def test_both_assessment_builders_reject_wrong_daily(builder):
    selection, relative, opening, _, _ = _opening_inputs()
    wrong = cpr_for(selection, source_daily_candle_identity="D-2")
    with pytest.raises(SourceBindingError, match="CPR_SOURCE_BINDING_MISMATCH"):
        if builder == "OPENING":
            build_opening_semantic_evidence(selection=selection, narrow_cpr_fact=wrong,
                nifty_relative_evidence=relative, provenance=PROVENANCE)
        else:
            build_semantic_qualification_evidence_v2(selection=selection, narrow_cpr_fact=wrong,
                opening_semantic=opening, nifty_relative=relative, provenance=PROVENANCE)


def test_relative_fact_must_bind_exact_selected_opening_candle():
    selection, relative, _, _, _ = _opening_inputs()
    args = relative_inputs()
    args["subject_candle"] = reseal_candle(args["subject_candle"], source_operation_identity="OTHER-OPERATION")
    other = build_nifty_relative_context(**args)
    with pytest.raises(SourceBindingError, match="RELATIVE_SOURCE_BINDING_MISMATCH"):
        build_opening_semantic_evidence(selection=selection, narrow_cpr_fact=cpr_for(selection),
            nifty_relative_evidence=other, provenance=PROVENANCE)


@pytest.mark.parametrize("day,previous", [(date(2026,8,24),date(2026,8,21)), (date(2026,1,27),date(2026,1,23))])
def test_domain008_weekend_and_exchange_holiday_previous_daily(day, previous):
    boundary = datetime.combine(day, time(9,30), IST)
    source = CurrentMarketCalendarScheduleSource(MarketCalendarPublisher(),
        observed_at=datetime(2026,9,7,12,tzinfo=IST), canonical_instrument_id="RELIANCE")
    current = source.schedule_for("NSE", day)
    prior = source.previous_trading_schedule("NSE", day)
    assert prior.trading_date == previous
    def candles(schedule, tf):
        return tuple(create_governed_historical_candle_payload(
            canonical_subject_identity="RELIANCE", exchange="NSE", market_identity="NSE",
            market_session_identity=schedule.session_id, timeframe=tf, candle_start=i.start,
            candle_end=i.end, open=Decimal("100"),high=Decimal("101"),low=Decimal("99"),
            close=Decimal("100"),volume=100,observation_boundary=boundary,
            provider_source_identity="FIXTURE",source_operation_identity="WO06B-OFFLINE",provenance=PROVENANCE)
            for i in expected_candle_boundaries(schedule,tf) if i.end<=boundary)
    selection = build_completed_evidence_selection(canonical_subject_identity="RELIANCE",analysis_boundary=boundary,
        current_schedule=current,previous_schedule=prior, previous_daily=candles(prior,TF.DAILY),
        previous_one_hour=candles(prior,TF.ONE_HOUR),current_one_hour=(),
        current_fifteen_minute=candles(current,TF.FIFTEEN_MINUTES),current_five_minute=candles(current,TF.FIVE_MINUTES),provenance=PROVENANCE)
    require_cpr_source_binding(selection,cpr_for(selection))
    assert len(selection.candles(TF.FIVE_MINUTES)) == 3


GOLDEN = json.loads(Path(__file__).with_name("wo06b_pre_binding_2_2_golden.json").read_text())
@pytest.mark.parametrize("key", sorted(GOLDEN))
def test_pre_binding_2_2_historical_bytes_unchanged(key):
    direction, prior, five, nifty = key.split("|")
    methodology = create_probables_v2_methodology()
    mapping = opening_mapping(methodology,direction,prior,five,nifty,source_binding_version="1.0.0")
    run = run_mapping(mapping,methodology)
    assert run.run_identity == GOLDEN[key]["run_identity"]
    assert sha256(_artifact_bytes(run)).hexdigest() == GOLDEN[key]["artifact_sha256"]


def test_one_immutable_cpr_fact_reused_across_opening_and_structure():
    opening, _, _, _, _ = _opening_inputs()
    later = _later_mapping(2, 0, boundary=datetime.combine(CURRENT_DAY,time(10,30),IST)).completed_evidence
    daily = opening.candles(TF.DAILY, EvidenceSessionRole.PREVIOUS_SESSION_DAILY)
    selection = build_completed_evidence_selection(
        canonical_subject_identity=opening.canonical_subject_identity, analysis_boundary=later.analysis_boundary,
        current_schedule=_schedule(CURRENT_DAY), previous_schedule=_schedule(PREVIOUS_DAY), previous_daily=daily,
        previous_one_hour=later.candles(TF.ONE_HOUR, EvidenceSessionRole.PRIOR_SESSION_1H_CONTEXT),
        current_one_hour=(), current_fifteen_minute=later.candles(TF.FIFTEEN_MINUTES),
        current_five_minute=later.candles(TF.FIVE_MINUTES), provenance=PROVENANCE)
    fact = cpr_for(opening)
    require_cpr_source_binding(opening,fact)
    require_cpr_source_binding(selection,fact)
    evidence = build_semantic_qualification_evidence_v2(selection=selection,narrow_cpr_fact=fact,
        participation_state="AVAILABLE_SUPPORTING_NON_BLOCKING",provenance=PROVENANCE)
    assert _artifact_from_bytes(_artifact_bytes(evidence)) == evidence


@pytest.mark.parametrize("day", [date(2026,8,25),date(2026,8,31)])
def test_actual_older_or_future_daily_cannot_supply_equal_cpr(day):
    selection = _opening_inputs()[0]
    schedule = _schedule(day)
    observed = max(selection.analysis_boundary,datetime.combine(day,time(17),IST))
    daily = _candle(selection.canonical_subject_identity,schedule,TF.DAILY,
        datetime.combine(day,OPEN,IST),close="100",observation_boundary=observed)
    wrong = _narrow_from_daily(daily,selection.current_market_session_identity,observed)
    assert wrong.pivot == cpr_for(selection).pivot
    with pytest.raises(SourceBindingError,match="CPR_SOURCE_BINDING_MISMATCH"):
        require_cpr_source_binding(selection,wrong)


@pytest.mark.parametrize("which", ["OPENING", "RELATIVE"])
def test_semantic_builder_revalidates_nested_source_integrity(which):
    selection, relative, opening, _, _ = _opening_inputs()
    target = copy(opening if which == "OPENING" else relative)
    object.__setattr__(target,"integrity_identity","INTEGRITY-TAMPERED")
    with pytest.raises(SourceBindingError,match="SEMANTIC_V2_SOURCE_INTEGRITY_INVALID"):
        build_semantic_qualification_evidence_v2(selection=selection,narrow_cpr_fact=cpr_for(selection),
            opening_semantic=target if which == "OPENING" else opening,
            nifty_relative=target if which == "RELATIVE" else relative,provenance=PROVENANCE)


def test_mapper_wrong_cpr_member_is_unavailable_and_other_members_survive(tmp_path):
    from tests.unit.intraday.test_probables_v2_refresh_control import _control, _payload
    from kronos.intraday.probables_v2_diagnostics import reconstruct_v2_execution, replay_v2_mapping
    from kronos.intraday.probables_v2_refresh import map_discovery_execution_to_probables_v2
    boundary = datetime(2026,8,24,9,35,tzinfo=IST)
    _, composition, control, _, mock_requests = _control(tmp_path,boundary=boundary)
    result = control.execute_document(_payload("SOURCE-BINDING-OFFLINE",boundary=boundary))
    envelope = composition.probables_v2_diagnostics_store.load_envelope(result["replay_envelope_identity"])
    assert envelope.mapping_policy_version == "2.1.0"
    good = replay_v2_mapping(envelope)
    execution = reconstruct_v2_execution(envelope)
    first = copy(execution.probables_v2_facts[0])
    selection = next(m.completed_evidence for m in good.member_evidence if m.canonical_subject_identity==first.canonical_subject_identity)
    previous = copy(first.previous_session_facts)
    # Exercise the mapper seam with an upstream payload whose independently
    # valid CPR names another Daily; no hashes or production files are rewritten.
    object.__setattr__(previous,"narrow_cpr",cpr_for(selection,source_daily_candle_identity="OLDER-DAILY"))
    object.__setattr__(first,"previous_session_facts",previous)
    changed = replace(execution,probables_v2_facts=(first,*execution.probables_v2_facts[1:]))
    reads = mock_requests[0]
    bad = map_discovery_execution_to_probables_v2(execution=changed,reconciliation=envelope.reconciliation)
    rejected = next(m for m in bad.unavailable_members if m.canonical_subject_identity==first.canonical_subject_identity)
    assert "CPR_SOURCE_BINDING_MISMATCH" in rejected.provenance
    assert rejected.reason.value == "MANDATORY_EVIDENCE_UNAVAILABLE"
    assert {m.canonical_subject_identity for m in bad.member_evidence} == {m.canonical_subject_identity for m in good.member_evidence}-{first.canonical_subject_identity}
    assert mock_requests[0] == reads
    from kronos.intraday.probables_v2 import evaluate_probables_v2_run
    source = envelope.discovery_run
    run = evaluate_probables_v2_run(source_discovery_run_identity=source.run_identity,
        universe_identity=source.universe_identity,universe_version=source.universe_version,
        reconciliation_identity=source.reconciliation_identity,reconciliation_version=source.reconciliation_version,
        market_session_identity=source.market_session_identity,analysis_boundary=source.observation_boundary,
        member_evidence=bad.member_evidence,unavailable_members=bad.unavailable_members,provenance=PROVENANCE)
    assert _artifact_from_bytes(_artifact_bytes(run)) == run
    assert all(_artifact_from_bytes(_artifact_bytes(m)) == m for m in bad.member_evidence)
