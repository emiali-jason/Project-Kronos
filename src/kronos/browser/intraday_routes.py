"""Intraday-owned Browser routing and presentation dispatch."""

from __future__ import annotations

from http import HTTPStatus
import json

from kronos.application.intraday_native_visual_reconciliation import (
    IntradayNativeVisualReconciliationApplication,
)
from kronos.application.intraday_review import IntradayReviewApplication
from kronos.browser.intraday_views import (
    render_intraday_detail,
    render_intraday_review,
    render_intraday_wo10,
    render_intraday_wo11,
    render_intraday_wo12,
    render_intraday_wo13,
    render_intraday_wo14,
    render_intraday_workstation,
)
from kronos.browser.intraday_probables_v2_control import (
    IntradayProbablesV2OperationalControl,
)
from kronos.browser.intraday_review_v2_control import (
    MAX_REVIEW_V2_REQUEST_BYTES,
    REVIEW_V2_STATUS_ROUTE,
    IntradayReviewV2OperationalControl,
)
from kronos.browser.intraday_wo10_control import (
    MAX_WO10_REQUEST_BYTES,
    WO10_CONTROL_ROUTE,
    WO10_PRODUCT_ROUTE,
    WO10_STATUS_ROUTE,
    IntradayWo10OperationalControl,
)
from kronos.browser.intraday_wo11_control import (
    MAX_WO11_REQUEST_BYTES,
    WO11_CONTROL_ROUTE,
    WO11_PRODUCT_ROUTE,
    WO11_STATUS_ROUTE,
    IntradayWo11OperationalControl,
)
from kronos.browser.intraday_wo12_v2_control import (
    MAX_WO12_V2_REQUEST_BYTES,
    WO12_V2_CONTROL_ROUTE,
    WO12_V2_PRODUCT_ROUTE,
    WO12_V2_STATUS_ROUTE,
    IntradayWo12V2OperationalControl,
)
from kronos.browser.intraday_wo13_control import (
    MAX_WO13_REQUEST_BYTES,
    WO13_CONTROL_ROUTE,
    WO13_PRODUCT_ROUTE,
    WO13_STATUS_ROUTE,
    IntradayWo13OperationalControl,
)
from kronos.browser.intraday_wo14_control import (
    MAX_WO14_REQUEST_BYTES,
    WO14_CONTROL_ROUTE,
    WO14_PRODUCT_ROUTE,
    WO14_STATUS_ROUTE,
    IntradayWo14OperationalControl,
)
from kronos.browser.product_routes import (
    BrowserGetRequest,
    BrowserPostRequest,
    BrowserRouteResponse,
    BrowserSnapshotProvider,
)
from kronos.intraday.review import ReviewError, ReviewFailure
from kronos.intraday.review_answer import MAX_ANSWER_BYTES
from kronos.intraday.review_v2 import (
    REVIEW_V2_ANSWER_IMPORT_ROUTE,
    REVIEW_V2_CHART_ROUTE,
)
from kronos.intraday.review_v2_transport import REVIEW_V2_QUESTION_TRANSPORT_ROUTE
from kronos.intraday.review_pdf import IntradayReviewPdfTransport
from kronos.intraday.review_persistence import IntradayReviewStore
from kronos.intraday.native_visual_reconciliation import ReconciliationError
from kronos.intraday.native_visual_reconciliation_persistence import (
    IntradayNativeVisualReconciliationStore,
)
from kronos.instrument.visual_identity_persistence import (
    load_default_visual_identity_resolver,
)


