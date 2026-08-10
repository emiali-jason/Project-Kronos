import inspect
from pathlib import Path

from tools.provider_pilots import provider_foundation_v2_provisioning as setup


class _Provisioner:
    def __init__(self) -> None:
        self.api_keys: list[tuple[str, str]] = []
        self.api_secrets: list[tuple[str, str]] = []
        self.principals: list[tuple[str, str]] = []

    def store_api_key(self, reference: str, value: str) -> None:
        self.api_keys.append((reference, value))

    def store_api_secret(self, reference: str, value: str) -> None:
        self.api_secrets.append((reference, value))

    def store_intended_principal(self, reference: str, value: str) -> None:
        self.principals.append((reference, value))


class _Probe:
    def __init__(
        self,
        *,
        api_key: bool,
        api_secret: bool,
        intended_principal: bool = True,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.intended_principal = intended_principal

    def api_key_stored(self, _reference: str) -> bool:
        return self.api_key

    def api_secret_stored(self, _reference: str) -> bool:
        return self.api_secret

    def intended_principal_stored(self, _reference: str) -> bool:
        return self.intended_principal


def test_provisioning_writes_config_and_both_protected_credentials(
    tmp_path: Path,
) -> None:
    provisioner = _Provisioner()
    probe = _Probe(api_key=True, api_secret=True)
    config_path = tmp_path / "provider-authentication.json"

    evidence = setup.provision_workstation(
        api_key="unit-api-key",
        api_secret="unit-api-secret",
        intended_principal="AB1234",
        provisioner=provisioner,
        probe=probe,
        config_path=config_path,
    )

    assert provisioner.api_keys == [
        ("ZERODHA-KITE-APP-REGISTRATION-PRIMARY", "unit-api-key")
    ]
    assert provisioner.api_secrets == [
        ("KITE-API-SECRET-PRIMARY", "unit-api-secret")
    ]
    assert provisioner.principals == [
        ("KITE-INTENDED-PRINCIPAL-PRIMARY", "AB1234")
    ]
    assert evidence == setup.ProvisioningEvidence(
        provider_configuration="READY",
        api_key="STORED",
        api_secret="STORED",
        intended_principal="STORED",
        authentication_readiness="READY",
    )
    contents = config_path.read_text(encoding="utf-8")
    assert "unit-api-key" not in contents
    assert "unit-api-secret" not in contents


def test_blank_fields_verify_existing_items_without_replacing_them(
    tmp_path: Path,
) -> None:
    provisioner = _Provisioner()

    evidence = setup.provision_workstation(
        api_key="",
        api_secret="",
        intended_principal="",
        provisioner=provisioner,
        probe=_Probe(api_key=True, api_secret=True),
        config_path=tmp_path / "provider-authentication.json",
    )

    assert provisioner.api_keys == []
    assert provisioner.api_secrets == []
    assert provisioner.principals == []
    assert evidence.authentication_readiness == "READY"


def test_missing_item_is_reported_without_retrieving_or_displaying_value(
    tmp_path: Path,
) -> None:
    path = setup.provision_provider_authentication_application_config(
        path=tmp_path / "provider-authentication.json"
    )

    evidence = setup.inspect_readiness(
        probe=_Probe(api_key=True, api_secret=False),
        config_path=path,
    )

    assert evidence.api_key == "STORED"
    assert evidence.api_secret == "MISSING"
    assert evidence.authentication_readiness == "NOT READY"


def test_setup_ui_has_no_authentication_or_order_path() -> None:
    source = inspect.getsource(setup)

    assert "begin_login" not in source
    assert "complete_callback" not in source
    assert "KiteConnect" not in source
    assert "place_order" not in source
    assert "modify_order" not in source
    assert "cancel_order" not in source
    assert "provider_foundation_v2_historical_proof" not in source
    assert 'show="•"' in source
    assert "print(" not in source
