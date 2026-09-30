"""Read-only DOMAIN-006 identity bridge for Swing MCX contract candidates.

This verifies a retained authenticated Provider snapshot and an exact normalized
contract. It deliberately does not turn an old master, exchange URL, or Kite
``lot_size`` into current specification, order-conversion, or entry authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.instrument_master import KITE_INSTRUMENT_MASTER_DATASET
from kronos.provider.instrument_master import ProviderAcquisitionOutcome
from kronos.provider.instrument_master_persistence import ProviderInstrumentSnapshotStore
from kronos.swing.v1.mcx_contract_profile import McxFamily, mcx_contract_name_matches
from kronos.swing.v1.mcx_contract_selection import (
    McxContractAdmissionFacts, McxContractOffer, V1_ADVISORY_SELECTION,
    prepare_mcx_contract_offer,
)


@dataclass(frozen=True, slots=True)
class McxRetainedMasterMatch:
    snapshot_identity: str
    record_identity: str
    snapshot_file_sha256: str
    acquired_at: datetime
    normalized_contract: InstrumentRecord
    provider_instrument_token: int
    record_integrity_identity: str
    acquisition_effective_at: datetime
    source_boundary: datetime
    provider_validity_assertion: str | None
    authority: str = "AUTHENTICATED_HISTORICAL_MASTER_ONLY"

    @property
    def permits_new_entry(self) -> bool:
        return False


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_retained_mcx_master_match(
    store: ProviderInstrumentSnapshotStore, *,
    snapshot_identity: str, record_identity: str,
    family: McxFamily, normalized_contract: InstrumentRecord,
    observed_at: datetime,
) -> McxRetainedMasterMatch:
    """Resolve one exact sealed record without inferring freshness or units."""

    if (type(store) is not ProviderInstrumentSnapshotStore
            or type(family) is not McxFamily
            or type(normalized_contract) is not InstrumentRecord
            or not mcx_contract_name_matches(family, normalized_contract)
            or observed_at.tzinfo is None or observed_at.utcoffset() is None):
        raise ValueError("MCX_RETAINED_MASTER_INPUT_INVALID")
    path = store.path_for(provider="KITE",
        dataset_identity=KITE_INSTRUMENT_MASTER_DATASET,
        snapshot_identity=snapshot_identity)
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise ValueError("MCX_RETAINED_MASTER_PATH_INVALID")
    try:
        before = _file_sha256(path)
        snapshot = store.load(provider="KITE",
            dataset_identity=KITE_INSTRUMENT_MASTER_DATASET,
            snapshot_identity=snapshot_identity)
        after = _file_sha256(path)
    except OSError as error:
        raise ValueError("MCX_RETAINED_MASTER_UNAVAILABLE") from error
    if (before != after
            or snapshot.acquisition_outcome is not ProviderAcquisitionOutcome.COMPLETE
            or snapshot.acquired_at > observed_at
            or not snapshot.authenticated_context_identity
            or not snapshot.authorized_operation_identity):
        raise ValueError("MCX_RETAINED_MASTER_UNAVAILABLE")
    matches = tuple(record for record in snapshot.records
                    if record.provider_record_identity == record_identity)
    if len(matches) != 1:
        raise ValueError("MCX_RETAINED_MASTER_RECORD_UNAVAILABLE")
    record = matches[0]
    exact = InstrumentRecord(
        record.provider, record.exchange, record.segment,
        record.trading_symbol, record.name, record.instrument_type,
        record.expiry, record.tick_size, record.lot_size,
    )
    if exact != normalized_contract:
        raise ValueError("MCX_RETAINED_MASTER_CONTRACT_MISMATCH")
    return McxRetainedMasterMatch(
        snapshot.snapshot_identity, record.provider_record_identity,
        before, snapshot.acquired_at, exact,
        record.provider_instrument_token, record.record_integrity_identity,
        snapshot.acquisition_effective_at, snapshot.source_boundary,
        snapshot.provider_validity_assertion,
    )


def listed_v1_mcx_offers(
    store: ProviderInstrumentSnapshotStore, *, snapshot_identity: str,
    run_identity: str, observed_at: datetime,
) -> dict[McxFamily, McxContractOffer]:
    """Read two nearest listed unexpired futures per family from one sealed master.

    This is an advisory selection read. A Provider expiry and token are factual
    identity; neither the historical snapshot nor lot_size proves contract
    specifications, broker restrictions, monetary value or a current quote.
    """
    if (type(store) is not ProviderInstrumentSnapshotStore
            or observed_at.tzinfo is None or observed_at.utcoffset() is None):
        raise ValueError("MCX_V1_MASTER_INPUT_INVALID")
    path = store.path_for(provider="KITE",
        dataset_identity=KITE_INSTRUMENT_MASTER_DATASET,
        snapshot_identity=snapshot_identity)
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise ValueError("MCX_V1_MASTER_PATH_INVALID")
    before = _file_sha256(path)
    snapshot = store.load(provider="KITE",
        dataset_identity=KITE_INSTRUMENT_MASTER_DATASET,
        snapshot_identity=snapshot_identity)
    if (before != _file_sha256(path)
            or snapshot.acquisition_outcome is not ProviderAcquisitionOutcome.COMPLETE
            or snapshot.acquired_at > observed_at
            or not snapshot.authenticated_context_identity
            or not snapshot.authorized_operation_identity):
        raise ValueError("MCX_V1_AUTHENTICATED_MASTER_UNAVAILABLE")
    facts: dict[McxFamily, list[McxContractAdmissionFacts]] = {
        family: [] for family in McxFamily
    }
    for record in snapshot.records:
        if (record.exchange != "MCX" or record.segment != "MCX-FUT"
                or record.instrument_type != "FUT" or record.expiry is None):
            continue
        try:
            family = McxFamily(record.name)
        except ValueError:
            continue
        exact = InstrumentRecord(record.provider, record.exchange, record.segment,
            record.trading_symbol, record.name, record.instrument_type,
            record.expiry, record.tick_size, record.lot_size)
        if mcx_contract_name_matches(family, exact):
            facts[family].append(McxContractAdmissionFacts(
                family=family, instrument=exact, verified_expiry=None,
                expiry_proof_sha256=None,
                provider_snapshot_identity=snapshot.snapshot_identity,
                provider_record_identity=record.provider_record_identity,
                master_valid_until=None, effective_specification_sha256=None,
                settlement=None, entry_until=None, delivery_start=None,
                broker_entry_until=None,
                snapshot_acquired_at=snapshot.acquired_at,
            ))
    return {family: prepare_mcx_contract_offer(run_identity, family,
        tuple(facts[family]), observed_at=observed_at,
        selection_policy=V1_ADVISORY_SELECTION)
        for family in McxFamily}
