import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router";
import { useCatalogParts, useLabels, useOrder, usePurchasing, useSites, useSuppliers } from "../api/hooks";
import type { PoLine, PurchaseOrder } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import { BandChip, ErrorNote, Field, Loading, Panel } from "../components/ui";
import { date, dateTime, num, num1, usd } from "../lib/format";
import { openInNewTab } from "../lib/popup";
import { PO_STATUS } from "./PurchasingPage";

const qty = (v: number, unit: string) => `${Number.isInteger(Number(v)) ? num(v) : num1(v)} ${unit}`;
const n = (v: string) => Number(v.replace(",", "."));

function DraftLine({ po, l }: { po: PurchaseOrder; l: PoLine }) {
  const { patchLine, deleteLine } = usePurchasing();
  const [q, setQ] = useState(String(l.qty));
  const [c, setC] = useState(l.unit_cost != null ? String(l.unit_cost) : "");
  const save = () => {
    const body: { id: string; line: string; qty?: number; unit_cost?: number | null } = { id: po.id, line: l.id };
    if (n(q) !== Number(l.qty)) body.qty = n(q);
    if ((c ? n(c) : null) !== (l.unit_cost != null ? Number(l.unit_cost) : null)) body.unit_cost = c ? n(c) : null;
    if (body.qty !== undefined || body.unit_cost !== undefined) patchLine.mutate(body);
  };
  return (
    <tr>
      <td><strong>{l.part_name}</strong><div className="muted small">{l.part_no}</div></td>
      <td className="num"><input className="qty-input" inputMode="decimal" value={q} onChange={(e) => setQ(e.target.value)} onBlur={save} aria-label="Miktar" /> {l.unit}</td>
      <td className="num"><input className="qty-input" inputMode="decimal" value={c} onChange={(e) => setC(e.target.value)} onBlur={save} aria-label="Birim fiyat" /></td>
      <td className="num">{usd(Number(l.qty) * Number(l.unit_cost ?? 0))}</td>
      <td className="row-actions"><button className="btn btn-small" onClick={() => deleteLine.mutate({ id: po.id, line: l.id })}>Sil</button></td>
    </tr>
  );
}

function AddLine({ po }: { po: PurchaseOrder }) {
  const catalog = useCatalogParts();
  const { addLine } = usePurchasing();
  const [part, setPart] = useState("");
  const [q, setQ] = useState("1");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    addLine.mutate({ id: po.id, part_id: part, qty: n(q) }, { onSuccess: () => { setPart(""); setQ("1"); } });
  };
  return (
    <form className="filters" onSubmit={submit}>
      <select value={part} onChange={(e) => setPart(e.target.value)} required aria-label="Eklenecek kalem">
        <option value="">Kalem ekle…</option>
        {catalog.data?.map((c) => <option key={c.id} value={c.id}>{c.name} · stok {num1(c.in_stock)} {c.unit}</option>)}
      </select>
      <input className="qty-input" inputMode="decimal" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Miktar" />
      <button className="btn btn-ghost" disabled={!part || addLine.isPending}>Ekle</button>
      <ErrorNote error={addLine.error} />
    </form>
  );
}

function Receive({ po }: { po: PurchaseOrder }) {
  const sites = useSites();
  const { receive } = usePurchasing();
  const labels = useLabels();
  const open = po.lines.filter((l) => Number(l.remaining) > 0);
  const [site, setSite] = useState("");
  const [ref, setRef] = useState("");
  const [qtys, setQtys] = useState<Record<string, string>>(Object.fromEntries(open.map((l) => [l.id, String(l.remaining)])));
  const [serials, setSerials] = useState<Record<string, string>>({});
  const [made, setMade] = useState<string[]>([]);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const lines = open.filter((l) => n(qtys[l.id] ?? "0") > 0).map((l) => ({
      line_id: l.id, qty: n(qtys[l.id]),
      serials: (serials[l.id] ?? "").split(/[\n,;]+/).map((s) => s.trim()).filter(Boolean),
    }));
    receive.mutate({ id: po.id, site_id: site || null, ref: ref || null, lines }, { onSuccess: (r) => setMade(r.part_ids) });
  };
  return (
    <Panel title="Teslim al" sub="Gelen miktarı girin; sarf malzemeleri stoğa, seri numaralı parçalar seri numaralarıyla tek tek girer.">
      <form className="form" onSubmit={submit}>
        <div className="form-row">
          <Field label="Depo">
            <select value={site} onChange={(e) => setSite(e.target.value)}>
              <option value="">Genel depo</option>
              {sites.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </Field>
          <Field label="İrsaliye / fatura no" hint={`Boşsa ${po.number}`}><input value={ref} onChange={(e) => setRef(e.target.value)} maxLength={60} /></Field>
        </div>
        {open.map((l) => (
          <div key={l.id} className="recv-line">
            <div><strong>{l.part_name}</strong><div className="muted small">Kalan {qty(l.remaining, l.unit)} / sipariş {qty(l.qty, l.unit)}</div></div>
            <Field label={`Gelen (${l.unit})`}>
              <input className="qty-input" inputMode="decimal" value={qtys[l.id] ?? ""} onChange={(e) => setQtys({ ...qtys, [l.id]: e.target.value })} />
            </Field>
            {l.is_serialized && (
              <Field label="Seri numaraları" hint="Her satıra bir; boş bırakılırsa seri nosuz kaydedilir">
                <textarea rows={Math.min(Math.max(Number(qtys[l.id] || 1), 2), 6)} value={serials[l.id] ?? ""}
                          onChange={(e) => setSerials({ ...serials, [l.id]: e.target.value })} />
              </Field>
            )}
          </div>
        ))}
        <ErrorNote error={receive.error} />
        <div className="actions">
          <button className="btn btn-primary" disabled={receive.isPending}>{receive.isPending ? "Kaydediliyor…" : "Teslim alındı olarak kaydet"}</button>
          {made.length > 0 && (
            <button type="button" className="btn btn-ghost" onClick={() =>
              openInNewTab(async () => (await labels.mutateAsync({ asset_ids: [], part_ids: made.slice(0, 63), skip: 0 })).url).catch(() => undefined)}>
              Gelen {made.length} parçanın etiketlerini yazdır
            </button>
          )}
        </div>
      </form>
    </Panel>
  );
}

