#!/usr/bin/env bash
# Push PHANTOMSHIFT (and optionally the offline assets) to the GB10 over SSH. Never sends .env or tokens:
# what ships is an ALLOW-LIST (scripts/ship.include, shared with package_offline.sh); everything not listed stays.
#   GB10_HOST=user@ip scripts/sync_to_gb10.sh [--dry-run] [--assets]
# Via a laptop jump host:  GB10_JUMP=me@laptop GB10_HOST=user@gb10-ip scripts/sync_to_gb10.sh
# Without a network path, copy the same files to the external SSD instead (see offline-kit/GB10_CONNECT.md).
set -euo pipefail
: "${GB10_HOST:?set GB10_HOST=user@ip (from 'whoami' and 'hostname -I' on the GB10)}"

# Hostnames come from the environment: refuse anything ssh/rsync could read as an option or a shell word.
valid_target() { [[ "$2" =~ ^[A-Za-z0-9._@-]+$ && "$2" != -* && "$2" != *@-* ]] || { echo "invalid $1: '$2' (allowed: letters digits . _ @ -, not starting with -)" >&2; exit 2; }; }
valid_target GB10_HOST "$GB10_HOST"
[ -z "${GB10_JUMP:-}" ] || valid_target GB10_JUMP "$GB10_JUMP"

dry=(); drynote=""; assets=0
for a in "$@"; do case "$a" in --dry-run) dry=(--dry-run); drynote="(dry run)";; --assets) assets=1;; *) echo "unknown arg $a" >&2; exit 2;; esac; done
root="$(cd "$(dirname "$0")/.." && pwd)"
filter="$root/scripts/ship.include"
[ -f "$filter" ] || { echo "missing $filter" >&2; exit 1; }
stage="$(cd "$root/.." && pwd)/offline-stage"

ssh_opts=(-o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new)
[ -z "${GB10_JUMP:-}" ] || ssh_opts+=(-J "$GB10_JUMP")
key="${GB10_KEY:-$HOME/.ssh/id_ed25519_gb10}"
[ ! -f "$key" ] || ssh_opts+=(-i "$key")

# rsync -e takes ONE string: quote each element of the ssh_opts array that needs it (rsync honours '...').
rsh="ssh"
for o in "${ssh_opts[@]}"; do
  case "$o" in *"'"*) echo "refusing ssh option containing a quote: $o" >&2; exit 2;; esac
  case "$o" in *[[:space:]]*) rsh+=" '$o'";; *) rsh+=" $o";; esac
done

echo "NOTE: StrictHostKeyChecking=accept-new trusts the FIRST host key it sees (trust-on-first-use)." >&2
echo "      Verify it once: on the GB10 run  ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub  and compare with" >&2
echo "      ssh-keygen -F <host>  (or 'ssh-keygen -lf ~/.ssh/known_hosts') on this machine. A later mismatch aborts." >&2

echo "[1] ssh reachability + architecture"
arch="$(ssh "${ssh_opts[@]}" -- "$GB10_HOST" 'uname -m')" || { echo "ssh failed: check IP/user/key/venue network isolation" >&2; exit 1; }
echo "remote arch: $arch"
[ "$arch" = "aarch64" ] || echo "WARNING: remote is not aarch64; this may not be the GB10." >&2
echo "[2] code (allow-list scripts/ship.include; no .env, keys, tokens, event DB) $drynote"
rsync -avP ${dry[@]+"${dry[@]}"} -e "$rsh" --exclude-from="$filter" -- "$root/" "$GB10_HOST:~/PHANTOMSHIFT/"
if [ "$assets" = 1 ]; then
  echo "[3] offline assets from $stage $drynote"
  [ -d "$stage" ] || { echo "no $stage" >&2; exit 1; }
  rsync -avP ${dry[@]+"${dry[@]}"} --partial -e "$rsh" --exclude 'fetch.log' --exclude 'pull.log' -- "$stage/" "$GB10_HOST:~/gb10-kit/"
  if [ -z "$drynote" ]; then
    echo "[4] verify checksums on the GB10"
    ssh "${ssh_opts[@]}" -- "$GB10_HOST" 'cd ~/gb10-kit && test -f manifest.sha256 && sha256sum -c manifest.sha256 --quiet && echo CHECKSUMS_OK'
  fi
fi
echo "Next on the GB10: cd ~/PHANTOMSHIFT && scripts/preflight_gb10.sh"
