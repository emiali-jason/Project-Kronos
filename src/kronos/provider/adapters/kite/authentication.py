"""Adapter-local access to the official Kite authentication lifecycle."""

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

from kronos.provider.adapters.kite.client import (
    _KiteAuthenticationClientHandle,
    _KiteSessionInvalidated,
    _UnexpectedAuthenticationResponse,
    _UnexpectedProfileResponse,
    _create_kite_authentication_client,
)
from kronos.provider.exceptions.connectivity import (
    ProviderConnectivityError,
    ProviderErrorCode,
)


class KiteContextEvidence(StrEnum):
    """Provider evidence for an already established Kite context."""

    VALID = "CONTEXT_VALID"
    INVALID = "CONTEXT_INVALID"
    UNAVAILABLE = "PROVIDER_OPERATIONALLY_UNAVAILABLE"


class KiteAuthenticationAdapter:
    """Contain SDK and credential mechanics behind the Kite boundary."""

    __slots__ = ("__api_secret", "__client")

    def __init__(
        self,
        api_secret: str,
        client: _KiteAuthenticationClientHandle,
    ) -> None:
        self.__api_secret: str | None = api_secret
        self.__client = client

    def login_url(self) -> str:
        try:
            login_url = self.__client.login_url()
        except Exception as error:
            code = _map_authentication_error_code(error)
        else:
            return login_url
        raise ProviderConnectivityError(code)

    def exchange(self, request_token: str) -> None:
        api_secret = self.__api_secret
        self.__api_secret = None
        if api_secret is None:
            raise ProviderConnectivityError(
                ProviderErrorCode.INTERNAL_ADAPTER_DEFECT
            )
        try:
            self.__client.exchange(request_token, api_secret)
        except Exception as error:
            code = _map_authentication_error_code(error)
        else:
            return
        finally:
            del api_secret
        raise ProviderConnectivityError(code)

    def context_evidence(self) -> KiteContextEvidence:
        try:
            self.__client.verify()
        except Exception as error:
            code = _map_authentication_error_code(error)
        else:
            return KiteContextEvidence.VALID
        if code is ProviderErrorCode.ACCESS_TOKEN_INVALID_OR_EXPIRED:
            return KiteContextEvidence.INVALID
        if code in {
            ProviderErrorCode.NETWORK_TIMEOUT,
            ProviderErrorCode.CONNECTION_FAILURE,
            ProviderErrorCode.RATE_LIMITED,
            ProviderErrorCode.PROVIDER_SERVICE_FAILURE,
        }:
            return KiteContextEvidence.UNAVAILABLE
        raise ProviderConnectivityError(code)

    def terminate(self) -> None:
        try:
            self.__client.terminate()
        except Exception as error:
            code = _map_authentication_error_code(error)
        else:
            return
        raise ProviderConnectivityError(code)


def create_kite_authentication_adapter(
    api_key: str,
    api_secret: str,
) -> KiteAuthenticationAdapter:
    try:
        client = _create_kite_authentication_client(api_key)
    except Exception as error:
        code = _map_authentication_error_code(error)
    else:
        return KiteAuthenticationAdapter(api_secret, client)
    raise ProviderConnectivityError(code)


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
    return ProviderErrorCode.INTERNAL_ADAPTER_DEFECT
