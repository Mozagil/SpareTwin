// Parça tipleri: ortak kütüphane salt okunur, firma kendi tipini ve ölçüm profilini yönetir.
import { useState, type FormEvent } from "react";
import { useCategories, useCategoryActions } from "../api/hooks";
import type { Category } from "../api/types";
import { Empty, ErrorNote, Field, Loading, Modal } from "../components/ui";
import { ANGLE_LABEL, angleLabel, num } from "../lib/format";
import { SLUG_RE, buildProfile, emptyMetric, slugify, toMetricDrafts, type MetricDraft } from "../lib/library";

function CategoryModal({ category, onClose }: { category: Category | null; onClose: () => void }) {
  const { save } = useCategoryActions();
  const [name, setName] = useState(category?.name ?? "");
  const [code, setCode] = useState(category?.code ?? "");
  const [codeTouched, setCodeTouched] = useState(false);
  const [serialized, setSerialized] = useState(category?.is_serialized ?? true);
  const [rows, setRows] = useState<MetricDraft[]>(toMetricDrafts(category?.measurement_profile ?? []));
  const [angles, setAngles] = useState<string[]>(category?.required_photo_angles ?? []);
  const [errors, setErrors] = useState<string[]>([]);

  const autoCode = codeTouched || category ? code : slugify(name);
  const setRow = (i: number, patch: Partial<MetricDraft>) => setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  // Firmanın daha önce yazdığı, listede olmayan açılar da görünür kalsın
  const angleOptions = [...new Set([...Object.keys(ANGLE_LABEL), ...angles])];

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const built = buildProfile(serialized ? rows : []);
    const errs = [...built.errors];
    if (name.trim().length < 2) errs.unshift("Tipe bir ad verin");
    if (!category && !SLUG_RE.test(autoCode)) errs.unshift("Kod küçük harfle başlamalı; harf, rakam ve alt çizgi içerebilir");
    setErrors(errs);
    if (errs.length || !built.profile) return;
    save.mutate(
      { id: category?.id, code: autoCode, name: name.trim(), is_serialized: serialized,
        measurement_profile: built.profile, required_photo_angles: serialized ? angles : [] },
      { onSuccess: onClose },
    );
  };

  return (
    <Modal wide title={category ? `${category.name}: parça tipi` : "Yeni parça tipi"} onClose={onClose}
      footer={<><button className="btn btn-ghost" onClick={onClose}>Vazgeç</button>
        <button className="btn btn-primary" form="category-form" disabled={save.isPending}>Kaydet</button></>}>
      <form id="category-form" className="form" onSubmit={submit}>
        <div className="form-row">
          <Field label="Ad"><input value={name} onChange={(e) => setName(e.target.value)} placeholder="Şanzıman" maxLength={60} required /></Field>
          <Field label="Kod" hint={category ? "Kayıtlar bu koda bağlı olduğu için değişmez" : "Addan üretilir; kaydedildikten sonra değişmez"}>
            <input value={autoCode} disabled={!!category} maxLength={40}
                   onChange={(e) => { setCodeTouched(true); setCode(e.target.value.toLowerCase()); }} />
          </Field>
        </div>
        <Field label="İzleme şekli" hint={category ? "Kaydedildikten sonra değişmez" : "Seri numaralı parça makinedeki yuvaya takılır ve ikizi tutulur; miktarla izlenen kalem stokta adet / litre olarak durur"}>
          <select value={serialized ? "1" : "0"} disabled={!!category} onChange={(e) => setSerialized(e.target.value === "1")}>
            <option value="1">Seri numarasıyla, tek tek (pompa, silindir, şanzıman)</option>
            <option value="0">Miktarla (filtre, yağ, keçe)</option>
          </select>
        </Field>

        {serialized && (
          <>
            <fieldset className="fieldset">
              <legend>Sahada ne ölçülecek</legend>
              {rows.length === 0 && <p className="muted small">Ölçüm tanımlı değil. Bu tipteki parçalar kontrol formunda yalnızca fotoğrafla (aşağıda seçilirse) yer alır.</p>}
              {rows.map((r, i) => (
                <div className="metric-row" key={i}>
                  <Field label="Ölçüm adı"><input value={r.label} onChange={(e) => setRow(i, { label: e.target.value })} placeholder="Yağ sıcaklığı" maxLength={60} /></Field>
                  <Field label="Birim"><input value={r.unit} onChange={(e) => setRow(i, { unit: e.target.value })} placeholder="°C" maxLength={12} /></Field>
                  <Field label="En az"><input inputMode="decimal" value={r.min} onChange={(e) => setRow(i, { min: e.target.value })} /></Field>
                  <Field label="En çok"><input inputMode="decimal" value={r.max} onChange={(e) => setRow(i, { max: e.target.value })} /></Field>
                  <label className="inline-check"><input type="checkbox" checked={r.required} onChange={(e) => setRow(i, { required: e.target.checked })} /> Zorunlu</label>
                  <button type="button" className="icon-btn" aria-label={`${r.label || `${i + 1}. ölçüm`} satırını sil`} onClick={() => setRows(rows.filter((_, j) => j !== i))}>×</button>
                </div>
              ))}
              <div>
                <button type="button" className="btn btn-small" disabled={rows.length >= 12} onClick={() => setRows([...rows, emptyMetric()])}>Ölçüm ekle</button>
              </div>
              <p className="muted small">Sınırların dışındaki değer girilirken teknisyen uyarılır. Zorunlu ölçüm girilmeden kontrol tamamlanamaz.</p>
            </fieldset>
            <fieldset className="fieldset">
              <legend>Zorunlu fotoğraflar</legend>
              <div className="check-row">
                {angleOptions.map((a) => (
                  <label className="inline-check" key={a}>
                    <input type="checkbox" checked={angles.includes(a)}
                           onChange={(e) => setAngles(e.target.checked ? [...angles, a] : angles.filter((x) => x !== a))} /> {angleLabel(a)}
                  </label>
                ))}
              </div>
            </fieldset>
          </>
        )}
        {errors.length > 0 && <div className="error-note" role="alert"><ul>{errors.map((m) => <li key={m}>{m}</li>)}</ul></div>}
        <ErrorNote error={save.error} />
      </form>
    </Modal>
  );
}

