"""Proposed Intraday new-work denials; no persisted eligibility or authority."""
from enum import Enum


class NewWorkAction(str, Enum):
    READINESS_HANDOFF = "READINESS_HANDOFF"
    LIFECYCLE_PRE_ENTRY = "LIFECYCLE_PRE_ENTRY"


class EligibilityReason(str, Enum):
    FIRST_FIVE_TIME_NOT_ESTABLISHED = "FIRST_FIVE_TIME_NOT_ESTABLISHED"
    ELIGIBILITY_AUTHORITY_UNAVAILABLE = "ELIGIBILITY_AUTHORITY_UNAVAILABLE"
    SOURCE_SUPERSEDED = "SOURCE_SUPERSEDED"
    SOURCE_LINEAGE_NOT_ESTABLISHED = "SOURCE_LINEAGE_NOT_ESTABLISHED"
    HISTORICAL_SESSION = "HISTORICAL_SESSION"


class NewWorkNotEligible(ValueError):
    """Typed operational denial; never a replacement for integrity/storage errors."""

    def __init__(self, reason: EligibilityReason, *, action: NewWorkAction):
        if type(reason) is not EligibilityReason or type(action) is not NewWorkAction:
            raise TypeError("INTRADAY_ELIGIBILITY_DENIAL_INVALID")
        self.reason, self.action = reason, action
        super().__init__(("WO11_NEW_WORK_" if action is NewWorkAction.LIFECYCLE_PRE_ENTRY else "") + reason.value)


def require_original_first_five():
    """Branch B: there is no commissioned original-event verifier in this base.

    Deliberately accepts no timestamp, readiness date or caller proof object.
    Future producer commissioning requires a separate exact verification contract.
    Historical serializers/builders are unchanged.
    """
    raise NewWorkNotEligible(EligibilityReason.FIRST_FIVE_TIME_NOT_ESTABLISHED,
                             action=NewWorkAction.READINESS_HANDOFF)
