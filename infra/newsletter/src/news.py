"""Recent news headlines for mover markets (Google News RSS, stdlib only).

The digest data says WHAT moved; headlines are the raw material for WHY.
Query building and RSS parsing are pure (unit-tested); fetch_mover_context
touches the network and fails open - a mover without context simply gets no
"why" line.
"""

import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

USER_AGENT = "Mozilla/5.0 (compatible; polymarket-tui-newsletter/1.0)"
MAX_MOVERS_WITH_CONTEXT = 3
HEADLINES_PER_MOVER = 5
MAX_HEADLINE_AGE_HOURS = 96

# Question scaffolding that carries no search signal.
_STOPWORDS = {
    "will", "be", "the", "a", "an", "new", "for", "in", "on", "of", "to",
    "by", "at", "vs", "vs.", "is", "are", "do", "does", "and", "or", "who",
    "what", "which", "how", "many", "much", "this", "that", "it",
    "before", "after", "between", "during",
}


def build_news_query(title: str) -> str:
    words = [w.strip(".,;:!?()[]") for w in title.split()]
    kept = [w for w in words if w and w.lower() not in _STOPWORDS]
    return " ".join(kept[:8])


def parse_news_rss(xml_bytes: bytes, now: datetime) -> list[str]:
    """Fresh headlines as "Title - Source (Fri 17 Jul)" lines, newest first."""
    root = ET.fromstring(xml_bytes)
    cutoff = now - timedelta(hours=MAX_HEADLINE_AGE_HOURS)
    dated = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        try:
            published = parsedate_to_datetime(item.findtext("pubDate") or "")
        except (ValueError, TypeError):
            continue
        if published < cutoff or published > now + timedelta(hours=1):
            continue
        dated.append((published, f"{title} ({published.strftime('%a %-d %b')})"))
    dated.sort(key=lambda pair: pair[0], reverse=True)
    return [line for _, line in dated[:HEADLINES_PER_MOVER]]


def fetch_mover_context(movers: list[dict], now: datetime) -> dict[str, list[str]]:
    """url -> fresh headline lines for the top movers. Any failure -> no lines."""
    context: dict[str, list[str]] = {}
    for item in movers[:MAX_MOVERS_WITH_CONTEXT]:
        query = build_news_query(item["title"])
        if not query:
            continue
        url = (
            "https://news.google.com/rss/search?q="
            + urllib.parse.quote(query)
            + "&hl=en-US&gl=US&ceid=US:en"
        )
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=8) as resp:
                lines = parse_news_rss(resp.read(), now)
        except Exception:  # noqa: BLE001 - missing context must not block the digest
            lines = []
        if lines:
            context[item["url"]] = lines
    return context
