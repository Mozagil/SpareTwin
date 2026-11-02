import { useRef, useState, type ChangeEvent } from "react";
import { Link } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { api, ApiError, download } from "../api/client";
import { useLabels } from "../api/hooks";
import { ErrorNote } from "../components/ui";
import { num1 } from "../lib/format";
import { openInNewTab } from "../lib/popup";

interface ImportRow {
  row: number;
  status: "ok" | "warning" | "error";
  errors: string[];
  warnings: string[];
  asset_code: string | null;
  position: string | null;
  size: string | null;
  brand: string | null;
  serial_no: string | null;
  tread_mm: number | null;
}
interface ImportResult {
  summary: { total: number; ok: number; warnings: number; errors: number; new_assets: number; new_catalog: number; with_tread: number };
  unknown_columns: string[];
  rows: ImportRow[];
  created?: { assets: number; models: number; catalog: number; tires: number; measurements: number };
  part_ids?: string[];
}

const ICON = { ok: "✓", warning: "!", error: "×" } as const;

function send(file: File, dryRun: boolean): Promise<ImportResult> {
  const form = new FormData();
  form.append("file", file);
  return api<ImportResult>("/import/tires", { method: "POST", form, query: { dry_run: dryRun } });
}

export function ImportPanel() {
  const qc = useQueryClient();
  const labels = useLabels();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportResult | null>(null);
  const [done, setDone] = useState<ImportResult | null>(null);
  const [busy, setBusy] = useState<"preview" | "commit" | "template" | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [onlyErrors, setOnlyErrors] = useState(false);

  const reset = () => {
    setFile(null);
    setPreview(null);
    setDone(null);
    setError(null);
  };

  const pick = async (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    reset();
    setFile(f);
    setBusy("preview");
    try {
      const r = await send(f, true);
      setPreview(r);
      setOnlyErrors(r.summary.errors > 0);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  };

  const commit = async () => {
    if (!file) return;
    setBusy("commit");
    setError(null);
    try {
      const r = await send(file, false);
      setDone(r);
      setPreview(null);
      await Promise.all(["assets", "asset", "parts", "part", "catalog-parts", "asset-models", "tire-cost"].map((k) => qc.invalidateQueries({ queryKey: [k] })));
    } catch (err) {
      // Bu arada veri değiştiyse sunucu yeni hata listesini döndürür
      setError(err);
    } finally {
      setBusy(null);
    }
  };

  const getTemplate = async () => {
    setBusy("template");
    setError(null);
    try {
      await download("/import/tires/template", "sparetwin-lastik-sablonu.xlsx");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  };

  if (done?.created) {
    const c = done.created;
    return (
      <div className="stack">
        <div className="success-note" role="status">
          <strong>{c.tires} lastik içe aktarıldı.</strong>{" "}
          {[c.assets && `${c.assets} yeni makine`, c.catalog && `${c.catalog} yeni katalog kalemi`, c.measurements && `${c.measurements} ölçüm`]
            .filter(Boolean).join(", ")}
          {c.assets + c.catalog + c.measurements > 0 && " eklendi."}
        </div>
        <div className="actions">
          <button className="btn btn-primary" disabled={labels.isPending} onClick={() =>
            openInNewTab(async () => (await labels.mutateAsync({ asset_ids: [], part_ids: (done.part_ids ?? []).slice(0, 63), skip: 0 })).url).catch(() => undefined)}>
            Yeni lastiklerin QR etiketlerini yazdır
          </button>
          <Link className="btn btn-ghost" to="/">Filoya git</Link>
          <button className="btn btn-ghost" onClick={reset}>Başka dosya yükle</button>
        </div>
        {(done.part_ids?.length ?? 0) > 63 && <p className="muted small">Tek seferde 63 etiket yazdırılır; kalanlar için Etiketler sayfasını kullanın.</p>}
      </div>
    );
  }

  const s = preview?.summary;
  const rows = (preview?.rows ?? []).filter((r) => !onlyErrors || r.status === "error");

  return (
    <div className="stack">
      <ol className="steps">
        <li>
          <strong>Şablonu indir.</strong> Sütunlar ve açıklamalar hazır; örnek satırları silip kendi listenizi yapıştırın.
          <div><button className="btn btn-ghost btn-small" onClick={getTemplate} disabled={busy === "template"}>
            {busy === "template" ? "İndiriliyor…" : "Excel şablonunu indir"}</button></div>
        </li>
        <li><strong>Dosyayı seç.</strong> .xlsx veya .csv; en fazla 2.000 satır. Önce önizleme gösterilir, hiçbir şey kaydedilmez.</li>
        <li><strong>Onayla.</strong> Bir satırda bile hata varsa hiçbiri kaydedilmez; düzeltip tekrar yükleyin.</li>
      </ol>

      <div>
        <button className="btn btn-primary" onClick={() => input.current?.click()} disabled={!!busy}>
          {busy === "preview" ? "Kontrol ediliyor…" : file ? "Başka dosya seç" : "Dosya seç"}
        </button>
        {file && <span className="muted small"> {file.name}</span>}
        <input ref={input} type="file" accept=".xlsx,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv"
               hidden onChange={pick} aria-label="İçe aktarılacak dosya" />
      </div>

      <ErrorNote error={error instanceof ApiError && error.status === 422 && preview ? new ApiError(422, error.message) : error} />

      {s && (
        <>
          <div className="import-summary">
            <span className="chip" style={{ ["--c" as string]: "var(--muted)" }}>{s.total} satır</span>
            {s.ok > 0 && <span className="chip" style={{ ["--c" as string]: "var(--ok)" }}>{s.ok} hazır</span>}
            {s.warnings > 0 && <span className="chip" style={{ ["--c" as string]: "var(--watch)" }}>{s.warnings} uyarılı</span>}
            {s.errors > 0 && <span className="chip" style={{ ["--c" as string]: "var(--critical)" }}>{s.errors} hatalı</span>}
            {s.new_assets > 0 && <span className="chip chip-plain">{s.new_assets} yeni makine</span>}
            {s.new_catalog > 0 && <span className="chip chip-plain">{s.new_catalog} yeni katalog kalemi</span>}
            <span className="chip chip-plain">{s.with_tread} ölçümlü</span>
          </div>
          {preview!.unknown_columns.length > 0 && (
            <p className="muted small">Tanınmayan sütunlar yok sayıldı: {preview!.unknown_columns.join(", ")}</p>
          )}
          {s.errors > 0 ? (
            <div className="error-note" role="alert">
              <strong>{s.errors} satırda hata var.</strong> Excel'de düzeltip dosyayı tekrar seçin. Hata kalmayınca içe aktarma düğmesi açılır.
            </div>
          ) : (
            <button className="btn btn-primary btn-xl" onClick={commit} disabled={busy === "commit"}>
              {busy === "commit" ? "İçe aktarılıyor…" : `${s.total} lastiği içe aktar`}
            </button>
          )}
          <label className="inline-check">
            <input type="checkbox" checked={onlyErrors} onChange={(e) => setOnlyErrors(e.target.checked)} /> Yalnızca hatalı satırlar
          </label>
          <div className="table-wrap">
            <table className="table import-table">
              <thead>
                <tr><th aria-label="Durum" /><th className="num">Satır</th><th>Makine</th><th>Pozisyon</th><th>Ebat / marka</th><th>Seri no</th><th className="num">Diş</th><th>Not</th></tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.row} className={`st-${r.status}`}>
                    <td><span className={`rowicon ${r.status}`} aria-label={r.status === "ok" ? "Hazır" : r.status === "warning" ? "Uyarı" : "Hata"}>{ICON[r.status]}</span></td>
                    <td className="num">{r.row}</td>
                    <td>{r.asset_code}</td>
                    <td>{r.position}</td>
                    <td>{r.size}{r.brand ? ` · ${r.brand}` : ""}</td>
                    <td>{r.serial_no ?? <span className="muted">–</span>}</td>
                    <td className="num">{r.tread_mm != null ? num1(r.tread_mm) : "–"}</td>
                    <td className="msgs">
                      {r.errors.map((m, i) => <div key={`e${i}`} className="t-critical">{m}</div>)}
                      {r.warnings.map((m, i) => <div key={`w${i}`} className="muted">{m}</div>)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
