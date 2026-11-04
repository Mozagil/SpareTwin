import { useState, type FormEvent, type ReactElement, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router";
import { useAssetModels, useCatalogParts, useCreate, useSites, useTemplates } from "../api/hooks";
import type { Role } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import { ErrorNote, Field, Panel } from "../components/ui";
import { ImportPanel } from "./ImportPanel";
import { CATEGORY_LABEL, LAYOUT_LABEL } from "../lib/format";

const nOrNull = (v: string) => (v.trim() === "" ? null : Number(v));
// Seri numarasıyla tek tek izlenen kategoriler; diğerleri (filtre, yağ, keçe) miktarla izlenir
const SERIALIZED = new Set(["tire", "rim", "hyd_cylinder", "hyd_pump", "battery"]);
const sOrNull = (v: string) => (v.trim() === "" ? null : v.trim());

function Success({ children }: { children: ReactNode }) {
  return <div className="success-note" role="status">{children}</div>;
}

// ---------- Parça teslim alma ----------
function ReceiveForm() {
  const [params] = useSearchParams();
  const catalog = useCatalogParts();
  const sites = useSites();
  const create = useCreate<unknown, { id: string; serial_no: string | null; qr_code: string }[]>("/parts", ["parts", "catalog-parts"]);
  const [partId, setPartId] = useState(params.get("kalem") ?? "");
  const [siteId, setSiteId] = useState("");
  const [serials, setSerials] = useState("");
  const [count, setCount] = useState("1");
  const [cost, setCost] = useState("");

  const serialList = serials.split(/[\n,;]+/).map((s) => s.trim()).filter(Boolean);
  const items = serialList.length > 0 ? serialList.map((s) => ({ serial_no: s })) : Array.from({ length: Number(count) || 0 }, () => ({}));

  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate(
      { part_id: partId, site_id: siteId || null, items, purchase_cost: nOrNull(cost) },
      { onSuccess: () => { setSerials(""); setCount("1"); } },
    );
  };
  return (
    <form className="form" onSubmit={submit}>
      <Field label="Katalog kalemi" hint="Seri numaralı parçalar. Filtre, yağ gibi sarf malzemeleri Stok sayfasından girilir.">
        <select value={partId} onChange={(e) => setPartId(e.target.value)} required>
          <option value="">Seçin</option>
          {catalog.data?.filter((c) => c.is_serialized).map((c) => (
            <option key={c.id} value={c.id}>
              {CATEGORY_LABEL[c.category_code] ?? c.category_code} · {c.name}{c.manufacturer ? ` (${c.manufacturer})` : ""} · stok {c.in_stock}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Seri numaraları" hint="Her satıra bir seri no. Boş bırakılırsa aşağıdaki adet kadar seri nosuz kayıt açılır.">
        <textarea rows={4} value={serials} onChange={(e) => setSerials(e.target.value)} placeholder={"MX29-0602\nMX29-0603"} />
      </Field>
      {serialList.length === 0 && (
        <Field label="Adet"><input type="number" min={1} max={100} value={count} onChange={(e) => setCount(e.target.value)} /></Field>
      )}
      <div className="form-row">
        <Field label="Birim fiyat ($)" hint="Boşsa katalog fiyatı">
          <input type="number" min={0} step="0.01" inputMode="decimal" value={cost} onChange={(e) => setCost(e.target.value)} />
        </Field>
        <Field label="Saha / depo">
          <select value={siteId} onChange={(e) => setSiteId(e.target.value)}>
            <option value="">Belirtilmedi</option>
            {sites.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </Field>
      </div>
      <ErrorNote error={create.error} />
      {create.data && (
        <Success>
          {create.data.length} parça stoğa girdi. <Link to="/etiketler">Etiketlerini yazdır</Link>
        </Success>
      )}
      <button className="btn btn-primary" disabled={!partId || items.length === 0 || create.isPending}>
        {items.length > 1 ? `${items.length} parçayı teslim al` : "Teslim al"}
      </button>
    </form>
  );
}

// ---------- Makine ----------
function AssetForm() {
  const models = useAssetModels();
  const sites = useSites();
  const create = useCreate<unknown, { id: string; code: string; qr_code: string }>("/assets", ["assets"]);
  const [f, setF] = useState({ code: "", model_id: "", site_id: "", serial_no: "", year: "", meter_hours: "0" });
  const up = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate(
      {
        code: f.code.trim(), model_id: f.model_id, site_id: f.site_id || null, serial_no: sOrNull(f.serial_no),
        year: nOrNull(f.year), meter_hours: Number(f.meter_hours) || 0,
      },
      { onSuccess: () => setF({ ...f, code: "", serial_no: "" }) },
    );
  };
  return (
    <form className="form" onSubmit={submit}>
      <div className="form-row">
        <Field label="Filo / ekipman no"><input value={f.code} onChange={up("code")} placeholder="LD-12" required maxLength={40} /></Field>
        <Field label="Makine modeli" hint="Listede yoksa “Makine modeli” sekmesinden ekleyin">
          <select value={f.model_id} onChange={up("model_id")} required>
            <option value="">Seçin</option>
            {models.data?.map((m) => <option key={m.id} value={m.id}>{m.manufacturer} {m.model} · {LAYOUT_LABEL[m.layout ?? "generic"]}</option>)}
          </select>
        </Field>
      </div>
      <div className="form-row">
        <Field label="Seri no"><input value={f.serial_no} onChange={up("serial_no")} maxLength={80} /></Field>
        <Field label="Yıl"><input type="number" min={1950} max={2100} value={f.year} onChange={up("year")} /></Field>
        <Field label="Motor saati"><input type="number" min={0} step="0.1" value={f.meter_hours} onChange={up("meter_hours")} /></Field>
      </div>
      <Field label="Saha">
        <select value={f.site_id} onChange={up("site_id")}>
          <option value="">Belirtilmedi</option>
          {sites.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
      </Field>
      <ErrorNote error={create.error} />
      {create.data && (
        <Success>
          {create.data.code} eklendi (QR {create.data.qr_code}). <Link to={`/makine/${create.data.id}`}>Parçalarını takmak için aç</Link>
        </Success>
      )}
      <button className="btn btn-primary" disabled={create.isPending}>Makine ekle</button>
    </form>
  );
}

// ---------- Katalog kalemi ----------
function CatalogForm() {
  const create = useCreate<unknown, { id: string; name: string }>("/catalog/parts", ["catalog-parts"]);
  const [cat, setCat] = useState("tire");
  const [f, setF] = useState({ name: "", manufacturer: "", part_no: "", list_cost: "", min_stock: "0", life: "", unit: "adet" });
  const [t, setT] = useState({ size: "", construction: "radial", tra_code: "", otd_mm: "", scrap_tread_mm: "" });
  const [r, setR] = useState({ size: "", pieces: "", ndt_interval_hours: "" });
  const up = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate(
      {
        category_code: cat, name: f.name.trim(), manufacturer: sOrNull(f.manufacturer), part_no: sOrNull(f.part_no),
        list_cost: nOrNull(f.list_cost), min_stock: Number(f.min_stock) || 0, unit: SERIALIZED.has(cat) ? "adet" : f.unit,
        expected_life_hours: cat !== "tire" ? nOrNull(f.life) : null,
        tire: cat === "tire" ? {
          size: t.size.trim(), construction: t.construction, tra_code: sOrNull(t.tra_code),
          otd_mm: Number(t.otd_mm), scrap_tread_mm: Number(t.scrap_tread_mm) || 0,
        } : null,
        rim: cat === "rim" && r.size.trim() ? {
          size: r.size.trim(), pieces: nOrNull(r.pieces), ndt_interval_hours: nOrNull(r.ndt_interval_hours),
        } : null,
      },
      { onSuccess: () => setF({ ...f, name: "", part_no: "" }) },
    );
  };
  return (
    <form className="form" onSubmit={submit}>
      <div className="form-row">
        <Field label="Tür">
          <select value={cat} onChange={(e) => setCat(e.target.value)}>
            {Object.entries(CATEGORY_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </Field>
        <Field label="Ad"><input value={f.name} onChange={up("name")} placeholder={cat === "tire" ? "29.5R25 L-4 radyal" : ""} required /></Field>
      </div>
      <div className="form-row">
        <Field label="Üretici"><input value={f.manufacturer} onChange={up("manufacturer")} /></Field>
        <Field label="Parça no"><input value={f.part_no} onChange={up("part_no")} /></Field>
      </div>
      <div className="form-row">
        <Field label="Liste fiyatı ($)"><input type="number" min={0} step="0.01" value={f.list_cost} onChange={up("list_cost")} /></Field>
        <Field label="Kritik stok seviyesi" hint="Altına düşünce uyarı"><input type="number" min={0} value={f.min_stock} onChange={up("min_stock")} /></Field>
      </div>
      {!SERIALIZED.has(cat) && (
        <Field label="Birim" hint="Bu kalem seri numarasıyla değil, miktarla izlenir (Stok sayfası)">
          <select value={f.unit} onChange={up("unit")}>
            {["adet", "litre", "kg", "metre", "takım"].map((u) => <option key={u} value={u}>{u}</option>)}
          </select>
        </Field>
      )}
      {cat === "tire" ? (
        <fieldset className="fieldset">
          <legend>Lastik bilgisi</legend>
          <div className="form-row">
            <Field label="Ebat"><input value={t.size} onChange={(e) => setT({ ...t, size: e.target.value })} placeholder="29.5R25" required /></Field>
            <Field label="Yapı">
              <select value={t.construction} onChange={(e) => setT({ ...t, construction: e.target.value })}>
                <option value="radial">Radyal</option><option value="bias">Diyagonal</option><option value="solid">Dolgu</option>
              </select>
            </Field>
            <Field label="TRA kodu"><input value={t.tra_code} onChange={(e) => setT({ ...t, tra_code: e.target.value })} placeholder="L-4" /></Field>
          </div>
          <div className="form-row">
            <Field label="Orijinal diş derinliği (mm)">
              <input type="number" min={1} step="0.1" value={t.otd_mm} onChange={(e) => setT({ ...t, otd_mm: e.target.value })} required />
            </Field>
            <Field label="Hurda / kaplama sınırı (mm)">
              <input type="number" min={0} step="0.1" value={t.scrap_tread_mm} onChange={(e) => setT({ ...t, scrap_tread_mm: e.target.value })} />
            </Field>
          </div>
        </fieldset>
      ) : SERIALIZED.has(cat) ? (
        <Field label="Beklenen ömür (çalışma saati)" hint="Sağlık skoru bu değere göre hesaplanır">
          <input type="number" min={1} value={f.life} onChange={up("life")} />
        </Field>
      ) : null}
      {cat === "rim" && (
        <fieldset className="fieldset">
          <legend>Jant bilgisi</legend>
          <div className="form-row">
            <Field label="Ebat"><input value={r.size} onChange={(e) => setR({ ...r, size: e.target.value })} placeholder="25x25.00/3.5" /></Field>
            <Field label="Parça sayısı"><input type="number" min={1} max={7} value={r.pieces} onChange={(e) => setR({ ...r, pieces: e.target.value })} /></Field>
            <Field label="NDT periyodu (saat)"><input type="number" min={1} value={r.ndt_interval_hours} onChange={(e) => setR({ ...r, ndt_interval_hours: e.target.value })} /></Field>
          </div>
        </fieldset>
      )}
      <ErrorNote error={create.error} />
      {create.data && <Success>{create.data.name} kataloğa eklendi.</Success>}
      <button className="btn btn-primary" disabled={create.isPending}>Kataloğa ekle</button>
    </form>
  );
}

// ---------- Makine modeli ----------
function ModelForm() {
  const templates = useTemplates();
  const create = useCreate<unknown, { manufacturer: string; model: string }>("/catalog/asset-models", ["asset-models"]);
  const [f, setF] = useState({ manufacturer: "", model: "", category: "wheel_loader", template_id: "" });
  const tpl = templates.data?.find((x) => x.id === f.template_id);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate(f);
  };
  return (
    <form className="form" onSubmit={submit}>
      <div className="form-row">
        <Field label="Üretici"><input value={f.manufacturer} onChange={(e) => setF({ ...f, manufacturer: e.target.value })} required /></Field>
        <Field label="Model"><input value={f.model} onChange={(e) => setF({ ...f, model: e.target.value })} required /></Field>
      </div>
      <div className="form-row">
        <Field label="Makine tipi">
          <select value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>
            <option value="wheel_loader">Lastikli yükleyici</option>
            <option value="reach_stacker">Reach stacker</option>
            <option value="forklift">Forklift</option>
            <option value="haul_truck">Maden kamyonu</option>
            <option value="excavator">Ekskavatör</option>
            <option value="other">Diğer</option>
          </select>
        </Field>
        <Field label="Pozisyon şablonu" hint="Parçaların takılacağı yuvalar">
          <select value={f.template_id} onChange={(e) => setF({ ...f, template_id: e.target.value })} required>
            <option value="">Seçin</option>
            {templates.data?.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
          </select>
        </Field>
      </div>
      {tpl && <p className="muted small">Yuvalar: {tpl.positions.map((p) => p.code).join(", ")}</p>}
      <ErrorNote error={create.error} />
      {create.data && <Success>{create.data.manufacturer} {create.data.model} eklendi.</Success>}
      <button className="btn btn-primary" disabled={create.isPending}>Model ekle</button>
    </form>
  );
}

// ---------- Saha ----------
function SiteForm() {
  const create = useCreate<unknown, { name: string }>("/sites", ["sites"]);
  const [f, setF] = useState({ name: "", kind: "", city: "" });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate({ name: f.name.trim(), kind: sOrNull(f.kind), city: sOrNull(f.city) }, { onSuccess: () => setF({ name: "", kind: "", city: "" }) });
  };
  return (
    <form className="form" onSubmit={submit}>
      <Field label="Ad"><input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required /></Field>
      <div className="form-row">
        <Field label="Tür"><input value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })} placeholder="maden, liman, depo…" /></Field>
        <Field label="Şehir"><input value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })} /></Field>
      </div>
      <ErrorNote error={create.error} />
      {create.data && <Success>{create.data.name} eklendi.</Success>}
      <button className="btn btn-primary" disabled={create.isPending}>Saha ekle</button>
    </form>
  );
}

