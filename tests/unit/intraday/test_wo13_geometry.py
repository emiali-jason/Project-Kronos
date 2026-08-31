from __future__ import annotations

from dataclasses import fields, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import inspect

import pytest

from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo13 import (
    Wo13FieldAvailability,
    Wo13GeometryAvailability,
    Wo13GeometryField,
    Wo13WarningCode,
)
from kronos.intraday.wo13_geometry import (
    WO13_GEOMETRY_CALCULATION_IDENTITY,
    WO13_INVALIDATION_EVENT_IDENTITY,
    WO13_RANGE_WIDTH_IDENTITY,
    WO13_STRUCTURAL_PRICE_FACT_IDENTITY,
    WO13_TARGET_CANDIDATE_IDENTITY,
    Wo13ForwardTargetState,
    Wo13GeometryFailure,
    Wo13GeometryRejected,
    Wo13PriceAuthority,
    Wo13StructuralPriceFact,
    Wo13StructuralRole,
    Wo13TargetCandidateKind,
    calculate_wo13_geometry,
    calculate_wo13_range_width,
    create_wo13_structural_price_fact,
    create_wo13_target_candidate,
    create_wo13_thesis_invalidation_event,
    resolve_wo13_structural_price_field,
)


_NOW = datetime(2026, 8, 31, 10, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))


def _fact(
    price: object,
    role: Wo13StructuralRole,
    *,
    subject: str = "NSE-EQ-RELIANCE",
    family: IntradayMarketFamily = IntradayMarketFamily.NSE_EQUITY,
    authority: Wo13PriceAuthority = Wo13PriceAuthority.NSE_EQUITY_UNDERLYING,
    timeframe: IntradayTimeframe = IntradayTimeframe.FIFTEEN_MINUTES,
    boundary: datetime = _NOW,
    instrument: str = "INSTRUMENT:NSE:RELIANCE",
    structure: str = "STRUCTURE:RELIANCE:15M:1",
    source: str | None = None,
    source_integrity: str | None = None,
    session: str | None = "NSE-SESSION-2026-08-31",
    actual_contract: str | None = None,
    roll_lineage: str | None = None,
) -> Wo13StructuralPriceFact:
    marker = str(price).replace("-", "M").replace(".", "_")
    source = source or f"SOURCE:{role.value}:{marker}"
    source_integrity = source_integrity or f"INTEGRITY:{role.value}:{marker}"
    return create_wo13_structural_price_fact(
        canonical_subject_identity=subject,
        market_family=family,
        timeframe=timeframe,
        price=price,
        structural_role=role,
        price_authority=authority,
        structure_identity=structure,
        source_evidence_identity=source,
        source_evidence_integrity=source_integrity,
        analysis_boundary=boundary,
        instrument_identity=instrument,
        actual_contract_identity=actual_contract,
        roll_lineage_identity=roll_lineage,
        market_session_identity=session,
    )


def _field(
    field: Wo13GeometryField,
    fact: Wo13StructuralPriceFact | None = None,
):
    return resolve_wo13_structural_price_field(
        field,
        facts=() if fact is None else (fact,),
    )


def _calculation(
    direction: SemanticDirection,
    *,
    entry: object,
    stop: object,
    target: object | None,
    include_event: bool = True,
):
    entry_fact = _fact(entry, Wo13StructuralRole.ENTRY_REFERENCE_SOURCE)
    stop_fact = _fact(stop, Wo13StructuralRole.STOP_REFERENCE_SOURCE)
    invalidation_fact = _fact(
        stop,
        Wo13StructuralRole.THESIS_INVALIDATION_REFERENCE,
    )
    target_fact = (
        None
        if target is None
        else _fact(target, Wo13StructuralRole.SETUP_NATIVE_TARGET)
    )
    event = (
        create_wo13_thesis_invalidation_event(
            reference=invalidation_fact,
            event_code="COMPLETED_15M_STRUCTURAL_FAILURE",
            source_evidence_identity="SOURCE:INVALIDATION:EVENT",
            source_evidence_integrity="INTEGRITY:INVALIDATION:EVENT",
        )
        if include_event
        else None
    )
    result = calculate_wo13_geometry(
        direction=direction,
        entry_reference=_field(Wo13GeometryField.ENTRY_REFERENCE, entry_fact),
        stop=_field(Wo13GeometryField.STOP, stop_fact),
        thesis_invalidation_reference=_field(
            Wo13GeometryField.THESIS_INVALIDATION_REFERENCE,
            invalidation_fact,
        ),
        thesis_invalidation_event=event,
        target=_field(Wo13GeometryField.CANONICAL_TARGET, target_fact),
    )
    return result, entry_fact, stop_fact, invalidation_fact, target_fact, event


