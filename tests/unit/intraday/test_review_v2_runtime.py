from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from kronos.application.intraday_review_v2 import IntradayReviewV2Application
from kronos.application.intraday_runtime import create_intraday_runtime
from kronos.intraday.probables_v2_persistence import ProbablesV2Store
from kronos.intraday.review import ReviewError, ReviewFailure
from kronos.intraday.review_v2_persistence import IntradayReviewV2Store
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
    assert composition.review_v2_current is None
    assert list(tmp_path.rglob("*")) == []
    assert provider.capability.calls == 0
    assert provider.begin_count == 0
    assert factory_calls == []
    assert shared.active_lease_count == 0


def test_runtime_restores_exact_v2_review_pointer_without_creating_review(
    tmp_path: Path,
) -> None:
    root = tmp_path.resolve()
    *_, mapping = _opening_inputs()
    run = _run(mapping)
    probables_store = ProbablesV2Store(root)
    probables_store.retain_complete(run=run, mappings=(mapping,))
    (root / "refresh-v2" / "CURRENT-PROBABLES-V2.json").unlink()
    review_store = IntradayReviewV2Store(root / "review-v2")
    review_application = IntradayReviewV2Application(
        probables_store=probables_store,
        review_store=review_store,
    )
    expected_cycles = review_application.create_eligible_cycles(run)
    expected_pointer = review_store.load_current()
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
    assert composition.review_v2_application.create_eligible_cycles(run) == expected_cycles
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
