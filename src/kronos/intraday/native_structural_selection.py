"""Exact Native selections: historical V1 contract and commissioned PULLBACK V1.1."""
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re

from kronos.intraday.wo10_futures_contract import PROGRAMME, digest, encoded, moment, number
from kronos.intraday.wo09_persistence import Wo09Store

SCHEMA = "NATIVE_STRUCTURAL_SELECTION_V1"
CONTRACT_VERSION = "1.0.0"
UNAVAILABLE = "STRUCTURAL_CONSTRUCTION_AUTHORITY_NOT_ESTABLISHED"
from kronos.intraday.native_pullback_policy import APPROVED_POLICY
APPROVED_NATIVE_SELECTION_POLICIES = frozenset({APPROVED_POLICY})
COMPLETENESS = frozenset({"COMPLETE_WITH_TARGETS", "COMPLETE_NO_APPLICABLE_FORWARD_TARGETS", "INCOMPLETE"})


def _text(value):
    return type(value) is str and bool(value.strip())


def _validate(d):
    if type(d) is dict and d.get("contract_version") == "1.1.0":
        from kronos.intraday.native_pullback_decision import validate_decision
        return validate_decision(d)
    if type(d) is dict and tuple(d.get(k) for k in ("policy_identity", "policy_version", "policy_checksum")) == APPROVED_POLICY:
        raise ValueError("STRUCTURAL_CONTRACT_AUTHORITY_INVALID")
    keys = {"programme_identity", "contract_version", "policy_identity", "policy_version", "policy_checksum",
            "subject", "direction", "setup_family", "setup_identity", "analysis_cycle", "analysis_boundary",
            "session", "trading_date", "machine_identity", "machine_integrity", "instrument_identity",
            "exact_contract", "roll_lineage", "created_at", "sources", "roles", "original_range_identity",
            "target_population_identity", "target_completeness", "targets"}
    if type(d) is not dict or set(d) != keys:
        raise ValueError("STRUCTURAL_CONTRACT_FIELDS_INVALID")
    nullable = {"exact_contract", "roll_lineage", "original_range_identity"}
    for name in keys - nullable - {"sources", "roles", "targets"}:
        if not _text(d[name]):
            raise ValueError("STRUCTURAL_CONTRACT_VALUE_INVALID:" + name)
    if (d["programme_identity"] != PROGRAMME or d["contract_version"] != CONTRACT_VERSION
            or d["direction"] not in {"LONG", "SHORT"} or d["setup_family"] not in {"PULLBACK", "BREAKOUT"}
            or not re.fullmatch("[a-f0-9]{64}", d["policy_checksum"])):
        raise ValueError("STRUCTURAL_CONTRACT_AUTHORITY_INVALID")
    mcx = d["subject"].startswith("MCX-")
    if (mcx and not all(_text(d[k]) for k in ("exact_contract", "roll_lineage"))
            or not mcx and any(d[k] is not None for k in ("exact_contract", "roll_lineage"))):
        raise ValueError("STRUCTURAL_MCX_BINDING_INVALID")
    boundary = moment(d["analysis_boundary"])
    if moment(d["created_at"]) < boundary:
        raise ValueError("STRUCTURAL_CREATED_BEFORE_BOUNDARY")
    from zoneinfo import ZoneInfo
    if boundary.astimezone(ZoneInfo("Asia/Kolkata")).date().isoformat() != d["trading_date"]:
        raise ValueError("SOURCE_TRADING_DATE_MISMATCH")
    if type(d["sources"]) is not dict or not d["sources"] or not all(_text(k) and _text(v) for k, v in d["sources"].items()):
        raise ValueError("STRUCTURAL_SOURCE_IDENTITIES_REQUIRED")
    required = {"QUALIFICATION_CANDLE_HIGH", "QUALIFICATION_CANDLE_LOW"}
    if d["setup_family"] == "PULLBACK":
        required |= ({"PULLBACK_STRUCTURAL_LOW", "PRIOR_IMPULSE_HIGH"} if d["direction"] == "LONG"
                     else {"PULLBACK_STRUCTURAL_HIGH", "PRIOR_IMPULSE_LOW"})
        if d["original_range_identity"] is not None:
            raise ValueError("STRUCTURAL_RANGE_NOT_APPLICABLE")
    else:
        required |= {"RANGE_HIGH", "RANGE_LOW"}
        if not _text(d["original_range_identity"]):
            raise ValueError("STRUCTURAL_RANGE_IDENTITY_REQUIRED")
    if type(d["roles"]) is not dict or set(d["roles"]) != required:
        raise ValueError("STRUCTURAL_REQUIRED_ROLE_SET_INVALID")
    if type(d["targets"]) is not list or d["target_completeness"] not in COMPLETENESS:
        raise ValueError("TARGET_POPULATION_COMPLETENESS_REQUIRED")
    if ((d["target_completeness"] == "COMPLETE_WITH_TARGETS" and not d["targets"])
            or (d["target_completeness"] == "COMPLETE_NO_APPLICABLE_FORWARD_TARGETS" and d["targets"])):
        raise ValueError("TARGET_POPULATION_COMPLETENESS_CONFLICT")
    from kronos.intraday.wo13_targets import WO13_ELIGIBLE_TARGET_CONSTRAINT_ROLES
    for target in d["targets"]:
        if type(target) is not dict or set(target) != {"role", "reference"} or target["role"] not in WO13_ELIGIBLE_TARGET_CONSTRAINT_ROLES:
            raise ValueError("TARGET_ROLE_INVALID")
    for ref in list(d["roles"].values()) + [t["reference"] for t in d["targets"]]:
        if (type(ref) is not dict or set(ref) != {"source_identity", "candle_identity", "candle_integrity", "field", "price", "structure_identity", "timeframe"}
                or not all(_text(ref[k]) for k in ref) or ref["source_identity"] not in d["sources"]
                or ref["field"] not in {"HIGH", "LOW"}):
            raise ValueError("STRUCTURAL_ROLE_REFERENCE_INVALID")
        number(ref["price"], positive=True)
        from kronos.intraday.contracts import IntradayTimeframe
        IntradayTimeframe(ref["timeframe"])
    qh, ql = (d["roles"]["QUALIFICATION_CANDLE_" + side] for side in ("HIGH", "LOW"))
    if ((qh["source_identity"], qh["candle_identity"], qh["candle_integrity"]) !=
            (ql["source_identity"], ql["candle_identity"], ql["candle_integrity"])):
        raise ValueError("STRUCTURAL_QUALIFICATION_CANDLE_MISMATCH")
    for role, ref in d["roles"].items():
        if ref["field"] != role.rsplit("_", 1)[-1]:
            raise ValueError("STRUCTURAL_ROLE_FIELD_MISMATCH")
        expected_structure = d["original_range_identity"] if role.startswith("RANGE_") else d["setup_identity"]
        if ref["structure_identity"] != expected_structure:
            raise ValueError("STRUCTURAL_SETUP_IDENTITY_MISMATCH")


