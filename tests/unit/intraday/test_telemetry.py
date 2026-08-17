from __future__ import annotations

from dataclasses import fields
from decimal import Decimal
import json

import pytest

from kronos.intraday.candles import reconcile_provider_candles
from kronos.intraday.contracts import DataAvailability
from kronos.intraday.structure import build_structural_evidence
from kronos.intraday.telemetry import (
    ExplicitTelemetryReferences,
    FactualComparison,
    ShadowTelemetryEvidence,
    TelemetryType,
    build_shadow_telemetry,
)
from kronos.intraday.telemetry_persistence import LocalShadowTelemetryStore
from kronos.provider.contracts.market_data import HistoricalCandle
from tests.unit.intraday.test_structure import _authority


def _measure(evidence: ShadowTelemetryEvidence, kind: TelemetryType, role: str | None = None):
    matches = tuple(item for item in evidence.measures if item.telemetry_type is kind)
    if role is None:
        return matches[0]
    return next(
        item for item in matches
        if any(value.name == "reference_role" and value.value == role for value in item.attributes)
    )


def _values(measure):  # type: ignore[no-untyped-def]
    return {item.name: item.value for item in measure.values}


def test_volume_and_explicit_reference_telemetry_are_exact_factual_measurements(
    instrument, schedule, provenance  # type: ignore[no-untyped-def]
) -> None:
    run, reconciliation = _authority(instrument, schedule, provenance)
    evidence = build_shadow_telemetry(
        run=run,
        reconciliation=reconciliation,
        references=ExplicitTelemetryReferences(
            selected_reference=Decimal("104"), selected_reference_identity="SELECTED:R1",
            breakout_boundary=Decimal("103"), breakout_boundary_identity="BREAKOUT:R1",
            impulse_origin=Decimal("100"), impulse_origin_identity="IMPULSE:CANDLE-1",
            pullback_reference=Decimal("105"), pullback_reference_identity="PULLBACK:CANDLE-7",
            next_barrier=Decimal("112"), next_barrier_identity="BARRIER:R2",
            structural_reward_reference=Decimal("112"),
            structural_reward_reference_identity="BARRIER:R2",
            structural_risk_reference=Decimal("102"),
            structural_risk_reference_identity="REFERENCE:RISK",
        ),
    )

    current = _measure(evidence, TelemetryType.VOLUME_OBSERVATION)
    recent = _measure(evidence, TelemetryType.RECENT_VOLUME_COMPARISON)
    session = _measure(evidence, TelemetryType.SESSION_VOLUME_COMPARISON)
    assert _values(current)["current_volume"] == Decimal("10008")
    assert _values(recent)["comparison_mean"] == Decimal("10005")
    assert tuple(
        _values(recent)[f"comparison_volume_{index:03d}"] for index in range(1, 6)
    ) == tuple(Decimal(value) for value in (10003, 10004, 10005, 10006, 10007))
    assert _values(recent)["volume_ratio"] == Decimal("10008") / Decimal("10005")
    assert recent.comparison is FactualComparison.EXPANSION
    assert _values(session)["comparison_candle_count"] == Decimal("8")
    distance = _measure(evidence, TelemetryType.REFERENCE_DISTANCE, "SELECTED_REFERENCE")
    assert _values(distance)["signed_distance"] == Decimal("0")
    reward_risk = _measure(evidence, TelemetryType.STRUCTURAL_REWARD_RISK_MEASUREMENT)
    assert _values(reward_risk)["structural_reward"] == Decimal("8")
    assert _values(reward_risk)["structural_risk"] == Decimal("2")
    assert _values(reward_risk)["structural_reward_risk_ratio"] == Decimal("4")
    incomplete = reconciliation.observations[-1]
    assert incomplete.candle_id not in evidence.governed_candle_ids
    assert all(incomplete.candle_id not in item.source_candle_ids for item in evidence.measures)


