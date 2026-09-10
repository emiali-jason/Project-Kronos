"""ADR-0036 ordered Sponsor transport; existing candidate engines own acceptance."""
from dataclasses import dataclass, replace
from hashlib import sha256
import json
from pathlib import Path

from kronos.intraday.review import ReviewError, ReviewFailure
from kronos.intraday.review_answer import MAX_ANSWER_BYTES
from kronos.intraday.review_v2_transport import visual_review_entry, _retain
from kronos.intraday.review_mcx_paired_transport import paired_visual_entry
from kronos.intraday.visual_review_pdf import render_visual_review
from kronos.instrument.visual_identity import uses_family_visual_authority

SCHEMA = "KRONOS-INTRADAY-ORDERED-BATCH-ANSWER-V1"
VERSION = "1.0.0"
BINDINGS = ("canonical_subject_identity", "review_cycle_identity", "chart_revision_identity",
            "review_pack_identity", "candidate_kind")


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def decode(payload):
    try:
        return json.loads(payload, object_pairs_hook=_unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non-JSON number")))
    except (ValueError, TypeError, UnicodeDecodeError, RecursionError) as error:
        raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID) from error


@dataclass(frozen=True)
class OrderedBatchTransport:
    transport_identity: str
    question_filename: str
    expected_answer_filename: str


@dataclass(frozen=True)
class OrderedBatchResult:
    transport: OrderedBatchTransport
    question_path: Path
    answer_template_path: Path


def _context(app, pointer):
    charts = []
    for member in pointer.cycles:
        active = app._review.load_current_chart(member.cycle_identity)
        if active is None:
            raise ReviewError(ReviewFailure.CHART_REQUIRED)
        chart = app._review.load_chart(active.chart_revision_identity)
        app._review.load_chart_bytes(chart)
        charts.append(chart)
    return charts


def _root(app):
    return app._review.root / "ordered-batches"


def _pointer_path(app, pointer):
    return _root(app) / "current" / (pointer.integrity_identity + ".json")


def _identity(core):
    return "INTRADAY-ORDERED-BATCH-" + sha256(encode(core)).hexdigest().upper()


def _transport(identity):
    suffix = identity.removeprefix("INTRADAY-ORDERED-BATCH-")
    if len(suffix) != 64 or any(c not in "0123456789ABCDEF" for c in suffix):
        raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
    stem = "KRONOS_INTRADAY_ORDERED_BATCH_" + suffix
    return OrderedBatchTransport(identity, stem + "_QUESTIONS.pdf", stem + "_ANSWERS.json")


def load(app, pointer, *, require_current=True):
    path = _pointer_path(app, pointer)
    if not path.exists():
        return None
    try:
        identity = decode(path.read_bytes())["identity"]
        transport = _transport(identity)
        folder = _root(app) / identity
        manifest = decode((folder / "manifest.json").read_bytes())
        if _identity(manifest["core"]) != identity:
            raise ValueError
        core = manifest["core"]
        if (core["pointer"] != pointer.integrity_identity or core["run"] != pointer.probables_run_identity
            or core["version"] != VERSION or len(core["members"]) != len(pointer.cycles)):
            raise ValueError
        for member, bound in zip(pointer.cycles, core["members"], strict=True):
            if (member.cycle_identity != bound["review_cycle_identity"]
                or member.canonical_subject_identity != bound["canonical_subject_identity"]):
                raise ValueError
            if require_current:
                active = app._review.load_current_chart(member.cycle_identity)
                if active is None or active.chart_revision_identity != bound["chart_revision_identity"]:
                    raise ReviewError(ReviewFailure.NOT_CURRENT)
        for name in ("question.pdf", "template.json"):
            if sha256((folder / name).read_bytes()).hexdigest() != manifest[name]:
                raise ValueError
        return manifest, transport, folder
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise ReviewError(ReviewFailure.INTEGRITY_INVALID) from error


