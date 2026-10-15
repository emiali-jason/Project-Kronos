"""TE-05B exact offline methodology publication/admission. No assessment.

Sponsor approves methodology semantics; the governed decision binds exact
publication bytes and effective applicability. This is a trusted composition
dependency, never an approval string/flag accepted from an Analyst or Browser.
Every admission rechecks the immutable publication graph; no cached fallback.
"""
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from kronos.theta.contracts import ThetaError, digest, encode, parse, require, stamp
from kronos.theta.store import directory, read_at

ROOT = Path(__file__).resolve().parents[3] / "docs/architecture/products/theta"
RESEARCH_ID = "KRONOS-THETA-ASTRA-RESEARCH-METHODOLOGY-V1"
ASSESSMENT_ID = "KRONOS-THETA-ANALYTICAL-ASSESSMENT-METHODOLOGY-V1"
DECISION_ID = "ADR-0067"
ADR_TITLE = "Theta V1 Astra Research and Analytical Assessment Methodology Governance"
ADR_PATH = "docs/architecture/adr/ADR-0067-THETA-V1-RESEARCH-AND-ASSESSMENT-METHODOLOGY.md"
VERSION = "1.0.0"
RESEARCH_SHA256 = "e9caff6ccf9b4b699737187a32e8eafe56366823fe280351868da6af06db9d5d"
ASSESSMENT_SHA256 = "3595575c45db9aaf8bc165ffbe903737ed71124e7280291ab2e65259da4bb785"
SPONSOR_ORDER_SHA256 = "12f8473fb02a9e7898a9387ae568b1acae1f3bd14ed3fb231fae9c7a26a4ee6a"
# Exact Sponsor approval plus CA-assigned ADR-0067 and prospective boundary.
DECISION_SHA256 = "a15e8ec6e5dfd088721a19ea5ff4637228e2a54409db242e9c153453608e75f8"
MANIFEST_NAME = "TE05B-METHODOLOGY-INTEGRITY.json"
DECISION_NAME = "TE05B-METHODOLOGY-APPROVAL.json"


class ThetaMethodologyPublication:
    """Read exact approved artifacts; return descriptors, never criterion results."""
    def __init__(self, root=ROOT):
        require(isinstance(root, Path) and root.is_absolute(), "THETA_METHODOLOGY_CONFIGURATION_INVALID")
        self.root = root

    def _snapshot(self):
        require(DECISION_SHA256 is not None and DECISION_ID != "PENDING_CA_ASSIGNMENT",
                "THETA_METHODOLOGY_GOVERNANCE_UNAVAILABLE")
        expected = {RESEARCH_ID + ".json": RESEARCH_SHA256,
                    ASSESSMENT_ID + ".json": ASSESSMENT_SHA256,
                    DECISION_NAME: DECISION_SHA256}
        try:
            with directory(self.root) as fd:
                manifest_raw = read_at(fd, MANIFEST_NAME, maximum=2 * 1024 * 1024)
                manifest = parse(manifest_raw)
                require(encode(manifest) == manifest_raw and manifest == {
                    "decision_identity": DECISION_ID, "files": expected}, "THETA_METHODOLOGY_INTEGRITY_INVALID")
                values = {}
                for name, expected_sha in expected.items():
                    raw = read_at(fd, name, maximum=2 * 1024 * 1024)
                    value = parse(raw)
                    require(digest(raw) == expected_sha and encode(value) == raw,
                            "THETA_METHODOLOGY_INTEGRITY_INVALID")
                    values[name] = value
        except (OSError, ValueError, KeyError, TypeError):
            raise ThetaError("THETA_METHODOLOGY_PUBLICATION_UNAVAILABLE") from None
        decision = values[DECISION_NAME]
        require(decision["decision_identity"] == DECISION_ID
                and decision["approval"] == "SPONSOR_APPROVED"
                and decision["adr_identity"] == DECISION_ID
                and decision["ca_assignment"] == {
                    "identity": DECISION_ID, "title": ADR_TITLE,
                    "canonical_path": ADR_PATH,
                    "scope": "Coordinated governance of the separately versioned Theta V1 Astra Research Methodology and Theta V1 Analytical Assessment Methodology.",
                    "supersedes": "NONE", "preserved_temporal_foundation": "ADR-0066"}
                and digest(decision["sponsor_order_utf8"].encode()) == SPONSOR_ORDER_SHA256
                and decision["sponsor_order_sha256"] == SPONSOR_ORDER_SHA256
                and decision["prospective_only"] is True,
                "THETA_METHODOLOGY_GOVERNANCE_UNAVAILABLE")
        for identity, expected_sha in ((RESEARCH_ID, RESEARCH_SHA256), (ASSESSMENT_ID, ASSESSMENT_SHA256)):
            policy = values[identity + ".json"]
            require(policy["identity"] == identity and policy["version"] == VERSION
                    and policy["governance_decision"] == DECISION_ID
                    and decision["methodologies"][identity] == {
                        "identity": identity, "version": VERSION, "sha256": expected_sha},
                    "THETA_METHODOLOGY_INTEGRITY_INVALID")
        stamp(decision["effective_after"])
        return decision, values[RESEARCH_ID + ".json"], values[ASSESSMENT_ID + ".json"]

    def _admit(self, at):
        require(type(at) is datetime and at.tzinfo is not None and at.utcoffset() is not None,
                "THETA_TIMESTAMP_INVALID")
        decision, research, assessment = self._snapshot()
        require(at > stamp(decision["effective_after"]), "THETA_METHODOLOGY_NOT_EFFECTIVE")
        return decision, research, assessment

    def research_inputs(self, at):
        decision, policy, _ = self._admit(at)
        return {"descriptor": deepcopy(decision["methodologies"][RESEARCH_ID]),
                "instructions": policy["instructions"]}

    def assessment_policy(self, information_cutoff):
        """Future TE-05C consumes this exact policy; TE-05B never evaluates it."""
        decision, _, policy = self._admit(information_cutoff)
        return {"descriptor": deepcopy(decision["methodologies"][ASSESSMENT_ID]),
                "effective_after": decision["effective_after"], "prospective_only": True,
                "policy": deepcopy(policy)}