def test_absent_explicit_references_and_insufficient_history_are_unavailable(
    instrument, schedule, provenance  # type: ignore[no-untyped-def]
) -> None:
    run, reconciliation = _authority(instrument, schedule, provenance)
    evidence = build_shadow_telemetry(run=run, reconciliation=reconciliation)

    assert all(
        item.availability is DataAvailability.UNAVAILABLE
        for item in evidence.measures
        if item.telemetry_type in {
            TelemetryType.REFERENCE_DISTANCE,
            TelemetryType.STRUCTURAL_REWARD_RISK_MEASUREMENT,
        }
    )
    assert not hasattr(evidence, "volatility_measure")


def test_shadow_telemetry_is_append_only_restart_safe_and_tamper_evident(
    tmp_path, instrument, schedule, provenance  # type: ignore[no-untyped-def]
) -> None:
    run, reconciliation = _authority(instrument, schedule, provenance)
    evidence = build_shadow_telemetry(run=run, reconciliation=reconciliation)
    store = LocalShadowTelemetryStore(tmp_path / "telemetry")
    store.retain(evidence)
    store.retain(evidence)

    loaded = LocalShadowTelemetryStore(store.root).load(
        run_id=run.run_id,
        mapping_identity=instrument.mapping_identity,
        trading_date=evidence.trading_date.isoformat(),
        timeframe=evidence.timeframe,
        evidence_id=evidence.evidence_id,
    )
    assert loaded == evidence
    path = next(store.root.rglob("*.json"))
    document = json.loads(path.read_bytes())
    document["evidence"]["measures"][0]["measure"]["values"][0]["value"] = "999999"
    path.write_text(json.dumps(document, indent=2, sort_keys=True))
    with pytest.raises(ValueError, match="UNAVAILABLE_OR_INVALID"):
        store.load(
            run_id=run.run_id,
            mapping_identity=instrument.mapping_identity,
            trading_date=evidence.trading_date.isoformat(),
            timeframe=evidence.timeframe,
            evidence_id=evidence.evidence_id,
        )


def test_shadow_changes_have_no_downstream_contract_or_structural_side_effect(
    instrument, schedule, provenance  # type: ignore[no-untyped-def]
) -> None:
    run, reconciliation = _authority(instrument, schedule, provenance)
    first = build_shadow_telemetry(run=run, reconciliation=reconciliation)
    changed = build_shadow_telemetry(
        run=run,
        reconciliation=reconciliation,
        references=ExplicitTelemetryReferences(
            selected_reference=Decimal("80"), selected_reference_identity="CHANGED:REFERENCE",
            structural_reward_reference=Decimal("150"),
            structural_reward_reference_identity="CHANGED:REWARD",
            structural_risk_reference=Decimal("90"),
            structural_risk_reference_identity="CHANGED:RISK",
        ),
    )
    contract_fields = {item.name for item in fields(ShadowTelemetryEvidence)}
    prohibited = {
        "candidate_state", "probable", "discovery", "readiness", "entry", "stop",
        "invalidation", "target", "risk_decision", "paper_eligibility", "live_eligibility",
    }

    assert contract_fields.isdisjoint(prohibited)
    assert first.evidence_id != changed.evidence_id

    changed_provider_candles = tuple(
        HistoricalCandle(
            item.boundary.start,
            float(item.open), float(item.high), float(item.low), float(item.close),
            item.volume + (1_000 if item is reconciliation.structural_candles[-1] else 0),
        )
        for item in reconciliation.observations
    )
    changed_reconciliation = reconcile_provider_candles(
        instrument=instrument,
        timeframe=reconciliation.timeframe,
        schedule=schedule,
        provider_candles=changed_provider_candles,
        observed_at=reconciliation.observation_boundary.observed_at,
        provenance=provenance,
    )
    changed_volume = build_shadow_telemetry(
        run=run, reconciliation=changed_reconciliation
    )
    original_structure = build_structural_evidence(
        run=run, reconciliation=reconciliation
    )
    changed_structure = build_structural_evidence(
        run=run, reconciliation=changed_reconciliation
    )
    semantic_facts = lambda evidence: tuple(  # noqa: E731
        (item.fact_type, item.direction, item.values, item.attributes)
        for item in evidence.facts
    )

    assert _values(_measure(first, TelemetryType.VOLUME_OBSERVATION)) != _values(
        _measure(changed_volume, TelemetryType.VOLUME_OBSERVATION)
    )
    assert semantic_facts(original_structure) == semantic_facts(changed_structure)
