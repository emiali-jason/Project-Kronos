from dataclasses import asdict, replace
from datetime import timedelta
from decimal import Decimal

import pytest

from kronos.swing.v1.native_sponsor_decision import SponsorTradeChoice
from kronos.swing.v1.observation_research_ledger_v2 import (
    CurrentMarketFactV2,
    GovernedPositionPresentationFactsV2,
    LocalObservationResearchLedgerV2Store,
    ObservationMode,
    ObservationOperationalRoute,
    ObservationResearchLedgerV2Service,
    ObservationResearchQueryV2,
    WebSocketPresentationState,
    _distance,
)
from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.paper_observation_track import (
    LocalPaperObservationTrackStore,
    PaperObservationOutcome,
    PaperObservationSourceKind,
    PaperObservationTrackState,
    _values_digest as paper_digest,
    create_paper_observation_track,
    make_event,
)
from kronos.swing.v1.sponsor_observation_decision import (
    SponsorActivationDisposition,
)
from kronos.swing.v1.step31_observation import Step31WarningSeverity
from tests.unit.swing.v1.test_observation_research_ledger import _service
from tests.unit.swing.v1.test_sponsor_observation_decision import (
    NOW,
    _green,
    _record,
    _red,
)


def _v2(tmp_path, result):  # type: ignore[no-untyped-def]
    v1 = _service(tmp_path, result)
    paper = LocalPaperObservationTrackStore(tmp_path / "paper")
    service = ObservationResearchLedgerV2Service(
        LocalObservationResearchLedgerV2Store(tmp_path / "v2"), v1, paper
    )
    service.retain_decision(result.decision.decision_identity)
    return service, paper


def _blocked(tmp_path):  # type: ignore[no-untyped-def]
    completed, observation = _red(tmp_path)
    return _record(
        completed,
        observation,
        SponsorTradeChoice.PAPER,
        SponsorActivationDisposition.BLOCKED_RISK_UNAVAILABLE,
        risk_state="RISK_UNAVAILABLE",
        acknowledged=True,
    )


def test_blocked_paper_is_one_row_and_late_track_is_linked_idempotently(tmp_path) -> None:
    result = _blocked(tmp_path)
    service, paper = _v2(tmp_path, result)

    before = service.snapshot()[0]
    assert before.paper_track_state is PaperObservationTrackState.AVAILABLE
    assert before.paper_track is None

    track = create_paper_observation_track(
        result,
        current_run_identity=result.snapshot.native_run_identity,
        created_at=NOW,
    )
    paper.retain_track(track)
    first = service.synchronize()
    second = service.synchronize()

    assert len(first) == len(second) == 1
    assert first == second
    assert first[0].paper_track is not None
    assert first[0].paper_track_state is PaperObservationTrackState.ACTIVE
    assert len(first[0].paper_links) == 1


