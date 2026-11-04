import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";
import { useLogEvent, useRims } from "../api/hooks";
import type { RimRow } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import { BandChip, Empty, ErrorNote, Field, Loading, Modal, Panel } from "../components/ui";
import { date, num } from "../lib/format";

const LABEL: Record<RimRow["compliance"], string> = {
  overdue: "Gecikmiş", due_soon: "Yaklaşıyor", ok: "Güncel", not_required: "Muayene gerekmiyor",
};
const BAND = { overdue: "critical", due_soon: "watch", ok: "ok", not_required: "unknown" } as const;

function NdtModal({ rim, onClose }: { rim: RimRow; onClose: () => void }) {
  const log = useLogEvent();
  const [notes, setNotes] = useState("");
  const [cost, setCost] = useState("");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    log.mutate({ partId: rim.id, event: "inspected", reason: "ndt", notes, cost: cost ? Number(cost.replace(",", ".")) : null },
      { onSuccess: onClose });
  };
  return (
    <Modal title={`${rim.serial_no ?? "Jant"}: muayene yapıldı`} onClose={onClose}
      footer={<>
        <button className="btn btn-ghost" onClick={onClose}>Vazgeç</button>
        <button className="btn btn-primary" form="ndt-form" disabled={log.isPending}>Kaydet</button>
      </>}>
      <form id="ndt-form" className="form" onSubmit={submit}>
        <p className="muted">
          Bugünün muayenesi kaydedilir; sıradaki muayene {num(rim.ndt_interval_hours)} çalışma saati sonra gelir.
          {rim.asset_code ? ` Saat, ${rim.asset_code} makinesinin güncel motor saatinden hesaplanır.` : ""}
        </p>
        <Field label="Sonuç / not" hint="Örn. çatlak bulunmadı, firma, rapor no">
          <input value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={1000} />
        </Field>
        <Field label="Maliyet ($)" hint="İsteğe bağlı">
          <input inputMode="decimal" value={cost} onChange={(e) => setCost(e.target.value)} />
        </Field>
        <ErrorNote error={log.error} />
      </form>
    </Modal>
  );
}

export function RimsPage() {
  const rims = useRims();
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const filter = (params.get("durum") ?? "") as RimRow["compliance"] | "";
  const [ndt, setNdt] = useState<RimRow | null>(null);

  const all = rims.data ?? [];
  const count = (c: RimRow["compliance"]) => all.filter((r) => r.compliance === c).length;
  const rows = filter ? all.filter((r) => r.compliance === filter) : all;

  return (
    <>
      <div className="page-head"><h1>Jant muayenesi</h1></div>
      <p className="sub lead">
        Çok parçalı OTR jantlar belirli çalışma saatlerinde tahribatsız muayeneden (NDT) geçmelidir. Muayenesi geçmiş bir
        jant, lastik şişirilirken ciddi kazalara yol açabilir.
      </p>
      <div className="tabs" role="tablist">
        {([["", `Tümü · ${all.length}`], ["overdue", `Gecikmiş · ${count("overdue")}`], ["due_soon", `Yaklaşan · ${count("due_soon")}`],
           ["ok", `Güncel · ${count("ok")}`]] as const).map(([k, l]) => (
          <button key={k} role="tab" aria-selected={filter === k}
                  onClick={() => setParams(k ? { durum: k } : {}, { replace: true })}>{l}</button>
        ))}
      </div>
      <Panel>
        {rims.isLoading ? <Loading /> : rims.error ? <ErrorNote error={rims.error} /> : rows.length === 0 ? (
          <Empty>{all.length === 0 ? "Henüz jant kaydı yok. Jantları Kayıt → Parça teslim al ile ekleyip makine sayfasından takabilirsiniz." : "Bu durumda jant yok."}</Empty>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Durum</th><th>Jant</th><th>Konum</th><th>Son muayene</th><th className="num">Muayeneden bu yana</th>
                  <th className="num">Sıradaki muayeneye</th><th /></tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td><BandChip band={BAND[r.compliance]}>{LABEL[r.compliance]}</BandChip></td>
                    <td><Link to={`/parca/${r.id}`}><strong>{r.serial_no ?? "seri no yok"}</strong></Link><div className="muted small">{r.part_name}</div></td>
                    <td>{r.asset_id ? <Link to={`/makine/${r.asset_id}`}>{r.asset_code} {r.current_position}</Link> : <span className="muted">stokta</span>}</td>
                    <td>{r.last_ndt_at ? date(r.last_ndt_at) : <span className="t-critical">hiç yapılmadı</span>}</td>
                    <td className="num">{num(r.hours_since_ndt)} / {num(r.ndt_interval_hours)} sa</td>
                    <td className="num">
                      {r.hours_to_due == null ? "–" : r.hours_to_due < 0
                        ? <span className="t-critical">{num(-r.hours_to_due)} sa gecikti</span>
                        : `${num(r.hours_to_due)} sa`}
                    </td>
                    <td className="row-actions">
                      {can("technician") && r.compliance !== "not_required" && (
                        <button className={`btn btn-small ${r.compliance === "ok" ? "" : "btn-primary"}`} onClick={() => setNdt(r)}>Muayene yapıldı</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      {ndt && <NdtModal rim={ndt} onClose={() => setNdt(null)} />}
    </>
  );
}
