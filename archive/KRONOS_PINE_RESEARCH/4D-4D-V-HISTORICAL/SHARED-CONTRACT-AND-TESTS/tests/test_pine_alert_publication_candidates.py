"""Qualification for Main Slice 4D Pine-side alert publication."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re

import pytest

from kronos.swing.v1.pine_evidence import (
    PINE_EVIDENCE_CONTRACT_ID,
    PINE_EVIDENCE_CONTRACT_VERSION,
    PINE_EVIDENCE_INTERNAL_MAX_BYTES,
    PineEvidenceDomain,
    canonical_serialize,
    validate_pine_evidence_payload,
)
from tests.fixtures.swing_v1_pine_evidence import (
    canonical_mcx_fixture,
    canonical_nse_fixture,
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
    "research/swing/pine-publication/candidates/4D-MCX/"
    "KRONOS_FUTURES_V2_PINE_EVIDENCE_V1_1_ALERT_CANDIDATE.pine"
)
NSE_CANDIDATE = ROOT / (
    "research/swing/pine-publication/candidates/4D-NSE/"
    "KRONOS_NSE_V1_SR1_PINE_EVIDENCE_V1_1_ALERT_CANDIDATE.pine"
)

PARENTS = {"MCX": MCX_PARENT, "NSE": NSE_PARENT}
CANDIDATES = {"MCX": MCX_CANDIDATE, "NSE": NSE_CANDIDATE}
EXPECTED_PARENT_SHA = {
    "MCX": "59f35175ea0c666fbadef00e6861f42e3c75b858a66891e3908657fd4bb0245d",
    "NSE": "f7a5098b6c406303686a110849ba93c2a505ffa3e9bd2d6ba77b038aa1639a43",
}
MARKERS = {
    "MCX": "MAIN SLICE 4D MCX STRUCTURED ALERT PUBLICATION",
    "NSE": "MAIN SLICE 4D NSE STRUCTURED ALERT PUBLICATION",
}


def _parts(product: str) -> tuple[bytes, str]:
    parent = PARENTS[product].read_bytes()
    candidate = CANDIDATES[product].read_bytes()
    assert candidate.startswith(parent)
    publication = candidate[len(parent) :].decode("utf-8")
    assert MARKERS[product] in publication
    return parent, publication


def _wire_fixture(product: str, *, worst_case: bool = False) -> dict[str, object]:
    envelope = canonical_mcx_fixture() if product == "MCX" else canonical_nse_fixture()
    payload = json.loads(canonical_serialize(envelope))
    payload["event_id"] = None
    if worst_case:
        escaped = '\\\"\n\r\t' * 4
        payload["identity"]["execution_subject"] = escaped
        payload["provenance"]["calculation_basis"] = escaped
        for field in payload["evidence"]:
            field["state"] = escaped
            if field["value"] is not None:
                field["value"] = escaped
            field["values"] = [escaped, escaped, escaped, escaped]
    return payload


@pytest.mark.parametrize("product", ("MCX", "NSE"))
def test_sponsor_validated_parent_is_exact_candidate_prefix(product: str) -> None:
    parent, _ = _parts(product)
    assert sha256(parent).hexdigest() == EXPECTED_PARENT_SHA[product]


@pytest.mark.parametrize("product", ("MCX", "NSE"))
def test_runtime_payload_uses_frozen_contract_and_candidate_role(product: str) -> None:
    _, publication = _parts(product)
    assert PINE_EVIDENCE_CONTRACT_ID in publication
    assert PINE_EVIDENCE_CONTRACT_VERSION in publication
    assert '\\"publisher_role\\":\\"CANDIDATE\\"' in publication
    assert "SHADOW_ONLY" in publication
    assert "IMPLEMENTATION_CHANGE_CONTRACT_COMPATIBLE" in publication
    assert "ApprovedPineRegistry" not in publication


@pytest.mark.parametrize("product", ("MCX", "NSE"))
def test_all_fourteen_domains_are_serialized_once_in_frozen_order(product: str) -> None:
    _, publication = _parts(product)
    prefix = "kr4b" if product == "MCX" else "kr4c"
    variables = {
        PineEvidenceDomain.CHART_INSTRUMENT_IDENTITY: "InstrumentIdentity",
        PineEvidenceDomain.CHART_TIMEFRAME_IDENTITY: "TimeframeIdentity",
        PineEvidenceDomain.PRICE_STRUCTURE: "PriceStructure",
        PineEvidenceDomain.VISIBLE_SWINGS: "VisibleSwings",
        PineEvidenceDomain.RANGE_OR_CONSOLIDATION: "RangeOrConsolidation",
        PineEvidenceDomain.BREAKOUT_OR_BREAKDOWN: "BreakoutOrBreakdown",
        PineEvidenceDomain.SMA20: "Sma20",
        PineEvidenceDomain.SMA50: "Sma50",
        PineEvidenceDomain.SMA200: "Sma200",
        PineEvidenceDomain.CANDLE_ACCEPTANCE: "CandleAcceptance",
        PineEvidenceDomain.VOLUME_CONTEXT: "VolumeContext",
        PineEvidenceDomain.REFERENCE_LEVELS: "ReferenceLevels",
        PineEvidenceDomain.BARRIERS: "Barriers",
        PineEvidenceDomain.PINE_DISPLAY: "PineDisplay",
    }
    positions = []
    for domain in PineEvidenceDomain:
        token = f"FieldJson({prefix}{variables[domain]},"
        assert publication.count(token) == 1
        positions.append(publication.index(token))
    assert positions == sorted(positions)


@pytest.mark.parametrize("product", ("MCX", "NSE"))
def test_wire_fixture_is_valid_deterministic_json(product: str) -> None:
    payload = _wire_fixture(product)
    first = canonical_serialize(payload)
    second = canonical_serialize(deepcopy(payload))
    assert first == second
    assert json.loads(first) == payload
    assert payload["contract_id"] == PINE_EVIDENCE_CONTRACT_ID
    assert payload["contract_version"] == PINE_EVIDENCE_CONTRACT_VERSION
    assert payload["event_id"] is None
    assert [item["question_id"] for item in payload["evidence"]] == [
        item.value for item in PineEvidenceDomain
    ]


@pytest.mark.parametrize("product", ("MCX", "NSE"))
def test_null_event_id_is_the_only_frozen_envelope_semantic_difference(
    product: str,
) -> None:
    envelope = canonical_mcx_fixture() if product == "MCX" else canonical_nse_fixture()
    canonical = json.loads(canonical_serialize(envelope))
    wire = _wire_fixture(product)
    assert wire | {"event_id": envelope.event_id} == canonical
    wire["event_id"] = envelope.event_id
    assert validate_pine_evidence_payload(wire).valid


@pytest.mark.parametrize("product", ("MCX", "NSE"))
def test_normal_and_qualified_worst_case_payloads_fit_internal_budget(product: str) -> None:
    representative = len(canonical_serialize(_wire_fixture(product)))
    worst_case = len(canonical_serialize(_wire_fixture(product, worst_case=True)))
    assert representative < worst_case < PINE_EVIDENCE_INTERNAL_MAX_BYTES


@pytest.mark.parametrize("product", ("MCX", "NSE"))
def test_runtime_has_hard_payload_budget_gate(product: str) -> None:
    _, publication = _parts(product)
    assert "const int kr4dInternalPayloadBudget = 16384" in publication
    assert re.search(
        r"str\.length\(kr4d(?:Mcx|Nse)Payload\) <= kr4dInternalPayloadBudget",
        publication,
    )
    assert re.search(
        r"kr4d(?:Mcx|Nse)PayloadWithinBudget\s*$",
        publication,
        re.MULTILINE,
    )


@pytest.mark.parametrize("product", ("MCX", "NSE"))
def test_json_string_escaping_is_ordered_and_complete(product: str) -> None:
    _, publication = _parts(product)
    escape_block = publication[
        publication.index("string kr4dJsonEscape") : publication.index(
            "string kr4dJsonString(string"
        )
    ]
    replacements = re.findall(r"str\.replace_all", escape_block)
    assert len(replacements) == 5
    assert escape_block.index('value, "\\\\"') < escape_block.index('value, "\\\""')
    for escaped in ('"\\n"', '"\\r"', '"\\t"'):
        assert escaped in escape_block


@pytest.mark.parametrize("product", ("MCX", "NSE"))
def test_unavailable_and_not_applicable_wire_handling_is_explicit(product: str) -> None:
    _, publication = _parts(product)
    assert 'valueJson = available and field.value != ""' in publication
    assert ': "null"' in publication
    assert 'valuesJson = available ?' in publication
    assert ': "[]"' in publication
    if product == "NSE":
        assert 'kr4dContextJson("NOT_APPLICABLE", "NOT_IN_NSE_V1"' in publication


def test_product_specific_payloads_are_isolated() -> None:
    _, mcx = _parts("MCX")
    _, nse = _parts("NSE")
    assert '\\"mcx\\":' in mcx and '\\"nse\\":null' in mcx
    assert not re.search(
        r"cash_analysis_symbol|sector_context|parent_index|relative_alignment|"
        r"NIFTY|BANKNIFTY|NOT_IN_NSE_V1",
        mcx,
    )
    assert '\\"mcx\\":null' in nse and '\\"nse\\":' in nse
    assert not re.search(
        r"COMEX|NYMEX|commodity_workstation|now_trigger_evidence|"
        r"reference_market|reference_symbol",
        nse,
        re.I,
    )


@pytest.mark.parametrize("product", ("MCX", "NSE"))
def test_event_identity_inputs_are_present_without_arrival_time(product: str) -> None:
    _, publication = _parts(product)
    for required in (
        "event_id\\\":null",
        "sequence_number",
        "source_period_identity",
        "chart_bar_open_ts",
        "chart_bar_close_ts",
        "pine_source_sha256",
        "tradingview_symbol",
        "canonical_instrument",
        "evidence",
    ):
        assert required in publication
    assert "arrival" not in publication.lower()


@pytest.mark.parametrize("product", ("MCX", "NSE"))
def test_completed_boundary_publication_is_single_and_duplicate_protected(
    product: str,
) -> None:
    _, publication = _parts(product)
    assert "barstate.isrealtime and barstate.isconfirmed" in publication
    executable = re.sub(r"//.*", "", publication)
    assert executable.count("alert(") == 1
    assert "alert.freq_once_per_bar_close" in publication
    assert "LastPublishedBarClose" in publication
    assert "LastPublishedBarClose != time_close" in publication
    assert "LastPublishedBarClose := time_close" in publication
    assert '"NON_FINAL_NOT_PUBLISHED"' in publication
    assert '"UNKNOWN_NOT_PUBLISHED"' in publication
    assert (
        'barstate.isconfirmed ? "COMPLETED" : barstate.isrealtime ? '
        '"DEVELOPING" : "UNKNOWN"'
    ) in publication


@pytest.mark.parametrize("product", ("MCX", "NSE"))
def test_source_sha_is_required_but_not_self_embedded(product: str) -> None:
    _, publication = _parts(product)
    assert 'CandidateSha256 = input.string(""' in publication
    assert "str.length(" in publication
    assert "CandidateSha256) == 64" in publication
    assert "CandidateShaReady" in publication


@pytest.mark.parametrize("product", ("MCX", "NSE"))
def test_publication_appends_no_analytical_calculation(product: str) -> None:
    _, publication = _parts(product)
    executable = re.sub(r'"(?:[^"\\]|\\.)*"', '""', publication)
    executable = re.sub(r"//.*", "", executable)
    prohibited = re.findall(
        r"\b(?:request\.security|ta\.[a-z_]+|plot[a-z_]*|strategy\.[a-z_]+)\s*\(",
        executable,
    )
    thresholds = re.findall(r"(?:>=|<=|>|<)\s*-?\d+(?:\.\d+)?", executable)
    assert prohibited == []
    assert thresholds == []


@pytest.mark.parametrize("product", ("MCX", "NSE"))
def test_payload_source_contains_no_secret_or_credential_fields(product: str) -> None:
    _, publication = _parts(product)
    assert not re.search(
        r"api[_-]?key|access[_-]?token|refresh[_-]?token|password|broker|account|"
        r"authorization|cookie|webhook[_-]?(?:secret|token)",
        publication,
        re.I,
    )
