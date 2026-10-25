import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import type { AlertItem, CallbackResult, CaseDetail } from "../types";
import { Icon, type IconName } from "../ui/Icon";
import { clock, personName } from "../format";
import { changes, invoiceLabel, longDate, plain, possessive, rowFor, shortName, whatHalberdDid, whyOf, type ChangeRow } from "../copy";
import { Paper } from "./Paper";
import { Amount } from "../ui/Amount";
import { PrimaryButton } from "../ui/Button";
import { InvoiceDrawer } from "./InvoiceDrawer";
import { CallPanel } from "./CallPanel";
import { RiskDot } from "../ui/RiskDot";

export const CLERK = "janet.kim";
export const MANAGER = "omar.reyes";

const isOpen = (s: string) => s === "OPEN" || s === "AWAITING_VENDOR" || s === "AWAITING_REQUESTER";
const VISION = new Set(["invoice_visual_diff", "hidden_pdf_text"]);
const PATTERN = new Set([
  "first_bank_change", "style_mismatch", "off_cycle_date", "bill_too_soon", "fixed_amount_changed", "amount_out_of_range",
  "no_billing_history", "one_time_bill", "invoice_out_of_sequence",
]);

export function CaseMain({ d, alert, busy, onCallback, onApprove, onReject, onNext }: {
  d: CaseDetail; alert: AlertItem | null; busy: boolean;
  onCallback: (r: CallbackResult) => void; onApprove: () => void; onReject: () => void; onNext: (() => void) | null;
}) {
  const c = d.case;
  const tone = c.outcome === "HOLD_CONFIRM" ? "confirm" : "fraud";
  const risky = isOpen(c.state);
  const mark = risky ? tone : "settled";
  const vendor = d.vendor?.name ?? c.vendorName ?? "Unknown sender";
  const has = (k: string) => d.findings.some((f) => f.check === k);
  const forged = !!d.hiddenText || has("invoice_visual_diff");
  const kind = forged ? "forged" : has("lookalike_domain") ? "domain"
    : has("first_bank_change") || has("style_mismatch") ? "pattern" : "none";
  const [drawer, setDrawer] = useState(false);

  const scroller = useRef<HTMLDivElement>(null);
  const last = useRef(c.state);
  useEffect(() => {
    if (last.current !== c.state) scroller.current?.closest(".main")?.scrollTo({ top: 0, behavior: "smooth" });
    last.current = c.state;
  }, [c.state]);

  const flags = changes(d.findings, 6);

  return (
    <div className="stack" ref={scroller}>
      <Hero d={d} vendor={vendor} tone={tone} risky={risky} onSeeInvoice={d.invoice.current ? () => setDrawer(true) : null} />
      <Timeline d={d} alert={alert} flags={flags} mark={mark} vendor={vendor} />

      <div id="proof" className="anchor">
        {kind === "domain" && <DomainProof d={d} mark={mark} />}
        {kind === "pattern" && <PatternProof d={d} vendor={vendor} mark={mark} />}
        {kind === "forged" && <ForgedPapers d={d} mark={mark} />}
      </div>

      {flags.length > 0 && (
        <section id="flags" className="card flags anchor">
          <div className="flags-head">
            <RiskDot size={22} />
            <h2 className="flags-title">Flags</h2>
            <span className="flags-count num">{flags.length}</span>
          </div>
          <FlagList flags={flags} mark={mark} />
        </section>
      )}

      <Asked d={d} />
      {!d.invoice.current && <BankTiles d={d} mark={mark} />}

      <Dock d={d} vendor={vendor} busy={busy} onCallback={onCallback} onApprove={onApprove} onReject={onReject} onNext={onNext} />
      {drawer && <InvoiceDrawer d={d} mark={mark} vendor={vendor} onClose={() => setDrawer(false)} />}
    </div>
  );
}

