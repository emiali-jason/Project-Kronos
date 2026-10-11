"""Typed NSE authority from the commissioned V2 reconciliation and exact Analysis master.

This is an additive consumer of existing canonical/provider mapping authority.
It never creates a V1 instrument, Provider assertion or execution permission.
"""
from dataclasses import dataclass
from kronos.intraday.discovery import NativeDiscoveryRun
from kronos.intraday.reconciliation import ReconciliationPublication, Availability


@dataclass(frozen=True, slots=True)
class ReconciledNseUnderlying:
    reconciliation: ReconciliationPublication
    discovery: NativeDiscoveryRun
    canonical_subject_identity: str

    def __post_init__(self):
        if type(self.reconciliation) is not ReconciliationPublication or type(self.discovery) is not NativeDiscoveryRun:
            raise ValueError('WO10_RECONCILED_UNDERLYING_SOURCE_REQUIRED')
        self.reconciliation.__post_init__()
        self.discovery.__post_init__()
        if (self.discovery.reconciliation_identity != self.reconciliation.publication_identity
                or self.discovery.reconciliation_version != self.reconciliation.publication_version
                or self.discovery.reconciliation_integrity_identity != self.reconciliation.integrity_identity):
            raise ValueError('WO10_RECONCILED_UNDERLYING_SOURCE_CONFLICT')
        members = [m for m in self.reconciliation.members if m.canonical_identity == self.canonical_subject_identity]
        if len(members) != 1:
            raise ValueError('WO10_RECONCILED_UNDERLYING_MEMBER_REQUIRED')
        member = members[0]
        member.__post_init__()
        if (member.exchange != 'NSE' or not member.provider_symbol or not member.provider_directive_identities
                or member.dimensions.canonical_identity is not Availability.AVAILABLE
                or member.dimensions.provider_mapping is not Availability.AVAILABLE):
            raise ValueError('WO10_RECONCILED_UNDERLYING_MAPPING_REQUIRED')

    def resolve(self, master, handoff, now):
        from kronos.intraday.wo09_experimental import ExperimentalNextWoHandoff
        self.__post_init__()
        if type(handoff) is not ExperimentalNextWoHandoff:
            raise ValueError('WO10_RECONCILED_UNDERLYING_TYPED_HANDOFF_REQUIRED')
        assessment = handoff.readiness_document['assessment_document']
        if (handoff.canonical_subject_identity != self.canonical_subject_identity
                or assessment['discovery_identity'] != self.discovery.run_identity
                or self.discovery.observation_boundary > now
                or self.reconciliation.effective_boundary > self.discovery.observation_boundary
                or master.snapshot_identity not in self.discovery.source_identities
                or master.integrity_identity not in self.discovery.source_identities):
            raise ValueError('WO10_RECONCILED_UNDERLYING_SOURCE_CONFLICT')
        member = next(m for m in self.reconciliation.members if m.canonical_identity == self.canonical_subject_identity)
        rows = [r for r in master.records if r.provider == 'KITE' and r.exchange == member.exchange
                and r.trading_symbol == member.provider_symbol]
        if len(rows) != 1:
            raise ValueError('WO10_UNDERLYING_MASTER_CONFLICT')
        rows[0].__post_init__()
        return rows[0]
