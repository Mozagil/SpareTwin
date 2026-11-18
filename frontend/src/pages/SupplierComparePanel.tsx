// Tedarikçi karşılaştırma: hangi kalem kimden kaç kez, kaça, kaç günde alındı.
// Ek veri girişi yok; verilmiş siparişler ve teslim alma kayıtlarından hesaplanır.
import { useSearchParams } from "react-router";
import { useSupplierComparison } from "../api/hooks";
import type { ComparedPart, SupplierStat } from "../api/types";
import { Empty, ErrorNote, Loading, Panel } from "../components/ui";
import { categoryLabel, date, num, num1, pct, usd } from "../lib/format";
import { leadDays, onTimeShare, shareSegments, supplierColors, verdict, type ShareSegment } from "../lib/suppliers";
import { TCO_PERIODS, sharePct } from "../lib/tco";

const qty = (v: number | string, unit: string) => `${Number.isInteger(Number(v)) ? num(Number(v)) : num1(Number(v))} ${unit}`;

function ShareBar({ segs, label, format }: { segs: ShareSegment[]; label: string; format: (v: number) => string }) {
  if (segs.length === 0) return null;
  return (
    <div className="tco-bar sup-bar" role="img" aria-label={`${label}: ${segs.map((s) => `${s.label} ${sharePct(s.share)}`).join(", ")}`}>
      {segs.map((s) => (
        <i key={s.id} style={{ flexGrow: s.value, background: s.color }} title={`${s.label}: ${format(s.value)} (${sharePct(s.share)})`} />
      ))}
    </div>
  );
}

function Legend({ segs, format }: { segs: ShareSegment[]; format: (v: number) => string }) {
  return (
    <div className="legend sup-legend">
      {segs.map((s) => (
        <span key={s.id} style={{ ["--c" as string]: s.color }}>{s.label} <strong>{sharePct(s.share)}</strong> · {format(s.value)}</span>
      ))}
    </div>
  );
}

const OnTime = ({ s }: { s: Pick<SupplierStat, "on_time" | "timed"> }) => {
  const share = onTimeShare(s);
  if (share == null) return <span className="muted">–</span>;
  return <span title={`${num(s.timed)} teslimatın ${num(s.on_time)} tanesi söz verilen tarihte geldi`}>{pct(share * 100)}</span>;
};

