"""WO-06H deterministic digest and exact, non-general equivalence authority."""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
import importlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

import tests.unit.intraday.test_live_shadow_epochs as epochs
from kronos.application.intraday_live_shadow import IntradayLiveShadowService, REQUIRED
from kronos.intraday.live_shadow import artifact, key, COHORT_A, COHORT_B
from kronos.intraday.live_shadow_epoch_capability import (
    CAPABILITY_IDENTITY, CAPABILITY_VERSION, PROTECTED_CALLABLES,
    capability, policy_declarations,
)
from kronos.intraday.live_shadow_epochs import COLLATERAL, document
from kronos.intraday.live_shadow_persistence import ShadowStore
from kronos.intraday.live_shadow_transition import capability_identity
from kronos.intraday.runtime_identity import LoadedCapability, LauncherConfiguration, create_runtime_manifest
from tests.unit.intraday.test_live_shadow import NOW, seed_row
from tests.unit.intraday.test_runtime_identity import _seed


CURRENT_REVISION = "b89b50f5b536ad79169f92ef4bba0487d34497f6"
CALCULATION = LoadedCapability("WO_06H_LIVE_SHADOW", "1.0.0", "5" * 64)


def sources():
    result = {}
    for module_name in sorted({module for module, _ in PROTECTED_CALLABLES}):
        module = importlib.import_module(module_name)
        result[module_name] = module.__spec__.loader.get_source(module_name)
    return result


def test_capability_is_versioned_canonical_ast_and_repeatable():
    values = [capability(CALCULATION) for _ in range(5)]
    assert len(set(values)) == 1
    assert values[0].identity == CAPABILITY_IDENTITY
    assert values[0].version == CAPABILITY_VERSION == "1.2.0"
    assert len(PROTECTED_CALLABLES) == 38 and len(set(PROTECTED_CALLABLES)) == 38


def test_cross_process_and_cold_warm_imports_are_identical(tmp_path):
    script = ("from kronos.intraday.runtime_identity import LoadedCapability;"
              "from kronos.intraday.live_shadow_epoch_capability import capability;"
              "c=LoadedCapability('WO_06H_LIVE_SHADOW','1.0.0','5'*64);"
              "print(capability(c).implementation_digest);"
              "print(capability(c).implementation_digest)")
    outputs = []
    for path in (tmp_path / "one", tmp_path / "two", tmp_path / "three"):
        path.mkdir()
        value = subprocess.check_output([sys.executable, "-c", script], cwd=path, text=True).splitlines()
        assert value[0] == value[1]
        outputs.append(value[0])
    assert len(set(outputs)) == 1


def test_paths_filenames_line_offsets_and_unrelated_sources_are_not_authority():
    original = sources()
    offset = {name: "\n\n\n" + value for name, value in original.items()}
    unrelated = dict(original, **{"kronos.browser.intraday_routes": "SEMANTICALLY DIFFERENT WO11 ROUTE"})
    assert capability(CALCULATION, sources=original) == capability(CALCULATION, sources=offset)
    assert capability(CALCULATION, sources=original) == capability(CALCULATION, sources=unrelated)
    for name, value in original.items():
        compile(value, "/different/checkout/" + name.replace(".", "/") + ".py", "exec")


def test_contextmanager_wrapper_provenance_is_not_hashed(monkeypatch):
    from kronos.intraday import live_shadow_epochs
    before = capability(CALCULATION)
    def foreign_wrapper(self):
        raise AssertionError("wrapper must not be inspected")
    monkeypatch.setattr(live_shadow_epochs.EpochStore, "transaction", foreign_wrapper)
    assert capability(CALCULATION) == before


@pytest.mark.parametrize("mutation", [
    ("kronos.application.intraday_shadow_epochs", "if not compatible(epoch['body']['proof'], current)",
     "if compatible(epoch['body']['proof'], current)"),
    ("kronos.intraday.live_shadow_epochs", "if value['kind'] != 'transition'", "if value['kind'] == 'transition'"),
    ("kronos.intraday.live_shadow_epochs", "if acceptance.key != key('acceptance'", "if acceptance.key == key('acceptance'"),
    ("kronos.application.intraday_shadow_epochs", "if maintenance is not True or idle is not True", "if maintenance is not True and idle is not True"),
    ("kronos.application.intraday_shadow_epochs", "if not compatible(epoch['body']['proof'], current) and not", "if not compatible(epoch['body']['proof'], current) or not"),
])
def test_acceptance_semantic_mutations_change_digest(mutation):
    module, old, new = mutation; changed = sources()
    assert old in changed[module]
    changed[module] = changed[module].replace(old, new, 1)
    assert capability(CALCULATION, sources=changed) != capability(CALCULATION)


