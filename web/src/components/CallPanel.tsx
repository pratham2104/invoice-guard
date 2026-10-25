import { useEffect, useMemo, useRef, useState, type PointerEvent as RPointerEvent } from "react";
import type { CallRef, CallTranscript } from "../types";
import { Icon } from "../ui/Icon";

const BARS = 72;
const SPEEDS = [1, 1.25, 1.5, 2];

/** Fixed pseudo-random waveform, seeded by the file name so each call keeps its own shape. */
function peaks(seed: string): number[] {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) h = Math.imul(h ^ seed.charCodeAt(i), 16777619);
  const out: number[] = [];
  for (let i = 0; i < BARS; i++) {
    h = Math.imul(h ^ (h >>> 15), 2246822507);
    h = Math.imul(h ^ (h >>> 13), 3266489909);
    const r = ((h ^= h >>> 16) >>> 0) / 4294967295;
    const env = 0.55 + 0.45 * Math.sin((i / BARS) * Math.PI * 3.1 + 0.6);
    out.push(Math.max(0.14, Math.min(1, 0.22 + r * 0.6 * env + 0.18 * env)));
  }
  return out;
}

const mmss = (t: number) => {
  if (!Number.isFinite(t) || t < 0) t = 0;
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
};

/**
 * The call Halberd's local voice agent placed: player, transcript in turns, and what the call heard.
 * It never decides anything; the human decision stays in the Next step bar.
 */
export function CallPanel({ call, headline, tone }: { call: CallRef | null; headline: string; tone: "fraud" | "neutral" }) {
  const [tx, setTx] = useState<CallTranscript | null>(null);
  const [failed, setFailed] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [t, setT] = useState(0);
  const [dur, setDur] = useState(0);
  const [speed, setSpeed] = useState(1);
  const audio = useRef<HTMLAudioElement>(null);
  const wave = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);
  const bars = useMemo(() => peaks(call?.audio ?? "call"), [call?.audio]);

  useEffect(() => {
    setTx(null); setFailed(false);
    if (!call?.transcript) return;
    let stop = false;
    fetch(call.transcript)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((j: CallTranscript) => { if (!stop && j && Array.isArray(j.turns)) setTx(j); })
      .catch(() => { if (!stop) setFailed(true); });
    return () => { stop = true; };
  }, [call?.transcript]);

  // Smooth clock while playing.
  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    const tick = () => { if (audio.current) setT(audio.current.currentTime); raf = requestAnimationFrame(tick); };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing]);

  const total = dur || tx?.duration || 0;
  const frac = total ? Math.min(1, t / total) : 0;
  const current = tx?.turns.findIndex((u) => t >= u.start && t < u.end) ?? -1;

  const toggle = () => {
    const a = audio.current;
    if (!a) return;
    if (a.paused) a.play().catch(() => setPlaying(false)); else a.pause();
  };
  const seek = (sec: number, play = false) => {
    const a = audio.current;
    if (!a) return;
    a.currentTime = Math.max(0, Math.min(total || a.duration || 0, sec));
    setT(a.currentTime);
    if (play && a.paused) a.play().catch(() => setPlaying(false));
  };
  const seekAt = (clientX: number) => {
    const el = wave.current;
    if (!el || !total) return;
    const r = el.getBoundingClientRect();
    seek(((clientX - r.left) / r.width) * total);
  };
  const onDown = (e: RPointerEvent<HTMLDivElement>) => { dragging.current = true; e.currentTarget.setPointerCapture(e.pointerId); seekAt(e.clientX); };
  const onMove = (e: RPointerEvent<HTMLDivElement>) => { if (dragging.current) seekAt(e.clientX); };
  const onUp = () => { dragging.current = false; };
  const cycle = () => {
    const next = SPEEDS[(SPEEDS.indexOf(speed) + 1) % SPEEDS.length];
    setSpeed(next);
    if (audio.current) audio.current.playbackRate = next;
  };

  const hasAudio = !!call?.audio && !failed;
  const firstStart = tx?.turns[0]?.start ?? 0;
  const ringing = playing && t < firstStart;

  return (
    <div className="call">
      <div className="call-head">
        <span className="call-tile"><Icon name="PhoneCall" size={20} /></span>
        <div>
          <div className="call-title">{headline}</div>
          <div className="call-sub">Local voice agent · ran on this box</div>
        </div>
        {tx?.result && <span className={`call-result ${tone}`}>{tx.result}</span>}
      </div>

      {hasAudio && (
        <div className="player">
          <audio
            ref={audio} src={call!.audio} preload="metadata"
            onLoadedMetadata={(e) => setDur(e.currentTarget.duration || 0)}
            onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)}
            onEnded={() => { setPlaying(false); setT(total); }}
            onError={() => setFailed(true)}
          />
          <button className="play" onClick={toggle} aria-label={playing ? "Pause" : "Play"}>
            <Icon name={playing ? "Pause" : "Play"} size={18} />
          </button>
          <div
            className="wave" ref={wave} role="slider" aria-label="Seek" aria-valuemin={0} aria-valuemax={Math.round(total)} aria-valuenow={Math.round(t)} tabIndex={0}
            onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp}
            onKeyDown={(e) => { if (e.key === "ArrowRight") seek(t + 5); if (e.key === "ArrowLeft") seek(t - 5); }}
          >
            {bars.map((h, i) => (
              <span key={i} className={`bar${(i + 0.5) / BARS <= frac ? " on" : ""}`} style={{ height: `${Math.round(h * 100)}%` }} />
            ))}
            <span className="wave-head" style={{ left: `${frac * 100}%` }} />
            <span className={`ring${ringing ? " on" : ""}`} aria-live="polite"><span>{ringing ? "Ringing…" : ""}</span></span>
          </div>
          <span className="ptime num">{mmss(t)} / {mmss(total)}</span>
          <button className="speed num" onClick={cycle} aria-label="Playback speed">{speed}×</button>
        </div>
      )}

      {tx && (
        <ol className="turns">
          {tx.turns.map((u, i) => (
            <li key={i}>
              <button className={`turn ${u.speaker}${i === current ? " now" : ""}`} onClick={() => seek(u.start + 0.01, true)}>
                <span className="turn-who">{u.speaker === "agent" ? "Halberd" : u.name}</span>
                <span className="turn-text">{u.text}</span>
                <span className="turn-at num">{mmss(u.start)}</span>
              </button>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
