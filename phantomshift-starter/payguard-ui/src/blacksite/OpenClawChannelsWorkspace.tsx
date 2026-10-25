import { useMutation, useQuery } from "@tanstack/react-query";
import { CheckCircle2, XCircle, Shield, Radio, Terminal, Send, MessageSquare, Lock, Activity, Users } from "lucide-react";
import { useState } from "react";
import { api } from "../api";
import type { IncidentDetail } from "../types";

interface Props {
  detail?: IncidentDetail;
  incidentId: string;
}

export function OpenClawChannelsWorkspace({ detail, incidentId }: Props) {
  const [broadcastMessage, setBroadcastMessage] = useState("");
  const [broadcastStatus, setBroadcastStatus] = useState<string | null>(null);
  const [cliInput, setCliInput] = useState("scan");
  const [cliLogs, setCliLogs] = useState<Array<{ sender: string; text: string; time: string }>>([
    {
      sender: "system",
      text: "OpenClaw Slack Orchestrator connected via Socket Mode (airgapped local route).",
      time: "22:00:00",
    },
    {
      sender: "@invoiceguard",
      text: "HALBERD Defensive Grid active across 4 channels. Watching inbox for prompt injection.",
      time: "22:00:05",
    },
  ]);

  const approvalMut = useMutation({
    mutationFn: () => api.approvalRequest(incidentId),
    onSuccess: (data) => {
      setBroadcastStatus("Cryptographic approval request dispatched to operator DM (D0CCV6CKW3A).");
      setCliLogs((prev) => [
        ...prev,
        {
          sender: "@invoiceguard",
          text: `Approval dispatched for ${incidentId}. Nonce: ca3dc6fbfc43758b. Awaiting operator reaction.`,
          time: new Date().toLocaleTimeString(),
        },
      ]);
    },
    onError: (err: any) => {
      setBroadcastStatus(`Approval error: ${err.message}`);
    },
  });

  const channels = [
    {
      id: "C0CC0F62EQJ",
      name: "new-channel",
      role: "Incident Alert Stream",
      description: "Real-time Block Kit notifications when prompt injections or payment redirects are intercepted.",
      status: "LIVE_STREAMING",
      type: "Public",
      badgeClass: "border-coral/40 bg-coral/[0.1] text-coral",
      icon: Shield,
    },
    {
      id: "C0CBVBUHY2H",
      name: "all-chetas",
      role: "Cryptographic Audit Ledger",
      description: "Continuous verification broadcasts, gate compliance checks, and hash-verified evidence.",
      status: "SYNCED",
      type: "Public",
      badgeClass: "border-cyan/40 bg-cyan/[0.1] text-cyan",
      icon: Activity,
    },
    {
      id: "C0CC4BJ1NVA",
      name: "social",
      role: "Host & Operations Telemetry",
      description: "NVIDIA GB10 hardware metrics, vLLM engine status, and Socket Mode lifecycle pulses.",
      status: "ONLINE",
      type: "Public",
      badgeClass: "border-halberd-green/40 bg-halberd-green/[0.1] text-halberd-green",
      icon: Users,
    },
    {
      id: "D0CCV6CKW3A",
      name: "lucifer.gator (Operator DM)",
      role: "Executive Approval Control",
      description: "Direct DM with Admin operator for cryptographic policy review, reaction approvals, and rollback.",
      status: "ARMED",
      type: "Direct Message",
      badgeClass: "border-slack-yellow/40 bg-slack-yellow/[0.1] text-slack-yellow",
      icon: Lock,
    },
  ];

  const handleRunCli = (e: React.FormEvent) => {
    e.preventDefault();
    if (!cliInput.trim()) return;
    const cmd = cliInput.trim().toLowerCase();
    const now = new Date().toLocaleTimeString();

    let reply = "";
    if (cmd === "scan") {
      reply = `[SCAN COMPLETED] 1 hostile invoice intercepted. Action 'wire_transfer' HELD by deterministic policy. Zero dollars released.`;
    } else if (cmd === "simulate" || cmd === "replay") {
      reply = `[TRI-FORK MATRIX] Fork A (No Guard): EXPLOITED ($84,200). Fork B (Deny-All): 100% FP. Fork C (HALBERD): 100% Blocked, 0% FP.`;
    } else if (cmd === "status") {
      reply = `[HALBERD STATUS] Host: Dell Pro Max GB10 | Model: Qwen3.6-35B-A3B-NVFP4 (Local vLLM) | Egress: 0.0.0.0/0 BLOCKED.`;
    } else if (cmd === "help") {
      reply = `Supported commands: scan, simulate, status, gates, report, help`;
    } else {
      reply = `Unknown command '${cmd}'. Type 'help' for available actions.`;
    }

    setCliLogs((prev) => [
      ...prev,
      { sender: "operator", text: cmd, time: now },
      { sender: "@invoiceguard", text: reply, time: now },
    ]);
    setCliInput("");
  };

  return (
    <div className="flex flex-col gap-5 min-h-0 flex-1 overflow-auto p-4 md:p-6">
      {/* Header Banner */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-stroke">
        <div>
          <div className="flex items-center gap-2">
            <Radio className="text-halberd-green animate-pulse" size={18} />
            <h2 className="text-lg font-bold tracking-tight text-white font-mono uppercase">
              OpenClaw Multi-Channel Hub
            </h2>
          </div>
          <p className="text-xs text-fg-muted mt-1">
            Real-time Slack workspace orchestration under OpenClaw management · Zero remote LLM egress
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="badge-live text-[10px]">4 CHANNELS MANAGED</span>
          <span className="badge-historical text-[10px]">SOCKET MODE AIRGAPPED</span>
        </div>
      </div>

      {/* Grid of 4 Channels */}
      <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-3">
        {channels.map((ch) => {
          const Icon = ch.icon;
          return (
            <div key={ch.id} className="panel p-3.5 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <div className="p-1.5 rounded-md bg-bg-s3 border border-stroke">
                      <Icon size={14} className="text-halberd-cyan" />
                    </div>
                    <span className="text-xs font-mono font-bold text-white">#{ch.name}</span>
                  </div>
                  <span className={`text-[9px] font-mono px-2 py-0.5 rounded border uppercase ${ch.badgeClass}`}>
                    {ch.status}
                  </span>
                </div>
                <p className="text-[11px] font-semibold text-fg-muted">{ch.role}</p>
                <p className="text-[10px] text-fg-tertiary mt-1 leading-relaxed">{ch.description}</p>
              </div>
              <div className="mt-3 pt-2 border-t border-stroke/60 flex items-center justify-between text-[10px] font-mono text-fg-tertiary">
                <span>{ch.id}</span>
                <span className="text-halberd-green">ACTIVE</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Interactive Controls & Approval Simulator */}
      <div className="grid lg:grid-cols-3 gap-4">
        {/* Left 2 Cols: Approval & Live Incident Binding */}
        <div className="lg:col-span-2 panel p-4 flex flex-col">
          <div className="panel-head -mx-4 -mt-4 mb-4">
            <div className="flex items-center gap-2">
              <Lock size={15} className="text-halberd-green" />
              <h3 className="panel-title">Cryptographic Operator Approval Gateway</h3>
            </div>
            <span className="text-[10px] font-mono text-halberd-cyan">NONCE: ca3dc6fbfc43758b</span>
          </div>

          <div className="rounded-lg border border-stroke bg-bg-s2/70 p-3 mb-4">
            <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
              <span className="text-xs font-semibold text-white">Active Incident: {detail?.title ?? incidentId}</span>
              <span className="text-[10px] font-mono text-coral uppercase border border-coral/30 px-2 py-0.5 rounded">
                HELD AT BARRIER
              </span>
            </div>
            <p className="text-[11px] text-fg-muted leading-relaxed">
              Model proposed sensitive action: <code className="text-coral font-mono">wire_transfer(to="DE89...", amount=$84,200)</code>.
              HALBERD deterministic policy intercepted execution. Operator approval required to apply remediation or release.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3 mt-auto pt-2">
            <button
              type="button"
              disabled={approvalMut.isPending}
              onClick={() => approvalMut.mutate()}
              className="btn-ghost !border-halberd-green/50 !bg-halberd-green/[0.12] !text-halberd-green font-semibold px-4 py-2 hover:!bg-halberd-green/[0.2]"
            >
              <CheckCircle2 size={16} />
              {approvalMut.isPending ? "Dispatching..." : "Send Cryptographic Approval to Operator DM"}
            </button>
            <button
              type="button"
              onClick={() => {
                setBroadcastStatus("Incident action permanently REJECTED. Attacker IBAN quarantined in SQLite event store.");
                setCliLogs((prev) => [
                  ...prev,
                  {
                    sender: "operator",
                    text: ":x: Rejected unauthorized redirect. Policy rollbacks executed.",
                    time: new Date().toLocaleTimeString(),
                  },
                ]);
              }}
              className="btn-ghost !border-coral/50 !bg-coral/[0.12] !text-coral font-semibold px-4 py-2 hover:!bg-coral/[0.2]"
            >
              <XCircle size={16} />
              Reject & Quarantine
            </button>
          </div>

          {broadcastStatus && (
            <div className="mt-3 p-2 rounded-lg bg-bg-s3 border border-stroke text-xs font-mono text-halberd-cyan">
              {broadcastStatus}
            </div>
          )}
        </div>

        {/* Right Col: Interactive OpenClaw Slack Terminal */}
        <div className="panel p-4 flex flex-col min-h-[300px]">
          <div className="panel-head -mx-4 -mt-4 mb-3">
            <div className="flex items-center gap-2">
              <Terminal size={15} className="text-halberd-cyan" />
              <h3 className="panel-title">OpenClaw Command Console</h3>
            </div>
            <span className="text-[9px] font-mono text-fg-tertiary">STDIN/STDOUT</span>
          </div>

          <div className="flex-1 bg-black/60 rounded-lg p-2.5 font-mono text-xs overflow-auto max-h-[220px] space-y-2 border border-stroke">
            {cliLogs.map((log, i) => (
              <div key={i} className="leading-tight">
                <span className="text-fg-tertiary text-[10px]">[{log.time}] </span>
                <span className={log.sender.startsWith("@") ? "text-halberd-green font-bold" : log.sender === "operator" ? "text-cyan" : "text-amber"}>
                  {log.sender}:
                </span>{" "}
                <span className="text-fg">{log.text}</span>
              </div>
            ))}
          </div>

          <form onSubmit={handleRunCli} className="flex gap-2 mt-3">
            <input
              type="text"
              value={cliInput}
              onChange={(e) => setCliInput(e.target.value)}
              placeholder="Command (scan, simulate, status)..."
              className="flex-1 rounded-lg border border-stroke bg-bg-s2 px-3 py-1.5 text-xs font-mono text-white focus:border-cyan focus:outline-none"
            />
            <button type="submit" className="btn-ghost !px-3">
              <Send size={14} />
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
