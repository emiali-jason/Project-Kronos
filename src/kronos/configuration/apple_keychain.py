"""Retrieval-only Apple Keychain backend behind an injected subprocess seam."""

from __future__ import annotations

import re
import subprocess
import ctypes
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from kronos.configuration.credentials import (
    CredentialRetrievalOutcome,
    OneUseSecretLease,
    SecretLease,
)
from kronos.configuration.principals import (
    IntendedPrincipalLease,
    IntendedPrincipalResolutionOutcome,
    IntendedPrincipalResolutionResult,
    OneUseIntendedPrincipalLease,
    PrincipalBindingResult,
)


SECURITY_EXECUTABLE = "/usr/bin/security"
SERVICE_PREFIX = "com.project-kronos.provider-authentication."
DEFAULT_TIMEOUT_SECONDS = 5.0
MAX_TIMEOUT_SECONDS = 10.0

_REFERENCE_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,64}\Z")
_PRINCIPAL_PATTERN = re.compile(r"[A-Za-z0-9]{1,64}\Z")
_MISSING_RETURN_CODES = frozenset({44, -25300})
_ACCESS_DENIED_RETURN_CODES = frozenset({36, 51})
_MINIMAL_ENVIRONMENT = (("LANG", "C"), ("PATH", "/usr/bin:/bin"))
_API_KEY_PURPOSE = "api-key:"
_API_SECRET_PURPOSE = "api-secret:"
_INTENDED_PRINCIPAL_PURPOSE = "intended-principal:"
_ALLOWED_ACCOUNT_PURPOSES = (
    _API_KEY_PURPOSE,
    _API_SECRET_PURPOSE,
    _INTENDED_PRINCIPAL_PURPOSE,
)


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


@dataclass(frozen=True, slots=True)
class ProvisioningSubprocessRequest:
    """Inspectable Keychain write request containing no credential value."""

    argv: tuple[str, ...]
    timeout_seconds: float
    shell: bool = False
    capture_output: bool = True
    environment: tuple[tuple[str, str], ...] = _MINIMAL_ENVIRONMENT


ProvisioningSubprocessRunner = Callable[
    [ProvisioningSubprocessRequest, bytes],
    SubprocessResult,
]


@dataclass(frozen=True, slots=True)
class PresenceSubprocessRequest:
    """Metadata-only Keychain query that never requests a stored value."""

    argv: tuple[str, ...]
    timeout_seconds: float
    shell: bool = False
    stdin_devnull: bool = True
    capture_output: bool = True
    environment: tuple[tuple[str, str], ...] = _MINIMAL_ENVIRONMENT


PresenceSubprocessRunner = Callable[[PresenceSubprocessRequest], SubprocessResult]


@dataclass(frozen=True, slots=True)
class RemovalSubprocessRequest:
    """Inspectable Keychain deletion request containing no credential value."""

    argv: tuple[str, ...]
    timeout_seconds: float
    shell: bool = False
    stdin_devnull: bool = True
    capture_output: bool = True
    environment: tuple[tuple[str, str], ...] = _MINIMAL_ENVIRONMENT


RemovalSubprocessRunner = Callable[[RemovalSubprocessRequest], SubprocessResult]


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
                f"{_API_SECRET_PURPOSE}{credential_ref}",
            ),
            timeout_seconds=self._timeout_seconds,
        )

        stdout = _retrieve_once(self._runner, request)
        secret = _decode_secret(stdout)
        return OneUseSecretLease(secret)

    def __repr__(self) -> str:
        return "<AppleKeychainCredentialSource redacted>"

    def __str__(self) -> str:
        return "<AppleKeychainCredentialSource redacted>"

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("CREDENTIAL_SOURCE_SERIALIZATION_PROHIBITED")


