import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";
import {
  useAssets, useNeeds, usePurchaseActions, usePurchaseOrder, usePurchaseOrders, useSites, useStock, useSuppliers,
} from "../api/hooks";
import type { PoStatus, PurchaseNeed, PurchaseOrderDetail, PurchaseOrderLine, StockRow, Supplier } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import { BandChip, Empty, ErrorNote, Field, Loading, Modal, Panel } from "../components/ui";
import { categoryLabel, date, dateTime, num, num1, usd } from "../lib/format";
import { PO_STATUS_BAND, PO_STATUS_LABEL, lineTotal, needItemLabel, needWhy, orderProgress } from "../lib/purchasing";

const q = (v: number | string | null | undefined, unit: string) =>
  v == null ? "–" : `${Number.isInteger(Number(v)) ? num(Number(v)) : num1(Number(v))} ${unit}`;
const parseNum = (v: string) => Number(v.replace(",", "."));
const today = () => new Date().toISOString().slice(0, 10);

type Tab = "ihtiyac" | "siparisler" | "tedarikciler";

// ---------- Yeni talep ----------
interface DraftLine { part_id: string; qty: string; unit_cost: string; asset_id: string; notes: string }

function NewOrderModal({ prefill, onClose, onCreated }: {
  prefill: DraftLine[]; onClose: () => void; onCreated: (id: string) => void;
}) {
  const suppliers = useSuppliers();
  const sites = useSites();
  const assets = useAssets();
  const stock = useStock({});
  const { createOrder } = usePurchaseActions();
  const [supplier, setSupplier] = useState("");
  const [site, setSite] = useState("");
  const [expected, setExpected] = useState("");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState<DraftLine[]>(prefill.length ? prefill : [{ part_id: "", qty: "", unit_cost: "", asset_id: "", notes: "" }]);
  const catalog = useMemo(() => [...(stock.data ?? [])].sort((a, b) => a.name.localeCompare(b.name, "tr")), [stock.data]);
  const byId = (id: string): StockRow | undefined => catalog.find((c) => c.part_id === id);
  const set = (i: number, patch: Partial<DraftLine>) => setLines((ls) => ls.map((l, k) => (k === i ? { ...l, ...patch } : l)));
  const total = lines.reduce((s, l) => s + (parseNum(l.qty) || 0) * (parseNum(l.unit_cost) || 0), 0);
  const valid = lines.length > 0 && lines.every((l) => l.part_id && parseNum(l.qty) > 0)
    && new Set(lines.map((l) => l.part_id)).size === lines.length;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    createOrder.mutate({
      supplier_id: supplier || null, site_id: site || null, expected_at: expected || null, notes: notes || null,
      lines: lines.map((l) => ({
        part_id: l.part_id, qty: parseNum(l.qty), unit_cost: l.unit_cost ? parseNum(l.unit_cost) : null,
        asset_id: l.asset_id || null, notes: l.notes || null,
      })),
    }, { onSuccess: (o) => onCreated(o.id) });
  };

  return (
    <Modal title="Satınalma talebi" onClose={onClose} wide>
      <form className="form" onSubmit={submit}>
        <div className="form-row">
          <Field label="Tedarikçi" hint="Talep aşamasında boş kalabilir; sipariş vermek için gerekir">
            <select value={supplier} onChange={(e) => setSupplier(e.target.value)}>
              <option value="">Henüz seçilmedi</option>
              {suppliers.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </Field>
          <Field label="Teslimat deposu">
            <select value={site} onChange={(e) => setSite(e.target.value)}>
              <option value="">Genel depo</option>
              {sites.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </Field>
          <Field label="Beklenen teslim">
            <input type="date" value={expected} min={today()} onChange={(e) => setExpected(e.target.value)} />
          </Field>
        </div>
        <h3 className="mini-head">Kalemler</h3>
        <div className="po-lines">
          {lines.map((l, i) => {
            const c = byId(l.part_id);
            return (
              <div className="po-line" key={i}>
                <select value={l.part_id} onChange={(e) => {
                  const n = byId(e.target.value);
                  set(i, { part_id: e.target.value, unit_cost: l.unit_cost || (n?.avg_cost != null ? String(n.avg_cost) : "") });
                }} required aria-label="Kalem">
                  <option value="" disabled>Kalem seçin</option>
                  {catalog.map((p) => <option key={p.part_id} value={p.part_id}>{p.name}{p.part_no ? ` · ${p.part_no}` : ""}</option>)}
                </select>
                <input inputMode="decimal" placeholder={`Miktar${c ? ` (${c.unit})` : ""}`} value={l.qty}
                       onChange={(e) => set(i, { qty: e.target.value })} required aria-label="Miktar" />
                <input inputMode="decimal" placeholder="Birim $" value={l.unit_cost}
                       onChange={(e) => set(i, { unit_cost: e.target.value })} aria-label="Birim fiyat" />
                <select value={l.asset_id} onChange={(e) => set(i, { asset_id: e.target.value })} aria-label="Makine">
                  <option value="">Makine: genel</option>
                  {assets.data?.map((a) => <option key={a.id} value={a.id}>{a.code}</option>)}
                </select>
                <button type="button" className="icon-btn" aria-label="Satırı sil" onClick={() => setLines((ls) => ls.filter((_, k) => k !== i))}>×</button>
                {c && (
                  <div className="po-line-hint muted small">
                    Stokta {q(c.qty, c.unit)}{c.min_stock ? `, kritik seviye ${q(c.min_stock, c.unit)}` : ""}
                    {c.is_serialized ? " · seri numaralı, teslimde her adet için seri girilir" : ""}
                  </div>
                )}
              </div>
            );
          })}
        </div>
        <div className="actions">
          <button type="button" className="btn btn-ghost" onClick={() => setLines((ls) => [...ls, { part_id: "", qty: "", unit_cost: "", asset_id: "", notes: "" }])}>+ Kalem ekle</button>
          <span className="muted small">Tahmini toplam: <strong>{usd(total)}</strong></span>
        </div>
        <Field label="Not"><input value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={1000} /></Field>
        <ErrorNote error={createOrder.error} />
        <div className="actions">
          <button className="btn btn-primary" disabled={!valid || createOrder.isPending}>
            {createOrder.isPending ? "Kaydediliyor…" : "Talebi kaydet"}
          </button>
          <button type="button" className="btn btn-ghost" onClick={onClose}>Vazgeç</button>
        </div>
      </form>
    </Modal>
  );
}

// ---------- Teslim alma ----------
function ReceiveForm({ order, onDone }: { order: PurchaseOrderDetail; onDone: () => void }) {
  const sites = useSites();
  const { receive } = usePurchaseActions();
  const open = order.lines.filter((l) => Number(l.received_qty) < Number(l.qty));
  const [site, setSite] = useState(order.site_id ?? "");
  const [ref, setRef] = useState("");
  const [qty, setQty] = useState<Record<number, string>>(() =>
    Object.fromEntries(open.map((l) => [l.id, String(Number(l.qty) - Number(l.received_qty))])));
  const [serials, setSerials] = useState<Record<number, string[]>>({});
  const count = (l: PurchaseOrderLine) => parseNum(qty[l.id] ?? "") || 0;
  const serialCount = (l: PurchaseOrderLine) => Math.max(0, Math.floor(count(l)));
  // Seri numaralı satırda miktar kadar seri alanı. Dizi yalnızca büyür; miktar geçici olarak
  // bozulsa (ör. yazarken) girilmiş seri numaraları kaybolmaz, fazlası gösterilmez.
  useEffect(() => {
    setSerials((s) => {
      const n: Record<number, string[]> = { ...s };
      for (const l of open) if (l.is_serialized) {
        const cur = s[l.id] ?? [];
        n[l.id] = cur.length >= serialCount(l) ? cur : [...cur, ...Array.from({ length: serialCount(l) - cur.length }, () => "")];
      }
      return n;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qty]);
  const visibleSerials = (l: PurchaseOrderLine) => (serials[l.id] ?? []).slice(0, serialCount(l));

  const submit = (e: FormEvent) => {
    e.preventDefault();
    receive.mutate({
      id: order.id,
      body: {
        site_id: site || null, ref: ref || null,
        lines: open.filter((l) => count(l) > 0).map((l) => ({
          line_id: l.id, qty: count(l),
          serials: l.is_serialized ? visibleSerials(l).map((s) => ({ serial_no: s.trim() || null })) : undefined,
        })),
      },
    }, { onSuccess: onDone });
  };

  return (
    <form className="form po-receive" onSubmit={submit}>
      <h3 className="mini-head">Teslim al</h3>
      <div className="form-row">
        <Field label="Depo"><select value={site} onChange={(e) => setSite(e.target.value)}>
          <option value="">Genel depo</option>
          {sites.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select></Field>
        <Field label="İrsaliye / fatura no"><input value={ref} onChange={(e) => setRef(e.target.value)} maxLength={60} /></Field>
      </div>
      {open.map((l) => (
        <div className="po-receive-line" key={l.id}>
          <div>
            <strong>{l.name}</strong>
            <div className="muted small">Kalan {q(Number(l.qty) - Number(l.received_qty), l.unit)}</div>
          </div>
          <input inputMode="decimal" aria-label={`${l.name} miktar`} value={qty[l.id] ?? ""} onChange={(e) => setQty({ ...qty, [l.id]: e.target.value })} />
          {l.is_serialized && visibleSerials(l).length > 0 && (
            <div className="po-serials">
              {visibleSerials(l).map((s, i) => (
                <input key={i} placeholder={`Seri no ${i + 1} (boşsa otomatik QR)`} value={s} aria-label={`${l.name} seri no ${i + 1}`}
                       onChange={(e) => setSerials({ ...serials, [l.id]: serials[l.id].map((x, k) => (k === i ? e.target.value : x)) })} />
              ))}
            </div>
          )}
        </div>
      ))}
      <ErrorNote error={receive.error} />
      <div className="actions">
        <button className="btn btn-primary" disabled={receive.isPending || !open.some((l) => count(l) > 0)}>
          {receive.isPending ? "Kaydediliyor…" : "Teslimatı kaydet"}
        </button>
        <button type="button" className="btn btn-ghost" onClick={onDone}>Vazgeç</button>
      </div>
    </form>
  );
}

// ---------- Sipariş ayrıntısı ----------
function OrderModal({ id, onClose }: { id: string; onClose: () => void }) {
  const { can } = useAuth();
  const o = usePurchaseOrder(id);
  const suppliers = useSuppliers();
  const sites = useSites();
  const { updateOrder, setStatus } = usePurchaseActions();
  const [mode, setMode] = useState<"view" | "receive" | "edit">("view");
  const [supplier, setSupplier] = useState("");
  const [site, setSite] = useState("");
  const [expected, setExpected] = useState("");
  const d = o.data;
  useEffect(() => {
    if (d) { setSupplier(d.supplier_id ?? ""); setSite(d.site_id ?? ""); setExpected(d.expected_at ?? ""); }
  }, [d]);
  if (!d) return <Modal title="Sipariş" onClose={onClose} wide>{o.error ? <ErrorNote error={o.error} /> : <Loading />}</Modal>;

  const isOpen = d.status === "draft" || d.status === "ordered" || d.status === "partial";
  const progress = orderProgress(d.lines);
  const saveHeader = () => updateOrder.mutate(
    { id, body: { supplier_id: supplier || null, site_id: site || null, expected_at: expected || null } },
    { onSuccess: () => setMode("view") });

  return (
    <Modal title={`${d.number} · ${PO_STATUS_LABEL[d.status]}`} onClose={onClose} wide>
      <div className="stack">
        <div className="row-between">
          <BandChip band={PO_STATUS_BAND[d.status]}>{PO_STATUS_LABEL[d.status]}{d.late ? " · gecikti" : ""}</BandChip>
          <span className="muted small">
            {d.requested_by_name ? `${d.requested_by_name} açtı, ${dateTime(d.created_at)}` : dateTime(d.created_at)}
            {d.ordered_at ? ` · sipariş ${date(d.ordered_at)}` : ""}{d.closed_at ? ` · kapandı ${date(d.closed_at)}` : ""}
          </span>
        </div>
        {mode === "edit" ? (
          <div className="form">
            <div className="form-row">
              <Field label="Tedarikçi"><select value={supplier} onChange={(e) => setSupplier(e.target.value)}>
                <option value="">Henüz seçilmedi</option>
                {suppliers.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select></Field>
              <Field label="Teslimat deposu"><select value={site} onChange={(e) => setSite(e.target.value)}>
                <option value="">Genel depo</option>
                {sites.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select></Field>
              <Field label="Beklenen teslim"><input type="date" value={expected} onChange={(e) => setExpected(e.target.value)} /></Field>
            </div>
            <ErrorNote error={updateOrder.error} />
            <div className="actions">
              <button className="btn btn-primary" onClick={saveHeader} disabled={updateOrder.isPending}>Kaydet</button>
              <button className="btn btn-ghost" onClick={() => setMode("view")}>Vazgeç</button>
            </div>
          </div>
        ) : (
          <dl className="facts">
            <div className="fact"><dt>Tedarikçi</dt><dd>{d.supplier_name ?? <span className="muted">seçilmedi</span>}</dd></div>
            <div className="fact"><dt>Teslimat</dt><dd>{d.site_name ?? "Genel depo"}</dd></div>
            <div className="fact"><dt>Beklenen</dt><dd className={d.late ? "t-watch" : undefined}>{date(d.expected_at)}</dd></div>
          </dl>
        )}
        {d.notes && <p className="muted small">{d.notes}</p>}

        <div className="table-wrap">
          <table className="table po-table">
            <thead><tr><th>Kalem</th><th className="num">Miktar</th><th className="num">Teslim</th><th className="num">Birim</th><th className="num">Tutar</th></tr></thead>
            <tbody>
              {d.lines.map((l) => (
                <tr key={l.id}>
                  <td><strong>{l.name}</strong>
                    <div className="muted small">{categoryLabel(l.category_code)}{l.asset_code ? ` · ${l.asset_code} için` : ""}{l.notes ? ` · ${l.notes}` : ""}</div></td>
                  <td className="num">{q(l.qty, l.unit)}</td>
                  <td className="num">{Number(l.received_qty) >= Number(l.qty) ? <span className="t-ok">tam</span> : q(l.received_qty, l.unit)}</td>
                  <td className="num">{usd(l.unit_cost)}</td>
                  <td className="num">{usd(lineTotal(l))}</td>
                </tr>
              ))}
            </tbody>
            <tfoot><tr><td colSpan={4}>Toplam{progress > 0 && progress < 1 ? ` · %${num(progress * 100)} teslim alındı` : ""}</td><td className="num"><strong>{usd(d.total)}</strong></td></tr></tfoot>
          </table>
        </div>

        {mode === "receive" ? <ReceiveForm order={d} onDone={() => setMode("view")} /> : isOpen && (
          <div className="actions">
            {d.status === "draft" && can("technician") && <button className="btn btn-ghost" onClick={() => setMode("edit")}>Düzenle</button>}
            {d.status === "draft" && can("manager") && (
              <button className="btn btn-primary" onClick={() => setStatus.mutate({ id, status: "ordered" })} disabled={setStatus.isPending}>Sipariş ver</button>)}
            {(d.status === "ordered" || d.status === "partial") && can("technician") && (
              <button className="btn btn-primary" onClick={() => setMode("receive")}>Teslim al</button>)}
            {d.status === "partial" && can("manager") && (
              <button className="btn btn-ghost" onClick={() => setStatus.mutate({ id, status: "received" })} disabled={setStatus.isPending}>Kalanı kapat</button>)}
            {(d.status === "draft" || d.status === "ordered") && can("manager") && (
              <button className="btn btn-ghost t-critical" onClick={() => setStatus.mutate({ id, status: "cancelled" })} disabled={setStatus.isPending}>İptal et</button>)}
          </div>
        )}
        <ErrorNote error={setStatus.error} />

        {d.receipts.length > 0 && (
          <>
            <h3 className="mini-head">Teslim alma kayıtları</h3>
            <ul className="moves">
              {d.receipts.map((r) => (
                <li key={r.id}>
                  <span className="mv-qty pos">+{q(r.qty, d.lines.find((l) => l.id === r.line_id)?.unit ?? "")}</span>
                  <span>
                    <strong>{r.name}</strong>{r.site_name ? ` · ${r.site_name}` : ""}{r.ref ? ` · ${r.ref}` : ""}
                    {r.serials?.length ? <> · {r.serials.map((s, i) => <span key={s.id}>{i ? ", " : ""}<Link to={`/parca/${s.id}`}>{s.serial_no ?? "seri yok"}</Link></span>)}</> : null}
                    <span className="muted small"> {dateTime(r.received_at)}{r.received_by_name ? ` · ${r.received_by_name}` : ""}</span>
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </Modal>
  );
}

// ---------- İhtiyaç ----------
function NeedsPanel({ onRequest }: { onRequest: (lines: DraftLine[]) => void }) {
  const { can } = useAuth();
  const needs = useNeeds();
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const rows = (needs.data ?? []).filter((n) => Number(n.need) > 0 || n.upcoming > 0);
  const toggle = (id: string) => setPicked((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const request = (list: PurchaseNeed[]) => onRequest(list.map((n) => ({
    part_id: n.part_id, qty: String(Math.max(Number(n.need), 1)), unit_cost: n.avg_cost != null ? String(n.avg_cost) : "",
    asset_id: "", notes: n.upcoming > 0 ? needWhy(n).replace(/\.$/, "") : "",
  })));
  return (
    <Panel title="Sipariş ihtiyacı" sub="Yaklaşan değişimler ve kritik stok seviyesi; stoktaki ve siparişteki düşülmüş"
           actions={can("technician") && picked.size > 0 ? (
             <button className="btn btn-primary" onClick={() => request(rows.filter((n) => picked.has(n.part_id)))}>
               Seçilenlerle talep aç ({picked.size})
             </button>) : undefined}>
      {needs.isLoading ? <Loading /> : needs.error ? <ErrorNote error={needs.error} /> : rows.length === 0 ? (
        <Empty>Şu an sipariş gereken kalem yok. Yaklaşan değişimler stok ve siparişle karşılanıyor.</Empty>
      ) : (
        <div className="table-wrap">
          <table className="table needs">
            <thead><tr>{can("technician") && <th />}<th>Kalem</th><th>Neden</th><th className="num">Stokta</th><th className="num">Siparişte</th><th className="num">Önerilen</th><th /></tr></thead>
            <tbody>
              {rows.map((n) => (
                <tr key={n.part_id}>
                  {can("technician") && <td><input type="checkbox" aria-label={`${n.name} seç`} checked={picked.has(n.part_id)} onChange={() => toggle(n.part_id)} /></td>}
                  <td><strong>{n.name}</strong><div className="muted small">{[categoryLabel(n.category_code), n.manufacturer, n.part_no].filter(Boolean).join(" · ")}</div></td>
                  <td>
                    <div>{needWhy(n)}</div>
                    {n.items && n.items.length > 0 && (
                      <div className="site-chips">
                        {n.items.slice(0, 6).map((i) => (
                          <Link key={i.id} to={`/parca/${i.id}`} className={`chip chip-plain t-${i.band}`}>{needItemLabel(i)}</Link>))}
                        {n.items.length > 6 && <span className="chip chip-plain">+{n.items.length - 6}</span>}
                      </div>
                    )}
                  </td>
                  <td className="num">{q(n.in_stock, n.unit)}</td>
                  <td className="num">{Number(n.on_order) ? q(n.on_order, n.unit) : "–"}{Number(n.requested) ? <div className="muted small">talepte {q(n.requested, n.unit)}</div> : null}</td>
                  <td className="num"><strong>{Number(n.need) > 0 ? q(n.need, n.unit) : "–"}</strong></td>
                  <td>{can("technician") && Number(n.need) > 0 && <button className="link-btn" onClick={() => request([n])}>Talep aç</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

// ---------- Siparişler ----------
function OrdersPanel({ onOpen, onNew }: { onOpen: (id: string) => void; onNew: () => void }) {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const f = { status: params.get("durum") ?? "", q: params.get("q") ?? "", all: params.get("tumu") === "1" };
  const orders = usePurchaseOrders({ status: f.status || undefined, q: f.q || undefined, open_only: !f.all && !f.status });
  const set = (k: string, v: string) => { const n = new URLSearchParams(params); if (v) n.set(k, v); else n.delete(k); setParams(n, { replace: true }); };
  return (
    <Panel title="Talepler ve siparişler" actions={can("technician") ? <button className="btn btn-primary" onClick={onNew}>Yeni talep</button> : undefined}>
      <div className="filters">
        <input type="search" placeholder="Sipariş no, tedarikçi veya kalem" value={f.q} onChange={(e) => set("q", e.target.value)} aria-label="Ara" />
        <select value={f.status} onChange={(e) => set("durum", e.target.value)} aria-label="Durum">
          <option value="">Açık olanlar</option>
          {(Object.keys(PO_STATUS_LABEL) as PoStatus[]).map((s) => <option key={s} value={s}>{PO_STATUS_LABEL[s]}</option>)}
        </select>
        <label className="inline-check"><input type="checkbox" checked={f.all} onChange={(e) => set("tumu", e.target.checked ? "1" : "")} /> Kapananları da göster</label>
      </div>
      {orders.isLoading ? <Loading /> : orders.error ? <ErrorNote error={orders.error} /> : (orders.data?.length ?? 0) === 0 ? (
        <Empty>Bu filtrelere uyan sipariş yok.</Empty>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>No</th><th>Durum</th><th>Tedarikçi</th><th>Kalemler</th><th className="num">Tutar</th><th>Beklenen</th></tr></thead>
            <tbody>
              {orders.data!.map((o) => (
                <tr key={o.id} onClick={() => onOpen(o.id)}>
                  <td><strong>{o.number}</strong><div className="muted small">{date(o.created_at)}{o.requested_by_name ? ` · ${o.requested_by_name}` : ""}</div></td>
                  <td><BandChip band={PO_STATUS_BAND[o.status]}>{PO_STATUS_LABEL[o.status]}</BandChip>{o.late && <div className="t-watch small">gecikti</div>}</td>
                  <td>{o.supplier_name ?? <span className="muted">–</span>}</td>
                  <td className="small">{o.summary}</td>
                  <td className="num">{usd(o.total)}</td>
                  <td>{date(o.expected_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

// ---------- Tedarikçiler ----------
const EMPTY_SUPPLIER = { name: "", contact_name: "", phone: "", email: "", tax_no: "", address: "", notes: "", lead_time_days: "", is_active: true };

function SupplierForm({ initial, onDone }: { initial?: Supplier; onDone: () => void }) {
  const { createSupplier, updateSupplier } = usePurchaseActions();
  const [f, setF] = useState(initial ? {
    name: initial.name, contact_name: initial.contact_name ?? "", phone: initial.phone ?? "", email: initial.email ?? "",
    tax_no: initial.tax_no ?? "", address: initial.address ?? "", notes: initial.notes ?? "",
    lead_time_days: initial.lead_time_days == null ? "" : String(initial.lead_time_days), is_active: initial.is_active,
  } : EMPTY_SUPPLIER);
  const m = initial ? updateSupplier : createSupplier;
  const up = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const body = {
      name: f.name, contact_name: f.contact_name || null, phone: f.phone || null, email: f.email || null, tax_no: f.tax_no || null,
      address: f.address || null, notes: f.notes || null, lead_time_days: f.lead_time_days ? Number(f.lead_time_days) : null, is_active: f.is_active,
    };
    if (initial) updateSupplier.mutate({ id: initial.id, body }, { onSuccess: onDone });
    else createSupplier.mutate(body, { onSuccess: onDone });
  };
  return (
    <form className="form" onSubmit={submit}>
      <div className="form-row">
        <Field label="Firma adı"><input value={f.name} onChange={up("name")} required minLength={2} maxLength={120} autoFocus /></Field>
        <Field label="Yetkili"><input value={f.contact_name} onChange={up("contact_name")} maxLength={120} /></Field>
        <Field label="Telefon"><input value={f.phone} onChange={up("phone")} maxLength={40} /></Field>
        <Field label="E-posta"><input type="email" value={f.email} onChange={up("email")} maxLength={120} /></Field>
        <Field label="Vergi no"><input value={f.tax_no} onChange={up("tax_no")} maxLength={40} /></Field>
        <Field label="Teslim süresi (gün)" hint="Sipariş verildiğinde beklenen tarih önerisi"><input inputMode="numeric" value={f.lead_time_days} onChange={up("lead_time_days")} /></Field>
      </div>
      <Field label="Adres"><input value={f.address} onChange={up("address")} maxLength={400} /></Field>
      <Field label="Not"><input value={f.notes} onChange={up("notes")} maxLength={1000} /></Field>
      {initial && <label className="inline-check"><input type="checkbox" checked={f.is_active} onChange={(e) => setF({ ...f, is_active: e.target.checked })} /> Aktif (listede görünür)</label>}
      <ErrorNote error={m.error} />
      <div className="actions">
        <button className="btn btn-primary" disabled={m.isPending || f.name.trim().length < 2}>{m.isPending ? "Kaydediliyor…" : "Kaydet"}</button>
        <button type="button" className="btn btn-ghost" onClick={onDone}>Vazgeç</button>
      </div>
    </form>
  );
}

function SuppliersPanel() {
  const { can } = useAuth();
  const [all, setAll] = useState(false);
  const suppliers = useSuppliers(all);
  const [edit, setEdit] = useState<Supplier | "new" | null>(null);
  return (
    <Panel title="Tedarikçiler" actions={can("manager") ? <button className="btn btn-primary" onClick={() => setEdit("new")}>Tedarikçi ekle</button> : undefined}>
      <div className="filters">
        <label className="inline-check"><input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /> Pasifleri de göster</label>
      </div>
      {suppliers.isLoading ? <Loading /> : (suppliers.data?.length ?? 0) === 0 ? <Empty>Henüz tedarikçi yok.</Empty> : (
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Tedarikçi</th><th>İletişim</th><th className="num">Teslim süresi</th><th className="num">Açık sipariş</th><th /></tr></thead>
            <tbody>
              {suppliers.data!.map((s) => (
                <tr key={s.id}>
                  <td><strong>{s.name}</strong>{!s.is_active && <span className="muted small"> · pasif</span>}{s.notes && <div className="muted small">{s.notes}</div>}</td>
                  <td className="small">{[s.contact_name, s.phone, s.email].filter(Boolean).join(" · ") || "–"}</td>
                  <td className="num">{s.lead_time_days != null ? `${s.lead_time_days} gün` : "–"}</td>
                  <td className="num">{s.open_orders ?? 0}</td>
                  <td>{can("manager") && <button className="link-btn" onClick={() => setEdit(s)}>Düzenle</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {edit && (
        <Modal title={edit === "new" ? "Yeni tedarikçi" : edit.name} onClose={() => setEdit(null)}>
          <SupplierForm initial={edit === "new" ? undefined : edit} onDone={() => setEdit(null)} />
        </Modal>
      )}
    </Panel>
  );
}

// ---------- Sayfa ----------
export function PurchasingPage() {
  const [params, setParams] = useSearchParams();
  const tab = (params.get("sekme") as Tab | null) ?? "ihtiyac";
  const openId = params.get("siparis");
  const newFor = params.get("yeni");
  const stock = useStock({});
  const [draft, setDraft] = useState<DraftLine[] | null>(null);
  const set = (k: string, v: string) => { const n = new URLSearchParams(params); if (v) n.set(k, v); else n.delete(k); setParams(n, { replace: true }); };

  // Stok sayfasından "Sipariş talebi aç" ile gelindi: kalem hazır
  useEffect(() => {
    if (!newFor || draft) return;
    const row = stock.data?.find((r) => r.part_id === newFor);
    if (row) {
      const need = Math.max(row.min_stock - Number(row.qty), 1);
      setDraft([{ part_id: row.part_id, qty: String(need), unit_cost: row.avg_cost != null ? String(row.avg_cost) : "", asset_id: "", notes: "" }]);
    }
  }, [newFor, stock.data, draft]);

  const tabs: { key: Tab; label: string }[] = [
    { key: "ihtiyac", label: "İhtiyaç" }, { key: "siparisler", label: "Siparişler" }, { key: "tedarikciler", label: "Tedarikçiler" },
  ];
  return (
    <>
      <div className="page-head"><h1>Satınalma</h1></div>
      <div className="tabs" role="tablist">
        {tabs.map((t) => <button key={t.key} role="tab" aria-selected={t.key === tab} onClick={() => set("sekme", t.key)}>{t.label}</button>)}
      </div>
      {tab === "ihtiyac" && <NeedsPanel onRequest={setDraft} />}
      {tab === "siparisler" && <OrdersPanel onOpen={(id) => set("siparis", id)} onNew={() => setDraft([])} />}
      {tab === "tedarikciler" && <SuppliersPanel />}
      {draft && (
        <NewOrderModal prefill={draft} onClose={() => { setDraft(null); if (newFor) set("yeni", ""); }}
                       onCreated={(id) => { setDraft(null); const n = new URLSearchParams(params); n.delete("yeni"); n.set("sekme", "siparisler"); n.set("siparis", id); setParams(n); }} />
      )}
      {openId && <OrderModal id={openId} onClose={() => set("siparis", "")} />}
    </>
  );
}
