"""WO-06 C01-C15: controlled evidence only, no production services."""
from dataclasses import asdict, replace
from datetime import timedelta
import json

import pytest

from kronos.swing.v1 import opportunity_continuity as c
from kronos.swing.v1 import native_discovery as n
from kronos.swing.v1.mtf_facts import CompletedTimeframeBar as Bar, FactualPivotSeries
from kronos.swing.v1.models import PivotCandidate, PivotKind
from tests.unit.swing.v1.test_opportunity_continuity import scenario, row, assessment, commit, later
from tests.unit.swing.v1.test_native_discovery import FactualTimeframe as TF, weekly_foundations


@pytest.fixture(scope="module")
def complete(scenario):
    snapshot, bindings = scenario
    gold = snapshot.instrument("GOLDM")
    facts, bars = [], []
    for fact in gold.timeframes:
        fact = replace(fact, observation_boundary=snapshot.observed_at - timedelta(minutes=1),
                       source_timestamp=snapshot.observed_at - timedelta(hours=1, minutes=1))
        if fact.timeframe is TF.WEEKLY:
            facts.append(fact)
            bars.append(Bar.from_fact(fact))
            continue
        period = timedelta(days=1) if fact.timeframe is TF.DAILY else timedelta(hours=4 if fact.timeframe is TF.FOUR_HOUR else 1)
        starts = [fact.observation_boundary - period * (16 - i) for i in range(16)]
        series = []
        for i, start in enumerate(starts):
            high, low = 97.0, 93.0
            high = {3: 100.0, 8: 110.0}.get(i, high)
            low = {5: 80.0, 10: 90.0}.get(i, low)
            if fact.timeframe is TF.ONE_HOUR and i in {12, 13, 14}:
                high, low = 113.0, (105.0 if i == 13 else 110.0)
            close = (high + low) / 2
            series.append(replace(Bar.from_fact(fact), source_timestamp=start,
                observation_boundary=start + period, high=high, low=low, open=close, close=close))
        close = 100.0 if fact.timeframe is TF.ONE_HOUR else fact.close
        series[-1] = replace(series[-1], high=close + 2, low=close - 2, open=close, close=close)
        def pivots(radius):
            low_indices = (5, 13) if radius == 1 and fact.timeframe is TF.ONE_HOUR else (5, 10)
            return FactualPivotSeries(f"FRACTAL_UNIQUE_EXTREME_RADIUS_{radius}", radius,
                tuple(PivotCandidate(PivotKind.HIGH, i, starts[i], series[i].high) for i in (3, 8)),
                tuple(PivotCandidate(PivotKind.LOW, i, starts[i], series[i].low) for i in low_indices))
        facts.append(replace(fact, **{key: getattr(series[-1], key) for key in
            ("source_timestamp", "observation_boundary", "open", "high", "low", "close")},
            structural_measurements=(pivots(1), pivots(2))))
        bars.extend(series)
    gold = replace(gold, timeframes=tuple(facts), completed_series=tuple(bars))
    snapshot = replace(snapshot, observed_at=max(f.observation_boundary for f in facts) + timedelta(minutes=1),
        instruments=tuple(gold if i.canonical_instrument == "GOLDM" else i for i in snapshot.instruments))
    return snapshot, bindings


def advance(snapshot, tf=TF.ONE_HOUR, *, close=120.0, number=2):
    gold = snapshot.instrument("GOLDM")
    fact = gold.fact(tf)
    period = timedelta(hours=4 if tf is TF.FOUR_HOUR else 1)
    fact = replace(fact, source_timestamp=fact.source_timestamp + period,
        observation_boundary=fact.observation_boundary + period, open=close, high=close + 2, low=close - 2, close=close)
    facts = tuple(fact if f.timeframe is tf else f for f in gold.timeframes)
    bars = tuple(b for t in TF for b in (*gold.completed_bars(t), Bar.from_fact(fact)) if b.timeframe is t)
    # Add the new bar only once, in its timeframe's ordered series.
    gold = replace(gold, timeframes=facts, completed_series=bars)
    return replace(snapshot, run_identity="SWING-RUN-" + f"{number:032X}",
        observed_at=max(snapshot.observed_at, fact.observation_boundary + timedelta(minutes=1)),
        instruments=tuple(gold if i.canonical_instrument == "GOLDM" else i for i in snapshot.instruments))