def test_policy_schema_and_calculation_mutations_change_digest():
    declarations = policy_declarations(); changed = deepcopy(declarations)
    changed["fields"]["epoch"] = changed["fields"]["epoch"] + ["UNAUTHORIZED"]
    assert capability(CALCULATION, declarations=changed) != capability(CALCULATION)
    changed = deepcopy(declarations); changed["epoch_policy"] += "-CHANGED"
    assert capability(CALCULATION, declarations=changed) != capability(CALCULATION)
    assert capability(replace(CALCULATION, implementation_digest="6" * 64)) != capability(CALCULATION)


def accepted_service(root):
    service = IntradayLiveShadowService(store=ShadowStore(root), clock=lambda: NOW)
    caps = [LoadedCapability(name, "1.0.0", "a" * 64) for name in sorted(REQUIRED)]
    caps.append(LoadedCapability(CAPABILITY_IDENTITY, "1.1.0", "b" * 64))
    manifest = create_runtime_manifest(_seed(startup_boundary_at=NOW), LauncherConfiguration(8947, False), tuple(caps))
    service.bind_runtime(manifest)
    service.accept_runtime(expected_revision="a" * 40, request_identity="ISOLATED_ACCEPTANCE")
    return service


def retain_historical_counts(service):
    row, _ = seed_row(service, price=None); raw = service._epochs.raw
    body = {key_:value for key_,value in row.body.items() if key_ not in {"epoch", "acceptance"}}
    (raw.root / "observation" / (row.key + ".json")).write_bytes(artifact("observation", row.key, body).payload)
    batch = raw.all("batch")[0].body
    for cohort, count in ((COHORT_A, 33), (COHORT_B, 66)):
        for number in range(count):
            observation = key("observation", service._window.key, cohort, str(number))
            batch_id = key("batch", service._window.key, cohort, str(number))
            pair = dict(body["assessment"], authority="WO06C_ADMISSION_PRICE" if cohort == COHORT_A else "WO06H_COHORT_B_RESEARCH_QUOTE")
            raw.retain(artifact("observation", observation, dict(body, result=str(number), cohort=cohort,
                narrow=cohort == COHORT_A, assessment=pair)))
            raw.retain(artifact("batch", batch_id, dict(batch, expected={
                COHORT_A: [observation] if cohort == COHORT_A else [],
                COHORT_B: [observation] if cohort == COHORT_B else []})))
    service._reconcile()


def corrected_restart(root, predecessor, *, mutation=None):
    at = predecessor.clock() + timedelta(hours=1)
    service = IntradayLiveShadowService(store=ShadowStore(root), clock=lambda: at)
    caps = []
    for value in predecessor._manifest.capabilities:
        if value.identity == CAPABILITY_IDENTITY:
            value = LoadedCapability(value.identity, "1.2.0", "c" * 64)
        if mutation == value.identity:
            value = replace(value, implementation_digest="f" * 64)
        caps.append(value)
    manifest = create_runtime_manifest(_seed(source_revision=CURRENT_REVISION, startup_boundary_at=at,
        process_nonce="3" * 32), LauncherConfiguration(8947, False), tuple(caps))
    service.bind_runtime(manifest)
    return service


