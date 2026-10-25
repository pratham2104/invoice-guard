import { useEffect, useState } from "react";
import type { InvoiceRow } from "../types";
import { Icon, type IconName } from "../ui/Icon";
import { money } from "../format";
import { dateLabel, invoiceLabel } from "../copy";
import { RiskDot } from "../ui/RiskDot";

const open = (r: InvoiceRow) => r.kind === "case" && r.state !== "APPROVED" && r.state !== "REJECTED";

export function Sidebar({ rows, selectedId, fresh, onSelect }: {
  rows: InvoiceRow[]; selectedId: string | null; fresh: Set<string>; onSelect: (id: string) => void;
}) {
  const held = rows.filter(open);
  const stopped = rows.filter((r) => r.kind === "case" && r.state === "REJECTED");
  const cleared = rows.filter((r) => !open(r) && !(r.kind === "case" && r.state === "REJECTED"));
  return (
    <nav className="side" aria-label="Invoices">
      {rows.length === 0 && <div className="side-empty">No invoices yet.</div>}
      <Section title="Held" kind="held" icon="Alert" word="held" rows={held} selectedId={selectedId} fresh={fresh} onSelect={onSelect} risky />
      <Section title="Stopped" kind="stopped" icon="Cross" word="stopped" rows={stopped} selectedId={selectedId} fresh={fresh} onSelect={onSelect} />
      <Section title="Cleared" kind="cleared" icon="Check" word="paid" rows={cleared} selectedId={selectedId} fresh={fresh} onSelect={onSelect} />
    </nav>
  );
}

const VISIBLE = 5;

function Section({ title, kind, icon, word, rows, selectedId, fresh, onSelect, risky }: {
  title: string; kind: string; icon: IconName; word: string; rows: InvoiceRow[]; selectedId: string | null; fresh: Set<string>;
  onSelect: (id: string) => void; risky?: boolean;
}) {
  const [all, setAll] = useState(false);
  const fold = kind === "cleared" && rows.length > VISIBLE;
  const head = fold ? rows.slice(0, VISIBLE) : rows;
  const rest = fold ? rows.slice(VISIBLE) : [];
  // If the selected invoice is in the folded part, show it.
  useEffect(() => {
    if (fold && selectedId && rest.some((r) => r.id === selectedId)) setAll(true);
  }, [selectedId]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!rows.length) return null;

  const row = (r: InvoiceRow) => {
    const tone = risky ? (r.risk === "fraud" ? "fraud" : r.risk === "confirm" ? "confirm" : "") : "";
    return (
      <button key={r.id} className={`srow${r.id === selectedId ? " on" : ""}${fresh.has(r.id) ? " fresh" : ""}`}
        onClick={() => onSelect(r.id)} aria-current={r.id === selectedId}>
        <span className="srow-main">
          <span className="srow-name">{r.vendorName ?? "Unknown sender"}</span>
          <span className="srow-sub">{invoiceLabel(r.invoiceNumber)} · {dateLabel(r.date)}</span>
        </span>
        <span className={`srow-amt ${tone}`}>
          {tone && <RiskDot size={16} />}
          {r.amount != null ? <span className="num">{money(r.amount)}</span> : <span className="srow-bank">Bank change</span>}
        </span>
      </button>
    );
  };

  return (
    <section className={`side-sec ${kind}`}>
      <div className="band">
        {kind === "held" ? <RiskDot size={18} /> : <Icon name={icon} size={16} />}
        <span className="band-title">{title}</span>
        <span className="band-count" key={rows.length}>{rows.length}</span>
        <span className="band-total num">{money(rows.reduce((t, r) => t + (r.amount ?? 0), 0), false)} {word}</span>
      </div>
      <div className="side-rows">
        {head.map(row)}
        {fold && (
          <>
            <div className={`more${all ? " open" : ""}`}>
              <div className="more-in" inert={!all}>{rest.map(row)}</div>
            </div>
            <button className="more-link" onClick={() => setAll((v) => !v)} aria-expanded={all}>
              {all ? "Show fewer" : `${rest.length} more`}
            </button>
          </>
        )}
      </div>
    </section>
  );
}
