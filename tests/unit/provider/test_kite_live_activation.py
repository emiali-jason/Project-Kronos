import copy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import importlib
import json
import pickle

import pytest

from kronos.provider.kite.live_activation import (
    ActivationProvenanceKind,
    CanonicalRepositoryEvidence,
    CoordinatedActivationValues,
    DurableConsumptionCoordinator,
    DurableConsumptionRecord,
    LiveActivationContext,
    LiveActivationError,
    LiveActivationFailure,
    MonotonicLifecycleDeadline,
    ReviewedActivationCapability,
    TrustedActivationReviewer,
    consumption_filename,
    parse_consumption_record,
    valid_activation_identity,
)
from kronos.provider.models.authentication import (
    AuthenticationModelError,
    AuthenticationModelFailure,
    ConsumptionOutcomeCategory,
    CoordinatedConsumptionState,
    GovernedAuthenticationOperation,
    SanitizedOperationCount,
    SanitizedOperationLedger,
)


PUBLICATION_SHA = "a" * 40
CAR016_SHA = "b" * 40
CAR017_SHA = "c" * 40
IDENTITY = "KRONOS-COORD-AUTH-20260803-001"
NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))


class _Verifier:
    def __init__(self, result: object = True, *, raises: bool = False) -> None:
        self.calls = 0
        self.result = result
        self.raises = raises

    def verify(self, expected, observed, repository_evidence):  # type: ignore[no-untyped-def]
        self.calls += 1
        if self.raises:
            raise RuntimeError("raw verifier detail")
        assert expected is observed or expected.exactly_matches(observed)
        assert repository_evidence.branch == "develop"
        return self.result


class _FakeFilesystem:
    def __init__(self, fail_at: str | None = None) -> None:
        self.fail_at = fail_at
        self.calls: list[tuple[object, ...]] = []
        self.parent = object()
        self.file = object()
        self.payload: bytes | None = None

    def _record(self, name: str, *args: object) -> None:
        self.calls.append((name, *args))
        occurrence = sum(call[0] == name for call in self.calls)
        if self.fail_at in (name, f"{name}:{occurrence}"):
            raise OSError("raw filesystem detail")

    def open_verified_parent_directory(
        self, directory: str, *, expected_owner: int, expected_mode: int
    ) -> object:
        self._record("open_parent", directory, expected_owner, expected_mode)
        return self.parent

    def create_exclusive_nofollow(
        self, parent_descriptor: object, filename: str, *, mode: int
    ) -> object:
        self._record("create", parent_descriptor, filename, mode)
        return self.file

    def verify_open_file(
        self,
        file_descriptor: object,
        *,
        expected_owner: int,
        expected_mode: int,
        expected_link_count: int,
    ) -> None:
        self._record(
            "verify",
            file_descriptor,
            expected_owner,
            expected_mode,
            expected_link_count,
        )

    def write_all(self, file_descriptor: object, payload: bytes) -> None:
        self.payload = payload
        self._record("write", file_descriptor, payload)

    def flush_file(self, file_descriptor: object) -> None:
        self._record("flush", file_descriptor)

    def fsync_file(self, file_descriptor: object) -> None:
        self._record("fsync_file", file_descriptor)

    def close_file(self, file_descriptor: object) -> None:
        self._record("close_file", file_descriptor)

    def fsync_directory(self, parent_descriptor: object) -> None:
        self._record("fsync_directory", parent_descriptor)

    def close_directory(self, parent_descriptor: object) -> None:
        self._record("close_directory", parent_descriptor)


