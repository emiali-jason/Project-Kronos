"""Sole governed CAR-018 live launcher; direct import remains inert."""

from __future__ import annotations

import os
import pwd
import re
import socket
import stat
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from importlib.metadata import version
from pathlib import Path

from kronos.configuration.loader import (
    load_governed_provider_authentication_configuration,
)
from kronos.configuration.settings import GovernedProviderAuthenticationConfiguration
from kronos.provider.kite.composition import (
    OperationLedgerRecorder,
    compose_kite_authentication,
)
from kronos.provider.kite.live_activation import (
    ActivationReview,
    ActivationProvenanceKind,
    CanonicalRepositoryEvidence,
    CoordinatedActivationValues,
    DurableConsumptionCoordinator,
    DurableConsumptionResult,
    TrustedActivationReviewer,
    consumption_filename,
)
from kronos.provider.models.authentication import (
    ConsumptionOutcomeCategory,
    CoordinatedConsumptionState,
    GovernedAuthenticationOperation,
)
if __package__:
    from tools.provider_pilots import car016_provider_authentication_gui
else:
    import car016_provider_authentication_gui


EXPECTED_PYTHON = (3, 13, 14)
EXPECTED_TKINTER = "9.0"
EXPECTED_KITE_SDK = "5.2.0"
_ACTIVATION_IDENTITY = "KRONOS-COORD-AUTH-20260804-002"
_CAR016_LOGICAL_REFERENCE = (
    "CAR-016-V1.2-CA1-KRONOS-COORD-AUTH-20260804-002"
)
_CAR017_LOGICAL_REFERENCE = (
    "CAR-017-V1.2-CA1-KRONOS-COORD-AUTH-20260804-002"
)
_FROZEN_CAR016_SHA = "bb5aa16fbc4fda2609376d53161d591fb0fe0d36"
_FROZEN_CAR017_SHA = "8f052d0cc3b7abc63a28c2951a3b4770c58b4454"
_FROZEN_CAR018_SHA = "6273663a8ca8729833a8a0f05e06d55973ce6dc0"
_COORDINATED_GOVERNANCE_PUBLICATION_SHA = (
    "cdaeaf1669e7182f36f9ea753315cf7992843d78"
)
_CAR018_OPERATIONAL_CORRECTION_SHA = (
    "218b01fa7ed7815f3b7fefb127e278dc3909481b"
)
_EFFECTIVE_AT = datetime(
    2026, 8, 6, 9, 0, tzinfo=timezone(timedelta(hours=5, minutes=30))
)
_EXPIRES_AT = datetime(
    2026, 8, 13, 9, 0, tzinfo=timezone(timedelta(hours=5, minutes=30))
)
_SPONSOR_ENVIRONMENT = "SPONSOR-MACOS-LOCAL-NONPROD-01"
_APPROVED_HOSTNAME = "Imrans-Mac-mini.local"
_GOVERNANCE_PATHS = (
    "docs/governance/reviews/"
    "CAR-016-PROVIDER-AUTHENTICATION-PILOT-AUTHORIZATION.md",
    "docs/governance/reviews/"
    "CAR-017-LIVE-COMPOSITION-LAYER-IMPLEMENTATION-AUTHORIZATION.md",
    "docs/governance/reviews/"
    "CAR-018-COMPLETE-PROVIDER-AUTHENTICATION-OPERATIONAL-CLOSURE-"
    "AUTHORIZATION.md",
    "docs/indexes/DOCUMENT-REGISTER.md",
)
_CORRECTIVE_PATHS = (
    "tools/provider_pilots/car017_live_authentication_launcher.py",
    "tests/unit/tools/test_car017_live_authentication_launcher.py",
)
_SHA_PATTERN = re.compile(r"[0-9a-f]{40}\Z")
_EXECUTABLE_ELIGIBILITY_ID = "PROVIDER-AUTH-EXECUTABLE"
_HISTORICAL_AMENDMENT = "CA1"
_CURRENT_AMENDMENT = "CA2"
_CA2_RETIRED_PREDECESSOR = "KRONOS-COORD-AUTH-20260804-002"
_RETIRED_UNUSED_DISPOSITION = "RETIRED FOR EXECUTION — UNUSED"
_CONSUMPTION_DIRECTORY = (
    "Library/Application Support/KRONOS/provider-authentication/"
    "activation-consumption"
)


@dataclass(frozen=True, slots=True, repr=False)
class CanonicalRepositorySnapshot:
    """Three independently evidenced repository identities for live preflight."""

    evidence: CanonicalRepositoryEvidence
    current_branch: str
    current_head_sha: str
    current_origin_develop_sha: str
    current_working_tree_clean: bool
    approved_corrective_implementation_sha: str
    corrective_parent_sha: str
    operational_correction_parent_sha: str
    corrective_paths: tuple[str, ...]
    activation_governance_publication_sha: str
    activation_governance_paths: tuple[str, ...]
    activation_governance_records: tuple[str, str, str, str]
    historical_governance_publication_sha: str
    historical_governance_paths: tuple[str, ...]
    historical_governance_records: tuple[str, str, str, str]

    def __repr__(self) -> str:
        return "<CanonicalRepositorySnapshot sanitized>"


@dataclass(frozen=True, slots=True, repr=False)
class ExecutableEligibilityRecord:
    """Canonical executable selection independent of Git and publication identity."""

    identity: str
    governed_scope: str
    repository: str
    branch: str
    current_eligible_sha: str
    status: str
    approved: str
    superseded_executable_sha: str

    def __repr__(self) -> str:
        return "<ExecutableEligibilityRecord sanitized>"


