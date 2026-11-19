// Rota: ürün ağacının sıralı işlemleri, 1 birim için planlanan süre ve makine saat maliyeti. Üretim emri işlemleri buradan kopyalar.
import { useEffect, useState, type FormEvent } from "react";
import { useRoute, useSaveRoute } from "../api/hooks";
import { Empty, ErrorNote, Loading } from "../components/ui";
import { usd } from "../lib/format";
import { duration } from "../lib/production";

interface Row { name: string; minutes: string; rate: string }
const parseNum = (v: string) => Number(v.replace(",", "."));

export function RoutePanel({ bomId, unit, edit }: { bomId: string; unit: string | null; edit: boolean }) {
  const route = useRoute(bomId);
  const save = useSaveRoute(bomId);
  const [rows, setRows] = useState<Row[]>([]);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (route.data) {
      setRows(route.data.map((o) => ({ name: o.name, minutes: o.planned_minutes == null ? "" : String(Number(o.planned_minutes)),
                                        rate: o.machine_rate == null ? "" : String(Number(o.machine_rate)) })));
      setDirty(false);
    }
  }, [route.data]);

  if (route.isLoading) return <Loading />;
  if (route.error) return <ErrorNote error={route.error} />;
  const total = (route.data ?? []).reduce((s, o) => s + Number(o.planned_minutes ?? 0), 0);
  const change = (next: Row[]) => { setRows(next); setDirty(true); };
  const set = (i: number, patch: Partial<Row>) => change(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const up = (i: number) => change(rows.map((r, j) => (j === i - 1 ? rows[i] : j === i ? rows[i - 1] : r)));
  const valid = rows.every((r) => r.name.trim().length >= 2 && (r.minutes.trim() === "" || parseNum(r.minutes) > 0)
    && (r.rate.trim() === "" || parseNum(r.rate) >= 0));
  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate(rows.map((r) => ({ name: r.name.trim(), planned_minutes: r.minutes.trim() === "" ? null : parseNum(r.minutes),
                                machine_rate: r.rate.trim() === "" ? null : parseNum(r.rate) })));
  };

  return (
    <div className="form">
      <h3 className="mini-head">Rota{total > 0 && <span className="muted small"> · 1 {unit ?? "adet"} için {duration(total)}</span>}</h3>
      {!edit ? (
        rows.length === 0 ? <Empty>Rota tanımlı değil.</Empty> : (
          <ol className="route-list">
            {route.data?.map((o) => <li key={o.id}><strong>{o.name}</strong> <span className="muted small">{o.planned_minutes == null ? "süre yok" : duration(o.planned_minutes)}{o.machine_rate != null && ` · makine ${usd(Number(o.machine_rate))}/saat`}</span></li>)}
          </ol>
        )
      ) : (
        <form className="form" onSubmit={submit}>
          {rows.length === 0 && <p className="muted small">Ürün hangi işlemlerden geçiyor? Sırayla yazın (kesim, kaynak, montaj…). Üretim emri açmak için en az bir işlem gerekir.</p>}
          <div className="route-rows">
            {rows.length > 0 && <div className="route-row route-head" aria-hidden="true"><span>İşlem</span><span>dk / birim</span><span>makine $/saat</span></div>}
            {rows.map((r, i) => (
              <div className="route-row" key={i}>
                <span className="route-seq">{i + 1}</span>
                <input aria-label={`${i + 1}. işlem adı`} placeholder="İşlem adı" value={r.name} maxLength={80} onChange={(e) => set(i, { name: e.target.value })} />
                <input aria-label={`${i + 1}. işlem süresi (dakika)`} placeholder="dk / birim" inputMode="decimal" value={r.minutes} onChange={(e) => set(i, { minutes: e.target.value })} />
                <input aria-label={`${i + 1}. işlem makine saat maliyeti`} placeholder="makine $/saat" inputMode="decimal" value={r.rate} onChange={(e) => set(i, { rate: e.target.value })} />
                <button type="button" className="icon-btn" aria-label={`${i + 1}. işlemi yukarı al`} disabled={i === 0} onClick={() => up(i)}>↑</button>
                <button type="button" className="icon-btn" aria-label={`${i + 1}. işlemi sil`} onClick={() => change(rows.filter((_, j) => j !== i))}>×</button>
              </div>
            ))}
          </div>
          <ErrorNote error={save.error} />
          <div className="actions">
            <button type="button" className="btn btn-small" onClick={() => change([...rows, { name: "", minutes: "", rate: "" }])}>İşlem ekle</button>
            {dirty && <button className="btn btn-primary btn-small" disabled={!valid || save.isPending}>Rotayı kaydet</button>}
          </div>
          <p className="muted small">Süre 1 {unit ?? "adet"} ürün için dakikadır; boş bırakılabilir. Makine saat maliyeti yalnızca makinede yapılan işlemlere yazılır. Rota değişikliği açılmış emirleri etkilemez.</p>
        </form>
      )}
    </div>
  );
}
