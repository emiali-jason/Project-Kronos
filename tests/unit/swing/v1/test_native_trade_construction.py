from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import inspect
import json

import pytest

from kronos.instrument.facts import CanonicalInstrumentContext, InstrumentContextStatus
from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.native_readiness import NativeReadinessState
from kronos.swing.v1.native_readiness import create_native_readiness_record
from kronos.swing.v1.native_trade_construction import (
    AuthoritativePriceEvidence,
    LocalTradePlanStore,
    MaterialPricedBarrier,
    QualificationCandleEvidence,
    TRADE_CONSTRUCTION_POLICY_ID,
    TradeConstructionInputRejected,
    TradePlanStatus,
    TradePlanUnavailableReason,
    TradeSetupIdentity,
    construct_trade_plan,
    create_trade_construction_evidence_package,
    step32_handoff,
)
from tests.unit.browser.test_browser_native_readiness import _record
from tests.unit.swing.v1.test_native_readiness import _complete_visual_for
from tests.unit.swing.v1.test_native_readiness import _complete_visual_pairs
from tests.unit.swing.v1.test_native_review import _layer2
from tests.unit.swing.v1.test_native_review import _evidence_run
from kronos.swing.v1.native_review import NativeLayer2EvidenceState
from kronos.swing.v1.native_review import NativeReviewEvidenceStore
from kronos.application.swing_native_review import NativeReviewWorkflow
import kronos.swing.v1.native_trade_construction as trade_construction_module


NOW = datetime(2026, 8, 17, 8, 0, tzinfo=UTC)


def _ready(direction: V1Direction = V1Direction.LONG):  # type: ignore[no-untyped-def]
    readiness, requirement, _ = _record(NativeReadinessState.READY_FOR_TRADE_CONSTRUCTION)
    if direction is not requirement.thesis.direction:
        requirement = replace(requirement, thesis=replace(requirement.thesis, direction=direction))
        readiness = replace(
            readiness,
            canonical_instrument="TEST",
            result_sha256="0" * 64,
        )
        # Use the real helper for inverse geometry only through a same-direction
        # requirement fixture below; altering a signed Readiness record is forbidden.
        raise AssertionError("direction fixture must be built by _inverse_ready")
    return readiness, requirement


def _inverse_ready():  # type: ignore[no-untyped-def]
    readiness, requirement = _ready()
    requirement = replace(requirement, thesis=replace(requirement.thesis, direction=V1Direction.SHORT))
    readiness = create_native_readiness_record(
        requirement,
        _layer2(requirement, NativeLayer2EvidenceState.SUPPORTS_NATIVE_THESIS),
        _complete_visual_for(requirement),
        created_at=NOW,
    )
    assert readiness.readiness is NativeReadinessState.READY_FOR_TRADE_CONSTRUCTION
    return readiness, requirement


def _price(identity: str, value: str, boundary: datetime) -> AuthoritativePriceEvidence:
    return AuthoritativePriceEvidence(
        identity, sha256(identity.encode()).hexdigest(),
        Decimal(value), boundary, f"GOVERNED:COMPLETED_4H:{identity}", ("KITE:HISTORICAL",),
    )


def _candle(boundary: datetime, *, high: str = "100", low: str = "95") -> QualificationCandleEvidence:
    return QualificationCandleEvidence(
        "QUAL-CANDLE", "a" * 64, Decimal(high), Decimal(low), boundary, True,
        "COMPLETED_OHLCV:QUALIFICATION_CANDLE", ("KITE:HISTORICAL", "DOMAIN-008"),
    )


def _context(instrument: str, *, tick: str = "0.05") -> CanonicalInstrumentContext:
    return CanonicalInstrumentContext(
        "INSTRUMENT-CONTEXT-" + "b" * 64,
        instrument, "CNC", "KITE", instrument, "NSE", "NSE", "EQ",
        Decimal(tick), 1, 2, InstrumentContextStatus.COMPLETE,
        ("DOMAIN-006:EAIC-002", f"KITE:NSE:{instrument}"),
    )


