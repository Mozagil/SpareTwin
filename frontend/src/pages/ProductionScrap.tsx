// Fire ve hurda: emrin malzemeleri (plan / kullanılan), emri tamamlama formu, fire ve hurda raporu.
import { useState, type FormEvent } from "react";
import { useProductionOrderActions, useScrapReport, useSites } from "../api/hooks";
import type { ProductionMaterial, ProductionOrder, ScrapReason } from "../api/types";
import { Empty, ErrorNote, Field, Loading, Panel } from "../components/ui";
import { num, num1, pct, usd } from "../lib/format";
import { SCRAP_REASONS, SCRAP_REASON_LABEL, waste } from "../lib/production";

const qty = (v: number | string, unit: string | null) => `${Number.isInteger(Number(v)) ? num(Number(v)) : num1(Number(v))} ${unit ?? ""}`.trim();
const parse = (s: string) => (s.trim() === "" ? NaN : Number(s.replace(",", ".")));
const text = (v: number | string) => String(Number(v)).replace(".", ",");

/** Plandan sapma: fazlası fire (izleme), azı tasarruf (yeşil). */
function Waste({ planned, actual, unit }: { planned: number | string; actual: number | string; unit: string | null }) {
  const w = waste(planned, actual);
  if (w.diff === 0) return <span className="muted">yok</span>;
  return <span className={w.diff > 0 ? "t-watch" : "t-ok"}>{w.diff > 0 ? "+" : "−"}{qty(Math.abs(w.diff), unit)} (%{num(Math.abs(w.pct))})</span>;
}

function ReasonSelect({ value, onChange, label }: { value: string; onChange: (v: string) => void; label: string }) {
  return (
    <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)} required>
      <option value="">Sebep seçin</option>
      {SCRAP_REASONS.map((r) => <option key={r} value={r}>{SCRAP_REASON_LABEL[r]}</option>)}
    </select>
  );
}

