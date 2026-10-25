#!/usr/bin/env bash
# Usage: scripts/make_manifest.sh <dir>   writes <dir>/manifest.sha256
set -euo pipefail
dir="${1:?usage: make_manifest.sh <dir>}"
cd "$dir"
find . -type f ! -name manifest.sha256 ! -path './.git/*' ! -path '*/__pycache__/*' -print0 | sort -z | xargs -0 sha256sum > manifest.sha256
echo "wrote $dir/manifest.sha256 ($(wc -l < manifest.sha256) files)"
