from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from kronos.intraday.wo15 import Wo15ProgressionSemantics
from kronos.intraday.wo15_persistence import (
    DEFAULT_WO15_ROOT,
    Wo15PersistenceError,
    Wo15Store,
    create_wo15_operation_request,
)

from .test_wo15_timing import _candle, _case, _progression


def _request(tmp_path):  # type: ignore[no-untyped-def]
    admission, session = _case(tmp_path)
    source, evidence = _candle(
        admission, session, minute=5, close="101"
    )
    progression = _progression(
        admission, evidence, Wo15ProgressionSemantics.ALIGNED
    )
    return create_wo15_operation_request(
        admission=admission,
        session=session,
        source_candle=source,
        evidence=evidence,
        progression=progression,
        observed_at=evidence.candle_end + timedelta(seconds=1),
        provenance=("ADR-0025", "WO-15D-TEST"),
    )


def test_default_root_is_dedicated_application_support_evidence_path() -> None:
    assert DEFAULT_WO15_ROOT.parts[-3:] == (
        "evidence", "intraday-v1", "wo15-entry-timing-v1"
    )
    assert "Application Support" in DEFAULT_WO15_ROOT.parts


def test_append_only_request_and_explicit_identity_reload(tmp_path) -> None:
    store = Wo15Store((tmp_path / "store").resolve())
    request = _request(tmp_path)
    path = store.retain_request(request)
    assert path.exists()
    assert store.load_request(request.request_identity) == request


def test_same_identity_same_canonical_bytes_is_idempotent(tmp_path) -> None:
    store = Wo15Store((tmp_path / "store").resolve())
    request = _request(tmp_path)
    first = store.retain_request(request)
    before = first.read_bytes()
    second = store.retain_request(request)
    assert first == second
    assert second.read_bytes() == before


def test_same_identity_different_bytes_conflicts_without_overwrite(tmp_path) -> None:
    store = Wo15Store((tmp_path / "store").resolve())
    request = _request(tmp_path)
    path = store.retain_request(request)
    path.write_bytes(b"different\n")
    with pytest.raises(Wo15PersistenceError, match="WO15_IMMUTABLE_CONFLICT"):
        store.retain_request(request)
    assert path.read_bytes() == b"different\n"


def test_corrupt_artifact_is_rejected(tmp_path) -> None:
    store = Wo15Store((tmp_path / "store").resolve())
    request = _request(tmp_path)
    path = store.retain_request(request)
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(
        Wo15PersistenceError, match="WO15_ARTIFACT_INTEGRITY_INVALID"
    ):
        store.load_request(request.request_identity)


@pytest.mark.parametrize("identity", ("../escape", "bad/name", ".."))
def test_path_traversal_and_unsafe_identity_are_rejected(
    tmp_path, identity
) -> None:
    store = Wo15Store((tmp_path / "store").resolve())
    with pytest.raises(Wo15PersistenceError, match="WO15_ARTIFACT_PATH_INVALID"):
        store.load_request(identity)


def test_request_rejects_changed_governed_content_with_old_identity(tmp_path) -> None:
    request = _request(tmp_path)
    with pytest.raises(Exception, match="WO15_OPERATION_REQUEST_INVALID"):
        replace(request, provenance=("CHANGED",))


def test_empty_store_has_no_current_or_failure_projection(tmp_path) -> None:
    store = Wo15Store((tmp_path / "store").resolve())
    assert store.load_current() is None
    assert store.load_latest_failure() is None


def test_store_root_must_be_absolute() -> None:
    with pytest.raises(ValueError, match="WO15_STORE_ROOT_INVALID"):
        Wo15Store(type(DEFAULT_WO15_ROOT)("relative"))


def test_request_preserves_exact_policy_and_lineage(tmp_path) -> None:
    request = _request(tmp_path)
    assert request.admission.policy.policy_checksum == (
        "d36386a98e2f1b78e5b70d0c27079c056951fd76a5b70ec2e9fa1bc1615a3f26"
    )
    assert request.evidence.session_identity == request.session.session_identity
    assert request.progression.analysis_boundary == request.evidence.observation_boundary


def test_request_has_no_sponsor_execution_or_broker_authority(tmp_path) -> None:
    request = _request(tmp_path)
    assert not request.admission.sponsor_decision_authority
    assert not request.admission.execution_authority
    assert not request.admission.broker_authority
