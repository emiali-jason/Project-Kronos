"""Build one MCX continuous qualification artifact without Provider access."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
import json

from kronos.intraday.mcx_continuous_research import (
    build_mcx_continuous_research_artifact,
    mcx_continuous_research_bytes,
)
from kronos.intraday.mcx_continuous_research_persistence import (
    McxContinuousResearchStore,
)
from kronos.intraday.mcx_historical_research_persistence import (
    McxHistoricalResearchCorpusStore,
)
from kronos.market.calendar import MarketCalendarPublisher


SOURCE_CORPUS_IDENTITY = (
    "INTRADAY-MCX-HISTORICAL-CORPUS-"
    "8F914F89E6409A4F1A7F6EBE1FA0B09E7950DE3716EE5C657D27A817E7486233"
)


def main() -> None:
    source = McxHistoricalResearchCorpusStore().load(
        corpus_identity=SOURCE_CORPUS_IDENTITY
    )
    artifact = build_mcx_continuous_research_artifact(
        source_corpus=source,
        created_at=datetime.now(UTC),
        calendar_publisher=MarketCalendarPublisher(),
    )
    store = McxContinuousResearchStore()
    path = store.retain(artifact)
    reloaded = store.load(artifact_identity=artifact.artifact_identity)
    if (
        reloaded != artifact
        or mcx_continuous_research_bytes(reloaded)
        != mcx_continuous_research_bytes(artifact)
    ):
        raise RuntimeError("MCX_CONTINUOUS_RELOAD_MISMATCH")
    output = {
        "artifact_identity": artifact.artifact_identity,
        "integrity_identity": artifact.integrity_identity,
        "path": str(path),
        "provider_requests": artifact.provider_request_count,
        "reload_equal": True,
        "subjects": {
            item.analytical_subject: {
                "quality": item.quality.value,
                "source_contracts": len(item.represented_contract_identities),
                "roll_boundaries": len(item.roll_boundaries),
                "candle_counts": {
                    key.value: value
                    for key, value in item.counts_by_timeframe.items()
                },
                "missing_dates": tuple(value.isoformat() for value in item.missing_trading_dates),
                "contract_attribution_exclusions": item.contract_attribution_exclusion_count,
            }
            for item in artifact.series
        },
        "qualifications": {
            item.analytical_subject: {
                "outcome": item.outcome.value,
                "commissioning_recommended": item.commissioning_recommended,
                "phase_assessments": item.phase_assessment_count,
                "result_accounting": dict(item.result_accounting),
                "conflicts": item.conflict_assessment_count,
                "state_transitions": item.state_transition_count,
            }
            for item in artifact.qualifications
        },
        "phase_totals": dict(Counter(
            item.phase.value for item in artifact.assessments
        )),
    }
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
