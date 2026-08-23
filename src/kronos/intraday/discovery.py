"""Intraday Native Discovery V0 contracts and factual scope accounting.

WO-03 owns contracts, identities, factual evaluability, and immutable run
accounting.  It deliberately does not implement the WO-05 scanner or any
numerical, directional, trading, Risk, or execution methodology.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import json
from collections.abc import Mapping
from typing import Iterable

from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.reconciliation import (
    Availability,
    ReconciliationPublication,
    ReconciliationState,
)


NATIVE_DISCOVERY_CONTRACT = "KRONOS-INTRADAY-NATIVE-DISCOVERY-V0"
NATIVE_DISCOVERY_VERSION = "0.1.0"
NATIVE_DISCOVERY_RESULT = "KRONOS-INTRADAY-NATIVE-DISCOVERY-RESULT-V0"
NATIVE_DISCOVERY_REASON = "KRONOS-INTRADAY-NATIVE-DISCOVERY-REASON-V0"
NATIVE_DISCOVERY_MACHINE_FACT_BUNDLE = (
    "KRONOS-INTRADAY-NATIVE-DISCOVERY-MACHINE-FACT-BUNDLE-V0"
)

STRUCTURAL_TIMEFRAMES = (
    IntradayTimeframe.DAILY,
    IntradayTimeframe.ONE_HOUR,
    IntradayTimeframe.FIFTEEN_MINUTES,
    IntradayTimeframe.FIVE_MINUTES,
)


class FactFamily(StrEnum):
    MARKET_SESSION_BOUNDARY = "MARKET_SESSION_BOUNDARY"
    GOVERNED_COMPLETED_OHLCV = "GOVERNED_COMPLETED_OHLCV"
    CANDLE_COMPLETENESS_RECONCILIATION = "CANDLE_COMPLETENESS_RECONCILIATION"
    PREVIOUS_SESSION_HLC_PDH_PDL = "PREVIOUS_SESSION_HLC_PDH_PDL"
    CLASSIC_PIVOTS_CPR = "CLASSIC_PIVOTS_CPR"
    STRUCTURAL_COMPARISONS = "STRUCTURAL_COMPARISONS"
    LOCAL_STRUCTURAL_PIVOTS_BARRIERS = "LOCAL_STRUCTURAL_PIVOTS_BARRIERS"
    TOUCH_BREAK_CLOSE_RETEST = "TOUCH_BREAK_CLOSE_RETEST"
    RANGE_MOVE_RETRACEMENT = "RANGE_MOVE_RETRACEMENT"
    VOLUME_OBSERVATIONS = "VOLUME_OBSERVATIONS"
    REFERENCE_DISTANCE_STRUCTURAL_RR = "REFERENCE_DISTANCE_STRUCTURAL_RR"
    SESSION_POSITION_TELEMETRY = "SESSION_POSITION_TELEMETRY"
    CURRENT_INCOMPLETE_CANDLE = "CURRENT_INCOMPLETE_CANDLE"


class FactRequirement(StrEnum):
    MANDATORY = "MANDATORY"
    OPTIONAL_TELEMETRY = "OPTIONAL_TELEMETRY"
    NOT_AUTHORIZED_FOR_CONSEQUENCE = "NOT_AUTHORIZED_FOR_CONSEQUENCE"


class MachineFactAuditStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    AVAILABLE_BUT_TELEMETRY_ONLY = "AVAILABLE_BUT_TELEMETRY_ONLY"
    MISSING_REQUIRED_FOR_DISCOVERY = "MISSING_REQUIRED_FOR_DISCOVERY"
    DEFERRED_METHODOLOGY = "DEFERRED_METHODOLOGY"
    NOT_V1 = "NOT_V1"


class MethodologyStatus(StrEnum):
    NOT_REQUIRED_NOW = "NOT_REQUIRED_NOW"
    DEFERRED_PENDING_EVIDENCE = "DEFERRED_PENDING_EVIDENCE"
    PLATFORMIZATION_CANDIDATE = "PLATFORMIZATION_CANDIDATE"


class FactualEvaluability(StrEnum):
    FACTUALLY_EVALUABLE = "FACTUALLY_EVALUABLE"
    PREREQUISITE_UNAVAILABLE = "PREREQUISITE_UNAVAILABLE"
    FACTUAL_FAILURE = "FACTUAL_FAILURE"
    OTHER_GOVERNED_UNAVAILABLE = "OTHER_GOVERNED_UNAVAILABLE"


class CandidateState(StrEnum):
    NOT_EVALUATED = "NOT_EVALUATED"
    CANDIDATE_ADMITTED = "CANDIDATE_ADMITTED"
    CANDIDATE_NOT_ADMITTED = "CANDIDATE_NOT_ADMITTED"
    NOT_EVALUATED_DUE_TO_PREREQUISITE = (
        "NOT_EVALUATED_DUE_TO_PREREQUISITE"
    )
    NOT_EVALUATED_DUE_TO_FACTUAL_FAILURE = (
        "NOT_EVALUATED_DUE_TO_FACTUAL_FAILURE"
    )


class DiscoveryReason(StrEnum):
    FACTUAL_PATH_AVAILABLE = "FACTUAL_PATH_AVAILABLE"
    ACTIVE_DERIVATIVE_BINDING_UNAVAILABLE = (
        "ACTIVE_DERIVATIVE_BINDING_UNAVAILABLE"
    )
    PROVIDER_CONTRACT_UNAVAILABLE = "PROVIDER_CONTRACT_UNAVAILABLE"
    PROVIDER_MAPPING_UNAVAILABLE = "PROVIDER_MAPPING_UNAVAILABLE"
    MARKET_SESSION_UNAVAILABLE = "MARKET_SESSION_UNAVAILABLE"
    MACHINE_FACT_BUNDLE_INCOMPLETE = "MACHINE_FACT_BUNDLE_INCOMPLETE"
    INCOMPLETE_CANDLE_NOT_AUTHORIZED = "INCOMPLETE_CANDLE_NOT_AUTHORIZED"
    SOURCE_STALE = "SOURCE_STALE"


class ExecutionEligibility(StrEnum):
    NOT_ESTABLISHED = "NOT_ESTABLISHED"


class DiscoveryFailure(StrEnum):
    UNIVERSE_VERSION_UNAVAILABLE = "UNIVERSE_VERSION_UNAVAILABLE"
    RECONCILIATION_VERSION_UNAVAILABLE = "RECONCILIATION_VERSION_UNAVAILABLE"
    CANONICAL_IDENTITY_UNAVAILABLE = "CANONICAL_IDENTITY_UNAVAILABLE"
    MACHINE_FACT_PREREQUISITE_UNAVAILABLE = (
        "MACHINE_FACT_PREREQUISITE_UNAVAILABLE"
    )
    MACHINE_FACT_BUNDLE_INCOMPLETE = "MACHINE_FACT_BUNDLE_INCOMPLETE"
    MARKET_SESSION_UNAVAILABLE = "MARKET_SESSION_UNAVAILABLE"
    OBSERVATION_BOUNDARY_INVALID = "OBSERVATION_BOUNDARY_INVALID"
    INCOMPLETE_CANDLE_NOT_AUTHORIZED = "INCOMPLETE_CANDLE_NOT_AUTHORIZED"
    SOURCE_STALE = "SOURCE_STALE"
    PUBLICATION_STALE = "PUBLICATION_STALE"
    INTEGRITY_INVALID = "INTEGRITY_INVALID"
    PERSISTENCE_CONFLICT = "PERSISTENCE_CONFLICT"
    PUBLICATION_UNAVAILABLE = "PUBLICATION_UNAVAILABLE"


class DiscoveryError(RuntimeError):
    """Sanitized fail-closed Discovery error."""

    def __init__(self, failure: DiscoveryFailure) -> None:
        self.failure = failure
        super().__init__(failure.value)


MANDATORY_FACT_FAMILIES = (
    FactFamily.MARKET_SESSION_BOUNDARY,
    FactFamily.GOVERNED_COMPLETED_OHLCV,
    FactFamily.CANDLE_COMPLETENESS_RECONCILIATION,
)

OPTIONAL_TELEMETRY_FACT_FAMILIES = (
    FactFamily.PREVIOUS_SESSION_HLC_PDH_PDL,
    FactFamily.CLASSIC_PIVOTS_CPR,
    FactFamily.STRUCTURAL_COMPARISONS,
    FactFamily.LOCAL_STRUCTURAL_PIVOTS_BARRIERS,
    FactFamily.TOUCH_BREAK_CLOSE_RETEST,
    FactFamily.RANGE_MOVE_RETRACEMENT,
    FactFamily.VOLUME_OBSERVATIONS,
    FactFamily.REFERENCE_DISTANCE_STRUCTURAL_RR,
    FactFamily.SESSION_POSITION_TELEMETRY,
)

MACHINE_FACT_GAP_AUDIT = (
    (FactFamily.MARKET_SESSION_BOUNDARY, MachineFactAuditStatus.AVAILABLE),
    (FactFamily.GOVERNED_COMPLETED_OHLCV, MachineFactAuditStatus.AVAILABLE),
    (
        FactFamily.CANDLE_COMPLETENESS_RECONCILIATION,
        MachineFactAuditStatus.AVAILABLE,
    ),
    (
        FactFamily.PREVIOUS_SESSION_HLC_PDH_PDL,
        MachineFactAuditStatus.AVAILABLE_BUT_TELEMETRY_ONLY,
    ),
    (
        FactFamily.CLASSIC_PIVOTS_CPR,
        MachineFactAuditStatus.AVAILABLE_BUT_TELEMETRY_ONLY,
    ),
    (
        FactFamily.STRUCTURAL_COMPARISONS,
        MachineFactAuditStatus.AVAILABLE_BUT_TELEMETRY_ONLY,
    ),
    (
        FactFamily.LOCAL_STRUCTURAL_PIVOTS_BARRIERS,
        MachineFactAuditStatus.AVAILABLE_BUT_TELEMETRY_ONLY,
    ),
    (
        FactFamily.TOUCH_BREAK_CLOSE_RETEST,
        MachineFactAuditStatus.AVAILABLE_BUT_TELEMETRY_ONLY,
    ),
    (
        FactFamily.RANGE_MOVE_RETRACEMENT,
        MachineFactAuditStatus.AVAILABLE_BUT_TELEMETRY_ONLY,
    ),
    (
        FactFamily.VOLUME_OBSERVATIONS,
        MachineFactAuditStatus.AVAILABLE_BUT_TELEMETRY_ONLY,
    ),
    (
        FactFamily.REFERENCE_DISTANCE_STRUCTURAL_RR,
        MachineFactAuditStatus.AVAILABLE_BUT_TELEMETRY_ONLY,
    ),
    (
        FactFamily.SESSION_POSITION_TELEMETRY,
        MachineFactAuditStatus.AVAILABLE_BUT_TELEMETRY_ONLY,
    ),
    (
        FactFamily.CURRENT_INCOMPLETE_CANDLE,
        MachineFactAuditStatus.AVAILABLE_BUT_TELEMETRY_ONLY,
    ),
)

METHODOLOGY_STATUS = (
    ("ATR", MethodologyStatus.DEFERRED_PENDING_EVIDENCE),
    ("SMA20", MethodologyStatus.DEFERRED_PENDING_EVIDENCE),
    ("SMA50", MethodologyStatus.DEFERRED_PENDING_EVIDENCE),
    ("SMA200", MethodologyStatus.DEFERRED_PENDING_EVIDENCE),
    ("RELATIVE_VOLUME", MethodologyStatus.DEFERRED_PENDING_EVIDENCE),
    ("VOLUME_LOOKBACK", MethodologyStatus.DEFERRED_PENDING_EVIDENCE),
    ("VOLUME_THRESHOLD", MethodologyStatus.DEFERRED_PENDING_EVIDENCE),
    ("NORMALIZED_EXTENSION", MethodologyStatus.DEFERRED_PENDING_EVIDENCE),
    ("PATH_CLEARANCE_ARITHMETIC", MethodologyStatus.DEFERRED_PENDING_EVIDENCE),
    ("SESSION_POSITION_TELEMETRY", MethodologyStatus.NOT_REQUIRED_NOW),
)


@dataclass(frozen=True, slots=True)
class MachineFactEvidence:
    family: FactFamily
    requirement: FactRequirement
    evidence_identity: str
    fact_version: str
    observed_at: datetime
    timeframe: IntradayTimeframe | None
    completed_candle: bool | None

    def __post_init__(self) -> None:
        if (
            type(self.family) is not FactFamily
            or type(self.requirement) is not FactRequirement
            or not _text(self.evidence_identity)
            or not _version(self.fact_version)
            or not _aware(self.observed_at)
            or (
                self.timeframe is not None
                and type(self.timeframe) is not IntradayTimeframe
            )
            or (
                self.completed_candle is not None
                and type(self.completed_candle) is not bool
            )
        ):
            raise DiscoveryError(DiscoveryFailure.INTEGRITY_INVALID)
        structural = self.family in {
            FactFamily.GOVERNED_COMPLETED_OHLCV,
            FactFamily.CANDLE_COMPLETENESS_RECONCILIATION,
        }
        if structural and (
            self.timeframe not in STRUCTURAL_TIMEFRAMES
            or self.completed_candle is not True
        ):
            raise DiscoveryError(
                DiscoveryFailure.INCOMPLETE_CANDLE_NOT_AUTHORIZED
            )
        if self.family is FactFamily.CURRENT_INCOMPLETE_CANDLE and (
            self.completed_candle is not False
            or self.requirement
            is not FactRequirement.NOT_AUTHORIZED_FOR_CONSEQUENCE
        ):
            raise DiscoveryError(
                DiscoveryFailure.INCOMPLETE_CANDLE_NOT_AUTHORIZED
            )


@dataclass(frozen=True, slots=True)
class NativeDiscoveryMachineFactBundle:
    canonical_identity: str
    universe_identity: str
    universe_version: str
    reconciliation_identity: str
    reconciliation_version: str
    market_session_identity: str
    market_session_boundary_identity: str
    observation_boundary: datetime
    evidence: tuple[MachineFactEvidence, ...]
    source_identities: tuple[str, ...]
    provenance: tuple[str, ...]
    bundle_identity: str
    schema_identity: str = NATIVE_DISCOVERY_MACHINE_FACT_BUNDLE
    bundle_version: str = NATIVE_DISCOVERY_VERSION

    def __post_init__(self) -> None:
        core = machine_fact_bundle_payload(self, include_identity=False)
        evidence_keys = tuple(
            (item.family, item.timeframe, item.evidence_identity)
            for item in self.evidence
        )
        if (
            self.schema_identity != NATIVE_DISCOVERY_MACHINE_FACT_BUNDLE
            or self.bundle_version != NATIVE_DISCOVERY_VERSION
            or any(
                not _text(item)
                for item in (
                    self.canonical_identity,
                    self.universe_identity,
                    self.universe_version,
                    self.reconciliation_identity,
                    self.reconciliation_version,
                    self.market_session_identity,
                    self.market_session_boundary_identity,
                )
            )
            or not _aware(self.observation_boundary)
            or not self.evidence
            or any(type(item) is not MachineFactEvidence for item in self.evidence)
            or len(set(evidence_keys)) != len(evidence_keys)
            or not _unique_texts(self.source_identities)
            or not _unique_texts(self.provenance)
            or self.bundle_identity != _identity("INTRADAY-DISCOVERY-FACT-BUNDLE", core)
        ):
            raise DiscoveryError(DiscoveryFailure.INTEGRITY_INVALID)
        _require_mandatory_bundle_evidence(self)


def create_machine_fact_bundle(**fields: object) -> NativeDiscoveryMachineFactBundle:
    values = dict(fields)
    values.setdefault("schema_identity", NATIVE_DISCOVERY_MACHINE_FACT_BUNDLE)
    values.setdefault("bundle_version", NATIVE_DISCOVERY_VERSION)
    temporary = _machine_fact_bundle_payload_from_values(values)
    return NativeDiscoveryMachineFactBundle(
        **values,  # type: ignore[arg-type]
        bundle_identity=_identity("INTRADAY-DISCOVERY-FACT-BUNDLE", temporary),
    )


@dataclass(frozen=True, slots=True)
class DiscoveryMemberResult:
    run_identity: str
    universe_member_identity: str
    sponsor_label: str
    canonical_identity: str
    observation_boundary: datetime
    machine_fact_bundle_identity: str | None
    evaluability: FactualEvaluability
    candidate_state: CandidateState
    reasons: tuple[DiscoveryReason, ...]
    execution_eligibility: ExecutionEligibility
    result_identity: str
    persistence_identity: str
    schema_identity: str = NATIVE_DISCOVERY_RESULT
    result_version: str = NATIVE_DISCOVERY_VERSION

    def __post_init__(self) -> None:
        core = discovery_result_payload(self, include_identities=False)
        if (
            self.schema_identity != NATIVE_DISCOVERY_RESULT
            or self.result_version != NATIVE_DISCOVERY_VERSION
            or any(
                not _text(item)
                for item in (
                    self.run_identity,
                    self.universe_member_identity,
                    self.sponsor_label,
                    self.canonical_identity,
                )
            )
            or not _aware(self.observation_boundary)
            or (
                self.machine_fact_bundle_identity is not None
                and not _text(self.machine_fact_bundle_identity)
            )
            or type(self.evaluability) is not FactualEvaluability
            or type(self.candidate_state) is not CandidateState
            or not self.reasons
            or any(type(item) is not DiscoveryReason for item in self.reasons)
            or len(set(self.reasons)) != len(self.reasons)
            or self.execution_eligibility
            is not ExecutionEligibility.NOT_ESTABLISHED
            or self.result_identity != _identity("INTRADAY-DISCOVERY-RESULT", core)
            or self.persistence_identity
            != _identity(
                "INTRADAY-DISCOVERY-RESULT-PERSISTENCE",
                {"result_identity": self.result_identity},
            )
        ):
            raise DiscoveryError(DiscoveryFailure.INTEGRITY_INVALID)
        _validate_result_state(self)


def create_discovery_result(**fields: object) -> DiscoveryMemberResult:
    values = dict(fields)
    values.setdefault("execution_eligibility", ExecutionEligibility.NOT_ESTABLISHED)
    values.setdefault("schema_identity", NATIVE_DISCOVERY_RESULT)
    values.setdefault("result_version", NATIVE_DISCOVERY_VERSION)
    core = _discovery_result_payload_from_values(values)
    result_identity = _identity("INTRADAY-DISCOVERY-RESULT", core)
    return DiscoveryMemberResult(
        **values,  # type: ignore[arg-type]
        result_identity=result_identity,
        persistence_identity=_identity(
            "INTRADAY-DISCOVERY-RESULT-PERSISTENCE",
            {"result_identity": result_identity},
        ),
    )


@dataclass(frozen=True, slots=True)
class DiscoveryRunAccounting:
    universe_members: int
    factually_evaluable: int
    prerequisite_unavailable: int
    evaluated: int
    candidate_results: int
    factual_failures: int
    other_governed_unavailable: int

    def __post_init__(self) -> None:
        values = tuple(
            getattr(self, name)
            for name in DiscoveryRunAccounting.__dataclass_fields__
        )
        if (
            any(type(item) is not int or item < 0 for item in values)
            or self.factually_evaluable
            + self.prerequisite_unavailable
            + self.factual_failures
            + self.other_governed_unavailable
            != self.universe_members
            or self.evaluated > self.factually_evaluable
            or self.candidate_results > self.evaluated
        ):
            raise DiscoveryError(DiscoveryFailure.INTEGRITY_INVALID)


@dataclass(frozen=True, slots=True)
class NativeDiscoveryRun:
    universe_identity: str
    universe_version: str
    universe_integrity_identity: str
    reconciliation_identity: str
    reconciliation_version: str
    reconciliation_integrity_identity: str
    machine_fact_bundle_schema: str
    market_session_identity: str
    market_session_boundary_identity: str
    observation_boundary: datetime
    accounting: DiscoveryRunAccounting
    results: tuple[DiscoveryMemberResult, ...]
    source_identities: tuple[str, ...]
    provenance: tuple[str, ...]
    run_identity: str
    integrity_identity: str
    contract_identity: str = NATIVE_DISCOVERY_CONTRACT
    contract_version: str = NATIVE_DISCOVERY_VERSION

    def __post_init__(self) -> None:
        result_ids = tuple(item.result_identity for item in self.results)
        member_ids = tuple(item.universe_member_identity for item in self.results)
        run_core = discovery_run_identity_payload(self)
        full = discovery_run_payload(self, include_integrity=False)
        if (
            self.contract_identity != NATIVE_DISCOVERY_CONTRACT
            or self.contract_version != NATIVE_DISCOVERY_VERSION
            or self.machine_fact_bundle_schema
            != NATIVE_DISCOVERY_MACHINE_FACT_BUNDLE
            or any(
                not _text(item)
                for item in (
                    self.universe_identity,
                    self.universe_version,
                    self.universe_integrity_identity,
                    self.reconciliation_identity,
                    self.reconciliation_version,
                    self.reconciliation_integrity_identity,
                    self.market_session_identity,
                    self.market_session_boundary_identity,
                )
            )
            or not _aware(self.observation_boundary)
            or type(self.accounting) is not DiscoveryRunAccounting
            or len(self.results) != self.accounting.universe_members
            or any(type(item) is not DiscoveryMemberResult for item in self.results)
            or any(item.run_identity != self.run_identity for item in self.results)
            or any(
                item.observation_boundary != self.observation_boundary
                for item in self.results
            )
            or len(set(result_ids)) != len(result_ids)
            or len(set(member_ids)) != len(member_ids)
            or _account_results(self.results) != self.accounting
            or not _unique_texts(self.source_identities)
            or not _unique_texts(self.provenance)
            or self.run_identity != _identity("INTRADAY-DISCOVERY-RUN", run_core)
            or self.integrity_identity
            != _identity("INTRADAY-DISCOVERY-RUN-INTEGRITY", full)
        ):
            raise DiscoveryError(DiscoveryFailure.INTEGRITY_INVALID)

    def lookup(self, sponsor_label: str) -> DiscoveryMemberResult:
        matches = tuple(item for item in self.results if item.sponsor_label == sponsor_label)
        if len(matches) != 1:
            raise DiscoveryError(DiscoveryFailure.CANONICAL_IDENTITY_UNAVAILABLE)
        return matches[0]


def create_discovery_scope_run(
    *,
    reconciliation: ReconciliationPublication,
    expected_universe_identity: str,
    expected_universe_version: str,
    expected_reconciliation_identity: str,
    expected_reconciliation_version: str,
    market_session_identity: str,
    market_session_boundary_identity: str,
    observation_boundary: datetime,
) -> NativeDiscoveryRun:
    """Account all governed members; do not execute candidate methodology."""

    if type(reconciliation) is not ReconciliationPublication:
        raise DiscoveryError(DiscoveryFailure.RECONCILIATION_VERSION_UNAVAILABLE)
    if (reconciliation.universe_identity, reconciliation.universe_version) != (
        expected_universe_identity,
        expected_universe_version,
    ):
        raise DiscoveryError(DiscoveryFailure.UNIVERSE_VERSION_UNAVAILABLE)
    if (
        reconciliation.publication_identity,
        reconciliation.publication_version,
    ) != (expected_reconciliation_identity, expected_reconciliation_version):
        raise DiscoveryError(DiscoveryFailure.RECONCILIATION_VERSION_UNAVAILABLE)
    if not _aware(observation_boundary):
        raise DiscoveryError(DiscoveryFailure.OBSERVATION_BOUNDARY_INVALID)
    if not _text(market_session_identity) or not _text(
        market_session_boundary_identity
    ):
        raise DiscoveryError(DiscoveryFailure.MARKET_SESSION_UNAVAILABLE)
    accounting = _scope_accounting(reconciliation)
    run_identity = _identity(
        "INTRADAY-DISCOVERY-RUN",
        _run_identity_values(
            universe_identity=reconciliation.universe_identity,
            universe_version=reconciliation.universe_version,
            reconciliation_identity=reconciliation.publication_identity,
            reconciliation_version=reconciliation.publication_version,
            market_session_identity=market_session_identity,
            market_session_boundary_identity=market_session_boundary_identity,
            observation_boundary=observation_boundary,
            accounting=accounting,
            member_identities=tuple(
                item.universe_member_identity for item in reconciliation.members
            ),
        ),
    )
    results = tuple(
        _scope_result(
            run_identity=run_identity,
            member=member,
            observation_boundary=observation_boundary,
        )
        for member in reconciliation.members
    )
    values = {
        "universe_identity": reconciliation.universe_identity,
        "universe_version": reconciliation.universe_version,
        "universe_integrity_identity": reconciliation.universe_integrity_identity,
        "reconciliation_identity": reconciliation.publication_identity,
        "reconciliation_version": reconciliation.publication_version,
        "reconciliation_integrity_identity": reconciliation.integrity_identity,
        "machine_fact_bundle_schema": NATIVE_DISCOVERY_MACHINE_FACT_BUNDLE,
        "market_session_identity": market_session_identity,
        "market_session_boundary_identity": market_session_boundary_identity,
        "observation_boundary": observation_boundary,
        "accounting": accounting,
        "results": results,
        "source_identities": (
            reconciliation.universe_integrity_identity,
            reconciliation.integrity_identity,
            market_session_boundary_identity,
        ),
        "provenance": (
            "CHIEF-ARCHITECT-WO-03-OPERATING-SCOPE-CLOSURE",
            "KRONOS-INTRADAY-WO-03",
            "No candidate methodology executed",
        ),
        "run_identity": run_identity,
        "contract_identity": NATIVE_DISCOVERY_CONTRACT,
        "contract_version": NATIVE_DISCOVERY_VERSION,
    }
    temporary = _discovery_run_payload_from_values(values)
    return NativeDiscoveryRun(
        **values,
        integrity_identity=_identity(
            "INTRADAY-DISCOVERY-RUN-INTEGRITY", temporary
        ),
    )


def create_discovery_runtime_run(
    *,
    reconciliation: ReconciliationPublication,
    expected_universe_identity: str,
    expected_universe_version: str,
    expected_reconciliation_identity: str,
    expected_reconciliation_version: str,
    market_session_identity: str,
    market_session_boundary_identity: str,
    observation_boundary: datetime,
    machine_fact_bundles: Mapping[str, NativeDiscoveryMachineFactBundle],
    factual_failures: Mapping[str, DiscoveryReason],
) -> NativeDiscoveryRun:
    """Seal one complete runtime run without applying admission methodology."""

    if type(reconciliation) is not ReconciliationPublication:
        raise DiscoveryError(DiscoveryFailure.RECONCILIATION_VERSION_UNAVAILABLE)
    if (reconciliation.universe_identity, reconciliation.universe_version) != (
        expected_universe_identity,
        expected_universe_version,
    ):
        raise DiscoveryError(DiscoveryFailure.UNIVERSE_VERSION_UNAVAILABLE)
    if (
        reconciliation.publication_identity,
        reconciliation.publication_version,
    ) != (expected_reconciliation_identity, expected_reconciliation_version):
        raise DiscoveryError(DiscoveryFailure.RECONCILIATION_VERSION_UNAVAILABLE)
    if not _aware(observation_boundary):
        raise DiscoveryError(DiscoveryFailure.OBSERVATION_BOUNDARY_INVALID)
    if not _text(market_session_identity) or not _text(
        market_session_boundary_identity
    ):
        raise DiscoveryError(DiscoveryFailure.MARKET_SESSION_UNAVAILABLE)
    if not isinstance(machine_fact_bundles, Mapping) or not isinstance(
        factual_failures, Mapping
    ):
        raise DiscoveryError(DiscoveryFailure.INTEGRITY_INVALID)

    eligible = {
        item.universe_member_identity: item
        for item in reconciliation.members
        if item.dimensions.machine_fact_consumability is Availability.AVAILABLE
    }
    supplied = set(machine_fact_bundles)
    failed = set(factual_failures)
    if (
        supplied & failed
        or supplied | failed != set(eligible)
        or any(type(reason) is not DiscoveryReason for reason in factual_failures.values())
        or any(
            type(bundle) is not NativeDiscoveryMachineFactBundle
            or bundle.canonical_identity != eligible[member_id].canonical_identity
            or bundle.universe_identity != reconciliation.universe_identity
            or bundle.universe_version != reconciliation.universe_version
            or bundle.reconciliation_identity != reconciliation.publication_identity
            or bundle.reconciliation_version != reconciliation.publication_version
            or bundle.market_session_identity != market_session_identity
            or bundle.market_session_boundary_identity
            != market_session_boundary_identity
            or bundle.observation_boundary != observation_boundary
            for member_id, bundle in machine_fact_bundles.items()
        )
    ):
        raise DiscoveryError(DiscoveryFailure.INTEGRITY_INVALID)

    accounting = DiscoveryRunAccounting(
        universe_members=len(reconciliation.members),
        factually_evaluable=len(machine_fact_bundles),
        prerequisite_unavailable=sum(
            item.dimensions.machine_fact_consumability is Availability.UNAVAILABLE
            for item in reconciliation.members
        ),
        evaluated=0,
        candidate_results=0,
        factual_failures=len(factual_failures),
        other_governed_unavailable=sum(
            item.dimensions.machine_fact_consumability
            not in {Availability.AVAILABLE, Availability.UNAVAILABLE}
            for item in reconciliation.members
        ),
    )
    run_identity = _identity(
        "INTRADAY-DISCOVERY-RUN",
        _run_identity_values(
            universe_identity=reconciliation.universe_identity,
            universe_version=reconciliation.universe_version,
            reconciliation_identity=reconciliation.publication_identity,
            reconciliation_version=reconciliation.publication_version,
            market_session_identity=market_session_identity,
            market_session_boundary_identity=market_session_boundary_identity,
            observation_boundary=observation_boundary,
            accounting=accounting,
            member_identities=tuple(
                item.universe_member_identity for item in reconciliation.members
            ),
        ),
    )
    results = tuple(
        _runtime_result(
            run_identity=run_identity,
            member=member,
            observation_boundary=observation_boundary,
            bundle=machine_fact_bundles.get(member.universe_member_identity),
            factual_failure=factual_failures.get(member.universe_member_identity),
        )
        for member in reconciliation.members
    )
    values = {
        "universe_identity": reconciliation.universe_identity,
        "universe_version": reconciliation.universe_version,
        "universe_integrity_identity": reconciliation.universe_integrity_identity,
        "reconciliation_identity": reconciliation.publication_identity,
        "reconciliation_version": reconciliation.publication_version,
        "reconciliation_integrity_identity": reconciliation.integrity_identity,
        "machine_fact_bundle_schema": NATIVE_DISCOVERY_MACHINE_FACT_BUNDLE,
        "market_session_identity": market_session_identity,
        "market_session_boundary_identity": market_session_boundary_identity,
        "observation_boundary": observation_boundary,
        "accounting": accounting,
        "results": results,
        "source_identities": (
            reconciliation.universe_integrity_identity,
            reconciliation.integrity_identity,
            market_session_boundary_identity,
        ),
        "provenance": (
            "KRONOS-INTRADAY-WO-05",
            "Governed completed factual evidence only",
            "Candidate admission methodology not commissioned",
        ),
        "run_identity": run_identity,
        "contract_identity": NATIVE_DISCOVERY_CONTRACT,
        "contract_version": NATIVE_DISCOVERY_VERSION,
    }
    return NativeDiscoveryRun(
        **values,
        integrity_identity=_identity(
            "INTRADAY-DISCOVERY-RUN-INTEGRITY",
            _discovery_run_payload_from_values(values),
        ),
    )


def discovery_result_payload(
    value: DiscoveryMemberResult, *, include_identities: bool = True
) -> dict[str, object]:
    payload = _discovery_result_payload_from_values(
        {
            name: getattr(value, name)
            for name in DiscoveryMemberResult.__dataclass_fields__
            if name not in {"result_identity", "persistence_identity"}
        }
    )
    if include_identities:
        payload["result_identity"] = value.result_identity
        payload["persistence_identity"] = value.persistence_identity
    return payload


def discovery_run_identity_payload(value: NativeDiscoveryRun) -> dict[str, object]:
    return _run_identity_values(
        universe_identity=value.universe_identity,
        universe_version=value.universe_version,
        reconciliation_identity=value.reconciliation_identity,
        reconciliation_version=value.reconciliation_version,
        market_session_identity=value.market_session_identity,
        market_session_boundary_identity=value.market_session_boundary_identity,
        observation_boundary=value.observation_boundary,
        accounting=value.accounting,
        member_identities=tuple(
            item.universe_member_identity for item in value.results
        ),
    )


def discovery_run_payload(
    value: NativeDiscoveryRun, *, include_integrity: bool = True
) -> dict[str, object]:
    payload = _discovery_run_payload_from_values(
        {
            name: getattr(value, name)
            for name in NativeDiscoveryRun.__dataclass_fields__
            if name != "integrity_identity"
        }
    )
    if include_integrity:
        payload["integrity_identity"] = value.integrity_identity
    return payload


def discovery_run_bytes(value: NativeDiscoveryRun) -> bytes:
    return _encode(discovery_run_payload(value))


def discovery_result_bytes(value: DiscoveryMemberResult) -> bytes:
    return _encode(discovery_result_payload(value))


def machine_fact_bundle_payload(
    value: NativeDiscoveryMachineFactBundle, *, include_identity: bool = True
) -> dict[str, object]:
    payload = _machine_fact_bundle_payload_from_values(
        {
            name: getattr(value, name)
            for name in NativeDiscoveryMachineFactBundle.__dataclass_fields__
            if name != "bundle_identity"
        }
    )
    if include_identity:
        payload["bundle_identity"] = value.bundle_identity
    return payload


def machine_fact_bundle_bytes(value: NativeDiscoveryMachineFactBundle) -> bytes:
    return _encode(machine_fact_bundle_payload(value))


def parse_machine_fact_bundle(
    encoded: bytes,
) -> NativeDiscoveryMachineFactBundle:
    try:
        item = json.loads(encoded)
        value = NativeDiscoveryMachineFactBundle(
            canonical_identity=item["canonical_identity"],
            universe_identity=item["universe_identity"],
            universe_version=item["universe_version"],
            reconciliation_identity=item["reconciliation_identity"],
            reconciliation_version=item["reconciliation_version"],
            market_session_identity=item["market_session_identity"],
            market_session_boundary_identity=item[
                "market_session_boundary_identity"
            ],
            observation_boundary=datetime.fromisoformat(
                item["observation_boundary"]
            ),
            evidence=tuple(
                MachineFactEvidence(
                    family=FactFamily(evidence["family"]),
                    requirement=FactRequirement(evidence["requirement"]),
                    evidence_identity=evidence["evidence_identity"],
                    fact_version=evidence["fact_version"],
                    observed_at=datetime.fromisoformat(evidence["observed_at"]),
                    timeframe=(
                        None
                        if evidence["timeframe"] is None
                        else IntradayTimeframe(evidence["timeframe"])
                    ),
                    completed_candle=evidence["completed_candle"],
                )
                for evidence in item["evidence"]
            ),
            source_identities=tuple(item["source_identities"]),
            provenance=tuple(item["provenance"]),
            bundle_identity=item["bundle_identity"],
            schema_identity=item["schema_identity"],
            bundle_version=item["bundle_version"],
        )
    except (
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        DiscoveryError,
    ) as error:
        raise DiscoveryError(DiscoveryFailure.INTEGRITY_INVALID) from error
    if machine_fact_bundle_bytes(value) != encoded:
        raise DiscoveryError(DiscoveryFailure.INTEGRITY_INVALID)
    return value


def parse_discovery_result(encoded: bytes) -> DiscoveryMemberResult:
    try:
        item = json.loads(encoded)
        value = DiscoveryMemberResult(
            run_identity=item["run_identity"],
            universe_member_identity=item["universe_member_identity"],
            sponsor_label=item["sponsor_label"],
            canonical_identity=item["canonical_identity"],
            observation_boundary=datetime.fromisoformat(
                item["observation_boundary"]
            ),
            machine_fact_bundle_identity=item["machine_fact_bundle_identity"],
            evaluability=FactualEvaluability(item["evaluability"]),
            candidate_state=CandidateState(item["candidate_state"]),
            reasons=tuple(DiscoveryReason(reason) for reason in item["reasons"]),
            execution_eligibility=ExecutionEligibility(
                item["execution_eligibility"]
            ),
            result_identity=item["result_identity"],
            persistence_identity=item["persistence_identity"],
            schema_identity=item["schema_identity"],
            result_version=item["result_version"],
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise DiscoveryError(DiscoveryFailure.INTEGRITY_INVALID) from error
    if discovery_result_bytes(value) != encoded:
        raise DiscoveryError(DiscoveryFailure.INTEGRITY_INVALID)
    return value


def parse_discovery_run(encoded: bytes) -> NativeDiscoveryRun:
    try:
        item = json.loads(encoded)
        accounting = DiscoveryRunAccounting(**item["accounting"])
        results = tuple(_result_from_payload(result) for result in item["results"])
        value = NativeDiscoveryRun(
            universe_identity=item["universe_identity"],
            universe_version=item["universe_version"],
            universe_integrity_identity=item["universe_integrity_identity"],
            reconciliation_identity=item["reconciliation_identity"],
            reconciliation_version=item["reconciliation_version"],
            reconciliation_integrity_identity=item[
                "reconciliation_integrity_identity"
            ],
            machine_fact_bundle_schema=item["machine_fact_bundle_schema"],
            market_session_identity=item["market_session_identity"],
            market_session_boundary_identity=item[
                "market_session_boundary_identity"
            ],
            observation_boundary=datetime.fromisoformat(
                item["observation_boundary"]
            ),
            accounting=accounting,
            results=results,
            source_identities=tuple(item["source_identities"]),
            provenance=tuple(item["provenance"]),
            run_identity=item["run_identity"],
            integrity_identity=item["integrity_identity"],
            contract_identity=item["contract_identity"],
            contract_version=item["contract_version"],
        )
    except (
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        DiscoveryError,
    ) as error:
        raise DiscoveryError(DiscoveryFailure.INTEGRITY_INVALID) from error
    if discovery_run_bytes(value) != encoded:
        raise DiscoveryError(DiscoveryFailure.INTEGRITY_INVALID)
    return value


def _scope_result(*, run_identity: str, member: object, observation_boundary: datetime) -> DiscoveryMemberResult:
    if member.dimensions.machine_fact_consumability is Availability.AVAILABLE:
        return create_discovery_result(
            run_identity=run_identity,
            universe_member_identity=member.universe_member_identity,
            sponsor_label=member.sponsor_label,
            canonical_identity=member.canonical_identity,
            observation_boundary=observation_boundary,
            machine_fact_bundle_identity=None,
            evaluability=FactualEvaluability.FACTUALLY_EVALUABLE,
            candidate_state=CandidateState.NOT_EVALUATED,
            reasons=(DiscoveryReason.FACTUAL_PATH_AVAILABLE,),
        )
    reason = {
        ReconciliationState.ACTIVE_CONTRACT_BINDING_UNAVAILABLE:
            DiscoveryReason.ACTIVE_DERIVATIVE_BINDING_UNAVAILABLE,
        ReconciliationState.PROVIDER_CONTRACT_UNAVAILABLE:
            DiscoveryReason.PROVIDER_CONTRACT_UNAVAILABLE,
    }.get(member.state, DiscoveryReason.MACHINE_FACT_BUNDLE_INCOMPLETE)
    return create_discovery_result(
        run_identity=run_identity,
        universe_member_identity=member.universe_member_identity,
        sponsor_label=member.sponsor_label,
        canonical_identity=member.canonical_identity,
        observation_boundary=observation_boundary,
        machine_fact_bundle_identity=None,
        evaluability=FactualEvaluability.PREREQUISITE_UNAVAILABLE,
        candidate_state=CandidateState.NOT_EVALUATED_DUE_TO_PREREQUISITE,
        reasons=(reason,),
    )


def _runtime_result(
    *,
    run_identity: str,
    member: object,
    observation_boundary: datetime,
    bundle: NativeDiscoveryMachineFactBundle | None,
    factual_failure: DiscoveryReason | None,
) -> DiscoveryMemberResult:
    if bundle is not None:
        return create_discovery_result(
            run_identity=run_identity,
            universe_member_identity=member.universe_member_identity,
            sponsor_label=member.sponsor_label,
            canonical_identity=member.canonical_identity,
            observation_boundary=observation_boundary,
            machine_fact_bundle_identity=bundle.bundle_identity,
            evaluability=FactualEvaluability.FACTUALLY_EVALUABLE,
            candidate_state=CandidateState.NOT_EVALUATED,
            reasons=(DiscoveryReason.FACTUAL_PATH_AVAILABLE,),
        )
    if factual_failure is not None:
        return create_discovery_result(
            run_identity=run_identity,
            universe_member_identity=member.universe_member_identity,
            sponsor_label=member.sponsor_label,
            canonical_identity=member.canonical_identity,
            observation_boundary=observation_boundary,
            machine_fact_bundle_identity=None,
            evaluability=FactualEvaluability.FACTUAL_FAILURE,
            candidate_state=CandidateState.NOT_EVALUATED_DUE_TO_FACTUAL_FAILURE,
            reasons=(factual_failure,),
        )
    return _scope_result(
        run_identity=run_identity,
        member=member,
        observation_boundary=observation_boundary,
    )


def _scope_accounting(
    reconciliation: ReconciliationPublication,
) -> DiscoveryRunAccounting:
    available = sum(
        item.dimensions.machine_fact_consumability is Availability.AVAILABLE
        for item in reconciliation.members
    )
    unavailable = sum(
        item.dimensions.machine_fact_consumability is Availability.UNAVAILABLE
        for item in reconciliation.members
    )
    other = len(reconciliation.members) - available - unavailable
    return DiscoveryRunAccounting(
        universe_members=len(reconciliation.members),
        factually_evaluable=available,
        prerequisite_unavailable=unavailable,
        evaluated=0,
        candidate_results=0,
        factual_failures=0,
        other_governed_unavailable=other,
    )


def _account_results(
    results: Iterable[DiscoveryMemberResult],
) -> DiscoveryRunAccounting:
    items = tuple(results)
    return DiscoveryRunAccounting(
        universe_members=len(items),
        factually_evaluable=sum(
            item.evaluability is FactualEvaluability.FACTUALLY_EVALUABLE
            for item in items
        ),
        prerequisite_unavailable=sum(
            item.evaluability is FactualEvaluability.PREREQUISITE_UNAVAILABLE
            for item in items
        ),
        evaluated=sum(
            item.candidate_state
            in {CandidateState.CANDIDATE_ADMITTED, CandidateState.CANDIDATE_NOT_ADMITTED}
            for item in items
        ),
        candidate_results=sum(
            item.candidate_state
            in {CandidateState.CANDIDATE_ADMITTED, CandidateState.CANDIDATE_NOT_ADMITTED}
            for item in items
        ),
        factual_failures=sum(
            item.evaluability is FactualEvaluability.FACTUAL_FAILURE
            for item in items
        ),
        other_governed_unavailable=sum(
            item.evaluability is FactualEvaluability.OTHER_GOVERNED_UNAVAILABLE
            for item in items
        ),
    )


def _validate_result_state(value: DiscoveryMemberResult) -> None:
    if value.evaluability is FactualEvaluability.PREREQUISITE_UNAVAILABLE:
        if (
            value.candidate_state
            is not CandidateState.NOT_EVALUATED_DUE_TO_PREREQUISITE
            or value.machine_fact_bundle_identity is not None
        ):
            raise DiscoveryError(DiscoveryFailure.INTEGRITY_INVALID)
    elif value.evaluability is FactualEvaluability.FACTUAL_FAILURE:
        if value.candidate_state is not CandidateState.NOT_EVALUATED_DUE_TO_FACTUAL_FAILURE:
            raise DiscoveryError(DiscoveryFailure.INTEGRITY_INVALID)
    elif value.candidate_state in {
        CandidateState.CANDIDATE_ADMITTED,
        CandidateState.CANDIDATE_NOT_ADMITTED,
    } and value.machine_fact_bundle_identity is None:
        raise DiscoveryError(DiscoveryFailure.MACHINE_FACT_BUNDLE_INCOMPLETE)


def _require_mandatory_bundle_evidence(
    bundle: NativeDiscoveryMachineFactBundle,
) -> None:
    if any(item.observed_at != bundle.observation_boundary for item in bundle.evidence):
        raise DiscoveryError(DiscoveryFailure.SOURCE_STALE)
    sessions = tuple(
        item
        for item in bundle.evidence
        if item.family is FactFamily.MARKET_SESSION_BOUNDARY
        and item.requirement is FactRequirement.MANDATORY
    )
    if len(sessions) != 1 or sessions[0].timeframe is not None:
        raise DiscoveryError(DiscoveryFailure.MARKET_SESSION_UNAVAILABLE)
    for family in (
        FactFamily.GOVERNED_COMPLETED_OHLCV,
        FactFamily.CANDLE_COMPLETENESS_RECONCILIATION,
    ):
        timeframes = tuple(
            item.timeframe
            for item in bundle.evidence
            if item.family is family
            and item.requirement is FactRequirement.MANDATORY
        )
        if len(timeframes) != len(STRUCTURAL_TIMEFRAMES) or set(timeframes) != set(
            STRUCTURAL_TIMEFRAMES
        ):
            raise DiscoveryError(DiscoveryFailure.MACHINE_FACT_BUNDLE_INCOMPLETE)


def _result_from_payload(item: dict[str, object]) -> DiscoveryMemberResult:
    return parse_discovery_result(_encode(item))


def _discovery_result_payload_from_values(values: dict[str, object]) -> dict[str, object]:
    return {
        "schema_identity": values["schema_identity"],
        "result_version": values["result_version"],
        "run_identity": values["run_identity"],
        "universe_member_identity": values["universe_member_identity"],
        "sponsor_label": values["sponsor_label"],
        "canonical_identity": values["canonical_identity"],
        "observation_boundary": values["observation_boundary"].isoformat(),
        "machine_fact_bundle_identity": values["machine_fact_bundle_identity"],
        "evaluability": values["evaluability"].value,
        "candidate_state": values["candidate_state"].value,
        "reasons": [item.value for item in values["reasons"]],
        "execution_eligibility": values["execution_eligibility"].value,
    }


def _run_identity_values(
    *,
    universe_identity: str,
    universe_version: str,
    reconciliation_identity: str,
    reconciliation_version: str,
    market_session_identity: str,
    market_session_boundary_identity: str,
    observation_boundary: datetime,
    accounting: DiscoveryRunAccounting,
    member_identities: tuple[str, ...],
) -> dict[str, object]:
    return {
        "contract_identity": NATIVE_DISCOVERY_CONTRACT,
        "contract_version": NATIVE_DISCOVERY_VERSION,
        "universe_identity": universe_identity,
        "universe_version": universe_version,
        "reconciliation_identity": reconciliation_identity,
        "reconciliation_version": reconciliation_version,
        "machine_fact_bundle_schema": NATIVE_DISCOVERY_MACHINE_FACT_BUNDLE,
        "market_session_identity": market_session_identity,
        "market_session_boundary_identity": market_session_boundary_identity,
        "observation_boundary": observation_boundary.isoformat(),
        "accounting": _accounting_payload(accounting),
        "member_identities": list(member_identities),
    }


def _discovery_run_payload_from_values(values: dict[str, object]) -> dict[str, object]:
    return {
        "contract_identity": values["contract_identity"],
        "contract_version": values["contract_version"],
        "universe_identity": values["universe_identity"],
        "universe_version": values["universe_version"],
        "universe_integrity_identity": values["universe_integrity_identity"],
        "reconciliation_identity": values["reconciliation_identity"],
        "reconciliation_version": values["reconciliation_version"],
        "reconciliation_integrity_identity": values[
            "reconciliation_integrity_identity"
        ],
        "machine_fact_bundle_schema": values["machine_fact_bundle_schema"],
        "market_session_identity": values["market_session_identity"],
        "market_session_boundary_identity": values[
            "market_session_boundary_identity"
        ],
        "observation_boundary": values["observation_boundary"].isoformat(),
        "accounting": _accounting_payload(values["accounting"]),
        "results": [discovery_result_payload(item) for item in values["results"]],
        "source_identities": list(values["source_identities"]),
        "provenance": list(values["provenance"]),
        "run_identity": values["run_identity"],
    }


def _machine_fact_bundle_payload_from_values(values: dict[str, object]) -> dict[str, object]:
    return {
        "schema_identity": values["schema_identity"],
        "bundle_version": values["bundle_version"],
        "canonical_identity": values["canonical_identity"],
        "universe_identity": values["universe_identity"],
        "universe_version": values["universe_version"],
        "reconciliation_identity": values["reconciliation_identity"],
        "reconciliation_version": values["reconciliation_version"],
        "market_session_identity": values["market_session_identity"],
        "market_session_boundary_identity": values[
            "market_session_boundary_identity"
        ],
        "observation_boundary": values["observation_boundary"].isoformat(),
        "evidence": [
            {
                "family": item.family.value,
                "requirement": item.requirement.value,
                "evidence_identity": item.evidence_identity,
                "fact_version": item.fact_version,
                "observed_at": item.observed_at.isoformat(),
                "timeframe": item.timeframe.value if item.timeframe else None,
                "completed_candle": item.completed_candle,
            }
            for item in values["evidence"]
        ],
        "source_identities": list(values["source_identities"]),
        "provenance": list(values["provenance"]),
    }


def _accounting_payload(value: DiscoveryRunAccounting) -> dict[str, int]:
    return {
        name: getattr(value, name)
        for name in DiscoveryRunAccounting.__dataclass_fields__
    }


def _identity(prefix: str, value: object) -> str:
    return f"{prefix}-{sha256(_encode(value)).hexdigest()}"


def _encode(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


def _version(value: object) -> bool:
    return (
        _text(value)
        and len(value.split(".")) == 3
        and all(part.isdigit() for part in value.split("."))
    )


def _unique_texts(values: object) -> bool:
    return (
        isinstance(values, tuple)
        and bool(values)
        and all(_text(item) for item in values)
        and len(set(values)) == len(values)
    )


__all__ = [
    "CandidateState",
    "DiscoveryError",
    "DiscoveryFailure",
    "DiscoveryMemberResult",
    "DiscoveryReason",
    "DiscoveryRunAccounting",
    "ExecutionEligibility",
    "FactFamily",
    "FactRequirement",
    "FactualEvaluability",
    "MACHINE_FACT_GAP_AUDIT",
    "MANDATORY_FACT_FAMILIES",
    "METHODOLOGY_STATUS",
    "MachineFactAuditStatus",
    "MachineFactEvidence",
    "MethodologyStatus",
    "NATIVE_DISCOVERY_CONTRACT",
    "NATIVE_DISCOVERY_MACHINE_FACT_BUNDLE",
    "NATIVE_DISCOVERY_REASON",
    "NATIVE_DISCOVERY_RESULT",
    "NATIVE_DISCOVERY_VERSION",
    "NativeDiscoveryMachineFactBundle",
    "NativeDiscoveryRun",
    "OPTIONAL_TELEMETRY_FACT_FAMILIES",
    "STRUCTURAL_TIMEFRAMES",
    "create_discovery_result",
    "create_discovery_runtime_run",
    "create_discovery_scope_run",
    "create_machine_fact_bundle",
    "discovery_result_bytes",
    "discovery_run_bytes",
    "machine_fact_bundle_payload",
    "machine_fact_bundle_bytes",
    "parse_machine_fact_bundle",
    "parse_discovery_result",
    "parse_discovery_run",
]
