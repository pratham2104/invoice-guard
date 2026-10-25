#!/usr/bin/env bash
# One-time: create a dedicated SSH key for the GB10 and print what to do. Edits nothing existing.
set -euo pipefail
key="$HOME/.ssh/id_ed25519_gb10"
mkdir -p "$HOME/.ssh"; chmod 700 "$HOME/.ssh"
[ -f "$key" ] || ssh-keygen -t ed25519 -N "" -C "phantomshift-gb10-$(date +%F)" -f "$key" >/dev/null
echo "Public key (add to ~/.ssh/authorized_keys on the GB10, or run: ssh-copy-id -i $key.pub user@gb10-ip):"
cat "$key.pub"
cat <<TXT

Suggested ~/.ssh/config block (not written for you):
Host gb10
  HostName <GB10_IP>
  User <GB10_USER>
  IdentityFile $key
  IdentitiesOnly yes
  # ProxyJump <you@laptop>    # if this server cannot reach the venue network directly

Then:  GB10_HOST=gb10 scripts/sync_to_gb10.sh --dry-run
The private key never leaves this machine. The GB10 must NOT call back into this server for inference.
TXT
