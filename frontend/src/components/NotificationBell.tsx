import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { useMarkRead, useNotifications } from "../api/hooks";
import type { Notification } from "../api/types";

export function notificationPath(n: Notification): string {
  switch (n.link.type) {
    case "part": return `/parca/${n.link.id}`;
    case "asset": return `/makine/${n.link.id}`;
    case "rim": return "/jantlar";
    case "stock": return `/stok?kalem=${n.link.id}`;
  }
}

export function NotificationBell() {
  const q = useNotifications();
  const mark = useMarkRead();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const unread = q.data?.unread ?? 0;

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
            {unread > 0 && (
              <button className="link-btn" onClick={() => mark.mutate({ all: true })} disabled={mark.isPending}>Tümünü okundu say</button>
            )}
          </div>
          {q.isLoading ? <p className="muted bell-empty">Yükleniyor…</p> : (q.data?.items.length ?? 0) === 0 ? (
            <p className="muted bell-empty">Şu an dikkat gerektiren bir durum yok.</p>
          ) : (
            <ul className="bell-list">
              {q.data!.items.map((n) => (
                <li key={n.key}>
                  <button className={`bell-item ${n.read ? "read" : ""}`} onClick={() => go(n)}>
                    <span className="sev" style={{ ["--c" as string]: `var(--${n.severity})` }} aria-hidden="true" />
                    <span>
                      <span className="bell-title">{n.title}</span>
                      <span className="bell-body">{n.body}</span>
                    </span>
                    {!n.read && <span className="bell-dot" aria-label="okunmamış" />}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