/** Emrin malzemeleri: açık emirde plan, tamamlanmış emirde kullanılan ve fire. */
export function MaterialsTable({ materials, done }: { materials: ProductionMaterial[]; done: boolean }) {
  if (materials.length === 0) return null;
  return (
    <div className="table-wrap prod-mats">
      <table className="table lib-table op-table">
        <thead><tr><th>Malzeme</th><th className="num">Planlanan</th>
          {done ? <><th className="num">Kullanılan</th><th className="num">Fire</th><th>Sebep</th></> : <th className="num">Stokta</th>}</tr></thead>
        <tbody>
          {materials.map((m) => (
            <tr key={m.part_id}>
              <td><strong>{m.name}</strong><div className="muted small">{m.part_no}</div></td>
              <td className="num" data-label="Planlanan">{qty(m.planned_qty, m.unit)}</td>
              {done && m.actual_qty != null ? <>
                <td className="num" data-label="Kullanılan">{qty(m.actual_qty, m.unit)}
                  {!m.stock_moved && Number(m.actual_qty) > 0 && <div className="muted small">stoktan düşülmedi</div>}</td>
                <td className="num" data-label="Fire"><Waste planned={m.planned_qty} actual={m.actual_qty} unit={m.unit} /></td>
                <td data-label="Sebep">{m.reason ? SCRAP_REASON_LABEL[m.reason] : <span className="muted">–</span>}</td>
              </> : (
                <td className="num" data-label="Stokta">
                  {Number(m.in_stock) >= Number(m.planned_qty) ? qty(m.in_stock, m.unit) : <span className="t-watch">{qty(m.in_stock, m.unit)}</span>}</td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Emri tamamla: depo, sağlam / hurda ürün, malzeme başına kullanılan miktar. Stok bu adımda işlenir. */
export function FinishForm({ order: o, onCancel }: { order: ProductionOrder; onCancel: () => void }) {
  const sites = useSites();
  const { finish } = useProductionOrderActions();
  const [siteId, setSiteId] = useState<string | null>(null);
  const [good, setGood] = useState(text(o.qty));
  const [scrap, setScrap] = useState("0");
  const [scrapReason, setScrapReason] = useState("");
  const [used, setUsed] = useState<Record<string, string>>(() => Object.fromEntries(o.materials.map((m) => [m.part_id, text(m.planned_qty)])));
  const [reasons, setReasons] = useState<Record<string, string>>({});
  // Depo seçilmediyse ilk depo; hiç depo yoksa "depo belirtilmemiş"
  const site = siteId ?? sites.data?.[0]?.id ?? "";
  const g = parse(good), s = parse(scrap);
  const at = (m: ProductionMaterial) => Number(m.stock_sites.find((x) => (x.site_id ?? "") === site)?.qty ?? 0);
  const short = o.materials.filter((m) => !m.is_serialized && parse(used[m.part_id] ?? "") > at(m));
  const valid = g >= 0 && s >= 0 && g + s > 0 && o.materials.every((m) => parse(used[m.part_id] ?? "") >= 0);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    finish.mutate({
      orderId: o.id, site_id: site || null, good_qty: g, scrap_qty: s, scrap_reason: s > 0 ? (scrapReason as ScrapReason) : null,
      materials: o.materials.map((m) => {
        const a = parse(used[m.part_id] ?? "");
        return { part_id: m.part_id, actual_qty: a, reason: a > Number(m.planned_qty) ? ((reasons[m.part_id] || null) as ScrapReason | null) : null };
      }),
    });
  };

  return (
    <form className="form finish-form" onSubmit={submit}>
      <h3 className="mini-head">Emri tamamla</h3>
      <div className="form-row">
        <Field label="Depo" hint="Malzeme buradan düşer, ürün buraya girer">
          <select value={site} onChange={(e) => setSiteId(e.target.value)}>
            {sites.data?.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
            <option value="">Depo belirtilmemiş</option>
          </select>
        </Field>
        <Field label={`Sağlam ürün (${o.unit})`}>
          <input inputMode="decimal" value={good} onChange={(e) => setGood(e.target.value)} />
        </Field>
        <Field label={`Hurda ürün (${o.unit})`}>
          <input inputMode="decimal" value={scrap} onChange={(e) => setScrap(e.target.value)} />
        </Field>
        {s > 0 && <Field label="Hurda sebebi"><ReasonSelect label="Hurda sebebi" value={scrapReason} onChange={setScrapReason} /></Field>}
      </div>
      {o.materials.length > 0 && (
        <div className="table-wrap">
          <table className="table lib-table op-table">
            <thead><tr><th>Malzeme</th><th className="num">Planlanan</th><th className="num">Depoda</th><th className="num">Kullanılan</th><th>Fire</th></tr></thead>
            <tbody>
              {o.materials.map((m) => {
                const a = parse(used[m.part_id] ?? "");
                const over = a > Number(m.planned_qty);
                return (
                  <tr key={m.part_id}>
                    <td><strong>{m.name}</strong><div className="muted small">{m.part_no}</div></td>
                    <td className="num" data-label="Planlanan">{qty(m.planned_qty, m.unit)}</td>
                    <td className="num" data-label="Depoda">{m.is_serialized ? <span className="muted">seri no ile izlenir</span>
                      : <span className={a > at(m) ? "t-critical" : undefined}>{qty(at(m), m.unit)}</span>}</td>
                    <td className="num" data-label="Kullanılan">
                      <input className="finish-qty" inputMode="decimal" aria-label={`${m.name}: kullanılan miktar`} value={used[m.part_id] ?? ""}
                             onChange={(e) => { setUsed({ ...used, [m.part_id]: e.target.value }); finish.reset(); }} /></td>
                    <td data-label="Fire">{!(a >= 0) ? <span className="muted">–</span> : over ? (
                      <span className="finish-reason"><Waste planned={m.planned_qty} actual={a} unit={m.unit} />
                        <ReasonSelect label={`${m.name}: fire sebebi`} value={reasons[m.part_id] ?? ""} onChange={(v) => setReasons({ ...reasons, [m.part_id]: v })} /></span>
                    ) : <Waste planned={m.planned_qty} actual={a} unit={m.unit} />}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {short.length > 0 && <p className="t-critical small" role="status">Seçilen depoda {num(short.length)} malzemenin stoku yetmiyor; emir bu hâliyle tamamlanmaz.</p>}
      <p className="muted small">Kullanılan malzeme stoktan düşer, sağlam ürün stoğa girer. Seri numarasıyla izlenen kalemlerde stok hareketi yapılmaz.</p>
      <ErrorNote error={finish.error} />
      <div className="actions">
        <button type="button" className="btn" onClick={onCancel}>Vazgeç</button>
        <button className="btn btn-primary" disabled={!valid || finish.isPending}>Tamamla ve stoğa işle</button>
      </div>
    </form>
  );
}

const PERIODS = [3, 6, 12, 24];

export function ScrapReportPanel() {
  const [months, setMonths] = useState(12);
  const report = useScrapReport(months);
  const r = report.data;
  const empty = !!r && r.products.length === 0 && r.materials.length === 0;
  // Plana uyan malzemeler tabloyu doldurmasın: yalnızca sapanlar listelenir
  const off = r?.materials.filter((m) => Number(m.actual_qty) !== Number(m.planned_qty)) ?? [];

  return (
    <Panel title="Fire ve hurda" sub="Tamamlanan emirlerde hurda ürün ve plana göre malzeme kullanımı"
           actions={<div className="seg" role="group" aria-label="Dönem">
             {PERIODS.map((m) => <button key={m} type="button" aria-pressed={m === months} onClick={() => setMonths(m)}>{m} ay</button>)}
           </div>}>
      {report.isLoading ? <Loading /> : report.error || !r ? <ErrorNote error={report.error} /> : empty ? (
        <Empty>Bu dönemde fire ya da hurda kaydı olan emir yok.</Empty>
      ) : (
        <div className="stack scrap-report">
          <h3 className="mini-head">Ürün hurdası</h3>
          <div className="table-wrap">
            <table className="table lib-table">
              <thead><tr><th>Ürün</th><th className="num">Emir</th><th className="num">Planlanan</th><th className="num">Sağlam</th>
                <th className="num">Hurda</th><th className="num">Hurda oranı</th></tr></thead>
              <tbody>
                {r.products.map((p) => {
                  const total = Number(p.good_qty) + Number(p.scrap_qty);
                  const rate = total > 0 ? (Number(p.scrap_qty) / total) * 100 : null;
                  return (
                    <tr key={p.part_id}>
                      <td><strong>{p.name}</strong><div className="muted small">{p.part_no}</div></td>
                      <td className="num">{num(p.order_count)}</td>
                      <td className="num">{qty(p.planned_qty, p.unit)}</td>
                      <td className="num">{qty(p.good_qty, p.unit)}</td>
                      <td className="num">{Number(p.scrap_qty) > 0 ? qty(p.scrap_qty, p.unit) : <span className="muted">yok</span>}</td>
                      <td className={`num ${rate ? "t-watch" : ""}`}>{pct(rate)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {off.length > 0 && <>
            <h3 className="mini-head">Malzeme firesi</h3>
            <div className="table-wrap">
              <table className="table lib-table">
                <thead><tr><th>Malzeme</th><th className="num">Emir</th><th className="num">Planlanan</th><th className="num">Kullanılan</th>
                  <th className="num">Fire</th><th className="num">Fire tutarı</th></tr></thead>
                <tbody>
                  {off.map((m) => (
                    <tr key={m.part_id}>
                      <td><strong>{m.name}</strong><div className="muted small">{m.part_no}</div></td>
                      <td className="num">{num(m.order_count)}</td>
                      <td className="num">{qty(m.planned_qty, m.unit)}</td>
                      <td className="num">{qty(m.actual_qty, m.unit)}</td>
                      <td className="num"><Waste planned={m.planned_qty} actual={m.actual_qty} unit={m.unit} /></td>
                      <td className="num">{m.waste_cost == null || Number(m.waste_cost) === 0 ? <span className="muted">–</span>
                        : Number(m.waste_cost) < 0 ? <span className="t-ok">−{usd(Math.abs(Number(m.waste_cost)))}</span> : usd(Number(m.waste_cost))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>}
          {r.reasons.length > 0 && <>
            <h3 className="mini-head">Sebepler</h3>
            <div className="table-wrap">
              <table className="table lib-table">
                <thead><tr><th>Sebep</th><th className="num">Hurda çıkan emir</th><th className="num">Fire veren malzeme</th><th className="num">Fire tutarı</th></tr></thead>
                <tbody>
                  {r.reasons.map((x) => (
                    <tr key={x.reason}>
                      <td><strong>{SCRAP_REASON_LABEL[x.reason]}</strong></td>
                      <td className="num">{num(Number(x.scrap_orders))}</td>
                      <td className="num">{num(Number(x.waste_lines))}</td>
                      <td className="num">{x.waste_cost == null ? <span className="muted">–</span> : usd(Number(x.waste_cost))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>}
          <p className="muted small">{r.materials.length > off.length ? `${num(r.materials.length - off.length)} malzeme planlandığı kadar kullanıldı; listede yalnızca sapanlar var. ` : ""}
            Fire = kullanılan − planlanan malzeme; eksi değer tasarruftur. Fire tutarı, tüketim anındaki birim maliyetle hesaplanır.</p>
        </div>
      )}
    </Panel>
  );
}
