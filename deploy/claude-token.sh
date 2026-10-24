#!/usr/bin/env bash
# Let the server's editor run on your Claude subscription. `claude setup-token` signs you in in the browser and
# prints a long-lived token; paste it when asked (nothing is echoed) and it goes straight into the server's
# secrets/zhiyin.env. Run it in your own terminal.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f deploy/local.conf ] && . deploy/local.conf
: "${KEY:?set KEY}" "${HOST:?set HOST}" "${SITE:?set SITE}"
GATEWAY_NETWORK=${GATEWAY_NETWORK:-proxy}

claude setup-token
printf '\nPaste the token it printed (hidden): '
read -rs TOKEN
echo
[ -n "$TOKEN" ] || { echo "no token, nothing changed"; exit 1; }
printf '%s\n' "$TOKEN" | ssh -i "$KEY" "$HOST" "sudo SITE=$SITE GATEWAY_NETWORK=$GATEWAY_NETWORK bash -c '
set -euo pipefail
read -r TOKEN
F=/opt/zhiyin/secrets/zhiyin.env
umask 077
{ grep -v \"^CLAUDE_CODE_OAUTH_TOKEN=\" \$F 2>/dev/null || true; echo \"CLAUDE_CODE_OAUTH_TOKEN=\$TOKEN\"; } > \$F.new
chmod 600 \$F.new && mv \$F.new \$F
cd /opt/zhiyin && env ZHIYIN_PUBLIC_URL=\$SITE GATEWAY_NETWORK=\$GATEWAY_NETWORK docker compose up -d --force-recreate 2>&1 | tail -1
for i in \$(seq 1 40); do docker exec zhiyin curl -fsS http://127.0.0.1:8817/healthz >/dev/null 2>&1 && break; sleep 1; done
printf \"Claude on the server: \"; docker exec zhiyin claude -p \"Reply with the single word: ready\" --model sonnet
'"
unset TOKEN
