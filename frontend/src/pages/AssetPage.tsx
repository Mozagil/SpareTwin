import { useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router";
import { useAsset, useMeter, useTransferActions } from "../api/hooks";
import type { PendingTransfer, Position } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import { MachineSchematic } from "../components/MachineSchematic";
import { InstallModal, PartTwin, RemoveModal } from "../components/PartActions";
import { ImageBox } from "../components/Images";
import { AssetMaintenance } from "../components/AssetMaintenance";
import { ReportButton } from "../components/ReportButton";
import { AssetOps } from "../components/Ops";
import { useDowntime, usePlans } from "../api/hooks";
import { BandChip, ErrorNote, Loading, Modal, Field, Panel } from "../components/ui";
import { LAYOUT_LABEL, categoryLabel, date, num, pct } from "../lib/format";
import { daysLeft } from "../lib/transfer";

function MeterModal({ assetId, current, onClose }: { assetId: string; current: number; onClose: () => void }) {
  const meter = useMeter();
  const [hours, setHours] = useState(String(current));
  const submit = (e: FormEvent) => {
    e.preventDefault();
    meter.mutate({ assetId, hours: Number(hours) }, { onSuccess: onClose });
  };
  return (
    <Modal title="Motor saati gir" onClose={onClose}
      footer={<><button className="btn btn-ghost" onClick={onClose}>Vazgeç</button>
        <button className="btn btn-primary" form="meter-form" disabled={meter.isPending}>Kaydet</button></>}>
      <form id="meter-form" className="form" onSubmit={submit}>
        <Field label="Motor saati" hint={`Mevcut: ${num(current)}. Geri gidemez.`}>
          <input type="number" inputMode="decimal" min={current} step="0.1" value={hours} onChange={(e) => setHours(e.target.value)} required />
        </Field>
        <ErrorNote error={meter.error} />
      </form>
    </Modal>
  );
}

function TransferModal({ assetId, assetCode, partCount, onClose }: { assetId: string; assetCode: string; partCount: number; onClose: () => void }) {
  const { create } = useTransferActions();
  const [note, setNote] = useState("");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate({ assetId, note: note.trim() || null }, { onSuccess: onClose });
  };
  return (
    <Modal title={`${assetCode} · müşteriye devret`} onClose={onClose}
      footer={<><button className="btn btn-ghost" onClick={onClose}>Vazgeç</button>
        <button className="btn btn-primary" form="transfer-form" disabled={create.isPending}>Devir kodu üret</button></>}>
      <form id="transfer-form" className="form" onSubmit={submit}>
        <p>
          Tek kullanımlık bir devir kodu üretilir. Makineyi teslim alan firma bu kodu kendi hesabında
          <strong> Kayıt › Makine devral</strong> ekranına girince makine, takılı {num(partCount)} parça ikizi ve
          geçmişleri (olaylar, ölçümler, kontroller, fotoğraflar) o firmaya geçer.
        </p>
        <Field label="Kime / not" hint="İsteğe bağlı. Alıcı kodu sorguladığında görür.">
          <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={300} placeholder="Kuzey Liman teslimatı" />
        </Field>
        <p className="muted small">
          Kod 30 gün geçerlidir; devralınana kadar iptal edebilirsiniz. Devralındıktan sonra makine filonuzdan çıkar ve işlem geri alınmaz.
          Parça alış fiyatları ve maliyet kayıtlarınız alıcıya geçmez.
        </p>
        <ErrorNote error={create.error} />
      </form>
    </Modal>
  );
}

