#!/usr/bin/env bash
# Pair this Mac with the server as its audio worker: a new shared token goes into the server's
# secrets/zhiyin.env and this Mac's data/worker.json (it is never printed), the container restarts to read it,
# and the login service switches from the local app to `zhiyin worker`.
# Uses KEY, HOST and SITE from deploy/local.conf, like deploy.sh.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f deploy/local.conf ] && . deploy/local.conf
: "${KEY:?set KEY}" "${HOST:?set HOST}" "${SITE:?set SITE}"
GATEWAY_NETWORK=${GATEWAY_NETWORK:-proxy}

TOKEN=$(openssl rand -hex 24)
printf '%s\n' "$TOKEN" | ssh -i "$KEY" "$HOST" "sudo SITE=$SITE GATEWAY_NETWORK=$GATEWAY_NETWORK bash -c '
set -euo pipefail
read -r TOKEN
F=/opt/zhiyin/secrets/zhiyin.env
umask 077
{ grep -v \"^ZHIYIN_WORKER_TOKEN=\" \$F 2>/dev/null || true; echo \"ZHIYIN_WORKER_TOKEN=\$TOKEN\"; } > \$F.new
chmod 600 \$F.new && mv \$F.new \$F
cd /opt/zhiyin && env ZHIYIN_PUBLIC_URL=\$SITE GATEWAY_NETWORK=\$GATEWAY_NETWORK docker compose up -d --force-recreate 2>&1 | tail -1
'"
mkdir -p data
umask 077
printf '{"url": "%s", "token": "%s"}\n' "$SITE" "$TOKEN" > data/worker.json
unset TOKEN
uv run zhiyin service install --worker
