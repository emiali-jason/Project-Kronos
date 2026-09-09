"""Registry-driven MCX qualification; synthetic NGAS admission is test-only.

No test publishes NATURALGASU2026 authority or commissions production NATGAS.
Sponsor labels are Answer fixtures, never inferred from Provider month codes.
"""
from datetime import datetime
import json

import pytest

from kronos.application.intraday_review_v2_paired import IntradayReviewV2PairedAdapter
from kronos.intraday import mcx_commissioning as commissioning
from kronos.intraday.review import ReviewError, ReviewFailure
from kronos.intraday.review_mcx_paired import (
    MCX_REFERENCE_RELATIONSHIPS, relationship_for_subject,
)
from kronos.intraday.review_mcx_paired_persistence import IntradayMcxPairedReviewStore
from kronos.instrument.visual_identity import VisualIdentityResolutionError
from kronos.instrument.visual_identity_persistence import load_visual_identity_resolver
from .test_review_v2_paired_intake import paired_fixture, complete_paired
from .test_review_mcx_paired import _resolver
from .test_review import _png
from .test_probables_v2 import _opening_inputs, _run
from .test_review_v2 import _application


# NGAS is Sponsor vocabulary; NATGAS is the existing exact governed subject.
CASES = (
    ('CRUDE', 'MCX-FUT-CRUDE-2026-09-21', 'NYMEX:CL1!', 'CRUDEOILU2026', 'CLV2026'),
    ('NATGAS', 'MCX-FUT-NATGAS-2026-09-25', 'NYMEX:NG1!', 'NATURALGASU2026', 'NGV2026'),
)


@pytest.fixture
def synthetic_commissioning(monkeypatch):
    """Condition future intake on admission, without modifying real governance."""
    before = commissioning.load_mcx_commissioning_publication()
    assert before.subject('MCX-SUBJECT-NATGAS').state is commissioning.McxCommissioningState.HELD
    with monkeypatch.context() as scoped:
        scoped.setattr(commissioning, '_QUALIFICATION_BINDINGS', tuple(
            (subject, commissioning.McxCommissioningState.COMMISSIONED,
             'TEST-ONLY-NGAS-PAIRED-QUALIFICATION-NOT-PRODUCTION')
            if subject == 'MCX-SUBJECT-NATGAS' else (subject, state, evidence)
            for subject, state, evidence in commissioning._QUALIFICATION_BINDINGS
        ))
        yield
    assert commissioning.load_mcx_commissioning_publication() == before


@pytest.fixture(params=CASES, ids=('CRUDE', 'NGAS'))
def paired_case(request, tmp_path, synthetic_commissioning):
    family, contract, continuous, native, reference = request.param
    app, cycle, metadata = paired_fixture(tmp_path, family=family, visible=native)
    # These fixture relationships are prospective visual-authority prerequisites,
    # not new production publications or historical relationships.
    app._clock = lambda: datetime.fromisoformat('2026-09-06T06:00:00+00:00')
    app._paired.native_resolver = _resolver(contract, native, app._clock())
    return app, cycle, metadata, request.param


def test_both_commodities_use_identical_intake_pack_and_import(paired_case):
    app, cycle, metadata, (family, contract, continuous, native, reference) = paired_case
    assert type(app._paired) is IntradayReviewV2PairedAdapter
    assert cycle.canonical_subject_identity == f'MCX-SUBJECT-{family}'
    binding = app._paired.validate_metadata(cycle, metadata)
    assert binding.canonical_subject_id == cycle.canonical_subject_identity
    assert binding.observation_boundary == cycle.analysis_boundary
    assert binding.active_binding.derivative_contract_id == contract
    assert metadata == {
        'native_binding_identity': binding.binding_identity,
        'native_contract_identity': contract,
        'reference_context_identity': continuous,
    }
    assert relationship_for_subject(cycle.canonical_subject_identity).governed_visible_identity == continuous
    # The Provider spelling never substitutes for an observed TradingView label.
    assert binding.provider_symbol != native
    chart = app.upload_chart(cycle.cycle_identity, payload=_png(4), media_type='image/png', paired_metadata=metadata)
    assert chart.revision_ordinal == 4
    assert chart.timeframe_set == ('1D', '4H', '15M', '5M')
    bundle, native_chart, reference_chart = app._paired.restore(cycle, chart)
    assert reference_chart.listed_contract_identity is None
    assert bundle.reference_relationship.governed_visible_identity == continuous
    question = app.create_individual_question_transport(cycle.cycle_identity)
    document = json.loads(question.answer_template_path.read_bytes())
    assert document['schema_identity'] == 'KRONOS-INTRADAY-MCX-PAIRED-ANSWER-PACK-V1'
    assert document['native_observed_visible_identity'].startswith('REPLACE_')
    assert document['reference_observed_visible_identity'].startswith('REPLACE_')
    pack = app._paired.retained(cycle, chart)[3]
    for side in ('NATIVE_MCX', 'INTERNATIONAL_REFERENCE'):
        timeframes = {q.timeframe for q in pack.questions if q.side == side}
        assert timeframes == {'1D', '4H', '15M', '5M', 'MULTI'}
        assert '1H' not in timeframes
    complete_paired(app, question, native=native, reference=reference)
    result = app.import_expected_answer(cycle.cycle_identity)
    assert (result.imported_count, result.rejected_count) == (0, 1)
    assert result.members[0].reason == ReviewFailure.CHART_CORRESPONDENCE_UNVERIFIABLE.value
    from tests.unit.intraday.chart_input_fixtures import retain_legacy_paired_fixture
    retain_legacy_paired_fixture(app, cycle, chart)
    assert app.import_expected_answer(cycle.cycle_identity).already_imported_count == 1
    evidence = app._paired.store.load_evidence_for_pack(pack.review_pack_identity)
    assert evidence.native_observed_visible_identity == native
    assert evidence.native_resolution.canonical_subject_identity == contract
    assert evidence.reference_observed_visible_identity == reference
    assert evidence.reference_expected_visible_identity == continuous
    assert evidence.reference_resolution is None
    assert evidence.reference_constituent_relationship == 'NOT_ESTABLISHED'
    assert evidence.reference_role == 'SUPPORTING_ONLY'
    assert all(r.observed_visible_subject_identity != reference
               for r in app._paired.native_resolver.publication.relationships)
    restored = IntradayMcxPairedReviewStore(app._paired.store.root)
    assert restored.load_evidence_for_pack(pack.review_pack_identity) == evidence
    assert restored.load_bundle(bundle.bundle_identity) == bundle
    from kronos.browser.intraday_views import _review_v2_candidate
    html = _review_v2_candidate(app.snapshot().candidates[0], 1)
    assert contract in html and continuous in html and reference in html
    assert 'IMPORT EXPECTED ANSWER' in html


