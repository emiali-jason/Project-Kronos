"""TE-06A explicit Sponsor orchestration over qualified Theta services.

This module owns no research, validation, persistence or assessment semantics.
It serializes the two Browser actions, records their exact application results,
and projects those results after refresh/restart without causing new work.
"""

from copy import deepcopy
import re
from threading import Lock

from kronos.theta.assessment import ThetaAssessmentEngine
from kronos.theta.contracts import SUBJECTS, digest, encode, require
from kronos.theta.producer_v3 import V3QuestionProducer
from kronos.theta.store import sealed, unseal


SCHEMA_ID = "KRONOS-THETA-SPONSOR-WORKFLOW-V1"
SCHEMA_VERSION = "1.0.0"
_POINTERS = {
    "QUESTION_PACK": "v3_question_operation",
    "ANSWER_IMPORT": "v3_import_operation",
}


class ThetaSponsorWorkflow:
    """Exactly two explicit operations; GET/status paths are read-only."""

    def __init__(self, producer, assessment):
        require(type(producer) is V3QuestionProducer
                and type(assessment) is ThetaAssessmentEngine
                and assessment.intake is producer.intake,
                "THETA_SPONSOR_WORKFLOW_CONFIGURATION_INVALID")
        self.producer = producer
        self.assessment = assessment
        self.intake = producer.intake
        self.workflow = producer.workflow
        self.store = producer.store
        # Browser requests already use the shared maintenance admission owner.
        # This narrow gate only prevents overlapping Theta button executions.
        self._button_gate = Lock()

    def _input_document(self):
        workspace = self.workflow.chart_workspace()
        now = self.workflow.now()
        return {
            "cycle_id": workspace["cycle_id"],
            "charts": {card["subject"]: {
                "cycle_id": card["cycle_id"],
                "revision_id": card["revision_id"],
                "sha256": None if card["chart"] is None else card["chart"]["sha256"],
            } for card in workspace["cards"]},
            # Exact public owner/method inputs protect a page rendered before an
            # authority successor or validity change. Only the digest is sent.
            "methodology": self.producer._methodology(now),
            "targets": {subject: self.producer.target_authority.v3_inputs(subject, now)
                        for subject in SUBJECTS},
        }

    def input_state_sha256(self):
        """Exact chart/Macro state rendered into the current page."""
        return digest(encode(self._input_document()))

    def _validate_record(self, value):
        require(type(value) is dict and set(value) == {
            "schema_identity", "schema_version", "operation_id", "operation", "result"
        } and value["schema_identity"] == SCHEMA_ID
        and value["schema_version"] == SCHEMA_VERSION
        and value["operation"] in _POINTERS and type(value["result"]) is dict,
                "THETA_SPONSOR_OPERATION_INTEGRITY_INVALID")
        core = {k: value[k] for k in value if k != "operation_id"}
        require(value["operation_id"] == "TSO-" + digest(encode(core)),
                "THETA_SPONSOR_OPERATION_INTEGRITY_INVALID")
        return value

    def _retain_result(self, operation, result):
        require(operation in _POINTERS and type(result) is dict,
                "THETA_SPONSOR_OPERATION_INVALID")
        core = {"schema_identity": SCHEMA_ID, "schema_version": SCHEMA_VERSION,
                "operation": operation, "result": deepcopy(result)}
        value = {**core, "operation_id": "TSO-" + digest(encode(core))}
        # One exact operation record, then one atomic existing Theta selection
        # pointer. No directory order, mtime or latest-file inference is used.
        with self.store.transaction():
            self.store.retain("v3-browser-operations", value["operation_id"] + ".json",
                              sealed(value))
            selection = self.store.current()
            selection[_POINTERS[operation]] = value["operation_id"]
            self.store.select(selection)
            retained = unseal(self.store.load("v3-browser-operations",
                                              value["operation_id"] + ".json"))
            self._validate_record(retained)
            require(retained == value, "THETA_SPONSOR_OPERATION_INTEGRITY_INVALID")
        return deepcopy(value)

    def _restore_one(self, operation):
        require(operation in _POINTERS, "THETA_SPONSOR_OPERATION_INVALID")
        with self.store.transaction():
            identity = self.store.current().get(_POINTERS[operation])
            if identity is None:
                return None
            require(type(identity) is str and re.fullmatch(r"TSO-[0-9a-f]{64}", identity),
                    "THETA_SPONSOR_OPERATION_INTEGRITY_INVALID")
            value = unseal(self.store.load("v3-browser-operations", identity + ".json"))
            self._validate_record(value)
            require(value["operation"] == operation,
                    "THETA_SPONSOR_OPERATION_INTEGRITY_INVALID")
            return deepcopy(value)

    def restore_status(self):
        """Read-only operation projection; never imports, assesses or republishes."""
        selected = self.producer.selected()
        return {
            "input_state_sha256": self.input_state_sha256(),
            "selected_question_pack": selected,
            "question_operation": self._restore_one("QUESTION_PACK"),
            "import_operation": self._restore_one("ANSWER_IMPORT"),
        }

    def _enter(self):
        require(self._button_gate.acquire(blocking=False), "THETA_SPONSOR_OPERATION_BUSY")

    def create_question_pack(self, expected_input_state_sha256):
        self._enter()
        try:
            require(type(expected_input_state_sha256) is str
                    and re.fullmatch(r"[0-9a-f]{64}", expected_input_state_sha256)
                    and expected_input_state_sha256 == self.input_state_sha256(),
                    "THETA_SPONSOR_INPUT_STATE_STALE")
            result = self.producer.create()
            require(result.get("complete") is True
                    and set(result.get("questions", {})) == set(SUBJECTS),
                    "THETA_SPONSOR_QUESTION_PACK_INVALID")
            return self._retain_result("QUESTION_PACK", result)
        finally:
            self._button_gate.release()

    @staticmethod
    def _assessment_projection(result):
        record = result.get("assessment")
        horizons = record["horizons"] if record is not None else result["horizons"]
        return {
            "assessment_id": None if record is None else record["assessment_id"],
            "disposition": result["disposition"],
            "currentness": result["currentness"],
            "E1": horizons["E1"]["result"],
            "E2": horizons["E2"]["result"],
            "reason": result.get("reason_code"),
        }

    def import_astra_answers(self, question_batch_id):
        self._enter()
        try:
            require(type(question_batch_id) is str
                    and re.fullmatch(r"TEB-[0-9a-f]{64}", question_batch_id),
                    "THETA_SPONSOR_BATCH_INVALID")
            selected = self.producer.selected()
            require(selected is not None and selected["batch_id"] == question_batch_id
                    and selected["current"], "THETA_SPONSOR_BATCH_STALE")
            intake = self.intake.import_combined_astra_answer(question_batch_id)
            assessments = {}
            for subject in SUBJECTS:
                child = intake["children"][subject]
                # Acceptance and assessment are deliberately separate. A child
                # changed to STALE during import is retained but not assessed.
                if (child["receipt_id"] is None or child["currentness"] != "CURRENT"
                        or child["status"] not in {"ACCEPTED", "REPLAY"}):
                    assessments[subject] = None
                    continue
                try:
                    assessed = self.assessment.assess_accepted_theta_answer(child["answer_id"])
                    assessments[subject] = self._assessment_projection(assessed)
                except (OSError, KeyError, TypeError, ValueError):
                    # The TE-04B acceptance remains authoritative and committed.
                    assessments[subject] = {
                        "assessment_id": None, "disposition": "NOT_EVALUABLE",
                        "currentness": child["currentness"],
                        "E1": "NOT_EVALUABLE", "E2": "NOT_EVALUABLE",
                        "reason": "THETA_ASSESSMENT_OPERATION_UNAVAILABLE",
                    }
            result = {"intake": intake, "assessments": assessments}
            return self._retain_result("ANSWER_IMPORT", result)
        finally:
            self._button_gate.release()

    def question_pack(self, question_batch_id):
        """Return exact retained bytes for a known V3 transport; no publication."""
        require(type(question_batch_id) is str
                and re.fullmatch(r"TEB-[0-9a-f]{64}", question_batch_id),
                "THETA_SPONSOR_BATCH_INVALID")
        with self.store.transaction():
            self.intake._batch(question_batch_id)
            record = unseal(self.store.load("v3-question-transports",
                                            question_batch_id + ".json"))
            require(record["batch_id"] == question_batch_id
                    and set(record) == {"batch_id", "filename", "zip_sha256"},
                    "THETA_SPONSOR_QUESTION_PACK_INVALID")
            payload = self.store.load_blob(record["zip_sha256"])
            require(digest(payload) == record["zip_sha256"],
                    "THETA_SPONSOR_QUESTION_PACK_INVALID")
            return record["filename"], payload

    def retained_answer(self, question_id, subject):
        """Read one exact accepted V3 lineage for Outlook/Detail; never assess."""
        require(subject in SUBJECTS and type(question_id) is str
                and re.fullmatch(r"TEQ-[0-9a-f]{64}", question_id),
                "THETA_SPONSOR_QUESTION_PACK_INVALID")
        with self.store.transaction():
            claim = self.intake._get("question-answers", question_id + ".json")
        # Each qualified reader owns its transaction; flock is not reentrant.
        evidence, receipt, question, answer = self.assessment._load_question_answer(
            claim["receipt_id"])
        require(receipt["subject"] == subject and receipt["question_id"] == question_id,
                "THETA_INTEGRITY_INVALID")
        restored = self.intake.restore_import(receipt["attempt_id"])
        child = restored["children"][subject]
        require(child["receipt_id"] == receipt["acceptance_id"],
                "THETA_INTEGRITY_INVALID")
        return {"question": question, "answer": answer, "receipt": receipt,
                "currentness": child["currentness"], "raw": evidence["child_raw"]}

    def outlook(self):
        """Project exactly selected Questions and retained TE-04B/TE-05C facts.

        Missing/corrupt assessment preserves an intact accepted forecast. Missing
        or noncurrent acceptance never substitutes a historical sibling. No
        operation-status snapshot or directory scan supplies currentness.
        """
        with self.store.transaction():
            selection = self.store.current()
        try:
            operation = self._restore_one("ANSWER_IMPORT")
            imported = None if operation is None else self.intake.restore_import(
                operation["result"]["intake"]["attempt_id"])
        except (OSError, KeyError, TypeError, ValueError):
            imported = None  # Diagnostic only; never a forecast/currentness source.
        rows = []
        for subject in SUBJECTS:
            row = {"subject": subject, "currentness": "UNAVAILABLE",
                   "reason": "NO_CURRENT_ACCEPTED_ANSWER", "evidence": None,
                   "assessment": None, "assessment_reason": "ASSESSMENT_UNAVAILABLE"}
            question_id = selection.get("v3_questions", {}).get(subject)
            if question_id is not None:
                try:
                    question = self.intake._get("questions", question_id + ".json")
                    row["currentness"] = self.intake._currentness(
                        question, selection, self.workflow.now())
                    row["reason"] = ("NO_ACCEPTED_ANSWER" if row["currentness"] == "CURRENT"
                                     else "QUESTION_" + row["currentness"])
                    evidence = self.retained_answer(question_id, subject)
                    row["currentness"] = evidence["currentness"]
                    if evidence["currentness"] == "CURRENT":
                        row["evidence"], row["reason"] = evidence, None
                        try:
                            assessed = self.assessment.restore_assessment(
                                self.assessment._identity(evidence["receipt"]))
                            require(assessed["currentness"] == "CURRENT",
                                    "THETA_INTEGRITY_INVALID")
                            row["assessment"] = assessed["assessment"]
                            row["assessment_reason"] = None
                        except (OSError, KeyError, TypeError, ValueError):
                            pass  # Read-only NOT_EVALUABLE presentation, no new record.
                    else:
                        row["reason"] = "ANSWER_" + evidence["currentness"]
                except FileNotFoundError:
                    pass
                except (OSError, KeyError, TypeError, ValueError):
                    row.update(currentness="UNAVAILABLE", reason="EVIDENCE_UNVERIFIABLE",
                               evidence=None, assessment=None)
            rows.append(row)
            if row["evidence"] is None and imported is not None:
                child = imported["children"][subject]
                if (child["question_id"] == question_id and child["status"] == "REJECTED"
                        and child["reason"] is not None):
                    row["reason"] = child["reason"]
        # A chart/Question successor may arrive while immutable records are
        # restored. Recheck through TE-04B under its selection lock before
        # returning any current forecast; never keep a stale read snapshot.
        with self.store.transaction():
            latest, now = self.store.current(), self.workflow.now()
            for row in rows:
                if row["evidence"] is None:
                    continue
                currentness = self.intake._currentness(row["evidence"]["question"], latest, now)
                row["currentness"] = currentness
                if currentness != "CURRENT":
                    row.update(evidence=None, assessment=None, reason="ANSWER_" + currentness)
        return rows

    def detail(self, question_id, subject):
        """Read one exact accepted forecast and its original assessment, including history."""
        evidence = self.retained_answer(question_id, subject)
        try:
            restored = self.assessment.restore_assessment(
                self.assessment._identity(evidence["receipt"]))
            assessment = restored["assessment"]
        except (OSError, KeyError, TypeError, ValueError):
            assessment = None
        with self.store.transaction():
            evidence["currentness"] = self.intake._currentness(
                evidence["question"], self.store.current(), self.workflow.now())
        return {**evidence, "assessment": assessment}

    def detail_chart(self, question_id, subject, role):
        """Return original Question-bound bytes even after chart/Question succession."""
        require(role in {"COMMODITY", "GLOBAL_MACRO"}, "THETA_CHART_INVALID")
        evidence = self.retained_answer(question_id, subject)
        binding = evidence["question"]["binding"][
            "commodity_chart" if role == "COMMODITY" else "macro_chart"]
        chart = self.store.chart(binding["chart_id"])
        require(chart["sha256"] == binding["sha256"], "THETA_INTEGRITY_INVALID")
        return chart["media_type"], self.store.load_blob(binding["sha256"])


__all__ = ["ThetaSponsorWorkflow"]
