import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { AlertItem, CallbackResult, InvoiceDetail, InvoiceRow, Status } from "./types";
import { type Backend, createLiveBackend, forcedMock, mockBackend, probeLive } from "./api";
import { Sidebar } from "./components/Sidebar";
import { CaseMain, CLERK, MANAGER } from "./components/CaseMain";
import { InvoiceMain } from "./components/InvoiceMain";
import { Boundary } from "./ui/Boundary";
import { Icon } from "./ui/Icon";

const isHeld = (r: InvoiceRow) => r.kind === "case" && r.state !== "APPROVED" && r.state !== "REJECTED";

export default function App() {
  const [backend, setBackend] = useState<Backend | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [rows, setRows] = useState<InvoiceRow[]>([]);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<InvoiceDetail | null>(null);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const known = useRef<Set<string> | null>(null);
  const selectedRef = useRef<string | null>(null);
  selectedRef.current = selectedId;

  // Real API when /api/status answers, otherwise the offline mock (checked again every few seconds).
  useEffect(() => {
    let stop = false;
    let timer: ReturnType<typeof setInterval> | null = null;
    const forced = forcedMock();
    (async () => {
      if (forced !== "off") {
        const m = mockBackend();
        if (forced === "empty") await m.reset();
        if (!stop) setBackend(m);
        return;
      }
      if (await probeLive()) { if (!stop) setBackend(createLiveBackend()); return; }
      if (!stop) setBackend(mockBackend());
      timer = setInterval(async () => {
        if (await probeLive()) {
          if (timer) clearInterval(timer);
          known.current = null;
          if (!stop) { setSelectedId(null); setDetail(null); setBackend(createLiveBackend()); }
        }
      }, 4000);
    })();
    return () => { stop = true; if (timer) clearInterval(timer); };
  }, []);

  const flash = (text: string, ms = 2200) => {
    setToast(text);
    window.setTimeout(() => setToast((t) => (t === text ? null : t)), ms);
  };

  const loadDetail = useCallback(async (b: Backend, id: string | null) => {
    if (!id) { setDetail(null); setDetailId(null); return; }
    try {
      const d = await b.invoiceDetail(id);
      if (selectedRef.current === id) { setDetail(d); setDetailId(id); }
    } catch {
      if (selectedRef.current === id) { setDetail(null); setDetailId(null); }
    }
  }, []);

  const refresh = useCallback(async (b: Backend) => {
    try {
      const [s, rs, al] = await Promise.all([b.status().catch(() => null), b.invoices(), b.alerts().catch(() => [] as AlertItem[])]);
      setStatus(s); setRows(rs); setAlerts(al);
      const ids = new Set(rs.filter((r) => r.kind === "case").map((r) => r.id));
      let sel = selectedRef.current;
      if (known.current) {
        const added = rs.filter((r) => r.kind === "case" && !known.current!.has(r.id));
        if (added.length) {
          setFresh(new Set(added.map((r) => r.id)));
          window.setTimeout(() => setFresh(new Set()), 2400);
          sel = added[0].id;
        }
      }
      known.current = ids;
      if (!sel || !rs.some((r) => r.id === sel)) sel = (rs.find(isHeld) ?? rs[0])?.id ?? null;
      if (sel !== selectedRef.current) { selectedRef.current = sel; setSelectedId(sel); }
      await loadDetail(b, sel);
    } catch (err) {
      flash((err as Error).message, 4000);
    } finally {
      setLoaded(true);
    }
  }, [loadDetail]);

  useEffect(() => {
    if (!backend) return;
    refresh(backend);
    let pending: ReturnType<typeof setTimeout> | null = null;
    const unsub = backend.subscribe(() => {
      if (pending) return;
      pending = setTimeout(() => { pending = null; refresh(backend); }, 150);
    });
    return () => { unsub(); if (pending) clearTimeout(pending); };
  }, [backend, refresh]);

  const mainRef = useRef<HTMLElement>(null);
  const select = (id: string) => {
    if (id !== selectedRef.current) mainRef.current?.scrollTo({ top: 0 });
    selectedRef.current = id;
    setSelectedId(id);
    if (backend) loadDetail(backend, id);
  };

  const run = async (fn: () => Promise<unknown>, done?: string) => {
    if (!backend) return;
    setBusy(true);
    try {
      await fn();
      if (done) flash(done);
      await refresh(backend);
    } catch (err) {
      flash((err as Error).message, 4000);
    } finally {
      setBusy(false);
    }
  };

  const caseId = detail?.kind === "case" ? detail.case.id : null;
  const onCallback = (r: CallbackResult) => caseId && run(() => backend!.callback(caseId, r, CLERK));
  const onApprove = () => caseId && run(() => backend!.approve(caseId, MANAGER, "manager"));
  const onReject = () => caseId && run(() => backend!.reject(caseId, MANAGER, "manager"));

  // Demo controls are keyboard only: N sends the next scenario email, Shift+R resets.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || busy || !backend) return;
      const t = e.target as HTMLElement;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      if (e.key === "n" || e.key === "N") {
        if (e.shiftKey) return;
        run(() => backend.ingest());
      } else if (e.key === "R" && e.shiftKey) {
        run(async () => {
          await backend.reset();
          known.current = null;
          selectedRef.current = null;
          setSelectedId(null); setDetail(null); setDetailId(null);
        });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const alert = useMemo(() => (caseId ? alerts.find((a) => a.caseId === caseId) ?? null : null), [alerts, caseId]);
  const shown = detail && detailId === selectedId ? detail : null;
  const nextHeld = rows.find((r) => isHeld(r) && r.id !== selectedId)?.id ?? null;

  return (
    <div className="app">
      <header className="top">
        <img className="logo" src="/brand/halberd-horizontal-color.svg" alt="Halberd" height={28} />
        <span className="org">{status?.org || "School District"}</span>
      </header>
      <div className="body">
        <Boundary label="Invoices">
          {loaded ? <Sidebar rows={rows} selectedId={selectedId} fresh={fresh} onSelect={select} /> : <SideSkeleton />}
        </Boundary>
        <main className="main" ref={mainRef}>
          {!loaded ? <MainSkeleton />
            : !shown ? (selectedId && rows.length ? null
              : rows.length ? <div className="calm"><p className="calm-only">Select an invoice.</p></div>
              : (
                <div className="calm">
                  <div className="calm-mark"><Icon name="HalberdMark" size={24} /></div>
                  <p className="calm-title">No invoices yet</p>
                  <p className="calm-sub">Halberd checks each one as it arrives.</p>
                </div>
              ))
            : (
              <div key={selectedId ?? ""} className="enter">
                <Boundary label="This invoice" resetKey={shown}>
                  {shown.kind === "case"
                    ? <CaseMain d={shown} alert={alert} busy={busy} onCallback={onCallback} onApprove={onApprove} onReject={onReject}
                        onNext={nextHeld ? () => select(nextHeld) : null} />
                    : <InvoiceMain d={shown} />}
                </Boundary>
              </div>
            )}
        </main>
      </div>
      {toast && <div className="toast" role="status">{toast}</div>}
    </div>
  );
}

function SideSkeleton() {
  return (
    <div className="side sk-side" aria-hidden>
      {[62, 48, 70, 55, 44].map((w, i) => (
        <div key={i} className="sk-row">
          <span className="sk" style={{ width: `${w}%`, height: 9 }} />
          <span className="sk" style={{ width: `${w - 22}%`, height: 7 }} />
        </div>
      ))}
    </div>
  );
}

function MainSkeleton() {
  return (
    <div className="stack" aria-hidden>
      <div className="sk-head">
        <div style={{ display: "grid", gap: 14, width: "50%" }}>
          <span className="sk" style={{ width: "34%", height: 20 }} />
          <span className="sk" style={{ width: "80%", height: 28 }} />
        </div>
        <span className="sk" style={{ width: "18%", height: 30 }} />
      </div>
      <div className="sk-card" style={{ height: 150 }} />
      <div className="sk-card" style={{ height: 220 }} />
    </div>
  );
}
