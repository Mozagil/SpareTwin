import { useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router";
import { useCategoryDefs, useSettingsActions, useTemplateDefs, useTenantSettings } from "../api/hooks";
import type { TemplateDef } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import { BandChip, Empty, ErrorNote, Field, Loading, Panel } from "../components/ui";
import { angleLabel } from "../lib/format";

const ANGLES = ["tread", "sidewall", "damage_closeup", "overview", "nameplate"] as const;
const ANGLE_EXTRA: Record<string, string> = { overview: "Genel görünüm", nameplate: "Etiket / plaka" };
const aLabel = (a: string) => ANGLE_EXTRA[a] ?? angleLabel(a);

function General() {
  const s = useTenantSettings();
  const { save } = useSettingsActions();
  const [f, setF] = useState({ inspection_interval_days: "", purchase_horizon_hours: "" });
  const [mods, setMods] = useState({ tireiq: true, parts: true });
  useEffect(() => {
    if (s.data) {
      setF({ inspection_interval_days: String(s.data.inspection_interval_days), purchase_horizon_hours: String(s.data.purchase_horizon_hours) });
      setMods({ tireiq: s.data.modules.tireiq, parts: s.data.modules.parts });
    }
  }, [s.data]);
  if (s.isLoading) return <Loading />;
  const edit = s.data?.can_edit;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate({ inspection_interval_days: Number(f.inspection_interval_days), purchase_horizon_hours: Number(f.purchase_horizon_hours), modules: mods });
  };
  return (
    <form className="form narrow-form" onSubmit={submit}>
      <fieldset className="fieldset">
        <legend>Modüller</legend>
        <p className="muted small">Filo, saha kontrolü, parçalar, kayıt ve etiketler her firmada açıktır. Kullanmadığınız modülü kapatınca menüden, bildirimlerden ve dashboard'dan kalkar; veriler silinmez.</p>
        <label className="module-row">
          <input type="checkbox" checked={mods.tireiq} disabled={!edit} onChange={(e) => setMods({ ...mods, tireiq: e.target.checked })} />
          <span><strong>Lastik ve jant (TireIQ)</strong><span className="muted small">Lastik aşınması ve maliyeti, jant muayenesi (NDT), lastiğe özel öneriler</span></span>
        </label>
        <label className="module-row">
          <input type="checkbox" checked={mods.parts} disabled={!edit} onChange={(e) => setMods({ ...mods, parts: e.target.checked })} />
          <span><strong>Yedek parça ve bakım</strong><span className="muted small">Stok, satınalma, bakım planları, arıza/duruş, toplam sahip olma maliyeti</span></span>
        </label>
        <label className="module-row disabled">
          <input type="checkbox" checked={false} disabled />
          <span><strong>KOBİ ERP</strong> <span className="chip chip-plain">Yakında</span><span className="muted small">Üretim emirleri, ürün ağacı (BOM), MRP · Faz 4</span></span>
        </label>
      </fieldset>
      <Field label="Saha kontrolü aralığı (gün)" hint="Bu kadar gün kontrol edilmeyen makine için bildirim gelir">
        <input type="number" min={1} max={365} value={f.inspection_interval_days} disabled={!edit}
               onChange={(e) => setF({ ...f, inspection_interval_days: e.target.value })} />
      </Field>
      <Field label="Satınalma ufku (çalışma saati)" hint="Önerilerde bu kadar saat içinde değişecek lastikler hesaba katılır; tedarik sürenize göre ayarlayın">
        <input type="number" min={100} max={10000} step={100} value={f.purchase_horizon_hours} disabled={!edit}
               onChange={(e) => setF({ ...f, purchase_horizon_hours: e.target.value })} />
      </Field>
      <ErrorNote error={save.error} />
      {save.isSuccess && <div className="success-note" role="status">Kaydedildi.</div>}
      {edit ? <div><button className="btn btn-primary" disabled={save.isPending}>Kaydet</button></div>
            : <p className="muted small">Firma ayarlarını sahip veya admin değiştirebilir.</p>}
    </form>
  );
}

type Row = { metric: string; label: string; unit: string; required: boolean; min: string; max: string };

