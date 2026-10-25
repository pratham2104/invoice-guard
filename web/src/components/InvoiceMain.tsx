import type { ClearedInvoice } from "../types";
import { invoiceLabel, longDate, possessive } from "../copy";
import { Paper } from "./Paper";
import { Amount } from "../ui/Amount";
import { Icon } from "../ui/Icon";

export function InvoiceMain({ d }: { d: ClearedInvoice }) {
  const inv = d.invoice;
  const vendor = d.vendor?.name ?? "this vendor";
  return (
    <div className="stack">
      <section className="hero cleared">
        <div className="hero-top">
          <span className="hero-pill"><Icon name="Check" size={14} />Cleared</span>
          <span className="hero-state"><Icon name="ShieldCheck" size={44} />{inv.status === "approved" ? "Approved" : "Paid"}</span>
        </div>
        <p className="hero-line">Matched {possessive(vendor)} normal pattern.</p>
        <div className="hero-foot">
          <div className="hero-who">
            <div className="hero-vendor">{d.vendor?.name ?? "Invoice"}</div>
            <div className="hero-meta">{invoiceLabel(inv.invoiceNumber)} · {longDate(inv.invoiceDate)}</div>
          </div>
          <div className="hero-amt"><Amount n={inv.amount} /></div>
        </div>
      </section>
      <section className="card papers-card">
        <h2>The invoice</h2>
        <div className="papers one"><Paper inv={inv} caption="" /></div>
      </section>
    </div>
  );
}