def _values(**changes: object) -> CoordinatedActivationValues:
    values: dict[str, object] = {
        "coordinated_activation_identity": IDENTITY,
        "coordinated_governance_publication_sha": PUBLICATION_SHA,
        "car016_logical_publication_ref": "CAR-016-V1.2-KRONOS-COORD-AUTH-20260803-001",
        "car017_logical_publication_ref": "CAR-017-V1.2-KRONOS-COORD-AUTH-20260803-001",
        "frozen_car016_implementation_sha": CAR016_SHA,
        "frozen_car017_implementation_sha": CAR017_SHA,
        "authority_effective_at": NOW - timedelta(days=1),
        "authority_effective_timezone": "Asia/Kolkata",
        "authority_expires_at": NOW + timedelta(days=6),
        "authority_expiry_timezone": "Asia/Kolkata",
        "authentication_attempt_timeout_seconds": 300,
        "sponsor_environment_ref": "SPONSOR-MACOS-LOCAL-NONPROD-01",
        "hostname": "Imrans-Mac-mini.local",
        "provider_identity": "ZERODHA_KITE",
        "operational_provider": "KITE",
        "provider_configuration_ref": "ZERODHA-KITE-PROVIDER-CONFIG-PRIMARY",
        "application_registration_ref": "ZERODHA-KITE-APP-REGISTRATION-PRIMARY",
        "credential_ref": "KITE-API-SECRET-PRIMARY",
        "intended_principal_registration_ref": "KITE-INTENDED-PRINCIPAL-PRIMARY",
        "composition_dependency_set_ref": "CAR017-LIVE-COMPOSITION-DEPENDENCY-SET-V1",
        "redirect_url": "http://127.0.0.1:8765/kite/callback",
        "attempt_cardinality": "ONE",
        "provider_availability_authority": "WITHHELD",
        "provider_availability_max_operations": 0,
        "car014_status": "UNEXECUTED",
        "consumption_state": CoordinatedConsumptionState.UNUSED,
    }
    values.update(changes)
    return CoordinatedActivationValues(**values)  # type: ignore[arg-type]


def _repository(**changes: object) -> CanonicalRepositoryEvidence:
    values: dict[str, object] = {
        "branch": "develop",
        "head_sha": PUBLICATION_SHA,
        "origin_develop_sha": PUBLICATION_SHA,
        "working_tree_clean": True,
        "car016_canonical": True,
        "car017_canonical": True,
        "car014_unexecuted": True,
    }
    values.update(changes)
    return CanonicalRepositoryEvidence(**values)  # type: ignore[arg-type]


def _review(
    *,
    expected: CoordinatedActivationValues | None = None,
    observed: CoordinatedActivationValues | None = None,
    repository: CanonicalRepositoryEvidence | None = None,
    reviewed_at: datetime = NOW,
    verifier: _Verifier | None = None,
):
    expected_values = expected or _values()
    return TrustedActivationReviewer(
        verifier or _Verifier(),
        provenance_kind=ActivationProvenanceKind.FAKE_ONLY,
    ).review(
        expected=expected_values,
        observed=observed or expected_values,
        repository_evidence=repository or _repository(),
        reviewed_at=reviewed_at,
    )


def _coordinator(filesystem: _FakeFilesystem) -> DurableConsumptionCoordinator:
    return DurableConsumptionCoordinator(
        filesystem=filesystem,
        sponsor_home="/Users/sponsor",
        sponsor_user_id=501,
    )


def test_exact_context_and_repository_evidence_issue_one_capability() -> None:
    verifier = _Verifier()
    expected = _values()
    review = _review(expected=expected, verifier=verifier)

    assert verifier.calls == 1
    assert type(review.context) is LiveActivationContext
    assert type(review.capability) is ReviewedActivationCapability
    assert review.context._matches_capability(review.capability)
    assert review.context._matches_values(expected)
    assert review.context.coordinated_activation_identity == IDENTITY
    assert review.context.coordinated_governance_publication_sha == PUBLICATION_SHA
    assert review.context.authentication_attempt_timeout_seconds == 300
    assert review.context._is_live_capable() is False


def test_direct_context_and_capability_construction_is_prohibited() -> None:
    with pytest.raises(LiveActivationError) as context_error:
        LiveActivationContext()
    with pytest.raises(LiveActivationError) as capability_error:
        ReviewedActivationCapability()

    assert context_error.value.failure is LiveActivationFailure.INVALID_PROVENANCE
    assert capability_error.value.failure is LiveActivationFailure.INVALID_PROVENANCE


def test_context_is_immutable_redacted_non_copyable_and_non_serializable() -> None:
    review = _review()

    assert repr(review.context) == "<LiveActivationContext redacted>"
    assert repr(review.capability) == "<ReviewedActivationCapability redacted>"
    assert PUBLICATION_SHA not in repr(review)
    with pytest.raises(AttributeError):
        review.context.value = "changed"  # type: ignore[attr-defined]
    with pytest.raises(TypeError):
        copy.copy(review.context)
    with pytest.raises(TypeError):
        copy.deepcopy(review.context)
    with pytest.raises((TypeError, pickle.PicklingError)):
        pickle.dumps(review.context)
    with pytest.raises((TypeError, pickle.PicklingError)):
        pickle.dumps(review.capability)
    with pytest.raises(TypeError):
        copy.copy(review.capability)
    with pytest.raises(TypeError):
        copy.deepcopy(review.capability)


