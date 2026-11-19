import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { usePurchasing, useOrders, useSuggestions, useSuppliers } from "../api/hooks";
import type { PoStatus, Suggestion } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import { BandChip, Empty, ErrorNote, Field, Loading, Panel } from "../components/ui";
import { categoryLabel, date, num, num1, usd } from "../lib/format";

export const PO_STATUS: Record<PoStatus, { label: string; band: "unknown" | "watch" | "ok" | "critical" }> = {
  draft: { label: "Talep", band: "unknown" },
  ordered: { label: "Sipariş verildi", band: "watch" },
  partial: { label: "Kısmen teslim alındı", band: "watch" },
  received: { label: "Teslim alındı", band: "ok" },
  cancelled: { label: "İptal", band: "unknown" },
};
const qty = (v: number, unit: string) => `${Number.isInteger(Number(v)) ? num(v) : num1(v)} ${unit}`;

// ---------- Öneriler ----------
function Suggestions() {
  const s = useSuggestions();
  const { create } = usePurchasing();
  const navigate = useNavigate();
  const [picked, setPicked] = useState<Record<string, string>>({}); // part_id → miktar
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  // İlk yüklemede acil önerileri seçili getir
  useEffect(() => {
    if (s.data && Object.keys(picked).length === 0) {
      setPicked(Object.fromEntries(s.data.filter((x) => x.urgent).map((x) => [x.part_id, String(x.suggested_qty)])));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [s.data]);

  const chosen = (s.data ?? []).filter((x) => picked[x.part_id] !== undefined && Number(picked[x.part_id].replace(",", ".")) > 0);
  // Tedarikçiye göre gruplanır: her tedarikçi için ayrı talep
  const groups = useMemo(() => {
    const g = new Map<string, { supplier_id: string | null; supplier_name: string; items: Suggestion[] }>();
    for (const x of chosen) {
      const k = x.supplier_id ?? "none";
      if (!g.has(k)) g.set(k, { supplier_id: x.supplier_id, supplier_name: x.supplier_name ?? "Tedarikçi seçilmemiş", items: [] });
      g.get(k)!.items.push(x);
    }
    return [...g.values()];
  }, [chosen]);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const made = [];
      for (const g of groups) {
        made.push(await create.mutateAsync({
          supplier_id: g.supplier_id, notes: "Satınalma önerilerinden",
          lines: g.items.map((x) => ({ part_id: x.part_id, qty: Number(picked[x.part_id].replace(",", ".")), unit_cost: x.unit_cost })),
        }));
      }
      navigate(made.length === 1 ? `/satinalma/${made[0].id}` : "/satinalma?sekme=belgeler");
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  if (s.isLoading) return <Loading />;
  if (s.error) return <ErrorNote error={s.error} />;
  if (!s.data?.length) return <Empty>Şu an alınması gereken bir şey yok: stoklar kritik seviyenin üstünde, yaklaşan değişimler karşılanıyor.</Empty>;

  return (
    <div className="stack">
      <p className="muted small">
        Önerilen miktar = kritik seviye + 1.000 saat içinde değişecek lastikler − stoktaki − yoldaki (verilmiş siparişler).
        Değişimler yapıldıktan sonra stok yine kritik seviyenin üstünde kalır.
      </p>
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th aria-label="Seç" /><th>Kalem</th><th>Neden</th><th className="num">Önerilen</th><th className="num">Sipariş miktarı</th><th>Son tedarikçi</th><th className="num">Son fiyat</th></tr></thead>
          <tbody>
            {s.data.map((x) => (
              <tr key={x.part_id} className={x.upcoming ? "row-urgent" : ""}>
                <td><input type="checkbox" checked={picked[x.part_id] !== undefined} aria-label={`${x.name} seç`}
                           onChange={(e) => setPicked((p) => {
                             const n = { ...p };
                             if (e.target.checked) n[x.part_id] = String(x.suggested_qty); else delete n[x.part_id];
                             return n;
                           })} /></td>
                <td><strong>{x.name}</strong><div className="muted small">{categoryLabel(x.category_code)}</div></td>
                <td className="small">{x.reasons.map((r, i) => <div key={i}>{r}</div>)}</td>
                <td className="num">{qty(x.suggested_qty, x.unit)}</td>
                <td className="num">
                  <input className="qty-input" inputMode="decimal" value={picked[x.part_id] ?? ""} placeholder="–"
                         aria-label={`${x.name} miktar`}
                         onChange={(e) => setPicked((p) => ({ ...p, [x.part_id]: e.target.value }))} />
                </td>
                <td className="small">{x.supplier_name ?? <span className="muted">–</span>}</td>
                <td className="num">{usd(x.unit_cost)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {groups.length > 0 && (
        <div className="suggest-foot">
          <div className="small">
            {groups.length === 1 ? "1 talep oluşturulacak" : `${groups.length} talep oluşturulacak (tedarikçi başına bir)`}:
            {" "}{groups.map((g) => `${g.supplier_name} (${g.items.length} kalem)`).join(", ")}
          </div>
          <button className="btn btn-primary" onClick={submit} disabled={busy}>{busy ? "Oluşturuluyor…" : "Talep oluştur"}</button>
        </div>
      )}
      <ErrorNote error={error} />
    </div>
  );
}

// ---------- Belgeler ----------
function Orders() {
  const [status, setStatus] = useState<PoStatus | "">("");
  const o = useOrders(status || undefined);
  const navigate = useNavigate();
  return (
    <div className="stack">
      <div className="filters">
        <select value={status} onChange={(e) => setStatus(e.target.value as PoStatus | "")} aria-label="Durum">
          <option value="">Tüm durumlar</option>
          {Object.entries(PO_STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
        </select>
      </div>
      {o.isLoading ? <Loading /> : (o.data?.length ?? 0) === 0 ? <Empty>Belge yok.</Empty> : (
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Belge</th><th>Tedarikçi</th><th>Durum</th><th className="num">Kalem</th><th className="num">Tutar</th><th>Beklenen</th><th>Oluşturma</th></tr></thead>
            <tbody>
              {o.data!.map((p) => (
                <tr key={p.id} onClick={() => navigate(`/satinalma/${p.id}`)}>
                  <td><Link to={`/satinalma/${p.id}`} onClick={(e) => e.stopPropagation()}><strong>{p.number}</strong></Link></td>
                  <td>{p.supplier_name ?? <span className="muted">seçilmemiş</span>}</td>
                  <td><BandChip band={PO_STATUS[p.status].band}>{PO_STATUS[p.status].label}</BandChip></td>
                  <td className="num">{p.lines}</td>
                  <td className="num">{usd(p.total)}</td>
                  <td className={p.late ? "t-critical" : ""}>{p.expected_date ? date(p.expected_date) : "–"}{p.late ? " · gecikti" : ""}</td>
                  <td className="small">{date(p.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ---------- Tedarikçiler ----------
function Suppliers() {
  const s = useSuppliers();
  const { can } = useAuth();
  const { createSupplier } = usePurchasing();
  const [f, setF] = useState({ name: "", contact: "", phone: "", email: "" });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    createSupplier.mutate({ name: f.name, contact: f.contact || null, phone: f.phone || null, email: f.email || null },
      { onSuccess: () => setF({ name: "", contact: "", phone: "", email: "" }) });
  };
  return (
    <div className="stack">
      {s.isLoading ? <Loading /> : (s.data?.length ?? 0) === 0 ? <Empty>Henüz tedarikçi yok.</Empty> : (
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Tedarikçi</th><th>İlgili kişi</th><th>Telefon</th><th>E-posta</th><th className="num">Belge</th></tr></thead>
            <tbody>
              {s.data!.map((x) => (
                <tr key={x.id}><td><strong>{x.name}</strong></td><td>{x.contact ?? "–"}</td><td>{x.phone ?? "–"}</td>
                  <td>{x.email ?? "–"}</td><td className="num">{x.orders}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {can("manager") && (
        <form className="form narrow-form" onSubmit={submit}>
          <h3 className="mini-head">Tedarikçi ekle</h3>
          <div className="form-row">
            <Field label="Ad"><input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required /></Field>
            <Field label="İlgili kişi"><input value={f.contact} onChange={(e) => setF({ ...f, contact: e.target.value })} /></Field>
          </div>
          <div className="form-row">
            <Field label="Telefon"><input value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} /></Field>
            <Field label="E-posta"><input type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
          </div>
          <ErrorNote error={createSupplier.error} />
          <div><button className="btn btn-primary" disabled={createSupplier.isPending}>Ekle</button></div>
        </form>
      )}
    </div>
  );
}

const TABS = [
  { key: "oneriler", label: "Öneriler", el: Suggestions, hint: "Kritik seviyenin altındaki kalemler ve yaklaşan lastik değişimleri" },
  { key: "belgeler", label: "Talepler ve siparişler", el: Orders, hint: "Talep → sipariş → teslim alma" },
  { key: "tedarikciler", label: "Tedarikçiler", el: Suppliers, hint: "" },
];

export function PurchasingPage() {
  const [params, setParams] = useSearchParams();
  const active = TABS.find((t) => t.key === params.get("sekme")) ?? TABS[0];
  const Body = active.el;
  return (
    <>
      <div className="page-head"><h1>Satınalma</h1></div>
      <div className="tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t.key} role="tab" aria-selected={t.key === active.key} onClick={() => setParams({ sekme: t.key })}>{t.label}</button>
        ))}
      </div>
      <Panel title={active.label} sub={active.hint || undefined}><Body /></Panel>
    </>
  );
}
