// Görsel bileşenleri: katalog/makine görseli kutusu, saha fotoğrafı şeridi, büyütme penceresi.
import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { useImage } from "../api/hooks";
import type { Img, Photo } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import { dateTime, num } from "../lib/format";
import { ErrorNote } from "./ui";

const ANGLE_LABEL: Record<string, string> = {
  tread: "Taban",
  sidewall: "Yanak",
  damage_closeup: "Hasar (yakın çekim)",
};
export const angleLabel = (a: string | null) => (a ? (ANGLE_LABEL[a] ?? a) : "Fotoğraf");

/**
 * Tek görsel kutusu. Yöneticiler görsel ekleyebilir, değiştirebilir, kaldırabilir.
 * `uploadPath` boşsa yalnızca gösterir.
 */
export function ImageBox({ image, uploadPath, alt, note, size = "md" }: {
  image: Img | null;
  uploadPath?: string;
  alt: string;
  note?: string;
  size?: "sm" | "md" | "lg";
}) {
  const { can } = useAuth();
  const editable = !!uploadPath && can("manager");
  const { upload, remove } = useImage(uploadPath ?? "");
  const input = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);

  if (!image && !editable) return null;

  const pick = () => input.current?.click();
  const onFile = (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) upload.mutate(f);
    e.target.value = "";
  };

  return (
    <div className={`imagebox imagebox-${size}`}>
      {image ? (
        <button type="button" className="imagebox-img" onClick={() => setOpen(true)} aria-label={`${alt} görselini büyüt`}>
          <img src={image.url} alt={alt} loading="lazy" />
        </button>
      ) : (
        <button type="button" className="imagebox-empty" onClick={pick} disabled={upload.isPending}>
          <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth={1.8} aria-hidden="true">
            <rect x="3" y="5" width="18" height="14" rx="2" /><circle cx="9" cy="10" r="2" /><path d="m21 16-5-5-8 8" />
          </svg>
          {upload.isPending ? "Yükleniyor…" : "Görsel ekle"}
        </button>
      )}
      {(note || (editable && image)) && (
        <div className="imagebox-bar">
          {note && <span className="muted small">{note}</span>}
          {editable && image && (
            <span className="imagebox-actions">
              <button type="button" className="link-btn" onClick={pick} disabled={upload.isPending}>
                {upload.isPending ? "Yükleniyor…" : "Değiştir"}
              </button>
              {image.source !== "model" && (
                <button type="button" className="link-btn" onClick={() => remove.mutate()} disabled={remove.isPending}>Kaldır</button>
              )}
            </span>
          )}
        </div>
      )}
      <input ref={input} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={onFile} />
      <ErrorNote error={upload.error ?? remove.error} />
      {open && image && <Lightbox items={[{ url: image.url, caption: alt }]} start={0} onClose={() => setOpen(false)} />}
    </div>
  );
}

/** Parçanın sahada çekilmiş fotoğrafları (en yeni önce). */
export function PhotoStrip({ photos, title }: { photos: Photo[]; title: string }) {
  const [openAt, setOpenAt] = useState<number | null>(null);
  if (photos.length === 0) return null;
  const items = photos.map((p) => ({
    url: p.url,
    caption: `${title} · ${angleLabel(p.angle)} · ${dateTime(p.created_at)}${p.asset_hours != null ? ` · ${num(p.asset_hours)} motor saati` : ""}`,
  }));
  return (
    <div className="photostrip">
      <div className="photostrip-head">Saha fotoğrafları <span className="muted">· {photos.length}</span></div>
      <div className="photostrip-row">
        {photos.map((p, i) => (
          <button type="button" key={p.id ?? i} className="thumb" onClick={() => setOpenAt(i)}
                  aria-label={`${angleLabel(p.angle)}, ${dateTime(p.created_at)}, büyüt`}>
            <img src={p.url} alt="" loading="lazy" />
            <span>{angleLabel(p.angle)}</span>
          </button>
        ))}
      </div>
      {openAt != null && <Lightbox items={items} start={openAt} onClose={() => setOpenAt(null)} />}
    </div>
  );
}

/** Büyütme penceresi: Escape kapatır, ok tuşlarıyla gezilir. */
export function Lightbox({ items, start, onClose }: { items: { url: string; caption: string }[]; start: number; onClose: () => void }) {
  const [i, setI] = useState(start);
  const closeBtn = useRef<HTMLButtonElement>(null);
  const n = items.length;
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    closeBtn.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight") setI((x) => (x + 1) % n);
      if (e.key === "ArrowLeft") setI((x) => (x - 1 + n) % n);
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      prev?.focus();
    };
  }, [n, onClose]);
  const it = items[i];
  return (
    <div className="lightbox" role="dialog" aria-modal="true" aria-label={it.caption}
         onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <button ref={closeBtn} className="lightbox-close" onClick={onClose} aria-label="Kapat">×</button>
      {n > 1 && <button className="lightbox-nav prev" onClick={() => setI((i - 1 + n) % n)} aria-label="Önceki">‹</button>}
      <figure>
        <img src={it.url} alt={it.caption} />
        <figcaption>{it.caption}{n > 1 && <span className="muted"> · {i + 1}/{n}</span>}</figcaption>
      </figure>
      {n > 1 && <button className="lightbox-nav next" onClick={() => setI((i + 1) % n)} aria-label="Sonraki">›</button>}
    </div>
  );
}
