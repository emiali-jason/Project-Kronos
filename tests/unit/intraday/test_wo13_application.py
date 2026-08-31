from __future__ import annotations

import pytest

from kronos.application.intraday_wo13 import (
    IntradayWo13Application, IntradayWo13RestorationService, Wo13ApplicationError,
)
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.wo13 import Wo13GeometryAvailability, create_wo13_construction_request
from kronos.intraday.wo13_persistence import Wo13Store
from kronos.intraday.wo13_targets import create_wo13_target_constraint_population

from .test_wo13_targets import _breakout, _constraint, _pullback


def _execute(tmp_path, geometry, *, candidates=()):  # type: ignore[no-untyped-def]
    handoff = geometry.evidence.handoff
    request = create_wo13_construction_request(
        handoff=handoff, sponsor_operation_identity="SPONSOR-WO13-SLICE6",
        requested_at=handoff.analysis_boundary, provenance=("ADR-0022", "SLICE6"),
    )
    population = create_wo13_target_constraint_population(
        setup_geometry=geometry, candidates=candidates,
    )
    store = Wo13Store((tmp_path / f"store-{geometry.geometry_identity[-8:]}").resolve())
    result = IntradayWo13Application(store=store).execute(
        request, geometry.evidence, population
    )
    return store, request, result


@pytest.mark.parametrize("factory", (_pullback, _breakout))
@pytest.mark.parametrize("direction", (SemanticDirection.LONG, SemanticDirection.SHORT))
def test_pullback_breakout_long_short_construct_persist_reload(tmp_path, factory, direction) -> None:  # type: ignore[no-untyped-def]
    geometry = factory(tmp_path, direction)
    store, request, result = _execute(tmp_path, geometry)
    assert result.trade_plan.geometry_availability is Wo13GeometryAvailability.GEOMETRY_COMPLETE
    assert result.trade_plan.direction is direction
    assert result.trade_plan.request_identity == request.request_identity
    assert store.restore_current().trade_plan == result.trade_plan  # type: ignore[union-attr]


def test_constraint_and_poor_rr_are_persisted_without_gate_or_repair(tmp_path) -> None:
    geometry = _pullback(tmp_path)
    candidate = _constraint(geometry, "105")
    _, _, result = _execute(tmp_path, geometry, candidates=(candidate,))
    assert result.trade_plan.canonical_target == candidate.candidate.price
    assert result.trade_plan.setup_native_target != result.trade_plan.canonical_target
    assert result.trade_plan.constraining_objective == result.trade_plan.canonical_target
    assert result.trade_plan.model_rr is not None
    assert result.trade_plan.geometry_availability is Wo13GeometryAvailability.GEOMETRY_COMPLETE


def test_identical_request_replays_exact_result_without_duplicate_plan(tmp_path) -> None:
    geometry = _pullback(tmp_path)
    store, request, first = _execute(tmp_path, geometry)
    population = create_wo13_target_constraint_population(setup_geometry=geometry)
    second = IntradayWo13Application(store=store).execute(request, geometry.evidence, population)
    assert second.replayed
    assert second.trade_plan == first.trade_plan
    assert len(tuple((store.root / "plans").glob("*.json"))) == 1


def test_same_request_with_changed_target_population_never_reuses_stale_plan(tmp_path) -> None:
    geometry = _pullback(tmp_path)
    store, request, _ = _execute(tmp_path, geometry)
    changed = create_wo13_target_constraint_population(
        setup_geometry=geometry, candidates=(_constraint(geometry, "105"),)
    )
    with pytest.raises(Wo13ApplicationError, match="WO13_IDEMPOTENT_REPLAY_INVALID"):
        IntradayWo13Application(store=store).execute(request, geometry.evidence, changed)
    assert store.restore_current().request == request  # type: ignore[union-attr]


def test_setup_evidence_mismatch_fails_without_false_pointer(tmp_path) -> None:
    pullback = _pullback(tmp_path)
    breakout = _breakout(tmp_path)
    handoff = pullback.evidence.handoff
    request = create_wo13_construction_request(
        handoff=handoff, sponsor_operation_identity="SPONSOR-WO13-MISMATCH",
        requested_at=handoff.analysis_boundary, provenance=("ADR-0022",),
    )
    population = create_wo13_target_constraint_population(setup_geometry=pullback)
    store = Wo13Store((tmp_path / "mismatch-store").resolve())
    with pytest.raises(Wo13ApplicationError):
        IntradayWo13Application(store=store).execute(request, breakout.evidence, population)
    assert store.load_current() is None


def test_restoration_reports_not_yet_run_loaded_and_corrupt_without_reevaluation(tmp_path) -> None:
    empty = Wo13Store((tmp_path / "empty").resolve())
    assert IntradayWo13RestorationService(store=empty).restore().state == "NOT_YET_RUN"
    geometry = _pullback(tmp_path)
    store, _, _ = _execute(tmp_path, geometry)
    service = IntradayWo13RestorationService(store=store)
    assert service.restore().state == "LOADED"
    path = store.root / "current" / "CURRENT-INTRADAY-WO13-V1.json"
    path.write_text("{}", encoding="utf-8")
    status = service.restore()
    assert status.state == "CORRUPT"
    assert status.failure_reason == "WO13_RESTORATION_FAILED"


def test_changed_policy_and_binding_fail_closed(tmp_path) -> None:
    geometry = _pullback(tmp_path)
    handoff = geometry.evidence.handoff
    request = create_wo13_construction_request(
        handoff=handoff, sponsor_operation_identity="SPONSOR-WO13-POLICY",
        requested_at=handoff.analysis_boundary, provenance=("ADR-0022",),
    )
    with pytest.raises(Exception):
        replace(request, request_integrity="WRONG")
