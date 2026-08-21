from kronos.configuration.credentials import OneUseSecretLease
from kronos.integrations.telegram import (
    TELEGRAM_BOT_TOKEN_REF,
    TELEGRAM_PRIVATE_CHAT_REF,
    TelegramConfigurationService,
    TelegramConfigurationState,
    TelegramDeliveryControlStore,
    TelegramDeliveryState,
    TelegramTransportError,
)


TOKEN = "123456789:" + ("A" * 24)


class Vault:
    def __init__(self) -> None:
        self.secret = {}
        self.key = {}

    def store_api_secret(self, reference, value):  # type: ignore[no-untyped-def]
        self.secret[reference] = value

    def store_api_key(self, reference, value):  # type: ignore[no-untyped-def]
        self.key[reference] = value

    def api_secret_stored(self, reference):  # type: ignore[no-untyped-def]
        return reference in self.secret

    def api_key_stored(self, reference):  # type: ignore[no-untyped-def]
        return reference in self.key

    def remove_api_secret(self, reference):  # type: ignore[no-untyped-def]
        self.secret.pop(reference, None)

    def remove_api_key(self, reference):  # type: ignore[no-untyped-def]
        self.key.pop(reference, None)


class Source:
    def __init__(self, values) -> None:  # type: ignore[no-untyped-def]
        self.values = values

    def acquire(self, reference):  # type: ignore[no-untyped-def]
        return OneUseSecretLease(self.values[reference])


class Transport:
    def __init__(self, updates=()) -> None:  # type: ignore[no-untyped-def]
        self.updates = updates
        self.calls = []
        self.failure = None

    def request(self, method, payload, *, token, timeout_seconds):  # type: ignore[no-untyped-def]
        self.calls.append((method, payload, token, timeout_seconds))
        if self.failure:
            raise self.failure
        if method == "getUpdates":
            return {"ok": True, "result": list(self.updates)}
        return {"ok": True, "result": {"id": 1}}


def service(updates=()):  # type: ignore[no-untyped-def]
    vault = Vault()
    transport = Transport(updates)
    value = TelegramConfigurationService(
        provisioner=vault,
        presence_probe=vault,
        remover=vault,
        token_source=Source(vault.secret),
        chat_source=Source(vault.key),
        transport=transport,
    )
    return value, vault, transport


def test_token_is_write_only_and_status_is_sanitized() -> None:
    value, vault, transport = service()
    assert value.status().state is TelegramConfigurationState.NOT_CONFIGURED
    status = value.configure_token(TOKEN)
    assert status.state is TelegramConfigurationState.PRIVATE_CHAT_REQUIRED
    assert vault.secret[TELEGRAM_BOT_TOKEN_REF] == TOKEN
    assert transport.calls[0][0] == "getMe"
    assert TOKEN not in repr(value) and TOKEN not in str(status)


def test_invalid_token_fails_closed_without_storage() -> None:
    value, vault, _ = service()
    status = value.configure_token("bad token")
    assert status.state is TelegramConfigurationState.CONNECTION_FAILED
    assert vault.secret == {}


def test_provider_rejected_token_fails_closed_without_storage() -> None:
    value, vault, transport = service()
    transport.failure = TelegramTransportError(
        "TELEGRAM_RESPONSE_REJECTED", retryable=False
    )
    status = value.configure_token(TOKEN)
    assert status.state is TelegramConfigurationState.CONNECTION_FAILED
    assert status.safe_detail == "TELEGRAM_RESPONSE_REJECTED"
    assert vault.secret == {}


def test_discovery_accepts_only_private_chats_and_requires_explicit_confirmation() -> None:
    updates = (
        {"message": {"chat": {"id": 11111, "type": "private"}}},
        {"message": {"chat": {"id": -22222, "type": "group"}}},
        {"channel_post": {"chat": {"id": -33333, "type": "channel"}}},
    )
    value, vault, transport = service(updates)
    value.configure_token(TOKEN)
    candidates = value.discover_private_chats()
    assert len(candidates) == 1
    assert candidates[0].display_identity == "PRIVATE CHAT 1"
    assert "11111" not in repr(candidates)
    assert vault.key == {}
    value.confirm_private_chat(candidates[0].selection_id)
    assert vault.key[TELEGRAM_PRIVATE_CHAT_REF] == "11111"
    assert value.status().state is TelegramConfigurationState.READY
    assert tuple(item[0] for item in transport.calls[:2]) == ("getMe", "getUpdates")