def test_import_and_ambient_values_create_no_live_authority() -> None:
    module = importlib.import_module("kronos.provider.kite.live_activation")

    assert not any(type(value) is LiveActivationContext for value in vars(module).values())
    for ambient in ("LIVE", {"authority": True}, ["--live"], object(), module):
        with pytest.raises(LiveActivationError):
            TrustedActivationReviewer(ambient)  # type: ignore[arg-type]


def test_provenance_kind_is_mandatory_and_exact() -> None:
    with pytest.raises(LiveActivationError) as missing:
        TrustedActivationReviewer(_Verifier())
    with pytest.raises(LiveActivationError) as synthetic:
        TrustedActivationReviewer(
            _Verifier(),
            provenance_kind="CANONICAL_LIVE",  # type: ignore[arg-type]
        )

    assert missing.value.failure is LiveActivationFailure.INVALID_PROVENANCE
    assert synthetic.value.failure is LiveActivationFailure.INVALID_PROVENANCE


def test_missing_nofollow_filesystem_capability_requires_escalation() -> None:
    with pytest.raises(LiveActivationError) as captured:
        DurableConsumptionCoordinator(
            filesystem=object(),  # type: ignore[arg-type]
            sponsor_home="/Users/sponsor",
            sponsor_user_id=501,
        )

    assert (
        captured.value.failure
        is LiveActivationFailure.FILESYSTEM_CAPABILITY_UNAVAILABLE_STOP_ESCALATE
    )


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("coordinated_activation_identity", "KRONOS-COORD-AUTH-20260803-002"),
        ("coordinated_governance_publication_sha", "d" * 40),
        ("car016_logical_publication_ref", "CAR-016-OTHER"),
        ("car017_logical_publication_ref", "CAR-017-OTHER"),
        ("frozen_car016_implementation_sha", "e" * 40),
        ("frozen_car017_implementation_sha", "f" * 40),
        ("authority_effective_at", NOW - timedelta(hours=1)),
        ("authority_expires_at", NOW + timedelta(hours=1)),
        ("sponsor_environment_ref", "SPONSOR-MACOS-LOCAL-NONPROD-02"),
        ("hostname", "Other-Mac.local"),
    ],
)
def test_every_variable_coordinated_reference_is_exact(
    field: str, replacement: object
) -> None:
    expected = _values()
    observed = replace(expected, **{field: replacement})

    with pytest.raises(LiveActivationError) as captured:
        _review(expected=expected, observed=observed)

    assert captured.value.failure is LiveActivationFailure.CONTEXT_MISMATCH


def test_equivalent_instant_with_different_numeric_offset_is_not_exact() -> None:
    expected = _values()
    observed = replace(
        expected,
        authority_effective_at=expected.authority_effective_at.astimezone(timezone.utc),
    )

    with pytest.raises(LiveActivationError) as captured:
        _review(expected=expected, observed=observed)

    assert captured.value.failure is LiveActivationFailure.CONTEXT_MISMATCH


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("authentication_attempt_timeout_seconds", 299),
        ("authority_effective_timezone", "Asia/Calcutta"),
        ("authority_expiry_timezone", "UTC"),
        ("provider_identity", "zerodha_kite"),
        ("operational_provider", "ZERODHA_KITE"),
        ("provider_configuration_ref", "zerodha-kite-provider-config-primary"),
        ("application_registration_ref", "ZERODHA-KITE-APP-REGISTRATION-primary"),
        ("credential_ref", "kite-api-secret-primary"),
        ("intended_principal_registration_ref", "kite-intended-principal-primary"),
        ("composition_dependency_set_ref", "car017-live-composition-dependency-set-v1"),
        ("redirect_url", "http://localhost:8765/kite/callback"),
        ("attempt_cardinality", "TWO"),
        ("provider_availability_authority", "AUTHORIZED"),
        ("provider_availability_max_operations", 1),
        ("car014_status", "EXECUTED"),
        ("consumption_state", CoordinatedConsumptionState.CONSUMED),
    ],
)
def test_fixed_coordinated_contract_values_fail_closed(
    field: str, replacement: object
) -> None:
    with pytest.raises(LiveActivationError) as captured:
        _values(**{field: replacement})

    assert captured.value.failure is LiveActivationFailure.INVALID_CONTEXT


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("branch", "main"),
        ("head_sha", "d" * 40),
        ("origin_develop_sha", "d" * 40),
        ("working_tree_clean", False),
        ("car016_canonical", False),
        ("car017_canonical", False),
        ("car014_unexecuted", False),
    ],
)
def test_repository_and_publication_provenance_fail_closed(
    field: str, replacement: object
) -> None:
    with pytest.raises(LiveActivationError) as captured:
        _review(repository=_repository(**{field: replacement}))

    assert captured.value.failure is LiveActivationFailure.INVALID_REPOSITORY_EVIDENCE


