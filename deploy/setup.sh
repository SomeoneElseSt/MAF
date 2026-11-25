#!/usr/bin/env bash
# One-time server setup for MAF on a fresh Ubuntu 24.04 machine. Run as root:
#   sudo bash setup.sh
# Safe to run again: it never overwrites /etc/maf/env (the secrets), the signing key or the database.
set -euo pipefail

REPO_URL=https://github.com/SomeoneElseSt/MAF.git
APP_DIR=/opt/maf
DATA_DIR=/var/lib/maf
ENV_DIR=/etc/maf
ENV_FILE=$ENV_DIR/env
KEY_FILE=$DATA_DIR/signing.key
SERVICE_USER=maf
PLACEHOLDER=CHANGE_ME_TO_THE_MAINTAINER_EMAIL

export DEBIAN_FRONTEND=noninteractive
# Use Ubuntu's own Python 3.12; never download an interpreter into a home directory.
export UV_PYTHON_PREFERENCE=only-system UV_PYTHON_DOWNLOADS=never UV_COMPILE_BYTECODE=1

log() { printf '\n==> %s\n' "$*"; }

install_packages() {
  log "Installing packages"
  apt-get update
  apt-get install -y ca-certificates curl gpg git openssl python3 \
    debian-keyring debian-archive-keyring apt-transport-https
}

# The name check's language model needs ~1 GB of the server's 2 GB; swap keeps a busy moment from
# running out of memory.
add_swap() {
  if swapon --show | grep -q /swapfile; then
    log "Swap already on"
    return
  fi
  log "Adding 1 GB of swap"
  fallocate -l 1G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
}

install_caddy() {
  if command -v caddy >/dev/null 2>&1; then
    log "Caddy already installed"
    return
  fi
  log "Installing Caddy from the official apt repository"
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update
  apt-get install -y caddy
}

install_uv() {
  if command -v uv >/dev/null 2>&1; then
    log "uv already installed"
    return
  fi
  log "Installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh
}

create_service_user() {
  if id "$SERVICE_USER" >/dev/null 2>&1; then
    return
  fi
  log "Creating system user $SERVICE_USER"
  useradd --system --home-dir "$DATA_DIR" --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
}

fetch_code() {
  if [ -d "$APP_DIR/.git" ]; then
    log "Updating $APP_DIR"
    git -C "$APP_DIR" pull --ff-only
    return
  fi
  log "Cloning $REPO_URL to $APP_DIR"
  git clone --branch main "$REPO_URL" "$APP_DIR"
}

sync_dependencies() {
  log "Installing Python dependencies (includes the spaCy model; takes a few minutes)"
  (cd "$APP_DIR" && uv sync --frozen --no-dev)
}

create_data_dir() {
  install -d -m 700 -o "$SERVICE_USER" -g "$SERVICE_USER" "$DATA_DIR"
}

random_secret() {
  openssl rand -hex 48
}

generate_signing_key() {
  if [ -e "$KEY_FILE" ]; then
    log "Signing key already exists, keeping it"
    return
  fi
  log "Generating the RSA signing key"
  (cd "$DATA_DIR" && runuser -u "$SERVICE_USER" -- "$APP_DIR/.venv/bin/python" -c \
    "from pathlib import Path; from maf.blind import generate_key; generate_key(Path('$KEY_FILE'))")
  chmod 600 "$KEY_FILE"
}

write_env_file() {
  if [ -e "$ENV_FILE" ]; then
    log "$ENV_FILE exists, leaving every secret as it is"
    if [ ! -e "$KEY_FILE" ]; then
      echo "WARNING: $ENV_FILE exists but $KEY_FILE does not. The app will not start until the key is restored." >&2
    fi
    return
  fi
  log "Writing $ENV_FILE with new secrets"
  generate_signing_key
  install -d -m 750 -o root -g "$SERVICE_USER" "$ENV_DIR"
  local tmp
  tmp=$(mktemp "$ENV_DIR/env.XXXXXX")
  cat > "$tmp" <<ENV
MAF_ENV=production
MAF_DATABASE=$DATA_DIR/maf.db
MAF_SIGNING_KEY=$KEY_FILE
LABEL_SECRET=$(random_secret)
SESSION_SECRET=$(random_secret)
EMAIL_BACKEND=ses
MAF_EMAIL_FROM=code@maforum.net
# SES (email) is in us-west-2 (Oregon); the server itself runs in us-east-1.
AWS_REGION=us-west-2
MAF_BASE_URL=https://maforum.net
# Moderation requests are emailed here. The maintainer must replace this value.
MAINTAINER_EMAIL=hello@maforum.net
# Who the forum is for. Quote values with spaces.
MAF_EMAIL_DOMAIN=uni.minerva.edu
MAF_CONTACT_EMAIL=hello@maforum.net
MAF_COMMUNITY="Minerva University students"
MAF_FORUM_NAME="Minerva Anonymous Forum"
MAF_ORG_TAG=minerva
MAF_SITE_NAME=MAF
MAF_EMAIL_KIND=university
MAF_NAMING_RULE=true
MAF_SOURCE_URL=https://github.com/SomeoneElseSt/MAF
# Your own hashtags with templates: copy deploy/hashtags.example.json, edit it, and point to it here.
# MAF_HASHTAGS_FILE=/etc/maf/hashtags.json
ENV
  chown root:"$SERVICE_USER" "$tmp"
  chmod 640 "$tmp"
  mv "$tmp" "$ENV_FILE"
}

install_cli_wrapper() {
  # `sudo maf requests` runs the maintainer CLI as the service user with the service's environment.
  cat > /usr/local/bin/maf <<'WRAPPER'
#!/usr/bin/env bash
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then exec sudo "$0" "$@"; fi
set -a
. /etc/maf/env
set +a
exec runuser --preserve-environment -u maf -- /opt/maf/.venv/bin/maf "$@"
WRAPPER
  chmod 755 /usr/local/bin/maf
}

install_service_and_proxy() {
  log "Installing the systemd unit and Caddyfile"
  install -m 644 "$APP_DIR/deploy/maf.service" /etc/systemd/system/maf.service
  caddy validate --config "$APP_DIR/deploy/Caddyfile" --adapter caddyfile
  install -m 644 "$APP_DIR/deploy/maintenance.html" /etc/caddy/maintenance.html
  install -m 644 "$APP_DIR/deploy/Caddyfile" /etc/caddy/Caddyfile
  systemctl daemon-reload
  systemctl enable maf.service caddy.service
  systemctl restart maf.service
  systemctl enable --now caddy.service
  systemctl reload caddy.service
}

wait_for_app() {
  log "Waiting for the app to answer on 127.0.0.1:8000"
  for _ in $(seq 1 60); do
    if curl -fsS -o /dev/null http://127.0.0.1:8000/sign-in; then
      echo "The app is up."
      return
    fi
    sleep 2
  done
  echo "The app did not answer in 2 minutes. Check: journalctl -u maf -n 50" >&2
  exit 1
}

warn_about_placeholder() {
  if ! grep -q "^MAINTAINER_EMAIL=$PLACEHOLDER" "$ENV_FILE"; then
    return
  fi
  cat <<MSG

ACTION NEEDED: set the maintainer address that receives moderation requests.
  sudo nano $ENV_FILE        # replace $PLACEHOLDER
  sudo systemctl restart maf
MSG
}

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi

install_packages
add_swap
install_caddy
install_uv
create_service_user
fetch_code
sync_dependencies
create_data_dir
write_env_file
install_cli_wrapper
install_service_and_proxy
wait_for_app
warn_about_placeholder
log "Done. Check https://maforum.net once the DNS records point at this server."
