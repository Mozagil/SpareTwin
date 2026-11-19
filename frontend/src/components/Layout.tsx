import { useState, type FormEvent, type ReactNode } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router";
import { ApiError } from "../api/client";
import { resolveQr, useModules } from "../api/hooks";
import { useAuth } from "../auth/AuthProvider";
import { NotificationBell } from "./NotificationBell";

const Icon = {
  fleet: <path d="M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z" />,
  parts: <><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="4" /></>,
  add: <><path d="M12 5v14M5 12h14" /><rect x="3" y="3" width="18" height="18" rx="3" /></>,
  label: <path d="M3 3h6v6H3zM15 3h6v6h-6zM3 15h6v6H3zM15 15h2v2h-2zM19 19h2v2h-2zM15 19h2" />,
  wrench: <path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.6 2.6-2.4-.6-.6-2.4z" />,
  coin: <><circle cx="12" cy="12" r="9" /><path d="M15 9.5c-.5-1-1.6-1.5-3-1.5-1.7 0-3 .8-3 2s1.3 1.7 3 2 3 .8 3 2-1.3 2-3 2c-1.4 0-2.5-.5-3-1.5M12 6v2M12 16v2" /></>,
  gear: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" /></>,
  cart: <><circle cx="9" cy="20" r="1.5" /><circle cx="18" cy="20" r="1.5" /><path d="M2 3h3l2.5 12h12L22 7H6.2" /></>,
  stock: <><path d="M3 8l9-5 9 5-9 5z" /><path d="M3 8v8l9 5 9-5V8" /><path d="M12 13v8" /></>,
  tire: <><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="4" /><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1" /></>,
  factory: <path d="M3 21V10l6 4V10l6 4V6h6v15z" />,
  rim: <><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="2.5" /><path d="M12 3v6.5M12 14.5V21M3 12h6.5M14.5 12H21" /></>,
  check: <><path d="M9 4h6v3H9z" /><path d="M7 5H5v16h14V5h-2" /><path d="m9 14 2 2 4-4" /></>,
};

function NavSection({ title, soon, children }: { title: string; soon?: boolean; children: ReactNode }) {
  return (
    <div className={`nav-section${soon ? " soon desktop-only" : ""}`} role="group" aria-label={title}>
      <div className="nav-section-title" aria-hidden="true">{title}</div>
      {children}
    </div>
  );
}

function NavItem({ to, label, icon, end, desktopOnly }: { to: string; label: string; icon: keyof typeof Icon; end?: boolean; desktopOnly?: boolean }) {
  const loc = useLocation();
  // "Lastikler" = Parçalar + lastik filtresi: ikisi aynı anda seçili görünmesin
  const [path, query] = to.split("?");
  const tireView = loc.pathname === "/parcalar" && new URLSearchParams(loc.search).get("tur") === "tire";
  return (
    <NavLink to={to} end={end} aria-label={label} title={label}
             className={({ isActive }) => {
               const on = query ? loc.pathname === path && loc.search.includes(query) : isActive && !(path === "/parcalar" && tireView);
               return `nav-item${desktopOnly ? " desktop-only" : ""}${on ? " on" : ""}`;
             }}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">{Icon[icon]}</svg>
      <span>{label}</span>
    </NavLink>
  );
}

export function Layout() {
  const { user, membership, logout, can } = useAuth();
  const mods = useModules();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [searchError, setSearchError] = useState<string | null>(null);

  const search = async (e: FormEvent) => {
    e.preventDefault();
    const term = q.trim();
    if (!term) return;
    setSearchError(null);
    if (/^ST-[AP]-/i.test(term)) {
      try {
        const r = await resolveQr(term.toUpperCase());
        navigate(r.type === "asset" ? `/makine/${r.id}` : `/parca/${r.id}`);
        setQ("");
      } catch (err) {
        setSearchError(err instanceof ApiError ? err.message : "Arama başarısız");
      }
    } else {
      navigate(`/parcalar?q=${encodeURIComponent(term)}`);
    }
  };

  const toggleTheme = () => {
    const r = document.documentElement;
    const dark = r.dataset.theme ? r.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    r.dataset.theme = dark ? "light" : "dark";
  };

  return (
    <div className="app">
      <nav className="rail" aria-label="Ana menü">
        <div className="brand-row">
          <div className="mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth={2}><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="3" /></svg>
          </div>
          <span className="brand-name">SpareTwin</span>
        </div>

        {/* Ortak çekirdek: her firma */}
        <NavItem to="/" end label="Filo" icon="fleet" />
        {can("technician") && <NavItem to="/kontrol" label="Kontrol" icon="check" />}
        <NavItem to="/parcalar" label="Parçalar" icon="parts" desktopOnly />

        {mods.tireiq && (
          <NavSection title="Lastik ve jant">
            <NavItem to="/parcalar?tur=tire" label="Lastikler" icon="tire" desktopOnly />
            <NavItem to="/jantlar" label="Jantlar" icon="rim" />
          </NavSection>
        )}

        {mods.parts && (
          <NavSection title="Yedek parça ve bakım">
            <NavItem to="/stok" label="Stok" icon="stock" />
            <NavItem to="/satinalma" label="Satınalma" icon="cart" desktopOnly />
            <NavItem to="/bakim" label="Bakım" icon="wrench" />
            <NavItem to="/maliyet" label="Maliyet" icon="coin" desktopOnly />
          </NavSection>
        )}

        <NavSection title="KOBİ ERP" soon>
          <span className="nav-item nav-soon desktop-only" title="Faz 4: üretim emirleri, ürün ağacı (BOM), MRP">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">{Icon.factory}</svg>
            <span>Üretim</span><em>Yakında</em>
          </span>
        </NavSection>

        <NavSection title="Yönetim">
          {can("technician") && <NavItem to="/kayit" label="Kayıt" icon="add" />}
          <NavItem to="/etiketler" label="Etiketler" icon="label" desktopOnly />
          {can("manager") && <NavItem to="/ayarlar" label="Ayarlar" icon="gear" desktopOnly />}
        </NavSection>
      </nav>
      <div className="main-col">
        <header className="topbar">
          <div className="org">
            <strong>{membership?.tenant_name}</strong>
            <span>{user?.full_name ?? user?.email} · {membership?.role}</span>
          </div>
          <form className="search" onSubmit={search} role="search">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">{Icon.label}</svg>
            <input type="search" value={q} onChange={(e) => setQ(e.target.value)}
                   placeholder="QR kodu (ST-…) veya seri no" aria-label="QR kodu veya seri no ile ara" />
          </form>
          <NotificationBell />
          <button className="btn btn-ghost" onClick={toggleTheme} aria-label="Açık/koyu tema">Tema</button>
          <button className="btn btn-ghost" onClick={() => logout()}>Çıkış</button>
        </header>
        {searchError && <div className="error-note slim" role="alert">{searchError}</div>}
        <main>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
