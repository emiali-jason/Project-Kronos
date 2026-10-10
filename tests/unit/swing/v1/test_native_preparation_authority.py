"""WO06H R5 Native preparation authority and historical uncertainty contract."""
from dataclasses import replace
from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

from kronos.application.swing_native_review import NativeReviewWorkflow, NativeReviewRunState
from kronos.swing.v1.evidence_store import LocalTradingViewEvidenceStore
from kronos.swing.v1.native_review import (
    NativeReviewEvidenceStore, NativeReviewRestorationStatus as Status,
    build_native_review_requirements,
)
from tests.unit.swing.v1.test_native_review import _evidence_run

NOW = datetime(2026, 10, 10, 12, tzinfo=UTC)


def workflow(root):
    return NativeReviewWorkflow(NativeReviewEvidenceStore(root),
        chart_store=LocalTradingViewEvidenceStore(root / "charts"), clock=lambda: NOW)


def witnesses(root):
    return tuple(sorted((root / "preparation-witnesses").rglob("*.json")))


def requirements_path(root):
    _, run, _ = _evidence_run()
    return root / "complete-runs" / (run.run_identity + ".json")


@pytest.fixture(scope="module")
def governed_historical_pdf_payloads(tmp_path_factory):
    from tests.unit.swing.v1.test_pdf_visual_review import _workflow
    from tests.unit.browser.test_swing_visual_v3_live import _live
    from tests.unit.swing.v1.test_visual_v3_cycle_publication import _prepared
    root = tmp_path_factory.mktemp("governed-historical-pdf")
    native, transport = _workflow(root / "v0")
    pack = native.generate_review_pack()
    payloads = {"v0": json.loads((transport.record_store.root / "review-packs" /
                                 (pack.review_pack_id + ".json")).read_text())}
    native, facts, live = _live(root / "v3")
    pack = live.transport.generate(_prepared(native, facts, live), scope="ALL_ELIGIBLE", skipped=())
    payloads["v3"] = json.loads((live.transport.record_store.root / "review-packs" /
                                (pack.review_pack_id + ".json")).read_text())
    return payloads


@pytest.mark.parametrize("family", ["v0", "v3"])
@pytest.mark.parametrize("corruption", ["minimal", "list-run", "integer-run", "invalid-run",
                                       "schema", "missing-field", "candidate-hash", "nonstring-id"])
def test_historical_pdf_validation_precedes_other_run_filter(
        tmp_path, governed_historical_pdf_payloads, family, corruption):
    payload = json.loads(json.dumps(governed_historical_pdf_payloads[family]))
    record = payload["record"]
    pack_id = record["review_pack_id"]
    record["native_run_identity"] = "SWING-RUN-" + "F" * 32
    for candidate in record.get("candidate_packs", []):
        candidate["native_run_identity"] = record["native_run_identity"]
    if corruption == "minimal":
        payload["record"] = {"review_pack_id": pack_id, "native_run_identity": ["lost-binding"]}
    elif corruption == "list-run":
        record["native_run_identity"] = ["lost-binding"]
    elif corruption == "integer-run":
        record["native_run_identity"] = 123
    elif corruption == "invalid-run":
        record["native_run_identity"] = "unbound-run"
    elif corruption == "schema":
        payload["schema"] = "UNRECOGNIZED"
    elif corruption == "missing-field":
        del record["question_pdf_sha256"]
    elif corruption == "candidate-hash":
        record["candidates" if family == "v0" else "candidate_packs"][0]["native_assessment_sha256"] = "bad"
    elif corruption == "nonstring-id":
        record["review_pack_id"] = 1
        pack_id = "1"
    path = tmp_path / ("pdf-transport-" + family) / "review-packs" / (pack_id + ".json")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload))
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    facts, run, _ = _evidence_run()
    owner = workflow(tmp_path)
    with pytest.raises(ValueError):
        owner.restore(run, facts)
    assert owner.restoration_result.status is Status.FAILED
    assert workflow(tmp_path).assess_without_analysis().status is Status.FAILED
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before


def test_historical_pdf_v3_inconsistent_run_binding_blocks(tmp_path, governed_historical_pdf_payloads):
    payload = json.loads(json.dumps(governed_historical_pdf_payloads["v3"]))
    payload["record"]["native_run_identity"] = "SWING-RUN-" + "F" * 32
    path = tmp_path / "pdf-transport-v3" / "review-packs" / (payload["record"]["review_pack_id"] + ".json")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload))
    facts, run, _ = _evidence_run()
    owner = workflow(tmp_path)
    with pytest.raises(ValueError):
        owner.restore(run, facts)
    assert owner.restoration_result.status is Status.FAILED


@pytest.mark.parametrize("family", ["v0", "v3"])
def test_historical_pdf_valid_other_run_remains_nonapplicable(
        tmp_path, governed_historical_pdf_payloads, family):
    from kronos.swing.v1.native_review_applicability import _historical_pdf_lineage
    payload = governed_historical_pdf_payloads[family]
    root = tmp_path / ("pdf-transport-" + family)
    path = root / "review-packs" / (payload["record"]["review_pack_id"] + ".json")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload))
    before = path.read_bytes()
    other = "SWING-RUN-" + "F" * 32
    assert not _historical_pdf_lineage({root}, other)
    assert _historical_pdf_lineage({root}, payload["record"]["native_run_identity"])
    assert _historical_pdf_lineage({root})
    facts, run, _ = _evidence_run()
    owner = workflow(tmp_path)
    with pytest.raises(ValueError, match="REQUIRED_EVIDENCE_LOST"):
        owner.restore(run, facts)
    # Rebind the complete retained record consistently to a second valid run;
    # the existing typed reader validates all candidate/parent bindings.
    payload = json.loads(json.dumps(payload))
    payload["record"]["native_run_identity"] = other
    for candidate in payload["record"].get("candidate_packs", []):
        candidate["native_run_identity"] = other
    path.write_text(json.dumps(payload))
    before = path.read_bytes()
    other_owner = workflow(tmp_path)
    other_owner.restore(run, facts)
    assert other_owner.restoration_result.status is Status.APPLICABILITY_NOT_ESTABLISHED
    assert path.read_bytes() == before
    assert not requirements_path(tmp_path).exists()
    assert not witnesses(tmp_path)


