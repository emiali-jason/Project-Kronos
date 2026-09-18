from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime
import math
from copy import copy
from requests import Session as _RequestSession
from typing import Any
from threading import RLock
from zoneinfo import ZoneInfo

from kiteconnect import KiteConnect as _KiteConnect


_KITE_MARKET_TIMEZONE = ZoneInfo("Asia/Kolkata")


class _UnexpectedProfileResponse(RuntimeError):
    pass


class _KiteClientClosedError(RuntimeError):
    pass


class _KiteCleanupError(RuntimeError):
    pass


class _KiteCleanupPending(_KiteCleanupError):
    """Local use is fenced, but an owned operation or close still runs."""


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
    """Pre-exchange owner; transfer occurs only after candidate construction."""

    __slots__ = (
        "__client",
        "__closed",
        "__state_lock",
        "__cleanup_state",
        "__close_in_progress",
        "__active_operations",
        "__exchange_started",
        "__initialization_failed",
        "__session_state",
    )

    def __init__(self, client: Any) -> None:
        self.__client = client
        self.__closed = False
        self.__state_lock = RLock()
        self.__cleanup_state = "OPEN"
        self.__close_in_progress = False
        self.__active_operations = 0
        self.__exchange_started = False
        self.__initialization_failed = False
        self.__session_state = _KiteSessionState()
        try:
            self.__client.set_session_expiry_hook(
                self.__session_state.mark_invalidated
            )
        except Exception:
            # The SDK object already exists: keep it owned for explicit local
            # cleanup without retaining the raw initialization exception.
            self.__initialization_failed = True

    def _worker_timeout_limit(self) -> float:
        # Only the private, serialized SDK child calls this compatibility seam.
        current = getattr(self.__client, "timeout", 7.0)
        if type(current) in {int, float} and math.isfinite(current) and current > 0:
            return float(current)
        return 7.0

    def _prepare_worker_operation(self, seconds: float) -> None:
        # The child restores its original configured limit for each operation.
        # An authentication-stage remainder must not poison retained reads.
        setattr(self.__client, "timeout", seconds)

    def login_url(self) -> str:
        return self._generate_login_url()

    def _generate_login_url(self) -> str:
        """Generate the SDK URL at the single internal ownership boundary."""
        with self.__state_lock:
            if self.__closed or self.__client is None:
                raise _KiteClientClosedError
            if self.__initialization_failed:
                raise _KiteClientClosedError
            client = self.__client
            self.__active_operations += 1
        try:
            login_url = client.login_url()
            with self.__state_lock:
                if self.__closed:
                    raise _KiteClientClosedError
                if not isinstance(login_url, str) or not login_url:
                    raise _UnexpectedAuthenticationResponse
                return login_url
        finally:
            with self.__state_lock:
                self.__active_operations -= 1

    def exchange_once(
        self,
        request_token: str,
        api_secret: str,
        *,
        timeout_seconds: float | None = None,
    ) -> "_KiteCandidateClientHandle":
        with self.__state_lock:
            if self.__closed:
                raise _KiteClientClosedError
            if self.__initialization_failed:
                raise _KiteClientClosedError
            if self.__exchange_started or self.__client is None:
                raise _KiteExchangeAlreadyAttempted
            if self.__session_state.invalidated:
                raise _KiteSessionInvalidated
            self.__exchange_started = True
            self.__active_operations += 1
            client = self.__client
        try:
            _apply_bounded_timeout(client, timeout_seconds)
            response = client.generate_session(request_token, api_secret)
            if not isinstance(response, Mapping):
                raise _UnexpectedAuthenticationResponse
            access_token = response.get("access_token")
            if not isinstance(access_token, str) or not access_token:
                raise _UnexpectedAuthenticationResponse
            del access_token
            del response
            # Constructor failure must leave the original owner intact. The
            # provisional candidate is not published until the transfer lock.
            candidate = _KiteCandidateClientHandle(client, self.__session_state)
            with self.__state_lock:
                if self.__closed:
                    raise _KiteClientClosedError
                if self.__session_state.invalidated:
                    raise _KiteSessionInvalidated
                self.__client = None
                return candidate
        finally:
            with self.__state_lock:
                self.__active_operations -= 1

    @property
    def active(self) -> bool:
        with self.__state_lock:
            return (
                not self.__closed
                and not self.__initialization_failed
                and self.__client is not None
                and not self.__session_state.invalidated
            )

    @property
    def local_cleanup_state(self) -> str:
        with self.__state_lock:
            return self.__cleanup_state

    def close_local(self) -> None:
        """Fence local use; an executing SDK worker is not interrupted."""

        with self.__state_lock:
            self.__closed = True
            if self.__cleanup_state == "COMPLETE":
                return
            if self.__cleanup_state == "FAILED":
                raise _KiteCleanupError
            self.__cleanup_state = "PENDING"
            if self.__active_operations or self.__close_in_progress:
                raise _KiteCleanupPending
            self.__close_in_progress = True
            client = self.__client
        failed = False
        try:
            if client is not None:
                _close_kite_client_locally(client)
        except BaseException:
            failed = True
        with self.__state_lock:
            self.__close_in_progress = False
            if failed:
                self.__cleanup_state = "FAILED"
            else:
                self.__client = None
                self.__cleanup_state = "COMPLETE"
        if failed:
            raise _KiteCleanupError

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
        "__state_lock",
        "__cleanup_state",
        "__close_in_progress",
        "__active_operations",
        "__principal_attempted",
        "__full_quote_lock",
        "__last_full_quote",
        "__session_state",
    )

    def __init__(self, client: Any, session_state: _KiteSessionState) -> None:
        self.__client = client
        self.__closed = False
        self.__state_lock = RLock()
        self.__cleanup_state = "OPEN"
        self.__close_in_progress = False
        self.__active_operations = 0
        self.__principal_attempted = False
        from threading import Lock
        self.__full_quote_lock = Lock()
        self.__last_full_quote = None
        self.__session_state = session_state

    def _prepare_worker_operation(self, seconds: float) -> None:
        setattr(self.__client, "timeout", seconds)

    def _worker_monitoring_credentials(self) -> tuple[str, str]:
        with self.__owned_operation() as client:
            api_key = getattr(client, "api_key", None)
            access_token = getattr(client, "access_token", None)
            if not isinstance(api_key, str) or not api_key or not isinstance(access_token, str) or not access_token:
                raise _UnexpectedAuthenticationResponse
            return api_key, access_token

    def principal_user_id_once(
        self,
        *,
        timeout_seconds: float | None = None,
    ) -> str | None:
        with self.__state_lock:
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

        with self.__owned_operation() as client:
            return client.instruments(exchange)

    def instrument_master_records(self) -> object:
        """Return the consolidated raw master only to the containing adapter."""

        with self.__owned_operation() as client:
            return client.instruments()

    def historical_candles(
        self,
        *,
        instrument_token: int,
        from_date: object,
        to_date: object,
        interval: str,
    ) -> object:
        """Return one raw historical response only to the containing adapter."""

        with self.__owned_operation() as client:
            return client.historical_data(
                instrument_token=instrument_token,
                from_date=_kite_market_boundary(from_date),
                to_date=_kite_market_boundary(to_date),
                interval=interval,
                continuous=False,
                oi=False,
            )

    def full_quotes(self, instruments: tuple[str, ...], *, timeout: int = 7) -> object:
        """One explicit bounded request; no retry and no credential transfer."""
        with self.__owned_operation() as client:
            if not 1 <= len(instruments) <= 2 or len(set(instruments)) != len(instruments) or timeout != 7:
                raise ValueError("FULL_QUOTE_REQUEST_INVALID")
            from time import monotonic
            if not self.__full_quote_lock.acquire(blocking=False):
                raise ValueError("FULL_QUOTE_BUSY")
            if self.__last_full_quote is not None and monotonic() - self.__last_full_quote < 1:
                self.__full_quote_lock.release()
                raise ValueError("FULL_QUOTE_RATE_LIMIT")
            self.__last_full_quote = monotonic()
            try:
                # Private request view stays inside Provider ownership. It reuses
                # the authorized SDK context without changing shared transport.
                view = copy(client)
                with _SingleQuoteSession() as transport:
                    view.reqsession = transport
                    view.timeout = timeout
                    return view.quote(list(instruments))
            finally:
                self.__full_quote_lock.release()

    def quote(self, instrument: str) -> object:
        """Return one raw quote response only to the containing Kite adapter."""

        return self._quote_snapshot(instrument)

    def _quote_snapshot(self, instrument: str) -> object:
        """Execute the worker-owned single-instrument quote operation."""

        return self.__live_snapshot("quote", instrument)

    def ltp(self, instrument: str) -> object:
        """Return one raw LTP response only to the containing Kite adapter."""

        return self._ltp_snapshot(instrument)

    def _ltp_snapshot(self, instrument: str) -> object:
        return self.__live_snapshot("ltp", instrument)

    def ohlc(self, instrument: str) -> object:
        """Return one raw OHLC response only to the containing Kite adapter."""

        return self._ohlc_snapshot(instrument)

    def _ohlc_snapshot(self, instrument: str) -> object:
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
        """Local unusability is independent of physical cleanup completion."""

        with self.__state_lock:
            return (
                not self.__closed
                and self.__client is not None
                and not self.__session_state.invalidated
            )

    @property
    def local_cleanup_state(self) -> str:
        with self.__state_lock:
            return self.__cleanup_state

    def close_local(self) -> None:
        """Fence local use; an executing SDK worker is not interrupted."""

        with self.__state_lock:
            self.__closed = True
            if self.__cleanup_state == "COMPLETE":
                return
            if self.__cleanup_state == "FAILED":
                raise _KiteCleanupError
            self.__cleanup_state = "PENDING"
            if self.__active_operations or self.__close_in_progress:
                raise _KiteCleanupPending
            self.__close_in_progress = True
            client = self.__client
        failed = False
        try:
            if client is not None:
                _close_kite_client_locally(client)
        except BaseException:
            failed = True
        with self.__state_lock:
            self.__close_in_progress = False
            if failed:
                self.__cleanup_state = "FAILED"
            else:
                self.__client = None
                self.__cleanup_state = "COMPLETE"
        if failed:
            raise _KiteCleanupError

    def invalidate_remote_session(self) -> None:
        """Retain the legacy remote operation as a separately named dead end."""

        with self.__owned_operation() as client:
            result = client.invalidate_access_token()
            if result is not True:
                raise _UnexpectedAuthenticationResponse

    def __profile_mapping(
        self,
        *,
        timeout_seconds: float | None = None,
    ) -> Mapping[str, object]:
        with self.__owned_operation() as client:
            _apply_bounded_timeout(client, timeout_seconds)
            profile = client.profile()
            if not isinstance(profile, Mapping):
                raise _UnexpectedProfileResponse
            return profile

    def __live_snapshot(self, operation: str, instrument: str) -> object:
        with self.__owned_operation() as client:
            if not isinstance(instrument, str) or not instrument:
                raise _UnexpectedAuthenticationResponse
            endpoint = getattr(client, operation, None)
            if not callable(endpoint):
                raise _UnexpectedAuthenticationResponse
            return endpoint([instrument])

    @contextmanager
    def __owned_operation(self) -> Iterator[Any]:
        with self.__state_lock:
            if self.__closed or self.__client is None:
                raise _KiteClientClosedError
            if self.__session_state.invalidated:
                raise _KiteSessionInvalidated
            client = self.__client
            self.__active_operations += 1
        try:
            yield client
        finally:
            with self.__state_lock:
                self.__active_operations -= 1
                closed = self.__closed
                invalidated = self.__session_state.invalidated
            # No result may escape after this owner was made locally unusable.
            if closed:
                raise _KiteClientClosedError from None
            if invalidated:
                raise _KiteSessionInvalidated from None

    def __repr__(self) -> str:
        return "<_KiteCandidateClientHandle redacted>"

    __str__ = __repr__

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("KITE_CANDIDATE_HANDLE_SERIALIZATION_PROHIBITED")


