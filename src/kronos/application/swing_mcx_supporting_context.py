"""Application boundary for MCX-CONTEXT-01 supporting evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from kronos.market.calendar import MarketCalendarPublisher
from kronos.swing.v1.mcx_supporting_context import (
    ContextAvailability,
    MCX_CONTEXT_INSTRUMENT_FAMILIES,
    McxContextFamily,
    McxContextSlot,
    McxSupportingContextRecord,
    McxSupportingContextStore,
    build_context_record,
)
from kronos.swing.v1.mcx_supporting_context_pdf import (
    McxContextPdfTransport,
    McxContextQuestionPack,
    McxContextStagedImage,
)
from kronos.swing.v1.pdf_visual_review import PdfReviewTransportError


_IST = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True, slots=True)
class McxContextFamilyStatus:
    family: McxContextFamily
    availability: ContextAvailability
    revision: int | None
    imported_at: datetime | None
    image_staged: bool


@dataclass(frozen=True, slots=True)
class McxContextSlotStatus:
    slot: McxContextSlot
    families: tuple[McxContextFamilyStatus, McxContextFamilyStatus]
    question_pack: McxContextQuestionPack | None
    last_error: str | None


@dataclass(frozen=True, slots=True)
class McxSupportingContextSnapshot:
    trading_date: date
    trading_date_required: bool
    slots: tuple[McxContextSlotStatus, McxContextSlotStatus]


class McxSupportingContextWorkflow:
    def __init__(
        self, store: McxSupportingContextStore, transport: McxContextPdfTransport,
        *, calendar: MarketCalendarPublisher | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.store = store; self.transport = transport
        self.calendar = calendar or MarketCalendarPublisher(); self._clock = clock
        self._errors: dict[McxContextSlot, str] = {}

    def governed_trading_date(self) -> tuple[date, bool]:
        now = self._now(); day = now.astimezone(_IST).date()
        return day, self.calendar.is_trading_date("MCX", day)

    def stage_image(
        self, *, slot: McxContextSlot, family: McxContextFamily,
        content_type: str, payload: bytes,
    ) -> McxContextStagedImage:
        day, required = self.governed_trading_date()
        if not required: raise ValueError("MCX_CONTEXT_NON_TRADING_DATE")
        result = self.transport.stage_image(
            trading_date=day, slot=slot, family=family,
            content_type=content_type, payload=payload,
        )
        self._errors.pop(slot, None); return result

    def create_question_pack(self, slot: McxContextSlot) -> McxContextQuestionPack:
        day, required = self.governed_trading_date()
        if not required: raise ValueError("MCX_CONTEXT_NON_TRADING_DATE")
        try: result = self.transport.generate(day, slot)
        except (PdfReviewTransportError, ValueError) as error:
            self._errors[slot] = str(error); raise
        self._errors.pop(slot, None); return result

    def upload_answer(self, slot: McxContextSlot) -> tuple[McxSupportingContextRecord, ...]:
        day, required = self.governed_trading_date()
        if not required: raise ValueError("MCX_CONTEXT_NON_TRADING_DATE")
        pack = self.transport.store.current(day, slot)
        if pack is None: raise ValueError("MCX_CONTEXT_QUESTION_PACK_REQUIRED")
        try:
            answer = self.transport.find_and_validate(pack); imported_at = self._now()
            existing = tuple(
                value for value in self.store.records(
                    trading_date=day, slot=slot
                )
                if value.question_pack_identity == pack.question_pack_identity
                and value.answer_pack_identity == answer.answer_pack_identity
            )
            if len(existing) == 2:
                self._errors.pop(slot, None)
                return existing
            records = tuple(build_context_record(
                trading_date=day, slot=slot, family=item.family,
                revision=self.store.next_revision(day, slot, item.family),
                question_pack_identity=pack.question_pack_identity,
                answer_pack_identity=answer.answer_pack_identity,
                captured_at=answer.captured_at, imported_at=imported_at,
                panels=item.panels, wti_brent_alignment=item.wti_brent_alignment,
                natural_gas_alignment=item.natural_gas_alignment,
            ) for item in answer.families)
            for value in records: self.store.retain(value)
        except (PdfReviewTransportError, ValueError) as error:
            self._errors[slot] = str(error); raise
        self._errors.pop(slot, None); return records

    def snapshot(self) -> McxSupportingContextSnapshot:
        day, required = self.governed_trading_date(); slots = []
        for slot in McxContextSlot:
            families = []
            for family in McxContextFamily:
                records = self.store.records(trading_date=day, slot=slot, family=family)
                latest = max(records, key=lambda item: item.revision, default=None)
                staged = self.transport.store.current_image(day, slot, family) is not None
                families.append(McxContextFamilyStatus(
                    family,
                    ContextAvailability.NOT_REQUIRED if not required else ContextAvailability.VALID if latest else ContextAvailability.NOT_PROVIDED,
                    None if latest is None else latest.revision,
                    None if latest is None else latest.imported_at,
                    staged,
                ))
                if required and latest is None and slot in self._errors:
                    families[-1] = McxContextFamilyStatus(
                        family, ContextAvailability.INVALID_INCOMPLETE,
                        None, None, staged,
                    )
            slots.append(McxContextSlotStatus(
                slot, tuple(families), self.transport.store.current(day, slot),
                self._errors.get(slot),
            ))
        return McxSupportingContextSnapshot(day, required, tuple(slots))  # type: ignore[arg-type]

    def context_for(
        self, canonical_instrument: str, *, assessment_boundary: datetime,
    ) -> McxSupportingContextRecord | None:
        family = MCX_CONTEXT_INSTRUMENT_FAMILIES.get(canonical_instrument)
        if family is None or assessment_boundary.tzinfo is None:
            return None
        trading_date = assessment_boundary.astimezone(_IST).date()
        try:
            governed = self.calendar.is_trading_date("MCX", trading_date)
        except ValueError:
            return None
        if not governed:
            return None
        return self.store.latest_valid(trading_date, family, boundary=assessment_boundary)

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("MCX_CONTEXT_CLOCK_INVALID")
        return value


__all__ = ["McxContextFamilyStatus", "McxContextSlotStatus", "McxSupportingContextSnapshot", "McxSupportingContextWorkflow"]
