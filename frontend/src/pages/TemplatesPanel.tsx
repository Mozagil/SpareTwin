// Pozisyon şablonları: liste ve sürükle-bırak düzenleyici. Ortak şablon salt okunur;
// "Kopyala" ile firmanın şablonu olarak uyarlanır.
import { useRef, useState, type ChangeEvent, type KeyboardEvent, type PointerEvent } from "react";
import { useCategories, useImage, useTemplateActions, useTemplates } from "../api/hooks";
import type { Layout, Template } from "../api/types";
import { Backdrop, X, Y } from "../components/MachineSchematic";
import { Empty, ErrorNote, Field, Loading, Modal } from "../components/ui";
import { LAYOUT_LABEL, categoryLabel, num } from "../lib/format";
import {
  buildTemplate, emptyTemplate, newPosition, nudge, positionCode, svgToPct, toTemplateDraft, withRimSlots,
  type PositionDraft, type TemplateDraft,
} from "../lib/library";

// ---------- Şema: yuvalar sürüklenir ya da ok tuşlarıyla taşınır ----------
function Canvas({ draft, image, selected, onSelect, onMove }: {
  draft: TemplateDraft; image?: string | null; selected: number | null;
  onSelect: (key: number) => void; onMove: (key: number, at: { x: number; y: number }) => void;
}) {
  const svg = useRef<SVGSVGElement>(null);
  const drag = useRef<number | null>(null);
  const placed = draft.positions.filter((p) => p.x != null && p.y != null);

  const at = (e: PointerEvent) => {
    const m = svg.current?.getScreenCTM();
    if (!m) return null;
    const pt = new DOMPoint(e.clientX, e.clientY).matrixTransform(m.inverse());
    return svgToPct(pt.x, pt.y);
  };
  const down = (p: PositionDraft) => (e: PointerEvent) => {
    drag.current = p.key;
    onSelect(p.key);
    svg.current?.setPointerCapture(e.pointerId);
  };
  const move = (e: PointerEvent) => {
    const to = drag.current != null ? at(e) : null;
    if (to) onMove(drag.current!, to);
  };
  const keys = (p: PositionDraft) => (e: KeyboardEvent) => {
    const step = e.shiftKey ? 5 : 1;
    const d = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[e.key];
    if (!d) return;
    e.preventDefault();
    const n = nudge(p, d[0]!, d[1]!);
    onMove(p.key, { x: n.x!, y: n.y! });
  };

  return (
    <div className="schematic-wrap">
      <svg ref={svg} className="schematic tpl-canvas" viewBox="0 0 640 360" role="group" aria-label="Şablon şeması: yuvaları sürükleyin"
           onPointerMove={move} onPointerUp={() => (drag.current = null)} onPointerCancel={() => (drag.current = null)}>
        {!image && <text x={X(-4)} y={18} className="sch-label">ön</text>}
        {!image && <text x={X(96)} y={18} className="sch-label" textAnchor="end">arka</text>}
        <Backdrop layout={draft.layout} image={image} />
        {placed.map((p) => {
          const cx = X(p.x!), cy = Y(p.y!);
          const tire = p.category_code === "tire";
          return (
            <g key={p.key} className="slot tpl-slot" tabIndex={0} role="button" aria-pressed={selected === p.key}
               aria-label={`${p.code} ${p.label}: ok tuşlarıyla taşıyın`}
               onPointerDown={down(p)} onFocus={() => onSelect(p.key)} onKeyDown={keys(p)}>
              {tire ? (
                <>
                  <rect className="halo" x={cx - 41} y={cy - 31} width={82} height={62} rx={12} />
                  <rect x={cx - 35} y={cy - 25} width={70} height={50} rx={8} fill="var(--rubber)" />
                </>
              ) : (
                <>
                  <circle className="halo" cx={cx} cy={cy} r={20} />
                  <circle cx={cx} cy={cy} r={13} fill="var(--brand)" />
                </>
              )}
              <text x={cx} y={tire ? (p.y! < 50 ? cy - 35 : cy + 45) : cy - 24} textAnchor="middle" className={tire ? "sch-label tpl-code" : "sch-label tpl-code tpl-code-opt"}>{p.code}</text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

// ---------- Şema resmi: makinenin üstten fotoğrafı ya da teknik çizimi ----------
function SchematicImage({ templateId, has }: { templateId: string; has: boolean }) {
  const { upload, remove } = useImage(`/catalog/templates/${templateId}/image`);
  const input = useRef<HTMLInputElement>(null);
  const onFile = (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) upload.mutate(f);
    e.target.value = "";
  };
  return (
    <div className="tpl-image">
      <button type="button" className="btn btn-small" disabled={upload.isPending} onClick={() => input.current?.click()}>
        {upload.isPending ? "Yükleniyor…" : has ? "Resmi değiştir" : "Makine resmi yükle"}
      </button>
      {has && <button type="button" className="btn btn-small" disabled={remove.isPending} onClick={() => remove.mutate()}>Resmi kaldır</button>}
      <span className="muted small">
        {has ? "Yuvalar bu resmin üzerine yerleşir; makine şeması da bu resimle çizilir."
             : "Hazır gövde çizimi uymuyorsa makinenin üstten fotoğrafını ya da teknik çizimini yükleyin (JPEG, PNG, WEBP)."}
      </span>
      <input ref={input} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={onFile} />
      <ErrorNote error={upload.error ?? remove.error} />
    </div>
  );
}

// ---------- Düzenleyici ----------
function Editor({ initial, onClose }: { initial: TemplateDraft; onClose: () => void }) {
  const cats = useCategories();
  const templates = useTemplates();
  const { save } = useTemplateActions();
  const [d, setD] = useState(initial);
  const [created, setCreated] = useState(false);
  const image = d.id ? templates.data?.find((t) => t.id === d.id)?.image?.url : null;
  const [selected, setSelected] = useState<number | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const slotTypes = (cats.data ?? []).filter((c) => c.is_serialized);

  const patch = (key: number, v: Partial<PositionDraft>) =>
    setD((cur) => ({ ...cur, positions: cur.positions.map((p) => (p.key === key ? { ...p, ...v } : p)) }));
  const add = () => {
    const p = newPosition(d.positions, slotTypes.find((c) => c.code === "tire")?.code ?? slotTypes[0]?.code ?? "tire");
    setD({ ...d, positions: [...d.positions, p] });
    setSelected(p.key);
  };
  const submit = () => {
    const built = buildTemplate(d);
    setErrors(built.errors);
    if (!built.body) return;
    // Yeni şablon kaydedilince düzenleyici açık kalır: resim ancak kayıtlı şablona yüklenebilir
    if (d.id) save.mutate({ id: d.id, ...built.body }, { onSuccess: onClose });
    else save.mutate(built.body, { onSuccess: (t) => { setD(toTemplateDraft(t)); setSelected(null); setCreated(true); } });
  };
  const hasTire = d.positions.some((p) => p.category_code === "tire");

  return (
    <div className="form">
      <div className="form-row">
        <Field label="Şablon adı"><input value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} placeholder="Çeneli kırıcı (paletli)" maxLength={80} /></Field>
        <Field label="Gövde çizimi" hint={image ? "Makine resmi yüklü olduğu için kullanılmıyor" : "Şemanın arka planı; yuvaların yerini etkilemez"}>
          <select value={d.layout} onChange={(e) => setD({ ...d, layout: e.target.value as Layout })}>
            {Object.entries(LAYOUT_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </Field>
      </div>

      {created && <div className="success-note" role="status">Şablon oluşturuldu. İsterseniz makine resmi ekleyin, sonra listeye dönün.</div>}
      {d.id ? <SchematicImage templateId={d.id} has={!!image} />
            : <p className="muted small">Makinenin kendi resmini şema olarak kullanmak için önce şablonu oluşturun; resim yükleme o zaman açılır.</p>}
      <Canvas draft={d} image={image} selected={selected} onSelect={setSelected} onMove={(key, at) => patch(key, at)} />
      <p className="muted small">Yuvayı sürükleyerek ya da seçip ok tuşlarıyla (Shift ile 5'er) yerine koyun. Lastik dışındaki yuvaların kodu, yuva seçilince ya da üzerine gelince görünür. Şemada gösterilmeyen yuvalar (ör. jant) yalnızca listede durur.</p>

      <div className="table-wrap">
        <table className="table lib-table tpl-table">
          <thead><tr><th>Kod</th><th>Ad</th><th>Parça tipi</th><th>Aks</th><th>Şemada</th><th /></tr></thead>
          <tbody>
            {d.positions.map((p) => (
              <tr key={p.key} aria-selected={selected === p.key} onFocus={() => setSelected(p.key)} onClick={() => setSelected(p.key)}>
                <td><input className="tpl-code-input" aria-label="Kod" value={p.code} maxLength={24} placeholder="A1-L"
                           onChange={(e) => patch(p.key, { code: positionCode(e.target.value) })} /></td>
                <td><input aria-label="Ad" value={p.label} maxLength={60} placeholder="Ön aks sol" onChange={(e) => patch(p.key, { label: e.target.value })} /></td>
                <td>
                  <select aria-label="Parça tipi" value={p.category_code} onChange={(e) => patch(p.key, { category_code: e.target.value })}>
                    {!slotTypes.some((c) => c.code === p.category_code) && <option value={p.category_code}>{categoryLabel(p.category_code)}</option>}
                    {slotTypes.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}
                  </select>
                </td>
                <td>{(p.category_code === "tire" || p.category_code === "rim") &&
                  <input className="tpl-axle" aria-label="Aks no" type="number" min={1} max={12} value={p.axle} onChange={(e) => patch(p.key, { axle: e.target.value })} />}</td>
                <td><input type="checkbox" aria-label="Şemada göster" checked={p.x != null}
                           onChange={(e) => patch(p.key, e.target.checked ? { x: 50, y: 50 } : { x: null, y: null })} /></td>
                <td className="row-actions">
                  <button type="button" className="icon-btn" aria-label={`${p.code || "Yuva"} satırını sil`}
                          onClick={() => setD({ ...d, positions: d.positions.filter((x) => x.key !== p.key) })}>×</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {d.positions.length === 0 && <Empty>Henüz yuva yok. “Yuva ekle” ile başlayın.</Empty>}
      <div className="lib-actions">
        <button type="button" className="btn btn-small" disabled={d.positions.length >= 60} onClick={add}>Yuva ekle</button>
        {hasTire && (
          <button type="button" className="btn btn-small" title="Her lastik yuvasına KOD-J adıyla jant yuvası ekler"
                  onClick={() => setD({ ...d, positions: withRimSlots(d.positions) })}>Lastiklere jant yuvası ekle</button>
        )}
        <span className="spacer" />
        <button type="button" className="btn btn-ghost" onClick={onClose}>{created ? "Listeye dön" : "Vazgeç"}</button>
        <button type="button" className="btn btn-primary" disabled={save.isPending} onClick={submit}>{d.id ? "Şablonu kaydet" : "Şablonu oluştur"}</button>
      </div>
      {errors.length > 0 && <div className="error-note" role="alert"><ul>{errors.map((m) => <li key={m}>{m}</li>)}</ul></div>}
      <ErrorNote error={save.error} />
    </div>
  );
}

// ---------- Liste ----------
export function TemplatesPanel() {
  const templates = useTemplates();
  const { remove } = useTemplateActions();
  const [draft, setDraft] = useState<TemplateDraft | null>(null);
  const [del, setDel] = useState<Template | null>(null);

  if (draft) return <Editor key={draft.id ?? "new"} initial={draft} onClose={() => setDraft(null)} />;
  if (templates.isLoading) return <Loading />;
  const rows = templates.data ?? [];

  return (
    <>
      <div className="lib-head">
        <p className="muted small">Ortak şablonlar değiştirilemez; “Kopyala” ile kendi makinenize uyarlayın ya da sıfırdan çizin. Şablonu makineye “Makine modeli” sekmesinde bağlarsınız.</p>
        <button className="btn btn-primary" onClick={() => setDraft(emptyTemplate())}>Yeni şablon</button>
      </div>
      <ErrorNote error={templates.error} />
      <ErrorNote error={remove.error} />
      {rows.length === 0 ? <Empty>Şablon yok.</Empty> : (
        <div className="table-wrap">
          <table className="table lib-table">
            <thead><tr><th>Şablon</th><th>Gövde çizimi</th><th>Yuvalar</th><th className="num">Makine modeli</th><th /></tr></thead>
            <tbody>
              {rows.map((t) => (
                <tr key={t.id}>
                  <td><strong>{t.name}</strong> {t.is_library ? <span className="chip chip-plain">Ortak</span> : <span className="chip t-ok">Firmanız</span>}</td>
                  <td>{t.image ? "Makine resmi" : LAYOUT_LABEL[t.layout]}</td>
                  <td>{num(t.positions.length)} yuva
                    <div className="muted small">{[...new Set(t.positions.map((p) => categoryLabel(p.category_code)))].join(", ")}</div></td>
                  <td className="num">{t.is_library ? "–" : num(t.model_count)}</td>
                  <td className="row-actions">
                    {!t.is_library && <><button className="btn btn-small" onClick={() => setDraft(toTemplateDraft(t))}>Düzenle</button>{" "}</>}
                    <button className="btn btn-small" onClick={() => setDraft(toTemplateDraft(t, true))}>Kopyala</button>
                    {!t.is_library && (
                      <>{" "}<button className="btn btn-small" disabled={remove.isPending || t.model_count > 0}
                              title={t.model_count > 0 ? "Bu şablonu kullanan makine modeli olduğu için silinemez" : undefined}
                              onClick={() => setDel(t)}>Sil</button></>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {del && (
        <Modal title="Şablonu sil" onClose={() => setDel(null)}
          footer={<><button className="btn btn-ghost" onClick={() => setDel(null)}>Vazgeç</button>
            <button className="btn btn-primary" disabled={remove.isPending}
                    onClick={() => remove.mutate(del.id, { onSettled: () => setDel(null) })}>Sil</button></>}>
          <p>“{del.name}” şablonu silinecek. Emin misiniz?</p>
        </Modal>
      )}
    </>
  );
}
