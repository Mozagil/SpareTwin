import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";
import { download } from "../api/client";
import { useSetDowntimeRate, useSites, useTco } from "../api/hooks";
import type { TcoCosts, TcoRow } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import { Empty, ErrorNote, Field, Loading, Modal, Panel } from "../components/ui";
import { date, num, usd } from "../lib/format";
import { downtime } from "../lib/maintenance";
import { TCO_ITEMS, TCO_PERIODS, hoursPartial, rateFromInput, sharePct, tcoSegments } from "../lib/tco";

const money = (v: number | string | null | undefined) => (v == null || Number(v) === 0 ? "–" : usd(Number(v)));

/** Yığılmış çubuk: kalemler sabit sırada; `scale` çubuğun satır içindeki genişliği (en pahalı makine = 1). */
function CostBar({ costs, scale = 1, label }: { costs: TcoCosts; scale?: number; label: string }) {
  const segs = tcoSegments(costs);
  if (!segs.length) return <span className="muted small">–</span>;
  return (
    <div className="tco-bar" role="img" aria-label={`${label}: ${segs.map((s) => `${s.label} ${sharePct(s.share)}`).join(", ")}`}
         style={{ width: `${Math.max(scale, 0.02) * 100}%` }}>
      {segs.map((s) => (
        <i key={s.key} style={{ flexGrow: s.value, background: s.color }} title={`${s.label}: ${usd(s.value)} (${sharePct(s.share)})`} />
      ))}
    </div>
  );
}

/** Makineye özel duruş saat maliyeti; boş bırakılırsa firma oranı geçerli olur. */
function RateModal({ row, tenantRate, onClose }: { row: TcoRow; tenantRate: number; onClose: () => void }) {
  const save = useSetDowntimeRate();
  const [text, setText] = useState(row.downtime_rate_own ? String(Number(row.downtime_rate)) : "");
  const rate = rateFromInput(text);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (rate !== undefined) save.mutate({ assetId: row.asset_id, rate }, { onSuccess: onClose });
  };
  return (
    <Modal title={`${row.asset_code}: duruş saat maliyeti`} onClose={onClose}
      footer={<><button className="btn btn-ghost" onClick={onClose}>Vazgeç</button>
        <button className="btn btn-primary" form="tco-rate-form" disabled={save.isPending || rate === undefined}>Kaydet</button></>}>
      <form id="tco-rate-form" className="form" onSubmit={submit}>
        <Field label="Bu makinenin bir saatlik duruşu ($)"
               hint={`Boş bırakılırsa firma oranı (${usd(tenantRate)}/saat) geçerli olur. 0 girilirse bu makinenin duruşu maliyet yazmaz.`}>
          <input type="number" inputMode="decimal" min={0} max={100000} step="0.01" value={text}
                 placeholder={String(tenantRate)} onChange={(e) => setText(e.target.value)} />
        </Field>
        <ErrorNote error={save.error} />
      </form>
    </Modal>
  );
}

