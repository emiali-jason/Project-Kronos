"""Intraday-owned phase-aware Probables V2 production composition."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from threading import RLock
from typing import Sequence

from kronos.intraday.probables_v2 import (
    DiscoveryProbablesEvidenceV2,
    ProbableMemberResultV2,
    ProbablesRunV2,
    ProbablesUnavailableMemberV2,
    ProbablesV2Error,
    create_probables_v2_methodology,
    evaluate_probables_v2_run,
)
from kronos.intraday.probables_v2_persistence import ProbablesV2Store


PROBABLES_V2_APPLICATION_IDENTITY = "KRONOS-INTRADAY-PROBABLES-APPLICATION-V2"
PROBABLES_V2_APPLICATION_VERSION = "2.0.0"


@dataclass(frozen=True, slots=True)
class IntradayProbablesV2Snapshot:
    current_failure: str | None
    last_successful_run_identity: str | None
    last_successful_discovery_run_identity: str | None
    last_successful_analysis: datetime | None
    results: tuple[ProbableMemberResultV2, ...]
    run: ProbablesRunV2 | None
    application_identity: str = PROBABLES_V2_APPLICATION_IDENTITY
    application_version: str = PROBABLES_V2_APPLICATION_VERSION

    def __post_init__(self) -> None:
        absent = self.run is None
        if (
            self.current_failure is not None and not _text(self.current_failure)
            or absent != (self.last_successful_run_identity is None)
            or absent != (self.last_successful_discovery_run_identity is None)
            or absent != (self.last_successful_analysis is None)
            or any(type(item) is not ProbableMemberResultV2 for item in self.results)
            or self.run is not None and type(self.run) is not ProbablesRunV2
            or (
                self.run is not None
                and (
                    self.run.run_identity != self.last_successful_run_identity
                    or self.run.source_discovery_run_identity
                    != self.last_successful_discovery_run_identity
                    or self.run.analysis_boundary != self.last_successful_analysis
                    or self.results != self.run.results
                )
            )
            or self.application_identity != PROBABLES_V2_APPLICATION_IDENTITY
            or self.application_version != PROBABLES_V2_APPLICATION_VERSION
        ):
            raise ValueError("INTRADAY_PROBABLES_V2_SNAPSHOT_INVALID")


class IntradayProbablesV2Application:
    """Evaluate, persist, and restore exact V2 runs without Provider access."""

    def __init__(self, *, store: ProbablesV2Store, restore_current: bool = True) -> None:
        if type(store) is not ProbablesV2Store or type(restore_current) is not bool:
            raise ValueError("INTRADAY_PROBABLES_V2_APPLICATION_INVALID")
        self._store = store
        self._methodology = create_probables_v2_methodology()
        self._run: ProbablesRunV2 | None = None
        self._current_failure: str | None = None
        self._lock = RLock()
        if restore_current:
            self._run = self._store.load_current_run()
            if self._run is not None and self._run.methodology != self._methodology:
                raise ProbablesV2Error("PROBABLES_V2_RESTART_METHODOLOGY_MISMATCH")

    def refresh_analysis(
        self,
        *,
        source_discovery_run_identity: str,
        universe_identity: str,
        universe_version: str,
        reconciliation_identity: str,
        reconciliation_version: str,
        market_session_identity: str,
        analysis_boundary: datetime,
        member_evidence: Sequence[DiscoveryProbablesEvidenceV2],
        unavailable_members: Sequence[ProbablesUnavailableMemberV2],
        provenance: tuple[str, ...],
    ) -> ProbablesRunV2:
        """Create one immutable V2 assessment; no Provider operation occurs."""

        with self._lock:
            try:
                mappings = tuple(member_evidence)
                run = evaluate_probables_v2_run(
                    source_discovery_run_identity=source_discovery_run_identity,
                    universe_identity=universe_identity,
                    universe_version=universe_version,
                    reconciliation_identity=reconciliation_identity,
                    reconciliation_version=reconciliation_version,
                    market_session_identity=market_session_identity,
                    analysis_boundary=analysis_boundary,
                    member_evidence=mappings,
                    unavailable_members=tuple(unavailable_members),
                    provenance=provenance,
                )
                self._store.retain_complete(run=run, mappings=mappings)
                restored = self._store.load_current_run()
                if restored != run:
                    raise ProbablesV2Error("PROBABLES_V2_RELOAD_MISMATCH")
            except ProbablesV2Error as error:
                self._current_failure = str(error)
                raise
            except Exception as error:
                self._current_failure = "PROBABLES_V2_REFRESH_FAILED"
                raise RuntimeError("PROBABLES_V2_REFRESH_FAILED") from error
            self._run = run
            self._current_failure = None
            return run

    def record_failure(self, failure: str) -> None:
        if not _text(failure) or not failure.replace("_", "").isalnum():
            raise ValueError("INTRADAY_PROBABLES_V2_FAILURE_INVALID")
        with self._lock:
            self._current_failure = failure

    def snapshot(self) -> IntradayProbablesV2Snapshot:
        with self._lock:
            return IntradayProbablesV2Snapshot(
                current_failure=self._current_failure,
                last_successful_run_identity=(
                    None if self._run is None else self._run.run_identity
                ),
                last_successful_discovery_run_identity=(
                    None
                    if self._run is None
                    else self._run.source_discovery_run_identity
                ),
                last_successful_analysis=(
                    None if self._run is None else self._run.analysis_boundary
                ),
                results=() if self._run is None else self._run.results,
                run=self._run,
            )


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


__all__ = [
    "PROBABLES_V2_APPLICATION_IDENTITY",
    "PROBABLES_V2_APPLICATION_VERSION",
    "IntradayProbablesV2Application",
    "IntradayProbablesV2Snapshot",
]
