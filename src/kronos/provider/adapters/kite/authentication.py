"""Adapter-local Kite exchange, candidate and verification containment."""

from __future__ import annotations

import re
from enum import StrEnum

from kiteconnect.exceptions import (
    DataException as _DataException,
    KiteException as _KiteException,
    NetworkException as _NetworkException,
    PermissionException as _PermissionException,
    TokenException as _TokenException,
)
from requests.exceptions import (
    ConnectionError as _RequestsConnectionError,
    Timeout as _RequestsTimeout,
)

from kronos.configuration.credentials import SecretLease
from kronos.configuration.principals import PrincipalBindingResult, PrincipalEvidence
from kronos.provider.adapters.kite.client import (
    _KiteAuthenticationClientHandle,
    _KiteCandidateClientHandle,
    _KiteCleanupError,
    _KiteClientClosedError,
    _KiteExchangeAlreadyAttempted,
    _KiteSessionInvalidated,
    _UnexpectedAuthenticationResponse,
    _UnexpectedProfileResponse,
    _create_kite_authentication_client,
)
from kronos.provider.contracts.provider_authentication import OneUseRequestToken
from kronos.provider.exceptions.connectivity import (
    ProviderConnectivityError,
    ProviderErrorCode,
)


_CANONICAL_PRINCIPAL = re.compile(r"[A-Za-z0-9]{1,64}\Z")


class KiteContextEvidence(StrEnum):
    """Sanitized result of one explicit Kite availability verification."""

    VALID = "CONTEXT_VALID"
    INVALID = "CONTEXT_INVALID"
    UNAVAILABLE = "PROVIDER_OPERATIONALLY_UNAVAILABLE"


class _KitePrincipalEvidence:
    """One-use minimum principal evidence with no raw-value getter."""

    __slots__ = ("_closed", "_forced", "_principal", "_used")

    def __init__(
        self,
        principal: str | None,
        *,
        forced: PrincipalBindingResult | None = None,
    ) -> None:
        self._principal = principal
        self._forced = forced
        self._used = False
        self._closed = False

    def compare_expected(self, expected_principal: str) -> PrincipalBindingResult:
        if self._closed or self._used:
            raise RuntimeError("PRINCIPAL_EVIDENCE_UNAVAILABLE")
        self._used = True
        principal = self._principal
        self._principal = None
        try:
            if self._forced is not None:
                return self._forced
            if not _canonical_principal(principal) or not _canonical_principal(
                expected_principal
            ):
                return PrincipalBindingResult.UNCONFIRMED
            return (
                PrincipalBindingResult.MATCHED
                if principal == expected_principal
                else PrincipalBindingResult.MISMATCHED
            )
        finally:
            self.close()

    def close(self) -> None:
        self._principal = None
        self._closed = True

    def __repr__(self) -> str:
        return "<_KitePrincipalEvidence redacted>"

    __str__ = __repr__

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("KITE_PRINCIPAL_EVIDENCE_SERIALIZATION_PROHIBITED")


