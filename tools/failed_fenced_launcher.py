"""R3 canonical controller stages and native platform observation.

No command-line path, environment selector, private MAC or payload manufactures
operational approval. The canonical compiled controller supplies the already
independently pinned PreparedStartupAuthority. Methods retain exact immutable
records and use actual Darwin observations. This is separate from ordinary V2.
"""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import ctypes
import errno
import json
import os
from pathlib import Path
import socket
import sys

from kronos.common.failed_fenced_recovery import (
    RecoveryCodec, RecoveryStore, RecoveryBudget, EvidenceRegistry,
    canonical_bytes, record_ref,
)
from kronos.common.failed_fenced_startup import (
    PreparedStartupAuthority, RecoveryStartupError, decode_native_startup,
    run_native_helper, validate_recovery_chain, guard_admission,
)


# This exact stdlib bootstrap is embedded by the canonical C controller.
# It captures source before import and never receives a lineage role key.
NATIVE_PIN_BOOTSTRAP = 'import os,sys,time,struct,select,json,hashlib,types,importlib.abc,importlib.util\norigin,stop=int(sys.argv[1]),int(sys.argv[2])\ndef check():\n    now=time.clock_gettime_ns(time.CLOCK_MONOTONIC)\n    if stop!=origin+15000000000 or not origin<=now<stop:raise RuntimeError(\'NATIVE_PIN_BUDGET\')\ndef read_exact(size):\n    result=bytearray()\n    while len(result)<size:\n        check();poll=select.poll();poll.register(0,select.POLLIN|select.POLLHUP|select.POLLERR)\n        if not poll.poll(max(1,(stop-time.clock_gettime_ns(time.CLOCK_MONOTONIC)+999999)//1000000)):continue\n        try:part=os.read(0,min(65536,size-len(result)))\n        except (InterruptedError,BlockingIOError):continue\n        if not part:raise RuntimeError(\'NATIVE_PIN_TRUNCATED\')\n        result.extend(part)\n    check();return bytes(result)\nlength=struct.unpack(\'!I\',read_exact(4))[0]\nif not 1<=length<=67108864:raise RuntimeError(\'NATIVE_PIN_BOUND\')\nraw=read_exact(length)\ndef pairs(rows):\n    result={}\n    for key,value in rows:\n        if key in result:raise RuntimeError(\'NATIVE_PIN_DUPLICATE\')\n        result[key]=value\n    return result\nframe=json.loads(raw,object_pairs_hook=pairs)\nif json.dumps(frame,sort_keys=True,separators=(\',\',\':\'),ensure_ascii=True).encode()!=raw or set(frame)!={\'inventory\',\'plan\',\'plan_hash\',\'sources\'}:raise RuntimeError(\'NATIVE_PIN_CANONICAL\')\nplan=frame[\'plan\'];planraw=json.dumps(plan,sort_keys=True,separators=(\',\',\':\'),ensure_ascii=True).encode()\nif hashlib.sha256(planraw).hexdigest()!=frame[\'plan_hash\'] or set(plan)!={\'schema\',\'identity\',\'source_inventory\',\'modules\',\'qualification\'} or plan[\'schema\']!=\'KRONOS-FAILED-FENCED-BOOTSTRAP-PLAN/1.0.0\':raise RuntimeError(\'NATIVE_PIN_PLAN\')\ninventory=frame[\'inventory\'];inventory_raw=json.dumps(inventory,sort_keys=True,separators=(\',\',\':\'),ensure_ascii=True).encode()\nif type(inventory) is not list or not 1<=len(inventory)<=4096 or any(type(row) is not list or len(row)!=2 or any(type(value) is not str for value in row) for row in inventory):raise RuntimeError(\'NATIVE_PIN_INVENTORY\')\nif hashlib.sha256(inventory_raw).hexdigest()!=plan[\'source_inventory\'][\'hash\'] or str(len(inventory_raw))!=plan[\'source_inventory\'][\'bytes\']:raise RuntimeError(\'NATIVE_PIN_INVENTORY_HASH\')\nexpected=dict(inventory)\nif len(expected)!=len(inventory) or list(expected)!=sorted(expected):raise RuntimeError(\'NATIVE_PIN_MODULES\')\nplanned={row[\'name\']:row[\'digest\'] for row in plan[\'modules\']}\nif len(planned)!=len(plan[\'modules\']) or list(planned)!=sorted(planned) or any(expected.get(name)!=digest for name,digest in planned.items()):raise RuntimeError(\'NATIVE_PIN_PLAN_SOURCE\')\nsources={}\nfor row in frame[\'sources\']:\n    check()\n    if set(row)!={\'name\',\'package\',\'path\',\'payload\'} or type(row[\'package\']) is not bool or row[\'name\'] in sources:raise RuntimeError(\'NATIVE_PIN_SOURCE\')\n    payload=bytes.fromhex(row[\'payload\'])\n    if expected.get(row[\'name\'])!=hashlib.sha256(payload).hexdigest():raise RuntimeError(\'NATIVE_PIN_SOURCE_HASH\')\n    sources[row[\'name\']]=(payload,row[\'package\'],row[\'path\'])\nif set(sources)!=set(expected) or \'tools.failed_fenced_launcher\' not in sources:raise RuntimeError(\'NATIVE_PIN_SOURCE_ROSTER\')\ncapsule=types.ModuleType(\'_kronos_native_bootstrap\')\ncapsule.script_hash=hashlib.sha256(sys.orig_argv[sys.orig_argv.index("-c")+1].encode()).hexdigest()\ncapsule.plan_hash=frame[\'plan_hash\'];capsule.sources=tuple((name,sources[name]) for name in sorted(sources))\nconstructed={}\nclass PinnedLoader(importlib.abc.Loader):\n    def __init__(self,name):\n        if name not in sources or name in constructed:raise RuntimeError(\'NATIVE_PIN_LOADER_REPLAY\')\n        self.name=name;self._kronos_native_pinned_payload=sources[name][0];self._kronos_native_plan_hash=frame[\'plan_hash\']\n        self.code=compile(self._kronos_native_pinned_payload,sources[name][2],\'exec\',dont_inherit=True)\n        constructed[name]=self\n    def create_module(self,spec):return None\n    def exec_module(self,module):\n        if module.__spec__.loader is not self or self.name!=module.__spec__.name:raise RuntimeError(\'NATIVE_PIN_LOADER_CHANGED\')\n        module.__file__=sources[self.name][2];exec(self.code,module.__dict__)\n    def is_package(self,name):return sources[name][1]\nclass PinnedFinder(importlib.abc.MetaPathFinder):\n    def find_spec(self,name,path=None,target=None):\n        if name in sources:return importlib.util.spec_from_loader(name,PinnedLoader(name),is_package=sources[name][1])\n        if name in {\'tools\',\'tools.macos\'} and name not in sources and any(key.startswith(name+\'.\') for key in sources):\n            specification=importlib.util.spec_from_loader(name,loader=None,is_package=True)\n            specification.submodule_search_locations=[];return specification\n        if name in {\'tools\',\'kronos\'} or name.startswith((\'tools.\',\'kronos.\')):raise ImportError(\'NATIVE_PIN_UNCAPTURED_MODULE\')\ncapsule.loader_type=PinnedLoader;capsule.constructed=constructed;capsule.finder=PinnedFinder()\nsys.modules[capsule.__name__]=capsule;sys.meta_path.insert(0,capsule.finder)\ncheck()\nfrom tools import failed_fenced_launcher as entry\nraise SystemExit(entry.native_helper_main(origin_ns=origin,stop_deadline_ns=stop))\n'
NATIVE_PIN_BOOTSTRAP_SHA256 = sha256(NATIVE_PIN_BOOTSTRAP.encode("ascii")).hexdigest()