export function TcoPanel() {
  const { can } = useAuth();
  const [rateRow, setRateRow] = useState<TcoRow | null>(null);
  const [busy, setBusy] = useState<"pdf" | "xlsx" | null>(null);
  const [exportError, setExportError] = useState<unknown>(null);
  const [params, setParams] = useSearchParams();
  const months = Number(params.get("donem")) || 12;
  const site = params.get("saha") ?? "";
  const sites = useSites();
  const rep = useTco({ months, site_id: site || undefined });
  const set = (k: string, v: string) => { const n = new URLSearchParams(params); if (v) n.set(k, v); else n.delete(k); setParams(n, { replace: true }); };

  const d = rep.data;
  const rows = d?.assets ?? [];
  const max = Math.max(...rows.map((r) => Number(r.total)), 0);
  const top = rows.find((r) => Number(r.total) > 0);
  const anyPartial = !!d && rows.some((r) => r.cost_per_hour != null && hoursPartial(r, d.from));
  const rate = Number(d?.downtime_cost_per_hour ?? 0);
  // Firma oranı 0 olsa da makineye özel oran girilmişse duruş paraya çevrilir
  const anyRate = rate > 0 || rows.some((r) => r.downtime_rate_own);
  const own = rows.filter((r) => r.downtime_rate_own).length;

  const exportAs = async (ext: "pdf" | "xlsx") => {
    setBusy(ext);
    setExportError(null);
    try {
      const q = new URLSearchParams({ months: String(months), ...(site ? { site_id: site } : {}) });
      await download(`/reports/tco.${ext}?${q}`, `sparetwin-maliyet.${ext}`);
    } catch (e) {
      setExportError(e);
    } finally {
      setBusy(null);
    }
  };

  return (
    <Panel title="Makine toplam sahip olma maliyeti"
           sub={d ? `${date(d.from)} – ${date(d.to)} · parça + sarf + işçilik + dış servis + duruş` : "Parça + sarf + işçilik + dış servis + duruş"}>
      <div className="filters tco-filters">
        <label className="small muted">Dönem
          <select value={months} onChange={(e) => set("donem", e.target.value === "12" ? "" : e.target.value)}>
            {TCO_PERIODS.map((p) => <option key={p.months} value={p.months}>{p.label}</option>)}
          </select>
        </label>
        <label className="small muted">Saha
          <select value={site} onChange={(e) => set("saha", e.target.value)}>
            <option value="">Tüm sahalar</option>
            {sites.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </label>
        <span className="spacer" />
        <button className="btn btn-ghost" onClick={() => exportAs("pdf")} disabled={!d || busy !== null}>
          {busy === "pdf" ? "Hazırlanıyor…" : "PDF"}
        </button>
        <button className="btn btn-ghost" onClick={() => exportAs("xlsx")} disabled={!d || busy !== null}>
          {busy === "xlsx" ? "Hazırlanıyor…" : "Excel"}
        </button>
      </div>
      <ErrorNote error={rep.error} />
      <ErrorNote error={exportError} />
      {rep.isLoading ? <Loading /> : !d || max === 0 ? <Empty>Bu dönemde makinelere yazılmış maliyet yok.</Empty> : (
        <>
          <div className="tco-kpis">
            <div className="tco-kpi">
              <span>Toplam maliyet</span>
              <strong>{usd(Number(d.totals.total))}</strong>
              <small>{num(rows.length)} makine</small>
            </div>
            <div className="tco-kpi">
              <span>Saat başı maliyet</span>
              <strong>{d.totals.cost_per_hour != null ? usd(Number(d.totals.cost_per_hour)) : "–"}</strong>
              <small>{num(Number(d.totals.hours_worked))} çalışma saati</small>
            </div>
            <div className="tco-kpi">
              <span>Duruş</span>
              <strong>{downtime(d.totals.downtime_minutes)}</strong>
              <small>{anyRate ? `${usd(Number(d.totals.downtime_cost))}${rate > 0 ? ` · firma ${usd(rate)}/saat` : ""}` : "saat maliyeti girilmemiş"}</small>
            </div>
            <div className="tco-kpi">
              <span>En yüksek maliyet</span>
              <strong>{top?.asset_code ?? "–"}</strong>
              <small>{top ? `${usd(Number(top.total))} · toplamın ${sharePct(Number(top.total) / Number(d.totals.total))}` : ""}</small>
            </div>
          </div>

          <div className="tco-fleet">
            <CostBar costs={d.totals} label="Filo maliyet dağılımı" />
            <div className="legend">
              {tcoSegments(d.totals).map((s) => (
                <span key={s.key} style={{ ["--c" as string]: s.color }} title={TCO_ITEMS.find((i) => i.key === s.key)?.hint}>
                  {s.label} <strong>{usd(s.value)}</strong> · {sharePct(s.share)}
                </span>
              ))}
            </div>
          </div>

          <div className="table-wrap">
            <table className="table tco-table">
              <thead>
                <tr>
                  <th>Makine</th><th className="tco-col-bar">Dağılım</th>
                  {TCO_ITEMS.map((i) => <th key={i.key} className="num" title={i.hint}>{i.label}</th>)}
                  <th className="num">Toplam</th><th className="num">Saat başı</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const partial = r.cost_per_hour != null && hoursPartial(r, d.from);
                  return (
                    <tr key={r.asset_id}>
                      <td>
                        <Link to={`/makine/${r.asset_id}`}><strong>{r.asset_code}</strong></Link>
                        {r.asset_status === "down" && <span className="t-critical small"> · arızalı</span>}
                        <div className="muted small">{[r.model_name, r.site_name].filter(Boolean).join(" · ")}</div>
                      </td>
                      <td className="tco-col-bar"><CostBar costs={r} scale={max ? Number(r.total) / max : 0} label={r.asset_code} /></td>
                      <td className="num">{money(r.parts_cost)}</td>
                      <td className="num">{money(r.consumables_cost)}</td>
                      <td className="num">{money(r.labor_cost)}</td>
                      <td className="num">{money(r.external_cost)}</td>
                      <td className="num">
                        {anyRate ? money(r.downtime_cost) : downtime(r.downtime_minutes)}
                        {anyRate && r.downtime_minutes > 0 && <div className="muted small">{downtime(r.downtime_minutes)}</div>}
                        {can("manager")
                          ? <div className="small"><button className="tco-rate" onClick={() => setRateRow(r)}
                                title={r.downtime_rate_own ? "Makineye özel oran; değiştir" : "Firma oranı; bu makineye özel oran gir"}>
                              {usd(Number(r.downtime_rate))}/saat{r.downtime_rate_own && " · özel"}</button></div>
                          : r.downtime_rate_own && <div className="muted small">{usd(Number(r.downtime_rate))}/saat · özel</div>}
                      </td>
                      <td className="num"><strong>{usd(Number(r.total))}</strong></td>
                      <td className="num">
                        {r.cost_per_hour != null ? <>{usd(Number(r.cost_per_hour))}{partial && <sup title={`Saat kaydı ${date(r.hours_from)} tarihinden başlıyor`}>*</sup>}</> : "–"}
                        <div className="muted small">{num(Number(r.hours_worked))} saat</div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot>
                <tr>
                  <td>Filo</td><td className="tco-col-bar" />
                  {TCO_ITEMS.map((i) => <td key={i.key} className="num">{money(d.totals[i.key])}</td>)}
                  <td className="num">{usd(Number(d.totals.total))}</td>
                  <td className="num">{d.totals.cost_per_hour != null ? usd(Number(d.totals.cost_per_hour)) : "–"}</td>
                </tr>
              </tfoot>
            </table>
          </div>

          <p className="muted small tco-note">
            Parçanın alış maliyeti ilk takıldığı makineye ve takıldığı güne yazılır; sarf, stok defterinden makineye yapılan çıkışlardır (iş emirleri dahil).
            Süren arızaların duruşu bugüne kadar sayılır.
            {anyRate
              ? ` Duruş maliyeti = duruş süresi × duruş saat maliyeti (firma oranı ${usd(rate)}/saat${own ? `; ${num(own)} makine kendi oranıyla` : ""}).`
              : " Duruş saat maliyeti girilmediği için duruş toplamı etkilemiyor."}
            {can("admin") && <> Firma oranını <Link to="/ayarlar">Ayarlar'dan {rate > 0 ? "değiştir" : "gir"}</Link>.</>}
            {can("manager") && " Makineye özel oran için satırdaki orana tıklayın."}
            {anyPartial && " * Saat kaydı dönemin tamamını kapsamıyor; saat başı maliyet olduğundan yüksek görünür."}
          </p>
        </>
      )}
      {rateRow && <RateModal row={rateRow} tenantRate={rate} onClose={() => setRateRow(null)} />}
    </Panel>
  );
}