@pytest.mark.parametrize("kind", ["v0-import", "v0-flat-import", "v0-artifact", "v3-import"])
@pytest.mark.parametrize("binding", ["mismatched-path", "unresolved-path", "valid-other-run"])
def test_historical_answer_namespace_is_part_of_pack_binding(
        tmp_path, governed_historical_pdf_payloads, kind, binding):
    from kronos.swing.v1.pdf_visual_review import (
        PdfReviewRecordStore, AnswerArtifactRecord, AnswerImportRecord, AnswerImportState,
    )
    from kronos.swing.v1.pdf_visual_review_v3_live import (
        VisualV3PdfRecordStore, VisualV3AnswerImportRecord, VisualV3AnswerImportState,
    )
    family = kind[:2]
    root = tmp_path / ("pdf-transport-" + family)
    payload = json.loads(json.dumps(governed_historical_pdf_payloads[family]))
    record = payload["record"]
    record["native_run_identity"] = "SWING-RUN-" + "F" * 32
    for candidate in record.get("candidate_packs", []):
        candidate["native_run_identity"] = record["native_run_identity"]
    pack_id = record["review_pack_id"]
    pack_path = root / "review-packs" / (pack_id + ".json")
    pack_path.parent.mkdir(parents=True)
    pack_path.write_text(json.dumps(payload))
    common = (pack_id, "REVIEW_ANSWERS.pdf", str(tmp_path / "REVIEW_ANSWERS.pdf"), "a" * 64, NOW)
    if kind == "v0-artifact":
        path = PdfReviewRecordStore(root).retain_answer_artifact(AnswerArtifactRecord(*common))
    elif kind in {"v0-import", "v0-flat-import"}:
        path = PdfReviewRecordStore(root).retain_answer_import(AnswerImportRecord(
            *common, AnswerImportState.ANSWER_PACK_REJECTED, ("ANSWER_FORMAT_INVALID",), False, None))
        if kind == "v0-flat-import":
            flat = path.parent.with_suffix(".json")
            path.rename(flat)
            path = flat
    else:
        path = VisualV3PdfRecordStore(root).retain_import(VisualV3AnswerImportRecord(
            *common, VisualV3AnswerImportState.ANSWER_PACK_REJECTED, ("ANSWER_FORMAT_INVALID",), False))
    if binding != "valid-other-run":
        parts = path.relative_to(root).parts
        missing = pack_id + "-MISSING"
        moved = root.joinpath(parts[0], missing, *parts[2:])
        moved.parent.mkdir(parents=True)
        path.rename(moved)
        if binding == "unresolved-path":
            body = json.loads(moved.read_text())
            body["record"]["review_pack_id"] = missing
            moved.write_text(json.dumps(body))
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    facts, run, _ = _evidence_run()
    owner = workflow(tmp_path)
    if binding == "valid-other-run":
        owner.restore(run, facts)
        assert owner.restoration_result.status is Status.APPLICABILITY_NOT_ESTABLISHED
    else:
        with pytest.raises(ValueError, match="HISTORICAL_PACK_LINEAGE_UNAVAILABLE"):
            owner.restore(run, facts)
        assert owner.restoration_result.status is Status.FAILED
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before


def _flat_v0_answer_fixture(root, payload):
    """Use the owned typed record in its retained digest-file representation."""
    from kronos.swing.v1.pdf_visual_review import (
        PdfReviewRecordStore, AnswerImportRecord, AnswerImportState,
    )
    pack_id = payload["record"]["review_pack_id"]
    pack_path = root / "review-packs" / (pack_id + ".json")
    pack_path.parent.mkdir(parents=True)
    pack_path.write_text(json.dumps(payload))
    store = PdfReviewRecordStore(root)
    record = AnswerImportRecord(pack_id, "REVIEW_ANSWERS.pdf",
        str(root / "REVIEW_ANSWERS.pdf"), "a" * 64, NOW,
        AnswerImportState.ANSWER_PACK_REJECTED, ("ANSWER_FORMAT_INVALID",), False, None)
    nested = store.retain_answer_import(record)
    flat = nested.parent.with_suffix(".json")
    nested.rename(flat)
    return store, record, flat, pack_path


def test_mixed_flat_and_nested_v0_imports_keep_owner_read_contract(
        tmp_path, governed_historical_pdf_payloads):
    from datetime import timedelta
    from kronos.swing.v1.native_review_applicability import _historical_pdf_lineage
    root = tmp_path / "pdf-transport-v0"
    payload = governed_historical_pdf_payloads["v0"]
    store, first, _, _ = _flat_v0_answer_fixture(root, payload)
    second = replace(first, discovered_at=NOW + timedelta(seconds=1))
    store.retain_answer_import(second)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert store.load_answer_imports(first.review_pack_id) == (first, second)
    assert _historical_pdf_lineage({root}, payload["record"]["native_run_identity"])
    assert not _historical_pdf_lineage({root}, "SWING-RUN-" + "F" * 32)
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize("damage", ["missing-pack", "wrong-digest", "attempt-as-filename",
                                    "extra-depth", "corrupt-json", "wrong-schema",
                                    "invalid-record", "misbound-record"])
