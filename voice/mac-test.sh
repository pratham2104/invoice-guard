#!/usr/bin/env bash
# Try the voice callback on a Mac, with Asterisk in Docker (no install on the Mac itself).
#   voice/mac-test.sh          → start Asterisk, print the Linphone login and the call command
#   voice/mac-test.sh stop     → remove the container
# Same config as the GB10 (voice/asterisk/*.conf), plus two Docker-on-Mac adjustments:
#   - Asterisk is told the Mac's Wi-Fi IP, so the phone's audio reaches it through Docker's NAT
#   - audio ports narrowed to 10000-10050 (publishing 10,000 UDP ports to Docker is very slow)
# Also adds a test-only "fake phone" (Local/answer@test) that answers and talks, for a no-phone test.
set -euo pipefail
NAME=ig-asterisk-mac
[ "${1:-}" = stop ] && { docker rm -f "$NAME" >/dev/null && echo "stopped"; exit 0; }

HERE="$(cd "$(dirname "$0")" && pwd)"
IP="$(ipconfig getifaddr en0 || ipconfig getifaddr en1)"
CFG="$(mktemp -d)"; mkdir -p "$CFG/rec"
SIP_PASSWORD=mac-test-sip; ARI_PASSWORD=mac-test-ari   # local test only; the GB10 generates random ones

for f in pjsip extensions http ari; do
  sed -e "s/__SIP_PASSWORD__/$SIP_PASSWORD/" -e "s/__ARI_PASSWORD__/$ARI_PASSWORD/" "$HERE/asterisk/$f.conf" > "$CFG/$f.conf"
done
sed -i '' 's/bindaddr=127.0.0.1/bindaddr=0.0.0.0/' "$CFG/http.conf"   # inside the container; published to 127.0.0.1 only
sed -i '' "s/^bind=0.0.0.0:5060$/bind=0.0.0.0:5060\nexternal_media_address=$IP\nexternal_signaling_address=$IP\nlocal_net=172.16.0.0\/12/" "$CFG/pjsip.conf"
printf '[general]\nrtpstart=10000\nrtpend=10050\n' > "$CFG/rtp.conf"
cat >> "$CFG/extensions.conf" <<'EOF'

; TEST ONLY: a fake phone that answers and keeps talking (no real phone needed).
[test]
exten => answer,1,Answer()
 same => n(loop),Playback(invoice-guard/q2)
 same => n,Goto(loop)
EOF

docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" \
  -p 5060:5060/udp -p 10000-10050:10000-10050/udp -p 127.0.0.1:8088:8088 \
  -v "$CFG/pjsip.conf:/etc/asterisk/pjsip.conf" -v "$CFG/extensions.conf:/etc/asterisk/extensions.conf" \
  -v "$CFG/http.conf:/etc/asterisk/http.conf" -v "$CFG/ari.conf:/etc/asterisk/ari.conf" -v "$CFG/rtp.conf:/etc/asterisk/rtp.conf" \
  -v "$HERE/prompts:/var/lib/asterisk/sounds/invoice-guard" -v "$CFG/rec:/var/spool/asterisk/recording" \
  andrius/asterisk:latest >/dev/null
for _ in $(seq 1 30); do curl -sf -u "invoice-guard:$ARI_PASSWORD" http://127.0.0.1:8088/ari/asterisk/info >/dev/null && break; sleep 2; done

cat <<EOF
Asterisk is running in Docker (container $NAME). Recordings land in: $CFG/rec

Linphone login (phone on the SAME Wi-Fi as this Mac, or Linphone desktop on this Mac):
  username: vendor-demo    password: $SIP_PASSWORD    domain: $IP    transport: UDP
  (Linphone desktop on this Mac: domain 127.0.0.1 also works)
Registered?   docker exec $NAME asterisk -rx "pjsip show contacts"

Call it (from the repo root):
  export ARI_PASSWORD=$ARI_PASSWORD
  npx -y node@22 --import tsx voice/call.ts --case TEST                                 # rings Linphone
  VOICE_ENDPOINT=Local/answer@test npx -y node@22 --import tsx voice/call.ts --case TEST # fake phone, no Linphone
Stop:  voice/mac-test.sh stop
EOF
