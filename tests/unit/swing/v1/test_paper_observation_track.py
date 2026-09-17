from datetime import timedelta
from dataclasses import replace
from decimal import Decimal
import json
import tracemalloc

import pytest

from kronos.swing.v1.native_sponsor_decision import SponsorTradeChoice
from kronos.swing.v1.paper_observation_track import (
    LocalPaperObservationTrackStore,
    PAPER_OBSERVATION_RETAINED_MATERIAL_TRANSITIONS,
    PAPER_OBSERVATION_TRACK_AUTHORITY,
    PaperObservationMonitoringApplicabilityState,
    PaperObservationMonitoringAuthorityV1,
    PaperObservationMonitoringState,
    PaperObservationOutcome,
    PaperObservationSourceKind,
    PaperObservationTrackState,
    create_paper_observation_track,
    make_event,
    make_market_fact,
    make_monitoring_applicability,
    make_monitoring_record,
    paper_observation_instrument_contract_identity,
    project_monitoring_applicability,
)
from kronos.swing.v1.sponsor_observation_decision import (
    SponsorActivationDisposition,
)
from tests.unit.swing.v1.test_sponsor_observation_decision import (
    NOW,
    _green,
    _record,
    _red,
)
from tests.unit.swing.v1.test_step31_observation import _observe, _package


def _consolidation_history(tmp_path, count=1):
    from kronos.swing.v1.paper_observation_track import _canonical, _primitive
    result = _blocked(tmp_path)
    track = create_paper_observation_track(result,
        current_run_identity=result.snapshot.native_run_identity, created_at=NOW)
    store = LocalPaperObservationTrackStore(tmp_path / "history")
    store.retain_track(track)
    directory = store.root / track.track_identity / "facts"
    directory.mkdir()
    for index in range(count):
        fact = make_market_fact(track, last_price=Decimal(100 + index % 11),
            observed_at=NOW + timedelta(seconds=index),
            received_at=NOW + timedelta(seconds=index), source_identity=f"TEST:SESSION:{index}",
            source_sequence=index, ordering_deterministic=True, recovered=False)
        (directory / f"{fact.fact_identity}.json").write_bytes(_canonical({
            "schema": "KRONOS-SWING-PAPER-OBSERVATION-STORE-V1", "fact": _primitive(fact)}))
    return store, track


def _consolidate(store, track):
    return store.prepare_historical_consolidation(track.track_identity,
        created_at=NOW + timedelta(days=2))


def _selected_historical_fixture(tmp_path, count=3):
    store, track = _consolidation_history(tmp_path, count)
    store.append_monitoring(make_monitoring_record(track.track_identity,
        PaperObservationMonitoringState.INTERRUPTED, "RECOVERY_REQUIRED", NOW))
    candidate = _consolidate(store, track)
    assert store.publish_historical_consolidation(candidate,
        maintenance_identity="ISOLATED-SLICE6A", published_at=NOW + timedelta(days=3))
    return store, track, candidate


@pytest.mark.parametrize('boundary', ['before_candidate', 'after_candidate', 'before_selection', 'after_selection'])
def test_slice8_historical_selection_interruption_is_explicit_and_read_only(tmp_path, monkeypatch, boundary):
    from kronos.swing.v1 import paper_observation_track as domain
    store, track = _consolidation_history(tmp_path, 3)
    candidate = _consolidate(store, track)
    atomic, append = domain._atomic_encoded, store._append
    def candidate_write(path, encoded):
        if path.parent.name == 'historical-consolidations':
            if boundary == 'before_candidate':
                raise OSError('isolated candidate interruption')
            atomic(path, encoded)
            if boundary == 'after_candidate':
                raise OSError('isolated candidate interruption')
            return
        return atomic(path, encoded)
    def selection_write(path, *args):
        if path.name == 'historical-representation.json':
            if boundary == 'before_selection':
                raise OSError('isolated selection interruption')
            result = append(path, *args)
            if boundary == 'after_selection':
                raise OSError('isolated selection interruption')
            return result
        return append(path, *args)
    with monkeypatch.context() as fault:
        fault.setattr(domain, '_atomic_encoded', candidate_write)
        fault.setattr(store, '_append', selection_write)
        with pytest.raises(OSError, match='isolated'):
            store.publish_historical_consolidation(candidate,
                maintenance_identity='SLICE8-ISOLATED', published_at=NOW + timedelta(days=3))
    before = {str(p): p.read_bytes() for p in store.root.rglob('*') if p.is_file()}
    reopened = LocalPaperObservationTrackStore(store.root)
    projection = reopened.projection(track.track_identity)
    assert projection.history_representation == (
        'COMPACT_HISTORICAL' if boundary == 'after_selection' else 'RAW_HISTORY')
    assert projection.last_factual_observation_at == NOW + timedelta(seconds=2)
    assert not reopened.restoration_projection(track.track_identity).applicability.automatic_restoration
    assert reopened.current_applicability(track.track_identity) is None
    assert before == {str(p): p.read_bytes() for p in store.root.rglob('*') if p.is_file()}


