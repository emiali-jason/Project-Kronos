"""Bounded, explicit Review V2 component collection; never used by GET.

Ownership is proven by decoded contracts and canonical store locations. Graph
edges are exact retained identities, including operation and batch membership.
External references protect entire connected components. Unknown evidence,
symlinks, changing files or an incomplete scan defer collection without exposing
filesystem details. Exported files outside Review storage are never deleted.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re

from kronos.intraday.review import ReviewError
from kronos.intraday.review_v2 import artifact_from_bytes_v2
from kronos.intraday.review_v2_operation_persistence import _decoded, _encoded
from kronos.intraday.review_v2_transport import transport_from_bytes_v2
from kronos.intraday.review_answer import parse_answer_pack, parse_batch_answer_transport

RETENTION_POLICY = "CURRENT_ONLY_PRESENTATION_WITH_REFERENCE_SAFE_GC"
_MAX_FILES = 200_000
_MAX_DELETE_BYTES = 128 * 1024 * 1024
_TOKEN = re.compile(rb"[A-Za-z0-9][A-Za-z0-9_.:-]{10,255}")
_FAMILIES = {
    "handoffs": ("ReviewHandoffV2", "handoff_identity"),
    "cycles": ("ReviewCycleV2", "cycle_identity"),
    "chart-requests": ("ChartIntakeRequestV2", "request_identity"),
    "chart-revisions": ("ChartRevisionV2", "chart_revision_identity"),
    "current-charts": ("CurrentChartPointerV2", "review_cycle_identity"),
    "question-packs": ("ReviewQuestionPackV2", "review_pack_identity"),
    "question-batches": ("ReviewQuestionBatchV2", "batch_identity"),
    "visual-evidence": ("ImportedVisualEvidenceV2", "visual_evidence_identity"),
    "current-visual-evidence": ("VisualEvidencePointerV2", "review_pack_identity"),
}


@dataclass(frozen=True)
class ReviewGCResult:
    status: str = "NOT_RUN"
    eligible_cycles: tuple[str, ...] = ()
    protected_cycles: tuple[str, ...] = ()
    files_before: int = 0
    bytes_before: int = 0
    files_removed: int = 0
    bytes_reclaimed: int = 0
    policy: str = RETENTION_POLICY


def _files(root: Path) -> list[Path]:
    # Reject links even within the root; do not traverse them or accept aliases.
    if any(p.is_symlink() for p in (root, *root.parents)):
        raise ValueError
    result = []
    for p in root.rglob("*"):
        if p.is_symlink():
            raise ValueError
        if p.is_file():
            result.append(p)
            if len(result) > _MAX_FILES:
                raise ValueError
    return sorted(result)


def _tokens(data: bytes) -> set[str]:
    return {x.decode("ascii") for x in _TOKEN.findall(data)}


def collect_review_components(store, transport) -> ReviewGCResult:
    """Internal maintenance entry: the store supplies the sole deletion root.

    Caller holds the application lock after exact currentization/restoration.
    There is no Browser path/root argument and no arbitrary path deletion API.
    """
    try:
        with store._lock:
            return _collect(store, transport)
    except (OSError, ValueError, TypeError, KeyError, IndexError, ReviewError):
        return ReviewGCResult(status="GC_DEFERRED_INTEGRITY_OR_IO")


def _collect(store, transport) -> ReviewGCResult:
    root = store.root
    if root.name != "review-v2" or root != root.resolve():
        raise ValueError
    pointer = store.load_current()
    if pointer is None:
        raise ValueError
    paths = _files(root)
    data = {p: p.read_bytes() for p in paths}
    # Nodes are files; identity indexes may include aliases of one artifact.
    identities: dict[str, set[Path]] = {}
    edges = {p: set() for p in paths}
    owners: dict[Path, set[str]] = {}
    assigned: set[Path] = set()
    cycles: dict[str, Path] = {}
    binary_owners: dict[bytes, set[Path]] = {}

    def node(p, ids, refs):
        if p not in data:
            raise ValueError
        assigned.add(p)
        owners[p] = set(refs)
        for identity in ids:
            identities.setdefault(identity, set()).add(p)

    def binary(parent, family, identity, suffix, digest):
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9-]+", identity):
            raise ValueError
        p = root / family / (identity + suffix)
        if sha256(data[p]).hexdigest() != digest:
            raise ValueError
        node(p, (identity,), ())
        binary_owners.setdefault(bytes.fromhex(digest), set()).add(p)
        edges[parent].add(p); edges[p].add(parent)

    current_path = root / "current" / "CURRENT-REVIEW-V2-POINTER.json"
    for p, payload in data.items():
        rel = p.relative_to(root)
        family = rel.parts[0]
        if family in _FAMILIES:
            if len(rel.parts) != 2:
                raise ValueError
            value = artifact_from_bytes_v2(payload)
            typename, key = _FAMILIES[family]
            identity = getattr(value, key)
            if type(value).__name__ != typename or p.name != identity + ".json":
                raise ValueError
            node(p, (identity, value.integrity_identity), _tokens(payload))
            if family == "cycles":
                cycles[identity] = p
                store.load_handoff(value.handoff_identity)
            elif family == "current-charts":
                store.load_current_chart(identity)
            elif family == "current-visual-evidence":
                store.load_visual_evidence_for_pack(identity)
            elif family == "question-packs":
                store.load_cycle(value.review_cycle_identity)
                store.load_chart(value.chart_revision_identity)
            elif family == "question-batches":
                for pack in value.review_pack_identities:
                    store.load_pack(pack)
            if family == "chart-revisions":
                store.load_chart_bytes(value)
                binary(p, "chart-binaries", value.chart_artifact_identity,
                       ".png" if value.media_type == "image/png" else ".jpg", value.payload_sha256)
        elif p == current_path:
            if artifact_from_bytes_v2(payload) != pointer:
                raise ValueError
            node(p, (pointer.integrity_identity,), _tokens(payload))
        elif family == "question-transports":
            value = transport_from_bytes_v2(payload)
            if len(rel.parts) != 2 or p.name != value.transport_identity + ".json":
                raise ValueError
            store.load_transport(value.transport_identity)
            node(p, (value.transport_identity, value.integrity_identity), _tokens(payload))
            binary(p, "question-transport-pdfs", value.transport_identity, ".pdf", value.question_pdf_sha256)
            binary(p, "answer-templates", value.transport_identity, ".json", value.answer_template_sha256)
        elif family in {"answer-transports", "batch-answer-transports"}:
            value = parse_answer_pack(payload) if family == "answer-transports" else parse_batch_answer_transport(payload)
            identity = value.review_pack_identity if family == "answer-transports" else value.review_batch_identity
            if len(rel.parts) != 2 or p.name != identity + "-" + sha256(payload).hexdigest() + ".json":
                raise ValueError
            node(p, (), _tokens(payload))
        elif family == "operations":
            value = _decoded(payload)
            expected = (value.provenance_identity if rel.parts[1] == "records"
                        else sha256(value.request_identity.encode()).hexdigest().upper())
            if len(rel.parts) != 3 or rel.parts[1] not in {"records", "requests"} or p.name != expected + ".json" or _encoded(value) != payload:
                raise ValueError
            node(p, (value.provenance_identity,), _tokens(payload))
    if assigned != set(paths):
        raise ValueError  # Unknown files are not inferred to be Review-owned.
    for p, references in owners.items():
        for reference in references:
            for target in identities.get(reference, ()):
                edges[p].add(target); edges[target].add(p)
    components = []
    unseen = set(paths)
    while unseen:
        component, pending = set(), [next(iter(unseen))]
        while pending:
            p = pending.pop()
            if p in component:
                continue
            component.add(p); pending.extend(edges[p] - component)
        unseen -= component
        components.append(component)

    # Scan the enclosing governed evidence tree, including sibling products.
    # Tests use an isolated tree. Unknown/malformed JSON or symlinks defer GC.
    scope = root.parent.parent if root.parent.name == "intraday-v1" else root.parent
    def external_files():
        found = {p for p in _files(scope) if not p.is_relative_to(root)}
        # Published transport outputs live outside the deletion namespace.
        # Their surviving references conservatively protect the component.
        for directory in (transport.question_outbox, transport.answer_inbox):
            if directory.exists():
                found.update(p for p in _files(directory) if not p.is_relative_to(root))
        return sorted(found)

    external = external_files()
    external_hashes = {}
    protected_nodes = set()
    reference_pattern = re.compile(b"|".join(re.escape(i.encode()) for i in sorted(identities, key=len, reverse=True)))
    scanned_bytes = 0
    for p in external:
        if p.stat().st_size > _MAX_DELETE_BYTES:
            raise ValueError
        payload = p.read_bytes()
        scanned_bytes += len(payload)
        if scanned_bytes > 8 * 1024 * 1024 * 1024:
            raise ValueError
        external_hashes[p] = sha256(payload).digest()
        protected_nodes.update(binary_owners.get(external_hashes[p], ()))
        if p.suffix == ".json":
            payload = json.dumps(json.loads(payload), ensure_ascii=False).encode()
        # Exact identities can also occur in path references or escaped JSON.
        for token in reference_pattern.findall(payload):
            protected_nodes.update(identities[token.decode()])
    current_ids = {c.cycle_identity for c in pointer.cycles}
    keep = {current_path} | {cycles[c] for c in current_ids}
    eligible, protected, deletion = [], [], set()
    for component in components:
        member_cycles = {c for c, p in cycles.items() if p in component}
        old = member_cycles - current_ids
        if component & (keep | protected_nodes):
            protected.extend(old)
        elif old:
            eligible.extend(old); deletion.update(component)
        # Unbound failed operations cannot be assigned to a superseded cycle.
    size = sum(len(data[p]) for p in deletion)
    if size > _MAX_DELETE_BYTES:
        raise ValueError
    if _files(root) != paths or store.load_current() != pointer:
        raise ValueError
    if any(p.read_bytes() != payload for p, payload in data.items()):
        raise ValueError
    if external_files() != external:
        raise ValueError
    if any(sha256(p.read_bytes()).digest() != h for p, h in external_hashes.items()):
        raise ValueError
    removed = []
    try:
        for p in sorted(deletion):
            p.unlink(); removed.append(p)
        if store.load_current() != pointer:
            raise ValueError
    except (OSError, ValueError, ReviewError):
        for p in removed:
            p.write_bytes(data[p])
        raise
    return ReviewGCResult("GC_COMPLETE", tuple(sorted(eligible)), tuple(sorted(protected)),
                          len(paths), sum(map(len, data.values())), len(deletion), size)
