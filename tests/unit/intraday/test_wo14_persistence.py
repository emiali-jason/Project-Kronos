from __future__ import annotations

import pytest

from kronos.intraday.wo14 import create_wo14_observation_request
from kronos.intraday.wo14_persistence import Wo14PersistenceError, Wo14Store

from .test_wo14_application import _components


def test_append_only_artifacts_exact_reload_and_current_alias(tmp_path) -> None:
    application, store, request = _components(tmp_path)
    result = application.execute(request)
    request_path = store.root / "requests" / f"{request.request_identity}.json"
    observation_path = (
        store.root / "observations" / f"{result.observation.observation_identity}.json"
    )
    before = (request_path.read_bytes(), observation_path.read_bytes())

    assert store.retain_request(request) == request_path
    assert store.retain_observation(result.observation) == observation_path
    assert (request_path.read_bytes(), observation_path.read_bytes()) == before
    assert store.load_request(request.request_identity) == request
    assert store.load_observation(result.observation.observation_identity) == result.observation


def test_same_identity_different_bytes_conflicts_without_overwrite(tmp_path) -> None:
    _, store, request = _components(tmp_path)
    path = store.retain_request(request)
    path.write_text("foreign", encoding="utf-8")
    with pytest.raises(Wo14PersistenceError, match="WO14_IMMUTABLE_CONFLICT"):
        store.retain_request(request)
    assert path.read_text(encoding="utf-8") == "foreign"


def test_path_traversal_and_artifact_corruption_fail_closed(tmp_path) -> None:
    application, store, request = _components(tmp_path)
    result = application.execute(request)
    with pytest.raises(Wo14PersistenceError, match="WO14_ARTIFACT_PATH_INVALID"):
        store.load_observation("../latest")

    path = store.root / "observations" / f"{result.observation.observation_identity}.json"
    path.write_bytes(path.read_bytes()[:-5])
    with pytest.raises(Wo14PersistenceError, match="WO14_ARTIFACT_INTEGRITY_INVALID"):
        store.load_observation(result.observation.observation_identity)


def test_latest_failure_pointer_is_separate_from_current_observation(tmp_path) -> None:
    application, store, request = _components(tmp_path)
    result = application.execute(request)
    current = store.load_current()
    plan = application.wo13_store.load_trade_plan(
        request.plan_binding.trade_plan_identity
    )
    application._wo13_store = type(application.wo13_store)(  # noqa: SLF001
        (tmp_path / "empty-wo13").resolve()
    )
    changed = create_wo14_observation_request(
        plan=plan,
        sponsor_operation_identity="SPONSOR-WO14-FAILURE-TEST",
        requested_at=plan.analysis_boundary,
        evaluation_boundary=plan.analysis_boundary,
        provenance=("ADR-0023", "WO14-FAILURE-TEST"),
    )
    with pytest.raises(Exception):
        application.execute(changed)

    assert store.load_current() == current
    assert store.load_current().observation_identity == result.observation.observation_identity
    assert store.load_latest_failure() is not None
