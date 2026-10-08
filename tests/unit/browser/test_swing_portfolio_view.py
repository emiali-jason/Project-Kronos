"""Swing Portfolio truth, navigation and responsive presentation boundaries."""

from datetime import UTC, datetime
from decimal import Decimal
from html.parser import HTMLParser
from types import SimpleNamespace

import pytest

from kronos.browser.views import render_portfolio
from tests.unit.application.test_swing_opportunities import _ready


NOW = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)


def projection(**changes):
    values = dict(available=True, source_status="AVAILABLE", issues=(), as_of=NOW,
        positions=(), waiting_plans=(), objective_models=(), observations=(), closed_positions=(),
        exposure_groups=(), coverage={"position_sources_complete": True,
            "current_plan_sources_complete": True, "source_complete": True,
            "monetary_valuation": "UNKNOWN"})
    values.update(changes)
    return SimpleNamespace(**values)


def row(identity="POSITION-ONE", **changes):
    values = dict(identity=identity, truth="SPONSOR_POSITION", state="PAPER_ACTIVE", market="MCX",
        family="GOLDM", instrument="GOLDM", contract="GOLDM26OCTFUT", expiry="2026-10-05",
        direction="LONG", mode="PAPER", lots=1, units=None,
        quantity_provenance="GOVERNED_ONE_LOT", entry=Decimal("120"), entry_at=NOW,
        model_entry=Decimal("119"), stop=Decimal("110"), target=Decimal("140"),
        exit=None, exit_at=None, closure_reason=None, monitoring="INTERRUPTED",
        current_price=None, current_price_at=None, last_price=Decimal("125"), last_price_at=NOW,
        valuation_state="UNKNOWN", attention=("MONITORING_INTERRUPTED",),
        evidence=(("position_integrity", "A" * 64), ("receipt_at", NOW)),
        links=(("Exact position owner", "/swing/mcx-v1"), ("Journal", "/journal?product=SWING&record=DECISION-ONE")))
    values.update(changes)
    return values


def render(value=None, **filters):
    return render_portfolio(_ready(), product="SWING", swing_projection=value, **filters)


