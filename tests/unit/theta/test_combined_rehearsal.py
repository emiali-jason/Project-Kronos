"""Production-shaped explicit local-file rehearsal; never a running service."""
from datetime import timedelta
import json
from pathlib import Path
import subprocess
import sys

import pytest

from kronos.theta.contracts import digest, encode, ThetaError
from tests.unit.theta.test_combined_intake import fixture_at, place, run, snapshot, RECEIPT


def test_combined_file_end_to_end_rehearsal(tmp_path, request, monkeypatch):
    output = request.config.getoption("--theta-combined-intake-output")
    root = Path(output) if output else tmp_path.resolve()/"theta-te04b-qualification"
    assert root.is_absolute() and root.name == "theta-te04b-qualification"
    root.mkdir(parents=True,exist_ok=False)
    complete = fixture_at(root/"complete")
    service = complete[0]
    raw = place(complete)
    accepted = run(complete)
    assert accepted["package_status"] == "COMPLETE", accepted
    (root/"representative-combined-answer.json").write_bytes(raw)
    evidence = service.accepted_evidence(accepted["children"]["GOLDM"]["receipt_id"])
    (root/"representative-acceptance-receipt.json").write_bytes(encode(evidence["receipt"]))
    (root/"representative-child-original.json").write_bytes(evidence["child_raw"])
    before = snapshot(service.store.root)
    replay = run(complete)
    assert replay["package_status"] == "REPLAY"
    assert snapshot(service.store.root) == before
    complete[3]["answer_package_id"] = "SYNTHETIC-CONFLICT-SAME-CHILD"
    complete[3]["answers"]["COPPER"]["forecasts"]["E1"]["confidence_pct"] = "75"
    place(complete); conflict = run(complete)
    assert conflict["package_status"] == "PARTIAL"
    assert conflict["children"]["COPPER"]["reason"] == "THETA_INTAKE_CHILD_IDENTITY_CONFLICT"
    place(complete,raw=raw)
    complete[4][0] += timedelta(days=80)
    historical = run(complete)
    assert historical["package_status"] == "REPLAY"
    assert all(c["currentness"] == "STALE" for c in historical["children"].values())
    complete[4][0] = RECEIPT  # Restore the test clock, not any production clock.
    code = '''import json,sys
from pathlib import Path
from datetime import datetime
from kronos.theta.store import ThetaStore
from kronos.theta.workflow import ThetaWorkflow
from kronos.theta.combined_intake import CombinedAnswerIntake
root,aid,bid,now=sys.argv[1:]
wf=ThetaWorkflow(ThetaStore(Path(root)),clock=lambda:datetime.fromisoformat(now))
s=CombinedAnswerIntake(wf)
_,questions=s._batch(bid)
s.current_authorities=lambda subject,at:{k:questions[subject]["binding"][k] for k in ("methodology","target_authority")}
print(json.dumps(s.restore_import(aid),sort_keys=True))
'''
    before_restart = snapshot(service.store.root)
    process = subprocess.run([sys.executable,"-B","-c",code,str(service.store.root),
        accepted["attempt_id"],complete[2]["batch_id"],RECEIPT.isoformat()],
        check=True,capture_output=True,text=True)
    restored = json.loads(process.stdout)
    assert restored == accepted
    assert snapshot(service.store.root) == before_restart
    partial = fixture_at(root/"partial")
    partial[3]["answers"]["COPPER"]["forecasts"]["E1"]["upper"] = "-20"
    place(partial); four = run(partial)
    assert four["package_status"] == "PARTIAL"
    assert sum(c["receipt_id"] is not None for c in four["children"].values()) == 4
    crash = fixture_at(root/"crash")
    crashraw = place(crash)
    retain = crash[0].store.retain
    def fail(family,name,payload):
        if family == "v3-imports":
            raise OSError("SYNTHETIC interrupted before import commit")
        return retain(family,name,payload)
    monkeypatch.setattr(crash[0].store,"retain",fail)
    failed = run(crash)
    assert failed["package_status"] == "REJECTED"
    monkeypatch.setattr(crash[0].store,"retain",retain)
    aid = "TIA-"+digest(encode([crash[2]["batch_id"],digest(crashraw)]))
    with pytest.raises(ThetaError,match="RESTORE_INVALID"):
        crash[0].restore_import(aid)
    assert run(crash)["reason"] == "THETA_INTAKE_INCOMPLETE"
    report = {"label":"SYNTHETIC — NOT FOR GENUINE FORECASTING",
        "methodology_authority":"NOT_ESTABLISHED", "complete":accepted,"partial":four,
        "replay":replay,"child_conflict":conflict,"historical_replay":historical,
        "fresh_process_restoration":restored,"restart_writes":0,"crash_result":failed,
        "incomplete_restore":"THETA_INTAKE_RESTORE_INVALID",
        "original_package_sha256":digest(raw),"exact_receipt_timestamp_preserved":True,
        "provider_calls":0,"broker_operations":0,"production_operations":0}
    (root/"rehearsal-report.json").write_bytes(encode(report))
    files = {str(p.relative_to(root)):digest(p.read_bytes()) for p in root.rglob("*") if p.is_file() and p.name!=".lock"}
    (root/"rehearsal-integrity.json").write_bytes(encode(files))
