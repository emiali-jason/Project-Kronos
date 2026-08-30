from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
import json
from pathlib import Path

import pytest

from kronos.instrument.visual_identity import (
    VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1,
    VisualIdentityRelationshipStatus,
    VisualIdentityResolver,
    VisualIdentitySourceContext,
    create_visual_identity_publication,
    create_visual_identity_relationship,
)
from kronos.intraday.mcx_commissioning import McxCommissioningState, load_mcx_commissioning_publication
from kronos.intraday.review import ReviewError
from kronos.intraday.review_mcx_paired import (
    MCX_MACHINE_RSI_AUTHORITY,
    MCX_PAIRED_QUESTIONS,
    MCX_PAIRED_VISUAL_TIMEFRAMES,
    NATIVE_MACHINE_REGIME_TIMEFRAME,
    REFERENCE_RSI_AUTHORITY,
    ChartSide,
    ReferenceSeriesKind,
    bind_native_identity,
    create_paired_chart_bundle,
    create_paired_chart_revision,
    create_paired_review_pack,
    relationship_for_subject,
)
from kronos.intraday.review_mcx_paired_answer import (
    bind_mcx_paired_import,
    parse_mcx_paired_answer,
)
from kronos.intraday.review_mcx_paired_persistence import IntradayMcxPairedReviewStore
from kronos.intraday.review_mcx_paired_transport import create_paired_transport
from instrument.test_active_derivative_selection import _resolve
from .test_probables_v2 import _opening_inputs
from .test_review import _png
from .test_review_v2 import _application


def _resolver(canonical: str, visible: str, boundary: datetime, *, duplicate: bool = False) -> VisualIdentityResolver:
    relationships = [create_visual_identity_relationship(
        canonical_subject_identity=canonical,
        observed_visible_subject_identity=visible,
        source_context=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
        effective_from=boundary - timedelta(days=2),
        effective_through=boundary + timedelta(days=2),
        status=VisualIdentityRelationshipStatus.ACTIVE,
        source_identity="TEST-TRADINGVIEW",
        provenance=("WO-10-SLICE-5", "TEST"),
        supersedes=None,
    )]
    if duplicate:
        relationships.append(create_visual_identity_relationship(
            canonical_subject_identity=canonical,
            observed_visible_subject_identity=visible,
            source_context=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
            effective_from=boundary - timedelta(days=1),
            effective_through=boundary + timedelta(days=1),
            status=VisualIdentityRelationshipStatus.ACTIVE,
            source_identity="TEST-TRADINGVIEW-DUPLICATE",
            provenance=("WO-10-SLICE-5", "TEST-DUPLICATE"),
            supersedes=None,
        ))
    return VisualIdentityResolver(create_visual_identity_publication(
        canonical_subject_identities=(canonical,),
        publication_identity=VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1,
        publication_version="1.0.0",
        effective_from=boundary - timedelta(days=2),
        effective_through=boundary + timedelta(days=2),
        source_identities=("WO-10-SLICE-5-TEST",),
        provenance=("DOMAIN-001", "TEST"),
        relationships=tuple(relationships),
        supersedes=None,
        schema_identity=VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1,
    ))


