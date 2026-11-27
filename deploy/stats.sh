#!/usr/bin/env bash
# Site stats from your machine: bash deploy/stats.sh
# SSHes to the server and runs `maf stats` there, so the numbers come from the live database.
# Uses the same SSH settings as release.sh (MAF_SERVER, MAF_SSH_KEY override them).
set -uo pipefail

SERVER="${MAF_SERVER:-ubuntu@3.233.18.162}"
SSH_KEY="${MAF_SSH_KEY:-$HOME/.ssh/maf.pem}"

if ! output=$(ssh -i "$SSH_KEY" -o ConnectTimeout=10 "$SERVER" 'sudo maf stats' 2>&1); then
  if grep -q "invalid choice: 'stats'" <<< "$output"; then
    echo "The server's maf has no stats command yet: it arrives with the next release." >&2
    exit 1
  fi
  printf '%s\n' "$output" >&2
  echo "If SSH timed out, your IP may have changed: the server only allows SSH from one address." >&2
  exit 1
fi
printf '%s\n' "$output"
