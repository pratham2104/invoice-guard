#!/usr/bin/env bash
# GB10 day-of preflight: a thin superset of scripts/preflight_gb10.sh (which it CALLS, not copies).
# Read-only: no sudo, no installs, no docker mutation, no model run, no network, no hashing unless --verify-hashes.
#
#   scripts/gb10_preflight.sh [--manifest PATH] [--sizes PATH] [--verify-hashes] [--require-gb10] [--no-base] [--emit-sizes]
#
# Adds to the base script:
#   * ROOTLESS Docker + host-visible docker bridge (172.16-31.x on docker0/br-*) detection, with a loud WARNING:
#     NemoClaw onboarding FAILED on this class of host (docs/GB10_RUNBOOK.md, "Rehearsal result on the dev host").
#   * staged files named in a manifest (default ../offline-stage/manifest.sha256, else ~/gb10-kit/manifest.sha256):
#     existence + SIZE only. sha256 manifests carry no sizes, so expected sizes come from a sibling manifest.sizes
#     ("<bytes>  <path>", same paths); create it where the files are known-good with `--emit-sizes > manifest.sizes`.
#     --verify-hashes runs sha256sum -c at lowest priority (nice 19, ionice idle); never done by default.
#   * free VRAM / RAM, ports 8000 8080 7890 18789 free, DISCORD_* env set/unset (values are never printed).
# Output: PASS/WARN/FAIL table. Exit 1 only if there is at least one FAIL (hard blocker), else 0.
# Thresholds below marked "heuristic" are ours, not NVIDIA's.
set -u
here="$(cd "$(dirname "$0")/.." && pwd)"
manifest="" ; sizes="" ; verify=0 ; require_gb10=0 ; run_base=1 ; emit=0
while [ $# -gt 0 ]; do
  case "$1" in
    --manifest) manifest="${2:-}"; shift 2 ;;
    --sizes) sizes="${2:-}"; shift 2 ;;
    --verify-hashes) verify=1; shift ;;
    --require-gb10) require_gb10=1; shift ;;
    --no-base) run_base=0; shift ;;
    --emit-sizes) emit=1; shift ;;
    -h|--help) sed -n 2,17p "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
done

if [ -z "$manifest" ]; then
  for c in "$here/../offline-stage/manifest.sha256" "$HOME/gb10-kit/manifest.sha256"; do
    [ -f "$c" ] && { manifest="$c"; break; }
  done
fi

# manifest line: "<64 hex>  <path>" (sha256sum text mode; "<hash> *<path>" is also accepted)
manifest_path() { local l="$1"; l="${l:64}"; l="${l# }"; l="${l#\*}"; l="${l# }"; printf '%s' "${l#./}"; }

if [ "$emit" = 1 ]; then
  [ -n "$manifest" ] && [ -f "$manifest" ] || { echo "no manifest found (use --manifest PATH)" >&2; exit 2; }
  mdir="$(cd "$(dirname "$manifest")" && pwd)"
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    p="$(manifest_path "$line")"
    [ -f "$mdir/$p" ] && printf '%s  ./%s\n' "$(stat -c %s "$mdir/$p")" "$p"
  done < "$manifest"
  exit 0
fi

ROWS=()
add() { ROWS+=("$1|$2|$(printf '%s' "$3" | tr '\n\t' '  ' | cut -c1-320)"); }

# ---------------------------------------------------------------- base preflight (called, not duplicated)
base_out=""
if [ "$run_base" = 1 ]; then
  base_out="$("$here/scripts/preflight_gb10.sh" 2>&1)"; base_rc=$?
  echo "================ base preflight (scripts/preflight_gb10.sh, rc=$base_rc) ================"
  printf '%s\n' "$base_out"
  echo "================ end base preflight ================"
else
  echo "(--no-base: scripts/preflight_gb10.sh skipped; host class and docker reachability fall back to local probes)"
fi
bjson() { printf '%s\n' "$base_out" | sed -n "s/^ *\"$1\": *\"\{0,1\}\([^\",]*\).*/\1/p" | head -1; }

arch="$(bjson arch)"; [ -n "$arch" ] || arch="$(uname -m)"
docker_ok="$(bjson docker_daemon_reachable)"
if [ -z "$docker_ok" ]; then docker info >/dev/null 2>&1 && docker_ok=yes || docker_ok=no; fi
disk_free="$(bjson disk_free_gib)"
if printf '%s\n' "$base_out" | grep -q '^GB10: likely'; then is_gb10=1
elif [ -z "$base_out" ]; then
  gname="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)"
  case "$arch:$gname" in aarch64:*GB10*|arm64:*GB10*) is_gb10=1 ;; *) is_gb10=0 ;; esac
