"""WO-05B: product-local, immutable operation accounting; no analytical authority."""
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
import json
from threading import RLock
from typing import Callable, TypeVar

_Result = TypeVar("_Result")


class ProviderRequestCategory(StrEnum):
    CURRENT_SESSION_CANDLE_REQUEST = "CURRENT_SESSION_CANDLE_REQUEST"
    PREVIOUS_SESSION_DAILY_REQUEST = "PREVIOUS_SESSION_DAILY_REQUEST"
    PREVIOUS_SESSION_INTRADAY_REQUEST = "PREVIOUS_SESSION_INTRADAY_REQUEST"
    INSTRUMENT_BINDING_REQUEST = "INSTRUMENT_BINDING_REQUEST"
    ASSESSMENT_OBSERVATION_REQUEST = "ASSESSMENT_OBSERVATION_REQUEST"


@dataclass(frozen=True, slots=True)
class DiscoveryOperationAccounting:
    accounting_identity: str
    operation_identity: str
    operation_kind: str
    analysis_boundary: datetime
    trusted_admission_time: datetime | None
    operation_started_at: datetime | None
    provider_acquisition_started_at: datetime | None
    operation_completed_at: datetime
    discovery_run_identity: str | None
    governed_members: int
    nse_index_focus_members: int
    nominal_evaluation_members: int
    nominal_timeframe_coverage: int
    factually_evaluable: int | None
    factual_failures: int | None
    prerequisite_unavailable: int | None
    not_reached_members: int | None
    actual_provider_requests: int | None
    request_categories: tuple[tuple[ProviderRequestCategory, int], ...] | None
    benchmark_subject_requests: int | None
    integrity_identity: str
    contract_identity: str = "KRONOS-INTRADAY-DISCOVERY-OPERATION-ACCOUNTING"
    contract_version: str = "1.0.0"

    def __post_init__(self) -> None:
        counts = (self.governed_members, self.nse_index_focus_members,
            self.nominal_evaluation_members, self.nominal_timeframe_coverage)
        outcomes = (self.factually_evaluable, self.factual_failures,
            self.prerequisite_unavailable, self.not_reached_members)
        if (not self.operation_identity.startswith("KRONOS-INTRADAY-DISCOVERY-OPERATION-")
            or self.operation_kind not in {"V2", "LEGACY"}
            or not _aware(self.analysis_boundary) or not _aware(self.operation_completed_at)
            or any(type(x) is not int or x < 0 for x in counts)
            or self.nse_index_focus_members > self.governed_members
            or self.nominal_evaluation_members > self.governed_members
            or self.nominal_timeframe_coverage != 4 * self.nominal_evaluation_members
            or (any(x is None for x in outcomes) and not all(x is None for x in outcomes))
            or (all(x is not None for x in outcomes) and (
                any(type(x) is not int or x < 0 for x in outcomes)
                or sum(outcomes) != self.governed_members))
            or (self.discovery_run_identity is not None and not self.discovery_run_identity.startswith("INTRADAY-DISCOVERY-RUN-"))
            or self.contract_identity != "KRONOS-INTRADAY-DISCOVERY-OPERATION-ACCOUNTING"
            or self.contract_version not in ("1.0.0", "1.1.0")):
            raise ValueError("INTRADAY_OPERATION_ACCOUNTING_INVALID")
        times = [x for x in (self.trusted_admission_time, self.operation_started_at,
            self.provider_acquisition_started_at, self.operation_completed_at) if x is not None]
        if (any(not _aware(x) for x in times)
            or any(a.astimezone(timezone.utc) > b.astimezone(timezone.utc) for a,b in zip(times,times[1:]))
            or (self.provider_acquisition_started_at is not None and self.operation_started_at is None)):
            raise ValueError("INTRADAY_OPERATION_ACCOUNTING_TIME_INVALID")
        if self.actual_provider_requests is None:
            if self.request_categories is not None or self.benchmark_subject_requests is not None:
                raise ValueError("INTRADAY_OPERATION_ACCOUNTING_UNKNOWN_INVALID")
        elif (type(self.actual_provider_requests) is not int or self.actual_provider_requests < 0
            or type(self.request_categories) is not tuple
            or any(type(k) is not ProviderRequestCategory for k, _ in self.request_categories)
            or tuple(x[0] for x in self.request_categories) != tuple(k for k in ProviderRequestCategory if self.contract_version == "1.1.0"
                or k is not ProviderRequestCategory.ASSESSMENT_OBSERVATION_REQUEST)
            or any(type(n) is not int or n < 0 for _,n in self.request_categories)
            or sum(n for _,n in self.request_categories) != self.actual_provider_requests
            or type(self.benchmark_subject_requests) is not int
            or not 0 <= self.benchmark_subject_requests <= self.actual_provider_requests):
            raise ValueError("INTRADAY_OPERATION_ACCOUNTING_COUNTS_INVALID")
        core = asdict(self)
        core.pop("accounting_identity"); core.pop("integrity_identity")
        if (self.accounting_identity != _identity("INTRADAY-OPERATION-ACCOUNTING-", core)
            or self.integrity_identity != _identity("INTEGRITY-INTRADAY-OPERATION-ACCOUNTING-", core)):
            raise ValueError("INTRADAY_OPERATION_ACCOUNTING_INTEGRITY_INVALID")

    @property
    def operation_duration_microseconds(self) -> int | None:
        if self.operation_started_at is None:
            return None
        delta = self.operation_completed_at.astimezone(timezone.utc) - self.operation_started_at.astimezone(timezone.utc)
        return (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds


def create_operation_accounting(**values) -> DiscoveryOperationAccounting:
    core = dict(values, contract_identity="KRONOS-INTRADAY-DISCOVERY-OPERATION-ACCOUNTING", contract_version="1.1.0")
    return DiscoveryOperationAccounting(
        accounting_identity=_identity("INTRADAY-OPERATION-ACCOUNTING-", core),
        integrity_identity=_identity("INTEGRITY-INTRADAY-OPERATION-ACCOUNTING-", core), **core)


class ProviderRequestCounter:
    """Count each actual acquisition-boundary invocation, including raised calls.

    These are DOMAIN-006 API attempts, not unobserved SDK/HTTP wire attempts.
    Categories partition calls; benchmark activity is an overlapping subset.
    """
    def __init__(self, clock: Callable[[], datetime]) -> None:
        self._clock = clock
        self._counts = Counter()
        self._benchmark = 0
        self._first = None
        self._first_sampled = False
        self._known = True
        self.population = None
        self._lock = RLock()

    def invoke(
        self, category: ProviderRequestCategory, method: Callable[..., _Result],
        *args: object, benchmark: bool = False, **kwargs: object,
    ) -> _Result:
        if type(category) is not ProviderRequestCategory or type(benchmark) is not bool:
            raise ValueError("INTRADAY_REQUEST_CATEGORY_INVALID")
        with self._lock:
            if not self._first_sampled:
                self._first_sampled = True
                try:
                    observed = self._clock()
                    self._first = observed if _aware(observed) else None
                except Exception:
                    # Missing time cannot discard a known invocation count.
                    self._first = None
            self._counts[category] += 1
            self._benchmark += int(benchmark)
        return method(*args, **kwargs)

    def record_population(self, successes: int, failures: int, prerequisites: int) -> None:
        with self._lock:
            self.population = dict(factually_evaluable=successes, factual_failures=failures,
                prerequisite_unavailable=prerequisites, not_reached_members=0)

    def mark_unknown(self) -> None:
        with self._lock:
            self._known = False

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return dict(provider_acquisition_started_at=self._first,
                actual_provider_requests=sum(self._counts.values()) if self._known else None,
                request_categories=tuple((k,self._counts[k]) for k in ProviderRequestCategory) if self._known else None,
                benchmark_subject_requests=self._benchmark if self._known else None)


def accounting_document(value: DiscoveryOperationAccounting | None) -> dict:
    if value is None:
        return {"availability": "NOT_RETAINED", "actual_provider_requests": None,
            "operation_duration_microseconds": None}
    result = json.loads(accounting_bytes(value))
    result.update(availability="RETAINED" if value.actual_provider_requests is not None else "NOT_RETAINED",
        operation_duration_microseconds=value.operation_duration_microseconds,
        provider_acquisition_start_availability=("RETAINED" if value.provider_acquisition_started_at is not None
            else "NOT_REACHED" if value.actual_provider_requests == 0 else "NOT_RETAINED"),
        provider_request_boundary="DOMAIN_006_ACQUISITION_API_INVOCATION",
        physical_http_attempts="NOT_RETAINED", response_sent_at="NOT_RETAINED")
    return result


def accounting_bytes(value: DiscoveryOperationAccounting) -> bytes:
    return _bytes(asdict(value)) + b"\n"


def restore_accounting(payload: bytes) -> DiscoveryOperationAccounting:
    try:
        values = json.loads(payload)
        for field in ("analysis_boundary", "trusted_admission_time", "operation_started_at",
            "provider_acquisition_started_at", "operation_completed_at"):
            if values[field] is not None:
                values[field] = datetime.fromisoformat(values[field])
        if values["request_categories"] is not None:
            values["request_categories"] = tuple((ProviderRequestCategory(k),n) for k,n in values["request_categories"])
        return DiscoveryOperationAccounting(**values)
    except (KeyError, TypeError, ValueError):
        raise ValueError("INTRADAY_OPERATION_ACCOUNTING_INVALID") from None


def _bytes(value: object) -> bytes:
    return json.dumps(value, default=lambda x:x.isoformat(), sort_keys=True, separators=(",", ":")).encode()


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(_bytes(value)).hexdigest().upper()


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None