def test_flat_v0_import_validation_precedes_other_run_filter(
        tmp_path, governed_historical_pdf_payloads, damage):
    payload = json.loads(json.dumps(governed_historical_pdf_payloads["v0"]))
    payload["record"]["native_run_identity"] = "SWING-RUN-" + "F" * 32
    root = tmp_path / "pdf-transport-v0"
    _, record, path, pack_path = _flat_v0_answer_fixture(root, payload)
    if damage == "missing-pack":
        pack_path.unlink()
    elif damage in {"wrong-digest", "attempt-as-filename"}:
        filename = "b" * 64 if damage == "wrong-digest" else record.attempt_identity
        path.rename(path.with_name(filename + ".json"))
    elif damage == "extra-depth":
        moved = path.parent / "extra" / path.name
        moved.parent.mkdir()
        path.rename(moved)
    elif damage == "corrupt-json":
        path.write_text("broken")
    else:
        body = json.loads(path.read_text())
        if damage == "wrong-schema":
            body["schema"] = "UNRECOGNIZED"
        elif damage == "invalid-record":
            body["record"]["answer_pdf_sha256"] = "invalid"
        else:
            body["record"]["review_pack_id"] += "-MISSING"
        path.write_text(json.dumps(body))
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    facts, run, _ = _evidence_run()
    owner = workflow(tmp_path)
    with pytest.raises(ValueError):
        owner.restore(run, facts)
    assert owner.restoration_result.status is Status.FAILED
    assert workflow(tmp_path).assess_without_analysis().status is Status.FAILED
    assert not witnesses(tmp_path)
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before


def test_flat_v3_import_is_not_an_allowed_historical_layout(
        tmp_path, governed_historical_pdf_payloads):
    from kronos.swing.v1.pdf_visual_review_v3_live import (
        VisualV3PdfRecordStore, VisualV3AnswerImportRecord, VisualV3AnswerImportState,
    )
    payload = governed_historical_pdf_payloads["v3"]
    pack_id = payload["record"]["review_pack_id"]
    root = tmp_path / "pdf-transport-v3"
    pack_path = root / "review-packs" / (pack_id + ".json")
    pack_path.parent.mkdir(parents=True)
    pack_path.write_text(json.dumps(payload))
    path = VisualV3PdfRecordStore(root).retain_import(VisualV3AnswerImportRecord(
        pack_id, "REVIEW_ANSWERS.pdf", str(tmp_path / "REVIEW_ANSWERS.pdf"), "a" * 64,
        NOW, VisualV3AnswerImportState.ANSWER_PACK_REJECTED, ("ANSWER_FORMAT_INVALID",), False))
    path.rename(path.parent.with_suffix(".json"))
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    facts, run, _ = _evidence_run()
    owner = workflow(tmp_path)
    with pytest.raises(ValueError, match="HISTORICAL_PACK_LINEAGE_UNAVAILABLE"):
        owner.restore(run, facts)
    assert owner.restoration_result.status is Status.FAILED
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize("requirements_retained", [False, True])
def test_flat_rejected_import_never_promotes_preparation_or_backfills_witness(
        tmp_path, governed_historical_pdf_payloads, requirements_retained):
    _flat_v0_answer_fixture(tmp_path / "pdf-transport-v0",
                           governed_historical_pdf_payloads["v0"])
    facts, run, _ = _evidence_run()
    if requirements_retained:
        NativeReviewEvidenceStore(tmp_path).retain(build_native_review_requirements(run, facts))
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    owner = workflow(tmp_path)
    if requirements_retained:
        owner.restore(run, facts)
        assert owner.restoration_result.status is Status.RESTORED
        assert owner.restoration_result.evidence == ("LEGACY_REQUIREMENTS",)
    else:
        with pytest.raises(ValueError, match="REQUIRED_EVIDENCE_LOST"):
            owner.restore(run, facts)
        assert owner.restoration_result.status is Status.FAILED
    assert not witnesses(tmp_path)
    assert not (tmp_path / "preparation-intents").exists()
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize("kind", ["v0-current", "v3-current", "v3-pointer-to-v0", "pending", "history", "recovery", "selected-recovery"])
@pytest.mark.parametrize("valid", [False, True])
def test_historical_pointer_and_recovery_reference_bindings(
        tmp_path, governed_historical_pdf_payloads, kind, valid):
    from kronos.swing.v1 import pdf_visual_review as v0
    from kronos.swing.v1 import pdf_visual_review_v3_live as v3
    from kronos.swing.v1 import pdf_visual_review_v3_recovery as recovery
    family = "v0" if kind == "v0-current" or (kind == "v3-pointer-to-v0" and not valid) else "v3"
    root = tmp_path / ("pdf-transport-" + family)
    payload = json.loads(json.dumps(governed_historical_pdf_payloads[family]))
    record = payload["record"]
    record["native_run_identity"] = "SWING-RUN-" + "F" * 32
    for candidate in record.get("candidate_packs", []):
        candidate["native_run_identity"] = record["native_run_identity"]
    pack_id = record["review_pack_id"]
    path = root / "review-packs" / (pack_id + ".json")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload))
    selection = {"schema": v3.VISUAL_V3_LIVE_SELECTION_SCHEMA, "review_pack_id": pack_id}
    if kind == "v0-current":
        reference = {"schema": v0.CURRENT_REVIEW_PACK_SELECTION_SCHEMA,
                     "selection": {"review_pack_id": pack_id, "scope": "ALL_ELIGIBLE", "skipped": []}}
        if not valid:
            reference["selection"]["review_pack_id"] += "-MISSING"
        target = root / "current-review-pack.json"
    elif kind in {"v3-current", "v3-pointer-to-v0"}:
        reference = dict(selection)
        if not valid and kind == "v3-current":
            reference["review_pack_id"] += "-MISSING"
        target = root / "current-review-pack.json"
    elif kind == "pending":
        reference = {"record": record, "temporary": str(tmp_path / "question.tmp")}
        if not valid:
            record["native_run_identity"] = "SWING-RUN-" + "E" * 32
        target = root / "pending-publication.json"
    elif kind == "history":
        reference = selection
        identity = recovery._digest(reference) if valid else "a" * 64
        target = root / "selection-history" / (identity + ".json")
    else:
        # Only retained recovery metadata binding is assessed, never rendering
        # or external PDF/source restoration. Match the producer's digest rules.
        body = {"schema": recovery.SCHEMA, "version": recovery.VERSION,
                "review_pack_id": pack_id, "canonical_pack_digest": recovery._digest(record),
                "predecessor_selection": selection}
        reference = {**body, "checksum": recovery._digest(body)}
        target = root / "artifact-recoveries" / (reference["checksum"] + ".json")
        if kind == "selected-recovery":
            pointer = root / "current-review-pack.json"
            pointer.write_text(json.dumps({**selection, "artifact_recovery_sha256": reference["checksum"]}))
        if not valid:
            target = target.with_name("a" * 64 + ".json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(reference))
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    facts, run, _ = _evidence_run()
    owner = workflow(tmp_path)
    if valid:
        owner.restore(run, facts)
        assert owner.restoration_result.status is Status.APPLICABILITY_NOT_ESTABLISHED
    else:
        with pytest.raises(ValueError):
            owner.restore(run, facts)
        assert owner.restoration_result.status is Status.FAILED
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before


def test_legacy_absence_explicit_nonblocking_uncertainty_without_writes(tmp_path):
    facts, run, _ = _evidence_run()
    owner = workflow(tmp_path)
    assert owner.restoration_result is None
    snapshot = owner.restore(run, facts)
    assert snapshot.state is NativeReviewRunState.NOT_PREPARED
    assert snapshot.native_run_identity is None
    assert snapshot.requirements == ()
    assert owner.restoration_result.status is Status.APPLICABILITY_NOT_ESTABLISHED
    assert owner.restoration_result.succeeded
    assert not owner.restoration_result.applicable
    assert not tuple(tmp_path.rglob("*"))


@pytest.mark.parametrize("path", [
    "reference-results/{run}/result.json",
    "visual-v2/{run}/subject/1D/evidence.json",
    "layer2-readiness-v0/{run}/result.json",
    "charts/native-review-composite-charts/{run}/subject/assessment/native/chart/manifest.json",
])
def test_exact_legacy_dependency_missing_requirements_blocks(tmp_path, path):
    facts, run, _ = _evidence_run()
    target = tmp_path / path.format(run=run.run_identity)
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"record": {"native_run_identity": run.run_identity, "review_pack_id": "pack"}}))
    owner = workflow(tmp_path)
    with pytest.raises(ValueError, match="REQUIRED_EVIDENCE_LOST"):
        owner.restore(run, facts)
    assert owner.restoration_result.status is Status.FAILED
    with pytest.raises(ValueError, match="REQUIRED_EVIDENCE_LOST"):
        owner.prepare(run, facts)
    assert not witnesses(tmp_path)
    assert not requirements_path(tmp_path).exists()


