import { useState } from "react";
import { useAssets, useLabels, useParts } from "../api/hooks";
import { ErrorNote, Field, Loading, Panel } from "../components/ui";
import { STATUS_LABEL } from "../lib/format";
import { openInNewTab } from "../lib/popup";

export function LabelsPage() {
  const assets = useAssets();
  const parts = useParts({ limit: 500 });
  const labels = useLabels();
  const [a, setA] = useState<Set<string>>(new Set());
  const [p, setP] = useState<Set<string>>(new Set());
  const [skip, setSkip] = useState(0);

  const flip = (s: Set<string>, setter: (v: Set<string>) => void, id: string) => {
    const n = new Set(s);
    if (n.has(id)) n.delete(id); else n.add(id);
    setter(n);
  };
  const total = a.size + p.size;
  const print = () =>
    openInNewTab(async () => (await labels.mutateAsync({ asset_ids: [...a], part_ids: [...p], skip })).url).catch(() => undefined);

  return (
    <>
      <div className="page-head"><h1>QR etiketleri</h1></div>
      <p className="sub lead">A4 hazır etiket kâğıdı, 63,5 × 38,1 mm (3 × 7 = 21 etiket). Etiketi makineye veya parçaya yapıştırın; uygulamadaki arama kutusuna kodu okutunca kayıt açılır.</p>
      <div className="grid">
        <Panel title="Makineler" actions={<button className="btn btn-small" onClick={() => setA(new Set(assets.data?.map((x) => x.id)))}>Tümü</button>}>
          {assets.isLoading ? <Loading /> : (
            <div className="checklist">
              {assets.data?.map((x) => (
                <label key={x.id}><input type="checkbox" checked={a.has(x.id)} onChange={() => flip(a, setA, x.id)} />
                  <strong>{x.code}</strong> <span className="muted">{x.manufacturer} {x.model}</span></label>
              ))}
            </div>
          )}
        </Panel>
        <Panel title="Parçalar" actions={
          <button className="btn btn-small" onClick={() => setP(new Set(parts.data?.filter((x) => x.status === "in_stock").map((x) => x.id)))}>Stoktakiler</button>
        }>
          {parts.isLoading ? <Loading /> : (
            <div className="checklist tall">
              {parts.data?.map((x) => (
                <label key={x.id}><input type="checkbox" checked={p.has(x.id)} onChange={() => flip(p, setP, x.id)} />
                  <strong>{x.serial_no ?? "seri no yok"}</strong>{" "}
                  <span className="muted">{x.part_name} · {x.asset_code ? `${x.asset_code} ${x.current_position}` : STATUS_LABEL[x.status]}</span></label>
              ))}
            </div>
          )}
        </Panel>
      </div>
      <Panel className="mt">
        <div className="filters">
          <Field label="Kâğıtta atlanacak etiket" hint="Yarısı kullanılmış kâğıt için">
            <input type="number" min={0} max={20} value={skip} onChange={(e) => setSkip(Number(e.target.value) || 0)} />
          </Field>
          <div className="spacer" />
          <button className="btn btn-primary" disabled={total === 0 || total > 63 || labels.isPending} onClick={print}>
            {total > 63 ? "En fazla 63 etiket" : `${total} etiketi yazdır`}
          </button>
        </div>
        <ErrorNote error={labels.error} />
      </Panel>
    </>
  );
}
