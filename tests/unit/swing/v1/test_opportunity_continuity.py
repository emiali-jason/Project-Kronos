"""C01-C14 controlled proofs; no production evidence or Provider calls."""
from dataclasses import asdict, replace
from datetime import timedelta
import json

import pytest

from kronos.swing.v1 import native_discovery as native
from kronos.swing.v1 import opportunity_continuity as c
from kronos.swing.run_provenance import SwingAnalysisRunProvenance
from tests.unit.application.test_swing_mtf_facts import _build, _instrument
from tests.unit.swing.v1.test_native_discovery import _fact, FactualTimeframe as TF


@pytest.fixture(scope="module")
def scenario():
    snapshot, _ = _build()
    # Exact positive controlled facts, using the existing classifier's fixture.
    gold = snapshot.instrument("GOLDM")
    facts = tuple(_fact(tf, close=116.0 if tf is TF.FOUR_HOUR else 120.0,
                        bucket="FULL_DURATION" if tf is TF.FOUR_HOUR else None)
                  for tf in (TF.WEEKLY, TF.DAILY, TF.FOUR_HOUR, TF.ONE_HOUR))
    gold = replace(gold, timeframes=facts, completed_series=(), reference_facts=(), one_hour_atr=None)
    snapshot = replace(snapshot, instruments=tuple(gold if i.canonical_instrument == "GOLDM" else
                                                  replace(i, reference_facts=(), one_hour_atr=None)
                                                  for i in snapshot.instruments))
    bindings = tuple(c.SourceBinding.from_instrument(i.canonical_instrument,
                     _instrument(i.canonical_instrument, i.exchange)) for i in snapshot.instruments)
    return snapshot, bindings


def row(bundle):
    return next(r for r in bundle.rows if r.canonical_instrument == "GOLDM")


def assessment(bundle):
    return next(a for a in bundle.native_run.assessments if a.canonical_instrument == "GOLDM")


def commit(bundle, snapshot):
    """Fake WO-05 commit owner, with exact committed contribution digest."""
    provenance = SwingAnalysisRunProvenance(snapshot.run_identity, snapshot.observed_at,
        snapshot.observed_at, "SWING-MARKET-DATA-SNAPSHOT-" + "a" * 64,
        row(bundle).last_analysis_checked)
    return c.CommittedContinuity.verify(bundle, native_run=bundle.native_run, mtf_snapshot=snapshot,
        provenance=provenance, committed_contribution_sha256=bundle.integrity_sha256)


def later(snapshot, number=2, *, changes=None):
    gold = snapshot.instrument("GOLDM")
    if changes:
        gold = replace(gold, timeframes=tuple(changes.get(f.timeframe, f) for f in gold.timeframes))
    return replace(snapshot, run_identity="SWING-RUN-" + f"{number:032X}",
                   observed_at=snapshot.observed_at + timedelta(minutes=number),
                   instruments=tuple(gold if i.canonical_instrument == "GOLDM" else i for i in snapshot.instruments))


def test_C01_C02_C09_admission_only_through_exact_commit(scenario, tmp_path):
    snapshot, bindings = scenario
    bundle = c.prepare_continuity(snapshot, bindings)
    assert assessment(bundle).status is native.NativeDiscoveryStatus.PROBABLE
    assert row(bundle).disposition is c.ContinuityDisposition.ADMITTED
    store = c.ContinuityEvidenceStore(tmp_path)
    store.retain_prepared(bundle)  # Not an admission/current selection operation.
    with pytest.raises(ValueError, match="COMMITTED_BINDING"):
        c.CommittedContinuity.verify(bundle, native_run=bundle.native_run, mtf_snapshot=snapshot,
            provenance=SwingAnalysisRunProvenance(snapshot.run_identity, snapshot.observed_at,
                snapshot.observed_at, "SWING-MARKET-DATA-SNAPSHOT-" + "a" * 64),
            committed_contribution_sha256=bundle.integrity_sha256)
    with pytest.raises(ValueError, match="COMMITTED_BINDING"):
        c.CommittedContinuity.verify(bundle, native_run=bundle.native_run, mtf_snapshot=snapshot,
            provenance=SwingAnalysisRunProvenance(snapshot.run_identity, snapshot.observed_at,
                snapshot.observed_at, "SWING-MARKET-DATA-SNAPSHOT-" + "a" * 64, snapshot.observed_at),
            committed_contribution_sha256="0" * 64)
    assert row(commit(bundle, snapshot).contribution).opportunity_id == row(bundle).opportunity_id
    forming = _fact(TF.FOUR_HOUR, close=104.0, r1=native.V1Direction.SHORT, bucket="SESSION_REMAINDER")
    other = later(snapshot, changes={TF.FOUR_HOUR: forming})
    draft = c.prepare_continuity(other, bindings)
    assert assessment(draft).status is native.NativeDiscoveryStatus.FORMING_WATCH
    assert row(draft).opportunity_id is None
    assert row(draft).consumptions


