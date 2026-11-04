import { useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router";
import { useAsset, useInstall, useLogEvent, useMove, useParts, usePart, usePartEvents, useRemove, useWear } from "../api/hooks";
import type { Position } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import {
  EVENT_LABEL, NEXT_STATUS, REMOVE_REASONS, STATUS_LABEL, categoryLabel, dateTime, num, num1, pct, reasonLabel, usd,
} from "../lib/format";
import { ImageBox, PhotoStrip } from "./Images";
import { WearChart } from "./WearChart";
import { BandChip, ErrorNote, Field, Loading, Modal } from "./ui";

// ---------- Takma ----------
export function InstallModal({ assetId, assetCode, position, rimSlot, onClose }: {
  assetId: string; assetCode: string; position: Position; rimSlot?: Position; onClose: () => void;
}) {
  const stock = useParts({ status: "in_stock", category: position.category_code, limit: 200 });
  const offerRim = position.category_code === "tire" && !!rimSlot && !rimSlot.part_item_id;
  const rims = useParts({ status: "in_stock", category: "rim", limit: 200 });
  const install = useInstall();
  const [partId, setPartId] = useState("");
  const [rimId, setRimId] = useState("");
  const [notes, setNotes] = useState("");

  const submit = (e: FormEvent) => {
    e.preventDefault();
    install.mutate({ partId, asset_id: assetId, position: position.code, notes, rim_id: offerRim ? rimId : null }, { onSuccess: onClose });
  };
  return (
    <Modal title={`${assetCode} · ${position.label}: parça tak`} onClose={onClose}
      footer={<>
        <button className="btn btn-ghost" onClick={onClose}>Vazgeç</button>
        <button className="btn btn-primary" form="install-form" disabled={!partId || install.isPending}>
          {install.isPending ? "Kaydediliyor…" : "Tak"}
        </button>
      </>}>
      <form id="install-form" onSubmit={submit} className="form">
        {stock.isLoading ? <Loading label="Stok yükleniyor" /> : (stock.data ?? []).length === 0 ? (
          <p className="muted">
            Stokta uygun {categoryLabel(position.category_code).toLocaleLowerCase("tr-TR")} yok.{" "}
            <Link to="/kayit?sekme=teslim">Parça teslim al</Link>
          </p>
        ) : (
          <Field label="Stoktaki parça">
            <select value={partId} onChange={(e) => setPartId(e.target.value)} required>
              <option value="">Seçin</option>
              {stock.data!.map((p) => (
                <option key={p.id} value={p.id}>{p.part_name} · {p.serial_no ?? "seri no yok"}</option>
              ))}
            </select>
          </Field>
        )}
        {offerRim && (
          <Field label="Jant (isteğe bağlı)"
                 hint={`${rimSlot!.code} pozisyonunda kayıtlı jant yok. Lastikle birlikte takılan jantı seçin; muayenesi takip edilir.`}>
            <select value={rimId} onChange={(e) => setRimId(e.target.value)}>
              <option value="">Jantı şimdi kaydetme</option>
              {rims.data?.map((r) => <option key={r.id} value={r.id}>{r.part_name} · {r.serial_no ?? "seri no yok"}</option>)}
            </select>
          </Field>
        )}
        <Field label="Not" hint="İsteğe bağlı">
          <input value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={1000} />
        </Field>
        <ErrorNote error={install.error} />
      </form>
    </Modal>
  );
}

// ---------- Rotasyon ----------
export function MoveModal({ partId, assetId, from, category, title, onClose }: {
  partId: string; assetId: string; from: string; category: string; title: string; onClose: () => void;
}) {
  const asset = useAsset(assetId);
  const move = useMove();
  const [to, setTo] = useState("");
  const targets = (asset.data?.positions ?? []).filter((p) => p.category_code === category && p.code !== from);
  const chosen = targets.find((p) => p.code === to);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    move.mutate({ partId, position: to }, { onSuccess: onClose });
  };
  return (
    <Modal title={`${title}: yer değiştir`} onClose={onClose}
      footer={<>
        <button className="btn btn-ghost" onClick={onClose}>Vazgeç</button>
        <button className="btn btn-primary" form="move-form" disabled={!to || move.isPending}>
          {chosen?.part_item_id ? "Yer değiştir" : "Taşı"}
        </button>
      </>}>
      <form id="move-form" className="form" onSubmit={submit}>
        {asset.isLoading ? <Loading /> : (
          <Field label="Hedef pozisyon">
            <select value={to} onChange={(e) => setTo(e.target.value)} required>
              <option value="">Seçin</option>
              {targets.map((p) => (
                <option key={p.code} value={p.code}>
                  {p.code} · {p.label} · {p.part_item_id ? `${p.serial_no ?? "dolu"} ile yer değiştirir` : "boş"}
                </option>
              ))}
            </select>
          </Field>
        )}
        <p className="muted small">
          {chosen?.part_item_id
            ? `İki parça yer değiştirir. Çalışma saatleri ve geçmişleri korunur; olay kaydına "rotasyon" yazılır.`
            : "Parça seçilen pozisyona taşınır. Çalışma saati ve geçmişi korunur."}
        </p>
        <ErrorNote error={move.error} />
      </form>
    </Modal>
  );
}

