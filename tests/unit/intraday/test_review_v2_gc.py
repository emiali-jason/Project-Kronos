"""Exact ownership, conservative external references and bounded deletion."""
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path

import pytest

from kronos.application.intraday_review_v2 import IntradayReviewV2Application
from kronos.intraday.review_v2 import create_question_pack_v2, create_question_batch_v2
from kronos.intraday.review_v2_gc import RETENTION_POLICY
from tests.unit.browser.test_intraday_review_v2_control import _control, _payload
from tests.unit.intraday.test_review_v2 import _retain_later_current_run
from tests.unit.intraday.test_review import _png


def fingerprints(root):
    return {p.relative_to(root): sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file() and not p.is_symlink()}


def population(tmp_path):
    run, app, control = _control(tmp_path)
    control.execute_document(_payload(run))
    old = app.snapshot().candidates[0].cycle_identity
    chart = app.upload_chart(old, media_type="image/png", payload=_png(41))
    cycle = app.review_store.load_cycle(old)
    pack = create_question_pack_v2(app.review_store.load_handoff(cycle.handoff_identity), cycle, chart)
    app.review_store.retain_pack(pack)
    app.review_store.retain_batch(create_question_batch_v2((pack,)))
    later = _retain_later_current_run(app)
    control.execute_document(_payload(later, "REVIEW-V2-REQUEST-SECOND"))
    current = app.snapshot().candidates[0].cycle_identity
    app.upload_chart(current, media_type="image/png", payload=_png(42))
    return app, old, current


def test_whole_component_gc_accounting_and_idempotent_restoration(tmp_path):
    app, old, current = population(tmp_path)
    root = app.review_store.root
    before = fingerprints(root)
    current_before = app.snapshot()
    probables_before = fingerprints(app.probables_store.root / "probables-v2")
    result = app.maintain_current_review()
    assert result.status == "GC_COMPLETE"
    assert result.policy == RETENTION_POLICY
    assert result.eligible_cycles == (old,)
    assert result.files_removed > 5 and result.bytes_reclaimed > 0
    after = fingerprints(root)
    assert result.files_before == len(before)
    assert result.files_removed == len(before) - len(after)
    assert all(before[p] == h for p, h in after.items())
    assert not (root / "cycles" / (old + ".json")).exists()
    assert (root / "cycles" / (current + ".json")).exists()
    restored = IntradayReviewV2Application(probables_store=app.probables_store, review_store=app.review_store)
    assert restored.snapshot() == current_before
    assert fingerprints(app.probables_store.root / "probables-v2") == probables_before
    assert app.maintain_current_review().files_removed == 0


@pytest.mark.parametrize("owner", ["wo10-reconciliation-v2", "wo11", "wo17", "domain-001", "domain-008", "foreign"])
def test_external_reference_protects_entire_component_and_foreign_bytes(tmp_path, owner):
    app, old, current = population(tmp_path)
    external = tmp_path / owner / "evidence.json"
    external.parent.mkdir(); external.write_text(json.dumps({"review_cycle_identity": old}))
    before = fingerprints(tmp_path)
    result = app.maintain_current_review()
    assert result.status == "GC_COMPLETE" and result.protected_cycles == (old,)
    assert result.files_removed == 0
    assert fingerprints(tmp_path) == before


@pytest.mark.parametrize("attack", ["unknown", "malformed", "renamed", "traversal", "symlink", "directory_symlink", "external_malformed"])
def test_gc_fails_closed_on_unproven_files_and_paths(tmp_path, attack):
    app, old, current = population(tmp_path)
    root = app.review_store.root
    cycle = root / "cycles" / (old + ".json")
    foreign = tmp_path / "foreign.json"; foreign.write_text('{"protected":true}')
    if attack == "unknown":
        (root / "unknown.json").write_text('{}')
    elif attack == "malformed":
        cycle.write_text('{')
    elif attack == "renamed":
        cycle.rename(cycle.with_name("FOREIGN.json"))
    elif attack == "traversal":
        document = json.loads(cycle.read_text()); document['handoff_identity'] = '../../foreign'
        cycle.write_text(json.dumps(document))
    elif attack == "symlink":
        (root / "escape.json").symlink_to(foreign)
    elif attack == "directory_symlink":
        (root / "escape").symlink_to(tmp_path, target_is_directory=True)
    else:
        foreign.write_text('{')
    before = fingerprints(tmp_path)
    result = app.maintain_current_review()
    assert result.status == "GC_DEFERRED_INTEGRITY_OR_IO"
    assert fingerprints(tmp_path) == before
    assert foreign.exists()


def test_failed_delete_rolls_back_exact_component(tmp_path, monkeypatch):
    app, old, current = population(tmp_path)
    before = fingerprints(tmp_path)
    unlink = Path.unlink
    calls = []
    def failing(path, *a, **kw):
        calls.append(path)
        if len(calls) == 2:
            raise OSError("SECRET /private/path")
        return unlink(path, *a, **kw)
    monkeypatch.setattr(Path, "unlink", failing)
    result = app.maintain_current_review()
    assert result.status == "GC_DEFERRED_INTEGRITY_OR_IO"
    assert "SECRET" not in repr(result)
    assert fingerprints(tmp_path) == before
    assert app.snapshot().candidates[0].cycle_identity == current


def test_currentization_required_and_gc_never_runs_on_snapshot(tmp_path, monkeypatch):
    app, old, current = population(tmp_path)
    import kronos.intraday.review_v2_gc as gc
    monkeypatch.setattr(gc, "collect_review_components", lambda *a: pytest.fail("GET GC"))
    app.snapshot(); app.currentness()
    _retain_later_current_run(app, boundary=__import__('datetime').datetime.fromisoformat('2026-08-28T13:00:00+05:30'))
    before = fingerprints(tmp_path)
    assert app.maintain_current_review().status == "GC_DEFERRED_NOT_CURRENT"
    assert fingerprints(tmp_path) == before


@pytest.mark.parametrize("reference", ["escaped_json", "file_path", "published_answer"])
def test_nonliteral_and_exported_references_are_protected(tmp_path, reference):
    app, old, current = population(tmp_path)
    if reference == "published_answer":
        folder = app._transport.answer_inbox
        folder.mkdir(exist_ok=True)
        target = folder / "expected.json"
    else:
        target = tmp_path / "foreign.json"
    payload = json.dumps({"reference": str(app.review_store.root / "cycles" / (old + ".json"))
                          if reference == "file_path" else old})
    if reference == "escaped_json":
        payload = payload.replace("INTRADAY", "\\u0049NTRADAY")
    target.write_text(payload)
    before = fingerprints(tmp_path)
    result = app.maintain_current_review()
    assert result.status == "GC_COMPLETE" and result.protected_cycles == (old,)
    assert fingerprints(tmp_path) == before


def test_published_compressed_pdf_alone_protects_transport_component(tmp_path):
    run, app, control = _control(tmp_path)
    control.execute_document(_payload(run))
    old = app.snapshot().candidates[0].cycle_identity
    app.upload_chart(old, media_type="image/png", payload=_png(1))
    batch = app.create_combined_question_transport()
    batch.answer_template_path.unlink()  # Only the exported compressed PDF survives.
    later = _retain_later_current_run(app)
    control.execute_document(_payload(later, "REVIEW-V2-REQUEST-SECOND"))
    before = fingerprints(tmp_path)
    result = app.maintain_current_review()
    assert result.status == "GC_COMPLETE" and result.protected_cycles == (old,)
    assert fingerprints(tmp_path) == before
