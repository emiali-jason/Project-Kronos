from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from kronos.application.intraday_review_v2 import IntradayReviewV2Application
from kronos.application.intraday_runtime import create_intraday_runtime
from kronos.intraday.probables_v2_persistence import ProbablesV2Store
from kronos.intraday.review import ReviewError, ReviewFailure
from kronos.intraday.review_v2_persistence import IntradayReviewV2Store
from kronos.intraday.review_v2_operation_persistence import (
    ReviewV2OperationProvenanceStore,
)
from tests.unit.intraday.test_probables_v2 import _opening_inputs, _run
from tests.unit.provider.test_shared_provider_runtime import _shared


def _fingerprints(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_runtime_composes_valid_empty_v2_review_without_autonomous_work(
    tmp_path: Path,
) -> None:
    shared, provider, factory_calls = _shared()

    composition = create_intraday_runtime(shared, evidence_root=tmp_path.resolve())

    assert type(composition.review_v2_store) is IntradayReviewV2Store
    assert type(composition.review_v2_application) is IntradayReviewV2Application
    assert composition.review_v2_store.root == tmp_path / "review-v2"
    assert composition.review_v2_application.review_store is composition.review_v2_store
    assert type(composition.review_v2_operation_store) is ReviewV2OperationProvenanceStore
    assert composition.review_v2_operation_store.root == tmp_path / "review-v2" / "operations"
    assert composition.review_v2_current is None
    assert list(tmp_path.rglob("*")) == []
    assert provider.capability.calls == 0
    assert provider.begin_count == 0
    assert factory_calls == []
    assert shared.active_lease_count == 0


def test_pf10_runtime_restoration_prepares_empty_generation_without_writes(
    tmp_path: Path,
) -> None:
    shared, provider, factory_calls = _shared()
    before = _fingerprints(tmp_path)

    composition = create_intraday_runtime(shared, evidence_root=tmp_path.resolve())

    generation = composition.review_v2_application._page_generation
    assert generation is not None
    assert generation.current_pointer_identity is None
    with composition.review_v2_application.page_read_scope():
        assert composition.review_v2_application.snapshot().candidates == ()
    assert _fingerprints(tmp_path) == before
    assert provider.begin_count == 0
    assert factory_calls == []


def test_runtime_restores_exact_v2_review_pointer_without_creating_review(
    tmp_path: Path,
) -> None:
    root = tmp_path.resolve()
    *_, mapping = _opening_inputs()
    run = _run(mapping)
    probables_store = ProbablesV2Store(root)
    probables_store.retain_complete(run=run, mappings=(mapping,))
    review_store = IntradayReviewV2Store(root / "review-v2")
    review_application = IntradayReviewV2Application(
        probables_store=probables_store,
        review_store=review_store,
    )
    expected_cycles = review_application.create_eligible_cycles(run)
    expected_pointer = review_store.load_current()
    # Historical Review was created lawfully before its producer pointer disappeared.
    (root / "refresh-v2" / "CURRENT-PROBABLES-V2.json").unlink()
    before = _fingerprints(root)
    shared, provider, factory_calls = _shared()

    composition = create_intraday_runtime(
        shared,
        evidence_root=root,
        clock=lambda: run.analysis_boundary,
    )

    assert composition.review_v2_current == expected_pointer
    assert composition.review_v2_store.load_current() == expected_pointer
    assert composition.review_v2_store.cycles_for_run(run.run_identity) == expected_cycles
    assert composition.review_v2_application.workspace_state() == "REVIEW_NON_CURRENT"
    assert composition.review_v2_application.snapshot().candidates == ()
    with pytest.raises(ReviewError, match=ReviewFailure.NOT_CURRENT.value):
        composition.review_v2_application.create_eligible_cycles(run)
    assert _fingerprints(root) == before
    assert provider.capability.calls == 0
    assert provider.begin_count == 0
    assert factory_calls == []
    assert shared.active_lease_count == 0


def test_runtime_never_falls_back_to_v1_and_corrupt_v2_pointer_fails_closed(
    tmp_path: Path,
) -> None:
    v1_only_root = (tmp_path / "v1-only").resolve()
    v1_pointer = v1_only_root / "review-v1" / "current" / "CURRENT-REVIEW-POINTER.json"
    v1_pointer.parent.mkdir(parents=True)
    v1_pointer.write_bytes(b"V1-ONLY-FIXTURE")
    shared, provider, factory_calls = _shared()

    composition = create_intraday_runtime(shared, evidence_root=v1_only_root)

    assert composition.review_v2_current is None
    assert composition.review_v2_store.root == v1_only_root / "review-v2"
    assert provider.capability.calls == 0
    assert provider.begin_count == 0
    assert factory_calls == []

    corrupt_root = (tmp_path / "corrupt-v2").resolve()
    corrupt_pointer = (
        corrupt_root / "review-v2" / "current" / "CURRENT-REVIEW-V2-POINTER.json"
    )
    corrupt_pointer.parent.mkdir(parents=True)
    corrupt_pointer.write_bytes(b"{}")
    corrupt_shared, corrupt_provider, corrupt_factory_calls = _shared()

    with pytest.raises(ReviewError, match=ReviewFailure.INTEGRITY_INVALID.value):
        create_intraday_runtime(corrupt_shared, evidence_root=corrupt_root)

    assert corrupt_provider.capability.calls == 0
    assert corrupt_provider.begin_count == 0
    assert corrupt_factory_calls == []


def _pf10_corrupt_same_size_and_mtime(path):
    import os
    before = path.stat()
    payload = path.read_bytes()
    path.write_bytes(bytes([payload[0] ^ 1]) + payload[1:])
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert path.stat().st_size == before.st_size
    assert path.stat().st_mtime_ns == before.st_mtime_ns


@pytest.mark.parametrize("owner", ("ordered", "paired", "binding", "reconciliation"))
def test_pf10_exact_owner_corruption_after_warming(owner, tmp_path, monkeypatch):
    from kronos.application.intraday_review_ordered_batch import load
    from tests.unit.browser.test_intraday_compact_serving import _pf10_populated_pages
    from tests.unit.browser.test_product_route_isolation import _snapshot
    from kronos.browser.product_routes import BrowserGetRequest
    from tests.unit.intraday.test_review_v2_paired_intake import paired_fixture
    from tests.unit.intraday.test_review import _png
    if owner in {"paired", "binding"}:
        app, cycle, metadata = paired_fixture(tmp_path)
        chart = app.upload_chart(cycle.cycle_identity, media_type="image/png",
                                 payload=_png(37), paired_metadata=metadata)
        read = app.snapshot
        path = (app._paired.store._path("paired-bundles", chart.paired_bundle_identity)
                if owner == "paired" else
                app._paired.bindings.path_for(metadata["native_binding_identity"]))
        expected = "INTRADAY_REVIEW_INTEGRITY_INVALID"
    else:
        runtime, routes = _pf10_populated_pages(tmp_path, monkeypatch)
        app = runtime.review_v2_application
        if owner == "ordered":
            pointer = app.review_store.load_current()
            _, _, folder = load(app, pointer)
            path = folder / "question.pdf"
            read = app.snapshot
            expected = "INTRADAY_REVIEW_INTEGRITY_INVALID"
        else:
            read = runtime.visual_reconciliation_v2_application.status
            cycle = app.snapshot().candidates[0].cycle_identity
            record = runtime.visual_reconciliation_v2_store.restore_current(cycle)
            path = runtime.visual_reconciliation_v2_store._record_path(record.reconciliation_identity)
            expected = "WO07F_RECORD_INTEGRITY_INVALID"
    with app.page_read_scope():
        first = read()
        assert read() == first
    pointer = app.review_store.load_current()
    _pf10_corrupt_same_size_and_mtime(path)
    with pytest.raises((ReviewError, ValueError), match=expected):
        with app.page_read_scope():
            read()
    assert app.review_store.load_current() == pointer
    if owner in {"ordered", "reconciliation"}:
        response = routes.handle_get(BrowserGetRequest("/intraday/review", {}), _snapshot)
        assert response.status == 503 and expected in response.body


@pytest.mark.parametrize("owner", ("review", "ordered", "paired", "binding", "reconciliation"))
def test_pf10_owner_mutation_fences_captured_generation(owner, tmp_path, monkeypatch):
    from datetime import timedelta
    from kronos.application.intraday_review_v2 import IntradayPageUnavailable
    from kronos.intraday.visual_reconciliation_v2 import create_reconciliation_record
    from tests.unit.browser.test_intraday_compact_serving import _pf10_populated_pages
    from tests.unit.intraday.test_review_v2_paired_intake import paired_fixture
    from tests.unit.intraday.test_review import _png
    if owner in {"paired", "binding"}:
        app, cycle, metadata = paired_fixture(tmp_path)
        chart = app.upload_chart(cycle.cycle_identity, media_type="image/png",
                                 payload=_png(37), paired_metadata=metadata)
        if owner == "binding":
            value = app._paired.bindings.load(binding_identity=metadata["native_binding_identity"])
            mutate = lambda: app._paired.bindings.retain(value)
        else:
            value = app._paired.store.load_bundle(chart.paired_bundle_identity)
            from kronos.intraday.review_mcx_paired import create_paired_review_pack
            pack = create_paired_review_pack(value, created_at=app._clock()+timedelta(seconds=2))
            mutate = lambda: app._paired.store.retain_pack(pack)
    else:
        runtime, _ = _pf10_populated_pages(tmp_path, monkeypatch)
        app = runtime.review_v2_application
        if owner == "review":
            pointer = app.review_store.load_current()
            mutate = lambda: app.review_store.save_current(pointer)
        elif owner == "ordered":
            mutate = app.create_all_question_transports
        else:
            candidate = app.snapshot().candidates[0]
            value = runtime.visual_reconciliation_v2_application._input(candidate.cycle_identity)
            # Remove the temporary fixture pointer before entering the request:
            # publishing a retained record must restore it or reject its conflict.
            record = create_reconciliation_record(value, created_at=app._clock()+timedelta(seconds=2))
            runtime.visual_reconciliation_v2_store._pointer_path(candidate.cycle_identity).unlink()
            mutate = lambda: runtime.visual_reconciliation_v2_store.retain(record)
    with pytest.raises(IntradayPageUnavailable, match="SOURCE_CHANGED"):
        with app.page_read_scope():
            app.snapshot()
            mutate()
            app.snapshot()


@pytest.mark.parametrize("owner", ("paired", "binding"))
def test_pf10_separate_owner_instances_share_publication_exclusion(owner, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from datetime import timedelta
    from threading import Event
    from tests.unit.intraday.test_review_v2_paired_intake import paired_fixture
    from tests.unit.intraday.test_review import _png
    from kronos.intraday.review_mcx_paired import create_paired_review_pack
    app, cycle, metadata = paired_fixture(tmp_path)
    chart = app.upload_chart(cycle.cycle_identity, media_type="image/png",
                             payload=_png(37), paired_metadata=metadata)
    if owner == "binding":
        first = app._paired.bindings
        value = first.load(binding_identity=metadata["native_binding_identity"])
        second = type(first)(first._root)
        write = lambda: second.retain(value)
    else:
        first = app._paired.store
        bundle = first.load_bundle(chart.paired_bundle_identity)
        pack = create_paired_review_pack(bundle, created_at=app._clock()+timedelta(seconds=2))
        second = type(first)(first.root)
        write = lambda: second.retain_pack(pack)
    started, finished = Event(), Event()
    def publish():
        started.set()
        write()
        finished.set()
    with ThreadPoolExecutor(max_workers=1) as pool:
        with app.page_read_scope():
            snapshot = app.snapshot()
            task = pool.submit(publish)
            assert started.wait(1) and not finished.wait(.05)
            assert app.snapshot() is snapshot
        task.result(timeout=2)
    assert finished.is_set()
