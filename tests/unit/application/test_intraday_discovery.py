from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from kronos.application.intraday_discovery import (
    DISCOVERY_OPERATIONAL_INVOCATION_SEAM_REQUIRED,
    IntradayDiscoveryApplication,
)
from kronos.intraday.discovery import DiscoveryError, DiscoveryFailure
from kronos.intraday.discovery_runtime import DiscoveryRunBoundary
from tests.unit.intraday.test_discovery_runtime import BOUNDARY, _publications, _service


def _application(tmp_path: Path):  # type: ignore[no-untyped-def]
    service, source, store, _ = _service(tmp_path)
    universe, reconciliation = _publications()
    return (
        IntradayDiscoveryApplication(
            universe=universe,
            reconciliation=reconciliation,
            store=store,
            service=service,
        ),
        source,
        store,
        universe,
        reconciliation,
    )


def test_no_successful_run_projects_exact_governed_scope_without_provider_calls(
    tmp_path: Path,
) -> None:
    app, source, _, _, _ = _application(tmp_path)

    snapshot = app.snapshot("RELIANCE")

    assert snapshot.system_status == "NO_SUCCESSFUL_DISCOVERY_RUN_AVAILABLE"
    assert snapshot.universe_count == 98
    assert snapshot.pre_evaluable_count == 93
    assert snapshot.prerequisite_unavailable_count == 5
    assert snapshot.machine_fact_success_count == 0
    assert snapshot.candidate_admitted_count == 0
    assert snapshot.candidate_not_admitted_count == 0
    assert snapshot.selected_member is not None
    assert snapshot.selected_member.sponsor_label == "RELIANCE"
    assert source.labels == []


def test_successful_run_snapshot_and_explicit_restart_reconstruction(
    tmp_path: Path,
) -> None:
    app, _, store, universe, reconciliation = _application(tmp_path)
    run = app.run_discovery(BOUNDARY)

    current = app.snapshot("RELIANCE")
    restarted = IntradayDiscoveryApplication(
        universe=universe,
        reconciliation=reconciliation,
        store=store,
        last_successful_run_identity=run.run_identity,
    ).snapshot("RELIANCE")

    assert current.last_successful_run_identity == run.run_identity
    assert current.last_successful_analysis == BOUNDARY.observation_boundary
    assert current.machine_fact_success_count == 93
    assert current.methodology_deferred_count == 93
    assert current.candidate_admitted_count == current.candidate_not_admitted_count == 0
    assert restarted.last_successful_run_identity == run.run_identity
    assert restarted.machine_fact_success_count == 93
    assert restarted.selected_member is not None
    assert restarted.selected_member.machine_fact_bundle is not None
    assert restarted.selected_member.evidence is None


def test_global_failure_does_not_erase_last_successful_run(tmp_path: Path) -> None:
    app, _, _, _, _ = _application(tmp_path)
    run = app.run_discovery(BOUNDARY)
    stale = DiscoveryRunBoundary(
        datetime(2025, 1, 1, tzinfo=ZoneInfo("Asia/Kolkata")),
        "NSE-STALE",
        "DOMAIN-008:NSE:STALE",
    )

    with pytest.raises(
        DiscoveryError,
        match=DiscoveryFailure.PUBLICATION_STALE.value,
    ):
        app.run_discovery(stale)

    snapshot = app.snapshot("RELIANCE")
    assert snapshot.last_successful_run_identity == run.run_identity
    assert snapshot.current_failure == DiscoveryFailure.PUBLICATION_STALE.value
    assert snapshot.machine_fact_success_count == 93


def test_missing_operational_seam_fails_closed_without_provider_activity(
    tmp_path: Path,
) -> None:
    _, source, store, universe, reconciliation = _application(tmp_path)
    app = IntradayDiscoveryApplication(
        universe=universe,
        reconciliation=reconciliation,
        store=store,
    )

    with pytest.raises(RuntimeError, match=DISCOVERY_OPERATIONAL_INVOCATION_SEAM_REQUIRED):
        app.run_discovery(BOUNDARY)

    assert source.labels == []
    assert app.snapshot().current_failure == DISCOVERY_OPERATIONAL_INVOCATION_SEAM_REQUIRED
