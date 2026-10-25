# Voice callback (T11): the box calls the vendor's phone, no cloud

Asterisk (open-source phone system) runs on the GB10. The "vendor's phone" is a teammate's phone running
**Linphone**, on the same hotspot. The call never leaves the local network: no Twilio, no phone carrier.
It doesn't dial phone numbers; it rings the Linphone app's SIP account.

The call **gathers evidence only** (recorded answers). A person still records "confirmed" or "denied" on
the case, and a manager approves. The greeting says the call is recorded (California needs everyone's consent).

## Steps on the GB10 (≈ 20–30 min)

```bash
cd ~/invoice-guard && git pull                 # this branch
sudo voice/setup.sh                            # installs Asterisk, writes config, prints the Linphone login
```
`setup.sh` backs up the original Asterisk config to `/etc/asterisk/backup-invoice-guard/`, opens
5060/udp + 10000–20000/udp if ufw is on, and keeps secrets in `~/.invoice-guard-voice.env` (never in git).

**On the teammate's phone** (same hotspot as the GB10):
1. Install **Linphone** → "Use a SIP account".
2. Username `vendor-demo`, password from `setup.sh`'s output, domain = the GB10's IP, transport **UDP**.
3. On the GB10, check it registered: `sudo asterisk -rx "pjsip show contacts"` → one `vendor-demo` contact, `Avail`.

**Call:**
```bash
npm run call -- --case HOLD-0003
```
The phone rings → greeting → question 1 → beep → answer → question 2 → beep → answer → goodbye.
Output lists the recordings: `/var/spool/asterisk/recording/HOLD-0003-q1.wav`, `-q2.wav`.
Listen: `sudo play /var/spool/asterisk/recording/HOLD-0003-q1.wav` (sox).

## If it doesn't work
| Symptom | Check |
|---|---|
| Linphone says "registration failed" / no contact | Same hotspot? Some hotspots block device-to-device traffic. Password/domain typo. `sudo asterisk -rvvv` shows the attempts |
| `status: no_answer` | The phone isn't registered (above), or nobody picked up within 30 s |
| Call connects, no audio | RTP ports 10000–20000/udp blocked; Linphone set to an encrypted media mode (set to "None") |
| `can't open ARI WebSocket` | Asterisk not running (`systemctl status asterisk`) or wrong `ARI_PASSWORD` in `~/.invoice-guard-voice.env` |
| No recording file for an answer | The answer was silent: Asterisk drops all-silent recordings |

## Files
| File | What |
|---|---|
| `setup.sh` | One-time install + config on the GB10 |
| `asterisk/*.conf` | `pjsip` (the phone account), `extensions` (the phone can't dial out), `http` + `ari` (call control, **127.0.0.1 only**) |
| `call.ts` | Places the call through ARI (Node 22 `fetch` + `WebSocket`, no extra packages); `verificationCall()` for the pipeline |
| `prompts/*.wav` | 8 kHz prompts. `make-prompts.sh` regenerates them (macOS voice today; Piper on the GB10 in production) |

## Status
- Tested against Asterisk 23 in Docker on a Mac with a simulated answering phone: rings, plays all prompts,
  records both answers, hangs up (≈ 28 s).
- **Not yet tried on the GB10 or with Linphone.**
- Not done: speech-to-text of the answers (whisper.cpp), and a "Call vendor" button wired to the case (T10/T03b).
  The demo routes Acme's number on file to the Linphone phone; production would be an extension on the district's phone system.