def _package(requirement, readiness, setup=TradeSetupIdentity.PULLBACK_CONTINUATION, **changes):  # type: ignore[no-untyped-def]
    values = dict(
        package_identity="STEP31-EVIDENCE-PACKAGE-1",
        native_run_identity=requirement.native_run_identity,
        canonical_instrument=requirement.canonical_instrument,
        native_assessment_sha256=requirement.thesis.native_assessment_sha256,
        setup_identity=setup,
        observation_boundary=readiness.observation_boundary,
        provenance=("NATIVE_REVIEW", "DOMAIN-002", "DOMAIN-008"),
        qualification_candle=_candle(readiness.observation_boundary),
        governing_structural_low=_price("STRUCTURAL-LOW", "90", readiness.observation_boundary),
        governing_structural_high=_price("STRUCTURAL-HIGH", "110", readiness.observation_boundary),
        prior_directional_swing_high=_price("PRIOR-SWING-HIGH", "120", readiness.observation_boundary),
        prior_directional_swing_low=_price("PRIOR-SWING-LOW", "80", readiness.observation_boundary),
        original_range_high=_price("RANGE-HIGH", "100", readiness.observation_boundary),
        original_range_low=_price("RANGE-LOW", "90", readiness.observation_boundary),
    )
    values.update(changes)
    return create_trade_construction_evidence_package(**values)


def test_input_gate_allows_ready_and_rejects_every_other_state() -> None:
    readiness, requirement = _ready()
    plan = construct_trade_plan(requirement, readiness, _package(requirement, readiness), _context(requirement.canonical_instrument), created_at=NOW)
    assert plan.geometry_viability is TradePlanStatus.TRADE_PLAN_READY
    for state in NativeReadinessState:
        if state is NativeReadinessState.READY_FOR_TRADE_CONSTRUCTION:
            continue
        other, other_requirement, _ = _record(state)
        with pytest.raises(TradeConstructionInputRejected, match="STEP31_READINESS_NOT_ELIGIBLE"):
            construct_trade_plan(other_requirement, other, _package(other_requirement, other), _context(other_requirement.canonical_instrument), created_at=NOW)


def test_pullback_long_geometry_invalidation_and_rr() -> None:
    readiness, requirement = _ready()
    plan = construct_trade_plan(requirement, readiness, _package(requirement, readiness), _context(requirement.canonical_instrument), created_at=NOW)
    assert (plan.entry, plan.stop, plan.invalidation_reference, plan.canonical_target) == (
        Decimal("100.00"), Decimal("90.00"), Decimal("90.00"), Decimal("120.00")
    )
    assert plan.invalidation_condition == "COMPLETED_DAILY_CLOSE_BELOW_GOVERNING_PULLBACK_STRUCTURAL_LOW"
    assert (plan.risk_per_unit, plan.reward_per_unit, plan.risk_reward_ratio) == (
        Decimal("10.00"), Decimal("20.00"), Decimal("2")
    )


def test_pullback_short_inverse_geometry() -> None:
    readiness, requirement = _inverse_ready()
    plan = construct_trade_plan(requirement, readiness, _package(requirement, readiness), _context(requirement.canonical_instrument), created_at=NOW)
    assert (plan.entry, plan.stop, plan.invalidation_reference, plan.canonical_target) == (
        Decimal("95.00"), Decimal("110.00"), Decimal("110.00"), Decimal("80.00")
    )
    assert plan.invalidation_condition == "COMPLETED_DAILY_CLOSE_ABOVE_GOVERNING_PULLBACK_STRUCTURAL_HIGH"
    assert plan.risk_per_unit == plan.reward_per_unit == Decimal("15.00")


def test_breakout_long_and_short_geometry() -> None:
    readiness, requirement = _ready()
    long = construct_trade_plan(
        requirement, readiness,
        _package(requirement, readiness, TradeSetupIdentity.CONSOLIDATION_BREAKOUT),
        _context(requirement.canonical_instrument), created_at=NOW,
    )
    assert (long.entry, long.stop, long.invalidation_reference, long.setup_native_raw_target, long.canonical_target) == (
        Decimal("100.00"), Decimal("95.00"), Decimal("100.00"), Decimal("110"), Decimal("110.00")
    )
    assert long.invalidation_condition == "COMPLETED_DAILY_CLOSE_AT_OR_BELOW_ORIGINAL_RANGE_HIGH"

    short_readiness, short_requirement = _inverse_ready()
    short = construct_trade_plan(
        short_requirement, short_readiness,
        _package(short_requirement, short_readiness, TradeSetupIdentity.CONSOLIDATION_BREAKOUT,
                 qualification_candle=_candle(short_readiness.observation_boundary, high="95", low="90")),
        _context(short_requirement.canonical_instrument), created_at=NOW,
    )
    assert (short.entry, short.stop, short.invalidation_reference, short.setup_native_raw_target, short.canonical_target) == (
        Decimal("90.00"), Decimal("95.00"), Decimal("90.00"), Decimal("80"), Decimal("80.00")
    )
    assert short.invalidation_condition == "COMPLETED_DAILY_CLOSE_AT_OR_ABOVE_ORIGINAL_RANGE_LOW"


