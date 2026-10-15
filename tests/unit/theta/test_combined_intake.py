"""TE-04B SYNTHETIC / NOT FOR GENUINE FORECASTING. No runtime enrollment."""
from copy import deepcopy
from datetime import timedelta
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from kronos.theta.combined_intake import CombinedAnswerIntake
from kronos.theta.contracts import SUBJECTS, ThetaError, digest, encode
from kronos.theta.contracts_v3 import make_question_v3, make_question_batch_v3
from kronos.theta.json_evidence import parse_representations
from kronos.market.option_authority import OptionAuthorityReview
from kronos.theta.target_authority import OwnerOptionAuthority, ThetaTargetAuthorityAdapter
from kronos.theta.packs import binding
from kronos.theta.schema_v3 import MAX_COMBINED_BYTES
from kronos.theta.store import ThetaStore, sealed, unseal
from kronos.theta.workflow import ThetaWorkflow
from tests.unit.theta.test_workflow import chart
from tests.unit.theta.v3_fixture import synthetic_contracts, T0, RECEIPT


def authority_adapter():
    owner = OwnerOptionAuthority()
    # Authentic bounded target review, NOT a methodology approval.
    assert owner.current_sha256 == "bfd2f9c50c823455e124cccf50722d05a92cacaf8665d6b6968d1327940dda1d"
    review = OptionAuthorityReview("KRONOS-CA-TE03A-20261012", owner.instrument.pin.reference,
        owner.market.pin.reference, owner.current_sha256, "APPROVED", "APPROVED")
    return ThetaTargetAuthorityAdapter(OwnerOptionAuthority(review=review))


def fixture_at(root):
    root = Path(root).resolve()
    clock = [T0 - timedelta(hours=1)]
    wf = ThetaWorkflow(ThetaStore(root / "evidence"), inbox=root / "CHATGPT ANSWERS",
        outbox=root / "KRONOS QUESTIONS", clock=lambda: clock[0], qualification_mode=True)
    for role in (*SUBJECTS, "GLOBAL_MACRO"):
        wf.intake_chart(subject=role, label="SYNTHETIC " + role, media_type="image/png",
            information_cutoff=clock[0].isoformat(), payload=chart())
    base, _, answer = synthetic_contracts()
    target = authority_adapter()
    questions = {}
    selection = wf.store.current()
    for subject, old in base.items():
        b = deepcopy(old["binding"])
        b.update(cycle_id=selection["cycle_id"],
                 commodity_chart=binding(wf._role_chart(selection, subject)),
                 macro_chart=binding(wf._role_chart(selection, "GLOBAL_MACRO")))
        actual = target.v3_inputs(subject, T0)
        b["target_authority"] = actual["target_authority"]
        q = make_question_v3(binding=b, targets=actual["targets"], created_at=old["created_at"],
            authority_valid_through=actual["authority_valid_through"],
            methodology_instructions=old["methodology_instructions"], synthetic=True)
        questions[subject] = q
        child = answer["answers"][subject]
        child.update(question_id=q["question_id"], question_sha256=digest(encode(q)), binding=deepcopy(b))
        child["research"]["chart_observations"][0]["chart_reference"] = deepcopy(b["commodity_chart"])
        for h in ("E1", "E2"):
            child["forecasts"][h]["target"] = deepcopy(q["targets"][h])
    batch = make_question_batch_v3(questions)
    answer.update(cycle_id=batch["cycle_id"], question_batch_id=batch["batch_id"],
                  question_batch_sha256=digest(encode(batch)))
    descriptors = {s: {k: deepcopy(q["binding"][k]) for k in ("methodology", "target_authority")}
                   for s, q in questions.items()}
    intake = CombinedAnswerIntake(wf, current_authorities=lambda s, at: descriptors[s])
    clock[0] = RECEIPT
    intake.retain_question_batch(batch, questions)
    intake.select_question_batch(batch["batch_id"])
    wf.inbox.mkdir(parents=True)
    return intake, questions, batch, answer, clock, descriptors


@pytest.fixture
def scenario(tmp_path):
    return fixture_at(tmp_path)