class ProductionCanonicalActivationEvidenceVerifier:
    """Verify exact historical governance and distinct current repository identity."""

    __slots__ = ("__snapshot",)

    def __init__(self, snapshot: CanonicalRepositorySnapshot) -> None:
        self.__snapshot = snapshot

    def verify(
        self,
        expected: object,
        observed: object,
        evidence: object,
    ) -> bool:
        snapshot = self.__snapshot
        try:
            eligibility = _executable_eligibility_record(
                snapshot.activation_governance_records
            )
        except RuntimeError:
            return False
        if (
            type(expected) is not CoordinatedActivationValues
            or type(observed) is not CoordinatedActivationValues
            or type(evidence) is not CanonicalRepositoryEvidence
            or not expected.exactly_matches(observed)
            or expected.attempt_cardinality != "ONE"
            or expected.consumption_state is not CoordinatedConsumptionState.UNUSED
            or expected.provider_availability_authority != "WITHHELD"
            or expected.provider_availability_max_operations != 0
            or expected.car014_status != "UNEXECUTED"
            or snapshot.historical_governance_publication_sha
            != _COORDINATED_GOVERNANCE_PUBLICATION_SHA
            or expected.coordinated_governance_publication_sha
            != snapshot.activation_governance_publication_sha
            or evidence.branch != snapshot.current_branch
            or evidence.head_sha != snapshot.current_head_sha
            or evidence.origin_develop_sha != snapshot.current_origin_develop_sha
            or evidence.working_tree_clean
            is not snapshot.current_working_tree_clean
            or tuple(sorted(snapshot.historical_governance_paths))
            != tuple(sorted(_GOVERNANCE_PATHS))
            or snapshot.current_branch != "develop"
            or snapshot.current_head_sha != snapshot.current_origin_develop_sha
            or snapshot.current_head_sha != eligibility.current_eligible_sha
            or snapshot.current_branch != eligibility.branch
            or not snapshot.current_working_tree_clean
            or not _SHA_PATTERN.fullmatch(
                snapshot.approved_corrective_implementation_sha
            )
            or snapshot.approved_corrective_implementation_sha
            == snapshot.current_head_sha
            or snapshot.approved_corrective_implementation_sha == _FROZEN_CAR018_SHA
            or snapshot.corrective_parent_sha
            != _CAR018_OPERATIONAL_CORRECTION_SHA
            or snapshot.operational_correction_parent_sha
            != snapshot.historical_governance_publication_sha
            or tuple(sorted(snapshot.corrective_paths))
            != tuple(sorted(_CORRECTIVE_PATHS))
            or tuple(sorted(snapshot.activation_governance_paths))
            != tuple(sorted(_GOVERNANCE_PATHS))
        ):
            return False
        old016, old017, old018, old_register = snapshot.historical_governance_records
        car016, car017, car018, register = snapshot.activation_governance_records
        historical = _historical_activation_context()
        return (
            _verify_car016_record(
                old016, historical, _FROZEN_CAR018_SHA, _HISTORICAL_AMENDMENT
            )
            and _verify_car017_record(
                old017, historical, _FROZEN_CAR018_SHA, _HISTORICAL_AMENDMENT
            )
            and _verify_car018_record(
                old018, historical, _FROZEN_CAR018_SHA, _HISTORICAL_AMENDMENT
            )
            and _verify_document_register(
                old_register,
                historical,
                _FROZEN_CAR018_SHA,
                _HISTORICAL_AMENDMENT,
            )
            and _verify_car016_record(
                car016,
                expected,
                snapshot.approved_corrective_implementation_sha,
                _CURRENT_AMENDMENT,
            )
            and _verify_car017_record(
                car017,
                expected,
                snapshot.approved_corrective_implementation_sha,
                _CURRENT_AMENDMENT,
            )
            and _verify_car018_record(
                car018,
                expected,
                snapshot.approved_corrective_implementation_sha,
                _CURRENT_AMENDMENT,
            )
            and _verify_document_register(
                register,
                expected,
                snapshot.approved_corrective_implementation_sha,
                _CURRENT_AMENDMENT,
            )
        )

    def __repr__(self) -> str:
        return "<ProductionCanonicalActivationEvidenceVerifier sanitized>"


class _BoundedSuccessorEvidenceBridge:
    """Bridge the legacy reviewer predicate after current-state verification."""

    __slots__ = ("__current_evidence", "__verifier")

    def __init__(
        self,
        verifier: ProductionCanonicalActivationEvidenceVerifier,
        current_evidence: CanonicalRepositoryEvidence,
    ) -> None:
        self.__verifier = verifier
        self.__current_evidence = current_evidence

    def verify(self, expected: object, observed: object, evidence: object) -> bool:
        if (
            type(expected) is not CoordinatedActivationValues
            or type(evidence) is not CanonicalRepositoryEvidence
            or evidence.branch != self.__current_evidence.branch
            or evidence.head_sha != expected.coordinated_governance_publication_sha
            or evidence.origin_develop_sha
            != expected.coordinated_governance_publication_sha
            or evidence.working_tree_clean
            is not self.__current_evidence.working_tree_clean
            or evidence.car016_canonical is not self.__current_evidence.car016_canonical
            or evidence.car017_canonical is not self.__current_evidence.car017_canonical
            or evidence.car014_unexecuted is not self.__current_evidence.car014_unexecuted
        ):
            return False
        return self.__verifier.verify(
            expected,
            observed,
            self.__current_evidence,
        )


class ProductionTrustedActivationReviewer:
    """Issue trusted provenance from an exact bounded-successor repository."""

    __slots__ = ("__verifier",)

    def __init__(
        self,
        snapshot: CanonicalRepositorySnapshot,
        verifier: ProductionCanonicalActivationEvidenceVerifier | None = None,
    ) -> None:
        self.__verifier = verifier or ProductionCanonicalActivationEvidenceVerifier(
            snapshot
        )

    def review(
        self,
        *,
        expected: CoordinatedActivationValues,
        observed: CoordinatedActivationValues,
        repository_evidence: CanonicalRepositoryEvidence,
        reviewed_at: datetime,
    ) -> ActivationReview:
        """Verify current evidence, retaining publication identity as provenance."""

        publication_evidence = CanonicalRepositoryEvidence(
            branch=repository_evidence.branch,
            head_sha=expected.coordinated_governance_publication_sha,
            origin_develop_sha=expected.coordinated_governance_publication_sha,
            working_tree_clean=repository_evidence.working_tree_clean,
            car016_canonical=repository_evidence.car016_canonical,
            car017_canonical=repository_evidence.car017_canonical,
            car014_unexecuted=repository_evidence.car014_unexecuted,
        )
        reviewer = TrustedActivationReviewer(
            _BoundedSuccessorEvidenceBridge(self.__verifier, repository_evidence),
            provenance_kind=ActivationProvenanceKind.CANONICAL_LIVE,
        )
        return reviewer.review(
            expected=expected,
            observed=observed,
            repository_evidence=publication_evidence,
            reviewed_at=reviewed_at,
        )

    def __repr__(self) -> str:
        return "<ProductionTrustedActivationReviewer sanitized>"


@dataclass(frozen=True, slots=True, repr=False)
class SanitizedPreflightEvidence:
    """Allow-listed preflight results containing no sensitive material."""

    repository: bool
    canonical_governance: bool
    activation_context: bool
    authority_window: bool
    runtime: bool
    configuration: bool
    durable_record_absent: bool
    consumption_directory_ready: bool
    port_ready_without_bind: bool

    @property
    def passed(self) -> bool:
        return all(
            (
                self.repository,
                self.canonical_governance,
                self.activation_context,
                self.authority_window,
                self.runtime,
                self.configuration,
                self.durable_record_absent,
                self.consumption_directory_ready,
                self.port_ready_without_bind,
            )
        )

    def render(self) -> str:
        rows = (
            ("Repository", self.repository),
            ("Canonical governance", self.canonical_governance),
            ("Activation Context", self.activation_context),
            ("Authority window", self.authority_window),
            ("Runtime versions", self.runtime),
            ("Governed configuration", self.configuration),
            ("Durable record absent", self.durable_record_absent),
            ("Consumption directory ready", self.consumption_directory_ready),
            ("Port 8765 ready without bind", self.port_ready_without_bind),
        )
        body = "\n".join(f"{name}: {'PASS' if value else 'FAIL'}" for name, value in rows)
        overall = "READY FOR FINAL SPONSOR CONFIRMATION" if self.passed else "NOT READY"
        return f"GOVERNED LIVE PREFLIGHT EVIDENCE PACKAGE\n{body}\nOverall: {overall}"

    def __repr__(self) -> str:
        return "<SanitizedPreflightEvidence sanitized>"


