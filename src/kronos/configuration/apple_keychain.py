"""Retrieval-only Apple Keychain backend behind an injected subprocess seam."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from kronos.configuration.credentials import (
    CredentialRetrievalOutcome,
    OneUseSecretLease,
    SecretLease,
)


SECURITY_EXECUTABLE = "/usr/bin/security"
SERVICE_PREFIX = "com.project-kronos.provider-authentication."
DEFAULT_TIMEOUT_SECONDS = 5.0
MAX_TIMEOUT_SECONDS = 10.0

_REFERENCE_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,64}\Z")
_MISSING_RETURN_CODES = frozenset({44})
_ACCESS_DENIED_RETURN_CODES = frozenset({36, 51})
_MINIMAL_ENVIRONMENT = (("LANG", "C"), ("PATH", "/usr/bin:/bin"))


@dataclass(frozen=True, slots=True)
class SubprocessRequest:
    """Inspectable command policy containing no credential value."""

    argv: tuple[str, ...]
    timeout_seconds: float
    shell: bool = False
    stdin_devnull: bool = True
    capture_output: bool = True
    environment: tuple[tuple[str, str], ...] = _MINIMAL_ENVIRONMENT


class SubprocessResult:
    """Transient captured process result; representation is always redacted."""

    __slots__ = ("_consumed", "_stderr", "_stdout", "returncode")

    def __init__(self, returncode: int, stdout: bytes, stderr: bytes) -> None:
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr
        self._consumed = False

    def _take_output(self) -> tuple[bytes, bytes]:
        if self._consumed:
            raise AppleKeychainCredentialError(
                CredentialRetrievalOutcome.MALFORMED
            )
        stdout = self._stdout
        stderr = self._stderr
        self._stdout = b""
        self._stderr = b""
        self._consumed = True
        return stdout, stderr

    def __repr__(self) -> str:
        return "<SubprocessResult redacted>"

    def __str__(self) -> str:
        return "<SubprocessResult redacted>"

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("SUBPROCESS_RESULT_SERIALIZATION_PROHIBITED")


SubprocessRunner = Callable[[SubprocessRequest], SubprocessResult]


class AppleKeychainCredentialError(RuntimeError):
    """Sanitized retrieval failure with no subprocess or secret material."""

    def __init__(self, outcome: CredentialRetrievalOutcome) -> None:
        self.outcome = outcome
        super().__init__(outcome.value)


class AppleKeychainCredentialSource:
    """Retrieve one API secret through an explicitly supplied runner."""

    __slots__ = ("_provider", "_runner", "_timeout_seconds")

    def __init__(
        self,
        *,
        provider: str,
        runner: SubprocessRunner,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not _valid_reference(provider):
            raise AppleKeychainCredentialError(
                CredentialRetrievalOutcome.MALFORMED
            )
        if not 0 < timeout_seconds <= MAX_TIMEOUT_SECONDS:
            raise AppleKeychainCredentialError(
                CredentialRetrievalOutcome.MALFORMED
            )
        self._provider = provider.lower()
        self._runner = runner
        self._timeout_seconds = timeout_seconds

    def acquire(self, credential_ref: str) -> SecretLease:
        """Acquire one redacted lease or raise one sanitized category."""

        if not _valid_reference(credential_ref):
            raise AppleKeychainCredentialError(
                CredentialRetrievalOutcome.MALFORMED
            )

        request = SubprocessRequest(
            argv=(
                SECURITY_EXECUTABLE,
                "find-generic-password",
                "-w",
                "-s",
                f"{SERVICE_PREFIX}{self._provider}",
                "-a",
                f"api-secret:{credential_ref}",
            ),
            timeout_seconds=self._timeout_seconds,
        )

        try:
            result = self._runner(request)
        except TimeoutError:
            raise AppleKeychainCredentialError(
                CredentialRetrievalOutcome.TIMED_OUT
            ) from None
        except PermissionError:
            raise AppleKeychainCredentialError(
                CredentialRetrievalOutcome.ACCESS_DENIED
            ) from None
        except (FileNotFoundError, OSError):
            raise AppleKeychainCredentialError(
                CredentialRetrievalOutcome.BACKEND_UNAVAILABLE
            ) from None
        except Exception:
            raise AppleKeychainCredentialError(
                CredentialRetrievalOutcome.BACKEND_UNAVAILABLE
            ) from None

        if not isinstance(result, SubprocessResult):
            raise AppleKeychainCredentialError(
                CredentialRetrievalOutcome.MALFORMED
            )

        returncode = result.returncode
        stdout, stderr = result._take_output()
        if returncode != 0:
            raise AppleKeychainCredentialError(
                _outcome_for_returncode(returncode)
            )
        if stderr:
            raise AppleKeychainCredentialError(CredentialRetrievalOutcome.MALFORMED)

        secret = _decode_secret(stdout)
        return OneUseSecretLease(secret)

    def __repr__(self) -> str:
        return "<AppleKeychainCredentialSource redacted>"

    def __str__(self) -> str:
        return "<AppleKeychainCredentialSource redacted>"

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("CREDENTIAL_SOURCE_SERIALIZATION_PROHIBITED")


def run_security_subprocess(request: SubprocessRequest) -> SubprocessResult:
    """Execute an approved request; callers must inject this seam explicitly."""

    if not _valid_security_request(request):
        raise AppleKeychainCredentialError(CredentialRetrievalOutcome.MALFORMED)

    try:
        completed = subprocess.run(
            request.argv,
            shell=False,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=request.timeout_seconds,
            env=_environment_mapping(request.environment),
        )
    except subprocess.TimeoutExpired:
        raise TimeoutError from None

    return SubprocessResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _environment_mapping(entries: tuple[tuple[str, str], ...]) -> Mapping[str, str]:
    environment = dict(entries)
    if environment != dict(_MINIMAL_ENVIRONMENT):
        raise AppleKeychainCredentialError(CredentialRetrievalOutcome.MALFORMED)
    return environment


def _valid_security_request(request: SubprocessRequest) -> bool:
    if request.shell or not request.stdin_devnull or not request.capture_output:
        return False
    if not 0 < request.timeout_seconds <= MAX_TIMEOUT_SECONDS:
        return False
    if len(request.argv) != 7:
        return False
    executable, operation, output_flag, service_flag, service, account_flag, account = (
        request.argv
    )
    if (
        executable != SECURITY_EXECUTABLE
        or operation != "find-generic-password"
        or output_flag != "-w"
        or service_flag != "-s"
        or account_flag != "-a"
        or not service.startswith(SERVICE_PREFIX)
        or not account.startswith("api-secret:")
    ):
        return False
    return _valid_reference(service.removeprefix(SERVICE_PREFIX)) and _valid_reference(
        account.removeprefix("api-secret:")
    )


def _valid_reference(value: object) -> bool:
    return isinstance(value, str) and _REFERENCE_PATTERN.fullmatch(value) is not None


def _outcome_for_returncode(returncode: int) -> CredentialRetrievalOutcome:
    if returncode in _MISSING_RETURN_CODES:
        return CredentialRetrievalOutcome.MISSING
    if returncode in _ACCESS_DENIED_RETURN_CODES:
        return CredentialRetrievalOutcome.ACCESS_DENIED
    return CredentialRetrievalOutcome.BACKEND_UNAVAILABLE


def _decode_secret(stdout: bytes) -> str:
    if not isinstance(stdout, bytes) or not stdout or len(stdout) > 4097:
        raise AppleKeychainCredentialError(CredentialRetrievalOutcome.MALFORMED)

    if stdout.endswith(b"\r\n"):
        value = stdout[:-2]
    elif stdout.endswith(b"\n"):
        value = stdout[:-1]
    else:
        value = stdout

    if not value or b"\x00" in value or b"\r" in value or b"\n" in value:
        raise AppleKeychainCredentialError(CredentialRetrievalOutcome.MALFORMED)
    try:
        secret = value.decode("utf-8")
    except UnicodeDecodeError:
        raise AppleKeychainCredentialError(
            CredentialRetrievalOutcome.MALFORMED
        ) from None
    if not secret:
        raise AppleKeychainCredentialError(CredentialRetrievalOutcome.MALFORMED)
    return secret


__all__ = [
    "AppleKeychainCredentialError",
    "AppleKeychainCredentialSource",
    "SubprocessRequest",
    "SubprocessResult",
    "run_security_subprocess",
]
