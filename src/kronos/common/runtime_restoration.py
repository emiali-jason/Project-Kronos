"""Pure native startup restoration predicate shared by Browser and R3 readers.

This is the existing Browser predicate, without product construction imports.
It establishes only the retained outcome tuple's existing validity rules.
"""

def _swing_restoration_failure(outcomes):
    required = {"LEGACY_MTF", "LEGACY_NATIVE", "NATIVE_REVIEW", "V3_RECORDS",
                "V3_RESTORE", "TRADE_WINDOW"}
    if (type(outcomes) is not tuple or len(outcomes) != len(required)
            or any(type(row) is not tuple or len(row) != 2 for row in outcomes)):
        return True
    result = dict(outcomes)
    return (set(result) != required
            or any(value not in ({"SUCCESS", "NOT_APPLICABLE", "APPLICABILITY_NOT_ESTABLISHED"}
                                 if key == "NATIVE_REVIEW" else {"SUCCESS", "NOT_APPLICABLE"})
                   for key, value in result.items())
            or result["V3_RECORDS"] != "SUCCESS"
            or result["TRADE_WINDOW"] != "SUCCESS")