// ---------- Sökme ----------
export function RemoveModal({ partId, title, onClose }: { partId: string; title: string; onClose: () => void }) {
  const remove = useRemove();
  const [reason, setReason] = useState("worn_out");
  const [next, setNext] = useState("in_stock");
  const [cost, setCost] = useState("");
  const [notes, setNotes] = useState("");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    remove.mutate(
      { partId, reason, next_status: next, cost: cost ? Number(cost) : null, notes },
      { onSuccess: onClose },
    );
  };
  return (
    <Modal title={`${title}: sökme`} onClose={onClose}
      footer={<>
        <button className="btn btn-ghost" onClick={onClose}>Vazgeç</button>
        <button className="btn btn-primary" form="remove-form" disabled={remove.isPending}>
          {remove.isPending ? "Kaydediliyor…" : "Sökmeyi kaydet"}
        </button>
      </>}>
      <form id="remove-form" onSubmit={submit} className="form">
        <Field label="Sebep">
          <select value={reason} onChange={(e) => setReason(e.target.value)}>
            {REMOVE_REASONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </Field>
        <Field label="Parça nereye gidiyor?">
          <select value={next} onChange={(e) => setNext(e.target.value)}>
            {NEXT_STATUS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </Field>
        <Field label="İşçilik / söküm maliyeti ($)" hint="İsteğe bağlı; parçanın toplam maliyetine eklenir">
          <input type="number" min={0} step="0.01" inputMode="decimal" value={cost} onChange={(e) => setCost(e.target.value)} />
        </Field>
        <Field label="Not"><input value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={1000} /></Field>
        <p className="muted small">Çalışma saati makinenin güncel motor saatinden otomatik hesaplanır.</p>
        <ErrorNote error={remove.error} />
      </form>
    </Modal>
  );
}

// ---------- Olay kaydı ----------
const EVENT_OPTIONS: { value: string; label: string; event: string; reason: string | null }[] = [
  { value: "repaired", label: "Tamir", event: "repaired", reason: null },
  { value: "ndt", label: "NDT muayenesi (jant)", event: "inspected", reason: "ndt" },
  { value: "refurbished", label: "Kaplamadan / yenilemeden döndü", event: "refurbished", reason: null },
  { value: "note", label: "Not", event: "note", reason: null },
];

export function EventModal({ partId, title, isRim, onClose }: { partId: string; title: string; isRim: boolean; onClose: () => void }) {
  const log = useLogEvent();
  const options = EVENT_OPTIONS.filter((o) => isRim || o.value !== "ndt");
  const [kind, setKind] = useState(options[0].value);
  const [cost, setCost] = useState("");
  const [notes, setNotes] = useState("");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const o = options.find((x) => x.value === kind)!;
    log.mutate({ partId, event: o.event, reason: o.reason, cost: cost ? Number(cost) : null, notes }, { onSuccess: onClose });
  };
  return (
    <Modal title={`${title}: kayıt ekle`} onClose={onClose}
      footer={<>
        <button className="btn btn-ghost" onClick={onClose}>Vazgeç</button>
        <button className="btn btn-primary" form="event-form" disabled={log.isPending}>Kaydet</button>
      </>}>
      <form id="event-form" onSubmit={submit} className="form">
        <Field label="Kayıt türü">
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </Field>
        <Field label="Maliyet ($)" hint="İsteğe bağlı">
          <input type="number" min={0} step="0.01" inputMode="decimal" value={cost} onChange={(e) => setCost(e.target.value)} />
        </Field>
        <Field label="Not"><input value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={1000} /></Field>
        <ErrorNote error={log.error} />
      </form>
    </Modal>
  );
}