@dataclass(frozen=True)
class NativeStructuralSelection:
    payload_json: str
    identity: str
    integrity: str

    def __post_init__(self):
        d = json.loads(self.payload_json)
        _validate(d)
        if encoded(d).decode() != self.payload_json or self.integrity != digest(d) or self.identity != SCHEMA + "-" + digest(d):
            raise ValueError("STRUCTURAL_SOURCE_INTEGRITY_INVALID")

    @property
    def data(self):
        return json.loads(self.payload_json)


def create_native_selection(**values):
    """Encode already-selected Native roles. This function grants no approval."""
    raw = encoded(values).decode()
    return NativeStructuralSelection(raw, SCHEMA + "-" + digest(values), digest(values))


class NativeStructuralStore:
    def __init__(self, root):
        self.root = Path(root)

    def retain(self, selection, *, approved_policies, cycle_identity):
        """Native producer seam; exact cycle only, no historical reconstruction."""
        selection.__post_init__()
        d = selection.data
        if (tuple(d[k] for k in ("policy_identity", "policy_version", "policy_checksum")) not in approved_policies
                or d["analysis_cycle"] != cycle_identity):
            raise ValueError(UNAVAILABLE)
        Wo09Store._retain(self.root / "records" / (selection.identity + ".json"), encoded(asdict(selection)))
        # One selected setup per exact machine source; competing selections fail closed.
        Wo09Store._retain(self.root / "bindings" / (digest(d["machine_identity"]) + ".json"),
                          encoded({"machine_identity": d["machine_identity"], "selection_identity": selection.identity}))
        return selection

    def load(self, identity):
        if not isinstance(identity, str) or not re.fullmatch(SCHEMA + "-[a-f0-9]{64}", identity):
            raise ValueError("STRUCTURAL_IDENTITY_INVALID")
        item = NativeStructuralSelection(**json.loads((self.root / "records" / (identity + ".json")).read_bytes()))
        if item.identity != identity:
            raise ValueError("STRUCTURAL_SOURCE_INTEGRITY_INVALID")
        return item

    def bound_identity(self, machine_identity):
        path = self.root / "bindings" / (digest(machine_identity) + ".json")
        if not path.exists():
            return None
        d = json.loads(path.read_bytes())
        if set(d) != {"machine_identity", "selection_identity"} or d["machine_identity"] != machine_identity:
            raise ValueError("STRUCTURAL_SOURCE_INTEGRITY_INVALID")
        return d["selection_identity"]


