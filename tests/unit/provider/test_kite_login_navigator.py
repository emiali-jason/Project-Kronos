import pickle

import pytest

from kronos.provider.adapters.kite.navigation import KiteLoginNavigator
from kronos.provider.models.authentication import (
    BrowserOpenCategory,
    BrowserOpenRequest,
)


VALID_URL = "https://kite.zerodha.com/connect/login?api_key=ABC123&v=3"


class _Opener:
    def __init__(self, result: bool | BaseException) -> None:
        self.result = result
        self.urls: list[str] = []

    def __call__(self, url: str) -> bool:
        self.urls.append(url)
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


def test_approved_kite_url_opens_once() -> None:
    opener = _Opener(True)
    navigator = KiteLoginNavigator(opener=opener)

    result = navigator.open_official_login(BrowserOpenRequest(VALID_URL))

    assert result.category is BrowserOpenCategory.OPENED
    assert opener.urls == [VALID_URL]


def test_browser_decline_is_one_call_with_no_fallback() -> None:
    opener = _Opener(False)
    navigator = KiteLoginNavigator(opener=opener)

    first = navigator.open_official_login(BrowserOpenRequest(VALID_URL))

    assert first.category is BrowserOpenCategory.DECLINED
    assert opener.urls == [VALID_URL]


def test_browser_exception_is_sanitized_and_not_retried() -> None:
    opener = _Opener(RuntimeError("raw browser failure"))
    navigator = KiteLoginNavigator(opener=opener)

    result = navigator.open_official_login(BrowserOpenRequest(VALID_URL))

    assert result.category is BrowserOpenCategory.FAILED
    assert opener.urls == [VALID_URL]
    assert "raw" not in repr(result)


@pytest.mark.parametrize(
    "url",
    [
        "http://kite.zerodha.com/connect/login?api_key=ABC123&v=3",
        "https://evil.example/connect/login?api_key=ABC123&v=3",
        "https://kite.zerodha.com.evil.example/connect/login?api_key=ABC123&v=3",
        "https://KITE.ZERODHA.COM/connect/login?api_key=ABC123&v=3",
        "https://user@kite.zerodha.com/connect/login?api_key=ABC123&v=3",
        "https://kite.zerodha.com:8443/connect/login?api_key=ABC123&v=3",
        "https://kite.zerodha.com/other?api_key=ABC123&v=3",
        "https://kite.zerodha.com/connect/login?api_key=ABC123&v=3#fragment",
        "https://kite.zerodha.com/connect/login?v=3",
        "https://kite.zerodha.com/connect/login?api_key=&v=3",
        "https://kite.zerodha.com/connect/login?api_key=ABC123",
        "https://kite.zerodha.com/connect/login?api_key=ABC123&v=2",
        "https://kite.zerodha.com/connect/login?api_key=ABC123&v=3&extra=1",
        "https://kite.zerodha.com/connect/login?api_key=ABC123&api_key=DEF456&v=3",
        "https://kite.zerodha.com/connect/login?api_key=ABC-123&v=3",
        "https://kite.zerodha.com/connect/login?api_key=ABC123&v=3&broken",
    ],
)
def test_non_governed_login_urls_are_rejected_before_browser(url: str) -> None:
    opener = _Opener(True)

    result = KiteLoginNavigator(opener=opener).open_official_login(
        BrowserOpenRequest(url)
    )

    assert result.category is BrowserOpenCategory.FAILED
    assert opener.urls == []


def test_explicit_default_https_port_is_permitted() -> None:
    opener = _Opener(True)
    url = "https://kite.zerodha.com:443/connect/login?v=3&api_key=ABC123"

    result = KiteLoginNavigator(opener=opener).open_official_login(
        BrowserOpenRequest(url)
    )

    assert result.category is BrowserOpenCategory.OPENED
    assert opener.urls == [url]


def test_invalid_request_type_never_calls_browser() -> None:
    opener = _Opener(True)

    result = KiteLoginNavigator(opener=opener).open_official_login(  # type: ignore[arg-type]
        object()
    )

    assert result.category is BrowserOpenCategory.FAILED
    assert opener.urls == []


def test_navigator_representation_and_serialization_are_redacted() -> None:
    navigator = KiteLoginNavigator(opener=_Opener(True))

    assert repr(navigator) == "<KiteLoginNavigator redacted>"
    assert str(navigator) == "<KiteLoginNavigator redacted>"
    assert "api_key" not in repr(navigator)
    with pytest.raises((TypeError, pickle.PicklingError)):
        pickle.dumps(navigator)
