from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from kronos.intraday.candles import expected_candle_boundaries, reconcile_provider_candles
from kronos.intraday.contracts import (
    IntradayInstrumentReference,
    IntradayTimeframe,
    SourceProvenance,
    create_intraday_run,
)
from kronos.intraday.persistence import (
    LocalIntradayFactualEvidenceStore,
    create_factual_evidence,
)
from kronos.market.schedule import MarketDaySchedule
from kronos.provider.contracts.market_data import HistoricalCandle


IST = ZoneInfo("Asia/Kolkata")


def _evidence(
    instrument: IntradayInstrumentReference,
    schedule: MarketDaySchedule,
    provenance: SourceProvenance,
):  # type: ignore[no-untyped-def]
    boundaries = expected_candle_boundaries(schedule, IntradayTimeframe.FIVE_MINUTES)
    observed_at = boundaries[0].end
    reconciliation = reconcile_provider_candles(
        instrument=instrument,
        timeframe=IntradayTimeframe.FIVE_MINUTES,
        schedule=schedule,
        provider_candles=(HistoricalCandle(boundaries[0].start, 100.0, 102.0, 99.0, 101.0, 1000),),
        observed_at=observed_at,
        provenance=provenance,
    )
    run = create_intraday_run(
        created_at=datetime(2026, 8, 17, 9, 15, tzinfo=IST),
        observation_boundary=observed_at,
    )
    return create_factual_evidence(run, reconciliation)


def test_evidence_is_idempotent_restart_safe_and_not_latest_based(
    tmp_path: Path,
    instrument: IntradayInstrumentReference,
    schedule: MarketDaySchedule,
    provenance: SourceProvenance,
) -> None:
    evidence = _evidence(instrument, schedule, provenance)
    store = LocalIntradayFactualEvidenceStore(tmp_path)
    store.retain(evidence)
    store.retain(evidence)

    restarted = LocalIntradayFactualEvidenceStore(tmp_path)
    loaded = restarted.load(
        run_id=evidence.run.run_id,
        mapping_identity=instrument.mapping_identity,
        timeframe=IntradayTimeframe.FIVE_MINUTES,
        evidence_id=evidence.evidence_id,
    )
    assert loaded == evidence
    assert list(tmp_path.rglob("*.json")) == [
        tmp_path
        / evidence.run.run_id
        / instrument.mapping_identity
        / IntradayTimeframe.FIVE_MINUTES.value
        / f"{evidence.evidence_id}.json"
    ]
    assert not list(tmp_path.rglob("latest*"))


def test_integrity_mismatch_fails_closed(
    tmp_path: Path,
    instrument: IntradayInstrumentReference,
    schedule: MarketDaySchedule,
    provenance: SourceProvenance,
) -> None:
    evidence = _evidence(instrument, schedule, provenance)
    store = LocalIntradayFactualEvidenceStore(tmp_path)
    store.retain(evidence)
    path = next(tmp_path.rglob("*.json"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["evidence"]["instrument"]["lot_size"] = 999
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")

    with pytest.raises(ValueError, match="INTRADAY_FACTUAL_EVIDENCE_INTEGRITY_MISMATCH"):
        store.load(
            run_id=evidence.run.run_id,
            mapping_identity=instrument.mapping_identity,
            timeframe=IntradayTimeframe.FIVE_MINUTES,
            evidence_id=evidence.evidence_id,
        )


def test_retaining_different_bytes_at_same_identity_is_rejected(
    tmp_path: Path,
    instrument: IntradayInstrumentReference,
    schedule: MarketDaySchedule,
    provenance: SourceProvenance,
) -> None:
    evidence = _evidence(instrument, schedule, provenance)
    store = LocalIntradayFactualEvidenceStore(tmp_path)
    store.retain(evidence)
    path = next(tmp_path.rglob("*.json"))
    path.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="INTRADAY_FACTUAL_EVIDENCE_IMMUTABLE"):
        store.retain(evidence)