def _mcx_fact(
    price: object,
    role: Wo13StructuralRole,
    *,
    contract: str = "MCX-CONTRACT-CRUDE-202609",
    roll: str = "MCX-ROLL-CRUDE-V1",
    structure: str = "STRUCTURE:CRUDE:15M:1",
) -> Wo13StructuralPriceFact:
    return _fact(
        price,
        role,
        subject="MCX-SUBJECT-CRUDE",
        family=IntradayMarketFamily.MCX,
        authority=Wo13PriceAuthority.MCX_ACTIVE_CONTRACT,
        instrument="INSTRUMENT:MCX:CRUDEOIL26SEPFUT",
        actual_contract=contract,
        roll_lineage=roll,
        structure=structure,
        session="MCX-SESSION-2026-08-31",
    )


def test_contract_identities_roles_and_exact_decimal_preservation() -> None:
    fact = _fact("100.037", Wo13StructuralRole.ENTRY_REFERENCE_SOURCE)

    assert fact.schema_identity == WO13_STRUCTURAL_PRICE_FACT_IDENTITY
    assert fact.price == Decimal("100.037")
    assert tuple(item.value for item in Wo13StructuralRole) == (
        "ENTRY_REFERENCE_SOURCE",
        "STOP_REFERENCE_SOURCE",
        "THESIS_INVALIDATION_REFERENCE",
        "SETUP_NATIVE_TARGET",
        "TARGET_CONSTRAINT",
        "RANGE_HIGH",
        "RANGE_LOW",
        "QUALIFICATION_CANDLE_HIGH",
        "QUALIFICATION_CANDLE_LOW",
        "PULLBACK_STRUCTURAL_HIGH",
        "PULLBACK_STRUCTURAL_LOW",
        "PRIOR_IMPULSE_HIGH",
        "PRIOR_IMPULSE_LOW",
        "SESSION_STRUCTURAL_HIGH",
        "SESSION_STRUCTURAL_LOW",
        "PDH",
        "PDL",
        "PIVOT_RESISTANCE",
        "PIVOT_SUPPORT",
        "GOVERNED_STRUCTURAL_BARRIER",
    )


def test_long_complete_geometry_and_model_rr_are_exact() -> None:
    result, entry, stop, invalidation, target, event = _calculation(
        SemanticDirection.LONG,
        entry="100",
        stop="98",
        target="106",
    )

    assert result.schema_identity == WO13_GEOMETRY_CALCULATION_IDENTITY
    assert (result.risk_distance, result.reward_distance, result.model_rr) == (
        Decimal("2"),
        Decimal("6"),
        Decimal("3"),
    )
    assert result.geometry_availability is Wo13GeometryAvailability.GEOMETRY_COMPLETE
    assert result.warnings == ()
    assert result.tick_normalization_applied is False
    assert stop is not invalidation
    assert stop.price == invalidation.price
    assert event is not None
    assert event.schema_identity == WO13_INVALIDATION_EVENT_IDENTITY
    assert entry.price == Decimal("100") and target is not None and target.price == Decimal("106")


def test_short_complete_geometry_and_model_rr_are_exact() -> None:
    result, *_ = _calculation(
        SemanticDirection.SHORT,
        entry="100",
        stop="103",
        target="94",
    )

    assert (result.risk_distance, result.reward_distance, result.model_rr) == (
        Decimal("3"),
        Decimal("6"),
        Decimal("2"),
    )
    assert result.geometry_availability is Wo13GeometryAvailability.GEOMETRY_COMPLETE


