"""Nov 2026 Sponsor compact Opportunities card (display only; owning fixtures)."""
from html.parser import HTMLParser

import pytest

from kronos.browser.views import _native_opportunity_card
from tests.unit.browser.test_swing_opportunity_sponsor_simplification import fixture, promotion


class Front(HTMLParser):
    """Text visible without opening the outer full-analysis disclosure."""
    def __init__(self):
        super().__init__()
        self.depth, self.front, self.open_full = 0, [], None

    def handle_starttag(self, tag, attrs):
        if tag == 'details':
            if ('class', 'swing-compact-full') in attrs:
                self.open_full = any(name == 'open' for name, _ in attrs)
            self.depth += 1

    def handle_endtag(self, tag):
        if tag == 'details':
            self.depth -= 1

    def handle_data(self, data):
        if self.depth == 0:
            self.front.append(data)


def front(html):
    parser = Front(); parser.feed(html)
    return ' '.join(parser.front), parser.open_full


@pytest.mark.parametrize('count,label,opened', [
    (5, 'BUY NOW', True), (4, 'BUY READY', False), (3, 'HARD GATED', False)])
def test_full_analysis_opens_only_for_now(count, label, opened):
    _, item, intake = fixture(symbol='INFY')
    record = promotion(item, count=count)
    html = _native_opportunity_card(item, None, native_intake=intake, promotions_v2=(record,))
    text, is_open = front(html)
    assert 'INFY' in text and 'LONG' in text and 'PROBABLE' in text and label in text
    assert is_open is opened
    assert '<details class="swing-compact-full"' in html
    # Everything else stays available inside the full-analysis disclosure.
    assert 'Current stage' in html and 'K1' in html


def test_ready_shows_what_it_is_waiting_for():
    _, item, intake = fixture(symbol='INFY')
    html = _native_opportunity_card(item, None, native_intake=intake,
                                    promotions_v2=(promotion(item, count=4),))
    text, _ = front(html)
    assert 'Waiting for' in text
    now = _native_opportunity_card(item, None, native_intake=intake,
                                   promotions_v2=(promotion(item, count=5),))
    assert 'Waiting for' not in front(now)[0]


def test_short_direction_and_no_promotion_stay_compact():
    _, item, intake = fixture(symbol='INFY', direction='SHORT')
    html = _native_opportunity_card(item, None, native_intake=intake)
    text, is_open = front(html)
    assert 'SHORT' in text and 'Waiting for' not in text and is_open is False
    assert 'Kronos opinion' in text
    assert 'Methodology' not in text and 'Pending requirements' not in text
