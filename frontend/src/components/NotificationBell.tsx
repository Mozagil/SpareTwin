import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { useMarkRead, useNotificationState, useNotifications } from "../api/hooks";
import type { Notification } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import { dateTime } from "../lib/format";

export function notificationPath(n: Notification): string {
  switch (n.link.type) {
    case "part": return `/parca/${n.link.id}`;
    case "asset": return `/makine/${n.link.id}`;
    case "rim": return "/jantlar";
    case "stock": return `/stok?kalem=${n.link.id}`;
    case "purchasing": return "/satinalma?sekme=ihtiyac";
    case "order": return `/satinalma?sekme=siparisler&siparis=${n.link.id}`;
    case "maintenance": return `/bakim?sekme=takvim&makine=${n.link.id}`;
    case "work_order": return `/bakim?sekme=emirler&emir=${n.link.id}`;
  }
}

/** Ekip durumunun tek satırlık açıklaması (zil ve testler için). */
export function stateLabel(n: Notification): string | null {
  if (!n.state) return null;
  const who = n.state_by ?? "biri";
  const when = n.state_at ? ` · ${dateTime(n.state_at)}` : "";
  return n.state === "acknowledged" ? `${who} üstlendi${when}` : `${who} gizledi${when}`;
}

export function NotificationBell() {
  const [showDismissed, setShowDismissed] = useState(false);
  const q = useNotifications(showDismissed);
  const mark = useMarkRead();
  const setState = useNotificationState();
  const { can } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const unread = q.data?.unread ?? 0;
  const dismissed = q.data?.dismissed ?? 0;

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const go = (n: Notification) => {
    if (!n.read) mark.mutate({ keys: [n.key] });
    setOpen(false);
    navigate(notificationPath(n));
  };

  const act = (n: Notification, state: Notification["state"]) => setState.mutate({ key: n.key, state });

  return (
    <div className="bell" ref={box}>
      <button className="btn btn-ghost bell-btn" onClick={() => setOpen(!open)} aria-expanded={open} aria-haspopup="true"
              aria-label={unread ? `Bildirimler, ${unread} okunmamış` : "Bildirimler"}>
        <svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
          <path d="M6 16V11a6 6 0 1 1 12 0v5l2 2H4z" /><path d="M10 20a2 2 0 0 0 4 0" />
        </svg>
        {unread > 0 && <span className="bell-count" aria-hidden="true">{unread > 99 ? "99+" : unread}</span>}
      </button>
      {open && (
        <div className="bell-panel" role="dialog" aria-label="Bildirimler">
          <div className="bell-head">
            <strong>Bildirimler</strong>
            <span className="bell-head-actions">
              {(dismissed > 0 || showDismissed) && (
                <button className="link-btn" onClick={() => setShowDismissed(!showDismissed)} aria-pressed={showDismissed}>
                  {showDismissed ? "Gizlenenleri sakla" : `Gizlenenler · ${dismissed}`}
                </button>
              )}
              {unread > 0 && (
                <button className="link-btn" onClick={() => mark.mutate({ all: true })} disabled={mark.isPending}>Tümünü okundu say</button>
              )}
            </span>
          </div>
          {setState.error && <p className="bell-error" role="alert">{(setState.error as Error).message}</p>}
          {q.isLoading ? <p className="muted bell-empty">Yükleniyor…</p> : (q.data?.items.length ?? 0) === 0 ? (
            <p className="muted bell-empty">Şu an dikkat gerektiren bir durum yok.</p>
          ) : (
            <ul className="bell-list">
              {q.data!.items.map((n) => (
                <li key={n.key} className={n.state === "dismissed" ? "dismissed" : ""}>
                  <button className={`bell-item ${n.read ? "read" : ""}`} onClick={() => go(n)}>
                    <span className="sev" style={{ ["--c" as string]: `var(--${n.severity})` }} aria-hidden="true" />
                    <span>
                      <span className="bell-title">{n.title}</span>
                      <span className="bell-body">{n.body}</span>
                      {n.state && (
                        <span className={`bell-state ${n.state}`}>
                          {n.state === "acknowledged" ? "✓ " : ""}{stateLabel(n)}{n.note ? ` · “${n.note}”` : ""}
                        </span>
                      )}
                    </span>
                    {!n.read && <span className="bell-dot" aria-label="okunmamış" />}
                  </button>
                  {can("technician") && (
                    <div className="bell-actions">
                      {n.state === null && <>
                        <button className="link-btn" onClick={() => act(n, "acknowledged")} disabled={setState.isPending}
                                title="Ekibe 'ben ilgileniyorum' de">Üstlen</button>
                        <button className="link-btn muted" onClick={() => act(n, "dismissed")} disabled={setState.isPending}
                                title="Durum değişene kadar gösterme">Gizle</button>
                      </>}
                      {n.state === "acknowledged" && <>
                        <button className="link-btn muted" onClick={() => act(n, null)} disabled={setState.isPending}>Bırak</button>
                        <button className="link-btn muted" onClick={() => act(n, "dismissed")} disabled={setState.isPending}>Gizle</button>
                      </>}
                      {n.state === "dismissed" && (
                        <button className="link-btn" onClick={() => act(n, null)} disabled={setState.isPending}>Geri al</button>
                      )}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
