#!/usr/bin/env bash
# Release MAF from your machine: bash deploy/release.sh
# Checks main is clean and tested, tags the next version (v1.0.0, v1.0.1, …), pushes it,
# runs update.sh on the server and checks the site answers. Browsers fetch changed CSS/JS
# on their own: every static URL carries a hash of the file's contents.
set -euo pipefail

SERVER="${MAF_SERVER:-ubuntu@3.233.18.162}"
SSH_KEY="${MAF_SSH_KEY:-$HOME/.ssh/maf.pem}"
SITE="${MAF_SITE:-https://maforum.net}"
FIRST_VERSION=v1.0.0

cd "$(git rev-parse --show-toplevel)"

if [ "$(git branch --show-current)" != main ]; then
  echo "Switch to main first." >&2
  exit 1
fi
if [ -n "$(git status --porcelain)" ]; then
  echo "Commit or stash your changes first." >&2
  exit 1
fi

uv run pytest -q

latest=$(git tag --list 'v*.*.*' --sort=-v:refname | head -1)
if [ -z "$latest" ]; then
  version=$FIRST_VERSION
else
  IFS=. read -r major minor patch <<< "${latest#v}"
  version="v$major.$minor.$((patch + 1))"
fi

git push origin main
git tag -a "$version" -m "Release $version"
git push origin "$version"
echo "Tagged $version"

if ! ssh -i "$SSH_KEY" -o ConnectTimeout=10 "$SERVER" 'sudo bash /opt/maf/deploy/update.sh'; then
  echo "Deploy failed. If SSH timed out, your IP may have changed: the server only allows SSH from one address." >&2
  exit 1
fi

for _ in $(seq 1 15); do
  if curl -fsS -o /dev/null "$SITE/sign-in"; then
    echo "$version is live at $SITE"
    exit 0
  fi
  sleep 1
done
echo "$SITE didn't answer after the restart. Check: sudo journalctl -u maf -n 50" >&2
exit 1
