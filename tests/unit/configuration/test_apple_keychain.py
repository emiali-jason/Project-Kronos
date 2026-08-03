from dataclasses import asdict
import pickle

import pytest

from kronos.configuration.apple_keychain import (
    AppleKeychainCredentialError,
    AppleKeychainCredentialSource,
    SubprocessRequest,
    SubprocessResult,
    run_security_subprocess,
)
from kronos.configuration.credentials import (
    CredentialRetrievalOutcome,
    SecretLeaseError,
)


class _FakeRunner:
    def __init__(self, result: SubprocessResult | BaseException) -> None:
        self.result = result
        self.requests: list[SubprocessRequest] = []

    def __call__(self, request: SubprocessRequest) -> SubprocessResult:
        self.requests.append(request)
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


def _source(runner: _FakeRunner) -> AppleKeychainCredentialSource:
    return AppleKeychainCredentialSource(provider="KITE", runner=runner)


def test_keychain_command_vector_is_exact_and_contains_no_secret() -> None:
    runner = _FakeRunner(SubprocessResult(0, b"unit-secret\n", b""))

    lease = _source(runner).acquire("primary.registration")

    assert runner.requests == [
        SubprocessRequest(
            argv=(
                "/usr/bin/security",
                "find-generic-password",
                "-w",
                "-s",
                "com.project-kronos.provider-authentication.kite",
                "-a",
                "api-secret:primary.registration",
            ),
            timeout_seconds=5.0,
        )
    ]
    request = runner.requests[0]
    assert request.shell is False
    assert request.stdin_devnull is True
    assert request.capture_output is True
    assert request.environment == (("LANG", "C"), ("PATH", "/usr/bin:/bin"))
    assert "unit-secret" not in repr(request)

    seen: list[str] = []
    assert lease.reveal_for_call(lambda value: seen.append(value)) is None
    assert seen == ["unit-secret"]
    with pytest.raises(SecretLeaseError):
        lease.reveal_for_call(lambda _value: None)


@pytest.mark.parametrize("reference", ["", "space ref", "../ref", "x" * 65])
def test_invalid_reference_is_rejected_before_runner(reference: str) -> None:
    runner = _FakeRunner(SubprocessResult(0, b"never-used\n", b""))

    with pytest.raises(AppleKeychainCredentialError) as captured:
        _source(runner).acquire(reference)

    assert captured.value.outcome is CredentialRetrievalOutcome.MALFORMED
    assert runner.requests == []


@pytest.mark.parametrize(
    ("result", "outcome"),
    [
        (SubprocessResult(44, b"", b"not retained"), CredentialRetrievalOutcome.MISSING),
        (
            SubprocessResult(36, b"", b"not retained"),
            CredentialRetrievalOutcome.ACCESS_DENIED,
        ),
        (
            SubprocessResult(1, b"", b"not retained"),
            CredentialRetrievalOutcome.BACKEND_UNAVAILABLE,
        ),
        (TimeoutError("raw timeout"), CredentialRetrievalOutcome.TIMED_OUT),
        (PermissionError("raw denial"), CredentialRetrievalOutcome.ACCESS_DENIED),
        (
            FileNotFoundError("raw path"),
            CredentialRetrievalOutcome.BACKEND_UNAVAILABLE,
        ),
        (RuntimeError("raw backend"), CredentialRetrievalOutcome.BACKEND_UNAVAILABLE),
    ],
)
def test_backend_failures_are_sanitized(
    result: SubprocessResult | BaseException,
    outcome: CredentialRetrievalOutcome,
) -> None:
    runner = _FakeRunner(result)

    with pytest.raises(AppleKeychainCredentialError) as captured:
        _source(runner).acquire("primary")

    assert captured.value.outcome is outcome
    assert str(captured.value) == outcome.value
    assert "raw" not in str(captured.value)
    assert "not retained" not in str(captured.value)


@pytest.mark.parametrize(
    "result",
    [
        SubprocessResult(0, b"", b""),
        SubprocessResult(0, b"secret\nextra", b""),
        SubprocessResult(0, b"secret\x00\n", b""),
        SubprocessResult(0, b"secret\n", b"diagnostic"),
        SubprocessResult(0, b"\xff\n", b""),
    ],
)
def test_malformed_output_is_never_leased(result: SubprocessResult) -> None:
    with pytest.raises(AppleKeychainCredentialError) as captured:
        _source(_FakeRunner(result)).acquire("primary")

    assert captured.value.outcome is CredentialRetrievalOutcome.MALFORMED


def test_captured_result_and_source_have_fixed_redacted_representations() -> None:
    result = SubprocessResult(0, b"highly-sensitive", b"sensitive-diagnostic")
    source = _source(_FakeRunner(result))

    assert repr(result) == "<SubprocessResult redacted>"
    assert str(result) == "<SubprocessResult redacted>"
    assert repr(source) == "<AppleKeychainCredentialSource redacted>"
    assert "highly-sensitive" not in repr(result)
    with pytest.raises(TypeError):
        asdict(result)  # type: ignore[arg-type]
    with pytest.raises((TypeError, pickle.PicklingError)):
        pickle.dumps(source)


@pytest.mark.parametrize(
    "argv",
    [
        ("/usr/bin/security", "delete-generic-password"),
        (
            "/usr/bin/security",
            "find-generic-password",
            "-w",
            "-s",
            "unapproved.service",
            "-a",
            "api-secret:primary",
        ),
        (
            "/usr/bin/security",
            "find-generic-password",
            "-w",
            "-s",
            "com.project-kronos.provider-authentication.kite",
            "-a",
            "wrong-account",
        ),
    ],
)
def test_real_subprocess_seam_rejects_non_retrieval_vectors_before_execution(
    argv: tuple[str, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "kronos.configuration.apple_keychain.subprocess.run",
        lambda *_args, **_kwargs: pytest.fail("subprocess must not execute"),
    )

    with pytest.raises(AppleKeychainCredentialError) as captured:
        run_security_subprocess(SubprocessRequest(argv=argv, timeout_seconds=5.0))

    assert captured.value.outcome is CredentialRetrievalOutcome.MALFORMED
