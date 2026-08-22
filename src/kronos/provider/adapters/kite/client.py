from collections.abc import Mapping
from datetime import datetime
import math
from typing import Any
from zoneinfo import ZoneInfo

from kiteconnect import KiteConnect as _KiteConnect


_KITE_MARKET_TIMEZONE = ZoneInfo("Asia/Kolkata")


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


class _KiteExchangeAlreadyAttempted(RuntimeError):
    pass


class _KiteSessionState:
    __slots__ = ("invalidated",)

    def __init__(self) -> None:
        self.invalidated = False

    def mark_invalidated(self) -> None:
        self.invalidated = True


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
    """Pre-exchange SDK handle that transfers ownership to one candidate."""

    __slots__ = (
        "__client",
        "__exchange_started",
        "__session_state",
    )

    def __init__(self, client: Any) -> None:
        self.__client = client
        self.__exchange_started = False
        self.__session_state = _KiteSessionState()
        self.__client.set_session_expiry_hook(
            self.__session_state.mark_invalidated
        )

    def login_url(self) -> str:
        login_url = self.__client.login_url()
        if not isinstance(login_url, str) or not login_url:
            raise _UnexpectedAuthenticationResponse
        return login_url

    def exchange_once(
        self,
        request_token: str,
        api_secret: str,
        *,
        timeout_seconds: float | None = None,
    ) -> "_KiteCandidateClientHandle":
        if self.__exchange_started:
            raise _KiteExchangeAlreadyAttempted
        if self.__session_state.invalidated:
            raise _KiteSessionInvalidated
        self.__exchange_started = True
        client = self.__client
        if client is None:
            raise _KiteExchangeAlreadyAttempted

        _apply_bounded_timeout(client, timeout_seconds)
        response = client.generate_session(request_token, api_secret)
        if not isinstance(response, Mapping):
            raise _UnexpectedAuthenticationResponse
        access_token = response.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise _UnexpectedAuthenticationResponse
        del access_token
        del response
        self.__client = None
        return _KiteCandidateClientHandle(client, self.__session_state)

    def __repr__(self) -> str:
        return "<_KiteAuthenticationClientHandle redacted>"

    __str__ = __repr__

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("KITE_AUTHENTICATION_HANDLE_SERIALIZATION_PROHIBITED")


