"""Build one family-wide MCX expiry-continuity artifact without Provider access."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

from kronos.instrument.semantic_v2_persistence import InstrumentSemanticV2Store
from kronos.intraday.mcx_continuous_research_persistence import McxContinuousResearchStore
from kronos.intraday.mcx_expiry_continuity_research import (
    build_mcx_family_expiry_continuity_artifact,
    mcx_expiry_continuity_bytes,
)
from kronos.intraday.mcx_expiry_continuity_research_persistence import McxExpiryContinuityStore
from kronos.intraday.mcx_historical_research_persistence import McxHistoricalResearchCorpusStore


SOURCE_CORPUS_IDENTITY = (
    "INTRADAY-MCX-HISTORICAL-CORPUS-"
    "8F914F89E6409A4F1A7F6EBE1FA0B09E7950DE3716EE5C657D27A817E7486233"
)
SOURCE_CONTINUOUS_IDENTITY = (
    "INTRADAY-MCX-CONTINUOUS-RESEARCH-"
    "9D9603E2E00EF693A58898215F9C24CB9FEC0C1B01DF63D1984274A5C4D2F125"
)


def main() -> None:
    source = McxHistoricalResearchCorpusStore().load(corpus_identity=SOURCE_CORPUS_IDENTITY)
    continuous = McxContinuousResearchStore().load(artifact_identity=SOURCE_CONTINUOUS_IDENTITY)
    catalogue = InstrumentSemanticV2Store(Path("data/instruments").resolve()).load(
        publication_identity="KRONOS-CANONICAL-INSTRUMENT-CATALOGUE-V2",
        publication_version="1.2.0",
    )
    artifact = build_mcx_family_expiry_continuity_artifact(
        source_corpus=source,
        continuous_artifact=continuous,
        catalogue=catalogue,
        created_at=datetime.now(UTC),
    )
    store = McxExpiryContinuityStore()
    path = store.retain(artifact)
    reloaded = store.load(artifact_identity=artifact.artifact_identity)
    if reloaded != artifact or mcx_expiry_continuity_bytes(reloaded) != mcx_expiry_continuity_bytes(artifact):
        raise RuntimeError("MCX_EXPIRY_CONTINUITY_RELOAD_MISMATCH")
    print(json.dumps({
        "artifact_identity": artifact.artifact_identity,
        "integrity_identity": artifact.integrity_identity,
        "path": str(path),
        "provider_requests": artifact.provider_request_count,
        "synthetic_market_candles": artifact.synthetic_market_candle_count,
        "production_state_modified": artifact.production_state_modified,
        "reload_equal": True,
        "mcx_family_expiry_continuity": artifact.mcx_family_expiry_continuity.value,
        "mcx_historical_analysis_survives_contract_expiry": artifact.mcx_historical_analysis_survives_contract_expiry,
        "manual_expiry_intervention_required": artifact.manual_expiry_intervention_required,
        "current_instrument_master_dependency_for_old_history": artifact.current_instrument_master_dependency_for_old_history,
        "scenarios": {
            item.analytical_subject: {
                "outcome": item.outcome.value,
                "contract_a": item.contract_a_identity,
                "contract_a_expiry": item.contract_a_expiry.isoformat(),
                "retained_candles": item.contract_a_candle_count,
                "successor_b": item.successor_contract_b_identity,
                "successor_b_expiry": item.successor_contract_b_expiry.isoformat(),
                "contract_a_absent": item.contract_a_absent_from_simulated_current_master,
                "replay_exact": item.replay_exact,
                "fabricated_market_candles": item.fabricated_market_candle_count,
            }
            for item in artifact.scenarios
        },
        "legacy_observed_roll_gaps": [
            {
                "subject": item.canonical_subject_identity,
                "expired_contract": item.expired_contract_identity,
                "successor_contract": item.successor_contract_identity,
                "disposition": item.disposition,
            }
            for item in artifact.legacy_observed_roll_gaps
        ],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