def qualify(complete):
    first, bindings = complete
    negative = c.prepare_continuity(first, bindings)
    assert assessment(negative).status is n.NativeDiscoveryStatus.NO_CURRENT_OPPORTUNITY
    assert row(negative).qualification.current.gaps == ()
    current = advance(first)
    positive = c.prepare_continuity(current, bindings, predecessor=commit(negative, first))
    assert assessment(positive).status is n.NativeDiscoveryStatus.PROBABLE
    return first, negative, current, positive, bindings


def test_C01_C09_complete_adjacent_transition_and_right_hand_confirmation(complete):
    first, negative, current, positive, _ = qualify(complete)
    q = row(positive).qualification
    assert q.origin.boundary == current.instrument("GOLDM").fact(TF.ONE_HOUR).observation_boundary
    assert q.origin.evidence.run == current.run_identity
    assert q.origin.evidence.assessment == assessment(positive).result_sha256
    assert q.origin.evidence.mtf == c._digest(current)
    assert q.origin.material_revision == row(positive).material_revision
    assert q.origin.first_detected == current.observed_at
    assert q.origin.attribution == "EXACT_COMMITTED_PREDECESSOR_TRANSITION"
    assert set(dict(q.origin.evidence.boundaries)) == {"1D", "4H", "1H"}  # MCX no Weekly gate
    assert all(p.centre < p.confirmation <= q.origin.boundary for p in q.origin.evidence.pivots)
    p = next(p for p in q.origin.evidence.pivots if p.timeframe == "1H" and p.kind == "LOW" and p.value == 105)
    assert p.confirmation == first.instrument("GOLDM").completed_bars(TF.ONE_HOUR)[14].observation_boundary
    stamped = c.stamp_completed_contribution(positive, current.observed_at + timedelta(seconds=7))
    assert row(stamped).qualification.origin.first_detected == row(stamped).first_admitted
    assert row(stamped).qualification.origin.boundary == q.origin.boundary


def test_C02_unknown_history_never_backdates_or_backfills(complete):
    _, _, current, _, bindings = qualify(complete)
    first = c.prepare_continuity(current, bindings)
    q = row(first).qualification
    assert q.origin.boundary is None and q.origin.first_detected == current.observed_at
    assert not q.current.gaps and q.validity == "VALID"
    # A gap between observations is not an adjacent completed transition.
    prior, bindings = complete
    b = c.prepare_continuity(prior, bindings)
    skipped = advance(advance(prior), number=3)
    b2 = c.prepare_continuity(skipped, bindings, predecessor=commit(b, prior))
    assert row(b2).qualification.origin.boundary is None
    # A provider history may omit the intervening hour. Array adjacency alone
    # cannot prove temporal adjacency (nor may WO-06 infer a session calendar).
    gold = skipped.instrument("GOLDM")
    omitted = gold.completed_bars(TF.ONE_HOUR)[-2]
    gold = replace(gold, completed_series=tuple(bar for bar in gold.completed_series if bar != omitted))
    gap = replace(skipped, instruments=tuple(gold if i.canonical_instrument == "GOLDM" else i for i in skipped.instruments))
    gap_result = c.prepare_continuity(gap, bindings, predecessor=commit(b, prior))
    assert row(gap_result).qualification.origin.boundary is None
    # A new latest bar plus a corrected older bar is not an exact transition.
    fresh = advance(prior)
    gold = fresh.instrument("GOLDM")
    target = gold.completed_bars(TF.ONE_HOUR)[0]
    gold = replace(gold, completed_series=tuple(replace(bar, volume=bar.volume + 1) if bar == target else bar for bar in gold.completed_series))
    fresh = replace(fresh, instruments=tuple(gold if i.canonical_instrument == "GOLDM" else i for i in fresh.instruments))
    corrected = c.prepare_continuity(fresh, bindings, predecessor=commit(b, prior))
    assert row(corrected).qualification.origin.boundary is None


