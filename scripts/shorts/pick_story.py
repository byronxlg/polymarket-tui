#!/usr/bin/env python3
"""Pick today's short story from live Polymarket data and emit a beat sheet.

    pick_story.py <outdir> [--exclude slug ...]

Writes <outdir>/daily-<date>.json (a record.sh beat sheet) and prints its path.
--exclude skips event slugs already used this week, so consecutive days do not
retell the same market.

Selection: among high-volume live events, score by how hard the lead market
repriced in 24h, weighted by volume. A market that moved is a story; a market
that sat still is a screenshot. Sports/esports titles are excluded not because
they are bad markets but because "LoL: X vs Y" is a weak hook for a general
audience and the matches are over before the video is.

Two story shapes:
- ladder: the event prices one question at several dates (Fed meetings,
  "by August 31?" families) - the story is the curve.
- mover: a single market that repriced - the story is the move.

Captions never contain prices: the market moves between generation and
recording. Wording states what the screen shows, not numbers.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
import sys
import urllib.request
from pathlib import Path

GAMMA = "https://gamma-api.polymarket.com"
SPORT = re.compile(
    r"LoL|Counter-Strike|Esports|CS2|Dota|Valorant|BO3| vs\.? |O/U|"
    r"win on \d|Grand Prix|F1\b|NBA|NFL|MLB|NHL|UFC|Premier League|Serie A",
    re.I,
)
DATEISH = re.compile(
    r"by (January|February|March|April|May|June|July|August|September|October|"
    r"November|December|\w+ \d+)|in (January|February|March|April|May|June|July|"
    r"August|September|October|November|December)\?|by \d{4}",
    re.I,
)
STOP = {"will", "the", "a", "an", "of", "in", "on", "by", "to", "be", "is", "and", "or", "for"}


def fetch(path: str):
    req = urllib.request.Request(GAMMA + path, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as fh:
        return json.load(fh)


def lead_market(event: dict) -> dict | None:
    best, best_v = None, -1.0
    for m in event.get("markets", []):
        if m.get("closed") or not m.get("active"):
            continue
        try:
            price = float(json.loads(m["outcomePrices"])[0])
        except (KeyError, ValueError, IndexError):
            continue
        vol = float(m.get("volume24hr") or 0)
        # Settled-in-all-but-name markets have no story left to tell.
        if not 0.03 < price < 0.97:
            continue
        # A market expiring within days is churn (the daily crypto strike
        # ladders): the video outlives the market. Keep stories with runway.
        end = m.get("endDate") or ""
        try:
            endd = dt.datetime.fromisoformat(end.replace("Z", "+00:00"))
            if (endd - dt.datetime.now(dt.UTC)).days < 3:
                continue
        except ValueError:
            pass
        if vol > best_v:
            best, best_v = m, vol
    return best


def score(event: dict, market: dict) -> float:
    try:
        change = abs(float(market.get("oneDayPriceChange") or 0))
    except (TypeError, ValueError):
        change = 0.0
    vol = float(event.get("volume24hr") or 0)
    if vol < 50_000:
        return 0.0
    return change * math.log10(max(vol, 10))


def search_query(title: str) -> str:
    """A query the TUI's search will resolve to this event as the top hit.

    Distinctive words beat complete words: 'strait of hormuz traffic' finds the
    family, and the picker's target is the highest-volume member, which is what
    the app's search ranks first for the same reason.
    """
    words = re.sub(r"[^\w\s]", " ", title).split()
    kept = [w for w in words if w.lower() not in STOP and not re.fullmatch(r"_+", w)][:4]
    return " ".join(kept).lower()


def is_ladder(event: dict) -> bool:
    dated = sum(1 for m in event.get("markets", []) if DATEISH.search(m.get("question", "")))
    return dated >= 3


def build_sheet(event: dict, market: dict, today: str) -> dict:
    title = event["title"].rstrip("?")
    ladder = is_ladder(event)
    headline = (title[:64] + "?") if not title.endswith("?") else title[:64]

    # Both shapes end on the market screen's book and chart, never the
    # expanded tape (its cursor rail foregrounds a named trader's wallet) and
    # never holding on the event screen: agg's terminal emulation diverges
    # from tmux there and leaves ghost text in the chart area, so the event
    # screen appears only as a transient hop. A ladder's curve is shown via
    # the search preview rail instead, which renders it clean.
    query = search_query(event["title"])
    if ladder:
        beats = [
            {"caption": "One question. A price for every date.", "wait": 1.8, "focus": "left"},
            {"caption": "Search it", "keys": ["/"], "wait": 0.9, "focus": "mid"},
            {"caption": "The whole curve, right in the preview", "type": query, "wait": 3.2,
             "focus": "right"},
            {"caption": "Pick a date", "keys": ["Down", "Enter"], "wait": 2.2, "focus": "left"},
            {"caption": "Its order book, streaming", "keys": ["Enter"], "wait": 3.4,
             "focus": "left"},
            {"caption": "Cursor the depth", "keys": ["Down", "Down", "Down"], "wait": 2.6,
             "focus": "left"},
            # No timeframe cycle here: a near-resolved date's 1H chart is a
            # flat line; the ALL view keeps the run-up on screen.
            {"caption": "The repricing, drawn live", "wait": 3.2, "focus": "mid"},
        ]
    else:
        beats = [
            {"caption": "This market repriced today", "wait": 1.8, "focus": "left"},
            {"caption": "Search it", "keys": ["/"], "wait": 0.9, "focus": "mid"},
            {"caption": "Straight to the market", "type": query, "wait": 2.6, "focus": "mid"},
            {"caption": "Live order book, streaming", "keys": ["Down", "Enter"], "wait": 3.6,
             "focus": "left"},
            {"caption": "Cursor the depth", "keys": ["Down", "Down", "Down"], "wait": 2.8,
             "focus": "left"},
            {"caption": "The tape prints beside it", "keys": [], "wait": 2.2, "focus": "right"},
            {"caption": "And the repricing, drawn live", "keys": ["t"], "wait": 3.4,
             "focus": "mid"},
        ]
    return {
        "slug": f"daily-{today}",
        "headline": headline,
        "tag": "uv tool install polymarket-tui",
        "pan": True,
        "story": {"shape": "ladder" if ladder else "mover", "event": event["slug"],
                  "market": market["question"], "picked": today},
        "beats": beats,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir", type=Path)
    ap.add_argument("--exclude", nargs="*", default=[])
    args = ap.parse_args()

    events = fetch("/events?active=true&closed=false&order=volume24hr&ascending=false&limit=60")
    ranked = []
    for event in events:
        if SPORT.search(event.get("title", "")):
            continue
        if event.get("slug") in args.exclude:
            continue
        market = lead_market(event)
        if market is None:
            continue
        ranked.append((score(event, market), event, market))
    ranked.sort(key=lambda r: r[0], reverse=True)
    if not ranked or ranked[0][0] <= 0:
        print("no story cleared the bar", file=sys.stderr)
        return 1

    _, event, market = ranked[0]
    today = dt.date.today().isoformat()
    sheet = build_sheet(event, market, today)
    args.outdir.mkdir(parents=True, exist_ok=True)
    out = args.outdir / f"{sheet['slug']}.json"
    out.write_text(json.dumps(sheet, indent=2) + "\n")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
