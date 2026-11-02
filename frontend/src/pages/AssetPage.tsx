import { useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router";
import { useAsset, useMeter } from "../api/hooks";
import type { Position } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import { MachineSchematic } from "../components/MachineSchematic";
import { InstallModal, PartTwin, RemoveModal } from "../components/PartActions";
import { ImageBox } from "../components/Images";
import { BandChip, ErrorNote, Loading, Modal, Field, Panel } from "../components/ui";
import { LAYOUT_LABEL, categoryLabel, date, num, pct } from "../lib/format";

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

export function AssetPage() {
  const { id } = useParams();
  const { can } = useAuth();
  const asset = useAsset(id);
  const [showAll, setShowAll] = useState(true);
  const [selected, setSelected] = useState<Position | null>(null);
  const [modal, setModal] = useState<{ kind: "install" | "remove" | "meter"; pos?: Position } | null>(null);

  // Başka bir makineye geçilince seçim sıfırlanır
  useEffect(() => setSelected(null), [id]);
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
          {can("technician") && <button className="btn btn-primary" onClick={() => setModal({ kind: "meter" })}>Saat gir</button>}
        </div>
      </div>

      <div className="grid">
        <Panel title="Şema" sub={`Son inspeksiyon: ${date(a.last_inspection_at)}`}
          actions={
            <div className="seg" role="group" aria-label="Gösterilen parçalar">
              <button aria-pressed={!showAll} onClick={() => setShowAll(false)}>Lastikler</button>
              <button aria-pressed={showAll} onClick={() => setShowAll(true)}>Tüm parçalar</button>
            </div>
          }>
          <div className="schematic-wrap">
            <MachineSchematic layout={a.layout} positions={a.positions} selected={sel?.code} showAll={showAll} onSelect={setSelected} />
          </div>
        </Panel>
        <Panel>
          {sel?.part_item_id ? <PartTwin partId={sel.part_item_id} compact /> : sel ? (
            <div className="stack">
              <h2>{sel.label}</h2>
              <p className="muted">Bu pozisyon boş ({categoryLabel(sel.category_code)}).</p>
              {can("technician") && <button className="btn btn-primary" onClick={() => setModal({ kind: "install", pos: sel })}>Parça tak</button>}
            </div>
          ) : <p className="muted">Şemadan veya tablodan bir pozisyon seçin.</p>}
        </Panel>
      </div>

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
                  <td>{p.part_item_id ? <Link to={`/parca/${p.part_item_id}`} onClick={(e) => e.stopPropagation()}>{p.serial_no ?? p.part_name}</Link> : <span className="muted">boş</span>}</td>
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

      {modal?.kind === "meter" && <MeterModal assetId={a.id} current={a.meter_hours} onClose={() => setModal(null)} />}
      {modal?.kind === "install" && modal.pos && (
        <InstallModal assetId={a.id} assetCode={a.code} position={modal.pos} onClose={() => setModal(null)} />
      )}
      {modal?.kind === "remove" && modal.pos?.part_item_id && (
        <RemoveModal partId={modal.pos.part_item_id} title={`${a.code} ${modal.pos.code}`} onClose={() => setModal(null)} />
      )}
    </>
  );
}
