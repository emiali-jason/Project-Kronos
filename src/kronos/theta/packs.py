"""TE-02 commissioning: canonical individual Questions, convenience batch only."""

from kronos.theta.contracts import (AuthorityBundle, ANSWER_SCHEMA, PROSPECTIVE_VERSION,
    QUESTION_SCHEMA, SUBJECTS, ThetaError, digest, encode, require, stamp)
from kronos.theta.question_pack import (combined_transport, instructions, pack_name,
                                       render_transport)
from kronos.theta.store import directory, read_at, sealed, unseal, write_at


def binding(card):
    require(card["chart"] is not None and card["intake"] is not None,
            "THETA_CHART_REQUIRED")
    return {key: card[key] for key in ("subject", "cycle_id", "chart_id", "revision_id")} | {
        "sha256": card["chart"]["sha256"]}


def current_binding(workflow, question, selection, subject):
    if question.get("schema_version") != PROSPECTIVE_VERSION:
        return True  # Preserve historical V1 selection/acceptance semantics.
    commodity = workflow._role_chart(selection, subject)
    macro = workflow._role_chart(selection, "GLOBAL_MACRO")
    return (question["cycle_id"] == workflow._cycle(selection)
            and question["chart_bindings"] == [binding(commodity), binding(macro)])


class QuestionPacks:
    def __init__(self, workflow):
        self.workflow = workflow
        self.store = workflow.store

    def _one(self, subject, now):
        workflow = self.workflow
        require(callable(workflow.authority_provider), "THETA_TARGET_AND_METHODOLOGY_NOT_ESTABLISHED")
        try:
            authority = workflow.authority_provider((subject,), now)
        except ThetaError as error:
            if str(error) in {"THETA_METHODOLOGY_UNAVAILABLE", "THETA_TARGET_OWNER_QUALIFICATION_REQUIRED"}:
                raise
            raise ThetaError("THETA_TARGET_AUTHORITY_UNAVAILABLE") from None
        except Exception:
            raise ThetaError("THETA_TARGET_AUTHORITY_UNAVAILABLE") from None
        require(type(authority) is AuthorityBundle, "THETA_TARGET_AUTHORITY_UNAVAILABLE")
        targets = authority.for_subjects((subject,), now)
        synthetic = workflow.qualification_mode
        require(synthetic or not any("SYNTHETIC" in str(value).upper()
                for target in targets for value in target.values()), "THETA_SYNTHETIC_AUTHORITY_FORBIDDEN")
        with self.store.transaction():
            selection = self.store.current()
            commodity = workflow._role_chart(selection, subject)
            macro = workflow._role_chart(selection, "GLOBAL_MACRO")
            require(macro["chart"] is not None, "THETA_MACRO_REQUIRED")
            bindings = [binding(commodity), binding(macro)]
            require(stamp(commodity["chart"]["information_cutoff"]) <= now
                    and stamp(macro["chart"]["information_cutoff"]) <= now,
                    "THETA_TIMESTAMP_INVALID")
            inputs = {"schema_identity": QUESTION_SCHEMA, "schema_version": PROSPECTIVE_VERSION,
                      "subjects": [subject], "charts": [commodity["chart"]], "macro_chart": macro["chart"],
                      "cycle_id": commodity["cycle_id"], "chart_bindings": bindings,
                      "targets": targets, "methodology_reference": authority.methodology_reference,
                      "methodology_instructions": authority.methodology_instructions,
                      "authority_valid_through": authority.valid_through,
                      "answer_schema_identity": ANSWER_SCHEMA, "answer_schema_version": PROSPECTIVE_VERSION,
                      "instructions": instructions(subject), "synthetic": synthetic}
            selected = selection["subjects"][subject].get("question_id")
            question = self.store.question(selected) if selected else None
            if question is None or any(question.get(key) != value for key,value in inputs.items()):
                core = {**inputs, "created_at":now.isoformat(), "information_cutoff":now.isoformat()}
                identity = "TEQ-" + digest(encode(core))
                question = {**core, "question_id":identity}
                binary = {c["sha256"]:self.store.load_blob(c["sha256"])
                          for c in [commodity["chart"], macro["chart"]]}
                try:
                    pdf, archive, template = render_transport(question, binary)
                except Exception:
                    raise ThetaError("THETA_QUESTION_RENDER_INVALID") from None
                self.store.retain("questions",identity+".json",sealed(question))
                transport = {"question_id":identity, "pdf_sha256":self.store.blob(pdf),
                             "zip_sha256":self.store.blob(archive), "template_sha256":self.store.blob(template),
                             "filenames":{kind:pack_name(question,kind) for kind in ("pdf","zip","template")}}
                self.store.retain("transports",identity+".json",sealed(transport))
            else:
                identity = question["question_id"]
                transport = unseal(self.store.load("transports",identity+".json"))
            require(transport["question_id"]==identity,"THETA_INTEGRITY_INVALID")
            outputs = {transport["filenames"][kind]:self.store.load_blob(transport[kind+"_sha256"])
                       for kind in ("pdf","zip","template")}
            # Preflight every existing name before publishing any new output.
            with directory(workflow.outbox,create=True) as fd:
                for name,payload in outputs.items():
                    try:
                        require(read_at(fd,name)==payload,"THETA_IMMUTABLE_CONFLICT")
                    except FileNotFoundError:
                        pass
                for name,payload in outputs.items():
                    write_at(fd,name,payload)
                    require(read_at(fd,name)==payload,"THETA_INTEGRITY_INVALID")
            selection["subjects"][subject]["question_id"] = identity
            self.store.select(selection)
            return identity

    def create(self, subjects):
        require(type(subjects) is tuple and bool(subjects) and len(set(subjects))==len(subjects)
                and all(s in SUBJECTS for s in subjects))
        subjects = tuple(s for s in SUBJECTS if s in subjects)
        now = self.workflow.now()
        states = {}
        for subject in subjects:
            try:
                identity = self._one(subject,now)
                states[subject] = {"status":"READY", "question_id":identity}
            except (OSError,ValueError,KeyError,TypeError) as error:
                states[subject] = {"status":"BLOCKED", "failure":str(error) if type(error) is ThetaError else "THETA_LOCAL_FILE_UNAVAILABLE"}
        result = {"states":states, "batch_id":None, "complete":False}
        ready = {s:v["question_id"] for s,v in states.items() if v["status"]=="READY"}
        if not ready:
            return result
        with self.store.transaction():
            selection = self.store.current()
            questions = {s:self.store.question(identity) for s,identity in ready.items()}
            require(all(current_binding(self.workflow,q,selection,s) for s,q in questions.items()),
                    "THETA_CHART_BINDING_STALE")
            first = next(iter(questions.values()))
            core = {"schema_identity":"KRONOS-THETA-TRANSPORT-V1", "schema_version":"1.0.0",
                    "cycle_id":first["cycle_id"], "subjects":list(subjects), "states":states,
                    "complete":tuple(ready)==SUBJECTS and len(ready)==len(subjects),
                    "synthetic":first["synthetic"], "macro_chart":first["macro_chart"]}
            identity = "TEB-"+digest(encode(core))
            batch = {**core,"batch_id":identity}
            packs = {}
            for subject,q in questions.items():
                transport=unseal(self.store.load("transports",q["question_id"]+".json"))
                packs[subject] = (q,self.store.load_blob(transport["pdf_sha256"]),
                                  self.store.load_blob(transport["template_sha256"]),
                                  self.store.load_blob(q["charts"][0]["sha256"]))
            archive = combined_transport(batch,packs,(first["macro_chart"],self.store.load_blob(first["macro_chart"]["sha256"])))
            filename = ("SYNTHETIC_" if first["synthetic"] else "")+"THETA_"+first["cycle_id"][4:20]+"_"+identity[4:]+("_ASTRA_ULTRA_QUESTION_PACK.zip" if core["complete"] else "_ASTRA_ULTRA_PARTIAL_PACK.zip")
            record = {"batch":batch,"zip_sha256":self.store.blob(archive),"filename":filename}
            with directory(self.workflow.outbox,create=True) as fd:
                write_at(fd,filename,archive)
                require(read_at(fd,filename)==archive,"THETA_INTEGRITY_INVALID")
            self.store.retain("batches",identity+".json",sealed(record))
            self.store.select({**selection,"question_batch":identity})
            return {**result,"batch_id":identity,"complete":core["complete"]}

    def batch(self, identity):
        require(type(identity) is str and identity.startswith("TEB-") and len(identity)==68)
        record = unseal(self.store.load("batches",identity+".json"))
        core = {k:v for k,v in record["batch"].items() if k!="batch_id"}
        require(record["batch"]["batch_id"]==identity and identity=="TEB-"+digest(encode(core)),"THETA_INTEGRITY_INVALID")
        self.store.load_blob(record["zip_sha256"])
        for state in record["batch"]["states"].values():
            if state["status"]=="READY":
                self.store.question(state["question_id"])
        return record

    def selected_batch(self):
        with self.store.transaction():
            selection = self.store.current()
            identity = selection.get("question_batch")
            if not identity:
                return None
            record = self.batch(identity)
            record["current"] = all(selection["subjects"].get(s,{}).get("question_id")==state["question_id"]
                and current_binding(self.workflow,self.store.question(state["question_id"]),selection,s)
                for s,state in record["batch"]["states"].items() if state["status"]=="READY")
            return record
