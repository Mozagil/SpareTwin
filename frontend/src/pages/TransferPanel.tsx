// Makine devral: devreden firmanın verdiği kodla makineyi, takılı parça ikizlerini ve
// geçmişlerini filoya alma. Altında iki yönlü devir geçmişi. Kurallar veritabanında (0024).
import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import { useSites, useTransferActions, useTransfers } from "../api/hooks";
import type { TransferRow } from "../api/types";
import { Empty, ErrorNote, Field, Loading } from "../components/ui";
import { categoryLabel, date, num } from "../lib/format";
import { daysLeft, normalizeTransferCode, transferLabel, transferTone } from "../lib/transfer";

function History() {
  const list = useTransfers();
  const { cancel } = useTransferActions();
  if (list.isLoading) return <Loading />;
  if (list.error) return <ErrorNote error={list.error} />;
  const rows = list.data ?? [];
  if (rows.length === 0) return <Empty>Henüz devredilen ya da devralınan makine yok.</Empty>;
  const machine = (t: TransferRow) => (t.direction === "in" && t.asset_id ? <Link to={`/makine/${t.asset_id}`}>{t.asset_code}</Link> : t.asset_code);
  return (
    <>
      <div className="table-wrap">
        <table className="table transfer-table">
          <thead><tr><th>Makine</th><th>Karşı firma</th><th className="num">Parça</th><th>Tarih</th><th>Durum</th><th /></tr></thead>
          <tbody>
            {rows.map((t) => (
              <tr key={t.id}>
                <td><strong>{machine(t)}</strong>
                  <div className="muted small">{[t.model_name, t.serial_no && `seri ${t.serial_no}`].filter(Boolean).join(" · ") || "–"}</div></td>
                <td>{t.direction === "out" ? "→ " : "← "}{t.counterparty ?? <span className="muted">{t.note ?? "henüz devralınmadı"}</span>}
                  {t.counterparty && t.note && <div className="muted small">{t.note}</div>}</td>
                <td className="num">{num(t.part_count)}</td>
                <td>{date(t.accepted_at ?? t.created_at)}</td>
                <td><span className={`chip ${transferTone(t.status)}`}>{transferLabel(t)}</span>
                  {t.code && <div className="mono transfer-code-small">{t.code} · {daysLeft(t.expires_at)}</div>}</td>
                <td className="row-actions">
                  {t.status === "pending" && (
                    <button className="btn btn-small" disabled={cancel.isPending} onClick={() => cancel.mutate(t.id)}>İptal et</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ErrorNote error={cancel.error} />
    </>
  );
}

export function TransferPanel() {
  const sites = useSites();
  const { preview, accept } = useTransferActions();
  const [code, setCode] = useState("");
  const [assetCode, setAssetCode] = useState("");
  const [siteId, setSiteId] = useState("");
  const p = preview.data;

  const lookup = (e: FormEvent) => {
    e.preventDefault();
    accept.reset();
    preview.mutate(normalizeTransferCode(code), { onSuccess: (d) => setAssetCode(d.code_taken ? "" : d.asset_code) });
  };
  const take = (e: FormEvent) => {
    e.preventDefault();
    if (!p) return;
    accept.mutate(
      { code: p.code, asset_code: assetCode.trim() || null, site_id: siteId || null },
      { onSuccess: () => { preview.reset(); setCode(""); } },
    );
  };

  return (
    <div className="stack transfer-panel">
      <form className="form transfer-lookup" onSubmit={lookup}>
        <Field label="Devir kodu" hint="Makineyi teslim eden firma kendi SpareTwin hesabında üretir ve size iletir.">
          <input className="mono" value={code} onChange={(e) => setCode(e.target.value)} placeholder="DV-XXXXXXXXXX" maxLength={40} required autoComplete="off" />
        </Field>
        <button className="btn btn-primary" disabled={preview.isPending || !code.trim()}>Sorgula</button>
      </form>
      <ErrorNote error={preview.error} />

      {accept.data && (
        <div className="success-note" role="status">
          {accept.data.asset_code} filonuza eklendi: {accept.data.from_tenant_name} firmasından {num(accept.data.part_count)} parça ikizi geçmişiyle geldi.{" "}
          <Link to={`/makine/${accept.data.asset_id}`}>Makineyi aç</Link>
        </div>
      )}

      {p && (
        <form className="form transfer-preview" onSubmit={take}>
          <h3 className="mini-head">{p.asset_code} · {p.model_name ?? "model belirtilmemiş"}</h3>
          <dl className="facts">
            <div className="fact"><dt>Devreden</dt><dd>{p.from_tenant_name}</dd></div>
            <div className="fact"><dt>Motor saati</dt><dd>{num(p.meter_hours)}</dd></div>
            <div className="fact"><dt>Takılı parça</dt><dd>{num(p.parts.length)}</dd></div>
          </dl>
          <p className="muted small">
            Seri {p.serial_no ?? "–"}{p.year ? ` · ${p.year}` : ""} · QR {p.qr_code ?? "–"}{p.note ? ` · Not: ${p.note}` : ""} · kod {daysLeft(p.expires_at) ?? "süresi doldu"} daha geçerli
          </p>
          {p.parts.length > 0 && (
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Pozisyon</th><th>Tür</th><th>Parça</th><th>Seri no</th><th className="num">Çalışma</th></tr></thead>
                <tbody>
                  {p.parts.map((x) => (
                    <tr key={x.position}>
                      <td><strong>{x.position}</strong></td>
                      <td>{categoryLabel(x.category_code) === x.category_code ? x.category_name : categoryLabel(x.category_code)}</td>
                      <td>{x.name}</td>
                      <td>{x.serial_no ?? "–"}</td>
                      <td className="num">{num(x.hours_total)} sa</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="form-row">
            <Field label="Filo / ekipman no" hint={p.code_taken ? `Filonuzda ${p.asset_code} kodlu makine var; başka bir kod girin.` : undefined}>
              <input value={assetCode} onChange={(e) => setAssetCode(e.target.value)} maxLength={40} required />
            </Field>
            <Field label="Saha">
              <select value={siteId} onChange={(e) => setSiteId(e.target.value)}>
                <option value="">Belirtilmedi</option>
                {sites.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </Field>
          </div>
          <p className="muted small">
            Devralınca makine, takılı parçalar ve geçmişleri (olaylar, ölçümler, kontroller, fotoğraflar) firmanıza geçer; QR etiketleri aynı kalır.
            Devredenin maliyet bilgileri gelmez. İşlem geri alınmaz.
          </p>
          <ErrorNote error={accept.error} />
          <div className="transfer-actions">
            <button type="button" className="btn btn-ghost" onClick={() => preview.reset()}>Vazgeç</button>
            <button className="btn btn-primary" disabled={accept.isPending || !assetCode.trim()}>Devral</button>
          </div>
        </form>
      )}

      <h3 className="mini-head sup-section">Devir geçmişi</h3>
      <History />
    </div>
  );
}