class NativeStructuralLoader:
    def __init__(self, store, source_loader=None, *, approved_policies=APPROVED_NATIVE_SELECTION_POLICIES):
        self.store, self.source_loader = store, source_loader
        self.approved_policies = frozenset(approved_policies)

    def load(self, handoff, *, now):
        handoff.__post_init__()
        identities = {v for source in handoff.machine_evidence_identities
                      if (v := self.store.bound_identity(source)) is not None}
        if not identities:
            raise ValueError(UNAVAILABLE)
        if len(identities) != 1:
            raise ValueError("STRUCTURAL_SELECTION_AMBIGUOUS")
        item = self.store.load(identities.pop()); d = item.data
        if tuple(d[k] for k in ("policy_identity", "policy_version", "policy_checksum")) not in self.approved_policies:
            raise ValueError(UNAVAILABLE)
        for key, expected in (("subject", handoff.canonical_subject_identity), ("direction", handoff.direction),
                ("session", handoff.session_identity), ("analysis_boundary", handoff.analysis_boundary),
                ("exact_contract", handoff.exact_mcx_contract_identity), ("roll_lineage", handoff.exact_mcx_roll_lineage),
                ("machine_integrity", handoff.machine_evidence_integrity)):
            from kronos.intraday.wo10_futures_contract import normalize
            # An explicit negative caused by missing MCX binding grants no
            # contract authority. Consume that negative without fabricating it.
            if (d.get("contract_version")=="1.1.0" and d.get("result")=="NOT_ESTABLISHED"
                    and "MCX_CONTRACT_BINDING_INVALID" in d.get("reasons", [])
                    and key in {"exact_contract", "roll_lineage"} and d[key] is None):
                continue
            if d[key] != normalize(expected):
                raise ValueError("SOURCE_" + key.upper() + "_MISMATCH")
        if (d["machine_identity"] not in handoff.machine_evidence_identities or moment(d["created_at"]) > moment(now)
                or moment(d["created_at"]) > moment(handoff.created_at)):
            raise ValueError("STRUCTURAL_SOURCE_BINDING_INVALID")
        if d["contract_version"] == "1.1.0":
            from kronos.intraday.native_pullback_decision import load_decision_source
            load_decision_source(self.store, item, handoff)
            return item
        if d["target_completeness"] == "INCOMPLETE":
            raise ValueError("TARGET_POPULATION_INCOMPLETE")
        if self.source_loader is None:
            raise ValueError("STRUCTURAL_EXACT_SOURCE_LOADER_UNAVAILABLE")
        sources = {}
        for identity, integrity in d["sources"].items():
            source = self.source_loader(identity)
            if digest(source) != integrity or source["identity"] != identity:
                raise ValueError("STRUCTURAL_SOURCE_INTEGRITY_INVALID")
            for key in ("subject", "direction", "analysis_cycle", "analysis_boundary", "session", "trading_date", "exact_contract", "roll_lineage", "machine_identity", "machine_integrity"):
                if source[key] != d[key]:
                    raise ValueError("SOURCE_" + key.upper() + "_MISMATCH")
            sources[identity] = source
        for role, ref in list(d["roles"].items()) + [(t["role"], t["reference"]) for t in d["targets"]]:
            # Exact lookup only. The Native source has already selected every role.
            candle = sources[ref["source_identity"]]["candles"][ref["candle_identity"]]
            if digest(candle) != ref["candle_integrity"]:
                raise ValueError("STRUCTURAL_CANDLE_INTEGRITY_INVALID")
            if (candle["subject"] != d["subject"] or candle["session"] != d["session"]
                    or candle["trading_date"] != d["trading_date"]):
                raise ValueError("SOURCE_CANDLE_CONTEXT_MISMATCH")
            if (candle["completion"] != "COMPLETE" or moment(candle["start"]) >= moment(candle["end"])
                    or moment(candle["available_at"]) != moment(candle["end"])
                    or moment(candle["end"]) > moment(d["analysis_boundary"])):
                raise ValueError("SOURCE_CANDLE_NOT_COMPLETED_AT_BOUNDARY")
            if candle["timeframe"] != ref["timeframe"] or (role.startswith("QUALIFICATION_") and candle["timeframe"] != "15M"):
                raise ValueError("SOURCE_QUALIFICATION_TIMEFRAME_INVALID")
            if number(candle[ref["field"]]) != number(ref["price"]):
                raise ValueError("SOURCE_ROLE_PRICE_MISMATCH")
        return item