def _foundation(tmp_path: Path):  # type: ignore[no-untyped-def]
    *_, mapping = _opening_inputs(subject="MCX-SUBJECT-GOLDM", subject_exchange="MCX")
    run, v2 = _application(tmp_path / "v2", mapping)
    cycle = v2.create_eligible_cycles(run)[0]
    active = _resolve(cycle.analysis_boundary).for_subject("GOLDM").binding
    assert active is not None
    native_binding = bind_native_identity(cycle, active, roll_history_identity="MCX-ROLL-HISTORY:GOLDM")
    relationship = relationship_for_subject(cycle.canonical_subject_identity)
    native_payload, reference_payload = _png(30), _png(60)
    native_visible = f"MCX:{active.provider_symbol}"
    native_chart = create_paired_chart_revision(
        payload=native_payload, side=ChartSide.NATIVE_MCX,
        review_cycle_identity=cycle.cycle_identity,
        expected_subject_identity=cycle.canonical_subject_identity,
        expected_visible_identity=native_visible, venue="MCX", series_kind=None,
        listed_contract_identity=None, observation_boundary=cycle.analysis_boundary,
        media_type="image/png", revision_ordinal=1,
        received_at=cycle.analysis_boundary + timedelta(seconds=1),
    )
    reference_chart = create_paired_chart_revision(
        payload=reference_payload, side=ChartSide.INTERNATIONAL_REFERENCE,
        review_cycle_identity=cycle.cycle_identity,
        expected_subject_identity=relationship.reference_analytical_subject_identity,
        expected_visible_identity=relationship.governed_visible_identity,
        venue=relationship.venue.value, series_kind=relationship.series_kind,
        listed_contract_identity=None, observation_boundary=cycle.analysis_boundary,
        media_type="image/png", revision_ordinal=1,
        received_at=cycle.analysis_boundary + timedelta(seconds=2),
    )
    bundle = create_paired_chart_bundle(
        cycle=cycle, native_binding=native_binding, native_chart=native_chart,
        reference_chart=reference_chart, reference_relationship=relationship,
    )
    pack = create_paired_review_pack(bundle, created_at=cycle.analysis_boundary + timedelta(seconds=3))
    return cycle, active, native_payload, reference_payload, native_chart, reference_chart, bundle, pack


def _completed_answer(pack, bundle, native_visible: str) -> bytes:  # type: ignore[no-untyped-def]
    _, _, template = create_paired_transport(
        pack=pack, bundle=bundle, native_chart_payload=_png(30),
        reference_chart_payload=_png(60), generated_at=pack.created_at,
    )
    document = json.loads(template)
    document["native_observed_visible_identity"] = native_visible
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode()


def test_exact_five_relationships_and_natgas_remains_held() -> None:
    expected = {
        "MCX-SUBJECT-GOLDM": ("REFERENCE-SUBJECT-COMEX-GOLD", "COMEX:GC1!"),
        "MCX-SUBJECT-SILVERM": ("REFERENCE-SUBJECT-COMEX-SILVER", "COMEX:SI1!"),
        "MCX-SUBJECT-COPPER": ("REFERENCE-SUBJECT-COMEX-COPPER", "COMEX:HG1!"),
        "MCX-SUBJECT-CRUDE": ("REFERENCE-SUBJECT-NYMEX-CRUDE-OIL", "NYMEX:CL1!"),
        "MCX-SUBJECT-NATGAS": ("REFERENCE-SUBJECT-NYMEX-NATURAL-GAS", "NYMEX:NG1!"),
    }
    for subject, pair in expected.items():
        relationship = relationship_for_subject(subject)
        assert (relationship.reference_analytical_subject_identity, relationship.governed_visible_identity) == pair
        assert relationship.series_kind is ReferenceSeriesKind.CONTINUOUS
    assert load_mcx_commissioning_publication().subject("MCX-SUBJECT-NATGAS").state is McxCommissioningState.HELD


def test_paired_bundle_is_independent_contract_bound_and_four_hour_is_not_one_hour(tmp_path: Path) -> None:
    cycle, active, _, _, native, reference, bundle, _ = _foundation(tmp_path)
    assert native.chart_revision_identity != reference.chart_revision_identity
    assert bundle.native_identity_binding.actual_derivative_contract_identity == active.active_binding.derivative_contract_id
    assert bundle.native_identity_binding.active_binding_identity == active.binding_identity
    assert bundle.native_identity_binding.active_binding_supersedes == active.active_binding.supersedes
    assert native.timeframes == reference.timeframes == MCX_PAIRED_VISUAL_TIMEFRAMES
    assert "4H" in native.timeframes and NATIVE_MACHINE_REGIME_TIMEFRAME == "1H"
    with pytest.raises(ReviewError):
        create_paired_chart_revision(
            payload=_png(90), side=ChartSide.NATIVE_MCX,
            review_cycle_identity=cycle.cycle_identity,
            expected_subject_identity=cycle.canonical_subject_identity,
            expected_visible_identity="MCX:GOLDM", venue="MCX", series_kind=None,
            listed_contract_identity=None, observation_boundary=cycle.analysis_boundary,
            media_type="image/png", revision_ordinal=1,
            received_at=cycle.analysis_boundary, timeframes=("1D", "1H", "15M", "5M"),
        )


