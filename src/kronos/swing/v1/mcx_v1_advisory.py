"""MCX V1 close-confirmed advice, explicitly distinct from P32-002.

This record reports two completed candle closes. It asserts neither intrabar
trade continuity nor a fill. The commissioning gate is owned by composition.
"""

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import RLock
from uuid import uuid4

from kronos.swing.v1.native_entry_timing import _values_digest


ADVISORY_RULE_ID = "SWING-MCX-COMPLETED-1H-ADVISORY-V1"
ADVISORY_SCHEMA = "KRONOS-MCX-CLOSE-CONFIRMED-ADVISORY-V1"


class McxAdvisoryState(str, Enum):
    LONG_CONFIRMED = "LONG_ADVISORY_CONFIRMED"
    SHORT_CONFIRMED = "SHORT_ADVISORY_CONFIRMED"


@dataclass(frozen=True, slots=True)
class McxV1AdvisoryOutcome:
    advisory_id: str
    native_run_identity: str
    canonical_instrument: str
    contract_symbol: str
    expiry: str
    provider_token: int
    session_identity: str
    direction: str
    kr370_source_identity: str
    trade_plan_id: str
    trade_plan_sha256: str
    risk_result_id: str
    monitoring_binding_id: str
    observation_boundary: datetime
    source_observation_ids: tuple[str, ...]
    source_sequence: tuple[int, ...]
    state: McxAdvisoryState
    occurred_at: datetime
    confirmed_at: datetime
    provenance: tuple[str, ...]
    integrity_sha256: str
    reason: str = "MCX_COMPLETED_1H_ADVISORY_CLOSE_CROSS"
    rule_id: str = ADVISORY_RULE_ID
    schema: str = ADVISORY_SCHEMA
    intrabar_trade_continuity: str = "UNVERIFIED"
    broker_authority: str = "NONE"

    def __post_init__(self):
        values = asdict(self)
        values.pop("integrity_sha256")
        if (not all((self.advisory_id, self.native_run_identity,
                     self.canonical_instrument, self.contract_symbol, self.expiry,
                     self.provider_token, self.session_identity,
                     self.kr370_source_identity, self.trade_plan_id,
                     self.risk_result_id, self.monitoring_binding_id))
                or not self.advisory_id.startswith("MCX-ADVISORY-")
                or self.direction not in {"LONG", "SHORT"}
                or type(self.provider_token) is not int or self.provider_token <= 0
                or len(self.trade_plan_sha256) != 64
                or self.state is not (McxAdvisoryState.LONG_CONFIRMED
                    if self.direction == "LONG" else McxAdvisoryState.SHORT_CONFIRMED)
                or self.observation_boundary.tzinfo is None
                or self.occurred_at != self.observation_boundary
                or self.confirmed_at.tzinfo is None
                or self.confirmed_at < self.occurred_at
                or len(self.source_observation_ids) != 2
                or len(set(self.source_observation_ids)) != 2
                or len(self.source_sequence) != 2
                or self.source_sequence[0] >= self.source_sequence[1]
                or self.schema != ADVISORY_SCHEMA or self.rule_id != ADVISORY_RULE_ID
                or self.reason != "MCX_COMPLETED_1H_ADVISORY_CLOSE_CROSS"
                or self.intrabar_trade_continuity != "UNVERIFIED"
                or self.broker_authority != "NONE"
                or ADVISORY_RULE_ID not in self.provenance
                or self.integrity_sha256 != _values_digest(values)):
            raise ValueError("MCX_V1_ADVISORY_INVALID")

    @property
    def entry_outcome_id(self):
        """Legacy record-reference field; identity remains explicitly ADVISORY."""
        return self.advisory_id

    @classmethod
    def create(cls, **values):
        values.update(reason="MCX_COMPLETED_1H_ADVISORY_CLOSE_CROSS",
                      rule_id=ADVISORY_RULE_ID, schema=ADVISORY_SCHEMA,
                      intrabar_trade_continuity="UNVERIFIED", broker_authority="NONE")
        return cls(**values, integrity_sha256=_values_digest(values))


class LocalMcxV1AdvisoryStore:
    """One immutable advisory per exact plan, with no P32-002 pointer writes."""

    def __init__(self, root: Path):
        self.root = Path(root)
        if not self.root.is_absolute() or self.root == Path("/"):
            raise ValueError("MCX_ADVISORY_STORE_INVALID")
        self._lock = RLock()

    def _path(self, plan_id):
        if not plan_id:
            raise ValueError("MCX_ADVISORY_PLAN_INVALID")
        return self.root / (sha256(plan_id.encode()).hexdigest() + ".json")

    def retain_current(self, record: McxV1AdvisoryOutcome):
        if type(record) is not McxV1AdvisoryOutcome:
            raise ValueError("MCX_ADVISORY_TYPE_REQUIRED")
        fields = asdict(record)
        for name in ("occurred_at", "observation_boundary", "confirmed_at"):
            fields[name] = fields[name].isoformat()
        fields["state"] = record.state.value
        payload = json.dumps(fields, sort_keys=True, separators=(",", ":")).encode()
        with self._lock:
            path = self._path(record.trade_plan_id)
            if self.root.is_symlink() or path.is_symlink():
                raise ValueError("MCX_ADVISORY_STORE_INVALID")
            if path.exists():
                if path.read_bytes() != payload:
                    raise ValueError("MCX_ADVISORY_REPLAY_CONFLICT")
                directory = os.open(self.root, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
                return
            self.root.mkdir(parents=True, exist_ok=True)
            temporary = self.root / ("." + uuid4().hex + ".pending")
            try:
                descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                try:
                    os.link(temporary, path, follow_symlinks=False)
                except FileExistsError:
                    if path.is_symlink() or path.read_bytes() != payload:
                        raise ValueError("MCX_ADVISORY_REPLAY_CONFLICT") from None
                directory = os.open(self.root, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            finally:
                temporary.unlink(missing_ok=True)

    def load_for_plan(self, plan_id):
        path = self._path(plan_id)
        if path.is_symlink() or self.root.is_symlink():
            raise ValueError("MCX_ADVISORY_STORE_INVALID")
        if not path.exists():
            return None
        fields = json.loads(path.read_bytes())
        for name in ("occurred_at", "observation_boundary", "confirmed_at"):
            fields[name] = datetime.fromisoformat(fields[name])
        for name in ("source_observation_ids", "source_sequence", "provenance"):
            fields[name] = tuple(fields[name])
        fields["state"] = McxAdvisoryState(fields["state"])
        record = McxV1AdvisoryOutcome(**fields)
        if record.trade_plan_id != plan_id:
            raise ValueError("MCX_ADVISORY_PLAN_MISMATCH")
        return record
