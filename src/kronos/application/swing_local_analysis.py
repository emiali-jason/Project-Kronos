"""LOCAL-02: retained-only local research under existing Swing owners.

No Provider/model client, worker, acquisition or trading capability is held here.
Explicit lifecycle operations prepare immutable research; GETs only read a fenced
prepared projection. WO-12 originals and commissioning remain owned by its store.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime
import json
from threading import Lock, RLock

from kronos.swing.v1.native_discovery import NativeDiscoveryRun, NativeProductPath
from kronos.swing.v1.nse_local_analysis import (
    SourceBinding, analyze_local, build_local_input, canonical, decode_input,
    decode_result, digest,
)
from kronos.swing.v1.nse_local_methodology import METHOD_VERSION
from kronos.swing.v1.prospective_research import record
from kronos.swing.v1.review_evidence_store import record_prepared_read

_ORIGINAL = "LOCAL_ANALYSIS_ORIGINAL"
_DISPOSITION = "LOCAL_ANALYSIS_DISPOSITION"
_AUTHORITY = "RESEARCH_ONLY_NO_ADMISSION_OR_EXECUTION"
# Only used after a completed original exists. A missing requirement at the
# initial gate remains a rejection without analysis or fabricated output.
_STALE = frozenset({"NSE_LOCAL_SOURCE_STALE", "NSE_LOCAL_REQUIREMENT_UNAVAILABLE",
    "REVIEW_BINDING_STALE",
    "SWING_PUBLICATION_CURRENT_CHANGED", "SWING_PUBLICATION_CURRENT_UNAVAILABLE",
    "SWING_PUBLICATION_BUNDLE_INVALID"})
_META = {"contract_identity", "contract_version"}


def _require(condition, reason="NSE_LOCAL_RECORD_INVALID"):
    if not condition:
        raise ValueError(reason)


def _time(value):
    _require(type(value) is str)
    parsed = datetime.fromisoformat(value)
    _require(parsed.tzinfo is not None and parsed.utcoffset() is not None)
    return parsed


def _plain(value):
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _operation(input_sha256):
    return "SWING-LOCAL-ANALYSIS-" + digest({
        "input_sha256": input_sha256, "method_version": METHOD_VERSION})


def _original(value):
    value.__post_init__()
    data = value.data
    _require(value.schema == "SWING_WO12_" + _ORIGINAL + "_V1")
    _require(set(data) == _META | {"operation_identity", "method_version",
        "input_json", "result_json", "input_sha256", "output_sha256",
        "captured_at", "completed_at", "trigger", "authority"})
    local_input = decode_input(data["input_json"])
    result = decode_result(data["result_json"], local_input,
                           expected_source=local_input.binding)
    _require(data["operation_identity"] == _operation(local_input.identity)
        and data["method_version"] == METHOD_VERSION
        and data["input_sha256"] == local_input.identity
        and data["output_sha256"] == result.identity
        and data["authority"] == _AUTHORITY
        and data["trigger"] in {"AUTOMATIC", "MANUAL"}
        and _time(local_input.binding.information_cutoff) <= _time(data["captured_at"])
        <= _time(data["completed_at"]))
    return local_input, result


def _disposition(value, originals):
    value.__post_init__()
    data = value.data
    _require(value.schema == "SWING_WO12_" + _DISPOSITION + "_V1")
    _require(set(data) == _META | {"original_identity", "operation_identity",
        "state", "reason", "checked_at", "authority"})
    original = originals.get(data["original_identity"])
    _require(original is not None)
    _require(data["operation_identity"] == original.data["operation_identity"]
        and data["authority"] == _AUTHORITY
        and data["state"] in {"SUCCEEDED", "STALE"}
        and ((data["state"] == "SUCCEEDED" and data["reason"] is None)
             or (data["state"] == "STALE" and data["reason"] == "NSE_LOCAL_SOURCE_STALE"))
        and _time(data["checked_at"]) >= _time(original.data["completed_at"]))


class SwingLocalAnalysisWorkflow:
    """One synchronous retained-only operation; no startup/GET evaluation."""

    def __init__(self, application, intake, research, *, clock=None, capture=None):
        self.application, self.intake, self.research = application, intake, research
        self.store = research.store
        self.clock = clock or (lambda: datetime.now(UTC))
        self.capture = capture
        self._lock = RLock()
        self._operation_lock = Lock()
        self._closed = False
        self._originals = {}
        self._dispositions = {}
        # Process-local proof of exact immutable bytes already fully validated.
        # A new owner starts empty and validates retained results on restoration.
        self._validated_originals = {}
        self._history_failure = None
        self._failure = None
        self._prepared = None
        self._preparation_failure = None
        self.restore()

    def _now(self):
        now = self.clock()
        _require(type(now) is datetime and now.tzinfo is not None
            and now.utcoffset() is not None, "NSE_LOCAL_CLOCK_INVALID")
        return now

    def _commissioned(self):
        if self.capture is not None:
            _require(self.capture.research is self.research,
                     "NSE_LOCAL_RESEARCH_OWNER_INVALID")
            enabled = self.capture.capture_enabled()
        else:
            enabled = self.store.pointer("COMMISSIONING", "active") is not None
        _require(enabled is True, "SWING_RESEARCH_COMMISSIONING_REQUIRED")
        # Reuse the existing commissioning receipt/pointer without rebinding it.
        # Explicit preparation contributes both exact files to the page fence.
        marker = self.store.pointer("COMMISSIONING", "active")
        _require(marker is not None, "SWING_RESEARCH_COMMISSIONING_REQUIRED")
        self._fence_record(marker)
        pointer = self.store.root / "current" / "COMMISSIONING" / "active.json"
        payload = pointer.read_bytes()
        expected = canonical({"schema": marker.schema, "identity": marker.identity,
            "data": marker.data, "integrity_sha256": marker.integrity_sha256}) + b"\n"
        _require(payload == expected, "SWING_RESEARCH_COMMISSIONING_REQUIRED")
        record_prepared_read(pointer, payload)

    def _validated_original_identity(self, item):
        item.__post_init__()
        payload = self._fence_record(item)
        prior = self._validated_originals.get(item.identity)
        if prior is not None and prior[0] == payload:
            return prior[1]
        # New or changed evidence must pass the complete immutable validator;
        # neither the record hash nor a source hash is a validation substitute.
        local_input, _ = _original(item)
        self._validated_originals[item.identity] = (payload, local_input.identity)
        return local_input.identity

    def _load_history(self):
        known_originals = set(self._validated_originals)
        originals, dispositions = {}, {}
        for item in self.store.records(_ORIGINAL):
            key = self._validated_original_identity(item)
            _require(key not in originals, "NSE_LOCAL_ORIGINAL_CONFLICT")
            originals[key] = item
        by_identity = {item.identity: item for item in originals.values()}
        # A vanished original already observed by this owner is not permission
        # to reconstruct it with a new capture timestamp. No repair or new index.
        _require(known_originals <= set(by_identity), "NSE_LOCAL_HISTORY_UNAVAILABLE")
        for item in self.store.records(_DISPOSITION):
            _disposition(item, by_identity)
            key = item.data["original_identity"]
            _require(key not in dispositions, "NSE_LOCAL_DISPOSITION_CONFLICT")
            dispositions[key] = item
        return originals, dispositions

    def restore(self):
        """Validate only this record namespace; never repair or run acquisition."""
        with self._lock:
            self._prepared = None
            try:
                self._originals, self._dispositions = self._load_history()
            except (OSError, ValueError, TypeError, KeyError, AttributeError):
                self._originals, self._dispositions = {}, {}
                self._history_failure = "NSE_LOCAL_HISTORY_UNAVAILABLE"
            else:
                self._history_failure = None
            return self.status()

    def status(self):
        with self._lock:
            return {"state": "CLOSED" if self._closed else (
                "UNAVAILABLE" if self._history_failure or self._failure else "READY"),
                "reason": self._history_failure or self._failure,
                "method_version": METHOD_VERSION,
                "retained_originals": len(self._originals)}

    def _control(self, run_identity, publication_sha256):
        native, control = self.application.current_run_control_authority()
        _require(type(native) is NativeDiscoveryRun and type(control) is dict,
                 "NSE_LOCAL_SOURCE_STALE")
        attempt, manifest = control.get("latest_attempt"), control.get("current_manifest")
        _require(type(attempt) is dict and type(manifest) is dict
            and native.run_identity == run_identity
            and attempt.get("run_id") == run_identity
            and attempt.get("state") == "SUCCEEDED"
            and manifest.get("sha256") == publication_sha256
            and type(control.get("admission_generation")) is int
            and control["admission_generation"] >= 0, "NSE_LOCAL_SOURCE_STALE")
        return canonical(control)

    def _context(self, prepared, run_identity=None, publication_sha256=None,
                 requirement_id=None):
        manifest, facts, review = self.intake._context(_response=prepared)
        native = prepared.authority.native
        _require(run_identity in {None, native.run_identity}
            and publication_sha256 in {None, manifest}, "NSE_LOCAL_SOURCE_STALE")
        control = self._control(native.run_identity, manifest)
        requirements = tuple(item for item in review.requirements
            if item.thesis.product_path is NativeProductPath.NSE
            and (requirement_id is None or item.requirement_sha256 == requirement_id))
        if requirement_id is not None:
            _require(len(requirements) == 1, "NSE_LOCAL_REQUIREMENT_UNAVAILABLE")
        return manifest, facts, native, requirements, control

    @staticmethod
    def _input(requirement, native, facts, manifest):
        local_input = build_local_input(requirement, native, facts, manifest)
        expected = SourceBinding(local_input.identity, native.run_identity, manifest,
            requirement.canonical_instrument, requirement.thesis.native_assessment_sha256,
            requirement.requirement_sha256, facts.provider_source_identity,
            facts.observed_at.isoformat())
        _require(local_input.binding == expected, "NSE_LOCAL_SOURCE_STALE")
        return local_input, expected

    def refresh(self, *, run_identity, publication_sha256, requirement_id=None,
                trigger="MANUAL"):
        _require(self._operation_lock.acquire(blocking=False), "NSE_LOCAL_OPERATION_BUSY")
        try:
            return self._refresh(run_identity=run_identity,
                publication_sha256=publication_sha256, requirement_id=requirement_id,
                trigger=trigger)
        finally:
            self._operation_lock.release()

    def _refresh(self, *, run_identity, publication_sha256, requirement_id=None,
                 trigger="MANUAL"):
        """Explicit owner operation. Completed originals survive final stale proof."""
        _require(trigger in {"AUTOMATIC", "MANUAL"}, "NSE_LOCAL_TRIGGER_INVALID")
        with self._lock:
            _require(not self._closed, "NSE_LOCAL_CLOSED")
            _require(self._history_failure is None, "NSE_LOCAL_HISTORY_UNAVAILABLE")
            self._prepared = None
            self._failure = None
            try:
                self._commissioned()
                with self.intake.response() as prepared:
                    manifest, facts, native, requirements, control = self._context(
                        prepared, run_identity, publication_sha256, requirement_id)
                    _require(bool(requirements), "NSE_LOCAL_REQUIREMENT_UNAVAILABLE")
                    inputs = tuple((item, *self._input(item, native, facts, manifest))
                                   for item in requirements)
                _require(self._control(run_identity, manifest) == control,
                         "NSE_LOCAL_SOURCE_STALE")
                for requirement, local_input, expected in inputs:
                    # Deduplicate and retain original before any final-currentness
                    # gate. No publication lock is acquired while this store lock
                    # is held. Cross-instance contenders fail BUSY, never retry.
                    with self.store.transaction():
                        self._commissioned()
                        originals, dispositions = self._load_history()
                        original = originals.get(local_input.identity)
                        if original is None:
                            captured_at = self._now()
                            _require(captured_at >= _time(expected.information_cutoff),
                                     "NSE_LOCAL_CLOCK_INVALID")
                            result = analyze_local(local_input, expected_source=expected)
                            completed_at = self._now()
                            _require(completed_at >= captured_at, "NSE_LOCAL_CLOCK_INVALID")
                            original = record(_ORIGINAL,
                                operation_identity=_operation(local_input.identity),
                                method_version=METHOD_VERSION,
                                input_json=local_input.to_json(), result_json=result.to_json(),
                                input_sha256=local_input.identity, output_sha256=result.identity,
                                captured_at=captured_at.isoformat(), completed_at=completed_at.isoformat(),
                                trigger=trigger, authority=_AUTHORITY)
                            validated_input, _ = _original(original)
                            self.store.retain(original)
                            # Cache only after exact bytes were durably retained.
                            self._validated_originals[original.identity] = (
                                self._fence_record(original), validated_input.identity)
                            originals[local_input.identity] = original
                        self._originals, self._dispositions = originals, dispositions
                    if original.identity in dispositions:
                        # A once-stale original is never rewritten/promoted by a
                        # repeated operation. Exact successful originals are reused.
                        continue
                    try:
                        with self.intake.response() as final:
                            final_manifest, final_facts, final_native, final_requirements, final_control = self._context(
                                final, run_identity, manifest, requirement.requirement_sha256)
                            rebuilt, rebuilt_expected = self._input(final_requirements[0],
                                final_native, final_facts, final_manifest)
                            _require(rebuilt == local_input and rebuilt_expected == expected
                                and final_control == control, "NSE_LOCAL_SOURCE_STALE")
                        # Application -> publication -> research lock ordering.
                        with self.application.publication_mutation_guard() as fence:
                            _require(canonical(_plain(fence.control)) == control,
                                     "NSE_LOCAL_SOURCE_STALE")
                            self._retain_disposition(original, "SUCCEEDED", None)
                    except ValueError as error:
                        if str(error) not in _STALE:
                            raise
                        self._retain_disposition(original, "STALE", "NSE_LOCAL_SOURCE_STALE")
                return self.prepare()
            except Exception as error:
                # Unexpected local computation/retention failures must be visible
                # on the next prepared page, not disguised as NOT_RECORDED.
                # No retry, fabricated result or historical repair occurs.
                self._prepared = None
                self._failure = (str(error) if isinstance(error, ValueError) and
                    str(error).startswith(("NSE_LOCAL_", "SWING_RESEARCH_COMMISSIONING_", "SWING_WO12_"))
                    else "NSE_LOCAL_OPERATION_UNAVAILABLE")
                raise

    def _retain_disposition(self, original, state, reason):
        with self.store.transaction():
            self._commissioned()
            originals, dispositions = self._load_history()
            _require(originals.get(original.data["input_sha256"]) == original,
                     "NSE_LOCAL_ORIGINAL_CONFLICT")
            prior = dispositions.get(original.identity)
            if prior is None:
                checked_at = self._now()
                _require(checked_at >= _time(original.data["completed_at"]),
                         "NSE_LOCAL_CLOCK_INVALID")
                prior = record(_DISPOSITION, original_identity=original.identity,
                    operation_identity=original.data["operation_identity"], state=state,
                    reason=reason, checked_at=checked_at.isoformat(), authority=_AUTHORITY)
                _disposition(prior, {original.identity: original})
                self.store.retain(prior)
                dispositions[original.identity] = prior
            self._originals, self._dispositions = originals, dispositions

    def _fence_record(self, item):
        path = self.store.root / "records" / item.schema / (item.identity + ".json")
        payload = path.read_bytes()
        expected = canonical({"schema": item.schema, "identity": item.identity,
            "data": item.data, "integrity_sha256": item.integrity_sha256}) + b"\n"
        _require(payload == expected, "NSE_LOCAL_HISTORY_UNAVAILABLE")
        record_prepared_read(path, payload)
        return payload

    def prepare(self, *, _response=None):
        """Explicit preparation only: no analysis, writes, or history selector."""
        if _response is None:
            with self.intake.response() as prepared:
                return self.prepare(_response=prepared)
        with self._lock:
            self._prepared = None
            try:
                _require(not self._closed, "NSE_LOCAL_CLOSED")
                _require(self._history_failure is None, "NSE_LOCAL_HISTORY_UNAVAILABLE")
                _require(self._failure is None, self._failure or "NSE_LOCAL_OPERATION_UNAVAILABLE")
                self._commissioned()
                manifest, facts, native, requirements, control = self._context(_response)
                rows = []
                completion_boundary = None
                now = self._now()
                for requirement in requirements:
                    local_input, _expected = self._input(requirement, native, facts, manifest)
                    original = self._originals.get(local_input.identity)
                    disposition = None if original is None else self._dispositions.get(original.identity)
                    state = "NOT_RECORDED" if original is None else (
                        "UNAVAILABLE" if disposition is None else disposition.data["state"])
                    reason = ("NSE_LOCAL_ORIGINAL_NOT_RECORDED" if original is None else
                        "NSE_LOCAL_FINAL_PROOF_MISSING" if disposition is None else disposition.data["reason"])
                    result = None
                    if original is not None:
                        self._fence_record(original)
                        boundary = _time(original.data["completed_at"])
                        if disposition is not None:
                            self._fence_record(disposition)
                            boundary = max(boundary, _time(disposition.data["checked_at"]))
                        # Chronologically valid immutable history can outlive a
                        # clock rollback. Preserve it, but do not present future
                        # capture/completion/final-proof times as current.
                        _require(boundary <= now, "NSE_LOCAL_CLOCK_INVALID")
                        completion_boundary = boundary if completion_boundary is None else max(
                            completion_boundary, boundary)
                        if state == "SUCCEEDED":
                            result = json.loads(original.data["result_json"])["result"]
                    rows.append(dict(instrument=requirement.canonical_instrument,
                        requirement_id=requirement.requirement_sha256, state=state, reason=reason,
                        original_identity=None if original is None else original.identity,
                        operation_identity=None if original is None else original.data["operation_identity"],
                        input_sha256=local_input.identity,
                        result_sha256=None if original is None else original.data["output_sha256"],
                        captured_at=None if original is None else original.data["captured_at"],
                        completed_at=None if original is None else original.data["completed_at"],
                        result=result))
                self.intake.recheck_response(_response)
                _require(self._control(native.run_identity, manifest) == control,
                         "NSE_LOCAL_SOURCE_STALE")
                projection = dict(state="READY", reason=None, rows=tuple(rows),
                    method_version=METHOD_VERSION, run_identity=native.run_identity,
                    publication_sha256=manifest)
                self._prepared = (native, facts, control, projection, completion_boundary)
                self._preparation_failure = None
                return deepcopy(projection)
            except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
                reason = (str(error) if isinstance(error, ValueError)
                    and str(error).startswith(("NSE_LOCAL_", "SWING_RESEARCH_COMMISSIONING_"))
                    else "NSE_LOCAL_PROJECTION_UNAVAILABLE")
                self._preparation_failure = reason
                return dict(state="UNAVAILABLE", reason=reason, rows=(),
                    method_version=METHOD_VERSION, run_identity=None, publication_sha256=None)

    def projection(self, *, _response=None):
        """Pure cached result read; no engine, history scan, write or recovery."""
        with self._lock:
            prepared = self._prepared
            if prepared is None or self._closed or self._failure or self._history_failure:
                return dict(state="UNAVAILABLE", reason=self._history_failure or self._failure
                    or self._preparation_failure or "NSE_LOCAL_PREPARATION_MISSING", rows=(), method_version=METHOD_VERSION,
                    run_identity=None, publication_sha256=None)
            native, facts, control, projection, completion_boundary = prepared
            try:
                _require(completion_boundary is None or completion_boundary <= self._now(),
                         "NSE_LOCAL_CLOCK_INVALID")
                _require(_response is not None and _response.active
                    and _response.owner is self.intake
                    and _response.authority.native is native
                    and _response.context[1] is facts
                    and _response.context[0] == projection["publication_sha256"],
                    "NSE_LOCAL_SOURCE_STALE")
                _require(self._control(native.run_identity, projection["publication_sha256"]) == control,
                         "NSE_LOCAL_SOURCE_STALE")
                return deepcopy(projection)
            except (OSError, ValueError, AttributeError, TypeError, KeyError) as error:
                clock_unavailable = str(error) == "NSE_LOCAL_CLOCK_INVALID"
                return dict(state="UNAVAILABLE" if clock_unavailable else "STALE",
                    reason="NSE_LOCAL_CLOCK_INVALID" if clock_unavailable else "NSE_LOCAL_SOURCE_STALE", rows=(),
                    method_version=METHOD_VERSION, run_identity=native.run_identity,
                    publication_sha256=projection["publication_sha256"])

    def on_committed(self, bundle):
        """Called once by ordinary committed NSE analysis while its work is owned."""
        return self.refresh(run_identity=bundle.native.run_identity,
            publication_sha256=bundle.reference["sha256"], trigger="AUTOMATIC")

    def close(self):
        with self._lock:
            self._closed = True
            self._prepared = None