def test_track_events_outcome_restart_query_and_export_remain_separate(tmp_path) -> None:
    result = _blocked(tmp_path)
    service, paper = _v2(tmp_path, result)
    track = paper.retain_track(create_paper_observation_track(
        result,
        current_run_identity=result.snapshot.native_run_identity,
        created_at=NOW,
    ))
    entry = make_event(
        track,
        PaperObservationOutcome.ENTRY_OBSERVED,
        observed_at=NOW + timedelta(minutes=1),
        recorded_at=NOW + timedelta(minutes=1),
        source_identity="KITE-FACT-1",
        source_kind=PaperObservationSourceKind.KITE_FACTUAL_TICK,
        observed_price=track.observation_entry_reference,
    )
    target = make_event(
        track,
        PaperObservationOutcome.TARGET_LEVEL_TOUCHED,
        observed_at=NOW + timedelta(minutes=2),
        recorded_at=NOW + timedelta(minutes=2),
        source_identity="KITE-FACT-2",
        source_kind=PaperObservationSourceKind.KITE_FACTUAL_TICK,
        observed_price=track.target,
    )
    paper.append_event(entry)
    paper.append_event(target)

    query = ObservationResearchQueryV2(
        choices=(SponsorTradeChoice.PAPER,),
        dispositions=(SponsorActivationDisposition.BLOCKED_RISK_UNAVAILABLE,),
        severities=(Step31WarningSeverity.RED,),
        risk_states=("RISK_UNAVAILABLE",),
        paper_track_states=(PaperObservationTrackState.COMPLETE,),
        paper_track_present=True,
        sponsor_position_present=False,
    )
    projected = service.synchronize()
    assert len(projected) == 1
    assert len(projected[0].paper_links) == 4  # track + 2 events + terminal link
    assert projected[0].paper_track.outcome_state is PaperObservationOutcome.TARGET_LEVEL_TOUCHED
    assert len(service.snapshot(query)) == 1
    exported = service.export_json(query)
    assert '"paper_track_outcome":"TARGET_LEVEL_TOUCHED"' in exported
    assert '"paper_track_monetary_pnl":"UNAVAILABLE"' in exported
    assert "win_rate" not in exported and "actual_r" not in exported
    assert "paper_track_identity" in service.export_csv(query).splitlines()[0]

    restored = ObservationResearchLedgerV2Service(service.store, service.v1, paper)
    assert restored.synchronize() == projected


def test_activated_paper_live_and_ignore_never_manufacture_track(tmp_path) -> None:
    completed, observation = _green(tmp_path)
    activated = _record(
        completed,
        observation,
        SponsorTradeChoice.PAPER,
        SponsorActivationDisposition.ACTIVATED,
        risk_state="RISK_APPROVED",
        risk_identity="RISK-1",
        existing_sponsor_decision_identity="SPONSOR-DECISION-1",
        sponsor_position_identity="SPONSOR-POSITION-1",
    )
    service, _paper = _v2(tmp_path, activated)
    projected = service.snapshot()[0]
    assert projected.paper_track is None
    assert projected.paper_track_state is PaperObservationTrackState.NOT_APPLICABLE_POSITION_ACTIVATED
    position_fact = GovernedPositionPresentationFactsV2(
        activated.decision.decision_identity,
        "SPONSOR-POSITION-1",
        SponsorTradeChoice.PAPER,
        "CLOSED",
        Decimal("101"),
        Decimal("111"),
        Decimal("1000"),
        NOW + timedelta(days=1),
        "9" * 64,
    )
    handoff = service.operational_handoffs(
        governed_current_trading_date=(NOW + timedelta(days=1)).date(),
        completion_trading_dates={
            activated.decision.decision_identity: (NOW + timedelta(days=1)).date()
        },
        position_facts={activated.decision.decision_identity: position_fact},
    )[0]
    assert handoff.mode is ObservationMode.PAPER
    assert handoff.entry == Decimal("101")
    assert handoff.exit == Decimal("111")
    assert handoff.position_gross_pnl == Decimal("1000")
    assert handoff.monetary_pnl_state == "AVAILABLE"

    for choice, disposition in (
        (SponsorTradeChoice.LIVE, SponsorActivationDisposition.BLOCKED_RISK_UNAVAILABLE),
        (SponsorTradeChoice.IGNORE, SponsorActivationDisposition.NOT_APPLICABLE_IGNORE),
    ):
        other_root = tmp_path / choice.value
        completed, observation = _red(other_root)
        result = _record(completed, observation, choice, disposition, acknowledged=True)
        other, _ = _v2(other_root, result)
        assert other.snapshot()[0].paper_track_state is None


