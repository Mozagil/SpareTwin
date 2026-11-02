import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { useInspectionActions, useSheet } from "../api/hooks";
import type { QcFlag, Sheet, SheetItem } from "../api/types";
import { Lightbox } from "../components/Images";
import { ErrorNote, Loading, Modal, Field } from "../components/ui";
import { angleLabel, categoryLabel, dateTime, num, num1 } from "../lib/format";
import { shrinkImage } from "../lib/image";
import { itemState, nextIncomplete, parseNum, rangeWarning } from "../lib/inspection";

type Notice = { kind: "ok" | "warn"; text: string };

const STATE_LABEL = { done: "Tamam", partial: "Eksik var", todo: "Başlanmadı", optional: "İsteğe bağlı" } as const;

// ---------- Fotoğraf yuvası ----------
function PhotoSlot({ item, angle, required, onUpload }: {
  item: SheetItem; angle: string; required: boolean;
  onUpload: (angle: string, blob: Blob) => Promise<unknown>;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [view, setView] = useState(false);
  const photo = item.photos.find((p) => p.angle === angle);

  const onFile = async (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    setBusy(true);
    setError(null);
    try {
      await onUpload(angle, await shrinkImage(f));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={`slot-photo ${photo ? "has" : ""}`}>
      {photo ? (
        <button type="button" className="slot-thumb" onClick={() => setView(true)} aria-label={`${angleLabel(angle)} fotoğrafını büyüt`}>
          <img src={photo.url} alt="" />
        </button>
      ) : (
        <div className="slot-thumb empty" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="30" height="30" fill="none" stroke="currentColor" strokeWidth={1.8}>
            <path d="M4 8h3l2-3h6l2 3h3v11H4z" /><circle cx="12" cy="13" r="3.5" />
          </svg>
        </div>
      )}
      <div className="slot-meta">
        <strong>{angleLabel(angle)}</strong>
        <span className={photo ? "t-ok" : required ? "t-critical" : "muted"}>
          {photo ? "✓ Çekildi" : required ? "Zorunlu" : "İsteğe bağlı"}
        </span>
        <button type="button" className="btn btn-ghost btn-small" onClick={() => input.current?.click()} disabled={busy}>
          {busy ? "Yükleniyor…" : photo ? "Yeniden çek" : "Fotoğraf çek"}
        </button>
      </div>
      <input ref={input} type="file" accept="image/*" capture="environment" hidden onChange={onFile}
             aria-label={`${angleLabel(angle)} fotoğrafı`} />
      <ErrorNote error={error} />
      {view && photo && <Lightbox items={[{ url: photo.url, caption: `${item.position} · ${angleLabel(angle)}` }]} start={0} onClose={() => setView(false)} />}
    </div>
  );
}

// ---------- Tek pozisyonun formu ----------
function ItemEditor({ sheet, item, onClose, onNext }: {
  sheet: Sheet; item: SheetItem; onClose: (msg?: Notice) => void; onNext: (after: string, msg: Notice) => void;
}) {
  const { save, photo } = useInspectionActions(sheet.id);
  const [vals, setVals] = useState<Record<string, string>>(() =>
    Object.fromEntries(item.profile.map((p) => [p.metric, item.values[p.metric] != null ? String(item.values[p.metric]) : ""])),
  );
  const [error, setError] = useState<string | null>(null);
  const first = useRef<HTMLInputElement>(null);
  useEffect(() => {
    first.current?.focus();
  }, [item.position]);

  const warnings = Object.fromEntries(item.profile.map((p) => [p.metric, rangeWarning(p, vals[p.metric] ?? "", item.previous[p.metric]?.value)]));
  const hard = item.profile.some((p) => {
    const raw = vals[p.metric] ?? "";
    if (raw.trim() === "") return false;
    const v = parseNum(raw);
    return !Number.isFinite(v) || (p.min != null && v < p.min) || (p.max != null && v > p.max);
  });

  const persist = async () => {
    setError(null);
    const items = item.profile
      .filter((p) => (vals[p.metric] ?? "").trim() !== "")
      .map((p) => ({ part_item_id: item.part_item_id, metric: p.metric, value: parseNum(vals[p.metric]), unit: p.unit }));
    if (items.length) await save.mutateAsync(items);
  };
  const submit = async (e: FormEvent, goNext: boolean) => {
    e.preventDefault();
    if (hard) return setError("Aralık dışındaki değerleri düzeltin.");
    try {
      await persist();
      // Kayıttan sonra hâlâ eksik olanları bildir (fotoğraflar ayrı yüklendiği için güncel durumdan hesapla)
      const missingMetrics = item.profile.filter((p) => p.required && (vals[p.metric] ?? "").trim() === "").map((p) => p.label);
      const have = new Set(item.photos.map((p) => p.angle));
      const missingPhotos = item.required_angles.filter((a) => !have.has(a)).map((a) => angleLabel(a).toLocaleLowerCase("tr-TR"));
      const missing = [...missingMetrics, ...(missingPhotos.length ? [`${missingPhotos.join(" ve ")} fotoğrafı`] : [])];
      const msg: Notice = missing.length
        ? { kind: "warn", text: `${item.position} kaydedildi · eksik: ${missing.join(", ")}` }
        : { kind: "ok", text: `${item.position} tamam ✓` };
      if (goNext) onNext(item.position, msg);
      else onClose(msg);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Kaydedilemedi");
    }
  };

  const angles = [...item.required_angles, ...(item.required_angles.includes("damage_closeup") ? [] : ["damage_closeup"])];

  return (
    <form className="editor" onSubmit={(e) => submit(e, true)}>
      <div className="editor-head">
        <button type="button" className="btn btn-ghost btn-small" onClick={() => onClose()}>‹ Liste</button>
        <div>
          <div className="editor-pos">{item.position} · {item.label}</div>
          <div className="muted small">{item.part_name} · seri {item.serial_no ?? "yok"}</div>
        </div>
      </div>

      {item.profile.map((p, i) => {
        const prev = item.previous[p.metric];
        return (
          <Field key={p.metric} label={`${p.label}${p.unit ? ` (${p.unit})` : ""}${p.required ? "" : " · isteğe bağlı"}`}
                 hint={prev ? `Önceki: ${num1(prev.value)} ${p.unit ?? ""} · ${dateTime(prev.at)}` : undefined}>
            <input ref={i === 0 ? first : undefined} className="input-xl" type="text" inputMode="decimal"
                   value={vals[p.metric] ?? ""} onChange={(e) => setVals({ ...vals, [p.metric]: e.target.value })}
                   aria-invalid={!!warnings[p.metric]} placeholder={prev ? String(prev.value) : ""} />
          </Field>
        );
      })}
      {item.profile.map((p) => warnings[p.metric] && (
        <p key={p.metric} className="warn" role="status">⚠ {p.label}: {warnings[p.metric]}</p>
      ))}

      {angles.length > 0 && (
        <div className="slots">
          {angles.map((a) => (
            <PhotoSlot key={a} item={item} angle={a} required={item.required_angles.includes(a)}
                       onUpload={(angle, blob) => photo.mutateAsync({ part_item_id: item.part_item_id, angle, blob })} />
          ))}
        </div>
      )}

      {error && <div className="error-note" role="alert">{error}</div>}
      <div className="editor-actions">
        <button type="button" className="btn btn-ghost btn-xl" disabled={save.isPending} onClick={(e) => submit(e, false)}>Kaydet</button>
        <button className="btn btn-primary btn-xl" disabled={save.isPending}>{save.isPending ? "Kaydediliyor…" : "Kaydet, sonraki ›"}</button>
      </div>
    </form>
  );
}

// ---------- Kalite kapısı sonuçları ----------
function Flags({ flags, sheet, onOpen }: { flags: QcFlag[]; sheet: Sheet; onOpen: (pos: string) => void }) {
  if (!flags.length) return null;
  return (
    <div className="flags" role="alert">
      <strong>Kontrol tamamlanamadı, şunlar eksik:</strong>
      <ul>
        {flags.map((f, i) => {
          const pos = f.position ?? sheet.items.find((x) => x.part_item_id === f.part_item_id)?.position;
          return (
            <li key={i}>
              {pos ? <button type="button" className="link-btn" onClick={() => onOpen(pos)}>{pos}</button> : <span>{f.gate}</span>}
              {" · "}{f.message}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

// ---------- Sayfa ----------
export function InspectionPage() {
  const { id } = useParams();
  const sheetQ = useSheet(id);
  const actions = useInspectionActions(id ?? "");
  const navigate = useNavigate();
  const [active, setActive] = useState<string | null>(null);
  const [flags, setFlags] = useState<QcFlag[] | null>(null);
  const [editHours, setEditHours] = useState(false);
  const [hours, setHours] = useState("");
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);

  useEffect(() => {
    if (!notice) return;
    const t = setTimeout(() => setNotice(null), 6000);
    return () => clearTimeout(t);
  }, [notice]);

  // Süslü parantez şart: yeni tarayıcılarda scrollTo bir Promise döndürür,
  // React bunu temizlik fonksiyonu sanıp sayfayı çökertir.
  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [active]);

  if (sheetQ.isLoading) return <Loading />;
  if (sheetQ.error) return <ErrorNote error={sheetQ.error} />;
  const s = sheetQ.data!;

  if (s.status !== "draft") {
    return (
      <div className="insp">
        <div className={`insp-card done-card ${s.status}`}>
          <div className="done-icon" aria-hidden="true">{s.status === "completed" ? "✓" : "×"}</div>
          <h1>{s.status === "completed" ? "Kontrol tamamlandı" : "Kontrol iptal edildi"}</h1>
          <p className="muted">{s.asset_code} · {num(s.asset_hours)} motor saati · {dateTime(s.completed_at ?? s.started_at)}</p>
          {s.status === "completed" && (
            <p>{s.items.filter((i) => i.started).length} parça ölçüldü ve fotoğraflandı. Sağlık skorları ve kalan ömür tahminleri güncellendi.</p>
          )}
          <div className="stack">
            <Link className="btn btn-primary btn-xl" to={`/makine/${s.asset_id}`}>{s.asset_code} sayfasına git</Link>
            <Link className="btn btn-ghost btn-xl" to="/kontrol">Yeni kontrol</Link>
          </div>
        </div>
      </div>
    );
  }

  const current = active ? s.items.find((i) => i.position === active) : undefined;
  const pct = s.progress.total ? Math.round((s.progress.done / s.progress.total) * 100) : 100;
  const openNext = (after: string, msg: Notice) => {
    setNotice(msg);
    // Sıradaki, bu pozisyondan sonra gelen eksik pozisyon. Sona gelindiyse başa dönmek yerine listeye dön:
    // böylece kullanıcı aynı lastikler arasında döngüye girmez, neyin eksik kaldığını listede görür.
    const idx = s.items.findIndex((i) => i.position === after);
    const n = nextIncomplete(s.items, after);
    setActive(n && s.items.indexOf(n) > idx ? n.position : null);
  };
  const finish = () =>
    actions.complete.mutate(undefined, {
      onSuccess: (r) => setFlags(r.status === "completed" ? [] : r.qc_flags),
    });

  const required = s.items.filter((i) => i.required);
  const optional = s.items.filter((i) => !i.required);

  return (
    <div className="insp">
      <header className="insp-bar">
        <div>
          <div className="insp-asset">{s.asset_code}</div>
          <button type="button" className="link-btn" onClick={() => { setHours(String(s.asset_hours ?? "")); setEditHours(true); }}>
            {num(s.asset_hours)} motor saati · düzelt
          </button>
        </div>
        <div className="insp-progress" aria-label={`${s.progress.done} / ${s.progress.total} tamam`}>
          <span>{s.progress.done}/{s.progress.total} <small>tamam</small></span>
          <div className="bar"><i style={{ width: `${pct}%` }} /></div>
          <small className="muted">{s.items.filter((i) => i.started).length} parça ölçüldü</small>
        </div>
      </header>
      {notice && (
        <div className={`notice ${notice.kind}`} role="status" onClick={() => setNotice(null)}>{notice.text}</div>
      )}

      {current ? (
        <ItemEditor key={current.position} sheet={s} item={current}
                    onClose={(msg) => { if (msg) setNotice(msg); setActive(null); }} onNext={openNext} />
      ) : (
        <>
          {flags && <Flags flags={flags} sheet={s} onOpen={(p) => { setFlags(null); setActive(p); }} />}
          <p className="muted small insp-note">
            Girilen değerler ve fotoğraflar hemen kaydedilir. Filo ekranına ve sağlık hesaplarına, kontrol
            4 kalite kapısından geçip <strong>tamamlandığında</strong> yansır.
          </p>
          <ul className="item-list">
            {[...required, ...optional].map((it) => {
              const st = itemState(it);
              return (
                <li key={it.position}>
                  <button className={`item-card st-${st}`} onClick={() => setActive(it.position)}>
                    <span className="item-dot" aria-hidden="true">{st === "done" ? "✓" : ""}</span>
                    <span className="item-main">
                      <strong>{it.position}</strong> <span className="muted">{it.label}</span>
                      <span className="small muted">{categoryLabel(it.category_code)} · {it.serial_no ?? "seri no yok"}</span>
                      {st === "partial" && (
                        <span className="small t-watch">
                          Eksik: {it.missing.map((m) => (m.kind === "metric" ? m.label : `${angleLabel(m.key)} fotoğrafı`)).join(", ")}
                        </span>
                      )}
                    </span>
                    <span className={`item-state st-${st}`}>{STATE_LABEL[st]}</span>
                  </button>
                </li>
              );
            })}
          </ul>
          <div className="insp-footer">
            <ErrorNote error={actions.complete.error} />
            <button className="btn btn-primary btn-xl" onClick={finish} disabled={actions.complete.isPending}>
              {actions.complete.isPending ? "Kontrol ediliyor…" : "Kontrolü tamamla"}
            </button>
            <button className="btn btn-ghost" onClick={() => setConfirmCancel(true)}>Kontrolü iptal et</button>
          </div>
        </>
      )}

      {editHours && (
        <Modal title="Motor saatini düzelt" onClose={() => setEditHours(false)}
          footer={<>
            <button className="btn btn-ghost" onClick={() => setEditHours(false)}>Vazgeç</button>
            <button className="btn btn-primary" form="hours-form" disabled={actions.hours.isPending}>Kaydet</button>
          </>}>
          <form id="hours-form" className="form" onSubmit={(e) => {
            e.preventDefault();
            actions.hours.mutate(parseNum(hours), { onSuccess: () => setEditHours(false) });
          }}>
            <Field label="Motor saati" hint={`Sistemdeki son değer: ${num(s.meter_hours)}`}>
              <input className="input-xl" inputMode="decimal" value={hours} onChange={(e) => setHours(e.target.value)} />
            </Field>
            <ErrorNote error={actions.hours.error} />
          </form>
        </Modal>
      )}
      {confirmCancel && (
        <Modal title="Kontrolü iptal et" onClose={() => setConfirmCancel(false)}
          footer={<>
            <button className="btn btn-ghost" onClick={() => setConfirmCancel(false)}>Vazgeç</button>
            <button className="btn btn-primary" onClick={() => actions.cancel.mutate(undefined, { onSuccess: () => navigate("/kontrol") })}>
              İptal et
            </button>
          </>}>
          <p>Bu kontrolde girilen ölçümler ve fotoğraflar sağlık hesaplarına katılmaz. Emin misiniz?</p>
        </Modal>
      )}
    </div>
  );
}
