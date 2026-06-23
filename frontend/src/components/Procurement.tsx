import { useState } from "react";
import { createPo, requestRfq, usd } from "../api";
import { Eyebrow } from "../design/ui";
import type { BomLine, Po, RfqResponse } from "../types";

const clean = (n: string) => n.replace(" (synthetic)", "");

export default function Procurement({ bom }: { bom: BomLine[] }) {
  const [rfq, setRfq] = useState<RfqResponse | null>(null);
  const [po, setPo] = useState<Po | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const lines = bom.map((b) => ({
    sku: b.sku, qty: b.qty, unit_list: b.unit_list,
    manufacturer_code: b.manufacturer_code ?? "", name: b.name,
  }));

  async function getRfq() {
    setBusy(true); setErr(null); setPo(null);
    try { setRfq(await requestRfq(lines)); }
    catch (e) { setErr(String(e instanceof Error ? e.message : e)); }
    finally { setBusy(false); }
  }
  async function pick(id: number) {
    setBusy(true); setErr(null);
    try { setPo(await createPo(lines, id)); }
    catch (e) { setErr(String(e instanceof Error ? e.message : e)); }
    finally { setBusy(false); }
  }

  return (
    <div className="procurement">
      <Eyebrow style={{ display: "block", marginBottom: 12 }}>Procurement · vendor sourcing</Eyebrow>
      {err && <div className="err">{err}</div>}

      {!rfq && (
        <button className="ds-btn ds-btn--ghost" onClick={getRfq} disabled={busy}>
          {busy ? "Requesting quotes…" : "Source to procurement →"}
        </button>
      )}

      {rfq && !po && (
        <div className="vendors">
          {rfq.vendors.map((v) => (
            <button className="vendor" key={v.vendor_id} onClick={() => pick(v.vendor_id)} disabled={busy}>
              <div className="v-top">
                <span className="v-name">
                  {clean(v.vendor_name)}
                  {v.rank === 1 && <em className="v-best">best</em>}
                </span>
                <span className="v-total">{usd(v.net_total)}</span>
              </div>
              <div className="v-meta">
                {v.city}, {v.state} · {v.lead_time_days}d lead · {Math.round(v.coverage_pct * 100)}% coverage
                {!v.can_fulfill_all && <span className="v-gap"> · partial</span>}
              </div>
            </button>
          ))}
          <p className="disclaim">Synthetic vendors — real dealer-vendor terms are private/unpublished.</p>
        </div>
      )}

      {po && (
        <div className="po">
          <div className="po-head">
            <span className="po-num">{po.po_number}</span>
            <button className="ds-btn ds-btn--quiet" onClick={() => setPo(null)}>← vendors</button>
          </div>
          <div className="po-vendor">{clean(po.vendor.name)} · {po.vendor.city}, {po.vendor.state}</div>
          <div className="rows">
            <div className="row"><span className="k">Subtotal (net)</span><span className="n">{usd(po.subtotal)}</span></div>
            <div className="row"><span className="k">Tax</span><span className="n">{usd(po.tax)}</span></div>
          </div>
          <div className="po-total"><small>PO total</small>{usd(po.total)}</div>
          <div className="po-deliver">
            Delivery {po.delivery_window.from} → {po.delivery_window.to} · {po.lead_time_days}d lead
          </div>
        </div>
      )}
    </div>
  );
}