@dataclass(frozen=True, slots=True, repr=False)
class RuntimeVersionEvidence:
    python: tuple[int, int, int]
    tkinter: str
    kite_sdk: str

    def valid(self) -> bool:
        return (
            self.python == EXPECTED_PYTHON
            and self.tkinter == EXPECTED_TKINTER
            and self.kite_sdk == EXPECTED_KITE_SDK
        )

    def __repr__(self) -> str:
        return "<RuntimeVersionEvidence sanitized>"


@dataclass(frozen=True, slots=True, repr=False)
class GovernedLaunchRequest:
    expected: CoordinatedActivationValues
    observed: CoordinatedActivationValues
    repository_evidence: CanonicalRepositoryEvidence
    reviewed_at: datetime
    runtime: RuntimeVersionEvidence

    def __repr__(self) -> str:
        return "<GovernedLaunchRequest redacted>"


class PreparedGovernedLaunch:
    """Validated inert preflight that consumes only after GUI confirmation."""

    __slots__ = (
        "__composition_factory",
        "__configuration",
        "__consumed_at",
        "__consumption",
        "__monotonic",
        "__recorder",
        "__review",
        "__values",
    )

    def __init__(
        self,
        *,
        review: ActivationReview,
        values: CoordinatedActivationValues,
        configuration: GovernedProviderAuthenticationConfiguration,
        consumption: DurableConsumptionCoordinator,
        consumed_at: Callable[[], datetime],
        monotonic: Callable[[], float],
        composition_factory: Callable[..., object],
        recorder: OperationLedgerRecorder,
    ) -> None:
        self.__review = review
        self.__values = values
        self.__configuration = configuration
        self.__consumption = consumption
        self.__consumed_at = consumed_at
        self.__monotonic = monotonic
        self.__composition_factory = composition_factory
        self.__recorder = recorder

    @property
    def activation(self) -> object:
        return self.__review.context

    def compose_after_confirmation(self, activation: object) -> object:
        """Consume, adopt the returned proof and deadline, then compose once."""

        if activation is not self.__review.context:
            raise RuntimeError("GOVERNED_ACTIVATION_CONTEXT_MISMATCH")
        result: DurableConsumptionResult = self.__consumption.consume(
            context=self.__review.context,
            capability=self.__review.capability,
            sponsor_confirmed=True,
            consumed_at=self.__consumed_at(),
            monotonic_now=float(self.__monotonic()),
            ledger=self.__recorder.snapshot(),
        )
        if (
            result.category is not ConsumptionOutcomeCategory.CONSUMED
            or result.proof is None
        ):
            raise RuntimeError(result.category.value)
        self.__recorder.adopt(result.proof.ledger)
        deadline = result.proof.deadline

        def remaining_budget() -> object:
            return deadline.remaining(monotonic_now=float(self.__monotonic()))

        return self.__composition_factory(
            self.__review.context,
            proven_consumption=result.proof,
            activation_capability=self.__review.capability,
            activation_values=self.__values,
            configuration=self.__configuration,
            operation_recorder=self.__recorder,
            remaining_budget=remaining_budget,
        )

    def operation_ledger(self) -> object:
        return self.__recorder.snapshot()

    def __repr__(self) -> str:
        return "<PreparedGovernedLaunch sanitized>"


def prepare_governed_launch(
    request: GovernedLaunchRequest,
    *,
    reviewer: TrustedActivationReviewer,
    consumption: DurableConsumptionCoordinator,
    configuration_loader: Callable[[], GovernedProviderAuthenticationConfiguration] = (
        load_governed_provider_authentication_configuration
    ),
    consumed_at: Callable[[], datetime],
    monotonic: Callable[[], float] = time.monotonic,
    composition_factory: Callable[..., object] = compose_kite_authentication,
) -> PreparedGovernedLaunch:
    """Validate all non-sensitive evidence without constructing live dependencies."""

    if type(request) is not GovernedLaunchRequest or not request.runtime.valid():
        raise RuntimeError("GOVERNED_RUNTIME_PREFLIGHT_FAILED")
    recorder = OperationLedgerRecorder()
    review = reviewer.review(
        expected=request.expected,
        observed=request.observed,
        repository_evidence=request.repository_evidence,
        reviewed_at=request.reviewed_at,
    )
    recorder.record(GovernedAuthenticationOperation.ACTIVATION_VALIDATION)
    configuration = configuration_loader()
    if type(configuration) is not GovernedProviderAuthenticationConfiguration:
        raise RuntimeError("GOVERNED_CONFIGURATION_INVALID")
    return PreparedGovernedLaunch(
        review=review,
        values=request.expected,
        configuration=configuration,
        consumption=consumption,
        consumed_at=consumed_at,
        monotonic=monotonic,
        composition_factory=composition_factory,
        recorder=recorder,
    )


def launch_prepared(
    prepared: PreparedGovernedLaunch,
    *,
    gui_main: Callable[..., None] = car016_provider_authentication_gui.main,
    confirmation: Callable[[], bool],
    worker_submit: Callable[[Callable[[], None]], None] | None = None,
) -> None:
    """Present one prepared capability; confirmation precedes consumption."""

    if type(prepared) is not PreparedGovernedLaunch:
        raise RuntimeError("GOVERNED_LAUNCH_NOT_PREPARED")
    submit = worker_submit or _submit_daemon_worker
    gui_main(
        activation=prepared.activation,
        composition_factory=prepared.compose_after_confirmation,
        worker_submit=submit,
        confirmation=confirmation,
        availability_authorized=False,
    )


def runtime_version_evidence() -> RuntimeVersionEvidence:
    """Return only allow-listed runtime versions; perform no external effect."""

    import sys
    import tkinter

    return RuntimeVersionEvidence(
        python=tuple(sys.version_info[:3]),  # type: ignore[arg-type]
        tkinter=str(tkinter.TkVersion),
        kite_sdk=version("kiteconnect"),
    )


