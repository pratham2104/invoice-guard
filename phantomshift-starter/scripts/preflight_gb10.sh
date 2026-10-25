#!/usr/bin/env bash
# Run ON the Dell GB10 (or any host to see what it would say). Read-only; no sudo, no installs.
# Writes artifacts/preflight/gb10.json next to the repo and prints a verdict.
set -u
here="$(cd "$(dirname "$0")/.." && pwd)"
out="$here/artifacts/preflight/gb10.json"
mkdir -p "$(dirname "$out")"
arch="$(uname -m)"
# GPU NAME only decides "looks like a GB10"; driver/memory/compute-cap fields must never match.
gpu_name="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)"
gpu="$(nvidia-smi --query-gpu=name,driver_version,memory.total,compute_cap --format=csv,noheader 2>/dev/null | head -1)"
mem_gib="$(awk '/MemTotal/{printf "%.0f",$2/1048576}' /proc/meminfo)"
free_gib="$(df -BG --output=avail "$here" | tail -1 | tr -dc 0-9)"
dver="$(docker --version 2>/dev/null || echo none)"
dok="no"; docker info >/dev/null 2>&1 && dok="yes"
nc="$(command -v nemoclaw >/dev/null && nemoclaw --version 2>&1 | grep -v -i experimental | grep -v trace-warn | head -1 || echo none)"
os="$(. /etc/os-release 2>/dev/null; echo "${PRETTY_NAME:-unknown}")"
is_gb10="no"
case "$arch" in aarch64|arm64) case "$gpu_name" in *GB10*) is_gb10="likely";; esac;; esac
collected="$(date -u +%FT%TZ)"
mem_gib="${mem_gib:-0}"; free_gib="${free_gib:-0}"

# JSON must stay valid when a field contains quotes, backslashes or control characters.
# (PREFLIGHT_NO_PYTHON=1 forces the sed fallback; used by tests.)
if [ -z "${PREFLIGHT_NO_PYTHON:-}" ] && command -v python3 >/dev/null 2>&1; then
  COLLECTED="$collected" ARCH="$arch" OS="$os" GPU="$gpu" GPU_NAME="$gpu_name" MEM="$mem_gib" FREE="$free_gib" \
  DVER="$dver" DOK="$dok" NC="$nc" GB10="$is_gb10" python3 - > "$out" <<'PY'
import json, os
e = os.environ
def num(v):
    return int(v) if v.isdigit() else 0
print(json.dumps({"collected": e["COLLECTED"], "arch": e["ARCH"], "os": e["OS"], "gpu": e["GPU"],
                  "gpu_name": e["GPU_NAME"], "ram_gib": num(e["MEM"]), "disk_free_gib": num(e["FREE"]),
                  "docker": e["DVER"], "docker_daemon_reachable": e["DOK"], "nemoclaw": e["NC"],
                  "looks_like_gb10": e["GB10"]}, indent=2))
PY
else
  # No python3: escape \ " and strip control characters with sed/tr (single-line fields only).
  jesc() { printf '%s' "$1" | tr -d '\000-\010\013\014\016-\037' | tr '\t\r\n' '   ' | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'; }
  num() { case "$1" in ''|*[!0-9]*) echo 0;; *) echo "$1";; esac; }
  {
    printf '{\n  "collected": "%s",\n  "arch": "%s",\n  "os": "%s",\n  "gpu": "%s",\n  "gpu_name": "%s",\n  "ram_gib": %s,\n  "disk_free_gib": %s,\n' \
      "$(jesc "$collected")" "$(jesc "$arch")" "$(jesc "$os")" "$(jesc "$gpu")" "$(jesc "$gpu_name")" "$(num "$mem_gib")" "$(num "$free_gib")"
    printf '  "docker": "%s",\n  "docker_daemon_reachable": "%s",\n  "nemoclaw": "%s",\n  "looks_like_gb10": "%s"\n}\n' \
      "$(jesc "$dver")" "$(jesc "$dok")" "$(jesc "$nc")" "$(jesc "$is_gb10")"
  } > "$out"
fi
cat "$out"
echo
echo "---- verdict ----"
[ "$is_gb10" = "likely" ] && echo "GB10: likely (arm64 + GPU name contains GB10). Confirm by eye." || echo "GB10: NO. This is not the competition host (arch=$arch, gpu name='${gpu_name:-none}')."
[ "$dok" = "yes" ] || echo "Docker daemon not reachable: fix before NemoClaw onboarding."
[ "$free_gib" -ge 100 ] || echo "Less than 100 GiB free: model + image + cache may not fit."
if command -v nemoclaw >/dev/null 2>&1; then
  echo "---- nemoclaw profiles (Lightning / Nano 4B lines) ----"
  nemoclaw profiles list 2>/dev/null | grep -E '^(vllm|llama)' | grep -E 'lightning|nano-4b|nano-30b' | cut -c1-140
  echo "Do not bypass a host-validation rejection; pick a supported profile instead."
else
  echo "nemoclaw not installed: official installer is in offline-stage/nemoclaw-bootstrap.sh (read it first)."
fi
