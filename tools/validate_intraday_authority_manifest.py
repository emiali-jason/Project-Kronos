"""Validate the documentation-only Intraday authority manifest; no runtime imports."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = Path(
    "docs/architecture/products/intraday/"
    "KRONOS-INTRADAY-CURRENT-AUTHORITY-MANIFEST-V1.json"
)
DIMENSIONS = (
    "APPROVED_POLICY", "IMPLEMENTED", "PUBLISHED", "RUNTIME_ACCEPTED",
    "OPERATIONALLY_PROVEN", "EMPIRICALLY_QUALIFIED",
)
STATUSES = {"YES", "NO", "PARTIAL", "NOT_ESTABLISHED", "NOT_APPLICABLE"}
CLASSIFICATIONS = {"CURRENT", "SUPERSEDED", "CONTRADICTORY", "MISSING", "OPEN_CORRECTION"}
WORK_ORDERS = {f"WO-{n:02}" for n in range(1, 10)} | {"WO-03A"}
FIELDS = {
    "capability_id", "work_order", "capability", "current_policy_contract",
    "effective_version", "status_dimensions", "implementation", "publication_commit",
    "test_evidence", "runtime_acceptance", "operational_evidence",
    "empirical_qualification", "current_classification", "supersedes",
    "superseded_by", "open_correction", "evidence_reference", "notes",
}
UNRESOLVED = {
    "02-coverage", "02-temporal-coverage", "05-trusted-time", "05-request-accounting",
    "05-operation-timing", "05-loaded-identity", "06-opening", "06-relative-binding",
    "06-cpr-binding", "06-assessment-observation", "06-cpr-usefulness",
    "06-phase-contribution", "06-candidate-outcomes", "07-chart-time",
    "07-visual-reliability", "07-turnaround", "09-producer-advance",
    "09-rejected-receipts", "09-current-index-acceptance",
}
HISTORICAL_SUCCESSORS = {
    "01-old-baselines": "01-authority-map",
    "03-reliance-only": "03a-canonical-identity",
    "03-missing97": "03a-canonical-identity",
    "03-five-mcx-unavailable": "03a-availability",
    "06-v1-only": "06-phase-aware", "06-v20-only": "06-phase-aware",
    "07-v1-only": "07-chart-revisions", "07-literal-identity": "07-visual-identity",
    "09-individual-only": "09-exact-import", "09-import-disabled": "09-exact-import",
    "09-finder": "09-secure-inbox", "09-br2-not-started": "09-br2-closure",
    "09-br2-unpublished": "09-br2-closure", "09-br2-runtime-pending": "09-br2-closure",
    "09-retroactive-defect": "09-producer-advance",
    "09-no-index-evidence": "09-historical-acceptance",
    "05-no-timestamps": "05-operation-timing",
}
REQUIRED_CURRENT = {
    "01-authority-map", "02-numerical-visual-boundary", "03-membership",
    "03a-canonical-identity", "03a-availability", "03a-execution-eligibility",
    "04-skip", "05-runtime", "06-phase-aware", "06-later-nifty-label",
    "07-chart-revisions", "07-visual-identity", "07-generic-mcx", "08-conditional",
    "09-exact-import", "09-replay-conflict", "09-secure-inbox",
    "09-historical-acceptance", "09-current-equity-acceptance", "09-br2-closure",
}
REQUIRED_TRANSITION_TESTS = {
    "producer advances before individual import", "producer advances before batch import",
    "producer advances during batch", "producer advances before final batch publication/currentization",
    "identical replay after divergence", "conflicting replay after divergence",
    "fresh Review N+1 replacement", "already-imported evidence preservation",
    "independently failed batch members", "restart/restoration after partial producer-advance batch",
}


class ManifestError(ValueError):
    """Bounded document validation failure."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ManifestError(message)


def nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def unique_strings(value: object, name: str, *, required: bool = False) -> list[str]:
    require(isinstance(value, list), f"{name}: expected list")
    require(all(nonempty(v) for v in value), f"{name}: nonempty strings required")
    require(len(value) == len(set(value)), f"{name}: duplicate value")
    require(not required or bool(value), f"{name}: required")
    return value


def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_keys)


