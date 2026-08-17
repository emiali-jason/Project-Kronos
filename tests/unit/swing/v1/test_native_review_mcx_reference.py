from dataclasses import replace
from pathlib import Path

import pytest

from kronos.application.swing_native_review import NativeReviewWorkflow
from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.mtf_facts import FactualTimeframe
from kronos.swing.v1.native_discovery import (
    Native1DState,
    Native1HState,
    Native1WState,
    Native4HState,
    NativeAnchor,
    NativeAnchorType,
    NativeContextKind,
    NativeDiscoveryStatus,
    NativeOpportunityIdentity,
    NativeProductPath,
    discover_native_mtf,
)
from kronos.swing.v1.native_review import (
    MCX_REFERENCE_MAPPINGS,
    McxReferenceEvidenceState,
    McxReferenceStatus,
    NativeLayer2EvidenceState,
    NativeReviewEvidenceStore,
    bind_mcx_reference_evidence,
    build_native_review_requirements,
    unavailable_mcx_reference,
)
from kronos.swing.v1.pine_evidence import ReferenceMarket, build_pine_layer2_handoff
from tests.fixtures.swing_v1_pine_evidence import MCX_PRODUCTION_COMPLETED, MCX_REGISTRY
from tests.unit.application.test_swing_mtf_facts import _build as _mtf_build
from tests.unit.swing.v1.test_native_review import _layer2


def _run_with_probables(*instruments: str):  # type: ignore[no-untyped-def]
    facts, _ = _mtf_build()
    base = discover_native_mtf(facts)
    selected = set(instruments)
    assessments = []
    for item in base.assessments:
        if item.canonical_instrument not in selected:
            assessments.append(
                replace(
                    item,
                    status=NativeDiscoveryStatus.NO_CURRENT_OPPORTUNITY,
                    context_kind=None,
                    opportunity_identity=None,
                    operative_anchor=None,
                )
            )
            continue
        boundary = facts.instrument(item.canonical_instrument).fact(
            FactualTimeframe.FOUR_HOUR
        ).observation_boundary
        assessments.append(
            replace(
                item,
                product_path=NativeProductPath.MCX,
                direction=V1Direction.LONG,
                weekly_state=Native1WState.NOT_APPLICABLE,
                daily_state=Native1DState.BULLISH_SWING_REGIME,
                four_hour_state=Native4HState.STRUCTURAL_HOLD,
                one_hour_state=Native1HState.NEUTRAL,
                status=NativeDiscoveryStatus.PROBABLE,
                context_kind=NativeContextKind.ESTABLISHED_TREND,
                opportunity_identity=NativeOpportunityIdentity.ESTABLISHED_TREND_STRUCTURAL_HOLD,
                operative_anchor=NativeAnchor(
                    NativeAnchorType.FOUR_HOUR_RADIUS_2_STRUCTURE, 100.0, boundary
                ),
                result_sha256=("a" if len(selected) == 1 else "c") * 64,
            )
        )
    return facts, replace(base, assessments=tuple(assessments), result_sha256="b" * 64)


@pytest.mark.parametrize(
    ("instrument", "identity", "market", "symbol"),
    (
        ("GOLDM", "COMEX Gold", ReferenceMarket.COMEX, "COMEX:GC1!"),
        ("SILVERM", "COMEX Silver", ReferenceMarket.COMEX, "COMEX:SI1!"),
        ("COPPER", "COMEX Copper", ReferenceMarket.COMEX, "COMEX:HG1!"),
        ("CRUDEOIL", "NYMEX Crude Oil", ReferenceMarket.NYMEX, "NYMEX:CL1!"),
        ("NATURALGAS", "NYMEX Natural Gas", ReferenceMarket.NYMEX, "NYMEX:NG1!"),
    ),
)
def test_probable_creates_only_approved_demand_driven_reference(
    instrument: str, identity: str, market: ReferenceMarket, symbol: str
) -> None:
    facts, run = _run_with_probables(instrument)
    requirement = build_native_review_requirements(run, facts)[0]
    reference = requirement.mcx_reference
    assert reference is not None
    assert (reference.reference_subject_identity, reference.reference_market, reference.reference_symbol) == (
        identity, market, symbol
    )
    assert MCX_REFERENCE_MAPPINGS[instrument] == (identity, market, symbol)


def test_multiple_probables_request_only_corresponding_references() -> None:
    facts, run = _run_with_probables("GOLDM", "CRUDEOIL")
    requirements = build_native_review_requirements(run, facts)
    assert {item.canonical_instrument for item in requirements} == {"GOLDM", "CRUDEOIL"}
    assert {item.mcx_reference.reference_symbol for item in requirements if item.mcx_reference} == {
        "COMEX:GC1!", "NYMEX:CL1!"
    }


