#!/usr/bin/env bash
# Upload a short to YouTube via the Data API resumable flow.
#
#   upload_youtube.sh <video.mp4> <title> <description-file>
#
# Needs YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET / YOUTUBE_REFRESH_TOKEN in
# the environment (GH secrets in CI; doppler run locally).
#
# YOUTUBE_PRIVACY defaults to private: until the project passes YouTube's
# compliance audit, the API forces private anyway - defaulting to it keeps the
# behaviour identical before and after rather than silently different. Flip
# the workflow to public once the audit clears.
#
# Prints the video id on success.
set -euo pipefail

VIDEO="${1:?usage: upload_youtube.sh <video.mp4> <title> <description-file>}"
TITLE="${2:?title required}"
DESC_FILE="${3:?description file required}"
PRIVACY="${YOUTUBE_PRIVACY:-private}"

ACCESS_TOKEN="$(curl -sf https://oauth2.googleapis.com/token \
    -d client_id="$YOUTUBE_CLIENT_ID" \
    -d client_secret="$YOUTUBE_CLIENT_SECRET" \
    -d refresh_token="$YOUTUBE_REFRESH_TOKEN" \
    -d grant_type=refresh_token | jq -r .access_token)"
[ -n "$ACCESS_TOKEN" ] && [ "$ACCESS_TOKEN" != "null" ] || {
    echo "token refresh failed" >&2
    exit 1
}

META="$(jq -n --arg t "$TITLE" --rawfile d "$DESC_FILE" --arg p "$PRIVACY" \
    '{snippet: {title: $t, description: $d, categoryId: "28"},
      status: {privacyStatus: $p, selfDeclaredMadeForKids: false}}')"

UPLOAD_URL="$(curl -sf -D - -o /dev/null \
    -X POST "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "Content-Type: application/json" \
    -d "$META" | tr -d '\r' | awk 'tolower($1)=="location:"{print $2}')"
[ -n "$UPLOAD_URL" ] || {
    echo "no resumable upload url" >&2
    exit 1
}

curl -sf -X PUT "$UPLOAD_URL" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "Content-Type: video/mp4" \
    --data-binary @"$VIDEO" | jq -r .id