def place(scenario, answer=None, raw=None):
    service, _, batch, initial, *_ = scenario
    raw = raw if raw is not None else json.dumps(initial if answer is None else answer,
                                                ensure_ascii=False, indent=2).encode() + b"\n"
    (service.inbox / (batch["batch_id"] + "_ANSWERS.json")).write_bytes(raw)
    return raw


def run(scenario):
    return scenario[0].import_combined_astra_answer(scenario[2]["batch_id"])


def snapshot(root):
    return {str(p.relative_to(root)): digest(p.read_bytes()) for p in root.rglob("*")
            if p.is_file() and p.name != ".lock"}


def test_complete_exact_raw_receipts_and_restart(scenario):
    service, questions, batch, answer, clock, owners = scenario
    raw = place(scenario)
    selection = service.store.current()
    result = run(scenario)
    assert result["package_status"] == "COMPLETE", result
    assert service.store.current() == selection
    _, spans = parse_representations(raw, maximum=MAX_COMBINED_BYTES)
    for subject, row in result["children"].items():
        assert row["status"] == "ACCEPTED" and row["currentness"] == "CURRENT"
        evidence = service.accepted_evidence(row["receipt_id"])
        receipt = evidence["receipt"]
        assert evidence["package_raw"] == raw
        assert evidence["child_raw"] == spans[subject].raw_bytes == raw[receipt["byte_start"]:receipt["byte_end"]]
        assert receipt["raw_package_sha256"] == digest(raw)
        assert receipt["canonical_package_sha256"] == digest(encode(answer))
        assert receipt["canonical_child_sha256"] == digest(encode(answer["answers"][subject]))
        assert receipt["binding"] == questions[subject]["binding"]
        assert receipt["accepted_at"] == RECEIPT.isoformat()
        assert receipt["information_cutoff"] == questions[subject]["information_cutoff"]
    before = snapshot(service.store.root)
    fresh = CombinedAnswerIntake(ThetaWorkflow(ThetaStore(service.store.root), inbox=service.inbox,
        clock=lambda: clock[0]), current_authorities=lambda s, at: owners[s])
    assert fresh.restore_import(result["attempt_id"]) == result
    assert snapshot(service.store.root) == before


def test_partial_is_independent_and_corrected_new_package_replays_siblings(scenario):
    service, _, batch, answer, *_ = scenario
    answer["answers"]["COPPER"]["forecasts"]["E1"]["confidence_pct"] = "101"
    place(scenario)
    first = run(scenario)
    assert first["package_status"] == "PARTIAL", first
    assert first["children"]["COPPER"]["status"] == "REJECTED"
    assert first["children"]["COPPER"]["reason"] == "THETA_V3_RANGE"
    assert sum(r["receipt_id"] is not None for r in first["children"].values()) == 4
    answer["answer_package_id"] = "SYNTHETIC-PACKAGE-2"
    answer["answers"]["COPPER"]["forecasts"]["E1"]["confidence_pct"] = "82.00"
    place(scenario)
    second = run(scenario)
    assert second["package_status"] == "COMPLETE", second
    for s in SUBJECTS:
        assert second["children"][s]["status"] == ("ACCEPTED" if s == "COPPER" else "REPLAY")
        if s != "COPPER":
            assert second["children"][s]["receipt_id"] == first["children"][s]["receipt_id"]
    assert service.restore_import(first["attempt_id"]) == first


@pytest.mark.parametrize("mutation", [
    lambda a: a.update(schema_version="9.0.0"),
    lambda a: a.update(schema_identity="FOREIGN"),
    lambda a: a.update(answer_package_id=None),
    lambda a: a.update(cycle_id="FOREIGN"),
    lambda a: a.update(question_batch_id="TEB-" + "a"*64),
    lambda a: a.update(question_batch_sha256="0"*64),
    lambda a: a["answers"].pop("COPPER"),
    lambda a: a["answers"].update(FOREIGN={}),
    lambda a: a.update(unexpected=True),
])
def test_wrapper_invalid_accepts_no_children(scenario, mutation):
    mutation(scenario[3]); raw = place(scenario)
    result = run(scenario)
    assert result["package_status"] == "REJECTED", result
    assert not any(r["receipt_id"] for r in result["children"].values())
    assert scenario[0].store.load_blob(digest(raw)) == raw
    assert not (scenario[0].store.root / "v3-receipts").exists()
    assert scenario[0].restore_import(result["attempt_id"]) == result