function TransferBanner({ transfer }: { transfer: PendingTransfer }) {
  const { cancel } = useTransferActions();
  const [copied, setCopied] = useState(false);
  const copy = () => navigator.clipboard?.writeText(transfer.code).then(() => setCopied(true));
  return (
    <div className="transfer-banner" role="status">
      <div>
        <strong>Devir bekliyor</strong>
        <p className="small">
          Bu kodu makineyi teslim alan firmaya iletin; Kayıt › Makine devral ekranına girecekler.
          {transfer.note ? ` Not: ${transfer.note}.` : ""} Kod {daysLeft(transfer.expires_at) ?? "0 gün"} daha geçerli.
        </p>
        <ErrorNote error={cancel.error} />
      </div>
      <div className="transfer-code mono">{transfer.code}</div>
      <div className="transfer-actions">
        <button className="btn btn-small" onClick={copy}>{copied ? "Kopyalandı" : "Kodu kopyala"}</button>
        <button className="btn btn-small" disabled={cancel.isPending} onClick={() => cancel.mutate(transfer.id)}>Devri iptal et</button>
      </div>
    </div>
  );
}

export function AssetPage() {
  const { id } = useParams();
  const { can } = useAuth();
  const asset = useAsset(id);
  const [showAll, setShowAll] = useState(true);
  const [selected, setSelected] = useState<Position | null>(null);
  const [modal, setModal] = useState<{ kind: "install" | "remove" | "meter" | "transfer"; pos?: Position } | null>(null);

  const plans = usePlans(id);
  const downtime = useDowntime(id);
  const openDown = downtime.data?.find((d) => !d.ended_at);
  // Başka bir makineye geçilince seçim sıfırlanır
  useEffect(() => {
    setSelected(null);
  }, [id]);
  // Açılışta en kötü durumdaki dolu pozisyonu seç (dashboard ile aynı davranış)
  useEffect(() => {
    if (!asset.data || selected) return;
    const worst = asset.data.positions
      .filter((p) => p.part_item_id)
      .sort((x, y) => (x.condition_pct ?? 101) - (y.condition_pct ?? 101))[0];
    if (worst) setSelected(worst);
  }, [asset.data, selected]);

  if (asset.isLoading) return <Loading />;
  if (asset.error) return <ErrorNote error={asset.error} />;
  const a = asset.data!;
  const sel = selected && a.positions.find((p) => p.code === selected.code);

  return (
    <>
      <div className="page-head">
        <div className="asset-head">
          <ImageBox image={a.image} uploadPath={`/assets/${a.id}/image`} alt={`${a.code} ${a.manufacturer ?? ""} ${a.model ?? ""}`}
                    size="sm" note={a.image?.source === "model" ? "Model görseli" : undefined} />
          <div>
          <p className="crumbs"><Link to="/">Filo</Link> / {a.code}</p>
          <h1>{a.code} · {a.manufacturer} {a.model}</h1>
          <p className="sub">
            {LAYOUT_LABEL[a.layout ?? "generic"]} · {a.site_name ?? "saha atanmamış"} · seri {a.serial_no ?? "–"}
            {a.year ? ` · ${a.year}` : ""} · QR {a.qr_code}
          </p>
          </div>
        </div>
        <div className="head-actions">
          <div className="meter"><span>Motor saati</span><strong>{num(a.meter_hours)}</strong></div>
          <ReportButton assetId={a.id} />
          {can("technician") && <button className="btn btn-ghost" onClick={() => setModal({ kind: "meter" })}>Saat gir</button>}
          {can("manager") && !a.transfer && <button className="btn btn-ghost" onClick={() => setModal({ kind: "transfer" })}>Müşteriye devret</button>}
          {can("technician") && <Link className="btn btn-primary" to={`/kontrol?makine=${a.id}`}>Kontrol başlat</Link>}
        </div>
      </div>
      {a.transfer && <TransferBanner transfer={a.transfer} />}

      <div className="grid">
        <Panel title="Şema" sub={`Son inspeksiyon: ${date(a.last_inspection_at)}`}
          actions={
            <div className="seg" role="group" aria-label="Gösterilen parçalar">
              <button aria-pressed={!showAll} onClick={() => setShowAll(false)}>Lastikler</button>
              <button aria-pressed={showAll} onClick={() => setShowAll(true)}>Tüm parçalar</button>
            </div>
          }>
          <div className="schematic-wrap">
            <MachineSchematic layout={a.layout} image={a.schematic_image?.url} positions={a.positions} selected={sel?.code} showAll={showAll} onSelect={setSelected} />
          </div>
        </Panel>
        <Panel>
          {sel?.part_item_id ? <PartTwin partId={sel.part_item_id} compact /> : sel ? (
            <div className="stack">
              <h2>{sel.label}</h2>
              <p className="muted">Bu pozisyon boş ({categoryLabel(sel.category_code)}).</p>
              {(sel.fits?.length ?? 0) > 0 && (
                <p className="small">Parça listesine göre uygun: {sel.fits!.map((f) => `${f.name} (${f.in_stock > 0 ? `stokta ${num(f.in_stock)}` : "stokta yok"})`).join(", ")}</p>
              )}
              {can("technician") && <button className="btn btn-primary" onClick={() => setModal({ kind: "install", pos: sel })}>Parça tak</button>}
            </div>
          ) : <p className="muted">Şemadan veya tablodan bir pozisyon seçin.</p>}
        </Panel>
      </div>

      <Panel title="Bakım ve duruş" className="mt">
        <AssetOps assetId={a.id} code={a.code} plans={plans.data ?? []}
                  downSince={openDown?.started_at ?? null} openDowntimeId={openDown?.id ?? null} />
      </Panel>

      <Panel title="Pozisyonlar" className="mt">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr><th>Pozisyon</th><th>Tür</th><th>Parça</th><th>Durum</th><th className="num">Çalışma</th><th className="num">Kalan</th><th /></tr>
            </thead>
            <tbody>
              {a.positions.map((p) => (
                <tr key={p.code} aria-selected={sel?.code === p.code} onClick={() => setSelected(p)}>
                  <td><strong>{p.code}</strong><div className="muted small">{p.label}</div></td>
                  <td>{categoryLabel(p.category_code)}</td>
                  <td>{p.part_item_id ? <Link to={`/parca/${p.part_item_id}`} onClick={(e) => e.stopPropagation()}>{p.serial_no ?? p.part_name}</Link> : <span className="muted">boş{p.fits?.length ? ` · uygun: ${p.fits.map((f) => f.name).join(", ")}` : ""}</span>}</td>
                  <td>{p.part_item_id ? <BandChip band={p.band}>{p.band === "unknown" ? "Ölçüm bekliyor" : pct(p.condition_pct)}</BandChip> : "–"}</td>
                  <td className="num">{p.hours_total != null ? `${num(p.hours_total)} sa` : "–"}</td>
                  <td className="num">{p.projected_hours_left != null ? `${num(p.projected_hours_left)} sa` : "–"}</td>
                  <td className="row-actions">
                    {can("technician") && (p.part_item_id
                      ? <button className="btn btn-small" onClick={(e) => { e.stopPropagation(); setModal({ kind: "remove", pos: p }); }}>Sök</button>
                      : <button className="btn btn-small btn-primary" onClick={(e) => { e.stopPropagation(); setModal({ kind: "install", pos: p }); }}>Tak</button>)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <AssetMaintenance assetId={a.id} assetCode={a.code} />

      {modal?.kind === "meter" && <MeterModal assetId={a.id} current={a.meter_hours} onClose={() => setModal(null)} />}
      {modal?.kind === "transfer" && (
        <TransferModal assetId={a.id} assetCode={a.code} partCount={a.positions.filter((p) => p.part_item_id).length} onClose={() => setModal(null)} />
      )}
      {modal?.kind === "install" && modal.pos && (
        <InstallModal assetId={a.id} assetCode={a.code} position={modal.pos}
                      rimSlot={a.positions.find((p) => p.code === `${modal.pos!.code}-J`)} onClose={() => setModal(null)} />
      )}
      {modal?.kind === "remove" && modal.pos?.part_item_id && (
        <RemoveModal partId={modal.pos.part_item_id} title={`${a.code} ${modal.pos.code}`} onClose={() => setModal(null)} />
      )}
    </>
  );
}
