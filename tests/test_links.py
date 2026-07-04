"""polymarket.com deep-link construction (issue #4)."""

from polymarket_tui.core.links import market_url


def test_market_url_prefers_event_slug():
    assert (
        market_url("katana-fdv", "katana-fdv-395-996")
        == "https://polymarket.com/event/katana-fdv"
    )


def test_market_url_falls_back_to_market_slug():
    assert market_url("", "some-market-1") == "https://polymarket.com/market/some-market-1"


def test_market_url_empty_when_no_slug():
    assert market_url("", "") == ""
