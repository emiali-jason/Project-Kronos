from dataclasses import replace
from datetime import UTC, datetime

import pytest

from kronos.swing.run_provenance import (
    LocalSwingRunProvenanceStore,
    SwingAnalysisRunProvenance,
)


_RUN = "SWING-RUN-0000000000000000000000000000000A"
_CREATED = datetime(2026, 8, 13, 5, 1, tzinfo=UTC)
_COMPLETED = datetime(2026, 8, 13, 5, 17, tzinfo=UTC)
_BOUNDARY = datetime(2026, 8, 12, 18, 30, tzinfo=UTC)
_SNAPSHOT = "SWING-MARKET-DATA-SNAPSHOT-" + "a" * 64


def _provenance() -> SwingAnalysisRunProvenance:
    return SwingAnalysisRunProvenance(
        run_id=_RUN,
        run_created_at=_CREATED,
        analysis_boundary=_BOUNDARY,
        market_data_snapshot_identity=_SNAPSHOT,
        successful_completed_at=_COMPLETED,
    )


def test_provenance_round_trip_preserves_original_run_timestamp(tmp_path) -> None:
    first_process = LocalSwingRunProvenanceStore(tmp_path)
    first_process.retain(_provenance())

    restarted_process = LocalSwingRunProvenanceStore(tmp_path)
    recovered = restarted_process.load(_RUN)

    assert recovered == _provenance()
    assert recovered.run_created_at == _CREATED
    assert recovered.successful_completed_at == _COMPLETED
    assert recovered.analysis_boundary == _BOUNDARY
    assert recovered.run_created_at != recovered.analysis_boundary


def test_run_provenance_is_append_only_and_idempotent(tmp_path) -> None:
    store = LocalSwingRunProvenanceStore(tmp_path)
    store.retain(_provenance())
    store.retain(_provenance())

    with pytest.raises(ValueError, match="SWING_RUN_PROVENANCE_IMMUTABLE"):
        store.retain(replace(
            _provenance(),
            run_created_at=_CREATED.replace(minute=15),
        ))


def test_provenance_file_is_private_and_contains_no_secrets(tmp_path) -> None:
    store = LocalSwingRunProvenanceStore(tmp_path)
    store.retain(_provenance())
    path = tmp_path / _RUN / "run-provenance.json"

    assert path.stat().st_mode & 0o777 == 0o600
    text = path.read_text(encoding="utf-8")
    assert _RUN in text
    assert "api_key" not in text.lower()
    assert "credential" not in text.lower()


def test_legacy_provenance_without_completion_remains_readable(tmp_path) -> None:
    store = LocalSwingRunProvenanceStore(tmp_path)
    store.retain(_provenance())
    path = tmp_path / _RUN / "run-provenance.json"
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.pop("successful_completed_at")
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert store.load(_RUN).successful_completed_at is None


def test_latest_returns_only_the_most_recent_successfully_completed_run(tmp_path) -> None:
    store = LocalSwingRunProvenanceStore(tmp_path)
    store.retain(_provenance())
    later = replace(
        _provenance(),
        run_id="SWING-RUN-0000000000000000000000000000000B",
        successful_completed_at=_COMPLETED.replace(minute=18),
    )
    store.retain(later)

    assert store.latest() == later