def _native_code_shape(code):
    """Exact executable metadata without marshal's intern/reference flags.

    marshal serializes object sharing, which is not a source/code identity.
    Retain every executable/location/exception field and every typed nested
    constant; unknown constant kinds fail closed.
    """
    import types
    import struct
    if type(code) is not types.CodeType:
        raise RecoveryStartupError("RECOVERY_NATIVE_CODE_OBJECT_REQUIRED")
    def constant(value):
        kind = type(value)
        if kind is types.CodeType:
            return ("code", _native_code_shape(value))
        if kind is tuple:
            return ("tuple", tuple(constant(item) for item in value))
        if kind is frozenset:
            return ("frozenset", tuple(sorted((constant(item) for item in value), key=repr)))
        if kind is float:
            return ("float", struct.pack("!d", value))
        if kind is complex:
            return ("complex", struct.pack("!dd", value.real, value.imag))
        if kind in {str, bytes, int, bool, type(None)}:
            return (kind.__name__, value)
        if value is Ellipsis:
            return ("ellipsis",)
        raise RecoveryStartupError("RECOVERY_NATIVE_CODE_CONSTANT_UNSUPPORTED")
    fields = ("co_argcount", "co_posonlyargcount", "co_kwonlyargcount", "co_nlocals",
        "co_stacksize", "co_flags", "co_code", "co_names", "co_varnames", "co_filename",
        "co_name", "co_qualname", "co_firstlineno", "co_linetable", "co_exceptiontable",
        "co_freevars", "co_cellvars")
    return tuple((field, getattr(code, field)) for field in fields) + (("co_consts", tuple(constant(value) for value in code.co_consts)),)


