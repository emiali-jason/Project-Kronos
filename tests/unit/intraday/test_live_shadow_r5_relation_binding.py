"""Exact R5 authority fixtures; offline validation and disposable-store IO only."""
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from kronos.intraday.live_shadow import ShadowError
from kronos.intraday.live_shadow_epochs import EpochStore, document
from kronos.intraday.live_shadow_transition import validate_successor_relation
from kronos.intraday.population_measurement import canonical


FIXTURES = Path(__file__).resolve().parents[2] / 'fixtures/intraday/wo06h_r5_relation_binding'
REVIEW_SHA256 = 'e5d63954815ffa526390e1d5d0e668a8c490371ead305c85a14b43d6c300c58e'
PERSISTED_SHA256 = '707ca654076df91af1935d082a569d8d8c0335f52a08d63a8047ea1a94e4e48b'
OFFLINE_VALIDATION_AT = datetime.fromisoformat('2026-10-10T12:00:00+05:30')
FIXTURE_HASHES = {
    'FINAL-DIRECT-SUCCESSOR-RELATION.json': (10035, REVIEW_SHA256),
    'RETAINED-SOURCE-EPOCH.json': (
        2304, '68f11b05428fafd16c97479154e1b015991bef8b7d21c78c373bb61c2933ad37'),
    'FINAL-TARGET-CAPABILITY.json': (
        3337, '81fb09d0babb1900a7f3d5a96d0ed17233003062a48484564da3286c89d4e97f'),
}


@pytest.fixture
def authority():
    """No live stores, runtime composition or Provider constructor is invoked."""
    values = {}
    for name, (size, expected_hash) in FIXTURE_HASHES.items():
        data = (FIXTURES / name).read_bytes()
        assert len(data) == size
        assert sha256(data).hexdigest() == expected_hash
        values[name] = json.loads(data)
    target = values['FINAL-TARGET-CAPABILITY.json']
    assert target['engineering_only'] is True
    assert target['live_runtime_proof'] is False
    return (
        (FIXTURES / 'FINAL-DIRECT-SUCCESSOR-RELATION.json').read_bytes(),
        values['FINAL-DIRECT-SUCCESSOR-RELATION.json'],
        values['RETAINED-SOURCE-EPOCH.json'],
        target['proof_for_offline_map_validation'],
    )


def assert_all_fields_equal(left, right, path='$'):
    """Require identical field names, JSON types, list order and scalar values."""
    assert type(left) is type(right), path
    if type(left) is dict:
        assert left.keys() == right.keys(), path
        for key in left:
            assert_all_fields_equal(left[key], right[key], f'{path}.{key}')
    elif type(left) is list:
        assert len(left) == len(right), path
        for index, (old, new) in enumerate(zip(left, right)):
            assert_all_fields_equal(old, new, f'{path}[{index}]')
    else:
        assert left == right, path


def test_review_and_canonical_artifacts_are_distinct_but_all_fields_equal(authority):
    review_bytes, relation, epoch, target = authority
    persisted = canonical(relation)
    assert len(persisted) == 8299
    assert sha256(persisted).hexdigest() == PERSISTED_SHA256
    assert sha256(review_bytes).hexdigest() != PERSISTED_SHA256
    assert review_bytes != persisted
    assert_all_fields_equal(relation, json.loads(persisted))
    assert relation['identity'] == (
        'WO06H-SUCCESSOR_COMPATIBILITY-'
        '4f6aac6c3a9f59fe2e19b788fb6266fec1a239358e71f2abc9f9c9ac4c0731ef')
    assert relation['integrity'] == (
        '500d75b4b1093b776886bab486a55ba4c2c9e1824b75564a9cfb0ecaba7b3e03')


def test_exact_canonical_relation_passes_default_approved_validator(authority):
    _, relation, epoch, target = authority
    assert inspect.signature(validate_successor_relation).parameters['require_approval'].default is True
    assert all(row['disposition'] == 'APPROVED' for row in relation['body']['owner_approvals'])
    assert validate_successor_relation(
        json.loads(canonical(relation)), epoch, target, OFFLINE_VALIDATION_AT) is True


def test_epoch_store_retains_and_loads_exact_canonical_bytes(authority, tmp_path):
    _, relation, epoch, target = authority
    store = EpochStore(SimpleNamespace(root=tmp_path / 'disposable-raw'))
    store.retain(relation)
    stored = (store.root / (relation['identity'] + '.json')).read_bytes()
    assert stored == canonical(relation)
    assert sha256(stored).hexdigest() == PERSISTED_SHA256
    loaded = store.load(relation['identity'])
    assert_all_fields_equal(relation, loaded)
    assert validate_successor_relation(loaded, epoch, target, OFFLINE_VALIDATION_AT) is True
    store.retain(relation)
    assert (store.root / (relation['identity'] + '.json')).read_bytes() == stored


