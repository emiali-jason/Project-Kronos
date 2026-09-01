from __future__ import annotations

import pytest

from kronos.application.intraday_wo14 import (
    IntradayWo14Application,
    IntradayWo14RestorationService,
    Wo14ApplicationError,
)
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.wo14 import create_wo14_observation_request
from kronos.intraday.wo14 import (
    Wo14QuantitySemantics,
    Wo14UnitSemantics,
    create_wo14_reference_quantity,
)
from kronos.intraday.wo14_persistence import Wo14Store

from .test_wo13_application import _execute
from .test_wo13_targets import _pullback


def _components(tmp_path):  # type: ignore[no-untyped-def]
    wo13, _, executed = _execute(tmp_path, _pullback(tmp_path))
    plan = executed.trade_plan
    request = create_wo14_observation_request(
        plan=plan,
        sponsor_operation_identity="SPONSOR-WO14-APPLICATION-TEST",
        requested_at=plan.analysis_boundary,
        evaluation_boundary=plan.analysis_boundary,
        provenance=("ADR-0023", "WO14-APPLICATION-TEST"),
    )
    store = Wo14Store((tmp_path / "wo14").resolve())
    return IntradayWo14Application(wo13_store=wo13, store=store), store, request


def test_exact_current_plan_executes_persists_reloads_and_replays(tmp_path) -> None:
    application, store, request = _components(tmp_path)

    first = application.execute(request)
    second = application.execute(request)
    restored = store.restore_current()

    assert not first.replayed and second.replayed
    assert second.observation == first.observation
    assert restored is not None
    assert restored.observation == first.observation
    assert restored.request == request
    assert len(tuple((store.root / "observations").glob("*.json"))) == 1


def test_superseded_wo13_plan_rejected_and_current_observation_preserved(tmp_path) -> None:
    application, store, request = _components(tmp_path)
    first = application.execute(request)
    old_plan = application.wo13_store.load_trade_plan(
        request.plan_binding.trade_plan_identity
    )

    replacement_wo13, _, _ = _execute(
        tmp_path / "replacement",
        _pullback(tmp_path / "replacement", SemanticDirection.SHORT),
    )
    application._wo13_store = replacement_wo13  # noqa: SLF001
    superseded = create_wo14_observation_request(
        plan=old_plan,
        sponsor_operation_identity="SPONSOR-WO14-SUPERSEDED",
        requested_at=old_plan.analysis_boundary,
        evaluation_boundary=old_plan.analysis_boundary,
        provenance=("ADR-0023", "WO14-SUPERSEDED-TEST"),
    )

    with pytest.raises(Wo14ApplicationError, match="WO14_SUPERSEDED_WO13_REJECTED"):
        application.execute(superseded)
    restored = store.restore_current()
    assert restored is not None and restored.observation == first.observation
    assert store.load_latest_failure() is not None


def test_absent_current_wo13_fails_without_false_observation(tmp_path) -> None:
    application, store, request = _components(tmp_path)
    application._wo13_store = type(application.wo13_store)(  # noqa: SLF001
        (tmp_path / "empty-wo13").resolve()
    )

    with pytest.raises(Wo14ApplicationError, match="WO14_CURRENT_WO13_UNAVAILABLE"):
        application.execute(request)
    assert store.load_current() is None
    assert store.load_latest_failure() is not None


def test_restoration_not_yet_run_loaded_and_corrupt_are_distinct(tmp_path) -> None:
    empty = Wo14Store((tmp_path / "empty").resolve())
    assert IntradayWo14RestorationService(store=empty).restore().state == "NOT_YET_RUN"

    application, store, request = _components(tmp_path)
    application.execute(request)
    service = IntradayWo14RestorationService(store=store)
    assert service.restore().state == "LOADED"

    path = store.root / "current" / "CURRENT-INTRADAY-WO14-V1.json"
    path.write_text("{}", encoding="utf-8")
    status = service.restore()
    assert status.state == "CORRUPT"
    assert status.failure_reason == "WO14_RESTORATION_FAILED"


def test_nonblocking_single_operation_lock_fails_closed(tmp_path) -> None:
    application, store, request = _components(tmp_path)
    assert application._lock.acquire(blocking=False)  # noqa: SLF001
    try:
        with pytest.raises(Wo14ApplicationError, match="WO14_OPERATION_BUSY"):
            application.execute(request)
    finally:
        application._lock.release()  # noqa: SLF001
    assert store.load_current() is None


def test_changed_factual_snapshot_creates_new_observation_and_supersession(tmp_path) -> None:
    application, store, request = _components(tmp_path)
    first = application.execute(request)
    plan = application.wo13_store.load_trade_plan(
        request.plan_binding.trade_plan_identity
    )
    quantity = create_wo14_reference_quantity(
        quantity=500,
        semantics=Wo14QuantitySemantics.SPONSOR_REFERENCE_QUANTITY,
        unit_semantics=Wo14UnitSemantics.SHARES,
        source_identity="SPONSOR-REFERENCE-QUANTITY-V2",
        observed_at=plan.analysis_boundary,
    )
    successor = create_wo14_observation_request(
        plan=plan,
        sponsor_operation_identity="SPONSOR-WO14-SUCCESSOR",
        requested_at=plan.analysis_boundary,
        evaluation_boundary=plan.analysis_boundary,
        provenance=("ADR-0023", "WO14-SUCCESSOR-TEST"),
        reference_quantity=quantity,
    )

    second = application.execute(successor)
    restored = store.restore_current()
    assert second.observation.observation_identity != first.observation.observation_identity
    assert second.supersession is not None
    assert second.supersession.predecessor_observation_identity == first.observation.observation_identity
    assert restored is not None and restored.supersession == second.supersession