@pytest.mark.parametrize("mutation", [
    lambda c: c["binding"].update(subject="GOLDM"),
    lambda c: c.update(question_id="TEQ-"+"a"*64),
    lambda c: c.update(question_sha256="a"*64),
    lambda c: c["binding"]["commodity_chart"].update(sha256="a"*64),
    lambda c: c["binding"]["macro_chart"].update(sha256="a"*64),
    lambda c: c["binding"]["target_authority"].update(sha256="a"*64),
    lambda c: c["binding"]["methodology"].update(sha256="a"*64),
    lambda c: c["forecasts"]["E1"]["target"].update(underlying_future="FOREIGN-FUTURE"),
    lambda c: c["forecasts"]["E2"]["target"].update(option_expiry="2026-11-22"),
    lambda c: c.update(information_cutoff="2026-10-12T07:00:00Z"),
    lambda c: c["forecasts"]["E1"].update(lower="120.000"),
    lambda c: c["forecasts"]["E1"].update(lower="130"),
    lambda c: c["forecasts"]["E1"].update(confidence_pct="-1"),
    lambda c: c["forecasts"]["E1"].update(upper=130.0),
    lambda c: c["forecasts"]["E1"].update(material_evidence_ids=["MISSING"]),
    lambda c: c["research"]["sources"][0].update(available_at="2026-10-12T09:00:00Z"),
    lambda c: c["research"]["sources"][0].update(published_at="2026-10-12T09:00:00Z"),
    lambda c: c["research"]["sources"][0].update(accessed_at="2026-10-12T12:00:00Z"),
    lambda c: c["research"]["scheduled_events"][0].update(schedule_known_at="2026-10-12T09:00:00Z"),
    lambda c: c["research"]["sources"][0].update(url="http://localhost/private"),
    lambda c: c["research"]["sources"][0].update(url="http://192.168.1.1/private"),
    lambda c: c.update(kite_token="FORBIDDEN-SYNTHETIC"),
])
def test_child_failure_never_contaminates_siblings(scenario, mutation):
    mutation(scenario[3]["answers"]["COPPER"])
    place(scenario)
    result = run(scenario)
    assert result["package_status"] == "PARTIAL", result
    assert result["children"]["COPPER"]["status"] == "REJECTED"
    assert all(result["children"][s]["status"] == "ACCEPTED" for s in SUBJECTS if s != "COPPER")


@pytest.mark.parametrize("raw", [b"{", b"\xff", b'{"a":1,"a":2}', b'{"a":NaN}',
                                   b'{"a":1e999}', b'{"a":Infinity}', b'{} trailing'])
def test_invalid_json_preserved_not_accepted(scenario, raw):
    place(scenario, raw=raw); result = run(scenario)
    assert result["package_status"] == "REJECTED", result
    assert scenario[0].store.load_blob(digest(raw)) == raw
    assert scenario[0].restore_import(result["attempt_id"]) == result


def test_exact_package_and_child_replay_after_expiry_do_not_change_evidence(scenario):
    service, _, _, answer, clock, *_ = scenario
    place(scenario); first = run(scenario)
    before = snapshot(service.store.root)
    clock[0] += timedelta(days=80)
    replay = run(scenario)
    assert replay["package_status"] == "REPLAY"
    assert all(r["status"] == "REPLAY" and r["currentness"] == "STALE" for r in replay["children"].values())
    assert snapshot(service.store.root) == before
    answer["answer_package_id"] = "SYNTHETIC-HISTORICAL-COPY"
    place(scenario); child_replay = run(scenario)
    assert child_replay["package_status"] == "REPLAY", child_replay
    assert all(r["receipt_id"] == first["children"][s]["receipt_id"] for s,r in child_replay["children"].items())


