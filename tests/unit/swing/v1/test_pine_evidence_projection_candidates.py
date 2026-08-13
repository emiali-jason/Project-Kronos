"""Static acceptance checks for Main Slice 4B/4C Pine projections.

TradingView does not provide a local Pine compiler.  These tests prove that
each controlled candidate has the frozen source as its exact byte prefix and
that its appended publication-only block conforms to the frozen V1.1 field
surface without introducing analytical or transport calls.
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import re

import pytest

from kronos.swing.v1.pine_evidence import (
    PINE_EVIDENCE_CONTRACT_ID,
    PINE_EVIDENCE_CONTRACT_VERSION,
    PineEvidenceDomain,
)


ROOT = Path(__file__).resolve().parents[4]
MCX_CANDIDATE = ROOT / (
    "research/swing/pine-publication/candidates/4B-MCX/"
    "KRONOS_FUTURES_V2_PINE_EVIDENCE_V1_1_CANDIDATE.pine"
)
NSE_CANDIDATE = ROOT / (
    "research/swing/pine-publication/candidates/4C-NSE/"
    "KRONOS_NSE_V1_SR1_PINE_EVIDENCE_V1_1_CANDIDATE.pine"
)

MARKERS = {
    "MCX": "// KRONOS SWING V1 — MAIN SLICE 4B MCX PINE EVIDENCE PROJECTION",
    "NSE": "// KRONOS SWING V1 — MAIN SLICE 4C NSE PINE EVIDENCE PROJECTION",
}

BASELINES = {
    "MCX": (
        356_587,
        "d3048aa6d0f6f3a97585a4cc35d36d5839352d91ec8ff05d5989a495d341d54a",
    ),
    "NSE": (
        350_567,
        "33ddbdd416d905bf4cb925d45d08d9d4efccfe6db969b668d5101164c96b48f2",
    ),
}

CANDIDATES = {"MCX": MCX_CANDIDATE, "NSE": NSE_CANDIDATE}

EXPECTED_DERIVATIONS = {
    "MCX": {
        PineEvidenceDomain.CHART_INSTRUMENT_IDENTITY: "DIRECT",
        PineEvidenceDomain.CHART_TIMEFRAME_IDENTITY: "DIRECT",
        PineEvidenceDomain.PRICE_STRUCTURE: "DERIVED",
        PineEvidenceDomain.VISIBLE_SWINGS: "EXPOSURE",
        PineEvidenceDomain.RANGE_OR_CONSOLIDATION: "DERIVED",
        PineEvidenceDomain.BREAKOUT_OR_BREAKDOWN: "DERIVED",
        PineEvidenceDomain.SMA20: "DERIVED",
        PineEvidenceDomain.SMA50: "DERIVED",
        PineEvidenceDomain.SMA200: "DERIVED",
        PineEvidenceDomain.CANDLE_ACCEPTANCE: "DERIVED",
        PineEvidenceDomain.VOLUME_CONTEXT: "DERIVED",
        PineEvidenceDomain.REFERENCE_LEVELS: "DERIVED",
        PineEvidenceDomain.BARRIERS: "DERIVED",
        PineEvidenceDomain.PINE_DISPLAY: "EXPOSURE",
    },
    "NSE": {
        PineEvidenceDomain.CHART_INSTRUMENT_IDENTITY: "DIRECT",
        PineEvidenceDomain.CHART_TIMEFRAME_IDENTITY: "DIRECT",
        PineEvidenceDomain.PRICE_STRUCTURE: "EXPOSURE",
        PineEvidenceDomain.VISIBLE_SWINGS: "EXPOSURE",
        PineEvidenceDomain.RANGE_OR_CONSOLIDATION: "DERIVED",
        PineEvidenceDomain.BREAKOUT_OR_BREAKDOWN: "DERIVED",
        PineEvidenceDomain.SMA20: "DERIVED",
        PineEvidenceDomain.SMA50: "DERIVED",
        PineEvidenceDomain.SMA200: "DERIVED",
        PineEvidenceDomain.CANDLE_ACCEPTANCE: "DERIVED",
        PineEvidenceDomain.VOLUME_CONTEXT: "DERIVED",
        PineEvidenceDomain.REFERENCE_LEVELS: "DERIVED",
        PineEvidenceDomain.BARRIERS: "DERIVED",
        PineEvidenceDomain.PINE_DISPLAY: "EXPOSURE",
    },
}


def _candidate_parts(product: str) -> tuple[bytes, str]:
    data = CANDIDATES[product].read_bytes()
    baseline_size, _ = BASELINES[product]
    marker = MARKERS[product]
    projection = data[baseline_size:].decode("utf-8")
    assert marker in projection
    return data[:baseline_size], projection


def _product_extension(product: str) -> str:
    _, projection = _candidate_parts(product)
    start = projection.index("// Product-only projection.")
    end = projection.index(
        f"// END OF MAIN SLICE 4{'B MCX' if product == 'MCX' else 'C NSE'} "
        "PINE EVIDENCE PROJECTION"
    )
    return projection[start:end]


@pytest.mark.parametrize("product", ("MCX", "NSE"))
def test_frozen_baseline_is_exact_candidate_prefix(product: str) -> None:
    prefix, _ = _candidate_parts(product)
    _, expected_sha = BASELINES[product]
    assert sha256(prefix).hexdigest() == expected_sha


@pytest.mark.parametrize("product", ("MCX", "NSE"))
def test_projection_declares_v11_candidate_shadow_metadata(product: str) -> None:
    _, projection = _candidate_parts(product)
    for required in (
        PINE_EVIDENCE_CONTRACT_ID,
        PINE_EVIDENCE_CONTRACT_VERSION,
        f'const string kr4{product == "NSE" and "c" or "b"}Product = "{product}"',
        '"CANDIDATE"',
        '"SHADOW_ONLY"',
        '"IMPLEMENTATION_CHANGE_CONTRACT_COMPATIBLE"',
        '"POLICY_UNRESOLVED"',
        "PublisherRegistryId",
        "PineIdentity",
        "PineVersion",
        "PineBuild",
        "PineSourceSha256",
        "EvidenceContractId",
        "EvidenceContractVersion",
    ):
        assert required in projection


@pytest.mark.parametrize("product", ("MCX", "NSE"))
def test_projection_has_exactly_the_fourteen_pine_owned_domains(product: str) -> None:
    _, projection = _candidate_parts(product)
    observed = re.findall(
        r'KRSwingV1PineEvidenceField4[BC]\.new\(\s*\n\s*"([A-Z0-9_]+)"',
        projection,
    )
    assert observed == [domain.value for domain in PineEvidenceDomain]


@pytest.mark.parametrize("product", ("MCX", "NSE"))
def test_projection_field_schema_matches_v11_contract(product: str) -> None:
    _, projection = _candidate_parts(product)
    expected = (
        "question_id",
        "availability",
        "state",
        "value",
        "values",
        "source_engine",
        "source_fields",
        "derivation",
        "integrity",
        "boundary_state",
        "provenance",
    )
    declaration = projection.split("const string", maxsplit=1)[0]
    assert tuple(re.findall(r"\bstring ([a-z_]+)", declaration)) == expected


@pytest.mark.parametrize("product", ("MCX", "NSE"))
def test_projection_derivation_class_is_explicit(product: str) -> None:
    _, projection = _candidate_parts(product)
    for domain, derivation in EXPECTED_DERIVATIONS[product].items():
        pattern = rf'"{domain.value}"[\s\S]*?"{derivation}"'
        match = re.search(pattern, projection)
        assert match is not None, domain
        assert match.start() < projection.find(
            f'"{list(PineEvidenceDomain)[list(PineEvidenceDomain).index(domain) + 1].value}"'
        ) if domain is not list(PineEvidenceDomain)[-1] else True


@pytest.mark.parametrize("product", ("MCX", "NSE"))
def test_projection_adds_no_analytical_engine_or_transport_calls(product: str) -> None:
    _, projection = _candidate_parts(product)
    executable = re.sub(r'"(?:[^"\\]|\\.)*"', '""', projection)
    executable = re.sub(r"//.*", "", executable)
    prohibited_calls = re.findall(
        r"\b(?:alert|alertcondition|request\.security|input\.[a-z_]+|"
        r"ta\.[a-z_]+|plot[a-z_]*|strategy\.[a-z_]+)\s*\(",
        executable,
    )
    numeric_thresholds = re.findall(r"(?:>=|<=|>|<)\s*-?\d+(?:\.\d+)?", executable)
    assert prohibited_calls == []
    assert numeric_thresholds == []


def test_product_extension_publication_outputs_are_semantically_isolated() -> None:
    mcx_extension = _product_extension("MCX")
    nse_extension = _product_extension("NSE")

    assert "kr4bMcxProductContext" in mcx_extension
    assert "relationshipIsMCXMetals or relationshipIsMCXEnergy" in mcx_extension
    assert re.search(
        r"\b(?:NSE|NIFTY|BANKNIFTY|SECTOR|NOT_IN_NSE_V1)\b",
        mcx_extension,
        re.I,
    ) is None
    assert "kr4c" not in mcx_extension

    assert "kr4cNseProductContext" in nse_extension
    assert "relationshipIsNSEEquity or relationshipIsNSEIndex" in nse_extension
    assert re.search(
        r"\b(?:MCX|COMEX|NYMEX|COMMODITY|NOWTRIGGEREVIDENCE)\b",
        nse_extension,
        re.I,
    ) is None
    assert "kr4b" not in nse_extension


def test_mcx_product_extension_is_projection_only() -> None:
    projection = _product_extension("MCX")
    for field in (
        "kr4bCommodityAnalyticalIdentity",
        "kr4bReferenceSymbol",
        "kr4bReferenceMarket",
        "kr4bReferenceTimeframeStates",
        "kr4bReadinessReferenceContext",
        "kr4bCommodityWorkstationSemantics",
        "kr4bNowTriggerEvidence",
    ):
        assert field in projection
    for assignment in re.findall(r"string (kr4b\w+) = (.+)", projection):
        field, expression = assignment
        if field != "kr4bReferenceMarket":
            assert "kr4bMcxProductContext" in expression, field


def test_nse_product_extension_is_projection_only_and_now_is_not_applicable() -> None:
    projection = _product_extension("NSE")
    for field in (
        "kr4cCashAnalysisSymbol",
        "kr4cFuturesToUnderlyingProvenance",
        "kr4cSectorIndex",
        "kr4cParentIndex",
        "kr4cSectorContext",
        "kr4cBroadMarketContext",
        "kr4cRelativeAlignment",
        "kr4cReferenceCompleteness",
        "kr4cReadinessContext",
        "kr4cOpportunitySemantics",
        "kr4cReadinessReductionSemantics",
    ):
        assert field in projection
    for assignment in re.findall(r"string (kr4c\w+) = (.+)", projection):
        field, expression = assignment
        if field not in {"kr4cNowAvailability", "kr4cNowState"}:
            assert "kr4cNseProductContext" in expression, field
    assert 'kr4cNowAvailability = "NOT_APPLICABLE"' in projection
    assert 'kr4cNowState = "NOT_IN_NSE_V1"' in projection
