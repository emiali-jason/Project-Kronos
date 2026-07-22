from collections.abc import Mapping
from typing import Any

from kiteconnect import KiteConnect as _KiteConnect


class _UnexpectedProfileResponse(RuntimeError):
    pass


class _KiteClientClosedError(RuntimeError):
    pass


class _KiteCleanupError(RuntimeError):
    pass


class _KiteClientHandle:
    """Narrow internal handle exposing only the EP-004 probe and cleanup."""

    __slots__ = ("__client", "__closed")

    def __init__(self, client: Any) -> None:
        self.__client = client
        self.__closed = False

    def probe_profile(self) -> None:
        if self.__closed:
            raise _KiteClientClosedError

        profile = self.__client.profile()
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


def _create_kite_client(api_key: str, access_token: str) -> _KiteClientHandle:
    client = _KiteConnect(
        api_key=api_key,
        access_token=access_token,
        debug=False,
    )
    return _KiteClientHandle(client)
