import ast
from pathlib import Path
import subprocess
import sys


SOURCE = Path(__file__).resolve().parents[2] / "src"
ALLOWED = {"dataclasses", "datetime", "enum", "hashlib", "json", "re", "uuid",
           "pathlib", "os", "stat", "tempfile", "threading"}


def test_all_source_imports_are_local_or_bounded_standard_library():
    files = list((SOURCE / "tvca").glob("*.py"))
    assert len(files) == 4
    local_names = {path.stem for path in files}
    for path in files:
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(alias.name in ALLOWED for alias in node.names), path
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    assert node.level == 1 and node.module in local_names, path
                else:
                    assert node.module in ALLOWED, path
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    assert node.func.id not in {"__import__", "eval", "exec", "compile"}, path
                elif isinstance(node.func, ast.Attribute):
                    assert node.func.attr not in {
                        "getenv", "putenv", "load_dotenv", "home", "system", "popen",
                        "spawn", "import_module", "exec_module",
                    }, path
            elif isinstance(node, ast.Attribute):
                assert node.attr not in {"environ", "environb"}, path


def test_fresh_process_import_and_lifecycle_have_no_external_services(tmp_path):
    # Only this test harness creates a subprocess; product source cannot import it.
    program = r'''
import sys
from pathlib import Path
from datetime import UTC, datetime
source, root = map(Path, sys.argv[1:])
sys.path.insert(0, str(source))
blocked = ("kronos", "openai", "requests", "httpx", "socket", "subprocess",
           "mcp", "tradingview", "kiteconnect")
class DenyExternalImports:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in blocked:
            raise AssertionError("forbidden import: " + fullname)
sys.meta_path.insert(0, DenyExternalImports())
allowed_reads = (source.resolve(), root.resolve(), Path(sys.base_prefix).resolve(),
                 Path(sys.prefix).resolve())
def audit(event, args):
    if event.startswith(("socket.", "subprocess.", "os.system", "os.exec", "os.spawn")):
        raise AssertionError("external action: " + event)
    if event == "open" and isinstance(args[0], str):
        target = Path(args[0]).resolve()
        assert any(target.is_relative_to(base) for base in allowed_reads), target
        mode, flags = args[1:3]
        if (mode and any(char in mode for char in "wax+")) or flags & (1 | 2 | 64 | 512):
            assert target.is_relative_to(root.resolve()), target
sys.addaudithook(audit)
import tvca
assert not list(root.iterdir()), "import created state"
core = tvca.TvcaCore(root)
assert not list(root.iterdir()), "constructor created records"
record = core.create("12345678-1234-4234-8234-123456789abc", "Expected", datetime(2026, 9, 6, tzinfo=UTC))
record = core.record_identity(record.ref, tvca.IdentityChannel.ADAPTER_OBSERVED, "Different", record.recorded_at)
sealed = core.seal(record.ref, record.recorded_at)
assert core.restore(record.ref) == record
assert sealed.status is tvca.CoreStatus.SEALED
assert not any(name.split(".")[0] in blocked for name in sys.modules)
assert Path(tvca.__file__).resolve().is_relative_to(source.resolve())
'''
    result = subprocess.run([sys.executable, "-I", "-B", "-c", program,
                             str(SOURCE), str(tmp_path.resolve())],
                            capture_output=True, text=True, timeout=20, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
