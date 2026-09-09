"""WO-07D exact-current, read-only retained chart access; no new evidence."""
from __future__ import annotations

import os
import re
import stat
from pathlib import Path

from kronos.intraday.review import ReviewError, ReviewFailure
from kronos.intraday.review_persistence import MAX_CHART_BYTES
from kronos.intraday.review_v2_persistence import IntradayReviewV2Store
from kronos.intraday.review_v2_transport import _trusted_answer_directory

CHART_PREVIEW_ROUTE = "/intraday/review/v2/chart-preview"
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}\Z")


class _PreviewStore(IntradayReviewV2Store):
    """Reuse governed parsers with no-follow, bounded reads for this surface."""

    @staticmethod
    def _read(path: Path) -> bytes:
        try:
            with _trusted_answer_directory(path.parent) as directory:
                fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=directory)
                with os.fdopen(fd, "rb") as handle:
                    before = os.fstat(handle.fileno())
                    if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_CHART_BYTES:
                        raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
                    payload = handle.read(MAX_CHART_BYTES + 1)
                    after = os.fstat(handle.fileno())
                    named = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
                    signature = lambda value: (value.st_dev, value.st_ino, value.st_size,
                                               value.st_mtime_ns, value.st_ctime_ns)
                    if (signature(before) != signature(after) or signature(after) != signature(named)
                        or len(payload) != before.st_size):
                        raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
            return payload
        except OSError as error:
            raise ReviewError(ReviewFailure.ARTIFACT_UNAVAILABLE) from error


def current_chart_preview(application, query: dict[str, list[str]]) -> tuple[str, bytes]:
    """Exact run/cycle/revision only. Old links never select a newer chart."""
    if set(query) != {"run", "cycle", "revision"} or any(
        type(value) is not list or len(value) != 1 or type(value[0]) is not str
        or not _ID.fullmatch(value[0]) for value in query.values()
    ):
        raise ReviewError(ReviewFailure.INPUT_INVALID)
    run, cycle, revision = (query[key][0] for key in ("run", "cycle", "revision"))
    store = _PreviewStore(application.review_store.root)
    with application.review_store.workspace_lock, application.probables_store.current_generation_guard():
        application._require_current_workspace(run_identity=run, cycle_identity=cycle)
        current = store.load_current()
        if current is None or current.probables_run_identity != run or cycle not in {
            member.cycle_identity for member in current.cycles
        }:
            raise ReviewError(ReviewFailure.NOT_CURRENT)
        active = store.load_current_chart(cycle)
        if active is None or active.chart_revision_identity != revision:
            raise ReviewError(ReviewFailure.ARTIFACT_UNAVAILABLE)
        chart = store.load_chart(revision)
        if chart.review_cycle_identity != cycle or chart.probables_run_identity != run:
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        payload = store.load_chart_bytes(chart)
        application._require_current_workspace(run_identity=run, cycle_identity=cycle)
        return chart.media_type, payload
