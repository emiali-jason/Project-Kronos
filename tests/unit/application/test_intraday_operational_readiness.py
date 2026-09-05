from __future__ import annotations

from datetime import timedelta

import pytest

from kronos.application.intraday_operational_readiness import (
    IntradayOperationalReadinessRuntimeService,
    WoBRuntimeState,
    _safe_reason,
)
from kronos.application.intraday_runtime import create_intraday_runtime
from kronos.intraday.operational_readiness_persistence import WoBStore
from tests.unit.intraday.test_operational_readiness_composition import (
    _boundary,
    _composition,
    _foundation,
)
from tests.unit.provider.test_shared_provider_runtime import _shared


UNSAFE_FAILURE_INPUTS = (
    "database exploded",
    "access_token=TEST_ONLY_NON_SECRET_VALUE",
    "password=PASSWORD_TEST_ONLY_VALUE",
    "api_key=API_KEY_TEST_ONLY_VALUE",
    "Authorization: Bearer BEARER_TEST_ONLY_VALUE",
    "/Users/example/private/path/test",
    "https://example.invalid/?token=TEST_ONLY",
    "Traceback (most recent call last): private diagnostic suffix",
    "arbitrary private diagnostic sentence",
    "ACCESS_TOKEN_TEST_ONLY_NON_SECRET_VALUE__PRIVATE_EXAMPLE_DIAGNOSTIC-DETAIL",
    "PASSWORD_TEST_ONLY_VALUE",
    "API_KEY_TEST_ONLY_VALUE",
    "BEARER_TEST_ONLY_VALUE",
    "WO_B_DOMAIN_001_BINDING_UNAVAILABLE_SECRET_SUFFIX",
    "WO_B_DOMAIN_001_BINDING_UNAVAILABLE\npassword=TEST_ONLY",
)
SAFE_FALLBACK = "WO_B_INTERNAL_PROJECTION_FAILURE"


class _Loader:
    def __init__(self, requests=()):  # type: ignore[no-untyped-def]
        self.requests = requests
        self.calls = 0

    def current_requests(self, observed_at):  # type: ignore[no-untyped-def]
        self.calls += 1
        return self.requests


def _service(tmp_path, *, loader=None):  # type: ignore[no-untyped-def]
    loader = loader or _Loader((_composition(*_foundation()),))
    return IntradayOperationalReadinessRuntimeService(
        loader=loader,
        store=WoBStore((tmp_path / "wo-b").resolve()),
        clock=lambda: _boundary() + timedelta(minutes=20),
    )


def test_startup_restoration_and_preview_are_inert(tmp_path) -> None:  # type: ignore[no-untyped-def]
    loader = _Loader((_composition(*_foundation()),))
    service = _service(tmp_path, loader=loader)
    assert loader.calls == 0
    assert not service.store.root.exists()

    projection = service.preview()

    assert projection.state is WoBRuntimeState.AVAILABLE
    assert len(projection.reviews) == 1
    assert loader.calls == 1
    assert not service.store.root.exists()


def test_explicit_rebuild_publishes_only_wo_b_and_restores(tmp_path) -> None:  # type: ignore[no-untyped-def]
    service = _service(tmp_path)
    projection = service.rebuild()
    candidate = projection.reviews[0].candidate_identity
    restored = service.store.restore_current(candidate)
    assert restored.snapshot == projection.reviews[0]

    replay = service.rebuild()
    assert replay.reviews == projection.reviews
    restarted = _service(tmp_path)
    assert restarted.status_document()["runtime_loaded"] is True


def test_empty_sources_are_truthful_not_yet_run(tmp_path) -> None:  # type: ignore[no-untyped-def]
    service = _service(tmp_path, loader=_Loader())
    document = service.status_document()
    assert document["restoration_state"] == "NOT_YET_RUN"
    assert document["reviews"] == ()
    assert document["provider_calls"] == 0
    assert document["upstream_operations"] == 0
    assert document["sponsor_operations"] == 0
    assert document["broker_operations"] == 0


