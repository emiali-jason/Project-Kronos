"""Source-owned default Intraday evidence location; no application imports."""
from pathlib import Path

DEFAULT_INTRADAY_EVIDENCE_ROOT = (
    Path.home() / "Library" / "Application Support" / "KRONOS" / "evidence" / "intraday-v1"
)