@pytest.mark.parametrize("kind", ["package", "child", "question"])
def test_immutable_conflict_preserves_accepted_evidence(scenario, kind):
    service, _, _, answer, *_ = scenario
    place(scenario); first = run(scenario)
    originals = {s: service.accepted_evidence(r["receipt_id"]) for s,r in first["children"].items()}
    answer["answers"]["COPPER"]["forecasts"]["E1"]["confidence_pct"] = "70.0"
    if kind != "package":
        answer["answer_package_id"] = "SYNTHETIC-CONFLICT"
    if kind == "question":
        answer["answers"]["COPPER"]["answer_id"] = "SYNTHETIC-NEW-ANSWER"
    place(scenario); result = run(scenario)
    assert result["package_status"] == ("REJECTED" if kind == "package" else "PARTIAL"), result
    if kind != "package":
        assert result["children"]["COPPER"]["receipt_id"] is None
    for s,row in first["children"].items():
        assert service.accepted_evidence(row["receipt_id"]) == originals[s]


@pytest.mark.parametrize("change", ["commodity", "macro", "target", "methodology", "question", "cycle", "missing_owner"])
def test_stale_evidence_retained_without_becoming_current(scenario, change):
    service, _, _, _, clock, owners = scenario
    if change in {"commodity", "macro"}:
        service.workflow.intake_chart(subject="COPPER" if change == "commodity" else "GLOBAL_MACRO",
            label="SYNTHETIC replacement", media_type="image/png", payload=chart(),
            information_cutoff=clock[0].isoformat())
    elif change in {"target", "methodology"}:
        owners["COPPER"]["target_authority" if change == "target" else "methodology"]["sha256"] = "0"*64
    elif change == "missing_owner":
        service.current_authorities = None
    else:
        selection = service.store.current()
        if change == "question":
            selection["v3_questions"]["COPPER"] = "TEQ-"+"a"*64
        else:
            # Historical explicit no-current selection, not a new fabricated cycle.
            selection.pop("v3_questions")
        service.store.select(selection)
    before_selection = service.store.current()
    place(scenario); result = run(scenario)
    assert result["package_status"] == "COMPLETE", result
    assert result["children"]["COPPER"]["status"] == "STALE"
    assert result["children"]["COPPER"]["currentness"] != "CURRENT"
    assert service.store.current() == before_selection
    assert service.restore_import(result["attempt_id"]) == result


@pytest.mark.parametrize("kind", ["wrong_name", "symlink", "hardlink", "directory", "fifo", "oversized", "empty"])
def test_safe_exact_file_discovery(scenario, tmp_path, kind):
    service, _, batch, *_ = scenario
    name = service.inbox / (batch["batch_id"] + "_ANSWERS.json")
    if kind == "wrong_name":
        (service.inbox / "LATEST_COPPER.json").write_bytes(encode(scenario[3]))
    elif kind in {"symlink", "hardlink"}:
        target = tmp_path / "outside.json"; target.write_bytes(encode(scenario[3]))
        name.symlink_to(target) if kind == "symlink" else os.link(target, name)
    elif kind == "directory":
        name.mkdir()
    elif kind == "fifo":
        os.mkfifo(name)
    elif kind == "oversized":
        with name.open("wb") as stream:
            stream.truncate(MAX_COMBINED_BYTES+1)
    else:
        name.touch()
    result = run(scenario)
    assert result["package_status"] == "REJECTED", result
    assert not (service.store.root / "v3-receipts").exists()
    assert name.exists() or kind == "wrong_name"


@pytest.mark.parametrize("identity", ["../../escape", "TEB-../escape", "", None, 123])
def test_identity_cannot_supply_path(scenario, identity):
    result = scenario[0].import_combined_astra_answer(identity)
    assert result["reason"] == "THETA_INTAKE_IDENTITY_INVALID"


@pytest.mark.parametrize("family", ["blobs", "v3-receipts", "v3-answer-identities", "v3-question-answers", "v3-imports"])
def test_crash_before_publication_does_not_restore_acceptance(scenario, monkeypatch, family):
    service = scenario[0]
    raw = place(scenario)
    original = service.store.retain
    def fail(f, name, payload):
        if f == family:
            raise OSError("SYNTHETIC simulated crash")
        return original(f, name, payload)
    monkeypatch.setattr(service.store, "retain", fail)
    result = run(scenario)
    assert result["package_status"] == "REJECTED", result
    monkeypatch.setattr(service.store, "retain", original)
    aid = "TIA-"+digest(encode([scenario[2]["batch_id"],digest(raw)]))
    with pytest.raises(ThetaError, match="RESTORE_INVALID"):
        service.restore_import(aid)
    assert run(scenario)["reason"] == "THETA_INTAKE_INCOMPLETE"


