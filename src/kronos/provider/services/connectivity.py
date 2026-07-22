import logging
from collections.abc import Callable

from kronos.configuration.exceptions import ConfigurationError
from kronos.configuration.settings import Settings
from kronos.provider.adapters.kite.connectivity import (
    KiteConnectivityAdapter,
    create_kite_connectivity_adapter,
)
from kronos.provider.exceptions.connectivity import (
    ProviderConnectivityError,
    ProviderErrorCode,
)
from kronos.provider.models.availability import (
    ProviderAvailability,
    ProviderAvailabilityState,
)


_LOGGER = logging.getLogger(__name__)
_AdapterFactory = Callable[[str, str], KiteConnectivityAdapter]


class KiteConnectivityService:
    """Orchestrate one explicit Provider-internal connectivity probe."""

    __slots__ = ("__adapter", "__adapter_factory", "__settings", "__state")

    def __init__(
        self,
        settings: Settings,
        adapter_factory: _AdapterFactory = create_kite_connectivity_adapter,
    ) -> None:
        self.__settings = settings
        self.__adapter_factory = adapter_factory
        self.__adapter: KiteConnectivityAdapter | None = None
        self.__state = ProviderAvailabilityState.NOT_INITIALIZED

    @property
    def state(self) -> ProviderAvailabilityState:
        return self.__state

    def probe(self) -> ProviderAvailability:
        if self.__adapter is None:
            invalid = self.__initialize()
            if invalid is not None:
                return invalid

        _LOGGER.info(
            "provider_connectivity_probe_started",
            extra={"provider": "KITE", "attempt": 1},
        )

        try:
            self.__adapter.probe()
        except ProviderConnectivityError as error:
            return self.__failure(error.code)

        self.__state = ProviderAvailabilityState.AVAILABLE
        _LOGGER.info(
            "provider_connectivity_probe_succeeded",
            extra={"provider": "KITE", "state": self.__state.value},
        )
        return ProviderAvailability(self.__state)

    def shutdown(self) -> ProviderAvailability:
        error_code: ProviderErrorCode | None = None
        adapter = self.__adapter
        self.__adapter = None

        _LOGGER.info(
            "provider_connectivity_shutdown_started",
            extra={"provider": "KITE"},
        )

        if adapter is not None:
            try:
                adapter.close()
            except ProviderConnectivityError as error:
                error_code = error.code
                _LOGGER.error(
                    "provider_connectivity_shutdown_failed",
                    extra={"provider": "KITE", "error_code": error.code.value},
                )

        self.__state = ProviderAvailabilityState.NOT_INITIALIZED
        _LOGGER.info(
            "provider_connectivity_shutdown_completed",
            extra={"provider": "KITE", "state": self.__state.value},
        )
        return ProviderAvailability(self.__state, error_code)

    def __initialize(self) -> ProviderAvailability | None:
        try:
            self.__settings.validate_kite_connectivity()
        except ConfigurationError:
            self.__state = ProviderAvailabilityState.CONFIGURATION_INVALID
            _LOGGER.error(
                "provider_connectivity_configuration_invalid",
                extra={"provider": "KITE", "state": self.__state.value},
            )
            return ProviderAvailability(
                self.__state,
                ProviderErrorCode.CONFIGURATION_INVALID,
            )

        try:
            _LOGGER.info(
                "provider_connectivity_initialization_started",
                extra={"provider": "KITE"},
            )
            self.__adapter = self.__adapter_factory(
                self.__settings.kite_api_key,
                self.__settings.kite_access_token,
            )
        except ProviderConnectivityError as error:
            return self.__failure(error.code)

        _LOGGER.info(
            "provider_connectivity_initialized",
            extra={"provider": "KITE"},
        )
        return None

    def __failure(self, code: ProviderErrorCode) -> ProviderAvailability:
        if code is ProviderErrorCode.CONFIGURATION_INVALID:
            state = ProviderAvailabilityState.CONFIGURATION_INVALID
        elif code in {
            ProviderErrorCode.AUTHENTICATION_REJECTED,
            ProviderErrorCode.ACCESS_TOKEN_INVALID_OR_EXPIRED,
        }:
            state = ProviderAvailabilityState.AUTHENTICATION_REJECTED
        else:
            state = ProviderAvailabilityState.TEMPORARILY_UNAVAILABLE

        self.__state = state
        _LOGGER.warning(
            "provider_connectivity_probe_failed",
            extra={
                "provider": "KITE",
                "state": state.value,
                "error_code": code.value,
            },
        )
        return ProviderAvailability(state, code)