class AppleKeychainApiKeySource:
    """Retrieve one protected API key for an application-registration reference."""

    __slots__ = ("_provider", "_runner", "_timeout_seconds")

    def __init__(
        self,
        *,
        provider: str,
        runner: SubprocessRunner,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not _valid_reference(provider) or not (
            0 < timeout_seconds <= MAX_TIMEOUT_SECONDS
        ):
            raise AppleKeychainCredentialError(
                CredentialRetrievalOutcome.MALFORMED
            )
        self._provider = provider.lower()
        self._runner = runner
        self._timeout_seconds = timeout_seconds

    def acquire(self, application_registration_ref: str) -> SecretLease:
        """Acquire one API-key lease without exposing its value."""

        if not _valid_reference(application_registration_ref):
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
                f"{_API_KEY_PURPOSE}{application_registration_ref}",
            ),
            timeout_seconds=self._timeout_seconds,
        )
        stdout = _retrieve_once(self._runner, request)
        api_key = _decode_secret(stdout)
        return OneUseSecretLease(api_key)

    def __repr__(self) -> str:
        return "<AppleKeychainApiKeySource redacted>"

    __str__ = __repr__

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("API_KEY_SOURCE_SERIALIZATION_PROHIBITED")


class AppleKeychainCredentialProvisioner:
    """Setup-only writer for API-key and API-secret Keychain items."""

    __slots__ = ("_provider", "_runner", "_timeout_seconds")

    def __init__(
        self,
        *,
        provider: str,
        runner: ProvisioningSubprocessRunner,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not _valid_reference(provider) or not (
            0 < timeout_seconds <= MAX_TIMEOUT_SECONDS
        ):
            raise AppleKeychainCredentialError(
                CredentialRetrievalOutcome.MALFORMED
            )
        self._provider = provider.lower()
        self._runner = runner
        self._timeout_seconds = timeout_seconds

    def store_api_key(self, reference: str, value: str) -> None:
        self._store(_API_KEY_PURPOSE, reference, value)

    def store_api_secret(self, reference: str, value: str) -> None:
        self._store(_API_SECRET_PURPOSE, reference, value)

    def store_intended_principal(self, reference: str, value: str) -> None:
        self._store(_INTENDED_PRINCIPAL_PURPOSE, reference, value)

    def _store(self, purpose: str, reference: str, value: str) -> None:
        if (
            purpose
            not in {
                _API_KEY_PURPOSE,
                _API_SECRET_PURPOSE,
                _INTENDED_PRINCIPAL_PURPOSE,
            }
            or not _valid_reference(reference)
            or not isinstance(value, str)
            or not value
            or "\x00" in value
            or "\n" in value
            or "\r" in value
        ):
            raise AppleKeychainCredentialError(
                CredentialRetrievalOutcome.MALFORMED
            )
        request = ProvisioningSubprocessRequest(
            argv=(
                SECURITY_EXECUTABLE,
                "add-generic-password",
                "-U",
                "-s",
                f"{SERVICE_PREFIX}{self._provider}",
                "-a",
                f"{purpose}{reference}",
                "-w",
            ),
            timeout_seconds=self._timeout_seconds,
        )
        secret_input = value.encode("utf-8") + b"\n"
        try:
            result = self._runner(request, secret_input)
            stdout, stderr = result._take_output()
            stdout = b""
            stderr = b""
            if result.returncode != 0:
                raise AppleKeychainCredentialError(
                    _outcome_for_returncode(result.returncode)
                )
        except AppleKeychainCredentialError:
            raise
        except TimeoutError:
            raise AppleKeychainCredentialError(
                CredentialRetrievalOutcome.TIMED_OUT
            ) from None
        except Exception:
            raise AppleKeychainCredentialError(
                CredentialRetrievalOutcome.BACKEND_UNAVAILABLE
            ) from None
        finally:
            secret_input = b""

    def __repr__(self) -> str:
        return "<AppleKeychainCredentialProvisioner redacted>"

    __str__ = __repr__

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("CREDENTIAL_PROVISIONER_SERIALIZATION_PROHIBITED")


class AppleKeychainCredentialPresenceProbe:
    """Check item presence without retrieving API-key or API-secret values."""

    __slots__ = ("_provider", "_runner", "_timeout_seconds")

    def __init__(
        self,
        *,
        provider: str,
        runner: PresenceSubprocessRunner,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not _valid_reference(provider) or not (
            0 < timeout_seconds <= MAX_TIMEOUT_SECONDS
        ):
            raise AppleKeychainCredentialError(
                CredentialRetrievalOutcome.MALFORMED
            )
        self._provider = provider.lower()
        self._runner = runner
        self._timeout_seconds = timeout_seconds

    def api_key_stored(self, reference: str) -> bool:
        return self._stored(_API_KEY_PURPOSE, reference)

    def api_secret_stored(self, reference: str) -> bool:
        return self._stored(_API_SECRET_PURPOSE, reference)

    def intended_principal_stored(self, reference: str) -> bool:
        return self._stored(_INTENDED_PRINCIPAL_PURPOSE, reference)

    def _stored(self, purpose: str, reference: str) -> bool:
        if (
            purpose
            not in {
                _API_KEY_PURPOSE,
                _API_SECRET_PURPOSE,
                _INTENDED_PRINCIPAL_PURPOSE,
            }
            or not _valid_reference(reference)
        ):
            raise AppleKeychainCredentialError(
                CredentialRetrievalOutcome.MALFORMED
            )
        request = PresenceSubprocessRequest(
            argv=(
                SECURITY_EXECUTABLE,
                "find-generic-password",
                "-s",
                f"{SERVICE_PREFIX}{self._provider}",
                "-a",
                f"{purpose}{reference}",
            ),
            timeout_seconds=self._timeout_seconds,
        )
        try:
            result = self._runner(request)
            result._take_output()
        except TimeoutError:
            raise AppleKeychainCredentialError(
                CredentialRetrievalOutcome.TIMED_OUT
            ) from None
        except AppleKeychainCredentialError:
            raise
        except Exception:
            raise AppleKeychainCredentialError(
                CredentialRetrievalOutcome.BACKEND_UNAVAILABLE
            ) from None
        if result.returncode == 0:
            return True
        if result.returncode in _MISSING_RETURN_CODES:
            return False
        raise AppleKeychainCredentialError(
            _outcome_for_returncode(result.returncode)
        )

    def __repr__(self) -> str:
        return "<AppleKeychainCredentialPresenceProbe redacted>"

    __str__ = __repr__

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("CREDENTIAL_PRESENCE_PROBE_SERIALIZATION_PROHIBITED")


class AppleKeychainCredentialRemover:
    """Explicit setup-boundary removal without retrieving protected values."""

    __slots__ = ("_provider", "_runner", "_timeout_seconds")

    def __init__(
        self,
        *,
        provider: str,
        runner: RemovalSubprocessRunner,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not _valid_reference(provider) or not (
            0 < timeout_seconds <= MAX_TIMEOUT_SECONDS
        ):
            raise AppleKeychainCredentialError(
                CredentialRetrievalOutcome.MALFORMED
            )
        self._provider = provider.lower()
        self._runner = runner
        self._timeout_seconds = timeout_seconds

    def remove_api_key(self, reference: str) -> None:
        self._remove(_API_KEY_PURPOSE, reference)

    def remove_api_secret(self, reference: str) -> None:
        self._remove(_API_SECRET_PURPOSE, reference)

    def _remove(self, purpose: str, reference: str) -> None:
        if purpose not in {_API_KEY_PURPOSE, _API_SECRET_PURPOSE} or not _valid_reference(
            reference
        ):
            raise AppleKeychainCredentialError(
                CredentialRetrievalOutcome.MALFORMED
            )
        request = RemovalSubprocessRequest(
            argv=(
                SECURITY_EXECUTABLE,
                "delete-generic-password",
                "-s",
                f"{SERVICE_PREFIX}{self._provider}",
                "-a",
                f"{purpose}{reference}",
            ),
            timeout_seconds=self._timeout_seconds,
        )
        try:
            result = self._runner(request)
            result._take_output()
        except TimeoutError:
            raise AppleKeychainCredentialError(
                CredentialRetrievalOutcome.TIMED_OUT
            ) from None
        except AppleKeychainCredentialError:
            raise
        except Exception:
            raise AppleKeychainCredentialError(
                CredentialRetrievalOutcome.BACKEND_UNAVAILABLE
            ) from None
        if result.returncode not in {0, *_MISSING_RETURN_CODES}:
            raise AppleKeychainCredentialError(
                _outcome_for_returncode(result.returncode)
            )

    def __repr__(self) -> str:
        return "<AppleKeychainCredentialRemover redacted>"

    __str__ = __repr__

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("CREDENTIAL_REMOVER_SERIALIZATION_PROHIBITED")


class AppleKeychainIntendedPrincipalResolver:
    """Resolve one intended principal through retrieval-only Keychain custody."""

    __slots__ = ("_provider", "_runner", "_timeout_seconds")

    def __init__(
        self,
        *,
        provider: str,
        runner: SubprocessRunner,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not _valid_reference(provider) or not (
            0 < timeout_seconds <= MAX_TIMEOUT_SECONDS
        ):
            raise AppleKeychainCredentialError(
                CredentialRetrievalOutcome.MALFORMED
            )
        self._provider = provider.lower()
        self._runner = runner
        self._timeout_seconds = timeout_seconds

    def use_resolved_once(
        self,
        registration_ref: str,
        operation: Callable[[IntendedPrincipalLease], PrincipalBindingResult],
    ) -> IntendedPrincipalResolutionResult:
        """Supply one protected principal lease and retain only its outcome."""

        if not _valid_reference(registration_ref) or not callable(operation):
            return IntendedPrincipalResolutionResult(
                IntendedPrincipalResolutionOutcome.INVALID_CONFIGURATION
            )

        request = SubprocessRequest(
            argv=(
                SECURITY_EXECUTABLE,
                "find-generic-password",
                "-w",
                "-s",
                f"{SERVICE_PREFIX}{self._provider}",
                "-a",
                f"{_INTENDED_PRINCIPAL_PURPOSE}{registration_ref}",
            ),
            timeout_seconds=self._timeout_seconds,
        )
        try:
            stdout = _retrieve_once(self._runner, request)
        except AppleKeychainCredentialError as error:
            return IntendedPrincipalResolutionResult(
                _principal_outcome(error.outcome)
            )

        try:
            expected_principal = _decode_principal(stdout)
            lease = OneUseIntendedPrincipalLease(expected_principal)
        except Exception:
            return IntendedPrincipalResolutionResult(
                IntendedPrincipalResolutionOutcome.SANITIZED_FAILURE
            )
        finally:
            stdout = b""

        del expected_principal
        try:
            result = operation(lease)
            if not isinstance(result, PrincipalBindingResult):
                raise TypeError("PRINCIPAL_BINDING_RESULT_INVALID")
        except Exception:
            return IntendedPrincipalResolutionResult(
                IntendedPrincipalResolutionOutcome.SANITIZED_FAILURE
            )
        finally:
            lease.close()

        return IntendedPrincipalResolutionResult(
            IntendedPrincipalResolutionOutcome.RESOLVED,
            result,
        )

    def __repr__(self) -> str:
        return "<AppleKeychainIntendedPrincipalResolver redacted>"

    __str__ = __repr__

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("INTENDED_PRINCIPAL_RESOLVER_SERIALIZATION_PROHIBITED")


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


def run_security_framework_subprocess(
    request: SubprocessRequest,
) -> SubprocessResult:
    """Retrieve through Security.framework under the KRONOS process identity."""

    if not _valid_security_request(request):
        raise AppleKeychainCredentialError(CredentialRetrievalOutcome.MALFORMED)
    service = request.argv[4].encode("utf-8")
    account = request.argv[6].encode("utf-8")
    try:
        status, value = _security_framework_retrieve(service, account)
    except Exception:
        raise AppleKeychainCredentialError(
            CredentialRetrievalOutcome.BACKEND_UNAVAILABLE
        ) from None
    return SubprocessResult(status, value, b"")


def run_security_provisioning_subprocess(
    request: ProvisioningSubprocessRequest,
    secret_input: bytes,
) -> SubprocessResult:
    """Write one item using stdin; the credential never enters argv."""

    if not _valid_provisioning_request(request) or not isinstance(
        secret_input,
        bytes,
    ):
        raise AppleKeychainCredentialError(CredentialRetrievalOutcome.MALFORMED)
    try:
        completed = subprocess.run(
            request.argv,
            shell=False,
            check=False,
            input=secret_input,
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


def run_security_framework_provisioning(
    request: ProvisioningSubprocessRequest,
    secret_input: bytes,
) -> SubprocessResult:
    """Store one credential through Security.framework, never a command line."""

    if (
        not _valid_provisioning_request(request)
        or not isinstance(secret_input, bytes)
        or not secret_input.endswith(b"\n")
        or len(secret_input) <= 1
    ):
        raise AppleKeychainCredentialError(CredentialRetrievalOutcome.MALFORMED)
    service = request.argv[4].encode("utf-8")
    account = request.argv[6].encode("utf-8")
    password = secret_input[:-1]
    try:
        status = _security_framework_store(service, account, password)
    except Exception:
        raise AppleKeychainCredentialError(
            CredentialRetrievalOutcome.BACKEND_UNAVAILABLE
        ) from None
    finally:
        password = b""
    return SubprocessResult(status, b"", b"")


def _security_framework_store(
    service: bytes,
    account: bytes,
    password: bytes,
) -> int:
    security = ctypes.CDLL(
        "/System/Library/Frameworks/Security.framework/Security"
    )
    core_foundation = ctypes.CDLL(
        "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
    )
    uint32 = ctypes.c_uint32
    pointer = ctypes.c_void_p
    status_type = ctypes.c_int32
    security.SecKeychainFindGenericPassword.argtypes = (
        pointer,
        uint32,
        pointer,
        uint32,
        pointer,
        pointer,
        pointer,
        ctypes.POINTER(pointer),
    )
    security.SecKeychainFindGenericPassword.restype = status_type
    security.SecKeychainAddGenericPassword.argtypes = (
        pointer,
        uint32,
        pointer,
        uint32,
        pointer,
        uint32,
        pointer,
        ctypes.POINTER(pointer),
    )
    security.SecKeychainAddGenericPassword.restype = status_type
    security.SecKeychainItemModifyAttributesAndData.argtypes = (
        pointer,
        pointer,
        uint32,
        pointer,
    )
    security.SecKeychainItemModifyAttributesAndData.restype = status_type
    core_foundation.CFRelease.argtypes = (pointer,)
    core_foundation.CFRelease.restype = None

    service_buffer = ctypes.create_string_buffer(service)
    account_buffer = ctypes.create_string_buffer(account)
    password_buffer = ctypes.create_string_buffer(password)
    item = pointer()
    status = security.SecKeychainFindGenericPassword(
        None,
        len(service),
        service_buffer,
        len(account),
        account_buffer,
        None,
        None,
        ctypes.byref(item),
    )
    try:
        if status == 0:
            return int(
                security.SecKeychainItemModifyAttributesAndData(
                    item,
                    None,
                    len(password),
                    password_buffer,
                )
            )
        if status == -25300:
            return int(
                security.SecKeychainAddGenericPassword(
                    None,
                    len(service),
                    service_buffer,
                    len(account),
                    account_buffer,
                    len(password),
                    password_buffer,
                    None,
                )
            )
        return int(status)
    finally:
        if item.value:
            core_foundation.CFRelease(item)


def _security_framework_retrieve(
    service: bytes,
    account: bytes,
) -> tuple[int, bytes]:
    security = ctypes.CDLL(
        "/System/Library/Frameworks/Security.framework/Security"
    )
    uint32 = ctypes.c_uint32
    pointer = ctypes.c_void_p
    status_type = ctypes.c_int32
    security.SecKeychainFindGenericPassword.argtypes = (
        pointer,
        uint32,
        pointer,
        uint32,
        pointer,
        ctypes.POINTER(uint32),
        ctypes.POINTER(pointer),
        pointer,
    )
    security.SecKeychainFindGenericPassword.restype = status_type
    security.SecKeychainItemFreeContent.argtypes = (pointer, pointer)
    security.SecKeychainItemFreeContent.restype = status_type

    service_buffer = ctypes.create_string_buffer(service)
    account_buffer = ctypes.create_string_buffer(account)
    value_length = uint32()
    value_pointer = pointer()
    status = int(
        security.SecKeychainFindGenericPassword(
            None,
            len(service),
            service_buffer,
            len(account),
            account_buffer,
            ctypes.byref(value_length),
            ctypes.byref(value_pointer),
            None,
        )
    )
    if status != 0:
        return status, b""
    try:
        return status, ctypes.string_at(value_pointer, value_length.value) + b"\n"
    finally:
        security.SecKeychainItemFreeContent(None, value_pointer)


def run_security_presence_subprocess(
    request: PresenceSubprocessRequest,
) -> SubprocessResult:
    """Inspect Keychain item presence without requesting its value."""

    if not _valid_presence_request(request):
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


def run_security_framework_removal(
    request: RemovalSubprocessRequest,
) -> SubprocessResult:
    """Delete one credential through Security.framework without reading it."""

    if not _valid_removal_request(request):
        raise AppleKeychainCredentialError(CredentialRetrievalOutcome.MALFORMED)
    service = request.argv[3].encode("utf-8")
    account = request.argv[5].encode("utf-8")
    try:
        status = _security_framework_remove(service, account)
    except Exception:
        raise AppleKeychainCredentialError(
            CredentialRetrievalOutcome.BACKEND_UNAVAILABLE
        ) from None
    return SubprocessResult(status, b"", b"")


def _security_framework_remove(service: bytes, account: bytes) -> int:
    security = ctypes.CDLL(
        "/System/Library/Frameworks/Security.framework/Security"
    )
    core_foundation = ctypes.CDLL(
        "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
    )
    uint32 = ctypes.c_uint32
    pointer = ctypes.c_void_p
    status_type = ctypes.c_int32
    security.SecKeychainFindGenericPassword.argtypes = (
        pointer, uint32, pointer, uint32, pointer, pointer, pointer,
        ctypes.POINTER(pointer),
    )
    security.SecKeychainFindGenericPassword.restype = status_type
    security.SecKeychainItemDelete.argtypes = (pointer,)
    security.SecKeychainItemDelete.restype = status_type
    core_foundation.CFRelease.argtypes = (pointer,)
    core_foundation.CFRelease.restype = None
    service_buffer = ctypes.create_string_buffer(service)
    account_buffer = ctypes.create_string_buffer(account)
    item = pointer()
    status = int(security.SecKeychainFindGenericPassword(
        None, len(service), service_buffer, len(account), account_buffer,
        None, None, ctypes.byref(item),
    ))
    try:
        return int(security.SecKeychainItemDelete(item)) if status == 0 else status
    finally:
        if item.value:
            core_foundation.CFRelease(item)


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
    ):
        return False
    account_reference = _account_reference(account)
    return (
        _valid_reference(service.removeprefix(SERVICE_PREFIX))
        and account_reference is not None
        and _valid_reference(account_reference)
    )


def _valid_provisioning_request(request: ProvisioningSubprocessRequest) -> bool:
    if request.shell or not request.capture_output:
        return False
    if not 0 < request.timeout_seconds <= MAX_TIMEOUT_SECONDS:
        return False
    if len(request.argv) != 8:
        return False
    executable, operation, update, service_flag, service, account_flag, account, prompt = (
        request.argv
    )
    account_reference = _account_reference(account)
    return (
        executable == SECURITY_EXECUTABLE
        and operation == "add-generic-password"
        and update == "-U"
        and service_flag == "-s"
        and account_flag == "-a"
        and prompt == "-w"
        and service.startswith(SERVICE_PREFIX)
        and _valid_reference(service.removeprefix(SERVICE_PREFIX))
        and account_reference is not None
        and _valid_reference(account_reference)
        and account.startswith(
            (
                _API_KEY_PURPOSE,
                _API_SECRET_PURPOSE,
                _INTENDED_PRINCIPAL_PURPOSE,
            )
        )
    )


def _valid_presence_request(request: PresenceSubprocessRequest) -> bool:
    if request.shell or not request.stdin_devnull or not request.capture_output:
        return False
    if not 0 < request.timeout_seconds <= MAX_TIMEOUT_SECONDS:
        return False
    if len(request.argv) != 6:
        return False
    executable, operation, service_flag, service, account_flag, account = request.argv
    account_reference = _account_reference(account)
    return (
        executable == SECURITY_EXECUTABLE
        and operation == "find-generic-password"
        and service_flag == "-s"
        and account_flag == "-a"
        and service.startswith(SERVICE_PREFIX)
        and _valid_reference(service.removeprefix(SERVICE_PREFIX))
        and account_reference is not None
        and _valid_reference(account_reference)
        and account.startswith(
            (
                _API_KEY_PURPOSE,
                _API_SECRET_PURPOSE,
                _INTENDED_PRINCIPAL_PURPOSE,
            )
        )
    )


def _valid_removal_request(request: RemovalSubprocessRequest) -> bool:
    if request.shell or not request.stdin_devnull or not request.capture_output:
        return False
    if not 0 < request.timeout_seconds <= MAX_TIMEOUT_SECONDS:
        return False
    if len(request.argv) != 6:
        return False
    executable, operation, service_flag, service, account_flag, account = request.argv
    account_reference = _account_reference(account)
    return (
        executable == SECURITY_EXECUTABLE
        and operation == "delete-generic-password"
        and service_flag == "-s"
        and account_flag == "-a"
        and service.startswith(SERVICE_PREFIX)
        and _valid_reference(service.removeprefix(SERVICE_PREFIX))
        and account_reference is not None
        and _valid_reference(account_reference)
        and account.startswith((_API_KEY_PURPOSE, _API_SECRET_PURPOSE))
    )


def _account_reference(account: str) -> str | None:
    for purpose in _ALLOWED_ACCOUNT_PURPOSES:
        if account.startswith(purpose):
            return account.removeprefix(purpose)
    return None


def _valid_reference(value: object) -> bool:
    return isinstance(value, str) and _REFERENCE_PATTERN.fullmatch(value) is not None


def _outcome_for_returncode(returncode: int) -> CredentialRetrievalOutcome:
    if returncode in _MISSING_RETURN_CODES:
        return CredentialRetrievalOutcome.MISSING
    if returncode in _ACCESS_DENIED_RETURN_CODES:
        return CredentialRetrievalOutcome.ACCESS_DENIED
    return CredentialRetrievalOutcome.BACKEND_UNAVAILABLE


def _retrieve_once(
    runner: SubprocessRunner,
    request: SubprocessRequest,
) -> bytes:
    try:
        result = runner(request)
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
        raise AppleKeychainCredentialError(CredentialRetrievalOutcome.MALFORMED)

    returncode = result.returncode
    stdout, stderr = result._take_output()
    if returncode != 0:
        stdout = b""
        stderr = b""
        raise AppleKeychainCredentialError(_outcome_for_returncode(returncode))
    if stderr:
        stdout = b""
        stderr = b""
        raise AppleKeychainCredentialError(CredentialRetrievalOutcome.MALFORMED)
    return stdout


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


def _decode_principal(stdout: bytes) -> str:
    principal = _decode_secret(stdout)
    if (
        principal != principal.strip()
        or _PRINCIPAL_PATTERN.fullmatch(principal) is None
    ):
        principal = ""
        raise AppleKeychainCredentialError(CredentialRetrievalOutcome.MALFORMED)
    return principal


def _principal_outcome(
    outcome: CredentialRetrievalOutcome,
) -> IntendedPrincipalResolutionOutcome:
    return {
        CredentialRetrievalOutcome.MISSING: (
            IntendedPrincipalResolutionOutcome.NOT_FOUND
        ),
        CredentialRetrievalOutcome.ACCESS_DENIED: (
            IntendedPrincipalResolutionOutcome.ACCESS_DENIED
        ),
        CredentialRetrievalOutcome.BACKEND_UNAVAILABLE: (
            IntendedPrincipalResolutionOutcome.BACKEND_UNAVAILABLE
        ),
        CredentialRetrievalOutcome.TIMED_OUT: (
            IntendedPrincipalResolutionOutcome.BACKEND_UNAVAILABLE
        ),
        CredentialRetrievalOutcome.MALFORMED: (
            IntendedPrincipalResolutionOutcome.SANITIZED_FAILURE
        ),
        CredentialRetrievalOutcome.FOUND: (
            IntendedPrincipalResolutionOutcome.SANITIZED_FAILURE
        ),
    }[outcome]


__all__ = [
    "AppleKeychainCredentialError",
    "AppleKeychainCredentialSource",
    "AppleKeychainIntendedPrincipalResolver",
    "SubprocessRequest",
    "SubprocessResult",
    "run_security_subprocess",
]
