interface Props {
  roi: Record<string, unknown> | undefined;
}

export function RoiIllustrativePanel({ roi }: Props) {
  if (!roi) return null;
  const m = roi as Record<string, number>;
  const hours =
    (m.monthly_invoice_count * m.exception_rate * m.minutes_saved_per_review) / 60;
  const gross = hours * m.analyst_hourly_cost_usd;
  const net = gross - m.hypothetical_monthly_price_usd;
  return (
    <div className="mt-2 rounded border border-warn/30 bg-warn/5 p-2 text-xs">
      <div className="font-mono text-warn uppercase text-[10px] mb-1">Illustrative ROI model — not measured savings</div>
      <dl className="grid grid-cols-2 gap-x-2 gap-y-1 font-mono text-[11px]">
        <dt className="text-ink-secondary">Hours saved / mo</dt>
        <dd>{hours.toFixed(1)}</dd>
        <dt className="text-ink-secondary">Gross labor value</dt>
        <dd>${gross.toLocaleString()}</dd>
        <dt className="text-ink-secondary">Net (after $1.5k price)</dt>
        <dd>${net.toLocaleString()}</dd>
      </dl>
    </div>
  );
}
