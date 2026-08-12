#!/usr/bin/env python3
"""Mint the YouTube upload refresh token and store it in Doppler.

    uv run --with google-auth-oauthlib python scripts/shorts/mint_youtube_token.py \
        ~/Downloads/client_secret_*.json

Opens a browser for the one-time OAuth consent. Sign in as the channel owner
and, on the account chooser, pick the BRAND channel the shorts should post to
(create "polymarket-tui" there if it does not exist yet) - the refresh token
is bound to whichever channel you pick.

Secrets never touch stdout or the repo: client id/secret and the refresh
token go straight into Doppler (polymarket-tui/prd) via the CLI, and the
local client-secret file is best deleted afterwards. The daily workflow reads
them from GitHub secrets - sync with:

    doppler secrets get --project polymarket-tui --config prd --plain YOUTUBE_CLIENT_ID \
      | gh secret set YOUTUBE_CLIENT_ID   # and likewise for the other two
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
DOPPLER = ["doppler", "secrets", "set", "--project", "polymarket-tui", "--config", "prd"]


def store(name: str, value: str) -> None:
    # Value via stdin so it never appears in the process table.
    subprocess.run([*DOPPLER, name], input=value, text=True, check=True,
                   stdout=subprocess.DEVNULL)


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
          "in Doppler polymarket-tui/prd.")
    print(f"You can now delete {client_file}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