def test_C02_C03_C07_twelve_refreshes_one_opportunity_revision(scenario):
    snapshot, bindings = scenario
    original = c.prepare_continuity(snapshot, bindings)
    previous = commit(original, snapshot)
    assessments = {assessment(original).result_sha256}
    for n in range(2, 13):
        current = later(snapshot, n)
        current = replace(current, provider_source_identity="KITE-MTF-FACTS-" + f"{n:064x}")
        bundle = c.prepare_continuity(current, tuple(reversed(bindings)), predecessor=previous)
        assert row(bundle).opportunity_id == row(original).opportunity_id
        assert row(bundle).material_revision == row(original).material_revision
        assert row(bundle).first_admitted == row(original).first_admitted
        assert row(bundle).no_material_change
        assert len(row(bundle).consumptions) == 1
        assert assessment(bundle).four_hour_state == assessment(original).four_hour_state
        assessments.add(assessment(bundle).result_sha256)
        previous = commit(bundle, current)
    assert len(assessments) == 12  # Existing exact run-bound hashes stay independent.


def test_C03_pre_admission_replay_and_exact_transition_seam(scenario):
    snapshot, bindings = scenario
    # Seed the existing approved predecessor state without changing its facts.
    initial = c.prepare_continuity(snapshot, bindings)
    previous_native = replace(assessment(initial), four_hour_state=native.Native4HState.STRUCTURAL_HOLD)
    previous_native = replace(previous_native, result_sha256=native._assessment_digest(previous_native))
    four = snapshot.instrument("GOLDM").fact(TF.FOUR_HOUR)
    daily = snapshot.instrument("GOLDM").fact(TF.DAILY)
    first = native.classify_native_four_hour(daily, four, previous_native.daily_state,
                                            previous_native.direction, previous_native.four_hour_state)
    assert first[0] is native.Native4HState.RESUMPTION_DEVELOPING
    assert native.classify_native_four_hour(daily, four, previous_native.daily_state,
        previous_native.direction, first[0])[0] is native.Native4HState.CONTINUATION_DEVELOPING
    # The callback is the exact production seam: the retained result is reused.
    called = []
    result = native._discover_instrument(snapshot, snapshot.instrument("GOLDM"), previous_native, (),
                                        four_hour_resolver=lambda *args: called.append(args) or first)
    assert len(called) == 1
    assert result.four_hour_state is native.Native4HState.RESUMPTION_DEVELOPING
    forming = _fact(TF.FOUR_HOUR, close=104.0, r1=native.V1Direction.SHORT, bucket="FULL_DURATION")
    s1 = later(snapshot, changes={TF.FOUR_HOUR: forming})
    b1 = c.prepare_continuity(s1, bindings)
    s2 = later(s1, 3)
    b2 = c.prepare_continuity(s2, bindings, predecessor=commit(b1, s1))
    assert row(b2).opportunity_id is None and row(b2).consumptions == row(b1).consumptions


def test_C04_new_hour_does_not_consume_four(scenario):
    snapshot, bindings = scenario
    initial = c.prepare_continuity(snapshot, bindings)
    hour = snapshot.instrument("GOLDM").fact(TF.ONE_HOUR)
    hour = replace(hour, source_timestamp=hour.source_timestamp + timedelta(hours=1),
                   observation_boundary=hour.observation_boundary + timedelta(hours=1))
    current = later(snapshot, changes={TF.ONE_HOUR: hour})
    bundle = c.prepare_continuity(current, bindings, predecessor=commit(initial, snapshot))
    assert row(bundle).material_revision != row(initial).material_revision
    assert row(bundle).opportunity_id == row(initial).opportunity_id
    assert row(bundle).consumptions == row(initial).consumptions


def test_C05_new_and_corrected_four_hour(scenario):
    snapshot, bindings = scenario
    initial = c.prepare_continuity(snapshot, bindings)
    four = snapshot.instrument("GOLDM").fact(TF.FOUR_HOUR)
    corrected = replace(four, close=117.0)
    s2 = later(snapshot, changes={TF.FOUR_HOUR: corrected})
    b2 = c.prepare_continuity(s2, bindings, predecessor=commit(initial, snapshot))
    assert len(row(b2).consumptions) == 2
    assert row(b2).consumptions[1].entering_state == row(initial).consumptions[0].entering_state
    assert row(b2).material_revision != row(initial).material_revision
    newer = replace(corrected, source_timestamp=four.source_timestamp + timedelta(hours=4),
                    observation_boundary=four.observation_boundary + timedelta(hours=4))
    s3 = later(snapshot, 3, changes={TF.FOUR_HOUR: newer})
    b3 = c.prepare_continuity(s3, bindings, predecessor=commit(b2, s2))
    assert len(row(b3).consumptions) == 3
    s4 = later(s3, 4)
    b4 = c.prepare_continuity(s4, bindings, predecessor=commit(b3, s3))
    assert row(b4).consumptions == row(b3).consumptions