@pytest.mark.parametrize("target", ["package", "child", "receipt", "intent", "identity", "commit", "rejection"])
def test_corrupt_graph_fails_closed_no_reconstruction(scenario, target):
    service = scenario[0]
    if target == "rejection":
        scenario[3]["answers"]["COPPER"]["forecasts"]["E1"]["confidence_pct"] = "101"
    place(scenario); result = run(scenario)
    receipt_id = result["children"]["GOLDM"]["receipt_id"]
    receipt = service.accepted_evidence(receipt_id)["receipt"]
    paths = {"package": service.store.root/"blobs"/receipt["raw_package_sha256"],
             "child": service.store.root/"blobs"/receipt["raw_child_sha256"],
             "receipt": service.store.root/"v3-receipts"/(receipt_id+".json"),
             "intent": service.store.root/"v3-intents"/(result["attempt_id"]+".json"),
             "identity": next((service.store.root/"v3-answer-identities").iterdir()),
             "commit": service.store.root/"v3-imports"/(result["attempt_id"]+".json")}
    path = next((service.store.root/"v3-rejections").iterdir()) if target == "rejection" else paths[target]
    path.write_bytes(b"corrupt")
    before = snapshot(service.store.root)
    with pytest.raises(ThetaError, match="RESTORE_INVALID"):
        service.restore_import(result["attempt_id"])
    assert snapshot(service.store.root) == before


def test_failed_selection_publication_never_currentizes(scenario, monkeypatch):
    service = scenario[0]
    selection = service.store.current()
    selection.pop("v3_questions"); selection.pop("v3_question_batch")
    service.store.select(selection)
    import kronos.theta.store as module
    original = module.write_at
    def fail(fd, name, payload, **kwargs):
        if name == "current.json":
            raise OSError("SYNTHETIC pointer publication failure")
        return original(fd, name, payload, **kwargs)
    monkeypatch.setattr(module, "write_at", fail)
    with pytest.raises(OSError):
        service.select_question_batch(scenario[2]["batch_id"])
    assert service.store.current() == selection
    place(scenario); result = run(scenario)
    assert all(c["currentness"] == "HISTORICAL" for c in result["children"].values())


def test_real_fresh_process_restores_exact_result_without_writes(scenario):
    service = scenario[0]
    place(scenario); result = run(scenario)
    before = snapshot(service.store.root)
    code = '''import json,sys
from pathlib import Path
from datetime import datetime
from kronos.theta.store import ThetaStore
from kronos.theta.workflow import ThetaWorkflow
from kronos.theta.combined_intake import CombinedAnswerIntake
root,aid,bid,now=sys.argv[1:]
wf=ThetaWorkflow(ThetaStore(Path(root)),clock=lambda:datetime.fromisoformat(now))
service=CombinedAnswerIntake(wf)
_,questions=service._batch(bid)
service.current_authorities=lambda s,at:{k:questions[s]["binding"][k] for k in ("methodology","target_authority")}
print(json.dumps(service.restore_import(aid),sort_keys=True))
'''
    restored = subprocess.run([sys.executable,"-B","-c",code,str(service.store.root),
        result["attempt_id"],scenario[2]["batch_id"],RECEIPT.isoformat()],check=True,capture_output=True,text=True)
    assert json.loads(restored.stdout) == result
    assert snapshot(service.store.root) == before


