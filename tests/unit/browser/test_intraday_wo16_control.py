from __future__ import annotations

from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

from kronos.application.intraday_runtime import create_intraday_runtime
from kronos.application.intraday_wo16 import (
    IntradayWo16PersistenceApplication,
    IntradayWo16RestorationService,
    Wo16ApplicationError,
)
from kronos.browser.intraday_routes import IntradayBrowserRoutes
from kronos.browser.intraday_wo16_control import (
    MAX_WO16_REQUEST_BYTES,
    WO16_CONTROL_ROUTE,
    WO16_PRODUCT_ROUTE,
    WO16_STATUS_ROUTE,
    IntradayWo16OperationalControl,
    operation_document,
)
from kronos.browser.product_routes import BrowserGetRequest, BrowserPostRequest
from kronos.intraday.wo13_persistence import Wo13Store
from kronos.intraday.wo14_persistence import Wo14Store
from kronos.intraday.wo15_persistence import Wo15Store
from kronos.intraday.wo16 import (
    WO16_POLICY_CHECKSUM,
    Wo16SponsorDecision,
)
from kronos.intraday.wo16_persistence import Wo16Store
from kronos.intraday.historical_semantic import SemanticDirection
from tests.unit.browser.test_product_route_isolation import _snapshot
from tests.unit.intraday.test_wo16_application import _request
from tests.unit.intraday.test_wo16_contracts import _chain
from tests.unit.provider.test_shared_provider_runtime import _shared


class _Workstation:
    def snapshot(self, selected=None):  # type: ignore[no-untyped-def]
        del selected
        return SimpleNamespace(probables=None, probables_v2=None)


def _control(
    tmp_path, choice=Wo16SponsorDecision.PAPER, **chain_options
):  # type: ignore[no-untyped-def]
    chain = _chain(tmp_path, **chain_options)
    request = _request(chain, choice)
    store = Wo16Store((tmp_path / "wo16").resolve())
    control = IntradayWo16OperationalControl(
        IntradayWo16PersistenceApplication(store=store),
        IntradayWo16RestorationService(store=store),
        wo13_store=Wo13Store(next(tmp_path.glob("store-*")).resolve()),
        wo14_store=Wo14Store((tmp_path / "wo14").resolve()),
        wo15_store=Wo15Store((tmp_path / "wo15").resolve()),
    )
    return control, store, request


def _post(
    control,
    payload,
    *,
    content_type="application/json",
    query=None,
    raw=None,
):  # type: ignore[no-untyped-def]
    body = (
        raw
        if raw is not None
        else json.dumps(payload).encode() if payload is not None else b""
    )
    return IntradayBrowserRoutes(
        _Workstation(), wo16_control=control
    ).handle_post(
        BrowserPostRequest(
            WO16_CONTROL_ROUTE,
            {} if query is None else query,
            content_type,
            body,
        ),
        _snapshot,
    )