function PartBlock({ part, colors }: { part: ComparedPart; colors: Map<string, string> }) {
  const segs = shareSegments(part.suppliers, (s) => s.order_count, colors);
  const times = (v: number) => `${num(v)} alım`;
  return (
    <section className="sup-part">
      <div className="row-between">
        <h3 className="mini-head">{part.name}</h3>
        <span className="muted small">{num(part.order_count)} alım · {usd(Number(part.spend))}</span>
      </div>
      <div className="muted small">{[categoryLabel(part.category_code), part.manufacturer, part.part_no].filter(Boolean).join(" · ")}</div>
      <ShareBar segs={segs} label={`${part.name} alım dağılımı`} format={times} />
      <div className="table-wrap">
        <table className="table sup-table">
          <thead><tr><th>Tedarikçi</th><th className="num">Kaç kez</th><th className="num">Miktar</th><th className="num">Ort. birim fiyat</th>
            <th className="num">Son fiyat</th><th className="num">Ort. teslim</th><th className="num">Zamanında</th></tr></thead>
          <tbody>
            {part.suppliers.map((s) => (
              <tr key={s.supplier_id}>
                <td><span className="sup-dot" style={{ background: colors.get(s.supplier_id) }} aria-hidden="true" />{s.supplier_name}</td>
                <td className="num">{num(s.order_count)}</td>
                <td className="num">{qty(s.qty, part.unit)}</td>
                <td className="num">{usd(s.avg_cost == null ? null : Number(s.avg_cost))}{s.cheapest && <div><span className="chip t-ok">En ucuz</span></div>}</td>
                <td className="num">{usd(s.last_cost == null ? null : Number(s.last_cost))}<div className="muted small">{date(s.last_ordered_at)}</div></td>
                <td className="num">{leadDays(s.avg_lead_days)}{s.fastest && <div><span className="chip t-ok">En hızlı</span></div>}
                  {s.delivered === 0 && <div className="muted small">henüz teslim yok</div>}</td>
                <td className="num"><OnTime s={s} />{s.short > 0 && <div className="t-watch small">{num(s.short)} eksik teslim</div>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="sup-verdict">{verdict(part)}</p>
    </section>
  );
}

export function SupplierComparePanel() {
  const [params, setParams] = useSearchParams();
  const months = Number(params.get("donem")) || 12;
  const rep = useSupplierComparison(months);
  const d = rep.data;
  const set = (v: string) => { const n = new URLSearchParams(params); if (v) n.set("donem", v); else n.delete("donem"); setParams(n, { replace: true }); };

  const colors = supplierColors(d?.suppliers ?? []);
  const active = (d?.suppliers ?? []).filter((s) => s.order_count > 0);
  const spend = shareSegments(active, (s) => Number(s.spend), colors);
  const money = (v: number) => usd(v);

  return (
    <Panel title="Tedarikçi karşılaştırma" sub="Verilmiş siparişler ve teslim alma kayıtlarından hesaplanır; ayrıca veri girilmez">
      <div className="filters tco-filters">
        <label className="small muted">Dönem
          <select value={months} onChange={(e) => set(e.target.value === "12" ? "" : e.target.value)}>
            {TCO_PERIODS.map((p) => <option key={p.months} value={p.months}>{p.label}</option>)}
          </select>
        </label>
      </div>
      <ErrorNote error={rep.error} />
      {rep.isLoading ? <Loading /> : !d || d.parts.length === 0 ? (
        <Empty>Bu dönemde verilmiş sipariş yok. Siparişler verilip teslim alındıkça karşılaştırma kendiliğinden oluşur.</Empty>
      ) : (
        <>
          <h3 className="mini-head">Harcamanın tedarikçilere dağılımı</h3>
          <ShareBar segs={spend} label="Harcamanın tedarikçilere dağılımı" format={money} />
          <Legend segs={spend} format={money} />
          <div className="table-wrap">
            <table className="table sup-table">
              <thead><tr><th>Tedarikçi</th><th className="num">Sipariş</th><th className="num">Kalem çeşidi</th><th className="num">Tutar</th>
                <th className="num">Ort. teslim</th><th className="num">Zamanında</th><th className="num">Eksik teslim</th></tr></thead>
              <tbody>
                {active.map((s) => (
                  <tr key={s.supplier_id}>
                    <td><span className="sup-dot" style={{ background: colors.get(s.supplier_id) }} aria-hidden="true" />{s.supplier_name}
                      {!s.is_active && <span className="muted small"> · pasif</span>}</td>
                    <td className="num">{num(s.order_count)}</td>
                    <td className="num">{num(s.part_count)}</td>
                    <td className="num">{usd(Number(s.spend))}</td>
                    <td className="num">{leadDays(s.avg_lead_days)}
                      {s.lead_time_days != null && s.avg_lead_days != null && <div className="muted small">söz verilen {num(s.lead_time_days)} gün</div>}</td>
                    <td className="num"><OnTime s={s} /></td>
                    <td className="num">{s.short > 0 ? num(s.short) : <span className="muted">–</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h3 className="mini-head sup-section">Kalem bazında: kimden kaç kez alındı</h3>
          {d.parts.map((p) => <PartBlock key={p.part_id} part={p} colors={colors} />)}
          <p className="muted small tco-note">
            Dönem sipariş tarihine göredir. Talep aşamasındaki ve iptal edilen kayıtlar sayılmaz. Ortalama fiyat miktar ağırlıklıdır.
            Teslim süresi sipariş tarihinden son teslimata kadardır; yalnızca tamamı teslim alınan kalemler ölçülür.
            “Zamanında”, siparişteki beklenen teslim tarihine göredir. “En ucuz” ve “En hızlı” yalnızca tek bir tedarikçi açıkça öndeyse gösterilir.
          </p>
        </>
      )}
    </Panel>
  );
}
