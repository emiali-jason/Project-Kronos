"""TE-04B explicit, Theta-local V3 evidence intake. No Browser or acquisition.

Question retention/selection are trusted upstream seams, not inbox authority.
Imports never commission Questions, select evidence, or assess research quality.
An import commit is published LAST. Interrupted graphs are unavailable, never
reconstructed on read/restart. All immutable artifacts use the retained store.
"""
from copy import deepcopy
import os
import re
import stat

from kronos.theta.contracts import SUBJECTS, ThetaError, digest, encode, require, stamp
from kronos.theta.contracts_v3 import validate_question_batch_v3, validate_combined_answer
from kronos.theta.json_evidence import parse_representations
from kronos.theta.schema_v3 import MAX_COMBINED_BYTES, V3Error
from kronos.theta.store import directory, sealed, unseal

RESULT_SCHEMA = "KRONOS-THETA-COMBINED-INTAKE-V1"


def _id(value, prefix):
    require(type(value) is str and re.fullmatch(prefix + r"-[0-9a-f]{64}", value),
            "THETA_INTAKE_IDENTITY_INVALID")


def _key(value):
    return digest(encode(value)) + ".json"


def _safe_read(inbox, name):
    """Bounded stable snapshot, not mtime-based discovery or freshness authority."""
    with directory(inbox) as parent:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                    and 0 < before.st_size <= MAX_COMBINED_BYTES, "THETA_INTAKE_FILE_INVALID")
            raw = stream.read(MAX_COMBINED_BYTES + 1)
            stream.seek(0)
            second = stream.read(MAX_COMBINED_BYTES + 1)
            after = os.fstat(stream.fileno())
            named = os.stat(name, dir_fd=parent, follow_symlinks=False)
            fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns", "st_nlink")
            require(len(raw) == before.st_size and raw == second
                    and all(getattr(before, k) == getattr(after, k) == getattr(named, k) for k in fields),
                    "THETA_INTAKE_FILE_UNSTABLE")
            return raw