@pytest.mark.parametrize(
    ("direction", "entry", "stop"),
    (
        (SemanticDirection.LONG, "100", "100"),
        (SemanticDirection.LONG, "100", "101"),
        (SemanticDirection.SHORT, "100", "100"),
        (SemanticDirection.SHORT, "100", "99"),
    ),
)
def test_non_positive_risk_is_unavailable_and_never_repaired(
    direction: SemanticDirection,
    entry: str,
    stop: str,
) -> None:
    result, entry_fact, stop_fact, *_ = _calculation(
        direction,
        entry=entry,
        stop=stop,
        target="106" if direction is SemanticDirection.LONG else "94",
    )

    assert result.risk_distance is None
    assert result.model_rr is None
    assert result.geometry_availability is Wo13GeometryAvailability.GEOMETRY_PARTIAL
    assert result.warnings == (
        Wo13WarningCode.NON_POSITIVE_RISK,
        Wo13WarningCode.INVALID_DIRECTIONAL_GEOMETRY,
    )
    assert entry_fact.price == Decimal(entry)
    assert stop_fact.price == Decimal(stop)


@pytest.mark.parametrize(
    ("direction", "entry", "target"),
    (
        (SemanticDirection.LONG, "100", "100"),
        (SemanticDirection.LONG, "100", "99"),
        (SemanticDirection.SHORT, "100", "100"),
        (SemanticDirection.SHORT, "100", "101"),
    ),
)
def test_non_positive_reward_is_unavailable_and_target_does_not_move(
    direction: SemanticDirection,
    entry: str,
    target: str,
) -> None:
    result, _, _, _, target_fact, _ = _calculation(
        direction,
        entry=entry,
        stop="98" if direction is SemanticDirection.LONG else "103",
        target=target,
    )

    assert result.reward_distance is None
    assert result.model_rr is None
    assert result.warnings == (
        Wo13WarningCode.NON_POSITIVE_REWARD,
        Wo13WarningCode.INVALID_DIRECTIONAL_GEOMETRY,
    )
    assert target_fact is not None and target_fact.price == Decimal(target)


@pytest.mark.parametrize("value", (Decimal("NaN"), Decimal("Infinity"), "bad"))
def test_non_finite_or_corrupt_price_fails_closed(value: object) -> None:
    with pytest.raises(Wo13GeometryRejected) as captured:
        _fact(value, Wo13StructuralRole.ENTRY_REFERENCE_SOURCE)
    expected = (
        Wo13GeometryFailure.NON_FINITE_VALUE
        if value != "bad"
        else Wo13GeometryFailure.PRICE_VALUE_INVALID
    )
    assert captured.value.failure is expected


def test_partial_and_unavailable_geometry_preserve_independent_fields() -> None:
    partial, *_ = _calculation(
        SemanticDirection.LONG,
        entry="100",
        stop="98",
        target=None,
    )
    empty = resolve_wo13_structural_price_field
    unavailable = calculate_wo13_geometry(
        direction=SemanticDirection.LONG,
        entry_reference=empty(Wo13GeometryField.ENTRY_REFERENCE),
        stop=empty(Wo13GeometryField.STOP),
        thesis_invalidation_reference=empty(
            Wo13GeometryField.THESIS_INVALIDATION_REFERENCE
        ),
        thesis_invalidation_event=None,
        target=empty(Wo13GeometryField.CANONICAL_TARGET),
    )

    assert partial.risk_distance == Decimal("2")
    assert partial.reward_distance is partial.model_rr is None
    assert partial.geometry_availability is Wo13GeometryAvailability.GEOMETRY_PARTIAL
    assert unavailable.risk_distance is unavailable.reward_distance is None
    assert unavailable.model_rr is None
    assert unavailable.geometry_availability is Wo13GeometryAvailability.GEOMETRY_UNAVAILABLE
    assert all(
        item.availability is Wo13FieldAvailability.UNAVAILABLE
        for item in unavailable.field_availability
    )


def test_risk_and_reward_measurement_identities_are_field_independent() -> None:
    baseline, *_ = _calculation(
        SemanticDirection.LONG,
        entry="100",
        stop="98",
        target="106",
    )
    changed_target, *_ = _calculation(
        SemanticDirection.LONG,
        entry="100",
        stop="98",
        target="110",
    )
    changed_stop, *_ = _calculation(
        SemanticDirection.LONG,
        entry="100",
        stop="97",
        target="106",
    )
    missing_target, *_ = _calculation(
        SemanticDirection.LONG,
        entry="100",
        stop="98",
        target=None,
    )

    assert baseline.risk_measurement.measurement_identity == (
        changed_target.risk_measurement.measurement_identity
    )
    assert baseline.risk_measurement.measurement_identity == (
        missing_target.risk_measurement.measurement_identity
    )
    assert baseline.reward_measurement.measurement_identity == (
        changed_stop.reward_measurement.measurement_identity
    )
    assert baseline.reward_measurement.measurement_identity != (
        changed_target.reward_measurement.measurement_identity
    )
    assert baseline.risk_measurement.measurement_identity != (
        changed_stop.risk_measurement.measurement_identity
    )
    assert missing_target.reward_measurement.value is None
    assert missing_target.model_rr_measurement.value is None


