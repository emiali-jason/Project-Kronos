"""Exact TE-01R admission handler only; no retained launcher/store dependency."""


def chart_intake_handler(base):
    """Sandbox-only exact route allowlist; shared guards still own admission."""
    from http import HTTPStatus
    from urllib.parse import urlsplit

    class ChartIntakeOnly(base):
        def mutation(self):
            self._text(HTTPStatus.METHOD_NOT_ALLOWED,
                'TE-01R sandbox permits only governed Theta chart intake. Other mutations are blocked.')

        def do_POST(self):
            if urlsplit(self.path).path != '/theta-earners/chart':
                self.mutation()
                return
            # No direct Theta dispatch: retain exact Host/Origin, shutdown and
            # maintenance admission, body limit and normal route validation.
            super().do_POST()

        do_PUT = mutation
        do_PATCH = mutation
        do_DELETE = mutation

    return ChartIntakeOnly
