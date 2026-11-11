import { Link } from "react-router";
import { useMaintenanceDue, useMaintenanceSummary, useWorkOrders } from "../api/hooks";
import { useAuth } from "../auth/AuthProvider";
import { BandChip, Empty, Loading, Panel } from "../components/ui";
import { date, usd } from "../lib/format";
import { DUE_STATE_BAND, DUE_STATE_LABEL, REASON_LABEL, WO_STATUS_LABEL, downtime, dueLeft } from "../lib/maintenance";

/** Makine sayfası: sıradaki bakımlar, açık emirler, son 12 ay özeti. */
export function AssetMaintenance({ assetId, assetCode }: { assetId: string; assetCode: string }) {
  const { can } = useAuth();
  const due = useMaintenanceDue({ asset_id: assetId });
  const open = useWorkOrders({ asset_id: assetId, open_only: true });
  const summary = useMaintenanceSummary();
  const s = summary.data?.find((r) => r.asset_id === assetId);
  const sub = s && (s.planned_done + s.breakdowns > 0)
    ? `Son 12 ay: ${s.planned_done} planlı bakım, ${s.breakdowns} arıza, ${downtime(s.downtime_minutes)} duruş, ${usd(Number(s.cost_12m))}`
    : "Son 12 ayda tamamlanmış iş emri yok";
  return (
    <Panel title="Bakım" sub={sub} className="mt"
      actions={
        <div className="actions" style={{ marginTop: 0 }}>
          {can("technician") && <Link className="btn btn-ghost t-critical" to={`/bakim?yeni=1&makine=${assetId}&tur=breakdown`}>Arıza bildir</Link>}
          <Link className="btn btn-ghost" to={`/bakim?sekme=emirler&makine=${assetId}&tumu=1`}>Tüm emirler</Link>
        </div>
      }>
      {due.isLoading || open.isLoading ? <Loading /> : (
        <div className="asset-maint">
          {(open.data?.length ?? 0) > 0 && (
            <div>
              <h3 className="mini-head">Açık emirler</h3>
              {open.data!.map((w) => (
                <div className="due-row" key={w.id}>
                  <div>
                    <Link to={`/bakim?sekme=emirler&emir=${w.id}`}><strong>{w.number}</strong></Link> · {w.title}
                    <div className="muted small">
                      {w.kind === "breakdown" ? `Arıza${w.reason_code ? ` · ${REASON_LABEL[w.reason_code]}` : ""}` : "Planlı bakım"}
                      {w.late ? " · gecikti" : ""}
                    </div>
                  </div>
                  <BandChip band={w.kind === "breakdown" ? "critical" : "watch"}>{WO_STATUS_LABEL[w.status]}</BandChip>
                </div>
              ))}
            </div>
          )}
          <div>
            <h3 className="mini-head">Sıradaki bakımlar</h3>
            {(due.data?.length ?? 0) === 0 ? <Empty>{assetCode} için bakım planı yok. <Link to="/bakim?sekme=planlar">Plan ekle</Link></Empty> : due.data!.map((d) => (
              <div className="due-row" key={d.plan_id}>
                <div>
                  <strong>{d.name}</strong>
                  <div className="muted small">
                    {d.last_done_hours != null ? `Son ${Number(d.last_done_hours).toLocaleString("tr-TR")} saatte` : d.last_done_at ? `Son ${date(d.last_done_at)}` : "Hiç yapılmadı"} · {dueLeft(d)}
                  </div>
                </div>
                <div className="actions" style={{ marginTop: 0 }}>
                  <BandChip band={DUE_STATE_BAND[d.state]}>{DUE_STATE_LABEL[d.state]}</BandChip>
                  {d.open_work_order_id ? (
                    <Link className="btn btn-small" to={`/bakim?sekme=emirler&emir=${d.open_work_order_id}`}>{d.open_work_order_number}</Link>
                  ) : can("technician") && (
                    <Link className={`btn btn-small${d.state !== "ok" ? " btn-primary" : ""}`} to={`/bakim?yeni=1&makine=${assetId}&plan=${d.plan_id}`}>Emir aç</Link>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </Panel>
  );
}
