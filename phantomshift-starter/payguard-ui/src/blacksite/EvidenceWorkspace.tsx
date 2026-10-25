import type { BenchmarkPack, IncidentSummary } from "../api";

interface Props {
  incidents: IncidentSummary[];
  benchmarks?: BenchmarkPack;
}

export function EvidenceWorkspace({ incidents, benchmarks }: Props) {
  const model = benchmarks?.model_development;
  const baselines = benchmarks?.policy_baselines ?? [];

  return (
    <div className="flex flex-col gap-4 p-4 overflow-auto flex-1">
      <div>
        <h2 className="text-lg font-semibold">Evidence & benchmarks</h2>
        <p className="text-xs text-fg-muted mt-1">Receipts, provenance, and honestly labeled measurements</p>
      </div>

      <section className="panel p-4">
        <h3 className="panel-title mb-3">Incidents</h3>
        <div className="overflow-auto">
          <table className="w-full text-xs text-left">
            <thead className="text-fg-muted uppercase text-[10px]">
              <tr>
                <th className="py-2 pr-3">ID</th>
                <th className="py-2 pr-3">Mode</th>
                <th className="py-2 pr-3">Status</th>
                <th className="py-2">Exposure</th>
              </tr>
            </thead>
            <tbody>
              {incidents.map((i) => (
                <tr key={i.id} className="border-t border-stroke/60">
                  <td className="py-2 pr-3 font-mono">{i.id}</td>
                  <td className="py-2 pr-3">
                    <span className="badge-demo text-[9px]">{i.mode}</span>
                  </td>
                  <td className="py-2 pr-3">{i.status}</td>
                  <td className="py-2">
                    {i.financial_exposure_usd ? `$${i.financial_exposure_usd} synthetic` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel p-4">
        <div className="flex items-center gap-2 mb-3">
          <h3 className="panel-title">Policy baselines (held-out)</h3>
          <span className="badge-historical">historical_benchmark</span>
        </div>
        <ul className="space-y-2 text-xs font-mono">
          {baselines.map((b) => (
            <li key={b.id} className="rounded-lg border border-stroke bg-bg-s2/60 p-2">
              {b.label}: attack {b.attack_k}/{b.attack_n} · legit {b.legit_k}/{b.legit_n}
            </li>
          ))}
        </ul>
      </section>

      {model && (
        <section className="panel p-4 border-amber/20">
          <div className="flex flex-wrap gap-2 mb-2">
            <h3 className="panel-title">Model development sample</h3>
            <span className="badge-historical">{model.label}</span>
          </div>
          <p className="text-xs text-fg-muted mb-2">{model.model} · {model.replay_mode}</p>
          <ul className="text-xs font-mono space-y-1">
            <li>Unguarded attack success: {model.unguarded_attack_success.k}/{model.unguarded_attack_success.n}</li>
            <li>Context-bound attack success: {model.context_bound_attack_success.k}/{model.context_bound_attack_success.n} (Wilson upper ≈11% at 0/30)</li>
            <li>Legit completion (baseline & guard): {model.legit_completion_baseline_and_guard.k}/{model.legit_completion_baseline_and_guard.n}</li>
          </ul>
          <p className="text-[10px] text-amber mt-3">See {benchmarks?.claims_doc} — not live GB10 proof.</p>
        </section>
      )}
    </div>
  );
}