def test_selected_historical_projection_preserves_exact_truth_and_denies_raw_audit(tmp_path, monkeypatch):
    store, track, candidate = _selected_historical_fixture(tmp_path)
    data = json.loads(candidate.canonical_bytes)
    for path in (store.root / track.track_identity / "facts").iterdir():
        path.unlink()
    monkeypatch.setattr(store, "_load_fact", lambda *_: pytest.fail("raw fact reconstruction"))
    before = {str(p):p.read_bytes() for p in store.root.rglob('*') if p.is_file()}
    projection = store.projection(track.track_identity)
    assert projection.history_representation == "COMPACT_HISTORICAL"
    assert projection.raw_detail_availability == "HISTORICAL_DETAIL_UNAVAILABLE"
    assert projection.track == track
    assert projection.last_factual_observation_at == NOW + timedelta(seconds=2)
    assert projection.first_factual_observation_at == NOW
    assert projection.last_factual_observation_at.isoformat() != data['created_at']
    assert projection.historical_fact_count == 3
    assert projection.historical_source_count == 5
    assert projection.outcome_state is PaperObservationOutcome.OUTCOME_NOT_ESTABLISHED
    assert projection.monitoring_state is PaperObservationMonitoringState.INTERRUPTED
    assert projection.monitoring_reason == "RECOVERY_REQUIRED"
    with pytest.raises(ValueError, match="HISTORICAL_DETAIL_UNAVAILABLE"):
        store.facts(track.track_identity)
    assert not store.restoration_projection(track.track_identity).applicability.automatic_restoration
    assert not store.publish_historical_consolidation(candidate,
        maintenance_identity="EXPLICIT_REPLAY", published_at=NOW + timedelta(days=3))
    assert before == {str(p):p.read_bytes() for p in store.root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('damage', ['wrong_track','corrupt','unsupported','coverage','stale_control','missing_record','missing_selection_target'])
def test_historical_selection_invalidity_is_bounded_and_cannot_hide_as_raw(tmp_path, damage):
    from kronos.swing.v1.paper_observation_track import _canonical, _values_digest
    from hashlib import sha256
    store, track, candidate = _selected_historical_fixture(tmp_path)
    directory=store.root/track.track_identity
    pointer=directory/'historical-representation.json'
    path=directory/'historical-consolidations'/f'{candidate.integrity_sha256}.json'
    if damage=='corrupt':path.write_bytes(b'corrupt')
    elif damage=='missing_record':path.unlink()
    elif damage=='missing_selection_target':
        pointer.unlink();pointer.symlink_to(directory/'missing.json')
    elif damage=='stale_control':
        store.append_monitoring(make_monitoring_record(track.track_identity,
            PaperObservationMonitoringState.ACTIVE,'UNEXPECTED_NEW_CONTROL',NOW+timedelta(seconds=1)))
    else:
        data=json.loads(path.read_bytes())
        if damage=='wrong_track':data['track']['track_identity']='FOREIGN'
        elif damage=='unsupported':data['implementation_version']='999'
        else:data['source_file_count']+=1
        encoded=_canonical(data);h=sha256(encoded).hexdigest()
        (path.parent/(h+'.json')).write_bytes(encoded)
        selected=json.loads(pointer.read_bytes());s=selected['selection']
        s.update(consolidation_sha256=h,consolidation_identity='PAPER-OBSERVATION-CONSOLIDATION-'+h,
                 source_file_count=data['source_file_count'],integrity_sha256='')
        s['integrity_sha256']=_values_digest(s)
        pointer.write_bytes(_canonical(selected))
    with pytest.raises(ValueError,match='HISTORICAL_EVIDENCE_UNAVAILABLE'):
        store.load_historical_consolidation(track.track_identity)
    p=store.projection(track.track_identity)
    assert p.history_representation=='HISTORY_UNAVAILABLE'
    assert p.last_factual_observation_at is None
    assert p.historical_fact_count is None
    assert p.raw_detail_availability=='HISTORICAL_DETAIL_UNAVAILABLE'


def test_unselected_candidate_does_not_authorize_compaction_or_hide_raw_corruption(tmp_path):
    store,track=_consolidation_history(tmp_path,2)
    candidate=_consolidate(store,track)
    (store.root/track.track_identity/'candidate.json').write_bytes(candidate.canonical_bytes)
    assert store.projection(track.track_identity).history_representation=='RAW_HISTORY'
    paths=list((store.root/track.track_identity/'facts').iterdir())
    original=paths[0].read_bytes();paths[0].write_bytes(b'corrupt')
    with pytest.raises(ValueError):store.projection(track.track_identity)
    paths[0].write_bytes(original)
    for path in paths:path.unlink()
    p=store.projection(track.track_identity)
    assert p.history_representation=='RAW_HISTORY'
    assert p.raw_detail_availability=='HISTORICAL_DETAIL_UNAVAILABLE'
    assert p.historical_fact_count is None


def test_publication_revalidates_source_and_prohibits_monitoring_or_new_facts(tmp_path):
    store,track=_consolidation_history(tmp_path,1)
    candidate=_consolidate(store,track)
    fact=make_market_fact(track,last_price=Decimal(2),observed_at=NOW+timedelta(seconds=1),
        received_at=NOW+timedelta(seconds=1),source_identity='NEW:1',source_sequence=1,
        ordering_deterministic=True,recovered=False)
    store.append_fact(fact)
    with pytest.raises(ValueError,match='SOURCE_COVERAGE_MISMATCH'):
        store.publish_historical_consolidation(candidate,maintenance_identity='TEST',published_at=NOW+timedelta(days=3))
    candidate=_consolidate(store,track)
    store.publish_historical_consolidation(candidate,maintenance_identity='TEST',published_at=NOW+timedelta(days=3))
    with pytest.raises(ValueError,match='HISTORICAL_DETAIL_UNAVAILABLE'):store.append_fact(fact)
    app=make_monitoring_applicability(track.track_identity,PaperObservationMonitoringApplicabilityState.OPEN,
        'CURRENT_AUTHORITY',_authority(track),NOW)
    with pytest.raises(ValueError,match='MONITORING_AUTHORITY_PROHIBITED'):store.append_applicability(app)


def test_consolidation_empty_fails_closed(tmp_path):
    store, track = _consolidation_history(tmp_path, 0)
    with pytest.raises(ValueError, match="EMPTY_HISTORY"):
        _consolidate(store, track)


def test_consolidation_replay_is_immutable_research_and_never_writes_sources(tmp_path):
    from hashlib import sha256
    store, track = _consolidation_history(tmp_path)
    before = {str(p): (p.stat().st_mtime_ns, p.stat().st_ctime_ns, p.read_bytes())
              for p in store.root.rglob("*") if p.is_file()}
    result = _consolidate(store, track)
    assert result == _consolidate(store, track)
    assert result.integrity_sha256 == sha256(result.canonical_bytes).hexdigest()
    data = json.loads(result.canonical_bytes)
    assert data["fact_count"] == 1 and data["source_file_count"] == 2
    assert data["authority"] == "RESEARCH_ONLY"
    assert data["applicability"] is None
    assert data["monitoring_restorable"] is False and data["deletion_ready"] is False
    assert data["deletion_readiness"] == "PENDING_REFERENCE_SCAN"
    assert data["final_state"]["outcome"] == "OUTCOME_NOT_ESTABLISHED"
    assert data["track"]["sponsor_decision_identity"] == track.sponsor_decision_identity
    assert not store.restoration_projection(track.track_identity).applicability.automatic_restoration
    assert before == {str(p): (p.stat().st_mtime_ns, p.stat().st_ctime_ns, p.read_bytes())
                      for p in store.root.rglob("*") if p.is_file()}


def test_consolidation_changed_population_changes_identity(tmp_path):
    store, track = _consolidation_history(tmp_path)
    first = _consolidate(store, track)
    fact = make_market_fact(track, last_price=Decimal(101), observed_at=NOW + timedelta(seconds=1),
        received_at=NOW + timedelta(seconds=1), source_identity="TEST:SESSION:1",
        source_sequence=1, ordering_deterministic=True, recovered=False)
    store.append_fact(fact)
    assert _consolidate(store, track).identity != first.identity


@pytest.mark.parametrize("damage", ["corrupt", "missing_sequence", "foreign", "missing_during_read"])
def test_consolidation_invalid_fact_fails_closed(tmp_path, monkeypatch, damage):
    from kronos.swing.v1 import paper_observation_track as module
    store, track = _consolidation_history(tmp_path)
    path = next((store.root / track.track_identity / "facts").iterdir())
    if damage == "missing_during_read":
        original = module._fact_from_bytes
        def remove_after_read(encoded):
            result = original(encoded)
            path.unlink()
            return result
        monkeypatch.setattr(module, "_fact_from_bytes", remove_after_read)
    else:
        data = json.loads(path.read_bytes())
        if damage == "corrupt":
            data["fact"]["last_price"] = "999"
        elif damage == "missing_sequence":
            del data["fact"]["source_sequence"]
        else:
            data["fact"]["track_identity"] = "FOREIGN"
            data["fact"]["integrity_sha256"] = ""
            data["fact"]["integrity_sha256"] = module._values_digest(data["fact"])
        path.write_text(json.dumps(data))
    with pytest.raises((ValueError, TypeError)):
        _consolidate(store, track)


def test_consolidation_conflicting_source_fails_closed(tmp_path):
    store, track = _consolidation_history(tmp_path)
    store.append_fact(make_market_fact(track, last_price=Decimal(999), observed_at=NOW,
        received_at=NOW, source_identity="TEST:SESSION:0", source_sequence=0,
        ordering_deterministic=True, recovered=False))
    with pytest.raises(ValueError, match="PROVIDER_SEQUENCE_CONFLICT"):
        _consolidate(store, track)


def test_consolidation_duplicate_source_fails_closed(tmp_path):
    from kronos.swing.v1.paper_observation_track import _primitive, _values_digest, _fact_from_dict
    store, track = _consolidation_history(tmp_path)
    original = store.facts(track.track_identity)[0]
    data = _primitive(original)
    data["fact_identity"] = "PAPER-OBSERVATION-FACT-" + "f" * 64
    data["integrity_sha256"] = ""
    data["integrity_sha256"] = _values_digest(data)
    store.append_fact(_fact_from_dict(data))
    with pytest.raises(ValueError, match="DUPLICATE_SOURCE"):
        _consolidate(store, track)


@pytest.mark.parametrize("kind", ["track", "event", "monitoring"])
def test_consolidation_validates_every_control_record(tmp_path, kind):
    store, track = _consolidation_history(tmp_path)
    store.append_monitoring(make_monitoring_record(track.track_identity,
        PaperObservationMonitoringState.INTERRUPTED, "RECOVERY_REQUIRED", NOW))
    store.append_event(make_event(track, PaperObservationOutcome.ENTRY_OBSERVED,
        observed_at=NOW, recorded_at=NOW, source_identity="TEST:SESSION:0",
        source_kind=PaperObservationSourceKind.KITE_FACTUAL_TICK, observed_price=Decimal(100)))
    directory = store.root / track.track_identity
    path = directory / "track.json" if kind == "track" else next((directory / ("events" if kind == "event" else kind)).iterdir())
    data = json.loads(path.read_bytes())
    data[kind]["integrity_sha256"] = "f" * 64
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        _consolidate(store, track)


def test_consolidation_unsequenced_preserves_absence_and_ambiguous_final_price(tmp_path):
    store, track = _consolidation_history(tmp_path)
    store.append_fact(make_market_fact(track, last_price=Decimal(99), observed_at=NOW,
        received_at=NOW, source_identity="TEST:SESSION:KRONOS_UNSEQUENCED_OBSERVATION:second",
        source_sequence=None, ordering_deterministic=True, recovered=False))
    data = json.loads(_consolidate(store, track).canonical_bytes)
    assert data["unsequenced_fact_count"] == 1
    assert data["final_observed_price"] is None
    assert data["final_state"]["outcome"] == "OUTCOME_NOT_ESTABLISHED"


@pytest.mark.parametrize("terminal", [False, True])
def test_consolidation_preserves_factual_events_separately_from_applicability(tmp_path, terminal):
    store, track = _consolidation_history(tmp_path)
    store.append_monitoring(make_monitoring_record(track.track_identity,
        PaperObservationMonitoringState.INTERRUPTED, "RECOVERY_REQUIRED", NOW))
    store.append_event(make_event(track, PaperObservationOutcome.ENTRY_OBSERVED,
        observed_at=NOW, recorded_at=NOW, source_identity="TEST:SESSION:0",
        source_kind=PaperObservationSourceKind.KITE_FACTUAL_TICK, observed_price=Decimal(100)))
    if terminal:
        store.append_event(make_event(track, PaperObservationOutcome.STOP_LEVEL_TOUCHED,
            observed_at=NOW + timedelta(seconds=1), recorded_at=NOW + timedelta(seconds=1),
            source_identity="CANDLE", source_kind=PaperObservationSourceKind.COMPLETED_CANDLE,
            interval_low=Decimal(1), interval_high=Decimal(1000)))
    before = store.projection(track.track_identity)
    data = json.loads(_consolidate(store, track).canonical_bytes)
    assert data["final_state"]["outcome"] == ("STOP_LEVEL_TOUCHED" if terminal else "OUTCOME_NOT_ESTABLISHED")
    assert data["final_state"]["track_state"] == ("COMPLETE" if terminal else "MONITORING_INTERRUPTED")
    assert data["applicability"] is None
    assert data["currentness"] == "HISTORICAL_NO_CURRENT_APPLICABILITY"
    assert data["interruption_count"] == 1
    assert store.projection(track.track_identity) == before


def test_consolidation_large_stream_uses_bounded_memory_and_full_history_still_validates(tmp_path, monkeypatch):
    from kronos.swing.v1 import paper_observation_track as module
    peaks = []
    for count in (256, 4096):
        store, track = _consolidation_history(tmp_path / str(count), count)
        with monkeypatch.context() as patch:
            patch.setattr(store, "facts", lambda *_: pytest.fail("full history loaded"))
            patch.setattr(store, "_load_fact", lambda *_: pytest.fail("fact cache used"))
            patch.setattr(store, "projection", lambda *_: pytest.fail("full projection loaded"))
            tracemalloc.start()
            data = json.loads(_consolidate(store, track).canonical_bytes)
            peaks.append(tracemalloc.get_traced_memory()[1])
            tracemalloc.stop()
        assert data["fact_count"] == count
        assert data["observed_low"] == "100" and data["observed_high"] == "110"
    # 16x the evidence must not produce a proportional retained object population.
    assert peaks[1] < peaks[0] * 3
    loaded = 0
    original = module._fact_from_bytes
    def count_read(encoded):
        nonlocal loaded
        loaded += 1
        return original(encoded)
    monkeypatch.setattr(module, "_fact_from_bytes", count_read)
    store.projection(track.track_identity)
    assert loaded == 4096
    path = next((store.root / track.track_identity / "facts").iterdir())
    payload = json.loads(path.read_bytes())
    payload["fact"]["last_price"] = "999"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        store.projection(track.track_identity)


def test_consolidation_rejects_prospective_state_without_overwriting_it(tmp_path):
    store, track = _consolidation_history(tmp_path)
    path = store.root / track.track_identity / "current-state.json"
    path.write_bytes(b"prospective checkpoint must not change")
    with pytest.raises(ValueError, match="NOT_HISTORICAL"):
        _consolidate(store, track)
    assert path.read_bytes() == b"prospective checkpoint must not change"


def test_consolidation_has_no_automatic_production_call_sites():
    import ast
    from pathlib import Path
    root = Path(__file__).resolve().parents[4] / "src" / "kronos"
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text())
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "prepare_historical_consolidation":
                owner = node
                while owner in parents and not isinstance(owner, ast.FunctionDef):
                    owner = parents[owner]
                assert path.name == "paper_observation_track.py" and owner.name == "publish_historical_consolidation"


