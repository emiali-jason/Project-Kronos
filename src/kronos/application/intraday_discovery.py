"""Intraday-owned application projection for Native Discovery V0."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from kronos.application.intraday_workstation import IntradayEvidenceBundle
from kronos.application.intraday_probables import (
    IntradayProbablesApplication,
    IntradayProbablesSnapshot,
)
from kronos.intraday.discovery import (
    CandidateState,
    DiscoveryError,
    DiscoveryReason,
    FactualEvaluability,
    NativeDiscoveryMachineFactBundle,
    NativeDiscoveryRun,
)
from kronos.intraday.discovery_persistence import NativeDiscoveryStore
from kronos.intraday.discovery_runtime import (
    DiscoveryRunBoundary,
    DiscoveryRuntimeExecution,
    IntradayNativeDiscoveryService,
)
from kronos.intraday.probables import ProbableMemberResult
from kronos.intraday.reconciliation import (
    Availability,
    ReconciliationMember,
    ReconciliationPublication,
    ReconciliationState,
)
from kronos.intraday.universe import IntradayUniversePublication
from kronos.instrument.active_derivative import ActiveDerivativeBindingArtifact
from kronos.instrument.active_derivative_persistence import (
    ActiveDerivativeBindingStore,
)


DISCOVERY_APPLICATION_IDENTITY = "KRONOS-INTRADAY-DISCOVERY-APPLICATION-V0"
DISCOVERY_APPLICATION_VERSION = "0.1.0"
DISCOVERY_OPERATIONAL_INVOCATION_SEAM_REQUIRED = (
    "DISCOVERY_OPERATIONAL_INVOCATION_SEAM_REQUIRED"
)


@dataclass(frozen=True, slots=True)
class IntradayDiscoveryMemberSnapshot:
    sponsor_label: str
    canonical_identity: str
    market_family: str
    prerequisite_ready: bool
    machine_facts_available: bool
    evaluability: FactualEvaluability
    candidate_state: CandidateState
    reasons: tuple[DiscoveryReason, ...]
    observation_boundary: datetime | None
    machine_fact_bundle: NativeDiscoveryMachineFactBundle | None
    evidence: IntradayEvidenceBundle | None
    probable_result: ProbableMemberResult | None = None
    analysis_contract: str | None = None
    contract_expiry: str | None = None
    active_binding_identity: str | None = None

    def __post_init__(self) -> None:
        if (
            not _text(self.sponsor_label)
            or not _text(self.canonical_identity)
            or not _text(self.market_family)
            or type(self.prerequisite_ready) is not bool
            or type(self.machine_facts_available) is not bool
            or type(self.evaluability) is not FactualEvaluability
            or type(self.candidate_state) is not CandidateState
            or not self.reasons
            or any(type(item) is not DiscoveryReason for item in self.reasons)
            or (self.observation_boundary is not None and not _aware(self.observation_boundary))
            or (
                self.machine_fact_bundle is not None
                and type(self.machine_fact_bundle) is not NativeDiscoveryMachineFactBundle
            )
            or (self.evidence is not None and type(self.evidence) is not IntradayEvidenceBundle)
            or self.machine_facts_available != (self.machine_fact_bundle is not None)
            or (self.evidence is not None and not self.machine_facts_available)
            or (
                self.probable_result is not None
                and type(self.probable_result) is not ProbableMemberResult
            )
            or any(
                value is not None and not _text(value)
                for value in (
                    self.analysis_contract,
                    self.contract_expiry,
                    self.active_binding_identity,
                )
            )
            or (
                self.analysis_contract is None
                and any(value is not None for value in (
                    self.contract_expiry,
                    self.active_binding_identity,
                ))
            )
        ):
            raise ValueError("INTRADAY_DISCOVERY_MEMBER_SNAPSHOT_INVALID")


@dataclass(frozen=True, slots=True)
class IntradayDiscoverySnapshot:
    system_status: str
    current_failure: str | None
    last_successful_run_identity: str | None
    last_successful_analysis: datetime | None
    universe_count: int
    pre_evaluable_count: int
    prerequisite_unavailable_count: int
    machine_fact_success_count: int
    machine_fact_failure_count: int
    candidate_admitted_count: int
    candidate_not_admitted_count: int
    methodology_deferred_count: int
    members: tuple[IntradayDiscoveryMemberSnapshot, ...]
    selected_member: IntradayDiscoveryMemberSnapshot | None
    universe_identity: str
    universe_version: str
    reconciliation_identity: str
    reconciliation_version: str
    probables: IntradayProbablesSnapshot | None = None
    application_identity: str = DISCOVERY_APPLICATION_IDENTITY
    application_version: str = DISCOVERY_APPLICATION_VERSION

    def __post_init__(self) -> None:
        labels = tuple(item.sponsor_label for item in self.members)
        if (
            not _text(self.system_status)
            or (self.current_failure is not None and not _text(self.current_failure))
            or (
                self.last_successful_run_identity is not None
                and not _text(self.last_successful_run_identity)
            )
            or (
                self.last_successful_analysis is not None
                and not _aware(self.last_successful_analysis)
            )
            or any(
                type(value) is not int or value < 0
                for value in (
                    self.universe_count,
                    self.pre_evaluable_count,
                    self.prerequisite_unavailable_count,
                    self.machine_fact_success_count,
                    self.machine_fact_failure_count,
                    self.candidate_admitted_count,
                    self.candidate_not_admitted_count,
                    self.methodology_deferred_count,
                )
            )
            or len(self.members) != self.universe_count
            or any(type(item) is not IntradayDiscoveryMemberSnapshot for item in self.members)
            or len(set(labels)) != len(labels)
            or (
                self.selected_member is not None
                and self.selected_member.sponsor_label not in set(labels)
            )
            or not all(_text(item) for item in (
                self.universe_identity,
                self.universe_version,
                self.reconciliation_identity,
                self.reconciliation_version,
            ))
            or (
                self.probables is not None
                and type(self.probables) is not IntradayProbablesSnapshot
            )
            or self.application_identity != DISCOVERY_APPLICATION_IDENTITY
            or self.application_version != DISCOVERY_APPLICATION_VERSION
        ):
            raise ValueError("INTRADAY_DISCOVERY_SNAPSHOT_INVALID")


class IntradayDiscoveryApplication:
    """Hold the last successful governed run separately from current failure."""

    def __init__(
        self,
        *,
        universe: IntradayUniversePublication,
        reconciliation: ReconciliationPublication,
        store: NativeDiscoveryStore,
        service: IntradayNativeDiscoveryService | None = None,
        probables: IntradayProbablesApplication | None = None,
        active_derivative_binding_store: ActiveDerivativeBindingStore | None = None,
        last_successful_run_identity: str | None = None,
    ) -> None:
        if (
            type(universe) is not IntradayUniversePublication
            or type(reconciliation) is not ReconciliationPublication
            or type(store) is not NativeDiscoveryStore
            or (
                service is not None
                and type(service) is not IntradayNativeDiscoveryService
            )
            or (
                probables is not None
                and type(probables) is not IntradayProbablesApplication
            )
            or (
                active_derivative_binding_store is not None
                and type(active_derivative_binding_store)
                is not ActiveDerivativeBindingStore
            )
        ):
            raise ValueError("INTRADAY_DISCOVERY_APPLICATION_INVALID")
        if (
            reconciliation.universe_identity != universe.publication_identity
            or reconciliation.universe_version != universe.publication_version
            or reconciliation.universe_integrity_identity != universe.integrity_identity
        ):
            raise ValueError("INTRADAY_DISCOVERY_PUBLICATION_MISMATCH")
        self._universe = universe
        self._reconciliation = reconciliation
        self._store = store
        self._service = service
        self._probables = probables
        self._active_derivative_binding_store = active_derivative_binding_store
        self._run: NativeDiscoveryRun | None = None
        self._bundles: dict[str, NativeDiscoveryMachineFactBundle] = {}
        self._evidence: dict[str, IntradayEvidenceBundle] = {}
        self._active_bindings: dict[str, ActiveDerivativeBindingArtifact] = {}
        self._current_failure: str | None = None
        if last_successful_run_identity is not None:
            self._restore(last_successful_run_identity)

    @property
    def operational_invocation_available(self) -> bool:
        return self._service is not None

    def run_discovery(self, boundary: DiscoveryRunBoundary) -> NativeDiscoveryRun:
        if self._service is None:
            self._current_failure = DISCOVERY_OPERATIONAL_INVOCATION_SEAM_REQUIRED
            raise RuntimeError(DISCOVERY_OPERATIONAL_INVOCATION_SEAM_REQUIRED)
        try:
            execution = self._service.execute(boundary)
        except DiscoveryError as error:
            self._current_failure = error.failure.value
            raise
        except Exception as error:
            self._current_failure = "DISCOVERY_OPERATION_FAILED"
            raise RuntimeError("DISCOVERY_OPERATION_FAILED") from error
        self._accept_execution(execution)
        self._current_failure = None
        return execution.run

    def record_failure(self, bounded_failure: str) -> None:
        if not _text(bounded_failure) or not bounded_failure.replace("_", "").isalnum():
            raise ValueError("INTRADAY_DISCOVERY_FAILURE_INVALID")
        self._current_failure = bounded_failure

    def accept_completed_execution(
        self,
        execution: DiscoveryRuntimeExecution,
    ) -> None:
        """Project one already-persisted governed execution into application state."""

        if type(execution) is not DiscoveryRuntimeExecution:
            raise ValueError("INTRADAY_DISCOVERY_EXECUTION_INVALID")
        retained = self._store.load_run(run_identity=execution.run.run_identity)
        if retained != execution.run:
            raise ValueError("INTRADAY_DISCOVERY_PERSISTED_RUN_MISMATCH")
        self._accept_execution(execution)
        self._current_failure = None

    def snapshot(
        self, selected_canonical_instrument_id: str | None = None
    ) -> IntradayDiscoverySnapshot:
        members = self._member_snapshots()
        selected = None
        if selected_canonical_instrument_id:
            selected = next((
                item for item in members
                if item.canonical_identity == selected_canonical_instrument_id
                or item.sponsor_label == selected_canonical_instrument_id
            ), None)
        return IntradayDiscoverySnapshot(
            system_status=(
                "NO_SUCCESSFUL_DISCOVERY_RUN_AVAILABLE"
                if self._run is None
                else "LAST_SUCCESSFUL_DISCOVERY_RUN_AVAILABLE"
            ),
            current_failure=self._current_failure,
            last_successful_run_identity=None if self._run is None else self._run.run_identity,
            last_successful_analysis=None if self._run is None else self._run.observation_boundary,
            universe_count=len(members),
            pre_evaluable_count=sum(item.prerequisite_ready for item in members),
            prerequisite_unavailable_count=sum(not item.prerequisite_ready for item in members),
            machine_fact_success_count=sum(item.machine_facts_available for item in members),
            machine_fact_failure_count=sum(
                item.evaluability is FactualEvaluability.FACTUAL_FAILURE for item in members
            ),
            candidate_admitted_count=sum(
                item.candidate_state is CandidateState.CANDIDATE_ADMITTED for item in members
            ),
            candidate_not_admitted_count=sum(
                item.candidate_state is CandidateState.CANDIDATE_NOT_ADMITTED for item in members
            ),
            methodology_deferred_count=sum(
                item.machine_facts_available
                and item.candidate_state is CandidateState.NOT_EVALUATED
                for item in members
            ),
            members=members,
            selected_member=selected,
            universe_identity=self._universe.publication_identity,
            universe_version=self._universe.publication_version,
            reconciliation_identity=self._reconciliation.publication_identity,
            reconciliation_version=self._reconciliation.publication_version,
            probables=None if self._probables is None else self._probables.snapshot(),
        )

    def _accept_execution(self, execution: DiscoveryRuntimeExecution) -> None:
        self._run = execution.run
        self._bundles = {item.bundle_identity: item for item in execution.bundles}
        self._evidence = dict(execution.evidence)
        self._load_active_bindings(execution.run)

    def _restore(self, run_identity: str) -> None:
        run = self._store.load_run(run_identity=run_identity)
        if (
            run.universe_identity != self._universe.publication_identity
            or run.universe_version != self._universe.publication_version
            or run.reconciliation_identity != self._reconciliation.publication_identity
            or run.reconciliation_version != self._reconciliation.publication_version
        ):
            raise ValueError("INTRADAY_DISCOVERY_PERSISTED_RUN_STALE")
        bundles = {
            identity: self._store.load_bundle(bundle_identity=identity)
            for identity in (
                item.machine_fact_bundle_identity
                for item in run.results
                if item.machine_fact_bundle_identity is not None
            )
        }
        self._run = run
        self._bundles = bundles
        self._load_active_bindings(run)

    def _load_active_bindings(self, run: NativeDiscoveryRun) -> None:
        self._active_bindings = {}
        if self._active_derivative_binding_store is None:
            return
        for identity in run.source_identities:
            if not identity.startswith("ACTIVE-DERIVATIVE-BINDING-"):
                continue
            binding = self._active_derivative_binding_store.load(
                binding_identity=identity
            )
            self._active_bindings[binding.canonical_subject_id] = binding

    def _member_snapshots(self) -> tuple[IntradayDiscoveryMemberSnapshot, ...]:
        results = {} if self._run is None else {
            item.universe_member_identity: item for item in self._run.results
        }
        probable_results = (
            {}
            if self._probables is None
            else {
                item.universe_member_identity: item
                for item in self._probables.snapshot().results
            }
        )
        items: list[IntradayDiscoveryMemberSnapshot] = []
        for member in self._reconciliation.members:
            result = results.get(member.universe_member_identity)
            prerequisite_ready = (
                member.dimensions.machine_fact_consumability is Availability.AVAILABLE
                or (
                    result is not None
                    and result.evaluability
                    is not FactualEvaluability.PREREQUISITE_UNAVAILABLE
                )
            )
            active_binding = self._active_bindings.get(member.canonical_identity)
            if result is None:
                evaluability = (
                    FactualEvaluability.FACTUALLY_EVALUABLE
                    if prerequisite_ready
                    else FactualEvaluability.PREREQUISITE_UNAVAILABLE
                )
                candidate_state = (
                    CandidateState.NOT_EVALUATED
                    if prerequisite_ready
                    else CandidateState.NOT_EVALUATED_DUE_TO_PREREQUISITE
                )
                reasons = (
                    (DiscoveryReason.FACTUAL_PATH_AVAILABLE,)
                    if prerequisite_ready
                    else (_prerequisite_reason(member),)
                )
                bundle = None
                observed_at = None
            else:
                evaluability = result.evaluability
                candidate_state = result.candidate_state
                reasons = result.reasons
                bundle = (
                    None
                    if result.machine_fact_bundle_identity is None
                    else self._bundles[result.machine_fact_bundle_identity]
                )
                observed_at = result.observation_boundary
            items.append(IntradayDiscoveryMemberSnapshot(
                sponsor_label=member.sponsor_label,
                canonical_identity=member.canonical_identity,
                market_family=member.market_family.value,
                prerequisite_ready=prerequisite_ready,
                machine_facts_available=bundle is not None,
                evaluability=evaluability,
                candidate_state=candidate_state,
                reasons=reasons,
                observation_boundary=observed_at,
                machine_fact_bundle=bundle,
                evidence=self._evidence.get(member.universe_member_identity),
                probable_result=probable_results.get(member.universe_member_identity),
                analysis_contract=(
                    None if active_binding is None else active_binding.provider_symbol
                ),
                contract_expiry=(
                    None
                    if active_binding is None
                    else active_binding.contract_expiry.isoformat()
                ),
                active_binding_identity=(
                    None
                    if active_binding is None
                    else active_binding.binding_identity
                ),
            ))
        return tuple(sorted(items, key=lambda item: (item.canonical_identity, item.sponsor_label)))


def _prerequisite_reason(member: ReconciliationMember) -> DiscoveryReason:
    if member.state is ReconciliationState.ACTIVE_CONTRACT_BINDING_UNAVAILABLE:
        return DiscoveryReason.ACTIVE_DERIVATIVE_BINDING_UNAVAILABLE
    if member.state is ReconciliationState.PROVIDER_CONTRACT_UNAVAILABLE:
        return DiscoveryReason.PROVIDER_CONTRACT_UNAVAILABLE
    return DiscoveryReason.MACHINE_FACT_BUNDLE_INCOMPLETE


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


__all__ = [
    "DISCOVERY_APPLICATION_IDENTITY",
    "DISCOVERY_APPLICATION_VERSION",
    "DISCOVERY_OPERATIONAL_INVOCATION_SEAM_REQUIRED",
    "IntradayDiscoveryApplication",
    "IntradayDiscoveryMemberSnapshot",
    "IntradayDiscoverySnapshot",
]