def test_wrong_reference_pair_and_continuous_listed_confusion_fail_closed(tmp_path: Path) -> None:
    cycle, _, _, _, native, reference, bundle, _ = _foundation(tmp_path)
    wrong = relationship_for_subject("MCX-SUBJECT-COPPER")
    with pytest.raises(ReviewError):
        create_paired_chart_bundle(
            cycle=cycle, native_binding=bundle.native_identity_binding,
            native_chart=native, reference_chart=reference,
            reference_relationship=wrong,
        )
    with pytest.raises(ReviewError):
        replace(reference, series_kind=ReferenceSeriesKind.LISTED_CONTRACT, listed_contract_identity=None)


def test_question_successor_is_independent_and_has_no_global_or_trading_fields() -> None:
    assert len(MCX_PAIRED_QUESTIONS) == 17
    assert tuple(item.question_id for item in MCX_PAIRED_QUESTIONS[:10]) == tuple(f"M{i:02d}" for i in range(1, 11))
    assert tuple(item.question_id for item in MCX_PAIRED_QUESTIONS[10:16]) == tuple(f"R{i:02d}" for i in range(1, 7))
    assert MCX_PAIRED_QUESTIONS[-1].observation == "MATERIAL_UNCAPTURED_VISUAL_OBSERVATION"
    serialized = json.dumps([item.observation for item in MCX_PAIRED_QUESTIONS])
    for forbidden in ("GLOBAL_MCX_COHERENCE", "PROMOTION_READY", "ENTRY", "STOP", "TARGET", "R:R"):
        assert forbidden not in serialized
    assert MCX_MACHINE_RSI_AUTHORITY == "EXTERNAL_CANONICAL_NUMERICAL_AUTHORITY"
    assert REFERENCE_RSI_AUTHORITY == "VISUAL_CONTEXT_ONLY"


def test_strict_answer_import_preserves_raw_identities_and_domain001_resolution(tmp_path: Path) -> None:
    cycle, _, _, _, native, reference, bundle, pack = _foundation(tmp_path)
    payload = _completed_answer(pack, bundle, native.expected_visible_identity)
    answer = parse_mcx_paired_answer(payload)
    evidence = bind_mcx_paired_import(
        pack=pack, bundle=bundle, native_chart=native, reference_chart=reference,
        answer=answer,
        native_resolver=_resolver(cycle.canonical_subject_identity, native.expected_visible_identity, cycle.analysis_boundary),
        reference_resolver=_resolver(bundle.reference_relationship.reference_analytical_subject_identity, reference.expected_visible_identity, cycle.analysis_boundary),
        imported_at=cycle.analysis_boundary + timedelta(seconds=4),
    )
    assert evidence.native_observed_visible_identity == native.expected_visible_identity
    assert evidence.reference_observed_visible_identity == "COMEX:GC1!"
    assert evidence.native_resolution.canonical_subject_identity == "MCX-SUBJECT-GOLDM"
    assert evidence.reference_resolution.canonical_subject_identity == "REFERENCE-SUBJECT-COMEX-GOLD"
    assert evidence.actual_derivative_contract_identity == bundle.native_identity_binding.actual_derivative_contract_identity
    store = IntradayMcxPairedReviewStore((tmp_path / "import-store").resolve())
    store.retain_answer(answer, payload)
    store.retain_evidence(evidence)
    assert store.load_answer(answer.answer_pack_identity) == answer
    assert store.load_evidence(evidence.visual_evidence_identity) == evidence

    document = json.loads(payload)
    document["GLOBAL_MCX_COHERENCE"] = "SUPPORTIVE"
    with pytest.raises(ReviewError):
        parse_mcx_paired_answer(json.dumps(document).encode())
    document.pop("GLOBAL_MCX_COHERENCE")
    document["native_answers"][0]["question_id"] = "M02"
    with pytest.raises(ReviewError):
        parse_mcx_paired_answer(json.dumps(document).encode())


