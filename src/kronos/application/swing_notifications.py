"""Swing-owned adapter from UX-08 watches to shared notification projection."""

from __future__ import annotations

from kronos.application.notifications import (
    ManagedNotification,
    NotificationHistoryEvent,
    NotificationProduct,
    NotificationState,
    NotificationWorkspaceSnapshot,
)
from kronos.application.swing_progression_watch import SwingProgressionWatchSnapshot


def project_swing_notification_workspace(
    progression: SwingProgressionWatchSnapshot,
) -> NotificationWorkspaceSnapshot:
    """Project UX-08 identities directly; no duplicate notification authority."""

    records = []
    for watch in progression.watches:
        if watch.workspace_hidden:
            continue
        requirement = watch.requirement
        if requirement.product != NotificationProduct.SWING.value:
            continue
        level = (
            f"{requirement.price:g}"
            if requirement.price is not None
            else (
                f"{requirement.zone_low:g}–{requirement.zone_high:g}"
                if requirement.zone_low is not None and requirement.zone_high is not None
                else "UNAVAILABLE"
            )
        )
        trigger_summary = ""
        if watch.trigger_bar is not None:
            trigger_summary = (
                f"Completed {watch.trigger_bar.timeframe.value} close "
                f"{watch.trigger_bar.close:g}"
            )
        records.append(ManagedNotification(
            source_identity=watch.watch_id,
            product=NotificationProduct.SWING,
            instrument=requirement.canonical_instrument,
            direction=requirement.direction.value,
            condition_identity=requirement.condition_identity,
            condition_summary=requirement.summary,
            timeframe=(requirement.timeframe.value if requirement.timeframe else "UNAVAILABLE"),
            comparator=(requirement.comparator.value if requirement.comparator else "UNAVAILABLE"),
            authoritative_level=level,
            source_run_identity=requirement.native_run_identity,
            activated_at=watch.activated_at,
            state=NotificationState(watch.state.value),
            triggered_at=watch.triggered_at,
            trigger_summary=trigger_summary,
            consequence=watch.consequence,
            history=tuple(
                NotificationHistoryEvent(
                    item.event_id, item.event_type.value, item.occurred_at,
                )
                for item in watch.history
            ),
            monitoring_active=watch.watch_id in progression.monitoring_watch_ids,
        ))
    return NotificationWorkspaceSnapshot(tuple(sorted(
        records,
        key=lambda item: (item.activated_at, item.source_identity),
        reverse=True,
    )))


__all__ = ["project_swing_notification_workspace"]