else is_gb10=0; fi

# ---------------------------------------------------------------- host class
if [ "$is_gb10" = 1 ]; then add PASS "host class" "arm64 + GPU name contains GB10 (likely GB10; confirm by eye)"
elif [ "$require_gb10" = 1 ]; then add FAIL "host class" "NOT a GB10 (arch=$arch) and --require-gb10 was given"
else add WARN "host class" "NOT a GB10 (arch=$arch, GPU name has no GB10). Not the competition host; --require-gb10 makes this a FAIL"; fi
[ "$arch" = aarch64 ] || [ "$arch" = arm64 ] || add WARN "cpu architecture" "$arch: staged images in offline-stage are arm64 and will not run here"

# ---------------------------------------------------------------- docker: reachability, rootless, bridge
have_docker=0; command -v docker >/dev/null 2>&1 && have_docker=1
ctx_host=""; secopts=""
if [ "$have_docker" = 1 ]; then
  ctx_host="${DOCKER_HOST:-$(docker context inspect --format '{{.Endpoints.docker.Host}}' 2>/dev/null)}"  # client-side only
  [ "$docker_ok" = yes ] && secopts="$(docker info --format '{{.SecurityOptions}}' 2>/dev/null)"
fi
sock_path="${ctx_host#unix://}"; [ "$sock_path" = "$ctx_host" ] && sock_path=""
uid="$(id -u)"
user_sock=""
for s in "${XDG_RUNTIME_DIR:-/nonexistent}/docker.sock" "/run/user/$uid/docker.sock" "$HOME/.docker/run/docker.sock" "$HOME/.docker/xdg/docker.sock"; do
  [ -S "$s" ] && [ -O "$s" ] && { user_sock="$s"; break; }