def test_multiple_private_chats_are_not_silently_bound() -> None:
    updates = tuple(
        {"message": {"chat": {"id": value, "type": "private"}}}
        for value in (11111, 22222)
    )
    value, vault, _ = service(updates)
    value.configure_token(TOKEN)
    assert len(value.discover_private_chats()) == 2
    assert vault.key == {}


def test_empty_discovery_gives_safe_actionable_retry_guidance() -> None:
    value, vault, _ = service()
    value.configure_token(TOKEN)
    assert value.discover_private_chats() == ()
    assert value.status().safe_detail == (
        "SEND A NEW MESSAGE TO KRONOS ALERTS, THEN DISCOVER AGAIN"
    )
    assert vault.key == {}


def test_test_message_is_exact_and_no_secret_is_returned() -> None:
    value, vault, transport = service()
    value.configure_token(TOKEN)
    vault.store_api_key(TELEGRAM_PRIVATE_CHAT_REF, "11111")
    result = value.test()
    assert result.state is TelegramDeliveryState.SENT
    method, payload, token, _ = transport.calls[-1]
    assert method == "sendMessage"
    assert payload["text"] == "KRONOS · SWING\nTelegram connection test successful."
    assert payload["chat_id"] == "11111"
    assert token == TOKEN
    assert TOKEN not in repr(result)


def test_retryable_and_final_transport_failures_are_sanitized() -> None:
    value, vault, transport = service()
    value.configure_token(TOKEN)
    vault.store_api_key(TELEGRAM_PRIVATE_CHAT_REF, "11111")
    transport.failure = TelegramTransportError(
        "TELEGRAM_RATE_LIMITED", retryable=True, retry_after_seconds=9
    )
    retryable = value.send("KRONOS · SWING\nTest")
    assert retryable.state is TelegramDeliveryState.FAILED_RETRYABLE
    assert retryable.retry_after_seconds == 9
    transport.failure = TelegramTransportError(
        "TELEGRAM_RESPONSE_REJECTED", retryable=False
    )
    final = value.send("KRONOS · SWING\nTest")
    assert final.state is TelegramDeliveryState.FAILED_FINAL


def test_unconfirmed_or_invalid_chat_fails_closed() -> None:
    value, _, transport = service()
    value.configure_token(TOKEN)
    assert value.test().state is TelegramDeliveryState.FAILED_RETRYABLE
    assert tuple(item[0] for item in transport.calls) == ("getMe",)


def test_disconnect_and_reconnect_only_control_delivery() -> None:
    value, vault, transport = service()
    value.configure_token(TOKEN)
    vault.store_api_key(TELEGRAM_PRIVATE_CHAT_REF, "11111")

    disconnected = value.disconnect()
    assert disconnected.state is TelegramConfigurationState.DISCONNECTED
    assert disconnected.delivery_enabled is False
    assert vault.secret[TELEGRAM_BOT_TOKEN_REF] == TOKEN
    assert vault.key[TELEGRAM_PRIVATE_CHAT_REF] == "11111"
    assert value.test().safe_reason == "TELEGRAM_DELIVERY_DISABLED"
    assert tuple(item[0] for item in transport.calls) == ("getMe",)

    connected = value.connect()
    assert connected.state is TelegramConfigurationState.READY
    assert connected.delivery_enabled is True
    assert tuple(item[0] for item in transport.calls) == ("getMe", "getMe")
    assert value.test().state is TelegramDeliveryState.SENT


def test_remove_configuration_is_explicit_and_removes_both_keychain_items() -> None:
    value, vault, _ = service()
    value.configure_token(TOKEN)
    vault.store_api_key(TELEGRAM_PRIVATE_CHAT_REF, "11111")

    status = value.remove_configuration()

    assert status.state is TelegramConfigurationState.NOT_CONFIGURED
    assert status.token_configured is False
    assert status.private_chat_configured is False
    assert vault.secret == {} and vault.key == {}


def test_delivery_control_store_is_private_atomic_and_restart_stable(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "telegram-delivery.json"
    assert TelegramDeliveryControlStore(path).enabled() is True
    first = TelegramDeliveryControlStore(path)
    first.set_enabled(False)
    assert TelegramDeliveryControlStore(path).enabled() is False
    assert path.stat().st_mode & 0o777 == 0o600
    first.set_enabled(True)
    assert TelegramDeliveryControlStore(path).enabled() is True