def create(app):
    with app._lock, app._probables.current_generation_guard():
        pointer = app._require_current_workspace()
        if pointer is None or not pointer.cycles:
            raise ReviewError(ReviewFailure.NOT_CURRENT)
        charts = _context(app, pointer)  # All charts before any export.
        members, documents, entries, flags = [], [], [], []
        for member, chart in zip(pointer.cycles, charts, strict=True):
            cycle = app._review.load_cycle(member.cycle_identity)
            paired = cycle.canonical_subject_identity.startswith("MCX-SUBJECT-")
            payload = app._review.load_chart_bytes(chart)
            if paired:
                result = app._paired.create(cycle, chart, export=False,
                    require_current=lambda: app._require_current_workspace(cycle.probables_run_identity, cycle.cycle_identity))
                bundle, _, _, pack, _, _, _ = app._paired.retained(cycle, chart)
                doc = decode(result.answer_template_path.read_bytes())
                entry = paired_visual_entry(pack, bundle, payload, payload,
                    family_visual=uses_family_visual_authority(app._paired.native_resolver))
            else:
                pack = app._current_pack(cycle.cycle_identity, require_retained=False)
                result = app._create_question_transport(((pack, payload),), export=False)
                doc = decode(result.answer_template_path.read_bytes())["candidates"][0]
                entry = visual_review_entry(pack, payload)
            bound = dict(canonical_subject_identity=cycle.canonical_subject_identity,
                review_cycle_identity=cycle.cycle_identity, chart_revision_identity=chart.chart_revision_identity,
                review_pack_identity=pack.review_pack_identity, candidate_kind="MCX_PAIRED" if paired else "NSE",
                transport_identity=result.transport.transport_identity)
            members.append(bound)
            documents.append({**{k: bound[k] for k in BINDINGS}, "global_observation_status": "INVALID", "answer": doc})
            orientation, images, questions = entry
            entries.append((orientation + ("Review cycle: " + cycle.cycle_identity,
                "Review Pack: " + pack.review_pack_identity, "Workspace chart revision: " + chart.chart_revision_identity), images, questions))
            flags.append(paired)
        core = dict(version=VERSION, pointer=pointer.integrity_identity, run=pointer.probables_run_identity, members=members)
        identity = _identity(core)
        transport = _transport(identity)
        folder = _root(app) / identity
        template = encode(dict(schema_identity=SCHEMA, schema_version=VERSION, batch_identity=identity,
            review_pointer_identity=pointer.integrity_identity, probables_run_identity=pointer.probables_run_identity,
            candidates=documents))
        manifest_path = folder / "manifest.json"
        if manifest_path.exists():
            manifest = decode(manifest_path.read_bytes())
            pdf = (folder / "question.pdf").read_bytes()
            if (manifest["core"] != core or (folder / "template.json").read_bytes() != template
                or manifest["question.pdf"] != sha256(pdf).hexdigest()
                or manifest["template.json"] != sha256(template).hexdigest()):
                raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        else:
            pdf = render_visual_review(tuple(entries), expected_filename=transport.expected_answer_filename,
                answer_template=template, paired_flags=tuple(flags))
            manifest = {"core": core, "question.pdf": sha256(pdf).hexdigest(), "template.json": sha256(template).hexdigest()}
            for name, data in (("question.pdf", pdf), ("template.json", template), ("manifest.json", encode(manifest))):
                app._review._retain(folder / name, data)
        app._require_current_workspace(pointer.probables_run_identity)
        if _context(app, pointer) != charts:
            raise ReviewError(ReviewFailure.NOT_CURRENT)
        # Publish one exact commission pointer and one Sponsor PDF. No JSON export.
        app._review._replace(_pointer_path(app, pointer), encode({"identity": identity}))
        app._transport.question_outbox.mkdir(parents=True, exist_ok=True)
        app._transport.answer_inbox.mkdir(parents=True, exist_ok=True)
        question = _retain(app._transport.question_outbox / transport.question_filename, pdf)
        return OrderedBatchResult(transport, question, folder / "template.json")


def validate_envelope(document, template):
    if type(document) is not dict or set(document) != set(template):
        raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
    if any(document[k] != template[k] for k in template if k != "candidates"):
        raise ReviewError(ReviewFailure.ANSWER_IDENTITY_MISMATCH)
    supplied = document["candidates"]
    if type(supplied) is not list or len(supplied) != len(template["candidates"]):
        raise ReviewError(ReviewFailure.ANSWER_IDENTITY_MISMATCH)
    for actual, expected in zip(supplied, template["candidates"], strict=True):
        if type(actual) is not dict or set(actual) != set(expected):
            raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
        if any(actual[k] != expected[k] for k in BINDINGS):
            raise ReviewError(ReviewFailure.ANSWER_IDENTITY_MISMATCH)
        # Preflight nested bindings too; do not allow a later member to expose a
        # mixed chart/cycle/population only after earlier candidates are imported.
        answer, frozen = actual["answer"], expected["answer"]
        if type(answer) is not dict:
            raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
        for k in frozen:
            if k.endswith("identity") and k not in ("observed_visible_subject_identity", "native_observed_visible_identity", "reference_observed_visible_identity"):
                if answer.get(k) != frozen[k]:
                    raise ReviewError(ReviewFailure.ANSWER_IDENTITY_MISMATCH)
        header = answer.get("chart_observation_header")
        frozen_header = frozen.get("chart_observation_header")
        if type(header) is dict and type(frozen_header) is dict:
            for k in ("review_cycle_identity", "chart_revision_identity", "paired_bundle_identity", "chart_binding_identity"):
                if k in frozen_header and header.get(k) != frozen_header[k]:
                    raise ReviewError(ReviewFailure.ANSWER_IDENTITY_MISMATCH)