def _blocked(tmp_path, *, red=False):  # type: ignore[no-untyped-def]
    completed, observation = _red(tmp_path) if red else _green(tmp_path)
    return _record(
        completed,
        observation,
        SponsorTradeChoice.PAPER,
        SponsorActivationDisposition.BLOCKED_RISK_UNAVAILABLE,
        acknowledged=red,
    )


def _authority(track, *, run_identity=None):  # type: ignore[no-untyped-def]
    return PaperObservationMonitoringAuthorityV1(
        native_run_identity=run_identity or track.native_run_identity,
        sponsor_decision_identity=track.sponsor_decision_identity,
        opportunity_identity="SWING-OPPORTUNITY-VBL",
        material_revision="MATERIAL-REVISION-V1",
        native_assessment_sha256=track.native_assessment_sha256,
        direction=track.direction,
        geometry_identity=track.step31_observation_identity,
        geometry_sha256=track.step31_observation_sha256,
        review_authority_identity="WO-SWING-07-REVIEW-V1",
        decision_authority_identity=track.sponsor_decision_identity,
        canonical_instrument=track.canonical_instrument,
        instrument_contract_identity=paper_observation_instrument_contract_identity(
            canonical_instrument=track.canonical_instrument,
            provider="KITE", exchange="NSE", segment="NSE",
            trading_symbol=track.canonical_instrument,
            instrument_type="EQ", expiry=None,
        ),
        monitoring_boundary_identity="SWING-D1-CLOSE",
        monitoring_window_identity="FROM_OBSERVATION_BOUNDARY_UNTIL_TERMINAL",
        capability_requirements=("KITE-READ-ONLY", "ORDERED-LIVE-TICKS"),
        policy_identity="SWING-SPONSOR-OBSERVATION-DECISION-V1",
        policy_version="1",
    )


