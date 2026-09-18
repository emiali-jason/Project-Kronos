"""Provider-private, single-session Kite SDK process and bounded typed IPC.

This module grants no authentication or trading authority. Only the service's
principal-bound publication transfers an authentication owner to session use.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import json
import math
import multiprocessing
import selectors
import socket
import threading
import time
from zoneinfo import ZoneInfo

from kronos.provider.exceptions.connectivity import ProviderConnectivityError, ProviderErrorCode
from kronos.provider.adapters.kite.client import (
    _KiteCleanupError, _KiteCleanupPending, _KiteClientClosedError,
    _KiteExchangeAlreadyAttempted, _KiteSessionInvalidated,
    _UnexpectedAuthenticationResponse,
)

_OPERATION_SECONDS = 7.0  # Installed KiteConnect default; never a renewed auth lifetime.
_CLOSE_SECONDS = 0.25
_STOP_GRACE_SECONDS = 0.25
_POLL_SECONDS = 0.02
_FRAME_BYTES = 256 * 1024
_REQUEST_BYTES = 16 * 1024
_RESULT_BYTES = 64 * 1024 * 1024
_BATCH_ITEMS = 128
_MAX_ITEMS = 250_000
_FULL_QUOTE_ERRORS = frozenset({
    'FULL_QUOTE_REQUEST_INVALID', 'FULL_QUOTE_BUSY', 'FULL_QUOTE_RATE_LIMIT',
    'FULL_QUOTE_REPEAT_REQUEST_PROHIBITED', 'FULL_QUOTE_REDIRECT_PROHIBITED',
    'FULL_QUOTE_RETRY_TRANSPORT_PROHIBITED',
})


class _RemoteFullQuoteError(ValueError):
    """Validated fixed contract rejection; the healthy owner stays usable."""


_owners_lock = threading.Lock()
_owners: list[SDKWorkerOwner] = []


def _encode(value, depth=0):
    if depth > 32:
        raise ValueError("SDK_IPC_DEPTH")
    if value is None or type(value) in {str, int, bool}:
        return value
    if type(value) is float:
        # Preserve malformed SDK numeric data for the established parent
        # normalizers; raw JSON NaN/Infinity remains prohibited.
        return value if math.isfinite(value) else {"t": "float", "v": str(value)}
    if type(value) is datetime:
        return {"t": "datetime", "v": value.isoformat(), "z": getattr(value.tzinfo, 'key', None)}
    if type(value) is date:
        return {"t": "date", "v": value.isoformat()}
    if type(value) is Decimal:
        return {"t": "decimal", "v": str(value)}
    if type(value) in {list, tuple}:
        return {"t": "tuple" if type(value) is tuple else "list", "v": [_encode(v, depth + 1) for v in value]}
    if type(value) is dict and all(type(k) is str for k in value):
        return {"t": "map", "v": [[k, _encode(v, depth + 1)] for k, v in value.items()]}
    raise ValueError("SDK_IPC_TYPE")


def _decode(value, depth=0):
    if depth > 32:
        raise ValueError("SDK_IPC_DEPTH")
    if value is None or type(value) in {str, int, bool}:
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if type(value) is not dict or set(value) not in ({'t', 'v'}, {'t', 'v', 'z'}):
        raise ValueError("SDK_IPC_TYPE")
    tag, body = value['t'], value['v']
    if tag == 'datetime' and set(value) == {'t', 'v', 'z'} and type(body) is str:
        result = datetime.fromisoformat(body)
        zone = value['z']
        if zone is not None:
            if type(zone) is not str or result.tzinfo is None:
                raise ValueError("SDK_IPC_TIMEZONE")
            result = result.astimezone(ZoneInfo(zone))
        return result
    if set(value) != {'t', 'v'}:
        raise ValueError("SDK_IPC_TYPE")
    if tag == 'date' and type(body) is str:
        return date.fromisoformat(body)
    if tag == 'float' and type(body) is str and body in {'nan', 'inf', '-inf'}:
        return float(body)
    if tag == 'decimal' and type(body) is str:
        return Decimal(body)
    if tag in {'list', 'tuple'} and type(body) is list:
        result = [_decode(v, depth + 1) for v in body]
        return tuple(result) if tag == 'tuple' else result
    if tag == 'map' and type(body) is list:
        result = {}
        for entry in body:
            if type(entry) is not list or len(entry) != 2 or type(entry[0]) is not str or entry[0] in result:
                raise ValueError("SDK_IPC_MAP")
            result[entry[0]] = _decode(entry[1], depth + 1)
        return result
    raise ValueError("SDK_IPC_TYPE")


def _json_bytes(value, limit):
    raw = json.dumps(value, allow_nan=False, separators=(',', ':')).encode('utf-8')
    if not 0 < len(raw) <= limit:
        raise ValueError("SDK_IPC_SIZE")
    return raw


def _parse(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("SDK_IPC_DUPLICATE")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('SDK_IPC_NUMBER')))


def _sdk_socket_pair():
    """Return one bidirectional OS channel; each use has one writer."""

    return socket.socketpair()


def _close_sdk_connection(connection):
    connection.close()


def _send_frame(connection, payload):
    connection.sendall(len(payload).to_bytes(4, 'big') + payload)


def _receive_frame(connection, limit):
    header = bytearray()
    while len(header) < 4:
        chunk = connection.recv(4 - len(header))
        if not chunk:
            raise ValueError('SDK_IPC_EOF')
        header.extend(chunk)
    size = int.from_bytes(header, 'big', signed=True)
    if not 0 < size <= limit:
        raise ValueError('SDK_IPC_SIZE')
    payload = bytearray()
    while len(payload) < size:
        chunk = connection.recv(min(65536, size - len(payload)))
        if not chunk:
            raise ValueError('SDK_IPC_EOF')
        payload.extend(chunk)
    return bytes(payload)


class SDKWorkerOwner:
    """Exactly one SDK process, with one executing and one waiting parent call."""

    def __init__(self, deadline):
        self._lock = threading.RLock()
        self._io_lock = threading.Lock()
        self._slots = threading.BoundedSemaphore(2)
        self._deadline = deadline
        self._custody_deadline = deadline
        self._cancelled = threading.Event()
        self._retained = False
        self._closed = False
        self._invalidated = False
        self._sequence = 0
        self._limit = _OPERATION_SECONDS
        self.process = None
        self._connections = []
        self._sender = self._receiver = None
        self.start_attempted = self.start_returned = False
        self.local_cleanup_state = 'PENDING'
        self.sdk_close_state = 'NOT_ATTEMPTED'
        self.exit_observation = None

    def start(self, api_key):
        with _owners_lock:
            if _owners:
                raise _KiteCleanupPending
            _owners.append(self)
        self._custody_deadline.hold_resource('KITE_SDK_WORKER', self)
        self._custody_deadline.add_terminal_callback(self.cancel_authentication)
        try:
            self._require()
            context = multiprocessing.get_context('spawn')
            self._sender, child_receiver = _sdk_socket_pair()
            self._connections.extend((child_receiver, self._sender))
            child_sender, self._receiver = _sdk_socket_pair()
            self._connections.extend((self._receiver, child_sender))
            self.process = context.Process(target=_sdk_worker, args=(child_receiver, child_sender), daemon=True)
            self._require()
            self.start_attempted = True
            self.process.start()
            self.start_returned = True
            child_receiver.close(); child_sender.close()
            self._sender.setblocking(False)
            self._receiver.setblocking(False)
            self.local_cleanup_state = 'OPEN'
            result = self.call('construct', {'api_key': api_key})
            if type(result) is not float or not 0 < result <= _OPERATION_SECONDS:
                raise _UnexpectedAuthenticationResponse
            self._limit = result
        except BaseException:
            if self.local_cleanup_state not in {'COMPLETE', 'FAILED'}:
                self._stop()
            raise
        finally:
            api_key = ''

    def cancel_authentication(self):
        # Deadline callback: state only, never IPC/startup/join.
        with self._lock:
            if not self._retained:
                self._cancelled.set()

    def retain_session(self):
        # Called in the service publication guard, with no remote operation.
        self._require()
        with self._lock:
            if self._closed or self._invalidated or self._cancelled.is_set():
                raise _KiteClientClosedError
            self._retained = True
            self._deadline = None
        self._custody_deadline._resolve_pending_resource(self)

    @property
    def active(self):
        with self._lock:
            usable = not self._closed and not self._invalidated and not self._cancelled.is_set()
        # is_alive is a nonblocking child observation, outside the state lock.
        try:
            return usable and self.process is not None and self.process.is_alive()
        except ValueError:
            return False

    def _require(self):
        deadline = self._deadline
        if deadline is not None:
            deadline.require()
        if self._invalidated:
            raise _KiteSessionInvalidated
        if self._cancelled.is_set() or self._closed:
            raise _KiteClientClosedError

    def _remaining(self, expires, *, cleanup=False):
        if not cleanup:
            self._require()
        remaining = expires - time.monotonic()
        if not cleanup and self._deadline is not None:
            remaining = min(remaining, self._deadline.remaining_seconds())
        if remaining <= 0:
            raise TimeoutError('SDK_OPERATION_TIMED_OUT')
        return remaining

    def call(self, operation, arguments, *, timeout_seconds=None):
        seconds = self._limit
        if timeout_seconds is not None:
            if type(timeout_seconds) not in {int, float} or not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
                raise _KiteClientClosedError
            seconds = min(seconds, float(timeout_seconds))
        expires = time.monotonic() + seconds
        self._require()
        if not self._slots.acquire(blocking=False):
            raise ProviderConnectivityError(ProviderErrorCode.CONNECTION_FAILURE)
        acquired = False
        try:
            while not acquired:
                acquired = self._io_lock.acquire(timeout=min(_POLL_SECONDS, self._remaining(expires)))
            # Expiry while waiting belongs only to that caller. It cannot kill
            # another consumer's still legitimate operation.
            self._remaining(expires)
            try:
                return self._exchange(operation, arguments, expires)
            except _RemoteFullQuoteError as error:
                raise ValueError(str(error)) from None
            except ProviderConnectivityError:
                raise
            except BaseException:
                self._stop()
                raise
        finally:
            if acquired:
                self._io_lock.release()
            self._slots.release()

    def _write(self, payload, expires, *, cleanup):
        frame = len(payload).to_bytes(4, 'big') + payload
        offset = 0
        with selectors.DefaultSelector() as selector:
            selector.register(self._sender, selectors.EVENT_WRITE)
            while offset < len(frame):
                if not selector.select(min(_POLL_SECONDS, self._remaining(expires, cleanup=cleanup))):
                    continue
                try:
                    offset += self._sender.send(frame[offset:offset + 65536])
                except BlockingIOError:
                    continue

    def _read(self, expires, *, cleanup):
        frame = bytearray()
        expected = 4
        with selectors.DefaultSelector() as selector:
            selector.register(self._receiver, selectors.EVENT_READ)
            while len(frame) < expected:
                if not selector.select(min(_POLL_SECONDS, self._remaining(expires, cleanup=cleanup))):
                    continue
                try:
                    chunk = self._receiver.recv(min(65536, expected - len(frame)))
                except BlockingIOError:
                    continue
                if not chunk:
                    raise _UnexpectedAuthenticationResponse
                frame.extend(chunk)
                if len(frame) == 4:
                    size = int.from_bytes(frame, 'big', signed=True)
                    if not 0 < size <= _FRAME_BYTES:
                        raise _UnexpectedAuthenticationResponse
                    expected = 4 + size
        return bytes(frame[4:])

    def _exchange(self, operation, arguments, expires, *, cleanup=False):
        self._sequence += 1
        identity = self._sequence
        payload = _json_bytes({'v': 1, 'id': identity, 'op': operation,
            'args': _encode(arguments), 'seconds': min(_OPERATION_SECONDS, self._remaining(expires, cleanup=cleanup)),
            'retained': self._retained}, _REQUEST_BYTES)
        self._write(payload, expires, cleanup=cleanup)
        payload = b''
        result = []; kind = None; total = 0
        while True:
            raw = self._read(expires, cleanup=cleanup)
            total += len(raw)
            if total > _RESULT_BYTES:
                raise _UnexpectedAuthenticationResponse
            packet = _parse(raw)
            if type(packet) is not dict or type(packet.get('id')) is not int or packet['id'] != identity:
                raise _UnexpectedAuthenticationResponse
            tag = packet.get('type')
            if (operation == 'full_quotes' and tag == 'full_quote_error'
                    and set(packet) == {'id', 'type', 'code'}
                    and type(packet['code']) is str and packet['code'] in _FULL_QUOTE_ERRORS):
                raise _RemoteFullQuoteError(packet['code'])
            if tag == 'error' and set(packet) == {'id', 'type', 'code'}:
                code = ProviderErrorCode(packet['code'])
                if code is ProviderErrorCode.ACCESS_TOKEN_INVALID_OR_EXPIRED:
                    self._invalidated = True
                raise ProviderConnectivityError(code)
            if tag == 'begin' and kind is None and set(packet) == {'id', 'type', 'kind'}:
                kind = packet['kind']
                if kind not in {'list', 'tuple', 'value'}:
                    raise _UnexpectedAuthenticationResponse
            elif tag == 'data' and kind is not None and set(packet) == {'id', 'type', 'items'}:
                if type(packet['items']) is not list or not 1 <= len(packet['items']) <= _BATCH_ITEMS:
                    raise _UnexpectedAuthenticationResponse
                result.extend(_decode(item) for item in packet['items'])
                if len(result) > _MAX_ITEMS or (kind == 'value' and len(result) > 1):
                    raise _UnexpectedAuthenticationResponse
            elif tag == 'end' and kind is not None and set(packet) == {'id', 'type', 'count'}:
                if type(packet['count']) is not int or packet['count'] != len(result):
                    raise _UnexpectedAuthenticationResponse
                self._remaining(expires, cleanup=cleanup)
                if kind == 'value':
                    if len(result) != 1:
                        raise _UnexpectedAuthenticationResponse
                    return result[0]
                return tuple(result) if kind == 'tuple' else result
            else:
                raise _UnexpectedAuthenticationResponse

    def close_local(self):
        with self._lock:
            if self.local_cleanup_state == 'COMPLETE':
                return
            if self.local_cleanup_state == 'FAILED':
                raise _KiteCleanupError
            self._closed = True
        if not self._io_lock.acquire(blocking=False):
            with self._lock:
                # The executing call can finish cleanup between the first
                # state check and this failed acquisition. Never regress it.
                if self.local_cleanup_state == 'COMPLETE':
                    return
                if self.local_cleanup_state == 'FAILED':
                    raise _KiteCleanupError
                self.local_cleanup_state = 'PENDING'
            raise _KiteCleanupPending
        try:
            if self.local_cleanup_state == 'COMPLETE':
                return
            if self.local_cleanup_state == 'FAILED':
                raise _KiteCleanupError
            self.sdk_close_state = 'PENDING'
            try:
                result = self._exchange('close', {}, time.monotonic() + _CLOSE_SECONDS, cleanup=True)
                if result is not True:
                    raise _KiteCleanupError
            except BaseException:
                self.sdk_close_state = 'FAILED_OR_UNCONFIRMED'
                self._stop(failed_close=True)
            else:
                self.sdk_close_state = 'SUCCEEDED'
                self._stop(graceful=True)
        finally:
            self._io_lock.release()
        if self.local_cleanup_state != 'COMPLETE':
            raise _KiteCleanupError

    def _stop(self, *, failed_close=False, graceful=False):
        with self._lock:
            if self.local_cleanup_state in {'COMPLETE', 'FAILED'}:
                return
            self._closed = True
            self.local_cleanup_state = 'PENDING'
        process = self.process
        failed = failed_close or (self.start_attempted and not self.start_returned and process.pid is None)
        try:
            if process is not None:
                if process.pid is not None:
                    if graceful:
                        process.join(_STOP_GRACE_SECONDS)
                    if process.is_alive():
                        process.terminate(); process.join(_STOP_GRACE_SECONDS)
                    if process.is_alive():
                        process.kill(); process.join(_STOP_GRACE_SECONDS)
                    self.exit_observation = (process.pid, process.exitcode, process.is_alive())
                    if process.is_alive():
                        raise _KiteCleanupError
                process.close()
        except Exception:
            failed = True
        for connection in self._connections:
            try:
                _close_sdk_connection(connection)
            except Exception:
                failed = True
        with self._lock:
            self.local_cleanup_state = 'FAILED' if failed else 'COMPLETE'
        if failed:
            self._custody_deadline.hold_resource('KITE_SDK_WORKER', self)
        else:
            self._custody_deadline._resolve_pending_resource(self)
            with _owners_lock:
                _owners.remove(self)

    def __repr__(self):
        return '<KiteSDKWorkerOwner redacted>'

    def __reduce_ex__(self, _protocol):
        raise TypeError('KITE_SDK_OWNER_SERIALIZATION_PROHIBITED')


def _send_result(sender, identity, result):
    total = 0
    def send(packet):
        nonlocal total
        payload = _json_bytes(packet, _FRAME_BYTES)
        total += len(payload)
        if total > _RESULT_BYTES:
            raise ValueError('SDK_IPC_SIZE')
        _send_frame(sender, payload)
    sequence = type(result) in {list, tuple}
    kind = ('list' if type(result) is list else 'tuple') if sequence else 'value'
    count = len(result) if sequence else 1
    if count > _MAX_ITEMS:
        raise ValueError('SDK_IPC_SIZE')
    send({'id': identity, 'type': 'begin', 'kind': kind})
    for start in range(0, count, _BATCH_ITEMS):
        batch = result[start:start + _BATCH_ITEMS] if sequence else [result]
        send({'id': identity, 'type': 'data', 'items': [_encode(item) for item in batch]})
    send({'id': identity, 'type': 'end', 'count': count})


def _validated_request(packet, previous):
    if (type(packet) is not dict or set(packet) != {'v', 'id', 'op', 'args', 'seconds', 'retained'}
            or type(packet['v']) is not int or packet['v'] != 1 or type(packet['id']) is not int or packet['id'] != previous + 1
            or type(packet['seconds']) not in {int, float} or not math.isfinite(packet['seconds'])
            or not 0 < packet['seconds'] <= _OPERATION_SECONDS or type(packet['retained']) is not bool):
        raise ValueError('SDK_REQUEST_INVALID')
    arguments = _decode(packet['args'])
    expected = {'construct': {'api_key'}, 'login_url': set(), 'exchange': {'token', 'secret'},
        'principal': set(), 'profile': set(), 'instruments': {'exchange'}, 'master': set(),
        'historical': {'instrument_token', 'from_date', 'to_date', 'interval'},
        'quote': {'instrument'}, 'ltp': {'instrument'}, 'ohlc': {'instrument'},
        'full_quotes': {'instruments'}, 'monitoring_bootstrap': set(), 'close': set()}
    operation = packet['op']
    if type(operation) is not str or operation not in expected or type(arguments) is not dict or set(arguments) != expected[operation]:
        raise ValueError('SDK_REQUEST_INVALID')
    for key in {'api_key', 'token', 'secret', 'exchange', 'instrument', 'interval'} & arguments.keys():
        if type(arguments[key]) is not str or not 0 < len(arguments[key]) <= 4096:
            raise ValueError('SDK_REQUEST_INVALID')
    if operation == 'historical' and (type(arguments['instrument_token']) is not int or arguments['instrument_token'] <= 0
            or any(type(arguments[key]) not in {date, datetime, str} for key in ('from_date', 'to_date'))):
        raise ValueError('SDK_REQUEST_INVALID')
    if operation == 'full_quotes' and (type(arguments['instruments']) is not tuple or not 1 <= len(arguments['instruments']) <= 2
            or any(type(item) is not str or not 0 < len(item) <= 256 for item in arguments['instruments'])
            or len(set(arguments['instruments'])) != len(arguments['instruments'])):
        raise ValueError('SDK_REQUEST_INVALID')
    return operation, arguments


def _sdk_worker(receiver, sender):
    """Child owns every SDK object; only fixed authentication/read commands exist."""
    from kronos.provider.adapters.kite.client import _create_kite_authentication_client
    from kronos.provider.adapters.kite.authentication import _map_authentication_error_code
    authentication = candidate = None
    previous = 0
    principal_attempted = False
    configured = _OPERATION_SECONDS
    try:
        while True:
            packet = _parse(_receive_frame(receiver, _REQUEST_BYTES))
            operation, arguments = _validated_request(packet, previous)
            previous = packet['id']
            identity = previous
            closing = operation == 'close'
            try:
                if operation == 'construct':
                    if authentication is not None or candidate is not None or identity != 1:
                        raise _KiteClientClosedError
                    authentication = _create_kite_authentication_client(arguments['api_key'])
                    configured = min(_OPERATION_SECONDS, authentication._worker_timeout_limit())
                    result = float(configured)
                elif closing:
                    owner = candidate or authentication
                    if owner is not None:
                        owner.close_local()
                    result = True
                elif operation == 'login_url' and authentication is not None and candidate is None:
                    result = authentication._generate_login_url()
                elif operation == 'exchange' and authentication is not None and candidate is None:
                    authentication._prepare_worker_operation(min(configured, packet['seconds']))
                    candidate = authentication.exchange_once(arguments['token'], arguments['secret'], timeout_seconds=float(packet['seconds']))
                    authentication = None
                    result = True
                elif operation == 'principal' and candidate is not None and not packet['retained'] and not principal_attempted:
                    principal_attempted = True
                    candidate._prepare_worker_operation(min(configured, packet['seconds']))
                    result = candidate.principal_user_id_once(timeout_seconds=float(packet['seconds']))
                elif candidate is not None and principal_attempted and packet['retained']:
                    candidate._prepare_worker_operation(min(configured, packet['seconds']))
                    if operation == 'profile':
                        result = candidate.verify_profile_once(timeout_seconds=float(packet['seconds']))
                    elif operation == 'instruments':
                        result = candidate.instrument_records(arguments['exchange'])
                    elif operation == 'master':
                        result = candidate.instrument_master_records()
                    elif operation == 'historical':
                        result = candidate.historical_candles(**arguments)
                    elif operation == 'quote':
                        result = candidate._quote_snapshot(arguments['instrument'])
                    elif operation == 'ltp':
                        result = candidate._ltp_snapshot(arguments['instrument'])
                    elif operation == 'ohlc':
                        result = candidate._ohlc_snapshot(arguments['instrument'])
                    elif operation == 'full_quotes':
                        result = candidate.full_quotes(arguments['instruments'])
                    elif operation == 'monitoring_bootstrap':
                        result = candidate._worker_monitoring_credentials()
                    else:
                        raise _KiteClientClosedError
                else:
                    raise _KiteClientClosedError
                _send_result(sender, identity, result)
                result = None
            except Exception as error:
                if operation == 'full_quotes' and isinstance(error, ValueError) and str(error) in _FULL_QUOTE_ERRORS:
                    code = str(error)
                    kind = 'full_quote_error'
                else:
                    code = _map_authentication_error_code(error).value
                    kind = 'error'
                _send_frame(sender, _json_bytes({'id': identity, 'type': kind, 'code': code}, _FRAME_BYTES))
            finally:
                arguments.clear(); packet = None
            if closing:
                break
    except BaseException:
        # No exception text, request or response material crosses this boundary.
        pass
    finally:
        receiver.close(); sender.close()


class _WorkerAuthenticationHandle:
    """Former adapter loses access to the owner at the candidate transfer."""

    def __init__(self, owner):
        self._owner = owner
        self._lock = threading.Lock()
        self._exchange_started = False
        self._closed = False

    def login_url(self):
        with self._lock:
            owner = self._owner
            if self._closed or owner is None:
                raise _KiteClientClosedError
        return owner.call('login_url', {})

    def exchange_once(self, request_token, api_secret, *, timeout_seconds=None):
        with self._lock:
            if self._closed or self._exchange_started or self._owner is None:
                raise _KiteExchangeAlreadyAttempted
            self._exchange_started = True
            owner = self._owner
        result = owner.call('exchange', {'token': request_token, 'secret': api_secret},
                            timeout_seconds=timeout_seconds)
        if result is not True:
            owner.close_local()
            raise _UnexpectedAuthenticationResponse
        candidate = _WorkerCandidateHandle(owner)
        with self._lock:
            if self._closed:
                raise _KiteClientClosedError
            owner._require()
            self._owner = None
        return candidate

    @property
    def active(self):
        with self._lock:
            owner = self._owner
            closed = self._closed
        return not closed and owner is not None and owner.active

    @property
    def local_cleanup_state(self):
        return self._owner.local_cleanup_state if self._owner is not None else 'COMPLETE'

    def close_local(self):
        with self._lock:
            self._closed = True
            owner = self._owner
        if owner is not None:
            owner.close_local()

    def __repr__(self):
        return '<KiteWorkerAuthenticationHandle redacted>'

    def __reduce_ex__(self, _protocol):
        raise TypeError('KITE_AUTHENTICATION_HANDLE_SERIALIZATION_PROHIBITED')


class _WorkerCandidateHandle:
    """Parent has fixed read messages, never a serialized SDK or callback."""

    def __init__(self, owner):
        self._owner = owner

    @property
    def active(self):
        return self._owner.active

    @property
    def local_cleanup_state(self):
        return self._owner.local_cleanup_state

    def retain_session(self):
        self._owner.retain_session()

    def close_local(self):
        self._owner.close_local()

    def principal_user_id_once(self, *, timeout_seconds=None):
        return self._owner.call('principal', {}, timeout_seconds=timeout_seconds)

    def verify_profile_once(self, *, timeout_seconds=None):
        return self._owner.call('profile', {}, timeout_seconds=timeout_seconds)

    def instrument_records(self, exchange):
        return self._owner.call('instruments', {'exchange': exchange})

    def instrument_master_records(self):
        return self._owner.call('master', {})

    def historical_candles(self, *, instrument_token, from_date, to_date, interval):
        return self._owner.call('historical', dict(instrument_token=instrument_token,
            from_date=from_date, to_date=to_date, interval=interval))

    def quote(self, instrument):
        return self._owner.call('quote', {'instrument': instrument})

    def ltp(self, instrument):
        return self._owner.call('ltp', {'instrument': instrument})

    def ohlc(self, instrument):
        return self._owner.call('ohlc', {'instrument': instrument})

    def full_quotes(self, instruments, *, timeout=7):
        if timeout != 7 or not 1 <= len(instruments) <= 2 or len(set(instruments)) != len(instruments):
            raise ValueError('FULL_QUOTE_REQUEST_INVALID')
        return self._owner.call('full_quotes', {'instruments': instruments})

    def open_monitoring_session(self, *, token_resolver, consumer, clock=None, socket_factory=None):
        # This one private bootstrap goes directly to the existing Provider
        # constructor; application callbacks never cross the process boundary.
        from kronos.provider.adapters.kite.monitoring import KiteReadOnlyMonitoringSession
        credentials = self._owner.call('monitoring_bootstrap', {})
        if type(credentials) is not tuple or len(credentials) != 2 or any(type(v) is not str or not v for v in credentials):
            raise _UnexpectedAuthenticationResponse
        arguments = dict(api_key=credentials[0], access_token=credentials[1],
                         token_resolver=token_resolver, consumer=consumer)
        if clock is not None:
            arguments['clock'] = clock
        if socket_factory is not None:
            arguments['socket_factory'] = socket_factory
        try:
            self._owner._require()
            return KiteReadOnlyMonitoringSession(**arguments)
        finally:
            arguments.clear()
            credentials = None

    def __repr__(self):
        return '<KiteWorkerCandidateHandle redacted>'

    def __reduce_ex__(self, _protocol):
        raise TypeError('KITE_CANDIDATE_HANDLE_SERIALIZATION_PROHIBITED')


def create_worker_authentication_handle(api_key, deadline):
    owner = SDKWorkerOwner(deadline)
    owner.start(api_key)
    return _WorkerAuthenticationHandle(owner)