@pytest.mark.parametrize("reviewed_at", [NOW - timedelta(days=2), NOW + timedelta(days=7)])
def test_activation_window_is_effective_inclusive_and_expiry_exclusive(
    reviewed_at: datetime,
) -> None:
    with pytest.raises(LiveActivationError) as captured:
        _review(reviewed_at=reviewed_at)

    assert captured.value.failure is LiveActivationFailure.OUTSIDE_AUTHORITY_WINDOW


@pytest.mark.parametrize("verifier", [_Verifier(False), _Verifier(raises=True)])
def test_untrusted_or_failed_provenance_is_sanitized(verifier: _Verifier) -> None:
    with pytest.raises(LiveActivationError) as captured:
        _review(verifier=verifier)

    assert captured.value.failure is LiveActivationFailure.INVALID_PROVENANCE
    assert "raw" not in str(captured.value)


@pytest.mark.parametrize(
    "identity",
    ["A", "A0", "A_B-C", "A" + "B" * 127],
)
def test_activation_identity_exact_grammar_accepts_valid_values(identity: str) -> None:
    assert valid_activation_identity(identity)
    assert consumption_filename(identity) == f"{identity}.json"


@pytest.mark.parametrize(
    "identity",
    [
        "",
        "_ABC",
        "ABC_",
        "abc",
        "A/B",
        "A\\B",
        "A%2FB",
        " A",
        "A ",
        "Å",
        "A" * 129,
    ],
)
def test_activation_identity_rejects_normalization_aliases_and_paths(
    identity: str,
) -> None:
    assert not valid_activation_identity(identity)
    with pytest.raises(LiveActivationError) as captured:
        consumption_filename(identity)
    assert captured.value.failure is LiveActivationFailure.INVALID_ACTIVATION_IDENTITY


def _record() -> DurableConsumptionRecord:
    return DurableConsumptionRecord(
        coordinated_activation_identity=IDENTITY,
        coordinated_governance_publication_sha=PUBLICATION_SHA,
        consumed_at="2026-08-04T12:00:00+05:30",
    )


def test_consumption_record_round_trip_is_exact_deterministic_utf8() -> None:
    payload = _record().to_bytes()

    assert len(payload) <= 1024
    assert not payload.startswith(b"\xef\xbb\xbf")
    assert tuple(json.loads(payload).keys()) == (
        "schema_version",
        "coordinated_activation_identity",
        "coordinated_governance_publication_sha",
        "consumption_state",
        "consumed_at",
    )
    assert parse_consumption_record(payload) == _record()
    assert payload == _record().to_bytes()
    assert parse_consumption_record(payload + b" \n\t") == _record()


@pytest.mark.parametrize(
    "payload",
    [
        b"\xef\xbb\xbf{}",
        b"x" * 1025,
        b"[]",
        b'{"schema_version":"1.0","schema_version":"1.0"}',
        b'{"schema_version":"1.0","unknown":"x"}',
        b'{"schema_version":"1.0"}',
        b'{/* comment */"schema_version":"1.0"}',
        b"{} trailing",
        b"\xff",
        b' {"schema_version":"1.0"} ',
    ],
)
def test_strict_parser_rejects_bom_size_shape_keys_comments_and_trailing_content(
    payload: bytes,
) -> None:
    with pytest.raises(LiveActivationError) as captured:
        parse_consumption_record(payload)
    assert captured.value.failure is LiveActivationFailure.INVALID_CONSUMPTION_RECORD