class CombinedAnswerIntake:
    """One explicitly invoked import; no watchers, Provider or runtime defaults.

    workflow supplies the existing chart lineage/selection and clock. The
    optional current_authorities(subject, now) is a read-only trusted owner
    projection returning methodology and target_authority descriptors. Missing
    authority never falls back to the historical Question to claim CURRENT.
    """
    def __init__(self, workflow, *, current_authorities=None):
        self.workflow, self.store = workflow, workflow.store
        self.inbox = workflow.inbox
        self.current_authorities = current_authorities

    def _put(self, family, name, value):
        payload = sealed(value)
        self.store.retain("v3-" + family, name, payload)
        require(self.store.load("v3-" + family, name) == payload, "THETA_INTEGRITY_INVALID")

    def _get(self, family, name):
        return unseal(self.store.load("v3-" + family, name))

    def _optional(self, family, name):
        try:
            return self._get(family, name)
        except FileNotFoundError:
            return None

    def _blob(self, raw):
        identity = self.store.blob(raw)
        require(self.store.load_blob(identity) == raw, "THETA_INTEGRITY_INVALID")
        return identity

    def _chart_graph(self, question):
        """Verify retained original chart/revision/cycle, independent of selection."""
        for key in ("commodity_chart", "macro_chart"):
            binding = question["binding"][key]
            chart = self.store.chart(binding["chart_id"])
            revision = unseal(self.store.load("chart-revisions", binding["revision_id"] + ".json"))
            cycle = unseal(self.store.load("cycles", binding["cycle_id"] + ".json"))
            require(binding["revision_id"] == "TCR-" + digest(encode(revision))
                    and binding["cycle_id"] == "TAC-" + digest(encode(cycle))
                    and revision["cycle_id"] == binding["cycle_id"]
                    and revision["chart_id"] == binding["chart_id"]
                    and revision["sha256"] == chart["sha256"] == binding["sha256"]
                    and chart["subject"] == binding["subject"]
                    and revision["subject"] == (None if key == "macro_chart" else binding["subject"])
                    and revision["byte_length"] == len(self.store.load_blob(binding["sha256"]))
                    and stamp(revision["accepted_at"]) <= stamp(question["information_cutoff"]),
                    "THETA_INTEGRITY_INVALID")

    def retain_question_batch(self, batch, questions):
        """Retain exact commissioned V3 inputs supplied by a trusted producer.

        Structural retention is NOT commissioning/methodology approval and does
        not select a batch. There is no path to this seam from an Analyst file.
        Historical V1/V2 storage/readers remain untouched.
        """
        validate_question_batch_v3(batch, questions)
        with self.store.transaction():
            for q in questions.values():
                self._chart_graph(q)
                self._put("questions", q["question_id"] + ".json", q)
            self._put("batches", batch["batch_id"] + ".json", batch)
            self._batch(batch["batch_id"])
        return batch["batch_id"]

    def _batch(self, identity):
        _id(identity, "TEB")
        batch = self._get("batches", identity + ".json")
        questions = {s: self._get("questions", batch["questions"][s]["question_id"] + ".json") for s in SUBJECTS}
        validate_question_batch_v3(batch, questions)
        require(batch["batch_id"] == identity, "THETA_INTEGRITY_INVALID")
        for q in questions.values():
            self._chart_graph(q)
        return batch, questions

    def _live_binding(self, q, selection, now):
        from kronos.theta.packs import binding
        if q["binding"]["cycle_id"] != self.workflow._cycle(selection):
            return False
        for key, role in (("commodity_chart", q["binding"]["subject"]), ("macro_chart", "GLOBAL_MACRO")):
            card = self.workflow._role_chart(selection, role)
            if card["chart"] is None or binding(card) != q["binding"][key]:
                return False
        if not callable(self.current_authorities):
            return False
        try:
            owner = self.current_authorities(q["binding"]["subject"], now)
        except Exception:
            return False  # Unavailable owner projection cannot assert currentness.
        return (type(owner) is dict and set(owner) == {"methodology", "target_authority"}
                and all(owner[k] == q["binding"][k] for k in owner)
                and now <= stamp(q["authority_valid_through"])
                and all(now < stamp(t["expires_at"]) for t in q["targets"].values()))

    def select_question_batch(self, identity):
        """Explicit upstream selection only; never invoked by import or read.

        Reuses existing atomic selection history with separate V3 keys so the
        legacy Browser cannot accidentally consume V3 as a V1/V2 Question.
        """
        with self.store.transaction():
            batch, questions = self._batch(identity)
            selection = self.store.current()
            now = self.workflow.now()
            require(all(self._live_binding(q, selection, now) for q in questions.values()),
                    "THETA_INTAKE_BINDING_STALE")
            selection["v3_question_batch"] = identity
            selection["v3_questions"] = {s: q["question_id"] for s, q in questions.items()}
            self.store.select(selection)

    def _currentness(self, q, selection, now):
        selected = selection.get("v3_questions", {}).get(q["binding"]["subject"])
        if selected is None:
            return "HISTORICAL"
        if selected != q["question_id"]:
            return "SUPERSEDED"
        return "CURRENT" if self._live_binding(q, selection, now) else "STALE"

    def _empty(self, batch_id, reason):
        return {"schema_identity": RESULT_SCHEMA, "schema_version": "1.0.0",
                "question_batch_id": batch_id, "answer_package_id": None,
                "attempt_id": None, "package_status": "REJECTED", "original_package_status": "REJECTED",
                "reason": reason, "children": {s: {"status": "REJECTED", "reason": reason,
                    "question_id": None, "answer_id": None, "receipt_id": None,
                    "currentness": "HISTORICAL"} for s in SUBJECTS}}

    def _receipt_core(self, attempt, child, q):
        r = child.representation
        return {"schema_identity": "KRONOS-THETA-V3-ACCEPTANCE-V1", "schema_version": "1.0.0",
                "attempt_id": attempt["attempt_id"], "answer_package_id": attempt["answer_package_id"],
                "question_batch_id": attempt["question_batch_id"], "question_id": q["question_id"],
                "subject": child.subject, "answer_id": child.answer["answer_id"],
                "raw_package_sha256": attempt["raw_package_sha256"],
                "canonical_package_sha256": attempt["canonical_package_sha256"],
                "raw_child_sha256": r.raw_sha256, "canonical_child_sha256": r.canonical_sha256,
                "byte_start": r.start, "byte_end": r.end,
                "question_sha256": digest(encode(q)), "binding": deepcopy(q["binding"]),
                "information_cutoff": q["information_cutoff"], "accepted_at": attempt["received_at"],
                "validation_contract": {"schema_identity": "KRONOS-THETA-ANSWER-V1", "schema_version": "3.0.0"}}

    def _origin(self, identity):
        """Read an import commit and exact original package at its original time."""
        _id(identity, "TIA")
        commit = self._get("imports", identity + ".json")
        require(commit["attempt_id"] == identity and identity == "TIA-" + digest(encode(
            [commit["question_batch_id"], commit["raw_package_sha256"]])), "THETA_INTEGRITY_INVALID")
        intent = self._get("intents", identity + ".json")
        require(intent == {k: commit[k] for k in ("attempt_id", "question_batch_id", "raw_package_sha256", "received_at")},
                "THETA_INTEGRITY_INVALID")
        batch, questions = self._batch(commit["question_batch_id"])
        raw = self.store.load_blob(commit["raw_package_sha256"])
        try:
            parsed, _ = parse_representations(raw, maximum=MAX_COMBINED_BYTES)
            canonical = digest(encode(parsed))
        except V3Error:
            canonical = None
        require(canonical == commit["canonical_package_sha256"], "THETA_INTEGRITY_INVALID")
        if commit["wrapper_valid"]:
            validated = validate_combined_answer(raw, batch=batch, questions=questions, received_at=stamp(commit["received_at"]))
            require(validated.answer_package_id == commit["answer_package_id"]
                    and validated.canonical_sha256 == commit["canonical_package_sha256"]
                    and self._get("package-identities", _key(validated.answer_package_id)) == {
                        "attempt_id": identity, "raw_package_sha256": commit["raw_package_sha256"]},
                    "THETA_INTEGRITY_INVALID")
            for c in validated.children:
                require(self.store.load_blob(c.representation.raw_sha256) == c.representation.raw_bytes,
                        "THETA_INTEGRITY_INVALID")
        else:
            validated = None
            try:
                validate_combined_answer(raw, batch=batch, questions=questions, received_at=stamp(commit["received_at"]))
            except V3Error as error:
                require(str(error) == commit["reason"], "THETA_INTEGRITY_INVALID")
            else:
                raise ThetaError("THETA_INTEGRITY_INVALID")
        require(set(commit["children"]) == set(SUBJECTS), "THETA_INTEGRITY_INVALID")
        for subject, row in commit["children"].items():
            require(row["question_id"] == questions[subject]["question_id"]
                    and row["status"] in {"ACCEPTED", "REPLAY", "REJECTED"}, "THETA_INTEGRITY_INVALID")
            if row["status"] == "REJECTED":
                expected = {"kind": "CHILD_REJECTED" if commit["wrapper_valid"] else "PACKAGE_REJECTED",
                    "attempt_id": identity, "subject": subject, "reason": row["reason"],
                    "raw_package_sha256": commit["raw_package_sha256"], "received_at": commit["received_at"]}
                require(row["receipt_id"] is None and row["answer_id"] is None
                        and self._get("rejections", _key([identity, subject])) == expected,
                        "THETA_INTEGRITY_INVALID")
            else:
                require(validated is not None and row["reason"] is None, "THETA_INTEGRITY_INVALID")
                representation = next(c.representation for c in validated.children if c.subject == subject)
                receipt = self._get("receipts", row["receipt_id"] + ".json")
                require(receipt["raw_child_sha256"] == representation.raw_sha256
                        and receipt["canonical_child_sha256"] == representation.canonical_sha256,
                        "THETA_INTEGRITY_INVALID")
        good = sum(c["receipt_id"] is not None for c in commit["children"].values())
        status = "COMPLETE" if good == 5 else "PARTIAL" if good else "REJECTED"
        if good == 5 and all(c["status"] == "REPLAY" for c in commit["children"].values()):
            status = "REPLAY"
        require(commit["package_status"] == status, "THETA_INTEGRITY_INVALID")
        return commit, questions, raw, validated

    def _receipt(self, identity):
        _id(identity, "TRA")
        receipt = self._get("receipts", identity + ".json")
        core = {k: v for k, v in receipt.items() if k != "acceptance_id"}
        require(receipt["acceptance_id"] == identity == "TRA-" + digest(encode(core)), "THETA_INTEGRITY_INVALID")
        commit, questions, _, validation = self._origin(receipt["attempt_id"])
        require(validation is not None, "THETA_INTEGRITY_INVALID")
        child = next(c for c in validation.children if c.subject == receipt["subject"])
        require(child.answer is not None and self._receipt_core(commit, child, questions[child.subject]) == core
                and commit["children"][child.subject]["receipt_id"] == identity
                and commit["children"][child.subject]["status"] == "ACCEPTED"
                and self._get("answer-identities", _key(receipt["answer_id"])) == {"receipt_id": identity}
                and self._get("question-answers", receipt["question_id"] + ".json") == {"receipt_id": identity},
                "THETA_INTEGRITY_INVALID")
        return receipt

    def _view(self, commit, questions, *, replay=False):
        selection, now = self.store.current(), self.workflow.now()
        result = {k: commit[k] for k in ("question_batch_id", "answer_package_id", "attempt_id", "reason")}
        result.update(schema_identity=RESULT_SCHEMA, schema_version="1.0.0",
                      package_status="REPLAY" if replay else commit["package_status"],
                      original_package_status=commit["package_status"], children={})
        for subject in SUBJECTS:
            child = deepcopy(commit["children"][subject])
            currentness = self._currentness(questions[subject], selection, now)
            child["currentness"] = currentness
            if child["receipt_id"]:
                receipt = self._receipt(child["receipt_id"])
                require(receipt["question_id"] == child["question_id"] and receipt["answer_id"] == child["answer_id"],
                        "THETA_INTEGRITY_INVALID")
                if replay:
                    child["status"] = "REPLAY"
                elif currentness != "CURRENT":
                    child["status"] = "STALE"
            result["children"][subject] = child
        return result

    def restore_import(self, attempt_id):
        """Read only; validates receipts at original receipt time, never now."""
        try:
            with self.store.transaction():
                commit, questions, _, _ = self._origin(attempt_id)
                return self._view(commit, questions)
        except (OSError, KeyError, TypeError, ValueError):
            raise ThetaError("THETA_INTAKE_RESTORE_INVALID") from None

    def accepted_evidence(self, receipt_id):
        with self.store.transaction():
            receipt = self._receipt(receipt_id)
            return {"receipt": receipt, "package_raw": self.store.load_blob(receipt["raw_package_sha256"]),
                    "child_raw": self.store.load_blob(receipt["raw_child_sha256"])}

    def import_combined_astra_answer(self, question_batch_id):
        """Read ONLY <question_batch_id>_ANSWERS.json; never alter Sponsor input."""
        try:
            _id(question_batch_id, "TEB")
            with self.store.transaction():
                return self._import(question_batch_id)
        except (OSError, KeyError, TypeError, ValueError) as error:
            code = str(error) if isinstance(error, ThetaError) and re.fullmatch(r"THETA_[A-Z0-9_]{1,100}", str(error)) else "THETA_INTAKE_LOCAL_EVIDENCE_UNAVAILABLE"
            result = self._empty(question_batch_id if type(question_batch_id) is str and re.fullmatch(r"TEB-[0-9a-f]{64}", question_batch_id) else None, code)
            # Bounded operation failure audit; no payload/path/exception trace.
            try:
                with self.store.transaction():
                    event = {"kind": "PACKAGE_REJECTED", "result": result, "observed_at": self.workflow.now().isoformat()}
                    self._put("failures", _key(event), event)
            except (OSError, ValueError):
                pass  # A broken store cannot honestly promise a durable rejection.
            return result

    def _import(self, identity):
        batch, questions = self._batch(identity)
        raw = _safe_read(self.inbox, identity + "_ANSWERS.json")
        raw_sha = digest(raw)
        aid = "TIA-" + digest(encode([identity, raw_sha]))
        if self._optional("imports", aid + ".json") is not None:
            commit, retained_questions, _, _ = self._origin(aid)
            return self._view(commit, retained_questions, replay=True)
        require(self._optional("intents", aid + ".json") is None, "THETA_INTAKE_INCOMPLETE")
        intent = {"attempt_id": aid, "question_batch_id": identity, "raw_package_sha256": raw_sha,
                  "received_at": self.workflow.now().isoformat()}
        self._put("intents", aid + ".json", intent)
        self._blob(raw)  # Whole exact bytes precede parsing or canonicalization.
        commit = {**intent, "answer_package_id": None, "canonical_package_sha256": None,
                  "wrapper_valid": False, "package_status": "REJECTED", "reason": None,
                  "children": {s: {"status": "REJECTED", "reason": None,
                    "question_id": q["question_id"], "answer_id": None, "receipt_id": None}
                    for s, q in questions.items()}}
        try:
            parsed, _ = parse_representations(raw, maximum=MAX_COMBINED_BYTES)
            commit["canonical_package_sha256"] = digest(encode(parsed))
            validation = validate_combined_answer(raw, batch=batch, questions=questions,
                                                  received_at=stamp(intent["received_at"]))
        except V3Error as error:
            commit["reason"] = str(error)
            for c in commit["children"].values():
                c["reason"] = str(error)
        else:
            commit.update(wrapper_valid=True, answer_package_id=validation.answer_package_id,
                          canonical_package_sha256=validation.canonical_sha256)
            claim = self._optional("package-identities", _key(validation.answer_package_id))
            if claim is not None:
                self._put("conflicts", aid + ".json", {"kind": "PACKAGE_REJECTED",
                    "reason": "THETA_INTAKE_PACKAGE_IDENTITY_CONFLICT", **intent,
                    "answer_package_id": validation.answer_package_id,
                    "canonical_package_sha256": validation.canonical_sha256,
                    "retained_claim": claim})
            require(claim is None, "THETA_INTAKE_PACKAGE_IDENTITY_CONFLICT")
            self._put("package-identities", _key(validation.answer_package_id),
                      {"attempt_id": aid, "raw_package_sha256": raw_sha})
            value, _ = parse_representations(raw, maximum=MAX_COMBINED_BYTES)
            for child in validation.children:
                subject, representation = child.subject, child.representation
                self._blob(representation.raw_bytes)
                row = commit["children"][subject]
                candidate = value["answers"][subject]
                answer_id = candidate.get("answer_id") if type(candidate) is dict else None
                index = self._optional("answer-identities", _key(answer_id)) if type(answer_id) is str else None
                if child.failure_code == "THETA_V3_IDENTITY_CONFLICT":
                    row["reason"] = child.failure_code
                elif index is not None:
                    receipt = self._receipt(index["receipt_id"])
                    if (receipt["question_id"] == questions[subject]["question_id"]
                            and receipt["raw_child_sha256"] == representation.raw_sha256
                            and receipt["canonical_child_sha256"] == representation.canonical_sha256):
                        row.update(status="REPLAY", answer_id=answer_id, receipt_id=receipt["acceptance_id"])
                    else:
                        row["reason"] = "THETA_INTAKE_CHILD_IDENTITY_CONFLICT"
                elif child.answer is None:
                    row["reason"] = child.failure_code
                elif self._optional("question-answers", questions[subject]["question_id"] + ".json") is not None:
                    row["reason"] = "THETA_INTAKE_QUESTION_ANSWER_CONFLICT"
                else:
                    core = self._receipt_core(commit, child, questions[subject])
                    rid = "TRA-" + digest(encode(core))
                    self._put("receipts", rid + ".json", {**core, "acceptance_id": rid})
                    self._put("answer-identities", _key(answer_id), {"receipt_id": rid})
                    self._put("question-answers", questions[subject]["question_id"] + ".json", {"receipt_id": rid})
                    row.update(status="ACCEPTED", answer_id=answer_id, receipt_id=rid)
            good = sum(c["receipt_id"] is not None for c in commit["children"].values())
            commit["package_status"] = "COMPLETE" if good == 5 else "PARTIAL" if good else "REJECTED"
            if good == 5 and all(c["status"] == "REPLAY" for c in commit["children"].values()):
                commit["package_status"] = "REPLAY"
        for subject, child in commit["children"].items():
            if child["status"] == "REJECTED":
                self._put("rejections", _key([aid, subject]), {"kind": "CHILD_REJECTED" if commit["wrapper_valid"] else "PACKAGE_REJECTED",
                    "attempt_id": aid, "subject": subject, "reason": child["reason"],
                    "raw_package_sha256": raw_sha, "received_at": intent["received_at"]})
        self._put("imports", aid + ".json", commit)  # Acceptance graph commit point.
        retained, retained_questions, _, _ = self._origin(aid)
        return self._view(retained, retained_questions)
