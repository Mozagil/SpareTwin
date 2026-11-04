import { useState } from "react";
import { download } from "../api/client";
import { ErrorNote } from "./ui";

/** PDF durum raporunu indirir (tüm filo ya da tek makine). */
export function ReportButton({ assetId, className = "btn btn-ghost" }: { assetId?: string; className?: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      await download(`/reports/fleet.pdf${assetId ? `?asset_id=${assetId}` : ""}`, "sparetwin-rapor.pdf");
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <span className="report-btn">
      <button className={className} onClick={run} disabled={busy}>
        <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
          <path d="M6 2h9l5 5v15H6z" /><path d="M14 2v6h6" /><path d="M9 14h6M9 18h4" />
        </svg>
        {busy ? "Hazırlanıyor…" : "PDF rapor"}
      </button>
      <ErrorNote error={error} />
    </span>
  );
}