class Elements(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


def test_missing_source_never_displays_valid_empty_or_zero_exposure():
    html = render(projection(available=False, source_status="UNAVAILABLE",
                             issues=("CANONICAL_POSITION_SOURCE_UNAVAILABLE",)))
    assert "SWING PORTFOLIO UNAVAILABLE" in html
    assert "Current exposure and completeness are UNKNOWN" in html
    assert "CANONICAL_POSITION_SOURCE_UNAVAILABLE" in html
    assert "VALID EMPTY" not in html
    assert "0 VISIBLE" not in html


def test_uninstalled_projection_is_explicitly_unavailable():
    html = render()
    assert "SWING PORTFOLIO UNAVAILABLE" in html
    assert "SWING PORTFOLIO — NOT YET OPERATIONAL" not in html


def test_valid_empty_is_distinct_from_filtered_absence():
    empty = render(projection())
    filtered = render(projection(), search="OTHER")
    assert "VALID EMPTY — NO CURRENT SWING POSITIONS OR WAITING PLANS" in empty
    assert "All required sources were validated" in empty
    assert "NO MATCHING SWING PORTFOLIO RECORDS" in filtered
    assert "VALID EMPTY" not in filtered
    assert "monetary valuation remains unknown" in empty.lower()


def test_empty_retained_positions_do_not_establish_empty_unavailable_current_plans():
    html = render(projection(coverage={"position_sources_complete": True,
        "current_plan_sources_complete": False, "source_complete": False}))
    assert "NO RETAINED ENTERED POSITIONS — CURRENT PLAN COVERAGE UNAVAILABLE" in html
    assert "WAITING / ARMED PLANS UNKNOWN — CURRENT PLAN COVERAGE UNAVAILABLE" in html
    assert "Waiting / armed plans are UNKNOWN" in html
    assert "VALID EMPTY" not in html
    assert "All required sources were validated" not in html


def test_partial_current_plan_coverage_preserves_retained_position_and_model_truth():
    html = render(projection(positions=(row("RETAINED-POSITION"),),
        objective_models=(row("RETAINED-MODEL", truth="OBJECTIVE_MODEL", lots=None),),
        coverage={"position_sources_complete": True, "current_plan_sources_complete": False,
                  "source_complete": False}), search="RETAINED")
    assert 'data-position-identity="RETAINED-POSITION"' in html
    assert 'data-position-identity="RETAINED-MODEL"' in html
    assert "CURRENT PLAN COVERAGE UNAVAILABLE" in html
    assert "Waiting / armed plans are UNKNOWN" in html
    assert "SWING PORTFOLIO UNAVAILABLE" not in html
    assert "VALID EMPTY" not in html
    assert "All required sources were validated" not in html


def test_waiting_sponsor_objective_and_observation_truth_are_separate():
    value = projection(
        positions=(row("SPONSOR-POSITION"),),
        waiting_plans=(row("ARMED-PLAN", truth="WAITING_PLAN", state="PAPER_ARMED", entry=None),),
        objective_models=(row("OBJECTIVE-ONE", truth="OBJECTIVE_MODEL", lots=None),),
        observations=(row("OBSERVATION-ONE", truth="OBSERVATION", lots=None),),
        exposure_groups=({"market": "MCX", "family": "GOLDM", "direction": "LONG",
                          "sponsor_positions": 1, "lots": 1, "monetary_value": None,
                          "completeness": "PARTIAL_VALUATION"},))
    html = render(value)
    for heading in ("WAITING / ARMED PLANS", "ENTERED PAPER / MANUAL-LIVE POSITIONS",
                    "OBJECTIVE MODELS", "OBSERVATION TRACKS"):
        assert heading in html
    for identity in ("SPONSOR-POSITION", "ARMED-PLAN", "OBJECTIVE-ONE", "OBSERVATION-ONE"):
        assert html.count('data-position-identity="' + identity + '"') == 1
    assert "Plans are not entered trades" in html
    assert "not added to Sponsor position exposure" in html
    assert "Observations contribute zero position exposure" in html
    assert "PARTIAL_VALUATION" in html
    assert "monetary value</dt><dd>UNKNOWN" in html


def test_interruption_retains_position_and_separates_retained_quote_from_current_value():
    html = render(projection(positions=(row(),)))
    assert 'data-position-identity="POSITION-ONE"' in html
    assert "PAPER_ACTIVE" in html
    assert "MONITORING INTERRUPTED" in html
    assert "Latest admitted observed price: UNKNOWN" in html
    assert "Retained price (not current valuation): 125" in html
    assert "Valuation: UNKNOWN" in html
    assert "Lots: 1" in html and "Units: UNKNOWN" in html
    assert "GOLDM26OCTFUT" in html and "2026-10-05" in html


def test_accepted_observation_has_factual_observation_receipt_age_and_unknown_freshness():
    html = render(projection(positions=(row(monitoring="LIVE", current_price=Decimal("125"),
        current_price_at=NOW, price_received_at=NOW, quote_age_seconds=Decimal("34"),
        valuation_state="LATEST_ACCEPTED_OBSERVATION_FRESHNESS_UNKNOWN"),)))
    assert "Latest admitted observed price: 125" in html
    assert "Observed at: " + NOW.isoformat() in html
    assert "Received at: " + NOW.isoformat() in html
    assert "Observation age (seconds): 34" in html
    assert "LATEST_ACCEPTED_OBSERVATION_FRESHNESS_UNKNOWN" in html


def test_validation_representation_is_separate_from_entered_production_positions():
    html = render(projection(validation_positions=(row("VALIDATION-ONE",
        authority="HISTORICAL STEP-32 VALIDATION ONLY", exposure=False),)))
    assert "VALIDATION-ONLY REPRESENTATIONS" in html
    assert "Historical validation representations contribute zero production exposure" in html
    assert html.count('data-position-identity="VALIDATION-ONE"') == 1
    entered = html.split("ENTERED PAPER / MANUAL-LIVE POSITIONS", 1)[1].split("OBJECTIVE MODELS", 1)[0]
    assert "VALIDATION-ONE" not in entered


def test_live_action_required_is_not_rendered_as_factual_exit_or_closure():
    html = render(projection(positions=(row(mode="LIVE", lots=3,
        quantity_provenance="SPONSOR_ATTESTED_WHOLE_LOTS", state="ACTION_REQUIRED",
        attention=("ACTION_REQUIRED",), entry=Decimal("130.5"), exit=None),)))
    assert "Mode: LIVE" in html and "Lots: 3" in html
    assert "SPONSOR_ATTESTED_WHOLE_LOTS" in html
    assert "ACTION REQUIRED" in html
    assert "Entry: 130.5" in html
    assert "Exit: UNKNOWN" in html and "Closure: UNKNOWN" in html
    assert "ACTION REQUIRED is not a fill or factual exit" in html


def test_closed_live_keeps_attested_factual_exit_and_zero_price_is_not_unknown():
    html = render(projection(closed_positions=(row(mode="LIVE", state="CLOSED", lots=2,
        exit=Decimal("0"), exit_at=NOW, closure_reason="SPONSOR_MANUAL_EXIT", attention=()),)), state="CLOSED")
    assert 'class="swing-portfolio-closed">CLOSED' in html
    assert "Exit: 0" in html and "SPONSOR_MANUAL_EXIT" in html
    assert "Exit: UNKNOWN" not in html
    assert NOW.isoformat() in html
    assert "NO MATCHING SWING PORTFOLIO RECORDS" not in html
    assert "Closed positions contribute no current exposure" in html


def test_source_identifiers_are_escaped_and_only_safe_local_navigation_is_linked():
    html = render(projection(positions=(row('POSITION-<script>"',
        instrument="<img src=x onerror=alert(1)>",
        evidence=(("<receipt>", '<script>alert("x")</script>'),),
        links=(("Exact <Journal>", "/journal?product=SWING&record=A%22B"),
               ("EXTERNAL", "https://example.com"), ("NETWORK", "//example.com"),
               ("SCRIPT", "javascript:alert(1)"), ("BACKSLASH", "/\\example.com"))),)))
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
    assert "&lt;script&gt;alert(&quot;" in html
    assert "Exact &lt;Journal&gt;" in html
    assert 'href="/journal?product=SWING&amp;record=A%22B"' in html
    for label in (">EXTERNAL<", ">NETWORK<", ">SCRIPT<", ">BACKSLASH<"):
        assert label not in html
    assert '<img src=x' not in html


def test_filters_are_get_only_and_preserve_selected_values():
    html = render(projection(), search='GOLDM " October', market="MCX", family="GOLDM",
                  mode="LIVE", state="ACTION_REQUIRED", direction="SHORT", monitoring="INTERRUPTED")
    elements = Elements(html).elements
    forms = [attrs for tag, attrs in elements if tag == "form" and attrs.get("action") == "/portfolio"]
    assert forms == [{"class": "swing-portfolio-filters", "method": "get", "action": "/portfolio"}]
    selected = {attrs.get("value") for tag, attrs in elements if tag == "option" and "selected" in attrs}
    assert {"MCX", "GOLDM", "LIVE", "ACTION_REQUIRED", "SHORT", "INTERRUPTED"} <= selected
    assert 'value="GOLDM &quot; October"' in html
    assert 'href="/swing/active"' in html and 'href="/swing/mcx-v1"' in html


def test_wide_tables_scroll_locally_are_keyboard_focusable_and_identifiers_wrap():
    html = render(projection(positions=(row("LONG-IDENTITY-" + "A" * 256),)))
    regions = [attrs for tag, attrs in Elements(html).elements
               if attrs.get("class") == "swing-portfolio-table-wrap"]
    assert regions and all(attrs["tabindex"] == "0" and attrs["role"] == "region" for attrs in regions)
    assert all("scroll horizontally" in attrs["aria-label"] for attrs in regions)
    assert ".swing-portfolio-table-wrap{width:100%;max-width:100%;overflow-x:auto" in html
    assert "overflow-wrap:anywhere" in html
    assert ".swing-portfolio{min-width:0;max-width:100%;font-size:12px" in html
    assert ".swing-portfolio :is(a,button,input,select,summary,[tabindex]):focus-visible" in html


@pytest.mark.parametrize("kwargs,marker", [({}, "NO ACTIVE INTRADAY PAPER POSITIONS"),
    ({"search": "LUPIN", "direction": "SHORT", "monitoring": "INTERRUPTED"}, "FILTER EXPOSURE")])
def test_intraday_empty_and_filters_keep_existing_product_boundary(kwargs, marker):
    html = render_portfolio(_ready(), product="INTRADAY", **kwargs)
    assert marker in html
    assert "Entered PAPER model exposure only. Observations are not exposure. LIVE is not commissioned." in html
    assert 'name="product" value="INTRADAY"' in html
    assert "swing-portfolio-filters" not in html
    assert "SWING PORTFOLIO UNAVAILABLE" not in html