function FlagList({ flags, mark }: { flags: ChangeRow[]; mark: string }) {
  return (
    <ol className={`flag-list ${mark}`}>
      {flags.map((r) => (
        <li key={r.key} className="flag">
          <span className="flag-label">{r.label}</span>
          <span className="flag-vals">
            <span className="flag-was">{r.usually}</span>
            <Icon name="Arrow" size={14} className="flag-arrow" />
            <span className="flag-now">{r.now}</span>
          </span>
        </li>
      ))}
    </ol>
  );
}

/* ------------------------------------------------------------------ hero verdict */

function Hero({ d, vendor, tone, risky, onSeeInvoice }: {
  d: CaseDetail; vendor: string; tone: string; risky: boolean; onSeeInvoice: (() => void) | null;
}) {
  const c = d.case;
  const date = d.invoice.current?.invoiceDate ?? d.email?.date ?? c.createdAt;
  const label = d.scenario?.label ?? (tone === "fraud" ? "Fraud risk" : "Needs confirmation");
  const line = d.scenario?.subline || whyOf(d);
  const state = c.state === "APPROVED" ? { word: "Released", icon: "Unlock" as IconName }
    : c.state === "REJECTED" ? { word: "Stopped", icon: "Cross" as IconName }
    : c.state === "READY_FOR_APPROVAL" ? { word: "Confirmed", icon: "ShieldCheck" as IconName }
    : { word: "Held", icon: "Lock" as IconName };
  const cls = c.state === "APPROVED" ? "released" : c.state === "REJECTED" ? "stopped" : "held";
  return (
    <section className={`hero ${cls}`}>
      <div className="hero-top">
        <span className={`hero-pill ${risky ? tone : ""}`}><Icon name="Alert" size={16} className="hero-alert" />{label}</span>
        <span className="hero-state fade" key={state.word}><Icon name={state.icon} size={44} />{state.word}</span>
      </div>
      <p className="hero-line">{line}</p>
      <div className="hero-foot">
        <div className="hero-who">
          <div className="hero-vendor">{vendor}</div>
          <div className="hero-meta">{invoiceLabel(c.invoiceNumber)} · {longDate(date)}</div>
          {onSeeInvoice && (
            <button className="hero-see" onClick={onSeeInvoice}><Icon name="Invoice" size={16} />See invoice<Icon name="ArrowUpRight" size={14} className="see-arrow" /></button>
          )}
        </div>
        <div className="hero-amt">
          {c.amount != null ? <Amount n={c.amount} /> : <span className="hero-bank">Bank change</span>}
        </div>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ interception timeline */

type StepState = "done" | "now" | "next";
interface Step { key: string; title: string; sub: string; state: StepState; panel: ReactNode }

function Timeline({ d, alert, flags, mark, vendor }: { d: CaseDetail; alert: AlertItem | null; flags: ChangeRow[]; mark: string; vendor: string }) {
  const c = d.case;
  const ev = d.audit.events;
  const find = (a: string) => [...ev].reverse().find((e) => e.action === a);
  const opened = find("case_opened");
  const checks = new Set<string>();
  for (const f of d.findings) checks.add(VISION.has(f.check) ? "Vision" : PATTERN.has(f.check) ? "Fingerprint" : "Rules");
  const order = ["Rules", "Fingerprint", "Vision"].filter((x) => checks.has(x));
  const viaPhone = c.nextStep !== "requester_confirmation";
  const rq = d.requesterChecks[0];
  const cb = d.callbacks[0];
  const phone = cb?.phone ?? d.vendor?.phoneOnFile;
  const ready = c.state === "READY_FOR_APPROVAL";
  const done = c.state === "APPROVED" || c.state === "REJECTED";
  const conf = find(viaPhone ? "vendor_confirmation" : "requester_confirmation");
  const confirmed = (conf?.detail as { confirmed?: boolean } | undefined)?.confirmed;
  const verified = ready || conf != null;
  const decided = find(c.state === "APPROVED" ? "approved" : "rejected");
  const did = whatHalberdDid(d, alert);
  const first = rq?.recipientName?.replace(/^(Dr|Mr|Mrs|Ms|Mx)\.?\s+/i, "").split(" ")[0] ?? "the requester";
  const verifyNow = !(verified || done);
  const [open, setOpen] = useState<string | null>(verifyNow ? "ver" : null);
  const call = d.call ?? (cb?.recordingUrl ? { audio: cb.recordingUrl, transcript: cb.transcriptUrl ?? null } : null);

  const verifySub = conf ? (confirmed === false ? (viaPhone ? "Vendor never sent it" : "Not ordered") : "Confirmed")
    : cb?.status === "no_answer" ? "No answer yet"
    : viaPhone ? "Call the number on file" : `Ask ${rq?.recipientName ?? "the requester"}`;

  const steps: Step[] = [
    { key: "rx", title: "Invoice received", sub: clock(c.createdAt), state: "done", panel: (
      <dl className="kv">
        {d.email?.from && <><dt>From</dt><dd>{d.email.from}</dd></>}
        {d.email?.subject && <><dt>Subject</dt><dd>{plain(d.email.subject)}</dd></>}
        <dt>Received</dt><dd>{clock(c.createdAt)}</dd>
      </dl>
    ) },
    { key: "chk", title: "Checked company fingerprint", sub: order.join(" · ") || "Rules", state: "done", panel: (
      <p className="panel-p">
        Halberd compared this email with {possessive(vendor)} history: who sends their email, the bank they use,
        how much and how often they bill, and how they write.
      </p>
    ) },
    { key: "flags", title: "Flags found", sub: flags.length === 1 ? "1 flag" : `${flags.length} flags`, state: "done",
      panel: flags.length ? <FlagList flags={flags} mark={mark} /> : <p className="panel-p">Nothing out of pattern.</p> },
    { key: "held", title: "Payment held", sub: clock(opened?.ts ?? c.createdAt), state: "done", panel: (
      <ul className="did">{did.map((x) => <li key={x}>{x}</li>)}<li>Nothing leaves until a manager releases it.</li></ul>
    ) },
    { key: "ver", title: viaPhone ? "Halberd called the vendor" : `Halberd called ${first}`, sub: verifySub,
      state: verifyNow ? "now" : "done", panel: (
        <CallPanel
          call={call}
          tone={viaPhone ? "fraud" : "neutral"}
          headline={viaPhone
            ? (phone ? `Halberd called ${vendor} at ${phone}, the number on file` : `No number on file for ${vendor}`)
            : `Halberd called ${rq?.recipientName ?? "the requester"} to confirm the order`}
        />
      ) },
    { key: "dec", title: "Decision", sub: done ? `${c.state === "APPROVED" ? "Released" : "Stopped"} ${decided ? clock(decided.ts) : ""}`.trim() : ready ? "Ready to approve" : "Approve or reject",
      state: done ? "done" : ready ? "now" : "next", panel: (
        <p className="panel-p">
          {done && decided ? `${personName(decided.actor)} ${c.state === "APPROVED" ? "released" : "stopped"} it at ${clock(decided.ts)}.`
            : "Only a manager can release a held payment. Halberd never pays on its own."}
        </p>
      ) },
  ];
  return (
    <section id="hero-tl" className="card tl" aria-label="What happened">
      <ol className="tl-steps">
        {steps.map((s) => (
          <li key={s.key} className={`tl-step ${s.state}${open === s.key ? " open" : ""}`}>
            <button className="tl-btn" onClick={() => setOpen((o) => (o === s.key ? null : s.key))} aria-expanded={open === s.key}>
              <span className="tl-node">{s.state === "done" ? <Icon name="Check" size={12} /> : <span className="tl-dot" />}</span>
              <span className="tl-head">
                <span className="tl-title">{s.title}</span>
                <Icon name="ChevronDown" size={16} className="tl-chev" />
              </span>
              <span className="tl-sub">{s.sub}</span>
            </button>
          </li>
        ))}
      </ol>
      <Reveal openKey={open} render={(k) => {
        const st = steps.find((x) => x.key === k);
        if (!st) return null;
        return <>{k !== "ver" && <div className="tl-panel-title">{st.title}</div>}{st.panel}</>;
      }} />
    </section>
  );
}

/**
 * Smooth open/close for the step panel: the height animates to the measured content, the content fades in from
 * -4px, and switching steps cross-fades the old panel out over the new one instead of collapsing to zero.
 */
function Reveal({ openKey, render }: { openKey: string | null; render: (key: string) => ReactNode }) {
  const [shown, setShown] = useState<string | null>(openKey);
  const [prev, setPrev] = useState<string | null>(null);
  const [h, setH] = useState(0);
  const inner = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (openKey && openKey !== shown) {
      if (shown) {
        setPrev(shown);
        const t = window.setTimeout(() => setPrev(null), 280);
        setShown(openKey);
        return () => window.clearTimeout(t);
      }
      setShown(openKey);
    }
    return undefined;
  }, [openKey]); // eslint-disable-line react-hooks/exhaustive-deps

  useLayoutEffect(() => {
    const el = inner.current;
    if (!el) return;
    const measure = () => setH(el.offsetHeight);
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [shown]);

  const isOpen = !!openKey;
  return (
    <div className={`tl-reveal${isOpen ? " open" : ""}`} style={{ height: isOpen ? h : 0 }} aria-hidden={!isOpen}>
      <div className="tl-reveal-in" ref={inner}>
        {shown && <div className="tl-panel" key={shown}><div className="tl-pane">{render(shown)}</div></div>}
      </div>
      {prev && prev !== shown && <div className="tl-panel tl-pane-out" key={`out-${prev}`}>{render(prev)}</div>}
    </div>
  );
}

/* ------------------------------------------------------------------ the one big proof per scenario */

function splitDiff(a: string, b: string): [string, string, string] {
  let i = 0;
  while (i < a.length && i < b.length && a[i] === b[i]) i++;
  let j = 0;
  while (j < a.length - i && j < b.length - i && a[a.length - 1 - j] === b[b.length - 1 - j]) j++;
  return [b.slice(0, i), b.slice(i, b.length - j), b.slice(b.length - j)];
}

function DomainProof({ d, mark }: { d: CaseDetail; mark: string }) {
  const f = d.findings.find((x) => x.check === "lookalike_domain")!;
  const real = plain(f.expected).replace(/^.*@/, "");
  const fake = plain(f.actual).replace(/^.*@/, "");
  const [rp, rm, rs] = splitDiff(fake, real);
  const [fp, fm, fs] = splitDiff(real, fake);
  return (
    <section className="card proof">
      <h2>One letter off</h2>
      <div className="dom">
        <div className="dom-col">
          <div className="dom-cap">Their real address</div>
          <div className="dom-big">{rp}{rm && <span className="dom-ok">{rm}</span>}{rs}</div>
        </div>
        <div className="dom-vs" aria-hidden><Icon name="Arrow" size={20} /></div>
        <div className="dom-col">
          <div className="dom-cap">This email came from</div>
          <div className={`dom-big fake ${mark}`}>{fp}{fm && <mark>{fm}</mark>}{fs}</div>
        </div>
      </div>
      {fm && rm && <p className="dom-note">“{fm}” where the real address has “{rm}”.</p>}
    </section>
  );
}

const TRAITS: { label: string; checks: string[]; ok: string }[] = [
  { label: "Sender address", checks: ["lookalike_domain", "freemail_sender", "unknown_sender", "reply_to_mismatch"], ok: "Their real address" },
  { label: "Bank account", checks: ["bank_mismatch", "bank_change_request", "first_bank_change"], ok: "The bank on file" },
  { label: "Writing style", checks: ["style_mismatch", "urgency", "unusual_request"], ok: "Reads like them" },
  { label: "Billing day", checks: ["off_cycle_date", "bill_too_soon"], ok: "On their usual schedule" },
  { label: "Amount", checks: ["fixed_amount_changed", "amount_out_of_range"], ok: "In their usual range" },
];

function PatternProof({ d, vendor, mark }: { d: CaseDetail; vendor: string; mark: string }) {
  const rows = TRAITS.map((t) => {
    const f = d.findings.find((x) => t.checks.includes(x.check) && x.severity !== "info" && x.severity !== "unknown");
    return { ...t, out: !!f, r: f ? rowFor(f) : null };
  });
  const matched = rows.filter((r) => !r.out).length;
  return (
    <section className="card proof">
      <div className="proof-head">
        <h2>How {shortName(vendor)} usually writes and bills</h2>
        <span className="meter-cap"><b>{matched} of {rows.length}</b> match</span>
      </div>
      <div className={`meter ${mark}`} aria-hidden>
        {rows.map((r) => <span key={r.label} className={`seg${r.out ? " out" : ""}`} />)}
      </div>
      <ul className={`traits ${mark}`}>
        {rows.map((r) => (
          <li key={r.label} className={`trait${r.out ? " out" : ""}`}>
            <span className="trait-ic">{r.out ? <Icon name="Alert" size={16} /> : <Icon name="Check" size={16} />}</span>
            <span className="trait-label">{r.label}</span>
            <span className="trait-was">{r.out && r.r ? r.r.usually : r.ok}</span>
            <span className="trait-now">{r.out && r.r ? r.r.now : "Matches"}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Forged invoice: the side-by-side is the proof itself, so it stays on the page. */
function ForgedPapers({ d, mark }: { d: CaseDetail; mark: string }) {
  if (!d.invoice.current) return null;
  return (
    <section className="card proof glow">
      <h2>Their last real invoice, next to this one</h2>
      <div className="papers">
        {d.invoice.lastReal && <Paper inv={d.invoice.lastReal} caption="Last real invoice" big />}
        <Paper inv={d.invoice.current} against={d.invoice.lastReal} tone={mark} caption="This invoice" hidden={d.hiddenText} big />
      </div>
    </section>
  );
}

function BankTiles({ d, mark }: { d: CaseDetail; mark: string }) {
  const b = d.bankOnFile;
  const f = d.findings.find((x) => (x.check === "bank_mismatch" || x.check === "bank_change_request") && /account/i.test(x.actual));
  const last4 = f?.actual.match(/account\s+\S*?(\d{4})/i)?.[1];
  const bank = f?.actual.split(",")[0]?.trim();
  return (
    <section className="card papers-card">
      <h2>Bank details</h2>
      <div className="tiles">
        <div className="tile">
          <div className="tile-cap">Bank on file</div>
          <div className="tile-num"><span className="dots">••</span><span className="num">{b?.accountLast4 ?? "—"}</span></div>
          <div className="tile-sub">{b?.bankName}</div>
        </div>
        <div className="tile-arrow"><Icon name="Arrow" size={20} /></div>
        <div className={`tile chg ${mark}`}>
          <div className="tile-cap">Requested in the email</div>
          <div className={`tile-num ${mark}`}>{last4 ? <><span className="dots">••</span><span className="num">{last4}</span></> : "New account"}</div>
          <div className="tile-sub">{bank && last4 ? bank : "No details given"}</div>
        </div>
      </div>
    </section>
  );
}

function Asked({ d }: { d: CaseDetail }) {
  const rq = d.requesterChecks[0];
  if (d.case.nextStep !== "requester_confirmation" || !rq?.text) return null;
  return (
    <section className="card asked">
      <h2>Halberd's question for {rq.recipientName ?? "the requester"}</h2>
      {rq.recipientContact && <p className="quiet">{[rq.recipientDepartment, rq.recipientContact].filter(Boolean).join(" · ")}</p>}
      <blockquote className="msg">{plain(rq.text)}</blockquote>
    </section>
  );
}

/* ------------------------------------------------------------------ the next thing to click */

function Dock({ d, vendor, busy, onCallback, onApprove, onReject, onNext }: {
  d: CaseDetail; vendor: string; busy: boolean;
  onCallback: (r: CallbackResult) => void; onApprove: () => void; onReject: () => void; onNext: (() => void) | null;
}) {
  const c = d.case;
  const viaPhone = c.nextStep !== "requester_confirmation";
  const rq = d.requesterChecks[0];
  const who = rq?.recipientName ?? "the requester";
  const first = rq?.recipientName?.replace(/^(Dr|Mr|Mrs|Ms|Mx)\.?\s+/i, "").split(" ")[0] ?? "Requester";
  const ev = d.audit.events;
  const lastEv = (a: string) => [...ev].reverse().find((e) => e.action === a);
  const cb = d.callbacks[0];
  const phone = cb?.phone ?? d.vendor?.phoneOnFile;

  let icon: IconName = "PhoneCall";
  let title: ReactNode;
  let sub: ReactNode = null;
  let actions: ReactNode;

  if (c.state === "APPROVED" || c.state === "REJECTED") {
    const stopped = c.state === "REJECTED";
    const e = lastEv(stopped ? "rejected" : "approved");
    const denied = ev.some((x) => (x.action === "vendor_confirmation" || x.action === "requester_confirmation") && (x.detail as { confirmed?: boolean })?.confirmed === false);
    icon = stopped ? "Cross" : "Unlock";
    title = stopped ? (denied ? (viaPhone ? `${vendor} never sent this. Payment stopped.` : `${first} didn't order this. Payment stopped.`) : "Payment stopped.")
      : `Released to ${vendor}.`;
    sub = e ? `${personName(e.actor)} ${stopped ? "stopped" : "released"} it at ${clock(e.ts)}.` : null;
    actions = onNext ? <PrimaryButton onClick={onNext}>Next held invoice</PrimaryButton> : null;
  } else if (c.state === "READY_FOR_APPROVAL") {
    icon = "ShieldCheck";
    title = viaPhone ? `${vendor} confirmed it by phone.` : `${first} confirmed the order.`;
    sub = "A manager can release the payment now.";
    actions = (
      <>
        <button className="btn ghost" disabled={busy} onClick={onReject}>Reject</button>
        <PrimaryButton disabled={busy} onClick={onApprove}>Approve and release</PrimaryButton>
      </>
    );
  } else if (viaPhone) {
    title = phone ? <>Call {shortName(vendor)} at <span className="dock-phone num">{phone}</span></> : `No number on file for ${vendor}.`;
    sub = cb?.status === "no_answer" ? `No answer at ${clock(cb.completedAt)}. Try again later.` : "The number on file. Never the one in the email.";
    actions = (
      <>
        <button className="btn ghost" disabled={busy} onClick={onReject}>Reject</button>
        {phone && <button className="btn" disabled={busy} onClick={() => onCallback("no_answer")}>No answer</button>}
        {phone && <button className="btn" disabled={busy} onClick={() => onCallback("confirmed_legit")}>Vendor confirmed</button>}
        {phone && <PrimaryButton disabled={busy} onClick={() => onCallback("confirmed_fraud")}>Vendor says it's fake</PrimaryButton>}
      </>
    );
  } else {
    icon = "Users";
    title = `Ask ${who} to confirm the order`;
    sub = "Approve unlocks once they confirm.";
    actions = (
      <>
        <button className="btn ghost" disabled={busy} onClick={onReject}>Reject</button>
        <button className="btn" disabled={busy} onClick={() => onCallback("confirmed_fraud")}>{first} didn't order it</button>
        <PrimaryButton disabled={busy} onClick={() => onCallback("confirmed_legit")}>{first} confirmed</PrimaryButton>
      </>
    );
  }

  return (
    <section id="dock" className={`dock ${c.state === "APPROVED" || c.state === "REJECTED" ? "done" : ""}`} aria-label="Next step">
      <div className="dock-in" key={c.state + (cb?.status ?? "")}>
        <span className="dock-ic"><Icon name={icon} size={20} /></span>
        <div className="dock-text">
          <div className="dock-eyebrow">{c.state === "APPROVED" || c.state === "REJECTED" ? "Done" : "Next step"}</div>
          <div className="dock-title">{title}</div>
          {sub && <div className="dock-sub">{sub}</div>}
        </div>
        <div className="dock-actions">{actions}</div>
      </div>
    </section>
  );
}

