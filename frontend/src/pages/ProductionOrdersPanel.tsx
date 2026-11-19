// Üretim emirleri: emir açma, işlem başında başla / durdur / bitir, tamamlama, işlem bazında süre raporu.
import { useState, type FormEvent } from "react";
import {
  useOperationReport, useProductBoms, useProductionOrder, useProductionOrderActions, useProductionOrders,
} from "../api/hooks";
import type { ProductionOp } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import { BandChip, Empty, ErrorNote, Field, Loading, Modal, Panel } from "../components/ui";
import { date, dateTime, num, num1 } from "../lib/format";
import { PROD_STATUS_BAND, PROD_STATUS_LABEL, SCRAP_REASON_LABEL, deviation, duration } from "../lib/production";
import { OrderCost } from "./ProductionCost";
import { FinishForm, MaterialsTable } from "./ProductionScrap";

const qty = (v: number | string, unit: string | null) => `${Number.isInteger(Number(v)) ? num(Number(v)) : num1(Number(v))} ${unit ?? ""}`.trim();

/** Plana göre sapma: geciken izlemede, erken biten yeşil. */
function Deviation({ planned, actual }: { planned: number | null; actual: number }) {
  const d = deviation(planned, actual);
  if (d == null) return <span className="muted">–</span>;
  return <span className={d > 10 ? "t-watch" : d < 0 ? "t-ok" : undefined}>{d > 0 ? "+" : d < 0 ? "−" : ""}%{num(Math.abs(d))}</span>;
}