def canonical_repository_snapshot(
    repository_root: Path,
    *,
    activation_governance_publication_sha: str,
    git_output: Callable[[tuple[str, ...]], str] | None = None,
) -> CanonicalRepositorySnapshot:
    """Collect bounded local Git and canonical-document evidence without fetch."""

    if not _SHA_PATTERN.fullmatch(activation_governance_publication_sha):
        raise RuntimeError("GOVERNED_ACTIVATION_PUBLICATION_EVIDENCE_INVALID")
    query = git_output or _local_git_output(repository_root)
    branch = query(("branch", "--show-current")).strip()
    head = query(("rev-parse", "HEAD")).strip()
    origin = query(("rev-parse", "origin/develop")).strip()
    clean = query(("status", "--porcelain")).strip() == ""
    activation_paths = tuple(
        line
        for line in query(
            (
                "diff-tree",
                "--no-commit-id",
                "--name-only",
                "-r",
                activation_governance_publication_sha,
            )
        ).splitlines()
        if line
    )
    activation_records = tuple(
        query(("show", f"{activation_governance_publication_sha}:{path}"))
        for path in _GOVERNANCE_PATHS
    )
    approved_corrective = _extract_corrective_sha(
        activation_records[2], _CURRENT_AMENDMENT
    )
    corrective_parent = query(("rev-parse", f"{approved_corrective}^")).strip()
    operational_correction_parent = query(
        ("rev-parse", f"{_CAR018_OPERATIONAL_CORRECTION_SHA}^")
    ).strip()
    corrective_paths = tuple(
        line
        for line in query(
            ("diff-tree", "--no-commit-id", "--name-only", "-r", approved_corrective)
        ).splitlines()
        if line
    )
    historical_paths = tuple(
        line
        for line in query(
            (
                "diff-tree",
                "--no-commit-id",
                "--name-only",
                "-r",
                _COORDINATED_GOVERNANCE_PUBLICATION_SHA,
            )
        ).splitlines()
        if line
    )
    historical_records = tuple(
        query(("show", f"{_COORDINATED_GOVERNANCE_PUBLICATION_SHA}:{path}"))
        for path in _GOVERNANCE_PATHS
    )
    car016, car017, car018, _register = activation_records
    evidence = CanonicalRepositoryEvidence(
        branch=branch,
        head_sha=head,
        origin_develop_sha=origin,
        working_tree_clean=clean,
        car016_canonical=_canonical_record(car016, "CAR-016-V1.2-CA2"),
        car017_canonical=_canonical_record(car017, "CAR-017-V1.2-CA2"),
        car014_unexecuted="CAR-014" in car018 and "UNEXECUTED" in car018,
    )
    return CanonicalRepositorySnapshot(
        evidence=evidence,
        current_branch=branch,
        current_head_sha=head,
        current_origin_develop_sha=origin,
        current_working_tree_clean=clean,
        approved_corrective_implementation_sha=approved_corrective,
        corrective_parent_sha=corrective_parent,
        operational_correction_parent_sha=operational_correction_parent,
        corrective_paths=corrective_paths,
        activation_governance_publication_sha=(
            activation_governance_publication_sha
        ),
        activation_governance_paths=activation_paths,
        activation_governance_records=activation_records,  # type: ignore[arg-type]
        historical_governance_publication_sha=(
            _COORDINATED_GOVERNANCE_PUBLICATION_SHA
        ),
        historical_governance_paths=historical_paths,
        historical_governance_records=historical_records,  # type: ignore[arg-type]
    )


def expected_activation_context(
    snapshot: CanonicalRepositorySnapshot,
) -> CoordinatedActivationValues:
    """Read the current governed binding while retaining historical provenance."""

    return replace(
        _activation_values_from_record(
            snapshot.activation_governance_records[0], _CURRENT_AMENDMENT
        ),
        coordinated_governance_publication_sha=(
            snapshot.activation_governance_publication_sha
        ),
    )


def observed_activation_context(
    *,
    expected: CoordinatedActivationValues,
    repository_evidence: CanonicalRepositoryEvidence,
    configuration: GovernedProviderAuthenticationConfiguration,
    hostname: str,
) -> CoordinatedActivationValues:
    """Project the observed non-sensitive runtime references independently."""

    authentication = configuration.authentication
    return replace(
        expected,
        hostname=hostname,
        operational_provider=authentication.provider,
        provider_identity=configuration.provider_identity,
        provider_configuration_ref=configuration.provider_configuration_ref,
        application_registration_ref=configuration.application_registration_ref,
        credential_ref=authentication.credential_ref,
        intended_principal_registration_ref=(
            authentication.intended_registration_ref
        ),
        redirect_url=authentication.redirect_uri,
    )


def execute_governed_launcher(
    *,
    repository_root: Path,
    environment: object,
    hostname: str,
    reviewed_at: datetime,
    runtime: RuntimeVersionEvidence,
    snapshot: CanonicalRepositorySnapshot,
    sponsor_home: str,
    sponsor_user_id: int,
    durable_state: tuple[bool, bool],
    port_ready_without_bind: bool,
    preflight_presenter: Callable[[str], None],
    confirmation: Callable[[], bool],
    gui_main: Callable[..., None] = car016_provider_authentication_gui.main,
    worker_submit: Callable[[Callable[[], None]], None] | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    consumed_at: Callable[[], datetime] | None = None,
    composition_factory: Callable[..., object] = compose_kite_authentication,
    filesystem: object | None = None,
) -> PreparedGovernedLaunch:
    """Assemble the approved path; effects remain gated by GUI confirmation."""

    configuration = load_governed_provider_authentication_configuration(environment)
    expected = expected_activation_context(snapshot)
    observed = observed_activation_context(
        expected=expected,
        repository_evidence=snapshot.evidence,
        configuration=configuration,
        hostname=hostname,
    )
    verifier = ProductionCanonicalActivationEvidenceVerifier(snapshot)
    canonical_verified = verifier.verify(expected, observed, snapshot.evidence)
    try:
        eligibility = _executable_eligibility_record(
            snapshot.activation_governance_records
        )
    except RuntimeError:
        eligibility = None
    directory_ready, record_absent = durable_state
    preflight = SanitizedPreflightEvidence(
        repository=(
            snapshot.current_branch == "develop"
            and snapshot.current_head_sha == snapshot.current_origin_develop_sha
            and eligibility is not None
            and snapshot.current_head_sha == eligibility.current_eligible_sha
            and snapshot.current_working_tree_clean
            and snapshot.corrective_parent_sha
            == _CAR018_OPERATIONAL_CORRECTION_SHA
            and snapshot.operational_correction_parent_sha
            == snapshot.historical_governance_publication_sha
            and tuple(sorted(snapshot.corrective_paths))
            == tuple(sorted(_CORRECTIVE_PATHS))
        ),
        canonical_governance=(
            canonical_verified
            and snapshot.evidence.car016_canonical
            and snapshot.evidence.car017_canonical
            and snapshot.evidence.car014_unexecuted
            and snapshot.historical_governance_publication_sha
            == _COORDINATED_GOVERNANCE_PUBLICATION_SHA
            and tuple(sorted(snapshot.activation_governance_paths))
            == tuple(sorted(_GOVERNANCE_PATHS))
        ),
        activation_context=expected.exactly_matches(observed),
        authority_window=(
            expected.authority_effective_at
            <= reviewed_at
            < expected.authority_expires_at
        ),
        runtime=runtime.valid(),
        configuration=True,
        durable_record_absent=record_absent,
        consumption_directory_ready=directory_ready,
        port_ready_without_bind=port_ready_without_bind,
    )
    preflight_presenter(preflight.render())
    if not preflight.passed:
        raise RuntimeError("GOVERNED_RUNTIME_PREFLIGHT_FAILED")
    reviewer = ProductionTrustedActivationReviewer(snapshot, verifier)
    consumption = DurableConsumptionCoordinator(
        filesystem=(
            filesystem
            if filesystem is not None
            else DescriptorDurableConsumptionFilesystem()
        ),  # type: ignore[arg-type]
        sponsor_home=sponsor_home,
        sponsor_user_id=sponsor_user_id,
    )
    prepared = prepare_governed_launch(
        GovernedLaunchRequest(
            expected=expected,
            observed=observed,
            repository_evidence=snapshot.evidence,
            reviewed_at=reviewed_at,
            runtime=runtime,
        ),
        reviewer=reviewer,
        consumption=consumption,
        configuration_loader=lambda: configuration,
        consumed_at=consumed_at or _local_now,
        monotonic=monotonic,
        composition_factory=composition_factory,
    )
    try:
        launch_prepared(
            prepared,
            gui_main=gui_main,
            confirmation=confirmation,
            worker_submit=worker_submit,
        )
    finally:
        preflight_presenter(_render_terminal_evidence(prepared))
    return prepared


