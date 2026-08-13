"""Protected OpenAI Chart Analyst credential configuration boundary."""

from __future__ import annotations

import json
from enum import StrEnum
import os
from pathlib import Path
import stat
import tempfile
from threading import RLock
from typing import Protocol

from kronos.configuration.exceptions import ConfigurationError


OPENAI_CHART_ANALYST_PROVIDER = "OPENAI"
OPENAI_CHART_ANALYST_CREDENTIAL_REF = "CHART-ANALYST-API-KEY-PRIMARY"
_MAX_API_KEY_CHARACTERS = 512
CHART_ANALYST_V2_ACTIVATION_SCHEMA = "KRONOS-CHART-ANALYST-V2-ACTIVATION-V1"
CHART_ANALYST_V2_ACTIVATION_CONFIG = "chart-analyst-v2-activation.json"


class ChartAnalystConnectionStatus(StrEnum):
    """The complete sanitized Browser-visible connection vocabulary."""

    CONNECTED = "CONNECTED"
    NOT_CONFIGURED = "NOT CONFIGURED"
    CONNECTION_FAILED = "CONNECTION FAILED"


class ChartAnalystV2ActivationStatus(StrEnum):
    """The complete Browser-visible activation vocabulary."""

    ENABLED = "ENABLED"
    DISABLED = "DISABLED"


def chart_analyst_v2_activation_config_path(*, home: Path | None = None) -> Path:
    """Return the stable per-user location for non-secret activation state."""

    root = Path.home() if home is None else home
    return (
        root
        / "Library"
        / "Application Support"
        / "Project-KRONOS"
        / CHART_ANALYST_V2_ACTIVATION_CONFIG
    )


class ChartAnalystV2ActivationService:
    """Persist the Sponsor's non-secret Chart Analyst V2 activation choice."""

    __slots__ = ("_lock", "_path")

    def __init__(self, path: Path | None = None) -> None:
        if path is not None and not isinstance(path, Path):
            raise TypeError("CHART_ANALYST_V2_ACTIVATION_DEPENDENCY_INVALID")
        self._path = path or chart_analyst_v2_activation_config_path()
        self._lock = RLock()

    def status(self) -> ChartAnalystV2ActivationStatus:
        with self._lock:
            return (
                ChartAnalystV2ActivationStatus.ENABLED
                if self._read_enabled()
                else ChartAnalystV2ActivationStatus.DISABLED
            )

    def enabled(self) -> bool:
        return self.status() is ChartAnalystV2ActivationStatus.ENABLED

    def set_enabled(self, enabled: bool) -> ChartAnalystV2ActivationStatus:
        if type(enabled) is not bool:
            raise TypeError("CHART_ANALYST_V2_ACTIVATION_INVALID")
        with self._lock:
            self._write(enabled)
            return (
                ChartAnalystV2ActivationStatus.ENABLED
                if enabled
                else ChartAnalystV2ActivationStatus.DISABLED
            )

    def _read_enabled(self) -> bool:
        try:
            metadata = self._path.lstat()
        except FileNotFoundError:
            return False
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
            and payload["schema_identity"] == CHART_ANALYST_V2_ACTIVATION_SCHEMA
            and type(payload["enabled"]) is bool
            and payload["enabled"]
        )

    def _write(self, enabled: bool) -> None:
        self._path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        payload = json.dumps(
            {
                "schema_identity": CHART_ANALYST_V2_ACTIVATION_SCHEMA,
                "enabled": enabled,
            },
            indent=2,
            sort_keys=True,
        ) + "\n"
        temporary_name = ""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._path.parent,
                prefix=f".{self._path.name}.",
                delete=False,
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
            raise ConfigurationError(
                "CHART_ANALYST_V2_ACTIVATION_WRITE_FAILED"
            ) from error


class ApiKeyProvisioner(Protocol):
    def store_api_key(self, reference: str, value: str) -> None: ...


class ApiKeyPresenceProbe(Protocol):
    def api_key_stored(self, reference: str) -> bool: ...


class ChartAnalystCapabilityTester(Protocol):
    def test_connection(self) -> bool: ...


