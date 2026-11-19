// Bakım planı ve duruş bileşenleri: Bakım sayfası ve makine sayfası birlikte kullanır.
import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import { useAssets, useCatalogParts, useOps, useSites } from "../api/hooks";
import type { DowntimeCategory, DueStatus, MaintenancePlan } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import { dateTime, num } from "../lib/format";
import { BandChip, ErrorNote, Field, Modal } from "./ui";

export const DUE: Record<DueStatus, { label: string; band: "critical" | "watch" | "ok" | "unknown" }> = {
  overdue: { label: "Gecikmiş", band: "critical" },
  due_soon: { label: "Yaklaşıyor", band: "watch" },
  ok: { label: "Güncel", band: "ok" },
  inactive: { label: "Pasif", band: "unknown" },
};
export const DOWNTIME: Record<DowntimeCategory, string> = {
  breakdown: "Arıza", planned_maintenance: "Planlı bakım", tire: "Lastik", waiting_parts: "Parça bekleniyor",
  operational: "Operasyonel", other: "Diğer",
};
const n = (v: string) => (v.trim() === "" ? null : Number(v.replace(",", ".")));

export function interval(p: MaintenancePlan) {
  return [p.interval_hours ? `${num(p.interval_hours)} saat` : null, p.interval_days ? `${p.interval_days} gün` : null]
    .filter(Boolean).join(" veya ");
}

export function remaining(p: MaintenancePlan) {
  const out: string[] = [];
  if (p.hours_left != null) out.push(p.hours_left < 0 ? `${num(-p.hours_left)} sa gecikti` : `${num(p.hours_left)} sa kaldı`);
  if (p.days_left != null) out.push(p.days_left < 0 ? `${-p.days_left} gün gecikti` : `${p.days_left} gün kaldı`);
  return out.join(" · ") || "–";
}

export function CompleteModal({ plan, onClose }: { plan: MaintenancePlan; onClose: () => void }) {
  const { complete } = useOps();
  const sites = useSites();
  const [hours, setHours] = useState("");
  const [labor, setLabor] = useState("");
  const [notes, setNotes] = useState("");
  const [site, setSite] = useState("");
  const [consume, setConsume] = useState(plan.materials.length > 0);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    complete.mutate({ id: plan.id, asset_hours: n(hours), labor_cost: n(labor), notes: notes || null, site_id: site || null, consume_materials: consume },
      { onSuccess: onClose });
  };
  return (
    <Modal title={`${plan.asset_code}: ${plan.name}`} onClose={onClose}
      footer={<>
        <button className="btn btn-ghost" onClick={onClose}>Vazgeç</button>
        <button className="btn btn-primary" form="complete-form" disabled={complete.isPending}>Bakım yapıldı</button>
      </>}>
      <form id="complete-form" className="form" onSubmit={submit}>
        <div className="form-row">
          <Field label="Motor saati" hint={`Boşsa güncel: ${num(plan.meter_hours)}`}>
            <input inputMode="decimal" value={hours} onChange={(e) => setHours(e.target.value)} placeholder={String(plan.meter_hours)} />
          </Field>
          <Field label="İşçilik ($)" hint="Maliyet raporuna girer"><input inputMode="decimal" value={labor} onChange={(e) => setLabor(e.target.value)} /></Field>
        </div>
        {plan.materials.length > 0 && (
          <fieldset className="fieldset">
            <legend>Malzemeler</legend>
            <ul className="mat-list">{plan.materials.map((m) => <li key={m.part_id}>{m.name} · {num(m.qty)} {m.unit}</li>)}</ul>
            <label className="inline-check"><input type="checkbox" checked={consume} onChange={(e) => setConsume(e.target.checked)} /> Stoktan düş (makineye çıkış)</label>
            {consume && (
              <Field label="Depo">
                <select value={site} onChange={(e) => setSite(e.target.value)}>
                  <option value="">Genel depo</option>
                  {sites.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </Field>
            )}
          </fieldset>
        )}
        <Field label="Not"><input value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={2000} /></Field>
        <ErrorNote error={complete.error} />
      </form>
    </Modal>
  );
}