def _submit_daemon_worker(operation: Callable[[], None]) -> None:
    thread = threading.Thread(target=operation, daemon=True)
    thread.start()


class DescriptorDurableConsumptionFilesystem:
    """Descriptor-relative exclusive no-follow persistence implementation."""

    __slots__ = ()

    def open_verified_parent_directory(
        self, directory: str, *, expected_owner: int, expected_mode: int
    ) -> int:
        descriptor = os.open(
            directory,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
        )
        try:
            _verify_descriptor(descriptor, expected_owner, expected_mode, directory=True)
        except Exception:
            os.close(descriptor)
            raise
        return descriptor

    def create_exclusive_nofollow(
        self, parent_descriptor: object, filename: str, *, mode: int
    ) -> int:
        if type(parent_descriptor) is not int or "/" in filename:
            raise RuntimeError("DURABLE_CONSUMPTION_PATH_INVALID")
        return os.open(
            filename,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            mode,
            dir_fd=parent_descriptor,
        )

    def verify_open_file(
        self,
        descriptor: object,
        *,
        expected_owner: int,
        expected_mode: int,
        expected_link_count: int,
    ) -> None:
        if type(descriptor) is not int:
            raise RuntimeError("DURABLE_CONSUMPTION_DESCRIPTOR_INVALID")
        result = os.fstat(descriptor)
        if (
            result.st_uid != expected_owner
            or stat.S_IMODE(result.st_mode) != expected_mode
            or not stat.S_ISREG(result.st_mode)
            or result.st_nlink != expected_link_count
        ):
            raise RuntimeError("DURABLE_CONSUMPTION_FILE_INVALID")

    def write_all(self, descriptor: object, payload: bytes) -> None:
        if type(descriptor) is not int or type(payload) is not bytes:
            raise RuntimeError("DURABLE_CONSUMPTION_WRITE_INVALID")
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise RuntimeError("DURABLE_CONSUMPTION_WRITE_FAILED")
            offset += written

    def flush_file(self, _descriptor: object) -> None:
        return None

    def fsync_file(self, descriptor: object) -> None:
        os.fsync(_descriptor(descriptor))

    def close_file(self, descriptor: object) -> None:
        os.close(_descriptor(descriptor))

    def fsync_directory(self, descriptor: object) -> None:
        os.fsync(_descriptor(descriptor))

    def close_directory(self, descriptor: object) -> None:
        os.close(_descriptor(descriptor))


def _verify_descriptor(
    descriptor: int, expected_owner: int, expected_mode: int, *, directory: bool
) -> None:
    result = os.fstat(descriptor)
    expected_type = stat.S_ISDIR if directory else stat.S_ISREG
    if (
        result.st_uid != expected_owner
        or stat.S_IMODE(result.st_mode) != expected_mode
        or not expected_type(result.st_mode)
    ):
        raise RuntimeError("DURABLE_CONSUMPTION_PARENT_INVALID")


def _descriptor(value: object) -> int:
    if type(value) is not int:
        raise RuntimeError("DURABLE_CONSUMPTION_DESCRIPTOR_INVALID")
    return value


def _activation_values(
    *,
    publication_sha: str,
    hostname: str,
    operational_provider: str,
    provider_identity: str,
    provider_configuration_ref: str,
    application_registration_ref: str,
    credential_ref: str,
    intended_principal_registration_ref: str,
    redirect_url: str,
) -> CoordinatedActivationValues:
    return CoordinatedActivationValues(
        coordinated_activation_identity=_ACTIVATION_IDENTITY,
        coordinated_governance_publication_sha=publication_sha,
        car016_logical_publication_ref=_CAR016_LOGICAL_REFERENCE,
        car017_logical_publication_ref=_CAR017_LOGICAL_REFERENCE,
        frozen_car016_implementation_sha=_FROZEN_CAR016_SHA,
        frozen_car017_implementation_sha=_FROZEN_CAR017_SHA,
        authority_effective_at=_EFFECTIVE_AT,
        authority_effective_timezone="Asia/Kolkata",
        authority_expires_at=_EXPIRES_AT,
        authority_expiry_timezone="Asia/Kolkata",
        authentication_attempt_timeout_seconds=300,
        sponsor_environment_ref=_SPONSOR_ENVIRONMENT,
        hostname=hostname,
        provider_identity=provider_identity,
        operational_provider=operational_provider,
        provider_configuration_ref=provider_configuration_ref,
        application_registration_ref=application_registration_ref,
        credential_ref=credential_ref,
        intended_principal_registration_ref=intended_principal_registration_ref,
        composition_dependency_set_ref="CAR017-LIVE-COMPOSITION-DEPENDENCY-SET-V1",
        redirect_url=redirect_url,
        attempt_cardinality="ONE",
        provider_availability_authority="WITHHELD",
        provider_availability_max_operations=0,
        car014_status="UNEXECUTED",
        consumption_state=CoordinatedConsumptionState.UNUSED,
    )


def _historical_activation_context() -> CoordinatedActivationValues:
    return _activation_values(
        publication_sha=_COORDINATED_GOVERNANCE_PUBLICATION_SHA,
        hostname=_APPROVED_HOSTNAME,
        operational_provider="KITE",
        provider_identity="ZERODHA_KITE",
        provider_configuration_ref="ZERODHA-KITE-PROVIDER-CONFIG-PRIMARY",
        application_registration_ref="ZERODHA-KITE-APP-REGISTRATION-PRIMARY",
        credential_ref="KITE-API-SECRET-PRIMARY",
        intended_principal_registration_ref="KITE-INTENDED-PRINCIPAL-PRIMARY",
        redirect_url="http://127.0.0.1:8765/kite/callback",
    )


def _amendment_section(document: str, record: str, amendment: str) -> str:
    if amendment in {_HISTORICAL_AMENDMENT, _CURRENT_AMENDMENT} and record in {
        "CAR-016",
        "CAR-017",
    }:
        heading = rf"^# \d+\. Controlled Amendment — {record}-V1\.2-{amendment}$"
        peer_heading = rf"^# \d+\. Controlled Amendment — {record}-V1\.2-CA\d+$"
    elif record == "CAR-018" and amendment == _HISTORICAL_AMENDMENT:
        heading = r"^## Approved Canonical coordinated activation disposition$"
        peer_heading = r"^## Approved Canonical .*activation disposition$"
    elif record == "CAR-018" and amendment == _CURRENT_AMENDMENT:
        heading = r"^## Approved Canonical post-correction CA2 activation disposition$"
        peer_heading = r"^## Approved Canonical .*activation disposition$"
    else:
        raise RuntimeError("GOVERNED_ACTIVATION_AMENDMENT_INVALID")
    matches = tuple(re.finditer(heading, document, re.MULTILINE))
    if len(matches) != 1:
        raise RuntimeError("GOVERNED_ACTIVATION_AMENDMENT_INVALID")
    start = matches[0].start()
    later_peers = tuple(
        match
        for match in re.finditer(peer_heading, document, re.MULTILINE)
        if match.start() > start
    )
    end = later_peers[0].start() if later_peers else len(document)
    return document[start:end]


