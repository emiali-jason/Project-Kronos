"""WO-05C immutable startup evidence. Bootstrap uses only the Python standard library."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import importlib.abc
import importlib.util
import importlib.machinery
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from uuid import uuid4
from types import MappingProxyType


SOURCE_STATES = frozenset({"CLEAN_COMMIT", "DIRTY_WORKTREE", "REVISION_UNAVAILABLE"})
_BOOTSTRAP_MODULES = frozenset({"kronos", "kronos.intraday", "kronos.intraday.runtime_identity",
    "tools", "tools.kronos_browser"})


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
        default=lambda item: item.isoformat()).encode("utf-8")


def digest(value: object) -> str:
    return sha256(canonical(value)).hexdigest()


@dataclass(frozen=True, slots=True)
class StartupEvidence:
    source_revision: str | None
    branch: str | None
    source_state: str
    checkout_mode: str
    process_id: int
    startup_boundary_at: datetime
    process_nonce: str
    python_runtime: str
    source_snapshot_digest: str | None
    loaded_modules: tuple[tuple[str, str], ...]
    load_verification: str
    evidence_identity: str
    contract_version: str = "1.0.0"

    def __post_init__(self) -> None:
        if (self.source_state not in SOURCE_STATES
            or self.checkout_mode not in {"BRANCH", "DETACHED", "UNAVAILABLE"}
            or (self.checkout_mode == "BRANCH") != (self.branch is not None)
            or (self.checkout_mode == "DETACHED" and self.source_revision is None)
            or type(self.process_id) is not int
            or self.process_id < 1 or not isinstance(self.startup_boundary_at, datetime)
            or self.startup_boundary_at.utcoffset() is None
            or re.fullmatch(r"[a-f0-9]{32}", self.process_nonce) is None
            or (self.source_revision is not None and re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", self.source_revision) is None)
            or (self.branch is not None and re.fullmatch(r"[A-Za-z0-9._/-]{1,200}", self.branch) is None)
            or self.load_verification not in {"PINNED_STARTUP_IMPORTS", "NOT_PROVEN"}
            or (self.source_state == "CLEAN_COMMIT" and (
                self.source_revision is None or self.load_verification != "PINNED_STARTUP_IMPORTS"))
            or re.fullmatch(r"[a-z]+ [0-9]+\.[0-9]+\.[0-9]+", self.python_runtime) is None
            or (self.source_snapshot_digest is not None and re.fullmatch(r"[a-f0-9]{64}", self.source_snapshot_digest) is None)
            or type(self.loaded_modules) is not tuple
            or any(re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*", name) is None
                or re.fullmatch(r"[a-f0-9]{64}", value) is None for name, value in self.loaded_modules)
            or len({name for name, _ in self.loaded_modules}) != len(self.loaded_modules)
            or (self.source_state != "REVISION_UNAVAILABLE" and (
                self.source_revision is None or not self.loaded_modules or self.source_snapshot_digest is None))
            or self.contract_version != "1.0.0"):
            raise ValueError("INTRADAY_STARTUP_EVIDENCE_INVALID")
        core = asdict(self); core.pop("evidence_identity")
        if self.evidence_identity != "INTRADAY-STARTUP-" + digest(core):
            raise ValueError("INTRADAY_STARTUP_EVIDENCE_INTEGRITY_INVALID")


def _startup(**values) -> StartupEvidence:
    core = dict(values, contract_version="1.0.0")
    core.setdefault("checkout_mode", "UNAVAILABLE" if core["source_revision"] is None
        else "DETACHED" if core["branch"] is None else "BRANCH")
    return StartupEvidence(**core, evidence_identity="INTRADAY-STARTUP-" + digest(core))


@dataclass(frozen=True, slots=True)
class LauncherConfiguration:
    """Only existing non-secret launcher controls; not the credential configuration."""
    browser_port: int
    open_browser: bool

    def __post_init__(self) -> None:
        if type(self.browser_port) is not int or not 0 <= self.browser_port <= 65535 or type(self.open_browser) is not bool:
            raise ValueError("INTRADAY_LAUNCHER_CONFIGURATION_INVALID")

    @property
    def identity(self) -> str:
        return "INTRADAY-LAUNCHER-CONFIG-" + digest({
            "contract": "INTRADAY-NONSECRET-LAUNCHER-CONFIG/1.0.0", **asdict(self)})


@dataclass(frozen=True, slots=True)
class LoadedCapability:
    identity: str
    version: str
    implementation_digest: str

    def __post_init__(self) -> None:
        if (re.fullmatch(r"[A-Z0-9_]{1,100}", self.identity) is None
            or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", self.version) is None
            or re.fullmatch(r"[a-f0-9]{64}", self.implementation_digest) is None):
            raise ValueError("INTRADAY_LOADED_CAPABILITY_INVALID")


@dataclass(frozen=True, slots=True)
class RuntimeManifest:
    startup: StartupEvidence
    configuration_identity: str | None
    capabilities: tuple[LoadedCapability, ...]
    manifest_identity: str
    product: str = "INTRADAY"
    contract_version: str = "1.0.0"

    def __post_init__(self) -> None:
        if (type(self.startup) is not StartupEvidence or self.product != "INTRADAY" or self.contract_version != "1.0.0"
            or type(self.capabilities) is not tuple or any(type(x) is not LoadedCapability for x in self.capabilities)
            or len({x.identity for x in self.capabilities}) != len(self.capabilities)
            or (self.configuration_identity is not None and re.fullmatch(r"INTRADAY-LAUNCHER-CONFIG-[a-f0-9]{64}", self.configuration_identity) is None)):
            raise ValueError("INTRADAY_RUNTIME_MANIFEST_INVALID")
        core = asdict(self); core.pop("manifest_identity")
        if self.manifest_identity != "INTRADAY-RUNTIME-" + digest(core):
            raise ValueError("INTRADAY_RUNTIME_MANIFEST_INTEGRITY_INVALID")


def create_runtime_manifest(startup, configuration, capabilities) -> RuntimeManifest:
    if type(startup) is not StartupEvidence or (configuration is not None and type(configuration) is not LauncherConfiguration):
        raise ValueError("INTRADAY_RUNTIME_MANIFEST_INPUT_INVALID")
    core = dict(startup=startup, configuration_identity=None if configuration is None else configuration.identity,
        capabilities=tuple(capabilities), product="INTRADAY", contract_version="1.0.0")
    serial = dict(core, startup=asdict(startup), capabilities=[asdict(x) for x in core["capabilities"]])
    return RuntimeManifest(**core, manifest_identity="INTRADAY-RUNTIME-" + digest(serial))


def runtime_document(manifest: RuntimeManifest | None) -> dict:
    if manifest is None:
        return {"availability": "NOT_RETAINED", "loaded_commit_revision": None,
            "runtime_accepted": "NOT_PROVEN"}
    if manifest.startup.process_id != os.getpid():
        return {"availability": "NOT_RETAINED", "loaded_commit_revision": None,
            "runtime_accepted": "NOT_PROVEN", "reason": "PROCESS_INSTANCE_MISMATCH"}
    document = json.loads(canonical(asdict(manifest)))
    document.update(availability="RETAINED",
        loaded_commit_revision=(manifest.startup.source_revision if manifest.startup.source_state == "CLEAN_COMMIT" else None),
        startup_checkout_mode=manifest.startup.checkout_mode,
        source_proof_scope="LAUNCHER_STARTUP_IMPORTS",
        configuration_scope="NONSECRET_LAUNCHER_CONTROLS_ONLY",
        other_configuration_identity="NOT_RETAINED", package_build_identity="NOT_RETAINED",
        os_process_birth_time="NOT_RETAINED", runtime_accepted="NOT_PROVEN",
        market_data_freshness="NOT_ASSESSED_BY_RUNTIME_IDENTITY")
    return document


class _PinnedLoader(importlib.abc.Loader):
    def __init__(self, capture, name, filename, payload):
        self.capture, self.name, self.filename, self.payload = capture, name, filename, payload

    def create_module(self, spec):
        return None

    def get_code(self, fullname):
        if self.capture._finished is None:
            self.capture._loaded[fullname] = sha256(self.payload).hexdigest()
        return compile(self.payload, self.filename, "exec", dont_inherit=True)

    def get_source(self, fullname):
        if fullname != self.name:
            raise ImportError(fullname)
        return self.payload.decode("utf-8")

    def exec_module(self, module):
        exec(self.get_code(module.__name__), module.__dict__)


class StartupCapture(importlib.abc.MetaPathFinder):
    """Instance-owned source pinning; launcher retains it for later local imports.

    Bootstrap/stdlib and third-party packages are outside the application proof.
    Existing application imports cannot be retroactively certified.
    """
    def __init__(self, root: Path, *, clock=lambda: datetime.now(timezone.utc),
                 process_id=None, nonce=None, keep_sources_pinned=False) -> None:
        self._keep_sources_pinned = keep_sources_pinned
        self._root = Path(root).resolve()
        self._started = clock()
        self._pid = os.getpid() if process_id is None else process_id
        self._nonce = uuid4().hex if nonce is None else nonce
        self._sources = {}; self._loaded = {}; self._namespaces = set(); self._entered = False; self._finished = None
        self._revision = None; self._branch = None; self._checkout_mode = "UNAVAILABLE"; self._state = "REVISION_UNAVAILABLE"
        self._valid = True
        self._preloaded = {name for name in sys.modules if self._application_name(name)}
        self._capture_sources()
        self._sources = MappingProxyType(self._sources)

    @staticmethod
    def _application_name(name):
        return name not in _BOOTSTRAP_MODULES and (name.startswith("kronos.") or name.startswith("tools."))

    def _git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self._root,
            stderr=subprocess.DEVNULL, timeout=10)

    def _capture_sources(self):
        try:
            self._revision = self._git("rev-parse", "HEAD").decode().strip()
            if re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", self._revision) is None:
                raise ValueError("INVALID_REVISION")
            try:
                self._branch = self._git("symbolic-ref", "--quiet", "--short", "HEAD").decode().strip()
                self._checkout_mode = "BRANCH"
            except subprocess.CalledProcessError as error:
                if error.returncode != 1:
                    raise
                self._branch = None
                self._checkout_mode = "DETACHED"
            if self._branch is not None and re.fullmatch(r"[A-Za-z0-9._/-]{1,200}", self._branch) is None:
                self._branch = None
                self._checkout_mode = "UNAVAILABLE"
            status = self._git("status", "--porcelain=v1", "--untracked-files=all")
            self._state = "DIRTY_WORKTREE" if status else "CLEAN_COMMIT"
        except (OSError, subprocess.SubprocessError, ValueError):
            self._revision = None; self._branch = None; self._checkout_mode = "UNAVAILABLE"
            self._state = "REVISION_UNAVAILABLE"
        try:
            for prefix, package in (("src/kronos", "kronos"), ("tools", "tools")):
                for path in sorted((self._root / prefix).rglob("*.py")):
                    if path.is_symlink() or not path.resolve().is_relative_to(self._root):
                        self._valid = False
                        continue
                    parts = list(path.relative_to(self._root / prefix).with_suffix("").parts)
                    is_package = parts[-1] == "__init__"
                    if is_package: parts.pop()
                    name = ".".join([package, *parts])
                    self._sources[name] = (str(path), path.read_bytes(), is_package)
            if self._revision is not None:
                if self._git("rev-parse", "HEAD").decode().strip() != self._revision or self._git("status", "--porcelain=v1", "--untracked-files=all") != status:
                    self._valid = False
                if self._state == "CLEAN_COMMIT":
                    # Verify source bytes, not just Git's timestamp/index cache.
                    tree = self._git("ls-tree", "-r", "-z", self._revision, "--", "src/kronos", "tools")
                    blobs = {row.split(b"\t",1)[1].decode():row.split(b"\t",1)[0].split()[2].decode()
                             for row in tree.split(b"\0") if row}
                    from hashlib import sha1
                    for filename, payload, _ in self._sources.values():
                        relative = str(Path(filename).relative_to(self._root))
                        raw = b"blob " + str(len(payload)).encode() + b"\0" + payload
                        actual = (sha1(raw).hexdigest() if len(self._revision) == 40 else sha256(raw).hexdigest())
                        if blobs.get(relative) != actual:
                            self._state = "DIRTY_WORKTREE"
        except (OSError, subprocess.SubprocessError, ValueError):
            self._valid = False

    def __enter__(self):
        if self._entered: raise ValueError("INTRADAY_STARTUP_CAPTURE_REUSED")
        self._entered = True
        sys.meta_path.insert(0, self)
        return self

    def find_spec(self, fullname, path=None, target=None):
        if fullname not in self._sources:
            if any(name.startswith(fullname + ".") for name in self._sources):
                self._namespaces.add(fullname)
                spec = importlib.machinery.ModuleSpec(fullname, loader=None, is_package=True)
                spec.submodule_search_locations = []
                return spec
            return None
        filename, payload, is_package = self._sources[fullname]
        return importlib.util.spec_from_file_location(fullname, filename,
            loader=_PinnedLoader(self, fullname, filename, payload),
            submodule_search_locations=[str(Path(filename).parent)] if is_package else None)

    def finish(self) -> StartupEvidence:
        if self._finished is not None: return self._finished
        unknown = {name for name in sys.modules if self._application_name(name)} - self._preloaded - self._loaded.keys() - self._namespaces
        verified = self._valid and not self._preloaded and not unknown and bool(self._loaded)
        self._finished = _startup(source_revision=self._revision, branch=self._branch, checkout_mode=self._checkout_mode,
            source_state=self._state if verified else "REVISION_UNAVAILABLE", process_id=self._pid,
            startup_boundary_at=self._started, process_nonce=self._nonce,
            python_runtime=f"{sys.implementation.name} {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            source_snapshot_digest=digest(tuple(sorted((name,sha256(item[1]).hexdigest()) for name,item in self._sources.items()))) if self._sources else None,
            loaded_modules=tuple(sorted(self._loaded.items())),
            load_verification="PINNED_STARTUP_IMPORTS" if verified else "NOT_PROVEN")
        return self._finished

    def __exit__(self, *exc):
        if (exc[0] is not None or not self._keep_sources_pinned) and self in sys.meta_path:
            sys.meta_path.remove(self)
        self.finish()
