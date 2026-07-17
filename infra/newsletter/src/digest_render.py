"""Render the digest as text + HTML email, plus the API's small web pages.

Emails use a light background (dark-mode email clients invert unpredictably)
with the site's mono aesthetic; {{UNSUB_URL}} is replaced per recipient.
"""

import html
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

SITE_NAME = "polymarket-tui"

# The schedule fires at 07:00 Pacific/Auckland (19:00 UTC the previous day);
# date the email for that morning, not for UTC.
try:
    DISPLAY_TZ = ZoneInfo("Pacific/Auckland")
except Exception:  # noqa: BLE001 - missing tzdata must not block a send
    DISPLAY_TZ = UTC

ACCENT = "#2f6fdb"
GREEN = "#1e8a4c"
RED = "#c6423a"
INK = "#16202c"
DIM = "#5c6a7a"
LINE = "#dde3ea"
MONO = "ui-monospace, 'SF Mono', Menlo, Consolas, monospace"

UNSUB_PLACEHOLDER = "{{UNSUB_URL}}"


def fmt_cents(price: float) -> str:
    cents = price * 100
    if cents < 1 or cents > 99:
        return f"{cents:.1f}".rstrip("0").rstrip(".") + "c"
    return f"{cents:.0f}c"


def fmt_change(change: float) -> str:
    return f"{change * 100:+.0f}c"


def fmt_usd(value: float) -> str:
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}m"
    if value >= 1_000:
        return f"${value / 1_000:.0f}k"
    return f"${value:.0f}"


def fmt_when(end: datetime | None) -> str:
    if end is None:
        return ""
    return end.strftime("%a %b %-d, %H:%M UTC")


def render_subject(now: datetime) -> str:
    return f"Polymarket daily - {now.astimezone(DISPLAY_TZ).strftime('%a %-d %b')}"


# --- plain text ---


def _text_market_line(item: dict, with_change: bool) -> list[str]:
    bits = [f"YES {fmt_cents(item['yes'])}"]
    if with_change:
        bits.append(fmt_change(item["change"]))
    bits.append(f"{fmt_usd(item['volume24h'])} 24h vol")
    return [f"* {item['title']} ({', '.join(bits)})", f"  {item['url']}"]


def _text_event_line(item: dict, with_end: bool) -> list[str]:
    bits = [f"{fmt_usd(item['volume24h'])} 24h vol"]
    leader = item.get("leader")
    if leader and leader.get("name"):
        bits.append(f"leader: {leader['name']} {fmt_cents(leader['yes'])}")
    if with_end and item.get("end"):
        bits.append(f"ends {fmt_when(item['end'])}")
    return [f"* {item['title']} ({', '.join(bits)})", f"  {item['url']}"]


def render_text(digest: dict) -> str:
    lines = [
        f"{SITE_NAME} / daily digest",
        digest["generated_at"].astimezone(DISPLAY_TZ).strftime("%A %-d %B %Y"),
        "",
    ]
    sections = [
        ("TOP MOVERS (24H)", digest["movers"], lambda i: _text_market_line(i, True)),
        ("MOST TRADED (24H)", digest["top_events"], lambda i: _text_event_line(i, False)),
        ("ENDING WITHIN 48H", digest["ending_soon"], lambda i: _text_event_line(i, True)),
        ("NEW AND ALREADY BUSY", digest["new_markets"], lambda i: _text_market_line(i, False)),
    ]
    for title, items, line_fn in sections:
        if not items:
            continue
        lines.append(title)
        for item in items:
            lines.extend(line_fn(item))
        lines.append("")
    lines += [
        "--",
        f"Sent by {SITE_NAME}, an unofficial Polymarket terminal client.",
        "Prices are market odds, not advice.",
        f"Unsubscribe: {UNSUB_PLACEHOLDER}",
    ]
    return "\n".join(lines)


# --- HTML ---


def _row(left: str, right: str) -> str:
    return (
        '<tr><td style="padding:8px 0;border-bottom:1px solid '
        + LINE
        + ';font-size:13px;line-height:1.5;">'
        + left
        + '</td><td align="right" style="padding:8px 0 8px 14px;border-bottom:1px solid '
        + LINE
        + ';font-size:13px;white-space:nowrap;vertical-align:top;">'
        + right
        + "</td></tr>"
    )


def _html_market_row(item: dict, with_change: bool) -> str:
    title = html.escape(item["title"])
    left = (
        f'<a href="{html.escape(item["url"])}"'
        f' style="color:{INK};text-decoration:none;">{title}</a>'
        f'<br><span style="color:{DIM};font-size:11px;">{fmt_usd(item["volume24h"])} 24h vol</span>'
    )
    right = f'<span style="color:{INK};font-weight:bold;">{fmt_cents(item["yes"])}</span>'
    if with_change:
        color = GREEN if item["change"] >= 0 else RED
        change = fmt_change(item["change"])
        right += f'<br><span style="color:{color};font-size:12px;">{change}</span>'
    return _row(left, right)


