import type { ReactNode } from "react";
import type { InvoiceView } from "../types";
import { money } from "../format";
import { invoiceLabel, longDate } from "../copy";
import { Icon } from "../ui/Icon";

const norm = (v: unknown) => String(v ?? "").trim().toLowerCase();

function F({ on, tone, children }: { on: boolean; tone: string; children: ReactNode }) {
  return <span className={`fld${on ? ` chg ${tone}` : ""}`}>{children}</span>;
}

/** One invoice as a clean paper card. With `against`, fields that differ get a thin risk outline. */
export function Paper({ inv, against, tone = "fraud", caption, hidden, big }: {
  inv: InvoiceView; against?: InvoiceView | null; tone?: string; caption: string; hidden?: string | null; big?: boolean;
}) {
  const ch = (k: keyof InvoiceView) => !!against && norm(inv[k]) !== norm(against[k]);
  const showPo = !!against && ch("poNumber");
  return (
    <div className={`paper-wrap${big ? " big" : ""}`}>
      {(caption || inv.pdfUrl) && (
        <div className="paper-cap">
          <span>{caption}</span>
          {inv.pdfUrl && <a className="pdf" href={inv.pdfUrl} target="_blank" rel="noreferrer">View PDF<Icon name="External" size={12} /></a>}
        </div>
      )}
      <div className="paper">
        <div className="paper-head">
          <span className="paper-no">{invoiceLabel(inv.invoiceNumber)}</span>
          <span className="muted">{longDate(inv.invoiceDate)}</span>
        </div>
        {showPo && (
          <div className="paper-po"><span className="muted">Purchase order</span><F on tone={tone}>{inv.poNumber ?? "None"}</F></div>
        )}
        <div className="paper-lines">
          {inv.lines.slice(0, 6).map((ln) => (
            <div key={ln.lineNo} className="pl">
              <span className="pl-d">{ln.description}</span>
              <span className="num pl-a">{money(ln.amount)}</span>
            </div>
          ))}
          {inv.lines.length > 6 && <div className="pl muted">{inv.lines.length - 6} more items</div>}
        </div>
        <div className="paper-total">
          <span>Total</span>
          <F on={ch("amount")} tone={tone}><span className="num">{money(inv.amount)}</span></F>
        </div>
        <div className="payto">
          <div className="pt"><span className="muted">Bank</span><F on={ch("bankName")} tone={tone}>{inv.bankName ?? "—"}</F></div>
          <div className="pt"><span className="muted">Account</span><F on={ch("accountLast4")} tone={tone}><span className="dots">••</span><span className="num">{inv.accountLast4 ?? "—"}</span></F></div>
          <div className="pt"><span className="muted">Routing</span><F on={ch("routingLast4")} tone={tone}><span className="dots">••</span><span className="num">{inv.routingLast4 ?? "—"}</span></F></div>
          <div className="pt"><span className="muted">Remit to</span><F on={ch("remitAddress")} tone={tone}>{inv.remitAddress ?? "—"}</F></div>
        </div>
        {hidden && (
          <div className={`hidden-text ${tone}`}>
            <span className="muted">Hidden text</span>
            <span>“{hidden}”</span>
          </div>
        )}
      </div>
    </div>
  );
}
