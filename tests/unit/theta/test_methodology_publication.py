"""TE-05B publication/admission only. Disposable evidence, no assessment."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import inspect
import json
from pathlib import Path

import pytest

from kronos.theta.contracts import SUBJECTS, ThetaError, digest, encode, stamp
from kronos.theta.contracts_v3 import validate_question_v3
from kronos.theta.methodology import (ThetaMethodologyPublication, ROOT, RESEARCH_ID,
    ASSESSMENT_ID, DECISION_ID, RESEARCH_SHA256, ASSESSMENT_SHA256,
    SPONSOR_ORDER_SHA256, MANIFEST_NAME, DECISION_NAME)
from kronos.theta.producer_v3 import V3QuestionProducer
from kronos.theta.store import ThetaStore, directory, read_at
from kronos.theta.workflow import ThetaWorkflow
from tests.unit.theta.test_combined_intake import authority_adapter, snapshot
from tests.unit.theta.test_producer_v3 import fixture as synthetic_fixture, generated, completed
from tests.unit.theta.test_workflow import chart

RETAINED_ROOT = ROOT
RETAINED_RESEARCH_SHA256 = RESEARCH_SHA256
RETAINED_ASSESSMENT_SHA256 = ASSESSMENT_SHA256


@pytest.fixture(autouse=True)
def provisional_ca_assignment(tmp_path, monkeypatch):
    """Pending CA: qualify mechanics, never publish fictitious authority.

    Only this disposable test process receives a visibly synthetic governance
    fixture. Once CA has supplied the real assignment and the final decision is
    pinned, these same tests run directly against the final retained bytes.
    """
    import kronos.theta.methodology as module
    if module.DECISION_SHA256 is not None:
        return
    fixture_root = tmp_path / "SYNTHETIC-CA-QUALIFICATION-ONLY"
    fixture_root.mkdir()
    values = {name: json.loads(raw) for name, raw in artifacts().items()}
    simulated = "SYNTHETIC-CA-ASSIGNMENT-FOR-QUALIFICATION"
    hashes = {}
    for identity in (RESEARCH_ID, ASSESSMENT_ID):
        values[identity + ".json"]["governance_decision"] = simulated
        hashes[identity] = digest(encode(values[identity + ".json"]))
    decision = values[DECISION_NAME]
    decision.update(decision_identity=simulated, adr_identity=simulated,
        publication_status="SYNTHETIC_QUALIFICATION_NOT_GOVERNANCE_AUTHORITY",
        effective_after="2026-10-12T08:30:00+00:00")
    for identity, sha in hashes.items():
        decision["methodologies"][identity]["sha256"] = sha
    decision_hash = digest(encode(decision))
    values[MANIFEST_NAME] = {"decision_identity": simulated, "files": {
        RESEARCH_ID + ".json": hashes[RESEARCH_ID],
        ASSESSMENT_ID + ".json": hashes[ASSESSMENT_ID], DECISION_NAME: decision_hash}}
    for name, value in values.items():
        (fixture_root / name).write_bytes(encode(value))
    monkeypatch.setattr(module, "DECISION_ID", simulated)
    monkeypatch.setattr(module, "DECISION_SHA256", decision_hash)
    monkeypatch.setattr(module, "RESEARCH_SHA256", hashes[RESEARCH_ID])
    monkeypatch.setattr(module, "ASSESSMENT_SHA256", hashes[ASSESSMENT_ID])
    monkeypatch.setitem(globals(), "ROOT", fixture_root)
    monkeypatch.setitem(globals(), "DECISION_ID", simulated)
    monkeypatch.setitem(globals(), "RESEARCH_SHA256", hashes[RESEARCH_ID])
    monkeypatch.setitem(globals(), "ASSESSMENT_SHA256", hashes[ASSESSMENT_ID])


def publication():
    return ThetaMethodologyPublication(ROOT)


def test_retained_publication_canonical_pins_and_pending_status():
    """Check actual candidate files, not the disposable CA fixture."""
    for identity, sha in ((RESEARCH_ID, RETAINED_RESEARCH_SHA256),
                          (ASSESSMENT_ID, RETAINED_ASSESSMENT_SHA256)):
        raw = (RETAINED_ROOT / (identity + ".json")).read_bytes()
        assert raw == encode(json.loads(raw)) and digest(raw) == sha
    decision_raw = (RETAINED_ROOT / DECISION_NAME).read_bytes()
    decision = json.loads(decision_raw)
    manifest_raw = (RETAINED_ROOT / MANIFEST_NAME).read_bytes()
    manifest = json.loads(manifest_raw)
    assert decision_raw == encode(decision) and manifest_raw == encode(manifest)
    assert manifest["files"][DECISION_NAME] == digest(decision_raw)
    assert manifest["files"][RESEARCH_ID + ".json"] == RETAINED_RESEARCH_SHA256
    assert manifest["files"][ASSESSMENT_ID + ".json"] == RETAINED_ASSESSMENT_SHA256
    if decision["adr_identity"] is None:
        assert decision["decision_identity"] == "PENDING_CA_ASSIGNMENT"
        assert decision["effective_after"] is None
        assert decision["publication_status"] == "CANDIDATE_PENDING_CA_ADR"
    else:
        assert decision["decision_identity"] == decision["adr_identity"] == "ADR-0067"
        assert decision["publication_status"] == "APPROVED_PROSPECTIVE_CANDIDATE"
        assert decision["effective_after"] == "2026-10-12T09:20:00+00:00"
        assert decision["ca_assignment"] == {
            "identity": "ADR-0067",
            "title": "Theta V1 Astra Research and Analytical Assessment Methodology Governance",
            "canonical_path": "docs/architecture/adr/ADR-0067-THETA-V1-RESEARCH-AND-ASSESSMENT-METHODOLOGY.md",
            "scope": "Coordinated governance of the separately versioned Theta V1 Astra Research Methodology and Theta V1 Analytical Assessment Methodology.",
            "supersedes": "NONE", "preserved_temporal_foundation": "ADR-0066"}


def test_adr0067_binds_publications_and_preserves_adr0066():
    adr = RETAINED_ROOT.parents[1] / "adr" / "ADR-0067-THETA-V1-RESEARCH-AND-ASSESSMENT-METHODOLOGY.md"
    temporal = RETAINED_ROOT.parents[1] / "adr" / "ADR-0066-THETA-PROSPECTIVE-INFORMATION-SET-AND-RETRIEVAL-TIMES.md"
    text = adr.read_text()
    assert "# ADR-0067 — Theta V1 Astra Research and Analytical Assessment Methodology Governance" in text
    assert RETAINED_RESEARCH_SHA256 in text and RETAINED_ASSESSMENT_SHA256 in text
    assert "**Supersedes:** None" in text and "ADR-0066 remains the unchanged temporal foundation" in text
    assert digest(temporal.read_bytes()) == "f44c0539745dbe36134873e4a8c52978a75ca46632bdb6ae7846c02076833587"


def test_pending_ca_assignment_cannot_admit_even_with_hash(monkeypatch):
    import kronos.theta.methodology as module
    monkeypatch.setattr(module, "DECISION_ID", "PENDING_CA_ASSIGNMENT")
    monkeypatch.setattr(module, "DECISION_SHA256", digest((RETAINED_ROOT / DECISION_NAME).read_bytes()))
    with pytest.raises(ThetaError, match="THETA_METHODOLOGY_GOVERNANCE_UNAVAILABLE"):
        ThetaMethodologyPublication(RETAINED_ROOT).research_inputs(datetime(2026, 10, 12, 12, tzinfo=timezone.utc))


def artifacts():
    with directory(ROOT) as fd:
        return {name: read_at(fd, name) for name in
            (RESEARCH_ID + ".json", ASSESSMENT_ID + ".json", MANIFEST_NAME, DECISION_NAME)}


def effective_after():
    return stamp(json.loads(artifacts()[DECISION_NAME])["effective_after"])


def disposable_publication(root):
    root.mkdir()
    for name, raw in artifacts().items():
        (root / name).write_bytes(raw)
    return ThetaMethodologyPublication(root)


def genuine_fixture(root, *, at=None, publication=None):
    """Exercise non-synthetic policy admission with expressly synthetic fixtures.

    The resulting Question is a disposable proof of the genuine commissioning
    path, not a real forecast. No production or Sponsor chart is used.
    """
    boundary = effective_after()
    clock = [boundary + timedelta(seconds=1)]
    wf = ThetaWorkflow(ThetaStore(root / "evidence"), inbox=root / "answers", outbox=root / "questions",
        clock=lambda: clock[0], qualification_mode=False)
    for role in (*SUBJECTS, "GLOBAL_MACRO"):
        wf.intake_chart(subject=role, label="SYNTHETIC TE05B qualification - " + role,
            information_cutoff=clock[0].isoformat(), media_type="image/png", payload=chart())
    clock[0] = boundary + timedelta(seconds=2) if at is None else at
    return V3QuestionProducer(wf, authority_adapter(),
        published_methodology=ThetaMethodologyPublication(ROOT) if publication is None else publication), clock


def test_exact_canonical_policy_bytes_hashes_and_approved_text():
    paths = ((RESEARCH_ID, RESEARCH_SHA256), (ASSESSMENT_ID, ASSESSMENT_SHA256))
    for identity, expected in paths:
        with directory(ROOT) as fd:
            raw = read_at(fd, identity + ".json")
        value = json.loads(raw)
        assert raw == encode(value) and digest(raw) == expected
        assert value["identity"] == identity and value["version"] == "1.0.0"
        assert value["governance_decision"] == DECISION_ID
    assessment = json.loads((ROOT / (ASSESSMENT_ID + ".json")).read_bytes())
    assert [c["identity"] for c in assessment["criteria"]] == ["C" + str(n) for n in range(1, 10)]
    assert [c["title"] for c in assessment["criteria"]] == [
        "Identity, provenance and references", "Horizon-specific rationale", "Supportive and opposing research",
        "Assumptions and limitations", "T0 and source chronology", "Chart/fundamental reconciliation",
        "Scheduled-event treatment", "Confidence justification and path risk", "Declared unresolved contradictions"]
    assert set(assessment["states"]) == {"DOCUMENTED", "LIMITED", "NOT_EVALUABLE"}
    assert assessment["aggregation"] == ["An assessment-admission failure gives NOT_EVALUABLE.",
        "Otherwise, any LIMITED criterion gives LIMITED.",
        "Otherwise, all criteria are DOCUMENTED, giving DOCUMENTED."]
    assert "without requiring fabricated opposition" in assessment["criteria"][2]["deterministic_result"]
    assert "applicable declared unresolved contradiction yields LIMITED" in assessment["criteria"][8]["deterministic_result"]
    assert "NONE FOUND" in assessment["clarifications"]["empty_evidence"]
    assert "No commodity-level roll-up" in assessment["independence"]


def test_manifest_decision_and_exact_sponsor_order_are_bound():
    import kronos.theta.methodology as module
    raw = artifacts()
    decision = json.loads(raw[DECISION_NAME])
    manifest = json.loads(raw[MANIFEST_NAME])
    assert digest(raw[DECISION_NAME]) == module.DECISION_SHA256
    assert all(raw[name] == encode(json.loads(raw[name])) for name in raw)
    assert manifest == {"decision_identity": DECISION_ID,
        "files": {name: digest(value) for name, value in raw.items() if name != MANIFEST_NAME}}
    assert decision["approval"] == "SPONSOR_APPROVED" and decision["adr_identity"]
    assert digest(decision["sponsor_order_utf8"].encode()) == decision["sponsor_order_sha256"] == SPONSOR_ORDER_SHA256
    assert decision["methodologies"] == {
        RESEARCH_ID: {"identity": RESEARCH_ID, "version": "1.0.0", "sha256": RESEARCH_SHA256},
        ASSESSMENT_ID: {"identity": ASSESSMENT_ID, "version": "1.0.0", "sha256": ASSESSMENT_SHA256}}


def test_publication_read_is_inert_and_future_assessment_policy_is_loadable():
    before = {p.name: p.read_bytes() for p in ROOT.iterdir() if p.is_file()}
    pub = publication()
    at = effective_after() + timedelta(seconds=1)
    research = pub.research_inputs(at)
    assessment = pub.assessment_policy(at)
    assert research["descriptor"] == {"identity": RESEARCH_ID, "version": "1.0.0", "sha256": RESEARCH_SHA256}
    assert research["instructions"] == json.loads(before[RESEARCH_ID + ".json"])["instructions"]
    assert assessment["descriptor"] == {"identity": ASSESSMENT_ID, "version": "1.0.0", "sha256": ASSESSMENT_SHA256}
    assert assessment["effective_after"] == effective_after().isoformat()
    assert assessment["prospective_only"] and assessment["policy"] == json.loads(before[ASSESSMENT_ID + ".json"])
    assert {p.name: p.read_bytes() for p in ROOT.iterdir() if p.is_file()} == before
    assert "result" not in assessment and "criterion_results" not in assessment
    assert set(n for n, v in inspect.getmembers(ThetaMethodologyPublication, inspect.isfunction) if not n.startswith("_")) == {"research_inputs", "assessment_policy"}


@pytest.mark.parametrize("offset", [-86400, -1, 0])
@pytest.mark.parametrize("operation", ["research_inputs", "assessment_policy"])
def test_before_and_at_effective_boundary_fail_closed(offset, operation):
    with pytest.raises(ThetaError, match="THETA_METHODOLOGY_NOT_EFFECTIVE"):
        getattr(publication(), operation)(effective_after() + timedelta(seconds=offset))


@pytest.mark.parametrize("at", [None, "APPROVED", datetime(2026, 10, 12, 12, 0), 0])
def test_invalid_timestamp_cannot_claim_prospective_authority(at):
    with pytest.raises(ThetaError, match="THETA_TIMESTAMP_INVALID"):
        publication().research_inputs(at)


def test_same_instant_different_offset_has_same_admission():
    at = effective_after() + timedelta(seconds=1)
    ist = at.astimezone(timezone(timedelta(hours=5, minutes=30)))
    assert publication().research_inputs(at) == publication().research_inputs(ist)


@pytest.mark.parametrize("fake", ["APPROVED", "KRONOS-CA-APPROVED", True,
    {"identity": RESEARCH_ID, "version": "1.0.0", "sha256": RESEARCH_SHA256},
    {"approved": True, "instructions": "approved"}])
def test_arbitrary_approval_string_flag_or_descriptor_cannot_admit(tmp_path, fake):
    p, _ = synthetic_fixture(tmp_path)
    p.workflow.qualification_mode = False
    before = snapshot(p.store.root)
    with pytest.raises(ThetaError, match="THETA_METHODOLOGY_CONFIGURATION_INVALID"):
        V3QuestionProducer(p.workflow, authority_adapter(), published_methodology=fake)
    assert snapshot(p.store.root) == before
    with pytest.raises(ThetaError, match="THETA_METHODOLOGY_UNAVAILABLE"):
        p.create()


def test_published_and_synthetic_paths_cannot_be_combined(tmp_path):
    p, _ = synthetic_fixture(tmp_path)
    with pytest.raises(ThetaError, match="THETA_METHODOLOGY_CONFIGURATION_INVALID"):
        V3QuestionProducer(p.workflow, authority_adapter(), synthetic_methodology=p.synthetic_methodology,
                          published_methodology=publication())


@pytest.mark.parametrize("name", [RESEARCH_ID + ".json", ASSESSMENT_ID + ".json", DECISION_NAME, MANIFEST_NAME])
@pytest.mark.parametrize("fault", ["missing", "changed", "symlink", "hardlink"])
def test_missing_corrupt_or_aliased_publication_fails_closed(tmp_path, name, fault):
    pub = disposable_publication(tmp_path / "publication")
    path = pub.root / name
    if fault == "missing":
        path.unlink()
    elif fault == "changed":
        path.write_bytes(path.read_bytes() + b" ")
    elif fault == "symlink":
        raw = path.read_bytes()
        path.unlink()
        target = tmp_path / "foreign"
        target.write_bytes(raw)
        path.symlink_to(target)
    else:
        import os
        os.link(path, tmp_path / "hardlink")
    with pytest.raises(ThetaError):
        pub.research_inputs(effective_after() + timedelta(seconds=1))


@pytest.mark.parametrize("change", ["predicate", "approval", "boundary", "descriptor", "adr"])
def test_rehashed_tampering_does_not_create_authority(tmp_path, change):
    pub = disposable_publication(tmp_path / "publication")
    name = ASSESSMENT_ID + ".json" if change == "predicate" else DECISION_NAME
    value = json.loads((pub.root / name).read_bytes())
    if change == "predicate":
        value["criteria"][2]["deterministic_result"] = "Require invented opposing evidence"
    elif change == "approval":
        value["approval"] = "APPROVED_BY_ENGINEERING"
    elif change == "boundary":
        value["effective_after"] = "2020-01-01T00:00:00+00:00"
    elif change == "adr":
        value["adr_identity"] = "ADR-9999"
    else:
        value["methodologies"][RESEARCH_ID]["sha256"] = digest(b"foreign")
    raw = encode(value)
    (pub.root / name).write_bytes(raw)
    manifest = json.loads((pub.root / MANIFEST_NAME).read_bytes())
    manifest["files"][name] = digest(raw)
    (pub.root / MANIFEST_NAME).write_bytes(encode(manifest))
    with pytest.raises(ThetaError):
        pub.research_inputs(effective_after() + timedelta(seconds=1))


def test_source_corruption_after_admission_cannot_use_cached_authority(tmp_path):
    pub = disposable_publication(tmp_path / "publication")
    at = effective_after() + timedelta(seconds=1)
    assert pub.research_inputs(at)
    (pub.root / (RESEARCH_ID + ".json")).write_bytes(b"corrupt")
    with pytest.raises(ThetaError):
        pub.research_inputs(at)


def test_publication_ancestor_symlink_fails_closed(tmp_path):
    pub = disposable_publication(tmp_path / "publication")
    alias = tmp_path / "alias"
    alias.symlink_to(pub.root, target_is_directory=True)
    with pytest.raises(ThetaError):
        ThetaMethodologyPublication(alias).research_inputs(effective_after() + timedelta(seconds=1))


def test_genuine_prospective_question_binds_exact_approved_methodology(tmp_path):
    p, clock = genuine_fixture(tmp_path)
    result, batch, qs, raw, files = generated(p)
    assert not batch["synthetic"] and not result["filename"].startswith("SYNTHETIC_")
    for q in qs.values():
        assert not q["synthetic"] and validate_question_v3(q) == q
        assert q["binding"]["methodology"] == {"identity": RESEARCH_ID, "version": "1.0.0", "sha256": RESEARCH_SHA256}
        assert q["information_cutoff"] == clock[0].isoformat()
        assert q["methodology_instructions"] == publication().research_inputs(clock[0])["instructions"]
        assert stamp(q["created_at"]) > effective_after()
    assert p.selected()["current"]
    before = snapshot(p.store.root)
    clock[0] += timedelta(minutes=1)
    assert p.create() == result and snapshot(p.store.root) == before


@pytest.mark.parametrize("field", ["methodology", "instructions", "target"])
def test_genuine_marker_guard_excludes_only_boolean_field_name(tmp_path, field):
    from kronos.theta.contracts_v3 import make_question_v3
    p, _ = genuine_fixture(tmp_path)
    _, _, qs, _, _ = generated(p)
    q = deepcopy(qs["GOLDM"])
    binding, targets, instructions = q["binding"], q["targets"], q["methodology_instructions"]
    if field == "methodology":
        binding["methodology"]["identity"] = "SYNTHETIC-UNAPPROVED"
    elif field == "instructions":
        instructions += " SYNTHETIC evidence"
    else:
        targets["E1"]["authority_reference"] = "SYNTHETIC-FOREIGN"
    with pytest.raises(ThetaError):
        make_question_v3(binding=binding, targets=targets, created_at=q["created_at"],
            authority_valid_through=q["authority_valid_through"],
            methodology_instructions=instructions, synthetic=False)


def test_methodology_does_not_rewrite_selected_historical_questions(tmp_path):
    old, clock = synthetic_fixture(tmp_path)
    old_result, _, old_qs, _, _ = generated(old)
    originals = {q["question_id"]: old.store.load("v3-questions", q["question_id"] + ".json") for q in old_qs.values()}
    clock[0] = effective_after() + timedelta(seconds=1)
    old.workflow.qualification_mode = False
    new = V3QuestionProducer(old.workflow, authority_adapter(), published_methodology=publication())
    result = new.create()
    assert result["batch_id"] != old_result["batch_id"]
    for s, q in old_qs.items():
        assert result["questions"][s] != q["question_id"]
        assert old.store.load("v3-questions", q["question_id"] + ".json") == originals[q["question_id"]]
        assert q["information_cutoff"] != clock[0].isoformat()


def test_question_before_boundary_cannot_be_reused_or_selected(tmp_path):
    from kronos.theta.contracts_v3 import make_question_v3, make_question_batch_v3
    p, clock = genuine_fixture(tmp_path)
    _, batch, qs, _, _ = generated(p)
    old_time = effective_after() - timedelta(seconds=1)
    foreign = {s: make_question_v3(binding=q["binding"], targets=q["targets"], created_at=old_time.isoformat(),
        authority_valid_through=q["authority_valid_through"], methodology_instructions=q["methodology_instructions"])
        for s, q in qs.items()}
    # Only test policy applicability here; construction alone cannot confer authority.
    for q in foreign.values():
        assert not p._current_inputs(q, p.store.current(), clock[0])


def test_no_evaluator_result_or_forecast_mutation(tmp_path):
    p, clock = genuine_fixture(tmp_path)
    _, batch, qs, _, _ = generated(p)
    before = snapshot(p.store.root)
    p.published_methodology.assessment_policy(clock[0])
    assert snapshot(p.store.root) == before
    assert not any("assessment" in name or "outcome" in name or "accepted" in name for name in before)
    assert all("forecasts" not in q for q in qs.values())


def test_prospective_methodology_answer_intake_and_restart_preserve_forecast(tmp_path):
    """Synthetic values prove the real admission path, not market research."""
    p, clock = genuine_fixture(tmp_path)
    _, batch, qs, _, _ = generated(p)
    answer = completed(batch, qs)
    for child in answer["answers"].values():
        child["analyzed_at"] = (clock[0] + timedelta(hours=2)).isoformat()
        for source in child["research"]["sources"]:
            source["accessed_at"] = (clock[0] + timedelta(hours=1)).isoformat()
    p.workflow.inbox.mkdir()
    raw = json.dumps(answer, indent=2, ensure_ascii=False).encode()
    (p.workflow.inbox / (batch["batch_id"] + "_ANSWERS.json")).write_bytes(raw)
    clock[0] += timedelta(hours=3)
    accepted = p.intake.import_combined_astra_answer(batch["batch_id"])
    assert accepted["package_status"] == "COMPLETE", accepted
    original = {s: p.intake.accepted_evidence(c["receipt_id"])
                for s, c in accepted["children"].items()}
    for s, evidence in original.items():
        assert evidence["package_raw"] == raw
        assert evidence["receipt"]["binding"] == qs[s]["binding"]
    before = snapshot(p.store.root)
    p.published_methodology.assessment_policy(clock[0])
    fresh = V3QuestionProducer(ThetaWorkflow(ThetaStore(p.store.root), inbox=p.workflow.inbox,
        outbox=p.workflow.outbox, clock=lambda: clock[0], qualification_mode=False),
        authority_adapter(), published_methodology=publication())
    assert fresh.selected() == p.selected()
    assert fresh.intake.restore_import(accepted["attempt_id"]) == accepted
    for s, child in accepted["children"].items():
        assert fresh.intake.accepted_evidence(child["receipt_id"]) == original[s]
    assert snapshot(p.store.root) == before
    assert not any("assessment" in name or "outcome" in name for name in before)
