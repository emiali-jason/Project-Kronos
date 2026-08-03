"""Externally inert Kite authentication dependency composition."""

from __future__ import annotations

import re
import secrets
import webbrowser
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from enum import StrEnum
from types import ModuleType
from typing import Any

from kronos.configuration.apple_keychain import (
    AppleKeychainCredentialSource,
    AppleKeychainIntendedPrincipalResolver,
    SubprocessRunner,
    run_security_subprocess,
)
from kronos.provider.adapters.kite.authentication import (
    create_kite_authentication_adapter,
)
from kronos.provider.adapters.kite.navigation import KiteLoginNavigator
from kronos.provider.callbacks.loopback import (
    LoopbackAuthenticationCallbackListener,
    ServerFactory,
    create_standard_library_server,
)
from kronos.provider.kite.adapter.kite_provider import KiteProvider
from kronos.provider.kite.auth.kite_authentication import KiteAuthentication
from kronos.provider.models.authentication import ProviderAuthenticationConfiguration
from kronos.provider.services.provider_authentication import (
    ProviderAuthenticationService,
)


_REFERENCE_PATTERN = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z")
_PROTECTED_REFERENCE_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,64}\Z")
_SHA_PATTERN = re.compile(r"[0-9a-f]{40}\Z")
_COORDINATED_PROVIDER_IDENTITY_REF = "ZERODHA_KITE"
_KITE_APPLICATION_REGISTRATION_REF = "ZERODHA-KITE-APP-REGISTRATION-PRIMARY"
_LIVE_DEPENDENCY_SET_REF = "CAR017-LIVE-COMPOSITION-DEPENDENCY-SET-V1"
_OPERATIONAL_PROVIDER = "KITE"

CapabilityValidator = Callable[[object], bool]
Clock = Callable[[], datetime]
IdentityFactory = Callable[[], str]


class LiveCompositionFailure(StrEnum):
    """Sanitized composition failures containing no activation material."""

    INVALID_ACTIVATION = "INVALID_ACTIVATION"
    INCOMPLETE_COMPOSITION = "INCOMPLETE_COMPOSITION"
    CONFIGURATION_MISMATCH = "CONFIGURATION_MISMATCH"
    DEPENDENCY_CONSTRUCTION_FAILED = "DEPENDENCY_CONSTRUCTION_FAILED"


class LiveCompositionError(RuntimeError):
    """Controlled composition failure with no raw exception retention."""

    def __init__(self, failure: LiveCompositionFailure) -> None:
        self.failure = failure
        super().__init__(failure.value)