def test_C03_C04_C05_C06_original_immutable_later_hour_four_and_identical(complete):
    _, _, current, positive, bindings = qualify(complete)
    origin = row(positive).qualification.origin
    for tf, number in ((TF.ONE_HOUR, 3), (TF.FOUR_HOUR, 4)):
        updated = advance(current, tf, number=number)
        value = c.prepare_continuity(updated, bindings, predecessor=commit(positive, current))
        assert row(value).qualification.origin == origin
        assert row(value).material_revision != row(positive).material_revision
        assert len(row(value).consumptions) == len(row(positive).consumptions) + (tf is TF.FOUR_HOUR)
        assert row(value).qualification.current.run == updated.run_identity
        current, positive = updated, value
    same = replace(current, run_identity="SWING-RUN-" + "9" * 32, observed_at=current.observed_at + timedelta(minutes=1))
    value = c.prepare_continuity(same, bindings, predecessor=commit(positive, current))
    assert row(value).qualification.origin == origin
    assert row(value).material_revision == row(positive).material_revision
    assert row(value).consumptions == row(positive).consumptions
    assert row(value).qualification.corrections == ()


def test_C08_missing_causal_history_retains_detection_manual(scenario):
    snapshot, bindings = scenario
    result = c.prepare_continuity(snapshot, bindings)
    q = row(result).qualification
    assert q.origin.boundary is None and q.origin.first_detected == snapshot.observed_at
    assert q.current.gaps and q.validity == "MANUAL_REVIEW_REQUIRED"
    assert assessment(result).status is n.NativeDiscoveryStatus.PROBABLE  # no methodology mutation


@pytest.mark.parametrize("close,support", [(121.0, "SUPPORTED"), (104.0, "NOT_SUPPORTED"), (89.0, "UNRESOLVED")])
def test_C10_same_boundary_correction_append_only(complete, close, support):
    _, _, current, positive, bindings = qualify(complete)
    origin = row(positive).qualification.origin
    gold = current.instrument("GOLDM")
    hour = replace(gold.fact(TF.ONE_HOUR), open=close, high=close + 2, low=close - 2, close=close)
    gold = replace(gold, timeframes=tuple(hour if f.timeframe is TF.ONE_HOUR else f for f in gold.timeframes),
        completed_series=tuple(Bar.from_fact(hour) if b.timeframe is TF.ONE_HOUR and b.observation_boundary == hour.observation_boundary else b for b in gold.completed_series))
    updated = replace(current, run_identity="SWING-RUN-" + "4" * 32,
        instruments=tuple(gold if i.canonical_instrument == "GOLDM" else i for i in current.instruments))
    value = c.prepare_continuity(updated, bindings, predecessor=commit(positive, current))
    q = row(value).qualification
    assert q.origin == origin and len(q.corrections) == 1
    assert q.corrections[0].timeframes == ("1H",) and q.corrections[0].support == support
    assert q.corrections[0].previous_assessment == assessment(positive).result_sha256
    assert q.corrections[0].evidence.assessment == assessment(value).result_sha256
    same = replace(updated, run_identity="SWING-RUN-" + "5" * 32)
    again = c.prepare_continuity(same, bindings, predecessor=commit(value, updated))
    assert row(again).qualification.corrections == q.corrections