// ---------- Parça ikizi ----------
export function PartTwin({ partId, compact = false }: { partId: string; compact?: boolean }) {
  const { can } = useAuth();
  const part = usePart(partId);
  const isTire = part.data?.category_code === "tire";
  const wear = useWear(partId, isTire);
  const events = usePartEvents(partId);
  const [modal, setModal] = useState<"remove" | "event" | "move" | "rim" | null>(null);

  if (part.isLoading) return <Loading />;
  if (part.error) return <ErrorNote error={part.error} />;
  const p = part.data!;
  const title = p.current_position ? `${p.asset_code} ${p.current_position}` : (p.serial_no ?? p.part_name);
  const tire = p.tire;

  let verdict: ReactNode = null;
  if (p.status === "installed") {
    if (isTire) {
      verdict = tire?.tread_mm == null
        ? <>Henüz diş derinliği ölçülmedi. İlk ölçümden sonra kalan ömür hesaplanır.</>
        : tire.projected_hours_left != null
          ? <>Bu hızla hurda sınırına yaklaşık <strong>{num(tire.projected_hours_left)} saat</strong> kaldı.</>
          : <>Aşınma hızını hesaplamak için bir ölçüm daha gerekli.</>;
    } else if (p.expected_life_hours) {
      verdict = <>Beklenen {num(p.expected_life_hours)} saatlik ömrün{" "}
        <strong>{pct(100 - (p.condition_pct ?? 0))}</strong> kadarı kullanıldı.</>;
    }
  }

  return (
    <div className="twin">
      <ImageBox image={p.image} uploadPath={`/catalog/parts/${p.part_id}/image`}
                alt={p.part_name} size={compact ? "sm" : "md"}
                note={p.image ? `Katalog görseli · ${p.part_name}` : undefined} />
      <div className="twin-head">
        <BandChip band={p.band} />
        <span className="chip chip-plain">{STATUS_LABEL[p.status]}</span>
      </div>
      <div className="twin-title">{compact ? title : p.part_name}</div>
      <div className="sub">
        {compact ? p.part_name : title} · seri {p.serial_no ?? "yok"} · {categoryLabel(p.category_code)}
      </div>

      <dl className="facts">
        <div className="fact">
          <dt>{isTire ? "Diş derinliği" : p.expected_life_hours ? "Kalan ömür" : "Durum"}</dt>
          <dd>{isTire ? (tire?.tread_mm != null ? `${num1(tire.tread_mm)} mm` : "–")
            : p.expected_life_hours ? `${num(Math.max(p.expected_life_hours - p.hours_total, 0))} sa` : pct(p.condition_pct)}</dd>
        </div>
        <div className="fact"><dt>Çalışma</dt><dd>{num(p.hours_total)} sa</dd></div>
        <div className="fact">
          <dt>Saat başı maliyet</dt>
          <dd>{p.hours_total > 0 ? usd(p.cost_total / p.hours_total) : "–"}</dd>
        </div>
      </dl>

      {isTire && wear.data && wear.data.points.length > 1 && <WearChart wear={wear.data} band={p.band} />}
      {!isTire && p.expected_life_hours && (
        <div className="lifebar" style={{ ["--c" as string]: `var(--${p.band})` }}>
          <i style={{ width: `${Math.min(100 - (p.condition_pct ?? 0), 100)}%` }} />
        </div>
      )}
      {p.rim && p.rim.compliance !== "not_required" && (
        <p className="verdict">
          Jant NDT muayenesi: {p.rim.compliance === "overdue" ? <strong className="t-critical">gecikmiş</strong>
            : p.rim.compliance === "due_soon" ? <strong className="t-watch">yaklaşıyor</strong> : "güncel"}
          {" "}(son muayeneden bu yana {num(p.rim.hours_since_ndt)} / {num(p.rim.ndt_interval_hours)} saat)
        </p>
      )}
      {verdict && <p className="verdict" style={{ ["--c" as string]: `var(--${p.band})` }}>{verdict}</p>}

      {isTire && p.rim_slot && (
        <div className={`pair ${p.mounted_rim ? `pair-${p.mounted_rim.compliance}` : "pair-missing"}`}>
          <div className="pair-label">Jant · {p.rim_slot}</div>
          {p.mounted_rim ? (
            <>
              <div><Link to={`/parca/${p.mounted_rim.id}`} className="pair-main">{p.mounted_rim.serial_no ?? "seri no yok"}</Link>
                <span className="muted small"> · {p.mounted_rim.part_name}</span></div>
              <div className="small">
                {p.mounted_rim.compliance === "overdue" ? (
                  <strong className="t-critical">Muayene gecikti{p.mounted_rim.hours_to_due != null ? ` (${num(-p.mounted_rim.hours_to_due)} sa)` : ""}</strong>
                ) : p.mounted_rim.compliance === "due_soon" ? (
                  <strong className="t-watch">Muayene yaklaşıyor · {num(p.mounted_rim.hours_to_due)} sa kaldı</strong>
                ) : p.mounted_rim.compliance === "ok" ? (
                  <span className="t-ok">Muayene güncel · sıradakine {num(p.mounted_rim.hours_to_due)} sa</span>
                ) : <span className="muted">Muayene takibi yok</span>}
              </div>
            </>
          ) : (
            <>
              <div className="small"><strong className="t-watch">Jant kaydı yok:</strong> bu jantın muayenesi takip edilmiyor.</div>
              {can("technician") && (
                <button className="btn btn-small" onClick={() => setModal("rim")}>Jant tak</button>
              )}
            </>
          )}
        </div>
      )}
      {p.category_code === "rim" && p.mounted_tire && (
        <div className="pair">
          <div className="pair-label">Üzerindeki lastik</div>
          <div><Link to={`/parca/${p.mounted_tire.id}`} className="pair-main">{p.mounted_tire.serial_no ?? "seri no yok"}</Link>
            <span className="muted small"> · {p.mounted_tire.part_name} </span>
            <BandChip band={p.mounted_tire.band}>{p.mounted_tire.band === "unknown" ? "Ölçüm bekliyor" : pct(p.mounted_tire.condition_pct)}</BandChip></div>
        </div>
      )}

      <PhotoStrip photos={p.photos} title={title} />

      {!compact && Object.keys(p.latest_measurements ?? {}).length > 0 && (
        <p className="muted small">
          Son ölçümler:{" "}
          {Object.entries(p.latest_measurements!).map(([k, m]) => `${k} ${num1(m.value)} ${m.unit ?? ""}`).join(" · ")}
        </p>
      )}

      <ol className="timeline">
        {(events.data ?? []).slice(0, compact ? 4 : 50).map((e) => (
          <li key={e.id}>
            {EVENT_LABEL[e.event_type] ?? e.event_type}
            {e.asset_code && e.position && ` · ${e.asset_code} ${e.position}`}
            {e.reason_code && ` · ${reasonLabel(e.reason_code)}`}
            {e.cost != null && ` · ${usd(e.cost)}`}
            {e.notes && <span className="muted"> · {e.notes}</span>}
            <time>
              {dateTime(e.occurred_at)}
              {e.part_hours != null && ` · parça ${num(e.part_hours)} sa`}
              {e.performed_by_name && ` · ${e.performed_by_name}`}
            </time>
          </li>
        ))}
      </ol>

      <div className="actions">
        {compact && <Link className="btn btn-ghost" to={`/parca/${p.id}`}>Ayrıntılar</Link>}
        {can("technician") && p.status === "installed" && (
          <button className="btn btn-primary" onClick={() => setModal("remove")}>Sökmeyi kaydet</button>
        )}
        {can("technician") && p.status === "installed" && p.category_code === "tire" && (
          <button className="btn btn-ghost" onClick={() => setModal("move")}>Yer değiştir</button>
        )}
        {can("technician") && (
          <button className="btn btn-ghost" onClick={() => setModal("event")}>Kayıt ekle</button>
        )}
      </div>
      {modal === "remove" && <RemoveModal partId={p.id} title={title} onClose={() => setModal(null)} />}
      {modal === "rim" && p.current_asset_id && p.rim_slot && (
        <InstallModal assetId={p.current_asset_id} assetCode={p.asset_code ?? ""} onClose={() => setModal(null)}
          position={{ code: p.rim_slot, label: `${p.current_position} jantı`, category_code: "rim", axle: null, x: null, y: null,
                      part_item_id: null, part_name: null, serial_no: null, condition_pct: null, band: "empty",
                      projected_hours_left: null, hours_total: null }} />
      )}
      {modal === "move" && p.current_asset_id && p.current_position && (
        <MoveModal partId={p.id} assetId={p.current_asset_id} from={p.current_position} category={p.category_code}
                   title={title} onClose={() => setModal(null)} />
      )}
      {modal === "event" && (
        <EventModal partId={p.id} title={title} isRim={p.category_code === "rim"} onClose={() => setModal(null)} />
      )}
    </div>
  );
}