def test_identity_mismatch_and_ambiguous_relationship_fail_closed(tmp_path: Path) -> None:
    cycle, _, _, _, native, reference, bundle, pack = _foundation(tmp_path)
    payload = _completed_answer(pack, bundle, native.expected_visible_identity)
    answer = parse_mcx_paired_answer(payload)
    wrong = _resolver("MCX-SUBJECT-COPPER", native.expected_visible_identity, cycle.analysis_boundary)
    with pytest.raises(ReviewError):
        bind_mcx_paired_import(
            pack=pack, bundle=bundle, native_chart=native, reference_chart=reference,
            answer=answer, native_resolver=wrong,
            reference_resolver=_resolver(bundle.reference_relationship.reference_analytical_subject_identity, reference.expected_visible_identity, cycle.analysis_boundary),
            imported_at=cycle.analysis_boundary + timedelta(seconds=4),
        )
    ambiguous = _resolver(cycle.canonical_subject_identity, native.expected_visible_identity, cycle.analysis_boundary, duplicate=True)
    with pytest.raises(Exception, match="VISUAL_IDENTITY_RELATIONSHIP_AMBIGUOUS"):
        ambiguous.resolve(
            observed_visible_subject_identity=native.expected_visible_identity,
            source_context=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
            governed_observation_boundary=cycle.analysis_boundary,
        )


def test_immutable_persistence_idempotency_explicit_reload_and_changed_chart_identity(tmp_path: Path) -> None:
    _, _, native_payload, reference_payload, native, reference, bundle, pack = _foundation(tmp_path)
    store = IntradayMcxPairedReviewStore((tmp_path / "review-mcx-paired-v1").resolve())
    assert store.retain_chart(native, native_payload) == store.retain_chart(native, native_payload)
    store.retain_chart(reference, reference_payload)
    assert store.retain_bundle(bundle) == store.retain_bundle(bundle)
    assert store.retain_pack(pack) == store.retain_pack(pack)
    assert store.load_chart(native.chart_revision_identity) == native
    assert store.load_bundle(bundle.bundle_identity) == bundle
    assert store.load_pack(pack.review_pack_identity) == pack
    assert "review-mcx-paired-v1" in str(store.root)
    with pytest.raises(ReviewError):
        store.load_bundle("INTRADAY-MCX-PAIRED-CHART-BUNDLE-NOT-LATEST")
    bundle_path = store.root / "paired-bundles" / f"{bundle.bundle_identity}.json"
    bundle_path.write_bytes(bundle_path.read_bytes() + b" ")
    with pytest.raises(ReviewError):
        store.retain_bundle(bundle)
    changed = create_paired_chart_revision(
        payload=_png(31), side=native.side, review_cycle_identity=native.review_cycle_identity,
        expected_subject_identity=native.expected_subject_identity,
        expected_visible_identity=native.expected_visible_identity, venue=native.venue,
        series_kind=None, listed_contract_identity=None,
        observation_boundary=native.observation_boundary, media_type=native.media_type,
        revision_ordinal=2, received_at=native.received_at + timedelta(seconds=1),
    )
    assert changed.chart_revision_identity != native.chart_revision_identity
    assert changed.chart_artifact_identity != native.chart_artifact_identity


def test_transport_retains_both_charts_and_exact_strict_answer_template(tmp_path: Path) -> None:
    _, _, native_payload, reference_payload, _, _, bundle, pack = _foundation(tmp_path)
    transport, pdf, template = create_paired_transport(
        pack=pack, bundle=bundle, native_chart_payload=native_payload,
        reference_chart_payload=reference_payload, generated_at=pack.created_at,
    )
    assert pdf.startswith(b"%PDF")
    document = json.loads(template)
    assert document["schema_identity"] == "KRONOS-INTRADAY-MCX-PAIRED-ANSWER-PACK-V1"
    assert [item["question_id"] for item in document["native_answers"]] == [item.question_id for item in MCX_PAIRED_QUESTIONS[:10]]
    assert [item["question_id"] for item in document["reference_answers"]] == [item.question_id for item in MCX_PAIRED_QUESTIONS[10:16]]
    store = IntradayMcxPairedReviewStore((tmp_path / "transport-store").resolve())
    store.retain_transport(transport, pdf, template)
    assert store.load_transport(transport.transport_identity) == transport
