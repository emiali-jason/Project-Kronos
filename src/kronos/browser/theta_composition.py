"""Optional Theta startup boundary; existing product owners stay registered.

PLC-02 negative-startup repair. Failure exposes one bounded Theta-only 503,
never an empty forecast, a second workflow, secret details or a write capability.
"""
from http import HTTPStatus

from kronos.browser.product_routes import (
    BrowserRouteResponse, ProductBrowserRoutes, with_theta_routes,
)


class _UnavailableThetaRoutes:
    def handle_get(self,request,snapshot_provider):
        if request.path=='/theta-earners' or request.path.startswith('/theta-earners/'):
            return self._response()
        return None

    def owns_post(self,path):
        return path in {'/theta-earners/chart','/theta-earners/question','/theta-earners/import'}

    def handle_post(self,request,snapshot_provider):
        return self._response() if self.owns_post(request.path) else None

    @staticmethod
    def _response():
        return BrowserRouteResponse(
            'THETA_SPONSOR_WORKFLOW_UNAVAILABLE: Theta startup composition failed. '
            'No Theta write operation is admitted.',
            status=HTTPStatus.SERVICE_UNAVAILABLE,
            content_type='text/plain; charset=utf-8')


def compose_theta_browser_routes(existing,*,factory):
    """Append the exact workflow or an explicit read-only failure projection.

    Only optional Theta construction/registration is caught. Current owners,
    server/source readiness and process shutdown exceptions are not swallowed.
    """
    if type(existing) is not ProductBrowserRoutes or not callable(factory):
        raise ValueError('THETA_BROWSER_COMPOSITION_INVALID')
    if existing.owns_post('/theta-earners/chart'):
        raise ValueError('THETA_BROWSER_ROUTE_ALREADY_REGISTERED')
    try:
        sponsor=factory()
        return with_theta_routes(existing,theta_workflow=sponsor.workflow,
                                 theta_sponsor_workflow=sponsor)
    except Exception:
        return ProductBrowserRoutes((*existing._routes,_UnavailableThetaRoutes()))
