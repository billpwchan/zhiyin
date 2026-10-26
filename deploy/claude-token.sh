#!/usr/bin/env bash
# Give the server a Claude of its own. Run it in your own terminal; whatever you paste is never echoed and goes
# straight into the server's secrets/zhiyin.env.
#
#   deploy/claude-token.sh            your Claude subscription, for your own listening only. `claude setup-token`
#                                     signs you in in the browser and prints a long-lived token to paste.
#   deploy/claude-token.sh --api-key  an Anthropic API key (platform.claude.com), billed per use. Needed before
#                                     you invite anyone: a subscription is for its owner's own use.
#   deploy/claude-token.sh --remove-api-key
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f deploy/local.conf ] && . deploy/local.conf
: "${KEY:?set KEY}" "${HOST:?set HOST}" "${SITE:?set SITE}"
GATEWAY_NETWORK=${GATEWAY_NETWORK:-proxy}

case "${1:-}" in
  "")                VAR=CLAUDE_CODE_OAUTH_TOKEN; CHECK="env -u ANTHROPIC_API_KEY claude"
                     claude setup-token
                     printf '\nPaste the token it printed (hidden): ' ;;
  --api-key)         VAR=ANTHROPIC_API_KEY; CHECK="zhiyin check-key"   # the Messages API, as the server uses it
                     printf 'Paste the API key (hidden): ' ;;
  --remove-api-key)  VAR=ANTHROPIC_API_KEY; CHECK="" ;;
  *)                 echo "usage: $0 [--api-key | --remove-api-key]"; exit 2 ;;
esac
VALUE=""
if [ -n "$CHECK" ]; then
  read -rs VALUE
  echo
  [ -n "$VALUE" ] || { echo "nothing pasted, nothing changed"; exit 1; }
fi

printf '%s\n' "$VALUE" | ssh -i "$KEY" "$HOST" "sudo SITE=$SITE GATEWAY_NETWORK=$GATEWAY_NETWORK VAR=$VAR CHECK='$CHECK' bash -c '
set -euo pipefail
read -r VALUE || true
F=/opt/zhiyin/secrets/zhiyin.env
umask 077
{ grep -v \"^\$VAR=\" \$F 2>/dev/null || true; if [ -n \"\$VALUE\" ]; then echo \"\$VAR=\$VALUE\"; fi; } > \$F.new
chmod 600 \$F.new && mv \$F.new \$F
cd /opt/zhiyin && docker compose up -d --force-recreate 2>&1 | tail -1   # settings from .env, written by deploy.sh
for i in \$(seq 1 40); do docker exec zhiyin curl -fsS http://127.0.0.1:8817/healthz >/dev/null 2>&1 && break; sleep 1; done
if [ -z \"\$CHECK\" ]; then echo \"\$VAR is no longer set\"; exit 0; fi
printf \"Claude on the server: \"
if [ \"\$VAR\" = ANTHROPIC_API_KEY ]; then docker exec zhiyin \$CHECK; else docker exec zhiyin \$CHECK -p \"Reply with the single word: ready\" --model sonnet; fi ||
  echo \"no answer: check what you pasted and run this again, or take it out with --remove-api-key\"
'"
unset VALUE
