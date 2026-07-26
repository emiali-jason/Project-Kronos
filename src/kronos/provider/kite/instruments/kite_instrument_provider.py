"""Kite instrument provider skeleton."""

from typing import Optional

from kronos.provider.contracts.instrument import InstrumentProvider


class KiteInstrumentProvider(InstrumentProvider):
    """Kite implementation placeholder for instrument capabilities."""

    def __init__(self, dependencies: Optional[object] = None) -> None:
        self._dependencies = dependencies