const TABS: { key: string; label: string; min: Role; el: () => ReactElement; hint: string }[] = [
  { key: "teslim", label: "Parça teslim al", min: "technician", el: ReceiveForm, hint: "Gelen lastik ve parçaları stoğa girin." },
  { key: "makine", label: "Makine", min: "manager", el: AssetForm, hint: "Filoya yeni makine ekleyin." },
  { key: "katalog", label: "Katalog kalemi", min: "manager", el: CatalogForm, hint: "Lastik ebadı, silindir modeli gibi parça tipleri." },
  { key: "model", label: "Makine modeli", min: "manager", el: ModelForm, hint: "Üretici + model ve pozisyon şablonu." },
  { key: "saha", label: "Saha", min: "manager", el: SiteForm, hint: "Maden, liman, şantiye veya depo." },
  { key: "excel", label: "Excel'den içe aktar", min: "manager", el: ImportPanel, hint: "Mevcut lastik listenizi tek seferde sisteme alın." },
];

export function RegisterPage() {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const tabs = TABS.filter((t) => can(t.min));
  const active = tabs.find((t) => t.key === params.get("sekme")) ?? tabs[0];
  if (!active) return <Panel title="Kayıt"><p>Bu sayfa için yetkiniz yok.</p></Panel>;
  const Form = active.el;
  return (
    <>
      <div className="page-head"><h1>Kayıt</h1></div>
      <div className="tabs" role="tablist">
        {tabs.map((t) => (
          <button key={t.key} role="tab" aria-selected={t.key === active.key} onClick={() => setParams({ sekme: t.key })}>{t.label}</button>
        ))}
      </div>
      <Panel className={active.key === "excel" ? "" : "narrow"} title={active.label} sub={active.hint}>
        <Form key={active.key} />
      </Panel>
    </>
  );
}
