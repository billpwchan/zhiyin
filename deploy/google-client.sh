#!/usr/bin/env bash
# Put the Google OAuth client you downloaded from Google Cloud Console (a "Web application" client, see
# docs/self-hosting.md) on the server. It is read on every sign-in, so no restart is needed.
#   deploy/google-client.sh ~/Downloads/client_secret_….json
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f deploy/local.conf ] && . deploy/local.conf
: "${KEY:?set KEY}" "${HOST:?set HOST}" "${SITE:?set SITE}"
F=${1:?usage: deploy/google-client.sh <downloaded client_secret JSON>}

python3 -I - "$F" "$SITE/auth/google/callback" <<'PY'
import json, sys
c = json.load(open(sys.argv[1]))
w = c.get("web")
if not w:
    sys.exit("this is not a Web application client; create one with type 'Web application'")
if sys.argv[2] not in w.get("redirect_uris", []):
    sys.exit(f"add {sys.argv[2]} to the client's Authorized redirect URIs, download it again, and rerun")
print("client ok:", w["client_id"].split("-")[0] + "-…")
PY
ssh -i "$KEY" "$HOST" "sudo install -m 600 -o 1000 -g 1000 /dev/stdin /opt/zhiyin/data/google_client.json" < "$F"
curl -fsS -o /dev/null -w "Google sign-in: %{http_code} (302 means it is on)\n" "$SITE/auth/google/start"