def test_C12_legacy_and_new_companions_exact_restoration(complete, tmp_path):
    _, _, current, positive, bindings = qualify(complete)
    store = c.ContinuityEvidenceStore(tmp_path)
    store.retain_prepared(positive)
    assert store.load_prepared(current.run_identity) == positive
    legacy = replace(positive, rows=tuple(replace(r, qualification=None) for r in positive.rows))
    legacy = replace(legacy, integrity_sha256=c._digest(c._material(legacy)))
    # Exact V1 row map and Native payload survive; no field added to old bytes.
    assert all("qualification" not in r for r in c._material(legacy)["rows"])
    other = c.ContinuityEvidenceStore(tmp_path / "legacy")
    original = c._bytes({**c._material(legacy), "integrity_sha256": legacy.integrity_sha256})
    assert other.retain_prepared(legacy).read_bytes() == original
    assert other.load_prepared(current.run_identity) == legacy
    next_snapshot = replace(current, run_identity="SWING-RUN-" + "6" * 32)
    next_value = c.prepare_continuity(next_snapshot, bindings, predecessor=commit(legacy, current))
    assert row(next_value).qualification.origin is None
    assert row(next_value).qualification.reason == "QUALIFICATION_HISTORY_UNAVAILABLE"


def test_C09_C12_corrupt_qualification_fails_closed(complete):
    _, _, _, positive, _ = qualify(complete)
    r = row(positive)
    invalid = replace(r.qualification.origin, boundary=r.qualification.origin.boundary - timedelta(hours=2))
    r = replace(r, qualification=replace(r.qualification, origin=invalid))
    value = replace(positive, rows=tuple(r if old.canonical_instrument == "GOLDM" else old for old in positive.rows))
    value = replace(value, integrity_sha256=c._digest(c._material(value)))
    with pytest.raises(ValueError, match="QUALIFICATION_BINDING"):
        value.validate()


def test_C14_compact_presentation(complete, scenario):
    from kronos.browser.views import _swing_continuity_summary
    _, _, _, positive, _ = qualify(complete)
    html = _swing_continuity_summary(row(positive))
    assert "Qualified on" in html and "First detected" in html and "Current validity · VALID" in html
    missing = c.prepare_continuity(*scenario)
    html = _swing_continuity_summary(row(missing))
    assert "Earlier qualification not established" in html and "MANUAL REVIEW REQUIRED" in html


def test_C07_daily_failure_preserves_first_qualification(complete):
    _, _, current, positive, bindings = qualify(complete)
    gold = current.instrument("GOLDM")
    daily = replace(gold.fact(TF.DAILY), open=70.0, high=72.0, low=68.0, close=70.0)
    gold = replace(gold, timeframes=tuple(daily if f.timeframe is TF.DAILY else f for f in gold.timeframes),
        completed_series=tuple(Bar.from_fact(daily) if b.timeframe is TF.DAILY and b.observation_boundary == daily.observation_boundary else b for b in gold.completed_series))
    updated = replace(current, run_identity="SWING-RUN-" + "7" * 32,
        instruments=tuple(gold if i.canonical_instrument == "GOLDM" else i for i in current.instruments))
    value = c.prepare_continuity(updated, bindings, predecessor=commit(positive, current))
    assert "DAILY_RADIUS2_STRUCTURAL_FAILURE" in assessment(value).reason_codes
    assert row(value).qualification.origin == row(positive).qualification.origin
    assert row(value).qualification.validity == "MANUAL_REVIEW_REQUIRED"
    assert row(value).qualification.corrections[-1].support == "UNRESOLVED"