def test_track_binds_exact_blocked_paper_decision_without_position_authority(
    tmp_path,
) -> None:
    result = _blocked(tmp_path)
    track = create_paper_observation_track(
        result,
        current_run_identity=result.snapshot.native_run_identity,
        created_at=NOW,
    )

    assert track.sponsor_decision_identity == result.decision.decision_identity
    assert track.sponsor_decision_timestamp == result.decision.decision_timestamp
    assert track.native_assessment_sha256 == result.snapshot.native_assessment_sha256
    assert track.observation_entry_reference == result.snapshot.entry
    assert track.stop == result.snapshot.stop
    assert track.target == result.snapshot.target
    assert track.step31_warnings == result.snapshot.step31_warnings
    assert track.step31_geometry_status == result.snapshot.step31_geometry_status
    assert track.risk_distance == result.snapshot.risk_distance
    assert track.reward_distance == result.snapshot.reward_distance
    assert track.risk_reward_ratio == result.snapshot.risk_reward_ratio
    assert track.risk_reward_state == result.snapshot.risk_reward_state
    assert track.entry_availability == "AVAILABLE"
    assert track.risk_state == "RISK_UNAVAILABLE"
    assert track.authority == PAPER_OBSERVATION_TRACK_AUTHORITY
    assert "POSITION" in track.authority and "BROKER" in track.authority
    assert not hasattr(track, "position_identity")
    assert not hasattr(track, "quantity")
    assert not hasattr(track, "pnl")


