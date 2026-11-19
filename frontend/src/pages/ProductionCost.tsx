// Üretim maliyeti: emrin maliyet dökümü (plan / gerçekleşen) ve ürün bazında maliyet raporu.
import { useState } from "react";
import { useCostReport } from "../api/hooks";
import type { ProductionOrder } from "../api/types";
import { Empty, ErrorNote, Loading, Panel } from "../components/ui";
import { num, num1, usd } from "../lib/format";
import { costDiff } from "../lib/production";

const qty = (v: number | string, unit: string | null) => `${Number.isInteger(Number(v)) ? num(Number(v)) : num1(Number(v))} ${unit ?? ""}`.trim();

/** Plana göre fark: pahalıya gelen izlemede, ucuza gelen yeşil. */
function Diff({ planned, actual }: { planned: number | string; actual: number | string }) {
  const d = costDiff(planned, actual);
  if (d === 0) return <span className="muted">–</span>;
  return <span className={d > 0 ? "t-watch" : "t-ok"}>{d > 0 ? "+" : "−"}{usd(Math.abs(d))}</span>;
}

/** Emrin maliyeti: açık emirde plan, tamamlanmış emirde plan / gerçekleşen ve birim maliyet. */
export function OrderCost({ order: o }: { order: ProductionOrder }) {
  const p = o.planned_cost;
  const done = o.material_cost != null;
  // Maliyet kalemi gelmeden önce tamamlanmış emir: gösterecek gerçekleşen yok
  if (o.status === "done" && !done) return null;
  const rows: [string, number, number | null][] = [
    ["Malzeme", p.material, o.material_cost], ["İşçilik", p.labor, o.labor_cost], ["Makine", p.machine, o.machine_cost],
  ];
  const rate = Number(p.labor_rate);
  return (
    <div className="prod-cost">
      <h3 className="mini-head">Maliyet{done && o.unit_cost != null && <span className="muted small"> · 1 {o.unit} sağlam ürün {usd(Number(o.unit_cost))}</span>}
        {!done && Number(p.total) > 0 && <span className="muted small"> · plana göre 1 {o.unit} {usd(Number(p.unit))}</span>}</h3>
      <div className="table-wrap">
        <table className="table lib-table">
          <thead><tr><th>Kalem</th><th className="num">Planlanan</th>{done && <><th className="num">Gerçekleşen</th><th className="num">Fark</th></>}</tr></thead>
          <tbody>
            {rows.map(([label, planned, actual]) => (
              <tr key={label}>
                <td>{label}</td>
                <td className="num">{usd(Number(planned))}</td>
                {done && <><td className="num">{usd(Number(actual))}</td><td className="num"><Diff planned={planned} actual={actual ?? 0} /></td></>}
              </tr>
            ))}
          </tbody>
          <tfoot><tr><td>Toplam</td><td className="num">{usd(Number(p.total))}</td>
            {done && <><td className="num">{usd(Number(o.total_cost))}</td><td className="num"><Diff planned={p.total} actual={o.total_cost ?? 0} /></td></>}</tr></tfoot>
        </table>
      </div>
      <p className="muted small">
        {rate > 0 ? `İşçilik ${usd(rate)}/saat üzerinden. ` : "İşçilik saat maliyeti girilmemiş (Ayarlar); işçilik 0 sayılır. "}
        {done ? "Maliyet emir tamamlanırken hesaplandı; sonradan değişen oranlar bu emri etkilemez. Hurdanın maliyeti sağlam ürüne biner."
          : "Gerçekleşen maliyet emir tamamlanınca hesaplanır."}
      </p>
    </div>
  );
}

const PERIODS = [3, 6, 12, 24];

export function CostReportPanel() {
  const [months, setMonths] = useState(12);
  const report = useCostReport(months);
  const r = report.data;
  const rows = r?.products ?? [];
  const sum = (k: "material_cost" | "labor_cost" | "machine_cost" | "total_cost") => rows.reduce((s, p) => s + Number(p[k]), 0);

  return (
    <Panel title="Üretim maliyeti" sub="Tamamlanan emirlerde malzeme, işçilik ve makine maliyeti; birim maliyet sağlam ürün başınadır"
           actions={<div className="seg" role="group" aria-label="Dönem">
             {PERIODS.map((m) => <button key={m} type="button" aria-pressed={m === months} onClick={() => setMonths(m)}>{m} ay</button>)}
           </div>}>
      {report.isLoading ? <Loading /> : report.error || !r ? <ErrorNote error={report.error} /> : rows.length === 0 ? (
        <Empty>Bu dönemde maliyeti hesaplanmış emir yok.</Empty>
      ) : (
        <div className="table-wrap">
          <table className="table lib-table">
            <thead><tr><th>Ürün</th><th className="num">Emir</th><th className="num">Sağlam</th><th>Dağılım</th><th className="num">Malzeme</th>
              <th className="num">İşçilik</th><th className="num">Makine</th><th className="num">Toplam</th><th className="num">Birim maliyet</th></tr></thead>
            <tbody>
              {rows.map((p) => {
                const total = Number(p.total_cost);
                const share = (v: number) => ({ width: `${total > 0 ? (Number(v) / total) * 100 : 0}%` });
                return (
                  <tr key={p.part_id}>
                    <td><strong>{p.name}</strong><div className="muted small">{p.part_no}</div></td>
                    <td className="num">{num(p.order_count)}</td>
                    <td className="num">{qty(p.good_qty, p.unit)}{Number(p.scrap_qty) > 0 && <div className="small t-watch">{qty(p.scrap_qty, p.unit)} hurda</div>}</td>
                    <td><div className="cost-bar" role="img"
                             aria-label={`${p.name}: malzeme ${usd(Number(p.material_cost))}, işçilik ${usd(Number(p.labor_cost))}, makine ${usd(Number(p.machine_cost))}`}>
                      <i className="cost-mat" style={share(p.material_cost)} /><i className="cost-lab" style={share(p.labor_cost)} /><i className="cost-mac" style={share(p.machine_cost)} />
                    </div></td>
                    <td className="num">{usd(Number(p.material_cost))}</td>
                    <td className="num">{usd(Number(p.labor_cost))}</td>
                    <td className="num">{usd(Number(p.machine_cost))}</td>
                    <td className="num"><strong>{usd(total)}</strong></td>
                    <td className="num">{p.unit_cost == null ? <span className="muted">–</span> : usd(Number(p.unit_cost))}</td>
                  </tr>
                );
              })}
            </tbody>
            <tfoot><tr><td colSpan={4}>Toplam</td><td className="num">{usd(sum("material_cost"))}</td><td className="num">{usd(sum("labor_cost"))}</td>
              <td className="num">{usd(sum("machine_cost"))}</td><td className="num">{usd(sum("total_cost"))}</td><td /></tr></tfoot>
          </table>
          <p className="muted small cost-legend"><i className="cost-mat" />malzeme<i className="cost-lab" />işçilik<i className="cost-mac" />makine ·
            {" "}{Number(r.labor_cost_per_hour) > 0 ? `Bugünkü işçilik oranı ${usd(Number(r.labor_cost_per_hour))}/saat; ` : "İşçilik saat maliyeti girilmemiş (Ayarlar); "}
            her emir tamamlandığı günkü oranla hesaplanır.</p>
        </div>
      )}
    </Panel>
  );
}