def test_preview_failure_is_sanitized_and_does_not_destroy_restored_current(tmp_path) -> None:  # type: ignore[no-untyped-def]
    service = _service(tmp_path)
    published = service.rebuild().reviews

    class _Failing:
        def current_requests(self, observed_at):  # type: ignore[no-untyped-def]
            raise ValueError("foreign /private/path raw detail")

    failed = IntradayOperationalReadinessRuntimeService(
        loader=_Failing(),
        store=service.store,
        clock=lambda: _boundary() + timedelta(minutes=30),
    ).preview()
    assert failed.state is WoBRuntimeState.UNAVAILABLE
    assert failed.reviews == published
    assert "/" not in failed.failure_reason
    assert " " not in failed.failure_reason
    assert failed.failure_reason == SAFE_FALLBACK


def test_corrupt_restoration_fails_closed_without_rebuild_or_write(tmp_path) -> None:  # type: ignore[no-untyped-def]
    service = _service(tmp_path)
    candidate = service.rebuild().reviews[0].candidate_identity
    alias = service.store._current_path(candidate)
    alias.write_text("{}", encoding="utf-8")
    before = alias.read_bytes()

    restarted = _service(tmp_path)
    document = restarted.status_document()

    assert document["restoration_state"] == "CORRUPT"
    assert document["reviews"] == ()
    assert document["failure_reason"] == "WO_B_ARTIFACT_INTEGRITY_INVALID"
    assert alias.read_bytes() == before


def test_status_preserves_source_state_and_review_classification(tmp_path) -> None:  # type: ignore[no-untyped-def]
    document = _service(tmp_path).status_document()
    review = document["reviews"][0]  # type: ignore[index]
    probable = next(
        item for item in review["items"]  # type: ignore[index]
        if item["source_boundary"] == "PROBABLES"
    )
    assert probable["source_state"] == "LONG_PROBABLE"
    assert probable["classification"] == "AVAILABLE"
    assert review["next_governed_stage"] == "ANALYTICAL_PROMOTION"  # type: ignore[index]
    assert review["sponsor_attention_available"] is False  # type: ignore[index]


def test_runtime_composes_wo_b_restore_only_without_provider_or_evidence_write(tmp_path) -> None:  # type: ignore[no-untyped-def]
    shared, provider, factory_calls = _shared()
    runtime = create_intraday_runtime(shared, evidence_root=tmp_path.resolve())
    assert runtime.wo_b_store.root == (
        tmp_path.resolve() / "wo-b-operational-readiness-review-v1"
    )
    assert runtime.wo_b_runtime.store is runtime.wo_b_store
    assert runtime.wo_b_runtime.status_document()["restoration_state"] == "NOT_YET_RUN"
    assert provider.capability.calls == 0
    assert provider.begin_count == 0
    assert factory_calls == []
    assert not runtime.wo_b_store.root.exists()


@pytest.mark.parametrize("raw", UNSAFE_FAILURE_INPUTS)
@pytest.mark.parametrize("error_type", (ValueError, RuntimeError))
def test_unknown_exception_reason_is_generic_without_raw_content(raw, error_type) -> None:  # type: ignore[no-untyped-def]
    assert _safe_reason(error_type(raw)) == SAFE_FALLBACK


@pytest.mark.parametrize("code", (
    "WO_B_DOMAIN_001_BINDING_UNAVAILABLE",
    "WO_B_ARTIFACT_INTEGRITY_INVALID",
    "WO_B_CURRENT_SNAPSHOT_NOT_NEWER",
))
def test_known_failure_reason_remains_exact(code) -> None:  # type: ignore[no-untyped-def]
    assert _safe_reason(ValueError(code)) == code


def test_failure_projection_never_calls_exception_serializers() -> None:
    class HostileError(RuntimeError):
        def __str__(self):
            raise AssertionError("Exception text must not be serialized")

        def __repr__(self):
            raise AssertionError("Exception repr must not be serialized")

    assert _safe_reason(HostileError("private")) == SAFE_FALLBACK
    assert _safe_reason(HostileError("WO_B_DOMAIN_001_BINDING_UNAVAILABLE")) == "WO_B_DOMAIN_001_BINDING_UNAVAILABLE"
    assert _safe_reason(RuntimeError("WO_B_DOMAIN_001_BINDING_UNAVAILABLE", "secret")) == SAFE_FALLBACK
    assert _safe_reason(RuntimeError()) == SAFE_FALLBACK


