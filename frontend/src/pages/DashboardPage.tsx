import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router";
import { useAsset, useAssets, useCatalogParts, useParts, useTireCost } from "../api/hooks";
import type { AssetSummary, Position } from "../api/types";
import { MachineSchematic } from "../components/MachineSchematic";
import { PartTwin } from "../components/PartActions";
import { Empty, ErrorNote, Loading, Panel } from "../components/ui";
import { LAYOUT_LABEL, categoryLabel, num, pct, usd } from "../lib/format";

function FleetStrip({ assets, selected, onSelect }: {
  assets: AssetSummary[]; selected: string | null; onSelect: (id: string) => void;
}) {
  return (
    <section className="fleet" aria-label="Makineler">
      {assets.map((a) => {
        const alert = a.critical_parts
          ? <span className="alert t-critical">{a.critical_parts} kritik parça</span>
          : a.watch_parts
            ? <span className="alert t-watch">{a.watch_parts} parça takipte</span>
            : <span className="alert t-ok">Sorun yok</span>;
        // Basit sağlık şeridi: kritik / takip / diğer
        const ok = Math.max(a.installed_parts - a.critical_parts - a.watch_parts, 0);
        return (
          <button key={a.id} className="unit" aria-pressed={a.id === selected} onClick={() => onSelect(a.id)}>
            <div className="row"><span className="code">{a.code}</span><span className="meta">{num(a.meter_hours)} saat</span></div>
            <div className="meta">{[a.manufacturer, a.model].filter(Boolean).join(" ")}{a.site_name ? ` · ${a.site_name}` : ""}</div>
            <div className="pips" aria-hidden="true">
              {Array.from({ length: a.critical_parts }, (_, i) => <i key={`c${i}`} className="pip" style={{ background: "var(--critical)" }} />)}
              {Array.from({ length: a.watch_parts }, (_, i) => <i key={`w${i}`} className="pip" style={{ background: "var(--watch)" }} />)}
              {Array.from({ length: ok }, (_, i) => <i key={`o${i}`} className="pip" style={{ background: "var(--ok)" }} />)}
            </div>
            {alert}
          </button>
        );
      })}
    </section>
  );
}

