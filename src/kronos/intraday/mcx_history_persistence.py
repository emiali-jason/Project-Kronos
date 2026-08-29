"""Append-only production persistence for retained MCX contract candles."""

from __future__ import annotations

from pathlib import Path
from threading import RLock
from uuid import uuid4

from kronos.intraday.mcx_history import (
    McxContinuousAnalyticalView,
    McxHistoryError,
    RetainedMcxContractCandle,
    build_continuous_analytical_view,
    parse_retained_mcx_candle,
    retained_mcx_candle_bytes,
)


MCX_HISTORY_NAMESPACE = "mcx-contract-history-v1"


class McxContractHistoryStore:
    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path) or not root.is_absolute() or root == Path("/"):
            raise ValueError("MCX_HISTORY_ROOT_INVALID")
        self._root = root / MCX_HISTORY_NAMESPACE
        self._lock = RLock()

    def retain(self, value: RetainedMcxContractCandle) -> Path:
        if type(value) is not RetainedMcxContractCandle:
            raise McxHistoryError("MCX_RETAINED_CANDLE_INVALID")
        path = self.path_for(value)
        encoded = retained_mcx_candle_bytes(value)
        with self._lock:
            if path.exists():
                if path.read_bytes() != encoded:
                    raise McxHistoryError("MCX_HISTORY_IMMUTABILITY_CONFLICT")
                return path
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
            try:
                with temporary.open("xb") as stream:
                    stream.write(encoded)
                    stream.flush()
                try:
                    path.hardlink_to(temporary)
                except FileExistsError:
                    if path.read_bytes() != encoded:
                        raise McxHistoryError("MCX_HISTORY_IMMUTABILITY_CONFLICT")
            finally:
                temporary.unlink(missing_ok=True)
        return path

    def retain_many(self, values: tuple[RetainedMcxContractCandle, ...]) -> tuple[Path, ...]:
        if any(type(item) is not RetainedMcxContractCandle for item in values):
            raise McxHistoryError("MCX_RETENTION_INPUT_INVALID")
        return tuple(self.retain(item) for item in values)

    def load(
        self,
        *,
        canonical_subject_identity: str,
        canonical_contract_identity: str,
        timeframe: str,
        candle_identity: str,
    ) -> RetainedMcxContractCandle:
        path = self._path(
            canonical_subject_identity, canonical_contract_identity,
            timeframe, candle_identity,
        )
        value = parse_retained_mcx_candle(path.read_bytes())
        if (
            value.canonical_subject_identity != canonical_subject_identity
            or value.canonical_contract_identity != canonical_contract_identity
            or value.timeframe.value != timeframe
            or value.candle_identity != candle_identity
        ):
            raise McxHistoryError("MCX_HISTORY_IDENTITY_MISMATCH")
        return value

    def load_contract(
        self,
        *,
        canonical_subject_identity: str,
        canonical_contract_identity: str,
    ) -> tuple[RetainedMcxContractCandle, ...]:
        base = self._root / canonical_subject_identity / canonical_contract_identity
        values = tuple(
            parse_retained_mcx_candle(path.read_bytes())
            for path in sorted(base.glob("*/*.json"))
        )
        if not values or any(
            item.canonical_subject_identity != canonical_subject_identity
            or item.canonical_contract_identity != canonical_contract_identity
            for item in values
        ):
            raise McxHistoryError("MCX_HISTORY_CONTRACT_UNAVAILABLE")
        return tuple(sorted(values, key=lambda item: (item.timeframe.value, item.candle_start)))

    def reconstruct(
        self,
        *,
        canonical_subject_identity: str,
        contract_identities: tuple[str, ...],
    ) -> McxContinuousAnalyticalView:
        retained: list[RetainedMcxContractCandle] = []
        for contract in contract_identities:
            try:
                retained.extend(self.load_contract(
                    canonical_subject_identity=canonical_subject_identity,
                    canonical_contract_identity=contract,
                ))
            except McxHistoryError as error:
                if str(error) != "MCX_HISTORY_CONTRACT_UNAVAILABLE":
                    raise
        return build_continuous_analytical_view(
            canonical_subject_identity=canonical_subject_identity,
            contract_identities=contract_identities,
            candles=tuple(retained),
        )

    def path_for(self, value: RetainedMcxContractCandle) -> Path:
        return self._path(
            value.canonical_subject_identity,
            value.canonical_contract_identity,
            value.timeframe.value,
            value.candle_identity,
        )

    def _path(self, subject: str, contract: str, timeframe: str, candle: str) -> Path:
        if not all(_component(item) for item in (subject, contract, timeframe, candle)):
            raise McxHistoryError("MCX_HISTORY_PATH_INVALID")
        return self._root / subject / contract / timeframe / f"{candle}.json"


def _component(value: object) -> bool:
    return (
        type(value) is str and bool(value) and value == value.strip()
        and value not in {".", ".."} and "/" not in value and "\\" not in value
    )


__all__ = ["MCX_HISTORY_NAMESPACE", "McxContractHistoryStore"]