export function PlanForm({ assetId, onClose }: { assetId?: string; onClose: () => void }) {
  const assets = useAssets();
  const catalog = useCatalogParts();
  const { createPlan } = useOps();
  const [asset, setAsset] = useState(assetId ?? "");
  const [name, setName] = useState("");
  const [ih, setIh] = useState("");
  const [id, setId] = useState("");
  const [last, setLast] = useState("");
  const [mats, setMats] = useState<{ part_id: string; qty: string }[]>([]);
  const consumables = (catalog.data ?? []).filter((c) => !c.is_serialized);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    createPlan.mutate({
      asset_id: asset, name, interval_hours: n(ih), interval_days: id ? Number(id) : null, last_done_hours: n(last),
      materials: mats.filter((m) => m.part_id && n(m.qty)).map((m) => ({ part_id: m.part_id, qty: n(m.qty)! })),
    }, { onSuccess: onClose });
  };
  return (
    <Modal title="Bakım planı ekle" onClose={onClose}
      footer={<>
        <button className="btn btn-ghost" onClick={onClose}>Vazgeç</button>
        <button className="btn btn-primary" form="plan-form" disabled={createPlan.isPending || !asset || !name || (!ih && !id)}>Kaydet</button>
      </>}>
      <form id="plan-form" className="form" onSubmit={submit}>
        {!assetId && (
          <Field label="Makine">
            <select value={asset} onChange={(e) => setAsset(e.target.value)} required>
              <option value="">Seçin</option>
              {assets.data?.map((a) => <option key={a.id} value={a.id}>{a.code} · {a.manufacturer} {a.model}</option>)}
            </select>
          </Field>
        )}
        <Field label="İş"><input value={name} onChange={(e) => setName(e.target.value)} placeholder="ör. Motor yağı değişimi" required /></Field>
        <div className="form-row">
          <Field label="Her … çalışma saatinde"><input inputMode="decimal" value={ih} onChange={(e) => setIh(e.target.value)} placeholder="500" /></Field>
          <Field label="ve/veya her … günde"><input inputMode="numeric" value={id} onChange={(e) => setId(e.target.value)} placeholder="180" /></Field>
        </div>
        <Field label="Son yapıldığı motor saati" hint="Boşsa: şimdi yapılmış sayılır, sayaç bugünden başlar">
          <input inputMode="decimal" value={last} onChange={(e) => setLast(e.target.value)} />
        </Field>
        <fieldset className="fieldset">
          <legend>Malzemeler (isteğe bağlı)</legend>
          {mats.map((m, i) => (
            <div key={i} className="mat-row">
              <select value={m.part_id} onChange={(e) => setMats(mats.map((x, j) => (j === i ? { ...x, part_id: e.target.value } : x)))} aria-label="Malzeme">
                <option value="">Seçin</option>
                {consumables.map((c) => <option key={c.id} value={c.id}>{c.name} ({c.unit})</option>)}
              </select>
              <input className="qty-input" inputMode="decimal" value={m.qty} aria-label="Miktar"
                     onChange={(e) => setMats(mats.map((x, j) => (j === i ? { ...x, qty: e.target.value } : x)))} />
              <button type="button" className="btn btn-small" onClick={() => setMats(mats.filter((_, j) => j !== i))}>Sil</button>
            </div>
          ))}
          <button type="button" className="btn btn-ghost btn-small" onClick={() => setMats([...mats, { part_id: "", qty: "1" }])}>Malzeme ekle</button>
        </fieldset>
        <ErrorNote error={createPlan.error} />
      </form>
    </Modal>
  );
}

