#!/usr/bin/env bash
# Deploy a new version of MAF. Run as root on the server: sudo bash /opt/maf/deploy/update.sh
# Pulls the latest code, syncs dependencies, refreshes the systemd unit and Caddyfile if they
# changed, restarts the app and prints its status. The database and secrets are never touched.
set -euo pipefail

APP_DIR=/opt/maf
UNIT_SRC="$APP_DIR/deploy/maf.service"
UNIT_DST=/etc/systemd/system/maf.service
CADDY_SRC="$APP_DIR/deploy/Caddyfile"
CADDY_DST=/etc/caddy/Caddyfile

export UV_PYTHON_PREFERENCE=only-system UV_PYTHON_DOWNLOADS=never UV_COMPILE_BYTECODE=1

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi

git -C "$APP_DIR" pull --ff-only
(cd "$APP_DIR" && uv sync --frozen --no-dev)

if ! cmp -s "$UNIT_SRC" "$UNIT_DST"; then
  install -m 644 "$UNIT_SRC" "$UNIT_DST"
  systemctl daemon-reload
  echo "Updated $UNIT_DST"
fi

if ! cmp -s "$CADDY_SRC" "$CADDY_DST"; then
  caddy validate --config "$CADDY_SRC" --adapter caddyfile
  install -m 644 "$CADDY_SRC" "$CADDY_DST"
  systemctl reload caddy
  echo "Updated $CADDY_DST"
fi

systemctl restart maf.service
systemctl status maf.service --no-pager || true
