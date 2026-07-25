"""Provider-agnostic provider contract."""

from typing import Protocol


class Provider(Protocol):
    """Base contract implemented by a provider integration."""