@pytest.mark.parametrize("path", [
    "visual-v3/{run}/subject/1D/response.json",
    "layer2-readiness-v3/{run}/result.json",
    "requests/prospective.json",
    "acceptance/prospective.json",
    "native-chart-selections/chart.json",
])
def test_receipt_or_unbound_downstream_does_not_invent_legacy_dependency(tmp_path, path):
    facts, run, _ = _evidence_run()
    target = tmp_path / path.format(run=run.run_identity)
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"native_run_identity": run.run_identity}))
    before = target.read_bytes()
    owner = workflow(tmp_path)
    owner.restore(run, facts)
    assert owner.restoration_result.status is Status.APPLICABILITY_NOT_ESTABLISHED
    assert target.read_bytes() == before
    assert not witnesses(tmp_path)


@pytest.mark.parametrize("method", ["prepare", "refresh"])
def test_successful_prospective_prepare_exact_witness_and_deterministic_repeat(tmp_path, method):
    facts, run, _ = _evidence_run()
    owner = workflow(tmp_path)
    before_run = run
    snapshot = getattr(owner, method)(run, facts)
    paths = witnesses(tmp_path)
    assert len(paths) == 1
    witness_bytes = paths[0].read_bytes()
    requirement_bytes = requirements_path(tmp_path).read_bytes()
    witness = json.loads(witness_bytes)
    assert witness["run_identity"] == run.run_identity
    assert witness["completed_at"] == NOW.isoformat()
    assert witness["requirement_identities"] == [r.requirement_sha256 for r in snapshot.requirements]
    assert snapshot.requirements == build_native_review_requirements(run, facts)
    assert run == before_run
    getattr(owner, method)(run, facts)
    fresh = workflow(tmp_path)
    getattr(fresh, method)(run, facts)
    assert witnesses(tmp_path) == paths
    assert paths[0].read_bytes() == witness_bytes
    assert requirements_path(tmp_path).read_bytes() == requirement_bytes
    restored = workflow(tmp_path)
    assert restored.restore(run, facts).requirements == snapshot.requirements
    assert restored.restoration_result.status is Status.RESTORED
    assert restored.restoration_result.evidence == ("WITNESSED",)


