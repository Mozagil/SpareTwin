import { useState, type FormEvent } from "react";
import { useAuth } from "../auth/AuthProvider";
import { ErrorNote, Field } from "../components/ui";

export function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-wrap">
      <form className="login" onSubmit={submit}>
        <div className="login-brand">
          <div className="mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth={2}><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="3" /></svg>
          </div>
          <div>
            <h1>SpareTwin</h1>
            <p className="sub">Lastik ve parça ikizi</p>
          </div>
        </div>
        <Field label="E-posta">
          <input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
        </Field>
        <Field label="Parola">
          <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </Field>
        <ErrorNote error={error} />
        <button className="btn btn-primary btn-block" disabled={busy}>{busy ? "Giriş yapılıyor…" : "Giriş yap"}</button>
        {import.meta.env.DEV && (
          <p className="muted small">Geliştirme: yonetici@demo.sparetwin.dev · demo-parola-2026</p>
        )}
      </form>
    </div>
  );
}

export function TenantPicker() {
  const { user, selectTenant, logout } = useAuth();
  if (!user) return null;
  return (
    <div className="login-wrap">
      <div className="login">
        <h1>Firma seçin</h1>
        {user.memberships.length === 0 ? (
          <p>Hesabınız henüz bir firmaya bağlı değil. Yöneticinizden davet isteyin.</p>
        ) : (
          <div className="stack">
            {user.memberships.map((m) => (
              <button key={m.tenant_id} className="btn btn-ghost btn-block" onClick={() => selectTenant(m.tenant_id)}>
                {m.tenant_name} <span className="muted">· {m.role}</span>
              </button>
            ))}
          </div>
        )}
        <button className="btn btn-ghost" onClick={() => logout()}>Çıkış</button>
      </div>
    </div>
  );
}