def test_only_current_blocked_paper_decision_is_eligible(tmp_path) -> None:
    blocked = _blocked(tmp_path)
    with pytest.raises(ValueError, match="TRUST_BINDING_INVALID"):
        create_paper_observation_track(
            blocked,
            current_run_identity="SWING-RUN-" + "F" * 32,
            created_at=NOW,
        )

    completed, observation = _green(tmp_path / "ignored")
    ignored = _record(
        completed,
        observation,
        SponsorTradeChoice.IGNORE,
        SponsorActivationDisposition.NOT_APPLICABLE_IGNORE,
    )
    with pytest.raises(ValueError, match="TRUST_BINDING_INVALID"):
        create_paper_observation_track(
            ignored,
            current_run_identity=ignored.snapshot.native_run_identity,
            created_at=NOW,
        )
    completed, observation = _green(tmp_path / "live")
    live = _record(
        completed,
        observation,
        SponsorTradeChoice.LIVE,
        SponsorActivationDisposition.BLOCKED_RISK_UNAVAILABLE,
    )
    with pytest.raises(ValueError, match="TRUST_BINDING_INVALID"):
        create_paper_observation_track(
            live,
            current_run_identity=live.snapshot.native_run_identity,
            created_at=NOW,
        )

    completed, observation = _green(tmp_path / "activated")
    activated = _record(
        completed,
        observation,
        SponsorTradeChoice.PAPER,
        SponsorActivationDisposition.ACTIVATED,
        risk_state="RISK_APPROVED",
        risk_identity="RISK-ACTIVE",
        existing_sponsor_decision_identity="SPONSOR-DECISION-ACTIVE",
        sponsor_position_identity="SPONSOR-POSITION-ACTIVE",
    )
    with pytest.raises(ValueError, match="TRUST_BINDING_INVALID"):
        create_paper_observation_track(
            activated,
            current_run_identity=activated.snapshot.native_run_identity,
            created_at=NOW,
        )


def test_store_is_append_only_restart_safe_and_preserves_exact_ordering(tmp_path) -> None:
    result = _blocked(tmp_path)
    track = create_paper_observation_track(
        result,
        current_run_identity=result.snapshot.native_run_identity,
        created_at=NOW,
    )
    store = LocalPaperObservationTrackStore(tmp_path / "tracks")
    assert store.retain_track(track) == track
    assert store.retain_track(track) == track

    fact = make_market_fact(
        track,
        last_price=track.observation_entry_reference or Decimal("100"),
        observed_at=NOW + timedelta(minutes=1),
        received_at=NOW + timedelta(minutes=1),
        source_identity="KITE:SESSION:1",
        source_sequence=1,
        ordering_deterministic=True,
        recovered=False,
    )
    assert store.append_fact(fact)
    assert not store.append_fact(fact)
    entry = make_event(
        track,
        PaperObservationOutcome.ENTRY_OBSERVED,
        observed_at=NOW + timedelta(minutes=1),
        recorded_at=NOW + timedelta(minutes=1),
        source_identity="KITE:SESSION:1",
        source_kind=PaperObservationSourceKind.KITE_FACTUAL_TICK,
        observed_price=fact.last_price,
    )
    terminal = make_event(
        track,
        PaperObservationOutcome.TARGET_LEVEL_TOUCHED,
        observed_at=NOW + timedelta(minutes=2),
        recorded_at=NOW + timedelta(minutes=2),
        source_identity="KITE:SESSION:2",
        source_kind=PaperObservationSourceKind.KITE_FACTUAL_TICK,
        observed_price=track.target,
    )
    assert store.append_event(entry)
    assert store.append_event(terminal)
    assert not store.append_event(terminal)
    store.append_monitoring(make_monitoring_record(
        track.track_identity,
        PaperObservationMonitoringState.COMPLETE,
        "TERMINAL_FACTUAL_OUTCOME_RETAINED",
        NOW + timedelta(minutes=2),
    ))

    restored = LocalPaperObservationTrackStore(tmp_path / "tracks")
    projection = restored.projection(track.track_identity)
    assert projection.track_state is PaperObservationTrackState.COMPLETE
    assert projection.entry_state is PaperObservationOutcome.ENTRY_OBSERVED
    assert projection.outcome_state is PaperObservationOutcome.TARGET_LEVEL_TOUCHED
    assert restored.facts(track.track_identity) == (fact,)
    assert restored.events(track.track_identity) == (entry, terminal)
    assert (tmp_path / "tracks" / track.track_identity / "track.json").stat().st_mode & 0o777 == 0o600


