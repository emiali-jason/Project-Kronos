"""Immutable, non-actionable MCX construction evidence.

This is a durable prepared proposal, not the commissioned Swing TradePlanRecord.
No current pointer, Sponsor decision or entry authority is written here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import RLock
from uuid import uuid4

from kronos.swing.v1.mcx_contract_profile import McxFamily
from kronos.swing.v1.mcx_step31_construction import (
    McxContractProofPrerequisites, McxPendingPlan, check_mcx_pending_entry,
)
from kronos.swing.v1.mcx_step31_prepared_handoff import (
    MCX_STEP31_COMMISSIONING, McxStep31PreparedHandoff,
)


SCHEMA = "KRONOS-SWING-MCX-PREPARED-PLAN-EVIDENCE-V1"
AUTHORITY = "NON_ACTIONABLE_PREPARATION_ONLY"


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True, slots=True)
class McxPreparedPlanEvidence:
    plan_id: str
    run_identity: str
    manifest_sha256: str
    family: McxFamily
    assessment_sha256: str
    contract_symbol: str
    expiry: str
    handoff_integrity_sha256: str
    receipt_integrity_sha256: str
    promotion_integrity_sha256: str
    completed_one_hour_sha256: str
    lots: int
    notional: str
    stop_risk: str
    prepared_at: str
    authority: str = AUTHORITY
    commissioning_state: str = MCX_STEP31_COMMISSIONING

    def __post_init__(self) -> None:
        if (
            type(self.family) is not McxFamily
            or type(self.lots) is not int or self.lots <= 0
            or not self.run_identity or not self.contract_symbol or not self.expiry
            or self.authority != AUTHORITY
            or self.commissioning_state != MCX_STEP31_COMMISSIONING
            or any(len(value) != 64 or any(c not in "0123456789abcdef" for c in value)
                   for value in (self.plan_id, self.manifest_sha256,
                                 self.assessment_sha256, self.handoff_integrity_sha256,
                                 self.receipt_integrity_sha256,
                                 self.promotion_integrity_sha256,
                                 self.completed_one_hour_sha256))
            or self.plan_id != self.digest()
        ):
            raise ValueError("MCX_PREPARED_PLAN_EVIDENCE_INVALID")

    def _unsigned(self) -> dict[str, object]:
        return {key: value.value if isinstance(value, McxFamily) else value
                for key, value in asdict(self).items() if key != "plan_id"}

    def digest(self) -> str:
        return sha256(_canonical({"schema": SCHEMA, "record": self._unsigned()})).hexdigest()

    @classmethod
    def create(cls, pending: McxPendingPlan, handoff: McxStep31PreparedHandoff):
        if type(pending) is not McxPendingPlan or type(handoff) is not McxStep31PreparedHandoff:
            raise ValueError("MCX_PREPARED_PLAN_BINDING_INVALID")
        bound = handoff.bound
        if (
            pending.run_identity != bound.run_identity
            or pending.assessment_sha256 != bound.assessment_sha256
            or pending.handoff_integrity_sha256 != handoff.integrity_sha256
            or (pending.family, pending.trading_symbol, pending.expiry)
            != (bound.family, bound.derivative_symbol, bound.derivative_expiry)
            or pending.entry_authority
            or pending.commissioning_state != MCX_STEP31_COMMISSIONING
        ):
            raise ValueError("MCX_PREPARED_PLAN_BINDING_INVALID")
        values = dict(
            run_identity=bound.run_identity, manifest_sha256=bound.manifest_sha256,
            family=bound.family, assessment_sha256=bound.assessment_sha256,
            contract_symbol=bound.derivative_symbol, expiry=bound.derivative_expiry,
            handoff_integrity_sha256=handoff.integrity_sha256,
            receipt_integrity_sha256=bound.receipt_integrity_sha256,
            promotion_integrity_sha256=bound.promotion_integrity_sha256,
            completed_one_hour_sha256=bound.completed_one_hour_sha256,
            lots=pending.risk.lots, notional=str(pending.risk.notional),
            stop_risk=str(pending.risk.stop_risk),
            prepared_at=pending.prepared_at.isoformat(),
        )
        unsigned = dict(values, authority=AUTHORITY,
                        commissioning_state=MCX_STEP31_COMMISSIONING)
        encoded = {key: value.value if isinstance(value, McxFamily) else value
                   for key, value in unsigned.items()}
        identity = sha256(_canonical({"schema": SCHEMA, "record": encoded})).hexdigest()
        return cls(plan_id=identity, **values)


class LocalMcxPreparedPlanStore:
    """Append-only evidence; does not create a Trade Window current selection."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser()
        if not self.root.is_absolute():
            raise ValueError("MCX_PREPARED_PLAN_STORE_INVALID")
        self._lock = RLock()

    def _path(self, record: McxPreparedPlanEvidence) -> Path:
        if "/" in record.run_identity or ".." in record.run_identity:
            raise ValueError("MCX_PREPARED_PLAN_RUN_INVALID")
        return self.root / record.run_identity / record.family.value / (record.plan_id + ".json")

    def retain(self, record: McxPreparedPlanEvidence) -> Path:
        if type(record) is not McxPreparedPlanEvidence:
            raise TypeError("MCX_PREPARED_PLAN_EVIDENCE_INVALID")
        path = self._path(record)
        payload = _canonical({"schema": SCHEMA, "record": {
            "plan_id": record.plan_id, **record._unsigned(),
        }})
        with self._lock:
            if path.exists():
                if path.is_symlink() or path.read_bytes() != payload:
                    raise ValueError("MCX_PREPARED_PLAN_IMMUTABLE")
                return path
            path.parent.mkdir(parents=True, exist_ok=True)
            if self.root.is_symlink() or path.parent.is_symlink():
                raise ValueError("MCX_PREPARED_PLAN_STORE_INVALID")
            temporary = path.parent / ("." + record.plan_id + "." + uuid4().hex + ".pending")
            try:
                descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(payload)
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
        return path

    def load(self, path: Path) -> McxPreparedPlanEvidence:
        path = Path(path)
        if path.is_symlink() or not path.is_relative_to(self.root):
            raise ValueError("MCX_PREPARED_PLAN_INTEGRITY_INVALID")
        try:
            value = json.loads(path.read_bytes())
            if value["schema"] != SCHEMA:
                raise ValueError
            data = value["record"]
            record = McxPreparedPlanEvidence(**(data | {"family": McxFamily(data["family"])}))
            if path != self._path(record) or path.read_bytes() != _canonical(value):
                raise ValueError
            return record
        except (KeyError, OSError, TypeError, ValueError) as error:
            raise ValueError("MCX_PREPARED_PLAN_INTEGRITY_INVALID") from error


def mcx_sponsor_admission_reasons(
    record: McxPreparedPlanEvidence, pending: McxPendingPlan,
    current: McxStep31PreparedHandoff, proof: McxContractProofPrerequisites,
    *, observed_at: datetime,
) -> tuple[str, ...]:
    """A durable proposal cannot enter the existing Sponsor position workflow."""

    try:
        if (
            type(record) is not McxPreparedPlanEvidence
            or type(pending) is not McxPendingPlan
            or record.plan_id != McxPreparedPlanEvidence.create(pending, current).plan_id
        ):
            raise ValueError("MCX_PREPARED_PLAN_CURRENT_BINDING_INVALID")
    except (AttributeError, TypeError, ValueError):
        return ("MCX_PREPARED_PLAN_CURRENT_BINDING_INVALID", MCX_STEP31_COMMISSIONING)
    try:
        return check_mcx_pending_entry(pending, current, proof, observed_at=observed_at)
    except (TypeError, ValueError):
        return ("MCX_SPONSOR_ADMISSION_INPUT_INVALID", MCX_STEP31_COMMISSIONING)