@pytest.mark.parametrize(
    "consumed_at",
    [
        "2026-08-04T12:00:00Z",
        "2026-08-04T12:00:00",
        "2026-08-04 12:00:00+05:30",
        "not-a-timestamp",
    ],
)
def test_consumed_at_requires_rfc3339_numeric_offset(consumed_at: str) -> None:
    with pytest.raises(LiveActivationError) as captured:
        DurableConsumptionRecord(
            coordinated_activation_identity=IDENTITY,
            coordinated_governance_publication_sha=PUBLICATION_SHA,
            consumed_at=consumed_at,
        )
    assert captured.value.failure is LiveActivationFailure.INVALID_CONSUMPTION_RECORD


def test_descriptor_relative_consumption_order_and_exact_properties() -> None:
    filesystem = _FakeFilesystem()
    review = _review()
    ledger = SanitizedOperationLedger.empty()

    result = _coordinator(filesystem).consume(
        context=review.context,
        capability=review.capability,
        sponsor_confirmed=True,
        consumed_at=NOW,
        monotonic_now=100.0,
        ledger=ledger,
    )

    assert result.category is ConsumptionOutcomeCategory.CONSUMED
    assert result.proof is not None
    assert [call[0] for call in filesystem.calls] == [
        "open_parent",
        "create",
        "verify",
        "write",
        "flush",
        "fsync_file",
        "verify",
        "close_file",
        "fsync_directory",
        "close_directory",
    ]
    assert filesystem.calls[0] == (
        "open_parent",
        "/Users/sponsor/Library/Application Support/KRONOS/provider-authentication/activation-consumption",
        501,
        0o700,
    )
    assert filesystem.calls[1] == ("create", filesystem.parent, f"{IDENTITY}.json", 0o600)
    assert filesystem.calls[2] == ("verify", filesystem.file, 501, 0o600, 1)
    assert filesystem.calls[6] == ("verify", filesystem.file, 501, 0o600, 1)
    assert parse_consumption_record(filesystem.payload or b"") == result.proof.record
    assert result.proof.ledger.count_for(
        GovernedAuthenticationOperation.AUTHORITY_CONSUMPTION
    ) == 1
    assert result.proof.deadline.remaining(monotonic_now=100.0).seconds == 300.0


@pytest.mark.parametrize(
    "failure",
    [
        "open_parent",
        "create",
        "verify",
        "verify:2",
        "write",
        "flush",
        "fsync_file",
        "close_file",
        "fsync_directory",
        "close_directory",
    ],
)
def test_every_persistence_uncertainty_fails_closed_without_proof(
    failure: str,
) -> None:
    filesystem = _FakeFilesystem(fail_at=failure)
    review = _review()

    result = _coordinator(filesystem).consume(
        context=review.context,
        capability=review.capability,
        sponsor_confirmed=True,
        consumed_at=NOW,
        monotonic_now=100.0,
        ledger=SanitizedOperationLedger.empty(),
    )

    assert (
        result.category
        is ConsumptionOutcomeCategory.POST_CONFIRMATION_CONSUMPTION_UNCERTAIN
    )
    assert result.proof is None
    assert not any(call[0] in {"attempt", "listener", "browser"} for call in filesystem.calls)


def test_pre_consumption_failure_runs_no_filesystem_operation() -> None:
    filesystem = _FakeFilesystem()
    review = _review()

    result = _coordinator(filesystem).consume(
        context=review.context,
        capability=review.capability,
        sponsor_confirmed=False,
        consumed_at=NOW,
        monotonic_now=100.0,
        ledger=SanitizedOperationLedger.empty(),
    )

    assert result.category is ConsumptionOutcomeCategory.PRE_CONSUMPTION_VALIDATION_FAILED
    assert result.proof is None
    assert filesystem.calls == []


@pytest.mark.parametrize(
    ("consumed_at", "monotonic_now"),
    [
        (NOW - timedelta(days=2), 100.0),
        (NOW + timedelta(days=7), 100.0),
        (NOW, float("nan")),
        (NOW, float("inf")),
    ],
)
def test_invalid_consumption_time_or_monotonic_source_is_prevalidation_failure(
    consumed_at: datetime,
    monotonic_now: float,
) -> None:
    filesystem = _FakeFilesystem()
    review = _review()

    result = _coordinator(filesystem).consume(
        context=review.context,
        capability=review.capability,
        sponsor_confirmed=True,
        consumed_at=consumed_at,
        monotonic_now=monotonic_now,
        ledger=SanitizedOperationLedger.empty(),
    )

    assert result.category is ConsumptionOutcomeCategory.PRE_CONSUMPTION_VALIDATION_FAILED
    assert filesystem.calls == []


