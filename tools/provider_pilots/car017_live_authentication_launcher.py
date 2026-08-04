"""Sole governed CAR-018 live launcher; direct import and launch are inert."""

from __future__ import annotations

import os
import stat
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from importlib.metadata import version

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
    CanonicalRepositoryEvidence,
    CoordinatedActivationValues,
    DurableConsumptionCoordinator,
    DurableConsumptionResult,
    TrustedActivationReviewer,
)
from kronos.provider.models.authentication import (
    ConsumptionOutcomeCategory,
    GovernedAuthenticationOperation,
)
from tools.provider_pilots import car016_provider_authentication_gui


EXPECTED_PYTHON = (3, 13, 14)
EXPECTED_TKINTER = "9.0"
EXPECTED_KITE_SDK = "5.2.0"


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


def main() -> None:
    """Ordinary direct launch remains inspection-only until prepared externally."""

    car016_provider_authentication_gui.main()


if __name__ == "__main__":
    main()