export function PurchaseOrderPage() {
  const { id } = useParams();
  const o = useOrder(id);
  const suppliers = useSuppliers();
  const { can } = useAuth();
  const { patch, place, cancel } = usePurchasing();
  const [expected, setExpected] = useState("");

  if (o.isLoading) return <Loading />;
  if (o.error) return <ErrorNote error={o.error} />;
  const po = o.data!;
  const st = PO_STATUS[po.status];
  const draft = po.status === "draft";

  return (
    <>
      <div className="page-head">
        <div>
          <p className="crumbs"><Link to="/satinalma?sekme=belgeler">Satınalma</Link> / {po.number}</p>
          <h1>{po.number} <BandChip band={st.band}>{st.label}</BandChip></h1>
          <p className="sub">
            Oluşturma {dateTime(po.created_at)}{po.ordered_at ? ` · sipariş ${dateTime(po.ordered_at)}` : ""}
            {po.received_at ? ` · teslim ${dateTime(po.received_at)}` : ""}
            {po.expected_date ? <> · beklenen <span className={po.late ? "t-critical" : ""}>{date(po.expected_date)}{po.late ? " (gecikti)" : ""}</span></> : ""}
          </p>
        </div>
        <div className="muted">Toplam <strong>{usd(po.total)}</strong></div>
      </div>

      <div className="grid">
        <Panel title="Satırlar">
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Kalem</th><th className="num">Miktar</th><th className="num">Birim fiyat</th><th className="num">Tutar</th>
                {draft ? <th /> : <th className="num">Teslim alınan</th>}</tr></thead>
              <tbody>
                {po.lines.map((l) => draft ? <DraftLine key={l.id} po={po} l={l} /> : (
                  <tr key={l.id}>
                    <td><strong>{l.part_name}</strong><div className="muted small">{l.part_no}</div></td>
                    <td className="num">{qty(l.qty, l.unit)}</td>
                    <td className="num">{usd(l.unit_cost)}</td>
                    <td className="num">{usd(Number(l.qty) * Number(l.unit_cost ?? 0))}</td>
                    <td className="num">{Number(l.received_qty) >= Number(l.qty) ? <span className="t-ok">✓ {qty(l.received_qty, l.unit)}</span> : qty(l.received_qty, l.unit)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {draft && <AddLine po={po} />}
        </Panel>

        <Panel title="Belge">
          <div className="form">
            <Field label="Tedarikçi">
              <select value={po.supplier_id ?? ""} disabled={!draft || patch.isPending}
                      onChange={(e) => patch.mutate({ id: po.id, supplier_id: e.target.value || null })}>
                <option value="">Seçilmemiş</option>
                {suppliers.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </Field>
            {po.notes && <p className="muted small">{po.notes}</p>}
            {draft && can("manager") && (
              <>
                <Field label="Beklenen teslim tarihi" hint="İsteğe bağlı; geçerse bildirim gelir">
                  <input type="date" value={expected} onChange={(e) => setExpected(e.target.value)} />
                </Field>
                <button className="btn btn-primary" disabled={place.isPending || !po.supplier_id || po.lines.length === 0}
                        onClick={() => place.mutate({ id: po.id, expected_date: expected || null })}>
                  Siparişi ver
                </button>
                {!po.supplier_id && <p className="muted small">Sipariş vermek için tedarikçi seçin.</p>}
              </>
            )}
            {draft && !can("manager") && <p className="muted small">Talep hazır. Siparişi yönetici verecek.</p>}
            {(po.status === "draft" || po.status === "ordered") && can("manager") && (
              <button className="btn btn-ghost" disabled={cancel.isPending} onClick={() => cancel.mutate(po.id)}>İptal et</button>
            )}
            <ErrorNote error={place.error ?? cancel.error ?? patch.error} />
          </div>
        </Panel>
      </div>

      {(po.status === "ordered" || po.status === "partial") && can("technician") && <div className="mt"><Receive key={po.status + po.lines.map((l) => l.received_qty).join()} po={po} /></div>}
    </>
  );
}