def test_restoration_projection_skips_large_fact_history_but_full_projection_validates_it(
    tmp_path, monkeypatch
) -> None:
    result = _blocked(tmp_path)
    track = create_paper_observation_track(
        result,
        current_run_identity=result.snapshot.native_run_identity,
        created_at=NOW,
    )
    store = LocalPaperObservationTrackStore(tmp_path / "tracks")
    store.retain_track(track)
    store.append_monitoring(make_monitoring_record(
        track.track_identity,
        PaperObservationMonitoringState.INTERRUPTED,
        "PROVIDER_DISCONNECTED",
        NOW,
    ))
    for sequence in range(512):
        fact = make_market_fact(
            track,
            last_price=(track.observation_entry_reference or Decimal("100")),
            observed_at=NOW + timedelta(microseconds=sequence + 1),
            received_at=NOW + timedelta(microseconds=sequence + 1),
            source_identity=f"KITE:LARGE-HISTORY:{sequence}",
            source_sequence=sequence,
            ordering_deterministic=True,
            recovered=False,
        )
        store.append_fact(fact)

    loaded = []
    original = LocalPaperObservationTrackStore._load_fact

    def counted(self, path):  # type: ignore[no-untyped-def]
        loaded.append(path)
        return original(self, path)

    monkeypatch.setattr(LocalPaperObservationTrackStore, "_load_fact", counted)
    restoration = store.restoration_projection(track.track_identity)
    assert restoration.track_identity == track.track_identity
    assert not restoration.terminal
    assert restoration.monitoring_reason == "PROVIDER_DISCONNECTED"
    assert loaded == []

    full = store.projection(track.track_identity)
    assert full.last_factual_observation_at == NOW + timedelta(microseconds=512)
    assert len(loaded) == 512

    fact_path = next((store.root / track.track_identity / "facts").glob("*.json"))
    fact_path.write_text("{}\n", encoding="utf-8")
    loaded.clear()
    assert store.restoration_projection(track.track_identity).track_identity == track.track_identity
    assert loaded == []
    with pytest.raises(ValueError, match="STORED_RECORD_INVALID"):
        store.projection(track.track_identity)


@pytest.mark.parametrize("record_directory", ["events", "monitoring"])
def test_restoration_projection_validates_every_control_record(
    tmp_path, record_directory
) -> None:  # type: ignore[no-untyped-def]
    result = _blocked(tmp_path)
    track = create_paper_observation_track(
        result,
        current_run_identity=result.snapshot.native_run_identity,
        created_at=NOW,
    )
    store = LocalPaperObservationTrackStore(tmp_path / "tracks")
    store.retain_track(track)
    if record_directory == "events":
        store.append_event(make_event(
            track,
            PaperObservationOutcome.ENTRY_OBSERVED,
            observed_at=NOW,
            recorded_at=NOW,
            source_identity="KITE:RESTORATION:EVENT",
            source_kind=PaperObservationSourceKind.KITE_FACTUAL_TICK,
            observed_price=track.observation_entry_reference,
        ))
    else:
        store.append_monitoring(make_monitoring_record(
            track.track_identity,
            PaperObservationMonitoringState.INTERRUPTED,
            "PROVIDER_DISCONNECTED",
            NOW,
        ))
    path = next((store.root / track.track_identity / record_directory).glob("*.json"))
    path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="STORED_RECORD_INVALID"):
        store.restoration_projection(track.track_identity)


def test_terminal_before_entry_and_mutation_fail_closed(tmp_path) -> None:
    result = _blocked(tmp_path)
    track = create_paper_observation_track(
        result,
        current_run_identity=result.snapshot.native_run_identity,
        created_at=NOW,
    )
    store = LocalPaperObservationTrackStore(tmp_path / "tracks")
    store.retain_track(track)
    terminal = make_event(
        track,
        PaperObservationOutcome.STOP_LEVEL_TOUCHED,
        observed_at=NOW,
        recorded_at=NOW,
        source_identity="COMPLETED-CANDLE-1",
        source_kind=PaperObservationSourceKind.COMPLETED_CANDLE,
        interval_low=Decimal("1"),
        interval_high=Decimal("200"),
    )
    with pytest.raises(ValueError, match="TERMINAL_BEFORE_ENTRY"):
        store.append_event(terminal)
    changed = create_paper_observation_track(
        result,
        current_run_identity=result.snapshot.native_run_identity,
        created_at=NOW + timedelta(seconds=1),
    )
    with pytest.raises(ValueError, match="IMMUTABILITY"):
        store.retain_track(changed)


@pytest.mark.parametrize("red", [False, True])
def test_green_and_red_warning_evidence_is_frozen(tmp_path, red) -> None:  # type: ignore[no-untyped-def]
    result = _blocked(tmp_path, red=red)
    track = create_paper_observation_track(
        result,
        current_run_identity=result.snapshot.native_run_identity,
        created_at=NOW,
    )
    assert track.step31_severity == result.snapshot.step31_severity
    assert track.step31_warnings == result.snapshot.step31_warnings
    assert track.risk_state == result.snapshot.risk_state


def test_amber_and_risk_rejected_blocked_paper_are_eligible(tmp_path) -> None:
    completed = _green(tmp_path)[0]
    amber_observation = _observe(
        completed, _package(completed, prior_directional_swing_high=None)
    )
    amber = _record(
        completed,
        amber_observation,
        SponsorTradeChoice.PAPER,
        SponsorActivationDisposition.BLOCKED_RISK_UNAVAILABLE,
    )
    amber_track = create_paper_observation_track(
        amber,
        current_run_identity=amber.snapshot.native_run_identity,
        created_at=NOW,
    )
    assert amber_track.step31_severity.value == "AMBER"
    assert amber_track.target is None
    assert amber_track.target_availability == "UNAVAILABLE"

    completed, green_observation = _green(tmp_path / "rejected")
    rejected = _record(
        completed,
        green_observation,
        SponsorTradeChoice.PAPER,
        SponsorActivationDisposition.BLOCKED_RISK_REJECTED,
        risk_state="RISK_REJECTED",
        risk_identity="RISK-REJECTED",
    )
    rejected_track = create_paper_observation_track(
        rejected,
        current_run_identity=rejected.snapshot.native_run_identity,
        created_at=NOW,
    )
    assert rejected_track.risk_state == "RISK_REJECTED"
    assert rejected_track.activation_disposition is SponsorActivationDisposition.BLOCKED_RISK_REJECTED


