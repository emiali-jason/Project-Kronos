"""Externally inert CAR-018 activation and durable-consumption contracts."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import PurePath
from typing import Final

from kronos.provider.contracts.provider_authentication import (
    CanonicalActivationEvidenceVerifier,
    DurableConsumptionFilesystem,
)
from kronos.provider.models.authentication import (
    ConsumptionOutcomeCategory,
    CoordinatedConsumptionState,
    GovernedAuthenticationOperation,
    SanitizedOperationLedger,
)


_SHA_PATTERN: Final = re.compile(r"[0-9a-f]{40}\Z")
_REFERENCE_PATTERN: Final = re.compile(r"[A-Za-z0-9._:-]{1,160}\Z")
_ACTIVATION_IDENTITY_PATTERN: Final = re.compile(
    r"[A-Z0-9](?:[A-Z0-9_-]{0,126}[A-Z0-9])?\Z",
    re.ASCII,
)
_RFC3339_OFFSET_PATTERN: Final = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?[+-]\d{2}:\d{2}\Z",
    re.ASCII,
)
_RECORD_KEYS: Final = (
    "schema_version",
    "coordinated_activation_identity",
    "coordinated_governance_publication_sha",
    "consumption_state",
    "consumed_at",
)
_CONSUMPTION_DIRECTORY_SUFFIX: Final = (
    "Library/Application Support/KRONOS/provider-authentication/"
    "activation-consumption"
)
_CONSUMPTION_RECORD_MAX_BYTES: Final = 1024
_DIRECTORY_MODE: Final = 0o700
_FILE_MODE: Final = 0o600
_LIFECYCLE_SECONDS: Final = 300.0
_PROVENANCE_SEAL: Final = object()


class LiveActivationFailure(StrEnum):
    """Sanitized, fail-closed Stage 1 failure categories."""

    INVALID_CONTEXT = "INVALID_CONTEXT"
    CONTEXT_MISMATCH = "CONTEXT_MISMATCH"
    INVALID_PROVENANCE = "INVALID_PROVENANCE"
    INVALID_REPOSITORY_EVIDENCE = "INVALID_REPOSITORY_EVIDENCE"
    OUTSIDE_AUTHORITY_WINDOW = "OUTSIDE_AUTHORITY_WINDOW"
    INVALID_ACTIVATION_IDENTITY = "INVALID_ACTIVATION_IDENTITY"
    INVALID_CONSUMPTION_RECORD = "INVALID_CONSUMPTION_RECORD"
    SPONSOR_CONFIRMATION_REQUIRED = "SPONSOR_CONFIRMATION_REQUIRED"
    POST_CONFIRMATION_CONSUMPTION_UNCERTAIN = (
        "POST_CONFIRMATION_CONSUMPTION_UNCERTAIN"
    )
    FILESYSTEM_CAPABILITY_UNAVAILABLE_STOP_ESCALATE = (
        "FILESYSTEM_CAPABILITY_UNAVAILABLE_STOP_ESCALATE"
    )
    DEADLINE_EXHAUSTED = "DEADLINE_EXHAUSTED"


class LiveActivationError(RuntimeError):
    """Controlled error that retains no activation evidence or raw exception."""

    def __init__(self, failure: LiveActivationFailure) -> None:
        self.failure = failure
        super().__init__(failure.value)


class ActivationProvenanceKind(StrEnum):
    """Explicitly separate fake-only review from a canonical live review."""

    FAKE_ONLY = "FAKE_ONLY"
    CANONICAL_LIVE = "CANONICAL_LIVE"


@dataclass(frozen=True, slots=True, repr=False)
class CoordinatedActivationValues:
    """Complete non-sensitive coordinated Activation Context projection."""

    coordinated_activation_identity: str
    coordinated_governance_publication_sha: str
    car016_logical_publication_ref: str
    car017_logical_publication_ref: str
    frozen_car016_implementation_sha: str
    frozen_car017_implementation_sha: str
    authority_effective_at: datetime
    authority_effective_timezone: str
    authority_expires_at: datetime
    authority_expiry_timezone: str
    authentication_attempt_timeout_seconds: int
    sponsor_environment_ref: str
    hostname: str
    provider_identity: str
    operational_provider: str
    provider_configuration_ref: str
    application_registration_ref: str
    credential_ref: str
    intended_principal_registration_ref: str
    composition_dependency_set_ref: str
    redirect_url: str
    attempt_cardinality: str
    provider_availability_authority: str
    provider_availability_max_operations: int
    car014_status: str
    consumption_state: CoordinatedConsumptionState

    def __post_init__(self) -> None:
        string_values = (
            self.coordinated_activation_identity,
            self.coordinated_governance_publication_sha,
            self.car016_logical_publication_ref,
            self.car017_logical_publication_ref,
            self.frozen_car016_implementation_sha,
            self.frozen_car017_implementation_sha,
            self.authority_effective_timezone,
            self.authority_expiry_timezone,
            self.sponsor_environment_ref,
            self.hostname,
            self.provider_identity,
            self.operational_provider,
            self.provider_configuration_ref,
            self.application_registration_ref,
            self.credential_ref,
            self.intended_principal_registration_ref,
            self.composition_dependency_set_ref,
            self.redirect_url,
            self.attempt_cardinality,
            self.provider_availability_authority,
            self.car014_status,
        )
        if any(type(value) is not str or not value for value in string_values):
            raise LiveActivationError(LiveActivationFailure.INVALID_CONTEXT)
        if not valid_activation_identity(self.coordinated_activation_identity):
            raise LiveActivationError(
                LiveActivationFailure.INVALID_ACTIVATION_IDENTITY
            )
        if any(
            _SHA_PATTERN.fullmatch(value) is None
            for value in (
                self.coordinated_governance_publication_sha,
                self.frozen_car016_implementation_sha,
                self.frozen_car017_implementation_sha,
            )
        ):
            raise LiveActivationError(LiveActivationFailure.INVALID_CONTEXT)
        if any(
            _REFERENCE_PATTERN.fullmatch(value) is None
            for value in (
                self.car016_logical_publication_ref,
                self.car017_logical_publication_ref,
                self.sponsor_environment_ref,
                self.provider_identity,
                self.operational_provider,
                self.provider_configuration_ref,
                self.application_registration_ref,
                self.credential_ref,
                self.intended_principal_registration_ref,
                self.composition_dependency_set_ref,
                self.attempt_cardinality,
                self.provider_availability_authority,
                self.car014_status,
            )
        ):
            raise LiveActivationError(LiveActivationFailure.INVALID_CONTEXT)
        if not _aware(self.authority_effective_at) or not _aware(
            self.authority_expires_at
        ):
            raise LiveActivationError(LiveActivationFailure.INVALID_CONTEXT)
        if self.authority_effective_at >= self.authority_expires_at:
            raise LiveActivationError(LiveActivationFailure.INVALID_CONTEXT)
        if (
            type(self.authentication_attempt_timeout_seconds) is not int
            or self.authentication_attempt_timeout_seconds != 300
            or type(self.provider_availability_max_operations) is not int
            or self.provider_availability_max_operations != 0
            or type(self.consumption_state) is not CoordinatedConsumptionState
            or self.consumption_state is not CoordinatedConsumptionState.UNUSED
        ):
            raise LiveActivationError(LiveActivationFailure.INVALID_CONTEXT)
        fixed_values = (
            (self.authority_effective_timezone, "Asia/Kolkata"),
            (self.authority_expiry_timezone, "Asia/Kolkata"),
            (self.provider_identity, "ZERODHA_KITE"),
            (self.operational_provider, "KITE"),
            (
                self.provider_configuration_ref,
                "ZERODHA-KITE-PROVIDER-CONFIG-PRIMARY",
            ),
            (
                self.application_registration_ref,
                "ZERODHA-KITE-APP-REGISTRATION-PRIMARY",
            ),
            (self.credential_ref, "KITE-API-SECRET-PRIMARY"),
            (
                self.intended_principal_registration_ref,
                "KITE-INTENDED-PRINCIPAL-PRIMARY",
            ),
            (
                self.composition_dependency_set_ref,
                "CAR017-LIVE-COMPOSITION-DEPENDENCY-SET-V1",
            ),
            (self.redirect_url, "http://127.0.0.1:8765/kite/callback"),
            (self.attempt_cardinality, "ONE"),
            (self.provider_availability_authority, "WITHHELD"),
            (self.car014_status, "UNEXECUTED"),
        )
        if any(actual != expected for actual, expected in fixed_values):
            raise LiveActivationError(LiveActivationFailure.INVALID_CONTEXT)

    def exactly_matches(self, other: object) -> bool:
        """Compare every value without datetime instant-normalization."""

        if type(other) is not CoordinatedActivationValues:
            return False
        return (
            self.coordinated_activation_identity
            == other.coordinated_activation_identity
            and self.coordinated_governance_publication_sha
            == other.coordinated_governance_publication_sha
            and self.car016_logical_publication_ref
            == other.car016_logical_publication_ref
            and self.car017_logical_publication_ref
            == other.car017_logical_publication_ref
            and self.frozen_car016_implementation_sha
            == other.frozen_car016_implementation_sha
            and self.frozen_car017_implementation_sha
            == other.frozen_car017_implementation_sha
            and self.authority_effective_at.isoformat()
            == other.authority_effective_at.isoformat()
            and self.authority_effective_timezone
            == other.authority_effective_timezone
            and self.authority_expires_at.isoformat()
            == other.authority_expires_at.isoformat()
            and self.authority_expiry_timezone == other.authority_expiry_timezone
            and self.authentication_attempt_timeout_seconds
            == other.authentication_attempt_timeout_seconds
            and self.sponsor_environment_ref == other.sponsor_environment_ref
            and self.hostname == other.hostname
            and self.provider_identity == other.provider_identity
            and self.operational_provider == other.operational_provider
            and self.provider_configuration_ref == other.provider_configuration_ref
            and self.application_registration_ref
            == other.application_registration_ref
            and self.credential_ref == other.credential_ref
            and self.intended_principal_registration_ref
            == other.intended_principal_registration_ref
            and self.composition_dependency_set_ref
            == other.composition_dependency_set_ref
            and self.redirect_url == other.redirect_url
            and self.attempt_cardinality == other.attempt_cardinality
            and self.provider_availability_authority
            == other.provider_availability_authority
            and self.provider_availability_max_operations
            == other.provider_availability_max_operations
            and self.car014_status == other.car014_status
            and self.consumption_state is other.consumption_state
        )

    def __repr__(self) -> str:
        return "<CoordinatedActivationValues redacted>"

    __str__ = __repr__

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("COORDINATED_ACTIVATION_VALUES_SERIALIZATION_PROHIBITED")


@dataclass(frozen=True, slots=True, repr=False)
class CanonicalRepositoryEvidence:
    """Non-sensitive repository evidence reviewed before capability issuance."""

    branch: str
    head_sha: str
    origin_develop_sha: str
    working_tree_clean: bool
    car016_canonical: bool
    car017_canonical: bool
    car014_unexecuted: bool

    def __post_init__(self) -> None:
        if (
            type(self.branch) is not str
            or _SHA_PATTERN.fullmatch(self.head_sha) is None
            or _SHA_PATTERN.fullmatch(self.origin_develop_sha) is None
            or any(
                type(value) is not bool
                for value in (
                    self.working_tree_clean,
                    self.car016_canonical,
                    self.car017_canonical,
                    self.car014_unexecuted,
                )
            )
        ):
            raise LiveActivationError(
                LiveActivationFailure.INVALID_REPOSITORY_EVIDENCE
            )

    def __repr__(self) -> str:
        return "<CanonicalRepositoryEvidence sanitized>"


class ReviewedActivationCapability:
    """Opaque capability issued only by TrustedActivationReviewer."""

    __slots__ = ("__context", "__kind", "__seal")

    def __new__(cls, *_args: object, **_kwargs: object) -> "ReviewedActivationCapability":
        raise LiveActivationError(LiveActivationFailure.INVALID_PROVENANCE)

    def __repr__(self) -> str:
        return "<ReviewedActivationCapability redacted>"

    __str__ = __repr__

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("REVIEWED_ACTIVATION_CAPABILITY_SERIALIZATION_PROHIBITED")

    def __setattr__(self, _name: str, _value: object) -> None:
        raise AttributeError("REVIEWED_ACTIVATION_CAPABILITY_IMMUTABLE")

    def __copy__(self) -> "ReviewedActivationCapability":
        raise TypeError("REVIEWED_ACTIVATION_CAPABILITY_COPY_PROHIBITED")

    def __deepcopy__(self, _memo: object) -> "ReviewedActivationCapability":
        raise TypeError("REVIEWED_ACTIVATION_CAPABILITY_COPY_PROHIBITED")

    def _is_valid_for(self, values: object) -> bool:
        return (
            getattr(self, "_ReviewedActivationCapability__seal", None)
            is _PROVENANCE_SEAL
            and getattr(self, "_ReviewedActivationCapability__context", None)
            is values
        )

    def _is_live_capable(self) -> bool:
        return (
            getattr(self, "_ReviewedActivationCapability__seal", None)
            is _PROVENANCE_SEAL
            and getattr(self, "_ReviewedActivationCapability__kind", None)
            is ActivationProvenanceKind.CANONICAL_LIVE
        )


class LiveActivationContext:
    """Immutable coordinated context backed by reviewed provenance."""

    __slots__ = ("__capability", "__values")

    def __new__(cls, *_args: object, **_kwargs: object) -> "LiveActivationContext":
        raise LiveActivationError(LiveActivationFailure.INVALID_PROVENANCE)

    def __setattr__(self, _name: str, _value: object) -> None:
        raise AttributeError("LIVE_ACTIVATION_CONTEXT_IMMUTABLE")

    @property
    def coordinated_activation_identity(self) -> str:
        return self.__values.coordinated_activation_identity

    @property
    def coordinated_governance_publication_sha(self) -> str:
        return self.__values.coordinated_governance_publication_sha

    @property
    def authentication_attempt_timeout_seconds(self) -> int:
        return self.__values.authentication_attempt_timeout_seconds

    def _matches_capability(self, capability: object) -> bool:
        return (
            capability is self.__capability
            and type(capability) is ReviewedActivationCapability
            and capability._is_valid_for(self.__values)
        )

    def _matches_values(self, values: object) -> bool:
        return self.__values.exactly_matches(values)

    def _is_live_capable(self) -> bool:
        return self.__capability._is_live_capable()

    def _permits_consumption_at(self, at: datetime) -> bool:
        return (
            _aware(at)
            and self.__values.authority_effective_at
            <= at
            < self.__values.authority_expires_at
            and self.__values.consumption_state
            is CoordinatedConsumptionState.UNUSED
        )

    def __repr__(self) -> str:
        return "<LiveActivationContext redacted>"

    __str__ = __repr__

    def __copy__(self) -> "LiveActivationContext":
        raise TypeError("LIVE_ACTIVATION_CONTEXT_COPY_PROHIBITED")

    def __deepcopy__(self, _memo: object) -> "LiveActivationContext":
        raise TypeError("LIVE_ACTIVATION_CONTEXT_COPY_PROHIBITED")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("LIVE_ACTIVATION_CONTEXT_SERIALIZATION_PROHIBITED")


@dataclass(frozen=True, slots=True, repr=False)
class ActivationReview:
    """One context and its identity-bound opaque capability."""

    context: LiveActivationContext
    capability: ReviewedActivationCapability

    def __repr__(self) -> str:
        return "<ActivationReview redacted>"

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("ACTIVATION_REVIEW_SERIALIZATION_PROHIBITED")


class TrustedActivationReviewer:
    """Issue provenance only after exact canonical evidence verification."""

    __slots__ = ("__kind", "__verifier")

    def __init__(
        self,
        verifier: CanonicalActivationEvidenceVerifier,
        *,
        provenance_kind: ActivationProvenanceKind | None = None,
    ) -> None:
        if (
            not callable(getattr(verifier, "verify", None))
            or type(provenance_kind) is not ActivationProvenanceKind
        ):
            raise LiveActivationError(LiveActivationFailure.INVALID_PROVENANCE)
        self.__verifier = verifier
        self.__kind = provenance_kind

    def review(
        self,
        *,
        expected: CoordinatedActivationValues,
        observed: CoordinatedActivationValues,
        repository_evidence: CanonicalRepositoryEvidence,
        reviewed_at: datetime,
    ) -> ActivationReview:
        """Validate every field and issue one inert reviewed capability."""

        if (
            type(expected) is not CoordinatedActivationValues
            or type(observed) is not CoordinatedActivationValues
            or type(repository_evidence) is not CanonicalRepositoryEvidence
            or not _aware(reviewed_at)
        ):
            raise LiveActivationError(LiveActivationFailure.INVALID_CONTEXT)
        if not expected.exactly_matches(observed):
            raise LiveActivationError(LiveActivationFailure.CONTEXT_MISMATCH)
        if not (
            repository_evidence.branch == "develop"
            and repository_evidence.head_sha
            == expected.coordinated_governance_publication_sha
            and repository_evidence.origin_develop_sha
            == expected.coordinated_governance_publication_sha
            and repository_evidence.working_tree_clean
            and repository_evidence.car016_canonical
            and repository_evidence.car017_canonical
            and repository_evidence.car014_unexecuted
        ):
            raise LiveActivationError(
                LiveActivationFailure.INVALID_REPOSITORY_EVIDENCE
            )
        if not (
            expected.authority_effective_at
            <= reviewed_at
            < expected.authority_expires_at
        ):
            raise LiveActivationError(LiveActivationFailure.OUTSIDE_AUTHORITY_WINDOW)
        try:
            verified = self.__verifier.verify(
                expected,
                observed,
                repository_evidence,
            )
        except Exception:
            raise LiveActivationError(
                LiveActivationFailure.INVALID_PROVENANCE
            ) from None
        if verified is not True:
            raise LiveActivationError(LiveActivationFailure.INVALID_PROVENANCE)

        capability = object.__new__(ReviewedActivationCapability)
        object.__setattr__(
            capability,
            "_ReviewedActivationCapability__context",
            expected,
        )
        object.__setattr__(
            capability,
            "_ReviewedActivationCapability__seal",
            _PROVENANCE_SEAL,
        )
        object.__setattr__(
            capability,
            "_ReviewedActivationCapability__kind",
            self.__kind,
        )
        context = object.__new__(LiveActivationContext)
        object.__setattr__(
            context,
            "_LiveActivationContext__capability",
            capability,
        )
        object.__setattr__(context, "_LiveActivationContext__values", expected)
        return ActivationReview(context=context, capability=capability)


@dataclass(frozen=True, slots=True, repr=False)
class RemainingBudget:
    """Sanitized remaining monotonic lifecycle budget."""

    seconds: float

    def __post_init__(self) -> None:
        if (
            type(self.seconds) is not float
            or not math.isfinite(self.seconds)
            or self.seconds < 0.0
            or self.seconds > _LIFECYCLE_SECONDS
        ):
            raise LiveActivationError(LiveActivationFailure.INVALID_CONTEXT)

    @property
    def exhausted(self) -> bool:
        return self.seconds <= 0.0

    def require_available(self) -> float:
        if self.exhausted:
            raise LiveActivationError(LiveActivationFailure.DEADLINE_EXHAUSTED)
        return self.seconds

    def __repr__(self) -> str:
        return "<RemainingBudget sanitized>"


class MonotonicLifecycleDeadline:
    """Immutable 300-second deadline starting after proven consumption."""

    __slots__ = ("__deadline",)

    def __init__(self, *, monotonic_now: float) -> None:
        if type(monotonic_now) is not float or not math.isfinite(monotonic_now):
            raise LiveActivationError(LiveActivationFailure.INVALID_CONTEXT)
        object.__setattr__(
            self,
            "_MonotonicLifecycleDeadline__deadline",
            monotonic_now + _LIFECYCLE_SECONDS,
        )

    def __setattr__(self, _name: str, _value: object) -> None:
        raise AttributeError("MONOTONIC_DEADLINE_IMMUTABLE")

    def remaining(self, *, monotonic_now: float) -> RemainingBudget:
        if type(monotonic_now) is not float or not math.isfinite(monotonic_now):
            raise LiveActivationError(LiveActivationFailure.INVALID_CONTEXT)
        return RemainingBudget(max(0.0, self.__deadline - monotonic_now))

    def __repr__(self) -> str:
        return "<MonotonicLifecycleDeadline sanitized>"

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("MONOTONIC_DEADLINE_SERIALIZATION_PROHIBITED")


@dataclass(frozen=True, slots=True, repr=False)
class DurableConsumptionRecord:
    """Exact five-key durable record; values are non-sensitive."""

    coordinated_activation_identity: str
    coordinated_governance_publication_sha: str
    consumed_at: str

    def __post_init__(self) -> None:
        if not valid_activation_identity(self.coordinated_activation_identity):
            raise LiveActivationError(
                LiveActivationFailure.INVALID_CONSUMPTION_RECORD
            )
        if (
            type(self.coordinated_governance_publication_sha) is not str
            or _SHA_PATTERN.fullmatch(
                self.coordinated_governance_publication_sha
            )
            is None
            or type(self.consumed_at) is not str
            or _RFC3339_OFFSET_PATTERN.fullmatch(self.consumed_at) is None
        ):
            raise LiveActivationError(
                LiveActivationFailure.INVALID_CONSUMPTION_RECORD
            )
        try:
            parsed = datetime.fromisoformat(self.consumed_at)
        except ValueError:
            raise LiveActivationError(
                LiveActivationFailure.INVALID_CONSUMPTION_RECORD
            ) from None
        if not _aware(parsed):
            raise LiveActivationError(
                LiveActivationFailure.INVALID_CONSUMPTION_RECORD
            )

    def to_bytes(self) -> bytes:
        values = {
            "schema_version": "1.0",
            "coordinated_activation_identity": self.coordinated_activation_identity,
            "coordinated_governance_publication_sha": (
                self.coordinated_governance_publication_sha
            ),
            "consumption_state": "CONSUMED",
            "consumed_at": self.consumed_at,
        }
        payload = json.dumps(
            values,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(payload) > _CONSUMPTION_RECORD_MAX_BYTES:
            raise LiveActivationError(
                LiveActivationFailure.INVALID_CONSUMPTION_RECORD
            )
        return payload

    def __repr__(self) -> str:
        return "<DurableConsumptionRecord sanitized>"


@dataclass(frozen=True, slots=True, repr=False)
class ProvenConsumption:
    """Proof that durable consumption completed before deadline creation."""

    record: DurableConsumptionRecord
    deadline: MonotonicLifecycleDeadline
    ledger: SanitizedOperationLedger

    def __repr__(self) -> str:
        return "<ProvenConsumption sanitized>"

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("PROVEN_CONSUMPTION_SERIALIZATION_PROHIBITED")


@dataclass(frozen=True, slots=True, repr=False)
class DurableConsumptionResult:
    """Sanitized outcome of the injected durable-consumption operation."""

    category: ConsumptionOutcomeCategory
    proof: ProvenConsumption | None

    def __post_init__(self) -> None:
        if type(self.category) is not ConsumptionOutcomeCategory:
            raise LiveActivationError(LiveActivationFailure.INVALID_CONTEXT)
        if (self.category is ConsumptionOutcomeCategory.CONSUMED) != (
            type(self.proof) is ProvenConsumption
        ):
            raise LiveActivationError(LiveActivationFailure.INVALID_CONTEXT)

    def __repr__(self) -> str:
        return "<DurableConsumptionResult sanitized>"


class DurableConsumptionCoordinator:
    """Execute the frozen persistence order only through an injected boundary."""

    __slots__ = ("__filesystem", "__sponsor_home", "__sponsor_user_id")

    def __init__(
        self,
        *,
        filesystem: DurableConsumptionFilesystem,
        sponsor_home: str,
        sponsor_user_id: int,
    ) -> None:
        if not all(
            callable(getattr(filesystem, name, None))
            for name in (
                "open_verified_parent_directory",
                "create_exclusive_nofollow",
                "verify_open_file",
                "write_all",
                "flush_file",
                "fsync_file",
                "close_file",
                "fsync_directory",
                "close_directory",
            )
        ):
            raise LiveActivationError(
                LiveActivationFailure.FILESYSTEM_CAPABILITY_UNAVAILABLE_STOP_ESCALATE
            )
        if (
            type(sponsor_home) is not str
            or not sponsor_home.startswith("/")
            or ".." in PurePath(sponsor_home).parts
            or type(sponsor_user_id) is not int
            or sponsor_user_id < 0
        ):
            raise LiveActivationError(LiveActivationFailure.INVALID_CONTEXT)
        self.__filesystem = filesystem
        self.__sponsor_home = sponsor_home.rstrip("/")
        self.__sponsor_user_id = sponsor_user_id

    def consume(
        self,
        *,
        context: LiveActivationContext,
        capability: ReviewedActivationCapability,
        sponsor_confirmed: bool,
        consumed_at: datetime,
        monotonic_now: float,
        ledger: SanitizedOperationLedger,
    ) -> DurableConsumptionResult:
        """Persist one terminal CONSUMED record or fail closed."""

        if (
            type(context) is not LiveActivationContext
            or type(capability) is not ReviewedActivationCapability
            or not context._matches_capability(capability)
            or type(sponsor_confirmed) is not bool
            or not _aware(consumed_at)
            or not context._permits_consumption_at(consumed_at)
            or type(monotonic_now) is not float
            or not math.isfinite(monotonic_now)
            or type(ledger) is not SanitizedOperationLedger
            or ledger.count_for(
                GovernedAuthenticationOperation.AUTHORITY_CONSUMPTION
            )
            != 0
            or ledger.count_for(
                GovernedAuthenticationOperation.PROVIDER_AVAILABILITY_VERIFICATION
            )
            != 0
        ):
            return DurableConsumptionResult(
                ConsumptionOutcomeCategory.PRE_CONSUMPTION_VALIDATION_FAILED,
                None,
            )
        if not sponsor_confirmed:
            return DurableConsumptionResult(
                ConsumptionOutcomeCategory.PRE_CONSUMPTION_VALIDATION_FAILED,
                None,
            )

        directory = f"{self.__sponsor_home}/{_CONSUMPTION_DIRECTORY_SUFFIX}"
        filename = consumption_filename(context.coordinated_activation_identity)
        record = DurableConsumptionRecord(
            coordinated_activation_identity=context.coordinated_activation_identity,
            coordinated_governance_publication_sha=(
                context.coordinated_governance_publication_sha
            ),
            consumed_at=consumed_at.isoformat(),
        )
        payload = record.to_bytes()
        parent_descriptor: object | None = None
        file_descriptor: object | None = None
        try:
            parent_descriptor = self.__filesystem.open_verified_parent_directory(
                directory,
                expected_owner=self.__sponsor_user_id,
                expected_mode=_DIRECTORY_MODE,
            )
            file_descriptor = self.__filesystem.create_exclusive_nofollow(
                parent_descriptor,
                filename,
                mode=_FILE_MODE,
            )
            self.__filesystem.verify_open_file(
                file_descriptor,
                expected_owner=self.__sponsor_user_id,
                expected_mode=_FILE_MODE,
                expected_link_count=1,
            )
            self.__filesystem.write_all(file_descriptor, payload)
            self.__filesystem.flush_file(file_descriptor)
            self.__filesystem.fsync_file(file_descriptor)
            self.__filesystem.verify_open_file(
                file_descriptor,
                expected_owner=self.__sponsor_user_id,
                expected_mode=_FILE_MODE,
                expected_link_count=1,
            )
            self.__filesystem.close_file(file_descriptor)
            file_descriptor = None
            self.__filesystem.fsync_directory(parent_descriptor)
            self.__filesystem.close_directory(parent_descriptor)
            parent_descriptor = None
        except Exception:
            if file_descriptor is not None:
                try:
                    self.__filesystem.close_file(file_descriptor)
                except Exception:
                    pass
            if parent_descriptor is not None:
                try:
                    self.__filesystem.close_directory(parent_descriptor)
                except Exception:
                    pass
            return DurableConsumptionResult(
                ConsumptionOutcomeCategory.POST_CONFIRMATION_CONSUMPTION_UNCERTAIN,
                None,
            )

        deadline = MonotonicLifecycleDeadline(monotonic_now=monotonic_now)
        consumed_ledger = ledger.record(
            GovernedAuthenticationOperation.AUTHORITY_CONSUMPTION
        )
        return DurableConsumptionResult(
            ConsumptionOutcomeCategory.CONSUMED,
            ProvenConsumption(
                record=record,
                deadline=deadline,
                ledger=consumed_ledger,
            ),
        )


def valid_activation_identity(value: object) -> bool:
    """Return true only for the exact ASCII filename-safe identity grammar."""

    return (
        type(value) is str
        and 1 <= len(value) <= 128
        and value.isascii()
        and _ACTIVATION_IDENTITY_PATTERN.fullmatch(value) is not None
    )


def consumption_filename(identity: object) -> str:
    """Map one already valid identity to its exact record filename."""

    if not valid_activation_identity(identity):
        raise LiveActivationError(LiveActivationFailure.INVALID_ACTIVATION_IDENTITY)
    return f"{identity}.json"


def parse_consumption_record(payload: object) -> DurableConsumptionRecord:
    """Strictly parse one deterministic UTF-8 durable record."""

    if (
        type(payload) is not bytes
        or len(payload) == 0
        or len(payload) > _CONSUMPTION_RECORD_MAX_BYTES
        or payload.startswith(b"\xef\xbb\xbf")
    ):
        raise LiveActivationError(LiveActivationFailure.INVALID_CONSUMPTION_RECORD)
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise LiveActivationError(
            LiveActivationFailure.INVALID_CONSUMPTION_RECORD
        ) from None

    def pairs_hook(pairs: list[tuple[str, object]]) -> dict[str, object]:
        keys = tuple(key for key, _value in pairs)
        if len(set(keys)) != len(keys) or keys != _RECORD_KEYS:
            raise LiveActivationError(
                LiveActivationFailure.INVALID_CONSUMPTION_RECORD
            )
        return dict(pairs)

    def reject_constant(_value: str) -> object:
        raise LiveActivationError(LiveActivationFailure.INVALID_CONSUMPTION_RECORD)

    try:
        parsed = json.loads(
            text,
            object_pairs_hook=pairs_hook,
            parse_constant=reject_constant,
        )
    except (json.JSONDecodeError, LiveActivationError, TypeError, ValueError):
        raise LiveActivationError(
            LiveActivationFailure.INVALID_CONSUMPTION_RECORD
        ) from None
    if type(parsed) is not dict or any(type(value) is not str for value in parsed.values()):
        raise LiveActivationError(LiveActivationFailure.INVALID_CONSUMPTION_RECORD)
    if parsed["schema_version"] != "1.0" or parsed["consumption_state"] != "CONSUMED":
        raise LiveActivationError(LiveActivationFailure.INVALID_CONSUMPTION_RECORD)
    return DurableConsumptionRecord(
        coordinated_activation_identity=parsed["coordinated_activation_identity"],
        coordinated_governance_publication_sha=parsed[
            "coordinated_governance_publication_sha"
        ],
        consumed_at=parsed["consumed_at"],
    )


def _aware(value: object) -> bool:
    return (
        type(value) is datetime
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


__all__ = [
    "ActivationProvenanceKind",
    "ActivationReview",
    "CanonicalRepositoryEvidence",
    "CoordinatedActivationValues",
    "DurableConsumptionCoordinator",
    "DurableConsumptionRecord",
    "DurableConsumptionResult",
    "LiveActivationContext",
    "LiveActivationError",
    "LiveActivationFailure",
    "MonotonicLifecycleDeadline",
    "ProvenConsumption",
    "RemainingBudget",
    "ReviewedActivationCapability",
    "TrustedActivationReviewer",
    "consumption_filename",
    "parse_consumption_record",
    "valid_activation_identity",
]