function Categories() {
  const c = useCategoryDefs();
  const { can } = useAuth();
  const { addCategory } = useSettingsActions();
  const [f, setF] = useState({ code: "", name: "", is_serialized: true });
  const [rows, setRows] = useState<Row[]>([]);
  const [angles, setAngles] = useState<string[]>([]);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    addCategory.mutate({
      ...f,
      measurement_profile: rows.filter((r) => r.metric && r.label).map((r) => ({
        metric: r.metric, label: r.label, unit: r.unit || null, required: r.required,
        min: r.min === "" ? null : Number(r.min), max: r.max === "" ? null : Number(r.max),
      })),
      required_photo_angles: angles,
    }, { onSuccess: () => { setF({ code: "", name: "", is_serialized: true }); setRows([]); setAngles([]); } });
  };
  if (c.isLoading) return <Loading />;
  return (
    <div className="stack">
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>Kategori</th><th>Kod</th><th>Takip</th><th>Ölçümler</th><th>Zorunlu fotoğraflar</th><th className="num">Katalog</th><th /></tr></thead>
          <tbody>
            {c.data!.map((x) => (
              <tr key={x.id}>
                <td><strong>{x.name}</strong></td><td><code>{x.code}</code></td>
                <td className="small">{x.is_serialized ? "Seri numaralı" : "Miktarla (sarf)"}</td>
                <td className="small">{x.measurement_profile.map((m) => `${m.label}${m.unit ? ` (${m.unit})` : ""}${m.required ? " *" : ""}`).join(", ") || "–"}</td>
                <td className="small">{x.required_photo_angles.map(aLabel).join(", ") || "–"}</td>
                <td className="num">{x.catalog_items}</td>
                <td>{x.library ? <BandChip band="unknown">Kütüphane</BandChip> : <BandChip band="ok">Firmanın</BandChip>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {can("manager") && (
        <form className="form" onSubmit={submit}>
          <h3 className="mini-head">Firmaya özel kategori ekle</h3>
          <p className="muted small">Örn. zincir, hidrolik hortum, kova dişi. Kategori ekledikten sonra Kayıt → Katalog kalemi ile bu kategoride kalem tanımlayabilirsiniz.</p>
          <div className="form-row">
            <Field label="Kod" hint="küçük harf, rakam ve _ (ör. zincir)"><input value={f.code} onChange={(e) => setF({ ...f, code: e.target.value })} required /></Field>
            <Field label="Ad"><input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required /></Field>
          </div>
          <label className="inline-check"><input type="checkbox" checked={f.is_serialized} onChange={(e) => setF({ ...f, is_serialized: e.target.checked })} /> Seri numarasıyla tek tek izlenir (işaretsizse miktarla izlenen sarf malzemesi)</label>
          <fieldset className="fieldset">
            <legend>Kontrolde ölçülecekler</legend>
            {rows.map((r, i) => (
              <div key={i} className="profile-row">
                <input placeholder="kod (ör. uzama)" value={r.metric} aria-label="Ölçüm kodu" onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, metric: e.target.value } : x))} />
                <input placeholder="ad (ör. Uzama)" value={r.label} aria-label="Ölçüm adı" onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, label: e.target.value } : x))} />
                <input placeholder="birim" value={r.unit} aria-label="Birim" onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, unit: e.target.value } : x))} />
                <input placeholder="en az" inputMode="decimal" value={r.min} aria-label="En az" onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, min: e.target.value } : x))} />
                <input placeholder="en çok" inputMode="decimal" value={r.max} aria-label="En çok" onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, max: e.target.value } : x))} />
                <label className="inline-check"><input type="checkbox" checked={r.required} onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, required: e.target.checked } : x))} /> zorunlu</label>
                <button type="button" className="btn btn-small" onClick={() => setRows(rows.filter((_, j) => j !== i))}>Sil</button>
              </div>
            ))}
            <button type="button" className="btn btn-ghost btn-small" onClick={() => setRows([...rows, { metric: "", label: "", unit: "", required: false, min: "", max: "" }])}>Ölçüm ekle</button>
          </fieldset>
          <fieldset className="fieldset">
            <legend>Zorunlu fotoğraflar</legend>
            <div className="check-row">
              {ANGLES.map((a) => (
                <label key={a} className="inline-check"><input type="checkbox" checked={angles.includes(a)}
                  onChange={(e) => setAngles(e.target.checked ? [...angles, a] : angles.filter((x) => x !== a))} /> {aLabel(a)}</label>
              ))}
            </div>
          </fieldset>
          <ErrorNote error={addCategory.error} />
          <div><button className="btn btn-primary" disabled={addCategory.isPending}>Kategori ekle</button></div>
        </form>
      )}
    </div>
  );
}