@pytest.mark.parametrize("method", ["prepare", "refresh"])
def test_witness_last_after_requirement_fsync_and_snapshot_validation(tmp_path, monkeypatch, method):
    import kronos.swing.v1.native_review as module
    facts, run, _ = _evidence_run()
    original = module._atomic_json
    observed = []
    def checked(path, payload):
        if "preparation-witnesses" in path.parts:
            assert requirements_path(tmp_path).is_file()
            assert workflow(tmp_path)._store.load(run, facts)
            assert not witnesses(tmp_path)
            observed.append("WITNESS")
        original(path, payload)
    monkeypatch.setattr(module, "_atomic_json", checked)
    getattr(workflow(tmp_path), method)(run, facts)
    assert observed == ["WITNESS"]


@pytest.mark.parametrize("stage", ["preparation-intents", "complete-runs", "snapshot", "preparation-witnesses"])
def test_failed_preparation_no_completion_authority_and_retry_safe(tmp_path, monkeypatch, stage):
    import kronos.swing.v1.native_review as module
    facts, run, _ = _evidence_run()
    owner = workflow(tmp_path)
    original = module._atomic_json
    def failed(path, payload):
        if stage in path.parts:
            raise OSError("injected write failure")
        original(path, payload)
    with monkeypatch.context() as patch:
        patch.setattr(module, "_atomic_json", failed)
        if stage == "snapshot":
            patch.setattr(owner, "_snapshot_unlocked", lambda: (_ for _ in ()).throw(ValueError("snapshot")))
        with pytest.raises((OSError, ValueError)):
            owner.prepare(run, facts)
    assert not witnesses(tmp_path)
    assert owner.snapshot().state is NativeReviewRunState.NOT_PREPARED
    assert owner.restoration_result.status is Status.FAILED
    if stage != "preparation-intents":
        fresh = workflow(tmp_path)
        with pytest.raises(ValueError, match="INCOMPLETE"):
            fresh.restore(run, facts)
        assert fresh.restoration_result.status is Status.FAILED
        assert not witnesses(tmp_path)
    retry = workflow(tmp_path)
    retry.prepare(run, facts)
    assert len(witnesses(tmp_path)) == 1
    retry.restore(run, facts)
    assert retry.restoration_result.status is Status.RESTORED


@pytest.mark.parametrize("corruption", ["wrong-run", "json", "hash", "missing-requirement", "corrupt-requirement", "extra-field", "ambiguous", "intent"])
def test_witness_binding_integrity_and_required_evidence_fail_closed(tmp_path, corruption):
    facts, run, _ = _evidence_run()
    workflow(tmp_path).prepare(run, facts)
    witness = witnesses(tmp_path)[0]
    payload = json.loads(witness.read_text())
    if corruption == "wrong-run":
        payload["run_identity"] = "SWING-ANALYSIS-foreign"
        witness.write_text(json.dumps(payload))
    elif corruption == "json":
        witness.write_text("broken")
    elif corruption == "hash":
        payload["integrity_sha256"] = "0" * 64
        witness.write_text(json.dumps(payload))
    elif corruption == "missing-requirement":
        requirements_path(tmp_path).unlink()
    elif corruption == "corrupt-requirement":
        requirements_path(tmp_path).write_text("broken")
    elif corruption == "extra-field":
        value = json.loads(requirements_path(tmp_path).read_text())
        value["inconsistent"] = True
        requirements_path(tmp_path).write_text(json.dumps(value))
    elif corruption == "ambiguous":
        witness.with_name("second.json").write_bytes(witness.read_bytes())
    elif corruption == "intent":
        (tmp_path / "preparation-intents" / (run.run_identity + ".json")).write_text("broken")
    owner = workflow(tmp_path)
    with pytest.raises(ValueError):
        owner.restore(run, facts)
    assert owner.restoration_result.status is Status.FAILED
    assert owner.snapshot().state is NativeReviewRunState.NOT_PREPARED


@pytest.mark.parametrize("method", ["restore", "prepare", "refresh"])
def test_no_historical_witness_backfill_or_requirement_rewrite(tmp_path, method):
    facts, run, _ = _evidence_run()
    store = NativeReviewEvidenceStore(tmp_path)
    store.retain(build_native_review_requirements(run, facts))
    original = requirements_path(tmp_path).read_bytes()
    getattr(workflow(tmp_path), method)(run, facts)
    assert requirements_path(tmp_path).read_bytes() == original
    assert not witnesses(tmp_path)
    assert not (tmp_path / "preparation-intents").exists()


def test_other_run_lineage_does_not_change_current_applicability(tmp_path):
    facts, run, _ = _evidence_run()
    path = tmp_path / "visual-v2" / "foreign-run" / "instrument" / "1D" / "evidence.json"
    path.parent.mkdir(parents=True)
    path.write_text("{}")
    owner = workflow(tmp_path)
    owner.restore(run, facts)
    assert owner.restoration_result.status is Status.APPLICABILITY_NOT_ESTABLISHED


