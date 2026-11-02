import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { useLabels, useParts } from "../api/hooks";
import { BandChip, Empty, ErrorNote, Loading, Panel } from "../components/ui";
import { CATEGORY_LABEL, STATUS_LABEL, num, pct, usd } from "../lib/format";
import { openInNewTab } from "../lib/popup";

export function PartsPage() {
  const [params, setParams] = useSearchParams();
  const f = {
    status: params.get("durum") ?? "",
    category: params.get("tur") ?? "",
    band: params.get("bant") ?? "",
    q: params.get("q") ?? "",
  };
  const parts = useParts({ ...f, limit: 500 });
  const labels = useLabels();
  const navigate = useNavigate();
  const [picked, setPicked] = useState<Set<string>>(new Set());

  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    setParams(next, { replace: true });
  };
  const toggle = (id: string) => {
    const n = new Set(picked);
    if (n.has(id)) n.delete(id); else n.add(id);
    setPicked(n);
  };
  const printLabels = () =>
    openInNewTab(async () => (await labels.mutateAsync({ asset_ids: [], part_ids: [...picked], skip: 0 })).url).catch(() => undefined);

  const rows = parts.data ?? [];
  return (
    <>
      <div className="page-head"><h1>Parçalar</h1></div>
      <Panel>
        <div className="filters">
          <input type="search" placeholder="Seri no veya parça adı" value={f.q} onChange={(e) => set("q", e.target.value)} aria-label="Ara" />
          <select value={f.status} onChange={(e) => set("durum", e.target.value)} aria-label="Durum">
            <option value="">Tüm durumlar</option>
            {Object.entries(STATUS_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <select value={f.category} onChange={(e) => set("tur", e.target.value)} aria-label="Tür">
            <option value="">Tüm türler</option>
            {Object.entries(CATEGORY_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <select value={f.band} onChange={(e) => set("bant", e.target.value)} aria-label="Sağlık">
            <option value="">Tüm sağlık durumları</option>
            <option value="critical">Kritik</option>
            <option value="watch">Takipte</option>
            <option value="ok">İyi</option>
            <option value="unknown">Ölçüm bekliyor</option>
          </select>
          <div className="spacer" />
          <button className="btn btn-ghost" disabled={picked.size === 0 || labels.isPending} onClick={printLabels}>
            {picked.size ? `${picked.size} etiket yazdır` : "Etiket için seçin"}
          </button>
        </div>
        <ErrorNote error={labels.error} />
        {parts.isLoading ? <Loading /> : parts.error ? <ErrorNote error={parts.error} /> : rows.length === 0 ? (
          <Empty>Bu filtrelere uyan parça yok.</Empty>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th aria-label="Seç" />
                  <th>Seri no</th><th>Parça</th><th>Durum</th><th>Konum</th><th>Sağlık</th>
                  <th className="num">Çalışma</th><th className="num">Kalan</th><th className="num">Maliyet</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => (
                  <tr key={p.id} onClick={() => navigate(`/parca/${p.id}`)}>
                    <td onClick={(e) => e.stopPropagation()}>
                      <input type="checkbox" checked={picked.has(p.id)} onChange={() => toggle(p.id)} aria-label={`${p.serial_no ?? p.part_name} seç`} />
                    </td>
                    <td><Link to={`/parca/${p.id}`} onClick={(e) => e.stopPropagation()}><strong>{p.serial_no ?? "–"}</strong></Link></td>
                    <td>{p.part_name}<div className="muted small">{p.manufacturer}</div></td>
                    <td>{STATUS_LABEL[p.status]}</td>
                    <td>{p.asset_code ? `${p.asset_code} ${p.current_position}` : "–"}</td>
                    <td>{p.status === "installed" ? <BandChip band={p.band}>{p.band === "unknown" ? "Ölçüm bekliyor" : pct(p.condition_pct)}</BandChip> : "–"}</td>
                    <td className="num">{num(p.hours_total)} sa</td>
                    <td className="num">{p.projected_hours_left != null ? `${num(p.projected_hours_left)} sa` : "–"}</td>
                    <td className="num">{usd(p.cost_total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}