class LiveActivationContext:
    """Immutable reviewed capability projection; construction alone has no effect."""

    __slots__ = (
        "__activation_authority_ref",
        "__activation_capability",
        "__application_registration_ref",
        "__availability_authority_ref",
        "__composition_dependency_set_ref",
        "__credential_ref",
        "__environment_ref",
        "__implementation_sha",
        "__intended_registration_ref",
        "__provider_identity_ref",
        "__provider_configuration_ref",
    )
    __hash__ = None

    def __new__(cls, *_args: object, **_kwargs: object) -> "LiveActivationContext":
        raise LiveCompositionError(LiveCompositionFailure.INVALID_ACTIVATION)

    @classmethod
    def from_reviewed_capability(
        cls,
        *,
        activation_capability: object,
        capability_validator: CapabilityValidator,
        activation_authority_ref: str,
        implementation_sha: str,
        environment_ref: str,
        provider_identity_ref: str,
        provider_configuration_ref: str,
        application_registration_ref: str,
        credential_ref: str,
        intended_registration_ref: str,
        composition_dependency_set_ref: str,
        availability_authority_ref: str | None = None,
    ) -> "LiveActivationContext":
        """Create one inert context after explicit provenance validation."""

        if not _valid_capability_type(activation_capability) or not callable(
            capability_validator
        ):
            raise LiveCompositionError(LiveCompositionFailure.INVALID_ACTIVATION)
        try:
            capability_valid = capability_validator(activation_capability)
        except Exception:
            raise LiveCompositionError(
                LiveCompositionFailure.INVALID_ACTIVATION
            ) from None
        if capability_valid is not True:
            raise LiveCompositionError(LiveCompositionFailure.INVALID_ACTIVATION)
        if not (
            _valid_reference(activation_authority_ref)
            and _SHA_PATTERN.fullmatch(implementation_sha) is not None
            and _valid_reference(environment_ref)
            and _valid_reference(provider_identity_ref)
            and _valid_reference(provider_configuration_ref)
            and _valid_reference(application_registration_ref)
            and _valid_protected_reference(credential_ref)
            and _valid_protected_reference(intended_registration_ref)
            and _valid_reference(composition_dependency_set_ref)
            and (
                availability_authority_ref is None
                or _valid_reference(availability_authority_ref)
            )
        ):
            raise LiveCompositionError(LiveCompositionFailure.INVALID_ACTIVATION)

        instance = object.__new__(cls)
        object.__setattr__(
            instance,
            "_LiveActivationContext__activation_capability",
            activation_capability,
        )
        object.__setattr__(
            instance,
            "_LiveActivationContext__activation_authority_ref",
            activation_authority_ref,
        )
        object.__setattr__(
            instance,
            "_LiveActivationContext__implementation_sha",
            implementation_sha,
        )
        object.__setattr__(
            instance,
            "_LiveActivationContext__environment_ref",
            environment_ref,
        )
        object.__setattr__(
            instance,
            "_LiveActivationContext__provider_identity_ref",
            provider_identity_ref,
        )
        object.__setattr__(
            instance,
            "_LiveActivationContext__provider_configuration_ref",
            provider_configuration_ref,
        )
        object.__setattr__(
            instance,
            "_LiveActivationContext__application_registration_ref",
            application_registration_ref,
        )
        object.__setattr__(
            instance,
            "_LiveActivationContext__credential_ref",
            credential_ref,
        )
        object.__setattr__(
            instance,
            "_LiveActivationContext__intended_registration_ref",
            intended_registration_ref,
        )
        object.__setattr__(
            instance,
            "_LiveActivationContext__composition_dependency_set_ref",
            composition_dependency_set_ref,
        )
        object.__setattr__(
            instance,
            "_LiveActivationContext__availability_authority_ref",
            availability_authority_ref,
        )
        return instance

    def __setattr__(self, _name: str, _value: object) -> None:
        raise AttributeError("LIVE_ACTIVATION_CONTEXT_IMMUTABLE")

    def _matches_capability(self, capability: object) -> bool:
        return capability is self.__activation_capability

    def _matches_configuration(
        self,
        configuration: ProviderAuthenticationConfiguration,
    ) -> bool:
        return (
            self.__credential_ref == configuration.credential_ref
            and self.__intended_registration_ref
            == configuration.intended_registration_ref
        )

    def _matches_coordinated_references(
        self,
        configuration: ProviderAuthenticationConfiguration,
    ) -> bool:
        return (
            self.__provider_identity_ref == _COORDINATED_PROVIDER_IDENTITY_REF
            and self.__application_registration_ref
            == _KITE_APPLICATION_REGISTRATION_REF
            and configuration.provider == _OPERATIONAL_PROVIDER
        )

    def _matches_dependency_set(self, dependency_set_ref: object) -> bool:
        return dependency_set_ref == self.__composition_dependency_set_ref

    @property
    def implementation_sha(self) -> str:
        return self.__implementation_sha

    @property
    def activation_authority_ref(self) -> str:
        return self.__activation_authority_ref

    @property
    def environment_ref(self) -> str:
        return self.__environment_ref

    @property
    def provider_identity_ref(self) -> str:
        return self.__provider_identity_ref

    @property
    def provider_configuration_ref(self) -> str:
        return self.__provider_configuration_ref

    @property
    def application_registration_ref(self) -> str:
        return self.__application_registration_ref

    @property
    def composition_dependency_set_ref(self) -> str:
        return self.__composition_dependency_set_ref

    @property
    def availability_authority_ref(self) -> str | None:
        return self.__availability_authority_ref

    def __repr__(self) -> str:
        return "<LiveActivationContext redacted>"

    __str__ = __repr__

    def __copy__(self) -> "LiveActivationContext":
        raise TypeError("LIVE_ACTIVATION_CONTEXT_COPY_PROHIBITED")

    def __deepcopy__(self, _memo: object) -> "LiveActivationContext":
        raise TypeError("LIVE_ACTIVATION_CONTEXT_COPY_PROHIBITED")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("LIVE_ACTIVATION_CONTEXT_SERIALIZATION_PROHIBITED")


