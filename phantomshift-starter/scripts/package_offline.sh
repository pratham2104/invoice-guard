#!/usr/bin/env bash
# Build/verify the offline kit manifest. Runs at lowest priority (sha256 of ~35 GB takes a while).
#   scripts/package_offline.sh build    -> repo tarball + offline-stage/manifest.sha256
#   scripts/package_offline.sh verify   -> sha256sum -c
# The tarball is made from a tree staged with the SAME rules as sync_to_gb10.sh (scripts/ship.include), so the
# two shipping paths cannot diverge: no .env*, *.pem, *.key, tokens, event DB, discord-preflight.json, verify.json.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"; stage="$(cd "$root/.." && pwd)/offline-stage"
cmd="${1:-build}"
case "$cmd" in
  build)
    command -v rsync >/dev/null || { echo "rsync is required to apply scripts/ship.include" >&2; exit 1; }
    mkdir -p "$stage"
    tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
    name="$(basename "$root")"
    rsync -a --exclude-from="$root/scripts/ship.include" -- "$root/" "$tmp/$name/"
    tar -C "$tmp" -czf "$stage/phantomshift-starter.tar.gz" "$name"
    cd "$stage"
    find . -type f ! -name manifest.sha256 ! -name '*.log' -print0 | sort -z | nice -n 19 ionice -c3 xargs -0 sha256sum > manifest.sha256
    echo "manifest: $(wc -l < manifest.sha256) files"; du -sh "$stage" ;;
  verify) cd "$stage"; nice -n 19 ionice -c3 sha256sum -c manifest.sha256 --quiet && echo VERIFY_OK ;;
  *) echo "usage: $0 build|verify" >&2; exit 2 ;;
esac