def test_later_run_identity_does_not_rewrite_original_track(tmp_path) -> None:
    result = _blocked(tmp_path)
    track = create_paper_observation_track(
        result,
        current_run_identity=result.snapshot.native_run_identity,
        created_at=NOW,
    )
    store = LocalPaperObservationTrackStore(tmp_path / "tracks")
    store.retain_track(track)
    later_run = "SWING-RUN-" + "A" * 32
    assert later_run != track.native_run_identity
    restored = store.load_track(track.track_identity)
    assert restored == track
    assert restored.native_run_identity == result.snapshot.native_run_identity
    assert restored.observation_entry_reference == result.snapshot.entry
    assert restored.stop == result.snapshot.stop
    assert restored.target == result.snapshot.target


@pytest.mark.parametrize(
    "state,operation,automatic",
    [
        (PaperObservationMonitoringApplicabilityState.OPEN, "AUTOMATIC_RESTORATION_ALLOWED", True),
        (PaperObservationMonitoringApplicabilityState.SUSPENDED, "RECOVERY_REQUIRED", False),
        (PaperObservationMonitoringApplicabilityState.CLOSED, "MONITORING_CLOSED", False),
    ],
)
def test_monitoring_applicability_states_validate_exactly(
    tmp_path, state, operation, automatic
) -> None:  # type: ignore[no-untyped-def]
    result = _blocked(tmp_path)
    track = create_paper_observation_track(
        result,
        current_run_identity=result.snapshot.native_run_identity,
        created_at=NOW,
    )
    store = LocalPaperObservationTrackStore(tmp_path / "tracks")
    store.retain_track(track)
    authority = _authority(track)
    record = make_monitoring_applicability(
        track.track_identity, state, f"{state.value}_BY_GOVERNED_ACTION", authority, NOW
    )
    assert store.append_applicability(record)
    assert store.publish_current_applicability(record)
    assert store.applicability(track.track_identity) == (record,)
    projected = project_monitoring_applicability(record, authority)
    assert projected.state is state
    assert projected.operation == operation
    assert projected.automatic_restoration is automatic
    with pytest.raises(ValueError):
        PaperObservationMonitoringApplicabilityState("EXPIRED")


def test_legacy_track_has_no_backfill_and_unprovable_currentness_is_suspended(
    tmp_path,
) -> None:
    result = _blocked(tmp_path)
    track = create_paper_observation_track(
        result,
        current_run_identity=result.snapshot.native_run_identity,
        created_at=NOW,
    )
    store = LocalPaperObservationTrackStore(tmp_path / "tracks")
    store.retain_track(track)
    before = tuple(store.root.rglob("*.json"))
    projection = store.restoration_projection(track.track_identity)
    assert projection.applicability.state is PaperObservationMonitoringApplicabilityState.SUSPENDED
    assert projection.applicability.operation == "RECOVERY_REQUIRED"
    assert not projection.applicability.automatic_restoration
    assert projection.applicability.reason_codes == ("APPLICABILITY_RECORD_UNAVAILABLE",)
    assert tuple(store.root.rglob("*.json")) == before
    assert not (store.root / track.track_identity / "applicability").exists()

    corrupt = store.root / track.track_identity / "current-applicability.json"
    corrupt.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="STORED_RECORD_INVALID"):
        store.current_applicability(track.track_identity)
    failed_closed = store.restoration_projection(track.track_identity)
    assert failed_closed.applicability.state is PaperObservationMonitoringApplicabilityState.SUSPENDED
    assert failed_closed.applicability.operation == "RECOVERY_REQUIRED"
    assert failed_closed.applicability.reason_codes == ("APPLICABILITY_RECORD_CORRUPT",)


def test_run_identity_alone_does_not_close_compatible_track(tmp_path) -> None:
    result = _blocked(tmp_path)
    track = create_paper_observation_track(
        result,
        current_run_identity=result.snapshot.native_run_identity,
        created_at=NOW,
    )
    retained = make_monitoring_applicability(
        track.track_identity,
        PaperObservationMonitoringApplicabilityState.OPEN,
        "MONITORING_OPENED",
        _authority(track),
        NOW,
    )
    later = _authority(track, run_identity="SWING-RUN-" + "A" * 32)
    projection = project_monitoring_applicability(retained, later)
    assert projection.state is PaperObservationMonitoringApplicabilityState.OPEN
    assert projection.automatic_restoration


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("opportunity_identity", "SWING-OPPORTUNITY-OTHER", "OPPORTUNITY_IDENTITY_INCOMPATIBLE"),
        ("material_revision", "MATERIAL-REVISION-V2", "MATERIAL_REVISION_INCOMPATIBLE"),
        ("native_assessment_sha256", "f" * 64, "NATIVE_ASSESSMENT_INCOMPATIBLE"),
        ("direction", None, "DIRECTION_INCOMPATIBLE"),
        ("geometry_sha256", "e" * 64, "GEOMETRY_INCOMPATIBLE"),
        ("review_authority_identity", "WO-SWING-07-REVIEW-V2", "REVIEW_AUTHORITY_INCOMPATIBLE"),
        ("decision_authority_identity", "SPONSOR-DECISION-OTHER", "DECISION_AUTHORITY_INCOMPATIBLE"),
        ("instrument_contract_identity", "NSE-FUTURE-VBL", "INSTRUMENT_CONTRACT_INCOMPATIBLE"),
        ("monitoring_boundary_identity", "SWING-W1-CLOSE", "MONITORING_BOUNDARY_INCOMPATIBLE"),
        ("capability_requirements", ("KITE-READ-ONLY",), "CAPABILITY_REQUIREMENTS_INCOMPATIBLE"),
    ],
)
def test_incompatible_authority_suspends_automatic_restoration(
    tmp_path, field, value, reason
) -> None:  # type: ignore[no-untyped-def]
    result = _blocked(tmp_path)
    track = create_paper_observation_track(
        result,
        current_run_identity=result.snapshot.native_run_identity,
        created_at=NOW,
    )
    authority = _authority(track)
    retained = make_monitoring_applicability(
        track.track_identity,
        PaperObservationMonitoringApplicabilityState.OPEN,
        "MONITORING_OPENED",
        authority,
        NOW,
    )
    if field == "direction":
        value = (
            type(track.direction).SHORT
            if track.direction is type(track.direction).LONG
            else type(track.direction).LONG
        )
    projection = project_monitoring_applicability(
        retained, replace(authority, **{field: value})
    )
    assert projection.state is PaperObservationMonitoringApplicabilityState.SUSPENDED
    assert projection.operation == "RECOVERY_REQUIRED"
    assert not projection.automatic_restoration
    assert reason in projection.reason_codes


