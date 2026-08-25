from datetime import timedelta
from decimal import Decimal

import pytest

from kronos.swing.v1.native_sponsor_decision import SponsorTradeChoice
from kronos.swing.v1.paper_observation_track import (
    LocalPaperObservationTrackStore,
    PAPER_OBSERVATION_TRACK_AUTHORITY,
    PaperObservationMonitoringState,
    PaperObservationOutcome,
    PaperObservationSourceKind,
    PaperObservationTrackState,
    create_paper_observation_track,
    make_event,
    make_market_fact,
    make_monitoring_record,
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


def _blocked(tmp_path, *, red=False):  # type: ignore[no-untyped-def]
    completed, observation = _red(tmp_path) if red else _green(tmp_path)
    return _record(
        completed,
        observation,
        SponsorTradeChoice.PAPER,
        SponsorActivationDisposition.BLOCKED_RISK_UNAVAILABLE,
        acknowledged=red,
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
