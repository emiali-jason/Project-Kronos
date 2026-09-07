"""Documentation-only qualification; never compose runtime or touch evidence stores."""
from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "intraday_authority_validator", ROOT / "tools/validate_intraday_authority_manifest.py"
)
assert SPEC is not None and SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


@pytest.fixture
def document():
    return validator.load_manifest(ROOT / validator.MANIFEST_PATH)


def row(document, identity):
    return next(r for r in document["capabilities"] if r["capability_id"] == identity)


def test_candidate_and_repository_references_validate_without_mutating_input(document):
    before = deepcopy(document)
    result = validator.validate_manifest(document, repository_root=ROOT)
    assert result["work_orders"] == 10  # Nine numbered WOs and explicit WO-03A.
    assert result["capabilities"] == len(document["capabilities"])
    assert result["classifications"]["OPEN_CORRECTION"] == len(validator.UNRESOLVED)
    assert result["statuses"]["EMPIRICALLY_QUALIFIED"]["YES"] == 0
    assert document == before


@pytest.mark.parametrize("field", sorted(validator.FIELDS))
def test_missing_capability_field_fails(document, field):
    del document["capabilities"][0][field]
    with pytest.raises(validator.ManifestError):
        validator.validate_manifest(document)


@pytest.mark.parametrize("dimension", validator.DIMENSIONS)
def test_unknown_status_fails_even_if_added_to_document_vocabulary(document, dimension):
    document["capabilities"][0]["status_dimensions"][dimension] = "COMPLETE"
    with pytest.raises(validator.ManifestError, match="unknown status"):
        validator.validate_manifest(document)
    document["status_vocabulary"]["COMPLETE"] = "Everything is done."
    with pytest.raises(validator.ManifestError, match="vocabulary"):
        validator.validate_manifest(document)


@pytest.mark.parametrize("first,second", list(zip(validator.DIMENSIONS, validator.DIMENSIONS[1:])))
def test_one_dimension_does_not_imply_the_next(document, first, second):
    capability = row(document, "02-numerical-visual-boundary")
    capability["status_dimensions"][first] = "YES"
    capability["status_dimensions"][second] = "NO"
    validator.validate_manifest(document)
    assert capability["status_dimensions"][second] == "NO"
    del capability["status_dimensions"][second]
    with pytest.raises(validator.ManifestError, match="six statuses"):
        validator.validate_manifest(document)


def test_duplicate_capability_identity_fails(document):
    document["capabilities"].append(deepcopy(document["capabilities"][0]))
    with pytest.raises(validator.ManifestError, match="duplicate capability"):
        validator.validate_manifest(document)


def test_duplicate_json_keys_fail_before_validation(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"capabilities": [], "capabilities": []}', encoding="utf-8")
    with pytest.raises(validator.ManifestError, match="duplicate JSON key"):
        validator.load_manifest(path)


@pytest.mark.parametrize("replacement", [[], ["UNREGISTERED"]])
def test_missing_or_unknown_evidence_reference_fails(document, replacement):
    document["capabilities"][0]["evidence_reference"] = replacement
    with pytest.raises(validator.ManifestError, match="evidence"):
        validator.validate_manifest(document)


def test_broken_repository_reference_fails(document):
    document["evidence_registry"]["ARCHITECTURE"]["location"] = "docs/no-such-source.md"
    with pytest.raises(validator.ManifestError, match="reference missing"):
        validator.validate_manifest(document, repository_root=ROOT)


@pytest.mark.parametrize("work_order", sorted(validator.WORK_ORDERS))
def test_required_work_order_coverage_cannot_be_removed(document, work_order):
    document["capabilities"] = [r for r in document["capabilities"] if r["work_order"] != work_order]
    with pytest.raises(validator.ManifestError, match="work-order"):
        validator.validate_manifest(document)


@pytest.mark.parametrize("identity", sorted(validator.UNRESOLVED))
def test_required_open_corrections_cannot_be_marked_complete(document, identity):
    capability = row(document, identity)
    capability["current_classification"] = ["CURRENT"]
    capability["open_correction"] = None
    capability["status_dimensions"] = dict.fromkeys(validator.DIMENSIONS, "YES")
    with pytest.raises(validator.ManifestError, match="remain open"):
        validator.validate_manifest(document)


