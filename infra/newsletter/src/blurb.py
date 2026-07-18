"""LLM-written intro blurb for the daily digest (Claude on Bedrock).

Prompt building and response validation are pure (unit-tested); only
generate_blurb touches AWS, and any failure returns None - the digest ships
without a blurb rather than not at all.
"""

import logging

from digest_render import fmt_cents, fmt_change, fmt_usd

logger = logging.getLogger()

MAX_BLURB_CHARS = 700


def _fact_lines(digest: dict) -> list[str]:
    lines = []
    for item in digest.get("movers", []):
        lines.append(
            f"- MOVER: {item['title']} now {fmt_cents(item['yes'])} YES "
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
        lines.append(f"- RESOLVING SOON: {item['title']}")
    for item in digest.get("new_markets", []):
        lines.append(
            f"- NEW MARKET: {item['title']} at {fmt_cents(item['yes'])} YES "
            f"({fmt_usd(item['volume24h'])} volume already)"
        )
    return lines


def build_blurb_prompt(digest: dict) -> str:
    facts = "\n".join(_fact_lines(digest))
    return (
        "You write the two-to-three sentence intro for a daily Polymarket digest "
        "email read by prediction-market traders. Below is today's data, which the "
        "reader sees in full right under your intro.\n\n"
        f"{facts}\n\n"
        "Write the intro: pick the one or two most interesting stories in the data "
        "and say what happened, plainly. Prices are in cents (a probability: 59c "
        "means 59%). Rules: plain text only, no markdown or emoji; no advice, no "
        "hype, no 'stay tuned'; do not invent facts not in the data; do not list "
        "everything - the sections below the intro already do that. Reply with the "
        "intro text only."
    )


def extract_blurb(raw: object) -> str | None:
    """Validate the model's reply; None means send without a blurb."""
    if not isinstance(raw, str):
        return None
    text = " ".join(raw.strip().split())
    if not text or len(text) > MAX_BLURB_CHARS:
        return None
    return text


def generate_blurb(digest: dict, model_id: str) -> str | None:
    """One Bedrock converse call; any failure logs and returns None."""
    try:
        import boto3
        from botocore.config import Config

        client = boto3.client(
            "bedrock-runtime",
            config=Config(connect_timeout=5, read_timeout=60, retries={"max_attempts": 1}),
        )
        response = client.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": build_blurb_prompt(digest)}]}],
            inferenceConfig={"maxTokens": 300},
        )
        blurb = extract_blurb(response["output"]["message"]["content"][0]["text"])
        if blurb is None:
            logger.error("blurb rejected by validation; sending without one")
        return blurb
    except Exception:  # noqa: BLE001 - the blurb must never block the digest
        logger.exception("blurb generation failed; sending without one")
        return None
