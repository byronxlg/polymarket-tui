"""Build the daily digest from the public Gamma API.

Section selection is pure (testable with fixture data); only fetch_json touches
the network. Field quirks follow docs/api-reference.md: outcomePrices is a
JSON-encoded string, active=true does not mean live (expired events keep the
flag), and endDate ordering needs end_date_min to skip long-dead markets.
"""

import json
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta

GAMMA = "https://gamma-api.polymarket.com"
USER_AGENT = "polymarket-tui-newsletter/1.0 (+https://polymarket-tui.botsmith.dev)"

# Movers: enough volume to be real, priced away from the poles (a market that
# jumped to 99c has effectively resolved - that is news, but not a "mover" a
# reader can still trade), and a change big enough to notice.
MOVER_MIN_VOLUME = 10_000
MOVER_PRICE_BAND = (0.05, 0.95)
MOVER_MIN_CHANGE = 0.03
ENDING_MIN_VOLUME = 25_000
NEW_MIN_VOLUME = 5_000
# Wider than the movers band: a 2c longshot is a legitimate new market, but a
# 0.1c one is effectively decided (seen live: an in-progress tennis match).
NEW_PRICE_BAND = (0.005, 0.995)


def fetch_json(path: str, params: dict) -> list:
    url = f"{GAMMA}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _f(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _yes_price(market: dict) -> float | None:
    """outcomePrices is a JSON-encoded string; index 0 is YES."""
    try:
        prices = json.loads(market.get("outcomePrices") or "[]")
        return float(prices[0])
    except (ValueError, TypeError, IndexError):
        return None


def _when(raw: object) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _market_url(market: dict) -> str:
    events = market.get("events") or []
    if events and isinstance(events, list) and events[0].get("slug"):
        return f"https://polymarket.com/event/{events[0]['slug']}"
    return f"https://polymarket.com/market/{market.get('slug', '')}"


# Polymarket splits one real-world happening across sibling events
# ("mls-lag-laf-2026-07-17", "...-exact-score", "...-more-markets"). Without
# grouping, one football match floods a whole section (seen in the first real
# send: the same game three times in Ending-within-48h).
_SIBLING_SUFFIXES = ("-exact-score", "-more-markets")


def _family(url: str) -> str:
    for suffix in _SIBLING_SUFFIXES:
        if url.endswith(suffix):
            return url[: -len(suffix)]
    return url


def _market_item(market: dict) -> dict | None:
    yes = _yes_price(market)
    if yes is None:
        return None
    return {
        "title": (market.get("question") or "").strip(),
        "url": _market_url(market),
        "yes": yes,
        "change": _f(market.get("oneDayPriceChange")) or 0.0,
        "volume24h": _f(market.get("volume24hr")) or 0.0,
        "end": _when(market.get("endDate")),
    }


def select_movers(markets: list[dict], limit: int = 6) -> list[dict]:
    """Biggest 24h price changes still inside the tradable band, one per event."""
    lo, hi = MOVER_PRICE_BAND
    seen_events: set[str] = set()
    picked = []
    for market in sorted(
        markets, key=lambda m: abs(_f(m.get("oneDayPriceChange")) or 0.0), reverse=True
    ):
        item = _market_item(market)
        if item is None:
            continue
        if abs(item["change"]) < MOVER_MIN_CHANGE:
            break  # sorted by |change|; nothing further qualifies
        if item["volume24h"] < MOVER_MIN_VOLUME or not lo <= item["yes"] <= hi:
            continue
        event_key = _family(item["url"])
        if event_key in seen_events:
            continue
        seen_events.add(event_key)
        picked.append(item)
        if len(picked) >= limit:
            break
    return picked


def _leading_market(event: dict) -> dict | None:
    markets = [m for m in event.get("markets") or [] if _yes_price(m) is not None]
    if not markets:
        return None
    # For a grouped event ("who wins?"), the leader is the highest-priced
    # outcome; groupItemTitle names it. For a single binary market the market
    # itself leads. Skip effectively-resolved outcomes (a finished game 1 in a
    # BO3 event pins at 100c and says nothing about the event) unless nothing
    # else is left.
    live = [m for m in markets if (_yes_price(m) or 0.0) < 0.99]
    top = max(live or markets, key=lambda m: _yes_price(m) or 0.0)
    return {
        "name": top.get("groupItemTitle") or top.get("question") or "",
        "yes": _yes_price(top),
    }