def test_C06_daily_invalidation_not_hidden(scenario):
    snapshot, bindings = scenario
    initial = c.prepare_continuity(snapshot, bindings)
    daily = snapshot.instrument("GOLDM").fact(TF.DAILY)
    failed = replace(daily, close=70.0, low=69.0)
    current = later(snapshot, changes={TF.DAILY: failed})
    bundle = c.prepare_continuity(current, bindings, predecessor=commit(initial, snapshot))
    assert "DAILY_RADIUS2_STRUCTURAL_FAILURE" in assessment(bundle).reason_codes
    assert row(bundle).disposition is c.ContinuityDisposition.MANUAL_REVIEW_REQUIRED
    assert assessment(bundle).status is not native.NativeDiscoveryStatus.PROBABLE


def test_C07_fingerprint_ignores_processing_and_pivot_indices(scenario):
    snapshot, bindings = scenario
    gold = snapshot.instrument("GOLDM")
    binding = next(b for b in bindings if b.canonical_instrument == "GOLDM")
    original = c.evidence_fingerprints(gold, binding)
    facts = tuple(replace(f, provenance=("different download attempt",),
        source_market_data_boundary=f.source_market_data_boundary + timedelta(hours=1),
        structural_measurements=tuple(replace(s,
            swing_highs=tuple(replace(p, candle_index=p.candle_index + 1) for p in s.swing_highs),
            swing_lows=tuple(replace(p, candle_index=p.candle_index + 1) for p in s.swing_lows))
            for s in f.structural_measurements)) for f in gold.timeframes)
    assert c.evidence_fingerprints(replace(gold, timeframes=facts), binding) == original
    nse = next(i for i in snapshot.instruments if i.exchange == "NSE")
    nb = next(b for b in bindings if b.canonical_instrument == nse.canonical_instrument)
    fp = c.evidence_fingerprints(nse, nb)
    week = nse.nse_weekly_foundation
    if week.current_sma200 is not None:
        changed = replace(nse, nse_weekly_foundation=replace(week, current_sma200=week.current_sma200 + 1,
                          sma200_difference=(week.current_sma200 + 1) - week.prior_sma200_5w))
        assert c.evidence_fingerprints(changed, nb)["1W"] != fp["1W"]


@pytest.mark.parametrize("change", ["source", "anchor", "direction", "missing"])
def test_C11_uncertain_continuity_has_no_successor(scenario, change):
    snapshot, bindings = scenario
    initial = c.prepare_continuity(snapshot, bindings)
    current = later(snapshot)
    if change == "source":
        bindings = tuple(replace(b, expiry="2027-01-01") if b.canonical_instrument == "GOLDM" else b for b in bindings)
    elif change == "missing":
        bindings = tuple(b for b in bindings if b.canonical_instrument != "GOLDM")
    elif change == "anchor":
        current = later(snapshot, changes={TF.FOUR_HOUR: _fact(TF.FOUR_HOUR, close=96.0,
            low=94.0, high=97.0, r1=native.V1Direction.SHORT, bucket="FULL_DURATION")})
    else:
        current = later(snapshot, changes={TF.DAILY: _fact(TF.DAILY, close=60.0,
            r1=native.V1Direction.SHORT, r2=native.V1Direction.SHORT)})
    bundle = c.prepare_continuity(current, bindings, predecessor=commit(initial, snapshot))
    assert row(bundle).disposition is c.ContinuityDisposition.MANUAL_REVIEW_REQUIRED
    assert row(bundle).opportunity_id == row(initial).opportunity_id
    assert row(bundle).material_revision == row(initial).material_revision


def test_C08_C09_restart_integrity_and_no_current_selector(scenario, tmp_path):
    snapshot, bindings = scenario
    bundle = c.prepare_continuity(snapshot, bindings)
    store = c.ContinuityEvidenceStore(tmp_path)
    path = store.retain_prepared(bundle)
    assert store.retain_prepared(bundle) == path
    restored = c.ContinuityEvidenceStore(tmp_path).load_prepared(snapshot.run_identity)
    assert restored == bundle
    assert commit(restored, snapshot) == commit(bundle, snapshot)
    assert not hasattr(store, "latest") and not hasattr(store, "current")
    data = json.loads(path.read_bytes())
    data["rows"][0]["material_fingerprint"] = "0" * 64
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="RESTORATION"):
        store.load_prepared(snapshot.run_identity)