export function OrdersPanel({ onOpen }: { onOpen: (id: string) => void }) {
  const { can } = useAuth();
  const orders = useProductionOrders();
  const boms = useProductBoms();
  const { create } = useProductionOrderActions();
  const [partId, setPartId] = useState("");
  const [amount, setAmount] = useState("1");
  const [due, setDue] = useState("");
  const [notes, setNotes] = useState("");
  const n = Number(amount.replace(",", "."));
  const product = boms.data?.find((b) => b.part_id === partId);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate({ part_id: partId, qty: n, due_at: due || null, notes: notes.trim() || null },
      { onSuccess: (o) => { setPartId(""); setAmount("1"); setDue(""); setNotes(""); onOpen(o.id); } });
  };

  return (
    <div className="prod">
      {can("manager") && (
        <Panel title="Yeni üretim emri" sub="İşlemler ürünün rotasından kopyalanır">
          <form className="form" onSubmit={submit}>
            <Field label="Ürün" hint="Ürün ağacı ve rotası olan kalemler">
              <select value={partId} onChange={(e) => setPartId(e.target.value)} required>
                <option value="">Seçin</option>
                {boms.data?.map((b) => <option key={b.id} value={b.part_id}>{b.name}{b.part_no ? ` · ${b.part_no}` : ""}</option>)}
              </select>
            </Field>
            <div className="form-row">
              <Field label={`Miktar${product?.unit ? ` (${product.unit})` : ""}`}>
                <input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
              </Field>
              <Field label="Termin">
                <input type="date" value={due} onChange={(e) => setDue(e.target.value)} />
              </Field>
            </div>
            <Field label="Not">
              <input value={notes} maxLength={1000} onChange={(e) => setNotes(e.target.value)} />
            </Field>
            <ErrorNote error={create.error} />
            <div className="actions"><button className="btn btn-primary" disabled={!partId || !(n > 0) || create.isPending}>Emri aç</button></div>
          </form>
        </Panel>
      )}
      <Panel title="Üretim emirleri" className={can("manager") ? "" : "prod-wide"}>
        {orders.isLoading ? <Loading /> : orders.error ? <ErrorNote error={orders.error} /> : !orders.data?.length ? (
          <Empty>Henüz üretim emri yok.</Empty>
        ) : (
          <div className="table-wrap">
            <table className="table lib-table">
              <thead><tr><th>Emir</th><th>Durum</th><th className="num">Miktar</th><th className="num">İşlem</th>
                <th className="num">Planlanan</th><th className="num">Gerçekleşen</th><th>Termin</th></tr></thead>
              <tbody>
                {orders.data.map((o) => (
                  <tr key={o.id}>
                    <td><button type="button" className="link-btn" onClick={() => onOpen(o.id)}>{o.number}</button>
                      <div className="muted small">{o.name}</div></td>
                    <td><BandChip band={PROD_STATUS_BAND[o.status]}>{PROD_STATUS_LABEL[o.status]}</BandChip>
                      {o.running > 0 && <div className="small t-watch">{num(o.running)} kişi çalışıyor</div>}</td>
                    <td className="num">{qty(o.qty, o.unit)}</td>
                    <td className="num">{num(o.ops_done)} / {num(o.op_count)}</td>
                    <td className="num">{duration(o.planned_minutes)}</td>
                    <td className="num">{duration(o.actual_minutes)}</td>
                    <td className={o.late ? "t-critical" : undefined}>{date(o.due_at)}{o.late && <div className="small">gecikti</div>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}

export function OrderModal({ id, onClose }: { id: string; onClose: () => void }) {
  const { can } = useAuth();
  const order = useProductionOrder(id);
  const { start, stop, setStatus } = useProductionOrderActions();
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [finishing, setFinishing] = useState(false);
  const o = order.data;
  const work = can("technician");
  const open = o?.status === "open" || o?.status === "in_progress";
  const busy = start.isPending || stop.isPending || setStatus.isPending;
  const allDone = !!o && o.ops_done === o.op_count;

  const opState = (op: ProductionOp) =>
    op.done_at ? <BandChip band="ok">Bitti</BandChip>
      : op.running_by.length ? <BandChip band="watch">Sürüyor</BandChip>
        : Number(op.actual_minutes) > 0 ? <BandChip band="unknown">Durdu</BandChip> : <BandChip band="empty">Bekliyor</BandChip>;

  return (
    <Modal wide title={o ? `${o.number} · ${o.name}` : "Üretim emri"} onClose={onClose}
           footer={o && open && !finishing ? <>
             {can("manager") && <button type="button" className="btn" disabled={busy} onClick={() => setConfirmCancel(true)}>Emri iptal et</button>}
             {work && <button type="button" className="btn btn-primary" disabled={busy || !allDone}
                              title={allDone ? undefined : "Bütün işlemler bitince tamamlanır"}
                              onClick={() => setFinishing(true)}>Emri tamamla</button>}
           </> : undefined}>
      {order.isLoading ? <Loading /> : order.error || !o ? <ErrorNote error={order.error} /> : (
        <>
          <dl className="facts">
            <div className="fact"><dt>Durum</dt><dd><BandChip band={PROD_STATUS_BAND[o.status]}>{PROD_STATUS_LABEL[o.status]}</BandChip></dd></div>
            <div className="fact"><dt>Miktar</dt><dd>{qty(o.qty, o.unit)}</dd></div>
            <div className="fact"><dt>Termin</dt><dd className={o.late ? "t-critical" : undefined}>{date(o.due_at)}</dd></div>
            <div className="fact"><dt>Planlanan süre</dt><dd>{duration(o.planned_minutes)}</dd></div>
            <div className="fact"><dt>Gerçekleşen süre</dt><dd>{duration(o.actual_minutes)}</dd></div>
            <div className="fact"><dt>İşlem</dt><dd>{num(o.ops_done)} / {num(o.op_count)}</dd></div>
            {o.good_qty != null && <>
              <div className="fact"><dt>Sağlam</dt><dd>{qty(o.good_qty, o.unit)}</dd></div>
              <div className="fact"><dt>Hurda</dt><dd className={Number(o.scrap_qty) > 0 ? "t-watch" : undefined}>{Number(o.scrap_qty) > 0 ? qty(o.scrap_qty ?? 0, o.unit) : "yok"}</dd>
                {o.scrap_reason && <div className="muted small">{SCRAP_REASON_LABEL[o.scrap_reason]}</div>}</div>
              <div className="fact"><dt>Depo</dt><dd>{o.site_name ?? "–"}</dd></div>
            </>}
          </dl>
          {o.notes && <p className="muted">{o.notes}</p>}
          <div className="table-wrap">
            <table className="table lib-table op-table">
              <thead><tr><th>İşlem</th><th>Durum</th><th className="num">Planlanan</th><th className="num">Gerçekleşen</th><th className="num">Sapma</th><th /></tr></thead>
              <tbody>
                {o.operations.map((op) => (
                  <tr key={op.id}>
                    <td><strong>{op.seq}. {op.name}</strong>
                      {op.running_by.length > 0 && <div className="small t-watch">çalışan: {op.running_by.join(", ")}</div>}
                      {op.done_at && <div className="muted small">{[op.done_by_name, dateTime(op.done_at)].filter(Boolean).join(" · ")}</div>}</td>
                    <td>{opState(op)}</td>
                    <td className="num" data-label="Planlanan">{duration(op.planned_minutes)}</td>
                    <td className="num" data-label="Gerçekleşen">{duration(op.actual_minutes)}</td>
                    <td className="num" data-label="Sapma">{op.done_at ? <Deviation planned={op.planned_minutes} actual={op.actual_minutes} /> : <span className="muted">–</span>}</td>
                    <td className="row-actions">{work && open && !op.done_at && (
                      <span className="op-actions">
                        {op.mine
                          ? <button type="button" className="btn btn-small" disabled={busy} onClick={() => stop.mutate({ orderId: id, opId: op.id, done: false })}>Durdur</button>
                          : <button type="button" className="btn btn-small btn-primary" disabled={busy} onClick={() => start.mutate({ orderId: id, opId: op.id })}>Başla</button>}
                        <button type="button" className="btn btn-small" disabled={busy} onClick={() => stop.mutate({ orderId: id, opId: op.id, done: true })}>Bitti</button>
                      </span>)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ErrorNote error={start.error ?? stop.error ?? setStatus.error} />
          {open && finishing ? <FinishForm order={o} onCancel={() => setFinishing(false)} />
            : <MaterialsTable materials={o.materials} done={o.status === "done"} />}
          {o.status !== "cancelled" && !finishing && <OrderCost order={o} />}
          {o.logs.length > 0 && (
            <details className="prod-logs">
              <summary>Zaman kayıtları ({num(o.logs.length)})</summary>
              <table className="table lib-table">
                <thead><tr><th>İşlem</th><th>Kişi</th><th>Başladı</th><th>Durdu</th><th className="num">Süre</th></tr></thead>
                <tbody>
                  {o.logs.map((l) => (
                    <tr key={l.id}><td>{l.operation}</td><td>{l.user_name}</td><td>{dateTime(l.started_at)}</td>
                      <td>{l.ended_at ? dateTime(l.ended_at) : <span className="t-watch">sürüyor</span>}</td><td className="num">{duration(l.minutes)}</td></tr>
                  ))}
                </tbody>
              </table>
            </details>
          )}
          {confirmCancel && (
            <Modal title="Emir iptal edilsin mi?" onClose={() => setConfirmCancel(false)}
                   footer={<>
                     <button type="button" className="btn" onClick={() => setConfirmCancel(false)}>Vazgeç</button>
                     <button type="button" className="btn btn-primary" disabled={busy}
                             onClick={() => setStatus.mutate({ orderId: id, status: "cancelled" }, { onSuccess: () => setConfirmCancel(false) })}>İptal et</button>
                   </>}>
              <p>{o.number} iptal edilir; süren zaman kayıtları kapanır. Tutulan süreler kayıtta kalır ama işlem raporuna girmez.</p>
            </Modal>
          )}
        </>
      )}
    </Modal>
  );
}

const PERIODS = [3, 6, 12, 24];

export function OperationReportPanel() {
  const [months, setMonths] = useState(12);
  const report = useOperationReport(months);
  const rows = report.data ?? [];
  const max = Math.max(1, ...rows.map((r) => Math.max(Number(r.actual_minutes), Number(r.planned_minutes ?? 0))));
  const planned = rows.reduce((s, r) => s + Number(r.planned_minutes ?? 0), 0);
  const actual = rows.reduce((s, r) => s + Number(r.actual_minutes), 0);

  return (
    <Panel title="İşlem raporu" sub="Biten işlemlerde planlanan ve gerçekleşen süre; iptal edilen emirler sayılmaz"
           actions={<div className="seg" role="group" aria-label="Dönem">
             {PERIODS.map((m) => <button key={m} type="button" aria-pressed={m === months} onClick={() => setMonths(m)}>{m} ay</button>)}
           </div>}>
      {report.isLoading ? <Loading /> : report.error ? <ErrorNote error={report.error} /> : rows.length === 0 ? (
        <Empty>Bu dönemde biten işlem yok.</Empty>
      ) : (
        <div className="table-wrap">
          <table className="table lib-table">
            <thead><tr><th>İşlem</th><th className="num">Emir</th><th className="op-bars-head">Planlanan / gerçekleşen</th>
              <th className="num">Planlanan</th><th className="num">Gerçekleşen</th><th className="num">Sapma</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.name}>
                  <td><strong>{r.name}</strong></td>
                  <td className="num">{num(r.order_count)}</td>
                  <td className="op-bars-cell">
                    <div className="op-bars" role="img" aria-label={`${r.name}: planlanan ${duration(r.planned_minutes)}, gerçekleşen ${duration(r.actual_minutes)}`}>
                      {r.planned_minutes != null && <i className="op-bar-plan" style={{ width: `${(Number(r.planned_minutes) / max) * 100}%` }} />}
                      <i className="op-bar-actual" style={{ width: `${(Number(r.actual_minutes) / max) * 100}%` }} />
                    </div>
                  </td>
                  <td className="num">{duration(r.planned_minutes)}</td>
                  <td className="num">{duration(r.actual_minutes)}</td>
                  <td className="num"><Deviation planned={r.planned_minutes} actual={Number(r.actual_planned_minutes)} /></td>
                </tr>
              ))}
            </tbody>
            <tfoot><tr><td colSpan={2}>Toplam</td><td className="op-bars-cell" /><td className="num">{duration(planned)}</td><td className="num">{duration(actual)}</td><td /></tr></tfoot>
          </table>
          <p className="muted small op-legend"><i className="op-bar-plan" /> planlanan <i className="op-bar-actual" /> gerçekleşen · Sapma yalnızca planlanan süresi olan işlemlerden hesaplanır.</p>
        </div>
      )}
    </Panel>
  );
}