def test_nearest_material_barrier_constrains_only_canonical_target() -> None:
    readiness, requirement = _ready()
    boundary = readiness.observation_boundary
    barriers = (
        MaterialPricedBarrier("BARRIER-115", "c" * 64, Decimal("115"), boundary, "REVIEWED_BARRIER", ("LAYER2",)),
        MaterialPricedBarrier("BARRIER-108", "d" * 64, Decimal("108"), boundary, "REVIEWED_BARRIER", ("LAYER2",)),
    )
    plan = construct_trade_plan(
        requirement, readiness, _package(requirement, readiness, material_barriers=barriers),
        _context(requirement.canonical_instrument), created_at=NOW,
    )
    assert plan.setup_native_raw_target == Decimal("120")
    assert plan.canonical_target == Decimal("108.00")
    assert plan.material_barrier_identity == "BARRIER-108"


def test_barrier_rounding_that_eliminates_reward_fails_closed() -> None:
    readiness, requirement = _ready()
    barrier = MaterialPricedBarrier(
        "BARRIER-100001", "e" * 64, Decimal("100.001"), readiness.observation_boundary,
        "REVIEWED_BARRIER", ("LAYER2",),
    )
    plan = construct_trade_plan(
        requirement, readiness, _package(requirement, readiness, material_barriers=(barrier,)),
        _context(requirement.canonical_instrument), created_at=NOW,
    )
    assert plan.geometry_viability is TradePlanStatus.TRADE_PLAN_UNAVAILABLE
    assert plan.unavailable_reason is TradePlanUnavailableReason.MATERIAL_BARRIER_ELIMINATES_POSITIVE_REWARD


@pytest.mark.parametrize(
    ("changes", "reason"),
    (
        ({"qualification_candle": None}, TradePlanUnavailableReason.ENTRY_AUTHORITY_UNAVAILABLE),
        ({"governing_structural_low": None}, TradePlanUnavailableReason.STOP_AUTHORITY_UNAVAILABLE),
        ({"governing_structural_high": None}, TradePlanUnavailableReason.TARGET_AUTHORITY_UNAVAILABLE),
        ({"prior_directional_swing_high": None}, TradePlanUnavailableReason.TARGET_AUTHORITY_UNAVAILABLE),
    ),
)
def test_missing_authority_fails_closed(changes, reason) -> None:  # type: ignore[no-untyped-def]
    readiness, requirement = _ready()
    if changes == {"governing_structural_high": None}:
        changes = {"original_range_high": None}
        setup = TradeSetupIdentity.CONSOLIDATION_BREAKOUT
        reason = TradePlanUnavailableReason.INVALIDATION_AUTHORITY_UNAVAILABLE
    else:
        setup = TradeSetupIdentity.PULLBACK_CONTINUATION
    plan = construct_trade_plan(
        requirement, readiness, _package(requirement, readiness, setup, **changes),
        _context(requirement.canonical_instrument), created_at=NOW,
    )
    assert plan.geometry_viability is TradePlanStatus.TRADE_PLAN_UNAVAILABLE
    assert plan.unavailable_reason is reason


@pytest.mark.parametrize(
    "changes",
    (
        {"governing_structural_low": "105"},
        {"prior_directional_swing_high": "99"},
    ),
)
def test_invalid_long_geometry_fails_closed(changes) -> None:  # type: ignore[no-untyped-def]
    readiness, requirement = _ready()
    kwargs = {
        name: _price(name.upper(), value, readiness.observation_boundary)
        for name, value in changes.items()
    }
    plan = construct_trade_plan(requirement, readiness, _package(requirement, readiness, **kwargs), _context(requirement.canonical_instrument), created_at=NOW)
    expected = (
        TradePlanUnavailableReason.TARGET_NOT_FORWARD_OF_ENTRY
        if "prior_directional_swing_high" in changes
        else TradePlanUnavailableReason.GEOMETRY_INVALID
    )
    assert plan.unavailable_reason is expected


