"""Credential-safe Telegram Bot API delivery for governed KRONOS messages."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from threading import RLock
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from kronos.configuration.credentials import SecureCredentialSource


TELEGRAM_PROVIDER = "telegram-bot"
TELEGRAM_BOT_TOKEN_REF = "ux10-bot-token"
TELEGRAM_PRIVATE_CHAT_REF = "ux10-private-chat"
_BOT_API_ROOT = "https://api.telegram.org"
_TOKEN = re.compile(r"[0-9]{6,12}:[A-Za-z0-9_-]{20,80}\Z")
_CHAT_ID = re.compile(r"[1-9][0-9]{4,19}\Z")
TELEGRAM_DELIVERY_CONTROL_SCHEMA = "KRONOS-TELEGRAM-DELIVERY-CONTROL-V1"
TELEGRAM_DELIVERY_CONTROL_CONFIG = "telegram-delivery-control-v1.json"


class TelegramConfigurationState(StrEnum):
    NOT_CONFIGURED = "NOT CONFIGURED"
    TOKEN_CONFIGURED = "TOKEN CONFIGURED"
    PRIVATE_CHAT_REQUIRED = "PRIVATE CHAT REQUIRED"
    READY = "READY"
    DISCONNECTED = "DISCONNECTED"
    CONNECTION_FAILED = "CONNECTION FAILED"


class TelegramDeliveryState(StrEnum):
    SENT = "SENT"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_FINAL = "FAILED_FINAL"


@dataclass(frozen=True, slots=True)
class TelegramConfigurationStatus:
    state: TelegramConfigurationState
    token_configured: bool
    private_chat_configured: bool
    safe_detail: str = ""
    delivery_enabled: bool = False


@dataclass(frozen=True, slots=True)
class TelegramPrivateChatCandidate:
    selection_id: str
    display_identity: str


@dataclass(frozen=True, slots=True)
class TelegramDeliveryResult:
    state: TelegramDeliveryState
    safe_reason: str = ""
    retry_after_seconds: int | None = None


class TelegramTransport(Protocol):
    def request(
        self,
        method: str,
        payload: dict[str, object],
        *,
        token: str,
        timeout_seconds: float,
    ) -> dict[str, object]: ...


class TelegramCredentialProvisioner(Protocol):
    def store_api_secret(self, reference: str, value: str) -> None: ...
    def store_api_key(self, reference: str, value: str) -> None: ...


class TelegramCredentialRemover(Protocol):
    def remove_api_secret(self, reference: str) -> None: ...
    def remove_api_key(self, reference: str) -> None: ...


class TelegramPresenceProbe(Protocol):
    def api_secret_stored(self, reference: str) -> bool: ...
    def api_key_stored(self, reference: str) -> bool: ...


class TelegramDeliveryControl(Protocol):
    def enabled(self) -> bool: ...
    def set_enabled(self, enabled: bool) -> None: ...


def telegram_delivery_control_path(*, home: Path | None = None) -> Path:
    root = Path.home() if home is None else home
    return (
        root / "Library" / "Application Support" / "Project-KRONOS"
        / TELEGRAM_DELIVERY_CONTROL_CONFIG
    )


class TelegramDeliveryControlStore:
    """Persist only the non-secret Sponsor Telegram-delivery choice."""

    def __init__(self, path: Path | None = None) -> None:
        if path is not None and not isinstance(path, Path):
            raise TypeError("TELEGRAM_DELIVERY_CONTROL_DEPENDENCY_INVALID")
        self._path = path or telegram_delivery_control_path()
        self._lock = RLock()

    def enabled(self) -> bool:
        with self._lock:
            try:
                metadata = self._path.lstat()
            except FileNotFoundError:
                return True
            except OSError:
                return False
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISREG(metadata.st_mode)
                or metadata.st_size > 4096
            ):
                return False
            try:
                payload = json.loads(self._path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                return False
            return (
                type(payload) is dict
                and set(payload) == {"schema_identity", "enabled"}
                and payload["schema_identity"] == TELEGRAM_DELIVERY_CONTROL_SCHEMA
                and type(payload["enabled"]) is bool
                and payload["enabled"]
            )

    def set_enabled(self, enabled: bool) -> None:
        if type(enabled) is not bool:
            raise TypeError("TELEGRAM_DELIVERY_CONTROL_INVALID")
        with self._lock:
            self._path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            payload = json.dumps({
                "schema_identity": TELEGRAM_DELIVERY_CONTROL_SCHEMA,
                "enabled": enabled,
            }, indent=2, sort_keys=True) + "\n"
            temporary_name = ""
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", dir=self._path.parent,
                    prefix=f".{self._path.name}.", delete=False,
                ) as temporary:
                    temporary_name = temporary.name
                    temporary.write(payload)
                    temporary.flush()
                    os.fsync(temporary.fileno())
                os.chmod(temporary_name, 0o600)
                os.replace(temporary_name, self._path)
            except OSError as error:
                if temporary_name:
                    try:
                        os.unlink(temporary_name)
                    except OSError:
                        pass
                raise RuntimeError("TELEGRAM_DELIVERY_CONTROL_WRITE_FAILED") from error


class InMemoryTelegramDeliveryControl:
    """Process-local default for injected/test services; production injects a store."""

    def __init__(self, enabled: bool = True) -> None:
        if type(enabled) is not bool:
            raise TypeError("TELEGRAM_DELIVERY_CONTROL_INVALID")
        self._enabled = enabled
        self._lock = RLock()

    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        if type(enabled) is not bool:
            raise TypeError("TELEGRAM_DELIVERY_CONTROL_INVALID")
        with self._lock:
            self._enabled = enabled


class UrllibTelegramBotApiTransport:
    """Official HTTPS Bot API transport; token never enters representation/logging."""

    def request(
        self,
        method: str,
        payload: dict[str, object],
        *,
        token: str,
        timeout_seconds: float,
    ) -> dict[str, object]:
        if method not in {"getMe", "getUpdates", "sendMessage"}:
            raise ValueError("TELEGRAM_METHOD_NOT_ALLOWED")
        body = urlencode(payload).encode("utf-8")
        request = Request(
            f"{_BOT_API_ROOT}/bot{token}/{method}",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
                raw = response.read(262_144)
        except HTTPError as error:
            retry_after = None
            try:
                parsed = json.loads(error.read(32_768).decode("utf-8"))
                parameters = parsed.get("parameters", {})
                value = parameters.get("retry_after") if isinstance(parameters, dict) else None
                retry_after = value if type(value) is int and 0 < value <= 3600 else None
            except Exception:
                pass
            failure = TelegramTransportError(
                "TELEGRAM_RATE_LIMITED" if error.code == 429 else "TELEGRAM_HTTP_REJECTED",
                retryable=error.code == 429 or error.code >= 500,
                retry_after_seconds=retry_after,
            )
            raise failure from None
        except (TimeoutError, URLError):
            raise TelegramTransportError("TELEGRAM_TRANSPORT_UNAVAILABLE", retryable=True) from None
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise TelegramTransportError("TELEGRAM_RESPONSE_INVALID", retryable=False) from None
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise TelegramTransportError("TELEGRAM_RESPONSE_REJECTED", retryable=False)
        return result

    def __repr__(self) -> str:
        return "<UrllibTelegramBotApiTransport redacted>"


class TelegramTransportError(RuntimeError):
    def __init__(
        self,
        reason: str,
        *,
        retryable: bool,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds


class TelegramConfigurationService:
    """Write-only configuration plus explicit private-chat discovery/confirmation."""

    def __init__(
        self,
        *,
        provisioner: TelegramCredentialProvisioner,
        presence_probe: TelegramPresenceProbe,
        token_source: SecureCredentialSource,
        chat_source: SecureCredentialSource,
        transport: TelegramTransport,
        remover: TelegramCredentialRemover | None = None,
        delivery_control: TelegramDeliveryControl | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        if not 0.0 < timeout_seconds <= 30.0:
            raise TypeError("TELEGRAM_CONFIGURATION_DEPENDENCY_INVALID")
        self._provisioner = provisioner
        self._presence = presence_probe
        self._token_source = token_source
        self._chat_source = chat_source
        self._transport = transport
        self._remover = remover
        self._delivery_control = delivery_control or InMemoryTelegramDeliveryControl()
        self._timeout = timeout_seconds
        self._lock = RLock()
        self._discoveries: dict[str, str] = {}
        self._last_detail = ""

    def status(self) -> TelegramConfigurationStatus:
        try:
            token = self._presence.api_secret_stored(TELEGRAM_BOT_TOKEN_REF)
            chat = self._presence.api_key_stored(TELEGRAM_PRIVATE_CHAT_REF)
        except Exception:
            return TelegramConfigurationStatus(
                TelegramConfigurationState.CONNECTION_FAILED, False, False,
                "SECURE CREDENTIAL BACKEND UNAVAILABLE", False,
            )
        try:
            enabled = self._delivery_control.enabled()
        except Exception:
            enabled = False
        state = (
            TelegramConfigurationState.READY if token and chat and enabled
            else TelegramConfigurationState.DISCONNECTED if token and chat
            else TelegramConfigurationState.PRIVATE_CHAT_REQUIRED if token
            else TelegramConfigurationState.NOT_CONFIGURED
        )
        return TelegramConfigurationStatus(
            state, token, chat, self._last_detail, enabled and token and chat
        )

    def connect(self) -> TelegramConfigurationStatus:
        status = self.status()
        if not status.token_configured or not status.private_chat_configured:
            self._last_detail = "ADVANCED SETUP REQUIRED"
            return self.status()
        try:
            self._with_token("getMe", {})
            self._delivery_control.set_enabled(True)
        except Exception:
            self._last_detail = "TELEGRAM CONNECTION FAILED"
        else:
            self._last_detail = "TELEGRAM DELIVERY ENABLED"
        return self.status()

    def disconnect(self) -> TelegramConfigurationStatus:
        status = self.status()
        if not status.token_configured or not status.private_chat_configured:
            self._last_detail = "TELEGRAM CONFIGURATION INCOMPLETE"
            return self.status()
        try:
            self._delivery_control.set_enabled(False)
        except Exception:
            self._last_detail = "TELEGRAM DELIVERY CONTROL FAILED"
        else:
            self._last_detail = "TELEGRAM DELIVERY DISABLED"
        return self.status()

    def remove_configuration(self) -> TelegramConfigurationStatus:
        if self._remover is None:
            self._last_detail = "TELEGRAM CONFIGURATION REMOVAL UNAVAILABLE"
            return self.status()
        try:
            self._remover.remove_api_secret(TELEGRAM_BOT_TOKEN_REF)
            self._remover.remove_api_key(TELEGRAM_PRIVATE_CHAT_REF)
            self._delivery_control.set_enabled(False)
        except Exception:
            self._last_detail = "TELEGRAM CONFIGURATION REMOVAL FAILED"
        else:
            with self._lock:
                self._discoveries = {}
            self._last_detail = "TELEGRAM CONFIGURATION REMOVED"
        return self.status()

    def configure_token(self, token: str) -> TelegramConfigurationStatus:
        if not isinstance(token, str) or _TOKEN.fullmatch(token) is None:
            self._last_detail = "BOT TOKEN FORMAT INVALID"
            return TelegramConfigurationStatus(
                TelegramConfigurationState.CONNECTION_FAILED, False, False,
                self._last_detail, False,
            )
        try:
            self._transport.request(
                "getMe", {}, token=token, timeout_seconds=self._timeout
            )
        except TelegramTransportError as error:
            self._last_detail = error.reason
            return TelegramConfigurationStatus(
                TelegramConfigurationState.CONNECTION_FAILED, False, False,
                self._last_detail, False,
            )
        except Exception:
            self._last_detail = "TELEGRAM_IDENTITY_CHECK_FAILED"
            return TelegramConfigurationStatus(
                TelegramConfigurationState.CONNECTION_FAILED, False, False,
                self._last_detail, False,
            )
        try:
            self._provisioner.store_api_secret(TELEGRAM_BOT_TOKEN_REF, token)
        except Exception:
            self._last_detail = "BOT TOKEN COULD NOT BE STORED"
        else:
            self._last_detail = "BOT TOKEN STORED SECURELY"
        finally:
            token = ""
        return self.status()

    def discover_private_chats(self) -> tuple[TelegramPrivateChatCandidate, ...]:
        result = self._with_token("getUpdates", {"limit": 100, "timeout": 0})
        updates = result.get("result")
        discovered: dict[str, str] = {}
        if isinstance(updates, list):
            for update in updates:
                if not isinstance(update, dict):
                    continue
                message = update.get("message")
                chat = message.get("chat") if isinstance(message, dict) else None
                chat_id = chat.get("id") if isinstance(chat, dict) else None
                chat_type = chat.get("type") if isinstance(chat, dict) else None
                if chat_type != "private" or type(chat_id) is not int:
                    continue
                value = str(chat_id)
                if _CHAT_ID.fullmatch(value) is None:
                    continue
                opaque = _opaque(value)
                discovered[opaque] = value
        with self._lock:
            self._discoveries = discovered
        self._last_detail = (
            "SEND A NEW MESSAGE TO KRONOS ALERTS, THEN DISCOVER AGAIN"
            if not discovered
            else "PRIVATE CHAT CONFIRMATION REQUIRED"
        )
        return tuple(
            TelegramPrivateChatCandidate(key, f"PRIVATE CHAT {index}")
            for index, key in enumerate(sorted(discovered), start=1)
        )

    def confirm_private_chat(self, selection_id: str) -> TelegramConfigurationStatus:
        with self._lock:
            chat_id = self._discoveries.get(selection_id)
        if chat_id is None:
            self._last_detail = "PRIVATE CHAT SELECTION INVALID"
            return self.status()
        self._provisioner.store_api_key(TELEGRAM_PRIVATE_CHAT_REF, chat_id)
        self._delivery_control.set_enabled(True)
        self._last_detail = "PRIVATE CHAT CONFIRMED"
        with self._lock:
            self._discoveries = {}
        return self.status()

    def private_chat_candidates(self) -> tuple[TelegramPrivateChatCandidate, ...]:
        with self._lock:
            keys = tuple(sorted(self._discoveries))
        return tuple(
            TelegramPrivateChatCandidate(key, f"PRIVATE CHAT {index}")
            for index, key in enumerate(keys, start=1)
        )

    def test(self) -> TelegramDeliveryResult:
        return self.send("KRONOS · SWING\nTelegram connection test successful.")

    def send(self, text: str) -> TelegramDeliveryResult:
        if not isinstance(text, str) or not text or len(text) > 4096:
            return TelegramDeliveryResult(
                TelegramDeliveryState.FAILED_FINAL, "TELEGRAM_MESSAGE_INVALID"
            )
        status = self.status()
        if status.private_chat_configured and not status.delivery_enabled:
            return TelegramDeliveryResult(
                TelegramDeliveryState.FAILED_FINAL, "TELEGRAM_DELIVERY_DISABLED"
            )
        try:
            chat_lease = self._chat_source.acquire(TELEGRAM_PRIVATE_CHAT_REF)
            try:
                return chat_lease.reveal_for_call(
                    lambda chat_id: self._send_to_chat(chat_id, text)
                )
            finally:
                chat_lease.close()
        except TelegramTransportError as error:
            return TelegramDeliveryResult(
                TelegramDeliveryState.FAILED_RETRYABLE
                if error.retryable else TelegramDeliveryState.FAILED_FINAL,
                error.reason,
                error.retry_after_seconds,
            )
        except Exception:
            return TelegramDeliveryResult(
                TelegramDeliveryState.FAILED_RETRYABLE,
                "TELEGRAM_CONFIGURATION_UNAVAILABLE",
            )

    def _send_to_chat(self, chat_id: str, text: str) -> TelegramDeliveryResult:
        if _CHAT_ID.fullmatch(chat_id) is None:
            return TelegramDeliveryResult(
                TelegramDeliveryState.FAILED_FINAL, "TELEGRAM_PRIVATE_CHAT_INVALID"
            )
        self._with_token("sendMessage", {"chat_id": chat_id, "text": text})
        return TelegramDeliveryResult(TelegramDeliveryState.SENT)

    def _with_token(self, method: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            lease = self._token_source.acquire(TELEGRAM_BOT_TOKEN_REF)
            try:
                return lease.reveal_for_call(
                    lambda token: self._transport.request(
                        method, payload, token=token, timeout_seconds=self._timeout
                    )
                )
            finally:
                lease.close()
        except TelegramTransportError:
            raise
        except Exception:
            raise TelegramTransportError(
                "TELEGRAM_CONFIGURATION_UNAVAILABLE", retryable=True
            ) from None

    def __repr__(self) -> str:
        return "<TelegramConfigurationService redacted>"


def _opaque(chat_id: str) -> str:
    from hashlib import sha256
    return sha256(("UX10-PRIVATE-CHAT:" + chat_id).encode()).hexdigest()


__all__ = [
    "TELEGRAM_BOT_TOKEN_REF", "TELEGRAM_PRIVATE_CHAT_REF", "TELEGRAM_PROVIDER",
    "TELEGRAM_DELIVERY_CONTROL_CONFIG", "TELEGRAM_DELIVERY_CONTROL_SCHEMA",
    "TelegramConfigurationService", "TelegramConfigurationState",
    "TelegramConfigurationStatus", "TelegramDeliveryResult",
    "InMemoryTelegramDeliveryControl", "TelegramDeliveryControlStore",
    "TelegramDeliveryState",
    "TelegramPrivateChatCandidate", "TelegramTransport",
    "TelegramTransportError", "UrllibTelegramBotApiTransport",
    "telegram_delivery_control_path",
]
