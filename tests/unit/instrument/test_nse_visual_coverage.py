"""Evidence-supported NSE publication; unsupported aliases remain unavailable."""
from dataclasses import replace
from datetime import datetime, timedelta
import json
from pathlib import Path

import pytest

from kronos.instrument.visual_identity import (
    VisualIdentityResolver, VisualIdentityResolutionError, VisualIdentitySourceContext,
    create_visual_identity_relationship, create_visual_identity_publication,
    encode_visual_identity_publication, parse_visual_identity_publication,
    VISUAL_IDENTITY_NSE_COVERAGE_VERSION,
)
from kronos.instrument.visual_identity_persistence import (
    load_visual_identity_resolver, resolver_for_retained_publication,
)

ROOT = Path(__file__).resolve().parents[3] / 'data/instruments'
AUDIT = json.loads((ROOT / 'KRONOS-GOVERNED-VISUAL-IDENTITY-RELATIONSHIP-PUBLICATION-V1/1.5.0-coverage.json').read_bytes())
BOUNDARY = datetime.fromisoformat(AUDIT['review_boundary'])
CANONICAL = tuple(x['canonical_id'] for x in json.loads((ROOT / 'KRONOS-CANONICAL-INSTRUMENT-CATALOGUE-V2/1.2.0.json').read_bytes())['semantic_objects'])


def resolver():
    return load_visual_identity_resolver(publication_version=VISUAL_IDENTITY_NSE_COVERAGE_VERSION)


def resolve(label, at=BOUNDARY, source=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART):
    return resolver().resolve(observed_visible_subject_identity=label,
        source_context=source, governed_observation_boundary=at)


@pytest.mark.parametrize('row', AUDIT['coverage'], ids=lambda r:r['canonical_identity'])
def test_every_current_nse_identity_has_truthful_explicit_coverage(row):
    publication = resolver().publication
    relationships = [x for x in publication.relationships if x.canonical_subject_identity == row['canonical_identity']]
    assert bool(relationships) == row['candidate_relationship_published']
    assert len(relationships) == len(row['relationships'])
    if relationships:
        for relationship in relationships:
            result = resolve(relationship.observed_visible_subject_identity)
            assert result.canonical_subject_identity == row['canonical_identity']
            assert result.relationship_identity == relationship.relationship_identity
            assert result.publication_integrity_identity == AUDIT['publication_integrity']
    else:
        # Neither catalogue canonical identity nor expected exchange symbol is a visual alias.
        for unregistered in (row['canonical_identity'], row['expected_tradingview_symbol']):
            with pytest.raises(VisualIdentityResolutionError, match='UNAVAILABLE'):
                resolve(unregistered)


def test_exact_counts_and_new_labels_have_independent_chart_provenance():
    rows = AUDIT['coverage']
    assert len(rows) == 93
    assert sum(r['candidate_relationship_published'] for r in rows) == 49
    assert sum(not r['candidate_relationship_published'] for r in rows) == 44
    old = load_visual_identity_resolver(publication_version='1.3.0').publication
    current = resolver().publication
    assert len(current.relationships) == 49 and len(old.relationships) == 14
    assert current.relationships[:14] == old.relationships
    assert current.supersedes == old.integrity_identity
    for relationship in current.relationships[14:]:
        source = next(r for r in AUDIT['new_chart_sources'] if r['canonical_identity'] == relationship.canonical_subject_identity)
        assert source['exact_visible_label'] == relationship.observed_visible_subject_identity
        assert relationship.effective_from.isoformat() == source['effective_from']
        assert 'CHART-SHA256-' + source['chart_sha256'] in relationship.provenance
        assert relationship.effective_from >= datetime.fromisoformat(source['retained_at'])


@pytest.mark.parametrize('label,canonical', [('Adani Green Energy Limited','NSE-EQ-ADANIGREEN'),
    ('Mahindra & Mahindra Ltd.','NSE-EQ-M&M'),('Nifty Bank Index','NSE-INDEX-BANKNIFTY')])
def test_operational_labels_resolve_without_rewriting_raw_identity(label, canonical):
    result = resolve(label)
    assert result.observed_visible_subject_identity == label
    assert result.canonical_subject_identity == canonical


@pytest.mark.parametrize('label', ['Nifty 50','NIFTY','M&M','Mahindra and Mahindra Ltd.',
    'Mahindra & Mahindra Ltd','adani green energy limited','Adani Green Energy Limited ',
    'ADANIGREEN','NSE-EQ-ADANIGREEN','Unknown Company','BANKNIFTY'])