def test_invalid_short_stop_and_target_geometry_fail_closed() -> None:
    readiness, requirement = _inverse_ready()
    bad_stop = construct_trade_plan(
        requirement, readiness,
        _package(requirement, readiness, governing_structural_high=_price("BAD-STOP", "90", readiness.observation_boundary)),
        _context(requirement.canonical_instrument), created_at=NOW,
    )
    assert bad_stop.unavailable_reason is TradePlanUnavailableReason.GEOMETRY_INVALID
    bad_target = construct_trade_plan(
        requirement, readiness,
        _package(requirement, readiness, prior_directional_swing_low=_price("BAD-TARGET", "96", readiness.observation_boundary)),
        _context(requirement.canonical_instrument), created_at=NOW,
    )
    assert bad_target.unavailable_reason is TradePlanUnavailableReason.TARGET_NOT_FORWARD_OF_ENTRY


@pytest.mark.parametrize("source", ("OPENAI_LEVEL", "PINE_CPR", "COMEX_REFERENCE", "NYMEX_REFERENCE"))
def test_excluded_authorities_cannot_enter_geometry(source: str) -> None:
    readiness, _ = _ready()
    with pytest.raises(ValueError, match="TRADE_PRICE_EVIDENCE_INVALID"):
        AuthoritativePriceEvidence(
            "FOREIGN-AUTHORITY", "f" * 64, Decimal("100"),
            readiness.observation_boundary, source, ("LAYER2",),
        )


def test_positive_rr_below_one_is_ready_and_never_moves_geometry() -> None:
    readiness, requirement = _ready()
    plan = construct_trade_plan(
        requirement, readiness,
        _package(requirement, readiness, prior_directional_swing_high=_price("TARGET-105", "105", readiness.observation_boundary)),
        _context(requirement.canonical_instrument), created_at=NOW,
    )
    assert plan.geometry_viability is TradePlanStatus.TRADE_PLAN_READY
    assert plan.risk_reward_ratio == Decimal("0.5")
    assert plan.canonical_target == Decimal("105.00")


def test_tick_rounding_is_directionally_safe_and_context_is_required() -> None:
    readiness, requirement = _ready()
    plan = construct_trade_plan(
        requirement, readiness,
        _package(
            requirement, readiness,
            qualification_candle=_candle(readiness.observation_boundary, high="100.021", low="95.019"),
            governing_structural_low=_price("STRUCTURAL-LOW", "90.021", readiness.observation_boundary),
            prior_directional_swing_high=_price("PRIOR-HIGH", "120.029", readiness.observation_boundary),
        ),
        _context(requirement.canonical_instrument), created_at=NOW,
    )
    assert (plan.entry, plan.stop, plan.canonical_target) == (Decimal("100.05"), Decimal("90.00"), Decimal("120.00"))
    incomplete = replace(_context(requirement.canonical_instrument), tick_size=None, lot_size=None,
                         price_precision=None, status=InstrumentContextStatus.INCOMPLETE)
    unavailable = construct_trade_plan(requirement, readiness, _package(requirement, readiness), incomplete, created_at=NOW)
    assert unavailable.unavailable_reason is TradePlanUnavailableReason.EXECUTION_CONTEXT_INCOMPLETE


def test_record_has_one_target_no_entry_zone_and_excludes_foreign_authority() -> None:
    readiness, requirement = _ready()
    plan = construct_trade_plan(requirement, readiness, _package(requirement, readiness), _context(requirement.canonical_instrument), created_at=NOW)
    assert not hasattr(plan, "entry_zone")
    assert hasattr(plan, "canonical_target") and not hasattr(plan, "target_2")
    serialized = repr(plan)
    assert "OPENAI" not in serialized and "PINE" not in serialized and "COMEX" not in serialized
    assert plan.authority.endswith("NO_SPONSOR_OR_EXECUTION_AUTHORITY")
    assert plan.trade_construction_policy_identity == TRADE_CONSTRUCTION_POLICY_ID


def test_evidence_binding_staleness_and_execution_context_fail_closed() -> None:
    readiness, requirement = _ready()
    stale = _package(
        requirement, readiness,
        observation_boundary=readiness.observation_boundary.replace(day=readiness.observation_boundary.day - 1),
    )
    plan = construct_trade_plan(requirement, readiness, stale, _context(requirement.canonical_instrument), created_at=NOW)
    assert plan.unavailable_reason is TradePlanUnavailableReason.EVIDENCE_STALE
    foreign = _package(requirement, readiness, canonical_instrument="FOREIGN")
    assert construct_trade_plan(requirement, readiness, foreign, _context(requirement.canonical_instrument), created_at=NOW).unavailable_reason is TradePlanUnavailableReason.EVIDENCE_BINDING_INVALID


