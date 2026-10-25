// Data access. Uses the real API (src/api/, proxied by Vite) whenever GET /api/status answers;
// otherwise the offline mock in mock.ts. Live updates: SSE /api/events, polling as a fallback.
import type { AlertItem, CallbackResult, CaseDetail, CaseSummary, ClearedInvoice, DemoFile, InvoiceDetail, InvoiceRow, Role, Status } from "./types";
import { createMockBackend } from "./mock";

export interface Backend {
  mode: "live" | "mock";
  status(): Promise<Status>;
  cases(): Promise<CaseSummary[]>;
  caseDetail(id: string): Promise<CaseDetail>;
  alerts(): Promise<AlertItem[]>;
  demoFiles(): Promise<DemoFile[]>;
  /** Sidebar: held cases first, then paid / approved history, newest first. */
  invoices(): Promise<InvoiceRow[]>;
  invoiceDetail(id: string): Promise<InvoiceDetail>;
  callback(id: string, result: CallbackResult, actor: string): Promise<unknown>;
  approve(id: string, actor: string, role: Role): Promise<unknown>;
  reject(id: string, actor: string, role: Role): Promise<unknown>;
  reset(): Promise<unknown>;
  ingest(file?: string): Promise<unknown>;
  /** Calls `fn` with an event kind ("case" | "alert" | "status") whenever something changes. */
  subscribe(fn: (kind: string) => void): () => void;
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });
  const text = await res.text();
  let body: any = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = text; }
  if (!res.ok) {
    const msg = (body && typeof body === "object" && (body.error || body.message)) || `HTTP ${res.status}`;
    throw new Error(String(msg));
  }
  return body as T;
}

/** Fill every optional part of a case detail so the view never meets a null array or object. */
export function normalizeDetail(raw: any): CaseDetail {
  const d = raw ?? {};
  const inv = (v: any) => (v ? { ...v, lines: Array.isArray(v.lines) ? v.lines : [] } : null);
  const c = d.case ?? {};
  return {
    case: { ...c, topChecks: Array.isArray(c.topChecks) ? c.topChecks : [], score: c.score ?? 0 },
    vendor: d.vendor ? { ...d.vendor, contacts: Array.isArray(d.vendor.contacts) ? d.vendor.contacts : [] } : null,
    bankOnFile: d.bankOnFile ?? null,
    invoice: { current: inv(d.invoice?.current), lastReal: inv(d.invoice?.lastReal) },
    email: d.email ?? null,
    findings: (Array.isArray(d.findings) ? d.findings : []).map((f: any) => ({
      ...f, check: String(f?.check ?? "check"), expected: f?.expected == null ? "" : String(f.expected),
      actual: f?.actual == null ? "" : String(f.actual), explanation: f?.explanation == null ? "" : String(f.explanation),
      severity: ["high", "medium", "low", "info", "unknown"].includes(f?.severity) ? f.severity : "unknown",
    })),
    decision: d.decision ?? { outcome: c.outcome, nextStep: c.nextStep, score: c.score ?? 0, severity: c.severity, reasons: [] },
    callbacks: Array.isArray(d.callbacks) ? d.callbacks : [],
    requesterChecks: Array.isArray(d.requesterChecks) ? d.requesterChecks : [],
    audit: {
      events: Array.isArray(d.audit?.events) ? d.audit.events : [],
      chainOk: d.audit?.chainOk !== false,
      count: d.audit?.count ?? 0,
    },
    scenario: d.scenario ?? null,
    why: d.why ?? null,
    hiddenText: d.hiddenText ?? null,
    call: d.call && typeof d.call.audio === "string" ? { audio: d.call.audio, transcript: d.call.transcript ?? null } : null,
  };
}

export function normalizeInvoiceDetail(raw: any): InvoiceDetail {
  if (raw && raw.kind === "invoice") {
    const inv = raw.invoice ?? {};
    return {
      kind: "invoice",
      invoice: { ...inv, lines: Array.isArray(inv.lines) ? inv.lines : [] },
      vendor: raw.vendor ?? null,
      verdict: raw.verdict ?? null,
    } as ClearedInvoice;
  }
  return { kind: "case", ...normalizeDetail(raw) };
}

const riskOf = (c: CaseSummary): InvoiceRow["risk"] =>
  c.outcome === "PASS" ? "cleared" : c.outcome === "HOLD_CONFIRM" ? "confirm" : "fraud";