def test_no_inferred_alias_case_punctuation_or_ticker_fallback(label):
    with pytest.raises(VisualIdentityResolutionError, match='UNAVAILABLE'):
        resolve(label)


@pytest.mark.parametrize('row', AUDIT['new_chart_sources'], ids=lambda r:r['canonical_identity'])
def test_relationship_effective_boundary_is_enforced(row):
    # Preserved relationships keep their original interval; new ones use the chart evidence interval.
    matches = [x for x in resolver().publication.relationships if x.canonical_subject_identity == row['canonical_identity']]
    relationship = matches[0]
    start = relationship.effective_from
    assert resolve(relationship.observed_visible_subject_identity, start).canonical_subject_identity == row['canonical_identity']
    with pytest.raises(VisualIdentityResolutionError):
        resolve(relationship.observed_visible_subject_identity, start-timedelta(microseconds=1))


def test_wrong_source_and_outside_publication_interval_rejected():
    with pytest.raises(VisualIdentityResolutionError, match='UNAVAILABLE'):
        resolve('Adani Green Energy Limited', source='PROVIDER_INSTRUMENT_MASTER')
    with pytest.raises(VisualIdentityResolutionError, match='STALE'):
        resolve('Adani Green Energy Limited', datetime.fromisoformat('2020-01-01T00:00:00+00:00'))


def test_duplicate_conflicting_ambiguous_and_tampered_publications():
    pub = resolver().publication
    first = pub.relationships[14]
    with pytest.raises(VisualIdentityResolutionError, match='INTEGRITY'):
        replace(pub, relationships=pub.relationships+(first,))
    from dataclasses import asdict
    fields = asdict(first)
    fields.pop('relationship_identity');fields.pop('integrity_identity')
    fields['canonical_subject_identity'] = 'NSE-EQ-M&M'
    conflict = create_visual_identity_relationship(**fields)
    values = asdict(pub);values.pop('integrity_identity');values['relationships'] = pub.relationships+(conflict,)
    with pytest.raises(VisualIdentityResolutionError, match='INTEGRITY'):
        create_visual_identity_publication(canonical_subject_identities=CANONICAL, **values)
    fields['canonical_subject_identity'] = first.canonical_subject_identity
    fields['source_identity'] = 'SECOND-EXPLICIT-SOURCE'
    duplicate_meaning = create_visual_identity_relationship(**fields)
    values['relationships'] = pub.relationships+(duplicate_meaning,)
    ambiguous = create_visual_identity_publication(canonical_subject_identities=CANONICAL, **values)
    with pytest.raises(VisualIdentityResolutionError, match='AMBIGUOUS'):
        VisualIdentityResolver(ambiguous).resolve(observed_visible_subject_identity=first.observed_visible_subject_identity,
            source_context=first.source_context, governed_observation_boundary=BOUNDARY)
    payload = encode_visual_identity_publication(pub).replace(b'Adani Green Energy Limited',b'Wrong Company')
    with pytest.raises(VisualIdentityResolutionError, match='INTEGRITY'):
        parse_visual_identity_publication(payload, canonical_subject_identities=CANONICAL)


@pytest.mark.parametrize('version', ['1.0.0','1.1.0','1.3.0','1.4.0'])
def test_exact_historical_authority_remains_loadable(version):
    old = load_visual_identity_resolver(publication_version=version)
    chosen = resolver_for_retained_publication(resolver(),
        publication_identity=old.publication.publication_identity,
        publication_version=version, publication_integrity_identity=old.publication.integrity_identity)
    assert chosen.publication == old.publication
    with pytest.raises(VisualIdentityResolutionError, match='INTEGRITY'):
        resolver_for_retained_publication(resolver(), publication_identity=old.publication.publication_identity,
            publication_version=version, publication_integrity_identity='TAMPERED')


def test_current_authority_does_not_fallback_on_unknown_label():
    with pytest.raises(VisualIdentityResolutionError): resolve('CRUDEOILU2026')
    with pytest.raises(VisualIdentityResolutionError, match='INTEGRITY'):
        resolver_for_retained_publication(resolver(), publication_identity='OTHER',
            publication_version='1.3.0',publication_integrity_identity='OTHER')


@pytest.mark.parametrize('version', ['../1.3.0','UNKNOWN','99.0.0'])
def test_retained_publication_selection_rejects_unknown_or_path_versions(version):
    current = resolver().publication
    with pytest.raises(VisualIdentityResolutionError, match='INTEGRITY'):
        resolver_for_retained_publication(resolver(), publication_identity=current.publication_identity,
            publication_version=version, publication_integrity_identity=current.integrity_identity)
