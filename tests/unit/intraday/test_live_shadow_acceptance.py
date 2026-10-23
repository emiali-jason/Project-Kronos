"""Native acceptance checks stay identical across owner and pure helper entry."""
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
import json
import subprocess
import sys

import pytest

from kronos.application.intraday_live_shadow import IntradayLiveShadowService
from kronos.intraday.live_shadow import ShadowError
from kronos.intraday.live_shadow_acceptance import validate_acceptance_proof
from tests.unit.intraday.test_live_shadow import service


@pytest.fixture
def native_proof(tmp_path):
    shadow, _, manifest = service(tmp_path)
    return shadow._runtime_proof(), manifest


def test_original_owner_delegates_exact_native_proof_without_changes(native_proof):
    proof, manifest = native_proof
    before = deepcopy(proof)
    assert IntradayLiveShadowService._validate_acceptance_proof(proof, manifest.manifest_identity) == validate_acceptance_proof(proof, manifest.manifest_identity)
    assert proof == before


@pytest.mark.parametrize("field,value", [
    ("manifest", "WRONG"), ("pid", 0), ("pid", True),
    ("revision", "not-a-revision"), ("source_state", "DIRTY"),
    ("configuration", "wrong"), ("capabilities", ()),
])
def test_invalid_native_proof_denied_by_both_entries(native_proof, field, value):
    proof, manifest = native_proof
    proof[field] = value
    for validator in (validate_acceptance_proof, IntradayLiveShadowService._validate_acceptance_proof):
        with pytest.raises(ShadowError, match="SHADOW_RESTORATION_PROOF_INVALID"):
            validator(proof, manifest.manifest_identity)


@pytest.mark.parametrize("change", ["duplicate", "required_missing"])
def test_native_capability_validation_remains_exact(native_proof, change):
    proof, manifest = native_proof
    if change == "duplicate": proof["capabilities"].append(deepcopy(proof["capabilities"][0]))
    else: proof["capabilities"] = []
    for validator in (validate_acceptance_proof, IntradayLiveShadowService._validate_acceptance_proof):
        with pytest.raises(ShadowError, match="SHADOW_RESTORATION_CAPABILITY_INVALID"):
            validator(proof, manifest.manifest_identity)


def test_recovery_native_proof_preserves_epoch_owner_without_eager_swing_or_pdf(tmp_path):
    shadow, _, manifest = service(tmp_path / "native-epoch")
    # A fresh interpreter reproduces the counted helper's narrow import graph.
    # The exact protected epoch function imports its original Intraday owner.
    # Only that fixed owner may load; unrelated application/Browser/PDF may not.
    root = Path(__file__).resolve().parents[3]
    script = '''
import importlib.abc,json,sys
sys.path.insert(0,sys.argv[1])
class DenyApplication(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if (fullname.startswith(('pypdf', 'kronos.browser'))
                or fullname.startswith('kronos.application.') and fullname != 'kronos.application.intraday_live_shadow'):
            raise AssertionError('UNEXPECTED_HELPER_DEPENDENCY:'+fullname)
sys.meta_path.insert(0,DenyApplication())
from kronos.common.failed_fenced_compatibility import read_native_runtime_manifest,native_wo06h_proof
from kronos.intraday.live_shadow_epochs import capabilities,EpochStore
from kronos.intraday.live_shadow_persistence import ShadowStore
from pathlib import Path
from kronos.intraday.runtime_identity import canonical
manifest=read_native_runtime_manifest(canonical(json.loads(sys.argv[2])))
proof=native_wo06h_proof(manifest)
assert capabilities(proof)
epochs=EpochStore(ShadowStore(Path(sys.argv[3])))
chain=epochs.chain()
assert len(chain)==1
window,acceptance=epochs.bound(chain[0])
assert window.key==chain[0]["body"]["window"]
assert acceptance.key==chain[0]["body"]["acceptance"]
assert 'kronos.application.intraday_live_shadow' in sys.modules
assert not any(n.startswith(('pypdf','kronos.browser')) or n.startswith('kronos.application.') and n != 'kronos.application.intraday_live_shadow' for n in sys.modules)
print('PURE_NATIVE_ACCEPTANCE_PASS')
'''
    result = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", script, str(root / "src"), __import__("kronos.intraday.runtime_identity",fromlist=["canonical"]).canonical(asdict(manifest)).decode(), str(shadow._epochs.raw.root.parent)], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "PURE_NATIVE_ACCEPTANCE_PASS"


@pytest.mark.parametrize("name,module", [
    (name, "kronos.application.swing_opportunities") for name in (
        "AnalysisState", "BrowserWorkspaceSnapshot", "CompletedSwingAnalysis",
        "EligiblePlanSnapshot", "MarketPanel", "OpportunitySnapshot",
        "ProviderConnectionState", "SwingAnalysisEvidenceSnapshot",
        "SwingOpportunitiesApplication")
] + [(name, "kronos.application.swing_v1_review") for name in (
    "STEP31_V1_HANDOFF_SCHEMA_ID", "Step31EligibilityHandoff", "Step31EligibleInstrument")])
def test_application_fixed_exports_keep_exact_owned_objects(name, module):
    import importlib
    import kronos.application as application
    expected = getattr(importlib.import_module(module), name)
    assert getattr(application, name) is expected
    assert name in application.__all__ and name in dir(application)
    namespace = {}
    exec("from kronos.application import " + name, namespace)
    assert namespace[name] is expected


def test_application_fixed_star_exports_and_unknown_name_preserve_contract():
    import kronos.application as application
    namespace = {}
    exec("from kronos.application import *", namespace)
    assert set(namespace) - {"__builtins__"} == set(application.__all__)
    assert len(application.__all__) == 12
    assert all(namespace[name] is getattr(application, name) for name in application.__all__)
    with pytest.raises(AttributeError):
        getattr(application, "NOT_AN_AUTHORIZED_APPLICATION_EXPORT")


def test_application_package_import_and_unknown_names_do_not_load_products():
    root = Path(__file__).resolve().parents[3]
    script = r"""
import sys,importlib.abc
sys.path.insert(0,sys.argv[1])
class DenyAllProducts(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.startswith(('kronos.application.','kronos.browser','pypdf')):
            raise AssertionError('unexpected eager product import:'+fullname)
sys.meta_path.insert(0,DenyAllProducts())
import kronos.application as application
assert len(application.__all__)==12
assert all(name in dir(application) for name in application.__all__)
try: application.NOT_AN_AUTHORIZED_APPLICATION_EXPORT
except AttributeError: pass
else: raise AssertionError('unknown export was accepted')
assert not any(name.startswith(('kronos.application.','kronos.browser','pypdf')) for name in sys.modules)
"""
    result = subprocess.run([sys.executable,"-I","-S","-B","-c",script,str(root/"src")],
        capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stdout+result.stderr