def validate_manifest(document: dict, *, repository_root: Path | None = None) -> dict:
    """Validate structure, independent statuses and this candidate's frozen open gates.

    This is a bounded executable schema for manifest 1.0.0, not a runtime contract.
    Statuses are required individually; they are never populated or inferred here.
    A later approved reconciliation may revise the version and these gate checks.
    """
    require(isinstance(document, dict), "manifest: expected object")
    require(document.get("manifest_id") == "KRONOS-INTRADAY-CURRENT-AUTHORITY-MANIFEST", "manifest identity")
    require(document.get("manifest_version") == "1.0.0", "unsupported manifest version")
    require(document.get("document_status") == "Approved", "WO-01C publication edition must be Approved")
    require(document.get("status_dimensions") == list(DIMENSIONS), "status dimensions")
    vocabulary = document.get("status_vocabulary")
    require(isinstance(vocabulary, dict) and set(vocabulary) == STATUSES, "status vocabulary")
    require(all(nonempty(v) for v in vocabulary.values()), "status definitions required")
    require(set(unique_strings(document.get("classification_vocabulary"), "classifications")) == CLASSIFICATIONS, "classification vocabulary")
    require(set(unique_strings(document.get("work_orders"), "work orders")) == WORK_ORDERS, "required WO-01 through WO-09 and WO-03A")
    registry = document.get("evidence_registry")
    require(isinstance(registry, dict) and bool(registry), "evidence registry required")
    for key, evidence in registry.items():
        require(nonempty(key) and isinstance(evidence, dict), "invalid evidence entry")
        require(set(evidence) == {"kind", "location", "detail"}, f"{key}: evidence fields")
        require(all(nonempty(v) for v in evidence.values()), f"{key}: evidence reference required")
        require(evidence["kind"] in {"SPONSOR_DECISION", "ACCEPTED_RECONCILIATION", "DOCUMENT", "RESEARCH", "RETAINED_EVIDENCE", "REPOSITORY"}, f"{key}: evidence kind")
        if evidence["kind"] == "REPOSITORY":
            path = Path(evidence["location"])
            require(not path.is_absolute() and ".." not in path.parts, f"{key}: repository reference containment")
            if repository_root is not None:
                target = (repository_root / path).resolve()
                require(target.is_relative_to(repository_root.resolve()) and target.is_file(), f"{key}: repository reference missing or outside root")
    rows = document.get("capabilities")
    require(isinstance(rows, list) and bool(rows), "capabilities required")
    by_id = {}
    for row in rows:
        require(isinstance(row, dict) and set(row) == FIELDS, "required capability fields")
        for field in FIELDS - {"status_dimensions", "publication_commit", "current_classification", "supersedes", "superseded_by", "open_correction", "evidence_reference"}:
            require(nonempty(row[field]), f"{field}: nonempty text required")
        identity = row["capability_id"]
        require(identity not in by_id, f"duplicate capability identity: {identity}")
        by_id[identity] = row
        require(row["work_order"] in WORK_ORDERS, f"{identity}: unknown work order")
        statuses = row["status_dimensions"]
        require(isinstance(statuses, dict) and set(statuses) == set(DIMENSIONS), f"{identity}: all six statuses required")
        require(all(isinstance(v, str) and v in STATUSES for v in statuses.values()), f"{identity}: unknown status")
        classes = unique_strings(row["current_classification"], identity + " classes", required=True)
        require(set(classes) <= CLASSIFICATIONS, f"{identity}: unknown classification")
        require(not ("CURRENT" in classes and "SUPERSEDED" in classes), f"{identity}: current/superseded conflict")
        refs = unique_strings(row["evidence_reference"], identity + " evidence", required=True)
        require(set(refs) <= set(registry), f"{identity}: unknown evidence reference")
        for sha in unique_strings(row["publication_commit"], identity + " commits"):
            require(re.fullmatch(r"[0-9a-f]{40}", sha) is not None, f"{identity}: full commit SHA required")
        for field in ("supersedes", "superseded_by"):
            unique_strings(row[field], identity + " " + field)
            require(identity not in row[field], f"{identity}: self supersession")
        if "SUPERSEDED" in classes:
            require(bool(row["superseded_by"]), f"{identity}: successor required")
        correction = row["open_correction"]
        if "OPEN_CORRECTION" in classes:
            require(isinstance(correction, dict) and set(correction) == {"owner", "status", "description"}, f"{identity}: correction ownership required")
            require(correction["owner"] == row["work_order"] and correction["status"] == "OPEN" and nonempty(correction["description"]), f"{identity}: correction must remain owned and open")
        else:
            require(correction is None, f"{identity}: undeclared correction")
    require({r["work_order"] for r in rows} == WORK_ORDERS, "missing work-order capability")
    require(REQUIRED_CURRENT | UNRESOLVED | set(HISTORICAL_SUCCESSORS) <= set(by_id), "missing required material capability")
    for identity, row in by_id.items():
        for field, reverse in (("supersedes", "superseded_by"), ("superseded_by", "supersedes")):
            for target in row[field]:
                require(target in by_id and identity in by_id[target][reverse], f"{identity}: unresolved supersession link")
    for identity, successor in HISTORICAL_SUCCESSORS.items():
        require("SUPERSEDED" in by_id[identity]["current_classification"] and by_id[identity]["superseded_by"] == [successor], f"{identity}: preserve historical successor")
    for identity in UNRESOLVED:
        row = by_id[identity]
        require("OPEN_CORRECTION" in row["current_classification"], f"{identity}: correction must remain open")
        require(row["status_dimensions"]["EMPIRICALLY_QUALIFIED"] != "YES", f"{identity}: no new empirical qualification")
        if identity != "09-current-index-acceptance":
            require(all(row["status_dimensions"][d] != "YES" for d in DIMENSIONS[1:]), f"{identity}: unresolved correction cannot be completed")
    require("CONTRADICTORY" in by_id["06-opening"]["current_classification"], "Opening contradiction must remain explicit")
    publication = document.get("publication_record")
    require(isinstance(publication, dict) and set(publication) == {"authority", "identity", "effective_condition", "qualification_snapshot", "closure_record"}, "manifest publication record required")
    require(all(nonempty(value) for value in publication.values()), "manifest publication record fields")
    require(by_id["01-authority-map"]["status_dimensions"]["PUBLISHED"] == "YES", "manifest own publication edition")
    transition = by_id["09-producer-advance"]
    require(transition["status_dimensions"] == dict(zip(DIMENSIONS, ("YES", "NO", "NO", "NO", "NO", "NOT_ESTABLISHED"))), "WO-09 producer-advance must remain policy-only")
    require(not transition["publication_commit"], "WO-09 transition is not published")
    for identity, marker in (("04-skip", "REQUIRED = NO"), ("08-conditional", "CONDITIONAL / SKIPPED")):
        row = by_id[identity]
        require(marker in row["current_policy_contract"] and "SKIPPED" in row["current_policy_contract"], f"{identity}: preserve skipped gate")
        require(all(row["status_dimensions"][d] == "NOT_APPLICABLE" for d in DIMENSIONS[1:]), f"{identity}: no implementation required")
        require(row["open_correction"] is None, f"{identity}: not reopened")
    policy = document.get("producer_advance_policy")
    require(isinstance(policy, dict), "producer-advance policy required")
    required_policy = {"authority", "currentness", "new_import_after_divergence", "already_imported", "identical_replay", "replay_must_not_create", "batch_checks", "producer_advance_during_batch", "fresh_review", "historical_review_ui", "historical_research_import", "br2", "required_future_tests", "downstream_authority"}
    require(set(policy) == required_policy, "complete producer-advance policy fields")
    require(set(unique_strings(policy["required_future_tests"], "transition tests")) == REQUIRED_TRANSITION_TESTS, "complete transition test matrix")
    require(set(unique_strings(policy["replay_must_not_create"], "replay effects")) == {"new evidence", "new authority", "new revision", "new current pointer", "new analytical consequence"}, "no replay consequences")
    for field, count in (("batch_checks", 3), ("producer_advance_during_batch", 5)):
        require(len(unique_strings(policy[field], field, required=True)) == count, f"{field}: complete batch guard sequence")
    for field in required_policy - {"required_future_tests", "replay_must_not_create", "batch_checks", "producer_advance_during_batch"}:
        require(nonempty(policy[field]), f"{field}: policy text required")
    require(policy["authority"] in registry, "transition decision reference")
    require(policy["historical_review_ui"] == "NOT AUTHORIZED" and policy["historical_research_import"].startswith("NOT AUTHORIZED"), "no historical workflow authority")
    programme = document.get("programme", {})
    for key, expected in {"WO-01A": "COMPLETE / PASS", "WO-01B": "COMPLETE / PASS / PUBLISHED", "WO-01C": "QUALIFIED / FINAL CLOSURE RECORDED IN LIVING MASTER", "STATISTICS": "HELD", "WO-10 REVALIDATION": "HELD", "WO-18": "HELD", "BR2": "CLOSED_WITH_SPONSOR_INPUT_PENDING", "AUTONOMOUS BROKER EXECUTION": "NONE"}.items():
        require(programme.get(key) == expected, f"programme boundary: {key}")
    return {
        "work_orders": len(WORK_ORDERS), "capabilities": len(rows),
        "classifications": {c: sum(c in r["current_classification"] for r in rows) for c in sorted(CLASSIFICATIONS)},
        "statuses": {d: {s: sum(r["status_dimensions"][d] == s for r in rows) for s in sorted(STATUSES)} for d in DIMENSIONS},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path, default=ROOT / MANIFEST_PATH)
    args = parser.parse_args()
    try:
        summary = validate_manifest(load_manifest(args.path), repository_root=ROOT)
    except (OSError, ValueError) as error:
        parser.exit(1, f"MANIFEST INVALID: {error}\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