def _global(member):
    answer = member["answer"]
    if member["candidate_kind"] == "NSE":
        return answer.get("global_observation_status")
    questions = [*answer.get("reference_answers", []), *answer.get("native_answers", []),
                 *answer.get("cross_market_answers", []), answer.get("escape_hatch_answer", {})]
    states = [q.get("observation_status") for q in questions]
    if states and len(set(states)) == 1:
        return states[0]
    return "PARTIAL" if "INVALID" not in states and any(s in ("OBSERVED", "PARTIAL") for s in states) else "INVALID"


def import_expected(app, pointer):
    from kronos.application.intraday_review_v2 import IntradayReviewV2InboxImportResult, IntradayReviewV2InboxMemberResult
    retained = load(app, pointer, require_current=False)
    if retained is None:
        return None  # Historical individual transport remains supported.
    manifest, transport, folder = retained
    filename = transport.expected_answer_filename
    names = [m.canonical_subject_identity for m in pointer.cycles]
    results = []
    found = False
    try:
        payload = app._transport.read_expected_answer(filename)
        if payload is None:
            results = [IntradayReviewV2InboxMemberResult(n, filename, "NOT_FOUND") for n in names]
        else:
            found = True
            if len(payload) > MAX_ANSWER_BYTES:
                raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
            app._review._retain(folder / "attempts" / (sha256(payload).hexdigest() + ".json"), payload)
            document = decode(payload)
            validate_envelope(document, decode((folder / "template.json").read_bytes()))
            load(app, pointer)  # Current chart bindings checked for whole batch.
            for bound, member in zip(manifest["core"]["members"], document["candidates"], strict=True):
                cycle = app._review.load_cycle(bound["review_cycle_identity"])
                try:
                    app._require_current_workspace(pointer.probables_run_identity, cycle.cycle_identity)
                    if (member["global_observation_status"] not in {"OBSERVED", "PARTIAL", "NOT_VISIBLE", "NOT_APPLICABLE", "UNAVAILABLE", "INVALID"}
                        or member["global_observation_status"] != _global(member)):
                        raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
                    if bound["candidate_kind"] == "MCX_PAIRED":
                        chart = app._review.load_chart(bound["chart_revision_identity"])
                        result = app._paired.import_expected(cycle, chart, app._clock(), payload=encode(member["answer"]),
                            require_current=lambda: app._require_current_workspace(pointer.probables_run_identity, cycle.cycle_identity))
                    else:
                        single = app._review.load_transport(bound["transport_identity"])
                        nested = decode(app._review.load_transport_answer_template(single))
                        nested["candidates"] = [member["answer"]]
                        result = app._import_inbox_transport(single, current_review_count=len(names), payload=encode(nested))
                    results.append(replace(result.members[0], expected_answer_filename=filename))
                except (ReviewError, TypeError, KeyError, AttributeError) as error:
                    reason = error.failure.value if isinstance(error, ReviewError) else ReviewFailure.ANSWER_SCHEMA_INVALID.value
                    results.append(IntradayReviewV2InboxMemberResult(cycle.canonical_subject_identity, filename, "REJECTED", reason))
    except ReviewError as error:
        results = [IntradayReviewV2InboxMemberResult(n, filename, "REJECTED", error.failure.value) for n in names]
    return IntradayReviewV2InboxImportResult(mode="ORDERED_BATCH", current_review_count=len(names),
        expected_count=len(names), found_count=len(names) if found else 0,
        imported_count=sum(r.state == "IMPORTED" for r in results),
        already_imported_count=sum(r.state == "ALREADY_IMPORTED" for r in results),
        not_found_count=sum(r.state == "NOT_FOUND" for r in results),
        rejected_count=sum(r.state == "REJECTED" for r in results), members=tuple(results),
        producer_advanced=not app.currentness().is_review_current)
