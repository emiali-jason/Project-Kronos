from dataclasses import asdict
import multiprocessing
import pickle
import time
from types import SimpleNamespace

import pytest

from kronos.configuration.apple_keychain import (
    AppleKeychainApiKeySource,
    AppleKeychainCredentialError,
    AppleKeychainCredentialPresenceProbe,
    AppleKeychainCredentialProvisioner,
    AppleKeychainCredentialRemover,
    AppleKeychainCredentialSource,
    AppleKeychainIntendedPrincipalResolver,
    PresenceSubprocessRequest,
    ProvisioningSubprocessRequest,
    RemovalSubprocessRequest,
    SubprocessRequest,
    SubprocessResult,
    run_security_provisioning_subprocess,
    run_security_framework_provisioning,
    run_security_framework_removal,
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


class _FakeRemovalRunner:
    def __init__(self, returncodes: list[int]) -> None:
        self.returncodes = returncodes
        self.requests: list[RemovalSubprocessRequest] = []

    def __call__(self, request: RemovalSubprocessRequest) -> SubprocessResult:
        self.requests.append(request)
        return SubprocessResult(self.returncodes.pop(0), b"", b"")


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
    calls: list[tuple[bytes, bytes, float]] = []

    def fake_retrieve(
        service: bytes,
        account: bytes,
        timeout_seconds: float,
    ) -> tuple[int, bytes]:
        calls.append((service, account, timeout_seconds))
        return 0, b"unit-api-key\n"

    monkeypatch.setattr(
        "kronos.configuration.apple_keychain._bounded_security_framework_retrieve",
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
            5.0,
        )
    ]


def test_framework_retrieval_isolated_helper_has_real_wall_clock_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = multiprocessing.get_context("fork")
    entered = context.Event()
    never = context.Event()

    def blocked_retrieve(
        _service: bytes,
        _account: bytes,
    ) -> tuple[int, bytes]:
        entered.set()
        never.wait()
        return 0, b"must-not-return\n"

    monkeypatch.setattr(
        "kronos.configuration.apple_keychain._security_framework_process_context",
        lambda: context,
    )
    monkeypatch.setattr(
        "kronos.configuration.apple_keychain._security_framework_retrieve",
        blocked_retrieve,
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
        timeout_seconds=0.05,
    )

    started = time.monotonic()
    with pytest.raises(TimeoutError):
        run_security_framework_subprocess(request)
    elapsed = time.monotonic() - started

    assert entered.is_set()
    assert elapsed < 0.75


def test_framework_timeout_is_sanitized_and_retains_no_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "kronos.configuration.apple_keychain._bounded_security_framework_retrieve",
        lambda *_args: (_ for _ in ()).throw(TimeoutError()),
    )
    source = AppleKeychainApiKeySource(
        provider="KITE",
        runner=run_security_framework_subprocess,
        timeout_seconds=0.05,
    )

    with pytest.raises(AppleKeychainCredentialError) as captured:
        source.acquire("app-primary")

    assert captured.value.outcome is CredentialRetrievalOutcome.TIMED_OUT
    assert str(captured.value) == "TIMED_OUT"
    assert "secret" not in repr(captured.value).lower()


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


def test_explicit_remover_deletes_only_named_api_credentials() -> None:
    runner = _FakeRemovalRunner([0, -25300])
    remover = AppleKeychainCredentialRemover(provider="TELEGRAM-BOT", runner=runner)

    remover.remove_api_secret("ux10-bot-token")
    remover.remove_api_key("ux10-private-chat")

    assert [request.argv for request in runner.requests] == [
        (
            "/usr/bin/security", "delete-generic-password", "-s",
            "com.project-kronos.provider-authentication.telegram-bot", "-a",
            "api-secret:ux10-bot-token",
        ),
        (
            "/usr/bin/security", "delete-generic-password", "-s",
            "com.project-kronos.provider-authentication.telegram-bot", "-a",
            "api-key:ux10-private-chat",
        ),
    ]
    assert repr(remover) == "<AppleKeychainCredentialRemover redacted>"


