"""Strict Kite login navigation behind an injected browser opener."""

from __future__ import annotations

import re
from collections.abc import Callable
from urllib.parse import parse_qs, urlsplit

from kronos.provider.models.authentication import (
    BrowserOpenCategory,
    BrowserOpenRequest,
    BrowserOpenResult,
)


_KITE_LOGIN_HOST = "kite.zerodha.com"
_KITE_LOGIN_PATH = "/connect/login"
_API_KEY_PATTERN = re.compile(r"[A-Za-z0-9]{1,64}\Z")

BrowserOpener = Callable[[str], bool]


class KiteLoginNavigator:
    """Open one governed official Kite login URL with no retry or retention."""

    __slots__ = ("_opener",)

    def __init__(self, *, opener: BrowserOpener) -> None:
        if not callable(opener):
            raise TypeError("BROWSER_OPENER_INVALID")
        self._opener = opener

    def open_official_login(self, request: BrowserOpenRequest) -> BrowserOpenResult:
        if not isinstance(request, BrowserOpenRequest):
            return BrowserOpenResult(BrowserOpenCategory.FAILED)
        login_url = request.official_login_url
        if not _approved_kite_login_url(login_url):
            return BrowserOpenResult(BrowserOpenCategory.FAILED)
        try:
            opened = self._opener(login_url)
        except Exception:
            return BrowserOpenResult(BrowserOpenCategory.FAILED)
        finally:
            del login_url
        return BrowserOpenResult(
            BrowserOpenCategory.OPENED
            if opened is True
            else BrowserOpenCategory.DECLINED
        )

    def __repr__(self) -> str:
        return "<KiteLoginNavigator redacted>"

    __str__ = __repr__

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("KITE_LOGIN_NAVIGATOR_SERIALIZATION_PROHIBITED")


def _approved_kite_login_url(candidate: object) -> bool:
    if not isinstance(candidate, str) or not candidate:
        return False
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
        query = parse_qs(
            parsed.query,
            keep_blank_values=True,
            strict_parsing=True,
        )
    except (TypeError, ValueError):
        return False
    if (
        parsed.scheme != "https"
        or parsed.hostname != _KITE_LOGIN_HOST
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or parsed.netloc not in {_KITE_LOGIN_HOST, f"{_KITE_LOGIN_HOST}:443"}
        or parsed.path != _KITE_LOGIN_PATH
        or parsed.fragment
        or set(query) != {"api_key", "v"}
        or query.get("v") != ["3"]
    ):
        return False
    api_keys = query.get("api_key", [])
    return (
        len(api_keys) == 1
        and _API_KEY_PATTERN.fullmatch(api_keys[0]) is not None
    )


__all__ = ["KiteLoginNavigator"]
