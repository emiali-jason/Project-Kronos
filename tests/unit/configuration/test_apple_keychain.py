from dataclasses import asdict
import pickle
from types import SimpleNamespace

import pytest

from kronos.configuration.apple_keychain import (
    AppleKeychainApiKeySource,
    AppleKeychainCredentialError,
    AppleKeychainCredentialPresenceProbe,
    AppleKeychainCredentialProvisioner,
    AppleKeychainCredentialSource,
    AppleKeychainIntendedPrincipalResolver,
    PresenceSubprocessRequest,
    ProvisioningSubprocessRequest,
    SubprocessRequest,
    SubprocessResult,
    run_security_provisioning_subprocess,
    run_security_framework_provisioning,
    run_security_framework_subprocess,
    run_security_subprocess,
)
from kronos.configuration.credentials import (
    CredentialRetrievalOutcome,
    SecretLeaseError,
)
from kronos.configuration.principals import (
    IntendedPrincipalResolutionOutcome,
    PrincipalBindingResult,
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


class _FakeProvisioningRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[ProvisioningSubprocessRequest, bytes]] = []

    def __call__(
        self,
        request: ProvisioningSubprocessRequest,
        secret_input: bytes,
    ) -> SubprocessResult:
        self.calls.append((request, secret_input))
        return SubprocessResult(0, b"", b"")


class _FakePresenceRunner:
    def __init__(self, returncodes: list[int]) -> None:
        self.returncodes = returncodes
        self.requests: list[PresenceSubprocessRequest] = []

    def __call__(self, request: PresenceSubprocessRequest) -> SubprocessResult:
        self.requests.append(request)
        return SubprocessResult(self.returncodes.pop(0), b"metadata", b"")


def _source(runner: _FakeRunner) -> AppleKeychainCredentialSource:
    return AppleKeychainCredentialSource(provider="KITE", runner=runner)


def _resolver(runner: _FakeRunner) -> AppleKeychainIntendedPrincipalResolver:
    return AppleKeychainIntendedPrincipalResolver(provider="KITE", runner=runner)


def _api_key_source(runner: _FakeRunner) -> AppleKeychainApiKeySource:
    return AppleKeychainApiKeySource(provider="KITE", runner=runner)


class _Evidence:
    def __init__(self, observed: str) -> None:
        self.observed = observed
        self.closed = False

    def compare_expected(self, expected: str) -> PrincipalBindingResult:
        return (
            PrincipalBindingResult.MATCHED
            if self.observed == expected
            else PrincipalBindingResult.MISMATCHED
        )

    def close(self) -> None:
        self.observed = ""
        self.closed = True


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


def test_api_key_uses_separate_protected_application_registration_account() -> None:
    runner = _FakeRunner(SubprocessResult(0, b"unit-api-key\n", b""))

    lease = _api_key_source(runner).acquire(
        "ZERODHA-KITE-APP-REGISTRATION-PRIMARY"
    )

    assert runner.requests == [
        SubprocessRequest(
            argv=(
                "/usr/bin/security",
                "find-generic-password",
                "-w",
                "-s",
                "com.project-kronos.provider-authentication.kite",
                "-a",
                "api-key:ZERODHA-KITE-APP-REGISTRATION-PRIMARY",
            ),
            timeout_seconds=5.0,
        )
    ]
    assert repr(_api_key_source(runner)) == "<AppleKeychainApiKeySource redacted>"
    observed: list[str] = []
    lease.reveal_for_call(lambda value: observed.append(value))
    assert observed == ["unit-api-key"]


def test_setup_writer_sends_credentials_only_through_stdin() -> None:
    runner = _FakeProvisioningRunner()
    provisioner = AppleKeychainCredentialProvisioner(
        provider="KITE",
        runner=runner,
    )

    provisioner.store_api_key("app-primary", "unit-api-key")
    provisioner.store_api_secret("secret-primary", "unit-api-secret")
    provisioner.store_intended_principal("principal-primary", "AB1234")

    assert [call[0].argv[-2] for call in runner.calls] == [
        "api-key:app-primary",
        "api-secret:secret-primary",
        "intended-principal:principal-primary",
    ]
    assert all(call[0].argv[-1] == "-w" for call in runner.calls)
    assert all("unit-api" not in repr(call[0]) for call in runner.calls)
    assert [call[1] for call in runner.calls] == [
        b"unit-api-key\n",
        b"unit-api-secret\n",
        b"AB1234\n",
    ]


