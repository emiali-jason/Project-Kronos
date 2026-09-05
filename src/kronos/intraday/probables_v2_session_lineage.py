"""Read-only validation of retained Discovery/Probables session lineage.

Uses Discovery's canonical digest and the Probables constructor's mapping
predicate. No schedule lookup, evidence selection, evaluation or publication.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from kronos.intraday.discovery_source import _identity as _discovery_identity
from kronos.intraday.probables_v2 import (
    DiscoveryProbablesEvidenceV2,
    ProbableMemberResultV2,
    ProbablesRunV2,
    _mapped_result_lineage_valid,
)
from kronos.intraday.probables_v2_diagnostics import ProbablesV2ReplayEnvelope
from kronos.intraday.probables_v2_diagnostics_persistence import ProbablesV2DiagnosticsStore
from kronos.intraday.probables_v2_refresh import DISCOVERY_PROBABLES_V2_REFRESH_IDENTITY
from kronos.intraday.refresh_v2 import RefreshV2Outcome
from kronos.intraday.refresh_v2_persistence import RefreshV2ProvenanceStore


def load_probables_session_envelope(
    root: Path, run: ProbablesRunV2,
) -> ProbablesV2ReplayEnvelope:
    """Resolve exact successful run provenance; never select latest evidence."""
    provenance = RefreshV2ProvenanceStore(root)
    records = provenance.load_for_probables_run(run.run_identity)
    identities = {record.replay_envelope_identity for record in records}
    if not records or len(identities) != 1 or None in identities:
        raise ValueError("PROBABLES_V2_SESSION_LINEAGE_UNAVAILABLE")
    envelope = ProbablesV2DiagnosticsStore(root).load_envelope(identities.pop())
    if any(
        record.outcome is not RefreshV2Outcome.SUCCESS
        or record.resulting_discovery_identity != run.source_discovery_run_identity
        or record.observation_boundary != run.analysis_boundary
        or record.methodology_publication_identity != run.methodology.publication_identity
        or record.request_identity != envelope.request_identity
        for record in records
    ):
        raise ValueError("PROBABLES_V2_SESSION_LINEAGE_UNAVAILABLE")
    return envelope


def probables_result_session_bound(
    *,
    run: ProbablesRunV2,
    result: ProbableMemberResultV2,
    mapping: DiscoveryProbablesEvidenceV2 | None,
    envelope: ProbablesV2ReplayEnvelope | None,
) -> bool:
    """Prove the exact member/session preimage retained at this run's boundary.

    Facts are ordered by the retained reconciliation, exactly as
    governed_market_session_identities orders its canonical payload. Missing
    constituents cannot be filled from today's calendar: either both retained
    Discovery digests match or this proof is unavailable.
    """
    if (
        type(run) is not ProbablesRunV2
        or type(result) is not ProbableMemberResultV2
        or type(mapping) is not DiscoveryProbablesEvidenceV2
        or type(envelope) is not ProbablesV2ReplayEnvelope
    ):
        return False
    try:
        # Re-run owner seals, including the envelope's complete nested payload.
        for value in (run, result, mapping, envelope):
            replace(value)
        discovery = envelope.discovery_run
        if (
            result.market_session_identity == run.market_session_identity
            or result not in run.results
            or run.source_discovery_run_identity != discovery.run_identity
            or run.market_session_identity != discovery.market_session_identity
            or run.analysis_boundary != envelope.analysis_boundary
            or run.universe_identity != discovery.universe_identity
            or run.universe_version != discovery.universe_version
            or run.reconciliation_identity != discovery.reconciliation_identity
            or run.reconciliation_version != discovery.reconciliation_version
            or run.methodology.publication_identity
            != envelope.methodology_publication_identity
            or not _mapped_result_lineage_valid(result, mapping)
        ):
            return False
        facts = {item.universe_member_identity: item for item in envelope.probables_v2_facts}
        members = {item.universe_member_identity: item for item in envelope.reconciliation.members}
        results = {item.universe_member_identity: item for item in discovery.results}
        bundles = {item.bundle_identity: item for item in envelope.machine_fact_bundles}
        if not facts or not facts.keys() <= members.keys():
            return False
        sessions = []
        for member in envelope.reconciliation.members:
            fact = facts.get(member.universe_member_identity)
            if fact is None:
                continue
            source_result = results.get(member.universe_member_identity)
            bundle = bundles.get(fact.discovery_bundle_identity)
            if (
                source_result is None
                or bundle is None
                or fact.canonical_subject_identity != member.canonical_identity
                or bundle.canonical_identity != member.canonical_identity
                or bundle.observation_boundary != run.analysis_boundary
                or bundle.market_session_identity != discovery.market_session_identity
                or bundle.market_session_boundary_identity
                != discovery.market_session_boundary_identity
                or source_result.machine_fact_bundle_identity != bundle.bundle_identity
            ):
                return False
            sessions.append((
                member.universe_member_identity,
                fact.current_schedule.session_id,
                tuple((window.opens_at, window.closes_at) for window in fact.current_schedule.windows),
            ))
        constituents = tuple(sessions)
        if (
            _discovery_identity("DISCOVERY-MARKET-SESSIONS", constituents)
            != discovery.market_session_identity
            or _discovery_identity("DISCOVERY-MARKET-BOUNDARY", {
                "observed_at": run.analysis_boundary, "sessions": constituents,
            }) != discovery.market_session_boundary_identity
        ):
            return False
        fact = facts.get(result.universe_member_identity)
        source_result = results.get(result.universe_member_identity)
        return (
            fact is not None
            and source_result is not None
            and result.canonical_subject_identity == fact.canonical_subject_identity
            and result.source_discovery_member_identity == source_result.persistence_identity
            and result.market_session_identity == fact.current_schedule.session_id
            and result.market_session_identity
            == mapping.completed_evidence.current_market_session_identity
            and mapping.completed_evidence.provenance == (
                DISCOVERY_PROBABLES_V2_REFRESH_IDENTITY, fact.facts_identity,
            )
            and mapping.provenance == (
                DISCOVERY_PROBABLES_V2_REFRESH_IDENTITY,
                fact.facts_identity, fact.integrity_identity,
            )
        )
    except (ValueError, TypeError, AttributeError):
        return False