def _event_item(event: dict) -> dict:
    title = (event.get("title") or "").strip()
    leader = _leading_market(event)
    # A single-market event's leader is the event itself; repeating the title
    # as the leader name is noise (keep its price).
    if leader and leader.get("name", "").strip() == title:
        leader = {**leader, "name": ""}
    return {
        "title": title,
        "url": f"https://polymarket.com/event/{event.get('slug', '')}",
        "volume24h": _f(event.get("volume24hr")) or 0.0,
        "end": _when(event.get("endDate")),
        "leader": leader,
    }


def select_top_events(events: list[dict], limit: int = 5) -> list[dict]:
    """Most traded events of the last 24h."""
    items = [_event_item(e) for e in events]
    items = [i for i in items if i["volume24h"] > 0]
    items.sort(key=lambda i: i["volume24h"], reverse=True)
    return items[:limit]


def select_ending_soon(
    events: list[dict], now: datetime, horizon_hours: int = 48, limit: int = 5
) -> list[dict]:
    """Liquid events resolving inside the horizon, soonest first.

    The window is full of 5-minute crypto up/down micro-markets; the volume
    floor keeps only events people actually trade.
    """
    horizon = now + timedelta(hours=horizon_hours)
    by_family: dict[str, dict] = {}
    for event in events:
        item = _event_item(event)
        if item["end"] is None or not now <= item["end"] <= horizon:
            continue
        if item["volume24h"] < ENDING_MIN_VOLUME:
            continue
        fam = _family(item["url"])
        if fam not in by_family or item["volume24h"] > by_family[fam]["volume24h"]:
            by_family[fam] = item
    items = sorted(by_family.values(), key=lambda i: i["end"])
    return items[:limit]


def select_new_markets(
    markets: list[dict], now: datetime, age_hours: int = 48, limit: int = 5
) -> list[dict]:
    """Markets created inside the window that already attract volume."""
    cutoff = now - timedelta(hours=age_hours)
    seen_events: set[str] = set()
    picked = []
    for market in sorted(markets, key=lambda m: _f(m.get("volume24hr")) or 0.0, reverse=True):
        created = _when(market.get("createdAt"))
        if created is None or created < cutoff:
            continue
        item = _market_item(market)
        if item is None or item["volume24h"] < NEW_MIN_VOLUME:
            continue
        # A "new" market past its endDate is a finished game, not news
        # (seen live: a same-day MLB over/under at 0.1c after the game).
        if item["end"] is not None and item["end"] < now:
            continue
        if not NEW_PRICE_BAND[0] <= item["yes"] <= NEW_PRICE_BAND[1]:
            continue
        fam = _family(item["url"])
        if fam in seen_events:
            continue
        seen_events.add(fam)
        picked.append(item)
        if len(picked) >= limit:
            break
    return picked


def build_digest(now: datetime | None = None, fetch=fetch_json) -> dict:
    """Fetch and assemble all sections. A failed section is dropped, not fatal."""
    now = now or datetime.now(UTC)
    base = {"active": "true", "closed": "false", "ascending": "false", "limit": "100"}

    def section(fn):
        try:
            return fn()
        except Exception:  # noqa: BLE001 - one bad section must not kill the digest
            return []

    def movers():
        up = fetch("/markets", {**base, "order": "oneDayPriceChange"})
        down = fetch("/markets", {**base, "order": "oneDayPriceChange", "ascending": "true"})
        return select_movers(up + down)

    def top_events():
        return select_top_events(fetch("/events", {**base, "order": "volume24hr", "limit": "25"}))

    def ending_soon():
        fmt = "%Y-%m-%dT%H:%M:%SZ"
        window = fetch(
            "/events",
            {
                **base,
                "order": "endDate",
                "ascending": "true",
                "end_date_min": now.strftime(fmt),
                "end_date_max": (now + timedelta(hours=48)).strftime(fmt),
            },
        )
        return select_ending_soon(window, now)

    def new_markets():
        return select_new_markets(fetch("/markets", {**base, "order": "volume24hr"}), now)

    return {
        "generated_at": now,
        "movers": section(movers),
        "top_events": section(top_events),
        "ending_soon": section(ending_soon),
        "new_markets": section(new_markets),
    }


def digest_is_empty(digest: dict) -> bool:
    return not any(
        digest.get(key) for key in ("movers", "top_events", "ending_soon", "new_markets")
    )
