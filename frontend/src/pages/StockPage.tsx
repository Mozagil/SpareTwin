import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";
import { useAssets, useSites, useStock, useStockActions, useStockMovements } from "../api/hooks";
import type { StockMovement, StockRow } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import { BandChip, Empty, ErrorNote, Field, Loading, Modal, Panel } from "../components/ui";
import { CATEGORY_LABEL, categoryLabel, dateTime, num, num1, usd } from "../lib/format";

const KIND_LABEL: Record<StockMovement["kind"], string> = {
  in: "Giriş", out: "Çıkış", adjust: "Sayım düzeltmesi", transfer_out: "Transfer (çıkış)", transfer_in: "Transfer (giriş)",
};
const q = (v: number | null | undefined, unit: string) => (v == null ? "–" : `${Number.isInteger(Number(v)) ? num(v) : num1(v)} ${unit}`);
const parseNum = (v: string) => Number(v.replace(",", "."));

type Action = "in" | "out" | "adjust" | "transfer";

function MoveForm({ row, action, onDone }: { row: StockRow; action: Action; onDone: () => void }) {
  const sites = useSites();
  const assets = useAssets();
  const { move, transfer } = useStockActions();
  const firstSite = row.sites?.find((s) => Number(s.qty) > 0)?.site_id ?? sites.data?.[0]?.id ?? "";
  const [site, setSite] = useState<string>(firstSite ?? "");
  const [to, setTo] = useState("");
  const [qty, setQty] = useState("");
  const [cost, setCost] = useState("");
  const [asset, setAsset] = useState("");
  const [reason, setReason] = useState(action === "out" ? "periyodik bakım" : action === "adjust" ? "sayım" : "satınalma");
  const [ref, setRef] = useState("");
  const [notes, setNotes] = useState("");
  const current = Number(row.sites?.find((s) => s.site_id === (site || null))?.qty ?? 0);
  const m = action === "transfer" ? transfer : move;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const n = parseNum(qty);
    if (action === "transfer") {
      transfer.mutate({ part_id: row.part_id, from_site_id: site || null, to_site_id: to || null, qty: n, notes: notes || null },
        { onSuccess: onDone });
    } else {
      move.mutate({
        part_id: row.part_id, site_id: site || null, kind: action, qty: n,
        unit_cost: action === "in" && cost ? parseNum(cost) : null, asset_id: action === "out" && asset ? asset : null,
        reason: reason || null, ref: ref || null, notes: notes || null,
      }, { onSuccess: onDone });
    }
  };

  return (
    <form className="form" onSubmit={submit}>
      <div className="form-row">
        <Field label={action === "transfer" ? "Kaynak depo" : "Depo"} hint={`Bu depoda: ${q(current, row.unit)}`}>
          <select value={site} onChange={(e) => setSite(e.target.value)}>
            {sites.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            <option value="">Genel depo</option>
          </select>
        </Field>
        {action === "transfer" && (
          <Field label="Hedef depo">
            <select value={to} onChange={(e) => setTo(e.target.value)} required>
              <option value="" disabled>Seçin</option>
              {sites.data?.filter((s) => s.id !== site).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </Field>
        )}
        <Field label={action === "adjust" ? `Sayılan miktar (${row.unit})` : `Miktar (${row.unit})`}
               hint={action === "adjust" ? "Depoda saydığınız gerçek miktar; fark otomatik yazılır" : undefined}>
          <input inputMode="decimal" value={qty} onChange={(e) => setQty(e.target.value)} required autoFocus />
        </Field>
      </div>
      {action === "in" && (
        <div className="form-row">
          <Field label="Birim fiyat ($)" hint={`Boşsa ortalama: ${usd(row.avg_cost)}`}>
            <input inputMode="decimal" value={cost} onChange={(e) => setCost(e.target.value)} />
          </Field>
          <Field label="Fatura / irsaliye no"><input value={ref} onChange={(e) => setRef(e.target.value)} maxLength={60} /></Field>
        </div>
      )}
      {action === "out" && (
        <Field label="Hangi makinede kullanıldı?" hint="Seçilirse maliyet o makineye yazılır">
          <select value={asset} onChange={(e) => setAsset(e.target.value)}>
            <option value="">Makineye bağlı değil</option>
            {assets.data?.map((a) => <option key={a.id} value={a.id}>{a.code} · {a.manufacturer} {a.model}</option>)}
          </select>
        </Field>
      )}
      {action !== "transfer" && (
        <Field label="Sebep"><input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={60} /></Field>
      )}
      <Field label="Not"><input value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={1000} /></Field>
      <ErrorNote error={m.error} />
      <button className="btn btn-primary" disabled={m.isPending || !qty}>
        {m.isPending ? "Kaydediliyor…" : { in: "Girişi kaydet", out: "Çıkışı kaydet", adjust: "Sayımı kaydet", transfer: "Transfer et" }[action]}
      </button>
    </form>
  );
}

function StockDetail({ row, siteName, onClose }: { row: StockRow; siteName: (id: string | null) => string; onClose: () => void }) {
  const { can } = useAuth();
  const mv = useStockMovements(row.part_id);
  const [action, setAction] = useState<Action | null>(null);
  return (
    <Modal title={row.name} onClose={onClose}>
      <div className="stack">
        <div className="muted small">{categoryLabel(row.category_code)}{row.manufacturer ? ` · ${row.manufacturer}` : ""}{row.part_no ? ` · ${row.part_no}` : ""}</div>
        <dl className="facts">
          <div className="fact"><dt>Toplam</dt><dd>{q(row.qty, row.unit)}</dd></div>
          <div className="fact"><dt>Kritik seviye</dt><dd>{q(row.min_stock, row.unit)}</dd></div>
          <div className="fact"><dt>Değer</dt><dd>{usd(row.value)}</dd></div>
        </dl>
        {can("technician") && (row.min_stock > Number(row.qty) || Number(row.qty) === 0) && (
          <div className="actions">
            <Link className="btn btn-ghost" to={`/satinalma?yeni=${row.part_id}`}>Sipariş talebi aç</Link>
          </div>
        )}
        {(row.sites?.length ?? 0) > 0 && (
          <div className="site-chips">{row.sites!.map((s) => <span key={s.site_id ?? "genel"} className="chip chip-plain">{siteName(s.site_id)}: {q(s.qty, row.unit)}</span>)}</div>
        )}
        {row.is_serialized ? (
          <div className="stack">
            <p className="muted small">Bu kalem seri numarasıyla tek tek izlenir. Stoğa giriş "Parça teslim al" ile, çıkış makineye takarak yapılır.</p>
            <div className="actions">
              {can("technician") && <Link className="btn btn-primary" to={`/kayit?sekme=teslim&kalem=${row.part_id}`}>Teslim al</Link>}
              <Link className="btn btn-ghost" to={`/parcalar?durum=in_stock&q=${encodeURIComponent(row.name)}`}>Stoktakileri gör</Link>
            </div>
          </div>
        ) : (
          <>
            {can("technician") && (
              <div className="seg seg-wrap" role="group" aria-label="Hareket">
                {(["in", "out", "adjust", "transfer"] as const).map((a) => (
                  <button key={a} aria-pressed={action === a} onClick={() => setAction(action === a ? null : a)}>
                    {{ in: "Giriş", out: "Çıkış", adjust: "Sayım", transfer: "Transfer" }[a]}
                  </button>
                ))}
              </div>
            )}
            {action && <MoveForm key={action} row={row} action={action} onDone={() => setAction(null)} />}
            <h3 className="mini-head">Hareketler</h3>
            {mv.isLoading ? <Loading /> : (mv.data?.length ?? 0) === 0 ? <p className="muted">Hareket yok.</p> : (
              <ul className="moves">
                {mv.data!.map((m) => (
                  <li key={m.id}>
                    <span className={`mv-qty ${Number(m.qty) < 0 ? "neg" : "pos"}`}>{Number(m.qty) > 0 ? "+" : ""}{q(m.qty, row.unit)}</span>
                    <span>
                      <strong>{KIND_LABEL[m.kind]}</strong>
                      {m.site_name ? ` · ${m.site_name}` : ""}
                      {m.asset_code && <> · <Link to={`/makine/${m.asset_id}`}>{m.asset_code}</Link></>}
                      {m.reason ? ` · ${m.reason}` : ""}{m.ref ? ` · ${m.ref}` : ""}
                      <span className="muted small"> {dateTime(m.occurred_at)}{m.performed_by_name ? ` · ${m.performed_by_name}` : ""}</span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>
    </Modal>
  );
}

export function StockPage() {
  const [params, setParams] = useSearchParams();
  const f = { category: params.get("tur") ?? "", below: params.get("kritik") === "1", q: params.get("q") ?? "", all: params.get("tumu") === "1" };
  const stock = useStock({ category: f.category || undefined, below: f.below, q: f.q || undefined });
  const sites = useSites();
  const siteName = (id: string | null) => (id ? sites.data?.find((s) => s.id === id)?.name ?? "Depo" : "Genel depo");
  const openId = params.get("kalem");
  const open = stock.data?.find((r) => r.part_id === openId);
  const set = (k: string, v: string) => {
    const n = new URLSearchParams(params);
    if (v) n.set(k, v); else n.delete(k);
    setParams(n, { replace: true });
  };
  const allRows = stock.data ?? [];
  // Stoğu olmayan ve kritik seviyesi tanımlanmamış kalemler (ör. hiç stoklanmayan silindirler) varsayılan olarak gizli
  const rows = f.all ? allRows : allRows.filter((r) => Number(r.qty) !== 0 || r.min_stock > 0);
  const hidden = allRows.length - rows.length;
  const totalValue = rows.reduce((s, r) => s + Number(r.value ?? 0), 0);

  return (
    <>
      <div className="page-head">
        <h1>Stok</h1>
        <span className="muted">Toplam stok değeri: <strong>{usd(totalValue)}</strong></span>
      </div>
      <Panel>
        <div className="filters">
          <input type="search" placeholder="Kalem adı veya parça no" value={f.q} onChange={(e) => set("q", e.target.value)} aria-label="Ara" />
          <select value={f.category} onChange={(e) => set("tur", e.target.value)} aria-label="Tür">
            <option value="">Tüm türler</option>
            {Object.entries(CATEGORY_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <label className="inline-check"><input type="checkbox" checked={f.below} onChange={(e) => set("kritik", e.target.checked ? "1" : "")} /> Yalnızca kritik seviye altı</label>
          <label className="inline-check"><input type="checkbox" checked={f.all} onChange={(e) => set("tumu", e.target.checked ? "1" : "")} /> Stoğu olmayanları da göster{!f.all && hidden > 0 ? ` (${hidden})` : ""}</label>
        </div>
        {stock.isLoading ? <Loading /> : stock.error ? <ErrorNote error={stock.error} /> : rows.length === 0 ? (
          <Empty>Bu filtrelere uyan kalem yok.</Empty>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Kalem</th><th>Tür</th><th>Depolar</th><th className="num">Toplam</th><th className="num">Kritik seviye</th>
                  <th className="num">Son 90 gün kullanım</th><th className="num">Değer</th><th>Durum</th></tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.part_id} onClick={() => set("kalem", r.part_id)}>
                    <td><strong>{r.name}</strong><div className="muted small">{[r.manufacturer, r.part_no].filter(Boolean).join(" · ")}</div></td>
                    <td>{categoryLabel(r.category_code)}{r.is_serialized && <div className="muted small">seri numaralı</div>}</td>
                    <td className="small">{(r.sites ?? []).map((s) => `${siteName(s.site_id)}: ${q(s.qty, r.unit)}`).join(" · ") || "–"}</td>
                    <td className="num"><strong>{q(r.qty, r.unit)}</strong></td>
                    <td className="num">{r.min_stock ? q(r.min_stock, r.unit) : "–"}</td>
                    <td className="num">{r.is_serialized ? "–" : q(r.used_90d, r.unit)}</td>
                    <td className="num">{usd(r.value)}</td>
                    <td>{r.min_stock > 0 ? (r.below_min ? <BandChip band="watch">Kritik altı</BandChip> : <BandChip band="ok">Yeterli</BandChip>) : <span className="muted">–</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      {open && <StockDetail row={open} siteName={siteName} onClose={() => set("kalem", "")} />}
    </>
  );
}