def _extract_table_value(section: str, label: str) -> str:
    pattern = re.compile(
        rf"^\| {re.escape(label)} \| `([^`\n]+)` \|$",
        re.MULTILINE,
    )
    matches = pattern.findall(section)
    if len(matches) != 1:
        raise RuntimeError("GOVERNED_ACTIVATION_RECORD_INVALID")
    return matches[0]


def _register_eligibility_section(document: str) -> str:
    heading = "## Governed Executable Eligibility Index"
    if document.splitlines().count(heading) != 1:
        raise RuntimeError("GOVERNED_EXECUTABLE_ELIGIBILITY_INVALID")
    start = document.index(heading)
    later_heading = re.search(
        r"^#(?:#)? ", document[start + len(heading) :], re.MULTILINE
    )
    end = (
        start + len(heading) + later_heading.start()
        if later_heading is not None
        else len(document)
    )
    return document[start:end]


def _eligibility_history(section: str) -> tuple[tuple[str, str], ...]:
    """Parse one exact, unambiguous append-only eligibility history table."""

    heading = "#### Append-only eligibility history"
    lines = section.splitlines()
    if lines.count(heading) != 1:
        raise RuntimeError("GOVERNED_EXECUTABLE_ELIGIBILITY_INVALID")
    start = lines.index(heading) + 1
    while start < len(lines) and not lines[start]:
        start += 1
    if lines[start : start + 2] != [
        "| Executable SHA | Eligibility disposition |",
        "|---|---|",
    ]:
        raise RuntimeError("GOVERNED_EXECUTABLE_ELIGIBILITY_INVALID")
    entries: list[tuple[str, str]] = []
    row_pattern = re.compile(
        r"\| `([0-9a-f]{40})` \| `(ACTIVE|SUPERSEDED)` \|\Z"
    )
    for line in lines[start + 2 :]:
        if not line:
            break
        match = row_pattern.fullmatch(line)
        if match is None:
            raise RuntimeError("GOVERNED_EXECUTABLE_ELIGIBILITY_INVALID")
        entries.append((match.group(1), match.group(2)))
    if not entries or len({sha for sha, _status in entries}) != len(entries):
        raise RuntimeError("GOVERNED_EXECUTABLE_ELIGIBILITY_INVALID")
    return tuple(entries)


def _executable_eligibility_record(
    records: tuple[str, str, str, str],
) -> ExecutableEligibilityRecord:
    """Resolve exactly one approved executable selection from canonical records."""

    if len(records) != 4:
        raise RuntimeError("GOVERNED_EXECUTABLE_ELIGIBILITY_INVALID")
    car016, car017, car018, register = records
    car016_section = _amendment_section(car016, "CAR-016", _CURRENT_AMENDMENT)
    car017_section = _amendment_section(car017, "CAR-017", _CURRENT_AMENDMENT)
    car018_section = _amendment_section(car018, "CAR-018", _CURRENT_AMENDMENT)
    register_section = _register_eligibility_section(register)
    references = (
        _extract_table_value(car016_section, "Executable Eligibility Identity"),
        _extract_table_value(car017_section, "Executable Eligibility Identity"),
        _extract_table_value(car018_section, "Executable Eligibility Identity"),
        _extract_table_value(register_section, "Executable Eligibility Identity"),
    )
    if len(set(references)) != 1 or references[0] != _EXECUTABLE_ELIGIBILITY_ID:
        raise RuntimeError("GOVERNED_EXECUTABLE_ELIGIBILITY_INVALID")

    labels = (
        "Governed Scope",
        "Repository",
        "Branch",
        "Current Eligible SHA",
        "Status",
        "Approved",
        "Supersedes",
    )
    car018_values = tuple(
        _extract_table_value(car018_section, label) for label in labels
    )
    if (
        _extract_table_value(register_section, "Authoritative Source") != "CAR-018"
        or _extract_table_value(register_section, "Repository Location")
        != "docs/governance/reviews/"
        "CAR-018-COMPLETE-PROVIDER-AUTHENTICATION-OPERATIONAL-CLOSURE-"
        "AUTHORIZATION.md"
        or _extract_table_value(register_section, "Index Authority")
        != "INDEX ONLY — CAR-018 AUTHORITATIVE"
    ):
        raise RuntimeError("GOVERNED_EXECUTABLE_ELIGIBILITY_INVALID")
    (
        scope,
        repository,
        branch,
        eligible_sha,
        status,
        approved,
        superseded_sha,
    ) = car018_values
    history = _eligibility_history(car018_section)
    active_entries = tuple(sha for sha, value in history if value == "ACTIVE")
    history_by_sha = dict(history)
    if (
        scope != "Provider Authentication / CAR-018 governed launcher"
        or not _SHA_PATTERN.fullmatch(eligible_sha)
        or repository != "emiali-jason/Project-Kronos"
        or branch != "develop"
        or status != "ACTIVE"
        or approved != "YES"
        or not _SHA_PATTERN.fullmatch(superseded_sha)
        or superseded_sha == eligible_sha
        or history_by_sha.get(superseded_sha) != "SUPERSEDED"
        or active_entries != (eligible_sha,)
    ):
        raise RuntimeError("GOVERNED_EXECUTABLE_ELIGIBILITY_INVALID")
    return ExecutableEligibilityRecord(
        identity=references[0],
        governed_scope=scope,
        repository=repository,
        branch=branch,
        current_eligible_sha=eligible_sha,
        status=status,
        approved=approved,
        superseded_executable_sha=superseded_sha,
    )


def _extract_corrective_sha(document: str, amendment: str) -> str:
    section = _amendment_section(document, "CAR-018", amendment)
    marker = "**Frozen CAR-018 Corrective Composite Implementation SHA:** `"
    matches = tuple(
        line[len(marker) : -1]
        for line in section.splitlines()
        if line.startswith(marker) and line.endswith("`")
    )
    if len(matches) != 1 or not _SHA_PATTERN.fullmatch(matches[0]):
        raise RuntimeError("GOVERNED_CORRECTIVE_IMPLEMENTATION_EVIDENCE_INVALID")
    return matches[0]


def _activation_values_from_record(
    document: str, amendment: str
) -> CoordinatedActivationValues:
    section = _amendment_section(document, "CAR-016", amendment)

    def value(label: str) -> str:
        return _extract_table_value(section, label)

    try:
        effective = datetime.fromisoformat(value("Authority effective timestamp"))
        expires = datetime.fromisoformat(value("Authority expiry timestamp"))
        timeout = value("Authentication Attempt timeout")
        maximum = value("Maximum Provider Availability verification operations")
        consumption = CoordinatedConsumptionState(
            value("Coordinated consumption state")
        )
    except (ValueError, TypeError) as error:
        raise RuntimeError("GOVERNED_ACTIVATION_RECORD_INVALID") from error
    if not timeout.endswith(" seconds"):
        raise RuntimeError("GOVERNED_ACTIVATION_RECORD_INVALID")
    return CoordinatedActivationValues(
        coordinated_activation_identity=value("Coordinated activation identity"),
        coordinated_governance_publication_sha=(
            _COORDINATED_GOVERNANCE_PUBLICATION_SHA
        ),
        car016_logical_publication_ref=value(
            f"Logical CAR-016 {amendment} publication reference"
        ),
        car017_logical_publication_ref=value(
            f"Logical CAR-017 {amendment} publication reference"
        ),
        frozen_car016_implementation_sha=value(
            "Frozen CAR-016 implementation SHA"
        ),
        frozen_car017_implementation_sha=value(
            "Frozen CAR-017 implementation SHA"
        ),
        authority_effective_at=effective,
        authority_effective_timezone=value("Authority effective timezone"),
        authority_expires_at=expires,
        authority_expiry_timezone=value("Authority expiry timezone"),
        authentication_attempt_timeout_seconds=int(timeout.removesuffix(" seconds")),
        sponsor_environment_ref=value("Sponsor environment reference"),
        hostname=value("Approved hostname"),
        provider_identity=value("Provider identity"),
        operational_provider=value("Operational Provider value"),
        provider_configuration_ref=value("Provider configuration reference"),
        application_registration_ref=value(
            "Kite application-registration reference"
        ),
        credential_ref=value("Secure-credential reference"),
        intended_principal_registration_ref=value(
            "Intended-principal registration reference"
        ),
        composition_dependency_set_ref=value(
            "Composition dependency-set reference"
        ),
        redirect_url=value("Redirect URL"),
        attempt_cardinality=value("Attempt cardinality"),
        provider_availability_authority=value(
            "Provider Availability Verification Authority"
        ),
        provider_availability_max_operations=int(maximum),
        car014_status=value("CAR-014 status"),
        consumption_state=consumption,
    )


