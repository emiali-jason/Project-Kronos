from decimal import Decimal

from kronos.browser.views import _native_trade_plan
from kronos.swing.v1.native_trade_construction import (
    TradePlanStatus,
    TradePlanUnavailableReason,
    MaterialPricedBarrier,
    construct_trade_plan,
)
from tests.unit.swing.v1.test_native_trade_construction import (
    NOW,
    _context,
    _package,
    _ready,
)


def test_ready_trade_plan_renders_compact_sponsor_geometry() -> None:
    readiness, requirement = _ready()
    record = construct_trade_plan(
        requirement, readiness, _package(requirement, readiness),
        _context(requirement.canonical_instrument), created_at=NOW,
    )
    html = _native_trade_plan(record)
    assert "TRADE PLAN READY" in html
    assert all(value in html for value in ("ENTRY", "STOP", "TARGET", "R:R", "ENTRY CONDITION", "INVALIDATION", "WHY THESE LEVELS"))
    assert "₹100" in html and "₹90" in html and "₹120" in html
    assert "PAPER" not in html and "LIVE" not in html and "ORDER" not in html


def test_unavailable_trade_plan_renders_exact_governed_reason() -> None:
    readiness, requirement = _ready()
    record = construct_trade_plan(
        requirement, readiness,
        _package(requirement, readiness, prior_directional_swing_high=None),
        _context(requirement.canonical_instrument), created_at=NOW,
    )
    assert record.geometry_viability is TradePlanStatus.TRADE_PLAN_UNAVAILABLE
    assert record.unavailable_reason is TradePlanUnavailableReason.TARGET_AUTHORITY_UNAVAILABLE
    html = _native_trade_plan(record)
    assert "TRADE PLAN UNAVAILABLE" in html
    assert "TARGET AUTHORITY UNAVAILABLE" in html
    assert "ENTRY CONDITION" not in html


def test_barrier_constraint_is_explained_without_extra_target() -> None:
    readiness, requirement = _ready()
    barrier = MaterialPricedBarrier(
        "BARRIER-1", "f" * 64, Decimal("108"), readiness.observation_boundary,
        "REVIEWED_BARRIER", ("LAYER2",),
    )
    constrained = construct_trade_plan(
        requirement, readiness,
        _package(requirement, readiness, material_barriers=(barrier,)),
        _context(requirement.canonical_instrument), created_at=NOW,
    )
    html = _native_trade_plan(constrained)
    assert "TARGET CONSTRAINED BY REVIEWED MATERIAL BARRIER" in html
    assert html.count("<span>TARGET</span>") == 1
