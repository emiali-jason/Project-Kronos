"""Qualification for the Main Slice 4D-V standardized visible panel."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import re

import pytest

from kronos.swing.v1.visible_pine_evidence import (
    VISIBLE_PINE_MISSING_TOKENS,
    VISIBLE_PINE_PANEL_CONTRACT_ID,
    VISIBLE_PINE_PANEL_DOMAIN_ROWS,
    VISIBLE_PINE_PANEL_PUBLISHER_ROLE,
    VISIBLE_PINE_PANEL_ROW_ORDER,
    VISIBLE_PINE_PANEL_VERSION,
)
from tests.fixtures.swing_v1_visible_pine_evidence import (
    MCX_VISIBLE_PANEL_KNOWN_TRUTH,
    NSE_VISIBLE_PANEL_KNOWN_TRUTH,
)


ROOT = Path(__file__).resolve().parents[4]
MCX_PARENT = ROOT / (
    "research/swing/pine-publication/candidates/4B-MCX/"
    "KRONOS_FUTURES_V2_PINE_EVIDENCE_V1_1_CANDIDATE.pine"
)
NSE_PARENT = ROOT / (
    "research/swing/pine-publication/candidates/4C-NSE/"
    "KRONOS_NSE_V1_SR1_PINE_EVIDENCE_V1_1_CANDIDATE.pine"
)
MCX_CANDIDATE = ROOT / (
    "research/swing/pine-publication/candidates/4D-V-MCX/"
    "KRONOS_FUTURES_V2_VISIBLE_EVIDENCE_V1_CANDIDATE.pine"
)
NSE_CANDIDATE = ROOT / (
    "research/swing/pine-publication/candidates/4D-V-NSE/"
    "KRONOS_NSE_V1_SR1_VISIBLE_EVIDENCE_V1_CANDIDATE.pine"
)

PARENTS = {"MCX": MCX_PARENT, "NSE": NSE_PARENT}
CANDIDATES = {"MCX": MCX_CANDIDATE, "NSE": NSE_CANDIDATE}
EXPECTED_PARENT_SHA = {
    "MCX": "59f35175ea0c666fbadef00e6861f42e3c75b858a66891e3908657fd4bb0245d",
    "NSE": "f7a5098b6c406303686a110849ba93c2a505ffa3e9bd2d6ba77b038aa1639a43",
}


def _parts(product: str) -> tuple[bytes, str]:
    parent = PARENTS[product].read_bytes()
    candidate = CANDIDATES[product].read_bytes()
    marker = f"// KRONOS SWING V1 — MAIN SLICE 4D-V {product} VISIBLE EVIDENCE PANEL"
    delimiter = ("\n//==================================================================\n" + marker).encode()
    boundary = candidate.index(delimiter)
    analytical_source = candidate[:boundary]
    expected = parent.decode("utf-8")
    prefix = "kr4b" if product == "MCX" else "kr4c"
    for helper in ("Available", "Integrity", "Value"):
        expected = re.sub(
            rf"^string ({prefix}{helper}\([^\n]+=>)",
            r"\1",
            expected,
            flags=re.MULTILINE,
        )
    assert analytical_source == expected.encode("utf-8")
    panel = candidate[boundary:].decode("utf-8")
    return parent, panel


def _row_labels(product: str) -> tuple[str, ...]:
    _, panel = _parts(product)
    return tuple(
        match.group(1)
        for match in re.finditer(r'kr4dvCell\(\d+, "([A-Z0-9_ ]+)"', panel)
    )


def _normalized(labels: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        "PRODUCT_CONTEXT_" + label.rsplit("_", 1)[-1]
        if label.startswith(("MCX_CONTEXT_", "NSE_CONTEXT_"))
        else label
        for label in labels
    )


@pytest.mark.parametrize("product", ("MCX", "NSE"))
def test_closed_projection_is_preserved_except_compile_only_helper_syntax(
    product: str,
) -> None:
    parent, _ = _parts(product)
    assert sha256(parent).hexdigest() == EXPECTED_PARENT_SHA[product]


@pytest.mark.parametrize("product", ("MCX", "NSE"))
def test_no_explicit_return_type_precedes_any_added_function(product: str) -> None:
    source = CANDIDATES[product].read_text(encoding="utf-8")
    invalid = re.findall(
        r"^(?:string|bool|int|float|color|void) "
        r"(?:kr4b|kr4c|kr4dv)[A-Za-z0-9_]*\([^)]*\) =>",
        source,
        re.MULTILINE,
    )
    assert invalid == []


@pytest.mark.parametrize("product", ("MCX", "NSE"))
def test_panel_contract_identity_and_candidate_provenance(product: str) -> None:
    _, panel = _parts(product)
    assert VISIBLE_PINE_PANEL_CONTRACT_ID in panel
    assert f'kr4dvPanelVersion = "{VISIBLE_PINE_PANEL_VERSION}"' in panel
    assert f'kr4dvProduct = "{product}"' in panel
    assert (
        f'kr4dvPublisherRole = "{VISIBLE_PINE_PANEL_PUBLISHER_ROLE}"' in panel
    )
    assert "SHADOW_ONLY" in panel
    for label in (
        "PANEL_SCHEMA",
        "PANEL_VERSION",
        "PRODUCT",
        "PINE_IDENTITY",
        "PINE_VERSION",
        "PINE_BUILD",
        "PUBLISHER_ROLE",
        "CANONICAL_INSTR",
        "TIMEFRAME",
        "OBS_BOUNDARY",
        "BOUNDARY_STATE",
    ):
        assert label in panel


@pytest.mark.parametrize("product", ("MCX", "NSE"))
def test_panel_has_fixed_two_column_top_right_geometry(product: str) -> None:
    _, panel = _parts(product)
    assert "const int kr4dvRows = 37" in panel
    assert "table.new(position.top_right, 2, kr4dvRows" in panel
    assert "table.set_position(kr705Panel, position.bottom_right)" in panel
    assert "scroll" not in panel.lower()
    assert "text_size=size.tiny" in panel
    assert "width=12" in panel and "width=42" in panel


@pytest.mark.parametrize("product", ("MCX", "NSE"))
def test_fixed_row_order_has_no_dynamic_disappearance(product: str) -> None:
    labels = _row_labels(product)
    assert len(labels) == 37
    assert len(set(labels)) == 37
    assert _normalized(labels) == VISIBLE_PINE_PANEL_ROW_ORDER


@pytest.mark.parametrize("product", ("MCX", "NSE"))
def test_fourteen_domain_rows_and_required_subfields_are_present(product: str) -> None:
    _, panel = _parts(product)
    labels = _normalized(_row_labels(product))
    assert all(label in labels for label in VISIBLE_PINE_PANEL_DOMAIN_ROWS)
    for required in (
        "HH=",
        "HL=",
        "LH=",
        "LL=",
        "BOS=",
        "CHOCH=",
        "SWING HIGH=",
        "SWING LOW=",
        "RANGE HIGH=",
        "RANGE LOW=",
        "BREAK DIR=",
        "BREAK ACCEPT=",
        "SLOPE=",
        "PRICE RELATION=",
        "INTERACTION=",
        "ACCEPT=",
        "BODY=",
        "UWICK=",
        "LWICK=",
        "CLOSE LOC=",
        "NORM RANGE=",
        "CLOSE PRESS=",
        "VOL REF=",
        "VOL STATE=",
        "PARTICIPATION=",
        "VOL MODE=",
        "CP=",
        "TC=",
        "BC=",
        "REF SUP=",
        "REF RES=",
        "REF HIGH=",
        "REF LOW=",
        "REF REL=",
        "BARRIER TYPE=",
        "BARRIER PX=",
        "BARRIER REL=",
        "BARRIER STATE=",
    ):
        assert required in panel


@pytest.mark.parametrize("product", ("MCX", "NSE"))
def test_missing_boundary_and_enum_tokens_are_textual(product: str) -> None:
    _, panel = _parts(product)
    for token in VISIBLE_PINE_MISSING_TOKENS:
        assert f'"{token}"' in panel
    for state in ("COMPLETED", "DEVELOPING", "UNKNOWN"):
        assert f'"{state}"' in panel
    for token in (
        "BULLISH",
        "BEARISH",
        "NEUTRAL",
        "MIXED",
        "YES",
        "NO",
        "NONE",
        "COMPRESSED",
        "NOT_RANGE",
        "BREAKOUT",
        "BREAKDOWN",
        "RISING",
        "FALLING",
        "FLAT",
        "ABOVE",
        "BELOW",
        "AT",
    ):
        assert f'"{token}"' in panel


@pytest.mark.parametrize("product", ("MCX", "NSE"))
def test_numeric_formatting_is_fixed_and_missing_safe(product: str) -> None:
    _, panel = _parts(product)
    assert "str.tostring(value, format.mintick)" in panel
    assert 'str.tostring(value, "#.000")' in panel
    assert "na(value) ? kr4dvUnavailable" in panel


@pytest.mark.parametrize("product", ("MCX", "NSE"))
def test_semantics_are_not_colour_only(product: str) -> None:
    _, panel = _parts(product)
    helper = panel[panel.index("kr4dvCell(int row") : panel.index("kr4dvRender()")]
    assert helper.count("table.cell(") == 2
    assert "label" in helper and "value" in helper
    assert "text_color=foreground" in helper
    assert not re.search(r"value\s*==.*color|color.*value\s*==", helper)


def test_mcx_extension_is_isolated() -> None:
    _, panel = _parts("MCX")
    for field in (
        "ANALYSIS ID=",
        "REF MARKET=",
        "REF TF=",
        "REF STATE=",
        "REF ALIGN=",
        "READINESS=",
        "NOW=",
        "PRODUCT=MCX",
    ):
        assert field in panel
    assert not re.search(r"NIFTY|BANKNIFTY|SECTOR STATE|MARKET STATE", panel)


def test_nse_extension_is_isolated_and_self_reference_safe() -> None:
    _, panel = _parts("NSE")
    for field in (
        "ANALYSIS ID=",
        "CHART SYMBOL=",
        "SECTOR=",
        "PARENT=",
        "SECTOR STATE=",
        "MARKET STATE=",
        "REF ALIGN=",
        "REF COMPLETE=",
        "READINESS=",
        "NOW=NOT_APPLICABLE",
        "PRODUCT=NSE",
    ):
        assert field in panel
    assert "selfReference = relationshipIsNSEIndex" in panel
    assert not re.search(r"COMEX|NYMEX|commodity workstation|BUY NOW|SELL NOW", panel, re.I)


def test_known_truth_fixtures_match_panel_topology_and_products() -> None:
    fixtures = (MCX_VISIBLE_PANEL_KNOWN_TRUTH, NSE_VISIBLE_PANEL_KNOWN_TRUTH)
    for fixture in fixtures:
        labels = tuple(row.label for row in fixture.rows)
        assert labels == _row_labels(fixture.product.value)
        assert fixture.publisher_role == "CANDIDATE"
        assert fixture.pine_owned_domains == VISIBLE_PINE_PANEL_DOMAIN_ROWS
        assert fixture.rows[9].value == fixture.timeframe
        assert fixture.rows[11].value == fixture.boundary_state.value
        assert fixture.rows[3].value == fixture.product.value


@pytest.mark.parametrize("product", ("MCX", "NSE"))
def test_appended_panel_has_no_analytical_webhook_or_openai_dependency(
    product: str,
) -> None:
    _, panel = _parts(product)
    executable = re.sub(r'"(?:[^"\\]|\\.)*"', '""', panel)
    executable = re.sub(r"//.*", "", executable)
    assert not re.search(
        r"\b(?:request\.security|ta\.[a-z_]+|plot[a-z_]*|strategy\.[a-z_]+|"
        r"alert|alertcondition)\s*\(",
        executable,
    )
    assert not re.search(r"webhook|https?://|openai|api[_-]?key", executable, re.I)
    assert "input." not in executable


@pytest.mark.parametrize("product", ("MCX", "NSE"))
def test_panel_is_presentation_only_and_preserves_analytical_prefix(product: str) -> None:
    parent, panel = _parts(product)
    assert sha256(parent).hexdigest() == EXPECTED_PARENT_SHA[product]
    assert ":=" not in panel
    assert "table." in panel
    assert "outKR380AReadinessContract.readinessState" in panel
    assert "outKR380CurrentPineStateContractInstance.integrity.currentStatus" in panel
