#!/usr/bin/env bash
# One-time Asterisk setup on the GB10 (Ubuntu 24.04, arm64). Run from the repo root:  sudo voice/setup.sh
# Installs Asterisk, writes our 4 config files (originals backed up), opens the SIP/RTP ports,
# copies the call prompts, and prints the Linphone login for the "vendor's phone".
# Secrets go to ~/.invoice-guard-voice.env (mode 600), never into the repo.
set -euo pipefail

[ "$(id -u)" = 0 ] || { echo "run with sudo: sudo voice/setup.sh"; exit 1; }
HERE="$(cd "$(dirname "$0")" && pwd)"
USER_HOME="$(getent passwd "${SUDO_USER:-root}" | cut -d: -f6)"
ENV_FILE="$USER_HOME/.invoice-guard-voice.env"

echo "== 1/5 install asterisk + sox"
command -v asterisk >/dev/null || { apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq asterisk sox; }
asterisk -V

echo "== 2/5 secrets ($ENV_FILE)"
if [ ! -f "$ENV_FILE" ]; then
  cat > "$ENV_FILE" <<EOF
SIP_PASSWORD=$(openssl rand -hex 8)
ARI_USER=invoice-guard
ARI_PASSWORD=$(openssl rand -hex 16)
ARI_URL=http://127.0.0.1:8088
VOICE_ENDPOINT=PJSIP/vendor-demo
EOF
  chown "${SUDO_USER:-root}" "$ENV_FILE"; chmod 600 "$ENV_FILE"
fi
# shellcheck disable=SC1090
. "$ENV_FILE"

echo "== 3/5 asterisk config (backup in /etc/asterisk/backup-invoice-guard)"
mkdir -p /etc/asterisk/backup-invoice-guard
for f in pjsip.conf extensions.conf http.conf ari.conf; do
  [ -f "/etc/asterisk/$f" ] && [ ! -f "/etc/asterisk/backup-invoice-guard/$f" ] && cp "/etc/asterisk/$f" /etc/asterisk/backup-invoice-guard/
  sed -e "s/__SIP_PASSWORD__/$SIP_PASSWORD/" -e "s/__ARI_PASSWORD__/$ARI_PASSWORD/" "$HERE/asterisk/$f" > "/etc/asterisk/$f"
  chown asterisk:asterisk "/etc/asterisk/$f" 2>/dev/null || true
  chmod 640 "/etc/asterisk/$f"
done
mkdir -p /var/lib/asterisk/sounds/invoice-guard
cp "$HERE"/prompts/*.wav /var/lib/asterisk/sounds/invoice-guard/
chown -R asterisk:asterisk /var/lib/asterisk/sounds/invoice-guard 2>/dev/null || true

echo "== 4/5 firewall"
if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
  ufw allow 5060/udp >/dev/null; ufw allow 10000:20000/udp >/dev/null; echo "ufw: opened 5060/udp and 10000-20000/udp"
else
  echo "ufw not active: nothing to open"
fi

echo "== 5/5 restart"
systemctl enable --now asterisk >/dev/null 2>&1 || true
systemctl restart asterisk
sleep 3
asterisk -rx "pjsip show endpoint vendor-demo" | head -5 || true
curl -s -u "$ARI_USER:$ARI_PASSWORD" "$ARI_URL/ari/asterisk/info" >/dev/null && echo "ARI: OK on $ARI_URL (loopback only)" || echo "ARI: NOT reachable"

IP="$(hostname -I | awk '{print $1}')"
cat <<EOF

Done. On the teammate's phone (same hotspot), in Linphone:
  "Use a SIP account"  →  username: vendor-demo   password: $SIP_PASSWORD
                          domain:   $IP           transport: UDP
Then check it registered:   sudo asterisk -rx "pjsip show contacts"
Place the test call:        npx tsx voice/call.ts
EOF
