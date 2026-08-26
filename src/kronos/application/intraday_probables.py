"""Intraday-owned production Probables application and last-successful state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from threading import RLock
from typing import Sequence

from kronos.intraday.probables import (
    FactualSourceKind,
    ProbableMemberResult,
    ProbablesError,
    ProbablesMemberEvidence,
    ProbablesMethodologyPublication,
    ProbablesRun,
    ProbablesUnavailableMember,
    create_v0_probables_methodology,
    evaluate_probables_run,
)
from kronos.intraday.probables_persistence import ProbablesStore


PROBABLES_APPLICATION_IDENTITY = "KRONOS-INTRADAY-PROBABLES-APPLICATION-V1"
PROBABLES_APPLICATION_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class IntradayProbablesSnapshot:
    methodology: ProbablesMethodologyPublication
    current_failure: str | None
    last_successful_run_identity: str | None
    last_successful_analysis: datetime | None
    results: tuple[ProbableMemberResult, ...]
    run: ProbablesRun | None
    application_identity: str = PROBABLES_APPLICATION_IDENTITY
    application_version: str = PROBABLES_APPLICATION_VERSION

    def __post_init__(self) -> None:
        if (
            type(self.methodology) is not ProbablesMethodologyPublication
            or self.current_failure is not None and not _text(self.current_failure)
            or self.last_successful_run_identity is not None
            and not _text(self.last_successful_run_identity)
            or self.last_successful_analysis is not None
            and not _aware(self.last_successful_analysis)
            or any(type(item) is not ProbableMemberResult for item in self.results)
            or self.run is not None and type(self.run) is not ProbablesRun
            or (self.run is None) != (self.last_successful_run_identity is None)
            or (self.run is None) != (self.last_successful_analysis is None)
            or self.application_identity != PROBABLES_APPLICATION_IDENTITY
            or self.application_version != PROBABLES_APPLICATION_VERSION
        ):
            raise ValueError("INTRADAY_PROBABLES_SNAPSHOT_INVALID")


class IntradayProbablesApplication:
    """Evaluate immutable runs and preserve last success across later failure."""

    def __init__(
        self,
        *,
        store: ProbablesStore,
        last_successful_run_identity: str | None = None,
    ) -> None:
        if type(store) is not ProbablesStore:
            raise ValueError("INTRADAY_PROBABLES_APPLICATION_INVALID")
        self._store = store
        self._methodology = create_v0_probables_methodology()
        self._run: ProbablesRun | None = None
        self._current_failure: str | None = None
        self._lock = RLock()
        if last_successful_run_identity is not None:
            self._run = store.load_run(run_identity=last_successful_run_identity)

    def refresh_analysis(
        self,
        *,
        source_kind: FactualSourceKind,
        source_run_identity: str,
        universe_identity: str,
        universe_version: str,
        reconciliation_identity: str,
        reconciliation_version: str,
        market_session_identity: str,
        observation_boundary: datetime,
        member_evidence: Sequence[ProbablesMemberEvidence],
        unavailable_members: Sequence[ProbablesUnavailableMember],
        provenance: tuple[str, ...],
    ) -> ProbablesRun:
        """Create one governed run; no Provider operation occurs here."""

        with self._lock:
            try:
                run = evaluate_probables_run(
                    methodology=self._methodology,
                    source_kind=source_kind,
                    source_run_identity=source_run_identity,
                    universe_identity=universe_identity,
                    universe_version=universe_version,
                    reconciliation_identity=reconciliation_identity,
                    reconciliation_version=reconciliation_version,
                    market_session_identity=market_session_identity,
                    observation_boundary=observation_boundary,
                    member_evidence=member_evidence,
                    unavailable_members=unavailable_members,
                    provenance=provenance,
                )
                self._store.retain_methodology(self._methodology)
                self._store.retain_run(run)
                retained = self._store.load_run(run_identity=run.run_identity)
                if retained != run:
                    raise ValueError("INTRADAY_PROBABLES_RELOAD_MISMATCH")
            except ProbablesError as error:
                self._current_failure = error.failure.value
                raise
            except Exception as error:
                self._current_failure = "PROBABLES_REFRESH_FAILED"
                raise RuntimeError("PROBABLES_REFRESH_FAILED") from error
            self._run = run
            self._current_failure = None
            return run

    def record_failure(self, failure: str) -> None:
        if not _text(failure) or not failure.replace("_", "").isalnum():
            raise ValueError("INTRADAY_PROBABLES_FAILURE_INVALID")
        with self._lock:
            self._current_failure = failure

    def snapshot(self) -> IntradayProbablesSnapshot:
        with self._lock:
            return IntradayProbablesSnapshot(
                methodology=self._methodology,
                current_failure=self._current_failure,
                last_successful_run_identity=None if self._run is None else self._run.run_identity,
                last_successful_analysis=None if self._run is None else self._run.observation_boundary,
                results=() if self._run is None else self._run.results,
                run=self._run,
            )


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


__all__ = [
    "PROBABLES_APPLICATION_IDENTITY",
    "PROBABLES_APPLICATION_VERSION",
    "IntradayProbablesApplication",
    "IntradayProbablesSnapshot",
]
