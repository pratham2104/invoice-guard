import { useEffect } from "react";
import type { CaseDetail } from "../types";
import { Icon } from "../ui/Icon";
import { invoiceLabel } from "../copy";
import { Paper } from "./Paper";

/** The invoice comparison, off the page: opened from "See invoice", closed with Esc, the scrim or the close button. */
export function InvoiceDrawer({ d, mark, vendor, onClose }: { d: CaseDetail; mark: string; vendor: string; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const cur = d.invoice.current;
  if (!cur) return null;
  return (
    <div className="drawer-wrap" role="dialog" aria-modal="true" aria-label="Invoice">
      <div className="drawer-scrim" onClick={onClose} />
      <aside className="drawer">
        <div className="drawer-head">
          <div>
            <div className="drawer-title">{vendor}</div>
            <div className="drawer-sub">{invoiceLabel(cur.invoiceNumber)}{d.invoice.lastReal ? ", next to their last real invoice" : ""}</div>
          </div>
          <button className="drawer-x" onClick={onClose} aria-label="Close"><Icon name="Cross" size={18} /></button>
        </div>
        <div className="drawer-body">
          <div className={`papers${d.invoice.lastReal ? "" : " one"}`}>
            {d.invoice.lastReal && <Paper inv={d.invoice.lastReal} caption="Last real invoice" />}
            <Paper inv={cur} against={d.invoice.lastReal} tone={mark} caption="This invoice" hidden={d.hiddenText} />
          </div>
        </div>
      </aside>
    </div>
  );
}