def retain_equivalence(service, *, fault=None):
    epoch = service._epochs.chain()[0]
    historical = capability_identity(epoch["body"]["proof"])
    corrected = capability_identity(service._runtime_proof())
    protected = [{"module": name, "historical_sha256": sha256((name + "-old").encode()).hexdigest(),
                  "corrected_sha256": sha256((name + "-new").encode()).hexdigest()}
                 for name in sorted({module for module, _ in PROTECTED_CALLABLES})]
    evidence = [sha256(b"367/367 accepted and current").hexdigest()]
    diagnosis_body = {"classification": COLLATERAL, "epoch": epoch["identity"],
        "acceptance": epoch["body"]["acceptance"], "window": epoch["body"]["window"],
        "historical_proof": historical, "corrected_proof": corrected,
        "protected_sources": protected, "equivalence_evidence": evidence,
        "report_sha256": "d" * 64, "sponsor_reference": "ISOLATED-SPONSOR-EA-DIAGNOSIS"}
    diagnosis = document("diagnosis", diagnosis_body); service._epochs.retain(diagnosis)
    body = {"epoch": epoch["identity"], "acceptance": epoch["body"]["acceptance"],
        "window": epoch["body"]["window"], "historical_proof": historical,
        "corrected_proof": corrected, "diagnosis": diagnosis["identity"],
        "classification": COLLATERAL, "protected_sources": protected,
        "equivalence_evidence": evidence, "sponsor_authorization": "ISOLATED-SPONSOR-EA-AUTHORIZATION"}
    if fault == "epoch": body["epoch"] = "WO06H-EPOCH-" + "f" * 64
    elif fault == "acceptance": body["acceptance"] = "WO06H-ACCEPTANCE-" + "f" * 64
    elif fault == "window": body["window"] = "WO06H-WINDOW-" + "f" * 64
    elif fault == "historical": body["historical_proof"] = "WO06H-CAPABILITY-" + "f" * 64
    elif fault == "corrected": body["corrected_proof"] = "WO06H-CAPABILITY-" + "f" * 64
    elif fault == "diagnosis": body["diagnosis"] = "WO06H-DIAGNOSIS-" + "f" * 64
    elif fault == "sponsor": body["sponsor_authorization"] = ""
    elif fault == "evidence": body["equivalence_evidence"] = []
    record = document("compatibility", body); service._epochs.retain(record)
    return record


@pytest.fixture
def production_case(tmp_path):
    historical = accepted_service(tmp_path); retain_historical_counts(historical)
    assert historical.status()["counts"]["cohort_a"] == 34
    assert historical.status()["counts"]["cohort_b"] == 66
    successor = epochs.restart(tmp_path, historical)
    epochs.perform(successor, epochs.authorize(successor))
    current = corrected_restart(tmp_path, successor)
    assert current.status()["failure"] == "SHADOW_RESTORATION_RUNTIME_INCOMPATIBLE"
    assert current.status()["counts"]["cohort_a"] == current.status()["counts"]["cohort_b"] == 0
    assert current.status()["all_epoch_counts"] == {"cohort_a": 34, "cohort_b": 66, "eod_available": 0}
    return current


def test_exact_1_1_to_1_2_equivalence_restores_same_epoch(production_case):
    before = production_case._epochs.chain()[0]
    retain_equivalence(production_case)
    production_case._restore_acceptance()
    status = production_case.status()
    assert status["enabled"] and status["runtime_accepted"]
    assert status["acceptance_disposition"] == "EXISTING_ACCEPTANCE_RESTORED"
    assert status["current_epoch"] == before["identity"]
    assert status["window"]["identity"] == before["body"]["window"]
    assert status["counts"]["cohort_a"] == status["counts"]["cohort_b"] == status["counts"]["eod_available"] == 0
    assert status["all_epoch_counts"] == {"cohort_a": 34, "cohort_b": 66, "eod_available": 0}


@pytest.mark.parametrize("fault", ["epoch", "acceptance", "window", "historical", "corrected", "diagnosis", "sponsor", "evidence"])
def test_invalid_equivalence_binding_never_restores(production_case, fault):
    retain_equivalence(production_case, fault=fault)
    production_case._restore_acceptance()
    assert not production_case.status()["enabled"]
    assert production_case.status()["failure"] == "SHADOW_RESTORATION_RUNTIME_INCOMPATIBLE" or fault in {
        "acceptance", "window", "diagnosis", "sponsor", "evidence"}


@pytest.mark.parametrize("mutation", ["WO_06H_LIVE_SHADOW", "INTRADAY_DISCOVERY_OPERATION"])
def test_calculation_or_arbitrary_future_mismatch_still_rejects(tmp_path, mutation):
    historical = accepted_service(tmp_path)
    successor = epochs.restart(tmp_path, historical); epochs.perform(successor, epochs.authorize(successor))
    exact = corrected_restart(tmp_path, successor); retain_equivalence(exact)
    changed = corrected_restart(tmp_path, successor, mutation=mutation)
    changed._restore_acceptance()
    assert not changed.status()["enabled"]
    assert changed.status()["failure"] == "SHADOW_RESTORATION_RUNTIME_INCOMPATIBLE"