def test_C10_C12_C13_original_native_bytes_and_trade_independence(scenario, tmp_path):
    snapshot, bindings = scenario
    legacy = native.discover_native_mtf(snapshot)
    store = native.NativeDiscoveryEvidenceStore(tmp_path)
    path = store.retain(legacy)
    before = path.read_bytes()
    initial = c.prepare_continuity(snapshot, bindings)
    assert initial.native_run == legacy
    for n in (2, 3):
        current = later(snapshot, n)
        c.prepare_continuity(current, bindings, predecessor=commit(initial, snapshot))
    assert store.load(snapshot.run_identity) == legacy and path.read_bytes() == before
    # No trade/position/Review input exists in the continuity contract.
    import inspect
    signature = inspect.signature(c.prepare_continuity)
    assert not {"trade", "position", "readiness", "review", "risk"}.intersection(signature.parameters)


def test_C03_full_bundle_hold_resumption_identical_four_never_continuation(scenario, monkeypatch):
    snapshot, bindings = scenario
    hold = _fact(TF.FOUR_HOUR, close=110.0, low=90.0, high=112.0, bucket="FULL_DURATION")
    s1 = later(snapshot, changes={TF.FOUR_HOUR: hold})
    b1 = c.prepare_continuity(s1, bindings)
    assert assessment(b1).four_hour_state is native.Native4HState.STRUCTURAL_HOLD
    progress = _fact(TF.FOUR_HOUR, close=116.0, bucket="FULL_DURATION")
    progress = replace(progress, source_timestamp=progress.source_timestamp + timedelta(hours=4),
                       observation_boundary=progress.observation_boundary + timedelta(hours=4))
    s2 = later(snapshot, 3, changes={TF.FOUR_HOUR: progress})
    b2 = c.prepare_continuity(s2, bindings, predecessor=commit(b1, s1))
    assert assessment(b2).four_hour_state is native.Native4HState.RESUMPTION_DEVELOPING
    s3 = later(s2, 4)
    original = native.classify_native_four_hour
    calls = []
    def observe(daily, four, *args):
        if four == progress:
            calls.append(four)
        return original(daily, four, *args)
    monkeypatch.setattr(native, 'classify_native_four_hour', observe)
    b3 = c.prepare_continuity(s3, bindings, predecessor=commit(b2, s2))
    assert assessment(b3).four_hour_state is native.Native4HState.RESUMPTION_DEVELOPING
    assert calls == []
    assert row(b3).consumptions == row(b2).consumptions
    corrected = replace(progress, close=117.0)
    s4 = later(s3, 5, changes={TF.FOUR_HOUR: corrected})
    b4 = c.prepare_continuity(s4, bindings, predecessor=commit(b3, s3))
    assert row(b4).consumptions[-1].entering_state is native.Native4HState.STRUCTURAL_HOLD
    assert assessment(b4).four_hour_state is native.Native4HState.RESUMPTION_DEVELOPING


def test_C09_boundary_regression_and_future_evidence_fail_closed(scenario):
    snapshot, bindings = scenario
    initial = c.prepare_continuity(snapshot, bindings)
    four = snapshot.instrument("GOLDM").fact(TF.FOUR_HOUR)
    new_four = replace(four, source_timestamp=four.source_timestamp + timedelta(hours=4),
                       observation_boundary=four.observation_boundary + timedelta(hours=4))
    current = later(snapshot, changes={TF.FOUR_HOUR: new_four})
    newer = c.prepare_continuity(current, bindings, predecessor=commit(initial, snapshot))
    regressed = later(snapshot, 3)
    blocked = c.prepare_continuity(regressed, bindings, predecessor=commit(newer, current))
    assert row(blocked).reason == "FOUR_HOUR_BOUNDARY_REGRESSION"
    assert assessment(blocked).status is not native.NativeDiscoveryStatus.PROBABLE
    future = replace(new_four, observation_boundary=snapshot.observed_at + timedelta(days=1))
    with pytest.raises(ValueError, match='INCOMPLETE_EVIDENCE'):
        c.prepare_continuity(later(snapshot, changes={TF.FOUR_HOUR: future}), bindings)


def test_C11_source_binding_preserves_normalized_reference_metadata():
    from kronos.provider.contracts.instrument import InstrumentRecord
    record = InstrumentRecord('KITE', 'NSE', 'INDICES', 'NIFTY 50', 'NIFTY 50', '', None,
                              tick_size=0, lot_size=0)
    binding = c.SourceBinding.from_instrument('NIFTY', record)
    assert binding.instrument_type == '' and binding.expiry is None