def _verify_car016_record(
    document: str,
    values: CoordinatedActivationValues,
    corrective_sha: str,
    amendment: str,
) -> bool:
    try:
        section = _amendment_section(document, "CAR-016", amendment)
    except RuntimeError:
        return False
    metadata = (
        f"**Controlled Amendment ID:** `CAR-016-V1.2-{amendment}`",
        "**Controlled Amendment Status:** Approved",
        "**Canonical Status:** Canonical Controlled Amendment",
        "**Underlying Canonical Record:** CAR-016 Version 1.2",
        "**Workflow Stage:** Repository Publication",
    )
    return (
        _contains_exact_lines_once(section, metadata)
        and (
            amendment != _CURRENT_AMENDMENT
            or _verify_retired_predecessor(section, values)
        )
        and _verify_context_table(section, values, corrective_sha, amendment)
    )


def _verify_car017_record(
    document: str,
    values: CoordinatedActivationValues,
    corrective_sha: str,
    amendment: str,
) -> bool:
    try:
        section = _amendment_section(document, "CAR-017", amendment)
    except RuntimeError:
        return False
    metadata = (
        f"**Controlled Amendment ID:** `CAR-017-V1.2-{amendment}`",
        "**Controlled Amendment Status:** Approved",
        "**Canonical Status:** Canonical Controlled Amendment",
        "**Underlying Canonical Record:** CAR-017 Version 1.2",
        "**Workflow Stage:** Repository Publication",
    )
    return (
        _contains_exact_lines_once(section, metadata)
        and (
            amendment != _CURRENT_AMENDMENT
            or _verify_retired_predecessor(section, values)
        )
        and _verify_context_table(section, values, corrective_sha, amendment)
    )


def _verify_car018_record(
    document: str,
    values: CoordinatedActivationValues,
    corrective_sha: str,
    amendment: str,
) -> bool:
    metadata = (
        "**Document ID:** CAR-018",
        "**Version:** 1.1",
        "**Status:** Approved",
        "**Canonical Status:** Canonical",
        "**Workflow Stage:** Repository Publication",
        "**Decision:** APPROVED — IMPLEMENTATION CONFORMANCE ACCEPTED",
    )
    if not _contains_exact_lines(document, metadata):
        return False
    try:
        section = _amendment_section(document, "CAR-018", amendment)
    except RuntimeError:
        return False
    if amendment == _CURRENT_AMENDMENT:
        amendment_metadata = (
            "**CAR-016 Controlled Amendment:** `CAR-016-V1.2-CA2`",
            "**CAR-017 Controlled Amendment:** `CAR-017-V1.2-CA2`",
            "**Controlled Amendment Status:** Approved",
            "**Canonical Status:** Canonical Controlled Amendment",
            "**Workflow Stage:** Repository Publication",
            "**Frozen CAR-018 Corrective Composite Implementation SHA:** "
            f"`{corrective_sha}`",
        )
        if not _contains_exact_lines_once(section, amendment_metadata):
            return False
        if not _verify_retired_predecessor(section, values):
            return False
    elif (
        "**Frozen CAR-018 Corrective Composite Implementation SHA:** "
        f"`{corrective_sha}`"
    ) not in document.splitlines():
        return False
    repeated_rows = tuple(
        f"| {label} | `{value}` | `{value}` | `{value}` | MATCH |"
        for label, value in _context_pairs(values, corrective_sha, amendment)
        if label != f"{amendment} coordinated governance publication commit SHA"
    )
    publication = (
        f"| {amendment} coordinated governance publication commit SHA | "
        "`PENDING — ESTABLISHED BY THE FOUR-FILE CANONICAL PUBLICATION COMMIT` | "
        "`PENDING — ESTABLISHED BY THE FOUR-FILE CANONICAL PUBLICATION COMMIT` | "
        "`PENDING — ESTABLISHED BY THE FOUR-FILE CANONICAL PUBLICATION COMMIT` | "
        "MATCH; replaced by the resulting publication SHA as post-publication evidence |"
    )
    return _contains_exact_lines(section, (*repeated_rows, publication))


def _verify_context_table(
    document: str,
    values: CoordinatedActivationValues,
    corrective_sha: str,
    amendment: str,
) -> bool:
    rows = tuple(
        f"| {label} | `{value}` |"
        for label, value in _context_pairs(values, corrective_sha, amendment)
    )
    return _contains_exact_lines(document, rows)


def _context_pairs(
    values: CoordinatedActivationValues,
    corrective_sha: str,
    amendment: str,
) -> tuple[tuple[str, str], ...]:
    return (
        ("Coordinated activation identity", values.coordinated_activation_identity),
        (
            f"{amendment} coordinated governance publication commit SHA",
            "PENDING — ESTABLISHED BY THE FOUR-FILE CANONICAL PUBLICATION COMMIT",
        ),
        (
            f"Logical CAR-016 {amendment} publication reference",
            values.car016_logical_publication_ref,
        ),
        (
            f"Logical CAR-017 {amendment} publication reference",
            values.car017_logical_publication_ref,
        ),
        ("Frozen CAR-016 implementation SHA", values.frozen_car016_implementation_sha),
        ("Frozen CAR-017 implementation SHA", values.frozen_car017_implementation_sha),
        ("Frozen CAR-018 corrective composite implementation SHA", corrective_sha),
        ("Authority effective timestamp", values.authority_effective_at.isoformat()),
        ("Authority effective timezone", values.authority_effective_timezone),
        ("Authority expiry timestamp", values.authority_expires_at.isoformat()),
        ("Authority expiry timezone", values.authority_expiry_timezone),
        (
            "Authentication Attempt timeout",
            f"{values.authentication_attempt_timeout_seconds} seconds",
        ),
        ("Sponsor environment reference", values.sponsor_environment_ref),
        ("Approved hostname", values.hostname),
        ("Provider identity", values.provider_identity),
        ("Operational Provider value", values.operational_provider),
        ("Provider configuration reference", values.provider_configuration_ref),
        (
            "Kite application-registration reference",
            values.application_registration_ref,
        ),
        ("Secure-credential reference", values.credential_ref),
        (
            "Intended-principal registration reference",
            values.intended_principal_registration_ref,
        ),
        (
            "Composition dependency-set reference",
            values.composition_dependency_set_ref,
        ),
        ("Redirect URL", values.redirect_url),
        ("Attempt cardinality", values.attempt_cardinality),
        (
            "Provider Availability Verification Authority",
            values.provider_availability_authority,
        ),
        (
            "Maximum Provider Availability verification operations",
            str(values.provider_availability_max_operations),
        ),
        ("CAR-014 status", values.car014_status),
        ("Coordinated consumption state", values.consumption_state.value),
        (
            "Controlled invalid-activation category",
            "COORDINATED_LIVE_ACTIVATION_NOT_AUTHORIZED_OR_CONTEXT_MISMATCH",
        ),
    )


