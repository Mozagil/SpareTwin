// Model parça listesi (BOM): yuvalara uyan katalog kalemleri ve makine geneli sarf / yedek.
import { useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { download } from "../api/client";
import { useBom, useBomActions, useCatalogParts } from "../api/hooks";
import type { AssetModel, BomImportResult } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import { Empty, ErrorNote, Field, Loading, Modal } from "../components/ui";
import { categoryLabel, num, num1 } from "../lib/format";

const qty = (v: number | string, unit: string) => `${Number.isInteger(Number(v)) ? num(Number(v)) : num1(Number(v))} ${unit}`;

export function ModelBomModal({ model, onClose }: { model: AssetModel; onClose: () => void }) {
  const { can } = useAuth();
  const edit = can("manager");
  const bom = useBom(model.id);
  const catalog = useCatalogParts();
  const { add, remove, importFile } = useBomActions(model.id);
  const [partId, setPartId] = useState("");
  const [slot, setSlot] = useState("");
  const [amount, setAmount] = useState("1");
  const [result, setResult] = useState<BomImportResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [dlError, setDlError] = useState<unknown>(null);
  const input = useRef<HTMLInputElement>(null);

  const part = catalog.data?.find((p) => p.id === partId);
  // Seri numaralı kalem, tipi uyan bir yuvaya ya da makine geneline (yedek) yazılır; sarf yalnızca makine geneline
  const slots = part?.is_serialized ? (bom.data?.slots ?? []).filter((s) => s.category_code === part.category_code) : [];
  const amountOk = slot !== "" || Number(amount.replace(",", ".")) > 0;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    add.mutate(
      { part_id: partId, position_code: slot || null, qty: slot ? 1 : Number(amount.replace(",", ".")) },
      { onSuccess: () => { setPartId(""); setSlot(""); setAmount("1"); } },
    );
  };
  const onFile = (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (f) importFile.mutate(f, { onSuccess: setResult });
  };
  const getTemplate = async () => {
    setBusy(true);
    setDlError(null);
    try {
      await download(`/catalog/asset-models/${model.id}/bom/template`, "sparetwin-parca-listesi.xlsx");
    } catch (err) {
      setDlError(err);
    } finally {
      setBusy(false);
    }
  };
  const lines = bom.data?.lines ?? [];

  return (
    <Modal wide title={`${model.manufacturer} ${model.model}: parça listesi`} onClose={onClose}>
      <div className="stack">
        <p className="muted small">
          Bu modelde izlediğiniz kritik kalemler: hangi yuvaya hangi parça uyar, makine başına hangi sarf kullanılır.
          Parça takarken uyumlu olanlar öne çıkar; boş yuvada neyin takılacağı makine sayfasında görünür.
        </p>
        {bom.isLoading ? <Loading /> : bom.error ? <ErrorNote error={bom.error} /> : lines.length === 0 ? (
          <Empty>Liste boş. Aşağıdan satır ekleyin ya da Excel'den içe aktarın.</Empty>
        ) : (
          <div className="table-wrap">
            <table className="table lib-table">
              <thead><tr><th>Yuva</th><th>Kalem</th><th className="num">Miktar</th><th className="num">Stokta</th><th /></tr></thead>
              <tbody>
                {lines.map((l) => (
                  <tr key={l.id}>
                    <td>{l.position_code ? <><strong>{l.position_code}</strong><div className="muted small">{l.position_label ?? "şablonda yok"}</div></>
                                         : <span className="muted">Makine geneli</span>}</td>
                    <td><strong>{l.name}</strong>
                      <div className="muted small">{[categoryLabel(l.category_code), l.manufacturer, l.part_no, l.notes].filter(Boolean).join(" · ")}</div></td>
                    <td className="num">{l.position_code ? "–" : qty(l.qty, l.unit)}</td>
                    <td className="num">{Number(l.in_stock) > 0 ? qty(l.in_stock, l.unit) : <span className="t-watch">yok</span>}</td>
                    <td className="row-actions">{edit && (
                      <button type="button" className="icon-btn" aria-label={`${l.name} satırını sil`} disabled={remove.isPending}
                              onClick={() => remove.mutate(l.id)}>×</button>)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <ErrorNote error={remove.error} />

        {edit && (
          <>
            <form className="form" onSubmit={submit}>
              <h3 className="mini-head">Satır ekle</h3>
              <div className="form-row">
                <Field label="Katalog kalemi" hint="Listede yoksa önce “Katalog kalemi” sekmesinden ekleyin">
                  <select value={partId} onChange={(e) => { setPartId(e.target.value); setSlot(""); }} required>
                    <option value="">Seçin</option>
                    {catalog.data?.map((p) => <option key={p.id} value={p.id}>{p.category_name} · {p.name}{p.part_no ? ` · ${p.part_no}` : ""}</option>)}
                  </select>
                </Field>
                <Field label="Yuva" hint={part && !part.is_serialized ? "Sarf kalemi makine geneline yazılır" : undefined}>
                  <select value={slot} onChange={(e) => setSlot(e.target.value)} disabled={slots.length === 0}>
                    <option value="">Makine geneli (sarf / yedek)</option>
                    {slots.map((s) => <option key={s.code} value={s.code}>{s.code} · {s.label}</option>)}
                  </select>
                </Field>
                <Field label={`Miktar${part ? ` (${part.unit})` : ""}`} hint="Makine başına">
                  <input inputMode="decimal" value={slot ? "1" : amount} disabled={!!slot} onChange={(e) => setAmount(e.target.value)} />
                </Field>
              </div>
              <ErrorNote error={add.error} />
              <div className="actions">
                <button className="btn btn-primary" disabled={!partId || !amountOk || add.isPending}>Listeye ekle</button>
              </div>
            </form>

            <div className="form">
              <h3 className="mini-head">Excel'den içe aktar</h3>
              <div className="lib-actions">
                <button type="button" className="btn btn-small" onClick={getTemplate} disabled={busy}>{busy ? "İndiriliyor…" : "Şablonu indir"}</button>
                <button type="button" className="btn btn-small" onClick={() => input.current?.click()} disabled={importFile.isPending}>
                  {importFile.isPending ? "Yükleniyor…" : "Dosya seç ve içe aktar"}</button>
                <span className="muted small">Sütunlar: Parça no, Yuva, Miktar, Not. Hata varsa hiçbir satır yazılmaz.</span>
                <input ref={input} type="file" accept=".xlsx" hidden onChange={onFile} />
              </div>
              <ErrorNote error={importFile.error ?? dlError} />
              {result && result.errors.length === 0 && (
                <div className="success-note" role="status">
                  {num(result.added)} satır eklendi{result.existing ? `, ${num(result.existing)} satır zaten listedeydi` : ""}.
                </div>
              )}
              {result && result.errors.length > 0 && (
                <div className="error-note" role="alert">
                  <strong>Dosyada {num(result.errors.length)} hata var; hiçbir satır eklenmedi.</strong>
                  <ul>{result.errors.slice(0, 12).map((e) => <li key={e.row}>{e.row}. satır: {e.message}</li>)}</ul>
                  {result.errors.length > 12 && <span className="small">… ve {num(result.errors.length - 12)} satır daha</span>}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}