def test_field_availability_is_derived_as_available_incomplete_and_ambiguous() -> None:
    first = _fact("100", Wo13StructuralRole.ENTRY_REFERENCE_SOURCE)
    second = _fact(
        "101",
        Wo13StructuralRole.ENTRY_REFERENCE_SOURCE,
        source="SOURCE:ENTRY:SECOND",
        source_integrity="INTEGRITY:ENTRY:SECOND",
    )
    available = resolve_wo13_structural_price_field(
        Wo13GeometryField.ENTRY_REFERENCE,
        facts=(first,),
    )
    incomplete = resolve_wo13_structural_price_field(
        Wo13GeometryField.ENTRY_REFERENCE,
        expected_sources=(("SOURCE:EXPECTED", "INTEGRITY:EXPECTED"),),
    )
    ambiguous = resolve_wo13_structural_price_field(
        Wo13GeometryField.ENTRY_REFERENCE,
        facts=(first, second),
    )

    assert available.availability is Wo13FieldAvailability.AVAILABLE
    assert incomplete.availability is Wo13FieldAvailability.INCOMPLETE
    assert ambiguous.availability is Wo13FieldAvailability.AMBIGUOUS
    assert available.selected_fact is first
    assert incomplete.selected_fact is ambiguous.selected_fact is None


@pytest.mark.parametrize(
    ("direction", "prices", "states", "distances"),
    (
        (
            SemanticDirection.LONG,
            ("95", "100", "105", "110"),
            (
                Wo13ForwardTargetState.BEHIND_ENTRY,
                Wo13ForwardTargetState.AT_ENTRY,
                Wo13ForwardTargetState.FORWARD,
                Wo13ForwardTargetState.FORWARD,
            ),
            (None, None, Decimal("5"), Decimal("10")),
        ),
        (
            SemanticDirection.SHORT,
            ("105", "100", "95", "90"),
            (
                Wo13ForwardTargetState.BEHIND_ENTRY,
                Wo13ForwardTargetState.AT_ENTRY,
                Wo13ForwardTargetState.FORWARD,
                Wo13ForwardTargetState.FORWARD,
            ),
            (None, None, Decimal("5"), Decimal("10")),
        ),
    ),
)
def test_forward_target_state_and_distance_are_factual_without_selection(
    direction: SemanticDirection,
    prices: tuple[str, ...],
    states: tuple[Wo13ForwardTargetState, ...],
    distances: tuple[Decimal | None, ...],
) -> None:
    entry = _fact("100", Wo13StructuralRole.ENTRY_REFERENCE_SOURCE)
    candidates = tuple(
        create_wo13_target_candidate(
            entry_reference=entry,
            candidate=_fact(price, Wo13StructuralRole.SETUP_NATIVE_TARGET),
            direction=direction,
            kind=Wo13TargetCandidateKind.SETUP_NATIVE_OBJECTIVE,
        )
        for price in prices
    )

    assert all(item.schema_identity == WO13_TARGET_CANDIDATE_IDENTITY for item in candidates)
    assert tuple(item.forward_state for item in candidates) == states
    assert tuple(item.directional_distance for item in candidates) == distances
    assert not any(name.startswith("select") for name in dir(__import__(
        "kronos.intraday.wo13_geometry",
        fromlist=["*"],
    )))


def test_setup_native_and_constraint_status_are_not_interchangeable() -> None:
    entry = _fact("100", Wo13StructuralRole.ENTRY_REFERENCE_SOURCE)
    pdh = _fact(
        "105",
        Wo13StructuralRole.PDH,
        timeframe=IntradayTimeframe.DAILY,
        session="NSE-SESSION-2026-08-28",
    )
    constraint = create_wo13_target_candidate(
        entry_reference=entry,
        candidate=pdh,
        direction=SemanticDirection.LONG,
        kind=Wo13TargetCandidateKind.STRUCTURAL_CONSTRAINT,
    )

    assert constraint.kind is Wo13TargetCandidateKind.STRUCTURAL_CONSTRAINT
    with pytest.raises(Wo13GeometryRejected):
        create_wo13_target_candidate(
            entry_reference=entry,
            candidate=pdh,
            direction=SemanticDirection.LONG,
            kind=Wo13TargetCandidateKind.SETUP_NATIVE_OBJECTIVE,
        )