def test_idempotent_persistence_restart_and_changed_evidence_supersession(tmp_path: Path) -> None:
    readiness, requirement = _ready()
    context = _context(requirement.canonical_instrument)
    package = _package(requirement, readiness)
    first = construct_trade_plan(requirement, readiness, package, context, created_at=NOW)
    repeated = construct_trade_plan(requirement, readiness, package, context, created_at=NOW)
    assert repeated.trade_plan_id == first.trade_plan_id
    store = LocalTradePlanStore(tmp_path.resolve())
    first_path = store.retain(first)
    assert store.retain(repeated) == first_path
    assert store.load_for_requirements((requirement,)) == (first,)

    changed = _package(
        requirement, readiness,
        package_identity="STEP31-EVIDENCE-PACKAGE-2",
        prior_directional_swing_high=_price("PRIOR-HIGH-NEW", "125", readiness.observation_boundary),
    )
    second = construct_trade_plan(requirement, readiness, changed, context, created_at=NOW)
    assert second.trade_plan_id != first.trade_plan_id
    store.retain(second)
    assert len(store.load_for_requirements((requirement,))) == 2


def test_only_ready_record_crosses_step32_handoff() -> None:
    readiness, requirement = _ready()
    ready = construct_trade_plan(requirement, readiness, _package(requirement, readiness), _context(requirement.canonical_instrument), created_at=NOW)
    assert step32_handoff(ready) is ready
    unavailable = construct_trade_plan(requirement, readiness, _package(requirement, readiness, prior_directional_swing_high=None), _context(requirement.canonical_instrument), created_at=NOW)
    with pytest.raises(ValueError, match="STEP32_TRADE_PLAN_HANDOFF_REJECTED"):
        step32_handoff(unavailable)


def test_native_review_workflow_constructs_idempotently_and_restores_plan(tmp_path: Path) -> None:
    facts, run, _ = _evidence_run()
    root = tmp_path.resolve()
    workflow = NativeReviewWorkflow(NativeReviewEvidenceStore(root), clock=lambda: NOW)
    prepared = workflow.prepare(run, facts)
    for request, response in _complete_visual_pairs():
        workflow.ingest_visual_v2(request, response)
    requirement = prepared.requirements[0]
    readiness = workflow.ingest_readiness(
        _layer2(requirement, NativeLayer2EvidenceState.SUPPORTS_NATIVE_THESIS),
        created_at=NOW,
    )
    package = _package(requirement, readiness)
    first = workflow.construct_trade_plan(
        requirement.canonical_instrument,
        package,
        _context(requirement.canonical_instrument),
    )
    assert workflow.construct_trade_plan(
        requirement.canonical_instrument,
        package,
        _context(requirement.canonical_instrument),
    ) is first
    assert workflow.snapshot().trade_plans == (first,)

    restored = NativeReviewWorkflow(NativeReviewEvidenceStore(root)).restore(run, facts)
    assert restored.trade_plans == (first,)


@pytest.mark.parametrize(
    ("direction", "candidate", "eligible"),
    (
        (V1Direction.LONG, "100", False),
        (V1Direction.LONG, "99", False),
        (V1Direction.LONG, "101", True),
        (V1Direction.SHORT, "95", False),
        (V1Direction.SHORT, "96", False),
        (V1Direction.SHORT, "94", True),
    ),
)
def test_v1_forward_target_gate_is_strict_and_symmetric(
    direction: V1Direction, candidate: str, eligible: bool,
) -> None:
    readiness, requirement = _ready() if direction is V1Direction.LONG else _inverse_ready()
    change = (
        {"prior_directional_swing_high": _price("CANDIDATE", candidate, readiness.observation_boundary)}
        if direction is V1Direction.LONG else
        {"prior_directional_swing_low": _price("CANDIDATE", candidate, readiness.observation_boundary)}
    )
    plan = construct_trade_plan(
        requirement, readiness, _package(requirement, readiness, **change),
        _context(requirement.canonical_instrument), created_at=NOW,
    )
    assert (plan.geometry_viability is TradePlanStatus.TRADE_PLAN_READY) is eligible
    if not eligible:
        assert plan.unavailable_reason is TradePlanUnavailableReason.TARGET_NOT_FORWARD_OF_ENTRY
        assert plan.canonical_target is None
        assert plan.reward_per_unit is None
        assert plan.risk_reward_ratio is None
        assert plan.rejected_target_candidate_price is not None


