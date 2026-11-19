// Sökme sebepleri: parçalar neden sökülüyor, hangi kalemde ve hangi makinede.
// Sebep sökme anında sabit listeden seçildiği için ek veri girişi yok.
import { Link, useSearchParams } from "react-router";
import { useCategories, useRemovalReasons } from "../api/hooks";
import { Empty, ErrorNote, Loading, Panel } from "../components/ui";
import { categoryLabel, num, pct, reasonLabel } from "../lib/format";
import { barWidth, prematureShare, reasonMix } from "../lib/reasons";
import { TCO_PERIODS, sharePct } from "../lib/tco";

const hours = (v: number | null) => (v == null ? "–" : `${num(v)} sa`);

export function RemovalReasonsPanel() {
  const [params, setParams] = useSearchParams();
  const months = Number(params.get("donem")) || 12;
  const category = params.get("tur") ?? "";
  const cats = useCategories();
  const rep = useRemovalReasons(months, category || undefined);
  const d = rep.data;
  const set = (k: string, v: string) => { const n = new URLSearchParams(params); if (v) n.set(k, v); else n.delete(k); setParams(n, { replace: true }); };

  const max = Math.max(...(d?.reasons.map((r) => r.count) ?? [0]), 0);
  const top = d?.reasons[0];
  const early = d ? prematureShare(d) : null;

  return (
    <Panel title="Sökme sebepleri" sub="Parçalar neden sökülüyor; sebep sökme sırasında sabit listeden seçilir">
      <div className="filters tco-filters">
        <label className="small muted">Dönem
          <select value={months} onChange={(e) => set("donem", e.target.value === "12" ? "" : e.target.value)}>
            {TCO_PERIODS.map((p) => <option key={p.months} value={p.months}>{p.label}</option>)}
          </select>
        </label>
        <label className="small muted">Parça tipi
          <select value={category} onChange={(e) => set("tur", e.target.value)}>
            <option value="">Tüm tipler</option>
            {cats.data?.filter((c) => c.is_serialized).map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}
          </select>
        </label>
      </div>
      <ErrorNote error={rep.error} />
      {rep.isLoading ? <Loading /> : !d || d.total === 0 ? (
        <Empty>Bu dönemde sökülen parça yok.{d && d.rotations > 0 ? ` ${num(d.rotations)} rotasyon yapıldı; rotasyon sökme sebebi sayılmaz.` : ""}</Empty>
      ) : (
        <>
          <div className="tco-kpis">
            <div className="tco-kpi"><span>Sökülen parça</span><strong>{num(d.total)}</strong>
              <small>{d.rotations > 0 ? `ayrıca ${num(d.rotations)} rotasyon` : "rotasyon hariç"}</small></div>
            {top && <div className="tco-kpi"><span>En sık sebep</span><strong>{reasonLabel(top.reason)}</strong>
              <small>{num(top.count)} sökme, {sharePct(top.count / d.total)}</small></div>}
            {early != null && <div className="tco-kpi"><span>Ömrünü doldurmadan sökülen</span><strong>{pct(early * 100)}</strong>
              <small>aşınma dışındaki sebeplerle</small></div>}
          </div>

          <div className="table-wrap">
            <table className="table reason-table">
              <thead><tr><th>Sebep</th><th className="reason-col-bar">Sökme sayısı</th><th className="num">Adet</th><th className="num">Pay</th>
                <th className="num" title="Sökme anında parçanın toplam çalışma saati">Ort. çalışma saati</th></tr></thead>
              <tbody>
                {d.reasons.map((r) => (
                  <tr key={r.reason}>
                    <td>{reasonLabel(r.reason)}</td>
                    <td className="reason-col-bar"><div className="reason-bar" style={{ width: `${barWidth(r.count, max)}%` }}
                          role="img" aria-label={`${reasonLabel(r.reason)}: ${num(r.count)} sökme`} /></td>
                    <td className="num">{num(r.count)}</td>
                    <td className="num">{sharePct(r.count / d.total)}</td>
                    <td className="num">{hours(r.avg_part_hours)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h3 className="mini-head sup-section">Katalog kalemine göre</h3>
          <div className="table-wrap">
            <table className="table reason-table">
              <thead><tr><th>Kalem</th><th className="num">Sökme</th><th className="num">Ort. çalışma saati</th><th>Sebepler</th></tr></thead>
              <tbody>
                {d.by_part.map((p) => (
                  <tr key={p.part_id}>
                    <td><strong>{p.name}</strong><div className="muted small">{[categoryLabel(p.category_code), p.manufacturer].filter(Boolean).join(" · ")}</div></td>
                    <td className="num">{num(p.count)}</td>
                    <td className="num">{hours(p.avg_part_hours)}</td>
                    <td>{reasonMix(p.reasons)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h3 className="mini-head sup-section">Makineye göre</h3>
          <div className="table-wrap">
            <table className="table reason-table">
              <thead><tr><th>Makine</th><th className="num">Sökme</th><th className="num">Ort. çalışma saati</th><th>Sebepler</th></tr></thead>
              <tbody>
                {d.by_asset.map((a) => (
                  <tr key={a.asset_id}>
                    <td><Link to={`/makine/${a.asset_id}`}><strong>{a.code}</strong></Link></td>
                    <td className="num">{num(a.count)}</td>
                    <td className="num">{hours(a.avg_part_hours)}</td>
                    <td>{reasonMix(a.reasons)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted small tco-note">
            Dönem sökme tarihine göredir. Rotasyon (aynı makinede yer değişimi) sökme sebebi sayılmaz. Ortalama çalışma saati,
            parçanın sökme anındaki toplam çalışma saatidir: aynı kalemde kesik ya da darbeyle sökülenlerin saati aşınmayla
            sökülenlerden belirgin düşükse kayıp oradadır.
          </p>
        </>
      )}
    </Panel>
  );
}
