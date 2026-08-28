"""WO-05 Intraday-owned Native Discovery runtime coordination.

The coordinator consumes exact governed publications and an injected factual
source.  It has no Provider authentication, candidate-admission, trading,
Risk, notification, monitoring, or Browser authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from typing import Protocol

from kronos.application.intraday_workstation import IntradayEvidenceBundle
from kronos.intraday.discovery import (
    DiscoveryError,
    DiscoveryFailure,
    DiscoveryReason,
    FactFamily,
    FactRequirement,
    MachineFactEvidence,
    NativeDiscoveryMachineFactBundle,
    NativeDiscoveryRun,
    create_discovery_runtime_run,
    create_machine_fact_bundle,
)
from kronos.intraday.discovery_persistence import NativeDiscoveryStore
from kronos.intraday.probables_refresh import DiscoveryProbablesFacts
from kronos.intraday.probables_v2_refresh import DiscoveryProbablesV2Facts
from kronos.intraday.reconciliation import (
    Availability,
    RECONCILIATION_IDENTITY,
    RECONCILIATION_VERSION,
    ReconciliationMember,
    ReconciliationPublication,
)
from kronos.intraday.universe import (
    INTRADAY_NATIVE_UNIVERSE_IDENTITY,
    INTRADAY_NATIVE_UNIVERSE_VERSION,
    IntradayUniversePublication,
)


DISCOVERY_RUNTIME_IDENTITY = "KRONOS-INTRADAY-NATIVE-DISCOVERY-RUNTIME-V0"
DISCOVERY_RUNTIME_VERSION = "0.1.0"


@dataclass(frozen=True, slots=True)
class DiscoveryRunBoundary:
    observation_boundary: datetime
    market_session_identity: str
    market_session_boundary_identity: str

    def __post_init__(self) -> None:
        if (
            not _aware(self.observation_boundary)
            or not _text(self.market_session_identity)
            or not _text(self.market_session_boundary_identity)
        ):
            raise DiscoveryError(DiscoveryFailure.OBSERVATION_BOUNDARY_INVALID)


@dataclass(frozen=True, slots=True)
class DiscoveryFactAcquisition:
    universe_member_identity: str
    canonical_identity: str
    bundle: NativeDiscoveryMachineFactBundle
    evidence: IntradayEvidenceBundle | None = None
    probables_facts: DiscoveryProbablesFacts | None = None
    probables_v2_facts: DiscoveryProbablesV2Facts | None = None

    def __post_init__(self) -> None:
        if (
            not _text(self.universe_member_identity)
            or not _text(self.canonical_identity)
            or type(self.bundle) is not NativeDiscoveryMachineFactBundle
            or self.bundle.canonical_identity != self.canonical_identity
            or (
                self.evidence is not None
                and (
                    type(self.evidence) is not IntradayEvidenceBundle
                    or self.evidence.canonical_instrument_id
                    != self.canonical_identity
                )
            )
            or (
                self.probables_facts is not None
                and (
                    type(self.probables_facts) is not DiscoveryProbablesFacts
                    or self.probables_facts.universe_member_identity
                    != self.universe_member_identity
                    or self.probables_facts.canonical_subject_identity
                    != self.canonical_identity
                    or self.probables_facts.discovery_bundle_identity
                    != self.bundle.bundle_identity
                    or self.probables_facts.observation_boundary
                    != self.bundle.observation_boundary
                )
            )
            or (
                self.probables_v2_facts is not None
                and (
                    type(self.probables_v2_facts) is not DiscoveryProbablesV2Facts
                    or self.probables_v2_facts.universe_member_identity
                    != self.universe_member_identity
                    or self.probables_v2_facts.canonical_subject_identity
                    != self.canonical_identity
                    or self.probables_v2_facts.discovery_bundle_identity
                    != self.bundle.bundle_identity
                    or self.probables_v2_facts.observation_boundary
                    != self.bundle.observation_boundary
                )
            )
        ):
            raise DiscoveryError(DiscoveryFailure.INTEGRITY_INVALID)


class DiscoveryFactualSource(Protocol):
    def acquire(
        self,
        *,
        member: ReconciliationMember,
        boundary: DiscoveryRunBoundary,
    ) -> DiscoveryFactAcquisition:
        """Return one completed governed factual bundle for one member."""


class DiscoveryMemberFactError(RuntimeError):
    """Bounded per-member factual failure; arbitrary exception text is excluded."""

    def __init__(self, reason: DiscoveryReason) -> None:
        if reason not in {
            DiscoveryReason.MARKET_SESSION_UNAVAILABLE,
            DiscoveryReason.MACHINE_FACT_BUNDLE_INCOMPLETE,
            DiscoveryReason.INCOMPLETE_CANDLE_NOT_AUTHORIZED,
            DiscoveryReason.SOURCE_STALE,
            DiscoveryReason.ACTIVE_DERIVATIVE_BINDING_UNAVAILABLE,
            DiscoveryReason.ACTIVE_DERIVATIVE_BINDING_AMBIGUOUS,
            DiscoveryReason.CANONICAL_DERIVATIVE_CONTRACT_UNAVAILABLE,
            DiscoveryReason.PROVIDER_CONTRACT_UNAVAILABLE,
        }:
            raise ValueError("DISCOVERY_MEMBER_FAILURE_REASON_INVALID")
        self.reason = reason
        super().__init__(reason.value)


@dataclass(frozen=True, slots=True)
class DiscoveryRuntimeExecution:
    run: NativeDiscoveryRun
    bundles: tuple[NativeDiscoveryMachineFactBundle, ...]
    evidence: tuple[tuple[str, IntradayEvidenceBundle], ...]
    probables_facts: tuple[DiscoveryProbablesFacts, ...]
    pre_evaluable_count: int
    prerequisite_unavailable_count: int
    timeframe_fact_requests: int
    source_operation_count: int
    probables_v2_facts: tuple[DiscoveryProbablesV2Facts, ...] = ()
    runtime_identity: str = DISCOVERY_RUNTIME_IDENTITY
    runtime_version: str = DISCOVERY_RUNTIME_VERSION

    def __post_init__(self) -> None:
        bundle_ids = tuple(item.bundle_identity for item in self.bundles)
        evidence_ids = tuple(item[0] for item in self.evidence)
        probables_ids = tuple(
            item.universe_member_identity for item in self.probables_facts
        )
        probables_v2_ids = tuple(
            item.universe_member_identity for item in self.probables_v2_facts
        )
        if (
            type(self.run) is not NativeDiscoveryRun
            or any(type(item) is not NativeDiscoveryMachineFactBundle for item in self.bundles)
            or len(set(bundle_ids)) != len(bundle_ids)
            or any(
                not _text(member_id) or type(value) is not IntradayEvidenceBundle
                for member_id, value in self.evidence
            )
            or len(set(evidence_ids)) != len(evidence_ids)
            or any(
                type(item) is not DiscoveryProbablesFacts
                or item.observation_boundary != self.run.observation_boundary
                for item in self.probables_facts
            )
            or len(set(probables_ids)) != len(probables_ids)
            or any(
                type(item) is not DiscoveryProbablesV2Facts
                or item.observation_boundary != self.run.observation_boundary
                for item in self.probables_v2_facts
            )
            or len(set(probables_v2_ids)) != len(probables_v2_ids)
            or any(
                type(value) is not int or value < 0
                for value in (
                    self.pre_evaluable_count,
                    self.prerequisite_unavailable_count,
                    self.timeframe_fact_requests,
                    self.source_operation_count,
                )
            )
            or self.pre_evaluable_count
            != self.run.accounting.factually_evaluable
            + self.run.accounting.factual_failures
            or self.prerequisite_unavailable_count
            != self.run.accounting.prerequisite_unavailable
            or self.runtime_identity != DISCOVERY_RUNTIME_IDENTITY
            or self.runtime_version != DISCOVERY_RUNTIME_VERSION
        ):
            raise DiscoveryError(DiscoveryFailure.INTEGRITY_INVALID)


class IntradayNativeDiscoveryService:
    """Execute one deterministic, operation-minimized, universe-driven run."""

    def __init__(
        self,
        *,
        universe: IntradayUniversePublication,
        reconciliation: ReconciliationPublication,
        factual_source: DiscoveryFactualSource,
        store: NativeDiscoveryStore,
        runtime_evaluable_member_ids: tuple[str, ...] = (),
        additional_source_identities: tuple[str, ...] = (),
    ) -> None:
        if (
            type(universe) is not IntradayUniversePublication
            or type(reconciliation) is not ReconciliationPublication
            or not callable(getattr(factual_source, "acquire", None))
            or type(store) is not NativeDiscoveryStore
            or type(runtime_evaluable_member_ids) is not tuple
            or len(set(runtime_evaluable_member_ids))
            != len(runtime_evaluable_member_ids)
            or type(additional_source_identities) is not tuple
            or len(set(additional_source_identities))
            != len(additional_source_identities)
        ):
            raise DiscoveryError(DiscoveryFailure.INTEGRITY_INVALID)
        if (
            universe.publication_identity != INTRADAY_NATIVE_UNIVERSE_IDENTITY
            or universe.publication_version != INTRADAY_NATIVE_UNIVERSE_VERSION
            or reconciliation.publication_identity != RECONCILIATION_IDENTITY
            or reconciliation.publication_version != RECONCILIATION_VERSION
            or reconciliation.universe_identity != universe.publication_identity
            or reconciliation.universe_version != universe.publication_version
            or reconciliation.universe_integrity_identity
            != universe.integrity_identity
            or tuple(item.sponsor_label for item in reconciliation.members)
            != tuple(item.sponsor_label for item in universe.members)
        ):
            raise DiscoveryError(DiscoveryFailure.PUBLICATION_STALE)
        self._universe = universe
        self._reconciliation = reconciliation
        self._source = factual_source
        self._store = store
        member_ids = {
            item.universe_member_identity for item in reconciliation.members
        }
        if (
            any(not _text(item) for item in runtime_evaluable_member_ids)
            or not set(runtime_evaluable_member_ids).issubset(member_ids)
            or any(not _text(item) for item in additional_source_identities)
        ):
            raise DiscoveryError(DiscoveryFailure.INTEGRITY_INVALID)
        self._runtime_evaluable_member_ids = runtime_evaluable_member_ids
        self._additional_source_identities = additional_source_identities

    def execute(self, boundary: DiscoveryRunBoundary) -> DiscoveryRuntimeExecution:
        if type(boundary) is not DiscoveryRunBoundary:
            raise DiscoveryError(DiscoveryFailure.OBSERVATION_BOUNDARY_INVALID)
        try:
            self._universe.require_current(boundary.observation_boundary)
        except Exception as error:
            raise DiscoveryError(DiscoveryFailure.PUBLICATION_STALE) from error

        bundles: dict[str, NativeDiscoveryMachineFactBundle] = {}
        failures: dict[str, DiscoveryReason] = {}
        evidence: list[tuple[str, IntradayEvidenceBundle]] = []
        probables_facts: list[DiscoveryProbablesFacts] = []
        probables_v2_facts: list[DiscoveryProbablesV2Facts] = []
        source_operations = 0
        for member in self._reconciliation.members:
            if (
                member.dimensions.machine_fact_consumability is not Availability.AVAILABLE
                and member.universe_member_identity
                not in self._runtime_evaluable_member_ids
            ):
                continue
            source_operations += 1
            try:
                acquired = self._source.acquire(member=member, boundary=boundary)
                if (
                    type(acquired) is not DiscoveryFactAcquisition
                    or acquired.universe_member_identity
                    != member.universe_member_identity
                    or acquired.canonical_identity != member.canonical_identity
                    or acquired.bundle.observation_boundary
                    != boundary.observation_boundary
                ):
                    raise DiscoveryMemberFactError(
                        DiscoveryReason.MACHINE_FACT_BUNDLE_INCOMPLETE
                    )
                bundles[member.universe_member_identity] = acquired.bundle
                if acquired.evidence is not None:
                    evidence.append((member.universe_member_identity, acquired.evidence))
                if acquired.probables_facts is not None:
                    probables_facts.append(acquired.probables_facts)
                if acquired.probables_v2_facts is not None:
                    probables_v2_facts.append(acquired.probables_v2_facts)
            except DiscoveryMemberFactError as error:
                failures[member.universe_member_identity] = error.reason
            except DiscoveryError as error:
                failures[member.universe_member_identity] = _reason_for_failure(
                    error.failure
                )
            except Exception:
                failures[member.universe_member_identity] = (
                    DiscoveryReason.MACHINE_FACT_BUNDLE_INCOMPLETE
                )

        run = create_discovery_runtime_run(
            reconciliation=self._reconciliation,
            expected_universe_identity=self._universe.publication_identity,
            expected_universe_version=self._universe.publication_version,
            expected_reconciliation_identity=self._reconciliation.publication_identity,
            expected_reconciliation_version=self._reconciliation.publication_version,
            market_session_identity=boundary.market_session_identity,
            market_session_boundary_identity=boundary.market_session_boundary_identity,
            observation_boundary=boundary.observation_boundary,
            machine_fact_bundles=bundles,
            factual_failures=failures,
            runtime_evaluable_member_ids=self._runtime_evaluable_member_ids,
            additional_source_identities=self._additional_source_identities,
        )
        retained = tuple(
            sorted(bundles.values(), key=lambda item: item.canonical_identity)
        )
        self._store.retain_run(run, bundles=retained)
        return DiscoveryRuntimeExecution(
            run=run,
            bundles=retained,
            evidence=tuple(sorted(evidence, key=lambda item: item[0])),
            probables_facts=tuple(sorted(
                probables_facts,
                key=lambda item: item.universe_member_identity,
            )),
            probables_v2_facts=tuple(sorted(
                probables_v2_facts,
                key=lambda item: item.universe_member_identity,
            )),
            pre_evaluable_count=len(bundles) + len(failures),
            prerequisite_unavailable_count=run.accounting.prerequisite_unavailable,
            timeframe_fact_requests=(len(bundles) + len(failures)) * 4,
            source_operation_count=source_operations,
        )


def assemble_machine_fact_bundle(
    *,
    member: ReconciliationMember,
    boundary: DiscoveryRunBoundary,
    evidence: IntradayEvidenceBundle,
    universe_identity: str,
    universe_version: str,
    reconciliation_identity: str,
    reconciliation_version: str,
) -> NativeDiscoveryMachineFactBundle:
    """Adapt existing Slice 1-3 factual evidence into the WO-03 bundle."""

    if (
        type(member) is not ReconciliationMember
        or type(boundary) is not DiscoveryRunBoundary
        or type(evidence) is not IntradayEvidenceBundle
        or evidence.canonical_instrument_id != member.canonical_identity
        or evidence.composition.run.observation_boundary.observed_at
        != boundary.observation_boundary
    ):
        raise DiscoveryMemberFactError(
            DiscoveryReason.MACHINE_FACT_BUNDLE_INCOMPLETE
        )
    composition = evidence.composition
    schedule = composition.market_session.schedule
    if schedule is None:
        raise DiscoveryMemberFactError(DiscoveryReason.MARKET_SESSION_UNAVAILABLE)
    facts: list[MachineFactEvidence] = [
        MachineFactEvidence(
            family=FactFamily.MARKET_SESSION_BOUNDARY,
            requirement=FactRequirement.MANDATORY,
            evidence_identity=_session_evidence_identity(
                schedule.session_id, boundary.observation_boundary
            ),
            fact_version=schedule.source_version,
            observed_at=boundary.observation_boundary,
            timeframe=None,
            completed_candle=None,
        )
    ]
    for item in composition.evidence:
        reconciliation = item.reconciliation
        if not reconciliation.structural_candles:
            raise DiscoveryMemberFactError(
                DiscoveryReason.MACHINE_FACT_BUNDLE_INCOMPLETE
            )
        facts.extend((
            MachineFactEvidence(
                family=FactFamily.GOVERNED_COMPLETED_OHLCV,
                requirement=FactRequirement.MANDATORY,
                evidence_identity=item.evidence_id,
                fact_version="1.0.0",
                observed_at=boundary.observation_boundary,
                timeframe=reconciliation.timeframe,
                completed_candle=True,
            ),
            MachineFactEvidence(
                family=FactFamily.CANDLE_COMPLETENESS_RECONCILIATION,
                requirement=FactRequirement.MANDATORY,
                evidence_identity=item.evidence_id,
                fact_version="1.0.0",
                observed_at=boundary.observation_boundary,
                timeframe=reconciliation.timeframe,
                completed_candle=True,
            ),
        ))
    if evidence.slice1e_context is not None:
        for family in (
            FactFamily.PREVIOUS_SESSION_HLC_PDH_PDL,
            FactFamily.CLASSIC_PIVOTS_CPR,
        ):
            facts.append(MachineFactEvidence(
                family=family,
                requirement=FactRequirement.OPTIONAL_TELEMETRY,
                evidence_identity=evidence.slice1e_context.evidence_id,
                fact_version="1.0.0",
                observed_at=boundary.observation_boundary,
                timeframe=None,
                completed_candle=None,
            ))
    for item in evidence.structural_evidence:
        facts.append(MachineFactEvidence(
            family=FactFamily.STRUCTURAL_COMPARISONS,
            requirement=FactRequirement.OPTIONAL_TELEMETRY,
            evidence_identity=item.evidence_id,
            fact_version="1.0.0",
            observed_at=boundary.observation_boundary,
            timeframe=item.timeframe,
            completed_candle=True,
        ))
    for item in evidence.shadow_telemetry:
        facts.append(MachineFactEvidence(
            family=FactFamily.VOLUME_OBSERVATIONS,
            requirement=FactRequirement.OPTIONAL_TELEMETRY,
            evidence_identity=item.evidence_id,
            fact_version="1.0.0",
            observed_at=boundary.observation_boundary,
            timeframe=item.timeframe,
            completed_candle=True,
        ))
    sources = tuple(sorted({
        item.reconciliation.provenance.source_identity
        for item in composition.evidence
    }))
    provenance = tuple(sorted({
        item.reconciliation.provenance.provider
        for item in composition.evidence
    } | {"KRONOS-INTRADAY-WO-05"}))
    return create_machine_fact_bundle(
        canonical_identity=member.canonical_identity,
        universe_identity=universe_identity,
        universe_version=universe_version,
        reconciliation_identity=reconciliation_identity,
        reconciliation_version=reconciliation_version,
        market_session_identity=boundary.market_session_identity,
        market_session_boundary_identity=boundary.market_session_boundary_identity,
        observation_boundary=boundary.observation_boundary,
        evidence=tuple(facts),
        source_identities=sources,
        provenance=provenance,
    )


def _reason_for_failure(failure: DiscoveryFailure) -> DiscoveryReason:
    return {
        DiscoveryFailure.MARKET_SESSION_UNAVAILABLE:
            DiscoveryReason.MARKET_SESSION_UNAVAILABLE,
        DiscoveryFailure.INCOMPLETE_CANDLE_NOT_AUTHORIZED:
            DiscoveryReason.INCOMPLETE_CANDLE_NOT_AUTHORIZED,
        DiscoveryFailure.SOURCE_STALE: DiscoveryReason.SOURCE_STALE,
    }.get(failure, DiscoveryReason.MACHINE_FACT_BUNDLE_INCOMPLETE)


def _session_evidence_identity(session_id: str, observed_at: datetime) -> str:
    payload = json.dumps(
        {"session_id": session_id, "observed_at": observed_at.isoformat()},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return f"INTRADAY-DISCOVERY-SESSION-{sha256(payload).hexdigest()}"


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


__all__ = [
    "DISCOVERY_RUNTIME_IDENTITY",
    "DISCOVERY_RUNTIME_VERSION",
    "DiscoveryFactAcquisition",
    "DiscoveryFactualSource",
    "DiscoveryMemberFactError",
    "DiscoveryRunBoundary",
    "DiscoveryRuntimeExecution",
    "IntradayNativeDiscoveryService",
    "assemble_machine_fact_bundle",
]
