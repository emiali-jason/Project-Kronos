"""Approval-bound record bytes use fixed record locations, never blob repair.

Actual codec/store/budget, synthetic schema-valid original records. This tests
read-only selection and authentication, not owner approval or native C success.
"""
from hashlib import sha256
import pytest
from kronos.common import failed_fenced_recovery as core
from kronos.common import failed_fenced_schema as schema
from kronos.common.failed_fenced_startup import _read_recovery_bound_record, RecoveryStartupError
from tests.unit.common.test_failed_fenced_recovery import private_store, codec, real_budget, CLOCK
from tests.unit.common.test_failed_fenced_child_receipts import _example


def record_bytes(kind):
    payload = _example(schema._parse(schema.RECORD_SCHEMAS[kind]))
    if kind == 'OBLIGATION':
        payload.update(state='ACCEPTED', owner='WO11', relation='WO11_PUBLICATION')
        payload['effect'].update(kind='WO11_PUBLICATION', transition=None)
    if kind == 'CLEANUP':
        owner = sorted(schema.CLEANUP_ACTIONS)[0]
        payload.update(state='NOT_STARTED', owner=owner, action=schema.CLEANUP_ACTIONS[owner][0])
    return codec().encode(kind, payload, 'PREDECESSOR', 2)


@pytest.mark.parametrize('kind', ['TERMINAL', 'OBLIGATION', 'CLEANUP'])
def test_approval_blob_descriptor_reads_only_its_existing_record(tmp_path, kind):
    store = private_store(tmp_path); raw = record_bytes(kind)
    store.publish(raw); reference = core.blob_ref('approved-record', raw)
    # A blob copy is neither necessary nor consulted for these fixed records.
    store._write(('blobs',), reference['hash']+'.blob', b'irrelevant wrong blob')
    before = {str(p): p.read_bytes() for p in store.root.rglob('*') if p.is_file()}
    actual, record = _read_recovery_bound_record(store, codec(), reference,
        purpose='TERMINAL' if kind == 'TERMINAL' else 'JOURNAL_HEAD', budget=real_budget())
    assert actual == raw and record == codec().decode(raw, kind)
    assert before == {str(p): p.read_bytes() for p in store.root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('fault', ['missing', 'blob-only', 'size', 'hash', 'mac', 'wrong-kind', 'unknown-purpose', 'expired'])
def test_record_binding_denies_missing_changed_or_wrong_domain_without_repair(tmp_path, fault):
    store = private_store(tmp_path); raw = record_bytes('TERMINAL')
    if fault == 'mac':
        value = core.decode_canonical(raw); value['mac'] = '0'*64
        raw = core.canonical_bytes(value)
    reference = core.blob_ref('approved-terminal', raw)
    if fault == 'blob-only': store.write_blob(reference['identity'], raw)
    elif fault != 'missing': store.publish(raw)
    if fault == 'size': reference['bytes'] = str(len(raw)+1)
    if fault == 'hash': reference['hash'] = 'f'*64
    purpose = 'JOURNAL_HEAD' if fault == 'wrong-kind' else 'TERMINAL'
    if fault == 'unknown-purpose': purpose = 'ORIGINAL'
    budget = core.RecoveryBudget(CLOCK, 1, 15_000_000_001) if fault == 'expired' else real_budget()
    before = {str(p): p.read_bytes() for p in store.root.rglob('*') if p.is_file()}
    with pytest.raises((core.RecoveryError, RecoveryStartupError)):
        _read_recovery_bound_record(store, codec(), reference, purpose=purpose, budget=budget)
    assert before == {str(p): p.read_bytes() for p in store.root.rglob('*') if p.is_file()}


def test_fixed_record_symlink_and_changed_bytes_never_use_other_storage(tmp_path):
    store = private_store(tmp_path); raw = record_bytes('TERMINAL')
    reference = core.blob_ref('approved-terminal', raw)
    store.write_blob(reference['identity'], raw)
    path = store.root/'records'/('TERMINAL-'+reference['hash']+'.json')
    path.symlink_to(store.root/'blobs'/(reference['hash']+'.blob'))
    with pytest.raises(core.RecoveryError):
        _read_recovery_bound_record(store, codec(), reference, purpose='TERMINAL', budget=real_budget())
    path.unlink(); store._write(('records',), path.name, raw+b' ')
    with pytest.raises(core.RecoveryError):
        _read_recovery_bound_record(store, codec(), reference, purpose='TERMINAL', budget=real_budget())


def test_printable_ascii_predicate_preserves_exact_original_character_boundary():
    from kronos.common.failed_fenced_recovery import _ascii_tree, RecoveryError
    # Exhaustive BMP, all ASCII, Unicode/surrogate/noncharacter extremes; no
    # protocol coercion, whitespace, control character or Unicode is admitted.
    for code in list(range(65536)) + [0x10000, 0x1ffff, 0x10fffe, 0x10ffff]:
        value = chr(code)
        if 32 <= code <= 126:
            _ascii_tree(value)
        else:
            with pytest.raises(RecoveryError, match='non-ASCII protocol string'):
                _ascii_tree(value)
    _ascii_tree('')
    _ascii_tree('a' * 200000)
    for invalid in ['\t', '\n', '\r', '\x00', '\x7f', '\u00a0', '\ud800', '\U0010ffff']:
        with pytest.raises(RecoveryError, match='non-ASCII protocol string'):
            _ascii_tree('a' * 200000 + invalid)
