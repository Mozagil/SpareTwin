// Üretim: ürün ağaçları (solda ürünler, sağda seçilen ürünün çok seviyeli ağacı ve rotası), üretim emirleri, raporlar.
import { useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { useSearchParams } from "react-router";
import { download } from "../api/client";
import { useCatalogParts, useProductBom, useProductBomActions, useProductBoms } from "../api/hooks";
import type { ProductBomImportResult } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import { Empty, ErrorNote, Field, Loading, Modal, Panel } from "../components/ui";
import { num, num1, usd } from "../lib/format";
import { flatten, leafTotals } from "../lib/production";
import { OperationReportPanel, OrderModal, OrdersPanel } from "./ProductionOrdersPanel";
import { BuildablePanel } from "./BuildablePanel";
import { CostReportPanel } from "./ProductionCost";
import { ScrapReportPanel } from "./ProductionScrap";
import { RoutePanel } from "./RoutePanel";

type Tab = "agaclar" | "emirler" | "rapor";
const TABS: { key: Tab; label: string }[] = [
  { key: "agaclar", label: "Ürün ağaçları" }, { key: "emirler", label: "Üretim emirleri" }, { key: "rapor", label: "Raporlar" },
];

const qty = (v: number | string, unit: string | null) => `${Number.isInteger(Number(v)) ? num(Number(v)) : num1(Number(v))} ${unit ?? ""}`.trim();

export function ProductionPage() {
  const [params, setParams] = useSearchParams();
  const tab = (params.get("sekme") as Tab | null) ?? "agaclar";
  const openId = params.get("emir");
  const set = (k: string, v: string) => { const n = new URLSearchParams(params); if (v) n.set(k, v); else n.delete(k); setParams(n, { replace: true }); };
  return (
    <>
      <div className="page-head"><h1>Üretim</h1></div>
      <div className="tabs" role="tablist">
        {TABS.map((t) => <button key={t.key} role="tab" aria-selected={t.key === tab} onClick={() => setParams(t.key === "agaclar" ? {} : { sekme: t.key }, { replace: true })}>{t.label}</button>)}
      </div>
      {tab === "agaclar" && <BomsPanel />}
      {tab === "emirler" && <OrdersPanel onOpen={(id) => set("emir", id)} />}
      {tab === "rapor" && <div className="stack prod-reports"><CostReportPanel /><OperationReportPanel /><ScrapReportPanel /></div>}
      {openId && <OrderModal id={openId} onClose={() => set("emir", "")} />}
    </>
  );
}

function BomsPanel() {
  const { can } = useAuth();
  const edit = can("manager");
  const [params, setParams] = useSearchParams();
  const boms = useProductBoms();
  const catalog = useCatalogParts();
  const { create, importFile } = useProductBomActions();
  const [newPart, setNewPart] = useState("");
  const [result, setResult] = useState<ProductBomImportResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [dlError, setDlError] = useState<unknown>(null);
  const input = useRef<HTMLInputElement>(null);

  const rows = boms.data ?? [];
  const selected = params.get("agac") ?? rows[0]?.id ?? "";
  const select = (id: string) => setParams(id ? { agac: id } : {}, { replace: true });
  const taken = new Set(rows.map((r) => r.part_id));

  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate({ part_id: newPart }, { onSuccess: (b) => { setNewPart(""); select(b.id); } });
  };
  const onFile = (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (f) importFile.mutate(f, { onSuccess: setResult });
  };
  const getTemplate = async () => {
    setBusy(true);
    setDlError(null);
    try {
      await download("/production/boms/template", "sparetwin-urun-agaci.xlsx");
    } catch (err) {
      setDlError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
      <div className="prod">
        <Panel title="Ürün ağaçları" sub="Ürettiğiniz kalem hangi parçalardan, kaçar birim oluşur">
          {boms.isLoading ? <Loading /> : boms.error ? <ErrorNote error={boms.error} /> : rows.length === 0 ? (
            <Empty>Henüz ürün ağacı yok.{edit ? " Aşağıdan bir ürün seçin ya da Excel'den içe aktarın." : ""}</Empty>
          ) : (
            <ul className="prod-list">
              {rows.map((b) => (
                <li key={b.id}>
                  <button type="button" aria-current={b.id === selected} onClick={() => select(b.id)}>
                    <span><strong>{b.name}</strong>
                      <span className="muted small">{[b.part_no, b.is_subassembly ? "alt montaj" : null, `${num(b.line_count)} bileşen`,
                        b.line_count > 0 ? (b.can_build > 0 ? `${num(b.can_build)} ${b.unit ?? "adet"} üretilebilir` : "stok yetmiyor") : null].filter(Boolean).join(" · ")}</span></span>
                    <span className="num">{usd(Number(b.material_cost))}{b.unknown_cost > 0 && <sup title="Maliyeti bilinmeyen bileşen var">*</sup>}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {edit && (
            <>
              <form className="form" onSubmit={submit}>
                <h3 className="mini-head">Yeni ürün ağacı</h3>
                <Field label="Üretilen kalem" hint="Listede yoksa önce Kayıt › Katalog kalemi'nden ekleyin">
                  <select value={newPart} onChange={(e) => setNewPart(e.target.value)} required>
                    <option value="">Seçin</option>
                    {catalog.data?.filter((p) => !taken.has(p.id)).map((p) => (
                      <option key={p.id} value={p.id}>{p.name}{p.part_no ? ` · ${p.part_no}` : ""}</option>
                    ))}
                  </select>
                </Field>
                <ErrorNote error={create.error} />
                <div className="actions"><button className="btn btn-primary" disabled={!newPart || create.isPending}>Ürün ağacı aç</button></div>
              </form>
              <div className="form">
                <h3 className="mini-head">Excel'den içe aktar</h3>
                <div className="lib-actions">
                  <button type="button" className="btn btn-small" onClick={getTemplate} disabled={busy}>{busy ? "İndiriliyor…" : "Şablonu indir"}</button>
                  <button type="button" className="btn btn-small" onClick={() => input.current?.click()} disabled={importFile.isPending}>
                    {importFile.isPending ? "Yükleniyor…" : "Dosya seç ve içe aktar"}</button>
                  <input ref={input} type="file" accept=".xlsx" hidden onChange={onFile} />
                </div>
                <p className="muted small">Sütunlar: Ürün parça no, Bileşen parça no, Miktar, Not. Alt montajlar aynı dosyada yazılır. Hata varsa hiçbir satır yazılmaz.</p>
                <ErrorNote error={importFile.error ?? dlError} />
                {result && result.errors.length === 0 && (
                  <div className="success-note" role="status">
                    {num(result.added)} satır eklendi{result.boms_created ? `, ${num(result.boms_created)} yeni ürün ağacı açıldı` : ""}
                    {result.existing ? `, ${num(result.existing)} satır zaten vardı` : ""}.
                  </div>
                )}
                {result && result.errors.length > 0 && (
                  <div className="error-note" role="alert">
                    <strong>Dosyada {num(result.errors.length)} hata var; hiçbir satır eklenmedi.</strong>
                    <ul>{result.errors.slice(0, 12).map((e) => <li key={e.row}>{e.row}. satır: {e.message}</li>)}</ul>
                    {result.errors.length > 12 && <span className="small">… ve {num(result.errors.length - 12)} satır daha</span>}
                  </div>
                )}
              </div>
            </>
          )}
        </Panel>
        {selected && rows.some((r) => r.id === selected) && <BomDetail key={selected} id={selected} edit={edit} onDeleted={() => select("")} onOpen={(partId) => {
          const target = rows.find((r) => r.part_id === partId);
          if (target) select(target.id);
        }} />}
      </div>
  );
}

function BomDetail({ id, edit, onDeleted, onOpen }: { id: string; edit: boolean; onDeleted: () => void; onOpen: (partId: string) => void }) {
  const bom = useProductBom(id);
  const catalog = useCatalogParts();
  const { addLine, removeLine, remove } = useProductBomActions();
  const [partId, setPartId] = useState("");
  const [amount, setAmount] = useState("1");
  const [closed, setClosed] = useState<Set<string>>(new Set());
  const [confirm, setConfirm] = useState(false);

  if (bom.isLoading) return <Panel><Loading /></Panel>;
  if (bom.error || !bom.data) return <Panel><ErrorNote error={bom.error} /></Panel>;
  const b = bom.data;
  const flat = flatten(b.lines, closed);
  const leaves = leafTotals(b.lines);
  const short = leaves.filter((l) => l.in_stock < l.qty);
  const part = catalog.data?.find((p) => p.id === partId);
  const direct = new Set(b.lines.map((l) => l.part_id));
  const n = Number(amount.replace(",", "."));
  const toggle = (path: string) => {
    const next = new Set(closed);
    if (next.has(path)) next.delete(path); else next.add(path);
    setClosed(next);
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    addLine.mutate({ bomId: id, part_id: partId, qty: n }, { onSuccess: () => { setPartId(""); setAmount("1"); } });
  };

  return (
    <Panel title={b.name ?? "Ürün ağacı"}
           sub={[b.part_no, b.used_in.length ? `şurada kullanılıyor: ${b.used_in.map((u) => u.name).join(", ")}` : null].filter(Boolean).join(" · ") || undefined}
           actions={edit ? <button type="button" className="btn btn-small" onClick={() => setConfirm(true)}>Ağacı sil</button> : undefined}>
      <dl className="facts">
        <div className="fact"><dt>Malzeme maliyeti (1 {b.unit ?? "adet"})</dt><dd>{usd(Number(b.material_cost))}</dd></div>
        <div className="fact"><dt>Satın alınan kalem</dt><dd>{num(leaves.length)}</dd></div>
        <div className="fact"><dt>Stoku 1 ürüne yetmeyen</dt><dd className={short.length ? "t-watch" : undefined}>{num(short.length)}</dd></div>
      </dl>
      {b.unknown_cost > 0 && <p className="muted small">* {num(b.unknown_cost)} bileşenin maliyeti bilinmiyor (stok girişi ya da liste fiyatı yok); toplamda sıfır sayıldı.</p>}
      {flat.length === 0 ? <Empty>Ağaç boş.{edit ? " Aşağıdan bileşen ekleyin." : ""}</Empty> : (
        <div className="table-wrap">
          <table className="table lib-table prod-table">
            <thead><tr><th>Bileşen</th><th className="num">Miktar</th><th className="num">Toplam</th><th className="num">Stokta</th>
              <th className="num">Birim maliyet</th><th className="num">Tutar</th><th /></tr></thead>
            <tbody>
              {flat.map((l) => (
                <tr key={l.path}>
                  <td style={{ paddingLeft: 10 + l.depth * 22 }}>
                    {l.has_bom ? (
                      <button type="button" className="prod-toggle" aria-expanded={!closed.has(l.path)} aria-label={`${l.name} alt montajını aç/kapat`}
                              onClick={() => toggle(l.path)}>{closed.has(l.path) ? "▸" : "▾"}</button>
                    ) : <span className="prod-toggle" aria-hidden="true" />}
                    <strong>{l.name}</strong>
                    <div className="muted small prod-sub">
                      {[l.part_no, l.notes].filter(Boolean).join(" · ")}
                      {l.has_bom && <> {l.part_no || l.notes ? "· " : ""}<button type="button" className="link-btn" onClick={() => onOpen(l.part_id)}>alt montaj</button></>}
                    </div>
                  </td>
                  <td className="num">{qty(l.qty, l.unit)}</td>
                  <td className="num">{qty(l.total_qty, l.unit)}</td>
                  <td className="num">{Number(l.in_stock) >= Number(l.total_qty) ? qty(l.in_stock, l.unit)
                    : <span className="t-watch">{Number(l.in_stock) > 0 ? qty(l.in_stock, l.unit) : "yok"}</span>}</td>
                  <td className="num">{l.unit_cost == null ? <span className="muted">bilinmiyor</span> : usd(Number(l.unit_cost))}</td>
                  <td className="num">{usd(Number(l.cost))}</td>
                  <td className="row-actions">{edit && l.depth === 0 && (
                    <button type="button" className="icon-btn" aria-label={`${l.name} satırını sil`} disabled={removeLine.isPending}
                            onClick={() => removeLine.mutate({ bomId: id, lineId: l.line_id })}>×</button>)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot><tr><td colSpan={5}>Malzeme maliyeti</td><td className="num">{usd(Number(b.material_cost))}</td><td /></tr></tfoot>
          </table>
        </div>
      )}
      <ErrorNote error={removeLine.error} />
      {b.lines.length > 0 && <BuildablePanel bomId={id} name={b.name} unit={b.unit} />}
      <RoutePanel bomId={id} unit={b.unit} edit={edit} />
      {edit && (
        <form className="form" onSubmit={submit}>
          <h3 className="mini-head">Bileşen ekle</h3>
          <div className="form-row">
            <Field label="Katalog kalemi" hint="Kendi ürün ağacı olan kalem alt montaj olarak açılır">
              <select value={partId} onChange={(e) => setPartId(e.target.value)} required>
                <option value="">Seçin</option>
                {catalog.data?.filter((p) => p.id !== b.part_id && !direct.has(p.id)).map((p) => (
                  <option key={p.id} value={p.id}>{p.category_name} · {p.name}{p.part_no ? ` · ${p.part_no}` : ""}</option>
                ))}
              </select>
            </Field>
            <Field label={`Miktar${part ? ` (${part.unit})` : ""}`} hint={`1 ${b.unit ?? "adet"} ürün için`}>
              <input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
            </Field>
          </div>
          <ErrorNote error={addLine.error} />
          <div className="actions"><button className="btn btn-primary" disabled={!partId || !(n > 0) || addLine.isPending}>Bileşen ekle</button></div>
        </form>
      )}
      {confirm && (
        <Modal title="Ürün ağacı silinsin mi?" onClose={() => setConfirm(false)}
               footer={<>
                 <button type="button" className="btn" onClick={() => setConfirm(false)}>Vazgeç</button>
                 <button type="button" className="btn btn-primary" disabled={remove.isPending}
                         onClick={() => remove.mutate(id, { onSuccess: onDeleted })}>Sil</button>
               </>}>
          <p>{b.name} ürün ağacı ve {num(b.lines.length)} satırı silinir. Katalog kalemi ve stok etkilenmez.</p>
          <ErrorNote error={remove.error} />
        </Modal>
      )}
    </Panel>
  );
}