_NATIVE_PIN_WITNESSES = {}


def native_pinned_module(module, plan_hash):
    """Return the byte object actually executed by the fixed native loader.

    This is a finite validator of the canonical C embedded bootstrap, not a
    user-supplied loader predicate or a current-file hash attestation.
    NativeSemanticExchange separately proves that this exact bootstrap ran
    under the actual canonical parent and its original private exchange.
    """
    capsule = sys.modules.get("_kronos_native_bootstrap")
    specification = getattr(module, "__spec__", None)
    name = getattr(specification, "name", None)
    loader = getattr(specification, "loader", None)
    if (type(plan_hash) is not str or capsule is None or type(name) is not str
            or getattr(capsule, "script_hash", None) != NATIVE_PIN_BOOTSTRAP_SHA256
            or getattr(capsule, "plan_hash", None) != plan_hash
            or capsule not in tuple(sys.modules.values())
            or getattr(capsule, "finder", None) not in sys.meta_path
            or type(loader) is not getattr(capsule, "loader_type", None)
            or getattr(capsule, "constructed", {}).get(name) is not loader):
        raise RecoveryStartupError("RECOVERY_NATIVE_FIXED_LOADER_REQUIRED")
    sources = getattr(capsule, "sources", None)
    if type(sources) is not tuple or tuple(sorted(sources)) != sources or len(dict(sources)) != len(sources):
        raise RecoveryStartupError("RECOVERY_NATIVE_FIXED_CAPTURE_CHANGED")
    captured = dict(sources).get(name)
    if (type(captured) is not tuple or len(captured) != 3 or type(captured[0]) is not bytes
            or type(captured[1]) is not bool or type(captured[2]) is not str
            or loader._kronos_native_pinned_payload is not captured[0]
            or loader._kronos_native_plan_hash != plan_hash
            or loader.name != name or getattr(loader.code, "co_filename", None) != captured[2]):
        raise RecoveryStartupError("RECOVERY_NATIVE_FIXED_CAPTURE_CHANGED")
    namespace = capsule.loader_type.exec_module.__globals__
    source_map = namespace.get("sources")
    if (namespace.get("constructed") is not capsule.constructed
            or type(source_map) is not dict or len(source_map) != len(sources)
            or any(source_map.get(key) is not retained for key, retained in sources)
            or namespace.get("frame", {}).get("plan_hash") != plan_hash):
        raise RecoveryStartupError("RECOVERY_NATIVE_FIXED_CAPTURE_CHANGED")
    # A CodeType and the captured bytes/tuples are immutable. Recompiling the
    # same large modules on every immutable-store read consumed the actual
    # shared 15-second budget. Reuse only a completed validation witness for
    # these exact objects; replacement of any loader, method/code, capture map,
    # namespace, capsule or executable code still fails on every use.
    methods = tuple((key, getattr(capsule.loader_type, key, None)) for key in
                    ("__init__", "create_module", "exec_module", "is_package"))
    identities = (capsule, sources, captured, loader, loader.code, capsule.loader_type,
        capsule.finder, capsule.constructed, namespace, source_map, namespace.get("frame"))
    method_identities = tuple((key, function, getattr(function, "__code__", None),
                              getattr(function, "__globals__", None)) for key, function in methods)
    namespace_identities = tuple(sorted(namespace.items()))
    key = (id(capsule), name)
    witness = _NATIVE_PIN_WITNESSES.get(key)
    if witness is not None:
        previous, previous_methods, previous_namespace = witness
        if (any(actual is not retained for actual, retained in zip(identities, previous))
                or len(identities) != len(previous)
                or any(actual[0] != retained[0] or any(left is not right for left, right in zip(actual[1:], retained[1:]))
                       for actual, retained in zip(method_identities, previous_methods))
                or len(namespace_identities) != len(previous_namespace)
                or any(actual[0] != retained[0] or actual[1] is not retained[1]
                       for actual, retained in zip(namespace_identities, previous_namespace))):
            raise RecoveryStartupError("RECOVERY_NATIVE_FIXED_CAPTURE_CHANGED")
        return captured[0]
    import types
    bootstrap_code = compile(NATIVE_PIN_BOOTSTRAP, "<string>", "exec", dont_inherit=True)
    expected_loader = next((value for value in bootstrap_code.co_consts
                            if type(value) is types.CodeType and value.co_name == "PinnedLoader"), None)
    if expected_loader is None:
        raise RecoveryStartupError("RECOVERY_NATIVE_FIXED_LOADER_CHANGED")
    expected_methods = {value.co_name: value for value in expected_loader.co_consts if type(value) is types.CodeType}
    for name, code in expected_methods.items():
        actual_method = getattr(capsule.loader_type, name, None)
        if type(actual_method) is not types.FunctionType or _native_code_shape(actual_method.__code__) != _native_code_shape(code):
            raise RecoveryStartupError("RECOVERY_NATIVE_FIXED_LOADER_CHANGED")
    if _native_code_shape(loader.code) != _native_code_shape(compile(captured[0], captured[2], "exec", dont_inherit=True)):
        raise RecoveryStartupError("RECOVERY_NATIVE_FIXED_CAPTURE_CHANGED")
    if len(_NATIVE_PIN_WITNESSES) >= 4096:
        raise RecoveryStartupError("RECOVERY_NATIVE_FIXED_CAPTURE_BOUND")
    _NATIVE_PIN_WITNESSES[key] = (identities, method_identities, namespace_identities)
    return captured[0]