function TemplateCard({ t }: { t: TemplateDef }) {
  const { can } = useAuth();
  const cats = useCategoryDefs();
  const { copyTemplate, addPosition, deletePosition } = useSettingsActions();
  const [name, setName] = useState(`${t.name} (firmamız)`);
  const [p, setP] = useState({ code: "", label: "", category_code: "", axle: "" });
  const err = copyTemplate.error ?? addPosition.error ?? deletePosition.error;
  return (
    <Panel title={t.name} sub={`${t.library ? "Ortak kütüphane" : "Firmanın şablonu"} · çizim: ${t.layout} · ${t.models} makine modelinde kullanılıyor`}>
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>Kod</th><th>Pozisyon</th><th>Kategori</th><th>Aks</th><th>Şemada</th><th /></tr></thead>
          <tbody>
            {t.positions.map((x) => (
              <tr key={x.code}>
                <td><code>{x.code}</code></td><td>{x.label}</td><td className="small">{cats.data?.find((c) => c.code === x.category_code)?.name ?? x.category_code}</td>
                <td>{x.axle ?? "–"}</td><td className="small">{x.on_schematic ? "evet" : "tabloda"}</td>
                <td className="row-actions">{!t.library && can("manager") && <button className="btn btn-small" onClick={() => deletePosition.mutate({ id: t.id, code: x.code })}>Sil</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {can("manager") && (t.library ? (
        <form className="filters" onSubmit={(e) => { e.preventDefault(); copyTemplate.mutate({ name, copy_from: t.id }); }}>
          <input value={name} onChange={(e) => setName(e.target.value)} aria-label="Yeni şablon adı" />
          <button className="btn btn-ghost" disabled={copyTemplate.isPending}>Kopyala ve düzenle</button>
        </form>
      ) : (
        <form className="filters" onSubmit={(e) => { e.preventDefault(); addPosition.mutate({ id: t.id, code: p.code, label: p.label, category_code: p.category_code, axle: p.axle ? Number(p.axle) : null }, { onSuccess: () => setP({ code: "", label: "", category_code: "", axle: "" }) }); }}>
          <input placeholder="Kod (ör. A3-L)" value={p.code} onChange={(e) => setP({ ...p, code: e.target.value })} aria-label="Pozisyon kodu" required />
          <input placeholder="Ad (ör. Üçüncü aks sol)" value={p.label} onChange={(e) => setP({ ...p, label: e.target.value })} aria-label="Pozisyon adı" required />
          <select value={p.category_code} onChange={(e) => setP({ ...p, category_code: e.target.value })} aria-label="Kategori" required>
            <option value="">Kategori</option>
            {cats.data?.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}
          </select>
          <input placeholder="Aks" inputMode="numeric" value={p.axle} onChange={(e) => setP({ ...p, axle: e.target.value })} aria-label="Aks" className="qty-input" />
          <button className="btn btn-ghost" disabled={addPosition.isPending}>Pozisyon ekle</button>
        </form>
      ))}
      <ErrorNote error={err} />
    </Panel>
  );
}

function Templates() {
  const t = useTemplateDefs();
  if (t.isLoading) return <Loading />;
  if (!t.data?.length) return <Empty>Şablon yok.</Empty>;
  return (
    <div className="stack">
      <p className="muted small">
        Ortak kütüphanedeki şablonlar değiştirilemez; kopyalayıp düzenleyin. Yeni eklenen pozisyonlar makine sayfasındaki tabloda
        görünür (şemada çizilmez). Kendi şablonunuzu Kayıt → Makine modeli ile bir modele bağlayın.
      </p>
      {t.data.map((x) => <TemplateCard key={x.id} t={x} />)}
    </div>
  );
}

const TABS = [
  { key: "genel", label: "Genel", el: General },
  { key: "kategoriler", label: "Parça kategorileri", el: Categories },
  { key: "sablonlar", label: "Makine şablonları", el: Templates },
];

export function SettingsPage() {
  const [params, setParams] = useSearchParams();
  const active = TABS.find((t) => t.key === params.get("sekme")) ?? TABS[0];
  const Body = active.el;
  return (
    <>
      <div className="page-head"><h1>Ayarlar</h1></div>
      <div className="tabs" role="tablist">
        {TABS.map((t) => <button key={t.key} role="tab" aria-selected={t.key === active.key} onClick={() => setParams({ sekme: t.key })}>{t.label}</button>)}
      </div>
      {active.key === "sablonlar" ? <Body /> : <Panel title={active.label}><Body /></Panel>}
    </>
  );
}
