"""WO-16 factual history policy; WO-12 remains research authority."""
from hashlib import sha256
import json

POLICY_IDENTITY = "KRONOS-INTRADAY-WO16-REPORTS-POLICY"
POLICY_VERSION = "1.0.0"
RULES = {
    "authority": "CANONICAL_WO10_DECISIONS_AND_WO11_LIFECYCLE_FACTS",
    "research": "WO12_ONLY_NO_RECALCULATION",
    "truth": ["PAPER_POSITION", "PAPER_OBSERVATION", "NONE", "DO_NOTHING"],
    "live": "LIVE_POSITION_NOT_COMMISSIONED_V1",
    "presentation_deletion": "NO_EFFECT_ON_HISTORY",
    "exports": "SHARED_FILTERED_FACTUAL_XLSX_CSV_JSON",
    "workbook": "NOT_WO12_CANONICAL_PUBLICATION",
}
POLICY_CHECKSUM = sha256(json.dumps(RULES, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
