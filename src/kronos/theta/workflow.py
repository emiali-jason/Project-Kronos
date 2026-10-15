"""Bounded manual workflow. No network, provider, forecast or trading capability."""

from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from reportlab.lib.utils import ImageReader

from kronos.theta.contracts import (
    AuthorityBundle, CANONICAL, INSTRUCTIONS, QUESTION_SCHEMA, SUBJECTS, VERSION,
    ThetaError, digest, encode, require, stamp, text, validate_answer,
)
from kronos.theta.store import (
    DEFAULT_INBOX, DEFAULT_OUTBOX, ThetaStore, directory, read_at, sealed, unseal, write_at,
)
from kronos.theta.transport import render_transport

MAX_CHART_BYTES = 16 * 1024 * 1024
CHART_ROLES = (*SUBJECTS, "GLOBAL_MACRO")


class ThetaWorkflow:
    """Authority provider is an explicit uncommissioned dependency in V1 candidate.

    It must consume approved Instrument/Market target evidence and applicable
    methodology. Default has no authority; neither Analyst nor Browser can
    self-enrol a mapping. Synthetic adapters prove mechanics only.
    """

    def __init__(self, store=None, *, inbox=DEFAULT_INBOX, outbox=DEFAULT_OUTBOX,
                 authority_provider=None, clock=None, qualification_mode=False):
        self.store = ThetaStore() if store is None else store
        self.inbox, self.outbox = inbox, outbox
        self.authority_provider = authority_provider
        require(type(qualification_mode) is bool)
        self.qualification_mode = qualification_mode
        self.clock = clock or (lambda: datetime.now(UTC))

    def now(self):
        result = self.clock()
        require(type(result) is datetime and result.tzinfo is not None
                and result.utcoffset() is not None, "THETA_CLOCK_INVALID")
        return result

    def intake_chart(self, *, subject: str, label: str, media_type: str,
                     information_cutoff: str, payload: bytes,
                     expected_cycle_id=None, expected_revision_id=...,
                     cutoff_basis="SPONSOR_DECLARED") -> str:
        now = self.now()
        require(subject in CHART_ROLES and text(label, 512), "THETA_CHART_INVALID")
        require(cutoff_basis in {"SPONSOR_DECLARED", "INTAKE_RECEIPT_NOT_CHART_TIME"})
        require(stamp(information_cutoff) <= now, "THETA_TIMESTAMP_INVALID")
        signatures = {"image/png": b"\x89PNG\r\n\x1a\n", "image/jpeg": b"\xff\xd8\xff"}
        require(media_type in signatures and type(payload) is bytes
                and 0 < len(payload) <= MAX_CHART_BYTES
                and payload.startswith(signatures[media_type]), "THETA_CHART_INVALID")
        try:
            image = ImageReader(BytesIO(payload))
            width, height = image.getSize()
            require(0 < width * height <= 40_000_000, "THETA_CHART_INVALID")
            image.getRGBData()
        except Exception:
            raise ThetaError("THETA_CHART_INVALID") from None
        # The declaration is not presented as verified visual correspondence.
        core = {"subject": subject, "canonical_subject": CANONICAL.get(subject),
                "label": label, "media_type": media_type,
                "information_cutoff": information_cutoff, "sha256": digest(payload)}
        identity = "TEC-" + digest(encode(core))
        with self.store.transaction():
            selection = self.store.current()
            cycle = self._cycle(selection)
            current = (selection.get("macro") if subject == "GLOBAL_MACRO"
                       else selection["subjects"].get(subject))
            if current is not None:
                self._role_chart(selection, subject)
            selected_revision = None if current is None else current.get("revision_id", current["chart_id"])
            require(expected_cycle_id is None or expected_cycle_id == (cycle or "UNSTARTED"),
                    "THETA_CHART_BINDING_STALE")
            require(expected_revision_id is ... or expected_revision_id == selected_revision,
                    "THETA_CHART_BINDING_STALE")
            if current and current["chart_id"] == identity and current.get("revision_id"):
                return identity
            if cycle is None:
                cycle_core = {"created_at": now.isoformat(), "nonce": uuid4().hex}
                cycle = "TAC-" + digest(encode(cycle_core))
                self.store.retain("cycles", cycle + ".json", sealed(cycle_core))
                selection["cycle_id"] = cycle
            self.store.blob(payload)
            self.store.retain("charts", identity + ".json", sealed(core))
            revision = {"cycle_id": cycle, "role": "GLOBAL_MACRO" if subject == "GLOBAL_MACRO" else "COMMODITY_COMPOSITE",
                        "subject": None if subject == "GLOBAL_MACRO" else subject,
                        "chart_id": identity, "accepted_at": now.isoformat(),
                        "media_type": media_type, "byte_length": len(payload), "sha256": digest(payload),
                        "cutoff_basis": cutoff_basis, "previous_revision_id": selected_revision}
            revision_id = "TCR-" + digest(encode(revision))
            self.store.retain("chart-revisions", revision_id + ".json", sealed(revision))
            entry = {"chart_id": identity, "revision_id": revision_id}
            if subject == "GLOBAL_MACRO":
                selection["macro"] = entry
            else:
                selection["subjects"][subject] = {**entry, "question_id": None}
            self.store.select(selection)
        return identity

    def _cycle(self, selection):
        identity = selection.get("cycle_id")
        if identity is not None:
            require(type(identity) is str and identity.startswith("TAC-"), "THETA_INTEGRITY_INVALID")
            core = unseal(self.store.load("cycles", identity + ".json"))
            require(identity == "TAC-" + digest(encode(core)), "THETA_INTEGRITY_INVALID")
            stamp(core["created_at"])
        return identity

    def _role_chart(self, selection, subject):
        cycle = self._cycle(selection)
        entry = selection.get("macro") if subject == "GLOBAL_MACRO" else selection["subjects"].get(subject)
        result = {"subject": subject, "cycle_id": cycle, "chart_id": None,
                  "revision_id": None, "chart": None, "intake": None}
        if entry is None:
            return result
        chart = self.store.chart(entry["chart_id"])
        require(chart["subject"] == subject and chart["canonical_subject"] == CANONICAL.get(subject),
                "THETA_INTEGRITY_INVALID")
        revision_id = entry.get("revision_id")
        if revision_id:
            revision = unseal(self.store.load("chart-revisions", revision_id + ".json"))
            require(revision_id == "TCR-" + digest(encode(revision))
                    and revision["cycle_id"] == cycle and revision["chart_id"] == entry["chart_id"]
                    and revision["sha256"] == chart["sha256"] and revision["media_type"] == chart["media_type"]
                    and revision["subject"] == (None if subject == "GLOBAL_MACRO" else subject)
                    and revision["role"] == ("GLOBAL_MACRO" if subject == "GLOBAL_MACRO" else "COMMODITY_COMPOSITE")
                    and revision["byte_length"] == len(self.store.load_blob(chart["sha256"])),
                    "THETA_INTEGRITY_INVALID")
            stamp(revision["accepted_at"])
            result["intake"] = revision
        # Older accepted chart records remain readable, never retroactively
        # assigned an intake time or cycle. Explicit replacement binds a new revision.
        result.update(chart_id=entry["chart_id"], revision_id=revision_id or entry["chart_id"], chart=chart)
        return result

    def chart_workspace(self):
        with self.store.transaction():
            selection = self.store.current()
            return {"cycle_id": self._cycle(selection),
                    "cards": [self._role_chart(selection, subject) for subject in CHART_ROLES]}

    def preview_chart(self, *, subject, cycle_id, revision_id):
        require(subject in CHART_ROLES, "THETA_CHART_INVALID")
        with self.store.transaction():
            state = self._role_chart(self.store.current(), subject)
            require(state["chart"] is not None and (state["cycle_id"] or "UNSTARTED") == cycle_id
                    and state["revision_id"] == revision_id, "THETA_CHART_BINDING_STALE")
            return state["chart"]["media_type"], self.store.load_blob(state["chart"]["sha256"])

    def create_question(self, subjects: tuple[str, ...]) -> str:
        """Retained V1 compatibility seam; new Sponsor commissioning uses TE-02 packs."""
        require(type(subjects) is tuple and bool(subjects) and len(subjects) <= 5
                and len(set(subjects)) == len(subjects) and all(s in SUBJECTS for s in subjects))
        subjects = tuple(s for s in SUBJECTS if s in subjects)
        now = self.now()
        require(callable(self.authority_provider), "THETA_TARGET_AND_METHODOLOGY_NOT_ESTABLISHED")
        try:
            authority = self.authority_provider(subjects, now)
        except Exception:
            # Owner-domain failures stay unavailable; never echo private adapter
            # exception detail into Browser responses or Analyst artifacts.
            raise ThetaError("THETA_TARGET_AUTHORITY_UNAVAILABLE") from None
        require(type(authority) is AuthorityBundle, "THETA_TARGET_AUTHORITY_UNAVAILABLE")
        targets = authority.for_subjects(subjects, now)
        with self.store.transaction():
            selection = self.store.current()
            charts = []
            for subject in subjects:
                entry = selection["subjects"].get(subject)
                require(entry is not None, "THETA_CHART_REQUIRED")
                chart = self._role_chart(selection, subject)["chart"]
                require(chart["subject"] == subject, "THETA_INTEGRITY_INVALID")
                charts.append(chart)
            core = {"schema_identity": QUESTION_SCHEMA, "schema_version": VERSION,
                    "created_at": now.isoformat(), "subjects": list(subjects), "charts": charts,
                    "targets": targets, "methodology_reference": authority.methodology_reference,
                    "methodology_instructions": authority.methodology_instructions,
                    "authority_valid_through": authority.valid_through,
                    "instructions": list(INSTRUCTIONS)}
            identity = "TEQ-" + digest(encode(core))
            question = {**core, "question_id": identity}
            binary = {chart["sha256"]: self.store.load_blob(chart["sha256"]) for chart in charts}
            try:
                pdf, archive = render_transport(question, binary)
            except Exception:
                raise ThetaError("THETA_QUESTION_RENDER_INVALID") from None
            self.store.retain("questions", identity + ".json", sealed(question))
            transport = {"question_id": identity, "pdf_sha256": self.store.blob(pdf),
                         "zip_sha256": self.store.blob(archive)}
            self.store.retain("transports", identity + ".json", sealed(transport))
            # Outbox readback precedes selection; export failure never currentizes.
            with directory(self.outbox, create=True) as fd:
                write_at(fd, identity + "_QUESTIONS.zip", archive)
            with directory(self.inbox, create=True):
                pass
            for subject in subjects:
                selection["subjects"][subject]["question_id"] = identity
            self.store.select(selection)
            return identity

    def commission_questions(self, subjects):
        from kronos.theta.packs import QuestionPacks
        return QuestionPacks(self).create(subjects)

    def question_batch(self):
        from kronos.theta.packs import QuestionPacks
        return QuestionPacks(self).selected_batch()

    def transport_filename(self, identity, kind):
        from kronos.theta.packs import QuestionPacks
        if identity.startswith("TEB-"):
            require(kind=="zip")
            return QuestionPacks(self).batch(identity)["filename"]
        with self.store.transaction():
            self.store.question(identity)
            record=unseal(self.store.load("transports",identity+".json"))
            return record.get("filenames",{}).get(kind,identity+"_QUESTIONS."+kind)

    def transport(self, identity: str, kind: str) -> bytes:
        require(kind in {"pdf", "zip", "template"})
        if identity.startswith("TEB-"):
            from kronos.theta.packs import QuestionPacks
            require(kind=="zip")
            with self.store.transaction():
                return self.store.load_blob(QuestionPacks(self).batch(identity)["zip_sha256"])
        with self.store.transaction():
            self.store.question(identity)
            record = unseal(self.store.load("transports", identity + ".json"))
            require(record["question_id"] == identity, "THETA_INTEGRITY_INVALID")
            return self.store.load_blob(record[kind + "_sha256"])

    def import_answer(self, identity: str) -> str:
        """Read exactly the expected local filename. Never delete/rewrite inbox bytes."""
        now = self.now()
        with self.store.transaction():
            question = self.store.question(identity)
            with directory(self.inbox) as fd:
                payload = read_at(fd, identity + "_ANSWERS.json", 2 * 1024 * 1024)
            raw_hash = digest(payload)
            try:
                existing = unseal(self.store.load("accepted", identity + ".json"))
            except FileNotFoundError:
                existing = None
            if existing is not None:
                require(existing["answer_sha256"] == raw_hash, "THETA_ANSWER_CONFLICT")
                # Exact replay validates the original acceptance, not a new T0.
                # It never reselects a superseded/expired historical Question.
                self._detail(identity)
                return raw_hash
            value = validate_answer(payload, question, received_at=now)
            selection = self.store.current()
            from kronos.theta.packs import current_binding
            require(all(current_binding(self,question,selection,s) for s in question["subjects"]),
                    "THETA_QUESTION_SUPERSEDED")
            require(all(selection["subjects"].get(s, {}).get("question_id") == identity
                        for s in question["subjects"]), "THETA_QUESTION_SUPERSEDED")
            require(now <= stamp(question["authority_valid_through"]), "THETA_TARGET_AUTHORITY_STALE")
            # Global Answer identity cannot refer to different bytes or a second Question.
            self.store.retain("answer-identities", value["answer_id"] + ".json",
                              sealed({"answer_sha256": raw_hash, "question_id": identity}))
            self.store.blob(payload)
            receipt = {"question_id": identity, "answer_sha256": raw_hash,
                       "answer_id": value["answer_id"], "accepted_at": now.isoformat(),
                       "question_sha256": digest(encode(question))}
            # This receipt is the acceptance commit point; all dependencies precede it.
            self.store.retain("accepted", identity + ".json", sealed(receipt))
            return raw_hash

    def _detail(self, identity: str) -> dict:
        question = self.store.question(identity)
        receipt = unseal(self.store.load("accepted", identity + ".json"))
        require(receipt["question_id"] == identity
                and receipt["question_sha256"] == digest(encode(question)), "THETA_INTEGRITY_INVALID")
        raw = self.store.load_blob(receipt["answer_sha256"])
        answer = validate_answer(raw, question, received_at=stamp(receipt["accepted_at"]))
        require(answer["answer_id"] == receipt["answer_id"], "THETA_INTEGRITY_INVALID")
        retained_identity = unseal(self.store.load("answer-identities", answer["answer_id"] + ".json"))
        require(retained_identity == {"answer_sha256": receipt["answer_sha256"], "question_id": identity},
                "THETA_INTEGRITY_INVALID")
        return {"question": question, "receipt": receipt, "answer": answer}

    def detail(self, identity: str) -> dict:
        with self.store.transaction():
            result = self._detail(identity)
            selection = self.store.current()
            from kronos.theta.packs import current_binding
            result["current_subjects"] = [s for s in result["question"]["subjects"]
                if selection["subjects"].get(s, {}).get("question_id") == identity
                and current_binding(self,result["question"],selection,s)
                and self.now() <= stamp(result["question"]["authority_valid_through"])
                and self.now() < min(stamp(t["expires_at"]) for t in result["question"]["targets"]
                    if t["subject"] == s)]
            return result

    def summary(self) -> list[dict]:
        rows = []
        with self.store.transaction():
            selection = self.store.current()
            for subject in SUBJECTS:
                row = {"subject": subject, "canonical_subject": CANONICAL[subject],
                       "status": "CHART_REQUIRED", "forecasts": []}
                current = selection["subjects"].get(subject)
                if current:
                    row.update(current)
                    chart = self._role_chart(selection, subject)["chart"]
                    require(chart["subject"] == subject and chart["canonical_subject"] == CANONICAL[subject],
                            "THETA_INTEGRITY_INVALID")
                    self.store.load_blob(chart["sha256"])
                    row["status"] = ("CHART_READY" if callable(self.authority_provider)
                                     else "TARGET_AND_METHODOLOGY_NOT_ESTABLISHED")
                    if current["question_id"]:
                        question = self.store.question(current["question_id"])
                        require(subject in question["subjects"] and chart in question["charts"],
                                "THETA_INTEGRITY_INVALID")
                        from kronos.theta.packs import current_binding
                        if not current_binding(self,question,selection,subject):
                            row.update(status="QUESTION_INPUT_CHANGED",forecasts=[])
                            rows.append(row)
                            continue
                        row["targets"] = [t for t in question["targets"] if t["subject"] == subject]
                        try:
                            detail = self._detail(current["question_id"])
                        except FileNotFoundError:
                            # Missing accepted receipt is pending; missing an accepted
                            # dependency is corruption, not a reason to fall back.
                            try:
                                self.store.load("accepted", current["question_id"] + ".json")
                            except FileNotFoundError:
                                row["status"] = "ANSWER_PENDING"
                            else:
                                raise ThetaError("THETA_INTEGRITY_INVALID") from None
                        else:
                            row.update(status="ACCEPTED_EXTERNAL_EVIDENCE",
                                       analyzed_at=detail["answer"]["analyzed_at"],
                                       forecasts=[f for f in detail["answer"]["forecasts"]
                                                  if f["target"]["subject"] == subject])
                        if any(self.now() >= stamp(t["expires_at"]) for t in row["targets"]):
                            row["status"] = "EXPIRED_HISTORICAL_ONLY"
                            row["forecasts"] = []
                        elif self.now() > stamp(question["authority_valid_through"]):
                            row["status"] = "TARGET_AUTHORITY_STALE / HISTORICAL_ONLY"
                            row["forecasts"] = []
                rows.append(row)
        return rows

    def chart_bytes(self, sha256: str) -> bytes:
        with self.store.transaction():
            return self.store.load_blob(sha256)

    def append_outcome(self, identity: str, *, target: dict, terminal: str,
                       observed_at: str, authority_reference: str) -> str:
        """Explicit owner evidence only; no acquisition or automatic evaluation.

        Separate appended research bytes, never a forecast/receipt/pointer update.
        This is not a Sponsor-facing outcome API or broker/exercise result.
        """
        from kronos.theta.contracts import decimal
        now = self.now()
        with self.store.transaction():
            detail = self._detail(identity)
            matches = [f for f in detail["answer"]["forecasts"] if f["target"] == target]
            require(len(matches) == 1 and text(authority_reference, 1024), "THETA_OUTCOME_INVALID")
            require(stamp(target["expires_at"]) <= stamp(observed_at) <= now, "THETA_OUTCOME_INVALID")
            forecast = matches[0]
            contained = decimal(forecast["lower"]) <= decimal(terminal) <= decimal(forecast["upper"])
            record = {"question_id": identity, "answer_sha256": detail["receipt"]["answer_sha256"],
                      "target": target, "terminal": terminal, "observed_at": observed_at,
                      "authority_reference": authority_reference, "classification": "RESEARCH_RESULT",
                      "result": "TERMINAL_CONTAINMENT_PASS" if contained else "TERMINAL_CONTAINMENT_FAIL"}
            outcome_id = digest(encode(record))
            self.store.retain("outcomes", outcome_id + ".json", sealed(record))
            return outcome_id