class _KiteCandidateContext:
    """Opaque unpublished candidate restricted to bounded verification."""

    __slots__ = ("__disposed", "__handle")

    def __init__(self, handle: _KiteCandidateClientHandle) -> None:
        self.__handle: _KiteCandidateClientHandle | None = handle
        self.__disposed = False

    def principal_evidence(self) -> PrincipalEvidence:
        handle = self._active_handle()
        try:
            principal = handle.principal_user_id_once()
        except Exception as error:
            code = _map_authentication_error_code(error)
        else:
            return _KitePrincipalEvidence(principal)

        if code is ProviderErrorCode.UNEXPECTED_RESPONSE:
            return _KitePrincipalEvidence(
                None,
                forced=PrincipalBindingResult.UNCONFIRMED,
            )
        if _operationally_unavailable(code):
            return _KitePrincipalEvidence(
                None,
                forced=PrincipalBindingResult.UNAVAILABLE,
            )
        raise ProviderConnectivityError(code) from None

    def verify_provider_availability(self) -> KiteContextEvidence:
        """Run one separate, explicitly initiated profile verification."""

        try:
            self._active_handle().verify_profile_once()
        except Exception as error:
            code = _map_authentication_error_code(error)
        else:
            return KiteContextEvidence.VALID
        if code is ProviderErrorCode.ACCESS_TOKEN_INVALID_OR_EXPIRED:
            return KiteContextEvidence.INVALID
        if _operationally_unavailable(code):
            return KiteContextEvidence.UNAVAILABLE
        raise ProviderConnectivityError(code) from None

    def dispose_local(self) -> None:
        """Release only local SDK/session state; never mutate Provider state."""

        if self.__disposed:
            return
        self.__disposed = True
        handle = self.__handle
        self.__handle = None
        if handle is None:
            return
        try:
            handle.close_local()
        except Exception as error:
            code = _map_authentication_error_code(error)
        else:
            return
        raise ProviderConnectivityError(code)

    def _active_handle(self) -> _KiteCandidateClientHandle:
        handle = self.__handle
        if self.__disposed or handle is None:
            raise ProviderConnectivityError(ProviderErrorCode.INTERNAL_ADAPTER_DEFECT)
        return handle

    def __repr__(self) -> str:
        return "<_KiteCandidateContext redacted>"

    __str__ = __repr__

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("KITE_CANDIDATE_SERIALIZATION_PROHIBITED")


class KiteAuthenticationAdapter:
    """Contain SDK and credential mechanics behind the Kite boundary."""

    __slots__ = ("__api_secret", "__client", "__legacy_candidate")

    def __init__(
        self,
        api_secret: str | None,
        client: _KiteAuthenticationClientHandle,
    ) -> None:
        self.__api_secret = api_secret
        self.__client: _KiteAuthenticationClientHandle | None = client
        self.__legacy_candidate: _KiteCandidateContext | None = None

    def login_url(self, redirect_uri: str | None = None) -> str:
        if redirect_uri is not None and not redirect_uri:
            raise ProviderConnectivityError(
                ProviderErrorCode.INTERNAL_ADAPTER_DEFECT
            )
        client = self.__client
        if client is None:
            raise ProviderConnectivityError(
                ProviderErrorCode.INTERNAL_ADAPTER_DEFECT
            )
        try:
            return client.login_url()
        except Exception as error:
            code = _map_authentication_error_code(error)
        raise ProviderConnectivityError(code)

    def exchange_once(
        self,
        request_token: OneUseRequestToken,
        api_secret: SecretLease,
    ) -> _KiteCandidateContext:
        """Consume one token and secret and return one unpublished candidate."""

        self.__api_secret = None

        def exchange_token(raw_token: str) -> _KiteCandidateContext:
            return api_secret.reveal_for_call(
                lambda raw_secret: self.__exchange_values(
                    raw_token,
                    raw_secret,
                )
            )

        try:
            candidate = request_token.consume_for_call(exchange_token)
        except ProviderConnectivityError:
            raise
        except Exception as error:
            code = _map_authentication_error_code(error)
        else:
            if not isinstance(candidate, _KiteCandidateContext):
                raise ProviderConnectivityError(
                    ProviderErrorCode.INTERNAL_ADAPTER_DEFECT
                )
            return candidate
        raise ProviderConnectivityError(code)

    def exchange(self, request_token: str) -> _KiteCandidateContext:
        """Compatibility bridge retained until the Stage 4 caller migration."""

        api_secret = self.__api_secret
        self.__api_secret = None
        if api_secret is None:
            raise ProviderConnectivityError(
                ProviderErrorCode.INTERNAL_ADAPTER_DEFECT
            )
        try:
            candidate = self.__exchange_values(request_token, api_secret)
        finally:
            del api_secret
        self.__legacy_candidate = candidate
        return candidate

    def context_evidence(self) -> KiteContextEvidence:
        """Compatibility bridge to separately invoked availability verification."""

        candidate = self.__legacy_candidate
        if candidate is None:
            raise ProviderConnectivityError(
                ProviderErrorCode.INTERNAL_ADAPTER_DEFECT
            )
        return candidate.verify_provider_availability()

    def terminate(self) -> None:
        """Compatibility bridge that performs local disposal only."""

        candidate = self.__legacy_candidate
        self.__legacy_candidate = None
        if candidate is not None:
            candidate.dispose_local()

    def __exchange_values(
        self,
        request_token: str,
        api_secret: str,
    ) -> _KiteCandidateContext:
        client = self.__client
        if client is None:
            raise ProviderConnectivityError(
                ProviderErrorCode.INTERNAL_ADAPTER_DEFECT
            )
        try:
            handle = client.exchange_once(request_token, api_secret)
        except Exception as error:
            code = _map_authentication_error_code(error)
        else:
            self.__client = None
            return _KiteCandidateContext(handle)
        raise ProviderConnectivityError(code)

    def __repr__(self) -> str:
        return "<KiteAuthenticationAdapter redacted>"

    __str__ = __repr__

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("KITE_AUTHENTICATION_ADAPTER_SERIALIZATION_PROHIBITED")


