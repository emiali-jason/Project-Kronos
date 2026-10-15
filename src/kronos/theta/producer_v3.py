"""TE-04C explicit V3 producer integration. No runtime/Browser enrollment.

Reuses TE-01 originals, TE-02 rendering/publication, frozen TE-03A authority,
TE-04A definitions and TE-04B upstream retention/selection. TE-05B adds explicit
governed methodology admission; default runtime composition remains unenrolled.
"""
from copy import deepcopy

from kronos.theta.combined_intake import CombinedAnswerIntake
from kronos.theta.contracts import CANONICAL, SUBJECTS, ThetaError, digest, encode, require, stamp
from kronos.theta.contracts_v3 import (make_question_v3, make_question_batch_v3,
    combined_answer_template, combined_answer_schema)
from kronos.theta.packs import binding
from kronos.theta.question_pack import COMMON, archive, render_question
from kronos.theta.schema_v3 import producer_instructions
from kronos.theta.store import directory, read_at, sealed, unseal, write_at
from kronos.theta.target_authority import ThetaTargetAuthorityAdapter
from kronos.theta.methodology import ThetaMethodologyPublication


def mandate_v3():
    """Keep research depth; replace only legacy machine-response directions."""
    result = []
    result.append(("Owner-bound terminal reference", "For each exact E1/E2 option expiry, forecast the daily settlement price "
        "of its specified underlying MCX futures contract ON THE OPTION EXPIRY DATE. "
        "This is not futures-expiry Due Date Rate (DDR), last traded price or an OHLC close. "
        "Use the supplied quotation unit, not lot size. These target facts come from the governed TE-03A authority."))
    for title, text in COMMON:
        if title == "Required response and exact machine template":
            result.append((title, "Complete the ONE combined-answer-template.json using combined-answer.schema.json. "
                "Each answers.<subject> independently answers its exact canonical Question. "
                "Preserve every prefilled identity, binding, target and per-Question T0. "
                "Use the structured research and independent E1/E2 forecast fields; do not return legacy V1/V2 fields."))
        elif title == "Cross-commodity consistency and analytical boundary":
            result.append((title, text.replace("Return each Answer to its own canonical Question/template.",
                "Return five independent child Answers in their exact combined template slots; Macro is not a sixth slot.")))
        else:
            result.append((title, text))
    result.extend(("V3 governed producer rules" if index == 0 else "", paragraph)
                  for index, paragraph in enumerate(producer_instructions().split("\n\n")))
    return result


def render_v3_question(question, batch, charts, originals):
    """Presentation adapter, never canonical conversion or historical rewrite."""
    b = question["binding"]
    view = {**question, "subjects": [b["subject"]], "cycle_id": b["cycle_id"],
            "charts": [charts[b["subject"]]], "macro_chart": charts["GLOBAL_MACRO"],
            "targets": list(question["targets"].values())}
    technical = {"question_id": question["question_id"], "question_sha256": digest(encode(question)),
        "cycle_id": b["cycle_id"], "information_cutoff": question["information_cutoff"],
        "methodology": encode(b["methodology"]).decode(), "target_authority": encode(b["target_authority"]).decode(),
        "answer_schema_identity": "KRONOS-THETA-ANSWER-V1", "answer_schema_version": "3.0.0",
        "expected_answer_filename": batch["batch_id"] + "_ANSWERS.json"}
    return render_question(view, originals, presentation={"mandate": mandate_v3(), "technical": technical})