@pytest.mark.parametrize("fault", ["after-replace", "directory-sync"])
def test_uncertain_witness_publication_resolves_exact_durable_success(tmp_path, monkeypatch, fault):
    import kronos.swing.v1.native_review as module
    facts, run, _ = _evidence_run()
    original_write, original_sync = module._atomic_json, module._sync_native_directory
    injected = []
    def write(path, payload):
        original_write(path, payload)
        if "preparation-witnesses" in path.parts and fault == "after-replace" and not injected:
            injected.append(True)
            raise OSError("after durable replacement")
    def sync(path):
        if "preparation-witnesses" in path.parts and fault == "directory-sync" and not injected:
            injected.append(True)
            raise OSError("first directory sync failed")
        original_sync(path)
    monkeypatch.setattr(module, "_atomic_json", write)
    monkeypatch.setattr(module, "_sync_native_directory", sync)
    owner = workflow(tmp_path)
    snapshot = owner.prepare(run, facts)
    assert injected and snapshot.state is NativeReviewRunState.REVIEW_REQUIRED
    assert len(witnesses(tmp_path)) == 1
    assert owner._store.preparation_authority(run, facts) == "WITNESSED"


def test_failed_refresh_preserves_exact_prior_valid_memory(tmp_path, monkeypatch):
    facts, run, _ = _evidence_run()
    owner = workflow(tmp_path)
    owner.prepare(run, facts)
    prior = owner.snapshot()
    def failed(*args, **kwargs):
        owner._requirements = ()
        owner._analysis.clear()
        raise ValueError("injected refresh failure")
    monkeypatch.setattr(owner, "_refresh_unlocked", failed)
    with pytest.raises(ValueError, match="refresh failure"):
        owner.refresh(run, facts)
    assert owner.snapshot() == prior
    assert len(witnesses(tmp_path)) == 1


def test_unreadable_namespace_cannot_be_treated_as_absence(tmp_path, monkeypatch):
    facts, run, _ = _evidence_run()
    owner = workflow(tmp_path)
    root = tmp_path / "visual-v2" / run.run_identity
    root.mkdir(parents=True)
    original = Path.iterdir
    def denied(path):
        if path == root:
            raise PermissionError("governed lineage unavailable")
        return original(path)
    monkeypatch.setattr(Path, "iterdir", denied)
    with pytest.raises(PermissionError):
        owner.restore(run, facts)
    assert owner.restoration_result.status is Status.FAILED


def test_real_historical_plan_transitive_dependency_blocks(tmp_path):
    from kronos.swing.v1.native_trade_construction import construct_trade_plan, LocalTradePlanStore
    from tests.unit.swing.v1.test_native_trade_construction import _ready, _package, _context
    facts, run, _ = _evidence_run()
    readiness, requirement = _ready()
    plan = construct_trade_plan(requirement, readiness, _package(requirement, readiness),
        _context(requirement.canonical_instrument), created_at=NOW)
    assert requirement == build_native_review_requirements(run, facts)[0]
    LocalTradePlanStore(tmp_path / "trade-construction-v0").retain(plan)
    owner = workflow(tmp_path)
    with pytest.raises(ValueError, match="REQUIRED_EVIDENCE_LOST"):
        owner.restore(run, facts)
    assert owner.restoration_result.status is Status.FAILED


def test_real_historical_pdf_and_chart_lineage_survives_requirement_loss(tmp_path):
    from tests.unit.swing.v1.test_pdf_visual_review import _workflow
    facts, run, _ = _evidence_run()
    owner, transport = _workflow(tmp_path)
    root = tmp_path / "native"
    # Erasing only test fixture witnesses simulates a genuinely pre-witness estate.
    for path in witnesses(root):
        path.unlink()
    for path in (root / "preparation-intents").glob("*.json"):
        path.unlink()
    owner.generate_review_pack()
    requirements_path(root).unlink()
    fresh = NativeReviewWorkflow(NativeReviewEvidenceStore(root),
        chart_store=LocalTradingViewEvidenceStore(tmp_path / "charts"), pdf_transport=transport)
    with pytest.raises(ValueError, match="REQUIRED_EVIDENCE_LOST"):
        fresh.restore(run, facts)
    assert fresh.restoration_result.status is Status.FAILED


def test_independent_v3_plan_does_not_prove_legacy_preparation(tmp_path):
    from kronos.application.swing_trade_window import SwingTradeWindowWorkflow
    from kronos.swing.v1.kr370_step31_handoff import LocalKr370Step31HandoffStore
    from kronos.swing.v1.native_trade_construction import LocalTradePlanStore
    from tests.unit.swing.v1.test_kr370_step31_handoff import _completed, _evidence, _context
    facts, run, _ = _evidence_run()
    completed = _completed(tmp_path / "cycle")
    plan_root = tmp_path / "trade-construction-v0"
    projection = SwingTradeWindowWorkflow(LocalKr370Step31HandoffStore(tmp_path / "handoffs"),
        LocalTradePlanStore(plan_root)).construct(completed, _evidence(completed),
        _context(completed.requirement.canonical_instrument),
        current_run_identity=completed.requirement.native_run_identity,
        current_analysis_boundary=completed.readiness.analysis_boundary, created_at=NOW)
    assert projection.trade_plan is not None
    assert projection.trade_plan.readiness_record_identity.startswith("NATIVE-V3-READINESS-")
    owner = workflow(tmp_path)
    owner.restore(run, facts)
    assert owner.restoration_result.status is Status.APPLICABILITY_NOT_ESTABLISHED