class IntradayBrowserRoutes:
    """Own Intraday Browser paths behind the stable product-route seam."""

    def __init__(
        self,
        workstation: object,
        review: IntradayReviewApplication | None = None,
        reconciliation: IntradayNativeVisualReconciliationApplication | None = None,
        probables_v2_control: IntradayProbablesV2OperationalControl | None = None,
        review_v2_control: IntradayReviewV2OperationalControl | None = None,
        wo10_control: IntradayWo10OperationalControl | None = None,
        wo11_control: IntradayWo11OperationalControl | None = None,
        wo12_v2_control: IntradayWo12V2OperationalControl | None = None,
        wo13_control: IntradayWo13OperationalControl | None = None,
        wo14_control: IntradayWo14OperationalControl | None = None,
        review_workstation: object | None = None,
    ) -> None:
        if not callable(getattr(workstation, "snapshot", None)):
            raise ValueError("INTRADAY_BROWSER_ROUTES_INVALID")
        self._workstation = workstation
        self._review_workstation = (
            workstation if review_workstation is None else review_workstation
        )
        if not callable(getattr(self._review_workstation, "snapshot", None)):
            raise ValueError("INTRADAY_BROWSER_ROUTES_INVALID")
        if (
            probables_v2_control is not None
            and type(probables_v2_control) is not IntradayProbablesV2OperationalControl
        ):
            raise ValueError("INTRADAY_BROWSER_ROUTES_INVALID")
        self._probables_v2_control = probables_v2_control
        if (
            review_v2_control is not None
            and type(review_v2_control) is not IntradayReviewV2OperationalControl
        ):
            raise ValueError("INTRADAY_BROWSER_ROUTES_INVALID")
        self._review_v2_control = review_v2_control
        if (
            wo10_control is not None
            and type(wo10_control) is not IntradayWo10OperationalControl
        ):
            raise ValueError("INTRADAY_BROWSER_ROUTES_INVALID")
        self._wo10_control = wo10_control
        if (
            wo11_control is not None
            and type(wo11_control) is not IntradayWo11OperationalControl
        ):
            raise ValueError("INTRADAY_BROWSER_ROUTES_INVALID")
        self._wo11_control = wo11_control
        if (
            wo12_v2_control is not None
            and type(wo12_v2_control) is not IntradayWo12V2OperationalControl
        ):
            raise ValueError("INTRADAY_BROWSER_ROUTES_INVALID")
        self._wo12_v2_control = wo12_v2_control
        if (
            wo13_control is not None
            and type(wo13_control) is not IntradayWo13OperationalControl
        ):
            raise ValueError("INTRADAY_BROWSER_ROUTES_INVALID")
        self._wo13_control = wo13_control
        if (
            wo14_control is not None
            and type(wo14_control) is not IntradayWo14OperationalControl
        ):
            raise ValueError("INTRADAY_BROWSER_ROUTES_INVALID")
        self._wo14_control = wo14_control
        self._review = review or IntradayReviewApplication(
            current_probables=self._current_probables,
            store=IntradayReviewStore(),
            transport=IntradayReviewPdfTransport(),
            visual_identity_resolver=load_default_visual_identity_resolver(),
        )
        self._reconciliation = reconciliation or IntradayNativeVisualReconciliationApplication(
            current_probables=self._review.current_probables,
            review_store=self._review.store,
            store=IntradayNativeVisualReconciliationStore(
                (self._review.store.root / "native-visual-reconciliation-v1").resolve()
            ),
        )

    def _current_probables(self):  # type: ignore[no-untyped-def]
        snapshot = self._review_workstation.snapshot()
        probables = getattr(snapshot, "probables", None)
        return None if probables is None else probables.run

    def _current_probables_v2(self):  # type: ignore[no-untyped-def]
        if self._review_v2_control is None:
            return None
        try:
            return self._review_v2_control.application.current_probables_run()
        except ReviewError:
            return None

    def _review_v2_snapshot(self):  # type: ignore[no-untyped-def]
        return (
            None
            if self._review_v2_control is None
            else self._review_v2_control.application.snapshot()
        )

    def _review_v2_status(self):  # type: ignore[no-untyped-def]
        return (
            None
            if self._review_v2_control is None
            else self._review_v2_control.status_document()
        )

    def handle_get(
        self,
        request: BrowserGetRequest,
        snapshot_provider: BrowserSnapshotProvider,
    ) -> BrowserRouteResponse | None:
        detail_prefix = "/intraday/evidence/"
        if request.path == "/intraday":
            selected = request.query.get("instrument", [None])[0]
            renderer = render_intraday_workstation
        elif request.path.startswith(detail_prefix):
            selected = request.path.removeprefix(detail_prefix)
            renderer = render_intraday_detail
        elif request.path == "/intraday/review":
            return BrowserRouteResponse(
                render_intraday_review(
                    snapshot_provider(),
                    self._review.snapshot(),
                    self._reconciliation.snapshot(),
                    review_v2=self._review_v2_snapshot(),
                    available_probables_v2_run=self._current_probables_v2(),
                    review_v2_status=self._review_v2_status(),
                )
            )
        elif request.path == WO10_PRODUCT_ROUTE:
            if self._wo10_control is None or request.query:
                return BrowserRouteResponse(
                    "Not found.",
                    status=HTTPStatus.NOT_FOUND,
                    content_type="text/plain; charset=utf-8",
                )
            return BrowserRouteResponse(
                render_intraday_wo10(
                    snapshot_provider(), self._wo10_control.status_document()
                )
            )
        elif request.path == WO11_PRODUCT_ROUTE:
            if self._wo11_control is None or request.query:
                return BrowserRouteResponse(
                    "Not found.",
                    status=HTTPStatus.NOT_FOUND,
                    content_type="text/plain; charset=utf-8",
                )
            return BrowserRouteResponse(
                render_intraday_wo11(
                    snapshot_provider(), self._wo11_control.status_document()
                )
            )
        elif request.path == WO12_V2_PRODUCT_ROUTE:
            if self._wo12_v2_control is None or request.query:
                return BrowserRouteResponse(
                    "Not found.",
                    status=HTTPStatus.NOT_FOUND,
                    content_type="text/plain; charset=utf-8",
                )
            return BrowserRouteResponse(
                render_intraday_wo12(
                    snapshot_provider(), self._wo12_v2_control.status_document()
                )
            )
        elif request.path == WO13_PRODUCT_ROUTE:
            if self._wo13_control is None or request.query:
                return BrowserRouteResponse(
                    "Not found.",
                    status=HTTPStatus.NOT_FOUND,
                    content_type="text/plain; charset=utf-8",
                )
            return BrowserRouteResponse(
                render_intraday_wo13(
                    snapshot_provider(), self._wo13_control.status_document()
                )
            )
        elif request.path == WO14_PRODUCT_ROUTE:
            if self._wo14_control is None or request.query:
                return BrowserRouteResponse(
                    "Not found.",
                    status=HTTPStatus.NOT_FOUND,
                    content_type="text/plain; charset=utf-8",
                )
            return BrowserRouteResponse(
                render_intraday_wo14(
                    snapshot_provider(), self._wo14_control.status_document()
                )
            )
        elif request.path == "/control/intraday-discovery/v2/status":
            if self._probables_v2_control is None or request.query:
                return BrowserRouteResponse(
                    "Not found.",
                    status=HTTPStatus.NOT_FOUND,
                    content_type="text/plain; charset=utf-8",
                )
            return BrowserRouteResponse(
                json.dumps(
                    self._probables_v2_control.status_document(),
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                content_type="application/json; charset=utf-8",
            )
        elif request.path == REVIEW_V2_STATUS_ROUTE:
            if self._review_v2_control is None or request.query:
                return BrowserRouteResponse(
                    "Not found.",
                    status=HTTPStatus.NOT_FOUND,
                    content_type="text/plain; charset=utf-8",
                )
            return BrowserRouteResponse(
                json.dumps(
                    self._review_v2_control.status_document(),
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                content_type="application/json; charset=utf-8",
            )
        elif request.path == WO10_STATUS_ROUTE:
            if self._wo10_control is None or request.query:
                return BrowserRouteResponse(
                    "Not found.",
                    status=HTTPStatus.NOT_FOUND,
                    content_type="text/plain; charset=utf-8",
                )
            return BrowserRouteResponse(
                json.dumps(
                    self._wo10_control.status_document(),
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                content_type="application/json; charset=utf-8",
            )
        elif request.path == WO11_STATUS_ROUTE:
            if self._wo11_control is None or request.query:
                return BrowserRouteResponse(
                    "Not found.",
                    status=HTTPStatus.NOT_FOUND,
                    content_type="text/plain; charset=utf-8",
                )
            return BrowserRouteResponse(
                json.dumps(
                    self._wo11_control.status_document(),
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                content_type="application/json; charset=utf-8",
            )
        elif request.path == WO12_V2_STATUS_ROUTE:
            if self._wo12_v2_control is None or request.query:
                return BrowserRouteResponse(
                    "Not found.",
                    status=HTTPStatus.NOT_FOUND,
                    content_type="text/plain; charset=utf-8",
                )
            return BrowserRouteResponse(
                json.dumps(
                    self._wo12_v2_control.status_document(),
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                content_type="application/json; charset=utf-8",
            )
        elif request.path == WO13_STATUS_ROUTE:
            if self._wo13_control is None or request.query:
                return BrowserRouteResponse(
                    "Not found.",
                    status=HTTPStatus.NOT_FOUND,
                    content_type="text/plain; charset=utf-8",
                )
            return BrowserRouteResponse(
                json.dumps(
                    self._wo13_control.status_document(),
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                content_type="application/json; charset=utf-8",
            )
        elif request.path == WO14_STATUS_ROUTE:
            if self._wo14_control is None or request.query:
                return BrowserRouteResponse(
                    "Not found.",
                    status=HTTPStatus.NOT_FOUND,
                    content_type="text/plain; charset=utf-8",
                )
            return BrowserRouteResponse(
                json.dumps(
                    self._wo14_control.status_document(),
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                content_type="application/json; charset=utf-8",
            )
        else:
            return None
        return BrowserRouteResponse(
            renderer(
                snapshot_provider(),
                self._workstation.snapshot(selected),
            )
        )

    def owns_post(self, path: str) -> bool:
        return path in {
            "/control/intraday-discovery/v2",
            "/control/intraday-review/v2",
            WO10_CONTROL_ROUTE,
            WO11_CONTROL_ROUTE,
            WO12_V2_CONTROL_ROUTE,
            WO13_CONTROL_ROUTE,
            WO14_CONTROL_ROUTE,
            REVIEW_V2_CHART_ROUTE,
            REVIEW_V2_QUESTION_TRANSPORT_ROUTE,
            REVIEW_V2_ANSWER_IMPORT_ROUTE,
            "/intraday/review/start",
            "/intraday/review/chart",
            "/intraday/review/question-pack",
            "/intraday/review/question-packs",
            "/intraday/review/answer",
            "/intraday/review/answers",
            "/intraday/review/reconcile",
            "/intraday/review/reconcile-all",
        }

    def handle_post(
        self,
        request: BrowserPostRequest,
        snapshot_provider: BrowserSnapshotProvider,
    ) -> BrowserRouteResponse | None:
        if not self.owns_post(request.path):
            return None
        try:
            if request.path == "/control/intraday-discovery/v2":
                if self._probables_v2_control is None:
                    raise ValueError
                if (
                    request.query
                    or request.content_type != "application/json"
                    or not request.body
                ):
                    payload = None
                else:
                    try:
                        payload = json.loads(request.body)
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        payload = None
                document = self._probables_v2_control.execute_document(payload)
                outcome = document["outcome"]
                return BrowserRouteResponse(
                    json.dumps(document, sort_keys=True, separators=(",", ":")),
                    status=(
                        HTTPStatus.OK
                        if outcome == "SUCCESS" or document["idempotent"]
                        else HTTPStatus.CONFLICT
                        if document["failure"]
                        == "INTRADAY_PROBABLES_V2_REQUEST_IDENTITY_CONFLICT"
                        else HTTPStatus.BAD_REQUEST
                        if outcome == "REJECTED"
                        else HTTPStatus.SERVICE_UNAVAILABLE
                    ),
                    content_type="application/json; charset=utf-8",
                )
            if request.path == "/control/intraday-review/v2":
                if self._review_v2_control is None:
                    raise ValueError
                if (
                    request.query
                    or request.content_type != "application/json"
                    or not request.body
                    or len(request.body) > MAX_REVIEW_V2_REQUEST_BYTES
                ):
                    payload = None
                else:
                    try:
                        payload = json.loads(request.body)
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        payload = None
                document = self._review_v2_control.execute_document(payload)
                outcome = document["outcome"]
                return BrowserRouteResponse(
                    json.dumps(document, sort_keys=True, separators=(",", ":")),
                    status=(
                        HTTPStatus.OK
                        if outcome == "COMPLETE" or document["idempotent"]
                        else HTTPStatus.CONFLICT
                        if document["failure_reason"] in {
                            "INTRADAY_REVIEW_V2_REQUEST_IDENTITY_CONFLICT",
                            "INTRADAY_REVIEW_V2_OPERATION_CONFLICT",
                        }
                        else HTTPStatus.BAD_REQUEST
                        if outcome == "REJECTED"
                        else HTTPStatus.SERVICE_UNAVAILABLE
                    ),
                    content_type="application/json; charset=utf-8",
                )
            if request.path == WO10_CONTROL_ROUTE:
                if self._wo10_control is None:
                    raise ValueError
                if (
                    request.query
                    or request.content_type != "application/json"
                    or not request.body
                    or len(request.body) > MAX_WO10_REQUEST_BYTES
                ):
                    payload = None
                else:
                    try:
                        payload = json.loads(request.body)
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        payload = None
                document = self._wo10_control.execute_document(payload)
                outcome = document["outcome"]
                return BrowserRouteResponse(
                    json.dumps(document, sort_keys=True, separators=(",", ":")),
                    status=(
                        HTTPStatus.OK
                        if outcome in {"COMPLETED", "RETAINED"}
                        else HTTPStatus.CONFLICT
                        if outcome in {"BUSY", "REJECTED"}
                        and document["failure_reason"] in {
                            "WO10_OPERATION_BUSY",
                            "WO10_REQUEST_IDENTITY_CONFLICT",
                        }
                        else HTTPStatus.BAD_REQUEST
                        if outcome == "REJECTED"
                        else HTTPStatus.SERVICE_UNAVAILABLE
                    ),
                    content_type="application/json; charset=utf-8",
                )
            if request.path == WO11_CONTROL_ROUTE:
                if self._wo11_control is None:
                    raise ValueError
                if (
                    request.query
                    or request.content_type != "application/json"
                    or not request.body
                    or len(request.body) > MAX_WO11_REQUEST_BYTES
                ):
                    payload = None
                else:
                    try:
                        payload = json.loads(request.body)
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        payload = None
                document = self._wo11_control.execute_document(payload)
                outcome = document["outcome"]
                return BrowserRouteResponse(
                    json.dumps(document, sort_keys=True, separators=(",", ":")),
                    status=(
                        HTTPStatus.OK
                        if outcome in {"COMPLETED", "RETAINED"}
                        else HTTPStatus.CONFLICT
                        if outcome in {"BUSY", "REJECTED"}
                        and document["failure_reason"] in {
                            "WO11_OPERATION_BUSY",
                            "WO11_REQUEST_IDENTITY_CONFLICT",
                        }
                        else HTTPStatus.BAD_REQUEST
                        if outcome == "REJECTED"
                        else HTTPStatus.SERVICE_UNAVAILABLE
                    ),
                    content_type="application/json; charset=utf-8",
                )
            if request.path == WO12_V2_CONTROL_ROUTE:
                if self._wo12_v2_control is None:
                    raise ValueError
                if (
                    request.query
                    or request.content_type != "application/json"
                    or not request.body
                    or len(request.body) > MAX_WO12_V2_REQUEST_BYTES
                ):
                    payload = None
                else:
                    try:
                        payload = json.loads(request.body)
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        payload = None
                document = self._wo12_v2_control.execute_document(payload)
                outcome = document["outcome"]
                return BrowserRouteResponse(
                    json.dumps(document, sort_keys=True, separators=(",", ":")),
                    status=(
                        HTTPStatus.OK
                        if outcome in {"COMPLETED", "RETAINED"}
                        else HTTPStatus.CONFLICT
                        if outcome == "BUSY"
                        or document["failure_reason"]
                        == "WO12_V2_REQUEST_IDENTITY_CONFLICT"
                        else HTTPStatus.BAD_REQUEST
                        if outcome == "REJECTED"
                        else HTTPStatus.SERVICE_UNAVAILABLE
                    ),
                    content_type="application/json; charset=utf-8",
                )
            if request.path == WO13_CONTROL_ROUTE:
                if self._wo13_control is None:
                    raise ValueError
                if (
                    request.query
                    or request.content_type != "application/json"
                    or not request.body
                    or len(request.body) > MAX_WO13_REQUEST_BYTES
                ):
                    payload = None
                else:
                    try:
                        payload = json.loads(request.body)
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        payload = None
                document = self._wo13_control.execute_document(payload)
                outcome = document["outcome"]
                return BrowserRouteResponse(
                    json.dumps(document, sort_keys=True, separators=(",", ":")),
                    status=(
                        HTTPStatus.OK
                        if outcome in {"COMPLETED", "RETAINED"}
                        else HTTPStatus.CONFLICT
                        if outcome == "BUSY"
                        or document["failure_reason"]
                        == "WO13_SUPERSEDED_WO12_REJECTED"
                        else HTTPStatus.BAD_REQUEST
                        if outcome == "REJECTED"
                        else HTTPStatus.SERVICE_UNAVAILABLE
                    ),
                    content_type="application/json; charset=utf-8",
                )
            if request.path == WO14_CONTROL_ROUTE:
                if self._wo14_control is None:
                    raise ValueError
                if (
                    request.query
                    or request.content_type != "application/json"
                    or not request.body
                    or len(request.body) > MAX_WO14_REQUEST_BYTES
                ):
                    payload = None
                else:
                    try:
                        payload = json.loads(request.body)
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        payload = None
                document = self._wo14_control.execute_document(payload)
                outcome = document["outcome"]
                return BrowserRouteResponse(
                    json.dumps(document, sort_keys=True, separators=(",", ":")),
                    status=(
                        HTTPStatus.OK
                        if outcome in {"COMPLETED", "RETAINED"}
                        else HTTPStatus.CONFLICT
                        if outcome == "BUSY"
                        or document["failure_reason"] in {
                            "WO14_SUPERSEDED_WO13_REJECTED",
                            "WO14_REQUEST_IDENTITY_CONFLICT",
                        }
                        else HTTPStatus.BAD_REQUEST
                        if outcome == "REJECTED"
                        else HTTPStatus.SERVICE_UNAVAILABLE
                    ),
                    content_type="application/json; charset=utf-8",
                )
            if request.path == REVIEW_V2_CHART_ROUTE:
                if self._review_v2_control is None:
                    raise ValueError
                self._review_v2_control.application.upload_chart(
                    _one_query(request, "cycle"),
                    media_type=request.content_type,
                    payload=request.body,
                )
            elif request.path == REVIEW_V2_QUESTION_TRANSPORT_ROUTE:
                if self._review_v2_control is None or request.query or request.body:
                    raise ValueError
                self._review_v2_control.application.create_combined_question_transport()
            elif request.path == REVIEW_V2_ANSWER_IMPORT_ROUTE:
                if (
                    self._review_v2_control is None
                    or request.query
                    or request.content_type != "application/json"
                    or not request.body
                    or len(request.body) > MAX_ANSWER_BYTES
                ):
                    raise ValueError
                self._review_v2_control.application.import_combined_answer(
                    request.body
                )
            elif request.path == "/intraday/review/start":
                result = _one_query(request, "result")
                if request.body:
                    raise ValueError
                self._review.start_review(result)
            elif request.path == "/intraday/review/chart":
                if set(request.query) == {"result"}:
                    self._review.upload_chart_for_result(
                        _one_query(request, "result"),
                        media_type=request.content_type,
                        payload=request.body,
                    )
                else:
                    self._review.upload_chart(
                        _one_query(request, "cycle"),
                        media_type=request.content_type,
                        payload=request.body,
                    )
            elif request.path == "/intraday/review/question-pack":
                cycle = _one_query(request, "cycle")
                if request.body:
                    raise ValueError
                self._review.create_question_pack(cycle)
            elif request.path == "/intraday/review/question-packs":
                if request.query or request.body:
                    raise ValueError
                batch_result = self._review.create_all_question_packs()
                return BrowserRouteResponse(
                    render_intraday_review(
                        snapshot_provider(),
                        self._review.snapshot(),
                        self._reconciliation.snapshot(),
                        batch_result=batch_result,
                    )
                )
            elif request.path == "/intraday/review/answer":
                cycle = _one_query(request, "cycle")
                answer_result = (
                    self._review.import_answer(cycle)
                    if not request.body
                    else self._review.upload_answer(
                        cycle, media_type=request.content_type, payload=request.body,
                    )
                )
                return BrowserRouteResponse(
                    render_intraday_review(
                        snapshot_provider(), self._review.snapshot(), answer_result=answer_result,
                        reconciliation=self._reconciliation.snapshot(),
                    )
                )
            elif request.path == "/intraday/review/answers":
                source_filename = (
                    _one_query(request, "filename") if request.body else None
                )
                if not request.body and request.query:
                    raise ValueError
                answer_batch_result = self._review.import_all_answers(
                    media_type=request.content_type if request.body else None,
                    payload=request.body or None,
                    source_filename=source_filename,
                )
                return BrowserRouteResponse(
                    render_intraday_review(
                        snapshot_provider(), self._review.snapshot(),
                        self._reconciliation.snapshot(),
                        answer_batch_result=answer_batch_result,
                    )
                )
            elif request.path == "/intraday/review/reconcile":
                cycle = _one_query(request, "cycle")
                if request.body:
                    raise ValueError
                reconciliation_result = self._reconciliation.reconcile(cycle)
                return BrowserRouteResponse(
                    render_intraday_review(
                        snapshot_provider(), self._review.snapshot(),
                        self._reconciliation.snapshot(),
                        reconciliation_result=reconciliation_result,
                    )
                )
            else:
                if request.query or request.body:
                    raise ValueError
                reconciliation_batch_result = self._reconciliation.reconcile_all_ready()
                return BrowserRouteResponse(
                    render_intraday_review(
                        snapshot_provider(), self._review.snapshot(),
                        self._reconciliation.snapshot(),
                        reconciliation_batch_result=reconciliation_batch_result,
                    )
                )
        except ValueError:
            return BrowserRouteResponse(
                "Intraday Review request rejected.",
                status=HTTPStatus.BAD_REQUEST,
                content_type="text/plain; charset=utf-8",
            )
        except ReviewError as error:
            status = (
                HTTPStatus.BAD_REQUEST
                if error.failure in {ReviewFailure.CHART_INVALID, ReviewFailure.INPUT_INVALID}
                else HTTPStatus.CONFLICT
            )
            return BrowserRouteResponse(
                error.failure.value,
                status=status,
                content_type="text/plain; charset=utf-8",
            )
        except ReconciliationError as error:
            return BrowserRouteResponse(
                error.failure.value,
                status=HTTPStatus.CONFLICT,
                content_type="text/plain; charset=utf-8",
            )
        return BrowserRouteResponse(
            render_intraday_review(
                snapshot_provider(), self._review.snapshot(), self._reconciliation.snapshot(),
                review_v2=self._review_v2_snapshot(),
                available_probables_v2_run=self._current_probables_v2(),
                review_v2_status=self._review_v2_status(),
            )
        )


def _one_query(request: BrowserPostRequest, name: str) -> str:
    if set(request.query) != {name} or len(request.query[name]) != 1:
        raise ValueError("INTRADAY_REVIEW_QUERY_INVALID")
    value = request.query[name][0]
    if not value or value != value.strip() or "/" in value or "\\" in value:
        raise ValueError("INTRADAY_REVIEW_QUERY_INVALID")
    return value


__all__ = ["IntradayBrowserRoutes"]