def test_framework_removal_uses_process_identity_without_secret_or_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[bytes, bytes]] = []
    monkeypatch.setattr(
        "kronos.configuration.apple_keychain._security_framework_remove",
        lambda service, account: calls.append((service, account)) or 0,
    )
    monkeypatch.setattr(
        "kronos.configuration.apple_keychain.subprocess.run",
        lambda *_args, **_kwargs: pytest.fail("subprocess must not execute"),
    )
    request = RemovalSubprocessRequest(
        argv=(
            "/usr/bin/security", "delete-generic-password", "-s",
            "com.project-kronos.provider-authentication.telegram-bot", "-a",
            "api-secret:ux10-bot-token",
        ),
        timeout_seconds=5.0,
    )

    result = run_security_framework_removal(request)

    assert result.returncode == 0
    assert calls == [(
        b"com.project-kronos.provider-authentication.telegram-bot",
        b"api-secret:ux10-bot-token",
    )]


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

# Spawn imports this function in the child. Only its synthetic retrieval runs.
def _pf02d_keychain_worker(sender, service, account, *, entered, release, mode):
    import os
    from kronos.configuration import apple_keychain as module
    if mode == "resist":
        import signal
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    selected = mode.startswith("production-") and account.startswith(mode.removeprefix("production-").encode() + b':')
    if not mode.startswith("production-") or selected:
        entered.set()
    if mode in {"partial", "oversized", "malformed", "exit", "trickle"}:
        if mode == "partial":
            os.write(sender.fileno(), (12).to_bytes(4, 'big') + b'\x00')
            release.wait(5)
        elif mode == "trickle":
            os.write(sender.fileno(), (100).to_bytes(4, 'big'))
            while not release.wait(0.02):
                os.write(sender.fileno(), b'x')
        elif mode == "oversized":
            os.write(sender.fileno(), (500000).to_bytes(4, 'big'))
        elif mode == "malformed":
            sender.send_bytes(b'x')
        sender.close()
        return
    def retrieve(_service, _account):
        if mode in {"blocked", "late", "resist"} or selected:
            release.wait(5)
        if mode == "failure":
            raise RuntimeError("synthetic-private-keychain-detail")
        if mode == "missing":
            return -25300, b''
        if mode.startswith("production-"):
            value = (b'service-api-key' if account.startswith(b'api-key:') else
                     b'service-api-secret' if account.startswith(b'api-secret:') else b'PRINCIPAL123')
            return 0, value + b'\n'
        return 0, b'synthetic-value\n'
    module._security_framework_retrieve = retrieve
    module._security_framework_retrieval_worker(sender, service, account)
    if mode == "lingering":
        release.wait(5)


def _pf02d_request(timeout=2.0):
    return SubprocessRequest(argv=(
        '/usr/bin/security', 'find-generic-password', '-w', '-s',
        'com.project-kronos.provider-authentication.kite', '-a', 'api-secret:test'),
        timeout_seconds=timeout)


@pytest.mark.parametrize('mode,success', [
    ('opened', True), ('missing', True), ('failure', False),
    ('oversized', False), ('malformed', False), ('exit', False), ('lingering', False),
])
def test_pf02d_spawn_keychain_result_requires_child_exit(monkeypatch, mode, success):
    from tests.unit.provider.test_kite_login_navigator import (
        _pf02d_process_fixture, _pf02d_assert_processes_released, _pf02d_finish)
    case = _pf02d_process_fixture(monkeypatch, keychain=True, mode=mode)
    try:
        if success:
            result = run_security_framework_subprocess(_pf02d_request(), deadline=case.deadline)
            assert result.returncode == (-25300 if mode == 'missing' else 0)
            assert result._take_output() == ((b'' if mode == 'missing' else b'synthetic-value\n'), b'')
        else:
            with pytest.raises(AppleKeychainCredentialError):
                run_security_framework_subprocess(_pf02d_request(), deadline=case.deadline)
        assert case.entered.is_set() and len(case.records) == 1
        _pf02d_assert_processes_released(case)
    finally:
        _pf02d_finish(case)


