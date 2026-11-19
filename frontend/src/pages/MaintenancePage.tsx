import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";
import {
  useAsset, useAssetModels, useAssets, useMaintenanceActions, useMaintenanceDue, useMaintenancePlans, useMaintenanceSummary,
  useSites, useStock, useWorkOrder, useWorkOrders,
} from "../api/hooks";
import type { MaintenancePlan, ReasonCode, WoKind, WoPartIn, WoStatus, WorkOrderDetail } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import { BandChip, Empty, ErrorNote, Field, Loading, Modal, Panel } from "../components/ui";
import { date, dateTime, num, num1, usd } from "../lib/format";
import {
  DUE_STATE_BAND, DUE_STATE_LABEL, REASONS, REASON_LABEL, WO_KIND_LABEL, WO_STATUS_BAND, WO_STATUS_LABEL,
  downtime, dueLeft, dueProgress, intervalLabel,
} from "../lib/maintenance";
import { TcoPanel } from "./TcoPanel";

const q = (v: number | string | null | undefined, unit: string) =>
  v == null ? "–" : `${Number.isInteger(Number(v)) ? num(Number(v)) : num1(Number(v))} ${unit}`;
const parseNum = (v: string) => Number(v.replace(",", "."));
/** datetime-local değeri (yerel saat, dakika hassasiyeti) */
const nowLocal = () => { const d = new Date(); d.setSeconds(0, 0); return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16); };
const toLocal = (iso: string | null) => (iso ? new Date(new Date(iso).getTime() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16) : "");
const toIso = (local: string) => (local ? new Date(local).toISOString() : null);

type Tab = "takvim" | "emirler" | "planlar" | "maliyet";

// ---------- Sarf satırları (emir ve plan ortak) ----------
interface PartLine { part_id: string; qty: string; site_id: string }