@pytest.mark.parametrize('field,value', (
    ('reference_context_identity', 'COMEX:GC1!'),
    ('reference_context_identity', 'UNKNOWN'),
    ('native_contract_identity', 'MCX-FUT-COPPER-2026-09-30'),
    ('native_binding_identity', 'ACTIVE-DERIVATIVE-BINDING-FOREIGN'),
))
def test_cross_commodity_or_unknown_metadata_rejects(paired_case, field, value):
    app, cycle, metadata, _ = paired_case
    before = app.review_store.load_current_chart(cycle.cycle_identity)
    with pytest.raises(ReviewError):
        app.upload_chart(cycle.cycle_identity, payload=_png(4), media_type='image/png',
                         paired_metadata={**metadata, field: value})
    assert app.review_store.load_current_chart(cycle.cycle_identity) == before


@pytest.mark.parametrize('wrong_native', ('REFERENCE_LISTED', 'REFERENCE_CONTINUOUS', 'FOREIGN_NATIVE', 'WRONG_EXPIRY'))
def test_observed_native_must_independently_match(paired_case, wrong_native):
    app, cycle, metadata, (family, contract, continuous, native, reference) = paired_case
    observed = {'REFERENCE_LISTED': reference, 'REFERENCE_CONTINUOUS': continuous,
                'FOREIGN_NATIVE': 'GOLDU2026', 'WRONG_EXPIRY': native.replace('U2026', 'M2026')}[wrong_native]
    app.upload_chart(cycle.cycle_identity, payload=_png(4), media_type='image/png', paired_metadata=metadata)
    question = app.create_individual_question_transport(cycle.cycle_identity)
    complete_paired(app, question, native=observed, reference=reference)
    result = app.import_expected_answer(cycle.cycle_identity)
    assert (result.imported_count, result.rejected_count) == (0, 1)
    assert result.members[0].reason == 'VISUAL_IDENTITY_RELATIONSHIP_UNAVAILABLE'


def test_resolved_but_wrong_native_contract_rejects(paired_case):
    app, cycle, metadata, (family, contract, continuous, native, reference) = paired_case
    other = next(c for c in CASES if c[0] != family)
    app._paired.native_resolver = _resolver(other[1], native, app._clock())
    app.upload_chart(cycle.cycle_identity, payload=_png(4), media_type='image/png', paired_metadata=metadata)
    question = app.create_individual_question_transport(cycle.cycle_identity)
    complete_paired(app, question, native=native, reference=reference)
    result = app.import_expected_answer(cycle.cycle_identity)
    assert result.rejected_count == 1 and result.imported_count == 0
    assert result.members[0].reason == ReviewFailure.ANSWER_IDENTITY_MISMATCH.value


@pytest.mark.parametrize('relationship', MCX_REFERENCE_RELATIONSHIPS,
                         ids=lambda item: item.canonical_mcx_subject_identity)
def test_every_registered_subject_uses_its_own_binding_and_context(tmp_path, synthetic_commissioning, relationship):
    family = relationship.canonical_mcx_subject_identity.removeprefix('MCX-SUBJECT-')
    app, cycle, metadata = paired_fixture(tmp_path, family=family)
    binding = app._paired.validate_metadata(cycle, metadata)
    assert binding.canonical_subject_id == relationship.canonical_mcx_subject_identity
    assert metadata['reference_context_identity'] == relationship.governed_visible_identity
    chart = app.upload_chart(cycle.cycle_identity, payload=_png(4), media_type='image/png', paired_metadata=metadata)
    bundle, _, reference = app._paired.restore(cycle, chart)
    assert bundle.reference_relationship == relationship
    assert reference.listed_contract_identity is None
    assert chart.timeframe_set == ('1D', '4H', '15M', '5M')


def test_ngas_remains_held_without_synthetic_prerequisite(tmp_path):
    publication = commissioning.load_mcx_commissioning_publication()
    assert publication.subject('MCX-SUBJECT-NATGAS').state is commissioning.McxCommissioningState.HELD
    mapping = _opening_inputs(subject='MCX-SUBJECT-NATGAS', subject_exchange='MCX')[-1]
    run, app = _application(tmp_path, mapping)
    assert app.create_eligible_cycles(run) == ()
    # No production visual-contract relationship is invented by fixture coverage.
    resolver = load_visual_identity_resolver(publication_version='1.4.0')
    with pytest.raises(VisualIdentityResolutionError):
        resolver.resolve(observed_visible_subject_identity='NATURALGASU2026',
            source_context=resolver.publication.relationships[0].source_context,
            governed_observation_boundary=datetime.fromisoformat('2026-09-06T06:00:00+00:00'))