export function CategoriesPanel() {
  const cats = useCategories();
  const { remove } = useCategoryActions();
  const [modal, setModal] = useState<Category | "new" | null>(null);
  const [del, setDel] = useState<Category | null>(null);
  if (cats.isLoading) return <Loading />;
  const rows = [...(cats.data ?? [])].sort((a, b) => Number(a.is_library) - Number(b.is_library) || a.name.localeCompare(b.name, "tr"));
  const own = rows.filter((c) => !c.is_library).length;

  return (
    <>
      <div className="lib-head">
        <p className="muted small">
          Ortak tipler her firmada hazır gelir ve değiştirilemez. {own === 0 && "Makinenizde izlemek istediğiniz başka parça varsa (şanzıman, zincir, palet…) kendi tipinizi ekleyin."}
        </p>
        <button className="btn btn-primary" onClick={() => setModal("new")}>Yeni parça tipi</button>
      </div>
      <ErrorNote error={cats.error} />
      <ErrorNote error={remove.error} />
      {rows.length === 0 ? <Empty>Parça tipi yok.</Empty> : (
        <div className="table-wrap">
          <table className="table lib-table">
            <thead><tr><th>Parça tipi</th><th>İzleme</th><th>Sahada ölçülen</th><th>Zorunlu fotoğraf</th><th className="num">Katalog kalemi</th><th /></tr></thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.id}>
                  <td><strong>{c.name}</strong> {c.is_library ? <span className="chip chip-plain">Ortak</span> : <span className="chip t-ok">Firmanız</span>}
                    <div className="muted small">{c.code}</div></td>
                  <td>{c.is_serialized ? "Seri no ile" : "Miktarla"}</td>
                  <td>{c.measurement_profile.length
                    ? c.measurement_profile.map((m) => `${m.label}${m.unit ? ` (${m.unit})` : ""}${m.required ? " *" : ""}`).join(", ")
                    : <span className="muted">–</span>}</td>
                  <td>{c.required_photo_angles.length ? c.required_photo_angles.map(angleLabel).join(", ") : <span className="muted">–</span>}</td>
                  <td className="num">{num(c.part_count)}</td>
                  <td className="row-actions">
                    {!c.is_library && (
                      <>
                        <button className="btn btn-small" onClick={() => setModal(c)}>Düzenle</button>{" "}
                        <button className="btn btn-small" disabled={remove.isPending || c.part_count > 0}
                                title={c.part_count > 0 ? "Bu tipte katalog kalemi olduğu için silinemez" : undefined}
                                onClick={() => setDel(c)}>Sil</button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="muted small">* zorunlu ölçüm</p>
      {del && (
        <Modal title="Parça tipini sil" onClose={() => setDel(null)}
          footer={<><button className="btn btn-ghost" onClick={() => setDel(null)}>Vazgeç</button>
            <button className="btn btn-primary" disabled={remove.isPending}
                    onClick={() => remove.mutate(del.id, { onSettled: () => setDel(null) })}>Sil</button></>}>
          <p>“{del.name}” parça tipi silinecek. Emin misiniz?</p>
        </Modal>
      )}
      {modal && <CategoryModal category={modal === "new" ? null : modal} onClose={() => setModal(null)} />}
    </>
  );
}
