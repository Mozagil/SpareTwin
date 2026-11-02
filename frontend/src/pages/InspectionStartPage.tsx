import { useCallback, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { api, ApiError } from "../api/client";
import { resolveQr, startInspection, useAssets, useDrafts } from "../api/hooks";
import type { PartDetail } from "../api/types";
import { QrScanner } from "../components/QrScanner";
import { ErrorNote, Field, Loading } from "../components/ui";
import { date, dateTime, num } from "../lib/format";

export function InspectionStartPage() {
  const [params, setParams] = useSearchParams();
  const assets = useAssets();
  const drafts = useDrafts();
  const navigate = useNavigate();
  const [scan, setScan] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [hours, setHours] = useState("");
  const [busy, setBusy] = useState(false);

  const assetId = params.get("makine");
  const asset = assets.data?.find((a) => a.id === assetId);
  const draft = drafts.data?.find((d) => d.asset_id === assetId);

  const choose = (id: string) => {
    setError(null);
    setHours("");
    setParams({ makine: id }, { replace: true });
  };

  const onCode = useCallback(async (code: string) => {
    setScan(false);
    setError(null);
    try {
      const r = await resolveQr(code);
      if (r.type === "asset") return choose(r.id);
      // Parça etiketi okutulduysa takılı olduğu makineye geç
      const part = await api<PartDetail>(`/parts/${r.id}`);
      if (part.current_asset_id) return choose(part.current_asset_id);
      setError(new ApiError(404, `${part.serial_no ?? "Bu parça"} şu an bir makineye takılı değil.`));
    } catch (e) {
      setError(e);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const start = async (e: FormEvent) => {
    e.preventDefault();
    if (!asset) return;
    setBusy(true);
    setError(null);
    try {
      const value = hours.trim() === "" ? asset.meter_hours : Number(hours.replace(",", "."));
      const r = await startInspection(asset.id, value);
      navigate(`/kontrol/${r.id}`);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="insp">
      <div className="page-head"><h1>Saha kontrolü</h1></div>

      {!asset ? (
        <>
          <button className="btn btn-primary btn-xl" onClick={() => setScan(true)}>
            <svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
              <path d="M3 7V4h3M21 7V4h-3M3 17v3h3M21 17v3h-3M7 8h4v4H7zM13 13h4v4h-4zM13 8h4M7 16h3" />
            </svg>
            Makinenin QR kodunu okut
          </button>
          <ErrorNote error={error} />

          {(drafts.data?.length ?? 0) > 0 && (
            <section className="insp-section">
              <h2>Yarım kalan kontroller</h2>
              <ul className="pick-list">
                {drafts.data!.map((d) => (
                  <li key={d.id}>
                    <Link to={`/kontrol/${d.id}`}>
                      <strong>{d.asset_code}</strong>
                      <span className="muted">{dateTime(d.started_at)} · {d.measured_parts} parça ölçüldü{d.inspected_by_name ? ` · ${d.inspected_by_name}` : ""}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section className="insp-section">
            <h2>veya listeden seç</h2>
            {assets.isLoading ? <Loading /> : (
              <ul className="pick-list">
                {assets.data?.map((a) => (
                  <li key={a.id}>
                    <button onClick={() => choose(a.id)}>
                      <strong>{a.code}</strong>
                      <span className="muted">{a.manufacturer} {a.model} · son kontrol {date(a.last_inspection_at)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      ) : (
        <form className="insp-card form" onSubmit={start}>
          <div>
            <div className="insp-asset">{asset.code}</div>
            <div className="muted">{asset.manufacturer} {asset.model}{asset.site_name ? ` · ${asset.site_name}` : ""}</div>
          </div>
          {draft ? (
            <div className="stack">
              <p>Bu makinede {dateTime(draft.started_at)} tarihinde başlanmış, tamamlanmamış bir kontrol var.</p>
              <Link className="btn btn-primary btn-xl" to={`/kontrol/${draft.id}`}>Kaldığın yerden devam et</Link>
            </div>
          ) : (
            <>
              <Field label="Motor saati" hint={`Sistemdeki son değer: ${num(asset.meter_hours)}. Göstergedeki değeri yazın.`}>
                <input type="text" inputMode="decimal" value={hours} onChange={(e) => setHours(e.target.value)}
                       placeholder={String(asset.meter_hours)} className="input-xl" />
              </Field>
              <button className="btn btn-primary btn-xl" disabled={busy}>{busy ? "Başlatılıyor…" : "Kontrolü başlat"}</button>
            </>
          )}
          <ErrorNote error={error} />
          <button type="button" className="btn btn-ghost" onClick={() => setParams({}, { replace: true })}>Başka makine seç</button>
        </form>
      )}

      {scan && <QrScanner onCode={onCode} onClose={() => setScan(false)} />}
    </div>
  );
}