def test_range_width_is_exact_and_rejects_bad_order_or_lineage() -> None:
    high = _fact("110", Wo13StructuralRole.RANGE_HIGH, structure="RANGE:1")
    low = _fact("100", Wo13StructuralRole.RANGE_LOW, structure="RANGE:1")
    width = calculate_wo13_range_width(high, low)

    assert width.schema_identity == WO13_RANGE_WIDTH_IDENTITY
    assert width.range_width == Decimal("10")
    with pytest.raises(Wo13GeometryRejected) as equal:
        calculate_wo13_range_width(
            _fact("100", Wo13StructuralRole.RANGE_HIGH, structure="RANGE:1"),
            low,
        )
    assert equal.value.failure is Wo13GeometryFailure.RANGE_WIDTH_NON_POSITIVE
    with pytest.raises(Wo13GeometryRejected) as reversed_range:
        calculate_wo13_range_width(
            _fact("99", Wo13StructuralRole.RANGE_HIGH, structure="RANGE:1"),
            low,
        )
    assert reversed_range.value.failure is Wo13GeometryFailure.RANGE_WIDTH_NON_POSITIVE
    with pytest.raises(Wo13GeometryRejected) as foreign:
        calculate_wo13_range_width(
            high,
            _fact("100", Wo13StructuralRole.RANGE_LOW, structure="RANGE:2"),
        )
    assert foreign.value.failure is Wo13GeometryFailure.RANGE_IDENTITY_MISMATCH


@pytest.mark.parametrize(
    "authority",
    (
        Wo13PriceAuthority.SMA_CONTEXT,
        Wo13PriceAuthority.COMEX_REFERENCE,
        Wo13PriceAuthority.NYMEX_REFERENCE,
        Wo13PriceAuthority.USDINR_REFERENCE,
    ),
)
def test_sma_and_mcx_reference_authorities_cannot_create_geometry(
    authority: Wo13PriceAuthority,
) -> None:
    with pytest.raises(Wo13GeometryRejected) as captured:
        _mcx_fact_with_authority(authority)
    assert captured.value.failure is Wo13GeometryFailure.SOURCE_AUTHORITY_PROHIBITED


def _mcx_fact_with_authority(authority: Wo13PriceAuthority):
    return _fact(
        "100",
        Wo13StructuralRole.TARGET_CONSTRAINT,
        subject="MCX-SUBJECT-CRUDE",
        family=IntradayMarketFamily.MCX,
        authority=authority,
        instrument="INSTRUMENT:MCX:CRUDEOIL26SEPFUT",
        actual_contract="MCX-CONTRACT-CRUDE-202609",
        roll_lineage="MCX-ROLL-CRUDE-V1",
    )


def test_index_requires_underlying_authority_and_rejects_option_premium() -> None:
    underlying = _fact(
        "25000",
        Wo13StructuralRole.ENTRY_REFERENCE_SOURCE,
        subject="NSE-INDEX-NIFTY",
        family=IntradayMarketFamily.NSE_INDEX,
        authority=Wo13PriceAuthority.NSE_INDEX_UNDERLYING,
        instrument="INSTRUMENT:NSE:NIFTY",
    )
    assert underlying.price_authority is Wo13PriceAuthority.NSE_INDEX_UNDERLYING

    with pytest.raises(Wo13GeometryRejected) as captured:
        _fact(
            "100",
            Wo13StructuralRole.ENTRY_REFERENCE_SOURCE,
            subject="NSE-INDEX-NIFTY",
            family=IntradayMarketFamily.NSE_INDEX,
            authority=Wo13PriceAuthority.OPTION_PREMIUM,
            instrument="INSTRUMENT:NFO:NIFTY:CALL",
        )
    assert captured.value.failure is Wo13GeometryFailure.SOURCE_AUTHORITY_PROHIBITED


