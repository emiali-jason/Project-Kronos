from collections.abc import Mapping
from typing import Any

from kiteconnect import KiteConnect as _KiteConnect


class _UnexpectedProfileResponse(RuntimeError):
    pass


class _KiteClientClosedError(RuntimeError):
    pass


class _KiteCleanupError(RuntimeError):
    pass


class _UnexpectedAuthenticationResponse(RuntimeError):
    pass


class _KiteSessionInvalidated(RuntimeError):
    pass


class _KiteClientHandle:
    """Narrow internal handle exposing only the EP-004 probe and cleanup."""

    __slots__ = ("__client", "__closed", "__session_invalidated")

    def __init__(self, client: Any) -> None:
        self.__client = client
        self.__closed = False
        self.__session_invalidated = False
        self.__client.set_session_expiry_hook(self.__mark_session_invalidated)

    def probe_profile(self) -> None:
        if self.__closed:
            raise _KiteClientClosedError
        if self.__session_invalidated:
            raise _KiteSessionInvalidated

        try:
            profile = self.__client.profile()
        finally:
            if self.__session_invalidated:
                raise _KiteSessionInvalidated from None
        if not isinstance(profile, Mapping):
            raise _UnexpectedProfileResponse

        del profile

    def close(self) -> None:
        if self.__closed:
            return

        self.__closed = True
        client = self.__client
        self.__client = None

        # KiteConnect 5.2.0 has no public close(). Revalidate this single
        # compatibility access to its HTTP session whenever the SDK changes.
        session = getattr(client, "reqsession", None)
        close_session = getattr(session, "close", None)
        if not callable(close_session):
            raise _KiteCleanupError

        close_session()

    def __mark_session_invalidated(self) -> None:
        self.__session_invalidated = True


def _create_kite_client(api_key: str, access_token: str) -> _KiteClientHandle:
    client = _KiteConnect(
        api_key=api_key,
        access_token=access_token,
        debug=False,
    )
    return _KiteClientHandle(client)


class _KiteAuthenticationClientHandle:
    """Narrow SDK handle for the official Kite authentication lifecycle."""

    __slots__ = (
        "__client",
        "__has_authenticated_context",
        "__session_invalidated",
    )

    def __init__(self, client: Any) -> None:
        self.__client = client
        self.__has_authenticated_context = False
        self.__session_invalidated = False
        self.__client.set_session_expiry_hook(self.__mark_session_invalidated)

    def login_url(self) -> str:
        login_url = self.__client.login_url()
        if not isinstance(login_url, str) or not login_url:
            raise _UnexpectedAuthenticationResponse
        return login_url

    def exchange(self, request_token: str, api_secret: str) -> None:
        response = self.__client.generate_session(request_token, api_secret)
        if not isinstance(response, Mapping):
            raise _UnexpectedAuthenticationResponse
        access_token = response.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise _UnexpectedAuthenticationResponse
        self.__has_authenticated_context = True
        self.__session_invalidated = False
        del access_token
        del response

    def verify(self) -> None:
        if not self.__has_authenticated_context or self.__session_invalidated:
            raise _KiteSessionInvalidated
        try:
            profile = self.__client.profile()
        finally:
            if self.__session_invalidated:
                raise _KiteSessionInvalidated from None
        if not isinstance(profile, Mapping):
            raise _UnexpectedProfileResponse
        del profile

    def session_invalidated(self) -> bool:
        return self.__session_invalidated

    def terminate(self) -> None:
        if not self.__has_authenticated_context:
            return
        result = self.__client.invalidate_access_token()
        if result is not True:
            raise _UnexpectedAuthenticationResponse
        self.__has_authenticated_context = False
        self.__session_invalidated = True

    def __mark_session_invalidated(self) -> None:
        self.__session_invalidated = True


def _create_kite_authentication_client(api_key: str) -> _KiteAuthenticationClientHandle:
    client = _KiteConnect(api_key=api_key, debug=False)
    return _KiteAuthenticationClientHandle(client)