def transport_v3(batch, questions, charts, originals):
    """One deterministic ZIP, exactly one standalone original Macro artifact."""
    files = {"transport.json": encode(batch),
        "combined-answer-template.json": encode(combined_answer_template(batch, questions)),
        "combined-answer.schema.json": encode(combined_answer_schema(batch, questions)),
        "producer-instructions.txt": producer_instructions().encode(),
        "README.txt": (("SYNTHETIC - NOT FOR GENUINE FORECASTING\n" if batch["synthetic"] else "") +
            "Manually submit the five Question PDFs, canonical Questions and exact original images to Astra-Ultra. "
            "Research depth takes precedence over speed. Each Question retains its own fixed T0 and E1/E2. "
            "This ZIP is transport convenience, not analytical authority. Shared Macro is supporting evidence only. "
            "Complete ONE combined-answer-template.json; null placeholders are not a completed Answer. "
            "Use the closed combined-answer.schema.json AND producer-instructions.txt for semantic rules. "
            "Return exactly " + batch["batch_id"] + "_ANSWERS.json to KRONOS REVIEW PACK / Theta Earners / CHATGPT ANSWERS. "
            "No automatic Analyst call, research, import, assessment or trading occurs. "
            "manifest.json checks every payload; originals are unmodified.\n").encode()}
    for subject, q in questions.items():
        prefix = "individual/" + subject + "/"
        files[prefix + "question.json"] = encode(q)
        files[prefix + "THETA_" + subject + "_QUESTION.pdf"] = render_v3_question(q, batch, charts, originals)
    for role, chart in charts.items():
        prefix = "shared/" if role == "GLOBAL_MACRO" else "individual/" + role + "/charts/"
        suffix = ".png" if chart["media_type"] == "image/png" else ".jpg"
        files[prefix + role + suffix] = originals[chart["sha256"]]
    return archive(files)