def test_current_ltp_distance_is_projection_only_and_touch_state_wins(tmp_path) -> None:
    result = _blocked(tmp_path)
    service, paper = _v2(tmp_path, result)
    track = paper.retain_track(create_paper_observation_track(
        result,
        current_run_identity=result.snapshot.native_run_identity,
        created_at=NOW,
    ))
    fact = CurrentMarketFactV2(
        result.snapshot.canonical_instrument,
        Decimal("105"),
        NOW + timedelta(minutes=1),
        "KITE-CONNECT-WEBSOCKET",
        True,
    )
    handoff = service.operational_handoffs(
        current_facts={result.snapshot.canonical_instrument: fact},
        governed_current_trading_date=NOW.date(),
        websocket_state=WebSocketPresentationState.CONNECTED,
    )[0]
    assert handoff.mode is ObservationMode.PAPER_OBSERVATION
    assert handoff.distance_to_target == result.snapshot.target - Decimal("105")
    assert handoff.distance_to_stop == Decimal("105") - result.snapshot.stop
    assert handoff.monetary_pnl_state == "UNAVAILABLE"
    assert handoff.operational_route is ObservationOperationalRoute.ACTIVE
    assert "105" not in service.export_json()

    paper.append_event(make_event(
        track,
        PaperObservationOutcome.ENTRY_OBSERVED,
        observed_at=NOW + timedelta(minutes=2),
        recorded_at=NOW + timedelta(minutes=2),
        source_identity="KITE-FACT-ENTRY",
        source_kind=PaperObservationSourceKind.KITE_FACTUAL_TICK,
        observed_price=track.observation_entry_reference,
    ))
    paper.append_event(make_event(
        track,
        PaperObservationOutcome.TARGET_LEVEL_TOUCHED,
        observed_at=NOW + timedelta(minutes=3),
        recorded_at=NOW + timedelta(minutes=3),
        source_identity="KITE-FACT-TARGET",
        source_kind=PaperObservationSourceKind.KITE_FACTUAL_TICK,
        observed_price=track.target,
    ))
    touched = service.operational_handoffs(
        current_facts={result.snapshot.canonical_instrument: fact},
        governed_current_trading_date=NOW.date(),
        completion_trading_dates={result.decision.decision_identity: NOW.date()},
    )[0]
    assert touched.distance_to_target is None
    assert touched.distance_to_target_state == "TARGET_LEVEL_TOUCHED"
    assert touched.operational_route is ObservationOperationalRoute.COMPLETED_CURRENT_TRADING_DAY


def test_long_short_distance_formulas_and_unavailable_values_are_exact() -> None:
    assert _distance(
        V1Direction.LONG, Decimal("100"), Decimal("120"), "TARGET", None
    ) == ("AVAILABLE", Decimal("20"))
    assert _distance(
        V1Direction.LONG, Decimal("100"), Decimal("90"), "STOP", None
    ) == ("AVAILABLE", Decimal("10"))
    assert _distance(
        V1Direction.SHORT, Decimal("100"), Decimal("80"), "TARGET", None
    ) == ("AVAILABLE", Decimal("20"))
    assert _distance(
        V1Direction.SHORT, Decimal("100"), Decimal("110"), "STOP", None
    ) == ("AVAILABLE", Decimal("10"))
    assert _distance(V1Direction.SHORT, None, Decimal("80"), "TARGET", None) == (
        "UNAVAILABLE", None
    )


def test_corrupt_foreign_track_fails_closed_without_changing_primary_row(tmp_path) -> None:
    result = _blocked(tmp_path)
    service, paper = _v2(tmp_path, result)
    track = create_paper_observation_track(
        result,
        current_run_identity=result.snapshot.native_run_identity,
        created_at=NOW,
    )
    values = asdict(track)
    values["canonical_instrument"] = "FOREIGN"
    values["integrity_sha256"] = ""
    corrupt = replace(
        track,
        canonical_instrument="FOREIGN",
        integrity_sha256=paper_digest(values),
    )
    paper.retain_track(corrupt)

    with pytest.raises(ValueError, match="TRACK_BINDING_INVALID"):
        service.synchronize()
    assert len(service.store.load_records()) == 1
    assert service.store.load_links() == ()