def test_persistent_witness_directory_sync_failure_leaves_no_valid_completion(tmp_path, monkeypatch):
    import kronos.swing.v1.native_review as module
    facts, run, _ = _evidence_run()
    original = module._sync_native_directory
    def denied(path):
        if "preparation-witnesses" in path.parts:
            raise OSError("persistent witness directory sync failure")
        original(path)
    owner = workflow(tmp_path)
    with monkeypatch.context() as patch:
        patch.setattr(module, "_sync_native_directory", denied)
        with pytest.raises(OSError, match="persistent"):
            owner.prepare(run, facts)
    assert not witnesses(tmp_path)
    assert owner.snapshot().state is NativeReviewRunState.NOT_PREPARED
    fresh = workflow(tmp_path)
    with pytest.raises(ValueError, match="INCOMPLETE"):
        fresh.restore(run, facts)
    fresh.prepare(run, facts)
    assert len(witnesses(tmp_path)) == 1


def test_no_analysis_empty_and_receipt_only_assessment_is_inert_uncertainty(tmp_path):
    owner = workflow(tmp_path)
    assert owner.assess_without_analysis().status is Status.APPLICABILITY_NOT_ESTABLISHED
    assert owner.restoration_result.native_run_identity is None
    assert not tuple(tmp_path.rglob("*"))
    for name in ("visual-v3/run/response.json", "layer2-readiness-v3/run/readiness.json", "requests/question.json", "acceptance/receipt.json"):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}")
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert owner.assess_without_analysis().status is Status.APPLICABILITY_NOT_ESTABLISHED
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


@pytest.mark.parametrize("path", ["complete-runs/run.json", "preparation-intents/run.json",
    "preparation-witnesses/run/witness.json", "visual-v2/run/subject/1D/evidence.json",
    "pdf-transport-v3/review-packs/pack.json", "layer2-readiness-v0/run/readiness.json"])
def test_no_analysis_retained_native_or_corrupt_evidence_blocks_without_writes(tmp_path, path):
    owner = workflow(tmp_path)
    target = tmp_path / path
    target.parent.mkdir(parents=True)
    target.write_text("corrupt-or-unresolvable")
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    result = owner.assess_without_analysis()
    assert result.status is Status.FAILED and result.native_run_identity is None
    assert result.evidence[0] in {"MISSING_ANALYSIS_FOR_RETAINED_NATIVE_EVIDENCE",
                                   "NATIVE_REVIEW_APPLICABILITY_UNAVAILABLE"}
    assert result == owner.restoration_result
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


def test_no_analysis_unreadable_namespace_fails_closed(tmp_path, monkeypatch):
    owner = workflow(tmp_path)
    directory = tmp_path / "preparation-witnesses"
    directory.mkdir()
    original = Path.iterdir
    def denied(path):
        if path == directory:
            raise PermissionError("unavailable witness namespace")
        return original(path)
    monkeypatch.setattr(Path, "iterdir", denied)
    assert owner.assess_without_analysis().status is Status.FAILED
    assert owner.restoration_result.evidence == ("NATIVE_REVIEW_APPLICABILITY_UNAVAILABLE",)


@pytest.mark.parametrize("kind", ["witness-root", "intent-file", "dangling-requirement"])
def test_preparation_namespace_symlinks_fail_closed(tmp_path, kind):
    facts, run, _ = _evidence_run()
    workflow(tmp_path).prepare(run, facts)
    if kind == "witness-root":
        source = tmp_path / "preparation-witnesses"
        moved = tmp_path / "moved-witnesses"
        source.rename(moved)
        source.symlink_to(moved, target_is_directory=True)
    elif kind == "intent-file":
        source = tmp_path / "preparation-intents" / (run.run_identity + ".json")
        moved = tmp_path / "moved-intent.json"
        source.rename(moved)
        source.symlink_to(moved)
    else:
        source = requirements_path(tmp_path)
        source.unlink()
        source.symlink_to(tmp_path / "missing.json")
    owner = workflow(tmp_path)
    with pytest.raises(ValueError, match="SYMLINK"):
        owner.restore(run, facts)
    assert owner.restoration_result.status is Status.FAILED


@pytest.mark.parametrize("namespace", ["complete-runs", "preparation-intents"])
def test_retry_recertifies_existing_intent_and_requirement_durability(tmp_path, monkeypatch, namespace):
    import kronos.swing.v1.native_review as module
    facts, run, _ = _evidence_run()
    original = module._sync_native_directory
    failed = []
    def first_failure(path):
        if path.name == namespace and not failed:
            failed.append(True)
            raise OSError("directory rename not certified")
        original(path)
    with monkeypatch.context() as patch:
        patch.setattr(module, "_sync_native_directory", first_failure)
        with pytest.raises(OSError):
            workflow(tmp_path).prepare(run, facts)
    assert not witnesses(tmp_path)
    order = []
    def persistent(path):
        order.append(path.name)
        if path.name == namespace:
            raise OSError("retained directory still unavailable")
        original(path)
    with monkeypatch.context() as patch:
        patch.setattr(module, "_sync_native_directory", persistent)
        with pytest.raises(OSError, match="still unavailable"):
            workflow(tmp_path).prepare(run, facts)
    assert namespace in order and not witnesses(tmp_path)
    order.clear()
    def observed(path):
        order.append(path.name)
        original(path)
    with monkeypatch.context() as patch:
        patch.setattr(module, "_sync_native_directory", observed)
        workflow(tmp_path).prepare(run, facts)
    assert order.index(namespace) < order.index(run.run_identity)
    assert len(witnesses(tmp_path)) == 1