def test_C11_C12_real_atomic_publication_failure_and_restart(complete, tmp_path):
    from tests.unit.swing.test_run_publication import make_checkpoint, provenance
    from kronos.swing.run_publication import SwingRunPublication
    from kronos.swing.v1.relative_context import build_relative_context_run
    from kronos.swing.universe import SWING_PHASE1_UNIVERSE
    initial, bindings = complete
    co, _, _, adopted = make_checkpoint(tmp_path, initial, bindings)
    def prepare(snapshot):
        token, prior = co.admit(snapshot.run_identity, snapshot.observed_at)
        draft = c.prepare_continuity(snapshot, bindings, predecessor=prior.continuity,
            adopted_predecessor=prior if prior.continuity is None else None)
        reference = co.prepare(token, mtf=snapshot, native=draft.native_run, continuity=draft,
            provenance=provenance(snapshot), relative=build_relative_context_run(snapshot, SWING_PHASE1_UNIVERSE))
        return token, reference, draft
    negative = advance(initial, TF.FOUR_HOUR)
    token, reference, draft = prepare(negative)
    assert row(draft).qualification.origin is None
    co.publish(token, reference, negative.observed_at)
    positive = advance(negative, number=3)
    token, reference, draft = prepare(positive)
    assert row(draft).qualification.origin is not None
    assert row(co.current().continuity.contribution).qualification.origin is None
    assert co.fail(token, positive.observed_at)
    assert row(co.current().continuity.contribution).qualification.origin is None
    retry = replace(positive, run_identity="SWING-RUN-" + "8" * 32)
    token, reference, draft = prepare(retry)
    published = co.publish(token, reference, retry.observed_at)
    assert row(published.continuity.contribution).qualification.origin.evidence.run == retry.run_identity
    restored = SwingRunPublication(co.root, mtf_store=co.mtf_store, native_store=co.native_store,
        relative_store=co.relative_store, provenance_store=co.provenance_store).recover(retry.observed_at)
    assert restored == published
    assert restored.native == draft.native_run


def test_C13_C15_native_serialization_and_downstream_contract_independence(complete):
    from kronos.swing.v1.native_trade_construction import QualificationCandleEvidence
    snapshot, bindings = complete
    baseline = n.discover_native_mtf(snapshot)
    prepared = c.prepare_continuity(snapshot, bindings)
    assert prepared.native_run == baseline
    assert n._json_value(asdict(prepared.native_run)) == n._json_value(asdict(baseline))
    assert "qualification" not in json.dumps(n._json_value(asdict(prepared.native_run)))
    assert tuple(QualificationCandleEvidence.__dataclass_fields__) == (
        "identity", "evidence_sha256", "high", "low", "observation_boundary", "completed", "source", "provenance")
    assert not hasattr(c, "latest") and not hasattr(c, "current")
    assert not hasattr(c.ContinuityEvidenceStore, "latest")


def test_C07_nse_weekly_gate_retained_without_mcx_symmetry(complete, weekly_foundations):
    snapshot, bindings = complete
    snapshot = advance(snapshot)
    gold = snapshot.instrument("GOLDM")
    rising, _, _, unavailable = weekly_foundations
    rising = replace(rising, canonical_instrument="IOC", run_identity=snapshot.run_identity)
    equity = replace(gold, canonical_instrument="IOC", exchange="NSE", nse_weekly_foundation=rising)
    snapshot = replace(snapshot, instruments=tuple(equity if i.canonical_instrument == "IOC" else i for i in snapshot.instruments))
    first = c.prepare_continuity(snapshot, bindings)
    eq = next(r for r in first.rows if r.canonical_instrument == "IOC")
    assert eq.qualification.origin is not None
    assert eq.qualification.current.gaps == ()
    assert eq.qualification.validity == "VALID"  # no added Weekly pivot gate
    assert "1W" in dict(eq.qualification.origin.evidence.boundaries)
    assert "1W" not in dict(row(first).qualification.origin.evidence.boundaries)
    unavailable = replace(unavailable, canonical_instrument="IOC", run_identity="SWING-RUN-" + "A" * 32)
    next_snapshot = replace(snapshot, run_identity=unavailable.run_identity,
        instruments=tuple(replace(i, nse_weekly_foundation=unavailable) if i.canonical_instrument == "IOC" else i for i in snapshot.instruments))
    second = c.prepare_continuity(next_snapshot, bindings, predecessor=commit(first, snapshot))
    eq2 = next(r for r in second.rows if r.canonical_instrument == "IOC")
    a2 = next(a for a in second.native_run.assessments if a.canonical_instrument == "IOC")
    assert a2.weekly_state is n.Native1WState.UNAVAILABLE
    assert a2.status is n.NativeDiscoveryStatus.UNAVAILABLE
    assert eq2.qualification.origin == eq.qualification.origin
    assert eq2.qualification.validity != "VALID"
    assert assessment(second).status is n.NativeDiscoveryStatus.PROBABLE