class _KiteCandidateClientHandle:
    """Opaque local owner of one exchanged Kite SDK candidate client."""

    __slots__ = (
        "__client",
        "__closed",
        "__principal_attempted",
        "__session_state",
    )

    def __init__(self, client: Any, session_state: _KiteSessionState) -> None:
        self.__client = client
        self.__closed = False
        self.__principal_attempted = False
        self.__session_state = session_state

    def principal_user_id_once(
        self,
        *,
        timeout_seconds: float | None = None,
    ) -> str | None:
        if self.__principal_attempted:
            raise _UnexpectedAuthenticationResponse
        self.__principal_attempted = True
        profile = self.__profile_mapping(timeout_seconds=timeout_seconds)
        principal = profile.get("user_id")
        del profile
        return principal if isinstance(principal, str) else None

    def verify_profile_once(self, *, timeout_seconds: float | None = None) -> None:
        profile = self.__profile_mapping(timeout_seconds=timeout_seconds)
        del profile

    def instrument_records(self, exchange: str) -> object:
        """Return one raw SDK response only to the containing Kite adapter."""

        if self.__closed or self.__client is None:
            raise _KiteClientClosedError
        if self.__session_state.invalidated:
            raise _KiteSessionInvalidated
        try:
            records = self.__client.instruments(exchange)
        finally:
            if self.__session_state.invalidated:
                raise _KiteSessionInvalidated from None
        return records

    def instrument_master_records(self) -> object:
        """Return the consolidated raw master only to the containing adapter."""

        if self.__closed or self.__client is None:
            raise _KiteClientClosedError
        if self.__session_state.invalidated:
            raise _KiteSessionInvalidated
        try:
            records = self.__client.instruments()
        finally:
            if self.__session_state.invalidated:
                raise _KiteSessionInvalidated from None
        return records

    def historical_candles(
        self,
        *,
        instrument_token: int,
        from_date: object,
        to_date: object,
        interval: str,
    ) -> object:
        """Return one raw historical response only to the containing adapter."""

        if self.__closed or self.__client is None:
            raise _KiteClientClosedError
        if self.__session_state.invalidated:
            raise _KiteSessionInvalidated
        try:
            candles = self.__client.historical_data(
                instrument_token=instrument_token,
                from_date=_kite_market_boundary(from_date),
                to_date=_kite_market_boundary(to_date),
                interval=interval,
                continuous=False,
                oi=False,
            )
        finally:
            if self.__session_state.invalidated:
                raise _KiteSessionInvalidated from None
        return candles

    def quote(self, instrument: str) -> object:
        """Return one raw quote response only to the containing Kite adapter."""

        return self.__live_snapshot("quote", instrument)

    def ltp(self, instrument: str) -> object:
        """Return one raw LTP response only to the containing Kite adapter."""

        return self.__live_snapshot("ltp", instrument)

    def ohlc(self, instrument: str) -> object:
        """Return one raw OHLC response only to the containing Kite adapter."""

        return self.__live_snapshot("ohlc", instrument)

    def open_monitoring_session(
        self,
        *,
        token_resolver: object,
        consumer: object,
        clock: object = None,
        socket_factory: object = None,
    ) -> object:
        """Construct an opaque Kite monitoring session without releasing credentials."""

        if self.__closed or self.__client is None or self.__session_state.invalidated:
            raise _KiteSessionInvalidated
        api_key = getattr(self.__client, "api_key", None)
        access_token = getattr(self.__client, "access_token", None)
        if not isinstance(api_key, str) or not api_key or not isinstance(access_token, str) or not access_token:
            raise _UnexpectedAuthenticationResponse
        from kronos.provider.adapters.kite.monitoring import KiteReadOnlyMonitoringSession

        arguments: dict[str, object] = {
            "api_key": api_key,
            "access_token": access_token,
            "token_resolver": token_resolver,
            "consumer": consumer,
        }
        if clock is not None:
            arguments["clock"] = clock
        if socket_factory is not None:
            arguments["socket_factory"] = socket_factory
        return KiteReadOnlyMonitoringSession(**arguments)  # type: ignore[arg-type]

    @property
    def active(self) -> bool:
        """Return local usability without exposing the client or session token."""

        return (
            not self.__closed
            and self.__client is not None
            and not self.__session_state.invalidated
        )

    def close_local(self) -> None:
        if self.__closed:
            return
        self.__closed = True
        client = self.__client
        self.__client = None
        if client is None:
            return

        session = getattr(client, "reqsession", None)
        close_session = getattr(session, "close", None)
        if not callable(close_session):
            raise _KiteCleanupError
        close_session()

    def invalidate_remote_session(self) -> None:
        """Retain the legacy remote operation as a separately named dead end."""

        if self.__closed or self.__client is None:
            raise _KiteClientClosedError
        result = self.__client.invalidate_access_token()
        if result is not True:
            raise _UnexpectedAuthenticationResponse

    def __profile_mapping(
        self,
        *,
        timeout_seconds: float | None = None,
    ) -> Mapping[str, object]:
        if self.__closed or self.__client is None:
            raise _KiteClientClosedError
        if self.__session_state.invalidated:
            raise _KiteSessionInvalidated
        _apply_bounded_timeout(self.__client, timeout_seconds)
        try:
            profile = self.__client.profile()
        finally:
            if self.__session_state.invalidated:
                raise _KiteSessionInvalidated from None
        if not isinstance(profile, Mapping):
            raise _UnexpectedProfileResponse
        return profile

    def __live_snapshot(self, operation: str, instrument: str) -> object:
        if self.__closed or self.__client is None:
            raise _KiteClientClosedError
        if self.__session_state.invalidated:
            raise _KiteSessionInvalidated
        if not isinstance(instrument, str) or not instrument:
            raise _UnexpectedAuthenticationResponse
        endpoint = getattr(self.__client, operation, None)
        if not callable(endpoint):
            raise _UnexpectedAuthenticationResponse
        try:
            response = endpoint([instrument])
        finally:
            if self.__session_state.invalidated:
                raise _KiteSessionInvalidated from None
        return response

    def __repr__(self) -> str:
        return "<_KiteCandidateClientHandle redacted>"

    __str__ = __repr__

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("KITE_CANDIDATE_HANDLE_SERIALIZATION_PROHIBITED")


def _kite_market_boundary(value: object) -> object:
    """Preserve an instant while supplying Kite's exchange-local wall time."""

    if (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    ):
        return value.astimezone(_KITE_MARKET_TIMEZONE)
    return value


def _create_kite_authentication_client(api_key: str) -> _KiteAuthenticationClientHandle:
    client = _KiteConnect(api_key=api_key, debug=False)
    return _KiteAuthenticationClientHandle(client)


def _apply_bounded_timeout(client: object, timeout_seconds: float | None) -> None:
    """Only shorten the SDK request timeout to the remaining lifecycle budget."""

    if timeout_seconds is None:
        return
    if (
        type(timeout_seconds) is not float
        or not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0.0
    ):
        raise _KiteClientClosedError
    current = getattr(client, "timeout", None)
    bounded = timeout_seconds
    if type(current) in {int, float} and math.isfinite(float(current)) and current > 0:
        bounded = min(float(current), timeout_seconds)
    setattr(client, "timeout", bounded)