/** Older API without /api/invoices: build the held part of the list from /api/cases. */
export const rowsFromCases = (cs: CaseSummary[]): InvoiceRow[] => cs.map((c) => ({
  id: c.id, kind: "case", caseId: c.id, vendorName: c.vendorName, invoiceNumber: c.invoiceNumber,
  date: c.createdAt, amount: c.amount, risk: riskOf(c), state: c.state,
}));

const post = <T,>(path: string, data: unknown = {}) => json<T>(path, { method: "POST", body: JSON.stringify(data) });

/** Accept either a bare array or { items|files|cases|alerts: [...] } from the API. */
function list<T>(v: any, key: string): T[] {
  if (Array.isArray(v)) return v;
  if (v && Array.isArray(v[key])) return v[key];
  if (v && Array.isArray(v.items)) return v.items;
  return [];
}

export function createLiveBackend(): Backend {
  return {
    mode: "live",
    status: () => json<Status>("/api/status"),
    cases: async () => list<CaseSummary>(await json("/api/cases"), "cases"),
    caseDetail: async (id) => normalizeDetail(await json(`/api/cases/${encodeURIComponent(id)}`)),
    alerts: async () => list<AlertItem>(await json("/api/alerts"), "alerts"),
    demoFiles: async () => {
      const raw = list<any>(await json("/api/demo/files"), "files");
      return raw.map((f) => (typeof f === "string" ? { file: f } : f));
    },
    invoices: async () => {
      try {
        return list<InvoiceRow>(await json("/api/invoices"), "invoices");
      } catch {
        return rowsFromCases(list<CaseSummary>(await json("/api/cases"), "cases"));
      }
    },
    invoiceDetail: async (id) => {
      try {
        return normalizeInvoiceDetail(await json(`/api/invoices/${encodeURIComponent(id)}`));
      } catch (err) {
        if (!/^HOLD-/.test(id)) throw err;
        return normalizeInvoiceDetail(await json(`/api/cases/${encodeURIComponent(id)}`));
      }
    },
    callback: (id, result, actor) => post(`/api/cases/${encodeURIComponent(id)}/callback`, { result, actor }),
    approve: (id, actor, role) => post(`/api/cases/${encodeURIComponent(id)}/approve`, { actor, role }),
    reject: (id, actor, role) => post(`/api/cases/${encodeURIComponent(id)}/reject`, { actor, role }),
    reset: () => post("/api/demo/reset"),
    ingest: (file) => post("/api/demo/ingest", file ? { file } : {}),
    subscribe(fn) {
      let es: EventSource | null = null;
      let poll: ReturnType<typeof setInterval> | null = null;
      let closed = false;
      const startPolling = () => {
        if (poll || closed) return;
        poll = setInterval(() => fn("poll"), 3000);
      };
      try {
        es = new EventSource("/api/events");
        for (const kind of ["case", "alert", "status", "reset"]) es.addEventListener(kind, () => fn(kind));
        es.onmessage = () => fn("message");
        es.onopen = () => { if (poll) { clearInterval(poll); poll = null; } };
        es.onerror = () => startPolling();
      } catch {
        startPolling();
      }
      // Slow safety poll even with SSE up, so a dropped event can never leave the screen stale.
      const safety = setInterval(() => fn("poll"), 15000);
      return () => {
        closed = true;
        es?.close();
        if (poll) clearInterval(poll);
        clearInterval(safety);
      };
    },
  };
}

/** Is the real API answering? */
export async function probeLive(timeoutMs = 1200): Promise<boolean> {
  try {
    const ctl = new AbortController();
    const t = setTimeout(() => ctl.abort(), timeoutMs);
    const res = await fetch("/api/status", { signal: ctl.signal });
    clearTimeout(t);
    if (!res.ok) return false;
    const body = await res.json();
    return !!body && typeof body === "object" && "counts" in body;
  } catch {
    return false;
  }
}

let mockSingleton: Backend | null = null;
export function mockBackend(): Backend {
  if (!mockSingleton) mockSingleton = createMockBackend();
  return mockSingleton;
}

/** Design phase: the mock is the default. ?live=1 uses the real API, ?mock=empty starts the mock empty. */
export function forcedMock(): "off" | "on" | "empty" {
  const q = new URLSearchParams(window.location.search);
  if (q.get("mock") === "empty") return "empty";
  if (q.get("live") === "1") return "off";
  return "on";
}
