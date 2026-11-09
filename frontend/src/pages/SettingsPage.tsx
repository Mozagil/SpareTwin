import { useEffect, useState, type FormEvent } from "react";
import { Navigate } from "react-router";
import { useAudit, useOrganization, useUpdateOrganization } from "../api/hooks";
import type { AuditRow } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import { Empty, ErrorNote, Field, Loading, Panel } from "../components/ui";
import { dateTime } from "../lib/format";
import { describeAudit, THRESHOLD_FIELDS, toForm, validateThresholds, type ThresholdForm } from "../lib/settings";

function ThresholdsForm() {
  const org = useOrganization();
  const save = useUpdateOrganization();
  const [name, setName] = useState("");
  const [form, setForm] = useState<ThresholdForm | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (org.data && form === null) {
      setForm(toForm(org.data.thresholds));
      setName(org.data.name);
    }
  }, [org.data, form]);

  if (org.isLoading || !form) return <Loading />;
  if (org.error) return <ErrorNote error={org.error} />;
  const data = org.data!;
  const { errors, values } = validateThresholds(form);
  const dirty = name.trim() !== data.name || JSON.stringify(values) !== JSON.stringify(data.thresholds);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!values) return;
    setSaved(false);
    save.mutate({ name: name.trim() !== data.name ? name.trim() : undefined, thresholds: values },
      { onSuccess: (o) => { setForm(toForm(o.thresholds)); setName(o.name); setSaved(true); } });
  };

  return (
    <form className="form" onSubmit={submit}>
      <Field label="Firma adı">
        <input value={name} onChange={(e) => setName(e.target.value)} minLength={2} maxLength={120} required />
      </Field>
      <fieldset className="fieldset">
        <legend>Uyarı eşikleri</legend>
        <p className="muted small" style={{ margin: 0 }}>
          Dashboard'daki renkler, bildirimler ve PDF rapor bu eşiklere göre hesaplanır. Değişiklik anında tüm filoya uygulanır;
          geçmiş ölçümler değişmez.
        </p>
        <div className="form-row">
          {THRESHOLD_FIELDS.map((d) => (
            <Field key={d.key} label={`${d.label} (${d.unit})`} hint={errors[d.key] ?? `${d.hint}. Varsayılan ${data.defaults[d.key]}`}>
              <input inputMode="decimal" value={form[d.key]} aria-invalid={!!errors[d.key]}
                     onChange={(e) => { setSaved(false); setForm({ ...form, [d.key]: e.target.value }); }} />
            </Field>
          ))}
        </div>
      </fieldset>
      <ErrorNote error={save.error} />
      <div className="row-actions" style={{ display: "flex", gap: 10, justifyContent: "flex-end", alignItems: "center" }}>
        {saved && !dirty && <span className="muted small">Kaydedildi</span>}
        <button type="button" className="btn btn-ghost" disabled={!dirty || save.isPending}
                onClick={() => { setForm(toForm(data.thresholds)); setName(data.name); }}>Vazgeç</button>
        <button type="button" className="btn btn-ghost" disabled={save.isPending}
                onClick={() => setForm(toForm(data.defaults))}>Varsayılanlara dön</button>
        <button className="btn btn-primary" disabled={!dirty || !values || save.isPending}>Kaydet</button>
      </div>
    </form>
  );
}

function Detail({ d }: { d: AuditRow["detail"] }) {
  if (!d) return null;
  const parts: string[] = [];
  const th = d.thresholds as Record<string, { from: number; to: number }> | undefined;
  if (th) for (const [k, v] of Object.entries(th)) parts.push(`${THRESHOLD_FIELDS.find((f) => f.key === k)?.label ?? k}: ${v.from} → ${v.to}`);
  const nm = d.name as { from: string; to: string } | undefined;
  if (nm) parts.push(`ad: ${nm.from} → ${nm.to}`);
  if (typeof d.notification === "string") parts.push(`${d.notification}${d.state ? ` → ${d.state === "acknowledged" ? "üstlenildi" : "gizlendi"}` : " → geri alındı"}`);
  if (typeof d.query === "string") parts.push(d.query);
  return parts.length ? <div className="muted small">{parts.join(" · ")}</div> : null;
}

function AuditLog() {
  const [q, setQ] = useState("");
  const [limit, setLimit] = useState(100);
  const rows = useAudit({ q: q.trim() || undefined, limit });
  const data = rows.data ?? [];
  return (
    <>
      <div className="form-row" style={{ marginBottom: 12 }}>
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Yol veya eylem ara (örn. install, login)"
               aria-label="Denetim kaydında ara" />
      </div>
      {rows.isLoading ? <Loading /> : rows.error ? <ErrorNote error={rows.error} /> : data.length === 0 ? (
        <Empty>Kayıt yok.</Empty>
      ) : (
        <div className="table-wrap">
          <table className="table audit">
            <thead><tr><th>Zaman</th><th>Kim</th><th>Ne</th><th>İstek</th><th className="num">Sonuç</th></tr></thead>
            <tbody>
              {data.map((r) => (
                <tr key={r.id}>
                  <td className="nowrap">{dateTime(r.at)}</td>
                  <td>{r.user_name ?? r.user_email ?? <span className="muted">—</span>}{r.user_name && <div className="muted small">{r.user_email}</div>}</td>
                  <td>{describeAudit(r.entity_type, r.action)}<Detail d={r.detail} /></td>
                  <td className="muted small mono">{r.method} {r.path}</td>
                  <td className={`num ${r.status >= 400 ? "t-critical" : ""}`}>{r.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.length >= limit && limit < 500 && (
            <p style={{ textAlign: "center", margin: "12px 0 0" }}>
              <button className="btn btn-small" onClick={() => setLimit(Math.min(500, limit + 200))}>Daha fazla göster</button>
            </p>
          )}
        </div>
      )}
    </>
  );
}

export function SettingsPage() {
  const { can } = useAuth();
  if (!can("admin")) return <Navigate to="/" replace />;
  return (
    <>
      <div className="page-head"><h1>Ayarlar</h1></div>
      <p className="sub lead">Firma adı, uyarı eşikleri ve denetim kaydı. Yalnızca yöneticiler görür ve değiştirir.</p>
      <Panel title="Firma ve eşikler" className="narrow">
        <ThresholdsForm />
      </Panel>
      <Panel title="Denetim kaydı" sub="Durum değiştiren her istek: kim, ne, ne zaman. Kayıtlar değiştirilemez." className="audit-panel">
        <AuditLog />
      </Panel>
    </>
  );
}
