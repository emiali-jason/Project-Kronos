"""Provider-agnostic instrument contract."""

from typing import Protocol


class InstrumentProvider(Protocol):
    """Contract for provider instrument capabilities."""