def test_v1_forward_gate_uses_rounded_entry_and_target_and_has_no_ltp_input() -> None:
    readiness, requirement = _ready()
    plan = construct_trade_plan(
        requirement,
        readiness,
        _package(
            requirement,
            readiness,
            qualification_candle=_candle(readiness.observation_boundary, high="100.021"),
            prior_directional_swing_high=_price("ROUNDING-CANDIDATE", "100.049", readiness.observation_boundary),
        ),
        _context(requirement.canonical_instrument),
        created_at=NOW,
    )
    assert plan.entry == Decimal("100.05")
    assert plan.rejected_target_candidate_price == Decimal("100.00")
    assert plan.unavailable_reason is TradePlanUnavailableReason.TARGET_NOT_FORWARD_OF_ENTRY
    assert "ltp" not in inspect.signature(construct_trade_plan).parameters


def test_rejected_candidate_does_not_search_barriers_as_fallback(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    readiness, requirement = _ready()

    def forbidden(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("BARRIER_SEARCH_MUST_NOT_RUN")

    monkeypatch.setattr(trade_construction_module, "_nearest_barrier", forbidden)
    plan = construct_trade_plan(
        requirement,
        readiness,
        _package(
            requirement,
            readiness,
            prior_directional_swing_high=_price("REJECTED", "99", readiness.observation_boundary),
        ),
        _context(requirement.canonical_instrument),
        created_at=NOW,
    )
    assert plan.unavailable_reason is TradePlanUnavailableReason.TARGET_NOT_FORWARD_OF_ENTRY


def test_equal_or_behind_barrier_cannot_replace_valid_forward_target() -> None:
    readiness, requirement = _ready()
    barriers = (
        MaterialPricedBarrier(
            "AT-ENTRY", "1" * 64, Decimal("100"), readiness.observation_boundary,
            "GOVERNED:COMPLETED_4H:BARRIER", ("LAYER2",),
        ),
        MaterialPricedBarrier(
            "BEHIND-ENTRY", "2" * 64, Decimal("99"), readiness.observation_boundary,
            "GOVERNED:COMPLETED_4H:BARRIER", ("LAYER2",),
        ),
    )
    plan = construct_trade_plan(
        requirement, readiness,
        _package(requirement, readiness, material_barriers=barriers),
        _context(requirement.canonical_instrument), created_at=NOW,
    )
    assert plan.canonical_target == Decimal("120.00")
    assert plan.material_barrier_identity is None


def test_breakout_non_forward_projection_fails_closed_without_hierarchy_change() -> None:
    readiness, requirement = _ready()
    plan = construct_trade_plan(
        requirement,
        readiness,
        _package(
            requirement,
            readiness,
            TradeSetupIdentity.CONSOLIDATION_BREAKOUT,
            qualification_candle=_candle(readiness.observation_boundary, high="120", low="115"),
        ),
        _context(requirement.canonical_instrument),
        created_at=NOW,
    )
    assert plan.setup_native_raw_target == Decimal("110")
    assert plan.rejected_target_candidate_identity.startswith("BREAKOUT-PROJECTION:")
    assert plan.unavailable_reason is TradePlanUnavailableReason.TARGET_NOT_FORWARD_OF_ENTRY


def test_vbl_and_mcx_controlled_replays_are_symmetric_rejected_context() -> None:
    short_readiness, short_requirement = _inverse_ready()
    vbl = construct_trade_plan(
        short_requirement,
        short_readiness,
        _package(
            short_requirement,
            short_readiness,
            qualification_candle=_candle(short_readiness.observation_boundary, high="420", low="408.75"),
            governing_structural_high=_price("VBL-STOP", "447.90", short_readiness.observation_boundary),
            prior_directional_swing_low=_price("VBL-CANDIDATE", "432.25", short_readiness.observation_boundary),
        ),
        _context(short_requirement.canonical_instrument),
        created_at=NOW,
    )
    long_readiness, long_requirement = _ready()
    mcx = construct_trade_plan(
        long_requirement,
        long_readiness,
        _package(
            long_requirement,
            long_readiness,
            qualification_candle=_candle(long_readiness.observation_boundary, high="3211.4", low="3100"),
            governing_structural_low=_price("MCX-STOP", "2892.1", long_readiness.observation_boundary),
            prior_directional_swing_high=_price("MCX-CANDIDATE", "3023.7", long_readiness.observation_boundary),
        ),
        _context(long_requirement.canonical_instrument, tick="0.1"),
        created_at=NOW,
    )
    assert (vbl.entry, vbl.rejected_target_candidate_price, vbl.canonical_target) == (
        Decimal("408.75"), Decimal("432.25"), None,
    )
    assert (mcx.entry, mcx.rejected_target_candidate_price, mcx.canonical_target) == (
        Decimal("3211.40"), Decimal("3023.70"), None,
    )
    assert vbl.reward_per_unit is mcx.reward_per_unit is None


def test_v0_and_v1_trade_plans_coexist_and_unknown_policy_fails_closed(tmp_path: Path) -> None:
    readiness, requirement = _ready()
    current = construct_trade_plan(
        requirement, readiness, _package(requirement, readiness),
        _context(requirement.canonical_instrument), created_at=NOW,
    )
    current_data = trade_construction_module._primitive(current)  # noqa: SLF001
    assert isinstance(current_data, dict)
    legacy_data = dict(current_data)
    legacy_data.update(
        contract_identity="KRONOS-SWING-V1-TRADE-PLAN-RECORD-V0",
        contract_version="0",
        trade_plan_id="TRADE-PLAN-LEGACY-V0",
        trade_construction_policy_identity="SWING-V1-TRADE-CONSTRUCTION-V0",
        trade_construction_policy_version="0",
        integrity_hash="",
    )
    for key in (
        "rejected_target_candidate_identity", "rejected_target_candidate_price",
        "rejected_target_candidate_timeframe", "rejected_target_candidate_source",
        "rejected_target_candidate_boundary", "rejected_target_candidate_evidence_sha256",
        "rejected_target_candidate_provenance", "target_rejection_reason",
    ):
        legacy_data.pop(key)
    legacy_data["integrity_hash"] = sha256(
        trade_construction_module._canonical(legacy_data)  # noqa: SLF001
    ).hexdigest()
    root = tmp_path / requirement.native_run_identity / requirement.canonical_instrument
    root.mkdir(parents=True)
    (root / "legacy.json").write_text(json.dumps({
        "schema": "KRONOS-SWING-V1-TRADE-PLAN-STORE-V0",
        "record": legacy_data,
    }))
    store = LocalTradePlanStore(tmp_path.resolve())
    store.retain(current)
    restored = store.load_for_requirements((requirement,))
    assert {item.trade_construction_policy_identity for item in restored} == {
        "SWING-V1-TRADE-CONSTRUCTION-V0", "SWING-V1-TRADE-CONSTRUCTION-V1",
    }

    corrupt = dict(current_data)
    corrupt["trade_construction_policy_version"] = "UNKNOWN"
    corrupt["integrity_hash"] = sha256(
        trade_construction_module._canonical(corrupt | {"integrity_hash": ""})  # noqa: SLF001
    ).hexdigest()
    (root / "unknown.json").write_text(json.dumps({
        "schema": "KRONOS-SWING-V1-TRADE-PLAN-STORE-V1", "record": corrupt,
    }))
    with pytest.raises(ValueError, match="STORED_RECORD_INVALID"):
        store.load_for_requirements((requirement,))


def test_rejected_v1_plan_restart_preserves_exact_unavailability(tmp_path: Path) -> None:
    readiness, requirement = _ready()
    rejected = construct_trade_plan(
        requirement, readiness,
        _package(
            requirement, readiness,
            prior_directional_swing_high=_price("RESTART-REJECTED", "99", readiness.observation_boundary),
        ),
        _context(requirement.canonical_instrument), created_at=NOW,
    )
    store = LocalTradePlanStore(tmp_path.resolve())
    store.retain(rejected)
    assert store.load_for_requirements((requirement,)) == (rejected,)
    assert rejected.trade_construction_policy_identity == "SWING-V1-TRADE-CONSTRUCTION-V1"
    assert rejected.canonical_target is rejected.reward_per_unit is rejected.risk_reward_ratio is None
