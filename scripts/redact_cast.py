"""Redact account identity from a recorded demo cast (asciinema v2).

The landing-page demo records an authed DRY session, so the header strip
carries the public profile name (or the funder short-form fallback).
Balances are already masked at the source (POLYMARKET_HIDE_BALANCES);
this rewrites the identity strings and then verifies the whole
ANSI-stripped output stream, failing loudly if anything survived - a
value split across output events would dodge substitution but not the
verify pass.

Usage:
    python3 redact_cast.py in.cast out.cast --funder 0x... [--name profile]
"""

from __future__ import annotations

import argparse
import json
import re
import sys

ANSI = re.compile(r"\x1b(\[[0-9;:?]*[a-zA-Z]|\][^\x07\x1b]*(\x07|\x1b\\)|[()][0-9A-B])")
CASH_VALUE = re.compile(r"(cash|pf) (is )?\$\d")  # header strip or the
# "Costs $X but cash is $Y" validation message - either means a real
# balance rendered despite POLYMARKET_HIDE_BALANCES


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--funder", required=True)
    ap.add_argument("--name", default=None)
    args = ap.parse_args()

    short = f"{args.funder[:6]}...{args.funder[-4:]}"
    subs: list[tuple[re.Pattern[str], str]] = [
        (re.compile(re.escape(args.funder), re.IGNORECASE), "0x" + "0" * 40),
        (re.compile(re.escape(short), re.IGNORECASE), "0xd3m0...cafe"),
    ]
    if args.name:
        subs.insert(0, (re.compile(re.escape(args.name)), "demo-trader"))

    out_lines: list[str] = []
    stream: list[str] = []
    with open(args.src) as f:
        out_lines.append(f.readline().rstrip("\n"))  # header
        for line in f:
            event = json.loads(line)
            if event[1] == "o":
                for pattern, repl in subs:
                    event[2] = pattern.sub(repl, event[2])
                stream.append(event[2])
            out_lines.append(json.dumps(event))

    plain = ANSI.sub("", "".join(stream))
    leaks = [
        needle
        for needle in (args.name, args.funder, args.funder.lower(), short)
        if needle and needle in plain
    ]
    if CASH_VALUE.search(plain):
        leaks.append("cash/pf dollar value (POLYMARKET_HIDE_BALANCES was off?)")
    if leaks:
        print(f"REFUSING to write {args.out} - leaked: {leaks}", file=sys.stderr)
        return 2

    with open(args.out, "w") as f:
        f.write("\n".join(out_lines) + "\n")
    print(f"redacted -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
