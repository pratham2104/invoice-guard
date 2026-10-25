import { useMutation, useQuery } from "@tanstack/react-query";
import { AlertTriangle, Menu } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { api } from "../api";
import { EvidenceInspector } from "../components/EvidenceInspector";
import { useViewport } from "../hooks/useViewport";
import { EvidenceWorkspace } from "./EvidenceWorkspace";
import { IncidentRail } from "./IncidentRail";
import { MobileTimeline } from "./MobileTimeline";
import { PolicyLabWorkspace } from "./PolicyLabWorkspace";
import { AttackCausalityGraph } from "./graph/AttackCausalityGraph";

const DEFAULT_INCIDENT = "fixture-invoice_redirect";
type Workspace = "control" | "policy" | "evidence";

export default function BlacksiteApp() {
  const { isMobile, isTablet } = useViewport();
  const [workspace, setWorkspace] = useState<Workspace>("control");
  const [incidentId, setIncidentId] = useState(DEFAULT_INCIDENT);
  const [selectedNode, setSelectedNode] = useState<string | null>("n-gate");
  const [railOpen, setRailOpen] = useState(!isMobile);
  const [inspectorOpen, setInspectorOpen] = useState(!isMobile);
  const [filter, setFilter] = useState("");

  const statusQ = useQuery({ queryKey: ["status"], queryFn: api.status, refetchInterval: 15_000 });
  const listQ = useQuery({ queryKey: ["incidents"], queryFn: api.incidents, refetchInterval: 30_000 });
  const detailQ = useQuery({
    queryKey: ["incident", incidentId],
    queryFn: () => api.incident(incidentId),
    enabled: Boolean(incidentId),
    refetchInterval: 15_000,
  });
  const replaysQ = useQuery({
    queryKey: ["replays", incidentId],
    queryFn: () => api.replays(incidentId),
    enabled: Boolean(incidentId),
    refetchInterval: 60_000,
  });
  const benchmarksQ = useQuery({
    queryKey: ["benchmarks"],
    queryFn: api.evidenceBenchmarks,
    refetchInterval: 60_000,
  });

  const approvalMut = useMutation({ mutationFn: () => api.approvalRequest(incidentId) });

  const detail = detailQ.data;
  const denied = Boolean(detail?.live_action?.held);
  const selected = detail?.nodes.find((n) => n.id === selectedNode);
  const connected = statusQ.data?.backend_connected !== false;
  const live = connected && (statusQ.data?.mode === "live_verified" || statusQ.data?.mode === "replay");

  const reducedMotion = useMemo(
    () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    [],
  );

  const selectIncident = useCallback(
    (id: string) => {
      setIncidentId(id);
      setSelectedNode("n-gate");
      if (isMobile) setRailOpen(false);
    },
    [isMobile],
  );

  const incidents = (listQ.data?.incidents ?? []).filter(
    (inc) =>
      !filter ||
      inc.title.toLowerCase().includes(filter.toLowerCase()) ||
      inc.id.toLowerCase().includes(filter.toLowerCase()),
  );

  const lastEvent = statusQ.data?.last_seen_at?.slice(11, 19) ?? "—";

  return (
    <div className="min-h-full flex flex-col bg-bg" data-mode={statusQ.data?.mode ?? "live_verified"}>
      <header className="shell-header px-4 py-2.5">
        <div className="flex flex-wrap items-center justify-between gap-3 max-w-[1600px] mx-auto">
          <div className="flex items-center gap-2 min-w-0">
            {(isMobile || isTablet) && (
              <button type="button" className="btn-ghost p-2" aria-label="Incidents" onClick={() => setRailOpen((v) => !v)}>
                <Menu size={16} />
              </button>
            )}
            <div className="min-w-0">
              <h1 className="text-sm font-semibold tracking-tight truncate">
                PHANTOMSHIFT <span className="text-chartreuse font-mono">BLACKSITE</span>
                <span className="text-fg-muted font-normal"> / PAYGUARD</span>
              </h1>
            </div>
          </div>

          <nav className="flex gap-1" aria-label="Workspaces">
            <button
              type="button"
              className={`btn-ghost ${workspace === "control" ? "btn-ghost-active" : ""}`}
              onClick={() => setWorkspace("control")}
            >
              Control
            </button>
            <button
              type="button"
              className={`btn-ghost ${workspace === "policy" ? "btn-ghost-active" : ""}`}
              onClick={() => setWorkspace("policy")}
            >
              Policies
            </button>
            <button
              type="button"
              className={`btn-ghost ${workspace === "evidence" ? "btn-ghost-active" : ""}`}
              onClick={() => setWorkspace("evidence")}
            >
              Evidence
            </button>
          </nav>

          <div className="flex items-center gap-2 text-[10px] font-mono">
            <span data-testid="mode-badge" className={live ? "badge-live" : "badge-demo"}>
              {live ? "LIVE" : "OFFLINE"}
            </span>
            <span className="rounded-md border border-stroke px-2 py-1 text-chartreuse">
              {statusQ.data?.guard_posture ?? (connected ? "ENFORCING" : "DISCONNECTED")}
            </span>
            <span className="text-fg-tertiary hidden sm:inline">Updated {lastEvent} UTC</span>
          </div>
        </div>
      </header>

      {!connected && (
        <div className="denial-banner mx-4 mt-2 max-w-[1600px] md:mx-auto" role="alert">
          <AlertTriangle size={16} />
          Cannot reach PHANTOMSHIFT server — start with <code className="mx-1">python3 -m phantomshift</code>
        </div>
      )}

      <main id="main" className="flex-1 max-w-[1600px] w-full mx-auto p-3 min-h-0 flex flex-col">
        {workspace === "control" && (
          <div className="flex-1 grid grid-cols-1 xl:grid-cols-[220px_1fr_300px] gap-3 min-h-[calc(100vh-7rem)]">
            {(!isMobile || railOpen) && (
              <IncidentRail
                incidents={incidents}
                selectedId={incidentId}
                filter={filter}
                onFilter={setFilter}
                onSelect={selectIncident}
              />
            )}

            <section className="panel flex flex-col min-h-0 min-w-0">
              <div className="panel-head py-2">
                <h2 className="panel-title normal-case tracking-normal text-fg text-xs font-medium">
                  {detail?.title ?? "Incident trace"}
                </h2>
                {isMobile && (
                  <button type="button" className="btn-ghost text-[10px]" onClick={() => setInspectorOpen(true)}>
                    Evidence
                  </button>
                )}
              </div>
              <div className="flex-1 flex flex-col p-2 min-h-0">
                {detailQ.isLoading && <p className="text-sm text-fg-muted p-4">Loading…</p>}
                {detail && (
                  <>
                    {isMobile ? (
                      <MobileTimeline
                        nodes={detail.nodes}
                        selectedId={selectedNode}
                        onSelect={setSelectedNode}
                        denied={denied}
                      />
                    ) : (
                      <AttackCausalityGraph
                        nodes={detail.nodes}
                        edges={detail.edges}
                        selectedId={selectedNode}
                        onSelect={setSelectedNode}
                        denied={denied}
                        motion={!reducedMotion}
                      />
                    )}
                    {denied && (
                      <p className="text-xs text-coral font-medium mt-2 px-1" role="status">
                        Blocked at trust boundary — payment not executed
                      </p>
                    )}
                  </>
                )}
              </div>
            </section>

            {!isMobile ? (
              <aside className="panel flex flex-col min-h-0 overflow-hidden">
                <div className="panel-head py-2">
                  <h2 className="panel-title">Evidence</h2>
                </div>
                <div className="p-3 overflow-auto flex-1 text-sm">
                  {detail ? (
                    <EvidenceInspector
                      detail={detail}
                      selected={selected}
                      onRequestApproval={() => approvalMut.mutate()}
                      approvalPending={approvalMut.isPending}
                      approvalData={approvalMut.data}
                    />
                  ) : (
                    <p className="text-fg-muted">Select an incident</p>
                  )}
                </div>
              </aside>
            ) : (
              inspectorOpen &&
              detail && (
                <div className="fixed inset-0 z-50 bg-black/75 flex justify-end" role="dialog" aria-modal="true">
                  <div className="panel w-full max-w-sm h-full border-l rounded-none overflow-auto">
                    <div className="panel-head">
                      <h2 className="panel-title">Evidence</h2>
                      <button type="button" className="btn-ghost" onClick={() => setInspectorOpen(false)}>
                        Close
                      </button>
                    </div>
                    <div className="p-3">
                      <EvidenceInspector
                        detail={detail}
                        selected={selected}
                        onRequestApproval={() => approvalMut.mutate()}
                        approvalPending={approvalMut.isPending}
                        approvalData={approvalMut.data}
                      />
                    </div>
                  </div>
                </div>
              )
            )}
          </div>
        )}

        {workspace === "policy" && (
          <div className="panel flex-1 min-h-[480px] overflow-hidden">
            <PolicyLabWorkspace
              detail={detail}
              replays={replaysQ.data?.replays ?? []}
              loading={replaysQ.isLoading}
            />
          </div>
        )}

        {workspace === "evidence" && (
          <div className="panel flex-1 min-h-[480px] overflow-hidden flex flex-col">
            <EvidenceWorkspace
              incidents={listQ.data?.incidents ?? []}
              benchmarks={benchmarksQ.data}
            />
          </div>
        )}
      </main>
    </div>
  );
}