function Priorities() {
  const crit = useParts({ band: "critical", status: "installed" });
  const watch = useParts({ band: "watch", status: "installed" });
  const catalog = useCatalogParts();
  const navigate = useNavigate();

  const items = useMemo(() => {
    const rows = [...(crit.data ?? []), ...(watch.data ?? [])]
      // Önce kritikler, sonra takiptekiler; her grupta en az kalan saat / en düşük durum önce
      .sort((a, b) =>
        (a.band === "critical" ? 0 : 1) - (b.band === "critical" ? 0 : 1) ||
        (a.projected_hours_left ?? 1e9) - (b.projected_hours_left ?? 1e9) ||
        (a.condition_pct ?? 0) - (b.condition_pct ?? 0))
      .slice(0, 6)
      .map((p) => ({
        key: p.id,
        band: p.band,
        what: `${p.asset_code} ${p.current_position} · ${categoryLabel(p.category_code)}`,
        why: p.category_code === "tire"
          ? `Diş ${pct(p.condition_pct)}${p.projected_hours_left != null ? `, yaklaşık ${num(p.projected_hours_left)} saat içinde değişim` : ""}.`
          : (p.condition_pct ?? 0) <= 0 ? "Beklenen ömrünü aştı." : `Ömrün ${pct(100 - (p.condition_pct ?? 0))} kadarı kullanıldı.`,
        to: `/parca/${p.id}`,
        action: p.category_code === "tire" ? "Değişim planla" : "İncele",
      }));
    const low = (catalog.data ?? [])
      .filter((c) => c.min_stock > 0 && c.in_stock < c.min_stock)
      .map((c) => ({
        key: `stock-${c.id}`,
        band: "watch" as const,
        what: `${c.name} stok seviyesi`,
        why: `Depoda ${c.in_stock} adet var, kritik seviye ${c.min_stock}.`,
        to: `/kayit?sekme=teslim&kalem=${c.id}`,
        action: "Teslim al",
      }));
    return [...rows.slice(0, 2), ...low.slice(0, 2), ...rows.slice(2)].slice(0, 7);
  }, [crit.data, watch.data, catalog.data]);

  return (
    <Panel className="a-prio" title="Öncelikli işler" sub="Kalan ömre göre sıralı; en acil olan en üstte">
      {crit.isLoading || watch.isLoading ? <Loading /> : items.length === 0 ? (
        <Empty>Şu an takip gerektiren parça yok.</Empty>
      ) : (
        <ul className="todo">
          {items.map((t) => (
            <li key={t.key}>
              <span className="sev" style={{ ["--c" as string]: `var(--${t.band})` }} />
              <div><div className="what">{t.what}</div><div className="why">{t.why}</div></div>
              <button onClick={() => navigate(t.to)}>{t.action}</button>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function TireCostPanel() {
  const cost = useTireCost();
  const rows = (cost.data ?? []).filter((r) => r.expected_cost_per_hour != null);
  const max = Math.max(...rows.map((r) => r.expected_cost_per_hour ?? 0), 0.01);
  return (
    <Panel className="a-cost" title="Lastik maliyeti, saat başına" sub="Makinedeki tüm lastikler, ömür sonunda beklenen değer">
      {cost.isLoading ? <Loading /> : rows.length === 0 ? <Empty>Hesap için en az bir diş ölçümü gerekiyor.</Empty> : (
        <div className="cph">
          {rows.map((r) => (
            <div className="cph-row" key={r.asset_id}>
              <Link to={`/makine/${r.asset_id}`}><b>{r.code}</b></Link>
              <span className="track"><i style={{ width: `${((r.expected_cost_per_hour ?? 0) / max) * 100}%` }} /></span>
              <span>{usd(r.expected_cost_per_hour)}</span>
            </div>
          ))}
        </div>
      )}
      <p className="note">Hesap: lastik maliyeti ÷ (çalıştığı saat + ölçülen aşınma hızıyla kalan saat).</p>
    </Panel>
  );
}

export function DashboardPage() {
  const assets = useAssets();
  const [assetId, setAssetId] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [slot, setSlot] = useState<Position | null>(null);
  const asset = useAsset(assetId ?? undefined);

  // İlk açılışta en sorunlu makineyi seç (liste zaten öyle sıralı gelir)
  useEffect(() => {
    if (!assetId && assets.data?.length) setAssetId(assets.data[0].id);
  }, [assets.data, assetId]);

  // Makine değişince en kötü parçayı seç
  useEffect(() => {
    if (!asset.data) return;
    const filled = asset.data.positions.filter((p) => p.part_item_id && (showAll || p.category_code === "tire"));
    const keep = slot && filled.find((p) => p.code === slot.code);
    if (keep) return;
    const worst = [...filled].sort((a, b) => (a.condition_pct ?? 101) - (b.condition_pct ?? 101))[0];
    setSlot(worst ?? null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [asset.data, showAll]);

  if (assets.isLoading) return <Loading />;
  if (assets.error) return <ErrorNote error={assets.error} />;
  if (!assets.data?.length)
    return (
      <Panel title="Henüz makine yok">
        <p>İlk makineyi ve parçalarını ekleyerek başlayın.</p>
        <Link className="btn btn-primary" to="/kayit">Makine ekle</Link>
      </Panel>
    );

  const a = asset.data;
  const current = slot && a?.positions.find((p) => p.code === slot.code);

  return (
    <>
      <div className="page-head"><h1>Filo durumu</h1></div>
      <FleetStrip assets={assets.data} selected={assetId} onSelect={(id) => { setAssetId(id); setSlot(null); }} />
      <div className="dash">
        <Panel
          className="a-schem"
          title={a ? <Link to={`/makine/${a.id}`} className="plain">{a.code} · {a.manufacturer} {a.model}</Link> : "…"}
          sub={a ? `${LAYOUT_LABEL[a.layout ?? "generic"]}${a.site_name ? `, ${a.site_name}` : ""}, ${num(a.meter_hours)} motor saati. Bir parçaya dokun, ikizini aç.` : ""}
          actions={
            <div className="seg" role="group" aria-label="Gösterilen parçalar">
              <button aria-pressed={!showAll} onClick={() => setShowAll(false)}>Lastikler</button>
              <button aria-pressed={showAll} onClick={() => setShowAll(true)}>Tüm parçalar</button>
            </div>
          }>
          {asset.isLoading || !a ? <Loading /> : (
            <>
              <div className="schematic-wrap">
                <MachineSchematic layout={a.layout} positions={a.positions} selected={slot?.code} showAll={showAll} onSelect={setSlot} />
              </div>
              <div className="legend">
                <span style={{ ["--c" as string]: "var(--ok)" }}>%40 üzeri</span>
                <span style={{ ["--c" as string]: "var(--watch)" }}>%20–40 takipte</span>
                <span style={{ ["--c" as string]: "var(--critical)" }}>%20 altı kritik</span>
                <span style={{ ["--c" as string]: "var(--unknown)" }}>Ölçüm bekliyor</span>
              </div>
            </>
          )}
        </Panel>
        <Panel className="a-twin" title={current ? undefined : "Parça ikizi"} sub={current ? undefined : "Şemadan bir parça seç"}>
          {current?.part_item_id ? (
            <PartTwin partId={current.part_item_id} compact />
          ) : current ? (
            <Empty>
              {current.label} boş.{" "}
              {a && <Link to={`/makine/${a.id}`}>Makine sayfasından parça takın.</Link>}
            </Empty>
          ) : (
            <p className="muted">Her lastik, silindir ve pompa burada kendi geçmişiyle görünür.</p>
          )}
        </Panel>
        <Priorities />
        <TireCostPanel />
      </div>
    </>
  );
}