class OpenAIChartAnalystCredentialService:
    """Coordinate write-only provisioning, presence and bounded capability tests."""

    __slots__ = (
        "_capability_tester",
        "_credential_ref",
        "_lock",
        "_presence_probe",
        "_provisioner",
        "_status",
    )

    def __init__(
        self,
        *,
        provisioner: ApiKeyProvisioner,
        presence_probe: ApiKeyPresenceProbe,
        capability_tester: ChartAnalystCapabilityTester,
        credential_ref: str = OPENAI_CHART_ANALYST_CREDENTIAL_REF,
    ) -> None:
        if (
            not credential_ref
            or not hasattr(provisioner, "store_api_key")
            or not hasattr(presence_probe, "api_key_stored")
            or not hasattr(capability_tester, "test_connection")
        ):
            raise TypeError("CHART_ANALYST_CREDENTIAL_DEPENDENCY_INVALID")
        self._provisioner = provisioner
        self._presence_probe = presence_probe
        self._capability_tester = capability_tester
        self._credential_ref = credential_ref
        self._lock = RLock()
        self._status = ChartAnalystConnectionStatus.NOT_CONFIGURED

    def status(self) -> ChartAnalystConnectionStatus:
        """Return only a sanitized presence/connection state."""

        with self._lock:
            stored = self._stored_status()
            if stored is not True:
                self._status = (
                    ChartAnalystConnectionStatus.NOT_CONFIGURED
                    if stored is False
                    else ChartAnalystConnectionStatus.CONNECTION_FAILED
                )
            elif self._status is ChartAnalystConnectionStatus.NOT_CONFIGURED:
                self._status = ChartAnalystConnectionStatus.CONNECTED
            return self._status

    def configure(self, api_key: str) -> ChartAnalystConnectionStatus:
        """Replace the protected credential without ever returning its value."""

        with self._lock:
            if not _valid_api_key(api_key):
                self._status = ChartAnalystConnectionStatus.CONNECTION_FAILED
                return self._status
            try:
                self._provisioner.store_api_key(self._credential_ref, api_key)
                api_key = ""
                if self._stored_status() is not True:
                    raise RuntimeError("CHART_ANALYST_CREDENTIAL_NOT_STORED")
            except Exception:
                self._status = ChartAnalystConnectionStatus.CONNECTION_FAILED
            else:
                self._status = ChartAnalystConnectionStatus.CONNECTED
            finally:
                api_key = ""
            return self._status

    def test_connection(self) -> ChartAnalystConnectionStatus:
        """Run one capability-only probe with no Swing or TradingView input."""

        with self._lock:
            stored = self._stored_status()
            if stored is False:
                self._status = ChartAnalystConnectionStatus.NOT_CONFIGURED
                return self._status
            if stored is not True:
                self._status = ChartAnalystConnectionStatus.CONNECTION_FAILED
                return self._status
            try:
                connected = self._capability_tester.test_connection()
            except Exception:
                connected = False
            self._status = (
                ChartAnalystConnectionStatus.CONNECTED
                if connected is True
                else ChartAnalystConnectionStatus.CONNECTION_FAILED
            )
            return self._status

    def _stored_status(self) -> bool | None:
        try:
            stored = self._presence_probe.api_key_stored(self._credential_ref)
        except Exception:
            return None
        return stored if type(stored) is bool else None

    def __repr__(self) -> str:
        return "<OpenAIChartAnalystCredentialService redacted>"

    __str__ = __repr__

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("CHART_ANALYST_CREDENTIAL_SERVICE_SERIALIZATION_PROHIBITED")


def _valid_api_key(value: object) -> bool:
    return (
        isinstance(value, str)
        and 8 <= len(value) <= _MAX_API_KEY_CHARACTERS
        and all(33 <= ord(character) <= 126 for character in value)
    )


__all__ = [
    "ChartAnalystCapabilityTester",
    "ChartAnalystConnectionStatus",
    "ChartAnalystV2ActivationService",
    "ChartAnalystV2ActivationStatus",
    "CHART_ANALYST_V2_ACTIVATION_CONFIG",
    "CHART_ANALYST_V2_ACTIVATION_SCHEMA",
    "OPENAI_CHART_ANALYST_CREDENTIAL_REF",
    "OPENAI_CHART_ANALYST_PROVIDER",
    "OpenAIChartAnalystCredentialService",
    "chart_analyst_v2_activation_config_path",
]