function PartLines({ lines, onChange, withSite }: { lines: PartLine[]; onChange: (l: PartLine[]) => void; withSite: boolean }) {
  const stock = useStock({});
  const sites = useSites();
  const catalog = useMemo(() => (stock.data ?? []).filter((s) => !s.is_serialized).sort((a, b) => a.name.localeCompare(b.name, "tr")), [stock.data]);
  const byId = (id: string) => catalog.find((c) => c.part_id === id);
  const set = (i: number, patch: Partial<PartLine>) => onChange(lines.map((l, k) => (k === i ? { ...l, ...patch } : l)));
  return (
    <div className="wo-parts">
      {lines.map((l, i) => {
        const c = byId(l.part_id);
        const here = withSite && c ? Number(c.sites?.find((s) => (s.site_id ?? "") === l.site_id)?.qty ?? 0) : null;
        return (
          <div className="wo-part" key={i}>
            <select value={l.part_id} onChange={(e) => set(i, { part_id: e.target.value })} required aria-label="Sarf kalemi">
              <option value="" disabled>Kalem seçin</option>
              {catalog.map((p) => <option key={p.part_id} value={p.part_id}>{p.name}{p.part_no ? ` · ${p.part_no}` : ""}</option>)}
            </select>
            <input inputMode="decimal" placeholder={`Miktar${c ? ` (${c.unit})` : ""}`} value={l.qty} onChange={(e) => set(i, { qty: e.target.value })} required aria-label="Miktar" />
            {withSite ? (
              <select value={l.site_id} onChange={(e) => set(i, { site_id: e.target.value })} aria-label="Depo">
                <option value="">Genel depo</option>
                {sites.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            ) : <span />}
            <button type="button" className="icon-btn" aria-label="Satırı sil" onClick={() => onChange(lines.filter((_, k) => k !== i))}>×</button>
            {c && (
              <div className="wo-part-hint muted small">
                {withSite ? `Bu depoda ${q(here, c.unit)}, toplam ${q(c.qty, c.unit)}` : `Stokta ${q(c.qty, c.unit)}`}
                {here != null && l.qty && parseNum(l.qty) > here ? <span className="t-critical"> · tamamlarken stok yetmez</span> : null}
              </div>
            )}
          </div>
        );
      })}
      <div className="actions">
        <button type="button" className="btn btn-ghost" onClick={() => onChange([...lines, { part_id: "", qty: "", site_id: "" }])}>+ Sarf ekle</button>
      </div>
    </div>
  );
}

const toPartsIn = (lines: PartLine[]): WoPartIn[] =>
  lines.filter((l) => l.part_id && l.qty).map((l) => ({ part_id: l.part_id, qty: parseNum(l.qty), site_id: l.site_id || null }));

// ---------- Yeni iş emri ----------
function NewWorkOrderModal({ prefill, onClose, onCreated }: {
  prefill: { asset_id?: string; plan_id?: string; kind?: WoKind }; onClose: () => void; onCreated: (id: string) => void;
}) {
  const assets = useAssets();
  const { createWorkOrder } = useMaintenanceActions();
  const [assetId, setAssetId] = useState(prefill.asset_id ?? "");
  const [kind, setKind] = useState<WoKind>(prefill.kind ?? "planned");
  const [planId, setPlanId] = useState(prefill.plan_id ?? "");
  const [title, setTitle] = useState("");
  const [desc, setDesc] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [dueHours, setDueHours] = useState("");
  const [downFrom, setDownFrom] = useState(nowLocal());
  const [reason, setReason] = useState<ReasonCode | "">("");
  const [partItem, setPartItem] = useState("");
  const [partsMode, setPartsMode] = useState<"plan" | "custom">("plan");
  const [lines, setLines] = useState<PartLine[]>([]);
  const plans = useMaintenancePlans(assetId ? { asset_id: assetId } : {});
  const due = useMaintenanceDue(assetId ? { asset_id: assetId } : {});
  const asset = useAsset(assetId || undefined);
  const plan = plans.data?.find((p) => p.id === planId);
  const dueRow = due.data?.find((d) => d.plan_id === planId && d.asset_id === assetId);
  const installed = (asset.data?.positions ?? []).filter((p) => p.part_item_id);

  // Makine değişince plan geçerliliğini koru; plan seçilince hedefi öner
  useEffect(() => { if (planId && plans.data && !plans.data.some((p) => p.id === planId)) setPlanId(""); }, [plans.data, planId]);
  useEffect(() => {
    if (!dueRow) return;
    setDueAt(dueRow.next_due_at ?? "");
    setDueHours(dueRow.next_due_hours != null ? String(dueRow.next_due_hours) : "");
  }, [dueRow]);

  const editPlanParts = () => {
    setLines((plan?.parts ?? []).map((p) => ({ part_id: p.part_id, qty: String(p.qty), site_id: asset.data?.site_id ?? "" })));
    setPartsMode("custom");
  };
  const valid = assetId && (kind === "breakdown" ? title.trim().length >= 2 : (planId || title.trim().length >= 2));
  const submit = (e: FormEvent) => {
    e.preventDefault();
    createWorkOrder.mutate({
      asset_id: assetId, kind, plan_id: kind === "planned" && planId ? planId : null, title: title.trim() || null,
      description: desc.trim() || null,
      due_at: kind === "planned" && dueAt ? dueAt : null, due_hours: kind === "planned" && dueHours ? parseNum(dueHours) : null,
      down_from: kind === "breakdown" ? toIso(downFrom) : null, reason_code: kind === "breakdown" && reason ? reason : null,
      part_item_id: kind === "breakdown" && partItem ? partItem : null,
      parts: kind === "planned" && planId && partsMode === "plan" ? null : toPartsIn(lines),
    }, { onSuccess: (w) => onCreated(w.id) });
  };

  return (
    <Modal title={kind === "breakdown" ? "Arıza bildir" : "Bakım emri aç"} onClose={onClose} wide>
      <form className="form" onSubmit={submit}>
        <div className="form-row">
          <Field label="Makine">
            <select value={assetId} onChange={(e) => setAssetId(e.target.value)} required autoFocus>
              <option value="" disabled>Makine seçin</option>
              {assets.data?.map((a) => <option key={a.id} value={a.id}>{a.code}{a.model ? ` · ${a.model}` : ""}</option>)}
            </select>
          </Field>
          <Field label="Tür">
            <div className="seg" role="group" aria-label="Emir türü">
              <button type="button" aria-pressed={kind === "planned"} onClick={() => setKind("planned")}>Planlı bakım</button>
              <button type="button" aria-pressed={kind === "breakdown"} onClick={() => setKind("breakdown")}>Arıza</button>
            </div>
          </Field>
          {kind === "planned" && (
            <Field label="Bakım planı" hint={plan ? `${intervalLabel(plan)}${dueRow ? ` · ${dueLeft(dueRow)}` : ""}` : "Plan dışı bakımda boş bırakıp başlık yazın"}>
              <select value={planId} onChange={(e) => { setPlanId(e.target.value); setPartsMode("plan"); }}>
                <option value="">Plan dışı</option>
                {plans.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </Field>
          )}
        </div>
        <Field label={kind === "breakdown" ? "Ne oldu?" : "Başlık"} hint={kind === "planned" && plan ? `Boşsa plan adı: ${plan.name}` : undefined}>
          <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={160} required={kind === "breakdown" || !planId}
                 placeholder={kind === "breakdown" ? "Örn. hidrolik hortum patladı" : plan?.name ?? "Örn. fren ayarı"} />
        </Field>
        {kind === "planned" ? (
          <div className="form-row">
            <Field label="Hedef tarih"><input type="date" value={dueAt} onChange={(e) => setDueAt(e.target.value)} /></Field>
            <Field label="Hedef makine saati" hint={asset.data ? `Makine şu an ${num(asset.data.meter_hours)} saatte` : undefined}>
              <input inputMode="decimal" value={dueHours} onChange={(e) => setDueHours(e.target.value)} />
            </Field>
          </div>
        ) : (
          <div className="form-row">
            <Field label="Makine ne zaman durdu?"><input type="datetime-local" value={downFrom} onChange={(e) => setDownFrom(e.target.value)} required /></Field>
            <Field label="Sebep">
              <select value={reason} onChange={(e) => setReason(e.target.value as ReasonCode | "")}>
                <option value="">Henüz bilinmiyor</option>
                {REASONS.map((r) => <option key={r} value={r}>{REASON_LABEL[r]}</option>)}
              </select>
            </Field>
            <Field label="İlgili parça" hint="Makinedeki takılı parçalardan">
              <select value={partItem} onChange={(e) => setPartItem(e.target.value)} disabled={!assetId}>
                <option value="">Yok / belirsiz</option>
                {installed.map((p) => <option key={p.code} value={p.part_item_id!}>{p.code} · {p.serial_no ?? p.part_name}</option>)}
              </select>
            </Field>
          </div>
        )}
        <Field label="Açıklama"><textarea value={desc} onChange={(e) => setDesc(e.target.value)} rows={2} maxLength={2000} /></Field>

        <h3 className="mini-head">Sarf malzemesi <span className="muted small">(tamamlanınca stoktan düşer)</span></h3>
        {kind === "planned" && planId && partsMode === "plan" ? (
          <div className="row-between">
            <span className="small">
              {plan?.parts.length ? `Plandan: ${plan.parts.map((p) => `${q(p.qty, p.unit)} ${p.name}`).join(", ")}` : "Planda sarf tanımlı değil"}
            </span>
            <button type="button" className="link-btn" onClick={editPlanParts}>Düzenle</button>
          </div>
        ) : <PartLines lines={lines} onChange={setLines} withSite />}
        <ErrorNote error={createWorkOrder.error} />
        <div className="actions">
          <button className="btn btn-primary" disabled={!valid || createWorkOrder.isPending}>
            {createWorkOrder.isPending ? "Kaydediliyor…" : kind === "breakdown" ? "Arızayı kaydet" : "Emri aç"}
          </button>
          <button type="button" className="btn btn-ghost" onClick={onClose}>Vazgeç</button>
        </div>
        {kind === "breakdown" && <p className="muted small">Kaydedilince makine <strong>arızalı</strong> görünür; emir tamamlanınca çalışmaya döner ve duruş süresi hesaplanır.</p>}
      </form>
    </Modal>
  );
}

// ---------- Tamamlama ----------
function CompleteForm({ w, onDone }: { w: WorkOrderDetail; onDone: () => void }) {
  const { setWorkOrderStatus } = useMaintenanceActions();
  const [hours, setHours] = useState(String(w.asset_meter_hours));
  const [downTo, setDownTo] = useState(nowLocal());
  const [labor, setLabor] = useState(w.labor_cost != null ? String(w.labor_cost) : "");
  const [external, setExternal] = useState(w.external_cost != null ? String(w.external_cost) : "");
  const [notes, setNotes] = useState("");
  const short = w.parts.filter((p) => Number(p.in_stock) < Number(p.qty));
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setWorkOrderStatus.mutate({ id: w.id, body: {
      status: "done", asset_hours: hours ? parseNum(hours) : null, down_to: w.kind === "breakdown" ? toIso(downTo) : null,
      labor_cost: labor ? parseNum(labor) : null, external_cost: external ? parseNum(external) : null, notes: notes.trim() || null,
    } }, { onSuccess: onDone });
  };
  return (
    <form className="form po-receive" onSubmit={submit}>
      <h3 className="mini-head">Tamamla</h3>
      <div className="form-row">
        <Field label="Makine saati" hint={`Sayaç ${num(w.asset_meter_hours)}; büyükse sayaç güncellenir`}>
          <input inputMode="decimal" value={hours} onChange={(e) => setHours(e.target.value)} />
        </Field>
        {w.kind === "breakdown" && (
          <Field label="Çalışmaya dönüş" hint={w.down_from ? `Duruş başlangıcı ${dateTime(w.down_from)}` : undefined}>
            <input type="datetime-local" value={downTo} onChange={(e) => setDownTo(e.target.value)} />
          </Field>
        )}
        <Field label="İşçilik $"><input inputMode="decimal" value={labor} onChange={(e) => setLabor(e.target.value)} /></Field>
        <Field label="Dış servis / nakliye $"><input inputMode="decimal" value={external} onChange={(e) => setExternal(e.target.value)} /></Field>
      </div>
      <Field label="Yapılan iş"><textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} maxLength={2000} /></Field>
      {w.parts.length > 0 && (
        <p className="small">
          Stoktan düşecek: {w.parts.map((p) => `${q(p.qty, p.unit)} ${p.name}`).join(", ")}.
          {short.length > 0 && <span className="t-critical"> Yetersiz: {short.map((p) => `${p.name} (depoda ${q(p.in_stock, p.unit)})`).join(", ")}.</span>}
        </p>
      )}
      <ErrorNote error={setWorkOrderStatus.error} />
      <div className="actions">
        <button className="btn btn-primary" disabled={setWorkOrderStatus.isPending}>{setWorkOrderStatus.isPending ? "Kaydediliyor…" : "Tamamlandı olarak kaydet"}</button>
        <button type="button" className="btn btn-ghost" onClick={onDone}>Vazgeç</button>
      </div>
    </form>
  );
}