def compose_kite_authentication(
    activation: object,
    *,
    activation_capability: object,
    configuration: ProviderAuthenticationConfiguration,
    composition_dependency_set_ref: str = _LIVE_DEPENDENCY_SET_REF,
    security_runner: SubprocessRunner = run_security_subprocess,
    browser_opener: Callable[[str], bool] = webbrowser.open,
    server_factory: ServerFactory = create_standard_library_server,
    adapter_factory: Callable[[str], Any] = create_kite_authentication_adapter,
    credential_source_factory: Callable[..., Any] = AppleKeychainCredentialSource,
    intended_principal_resolver_factory: Callable[..., Any] = (
        AppleKeychainIntendedPrincipalResolver
    ),
    navigator_factory: Callable[..., Any] = KiteLoginNavigator,
    service_factory: Callable[..., Any] = ProviderAuthenticationService,
    clock: Clock | None = None,
    identity_factory: IdentityFactory | None = None,
) -> KiteProvider:
    """Wire the one authoritative Kite path after pre-factory validation."""

    if (
        type(activation) is not LiveActivationContext
        or not activation._matches_capability(activation_capability)  # type: ignore[attr-defined]
        or not activation._matches_dependency_set(  # type: ignore[attr-defined]
            composition_dependency_set_ref
        )
    ):
        raise LiveCompositionError(LiveCompositionFailure.INVALID_ACTIVATION)

    dependencies = (
        security_runner,
        browser_opener,
        server_factory,
        adapter_factory,
        credential_source_factory,
        intended_principal_resolver_factory,
        navigator_factory,
        service_factory,
        clock or _utc_now,
        identity_factory or _new_attempt_identity,
    )
    if any(not callable(dependency) for dependency in dependencies):
        raise LiveCompositionError(LiveCompositionFailure.INCOMPLETE_COMPOSITION)
    if composition_dependency_set_ref != _LIVE_DEPENDENCY_SET_REF and any(
        dependency is real_dependency
        for dependency, real_dependency in (
            (security_runner, run_security_subprocess),
            (browser_opener, webbrowser.open),
            (server_factory, create_standard_library_server),
            (adapter_factory, create_kite_authentication_adapter),
            (credential_source_factory, AppleKeychainCredentialSource),
            (
                intended_principal_resolver_factory,
                AppleKeychainIntendedPrincipalResolver,
            ),
        )
    ):
        raise LiveCompositionError(LiveCompositionFailure.INVALID_ACTIVATION)
    if type(configuration) is not ProviderAuthenticationConfiguration:
        raise LiveCompositionError(LiveCompositionFailure.CONFIGURATION_MISMATCH)
    if not activation._matches_coordinated_references(  # type: ignore[attr-defined]
        configuration
    ):
        raise LiveCompositionError(LiveCompositionFailure.CONFIGURATION_MISMATCH)
    if not activation._matches_configuration(configuration):  # type: ignore[attr-defined]
        raise LiveCompositionError(LiveCompositionFailure.CONFIGURATION_MISMATCH)

    effective_clock = clock or _utc_now
    effective_identity_factory = identity_factory or _new_attempt_identity

    try:
        credential_source = credential_source_factory(
            provider=configuration.provider,
            runner=security_runner,
        )
        principal_resolver = intended_principal_resolver_factory(
            provider=configuration.provider,
            runner=security_runner,
        )
        navigator = navigator_factory(opener=browser_opener)

        def listener_factory() -> LoopbackAuthenticationCallbackListener:
            return LoopbackAuthenticationCallbackListener(
                server_factory=server_factory,
                clock=effective_clock,
            )

        service = service_factory(
            configuration,
            credential_source=credential_source,
            principal_resolver=principal_resolver,
            adapter_factory=adapter_factory,
            listener_factory=listener_factory,
            navigator=navigator,
            clock=effective_clock,
            identity_factory=effective_identity_factory,
        )
        authentication = KiteAuthentication(service, clock=effective_clock)
        return KiteProvider(authentication)
    except LiveCompositionError:
        raise
    except Exception:
        raise LiveCompositionError(
            LiveCompositionFailure.DEPENDENCY_CONSTRUCTION_FAILED
        ) from None


def _valid_capability_type(capability: object) -> bool:
    if isinstance(
        capability,
        (
            str,
            bytes,
            bytearray,
            bool,
            int,
            float,
            Mapping,
            Sequence,
            ModuleType,
            type,
            ProviderAuthenticationConfiguration,
        ),
    ):
        return False
    if callable(capability):
        return False
    if callable(getattr(capability, "__fspath__", None)):
        return False
    return not type(capability).__module__.startswith("kronos.configuration")


def _valid_reference(value: object) -> bool:
    return isinstance(value, str) and _REFERENCE_PATTERN.fullmatch(value) is not None


def _valid_protected_reference(value: object) -> bool:
    return (
        isinstance(value, str)
        and _PROTECTED_REFERENCE_PATTERN.fullmatch(value) is not None
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_attempt_identity() -> str:
    return secrets.token_hex(16)


__all__ = [
    "LiveActivationContext",
    "LiveCompositionError",
    "LiveCompositionFailure",
    "compose_kite_authentication",
]