@pytest.mark.parametrize('encoding', ['review_artifact', 'canonical_with_whitespace'])
def test_epoch_reader_rejects_noncanonical_physical_representation(authority, tmp_path, encoding):
    review_bytes, relation, _, _ = authority
    store = EpochStore(SimpleNamespace(root=tmp_path / 'disposable-raw'))
    store.root.mkdir(parents=True)
    data = review_bytes if encoding == 'review_artifact' else canonical(relation) + b'\n'
    assert_all_fields_equal(relation, json.loads(data))
    (store.root / (relation['identity'] + '.json')).write_bytes(data)
    with pytest.raises(ShadowError, match='^SHADOW_EPOCH_ENCODING_INVALID$'):
        store.load(relation['identity'])


@pytest.mark.parametrize('mutation,reason', [
    ('schema', 'SHADOW_SUCCESSOR_COMPATIBILITY_VERSION_INVALID'),
    ('direction', 'SHADOW_SUCCESSOR_COMPATIBILITY_DIRECTION_INVALID'),
    ('non_transitive', 'SHADOW_SUCCESSOR_COMPATIBILITY_DIRECTION_INVALID'),
    ('epoch', 'SHADOW_SUCCESSOR_COMPATIBILITY_BINDING_INVALID'),
    ('acceptance', 'SHADOW_SUCCESSOR_COMPATIBILITY_BINDING_INVALID'),
    ('window', 'SHADOW_SUCCESSOR_COMPATIBILITY_BINDING_INVALID'),
    ('start', 'SHADOW_SUCCESSOR_COMPATIBILITY_BINDING_INVALID'),
    ('end', 'SHADOW_SUCCESSOR_COMPATIBILITY_BINDING_INVALID'),
    ('configuration', 'SHADOW_SUCCESSOR_COMPATIBILITY_MAP_INVALID'),
    ('source_aggregate', 'SHADOW_SUCCESSOR_COMPATIBILITY_MAP_INVALID'),
    ('target_aggregate', 'SHADOW_SUCCESSOR_COMPATIBILITY_MAP_INVALID'),
    ('source_map', 'SHADOW_SUCCESSOR_COMPATIBILITY_MAP_INVALID'),
    ('target_map', 'SHADOW_SUCCESSOR_COMPATIBILITY_MAP_INVALID'),
    ('reviewed_delta', 'SHADOW_SUCCESSOR_COMPATIBILITY_DELTA_INVALID'),
    ('approval_pending', 'SHADOW_SUCCESSOR_COMPATIBILITY_NOT_APPROVED'),
    ('approval_digest', 'SHADOW_SUCCESSOR_COMPATIBILITY_APPROVAL_INVALID'),
    ('integrity', 'SHADOW_EPOCH_INTEGRITY_INVALID'),
])
def test_changed_semantic_or_approval_authority_is_rejected(authority, mutation, reason):
    _, relation, epoch, target = authority
    body = deepcopy(relation['body'])
    if mutation == 'schema':
        body['schema'] = 'KRONOS-WO06H-SUCCESSOR-RUNTIME-COMPATIBILITY/0.0.0'
    elif mutation == 'direction':
        body['direction'] = 'TARGET_TO_SOURCE'
    elif mutation == 'non_transitive':
        body['non_transitive'] = False
    elif mutation in ('epoch', 'acceptance', 'window', 'source_aggregate', 'target_aggregate'):
        body[mutation] = body[mutation].rsplit('-', 1)[0] + '-' + '0' * 64
    elif mutation in ('start', 'end'):
        body[mutation] = '2026-10-11T07:50:33.006722+05:30'
    elif mutation == 'configuration':
        body['configuration'] = 'INTRADAY-LAUNCHER-CONFIG-' + '0' * 64
    elif mutation in ('source_map', 'target_map'):
        body[mutation.replace('_map', '_capabilities')][0]['implementation_digest'] = '0' * 64
    elif mutation == 'reviewed_delta':
        body['reviewed_changes'] = body['reviewed_changes'][:-1]
    elif mutation == 'approval_pending':
        body['owner_approvals'][0]['disposition'] = 'PENDING'
    elif mutation == 'approval_digest':
        body['owner_approvals'][0]['sha256'] = 'malformed'
    changed = deepcopy(relation) if mutation == 'integrity' else document('successor_compatibility', body)
    if mutation == 'integrity':
        changed['integrity'] = '0' * 64
    with pytest.raises(ShadowError, match=f'^{reason}$'):
        validate_successor_relation(changed, epoch, target, OFFLINE_VALIDATION_AT)
