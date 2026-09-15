#!/usr/bin/env python3
"""Mint the YouTube upload refresh token and store it in SSM Parameter Store.

    uv run --with google-auth-oauthlib python scripts/shorts/mint_youtube_token.py \
        ~/Downloads/client_secret_*.json

Opens a browser for the one-time OAuth consent. Sign in as the channel owner
and, on the account chooser, pick the BRAND channel the shorts should post to
(create "polymarket-tui" there if it does not exist yet) - the refresh token
is bound to whichever channel you pick.

Secrets never touch stdout or the repo: client id/secret and the refresh
token go straight into SSM (/polymarket-tui/prd/<KEY>, management D28) via
the AWS CLI under the admin keys, and the local client-secret file is best
deleted afterwards. Run it as:

    doppler run --project global --config home -- \
        uv run --with google-auth-oauthlib python scripts/shorts/mint_youtube_token.py ...

The daily workflow reads them from GitHub secrets - sync with:

    doppler run --project global --config home -- chamber exec polymarket-tui/prd -- \
        sh -c 'printf %s "$YOUTUBE_CLIENT_ID" | gh secret set YOUTUBE_CLIENT_ID'   # and likewise for the other two
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
SSM_PREFIX = "/polymarket-tui/prd/"
REGION = "ap-southeast-2"


def store(name: str, value: str) -> None:
    # Value via a 0600 temp file so it never appears in the process table.
    doc = {"Name": SSM_PREFIX + name, "Type": "SecureString", "Value": value,
           "Description": "YouTube upload credential, minted by scripts/shorts/mint_youtube_token.py",
           "Overwrite": True}
    fd, path = tempfile.mkstemp(suffix=".json")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(doc, f)
        subprocess.run(["aws", "ssm", "put-parameter", "--region", REGION,
                        "--cli-input-json", f"file://{path}"],
                       check=True, stdout=subprocess.DEVNULL)
    finally:
        os.unlink(path)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    client_file = Path(sys.argv[1]).expanduser()
    flow = InstalledAppFlow.from_client_secrets_file(str(client_file), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    if not creds.refresh_token:
        print("no refresh token returned - rerun and approve the consent screen")
        return 1

    client = json.loads(client_file.read_text())["installed"]
    store("YOUTUBE_CLIENT_ID", client["client_id"])
    store("YOUTUBE_CLIENT_SECRET", client["client_secret"])
    store("YOUTUBE_REFRESH_TOKEN", creds.refresh_token)
    print("Stored YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET / YOUTUBE_REFRESH_TOKEN "
          f"in SSM under {SSM_PREFIX}.")
    print(f"You can now delete {client_file}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