def test_partial_successor_never_substitutes_old_copper_and_old_replay_stays_historical(scenario):
    service, questions, batch, answer, *_ = scenario
    place(scenario); first = run(scenario)
    revised = {s: make_question_v3(binding=q["binding"], targets=q["targets"],
        created_at=q["created_at"], authority_valid_through=q["authority_valid_through"],
        methodology_instructions=q["methodology_instructions"]+" SYNTHETIC successor", synthetic=True)
        for s,q in questions.items()}
    successor = make_question_batch_v3(revised)
    service.retain_question_batch(successor, revised)
    service.select_question_batch(successor["batch_id"])
    new_answer = deepcopy(answer)
    new_answer.update(answer_package_id="SYNTHETIC-SUCCESSOR", question_batch_id=successor["batch_id"],
                      question_batch_sha256=digest(encode(successor)))
    for s,c in new_answer["answers"].items():
        c.update(answer_id=c["answer_id"]+"-NEXT", question_id=revised[s]["question_id"],
                 question_sha256=digest(encode(revised[s])))
    new_answer["answers"]["COPPER"]["forecasts"]["E1"]["confidence_pct"] = "101"
    (service.inbox/(successor["batch_id"]+"_ANSWERS.json")).write_bytes(encode(new_answer))
    second = service.import_combined_astra_answer(successor["batch_id"])
    assert second["package_status"] == "PARTIAL", second
    assert second["children"]["COPPER"]["receipt_id"] is None
    selection = service.store.current()
    old_replay = run(scenario)
    assert old_replay["package_status"] == "REPLAY"
    assert all(c["currentness"] == "SUPERSEDED" for c in old_replay["children"].values())
    assert service.store.current() == selection
    assert service.accepted_evidence(first["children"]["COPPER"]["receipt_id"])


def test_same_canonical_different_raw_package_is_conflict(scenario):
    raw = place(scenario); first = run(scenario)
    place(scenario, raw=raw+b" \n")
    result = run(scenario)
    assert result["reason"] == "THETA_INTAKE_PACKAGE_IDENTITY_CONFLICT"
    assert scenario[0].restore_import(first["attempt_id"]) == first


def test_identical_child_in_new_envelope_preserves_own_original_offsets(scenario):
    service = scenario[0]
    place(scenario); first = run(scenario)
    scenario[3]["answer_package_id"] = "SYNTHETIC-LONGER-ENVELOPE-PACKAGE-ID"
    place(scenario); replay = run(scenario)
    assert replay["package_status"] == "REPLAY", replay
    assert all(c["receipt_id"] == first["children"][s]["receipt_id"] for s,c in replay["children"].items())
    assert service.restore_import(replay["attempt_id"]) == replay


def test_duplicate_child_identity_respects_frozen_collision_rejection(scenario):
    scenario[3]["answers"]["COPPER"]["answer_id"] = scenario[3]["answers"]["GOLDM"]["answer_id"]
    place(scenario); result = run(scenario)
    assert result["package_status"] == "PARTIAL"
    assert sum(c["receipt_id"] is not None for c in result["children"].values()) == 3
    for s in ("GOLDM", "COPPER"):
        assert result["children"][s]["reason"] == "THETA_V3_IDENTITY_CONFLICT"


def test_symlinked_inbox_component_fails_closed(scenario):
    service = scenario[0]
    place(scenario)
    alternate = service.inbox.parent/"alternate"
    service.inbox.rename(alternate)
    service.inbox.symlink_to(alternate, target_is_directory=True)
    assert run(scenario)["package_status"] == "REJECTED"


def test_concurrent_replacement_during_read_fails_closed(scenario, monkeypatch):
    from types import SimpleNamespace
    import kronos.theta.combined_intake as module
    place(scenario)
    actual = os.stat
    def changed(path, **kwargs):
        value = actual(path, **kwargs)
        if kwargs.get("follow_symlinks") is False and str(path).endswith("_ANSWERS.json"):
            fields = {k:getattr(value,k) for k in ("st_dev","st_ino","st_size","st_mtime_ns","st_ctime_ns","st_nlink")}
            fields["st_ino"] += 1
            return SimpleNamespace(**fields)
        return value
    monkeypatch.setattr(module.os,"stat",changed)
    assert run(scenario)["reason"] == "THETA_INTAKE_FILE_UNSTABLE"