def test_applicability_cannot_change_factual_outcome(tmp_path) -> None:
    result = _blocked(tmp_path)
    track = create_paper_observation_track(
        result,
        current_run_identity=result.snapshot.native_run_identity,
        created_at=NOW,
    )
    store = LocalPaperObservationTrackStore(tmp_path / "tracks")
    store.retain_track(track)
    store.append_event(make_event(
        track,
        PaperObservationOutcome.ENTRY_OBSERVED,
        observed_at=NOW,
        recorded_at=NOW,
        source_identity="KITE:ENTRY",
        source_kind=PaperObservationSourceKind.KITE_FACTUAL_TICK,
        observed_price=track.observation_entry_reference,
    ))
    store.append_event(make_event(
        track,
        PaperObservationOutcome.TARGET_LEVEL_TOUCHED,
        observed_at=NOW + timedelta(seconds=1),
        recorded_at=NOW + timedelta(seconds=1),
        source_identity="KITE:TARGET",
        source_kind=PaperObservationSourceKind.KITE_FACTUAL_TICK,
        observed_price=track.target,
    ))
    closed = make_monitoring_applicability(
        track.track_identity,
        PaperObservationMonitoringApplicabilityState.CLOSED,
        "SPONSOR_STOPPED_MONITORING",
        _authority(track),
        NOW + timedelta(seconds=2),
    )
    store.append_applicability(closed)
    store.publish_current_applicability(closed)
    full = store.projection(track.track_identity)
    restoration = store.restoration_projection(track.track_identity, _authority(track))
    assert full.outcome_state is PaperObservationOutcome.TARGET_LEVEL_TOUCHED
    assert restoration.latest_event is PaperObservationOutcome.TARGET_LEVEL_TOUCHED
    assert restoration.applicability.state is PaperObservationMonitoringApplicabilityState.CLOSED


def test_retention_contract_authorizes_only_material_transitions() -> None:
    assert PAPER_OBSERVATION_RETAINED_MATERIAL_TRANSITIONS == {
        "MONITORING_OPENED",
        "ENTRY_ACTIVATED",
        "STOP_TOUCHED",
        "TARGET_TOUCHED",
        "ORDERING_AMBIGUITY",
        "PROVIDER_MONITORING_GAP",
        "AUTHORITY_SUPERSEDED",
        "SPONSOR_STOPPED_MONITORING",
        "MONITORING_CLOSED",
    }
    assert not any("TICK" in item or "FACT" in item for item in PAPER_OBSERVATION_RETAINED_MATERIAL_TRANSITIONS)


@pytest.mark.parametrize("field", ["last_price", "observed_at", "sequence", "session", "monitoring_generation"])
def test_compact_latest_observation_and_derived_values_cannot_disagree(tmp_path, field):
    from kronos.swing.v1.paper_observation_track import compact_replace
    from tests.unit.application.test_paper_observation_tracking import _compact_started, _tick
    workflow, store, started, instrument = _compact_started(tmp_path)
    identity = started.track.track_identity
    workflow.observe_tick(identity, _tick(instrument, started.track.observation_entry_reference - 1, 1, NOW))
    state = store.load_compact(identity)
    value = {"last_price": state.last_price + 1, "observed_at": NOW + timedelta(seconds=1),
             "sequence": 2, "session": "WRONG", "monitoring_generation": "WRONG"}[field]
    with pytest.raises(ValueError, match="COMPACT_RECOVERY_REQUIRED"):
        compact_replace(state, **{field: value})


def test_compact_exact_material_head_corruption_fails_closed_without_history_scan(tmp_path, monkeypatch):
    from tests.unit.application.test_paper_observation_tracking import _compact_started, _tick, _monitoring_authority
    workflow, store, started, instrument = _compact_started(tmp_path)
    identity, entry = started.track.track_identity, started.track.observation_entry_reference
    workflow.observe_tick(identity, _tick(instrument, entry - 1, 1, NOW))
    workflow.observe_tick(identity, _tick(instrument, entry, 2, NOW + timedelta(seconds=1)))
    state = store.load_compact(identity)
    (store.root / identity / "transitions" / f"{state.material_head}.json").write_bytes(b"{}")
    for name in ("facts", "events", "monitoring", "projection"):
        monkeypatch.setattr(store, name, lambda *_: pytest.fail("history fallback"))
    projected = store.restoration_projection(identity, _monitoring_authority(started.track))
    assert projected.applicability.operation == "RECOVERY_REQUIRED"
