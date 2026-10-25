// Verification call through the local Asterisk (ARI on 127.0.0.1:8088): ring the vendor's phone,
// play each question, record each answer. No cloud: the call stays on the local network.
// It gathers evidence only; a person still records "confirmed" or "denied" on the case.
//
//   npx tsx voice/call.ts                     → calls PJSIP/vendor-demo (the Linphone phone)
//   npx tsx voice/call.ts --case HOLD-0003    → recordings named after the case
//
// Settings come from ~/.invoice-guard-voice.env (written by voice/setup.sh) or the environment.
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const envFile = join(homedir(), ".invoice-guard-voice.env");
if (existsSync(envFile)) process.loadEnvFile(envFile);

const ARI = (process.env.ARI_URL ?? "http://127.0.0.1:8088").replace(/\/$/, "");
const AUTH = `${process.env.ARI_USER ?? "invoice-guard"}:${process.env.ARI_PASSWORD ?? ""}`;
const APP = "invoice-guard";
const SOUNDS = process.env.VOICE_SOUNDS ?? "sound:invoice-guard/";   // /var/lib/asterisk/sounds/invoice-guard/*.wav
const QUESTIONS = ["q1", "q2"];

export interface CallResult {
  status: "completed" | "no_answer" | "hung_up" | "failed";
  endpoint: string;
  recordings: { question: string; file: string }[];   // on the GB10: /var/spool/asterisk/recording/<name>.wav
  error?: string;
}

type AriEvent = { type: string; channel?: { id: string }; playback?: { id: string }; recording?: { name: string; state?: string; cause?: string }; cause?: number };

async function ari(method: string, path: string, params: Record<string, string | number | boolean> = {}) {
  const q = new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)]));
  const res = await fetch(`${ARI}/ari${path}${q.size ? `?${q}` : ""}`, {
    method, headers: { authorization: `Basic ${Buffer.from(AUTH).toString("base64")}` },
  });
  if (!res.ok) throw new Error(`ARI ${method} ${path}: HTTP ${res.status} ${await res.text()}`);
  return res.status === 204 ? null : res.json();
}

/** Listen to ARI events for our app; waitFor() resolves on the first matching event, rejects if the call ends first. */
function events() {
  const ws = new WebSocket(`${ARI.replace(/^http/, "ws")}/ari/events?app=${APP}&api_key=${encodeURIComponent(AUTH)}`);
  const waiters: { match: (e: AriEvent) => boolean; resolve: (e: AriEvent) => void; reject: (err: Error) => void; timer: NodeJS.Timeout }[] = [];
  let ended: string | null = null;
  let channelId: string | null = null;
  ws.onmessage = (m) => {
    const e = JSON.parse(String(m.data)) as AriEvent;
    for (const w of [...waiters]) if (w.match(e)) { clearTimeout(w.timer); waiters.splice(waiters.indexOf(w), 1); w.resolve(e); }
    if (channelId && e.channel?.id === channelId && (e.type === "ChannelDestroyed" || e.type === "StasisEnd")) {
      ended = e.type;
      for (const w of waiters.splice(0)) { clearTimeout(w.timer); w.reject(new Error(`call ended (${e.type})`)); }
    }
  };
  const open = new Promise<void>((resolve, reject) => { ws.onopen = () => resolve(); ws.onerror = () => reject(new Error(`can't open ARI WebSocket at ${ARI}`)); });
  return {
    open, close: () => ws.close(), watch: (id: string) => { channelId = id; }, get ended() { return ended; },
    waitFor(match: (e: AriEvent) => boolean, ms: number, what: string) {
      if (ended) return Promise.reject(new Error(`call ended (${ended})`));
      return new Promise<AriEvent>((resolve, reject) => {
        const timer = setTimeout(() => { waiters.splice(waiters.findIndex((w) => w.timer === timer), 1); reject(new Error(`timed out waiting for ${what}`)); }, ms);
        waiters.push({ match, resolve, reject, timer });
      });
    },
  };
}

export async function verificationCall(opts: { endpoint?: string; caseId?: string; ringSeconds?: number } = {}): Promise<CallResult> {
  const endpoint = opts.endpoint ?? process.env.VOICE_ENDPOINT ?? "PJSIP/vendor-demo";
  const tag = (opts.caseId ?? `call-${Date.now()}`).replace(/[^\w-]/g, "_");
  const recordings: CallResult["recordings"] = [];
  const ev = events();
  await ev.open;
  let channelId: string | null = null;
  try {
    const answered = ev.waitFor((e) => e.type === "StasisStart", (opts.ringSeconds ?? 30) * 1000 + 5000, "the phone to answer");
    const ch = await ari("POST", "/channels", { endpoint, app: APP, callerId: "\"AP Verification\" <100>", timeout: opts.ringSeconds ?? 30 });
    channelId = ch.id;
    ev.watch(ch.id);
    try { await answered; } catch { return { status: "no_answer", endpoint, recordings }; }

    const play = async (sound: string) => {
      const pb = await ari("POST", `/channels/${channelId}/play`, { media: `${SOUNDS}${sound}` });
      await ev.waitFor((e) => e.type === "PlaybackFinished" && e.playback?.id === pb.id, 60_000, `prompt ${sound}`);
    };
    await play("greeting");
    for (const q of QUESTIONS) {
      await play(q);
      await play("beep");   // our own tone: Asterisk's sound packs aren't always installed
      const name = `${tag}-${q}`;
      await ari("POST", `/channels/${channelId}/record`, { name, format: "wav", maxDurationSeconds: 20,
                                                           maxSilenceSeconds: 3, ifExists: "overwrite", terminateOn: "#" });
      const done = await ev.waitFor((e) => (e.type === "RecordingFinished" || e.type === "RecordingFailed") && e.recording?.name === name,
                                    30_000, `answer to ${q}`);
      if (done.type === "RecordingFinished") recordings.push({ question: q, file: `/var/spool/asterisk/recording/${name}.wav` });
    }
    await play("goodbye");
    return { status: "completed", endpoint, recordings };
  } catch (err) {
    const msg = (err as Error).message;
    return { status: msg.startsWith("call ended") ? "hung_up" : "failed", endpoint, recordings, error: msg };
  } finally {
    if (channelId && !ev.ended) await ari("DELETE", `/channels/${channelId}`).catch(() => {});
    ev.close();
  }
}

// CLI
if (process.argv[1]?.endsWith("call.ts")) {
  const args = process.argv.slice(2);
  const flag = (n: string) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : undefined; };
  const r = await verificationCall({ caseId: flag("--case"), endpoint: flag("--endpoint") });
  console.log(JSON.stringify(r, null, 2));
  process.exit(r.status === "completed" ? 0 : 1);
}