done
rootless=0; why=""
case "$secopts" in *rootless*) rootless=1; why="docker info SecurityOptions contains rootless" ;; esac
case "$sock_path" in "$HOME"/*|/run/user/*) rootless=1; why="${why:+$why; }docker endpoint socket is user-owned ($sock_path)" ;; esac
if [ "$rootless" = 0 ] && [ -n "$user_sock" ] && [ ! -S /var/run/docker.sock ]; then
  rootless=1; why="user-owned docker socket $user_sock exists and /var/run/docker.sock does not"
fi

if [ "$have_docker" = 0 ]; then add FAIL "docker" "docker CLI not found"
elif [ "$docker_ok" = yes ]; then add PASS "docker daemon" "reachable at ${ctx_host:-default endpoint}"
else add FAIL "docker daemon" "not reachable at ${ctx_host:-default endpoint}${user_sock:+; a user-owned socket exists at $user_sock (this script does not connect to it; set DOCKER_HOST yourself if intended)}"; fi

bridge="$(ip -4 -o addr 2>/dev/null | awk '$2 ~ /^(docker0|br-)/ && $4 ~ /^172\.(1[6-9]|2[0-9]|3[01])\./ {print $2"="$4}' | tr '\n' ' ')"
other172="$(ip -4 -o addr 2>/dev/null | awk '$2 !~ /^(docker0|br-|lo)/ && $4 ~ /^172\./ {print $2"="$4}' | tr '\n' ' ')"
if [ -n "$bridge" ]; then add PASS "docker bridge address" "host-visible bridge: $bridge"
else add WARN "docker bridge address" "no 172.16-31.x address on docker0/br-* in 'ip -4 addr'${other172:+ (172.x exists on a non-bridge interface: $other172)}"; fi

if [ "$rootless" = 1 ]; then
  cat <<EOF

##############################################################################
# WARNING: ROOTLESS DOCKER DETECTED ($why)
# NemoClaw onboarding FAILED on this class of host: the OpenShell gateway binds
# the Docker bridge address (172.18.0.1:8080), which does not exist on the host
# when Docker is rootless (bridge lives in a private network namespace):
#   "failed to bind to 172.18.0.1:8080: Cannot assign requested address"
# See docs/GB10_RUNBOOK.md, section "Rehearsal result on the dev host".
# On the GB10 verify rootful Docker and a host-visible 172.x bridge BEFORE onboarding.
# Do not work around it by weakening network isolation.
##############################################################################

EOF
  if [ -n "$bridge" ]; then add WARN "rootless docker" "$why. Bridge address is visible, so the known failure may not apply; still unverified"
  else add FAIL "rootless docker" "$why, and no host-visible docker bridge: this is the configuration where NemoClaw onboarding failed (GB10_RUNBOOK rehearsal section)"; fi
else
  add PASS "rootless docker" "not detected (docker info: ${secopts:-unavailable}; endpoint ${ctx_host:-default})"
fi

# ---------------------------------------------------------------- tools
if command -v nemoclaw >/dev/null 2>&1; then add PASS "nemoclaw" "installed ($(nemoclaw --version 2>&1 | grep -v -i -e experimental -e trace-warn | head -1))"
else add WARN "nemoclaw" "not installed (official installer: offline-stage/nemoclaw-bootstrap.sh, read it first; needs network)"; fi
command -v openshell >/dev/null 2>&1 && add PASS "openshell" "installed" || add WARN "openshell" "not installed (installed by the NemoClaw installer)"

# ---------------------------------------------------------------- staged files: existence + sizes only
if [ -z "$manifest" ] || [ ! -f "$manifest" ]; then
  add WARN "staged files" "no manifest found (../offline-stage/manifest.sha256, ~/gb10-kit/manifest.sha256, or --manifest PATH)"
else
  mdir="$(cd "$(dirname "$manifest")" && pwd)"
  [ -n "$sizes" ] || { [ -f "$mdir/manifest.sizes" ] && sizes="$mdir/manifest.sizes"; }
  declare -A want
  if [ -n "$sizes" ] && [ -f "$sizes" ]; then
    while IFS= read -r l; do
      [ -n "$l" ] || continue
      want["${l#*  ./}"]="${l%%  *}"
    done < "$sizes"
  fi
  total=0; missing=0; bad=0; checked=0; zero=0; first_missing=""; first_bad=""; first_zero=""
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    p="$(manifest_path "$line")"; total=$((total+1))
    if [ ! -f "$mdir/$p" ]; then missing=$((missing+1)); [ -n "$first_missing" ] || first_missing="$p"; continue; fi
    sz="$(stat -c %s "$mdir/$p")"
    [ "$sz" = 0 ] && { zero=$((zero+1)); [ -n "$first_zero" ] || first_zero="$p"; }
    if [ -n "${want[$p]:-}" ]; then
      checked=$((checked+1))
      [ "${want[$p]}" = "$sz" ] || { bad=$((bad+1)); [ -n "$first_bad" ] || first_bad="$p (have $sz, want ${want[$p]})"; }
    fi
  done < "$manifest"
  note="$total entries in $manifest"; [ "$zero" -gt 0 ] && note="$note; $zero zero-byte (first: $first_zero)"
  if [ "$missing" -gt 0 ]; then add FAIL "staged files" "$missing of $total missing (first: $first_missing)"
  elif [ "$bad" -gt 0 ]; then add FAIL "staged files" "$bad size mismatch (first: $first_bad); $note"
  elif [ "$checked" -gt 0 ] && [ "$checked" -eq "$total" ]; then add PASS "staged files" "all $total exist and sizes match $sizes"
  elif [ "$checked" -gt 0 ]; then add WARN "staged files" "all $total exist; sizes verified for only $checked (sizes file incomplete)"
  else add WARN "staged files" "all $total exist (existence only: no sizes file; create one with --emit-sizes > manifest.sizes on the known-good copy). $note"; fi
  if [ "$verify" = 1 ]; then
    if (cd "$mdir" && nice -n 19 ionice -c3 sha256sum -c "$(basename "$manifest")" --quiet >/dev/null 2>&1); then add PASS "staged hashes" "sha256sum -c OK (nice 19, ionice idle)"
    else add FAIL "staged hashes" "sha256sum -c reported failures in $mdir (run it by hand for the list)"; fi
  else add WARN "staged hashes" "not verified (pass --verify-hashes; hashes ~35 GB at lowest priority)"; fi
fi

# ---------------------------------------------------------------- VRAM / RAM / disk
LIGHT_MIN=21561882284; NANO_MIN=5280000000   # minimumGpuMemoryBytes in the NemoClaw Lightning / Nano-4B recipes
if command -v nvidia-smi >/dev/null 2>&1; then
  best=-1
  while IFS=, read -r f t; do
    f="$(printf '%s' "$f" | tr -dc 0-9)"; [ -n "$f" ] && [ "$f" -gt "$best" ] && best="$f"
  done < <(nvidia-smi --query-gpu=memory.free,memory.total --format=csv,noheader,nounits 2>/dev/null)
  if [ "$best" -lt 0 ]; then add WARN "free VRAM" "nvidia-smi reports no numeric free memory (unified memory on GB10 is expected to; see RAM row)"
  else
    bytes=$((best*1048576)); gb="$(awk -v b="$bytes" 'BEGIN{printf "%.1f GB", b/1e9}')"
    if [ "$bytes" -ge "$LIGHT_MIN" ]; then add PASS "free VRAM" "$gb free on the freest GPU (>= Lightning recipe minimum 21.56 GB)"
    elif [ "$bytes" -ge "$NANO_MIN" ]; then add WARN "free VRAM" "$gb free: enough for Nano-4B FP8 (5.28 GB), not for Lightning (21.56 GB)"
    else add FAIL "free VRAM" "$gb free: below the Nano-4B FP8 recipe minimum (5.28 GB)"; fi
  fi
else add FAIL "free VRAM" "nvidia-smi not found"; fi
mem_kb="$(awk '/MemAvailable/{print $2}' /proc/meminfo)"; mem_gib=$(( ${mem_kb:-0} / 1048576 ))
# heuristic: Lightning weights 21.6 GB + OS/containers headroom; unified memory on a GB10 is shared with the GPU
if [ "$mem_gib" -ge 48 ]; then add PASS "free RAM" "${mem_gib} GiB available (heuristic: >= 48 GiB)"
elif [ "$mem_gib" -ge 24 ]; then add WARN "free RAM" "${mem_gib} GiB available (heuristic: < 48 GiB; Spark hard-freezes under memory pressure, see NemoClaw troubleshooting)"
else add FAIL "free RAM" "${mem_gib} GiB available (heuristic: < 24 GiB, cannot hold Lightning weights plus headroom)"; fi
if [ -n "$disk_free" ] && [ "$disk_free" -lt 100 ] 2>/dev/null; then add WARN "free disk" "${disk_free} GiB free (< 100 GiB: model + image + cache may not fit)"
elif [ -n "$disk_free" ]; then add PASS "free disk" "${disk_free} GiB free"; fi

# ---------------------------------------------------------------- ports
listening="$(ss -ltnH 2>/dev/null | awk '{print $4}')"
port_busy() { printf '%s\n' "$listening" | grep -Eq "[:.]$1\$"; }
for spec in "8000:WARN:vLLM/llama.cpp model port (NemoClaw reuses a server it detects there, so confirm it is the intended one)" \
            "8080:FAIL:OpenShell gateway port" \
            "7890:WARN:PHANTOMSHIFT adapter default (change with --adapter-port)" \
            "18789:FAIL:OpenClaw gateway port"; do
  port="${spec%%:*}"; rest="${spec#*:}"; sev="${rest%%:*}"; what="${rest#*:}"
  if port_busy "$port"; then add "$sev" "port $port" "in use: $what"; else add PASS "port $port" "free"; fi
done

# ---------------------------------------------------------------- Discord env (values never printed)
for v in DISCORD_BOT_TOKEN DISCORD_SERVER_ID DISCORD_USER_ID; do
  if [ -n "${!v:-}" ]; then add PASS "env $v" "set"; else add WARN "env $v" "NOT set (enter it at the silent prompt on site; see ONSITE_CHECKLIST H05 step 1)"; fi
done

# ---------------------------------------------------------------- table + exit code
echo
printf '%-6s  %-24s  %s\n' STATUS CHECK DETAIL
printf '%-6s  %-24s  %s\n' ------ ------------------------ ------
np=0; nw=0; nf=0
for r in "${ROWS[@]}"; do
  st="${r%%|*}"; rest="${r#*|}"; ck="${rest%%|*}"; dt="${rest#*|}"
  printf '%-6s  %-24s  %s\n' "$st" "$ck" "$dt"
  case "$st" in PASS) np=$((np+1));; WARN) nw=$((nw+1));; FAIL) nf=$((nf+1));; esac
done
echo
echo "RESULT: $np PASS, $nw WARN, $nf FAIL"
if [ "$nf" -gt 0 ]; then echo "At least one hard blocker (FAIL). Exit 1."; exit 1; fi
echo "No hard blockers. WARN rows are unverified or non-fatal; read them. Exit 0."
exit 0
