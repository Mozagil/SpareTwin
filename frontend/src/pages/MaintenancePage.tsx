import { useState } from "react";
import { Link, useSearchParams } from "react-router";
import { useDowntime, usePlans, useRecords } from "../api/hooks";
import type { MaintenancePlan } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import { CompleteModal, DOWNTIME, DUE, EndDowntimeModal, interval, PlanForm, remaining, StartDowntimeModal } from "../components/Ops";
import { BandChip, Empty, ErrorNote, Loading, Panel } from "../components/ui";
import { date, dateTime, num, usd } from "../lib/format";

function Plans() {
  const p = usePlans();
  const { can } = useAuth();
  const [done, setDone] = useState<MaintenancePlan | null>(null);
  const [add, setAdd] = useState(false);
  if (p.isLoading) return <Loading />;
  if (p.error) return <ErrorNote error={p.error} />;
  return (
    <div className="stack">
      {can("manager") && <div><button className="btn btn-primary" onClick={() => setAdd(true)}>Plan ekle</button></div>}
      {(p.data?.length ?? 0) === 0 ? <Empty>Henüz bakım planı yok.</Empty> : (
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Durum</th><th>Makine</th><th>İş</th><th>Periyot</th><th>Son yapılış</th><th>Kalan</th><th>Malzemeler</th><th /></tr></thead>
            <tbody>
              {p.data!.map((x) => (
                <tr key={x.id}>
                  <td><BandChip band={DUE[x.due_status].band}>{DUE[x.due_status].label}</BandChip></td>
                  <td><Link to={`/makine/${x.asset_id}`}><strong>{x.asset_code}</strong></Link></td>
                  <td>{x.name}</td>
                  <td className="small">{interval(x)}</td>
                  <td className="small">{x.last_done_at ? date(x.last_done_at) : "–"}{x.last_done_hours != null ? ` · ${num(x.last_done_hours)} sa` : ""}</td>
                  <td className={`small ${x.due_status === "overdue" ? "t-critical" : x.due_status === "due_soon" ? "t-watch" : ""}`}>{remaining(x)}</td>
                  <td className="small">{x.materials.map((m) => `${m.name} ×${num(m.qty)}`).join(", ") || "–"}</td>
                  <td className="row-actions">{can("technician") && x.active && <button className="btn btn-small" onClick={() => setDone(x)}>Yapıldı</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {done && <CompleteModal plan={done} onClose={() => setDone(null)} />}
      {add && <PlanForm onClose={() => setAdd(false)} />}
    </div>
  );
}

function Records() {
  const r = useRecords();
  if (r.isLoading) return <Loading />;
  if ((r.data?.length ?? 0) === 0) return <Empty>Henüz bakım kaydı yok.</Empty>;
  return (
    <div className="table-wrap">
      <table className="table">
        <thead><tr><th>Tarih</th><th>Makine</th><th>İş</th><th className="num">Motor saati</th><th className="num">İşçilik</th><th>Not</th><th>Yapan</th></tr></thead>
        <tbody>
          {r.data!.map((x) => (
            <tr key={x.id}>
              <td className="small">{dateTime(x.performed_at)}</td>
              <td><Link to={`/makine/${x.asset_id}`}>{x.asset_code}</Link></td>
              <td>{x.title}</td><td className="num">{num(x.asset_hours)}</td><td className="num">{usd(x.labor_cost)}</td>
              <td className="small">{x.notes ?? "–"}</td><td className="small">{x.performed_by_name ?? "–"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DowntimeList() {
  const d = useDowntime();
  const { can } = useAuth();
  const [start, setStart] = useState(false);
  const [end, setEnd] = useState<{ id: string; code: string } | null>(null);
  if (d.isLoading) return <Loading />;
  return (
    <div className="stack">
      {can("technician") && <div><button className="btn btn-primary" onClick={() => setStart(true)}>Duruş başlat</button></div>}
      {(d.data?.length ?? 0) === 0 ? <Empty>Duruş kaydı yok.</Empty> : (
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Makine</th><th>Sebep</th><th>Açıklama</th><th>Başlangıç</th><th>Bitiş</th><th className="num">Süre</th><th className="num">Bedel</th><th /></tr></thead>
            <tbody>
              {d.data!.map((x) => (
                <tr key={x.id} className={x.ended_at ? "" : "row-down"}>
                  <td><Link to={`/makine/${x.asset_id}`}><strong>{x.asset_code}</strong></Link></td>
                  <td>{DOWNTIME[x.category]}</td><td className="small">{x.description ?? "–"}</td>
                  <td className="small">{dateTime(x.started_at)}</td>
                  <td className="small">{x.ended_at ? dateTime(x.ended_at) : <strong className="t-critical">sürüyor</strong>}</td>
                  <td className="num">{num(x.hours)} sa</td><td className="num">{usd(x.cost)}</td>
                  <td className="row-actions">{!x.ended_at && can("technician") && <button className="btn btn-small btn-primary" onClick={() => setEnd({ id: x.id, code: x.asset_code })}>Bitir</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {start && <StartDowntimeModal onClose={() => setStart(false)} />}
      {end && <EndDowntimeModal id={end.id} code={end.code} onClose={() => setEnd(null)} />}
    </div>
  );
}

const TABS = [
  { key: "planlar", label: "Bakım planları", el: Plans, hint: "Saat ve/veya takvim bazlı periyodik işler; gecikenler önce" },
  { key: "kayitlar", label: "Bakım kayıtları", el: Records, hint: "Yapılan bakımlar" },
  { key: "duruslar", label: "Arıza ve duruş", el: DowntimeList, hint: "Makinenin çalışmadığı süreler; sürenler önce" },
];

export function MaintenancePage() {
  const [params, setParams] = useSearchParams();
  const active = TABS.find((t) => t.key === params.get("sekme")) ?? TABS[0];
  const Body = active.el;
  return (
    <>
      <div className="page-head"><h1>Bakım</h1></div>
      <div className="tabs" role="tablist">
        {TABS.map((t) => <button key={t.key} role="tab" aria-selected={t.key === active.key} onClick={() => setParams({ sekme: t.key })}>{t.label}</button>)}
      </div>
      <Panel title={active.label} sub={active.hint}><Body /></Panel>
    </>
  );
}