def test_real_provisioning_runner_uses_stdin_and_never_argv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_run(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(
        "kronos.configuration.apple_keychain.subprocess.run",
        fake_run,
    )
    request = ProvisioningSubprocessRequest(
        argv=(
            "/usr/bin/security",
            "add-generic-password",
            "-U",
            "-s",
            "com.project-kronos.provider-authentication.kite",
            "-a",
            "api-key:app-primary",
            "-w",
        ),
        timeout_seconds=5.0,
    )

    result = run_security_provisioning_subprocess(
        request,
        b"unit-api-key\n",
    )

    assert result.returncode == 0
    assert calls[0][0] == (request.argv,)
    assert calls[0][1]["input"] == b"unit-api-key\n"
    assert "unit-api-key" not in repr(request)


def test_framework_provisioning_never_invokes_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[bytes, bytes, bytes]] = []

    def fake_store(service: bytes, account: bytes, password: bytes) -> int:
        calls.append((service, account, password))
        return 0

    monkeypatch.setattr(
        "kronos.configuration.apple_keychain._security_framework_store",
        fake_store,
    )
    monkeypatch.setattr(
        "kronos.configuration.apple_keychain.subprocess.run",
        lambda *_args, **_kwargs: pytest.fail("subprocess must not execute"),
    )
    request = ProvisioningSubprocessRequest(
        argv=(
            "/usr/bin/security",
            "add-generic-password",
            "-U",
            "-s",
            "com.project-kronos.provider-authentication.kite",
            "-a",
            "api-key:app-primary",
            "-w",
        ),
        timeout_seconds=5.0,
    )

    result = run_security_framework_provisioning(
        request,
        b"unit-api-key\n",
    )

    assert result.returncode == 0
    assert calls == [
        (
            b"com.project-kronos.provider-authentication.kite",
            b"api-key:app-primary",
            b"unit-api-key",
        )
    ]


def test_framework_retrieval_uses_kronos_process_identity_without_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[bytes, bytes]] = []

    def fake_retrieve(service: bytes, account: bytes) -> tuple[int, bytes]:
        calls.append((service, account))
        return 0, b"unit-api-key\n"

    monkeypatch.setattr(
        "kronos.configuration.apple_keychain._security_framework_retrieve",
        fake_retrieve,
    )
    monkeypatch.setattr(
        "kronos.configuration.apple_keychain.subprocess.run",
        lambda *_args, **_kwargs: pytest.fail("subprocess must not execute"),
    )
    request = SubprocessRequest(
        argv=(
            "/usr/bin/security",
            "find-generic-password",
            "-w",
            "-s",
            "com.project-kronos.provider-authentication.kite",
            "-a",
            "api-key:app-primary",
        ),
        timeout_seconds=5.0,
    )

    result = run_security_framework_subprocess(request)

    assert result.returncode == 0
    assert calls == [
        (
            b"com.project-kronos.provider-authentication.kite",
            b"api-key:app-primary",
        )
    ]


def test_presence_probe_never_requests_keychain_values() -> None:
    runner = _FakePresenceRunner([0, 44])
    probe = AppleKeychainCredentialPresenceProbe(
        provider="KITE",
        runner=runner,
    )

    assert probe.api_key_stored("app-primary") is True
    assert probe.api_secret_stored("secret-primary") is False
    assert all("-w" not in request.argv for request in runner.requests)
    assert [request.argv[-1] for request in runner.requests] == [
        "api-key:app-primary",
        "api-secret:secret-primary",
    ]


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


def test_real_subprocess_seam_allows_exact_intended_principal_purpose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_run(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout=b"AB1234\n", stderr=b"")

    monkeypatch.setattr(
        "kronos.configuration.apple_keychain.subprocess.run",
        fake_run,
    )
    request = SubprocessRequest(
        argv=(
            "/usr/bin/security",
            "find-generic-password",
            "-w",
            "-s",
            "com.project-kronos.provider-authentication.kite",
            "-a",
            "intended-principal:primary.registration",
        ),
        timeout_seconds=5.0,
    )

    result = run_security_subprocess(request)

    assert result.returncode == 0
    assert len(calls) == 1
    assert calls[0][0] == (request.argv,)
    assert calls[0][1]["shell"] is False


