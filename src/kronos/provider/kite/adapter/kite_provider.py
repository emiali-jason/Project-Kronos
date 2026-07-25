"""Kite provider skeleton."""

from typing import Optional

from kronos.provider.contracts import Provider


class KiteProvider(Provider):
    """Kite implementation placeholder for the base provider contract."""

    def __init__(self, dependencies: Optional[object] = None) -> None:
        self._dependencies = dependencies
