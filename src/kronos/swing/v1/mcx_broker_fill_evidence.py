"""Isolated, immutable Sponsor-submitted MCX broker fill byte capture.

Hash and binding verification prove retention, not broker authenticity. No
production composition uses this store or grants entry authority from it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import RLock
from uuid import uuid4

from kronos.swing.v1.mcx_live_attestation import McxLiveFillAttestation
from kronos.swing.v1.mcx_contract_lifecycle import McxHistoricalContractBinding
from kronos.swing.v1.native_active_trade_lifecycle import (
    ActiveLifecyclePosition, TradeClosureRecord,
)


SCHEMA = "KRONOS-SWING-MCX-BROKER-FILL-CAPTURE-V1"
MAX_BYTES = 1024 * 1024
ORIGIN = "SPONSOR_SUBMITTED_UNVERIFIED"


def _payload(value: dict[str, object]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


@dataclass(frozen=True, slots=True)
class McxBrokerFillCapture:
    position_id: str
    plan_id: str
    attestation_sha256: str
    evidence_id: str
    evidence_sha256: str
    evidence_bytes: int
    contract_symbol: str
    expiry: str
    lots: int
    fill_price: Decimal
    fill_at: datetime
    origin: str = ORIGIN

    def __post_init__(self) -> None:
        if (not self.position_id or "/" in self.position_id or ".." in self.position_id
                or not self.plan_id or "/" in self.plan_id or ".." in self.plan_id
                or not self.evidence_id
                or "/" in self.evidence_id or ".." in self.evidence_id
                or any(len(value) != 64 or any(c not in "0123456789abcdef" for c in value)
                       for value in (self.attestation_sha256, self.evidence_sha256))
                or not 0 < self.evidence_bytes <= MAX_BYTES
                or not self.contract_symbol or not self.expiry
                or type(self.lots) is not int or self.lots <= 0
                or type(self.fill_price) is not Decimal
                or not self.fill_price.is_finite() or self.fill_price <= 0
                or self.fill_at.tzinfo is None or self.origin != ORIGIN):
            raise ValueError("MCX_BROKER_FILL_CAPTURE_INVALID")

    @classmethod
    def from_attestation(cls, position_id: str,
                         attestation: McxLiveFillAttestation,
                         original_bytes: bytes) -> "McxBrokerFillCapture":
        if type(original_bytes) is not bytes or not 0 < len(original_bytes) <= MAX_BYTES:
            raise ValueError("MCX_BROKER_FILL_BYTES_INVALID")
        return cls(position_id, attestation.plan_id,
                   attestation.integrity_sha256, attestation.broker_evidence_id,
                   sha256(original_bytes).hexdigest(), len(original_bytes),
                   attestation.contract_symbol, attestation.expiry,
                   attestation.lots, attestation.fill_price, attestation.fill_at)


class LocalMcxBrokerFillEvidenceStore:
    """Retain original bytes and typed binding without claiming authentication."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser()
        if not self.root.is_absolute():
            raise ValueError("MCX_BROKER_FILL_STORE_INVALID")
        self._lock = RLock()

    def _paths(self, capture: McxBrokerFillCapture) -> tuple[Path, Path]:
        directory = self.root / capture.position_id
        return directory / (capture.evidence_id + ".bin"), directory / (capture.evidence_id + ".json")

    @staticmethod
    def _retain(path: Path, value: bytes) -> None:
        if path.exists():
            if path.is_symlink() or path.read_bytes() != value:
                raise ValueError("MCX_BROKER_FILL_EVIDENCE_IMMUTABLE")
            return
        temporary = path.parent / ("." + uuid4().hex + ".pending")
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(value)
                handle.flush()
                os.fsync(handle.fileno())
            os.link(temporary, path, follow_symlinks=False)
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            temporary.unlink(missing_ok=True)

    def capture(self, capture: McxBrokerFillCapture,
                original_bytes: bytes) -> None:
        if (type(capture) is not McxBrokerFillCapture
                or type(original_bytes) is not bytes
                or len(original_bytes) != capture.evidence_bytes
                or sha256(original_bytes).hexdigest() != capture.evidence_sha256):
            raise ValueError("MCX_BROKER_FILL_BYTES_INVALID")
        byte_path, record_path = self._paths(capture)
        fields = asdict(capture)
        fields["fill_price"] = str(capture.fill_price)
        fields["fill_at"] = capture.fill_at.isoformat()
        record_bytes = _payload({"schema": SCHEMA, **fields})
        with self._lock:
            if self.root.is_symlink():
                raise ValueError("MCX_BROKER_FILL_STORE_INVALID")
            byte_path.parent.mkdir(parents=True, exist_ok=True)
            if byte_path.parent.is_symlink():
                raise ValueError("MCX_BROKER_FILL_STORE_INVALID")
            self._retain(byte_path, original_bytes)
            self._retain(record_path, record_bytes)

    def verify(self, capture: McxBrokerFillCapture,
               attestation: McxLiveFillAttestation,
               position: ActiveLifecyclePosition,
               binding: McxHistoricalContractBinding) -> None:
        if (type(capture) is not McxBrokerFillCapture
                or type(attestation) is not McxLiveFillAttestation
                or type(position) is not ActiveLifecyclePosition
                or type(binding) is not McxHistoricalContractBinding
                or (position.mcx_quantity is None
                    and position.mcx_v1_contract_symbol is None)
                or (position.mcx_quantity is not None and
                    position.mcx_quantity.provider_order_quantity
                    != attestation.provider_order_quantity)
                or (position.mcx_v1_contract_symbol is not None and
                    (not attestation.v1_manual
                     or attestation.provider_order_quantity is not None
                     or position.mcx_v1_contract_symbol
                        != attestation.contract_symbol))
                or position.canonical_instrument != binding.family.value
                or attestation.family is not binding.family
                or (binding.position_id, binding.trade_plan_hash,
                    binding.decision_id, binding.instrument.trading_symbol,
                    binding.instrument.expiry.isoformat())
                   != (position.position_id, position.trade_plan_hash,
                       position.decision_id, capture.contract_symbol,
                       capture.expiry)
                or (capture.position_id, capture.plan_id,
                    capture.attestation_sha256, capture.evidence_id,
                    capture.evidence_sha256, capture.contract_symbol,
                    capture.expiry, capture.lots, capture.fill_price,
                    capture.fill_at)
                   != (position.position_id, position.trade_plan_id,
                       attestation.integrity_sha256,
                       attestation.broker_evidence_id,
                       attestation.broker_evidence_sha256,
                       attestation.contract_symbol, attestation.expiry,
                       position.lots, position.actual_entry,
                       position.entry_timestamp)
                or position.trade_plan_hash != attestation.plan_sha256):
            raise ValueError("MCX_BROKER_FILL_BINDING_INVALID")
        byte_path, record_path = self._paths(capture)
        if byte_path.is_symlink() or record_path.is_symlink():
            raise ValueError("MCX_BROKER_FILL_EVIDENCE_INVALID")
        try:
            original = byte_path.read_bytes()
            record = record_path.read_bytes()
            fields = asdict(capture)
            fields["fill_price"] = str(capture.fill_price)
            fields["fill_at"] = capture.fill_at.isoformat()
            if (len(original) != capture.evidence_bytes
                    or sha256(original).hexdigest() != capture.evidence_sha256
                    or record != _payload({"schema": SCHEMA, **fields})):
                raise ValueError
        except (OSError, ValueError) as error:
            raise ValueError("MCX_BROKER_FILL_EVIDENCE_INVALID") from error

    def verify_exit(self, capture: McxBrokerFillCapture,
                    attestation: McxLiveFillAttestation,
                    closure: TradeClosureRecord,
                    binding: McxHistoricalContractBinding) -> None:
        """Bind retained exit bytes to the same historical future and closure."""
        if (type(capture) is not McxBrokerFillCapture
                or type(attestation) is not McxLiveFillAttestation
                or type(closure) is not TradeClosureRecord
                or type(binding) is not McxHistoricalContractBinding
                or (closure.mcx_quantity is None
                    and closure.mcx_v1_contract_symbol is None)
                or (closure.mcx_quantity is not None and
                    closure.mcx_quantity.provider_order_quantity
                    != attestation.provider_order_quantity)
                or (closure.mcx_v1_contract_symbol is not None and
                    (not attestation.v1_manual
                     or attestation.provider_order_quantity is not None
                     or closure.mcx_v1_contract_symbol
                        != attestation.contract_symbol))
                or closure.instrument != binding.family.value
                or attestation.family is not binding.family
                or (capture.position_id, capture.plan_id,
                    capture.attestation_sha256, capture.evidence_id,
                    capture.evidence_sha256, capture.contract_symbol,
                    capture.expiry, capture.lots, capture.fill_price,
                    capture.fill_at)
                   != (closure.position_id, closure.trade_plan_id,
                       attestation.integrity_sha256,
                       attestation.broker_evidence_id,
                       attestation.broker_evidence_sha256,
                       binding.instrument.trading_symbol,
                       binding.instrument.expiry.isoformat(),
                       closure.lots, closure.actual_exit,
                       closure.exit_timestamp)
                or binding.position_id != closure.position_id
                or binding.trade_plan_hash != closure.trade_plan_hash
                or attestation.plan_sha256 != closure.trade_plan_hash):
            raise ValueError("MCX_BROKER_FILL_BINDING_INVALID")
        byte_path, record_path = self._paths(capture)
        if byte_path.is_symlink() or record_path.is_symlink():
            raise ValueError("MCX_BROKER_FILL_EVIDENCE_INVALID")
        try:
            original = byte_path.read_bytes()
            record = record_path.read_bytes()
            fields = asdict(capture)
            fields["fill_price"] = str(capture.fill_price)
            fields["fill_at"] = capture.fill_at.isoformat()
            if (len(original) != capture.evidence_bytes
                    or sha256(original).hexdigest() != capture.evidence_sha256
                    or record != _payload({"schema": SCHEMA, **fields})):
                raise ValueError
        except (OSError, ValueError) as error:
            raise ValueError("MCX_BROKER_FILL_EVIDENCE_INVALID") from error
