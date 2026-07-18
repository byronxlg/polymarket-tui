"""LLM-written headlines for the daily digest (Claude on Bedrock).

One converse call produces the subject line, the hidden preheader, and the
2-sentence intro blurb as JSON. Prompt building and response validation are
pure (unit-tested); only generate_headlines touches AWS, and any failure
returns {} - the digest ships with deterministic fallbacks rather than not
at all.
"""

import json
import logging

from digest_render import fmt_cents, fmt_change, fmt_usd, fmt_when_nz

logger = logging.getLogger()

MAX_BLURB_CHARS = 700
MAX_SUBJECT_CHARS = 60  # " - Polymarket daily" rides behind; mobile clips ~60
MAX_PREHEADER_CHARS = 110


def _fact_lines(digest: dict) -> list[str]:
    now = digest["generated_at"]
    lines = []
    for item in digest.get("movers", []):
        prior = min(max(item["yes"] - item["change"], 0.0), 1.0)
        lines.append(
            f"- MOVER: {item['title']} moved {fmt_cents(prior)} -> {fmt_cents(item['yes'])} YES "
            f"({fmt_change(item['change'])} in 24h, {fmt_usd(item['volume24h'])} volume)"
        )
    for item in digest.get("top_events", []):
        leader = item.get("leader") or {}
        lead = ""
        if leader.get("name"):
            lead = f", leader {leader['name']} at {fmt_cents(leader['yes'])}"
        lines.append(
            f"- MOST TRADED: {item['title']} ({fmt_usd(item['volume24h'])} 24h volume{lead})"
        )
    for item in digest.get("ending_soon", []):
        when = fmt_when_nz(item["end"], now) if item.get("end") else "soon"
        lines.append(f"- RESOLVING {when}: {item['title']}")
    for item in digest.get("new_markets", []):
        outcome = f" ({item['outcome']})" if item.get("outcome") else ""
        lines.append(
            f"- NEW MARKET: {item['title']}{outcome} at {fmt_cents(item['yes'])} YES "
            f"({fmt_usd(item['volume24h'])} volume already)"
        )
    return lines


def build_headlines_prompt(digest: dict) -> str:
    facts = "\n".join(_fact_lines(digest))
    return (
        "You write the envelope copy for a daily Polymarket digest email read by "
        "prediction-market traders. Below is today's data; the reader sees it in "
        "full inside the email.\n\n"
        f"{facts}\n\n"
        "Produce exactly this JSON (no other text):\n"
        '{"subject": ..., "preheader": ..., "blurb": ...}\n\n'
        "subject: under 55 characters. It MUST be about the first MOVER line "
        "(the day's lead story), stated with its numbers (e.g. \"Nordone 11c "
        "-> 69c for SC Senate\"). No date, no 'Polymarket daily' prefix - "
        "those are added elsewhere.\n"
        "preheader: under 100 characters. A story from a DIFFERENT line than "
        "the subject. Shown next to the subject in the inbox preview.\n"
        "blurb: at most 2 sentences, the email's opening. Sentence one goes "
        "deeper on the lead story (prior price, how thin or deep the volume "
        "is). Sentence two must draw from a different section (what resolves "
        "when, where the volume is). Do not restate every row - the reader "
        "sees them all next.\n\n"
        "Rules for all three: plain text, no markdown or emoji. Prices in "
        "cents (59c), never percent. Times in NZ reader time exactly as the data "
        "writes them (today 4pm NZT), never UTC. Keep symbols as the data writes "
        "them (19\u00b0C stays 19\u00b0C). Superlatives like 'most active' or "
        "'biggest' only when the data literally shows it. State facts only - "
        "no speculation about causes; banned words: surge, soar, rocket, "
        "explode, massive, huge, serious, incredible, dramatic, suggesting, "
        "likely, appears, stay tuned. Never invent facts not in the data. "
        "Never give advice."
    )


def _clean(raw: object, max_chars: int) -> str | None:
    if not isinstance(raw, str):
        return None
    text = " ".join(raw.strip().split())
    if not text or len(text) > max_chars:
        return None
    return text


def extract_headlines(raw: object) -> dict:
    """Parse and validate the model's JSON; invalid fields drop to fallbacks."""
    if not isinstance(raw, str):
        return {}
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        data = json.loads(raw[start : end + 1])
    except ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    out = {
        "subject": _clean(data.get("subject"), MAX_SUBJECT_CHARS),
        "preheader": _clean(data.get("preheader"), MAX_PREHEADER_CHARS),
        "blurb": _clean(data.get("blurb"), MAX_BLURB_CHARS),
    }
    return {k: v for k, v in out.items() if v is not None}


def generate_headlines(digest: dict, model_id: str) -> dict:
    """One Bedrock converse call; any failure logs and returns {}."""
    try:
        import boto3
        from botocore.config import Config

        client = boto3.client(
            "bedrock-runtime",
            config=Config(connect_timeout=5, read_timeout=60, retries={"max_attempts": 1}),
        )
        response = client.converse(
            modelId=model_id,
            messages=[
                {"role": "user", "content": [{"text": build_headlines_prompt(digest)}]}
            ],
            inferenceConfig={"maxTokens": 400},
        )
        headlines = extract_headlines(response["output"]["message"]["content"][0]["text"])
        if not headlines:
            logger.error("headline JSON rejected by validation; using fallbacks")
        return headlines
    except Exception:  # noqa: BLE001 - headlines must never block the digest
        logger.exception("headline generation failed; using fallbacks")
        return {}