def test_crash_after_commit_publication_restores_original_time(scenario, monkeypatch):
    service = scenario[0]
    place(scenario)
    original = service.store.retain
    def fail(family, name, payload):
        original(family, name, payload)
        if family == "v3-imports":
            raise OSError("SYNTHETIC acknowledgement lost after durable commit")
    monkeypatch.setattr(service.store,"retain",fail)
    assert run(scenario)["package_status"] == "REJECTED"
    monkeypatch.setattr(service.store,"retain",original)
    replay = run(scenario)
    assert replay["package_status"] == "REPLAY"
    for row in replay["children"].values():
        assert service.accepted_evidence(row["receipt_id"])["receipt"]["accepted_at"] == RECEIPT.isoformat()


def test_unicode_escaped_keys_and_decimal_text_preserved(scenario):
    raw = json.dumps(scenario[3],ensure_ascii=True,indent=3).encode().replace(b'"answers":',b'"answe\\u0072s":')
    place(scenario,raw=raw); result = run(scenario)
    assert result["package_status"] == "COMPLETE", result
    e = scenario[0].accepted_evidence(result["children"]["GOLDM"]["receipt_id"])
    assert e["package_raw"] == raw
    assert b'120.000' in e["child_raw"] and b'\\u2014' in e["child_raw"]


def test_wrapper_foreign_bytes_do_not_override_prior_acceptance(scenario):
    service = scenario[0]
    place(scenario); first = run(scenario)
    scenario[3]["question_batch_id"] = "TEB-"+"0"*64
    place(scenario); rejected = run(scenario)
    assert rejected["package_status"] == "REJECTED"
    assert service.restore_import(first["attempt_id"]) == first


def test_intake_does_not_create_legacy_outlook_or_analytical_records(scenario):
    service = scenario[0]
    before = service.workflow.summary()
    place(scenario); assert run(scenario)["package_status"] == "COMPLETE"
    assert service.workflow.summary() == before
    assert not (service.store.root/"accepted").exists()
    assert not (service.store.root/"outcomes").exists()


@pytest.mark.parametrize("point", ["child_bytes", "second_receipt", "fourth_receipt"])
def test_partial_child_publication_never_looks_accepted(scenario, monkeypatch, point):
    service = scenario[0]
    raw = place(scenario)
    original = service.store.retain
    receipts = [0]
    def fail(family,name,payload):
        if family == "v3-receipts":
            receipts[0] += 1
            if receipts[0] == {"second_receipt":2,"fourth_receipt":4}.get(point):
                raise OSError("SYNTHETIC interrupted siblings")
        if point == "child_bytes" and family == "blobs" and name != digest(raw):
            raise OSError("SYNTHETIC child evidence failure")
        return original(family,name,payload)
    monkeypatch.setattr(service.store,"retain",fail)
    assert run(scenario)["package_status"] == "REJECTED"
    monkeypatch.setattr(service.store,"retain",original)
    aid = "TIA-"+digest(encode([scenario[2]["batch_id"],digest(raw)]))
    fresh = CombinedAnswerIntake(ThetaWorkflow(ThetaStore(service.store.root),clock=lambda:RECEIPT))
    with pytest.raises(ThetaError,match="RESTORE_INVALID"):
        fresh.restore_import(aid)


def test_later_interrupted_package_does_not_damage_original(scenario, monkeypatch):
    service = scenario[0]
    place(scenario); original_result = run(scenario)
    scenario[3]["answer_package_id"] = "SYNTHETIC-INTERRUPTED-COPY"
    place(scenario)
    retain = service.store.retain
    def fail(family,name,payload):
        if family == "v3-imports":
            raise OSError("SYNTHETIC interrupted")
        return retain(family,name,payload)
    monkeypatch.setattr(service.store,"retain",fail)
    assert run(scenario)["package_status"] == "REJECTED"
    assert service.restore_import(original_result["attempt_id"]) == original_result


def test_partial_new_instance_retains_exact_rejections(scenario):
    service = scenario[0]
    scenario[3]["answers"]["COPPER"]["forecasts"]["E1"]["confidence_pct"] = "101"
    place(scenario); original = run(scenario)
    owners = scenario[5]
    fresh = CombinedAnswerIntake(ThetaWorkflow(ThetaStore(service.store.root),clock=lambda:RECEIPT),
        current_authorities=lambda s,at:owners[s])
    assert fresh.restore_import(original["attempt_id"]) == original
