import { useState, type FormEvent } from "react";
import { NavLink, Outlet, useNavigate } from "react-router";
import { ApiError } from "../api/client";
import { resolveQr } from "../api/hooks";
import { useAuth } from "../auth/AuthProvider";

const Icon = {
  fleet: <path d="M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z" />,
  parts: <><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="4" /></>,
  add: <><path d="M12 5v14M5 12h14" /><rect x="3" y="3" width="18" height="18" rx="3" /></>,
  label: <path d="M3 3h6v6H3zM15 3h6v6h-6zM3 15h6v6H3zM15 15h2v2h-2zM19 19h2v2h-2zM15 19h2" />,
  check: <><path d="M9 4h6v3H9z" /><path d="M7 5H5v16h14V5h-2" /><path d="m9 14 2 2 4-4" /></>,
};

function NavItem({ to, label, icon, end }: { to: string; label: string; icon: keyof typeof Icon; end?: boolean }) {
  return (
    <NavLink to={to} end={end} className="nav-item" aria-label={label} title={label}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">{Icon[icon]}</svg>
      <span>{label}</span>
    </NavLink>
  );
}

export function Layout() {
  const { user, membership, logout, can } = useAuth();
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
        <div className="mark" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth={2}><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="3" /></svg>
        </div>
        <NavItem to="/" end label="Filo" icon="fleet" />
        {can("technician") && <NavItem to="/kontrol" label="Kontrol" icon="check" />}
        <NavItem to="/parcalar" label="Parçalar" icon="parts" />
        {can("technician") && <NavItem to="/kayit" label="Kayıt" icon="add" />}
        <NavItem to="/etiketler" label="Etiketler" icon="label" />
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