@pytest.mark.parametrize('mode', ['blocked', 'partial', 'trickle', 'resist'])
@pytest.mark.parametrize('terminal', ['cancel', 'deadline'])
def test_pf02d_spawn_keychain_stall_is_terminated(monkeypatch, mode, terminal):
    from tests.unit.provider.test_kite_login_navigator import (
        _pf02d_process_fixture, _pf02d_assert_processes_released, _pf02d_finish)
    case = _pf02d_process_fixture(monkeypatch, keychain=True, mode=mode)
    errors = []
    def retrieve():
        try:
            run_security_framework_subprocess(_pf02d_request(), deadline=case.deadline)
        except BaseException as error:
            errors.append(type(error))
    thread = case.threading.Thread(target=retrieve)
    try:
        thread.start()
        assert case.entered.wait(2)
        started = time.perf_counter()
        if terminal == 'cancel':
            case.deadline.cancel()
        else:
            case.deadline.shorten(0.08)
        thread.join(1.5)
        elapsed = time.perf_counter() - started
        assert not thread.is_alive() and errors == [TimeoutError]
        _pf02d_assert_processes_released(case)
        if mode == "resist":
            import signal
            assert case.records[0].exited[1] == -signal.SIGKILL
        print('PF02D_KEYCHAIN_STOP', mode, terminal, round(elapsed, 4))
    finally:
        _pf02d_finish(case)
        thread.join(2)


def test_pf02d_keychain_late_result_cannot_create_secret_lease(monkeypatch):
    from tests.unit.provider.test_kite_login_navigator import (
        _pf02d_process_fixture, _pf02d_assert_processes_released, _pf02d_finish)
    case = _pf02d_process_fixture(monkeypatch, keychain=True, mode='late')
    source = AppleKeychainCredentialSource(provider='KITE', runner=run_security_framework_subprocess, deadline=case.deadline)
    leases, errors = [], []
    def acquire():
        try:
            leases.append(source.acquire('test'))
        except AppleKeychainCredentialError as error:
            errors.append(error.outcome)
    thread = case.threading.Thread(target=acquire)
    try:
        thread.start()
        assert case.entered.wait(2)
        case.deadline.cancel()
        case.release.set()
        thread.join(1.5)
        assert not thread.is_alive() and leases == []
        assert errors == [CredentialRetrievalOutcome.TIMED_OUT]
        _pf02d_assert_processes_released(case)
    finally:
        _pf02d_finish(case)
        thread.join(2)


def test_pf02d_keychain_failed_cleanup_retains_actual_child_and_fence(monkeypatch):
    from kronos.configuration import apple_keychain as module
    from tests.unit.provider.test_kite_login_navigator import _pf02d_process_fixture, _pf02d_finish
    case = _pf02d_process_fixture(monkeypatch, keychain=True, mode='blocked')
    errors = []
    def retrieve():
        try:
            run_security_framework_subprocess(_pf02d_request(), deadline=case.deadline)
        except BaseException as error:
            errors.append(type(error))
    thread = case.threading.Thread(target=retrieve)
    owner = None
    try:
        thread.start()
        assert case.entered.wait(2)
        process = case.records[0].process
        terminate, kill = process.terminate, process.kill
        process.terminate = process.kill = lambda: None
        case.deadline.cancel()
        thread.join(1.5)
        assert not thread.is_alive() and process.is_alive()
        owner = module._retrieval_owners[0]
        assert owner.process is process and owner.local_cleanup_state == 'FAILED'
        case.deadline.worker_finished()
        assert not case.deadline.retry_ready
        with pytest.raises(AppleKeychainCredentialError):
            run_security_framework_subprocess(_pf02d_request())
        assert len(case.records) == 1
        process.terminate, process.kill = terminate, kill
        case.release.set(); process.join(1)
        assert not process.is_alive()
        assert owner.local_cleanup_state == 'FAILED' and not case.deadline.retry_ready
    finally:
        if case.records and "terminate" in locals():
            case.records[0].process.terminate, case.records[0].process.kill = terminate, kill
        _pf02d_finish(case)
        thread.join(2)
        # Test-only release of the injected failure; production has no recovery.
        if owner in module._retrieval_owners:
            module._retrieval_owners.remove(owner)