def test_native_sponsor_admission_proves_preparation_even_if_plan_is_lost(tmp_path):
    from kronos.swing.v1.native_sponsor_decision import LocalSponsorDecisionStore, SponsorTradeChoice
    from tests.unit.swing.v1.test_native_sponsor_decision import _go
    facts, run, _ = _evidence_run()
    result, *_ = _go(SponsorTradeChoice.PAPER)
    LocalSponsorDecisionStore(tmp_path / "sponsor-trade-decision-v0").retain(result)
    owner = workflow(tmp_path)
    with pytest.raises(ValueError, match="REQUIRED_EVIDENCE_LOST"):
        owner.restore(run, facts)
    assert owner.assess_without_analysis().status is Status.FAILED


def test_native_lifecycle_with_missing_analysis_remains_unresolved_positive_lineage(tmp_path):
    from kronos.swing.v1.native_active_trade_lifecycle import LocalActiveTradeLifecycleStore
    from tests.unit.swing.v1.test_native_active_trade_lifecycle import _position
    position, *_ = _position()
    LocalActiveTradeLifecycleStore(tmp_path / "active-trade-lifecycle-v0").retain_position(position)
    owner = workflow(tmp_path)
    assert owner.assess_without_analysis().status is Status.FAILED
    assert "NATIVE_LIFECYCLE" in owner.restoration_result.evidence


@pytest.mark.parametrize("path", ["visual-v2/{run}/misplaced.json",
    "charts/native-review-composite-charts/{run}/orphan.png",
    "reference-results/{run}/partial.tmp"])
def test_partial_or_misplaced_exact_legacy_evidence_cannot_look_unprepared(tmp_path, path):
    facts, run, _ = _evidence_run()
    target = tmp_path / path.format(run=run.run_identity)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"retained incomplete evidence")
    owner = workflow(tmp_path)
    with pytest.raises(ValueError, match="REQUIRED_EVIDENCE_LOST"):
        owner.restore(run, facts)
    assert owner.restoration_result.status is Status.FAILED


def test_exact_legacy_namespace_rejects_configured_root_symlink(tmp_path):
    facts, run, _ = _evidence_run()
    target = tmp_path / "other-visual"
    target.mkdir()
    (tmp_path / "visual-v2").symlink_to(target, target_is_directory=True)
    owner = workflow(tmp_path)
    with pytest.raises(ValueError, match="SYMLINK"):
        owner.restore(run, facts)
    assert owner.restoration_result.status is Status.FAILED


def test_orphaned_native_sponsor_position_remains_positive_incomplete_lineage(tmp_path):
    from kronos.swing.v1.native_sponsor_decision import LocalSponsorDecisionStore, SponsorTradeChoice
    from tests.unit.swing.v1.test_native_sponsor_decision import _go
    facts, run, _ = _evidence_run()
    result, plan, *_ = _go(SponsorTradeChoice.PAPER)
    store = LocalSponsorDecisionStore(tmp_path / "sponsor-trade-decision-v0")
    store.retain(result)
    (store.root / run.run_identity / plan.trade_plan_id / "decision.json").unlink()
    owner = workflow(tmp_path)
    with pytest.raises((OSError, ValueError)):
        owner.restore(run, facts)
    assert owner.restoration_result.status is Status.FAILED


def test_independent_mcx_sponsor_namespace_does_not_prove_native_preparation(tmp_path):
    facts, run, _ = _evidence_run()
    target = tmp_path / "sponsor-trade-decision-v0" / run.run_identity / ("MCX-TRADE-PLAN-" + "a" * 64) / "position.json"
    target.parent.mkdir(parents=True)
    target.write_text("MCX owner validates its independent evidence")
    owner = workflow(tmp_path)
    owner.restore(run, facts)
    assert owner.restoration_result.status is Status.APPLICABILITY_NOT_ESTABLISHED
    assert owner.assess_without_analysis().status is Status.APPLICABILITY_NOT_ESTABLISHED


@pytest.mark.parametrize("filename", ["misplaced.json", "instrument/partial.tmp", "instrument/extra/deep.json"])
def test_plan_layout_corruption_never_becomes_legacy_absence(tmp_path, filename):
    facts, run, _ = _evidence_run()
    path = tmp_path / "trade-construction-v0" / run.run_identity / filename
    path.parent.mkdir(parents=True)
    path.write_text("retained incomplete plan")
    owner = workflow(tmp_path)
    with pytest.raises(ValueError, match="LINEAGE_INVALID"):
        owner.restore(run, facts)
    assert owner.restoration_result.status is Status.FAILED


@pytest.mark.parametrize("record", ["complete-runs", "preparation-intents"])
def test_preparation_record_must_be_regular_file(tmp_path, record):
    facts, run, _ = _evidence_run()
    workflow(tmp_path).prepare(run, facts)
    path = tmp_path / record / (run.run_identity + ".json")
    path.unlink()
    path.mkdir()
    owner = workflow(tmp_path)
    with pytest.raises(ValueError, match="FILE_INVALID"):
        owner.restore(run, facts)
    assert owner.restoration_result.status is Status.FAILED


@pytest.mark.parametrize("namespace", ["pdf-transport-v0", "pdf-transport-v3"])
@pytest.mark.parametrize("leaf", ["current-review-pack.json", "answer-imports/pack/import.json",
                                  "answer-artifacts/pack/artifact.json"])
def test_orphaned_historical_pdf_reference_cannot_become_no_applicability(tmp_path, namespace, leaf):
    facts, run, _ = _evidence_run()
    path = tmp_path / namespace / leaf
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"record": {"review_pack_id": "missing-pack"}}))
    owner = workflow(tmp_path)
    with pytest.raises(ValueError, match="HISTORICAL_PACK_LINEAGE_UNAVAILABLE"):
        owner.restore(run, facts)
    assert owner.restoration_result.status is Status.FAILED
    assert owner.assess_without_analysis().status is Status.FAILED