def _verify_document_register(
    document: str,
    values: CoordinatedActivationValues,
    corrective_sha: str,
    amendment: str,
) -> bool:
    rows = {
        identifier: tuple(
            line for line in document.splitlines() if line.startswith(f"| {identifier} |")
        )
        for identifier in ("CAR-016", "CAR-017", "CAR-018")
    }
    if any(len(matches) != 1 for matches in rows.values()):
        return False
    common = (
        values.coordinated_activation_identity,
        values.car016_logical_publication_ref,
        values.car017_logical_publication_ref,
        corrective_sha,
        values.authority_effective_at.isoformat(),
        values.authority_expires_at.isoformat(),
        "attempt cardinality: ONE",
        "consumption state: UNUSED",
        "Provider Availability Verification Authority: WITHHELD",
        "maximum operations: 0",
        "CAR-014 UNEXECUTED",
    )
    if amendment == _CURRENT_AMENDMENT:
        common = (
            *common,
            f"previous coordinated identity: `{_CA2_RETIRED_PREDECESSOR}`",
            f"previous identity disposition: {_RETIRED_UNUSED_DISPOSITION}",
        )
    record_specific = {
        "CAR-016": (
            "Version: 1.2",
            f"Controlled Amendment: `CAR-016-V1.2-{amendment}`",
            "Canonical Status: Canonical Controlled Amendment",
        ),
        "CAR-017": (
            "Version: 1.2",
            f"Controlled Amendment: `CAR-017-V1.2-{amendment}`",
            "Canonical Status: Canonical Controlled Amendment",
        ),
        "CAR-018": (
            "Version: 1.1",
            "Canonical Status: Canonical",
            "Decision: APPROVED — IMPLEMENTATION CONFORMANCE ACCEPTED",
        ),
    }
    return all(
        all(token in rows[identifier][0] for token in (*common, *specific))
        for identifier, specific in record_specific.items()
    )


def _contains_exact_lines(document: str, expected: tuple[str, ...]) -> bool:
    lines = frozenset(document.splitlines())
    return all(line in lines for line in expected)


def _contains_exact_lines_once(document: str, expected: tuple[str, ...]) -> bool:
    lines = document.splitlines()
    return all(lines.count(line) == 1 for line in expected)


def _verify_retired_predecessor(
    section: str, values: CoordinatedActivationValues
) -> bool:
    previous = re.findall(
        r"^\| Previous coordinated activation identity \| `([^`\n]+)` \|$",
        section,
        re.MULTILINE,
    )
    disposition = (
        f"| Previous identity disposition | `{_RETIRED_UNUSED_DISPOSITION}` |"
    )
    return (
        len(previous) == 1
        and previous[0] == _CA2_RETIRED_PREDECESSOR
        and values.coordinated_activation_identity != _CA2_RETIRED_PREDECESSOR
        and section.splitlines().count(disposition) == 1
    )


def _local_git_output(repository_root: Path) -> Callable[[tuple[str, ...]], str]:
    def query(arguments: tuple[str, ...]) -> str:
        result = subprocess.run(
            ("git", *arguments),
            cwd=repository_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError("GOVERNED_REPOSITORY_EVIDENCE_UNAVAILABLE")
        return result.stdout

    return query


def _canonical_record(document: str, amendment: str) -> bool:
    return (
        "**Canonical Status:** Canonical" in document
        and amendment in document
        and "Canonical Controlled Amendment" in document
    )


def _durable_state(
    sponsor_home: str,
    sponsor_user_id: int,
    activation_identity: str,
) -> tuple[bool, bool]:
    directory = Path(sponsor_home) / _CONSUMPTION_DIRECTORY
    try:
        details = directory.lstat()
    except OSError:
        return False, False
    directory_ready = (
        stat.S_ISDIR(details.st_mode)
        and not directory.is_symlink()
        and details.st_uid == sponsor_user_id
        and stat.S_IMODE(details.st_mode) == 0o700
    )
    if not directory_ready:
        return False, False
    record = directory / consumption_filename(activation_identity)
    try:
        record.lstat()
    except FileNotFoundError:
        return True, True
    except OSError:
        return True, False
    return True, False


def _port_ready_without_bind() -> bool:
    try:
        result = subprocess.run(
            ("/usr/sbin/lsof", "-nP", "-iTCP:8765", "-sTCP:LISTEN"),
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 1 and result.stdout == ""


def _local_now() -> datetime:
    return datetime.now().astimezone()


def _final_sponsor_confirmation() -> bool:
    from tkinter import messagebox

    return bool(
        messagebox.askyesno(
            "CAR-018 final Sponsor confirmation",
            "Proceed with the single governed authentication attempt? "
            "Confirmation durably consumes the coordinated authority. "
            "No retry is authorized.",
        )
    )


def _render_terminal_evidence(prepared: PreparedGovernedLaunch) -> str:
    ledger = prepared.operation_ledger()
    rows = tuple(
        f"{operation.value}: {ledger.count_for(operation)}"
        for operation in GovernedAuthenticationOperation
    )
    return "SANITIZED GOVERNED TERMINAL EVIDENCE\n" + "\n".join(rows)


def main() -> int:
    """Assemble the sole governed path and fail with sanitized evidence."""

    repository_root = Path(__file__).resolve().parents[2]
    try:
        snapshot = canonical_repository_snapshot(
            repository_root,
            activation_governance_publication_sha=os.environ.get(
                "KRONOS_ACTIVATION_GOVERNANCE_PUBLICATION_SHA", ""
            ),
        )
        expected = expected_activation_context(snapshot)
        sponsor = pwd.getpwuid(os.getuid())
        execute_governed_launcher(
            repository_root=repository_root,
            environment=os.environ,
            hostname=socket.gethostname(),
            reviewed_at=_local_now(),
            runtime=runtime_version_evidence(),
            snapshot=snapshot,
            sponsor_home=sponsor.pw_dir,
            sponsor_user_id=sponsor.pw_uid,
            durable_state=_durable_state(
                sponsor.pw_dir,
                sponsor.pw_uid,
                expected.coordinated_activation_identity,
            ),
            port_ready_without_bind=_port_ready_without_bind(),
            preflight_presenter=print,
            confirmation=_final_sponsor_confirmation,
        )
    except Exception:
        print("GOVERNED LIVE AUTHENTICATION: SANITIZED FAILURE")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
