from __future__ import annotations

import copy
import pickle

import pytest

from kronos.configuration.credentials import (
    CredentialRetrievalOutcome,
    OneUseSecretLease,
    SecretLeaseError,
    SecretLeaseFailure,
)


SYNTHETIC_SECRET = "SYNTHETIC_SECRET_MARKER"


def test_credential_outcomes_are_exact_and_sanitized() -> None:
    assert [outcome.value for outcome in CredentialRetrievalOutcome] == [
        "FOUND",
        "MISSING",
        "ACCESS_DENIED",
        "BACKEND_UNAVAILABLE",
        "TIMED_OUT",
        "MALFORMED",
    ]


@pytest.mark.parametrize("invalid", ["", None, 7])
def test_secret_lease_rejects_invalid_secret_without_echoing_it(invalid: object) -> None:
    with pytest.raises(SecretLeaseError) as captured:
        OneUseSecretLease(invalid)  # type: ignore[arg-type]

    assert captured.value.failure is SecretLeaseFailure.INVALID_SECRET
    assert str(captured.value) == "INVALID_SECRET"


def test_secret_lease_supplies_secret_once_then_closes() -> None:
    lease = OneUseSecretLease(SYNTHETIC_SECRET)
    calls: list[str] = []
    result_marker = object()

    result = lease.reveal_for_call(
        lambda secret: calls.append(secret) or result_marker
    )

    assert result is result_marker
    assert calls == [SYNTHETIC_SECRET]
    assert lease.used is True
    assert lease.closed is True
    with pytest.raises(SecretLeaseError) as captured:
        lease.reveal_for_call(lambda _secret: object())
    assert captured.value.failure is SecretLeaseFailure.CLOSED


def test_secret_lease_closes_when_operation_raises() -> None:
    lease = OneUseSecretLease(SYNTHETIC_SECRET)

    def fail(_secret: str) -> object:
        raise RuntimeError("SYNTHETIC_OPERATION_FAILURE")

    with pytest.raises(RuntimeError, match="SYNTHETIC_OPERATION_FAILURE"):
        lease.reveal_for_call(fail)

    assert lease.used is True
    assert lease.closed is True


def test_secret_lease_rejects_returning_the_secret() -> None:
    lease = OneUseSecretLease(SYNTHETIC_SECRET)

    with pytest.raises(SecretLeaseError) as captured:
        lease.reveal_for_call(lambda secret: secret)

    assert captured.value.failure is SecretLeaseFailure.SECRET_RETURNED
    assert lease.closed is True


def test_secret_lease_close_is_idempotent() -> None:
    lease = OneUseSecretLease(SYNTHETIC_SECRET)

    lease.close()
    lease.close()

    assert lease.closed is True
    assert lease.used is False


def test_secret_lease_representation_is_fixed_and_redacted() -> None:
    lease = OneUseSecretLease(SYNTHETIC_SECRET)

    assert repr(lease) == "<SecretLease redacted>"
    assert str(lease) == "<SecretLease redacted>"
    assert SYNTHETIC_SECRET not in repr(lease)
    assert not hasattr(lease, "secret")
    assert not hasattr(lease, "value")


@pytest.mark.parametrize(
    "operation",
    [
        copy.copy,
        copy.deepcopy,
        pickle.dumps,
    ],
)
def test_secret_lease_copy_and_serialization_are_prohibited(operation: object) -> None:
    lease = OneUseSecretLease(SYNTHETIC_SECRET)

    with pytest.raises(TypeError) as captured:
        operation(lease)  # type: ignore[operator]

    assert SYNTHETIC_SECRET not in str(captured.value)


def test_fake_credential_source_uses_only_the_contract_boundary() -> None:
    class FakeCredentialSource:
        def __init__(self) -> None:
            self.refs: list[str] = []

        def acquire(self, credential_ref: str) -> OneUseSecretLease:
            self.refs.append(credential_ref)
            return OneUseSecretLease(SYNTHETIC_SECRET)

    source = FakeCredentialSource()
    lease = source.acquire("synthetic-reference")

    assert source.refs == ["synthetic-reference"]
    assert lease.reveal_for_call(lambda _secret: "candidate") == "candidate"
    assert lease.closed is True