def _close_kite_client_locally(client: Any) -> None:
    """Single local transport close, with no logout or token revocation."""

    failed = False
    # KiteConnect stores these secrets on the SDK object. They are no longer
    # usable by this disposed owner, including when physical close fails.
    for attribute in ("api_key", "access_token"):
        try:
            setattr(client, attribute, None)
        except BaseException:
            failed = True
    try:
        # KiteConnect 5.2.0 has no public close(). Keep this compatibility access
        # local and revalidate it when the pinned SDK changes.
        session = getattr(client, "reqsession", None)
        close_session = getattr(session, "close", None)
        if not callable(close_session):
            failed = True
        else:
            close_session()
    except BaseException:
        failed = True
    if failed:
        raise _KiteCleanupError


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


class _SingleQuoteSession(_RequestSession):
    """One physical quote request, no redirect or automatic retry transport."""
    def __init__(self):
        super().__init__()
        self._attempted = False
        if any(adapter.max_retries.total != 0 for adapter in self.adapters.values()):
            raise ValueError("FULL_QUOTE_RETRY_TRANSPORT_PROHIBITED")

    def request(self, method, url, **kwargs):
        if self._attempted or method != "GET":
            raise ValueError("FULL_QUOTE_REPEAT_REQUEST_PROHIBITED")
        self._attempted = True
        kwargs["allow_redirects"] = False
        kwargs["timeout"] = 7
        response = super().request(method, url, **kwargs)
        if 300 <= response.status_code < 400:
            raise ValueError("FULL_QUOTE_REDIRECT_PROHIBITED")
        return response