@pytest.mark.parametrize("owner", [None, "WO-08"])
def test_open_correction_owner_must_be_explicit_and_correct(document, owner):
    row(document, "06-opening")["open_correction"]["owner"] = owner
    with pytest.raises(validator.ManifestError, match="owned and open"):
        validator.validate_manifest(document)


def test_superseded_statement_requires_successor(document):
    row(document, "09-finder")["superseded_by"] = []
    with pytest.raises(validator.ManifestError, match="successor required"):
        validator.validate_manifest(document)


def test_unknown_classification_rejected(document):
    document["capabilities"][0]["current_classification"] = ["COMPLETE"]
    with pytest.raises(validator.ManifestError, match="unknown classification"):
        validator.validate_manifest(document)


@pytest.mark.parametrize("dimension", validator.DIMENSIONS[1:])
def test_producer_advance_policy_cannot_acquire_implementation_or_qualification(document, dimension):
    row(document, "09-producer-advance")["status_dimensions"][dimension] = "YES"
    with pytest.raises(validator.ManifestError):
        validator.validate_manifest(document)


def test_producer_advance_has_no_publication_commit(document):
    row(document, "09-producer-advance")["publication_commit"] = [document["qualification_baseline"]["local_head"]]
    with pytest.raises(validator.ManifestError, match="not published"):
        validator.validate_manifest(document)


def test_transition_policy_retains_batch_replay_history_and_restoration_requirements(document):
    policy = document["producer_advance_policy"]
    assert "NON_CURRENT" in policy["currentness"]
    assert policy["new_import_after_divergence"].startswith("BLOCKED")
    assert "PRESERVE IMMUTABLY" in policy["already_imported"]
    assert "IDEMPOTENT REPLAY" in policy["identical_replay"]
    assert "not-yet-imported" in policy["batch_checks"][1]
    assert "publication/currentization" in policy["batch_checks"][2]
    assert any("partial completion" in step for step in policy["producer_advance_during_batch"])
    assert any("stale Review never becomes current" in step for step in policy["producer_advance_during_batch"])
    assert "Review bound to N+1" in policy["fresh_review"]
    assert "NON_CURRENT_RESEARCH" in policy["historical_research_import"]
    assert "CLOSED_WITH_SPONSOR_INPUT_PENDING" in policy["br2"]
    assert set(policy["required_future_tests"]) == validator.REQUIRED_TRANSITION_TESTS
    policy["required_future_tests"].pop()
    with pytest.raises(validator.ManifestError, match="test matrix"):
        validator.validate_manifest(document)


@pytest.mark.parametrize("identity", ["04-skip", "08-conditional"])
def test_skipped_gates_cannot_be_reopened(document, identity):
    row(document, identity)["status_dimensions"]["IMPLEMENTED"] = "YES"
    with pytest.raises(validator.ManifestError, match="no implementation required"):
        validator.validate_manifest(document)


def test_historical_workflow_cannot_be_authorized(document):
    document["producer_advance_policy"]["historical_review_ui"] = "AUTHORIZED"
    with pytest.raises(validator.ManifestError, match="historical workflow"):
        validator.validate_manifest(document)


def test_programme_holds_are_preserved(document):
    document["programme"]["WO-01C"] = "STARTED"
    with pytest.raises(validator.ManifestError, match="programme boundary"):
        validator.validate_manifest(document)


def test_empirical_and_membership_discipline_is_explicit(document):
    discipline = document["empirical_discipline"]
    assert set(discipline["never_infer"]) == {
        "profitability", "Win Rate", "tradability", "Futures suitability",
        "Options suitability", "Risk suitability", "execution eligibility",
    }
    policy = row(document, "03-membership")["current_policy_contract"]
    assert "93 is not architecture capacity" in policy
    assert "DEFERRED" in policy and "98 governed members" in policy
    price = row(document, "06-assessment-observation")["current_policy_contract"]
    assert "same governed price observation" in price
    assert "arbitrary candle close" in price


def test_publication_edition_promotes_only_manifest_publication(document):
    assert document["document_status"] == "Approved"
    assert row(document, "01-authority-map")["status_dimensions"]["PUBLISHED"] == "YES"
    assert row(document, "09-producer-advance")["status_dimensions"]["PUBLISHED"] == "NO"
    assert "uncommitted or unpushed candidate alone is not publication" in document["publication_record"]["effective_condition"]
    assert "No self-referential commit hash" in document["publication_record"]["identity"]
    del document["publication_record"]
    with pytest.raises(validator.ManifestError, match="publication record required"):
        validator.validate_manifest(document)