def test_intended_principal_command_is_purpose_separated_and_one_use() -> None:
    runner = _FakeRunner(SubprocessResult(0, b"AB1234\n", b""))
    evidence = _Evidence("AB1234")
    captured_lease: list[object] = []

    result = _resolver(runner).use_resolved_once(
        "primary.registration",
        lambda lease: (
            captured_lease.append(lease),
            lease.compare_once(evidence),
        )[1],
    )

    assert result.outcome is IntendedPrincipalResolutionOutcome.RESOLVED
    assert result.binding_result is PrincipalBindingResult.MATCHED
    assert runner.requests == [
        SubprocessRequest(
            argv=(
                "/usr/bin/security",
                "find-generic-password",
                "-w",
                "-s",
                "com.project-kronos.provider-authentication.kite",
                "-a",
                "intended-principal:primary.registration",
            ),
            timeout_seconds=5.0,
        )
    ]
    assert evidence.closed is True
    assert captured_lease[0].closed is True  # type: ignore[attr-defined]
    assert "AB1234" not in repr(captured_lease[0])


def test_api_secret_and_intended_principal_accounts_cannot_cross() -> None:
    secret_runner = _FakeRunner(SubprocessResult(0, b"unit-secret\n", b""))
    principal_runner = _FakeRunner(SubprocessResult(0, b"AB1234\n", b""))

    _source(secret_runner).acquire("same-reference")
    _resolver(principal_runner).use_resolved_once(
        "same-reference",
        lambda lease: lease.compare_once(_Evidence("AB1234")),
    )

    assert secret_runner.requests[0].argv[-1] == "api-secret:same-reference"
    assert (
        principal_runner.requests[0].argv[-1]
        == "intended-principal:same-reference"
    )
    assert secret_runner.requests[0].argv != principal_runner.requests[0].argv


@pytest.mark.parametrize("reference", ["", "space ref", "../ref", "x" * 65])
def test_invalid_intended_principal_reference_never_calls_runner(
    reference: str,
) -> None:
    runner = _FakeRunner(SubprocessResult(0, b"AB1234\n", b""))

    result = _resolver(runner).use_resolved_once(
        reference,
        lambda _lease: PrincipalBindingResult.MATCHED,
    )

    assert result.outcome is IntendedPrincipalResolutionOutcome.INVALID_CONFIGURATION
    assert runner.requests == []


@pytest.mark.parametrize(
    ("runner_result", "expected"),
    [
        (SubprocessResult(44, b"", b"ignored"), IntendedPrincipalResolutionOutcome.NOT_FOUND),
        (
            SubprocessResult(36, b"", b"ignored"),
            IntendedPrincipalResolutionOutcome.ACCESS_DENIED,
        ),
        (
            SubprocessResult(1, b"", b"ignored"),
            IntendedPrincipalResolutionOutcome.BACKEND_UNAVAILABLE,
        ),
        (TimeoutError("raw"), IntendedPrincipalResolutionOutcome.BACKEND_UNAVAILABLE),
    ],
)
def test_intended_principal_backend_failures_are_sanitized(
    runner_result: SubprocessResult | BaseException,
    expected: IntendedPrincipalResolutionOutcome,
) -> None:
    result = _resolver(_FakeRunner(runner_result)).use_resolved_once(
        "primary",
        lambda _lease: pytest.fail("operation must not run"),
    )

    assert result.outcome is expected
    assert result.binding_result is None
    assert "raw" not in repr(result)


@pytest.mark.parametrize(
    "principal",
    [b"", b" AB1234\n", b"ab-123\n", b"A" * 65 + b"\n", b"AB1234\nextra"],
)
def test_malformed_intended_principal_is_not_retained(principal: bytes) -> None:
    resolver = _resolver(_FakeRunner(SubprocessResult(0, principal, b"")))

    result = resolver.use_resolved_once(
        "primary",
        lambda _lease: pytest.fail("operation must not run"),
    )

    assert result.outcome is IntendedPrincipalResolutionOutcome.SANITIZED_FAILURE
    assert repr(resolver) == "<AppleKeychainIntendedPrincipalResolver redacted>"
    assert not hasattr(resolver, "_expected_principal")
    with pytest.raises((TypeError, pickle.PicklingError)):
        pickle.dumps(resolver)


def test_intended_principal_operation_failure_closes_lease_and_is_sanitized() -> None:
    captured: list[object] = []
    resolver = _resolver(_FakeRunner(SubprocessResult(0, b"AB1234\n", b"")))

    def fail(lease: object) -> PrincipalBindingResult:
        captured.append(lease)
        raise RuntimeError("raw principal operation")

    result = resolver.use_resolved_once("primary", fail)

    assert result.outcome is IntendedPrincipalResolutionOutcome.SANITIZED_FAILURE
    assert captured[0].closed is True  # type: ignore[attr-defined]
    assert "raw" not in repr(result)
    PresenceSubprocessRequest,
    ProvisioningSubprocessRequest,
