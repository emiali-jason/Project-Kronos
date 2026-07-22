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
    _KiteClientHandle,
    _UnexpectedProfileResponse,
    _create_kite_client,
)
from kronos.provider.exceptions.connectivity import (
    ProviderConnectivityError,
    ProviderErrorCode,
)


class KiteConnectivityAdapter:
    """Profile-only Kite connectivity adapter for EP-004."""

    __slots__ = ("__client",)

    def __init__(self, client: _KiteClientHandle) -> None:
        self.__client = client

    def probe(self) -> None:
        try:
            self.__client.probe_profile()
        except Exception as error:
            code = _map_probe_error_code(error)
        else:
            return

        raise ProviderConnectivityError(code)

    def close(self) -> None:
        try:
            self.__client.close()
        except Exception:
            code = ProviderErrorCode.SHUTDOWN_FAILURE
        else:
            return

        raise ProviderConnectivityError(code)


def create_kite_connectivity_adapter(
    api_key: str,
    access_token: str,
) -> KiteConnectivityAdapter:
    try:
        client = _create_kite_client(api_key, access_token)
    except Exception:
        code = ProviderErrorCode.INTERNAL_ADAPTER_DEFECT
    else:
        return KiteConnectivityAdapter(client)

    raise ProviderConnectivityError(code)


def _map_probe_error_code(error: Exception) -> ProviderErrorCode:
    if isinstance(error, _TokenException):
        code = ProviderErrorCode.ACCESS_TOKEN_INVALID_OR_EXPIRED
    elif isinstance(error, _PermissionException):
        code = ProviderErrorCode.AUTHENTICATION_REJECTED
    elif isinstance(error, (_RequestsTimeout, TimeoutError)):
        code = ProviderErrorCode.NETWORK_TIMEOUT
    elif isinstance(error, (_RequestsConnectionError, ConnectionError, OSError)):
        code = ProviderErrorCode.CONNECTION_FAILURE
    elif isinstance(error, (_UnexpectedProfileResponse, _DataException)):
        code = ProviderErrorCode.UNEXPECTED_RESPONSE
    elif isinstance(error, (_NetworkException, _KiteException)):
        status_code = getattr(error, "code", None)
        code = (
            ProviderErrorCode.RATE_LIMITED
            if status_code == 429
            else ProviderErrorCode.PROVIDER_SERVICE_FAILURE
        )
    else:
        code = ProviderErrorCode.INTERNAL_ADAPTER_DEFECT

    return code