class _ProcBSDInfo(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint32) for name in (
        "flags", "status", "xstatus", "pid", "ppid", "uid", "gid", "ruid", "rgid", "svuid", "svgid", "rfu1")]
    _fields_ += [("comm", ctypes.c_char * 16), ("name", ctypes.c_char * 32)]
    _fields_ += [(name, ctypes.c_uint32) for name in ("nfiles", "pgid", "pjobc", "e_tdev", "e_tpgid", "nice")]
    _fields_ += [("start_seconds", ctypes.c_uint64), ("start_microseconds", ctypes.c_uint64)]


class DarwinKernelObserver:
    """Fixed libproc/codesign/lsof observations, never caller supplied booleans."""
    def __init__(self, codec, store, budget, process):
        if (sys.platform != "darwin" or type(codec) is not RecoveryCodec
                or type(store) is not RecoveryStore or type(budget) is not RecoveryBudget
                or ctypes.sizeof(_ProcBSDInfo) != 136):
            raise RecoveryStartupError("RECOVERY_DARWIN_PLATFORM_REQUIRED")
        self.codec, self.store, self.budget, self.process = codec, store, budget, process
        self.lib = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        self.lib.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
        self.lib.proc_pidinfo.restype = ctypes.c_int
        self.lib.proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        self.lib.proc_pidpath.restype = ctypes.c_int

    def process_observation(self, subject, kind="PROCESS_BIRTH"):
        self.budget.check()
        value = _ProcBSDInfo()
        ctypes.set_errno(0)
        count = self.lib.proc_pidinfo(int(subject["pid"]), 3, 0, ctypes.byref(value), ctypes.sizeof(value))
        error = ctypes.get_errno()
        self.budget.check()
        observed = None
        if count == ctypes.sizeof(value):
            observed = {"pid": str(value.pid), "kernel_birth": {"seconds": str(value.start_seconds),
                "microseconds": str(value.start_microseconds)}, "runtime": subject["runtime"]}
        if kind == "PROCESS_BIRTH":
            if observed != subject or error != 0:
                raise RecoveryStartupError("RECOVERY_NATIVE_PROCESS_CHANGED")
            result = "MATCH"
        elif kind == "PROCESS_EXIT":
            gone = count == 0 and error == errno.ESRCH
            reused = (count == ctypes.sizeof(value) and observed["pid"] == subject["pid"]
                      and observed["kernel_birth"] != subject["kernel_birth"])
            if not (gone or reused):
                raise RecoveryStartupError("RECOVERY_NATIVE_PROCESS_STILL_PRESENT")
            result = "EXITED"
        else:
            raise RecoveryStartupError("RECOVERY_NATIVE_PROCESS_KIND")
        fields = {"syscall": "proc_pidinfo:PROC_PIDTBSDINFO", "return_bytes": str(count),
                  "errno": str(error), "observed_process": observed}
        return self._publish(subject, kind, result, fields)

    def _publish(self, subject, kind, result, fields):
        now = self.budget.check()
        identity = "native-" + kind + "-" + str(now)
        base = {"schema": "KRONOS_DARWIN_KERNEL_OBSERVATION_V1", "adapter": "DARWIN_KERNEL_V1",
                "boot_id": self.codec.clock["boot_id"], "observed_ns": str(now),
                "observer": self.process, "subject": subject, "kind": kind}
        raw = json.dumps(dict(base, **fields), sort_keys=True, separators=(",", ":")).encode("ascii")
        # Native facts are unsigned. Only the actual canonical C observer may
        # retain and issue its own bound PLATFORM_OBSERVATION proof.
        native = {"identity": identity + "-raw", "hash": sha256(raw).hexdigest(), "bytes": str(len(raw))}
        payload = {"identity": identity, "observer": self.process, "subject": subject, "kind": kind,
            "adapter": "DARWIN_KERNEL_V1", "boot_id": self.codec.clock["boot_id"],
            "observed_ns": str(now), "raw": native, "result": result}
        self.budget.check()
        return {"native": raw, "payload": payload}

    def canonical_parent(self, subject):
        self.budget.check()
        child = _ProcBSDInfo()
        if self.lib.proc_pidinfo(os.getpid(), 3, 0, ctypes.byref(child), ctypes.sizeof(child)) != ctypes.sizeof(child) or child.ppid != int(subject["pid"]):
            raise RecoveryStartupError("RECOVERY_NATIVE_PARENT_CHANGED")
        image = ctypes.create_string_buffer(4096)
        if self.lib.proc_pidpath(child.ppid, image, len(image)) <= 0:
            raise RecoveryStartupError("RECOVERY_NATIVE_PARENT_IMAGE_UNAVAILABLE")
        canonical = "/Applications/KRONOS.app/Contents/MacOS/KRONOS"
        if os.fsdecode(image.value) != canonical or Path(canonical).resolve() != Path(canonical):
            raise RecoveryStartupError("RECOVERY_NATIVE_PARENT_IMAGE_CHANGED")
        run_native_helper(["/usr/bin/codesign", "--verify", "--deep", "--strict", "-R",
            '=identifier "com.project-kronos.browser-v1"', "/Applications/KRONOS.app"],
            budget=self.budget, timeout_cap=10)
        return self._publish(subject, "CANONICAL_PARENT", "MATCH", {"kernel_parent_pid": str(child.ppid),
            "resolved_image": canonical, "signature_exit": "0", "signature_stderr": ""})


