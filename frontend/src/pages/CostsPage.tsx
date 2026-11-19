import { useState } from "react";
import { Link } from "react-router";
import { useCosts } from "../api/hooks";
import { ErrorNote, Loading, Panel } from "../components/ui";
import { num, usd } from "../lib/format";

const PERIODS = [[30, "Son 30 gün"], [90, "Son 90 gün"], [365, "Son 1 yıl"], [0, "Tümü"]] as const;

export function CostsPage() {
  const [days, setDays] = useState(90);
  const c = useCosts(days);
  const rows = c.data?.rows ?? [];
  const maxCph = Math.max(...rows.map((r) => Number(r.cost_per_hour ?? 0)), 1);
  const t = c.data?.totals;
  return (
    <>
      <div className="page-head">
        <h1>Toplam sahip olma maliyeti</h1>
        <div className="seg" role="group" aria-label="Dönem">
          {PERIODS.map(([d, l]) => <button key={d} aria-pressed={days === d} onClick={() => setDays(d)}>{l}</button>)}
        </div>
      </div>
      <Panel sub="Parça: dönemde makineye ilk kez takılan parçaların alış bedeli (rotasyon ve Excel ile ilk kurulumda aktarılanlar sayılmaz) · Sarf: stoktan makineye çıkışlar · Servis: parça olaylarına girilen bedeller · Bakım: işçilik · Duruş: tamir bedeli. Saat başı = toplam ÷ dönemde çalışılan motor saati.">
        {c.isLoading ? <Loading /> : c.error ? <ErrorNote error={c.error} /> : (
          <div className="table-wrap">
            <table className="table cost-table">
              <thead>
                <tr><th>Makine</th><th className="num">Parça</th><th className="num">Sarf</th><th className="num">Servis</th><th className="num">Bakım</th>
                  <th className="num">Duruş</th><th className="num">Toplam</th><th className="num">Çalışma</th><th>Saat başı</th><th className="num">Duruş süresi</th></tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td><Link to={`/makine/${r.id}`}><strong>{r.code}</strong></Link><div className="muted small">{r.manufacturer} {r.model}</div></td>
                    <td className="num">{usd(r.parts)}{r.parts_count ? <div className="muted small">{r.parts_count} parça</div> : null}</td>
                    <td className="num">{usd(r.consumables)}</td>
                    <td className="num">{usd(r.services)}</td>
                    <td className="num">{usd(r.maintenance)}{r.maintenance_count ? <div className="muted small">{r.maintenance_count} bakım</div> : null}</td>
                    <td className="num">{usd(r.downtime_cost)}</td>
                    <td className="num"><strong>{usd(r.total)}</strong></td>
                    <td className="num">{r.hours_worked != null ? `${num(r.hours_worked)} sa` : "–"}</td>
                    <td>
                      {r.cost_per_hour != null ? (
                        <div className="cph"><span style={{ width: `${(Number(r.cost_per_hour) / maxCph) * 100}%` }} /><strong>{usd(r.cost_per_hour)}</strong></div>
                      ) : <span className="muted small">saat verisi yok</span>}
                    </td>
                    <td className="num">{Number(r.downtime_hours) ? `${num(r.downtime_hours)} sa` : "–"}</td>
                  </tr>
                ))}
              </tbody>
              {t && (
                <tfoot>
                  <tr><td><strong>Filo</strong></td><td className="num">{usd(t.parts)}</td><td className="num">{usd(t.consumables)}</td>
                    <td className="num">{usd(t.services)}</td><td className="num">{usd(t.maintenance)}</td><td className="num">{usd(t.downtime_cost)}</td>
                    <td className="num"><strong>{usd(t.total)}</strong></td><td className="num">{num(t.hours_worked)} sa</td>
                    <td><strong>{usd(t.cost_per_hour)}</strong></td><td className="num">{num(t.downtime_hours)} sa</td></tr>
                </tfoot>
              )}
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}
