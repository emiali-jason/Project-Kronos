"""WO-05A admission-time authority; never changes candle/session semantics."""

from collections.abc import Callable
from datetime import datetime, timezone

from kronos.intraday.discovery import DiscoveryError, DiscoveryFailure


def trusted_now() -> datetime:
    """Production default; tests inject a clock on each service instance."""
    return datetime.now(timezone.utc)


class AnalysisTimeAdmissionError(DiscoveryError):
    def __init__(
        self, failure: DiscoveryFailure, requested: datetime,
        trusted_admission_time: datetime | None = None,
    ) -> None:
        self.requested_boundary = requested
        self.trusted_admission_time = trusted_admission_time
        super().__init__(failure)


def admit_analysis_time(
    requested: datetime, clock: Callable[[], datetime],
) -> datetime:
    """Admit equality/history, reject any future instant, with no tolerance."""
    if not _aware(requested):
        raise AnalysisTimeAdmissionError(
            DiscoveryFailure.OBSERVATION_BOUNDARY_INVALID, requested,
        )
    try:
        observed = clock()
        if not _aware(observed):
            raise ValueError("TRUSTED_TIME_UNAVAILABLE")
    except Exception as error:
        raise AnalysisTimeAdmissionError(
            DiscoveryFailure.TRUSTED_TIME_UNAVAILABLE, requested,
        ) from error
    # Compare instants explicitly, including equivalent offsets and DST folds.
    # The caller's original timezone and historical boundary are never replaced.
    if requested.astimezone(timezone.utc) > observed.astimezone(timezone.utc):
        raise AnalysisTimeAdmissionError(
            DiscoveryFailure.OBSERVATION_BOUNDARY_FUTURE, requested, observed,
        )
    return observed


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime) and value.tzinfo is not None
        and value.utcoffset() is not None
    )