class CanonicalRecoveryController:
    """Read-only semantic preparation checks; never a substitute L issuer.

    The actual native C controller retains custody, signs and publishes its
    own records. The helper cannot encode or publish even a correct proposal.
    Other native stages remain denied until their physical prepared entry is
    qualified; an unfinished stage is never reported VERIFIED.
    """
    def __init__(self, context):
        from kronos.common.failed_fenced_recovery import NativeSemanticContext
        if type(context) is not NativeSemanticContext:
            raise RecoveryStartupError("RECOVERY_NATIVE_KEYLESS_CONTEXT_REQUIRED")
        self.context = context

    def validate_preparation(self):
        exchange = self.context.codec._exchange
        exchange.require_current()
        if exchange.stage not in {"PREPARATION", "RECOVERY_CLAIM"}:
            raise RecoveryStartupError("RECOVERY_NATIVE_STAGE_NOT_INTEGRATED")
        from tools.runtime_source_gate import qualify_repository
        qualify_repository(Path(__file__).resolve().parents[1], budget=self.context.budget)
        return {"stage": exchange.stage, "operation": exchange.operation,
            "decision": "PREPARATION_VERIFIED", "preparation": self.context.registry.preparation.pin["preparation"]}


def native_helper_main(*, origin_ns, stop_deadline_ns):
    """One unsigned response on the original private helper pipe, then EOF."""
    import struct
    from kronos.common.failed_fenced_startup import NativeSemanticExchange
    from kronos.common.failed_fenced_recovery import NativeSemanticContext
    exchange = NativeSemanticExchange.receive(origin_ns=origin_ns, stop_deadline_ns=stop_deadline_ns)
    context = NativeSemanticContext.from_exchange(exchange)
    if exchange.stage == "GUARD_ADMISSION":
        from kronos.common.failed_fenced_startup import run_native_guard_admission
        run_native_guard_admission(context)
        return 0
    controller = CanonicalRecoveryController(context)
    if exchange._broker:
        if context.registry.preparation.record["mode"] == "RECOVERY":
            controller.validate_preparation()
            from kronos.common.failed_fenced_startup import run_native_recovery
            run_native_recovery(context)
        else:
            controller.validate_preparation()
            from kronos.common.failed_fenced_startup import run_native_original_facts
            run_native_original_facts(context)
            exchange.native_call("DONE", {})
        return 0
    result = controller.validate_preparation()
    raw = canonical_bytes(result)
    exchange.require_current()
    if not 1 <= len(raw) <= 1 << 20:
        raise RecoveryStartupError("RECOVERY_NATIVE_UNSIGNED_RESULT_BOUND")
    frame, offset = struct.pack("!I", len(raw)) + raw, 0
    while offset < len(frame):
        context.budget.check()
        try:
            count = os.write(1, frame[offset:])
        except (BlockingIOError, InterruptedError):
            import select
            poll = select.poll();poll.register(1, select.POLLOUT)
            poll.poll(max(1, int(context.budget.remaining_seconds() * 1000)))
            continue
        if count <= 0:
            raise RecoveryStartupError("RECOVERY_NATIVE_UNSIGNED_RESULT_WRITE")
        offset += count
    context.budget.check()
    return 0


if __name__ == "__main__":
    # No CLI or environment can stand in for the source-owned, independently
    # pinned native control preparation boundary. No successful empty stage.
    raise SystemExit("FAILED_FENCED_SOURCE_OWNED_PREPARATION_REQUIRED")
