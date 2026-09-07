"""Append-only accounting artifacts; latest is a diagnostic projection only."""
import json
import os
from pathlib import Path
import re
from uuid import uuid4
from kronos.intraday.operation_accounting import (
    DiscoveryOperationAccounting, accounting_bytes, restore_accounting,
)


class DiscoveryOperationAccountingStore:
    def __init__(self, root: Path) -> None:
        if not isinstance(root,Path) or not root.is_absolute() or root == Path("/"):
            raise ValueError("INTRADAY_ACCOUNTING_ROOT_INVALID")
        self.root = root / "native-discovery" / "operation-accounting"

    def _path(self, identity: str) -> Path:
        if not isinstance(identity,str) or re.fullmatch(r"INTRADAY-OPERATION-ACCOUNTING-[A-F0-9]{64}",identity) is None:
            raise ValueError("INTRADAY_ACCOUNTING_IDENTITY_INVALID")
        return self.root / "records" / (identity + ".json")

    def retain(self, value: DiscoveryOperationAccounting) -> Path:
        path = self._path(value.accounting_identity)
        payload = accounting_bytes(value)
        restore_accounting(payload)
        path.parent.mkdir(parents=True,exist_ok=True)
        temp = path.parent / ("." + uuid4().hex + ".tmp")
        try:
            temp.write_bytes(payload)
            try:
                os.link(temp,path)
            except FileExistsError:
                if path.read_bytes() != payload:
                    raise ValueError("INTRADAY_ACCOUNTING_IMMUTABLE_CONFLICT")
        finally:
            temp.unlink(missing_ok=True)
        pointer = self.root / ("latest-" + value.operation_kind + ".json")
        temp = self.root / ("." + uuid4().hex + ".tmp")
        try:
            temp.write_text(json.dumps({"accounting_identity":value.accounting_identity}) + "\n")
            os.replace(temp,pointer)
        finally:
            temp.unlink(missing_ok=True)
        return path

    def load(self, identity: str) -> DiscoveryOperationAccounting:
        try:
            value = restore_accounting(self._path(identity).read_bytes())
        except OSError:
            raise ValueError("INTRADAY_ACCOUNTING_NOT_AVAILABLE") from None
        if value.accounting_identity != identity:
            raise ValueError("INTRADAY_ACCOUNTING_IDENTITY_MISMATCH")
        return value

    def latest(self, kind: str) -> DiscoveryOperationAccounting | None:
        if kind not in {"V2","LEGACY"}:
            raise ValueError("INTRADAY_ACCOUNTING_KIND_INVALID")
        pointer = self.root / ("latest-" + kind + ".json")
        if not pointer.exists():
            return None
        value = self.load(json.loads(pointer.read_bytes())["accounting_identity"])
        if value.operation_kind != kind:
            raise ValueError("INTRADAY_ACCOUNTING_KIND_INVALID")
        return value