def create_kite_authentication_adapter(
    api_key: str,
    api_secret: str | None = None,
) -> KiteAuthenticationAdapter:
    try:
        client = _create_kite_authentication_client(api_key)
    except Exception as error:
        code = _map_authentication_error_code(error)
    else:
        return KiteAuthenticationAdapter(api_secret, client)
    raise ProviderConnectivityError(code)


def _canonical_principal(value: object) -> bool:
    return (
        isinstance(value, str)
        and value == value.strip()
        and _CANONICAL_PRINCIPAL.fullmatch(value) is not None
    )


def _operationally_unavailable(code: ProviderErrorCode) -> bool:
    return code in {
        ProviderErrorCode.NETWORK_TIMEOUT,
        ProviderErrorCode.CONNECTION_FAILURE,
        ProviderErrorCode.RATE_LIMITED,
        ProviderErrorCode.PROVIDER_SERVICE_FAILURE,
    }


def _map_authentication_error_code(error: Exception) -> ProviderErrorCode:
    if isinstance(error, (_KiteSessionInvalidated, _TokenException)):
        return ProviderErrorCode.ACCESS_TOKEN_INVALID_OR_EXPIRED
    if isinstance(error, _PermissionException):
        return ProviderErrorCode.AUTHENTICATION_REJECTED
    if isinstance(error, (_RequestsTimeout, TimeoutError)):
        return ProviderErrorCode.NETWORK_TIMEOUT
    if isinstance(error, (_RequestsConnectionError, ConnectionError, OSError)):
        return ProviderErrorCode.CONNECTION_FAILURE
    if isinstance(
        error,
        (
            _UnexpectedAuthenticationResponse,
            _UnexpectedProfileResponse,
            _DataException,
        ),
    ):
        return ProviderErrorCode.UNEXPECTED_RESPONSE
    if isinstance(error, (_NetworkException, _KiteException)):
        status_code = getattr(error, "code", None)
        return (
            ProviderErrorCode.RATE_LIMITED
            if status_code == 429
            else ProviderErrorCode.PROVIDER_SERVICE_FAILURE
        )
    if isinstance(
        error,
        (_KiteCleanupError, _KiteClientClosedError, _KiteExchangeAlreadyAttempted),
    ):
        return ProviderErrorCode.INTERNAL_ADAPTER_DEFECT
    if isinstance(error, ProviderConnectivityError):
        return error.code
    return ProviderErrorCode.INTERNAL_ADAPTER_DEFECT


__all__ = [
    "KiteAuthenticationAdapter",
    "KiteContextEvidence",
    "create_kite_authentication_adapter",
]