def _fingerprint(root):  # type: ignore[no-untyped-def]
    if not root.exists():
        return ()
    return tuple(
        (str(path.relative_to(root)), path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )


def test_runtime_composes_exact_store_and_restores_without_writes(tmp_path) -> None:
    shared, provider, factory_calls = _shared()
    root = tmp_path.resolve()

    composition = create_intraday_runtime(shared, evidence_root=root)

    assert composition.wo16_store.root == (
        root / "wo16-sponsor-decision-lifecycle-admission-v1"
    )
    assert composition.wo16_application.store is composition.wo16_store
    assert composition.wo16_restored.state.value == "NOT_YET_RUN"
    assert composition.wo16_restoration.restore().state.value == "NOT_YET_RUN"
    assert provider.capability.calls == 0
    assert provider.begin_count == 0
    assert factory_calls == []
    assert _fingerprint(composition.wo16_store.root) == ()


def test_empty_product_and_status_get_are_inert(tmp_path) -> None:
    control, store, _ = _control(tmp_path)
    routes = IntradayBrowserRoutes(_Workstation(), wo16_control=control)
    before = _fingerprint(store.root)

    page = routes.handle_get(BrowserGetRequest(WO16_PRODUCT_ROUTE, {}), _snapshot)
    status = routes.handle_get(BrowserGetRequest(WO16_STATUS_ROUTE, {}), _snapshot)

    assert page is not None and page.status.value == 200
    assert "NOT_YET_RUN" in page.body
    assert status is not None and status.status.value == 200
    document = json.loads(status.body)
    assert document["restoration_state"] == "NOT_YET_RUN"
    assert document["decision_controls_available"] is False
    for counter in (
        "provider_calls",
        "wo13_operations",
        "wo14_operations",
        "wo15_operations",
        "upstream_operations",
        "autonomous_operations",
        "sponsor_operations",
        "decision_operations",
        "persistence_writes_from_get",
        "broker_operations",
    ):
        assert document[counter] == 0
    assert _fingerprint(store.root) == before


@pytest.mark.parametrize(
    ("choice", "disposition"),
    (
        (Wo16SponsorDecision.PAPER, "PENDING_POSITION_EVIDENCE"),
        (Wo16SponsorDecision.LIVE, "PENDING_POSITION_EVIDENCE"),
        (Wo16SponsorDecision.IGNORE, "NOT_APPLICABLE_IGNORE"),
    ),
)
def test_exact_choice_post_persists_and_restores(
    tmp_path, choice, disposition
) -> None:  # type: ignore[no-untyped-def]
    control, store, request = _control(tmp_path, choice)

    response = _post(control, operation_document(request))

    assert response is not None and response.status.value == 200
    document = json.loads(response.body)
    assert document["outcome"] == "COMPLETED"
    assert document["decision"]["sponsor_decision"]["choice"] == choice.value
    assert document["decision"]["lifecycle_admission"]["disposition"] == disposition
    assert document["decision"]["position_created"] is False
    restored = store.restore_current(request.wo13_trade_plan.canonical_subject_identity)
    assert restored is not None
    assert restored.decision.choice is choice


def test_exact_replay_is_retained_and_does_not_write(tmp_path) -> None:
    control, store, request = _control(tmp_path)
    payload = operation_document(request)
    assert _post(control, payload).status.value == 200
    before = _fingerprint(store.root)

    replay = _post(control, payload)

    assert replay is not None and replay.status.value == 200
    assert json.loads(replay.body)["outcome"] == "RETAINED"
    assert _fingerprint(store.root) == before
    assert control.status_document()["decision_operations"] == 1
    assert control.status_document()["sponsor_operations"] == 2


def test_transport_and_exact_schema_guards_fail_closed(tmp_path) -> None:
    control, store, request = _control(tmp_path)
    valid = operation_document(request)
    missing = json.loads(json.dumps(valid))
    missing["request"].pop("provenance")
    extra = json.loads(json.dumps(valid))
    extra["request"]["extra"] = True
    naive = json.loads(json.dumps(valid))
    naive["request"]["decision_timestamp"] = "2026-09-03T10:00:00"
    numeric = json.loads(json.dumps(valid))
    numeric["request"]["wo13_trade_plan"]["entry_reference"] = 100
    responses = (
        _post(control, missing),
        _post(control, extra),
        _post(control, naive),
        _post(control, numeric),
        _post(control, valid, content_type="text/plain"),
        _post(control, valid, query={"unexpected": ["1"]}),
        _post(control, None, raw=b"{"),
        _post(control, None, raw=b"x" * (MAX_WO16_REQUEST_BYTES + 1)),
    )

    assert all(item is not None and item.status.value == 400 for item in responses)
    assert all(json.loads(item.body)["outcome"] == "REJECTED" for item in responses)
    assert not store.root.exists()


def test_concurrency_stale_and_application_failure_statuses(tmp_path, monkeypatch) -> None:
    control, store, request = _control(tmp_path)
    payload = operation_document(request)
    control._active_request_identity = "ACTIVE-WO16"  # noqa: SLF001
    busy = _post(control, payload)
    control._active_request_identity = None  # noqa: SLF001
    stale_request = _request(
        _chain(tmp_path / "foreign", direction=SemanticDirection.SHORT),
        current_wo13_pointer=request.current_wo13_pointer,
    )
    stale = _post(control, operation_document(stale_request))

    def fail(_request):  # type: ignore[no-untyped-def]
        raise OSError("/private/secret/path")

    monkeypatch.setattr(control.application, "execute", fail)
    failed = _post(control, payload)

    assert busy is not None and busy.status.value == 409
    assert json.loads(busy.body)["failure_reason"] == "WO16_OPERATION_BUSY"
    assert stale is not None and stale.status.value == 409
    assert json.loads(stale.body)["failure_reason"] in {
        "WO13_NOT_CURRENT", "WO14_NOT_CURRENT", "WO15_NOT_CURRENT"
    }
    assert failed is not None and failed.status.value == 503
    assert "/private/secret/path" not in failed.body
    assert store.restore_all() == ()


@pytest.mark.parametrize(
    "reason",
    (
        "WO15_TIMING_NOT_QUALIFIED",
        "DOMAIN_008_SESSION_ENDED",
        "MCX_CONTRACT_LINEAGE_MISMATCH",
        "WO16_DECISION_ALREADY_FINAL",
    ),
)
def test_governed_semantic_rejections_map_to_conflict(
    tmp_path, monkeypatch, reason
) -> None:  # type: ignore[no-untyped-def]
    control, _, request = _control(tmp_path)

    def reject(_request):  # type: ignore[no-untyped-def]
        raise Wo16ApplicationError(reason)

    monkeypatch.setattr(control.application, "execute", reject)
    response = _post(control, operation_document(request))

    assert response is not None and response.status.value == 409
    assert json.loads(response.body)["failure_reason"] == reason


def test_policy_identity_and_negative_authority_projection(tmp_path) -> None:
    control, _, request = _control(tmp_path, mcx=True)
    assert _post(control, operation_document(request)).status.value == 200

    current = control.status_document()["current_decisions"][0]

    assert current["actual_contract_identity"] == request.wo13_trade_plan.actual_contract_identity
    assert current["roll_lineage_identity"] == request.wo13_source_handoff.roll_lineage_identity
    assert control.status_document()["policy_checksum"] == WO16_POLICY_CHECKSUM
    assert current["position_created"] is False
    assert current["actual_fill"] == "UNAVAILABLE"
    assert current["quantity"] == "UNAVAILABLE"
    assert current["pnl"] == "UNAVAILABLE"
    assert current["realised_r"] == "UNAVAILABLE"
    assert current["broker_order"] == "NONE"


def test_existing_routes_remain_owned_without_wo16_control() -> None:
    routes = IntradayBrowserRoutes(_Workstation())

    response = routes.handle_get(BrowserGetRequest("/intraday/wo16", {}), _snapshot)
    assert response.status.value == 404
    assert routes.owns_post("/control/intraday-review/v2")
    assert routes.owns_post("/intraday/review/start")
    assert not routes.owns_post("/control/swing-run")
