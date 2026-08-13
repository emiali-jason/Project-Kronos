import pickle
import json
from pathlib import Path

from kronos.configuration.openai_chart_analyst import (
    ChartAnalystConnectionStatus,
    ChartAnalystV2ActivationService,
    ChartAnalystV2ActivationStatus,
    CHART_ANALYST_V2_ACTIVATION_SCHEMA,
    OPENAI_CHART_ANALYST_CREDENTIAL_REF,
    OpenAIChartAnalystCredentialService,
)


class _Provisioner:
    def __init__(self, failure: BaseException | None = None) -> None:
        self.failure = failure
        self.calls: list[tuple[str, str]] = []

    def store_api_key(self, reference: str, value: str) -> None:
        self.calls.append((reference, value))
        if self.failure is not None:
            raise self.failure


class _PresenceProbe:
    def __init__(self, stored: bool | BaseException) -> None:
        self.stored = stored
        self.calls: list[str] = []

    def api_key_stored(self, reference: str) -> bool:
        self.calls.append(reference)
        if isinstance(self.stored, BaseException):
            raise self.stored
        return self.stored


class _CapabilityTester:
    def __init__(self, result: bool | BaseException) -> None:
        self.result = result
        self.calls = 0

    def test_connection(self) -> bool:
        self.calls += 1
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


def _service(
    *,
    provisioner: _Provisioner | None = None,
    stored: bool | BaseException = False,
    connection: bool | BaseException = True,
) -> tuple[
    OpenAIChartAnalystCredentialService,
    _Provisioner,
    _PresenceProbe,
    _CapabilityTester,
]:
    writer = provisioner or _Provisioner()
    presence = _PresenceProbe(stored)
    tester = _CapabilityTester(connection)
    return (
        OpenAIChartAnalystCredentialService(
            provisioner=writer,
            presence_probe=presence,
            capability_tester=tester,
        ),
        writer,
        presence,
        tester,
    )


def test_status_uses_only_the_three_sanitized_values() -> None:
    assert {item.value for item in ChartAnalystConnectionStatus} == {
        "CONNECTED",
        "NOT CONFIGURED",
        "CONNECTION FAILED",
    }
    service, _, presence, tester = _service(stored=False)

    assert service.status() is ChartAnalystConnectionStatus.NOT_CONFIGURED
    assert presence.calls == [OPENAI_CHART_ANALYST_CREDENTIAL_REF]
    assert tester.calls == 0


def test_write_only_configuration_stores_key_by_opaque_reference() -> None:
    service, provisioner, presence, _ = _service(stored=True)
    api_key = "fake-openai-key-value"

    status = service.configure(api_key)

    assert status is ChartAnalystConnectionStatus.CONNECTED
    assert provisioner.calls == [
        (OPENAI_CHART_ANALYST_CREDENTIAL_REF, api_key)
    ]
    assert presence.calls == [OPENAI_CHART_ANALYST_CREDENTIAL_REF]
    assert api_key not in repr(service)
    assert repr(service) == "<OpenAIChartAnalystCredentialService redacted>"


def test_invalid_or_failed_configuration_returns_only_connection_failed() -> None:
    invalid, invalid_writer, _, _ = _service(stored=True)
    assert invalid.configure("short") is ChartAnalystConnectionStatus.CONNECTION_FAILED
    assert invalid_writer.calls == []

    api_key = "fake-openai-key-value"
    failed, writer, _, _ = _service(
        provisioner=_Provisioner(RuntimeError(api_key)),
        stored=True,
    )
    assert failed.configure(api_key) is ChartAnalystConnectionStatus.CONNECTION_FAILED
    assert writer.calls == [(OPENAI_CHART_ANALYST_CREDENTIAL_REF, api_key)]
    assert api_key not in repr(failed)


def test_capability_test_is_bounded_to_presence_then_tester() -> None:
    missing, _, _, missing_tester = _service(stored=False)
    assert missing.test_connection() is ChartAnalystConnectionStatus.NOT_CONFIGURED
    assert missing_tester.calls == 0

    connected, _, _, connected_tester = _service(stored=True, connection=True)
    assert connected.test_connection() is ChartAnalystConnectionStatus.CONNECTED
    assert connected_tester.calls == 1

    failed, _, _, failed_tester = _service(
        stored=True,
        connection=RuntimeError("sensitive provider detail"),
    )
    assert failed.test_connection() is ChartAnalystConnectionStatus.CONNECTION_FAILED
    assert failed_tester.calls == 1


def test_credential_service_cannot_be_serialized() -> None:
    service, _, _, _ = _service(stored=True)

    try:
        pickle.dumps(service)
    except TypeError as error:
        assert str(error) == "CHART_ANALYST_CREDENTIAL_SERVICE_SERIALIZATION_PROHIBITED"
    else:
        raise AssertionError("credential service serialization must fail")


def test_v2_activation_persists_across_service_restart(tmp_path: Path) -> None:
    path = tmp_path / "configuration" / "chart-analyst-v2-activation.json"
    first = ChartAnalystV2ActivationService(path)
    assert first.status() is ChartAnalystV2ActivationStatus.DISABLED

    assert first.set_enabled(True) is ChartAnalystV2ActivationStatus.ENABLED
    restarted = ChartAnalystV2ActivationService(path)
    assert restarted.status() is ChartAnalystV2ActivationStatus.ENABLED
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "schema_identity": CHART_ANALYST_V2_ACTIVATION_SCHEMA,
        "enabled": True,
    }
    assert path.stat().st_mode & 0o777 == 0o600

    assert restarted.set_enabled(False) is ChartAnalystV2ActivationStatus.DISABLED
    assert ChartAnalystV2ActivationService(path).enabled() is False


def test_v2_activation_fails_closed_for_invalid_or_linked_records(
    tmp_path: Path,
) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"enabled":true}', encoding="utf-8")
    assert ChartAnalystV2ActivationService(invalid).enabled() is False

    target = tmp_path / "target.json"
    ChartAnalystV2ActivationService(target).set_enabled(True)
    linked = tmp_path / "linked.json"
    linked.symlink_to(target)
    assert ChartAnalystV2ActivationService(linked).enabled() is False