def test_non_probable_mcx_and_nse_probable_do_not_create_reference() -> None:
    facts, run = _run_with_probables("GOLDM")
    gold = next(item for item in run.assessments if item.canonical_instrument == "GOLDM")
    forming = replace(
        gold, status=NativeDiscoveryStatus.FORMING_WATCH,
        context_kind=None, opportunity_identity=None, operative_anchor=None,
    )
    changed = replace(run, assessments=tuple(forming if item is gold else item for item in run.assessments))
    assert build_native_review_requirements(changed, facts) == ()

    from tests.unit.swing.v1.test_native_review import _evidence_run
    nse_facts, nse_run, _ = _evidence_run()
    assert build_native_review_requirements(nse_run, nse_facts)[0].mcx_reference is None


@pytest.mark.parametrize(
    "state",
    (McxReferenceEvidenceState.SUPPORTS, McxReferenceEvidenceState.NEUTRAL,
     McxReferenceEvidenceState.CONTRADICTS),
)
def test_valid_reference_state_is_retained_without_rewriting_native_thesis(state) -> None:  # type: ignore[no-untyped-def]
    facts, run = _run_with_probables("GOLDM")
    requirement = build_native_review_requirements(run, facts)[0]
    handoff = build_pine_layer2_handoff(MCX_PRODUCTION_COMPLETED, MCX_REGISTRY)
    result = bind_mcx_reference_evidence(
        requirement, handoff,
        native_run_identity=run.run_identity,
        mcx_canonical_instrument="GOLDM",
        chart_revision_sha256="d" * 64,
        expected_chart_revision_sha256="d" * 64,
        expected_timeframe=handoff.timeframe,
        evidence_state=state,
    )
    assert result.status is McxReferenceStatus.ANALYZED
    assert result.evidence_state is state
    assert result.requirement.native_assessment_sha256 == requirement.thesis.native_assessment_sha256
    assert result.requirement.direction is requirement.thesis.direction


@pytest.mark.parametrize(
    "mismatch", ("run", "instrument", "symbol", "market", "revision", "timeframe")
)
def test_wrong_reference_binding_is_invalid(mismatch: str) -> None:
    facts, run = _run_with_probables("GOLDM")
    requirement = build_native_review_requirements(run, facts)[0]
    handoff = build_pine_layer2_handoff(MCX_PRODUCTION_COMPLETED, MCX_REGISTRY)
    run_id = run.run_identity
    instrument = "GOLDM"
    expected_revision = "d" * 64
    expected_timeframe = handoff.timeframe
    if mismatch == "run":
        run_id = "SWING-RUN-" + "F" * 32
    elif mismatch == "instrument":
        instrument = "SILVERM"
    elif mismatch == "symbol":
        handoff = replace(handoff, mcx=replace(handoff.mcx, reference_symbol="COMEX:SI1!"))
    else:
        if mismatch == "market":
            handoff = replace(handoff, mcx=replace(handoff.mcx, reference_market=ReferenceMarket.NYMEX))
        elif mismatch == "revision":
            expected_revision = "e" * 64
        else:
            expected_timeframe = "D"
    result = bind_mcx_reference_evidence(
        requirement, handoff, native_run_identity=run_id,
        mcx_canonical_instrument=instrument, chart_revision_sha256="d" * 64,
        expected_chart_revision_sha256=expected_revision,
        expected_timeframe=expected_timeframe,
        evidence_state=McxReferenceEvidenceState.SUPPORTS,
    )
    assert result.status is McxReferenceStatus.INVALID
    assert result.evidence_state is McxReferenceEvidenceState.INVALID


def test_missing_reference_is_unavailable_and_restart_restores_immutable_result(tmp_path: Path) -> None:
    facts, run = _run_with_probables("GOLDM")
    workflow = NativeReviewWorkflow(NativeReviewEvidenceStore(tmp_path))
    prepared = workflow.prepare(run, facts)
    workflow.ingest_layer2(
        _layer2(prepared.requirements[0], NativeLayer2EvidenceState.SUPPORTS_NATIVE_THESIS)
    )
    missing = unavailable_mcx_reference(prepared.requirements[0])
    workflow.ingest_reference(missing)
    assert workflow.snapshot().layer2_records[0].mcx_reference_result == missing

    restored = NativeReviewWorkflow(NativeReviewEvidenceStore(tmp_path)).restore(run, facts)
    assert restored.reference_results == (missing,)
    assert missing.reference_evidence_sha256 is None


def test_orphaned_reference_result_fails_closed(tmp_path: Path) -> None:
    facts, run = _run_with_probables("GOLDM")
    requirement = build_native_review_requirements(run, facts)[0]
    result = unavailable_mcx_reference(requirement)
    with pytest.raises(ValueError, match="ORPHANED"):
        NativeReviewEvidenceStore(tmp_path).retain_reference_result(result)
