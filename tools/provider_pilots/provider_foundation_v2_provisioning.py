"""One-time Sponsor workstation provisioning for Provider Foundation V2."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from typing import Callable, Protocol

from kronos.configuration.apple_keychain import (
    AppleKeychainCredentialPresenceProbe,
    AppleKeychainCredentialProvisioner,
    run_security_presence_subprocess,
    run_security_framework_provisioning,
)
from kronos.configuration.loader import (
    provider_authentication_application_config_path,
    provider_authentication_application_config_ready,
    provision_provider_authentication_application_config,
)


WINDOW_TITLE = "KRONOS — Provider Foundation V2 Setup"
API_KEY_REFERENCE = "ZERODHA-KITE-APP-REGISTRATION-PRIMARY"
API_SECRET_REFERENCE = "KITE-API-SECRET-PRIMARY"
INTENDED_PRINCIPAL_REFERENCE = "KITE-INTENDED-PRINCIPAL-PRIMARY"


class CredentialProvisioner(Protocol):
    def store_api_key(self, reference: str, value: str) -> None: ...

    def store_api_secret(self, reference: str, value: str) -> None: ...

    def store_intended_principal(self, reference: str, value: str) -> None: ...


class CredentialPresenceProbe(Protocol):
    def api_key_stored(self, reference: str) -> bool: ...

    def api_secret_stored(self, reference: str) -> bool: ...

    def intended_principal_stored(self, reference: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class ProvisioningEvidence:
    provider_configuration: str
    api_key: str
    api_secret: str
    intended_principal: str
    authentication_readiness: str


def inspect_readiness(
    *,
    probe: CredentialPresenceProbe,
    config_path: Path,
) -> ProvisioningEvidence:
    """Return sanitized presence-only readiness evidence."""

    try:
        configuration_ready = provider_authentication_application_config_ready(
            path=config_path
        )
        api_key_stored = probe.api_key_stored(API_KEY_REFERENCE)
        api_secret_stored = probe.api_secret_stored(API_SECRET_REFERENCE)
        intended_principal_stored = probe.intended_principal_stored(
            INTENDED_PRINCIPAL_REFERENCE
        )
    except Exception:
        return ProvisioningEvidence(
            provider_configuration="NOT READY",
            api_key="MISSING",
            api_secret="MISSING",
            intended_principal="MISSING",
            authentication_readiness="NOT READY",
        )
    ready = (
        configuration_ready
        and api_key_stored
        and api_secret_stored
        and intended_principal_stored
    )
    return ProvisioningEvidence(
        provider_configuration="READY" if configuration_ready else "NOT READY",
        api_key="STORED" if api_key_stored else "MISSING",
        api_secret="STORED" if api_secret_stored else "MISSING",
        intended_principal=(
            "STORED" if intended_principal_stored else "MISSING"
        ),
        authentication_readiness="READY" if ready else "NOT READY",
    )


def provision_workstation(
    *,
    api_key: str,
    api_secret: str,
    intended_principal: str,
    provisioner: CredentialProvisioner,
    probe: CredentialPresenceProbe,
    config_path: Path,
    config_writer: Callable[..., Path] = (
        provision_provider_authentication_application_config
    ),
) -> ProvisioningEvidence:
    """Provision supplied credentials and return sanitized readiness only."""

    config_writer(path=config_path)
    if api_key:
        provisioner.store_api_key(API_KEY_REFERENCE, api_key)
    if api_secret:
        provisioner.store_api_secret(API_SECRET_REFERENCE, api_secret)
    if intended_principal:
        provisioner.store_intended_principal(
            INTENDED_PRINCIPAL_REFERENCE,
            intended_principal,
        )
    return inspect_readiness(probe=probe, config_path=config_path)


class _ProvisioningWindow:
    """Setup-only UI; entered values are cleared immediately after use."""

    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        self._config_path = provider_authentication_application_config_path()
        self._provisioner = AppleKeychainCredentialProvisioner(
            provider="KITE",
            runner=run_security_framework_provisioning,
        )
        self._probe = AppleKeychainCredentialPresenceProbe(
            provider="KITE",
            runner=run_security_presence_subprocess,
        )
        root.title(WINDOW_TITLE)
        root.resizable(False, False)
        frame = ttk.Frame(root, padding=18)
        frame.grid(row=0, column=0)
        ttk.Label(
            frame,
            text="One-time Kite workstation setup or credential replacement",
        ).grid(row=0, column=0, columnspan=2, sticky="w")

        ttk.Label(frame, text="Kite API key").grid(
            row=1,
            column=0,
            sticky="w",
            pady=(14, 4),
        )
        self._api_key = ttk.Entry(frame, width=42, show="•")
        self._api_key.grid(row=1, column=1, pady=(14, 4))
        ttk.Label(frame, text="Kite API secret").grid(
            row=2,
            column=0,
            sticky="w",
            pady=4,
        )
        self._api_secret = ttk.Entry(frame, width=42, show="•")
        self._api_secret.grid(row=2, column=1, pady=4)
        ttk.Label(frame, text="Intended Kite principal").grid(
            row=3,
            column=0,
            sticky="w",
            pady=4,
        )
        self._intended_principal = ttk.Entry(frame, width=42, show="•")
        self._intended_principal.grid(row=3, column=1, pady=4)

        self._status = tk.StringVar(value="Checking readiness…")
        ttk.Label(
            frame,
            textvariable=self._status,
            justify="left",
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(14, 10))
        ttk.Button(
            frame,
            text="Provision / Verify",
            command=self._provision,
        ).grid(row=5, column=0, columnspan=2, sticky="w")
        self._refresh()

    def _render(self, evidence: ProvisioningEvidence) -> None:
        self._status.set(
            "\n".join(
                (
                    f"Provider configuration: {evidence.provider_configuration}",
                    f"Kite API key: {evidence.api_key}",
                    f"Kite API secret: {evidence.api_secret}",
                    f"Intended principal: {evidence.intended_principal}",
                    f"Authentication readiness: {evidence.authentication_readiness}",
                )
            )
        )

    def _refresh(self) -> None:
        self._render(
            inspect_readiness(
                probe=self._probe,
                config_path=self._config_path,
            )
        )

    def _provision(self) -> None:
        api_key = self._api_key.get()
        api_secret = self._api_secret.get()
        intended_principal = self._intended_principal.get()
        self._api_key.delete(0, tk.END)
        self._api_secret.delete(0, tk.END)
        self._intended_principal.delete(0, tk.END)
        try:
            evidence = provision_workstation(
                api_key=api_key,
                api_secret=api_secret,
                intended_principal=intended_principal,
                provisioner=self._provisioner,
                probe=self._probe,
                config_path=self._config_path,
            )
        except Exception:
            evidence = inspect_readiness(
                probe=self._probe,
                config_path=self._config_path,
            )
        finally:
            api_key = ""
            api_secret = ""
            intended_principal = ""
        self._render(evidence)


def main() -> None:
    root = tk.Tk()
    _ProvisioningWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