def test_unknown_restoration_error_is_generic_and_inert(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def failed_store(self):
        raise RuntimeError("password=PASSWORD_TEST_ONLY_VALUE")

    monkeypatch.setattr(WoBStore, "current_candidates", failed_store)
    service = _service(tmp_path)
    assert service.status_document()["restoration_state"] == "CORRUPT"
    assert service.status_document()["failure_reason"] == SAFE_FALLBACK
    assert not service.store.root.exists()


def test_legacy_failure_bytes_restore_unchanged_but_project_safely(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import kronos.intraday.operational_readiness_persistence as persistence
    from kronos.browser.intraday_views import render_intraday_operational_readiness
    from tests.unit.browser.test_product_route_isolation import _snapshot

    service = _service(tmp_path)
    snapshot = service.rebuild().reviews[0]
    failure = persistence.create_wo_b_failure(
        candidate_identity=snapshot.candidate_identity,
        analysis_run_identity=snapshot.analysis_run_lineage[-1],
        stage=persistence.WoBFailureStage.SOURCE_BINDING,
        reason="WO_B_SOURCE_INTEGRITY_MISMATCH",
        failed_at=_boundary(),
    )
    # Reconstruct a sealed pre-correction artifact only in isolated test storage.
    values = persistence._without(failure, "failure_identity", "failure_integrity")
    values["reason"] = "ACCESS_TOKEN_TEST_ONLY_NON_SECRET_VALUE"
    legacy = persistence.WoBReviewFailure(
        failure_identity=persistence._identity("INTRADAY-WO-B-FAILURE-", values),
        failure_integrity=persistence._identity("INTEGRITY-INTRADAY-WO-B-FAILURE-", values),
        **values,
    )
    encoded = persistence._artifact_bytes(legacy)
    for path in (
        service.store._path("failures", legacy.failure_identity),
        service.store._failure_path(legacy.candidate_identity),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(encoded)
    before = {path: path.read_bytes() for path in service.store.root.rglob("*.json")}
    restored = _service(tmp_path)
    document = restored.status_document()
    assert document["latest_failures"][0]["reason"] == SAFE_FALLBACK
    assert "TEST_ONLY" not in str(document)
    assert "TEST_ONLY" not in render_intraday_operational_readiness(_snapshot(), document)
    assert restored.store.load_latest_failure(legacy.candidate_identity) == legacy
    with pytest.raises(persistence.WoBPersistenceError, match="^WO_B_FAILURE_INVALID$"):
        restored.store.publish_latest_failure(legacy)
    assert {path: path.read_bytes() for path in service.store.root.rglob("*.json")} == before


@pytest.mark.parametrize("state,reason", (
    ("RISK_UNAVAILABLE", "CAPITAL_REFERENCE_UNAVAILABLE"),
    ("TIMING_FAILED", "INVALIDATED"),
))
def test_source_owned_reasons_are_not_internal_exception_codes(tmp_path, state, reason) -> None:  # type: ignore[no-untyped-def]
    from kronos.browser.intraday_views import render_intraday_operational_readiness
    from tests.unit.browser.test_product_route_isolation import _snapshot
    from tests.unit.intraday.test_operational_readiness import _reference
    from kronos.intraday.operational_readiness import create_review_item, WoBClassificationBasis

    reference = _reference(state=state, reason=reason)
    item = create_review_item(
        source_boundary=reference.source_boundary,
        classification_basis=WoBClassificationBasis.SOURCE_UNAVAILABLE,
        source_reference=reference,
    )
    # Source-owned values bypass the internal-exception allowlist by design.
    assert item.exact_source_state == state
    assert item.exact_source_reason == reason
    body = render_intraday_operational_readiness(_snapshot(), {"reviews": ({"items": ({
        "source_boundary": item.source_boundary.value,
        "source_state": item.exact_source_state,
        "source_reason": item.exact_source_reason,
        "classification": item.review_classification.value,
    },)},)})
    assert state in body
    assert reason in body
