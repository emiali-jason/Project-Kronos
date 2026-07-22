from enum import StrEnum


class ProviderErrorCode(StrEnum):
    """Stable, redacted Provider-owned technical error categories."""

    CONFIGURATION_INVALID = "CONFIGURATION_INVALID"
    AUTHENTICATION_REJECTED = "AUTHENTICATION_REJECTED"
    ACCESS_TOKEN_INVALID_OR_EXPIRED = "ACCESS_TOKEN_INVALID_OR_EXPIRED"
    NETWORK_TIMEOUT = "NETWORK_TIMEOUT"
    CONNECTION_FAILURE = "CONNECTION_FAILURE"
    RATE_LIMITED = "RATE_LIMITED"
    PROVIDER_SERVICE_FAILURE = "PROVIDER_SERVICE_FAILURE"
    UNEXPECTED_RESPONSE = "UNEXPECTED_RESPONSE"
    INTERNAL_ADAPTER_DEFECT = "INTERNAL_ADAPTER_DEFECT"
    SHUTDOWN_FAILURE = "SHUTDOWN_FAILURE"


class ProviderConnectivityError(RuntimeError):
    """A redacted Provider error that never includes SDK exception text."""

    def __init__(self, code: ProviderErrorCode) -> None:
        self.code = code
        super().__init__(f"Provider connectivity failed: {code.value}")