export function StartDowntimeModal({ assetId, onClose }: { assetId?: string; onClose: () => void }) {
  const assets = useAssets();
  const { startDowntime } = useOps();
  const [asset, setAsset] = useState(assetId ?? "");
  const [cat, setCat] = useState<DowntimeCategory>("breakdown");
  const [desc, setDesc] = useState("");
  return (
    <Modal title="Duruş başlat" onClose={onClose}
      footer={<>
        <button className="btn btn-ghost" onClick={onClose}>Vazgeç</button>
        <button className="btn btn-primary" form="down-form" disabled={startDowntime.isPending || !asset}>Makine durdu</button>
      </>}>
      <form id="down-form" className="form" onSubmit={(e) => { e.preventDefault(); startDowntime.mutate({ asset_id: asset, category: cat, description: desc || null }, { onSuccess: onClose }); }}>
        {!assetId && (
          <Field label="Makine">
            <select value={asset} onChange={(e) => setAsset(e.target.value)} required>
              <option value="">Seçin</option>
              {assets.data?.filter((a) => !a.down_since).map((a) => <option key={a.id} value={a.id}>{a.code}</option>)}
            </select>
          </Field>
        )}
        <Field label="Sebep">
          <select value={cat} onChange={(e) => setCat(e.target.value as DowntimeCategory)}>
            {Object.entries(DOWNTIME).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </Field>
        <Field label="Açıklama"><input value={desc} onChange={(e) => setDesc(e.target.value)} maxLength={1000} placeholder="ör. Hidrolik hortum patladı" /></Field>
        <ErrorNote error={startDowntime.error} />
      </form>
    </Modal>
  );
}

export function EndDowntimeModal({ id, code, onClose }: { id: string; code: string; onClose: () => void }) {
  const { endDowntime } = useOps();
  const [cost, setCost] = useState("");
  return (
    <Modal title={`${code}: makine tekrar çalışıyor`} onClose={onClose}
      footer={<>
        <button className="btn btn-ghost" onClick={onClose}>Vazgeç</button>
        <button className="btn btn-primary" form="end-form" disabled={endDowntime.isPending}>Duruşu bitir</button>
      </>}>
      <form id="end-form" className="form" onSubmit={(e) => { e.preventDefault(); endDowntime.mutate({ id, cost: n(cost) }, { onSuccess: onClose }); }}>
        <Field label="Tamir / servis bedeli ($)" hint="İsteğe bağlı; maliyet raporuna girer">
          <input inputMode="decimal" value={cost} onChange={(e) => setCost(e.target.value)} autoFocus />
        </Field>
        <ErrorNote error={endDowntime.error} />
      </form>
    </Modal>
  );
}

/** Makine sayfası için: açık duruş, bakım planları. */
export function AssetOps({ assetId, code, plans, downSince, openDowntimeId }: {
  assetId: string; code: string; plans: MaintenancePlan[]; downSince: string | null; openDowntimeId: string | null;
}) {
  const { can } = useAuth();
  const [modal, setModal] = useState<"start" | "end" | "plan" | MaintenancePlan | null>(null);
  return (
    <div className="stack">
      {downSince ? (
        <div className="down-banner" role="status">
          <strong>Duruşta</strong> · {dateTime(downSince)} tarihinden beri
          {can("technician") && openDowntimeId && <button className="btn btn-small" onClick={() => setModal("end")}>Duruşu bitir</button>}
        </div>
      ) : can("technician") && (
        <div><button className="btn btn-ghost btn-small" onClick={() => setModal("start")}>Duruş başlat</button></div>
      )}
      {plans.length === 0 ? <p className="muted small">Bu makine için bakım planı yok.</p> : (
        <ul className="plan-list">
          {plans.map((p) => (
            <li key={p.id}>
              <BandChip band={DUE[p.due_status].band}>{DUE[p.due_status].label}</BandChip>
              <span><strong>{p.name}</strong><span className="muted small"> · {interval(p)} · {remaining(p)}</span></span>
              {can("technician") && p.active && <button className="btn btn-small" onClick={() => setModal(p)}>Yapıldı</button>}
            </li>
          ))}
        </ul>
      )}
      <div className="actions">
        {can("manager") && <button className="btn btn-ghost btn-small" onClick={() => setModal("plan")}>Plan ekle</button>}
        <Link className="btn btn-ghost btn-small" to="/bakim">Tüm bakımlar</Link>
      </div>
      {modal === "start" && <StartDowntimeModal assetId={assetId} onClose={() => setModal(null)} />}
      {modal === "end" && openDowntimeId && <EndDowntimeModal id={openDowntimeId} code={code} onClose={() => setModal(null)} />}
      {modal === "plan" && <PlanForm assetId={assetId} onClose={() => setModal(null)} />}
      {modal && typeof modal === "object" && <CompleteModal plan={modal} onClose={() => setModal(null)} />}
    </div>
  );
}