def test_pf02d_keychain_repeated_spawn_cycles_release_handles(monkeypatch):
    import os
    from tests.unit.provider.test_kite_login_navigator import (
        _pf02d_process_fixture, _pf02d_assert_processes_released, _pf02d_finish)
    case = _pf02d_process_fixture(monkeypatch, keychain=True, timeout=10)
    children = {p.pid for p in multiprocessing.active_children()}
    try:
        for index in range(7):
            result = run_security_framework_subprocess(_pf02d_request(), deadline=case.deadline)
            assert result._take_output() == (b'synthetic-value\n', b'')
            if index == 0:
                descriptors = len(os.listdir('/dev/fd'))
        assert len(os.listdir('/dev/fd')) <= descriptors
        assert {p.pid for p in multiprocessing.active_children()} == children
        _pf02d_assert_processes_released(case)
    finally:
        _pf02d_finish(case)


def test_pf02d_all_three_retrievals_use_same_remaining_attempt_budget():
    from kronos.provider.services.provider_authentication import ConnectionAttemptDeadline
    now = [0.0]
    deadline = ConnectionAttemptDeadline(1, timeout_seconds=6, monotonic_clock=lambda: now[0])
    requests = []
    def runner(request):
        requests.append(request)
        now[0] += 2
        return SubprocessResult(0, b'AB1234\n', b'')
    key = AppleKeychainApiKeySource(provider='KITE', runner=runner, deadline=deadline)
    secret = AppleKeychainCredentialSource(provider='KITE', runner=runner, deadline=deadline)
    principal = AppleKeychainIntendedPrincipalResolver(provider='KITE', runner=runner, deadline=deadline)
    key.acquire('test').close()
    secret.acquire('test').close()
    outcomes = []
    result = principal.use_resolved_once('test', lambda lease: outcomes.append(lease))
    assert [r.timeout_seconds for r in requests] == [5.0, 4.0, 2.0]
    assert [r.argv[-1].split(':')[0] for r in requests] == ['api-key', 'api-secret', 'intended-principal']
    assert outcomes == [] and result.outcome is not IntendedPrincipalResolutionOutcome.RESOLVED


@pytest.mark.parametrize('configured', [0.05, 5.0, 10.0])
def test_pf02d_configured_stricter_retrieval_timeout_preserved(configured):
    from kronos.provider.services.provider_authentication import ConnectionAttemptDeadline
    deadline = ConnectionAttemptDeadline(1, timeout_seconds=20)
    runner = _FakeRunner(SubprocessResult(0, b'unit-value\n', b''))
    source = AppleKeychainCredentialSource(provider='KITE', runner=runner, deadline=deadline, timeout_seconds=configured)
    source.acquire('test').close()
    assert runner.requests[0].timeout_seconds == configured
    with pytest.raises(AppleKeychainCredentialError):
        AppleKeychainCredentialSource(provider='KITE', runner=runner, timeout_seconds=10.01)


def test_pf02d_spawn_configured_timeout_includes_startup_and_receipt(monkeypatch):
    from tests.unit.provider.test_kite_login_navigator import (
        _pf02d_process_fixture, _pf02d_assert_processes_released, _pf02d_finish)
    case = _pf02d_process_fixture(monkeypatch, keychain=True, mode='blocked')
    try:
        start = time.perf_counter()
        with pytest.raises(TimeoutError):
            run_security_framework_subprocess(_pf02d_request(0.3))
        elapsed = time.perf_counter() - start
        assert case.entered.is_set()
        assert 0.3 <= elapsed < 1.05
        _pf02d_assert_processes_released(case)
        print('PF02D_KEYCHAIN_CONFIGURED_TIMEOUT', round(elapsed, 4))
    finally:
        _pf02d_finish(case)
