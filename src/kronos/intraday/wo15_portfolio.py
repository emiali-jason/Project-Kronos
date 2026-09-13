"""WO-15 current exposure policy. No lifecycle or monitoring ownership."""
from hashlib import sha256
import json

POLICY_IDENTITY = "KRONOS-INTRADAY-WO15-PORTFOLIO-POLICY"
POLICY_VERSION = "1.0.0"
RULES = {
    "exposure": "WO11_ENTERED_NONTERMINAL_PAPER_POSITION",
    "lots": 1,
    "observation": "NON_EXPOSURE",
    "live": "LIVE_POSITION_NOT_COMMISSIONED_V1",
    "identity": "CONSUME_RETAINED_OPPORTUNITY_ORIGIN",
    "price": "LATEST_PROCESS_LOCAL_WO11_ELIGIBLE_OBSERVATION_WITH_TIMESTAMP",
    "monitoring": "EXACT_WO11_OWNER_AND_SHARED_TRANSPORT",
    "delete": "NOT_SUPPORTED",
    "exit": "NO_EXISTING_SHARED_PORTFOLIO_CONTROL",
}
POLICY_CHECKSUM = sha256(json.dumps(RULES, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def is_exposure(data):
    return (data["truth_class"] == "PAPER_POSITION" and data["entry"] is not None
            and not data["terminal"] and data["model_lots"] == 1)