def test_previously_consumed_ledger_is_rejected_before_filesystem() -> None:
    filesystem = _FakeFilesystem()
    review = _review()
    ledger = SanitizedOperationLedger.empty().record(
        GovernedAuthenticationOperation.AUTHORITY_CONSUMPTION
    )

    result = _coordinator(filesystem).consume(
        context=review.context,
        capability=review.capability,
        sponsor_confirmed=True,
        consumed_at=NOW,
        monotonic_now=100.0,
        ledger=ledger,
    )

    assert result.category is ConsumptionOutcomeCategory.PRE_CONSUMPTION_VALIDATION_FAILED
    assert filesystem.calls == []


def test_wrong_capability_is_rejected_before_filesystem_operation() -> None:
    filesystem = _FakeFilesystem()
    one = _review()
    other = _review()

    result = _coordinator(filesystem).consume(
        context=one.context,
        capability=other.capability,
        sponsor_confirmed=True,
        consumed_at=NOW,
        monotonic_now=100.0,
        ledger=SanitizedOperationLedger.empty(),
    )

    assert result.category is ConsumptionOutcomeCategory.PRE_CONSUMPTION_VALIDATION_FAILED
    assert filesystem.calls == []


def test_deadline_is_monotonic_fixed_and_exhaustion_prevents_operation() -> None:
    deadline = MonotonicLifecycleDeadline(monotonic_now=50.0)

    assert deadline.remaining(monotonic_now=50.0).require_available() == 300.0
    assert deadline.remaining(monotonic_now=349.5).require_available() == 0.5
    exhausted = deadline.remaining(monotonic_now=350.0)
    assert exhausted.seconds == 0.0
    assert exhausted.exhausted
    with pytest.raises(LiveActivationError) as captured:
        exhausted.require_available()
    assert captured.value.failure is LiveActivationFailure.DEADLINE_EXHAUSTED


def test_deadline_is_immutable_redacted_and_non_serializable() -> None:
    deadline = MonotonicLifecycleDeadline(monotonic_now=50.0)

    assert repr(deadline) == "<MonotonicLifecycleDeadline sanitized>"
    with pytest.raises(AttributeError):
        deadline.value = 10.0  # type: ignore[attr-defined]
    with pytest.raises((TypeError, pickle.PicklingError)):
        pickle.dumps(deadline)


def test_sanitized_ledger_has_all_operations_once_and_availability_zero() -> None:
    ledger = SanitizedOperationLedger.empty()

    assert tuple(item.operation for item in ledger.counts) == tuple(
        GovernedAuthenticationOperation
    )
    assert all(item.count == 0 for item in ledger.counts)
    recorded = ledger.record(GovernedAuthenticationOperation.ACTIVATION_VALIDATION)
    assert recorded.count_for(GovernedAuthenticationOperation.ACTIVATION_VALIDATION) == 1
    assert ledger.count_for(GovernedAuthenticationOperation.ACTIVATION_VALIDATION) == 0
    with pytest.raises(AuthenticationModelError) as duplicate:
        recorded.record(GovernedAuthenticationOperation.ACTIVATION_VALIDATION)
    assert duplicate.value.failure is AuthenticationModelFailure.OPERATION_CARDINALITY_EXCEEDED
    with pytest.raises(AuthenticationModelError) as withheld:
        ledger.record(GovernedAuthenticationOperation.PROVIDER_AVAILABILITY_VERIFICATION)
    assert withheld.value.failure is AuthenticationModelFailure.PROVIDER_AVAILABILITY_WITHHELD


def test_ledger_rejects_incomplete_order_and_sensitive_serialization() -> None:
    with pytest.raises(AuthenticationModelError):
        SanitizedOperationLedger(
            (SanitizedOperationCount(GovernedAuthenticationOperation.LOCAL_CLEANUP, 0),)
        )

    ledger = SanitizedOperationLedger.empty()
    assert repr(ledger) == "<SanitizedOperationLedger counts-only>"
    with pytest.raises((TypeError, pickle.PicklingError)):
        pickle.dumps(ledger)


def test_stage1_types_contain_no_external_effect_dependencies() -> None:
    module = importlib.import_module("kronos.provider.kite.live_activation")
    rendered = " ".join(vars(module))

    assert "kiteconnect" not in rendered.lower()
    assert "webbrowser" not in rendered.lower()
    assert "socket" not in rendered.lower()
    assert "subprocess" not in rendered.lower()