def test_mcx_geometry_is_exact_contract_and_roll_local() -> None:
    entry = _mcx_fact("7000", Wo13StructuralRole.ENTRY_REFERENCE_SOURCE)
    candidate = _mcx_fact("7100", Wo13StructuralRole.SETUP_NATIVE_TARGET)
    accepted = create_wo13_target_candidate(
        entry_reference=entry,
        candidate=candidate,
        direction=SemanticDirection.LONG,
        kind=Wo13TargetCandidateKind.SETUP_NATIVE_OBJECTIVE,
    )
    assert accepted.directional_distance == Decimal("100")

    for foreign in (
        _mcx_fact(
            "7100",
            Wo13StructuralRole.SETUP_NATIVE_TARGET,
            contract="MCX-CONTRACT-CRUDE-202610",
        ),
        _mcx_fact(
            "7100",
            Wo13StructuralRole.SETUP_NATIVE_TARGET,
            roll="MCX-ROLL-CRUDE-V2",
        ),
    ):
        with pytest.raises(Wo13GeometryRejected) as captured:
            create_wo13_target_candidate(
                entry_reference=entry,
                candidate=foreign,
                direction=SemanticDirection.LONG,
                kind=Wo13TargetCandidateKind.SETUP_NATIVE_OBJECTIVE,
            )
        assert captured.value.failure is Wo13GeometryFailure.TRUST_CONTEXT_MISMATCH


def test_rr_evaluates_geometry_and_cannot_manufacture_it() -> None:
    baseline, baseline_entry, baseline_stop, *_ = _calculation(
        SemanticDirection.LONG,
        entry="100",
        stop="98",
        target="104",
    )
    farther, farther_entry, farther_stop, *_ = _calculation(
        SemanticDirection.LONG,
        entry="100",
        stop="98",
        target="110",
    )

    assert baseline.model_rr == Decimal("2")
    assert farther.model_rr == Decimal("5")
    assert baseline_entry.price == farther_entry.price == Decimal("100")
    assert baseline_stop.price == farther_stop.price == Decimal("98")
    assert "minimum_rr" not in inspect.signature(calculate_wo13_geometry).parameters
    assert "desired_rr" not in inspect.signature(calculate_wo13_geometry).parameters


def test_identity_integrity_is_deterministic_and_corruption_fails_closed() -> None:
    first = _fact("100", Wo13StructuralRole.ENTRY_REFERENCE_SOURCE)
    repeated = _fact("100", Wo13StructuralRole.ENTRY_REFERENCE_SOURCE)
    changed_price = _fact("101", Wo13StructuralRole.ENTRY_REFERENCE_SOURCE)
    changed_source = _fact(
        "100",
        Wo13StructuralRole.ENTRY_REFERENCE_SOURCE,
        source="SOURCE:CHANGED",
        source_integrity="INTEGRITY:CHANGED",
    )
    changed_boundary = _fact(
        "100",
        Wo13StructuralRole.ENTRY_REFERENCE_SOURCE,
        boundary=_NOW + timedelta(minutes=15),
    )

    assert first == repeated
    assert len({
        first.fact_identity,
        changed_price.fact_identity,
        changed_source.fact_identity,
        changed_boundary.fact_identity,
    }) == 4
    with pytest.raises(Wo13GeometryRejected) as captured:
        replace(first, fact_integrity="INTEGRITY:CORRUPT")
    assert captured.value.failure is Wo13GeometryFailure.SOURCE_INTEGRITY_INVALID


def test_no_5m_risk_sponsor_or_execution_authority_surface() -> None:
    names = {item.name for item in fields(__import__(
        "kronos.intraday.wo13_geometry",
        fromlist=["Wo13GeometryCalculation"],
    ).Wo13GeometryCalculation)}
    assert names.isdisjoint({
        "current_ltp",
        "timing_state",
        "capital_reference",
        "quantity",
        "margin",
        "position_size",
        "risk_observation_state",
        "risk_alert",
    })
    result, *_ = _calculation(
        SemanticDirection.LONG,
        entry="100",
        stop="98",
        target="106",
    )
    assert not any((
        result.risk_authority,
        result.entry_timing_authority,
        result.sponsor_decision_authority,
        result.execution_authority,
        result.broker_authority,
    ))
    with pytest.raises(Wo13GeometryRejected) as five_minute:
        _fact(
            "100",
            Wo13StructuralRole.ENTRY_REFERENCE_SOURCE,
            timeframe=IntradayTimeframe.FIVE_MINUTES,
        )
    assert five_minute.value.failure is Wo13GeometryFailure.TIMEFRAME_AUTHORITY_INVALID
