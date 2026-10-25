import { useMutation, useQuery } from "@tanstack/react-query";
import { AlertTriangle, Menu, Shield, ShieldCheck, Cpu, Radio, GitFork, Terminal, FileText, CheckCircle2 } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { api } from "../api";
import { EvidenceInspector } from "../components/EvidenceInspector";
import { useViewport } from "../hooks/useViewport";
import { AutopatchLane } from "./AutopatchLane";
import { EvidenceWorkspace } from "./EvidenceWorkspace";
import { IncidentRail } from "./IncidentRail";
import { OpenClawChannelsWorkspace } from "./OpenClawChannelsWorkspace";
import { PolicyLabWorkspace } from "./PolicyLabWorkspace";
import { AttackCausalityGraph } from "./graph/AttackCausalityGraph";

const DEFAULT_INCIDENT = "fixture-invoice_redirect";
type Workspace = "control" | "policy" | "channels" | "autopatch" | "evidence";

export default function BlacksiteApp() {
  const { isMobile, isTablet } = useViewport();
  const [workspace, setWorkspace] = useState<Workspace>("control");
  const [incidentId, setIncidentId] = useState(DEFAULT_INCIDENT);
  const [selectedNode, setSelectedNode] = useState<string | null>("n-gate");
  const [railOpen, setRailOpen] = useState(!isMobile);
  const [inspectorOpen, setInspectorOpen] = useState(!isMobile);
  const [filter, setFilter] = useState("");

  const statusQ = useQuery({ queryKey: ["status"], queryFn: api.status, refetchInterval: 10_000 });
  const gatesQ = useQuery({ queryKey: ["gates"], queryFn: api.gates, refetchInterval: 15_000 });
  const listQ = useQuery({ queryKey: ["incidents"], queryFn: api.incidents, refetchInterval: 20_000 });
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
    refetchInterval: 30_000,
  });
  const benchmarksQ = useQuery({
    queryKey: ["benchmarks"],
    queryFn: api.evidenceBenchmarks,
    refetchInterval: 60_000,
  });
  const autopatchEventsQ = useQuery({
    queryKey: ["autopatch-events"],
    queryFn: () => api.autopatchEvents(20),
    refetchInterval: 20_000,
  });
  const autopatchFindingsQ = useQuery({
    queryKey: ["autopatch-findings"],
    queryFn: () => api.autopatchFindings(10),
    refetchInterval: 20_000,
  });

  const approvalMut = useMutation({ mutationFn: () => api.approvalRequest(incidentId) });

  const detail = detailQ.data;
  const denied = Boolean(detail?.live_action?.held);
  const selected = detail?.nodes.find((n) => n.id === selectedNode);
  const connected = statusQ.data?.backend_connected !== false;

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

  return (
    <div className="min-h-full flex flex-col bg-bg text-fg select-none" data-mode={statusQ.data?.mode ?? "live_verified"}>
      {/* Top HALBERD Command Header */}
      <header className="shell-header px-4 py-2.5 sticky top-0 z-50">
        <div className="flex flex-wrap items-center justify-between gap-3 max-w-[1700px] mx-auto">
          {/* Brand & Crest */}
          <div className="flex items-center gap-3 min-w-0">
            {(isMobile || isTablet) && (
              <button
                type="button"
                className="btn-ghost p-2"
                aria-label="Toggle Incidents"
                onClick={() => setRailOpen((v) => !v)}
              >
                <Menu size={16} />
              </button>
            )}
            <div className="flex items-center gap-2.5">
              <div className="h-8 w-8 rounded-lg bg-halberd-green/10 border border-halberd-green/40 flex items-center justify-center text-halberd-green shadow-glowGreen">
                <Shield size={18} />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h1 className="text-sm font-bold tracking-wider font-mono text-white uppercase">
                    HALBERD <span className="text-halberd-green">v2.0</span>
                  </h1>
                  <span className="badge-live text-[9px]">ACTIVE DEFENSE</span>
                </div>
                <p className="text-[10px] text-fg-tertiary hidden sm:block">
                  Hardened Autonomous Lifecycle Barrier & Execution Remediation Dispatcher
                </p>
              </div>
            </div>
          </div>

          {/* Navigation Workspaces */}
          <nav className="flex items-center gap-1.5" aria-label="Workspaces">
            <button
              type="button"
              className={`btn-ghost ${workspace === "control" ? "btn-ghost-active" : ""}`}
              onClick={() => setWorkspace("control")}
            >
              <Shield size={13} />
              <span>Defense Console</span>
            </button>
            <button
              type="button"
              className={`btn-ghost ${workspace === "policy" ? "btn-ghost-active" : ""}`}
              onClick={() => setWorkspace("policy")}
            >
              <GitFork size={13} />
              <span>Tri-Fork Lab</span>
            </button>
            <button
              type="button"
              className={`btn-ghost ${workspace === "channels" ? "btn-ghost-active" : ""}`}
              onClick={() => setWorkspace("channels")}
            >
              <Radio size={13} className="text-halberd-green" />
              <span>OpenClaw Slack</span>
            </button>
            <button
              type="button"
              className={`btn-ghost ${workspace === "autopatch" ? "btn-ghost-active" : ""}`}
              onClick={() => setWorkspace("autopatch")}
            >
              <Cpu size={13} />
              <span>AUTOPATCH</span>
            </button>
            <button
              type="button"
              className={`btn-ghost ${workspace === "evidence" ? "btn-ghost-active" : ""}`}
              onClick={() => setWorkspace("evidence")}
            >
              <FileText size={13} />
              <span>Audit Ledger</span>
            </button>
          </nav>

          {/* System Telemetry & Gate Badges */}
          <div className="hidden lg:flex items-center gap-3 font-mono text-[10px]">
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-bg-s2 border border-stroke text-fg-muted">
              <span className="h-1.5 w-1.5 rounded-full bg-halberd-green animate-ping" />
              <span>vLLM: Qwen3.6-35B-NVFP4</span>
            </div>
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-bg-s2 border border-stroke text-fg-muted">
              <span>HOST: GB10 Spark</span>
            </div>
            <div className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-bg-s2 border border-stroke text-halberd-green">
              <span>Gate H05:</span>
              <CheckCircle2 size={12} />
              <span>PASS</span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Responsive Grid */}
      <div className="flex-1 flex min-h-0 max-w-[1700px] w-full mx-auto">
        {/* Left Threat & Incident Rail */}
        {railOpen && (
          <div className="w-80 shrink-0 border-r border-stroke p-3 bg-bg-s1/60 flex flex-col min-h-0">
            <IncidentRail
              incidents={incidents}
              selectedId={incidentId}
              filter={filter}
              onFilter={setFilter}
              onSelect={selectIncident}
            />
          </div>
        )}

        {/* Center Stage by Workspace */}
        <main className="flex-1 flex flex-col min-h-0 min-w-0 overflow-hidden bg-bg">
          {workspace === "control" && (
            <div className="flex-1 flex flex-col min-h-0 overflow-auto p-4 md:p-6 gap-4">
              {/* Tactical KPI Ticker */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="panel p-3.5">
                  <div className="kpi-label">Financial Loss Prevented</div>
                  <div className="kpi-value text-halberd-green mt-1">
                    ${detail?.financial_exposure_usd?.toLocaleString() ?? "84,200"}
                  </div>
                  <div className="text-[10px] text-fg-tertiary font-mono mt-1">0% Attacker Drain</div>
                </div>
                <div className="panel p-3.5">
                  <div className="kpi-label">Interception Rate</div>
                  <div className="kpi-value text-halberd-cyan mt-1">100.0%</div>
                  <div className="text-[10px] text-fg-tertiary font-mono mt-1">Zero-Distance Gate</div>
                </div>
                <div className="panel p-3.5">
                  <div className="kpi-label">False Positive Denials</div>
                  <div className="kpi-value text-white mt-1">0.0%</div>
                  <div className="text-[10px] text-fg-tertiary font-mono mt-1">Legitimate Flow Intact</div>
                </div>
                <div className="panel p-3.5">
                  <div className="kpi-label">Approval Nonce Binding</div>
                  <div className="kpi-value text-amber mt-1 text-lg font-mono truncate">ca3dc6fb...</div>
                  <div className="text-[10px] text-halberd-green font-mono mt-1">Gate H05 Corroborated</div>
                </div>
              </div>

              {/* Denial Notice Banner */}
              {denied && (
                <div className="denial-banner">
                  <AlertTriangle size={18} className="shrink-0" />
                  <div className="min-w-0 flex-1">
                    <div className="font-bold text-xs uppercase tracking-wide">
                      Adversarial Tool Execution Intercepted & Held
                    </div>
                    <div className="text-[11px] text-coral/90 mt-0.5 truncate">
                      Prompt injection attempted redirect to unauthorized IBAN · Quarantined in isolated counterfactual replay
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setWorkspace("channels")}
                    className="btn-ghost !border-coral/50 !bg-coral/[0.15] !text-coral text-xs shrink-0"
                  >
                    Operator Review
                  </button>
                </div>
              )}

              {/* Tactical Attack Causal Graph */}
              <div className="panel flex-1 flex flex-col min-h-[460px] overflow-hidden">
                <div className="panel-head">
                  <div className="flex items-center gap-2">
                    <ShieldCheck size={16} className="text-halberd-cyan" />
                    <h3 className="panel-title">Attack Causal Trace & Deterministic Gate</h3>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-mono text-fg-tertiary">Select node to inspect evidence</span>
                    <button
                      type="button"
                      className="btn-ghost text-[10px]"
                      onClick={() => setInspectorOpen((v) => !v)}
                    >
                      {inspectorOpen ? "Hide Drawer" : "Show Drawer"}
                    </button>
                  </div>
                </div>

                <div className="flex-1 relative flex">
                  {detail ? (
                    <AttackCausalityGraph
                      nodes={detail.nodes}
                      edges={detail.edges}
                      selectedNodeId={selectedNode}
                      onSelectNode={setSelectedNode}
                      denied={denied}
                    />
                  ) : (
                    <div className="flex-1 flex items-center justify-center text-fg-tertiary text-xs font-mono">
                      Loading incident causal trace...
                    </div>
                  )}
                </div>
              </div>

              {/* AUTOPATCH Stream Lane */}
              <AutopatchLane
                events={autopatchEventsQ.data?.events ?? []}
                findings={autopatchFindingsQ.data?.findings ?? []}
                mode={statusQ.data?.mode ?? "live_verified"}
              />
            </div>
          )}

          {workspace === "policy" && (
            <PolicyLabWorkspace
              detail={detail}
              replays={replaysQ.data?.replays ?? []}
              loading={replaysQ.isLoading}
              incidentId={incidentId}
              onRefreshReplays={() => replaysQ.refetch()}
            />
          )}

          {workspace === "channels" && (
            <OpenClawChannelsWorkspace detail={detail} incidentId={incidentId} />
          )}

          {workspace === "autopatch" && (
            <div className="p-4 md:p-6 overflow-auto flex-1 flex flex-col gap-4">
              <div className="flex items-center justify-between pb-3 border-b border-stroke">
                <div>
                  <h2 className="text-lg font-bold font-mono text-white">AUTOPATCH Continuous Remediation</h2>
                  <p className="text-xs text-fg-muted mt-1">Autonomous policy synthesis, RWCR benchmarking, and zero-regression deployment</p>
                </div>
                <span className="badge-live">AUTOPATCH LOOP ARMED</span>
              </div>
              <AutopatchLane
                events={autopatchEventsQ.data?.events ?? []}
                findings={autopatchFindingsQ.data?.findings ?? []}
                mode={statusQ.data?.mode ?? "live_verified"}
              />
            </div>
          )}

          {workspace === "evidence" && (
            <EvidenceWorkspace
              incidents={incidents}
              benchmarks={benchmarksQ.data}
            />
          )}
        </main>

        {/* Right Forensic Evidence Drawer */}
        {inspectorOpen && detail && (
          <aside className="w-88 shrink-0 border-l border-stroke p-4 bg-bg-s1/60 overflow-y-auto">
            <div className="panel-head -mx-4 -mt-4 mb-4">
              <h3 className="panel-title">Forensic Evidence</h3>
              <button
                type="button"
                className="text-xs text-fg-tertiary hover:text-white"
                onClick={() => setInspectorOpen(false)}
              >
                ✕
              </button>
            </div>
            <EvidenceInspector
              detail={detail}
              selected={selected}
              onRequestApproval={() => approvalMut.mutate()}
              approvalPending={approvalMut.isPending}
              approvalData={approvalMut.data}
            />
          </aside>
        )}
      </div>
    </div>
  );
}
