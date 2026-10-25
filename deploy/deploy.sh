#!/usr/bin/env bash
# Ship the current tree to the server: a new timestamped release, `current` repointed, the image rebuilt there and
# the container recreated. Earlier releases stay in $R/releases for rollback (repoint `current`, run compose up).
# Listener data lives in $R/data and is never touched by a release. On the first run this creates
# $R/secrets/zhiyin.env with a fresh worker token; Claude goes in with deploy/claude-token.sh (docs/self-hosting.md).
# Settings come from the environment or deploy/local.conf (not tracked):
#   KEY=<ssh key file>  HOST=user@host  SITE=https://zhiyin.example.com  GATEWAY_NETWORK=proxy
#   YT_LANGUAGE=en (the YouTube Music interface language song titles are read in, e.g. zh_TW)
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f deploy/local.conf ] && . deploy/local.conf
: "${KEY:?set KEY (ssh key) in the environment or deploy/local.conf}"
: "${HOST:?set HOST (user@host)}"
: "${SITE:?set SITE (the public https URL)}"
GATEWAY_NETWORK=${GATEWAY_NETWORK:-proxy}
STAMP=$(date +%Y%m%d-%H%M%S)

ssh -i "$KEY" "$HOST" 'mkdir -p ~/zhiyin-upload/src'
rsync -az --delete --exclude __pycache__ -e "ssh -i $KEY" \
  zhiyin web demo pyproject.toml uv.lock README.md LICENSE Dockerfile .dockerignore "$HOST:zhiyin-upload/src/"
rsync -az -e "ssh -i $KEY" deploy/compose.yaml "$HOST:zhiyin-upload/"
ssh -i "$KEY" "$HOST" "STAMP=$STAMP SITE=$SITE GATEWAY_NETWORK=$GATEWAY_NETWORK YT_LANGUAGE=${YT_LANGUAGE:-en} bash -s" <<'REMOTE'
set -euo pipefail
R=/opt/zhiyin
sudo mkdir -p $R/releases $R/data $R/secrets
sudo rsync -a --delete ~/zhiyin-upload/src/ $R/releases/$STAMP/
sudo cp ~/zhiyin-upload/compose.yaml $R/compose.yaml
sudo ln -sfn releases/$STAMP $R/current
sudo chown -R 1000:1000 $R/data
if [ ! -f $R/secrets/zhiyin.env ]; then
  umask 077
  echo "ZHIYIN_WORKER_TOKEN=$(openssl rand -hex 24)" | sudo tee $R/secrets/zhiyin.env >/dev/null
fi
sudo chmod 600 $R/secrets/zhiyin.env
cd $R
sudo env ZHIYIN_PUBLIC_URL=$SITE ZHIYIN_YT_LANGUAGE=$YT_LANGUAGE GATEWAY_NETWORK=$GATEWAY_NETWORK docker compose build --pull -q
sudo env ZHIYIN_PUBLIC_URL=$SITE ZHIYIN_YT_LANGUAGE=$YT_LANGUAGE GATEWAY_NETWORK=$GATEWAY_NETWORK docker compose up -d --force-recreate
for i in $(seq 1 60); do sudo docker exec zhiyin curl -fsS http://127.0.0.1:8817/healthz 2>/dev/null && break; sleep 1; done
echo
echo "released $STAMP"
# keep the five newest releases
ls -1d $R/releases/* | sort | head -n -5 | xargs -r sudo rm -rf
REMOTE
curl -fsS -o /dev/null -w "live %{http_code}\n" "$SITE/healthz"
