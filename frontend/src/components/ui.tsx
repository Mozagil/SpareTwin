// Küçük, ortak arayüz parçaları.
import { cloneElement, useEffect, useId, useRef, type ReactElement, type ReactNode } from "react";
import type { Band } from "../api/types";
import { ApiError } from "../api/client";
import { BAND_LABEL } from "../lib/format";

export function BandChip({ band, children }: { band: Band; children?: ReactNode }) {
  return <span className="chip" style={{ ["--c" as string]: `var(--${band === "empty" ? "unknown" : band})` }}>{children ?? BAND_LABEL[band]}</span>;
}

export function Panel({ title, sub, actions, children, className = "" }: {
  title?: ReactNode; sub?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      {(title || actions) && (
        <div className="panel-head">
          <div>
            {title && <h2>{title}</h2>}
            {sub && <p className="sub">{sub}</p>}
          </div>
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function Loading({ label = "Yükleniyor" }: { label?: string }) {
  return <div className="loading" role="status"><span className="spinner" aria-hidden="true" />{label}…</div>;
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  const msg = error instanceof ApiError ? error.message : "Beklenmeyen bir hata oluştu. Bağlantıyı kontrol edin.";
  const fields = error instanceof ApiError ? error.fields : [];
  return (
    <div className="error-note" role="alert">
      <strong>{msg}</strong>
      {fields.length > 0 && (
        <ul>{fields.map((f, i) => <li key={i}>{f.field ? `${f.field}: ` : ""}{f.message}</li>)}</ul>
      )}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

/** Erişilebilir modal: Escape ile kapanır, açılınca ilk alana odaklanır. */
export function Modal({ title, onClose, children, footer, wide }: {
  title: string; onClose: () => void; children: ReactNode; footer?: ReactNode; wide?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    ref.current?.querySelector<HTMLElement>("input, select, textarea, button")?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      prev?.focus();
    };
  }, [onClose]);
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={wide ? "modal modal-wide" : "modal"} role="dialog" aria-modal="true" aria-label={title} ref={ref}>
        <div className="modal-head">
          <h2>{title}</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Kapat">×</button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>
  );
}

/** Etiketli form alanı. Açıklama metni alan adına karışmaz, aria-describedby ile bağlanır. */
export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactElement<Record<string, unknown>> }) {
  const id = useId();
  const hintId = `${id}-hint`;
  const control = cloneElement(children, {
    id,
    ...(hint ? { "aria-describedby": hintId } : {}),
  });
  return (
    <div className="field">
      <label className="field-label" htmlFor={id}>{label}</label>
      {control}
      {hint && <span className="field-hint" id={hintId}>{hint}</span>}
    </div>
  );
}