class V3QuestionProducer:
    def __init__(self, workflow, target_authority, *, synthetic_methodology=None, published_methodology=None):
        require(type(target_authority) is ThetaTargetAuthorityAdapter, "THETA_TARGET_AUTHORITY_UNAVAILABLE")
        require(published_methodology is None or type(published_methodology) is ThetaMethodologyPublication,
                "THETA_METHODOLOGY_CONFIGURATION_INVALID")
        require(published_methodology is None or synthetic_methodology is None,
                "THETA_METHODOLOGY_CONFIGURATION_INVALID")
        self.workflow, self.store = workflow, workflow.store
        self.target_authority = target_authority
        self.synthetic_methodology = deepcopy(synthetic_methodology)
        self.published_methodology = published_methodology
        self.intake = CombinedAnswerIntake(workflow, current_authorities=self.current_authorities)

    def _methodology(self, at=None):
        if self.published_methodology is not None:
            return self.published_methodology.research_inputs(self.workflow.now() if at is None else at)
        # This explicit hold cannot be bypassed by merely supplying a descriptor.
        require(self.workflow.qualification_mode and self.synthetic_methodology is not None,
                "THETA_METHODOLOGY_UNAVAILABLE")
        value = self.synthetic_methodology
        require(type(value) is dict and set(value) == {"descriptor", "instructions"}
                and type(value["descriptor"]) is dict
                and type(value["descriptor"].get("identity")) is str
                and value["descriptor"]["identity"].startswith("SYNTHETIC-")
                and type(value["instructions"]) is str
                and "SYNTHETIC" in value["instructions"]
                and "NOT FOR GENUINE FORECASTING" in value["instructions"],
                "THETA_SYNTHETIC_AUTHORITY_REQUIRED")
        return deepcopy(value)

    def current_authorities(self, subject, at):
        return {"methodology": self._methodology(at)["descriptor"],
                "target_authority": self.target_authority.v3_inputs(subject, at)["target_authority"]}

    def _current_inputs(self, question, selection, now):
        if not self.intake._live_binding(question, selection, now):
            return False
        method = self._methodology(now)
        if self.published_methodology is not None:
            try:
                self.published_methodology.research_inputs(stamp(question["information_cutoff"]))
            except ThetaError:
                return False
        authority = self.target_authority.v3_inputs(question["binding"]["subject"], now)
        return (question["methodology_instructions"] == method["instructions"]
                and question["targets"] == authority["targets"]
                and question["authority_valid_through"] == authority["authority_valid_through"])

    def create(self):
        now = self.workflow.now()
        method = self._methodology(now)
        with self.store.transaction():
            selection = self.store.current()
            previous = selection.get("v3_question_batch")
            old = self.intake._batch(previous)[1] if previous else {}
            charts, originals = {}, {}
            cards = {s: self.workflow._role_chart(selection, s) for s in (*SUBJECTS, "GLOBAL_MACRO")}
            for role, card in cards.items():
                binding(card)  # Mandatory exact selected original and receipt.
                chart = card["chart"]
                require(stamp(chart["information_cutoff"]) <= now, "THETA_TIMESTAMP_INVALID")
                charts[role] = chart
                originals[chart["sha256"]] = self.store.load_blob(chart["sha256"])
            questions = {}
            for subject in SUBJECTS:
                authority = self.target_authority.v3_inputs(subject, now)
                b = {"subject": subject, "canonical_subject": CANONICAL[subject],
                    "cycle_id": self.workflow._cycle(selection),
                    "commodity_chart": binding(cards[subject]), "macro_chart": binding(cards["GLOBAL_MACRO"]),
                    "methodology": method["descriptor"], "target_authority": authority["target_authority"]}
                inputs = {"binding": b, "targets": authority["targets"],
                    "authority_valid_through": authority["authority_valid_through"],
                    "methodology_instructions": method["instructions"], "synthetic": self.workflow.qualification_mode}
                prior = old.get(subject)
                if prior and all(prior[k] == v for k, v in inputs.items()) and self._current_inputs(prior, selection, now):
                    require(stamp(prior["information_cutoff"]) <= now, "THETA_TIMESTAMP_INVALID")
                    questions[subject] = prior  # Preserve this child's original T0.
                else:
                    questions[subject] = make_question_v3(**inputs, created_at=now.isoformat())
            batch = make_question_batch_v3(questions)
        # Existing TE-04B seams acquire their own lock (never nest flock).
        self.intake.retain_question_batch(batch, questions)
        identity = batch["batch_id"]
        with self.store.transaction():
            record = self.intake._optional("question-transports", identity + ".json")
        if record is None:
            payload = transport_v3(batch, questions, charts, originals)
            filename = ("SYNTHETIC_" if batch["synthetic"] else "") + "THETA_" + batch["cycle_id"][4:20] + "_" + identity[4:] + "_ASTRA_ULTRA_QUESTION_PACK.zip"
            record = {"batch_id": identity, "filename": filename, "zip_sha256": digest(payload)}
        else:
            require(record["batch_id"] == identity, "THETA_INTEGRITY_INVALID")
            payload = self.store.load_blob(record["zip_sha256"])
        with self.store.transaction():
            current = self.store.current()
            require(all(self._current_inputs(q, current, self.workflow.now()) for q in questions.values()),
                    "THETA_INTAKE_BINDING_STALE")
            with directory(self.workflow.outbox, create=True) as fd:
                write_at(fd, record["filename"], payload)
                require(read_at(fd, record["filename"]) == payload, "THETA_INTEGRITY_INVALID")
            require(self.store.blob(payload) == record["zip_sha256"], "THETA_INTEGRITY_INVALID")
            self.store.retain("v3-question-transports", identity + ".json", sealed(record))
        # A concurrent chart replacement fails this final admission, not silently
        # publishing a stale selection. Intact earlier output remains historical.
        self.intake.select_question_batch(identity)
        return {**record, "complete": True, "questions": {s: q["question_id"] for s, q in questions.items()}}

    def selected(self):
        """Read currentness; no publication, acceptance, re-T0 or selection write."""
        with self.store.transaction():
            selection = self.store.current()
            identity = selection.get("v3_question_batch")
            if not identity:
                return None
            batch, questions = self.intake._batch(identity)
            record = unseal(self.store.load("v3-question-transports", identity + ".json"))
            require(record["batch_id"] == identity, "THETA_INTEGRITY_INVALID")
            self.store.load_blob(record["zip_sha256"])
            current = {s: self.intake._currentness(q, selection, self.workflow.now()) for s, q in questions.items()}
            for s, q in questions.items():
                if current[s] == "CURRENT" and not self._current_inputs(q, selection, self.workflow.now()):
                    current[s] = "STALE"
            return {**record, "current": all(v == "CURRENT" for v in current.values()), "currentness": current}