def _html_event_row(item: dict, with_end: bool) -> str:
    title = html.escape(item["title"])
    sub = f"{fmt_usd(item['volume24h'])} 24h vol"
    leader = item.get("leader")
    if leader and leader.get("name"):
        sub += f" &middot; {html.escape(leader['name'])} {fmt_cents(leader['yes'])}"
    if with_end and item.get("end"):
        sub += f" &middot; ends {fmt_when(item['end'])}"
    left = (
        f'<a href="{html.escape(item["url"])}"'
        f' style="color:{INK};text-decoration:none;">{title}</a>'
        f'<br><span style="color:{DIM};font-size:11px;">{sub}</span>'
    )
    right = ""
    if leader and leader.get("yes") is not None:
        right = f'<span style="color:{INK};font-weight:bold;">{fmt_cents(leader["yes"])}</span>'
    return _row(left, right)


def _html_section(title: str, rows: list[str]) -> str:
    if not rows:
        return ""
    return (
        f'<tr><td colspan="2" style="padding:26px 0 4px;font-size:11px;letter-spacing:2px;'
        f'color:{DIM};">{title}</td></tr>' + "".join(rows)
    )


def render_html(digest: dict, site_url: str) -> str:
    body_sections = (
        _html_section(
            "TOP MOVERS (24H)", [_html_market_row(i, True) for i in digest["movers"]]
        )
        + _html_section(
            "MOST TRADED (24H)", [_html_event_row(i, False) for i in digest["top_events"]]
        )
        + _html_section(
            "ENDING WITHIN 48H", [_html_event_row(i, True) for i in digest["ending_soon"]]
        )
        + _html_section(
            "NEW AND ALREADY BUSY",
            [_html_market_row(i, False) for i in digest["new_markets"]],
        )
    )
    date_line = digest["generated_at"].astimezone(DISPLAY_TZ).strftime("%A %-d %B %Y")
    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#f4f6f8;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f8;">
<tr><td align="center" style="padding:24px 12px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0"
  style="max-width:600px;width:100%;background:#ffffff;border:1px solid {LINE};
  font-family:{MONO};color:{INK};">
<tr><td style="padding:22px 28px 0;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
    <tr><td style="font-size:14px;font-weight:bold;">
      <span style="color:{ACCENT};">&gt;_</span> {SITE_NAME}
      <span style="color:{DIM};font-weight:normal;">/ daily digest</span>
    </td><td align="right" style="font-size:11px;color:{DIM};">{date_line}</td></tr>
  </table>
</td></tr>
<tr><td style="padding:0 28px 24px;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
    {body_sections}
  </table>
</td></tr>
<tr><td style="padding:16px 28px 22px;border-top:1px solid {LINE};font-size:11px;
  color:{DIM};line-height:1.7;">
  Sent by <a href="{site_url}" style="color:{DIM};">{SITE_NAME}</a>, an unofficial Polymarket
  terminal client. Prices are market odds, not advice.<br>
  <a href="{UNSUB_PLACEHOLDER}" style="color:{DIM};">Unsubscribe</a>
</td></tr>
</table>
</td></tr>
</table>
</body></html>"""


# --- confirmation email ---


def render_confirm_text(confirm_url: str) -> str:
    return (
        f"Confirm your {SITE_NAME} daily digest subscription:\n\n"
        f"{confirm_url}\n\n"
        "One email a day with Polymarket movers, volume leaders, and markets\n"
        "about to resolve. If you didn't sign up, ignore this and nothing\n"
        "will be sent again."
    )


def render_confirm_html(confirm_url: str) -> str:
    url = html.escape(confirm_url)
    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#f4f6f8;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f8;">
<tr><td align="center" style="padding:24px 12px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0"
  style="max-width:600px;width:100%;background:#ffffff;border:1px solid {LINE};
  font-family:{MONO};color:{INK};">
<tr><td style="padding:26px 28px;">
  <div style="font-size:14px;font-weight:bold;margin-bottom:14px;">
    <span style="color:{ACCENT};">&gt;_</span> {SITE_NAME}
  </div>
  <div style="font-size:13px;line-height:1.7;margin-bottom:20px;">
    Confirm your daily digest subscription: one email a day with Polymarket
    movers, volume leaders, and markets about to resolve.
  </div>
  <a href="{url}" style="display:inline-block;background:{ACCENT};color:#ffffff;
    font-size:13px;font-weight:bold;padding:10px 18px;
    text-decoration:none;">Confirm subscription</a>
  <div style="font-size:11px;color:{DIM};line-height:1.7;margin-top:20px;">
    If you didn't sign up, ignore this email and nothing will be sent again.
  </div>
</td></tr>
</table>
</td></tr>
</table>
</body></html>"""


# --- API web pages (confirm / unsubscribe land here from email links) ---


def page_html(title: str, message: str, site_url: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} - {SITE_NAME}</title>
<meta name="robots" content="noindex">
</head>
<body style="margin:0;background:#0a0e14;color:#c9d3df;font-family:{MONO};
  display:flex;align-items:center;justify-content:center;min-height:100vh;">
<div style="max-width:520px;padding:40px 28px;border:1px solid #1b232e;">
  <div style="font-size:14px;font-weight:bold;margin-bottom:16px;">
    <span style="color:#4d8bf5;">&gt;_</span> {SITE_NAME}
  </div>
  <div style="font-size:16px;font-weight:bold;margin-bottom:10px;color:#ffffff;">{
    html.escape(title)}</div>
  <div style="font-size:13px;line-height:1.7;color:#828f9e;">{html.escape(message)}</div>
  <div style="margin-top:22px;font-size:12px;">
    <a href="{site_url}" style="color:#4d8bf5;text-decoration:none;">&larr;
      {SITE_NAME.replace("-", "&#8209;")}</a>
  </div>
</div>
</body></html>"""