// ---------- İş emri ayrıntısı ----------
function WorkOrderModal({ id, onClose }: { id: string; onClose: () => void }) {
  const { can } = useAuth();
  const wo = useWorkOrder(id);
  const { updateWorkOrder, setWorkOrderStatus } = useMaintenanceActions();
  const [mode, setMode] = useState<"view" | "edit" | "complete">("view");
  const [title, setTitle] = useState("");
  const [desc, setDesc] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [dueHours, setDueHours] = useState("");
  const [downFrom, setDownFrom] = useState("");
  const [reason, setReason] = useState<ReasonCode | "">("");
  const [lines, setLines] = useState<PartLine[]>([]);
  const w = wo.data;
  useEffect(() => {
    if (!w) return;
    setTitle(w.title); setDesc(w.description ?? ""); setDueAt(w.due_at ?? ""); setDueHours(w.due_hours != null ? String(w.due_hours) : "");
    setDownFrom(toLocal(w.down_from)); setReason(w.reason_code ?? "");
    setLines(w.parts.map((p) => ({ part_id: p.part_id, qty: String(p.qty), site_id: p.site_id ?? "" })));
  }, [w]);
  if (!w) return <Modal title="İş emri" onClose={onClose} wide>{wo.error ? <ErrorNote error={wo.error} /> : <Loading />}</Modal>;

  const isOpen = w.status === "open" || w.status === "in_progress";
  const cost = Number(w.labor_cost ?? 0) + Number(w.external_cost ?? 0) + Number(w.parts_cost ?? 0);
  const save = () => updateWorkOrder.mutate({ id, body: {
    title: title.trim(), description: desc.trim() || null,
    ...(w.kind === "planned" ? { due_at: dueAt || null, due_hours: dueHours ? parseNum(dueHours) : null }
                            : { down_from: toIso(downFrom), reason_code: reason || null }),
    parts: toPartsIn(lines),
  } }, { onSuccess: () => setMode("view") });

  return (
    <Modal title={`${w.number} · ${w.title}`} onClose={onClose} wide>
      <div className="stack">
        <div className="row-between">
          <span>
            <BandChip band={w.kind === "breakdown" && isOpen ? "critical" : WO_STATUS_BAND[w.status]}>{WO_KIND_LABEL[w.kind]} · {WO_STATUS_LABEL[w.status]}</BandChip>
            {w.late && <span className="t-watch small"> gecikti</span>}
          </span>
          <span className="muted small">
            {w.created_by_name ? `${w.created_by_name} açtı, ${dateTime(w.created_at)}` : dateTime(w.created_at)}
            {w.started_at ? ` · başladı ${dateTime(w.started_at)}` : ""}
            {w.completed_at ? ` · ${w.status === "done" ? "tamamlandı" : "kapandı"} ${dateTime(w.completed_at)}${w.completed_by_name ? ` (${w.completed_by_name})` : ""}` : ""}
          </span>
        </div>

        {mode === "edit" ? (
          <div className="form">
            <Field label="Başlık"><input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={160} required /></Field>
            {w.kind === "planned" ? (
              <div className="form-row">
                <Field label="Hedef tarih"><input type="date" value={dueAt} onChange={(e) => setDueAt(e.target.value)} /></Field>
                <Field label="Hedef makine saati"><input inputMode="decimal" value={dueHours} onChange={(e) => setDueHours(e.target.value)} /></Field>
              </div>
            ) : (
              <div className="form-row">
                <Field label="Makine ne zaman durdu?"><input type="datetime-local" value={downFrom} onChange={(e) => setDownFrom(e.target.value)} /></Field>
                <Field label="Sebep"><select value={reason} onChange={(e) => setReason(e.target.value as ReasonCode | "")}>
                  <option value="">Henüz bilinmiyor</option>
                  {REASONS.map((r) => <option key={r} value={r}>{REASON_LABEL[r]}</option>)}
                </select></Field>
              </div>
            )}
            <Field label="Açıklama"><textarea value={desc} onChange={(e) => setDesc(e.target.value)} rows={3} maxLength={2000} /></Field>
            <h3 className="mini-head">Sarf malzemesi</h3>
            <PartLines lines={lines} onChange={setLines} withSite />
            <ErrorNote error={updateWorkOrder.error} />
            <div className="actions">
              <button className="btn btn-primary" onClick={save} disabled={updateWorkOrder.isPending || title.trim().length < 2}>Kaydet</button>
              <button className="btn btn-ghost" onClick={() => setMode("view")}>Vazgeç</button>
            </div>
          </div>
        ) : (
          <>
            <dl className="facts">
              <div className="fact"><dt>Makine</dt><dd><Link to={`/makine/${w.asset_id}`}>{w.asset_code}</Link><span className="muted small"> · {num(w.asset_meter_hours)} sa</span></dd></div>
              {w.kind === "planned" ? (
                <>
                  <div className="fact"><dt>Plan</dt><dd>{w.plan_name ?? <span className="muted">plan dışı</span>}</dd></div>
                  <div className="fact"><dt>Hedef</dt><dd className={w.late ? "t-watch" : undefined}>
                    {[w.due_hours != null ? `${num(Number(w.due_hours))} sa` : null, w.due_at ? date(w.due_at) : null].filter(Boolean).join(" · ") || "–"}
                  </dd></div>
                </>
              ) : (
                <>
                  <div className="fact"><dt>Sebep</dt><dd>{w.reason_code ? REASON_LABEL[w.reason_code] : <span className="muted">bilinmiyor</span>}
                    {w.part_item_id && <div className="small"><Link to={`/parca/${w.part_item_id}`}>{w.part_serial_no ?? w.part_name}</Link></div>}</dd></div>
                  <div className="fact"><dt>Duruş</dt><dd className={isOpen ? "t-critical" : undefined}>
                    {w.downtime_minutes != null ? downtime(w.downtime_minutes) : w.down_from ? "sürüyor" : "–"}
                    <div className="muted small">{w.down_from ? `${dateTime(w.down_from)}${w.down_to ? ` → ${dateTime(w.down_to)}` : ""}` : ""}</div>
                  </dd></div>
                </>
              )}
              <div className="fact"><dt>Maliyet</dt><dd>{cost > 0 ? usd(cost) : "–"}
                <div className="muted small">{[w.labor_cost != null ? `işçilik ${usd(Number(w.labor_cost))}` : null, w.external_cost != null ? `dış ${usd(Number(w.external_cost))}` : null,
                  Number(w.parts_cost ?? 0) > 0 ? `sarf ${usd(Number(w.parts_cost))}` : null].filter(Boolean).join(" · ")}</div></dd></div>
              {w.asset_hours_at_done != null && <div className="fact"><dt>Bakım saati</dt><dd>{num(Number(w.asset_hours_at_done))} sa</dd></div>}
            </dl>
            {w.description && <p className="small" style={{ whiteSpace: "pre-wrap" }}>{w.description}</p>}
          </>
        )}

        {w.checklist && w.checklist.length > 0 && mode !== "edit" && (
          <>
            <h3 className="mini-head">Kontrol listesi</h3>
            <ul className="checklist">{w.checklist.map((c, i) => <li key={i}>{c}</li>)}</ul>
          </>
        )}

        {w.parts.length > 0 && mode !== "edit" && (
          <div className="table-wrap">
            <table className="table po-table">
              <thead><tr><th>Sarf</th><th className="num">Miktar</th><th>Depo</th><th className="num">Depoda</th><th className="num">Birim</th></tr></thead>
              <tbody>
                {w.parts.map((p) => (
                  <tr key={p.id}>
                    <td><strong>{p.name}</strong></td>
                    <td className="num">{q(p.qty, p.unit)}</td>
                    <td>{p.site_name ?? "Genel depo"}</td>
                    <td className={`num${isOpen && Number(p.in_stock) < Number(p.qty) ? " t-critical" : ""}`}>{q(p.in_stock, p.unit)}</td>
                    <td className="num">{usd(p.unit_cost)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {mode === "complete" ? <CompleteForm w={w} onDone={() => setMode("view")} /> : mode === "view" && isOpen && (
          <div className="actions">
            {w.status === "open" && can("technician") && (
              <button className="btn btn-primary" onClick={() => setWorkOrderStatus.mutate({ id, body: { status: "in_progress" } })} disabled={setWorkOrderStatus.isPending}>Başla</button>)}
            {can("technician") && <button className={`btn ${w.status === "in_progress" ? "btn-primary" : "btn-ghost"}`} onClick={() => setMode("complete")}>Tamamla</button>}
            {can("technician") && <button className="btn btn-ghost" onClick={() => setMode("edit")}>Düzenle</button>}
            {can("manager") && (
              <button className="btn btn-ghost t-critical" onClick={() => setWorkOrderStatus.mutate({ id, body: { status: "cancelled" } })} disabled={setWorkOrderStatus.isPending}>İptal et</button>)}
          </div>
        )}
        {mode === "view" && <ErrorNote error={setWorkOrderStatus.error} />}
      </div>
    </Modal>
  );
}

// ---------- Takvim: sıradaki bakımlar ----------
function DuePanel({ onNew, onOpen }: { onNew: (p: { asset_id: string; plan_id: string }) => void; onOpen: (id: string) => void }) {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const assets = useAssets();
  const assetId = params.get("makine") ?? "";
  const state = params.get("durum") ?? "";
  const due = useMaintenanceDue({ asset_id: assetId || undefined, state: state || undefined });
  const set = (k: string, v: string) => { const n = new URLSearchParams(params); if (v) n.set(k, v); else n.delete(k); setParams(n, { replace: true }); };
  return (
    <Panel title="Sıradaki bakımlar" sub="Plan × makine; son bakımdan periyot kadar sonra. Yaklaşıyor eşiği firma ayarı">
      <div className="filters">
        <select value={assetId} onChange={(e) => set("makine", e.target.value)} aria-label="Makine">
          <option value="">Tüm makineler</option>
          {assets.data?.map((a) => <option key={a.id} value={a.id}>{a.code}</option>)}
        </select>
        <select value={state} onChange={(e) => set("durum", e.target.value)} aria-label="Durum">
          <option value="">Hepsi</option>
          <option value="overdue">Gecikenler</option>
          <option value="due_soon">Yaklaşanlar</option>
        </select>
      </div>
      {due.isLoading ? <Loading /> : due.error ? <ErrorNote error={due.error} /> : (due.data?.length ?? 0) === 0 ? (
        <Empty>{assetId || state ? "Bu filtreye uyan bakım yok." : "Henüz bakım planı yok. Planlar sekmesinden ekleyin."}</Empty>
      ) : (
        <div className="table-wrap">
          <table className="table due">
            <thead><tr><th>Makine</th><th>Bakım</th><th>Son</th><th>Sıradaki</th><th>Kalan</th><th>Durum</th><th /></tr></thead>
            <tbody>
              {due.data!.map((d) => (
                <tr key={`${d.plan_id}-${d.asset_id}`}>
                  <td><Link to={`/makine/${d.asset_id}`}><strong>{d.asset_code}</strong></Link><div className="muted small">{num(Number(d.meter_hours))} sa</div></td>
                  <td>{d.name}<div className="muted small">{intervalLabel(d)}</div>
                    <div className="due-bar" aria-hidden="true"><span style={{ width: `${Math.round(dueProgress(d) * 100)}%`, ["--c" as string]: `var(--${DUE_STATE_BAND[d.state]})` }} /></div></td>
                  <td className="small">{d.last_done_hours != null ? `${num(Number(d.last_done_hours))} sa` : d.last_done_at ? date(d.last_done_at) : <span className="muted">yok</span>}
                    {d.last_done_number && <div className="muted small">{d.last_done_number}</div>}</td>
                  <td className="small">{[d.next_due_hours != null ? `${num(Number(d.next_due_hours))} sa` : null, d.next_due_at ? date(d.next_due_at) : null].filter(Boolean).join(" · ")}</td>
                  <td className="small">{dueLeft(d)}</td>
                  <td><BandChip band={DUE_STATE_BAND[d.state]}>{DUE_STATE_LABEL[d.state]}</BandChip></td>
                  <td className="row-actions">
                    {d.open_work_order_id ? (
                      <button className="link-btn" onClick={() => onOpen(d.open_work_order_id!)}>{d.open_work_order_number} {d.open_work_order_status === "in_progress" ? "sürüyor" : "açık"}</button>
                    ) : can("technician") && (
                      <button className={`btn btn-small${d.state !== "ok" ? " btn-primary" : ""}`} onClick={() => onNew({ asset_id: d.asset_id, plan_id: d.plan_id })}>Emir aç</button>)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

function SummaryPanel() {
  const s = useMaintenanceSummary();
  const rows = (s.data ?? []).filter((r) => r.planned_done + r.breakdowns + r.open_orders > 0);
  return (
    <Panel title="Makine başına bakım, son 12 ay" sub="Planlı bakım, arıza ve duruş; maliyet = işçilik + dış servis + sarf" className="mt">
      {s.isLoading ? <Loading /> : rows.length === 0 ? <Empty>Henüz tamamlanmış iş emri yok.</Empty> : (
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Makine</th><th className="num">Planlı</th><th className="num">Arıza</th><th className="num">Duruş</th><th className="num">Maliyet</th><th className="num">Açık emir</th><th>Son bakım</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.asset_id}>
                  <td><Link to={`/makine/${r.asset_id}`}><strong>{r.asset_code}</strong></Link>{r.asset_status === "down" && <span className="t-critical small"> · arızalı</span>}</td>
                  <td className="num">{r.planned_done}</td>
                  <td className={`num${r.breakdowns ? " t-watch" : ""}`}>{r.breakdowns}</td>
                  <td className="num">{downtime(r.downtime_minutes)}</td>
                  <td className="num">{usd(Number(r.cost_12m))}</td>
                  <td className="num">{r.open_orders || "–"}</td>
                  <td className="small">{date(r.last_done_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

// ---------- İş emirleri ----------
function OrdersPanel({ onOpen, onNew }: { onOpen: (id: string) => void; onNew: (kind: WoKind) => void }) {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const assets = useAssets();
  const f = { status: params.get("durum") ?? "", kind: params.get("tur") ?? "", asset: params.get("makine") ?? "", q: params.get("q") ?? "", all: params.get("tumu") === "1" };
  const orders = useWorkOrders({ status: f.status || undefined, kind: f.kind || undefined, asset_id: f.asset || undefined, q: f.q || undefined, open_only: !f.all && !f.status });
  const set = (k: string, v: string) => { const n = new URLSearchParams(params); if (v) n.set(k, v); else n.delete(k); setParams(n, { replace: true }); };
  return (
    <Panel title="İş emirleri" actions={can("technician") ? (
      <div className="actions" style={{ marginTop: 0 }}>
        <button className="btn btn-ghost t-critical" onClick={() => onNew("breakdown")}>Arıza bildir</button>
        <button className="btn btn-primary" onClick={() => onNew("planned")}>Bakım emri</button>
      </div>) : undefined}>
      <div className="filters">
        <input type="search" placeholder="Emir no, başlık veya makine" value={f.q} onChange={(e) => set("q", e.target.value)} aria-label="Ara" />
        <select value={f.asset} onChange={(e) => set("makine", e.target.value)} aria-label="Makine">
          <option value="">Tüm makineler</option>
          {assets.data?.map((a) => <option key={a.id} value={a.id}>{a.code}</option>)}
        </select>
        <select value={f.kind} onChange={(e) => set("tur", e.target.value)} aria-label="Tür">
          <option value="">Planlı ve arıza</option>
          <option value="planned">Planlı bakım</option>
          <option value="breakdown">Arıza</option>
        </select>
        <select value={f.status} onChange={(e) => set("durum", e.target.value)} aria-label="Durum">
          <option value="">Açık olanlar</option>
          {(Object.keys(WO_STATUS_LABEL) as WoStatus[]).map((s) => <option key={s} value={s}>{WO_STATUS_LABEL[s]}</option>)}
        </select>
        <label className="inline-check"><input type="checkbox" checked={f.all} onChange={(e) => set("tumu", e.target.checked ? "1" : "")} /> Kapananları da göster</label>
      </div>
      {orders.isLoading ? <Loading /> : orders.error ? <ErrorNote error={orders.error} /> : (orders.data?.length ?? 0) === 0 ? (
        <Empty>Bu filtrelere uyan iş emri yok.</Empty>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>No</th><th>Durum</th><th>Makine</th><th>İş</th><th>Hedef / duruş</th><th className="num">Maliyet</th></tr></thead>
            <tbody>
              {orders.data!.map((w) => {
                const open = w.status === "open" || w.status === "in_progress";
                const cost = Number(w.labor_cost ?? 0) + Number(w.external_cost ?? 0) + Number(w.parts_cost ?? 0);
                return (
                  <tr key={w.id} onClick={() => onOpen(w.id)}>
                    <td><strong>{w.number}</strong><div className="muted small">{date(w.created_at)}{w.created_by_name ? ` · ${w.created_by_name}` : ""}</div></td>
                    <td><BandChip band={w.kind === "breakdown" && open ? "critical" : WO_STATUS_BAND[w.status]}>{WO_STATUS_LABEL[w.status]}</BandChip>
                      {w.late && <div className="t-watch small">gecikti</div>}</td>
                    <td><strong>{w.asset_code}</strong></td>
                    <td><div>{w.title}</div><div className="muted small">{WO_KIND_LABEL[w.kind]}{w.reason_code ? ` · ${REASON_LABEL[w.reason_code]}` : ""}{w.part_count ? ` · ${w.part_count} sarf` : ""}</div></td>
                    <td className="small">
                      {w.kind === "planned"
                        ? [w.due_hours != null ? `${num(Number(w.due_hours))} sa` : null, w.due_at ? date(w.due_at) : null].filter(Boolean).join(" · ") || "–"
                        : w.downtime_minutes != null ? `${downtime(w.downtime_minutes)} duruş` : w.down_from ? <span className="t-critical">{dateTime(w.down_from)} beri duruyor</span> : "–"}
                    </td>
                    <td className="num">{cost > 0 ? usd(cost) : "–"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

// ---------- Planlar ----------
function PlanForm({ initial, onDone }: { initial?: MaintenancePlan; onDone: () => void }) {
  const assets = useAssets();
  const models = useAssetModels();
  const { createPlan, updatePlan } = useMaintenanceActions();
  const [name, setName] = useState(initial?.name ?? "");
  const [scope, setScope] = useState<"model" | "asset">(initial?.asset_id ? "asset" : "model");
  const [assetId, setAssetId] = useState(initial?.asset_id ?? "");
  const [modelId, setModelId] = useState(initial?.model_id ?? "");
  const [hours, setHours] = useState(initial?.interval_hours != null ? String(initial.interval_hours) : "");
  const [days, setDays] = useState(initial?.interval_days != null ? String(initial.interval_days) : "");
  const [checklist, setChecklist] = useState((initial?.checklist ?? []).join("\n"));
  const [notes, setNotes] = useState(initial?.notes ?? "");
  const [active, setActive] = useState(initial?.is_active ?? true);
  const [lines, setLines] = useState<PartLine[]>((initial?.parts ?? []).map((p) => ({ part_id: p.part_id, qty: String(p.qty), site_id: "" })));
  const m = initial ? updatePlan : createPlan;
  const valid = name.trim().length >= 2 && (scope === "asset" ? assetId : modelId) && (hours || days);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const body = {
      name: name.trim(), asset_id: scope === "asset" ? assetId : null, model_id: scope === "model" ? modelId : null,
      interval_hours: hours ? parseNum(hours) : null, interval_days: days ? Number(days) : null,
      checklist: checklist.split("\n").map((s) => s.trim()).filter(Boolean), notes: notes.trim() || null, is_active: active,
      parts: toPartsIn(lines).map(({ part_id, qty }) => ({ part_id, qty })),
    };
    if (initial) updatePlan.mutate({ id: initial.id, body }, { onSuccess: onDone });
    else createPlan.mutate(body, { onSuccess: onDone });
  };
  return (
    <form className="form" onSubmit={submit}>
      <Field label="Plan adı"><input value={name} onChange={(e) => setName(e.target.value)} required minLength={2} maxLength={120} autoFocus placeholder="Örn. 500 saat periyodik bakım" /></Field>
      <div className="form-row">
        <Field label="Kapsam">
          <div className="seg" role="group" aria-label="Kapsam">
            <button type="button" aria-pressed={scope === "model"} onClick={() => setScope("model")}>Model</button>
            <button type="button" aria-pressed={scope === "asset"} onClick={() => setScope("asset")}>Tek makine</button>
          </div>
        </Field>
        {scope === "model" ? (
          <Field label="Makine modeli" hint="Modelin tüm makinelerine uygulanır">
            <select value={modelId} onChange={(e) => setModelId(e.target.value)} required>
              <option value="" disabled>Model seçin</option>
              {models.data?.map((mo) => <option key={mo.id} value={mo.id}>{mo.manufacturer} {mo.model}</option>)}
            </select>
          </Field>
        ) : (
          <Field label="Makine">
            <select value={assetId} onChange={(e) => setAssetId(e.target.value)} required>
              <option value="" disabled>Makine seçin</option>
              {assets.data?.map((a) => <option key={a.id} value={a.id}>{a.code}</option>)}
            </select>
          </Field>
        )}
      </div>
      <div className="form-row">
        <Field label="Periyot (saat)" hint="Makine saatine göre; örn. 500"><input inputMode="decimal" value={hours} onChange={(e) => setHours(e.target.value)} /></Field>
        <Field label="Periyot (gün)" hint="Takvime göre; örn. 180. İkisi birden olabilir, hangisi önce gelirse"><input inputMode="numeric" value={days} onChange={(e) => setDays(e.target.value)} /></Field>
      </div>
      <Field label="Kontrol listesi" hint="Her satır bir madde"><textarea value={checklist} onChange={(e) => setChecklist(e.target.value)} rows={4} /></Field>
      <h3 className="mini-head">Her bakımda kullanılan sarf</h3>
      <PartLines lines={lines} onChange={setLines} withSite={false} />
      <Field label="Not"><input value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={1000} /></Field>
      {initial && <label className="inline-check"><input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} /> Aktif (takvimde görünür)</label>}
      <ErrorNote error={m.error} />
      <div className="actions">
        <button className="btn btn-primary" disabled={m.isPending || !valid}>{m.isPending ? "Kaydediliyor…" : "Kaydet"}</button>
        <button type="button" className="btn btn-ghost" onClick={onDone}>Vazgeç</button>
      </div>
    </form>
  );
}

function PlansPanel() {
  const { can } = useAuth();
  const [all, setAll] = useState(false);
  const plans = useMaintenancePlans({ include_inactive: all });
  const [edit, setEdit] = useState<MaintenancePlan | "new" | null>(null);
  return (
    <Panel title="Bakım planları" sub="Saat ve/veya takvim periyodu; tek makine ya da modelin tüm makineleri"
           actions={can("manager") ? <button className="btn btn-primary" onClick={() => setEdit("new")}>Plan ekle</button> : undefined}>
      <div className="filters">
        <label className="inline-check"><input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /> Pasifleri de göster</label>
      </div>
      {plans.isLoading ? <Loading /> : (plans.data?.length ?? 0) === 0 ? <Empty>Henüz bakım planı yok.</Empty> : (
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Plan</th><th>Kapsam</th><th>Periyot</th><th>Sarf</th><th className="num">Kontrol</th><th /></tr></thead>
            <tbody>
              {plans.data!.map((p) => (
                <tr key={p.id}>
                  <td><strong>{p.name}</strong>{!p.is_active && <span className="muted small"> · pasif</span>}{p.notes && <div className="muted small">{p.notes}</div>}</td>
                  <td>{p.asset_id ? <Link to={`/makine/${p.asset_id}`}>{p.asset_code}</Link> : <>{p.model_name}<div className="muted small">{p.asset_count} makine</div></>}</td>
                  <td>{intervalLabel(p)}</td>
                  <td className="small">{p.parts.length ? p.parts.map((x) => `${q(x.qty, x.unit)} ${x.name}`).join(", ") : <span className="muted">–</span>}</td>
                  <td className="num">{p.checklist.length || "–"}</td>
                  <td>{can("manager") && <button className="link-btn" onClick={() => setEdit(p)}>Düzenle</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {edit && (
        <Modal title={edit === "new" ? "Yeni bakım planı" : edit.name} onClose={() => setEdit(null)} wide>
          <PlanForm initial={edit === "new" ? undefined : edit} onDone={() => setEdit(null)} />
        </Modal>
      )}
    </Panel>
  );
}

// ---------- Sayfa ----------
export function MaintenancePage() {
  const [params, setParams] = useSearchParams();
  const tab = (params.get("sekme") as Tab | null) ?? "takvim";
  const openId = params.get("emir");
  const isNew = params.get("yeni") === "1";
  const set = (k: string, v: string) => { const n = new URLSearchParams(params); if (v) n.set(k, v); else n.delete(k); setParams(n, { replace: true }); };
  const openNew = (p: { asset_id?: string; plan_id?: string; kind?: WoKind }) => {
    const n = new URLSearchParams(params); n.set("yeni", "1");
    if (p.asset_id) n.set("makine", p.asset_id); if (p.plan_id) n.set("plan", p.plan_id); else n.delete("plan");
    if (p.kind) n.set("tur", p.kind); else n.delete("tur");
    setParams(n);
  };
  const closeNew = () => { const n = new URLSearchParams(params); n.delete("yeni"); n.delete("plan"); setParams(n, { replace: true }); };
  const tabs: { key: Tab; label: string }[] = [{ key: "takvim", label: "Takvim" }, { key: "emirler", label: "İş emirleri" }, { key: "planlar", label: "Planlar" },
    { key: "maliyet", label: "Maliyet" }];
  return (
    <>
      <div className="page-head"><h1>Bakım</h1></div>
      <div className="tabs" role="tablist">
        {tabs.map((t) => <button key={t.key} role="tab" aria-selected={t.key === tab} onClick={() => set("sekme", t.key)}>{t.label}</button>)}
      </div>
      {tab === "takvim" && <><DuePanel onNew={openNew} onOpen={(id) => set("emir", id)} /><SummaryPanel /></>}
      {tab === "emirler" && <OrdersPanel onOpen={(id) => set("emir", id)} onNew={(kind) => openNew({ kind })} />}
      {tab === "planlar" && <PlansPanel />}
      {tab === "maliyet" && <TcoPanel />}
      {isNew && (
        <NewWorkOrderModal
          prefill={{ asset_id: params.get("makine") ?? undefined, plan_id: params.get("plan") ?? undefined, kind: (params.get("tur") as WoKind | null) ?? undefined }}
          onClose={closeNew}
          onCreated={(id) => { const n = new URLSearchParams(params); n.delete("yeni"); n.delete("plan"); n.delete("tur"); n.set("sekme", "emirler"); n.set("emir", id); setParams(n); }} />
      )}
      {openId && <WorkOrderModal id={openId} onClose={() => set("emir", "")} />}
    </>
  );
}
