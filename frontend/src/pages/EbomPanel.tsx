// Mühendislik ağacı (eBOM): solda ürünler, sağda seçilen ürünün tasarım ağacı ve
// firmanın kuralları uygulanınca çıkan üretim ağacı (mBOM) önizlemesi. Dönüşüm sunucuda hesaplanır.
import { useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";
import { download } from "../api/client";
import { useBomRuleActions, useBomRules, useCatalogParts, useCategories, useEbom, useEbomActions, useEboms } from "../api/hooks";
import type { MbomLine, ProductBomImportResult } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import { Empty, ErrorNote, Field, Loading, Modal, Panel } from "../components/ui";
import { categoryLabel, num } from "../lib/format";
import { EMPTY_RULE, RULE_ACTIONS, buildRule, ebomState, matchKinds, type MatchKind, type RuleForm } from "../lib/ebom";

const nf = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 4 });
const qty = (v: number | string | null, unit: string | null) => (v == null ? "–" : `${nf.format(Number(v))} ${unit ?? ""}`.trim());
const MATCH_LABEL: Record<MatchKind, string> = { category: "Parça tipi", part: "Tek kalem", all: "Tüm kalemler" };

// ---------- Kurallar ----------
function RulesModal({ edit, onClose }: { edit: boolean; onClose: () => void }) {
  const rules = useBomRules();
  const catalog = useCatalogParts();
  const categories = useCategories();
  const { create, toggle, remove } = useBomRuleActions();
  const [f, setF] = useState<RuleForm>(EMPTY_RULE);
  const [problem, setProblem] = useState<string | null>(null);
  const kinds = matchKinds(f.action);
  const match = kinds.includes(f.match) ? f.match : kinds[0]!;
  const action = RULE_ACTIONS.find((a) => a.key === f.action)!;
  const up = <K extends keyof RuleForm>(k: K, v: RuleForm[K]) => { setProblem(null); setF({ ...f, [k]: v }); };
  const partOptions = catalog.data?.map((p) => <option key={p.id} value={p.id}>{p.category_name} · {p.name}{p.part_no ? ` · ${p.part_no}` : ""}</option>);
  const target = catalog.data?.find((p) => p.id === f.target);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const built = buildRule({ ...f, match });
    if ("error" in built) return setProblem(built.error);
    create.mutate(built.body, { onSuccess: () => setF({ ...EMPTY_RULE, action: f.action, match }) });
  };

  return (
    <Modal title="eBOM → mBOM kuralları" onClose={onClose} wide
           footer={<button type="button" className="btn" onClick={onClose}>Kapat</button>}>
      <p className="muted small">
        Kurallar firmanın bütün mühendislik ağaçlarına uygulanır. Sıra sabittir: düzleştir → çıkar → değiştir → sarf ekle → fire payı.
        Kural değişince ürün ağaçları kendiliğinden değişmez; her ürün için “Üretim ağacına yaz” denir.
      </p>
      {rules.isLoading ? <Loading /> : rules.error ? <ErrorNote error={rules.error} /> : (rules.data ?? []).length === 0 ? (
        <Empty>Henüz kural yok: üretim ağacı mühendislik ağacının aynısı olur.</Empty>
      ) : (
        <ul className="rule-list">
          {rules.data!.map((r) => (
            <li key={r.id} className={r.is_active ? undefined : "is-off"}>
              <span>{r.label}{!r.is_active && <span className="muted small"> · kapalı</span>}</span>
              {edit && (
                <span className="lib-actions">
                  <button type="button" className="btn btn-small" disabled={toggle.isPending}
                          onClick={() => toggle.mutate({ id: r.id, is_active: !r.is_active })}>{r.is_active ? "Kapat" : "Aç"}</button>
                  <button type="button" className="icon-btn" aria-label={`${r.label} kuralını sil`} disabled={remove.isPending}
                          onClick={() => remove.mutate(r.id)}>×</button>
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      <ErrorNote error={toggle.error ?? remove.error} />
      {edit && (
        <form className="form rule-form" onSubmit={submit}>
          <h3 className="mini-head">Kural ekle</h3>
          <div className="form-row">
            <Field label="Kural tipi" hint={action.hint}>
              <select value={f.action} onChange={(e) => up("action", e.target.value as RuleForm["action"])}>
                {RULE_ACTIONS.map((a) => <option key={a.key} value={a.key}>{a.label}</option>)}
              </select>
            </Field>
            <Field label={f.action === "add" ? "Hangi ürünlerde / neye göre" : "Neye uygulanır"}>
              <select value={match} onChange={(e) => up("match", e.target.value as MatchKind)} disabled={kinds.length === 1}>
                {kinds.map((k) => <option key={k} value={k}>{k === "all" && f.action === "add" ? "Bütün ürünler" : MATCH_LABEL[k]}</option>)}
              </select>
            </Field>
            {match === "category" && (
              <Field label="Parça tipi">
                <select value={f.matchCategory} onChange={(e) => up("matchCategory", e.target.value)}>
                  <option value="">Seçin</option>
                  {categories.data?.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}
                </select>
              </Field>
            )}
            {match === "part" && (
              <Field label={f.action === "substitute" ? "Tasarımdaki kalem" : "Kalem"}>
                <select value={f.matchPart} onChange={(e) => up("matchPart", e.target.value)}>
                  <option value="">Seçin</option>
                  {partOptions}
                </select>
              </Field>
            )}
          </div>
          {f.action === "scrap" && (
            <div className="form-row">
              <Field label="Fire payı (%)"><input inputMode="decimal" value={f.pct} onChange={(e) => up("pct", e.target.value)} /></Field>
            </div>
          )}
          {(f.action === "substitute" || f.action === "add") && (
            <div className="form-row">
              <Field label={f.action === "add" ? "Eklenecek kalem" : "Üretimde kullanılan kalem"}>
                <select value={f.target} onChange={(e) => up("target", e.target.value)}>
                  <option value="">Seçin</option>
                  {partOptions}
                </select>
              </Field>
              <Field label={f.action === "add" ? `Miktar${target ? ` (${target.unit})` : ""}` : "Oran"}
                     hint={f.action === "substitute" ? "1 birim tasarım kalemi yerine kaç birim" : undefined}>
                <input inputMode="decimal" value={f.qty} onChange={(e) => up("qty", e.target.value)} />
              </Field>
              {f.action === "add" && (
                <Field label="Neye göre">
                  <select value={f.per} onChange={(e) => up("per", e.target.value as RuleForm["per"])}>
                    <option value="product">Ürün başına</option>
                    <option value="match" disabled={match === "all"}>Eşleşen her birim için</option>
                  </select>
                </Field>
              )}
            </div>
          )}
          {problem && <div className="error-note" role="alert"><strong>{problem}</strong></div>}
          <ErrorNote error={create.error} />
          <div className="actions"><button className="btn btn-primary" disabled={create.isPending}>Kural ekle</button></div>
        </form>
      )}
    </Modal>
  );
}

// ---------- Liste ----------
export function EbomPanel() {
  const { can } = useAuth();
  const edit = can("manager");
  const [params, setParams] = useSearchParams();
  const eboms = useEboms();
  const rules = useBomRules();
  const catalog = useCatalogParts();
  const { create, importFile } = useEbomActions();
  const [newPart, setNewPart] = useState("");
  const [result, setResult] = useState<ProductBomImportResult | null>(null);
  const [showRules, setShowRules] = useState(false);
  const [dlError, setDlError] = useState<unknown>(null);
  const input = useRef<HTMLInputElement>(null);

  const rows = eboms.data ?? [];
  const selected = params.get("ebom") ?? rows[0]?.id ?? "";
  const select = (id: string) => setParams(id ? { sekme: "ebom", ebom: id } : { sekme: "ebom" }, { replace: true });
  const taken = new Set(rows.map((r) => r.part_id));
  const active = (rules.data ?? []).filter((r) => r.is_active).length;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate({ part_id: newPart }, { onSuccess: (b) => { setNewPart(""); select(b.id); } });
  };
  const onFile = (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (f) importFile.mutate(f, { onSuccess: setResult });
  };

  return (
    <div className="prod">
      <Panel title="Mühendislik ağaçları" sub="Tasarımın ağacı (eBOM). Üretim ağacı bundan kurallarla türetilir"
             actions={<button type="button" className="btn btn-small" onClick={() => setShowRules(true)}>Kurallar ({num(active)})</button>}>
        {eboms.isLoading ? <Loading /> : eboms.error ? <ErrorNote error={eboms.error} /> : rows.length === 0 ? (
          <Empty>Henüz mühendislik ağacı yok.{edit ? " Aşağıdan bir ürün seçin ya da Excel'den içe aktarın." : ""}</Empty>
        ) : (
          <ul className="prod-list">
            {rows.map((b) => {
              const st = ebomState(b);
              return (
                <li key={b.id}>
                  <button type="button" aria-current={b.id === selected} onClick={() => select(b.id)}>
                    <span><strong>{b.name}</strong>
                      <span className="muted small">{[b.part_no, `${num(b.line_count)} bileşen`].filter(Boolean).join(" · ")}</span></span>
                    <span className={`chip ${st.tone}`}>{st.label}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
        {edit && (
          <>
            <form className="form" onSubmit={submit}>
              <h3 className="mini-head">Yeni mühendislik ağacı</h3>
              <Field label="Tasarlanan kalem" hint="Listede yoksa önce Kayıt › Katalog kalemi'nden ekleyin">
                <select value={newPart} onChange={(e) => setNewPart(e.target.value)} required>
                  <option value="">Seçin</option>
                  {catalog.data?.filter((p) => !taken.has(p.id)).map((p) => (
                    <option key={p.id} value={p.id}>{p.name}{p.part_no ? ` · ${p.part_no}` : ""}</option>
                  ))}
                </select>
              </Field>
              <ErrorNote error={create.error} />
              <div className="actions"><button className="btn btn-primary" disabled={!newPart || create.isPending}>Mühendislik ağacı aç</button></div>
            </form>
            <div className="form">
              <h3 className="mini-head">Excel'den içe aktar</h3>
              <div className="lib-actions">
                <button type="button" className="btn btn-small"
                        onClick={() => { setDlError(null); download("/production/boms/template", "sparetwin-urun-agaci.xlsx").catch(setDlError); }}>Şablonu indir</button>
                <button type="button" className="btn btn-small" onClick={() => input.current?.click()} disabled={importFile.isPending}>
                  {importFile.isPending ? "Yükleniyor…" : "Dosya seç ve içe aktar"}</button>
                <input ref={input} type="file" accept=".xlsx" hidden onChange={onFile} />
              </div>
              <p className="muted small">Ürün ağacı şablonuyla aynı sütunlar: Ürün parça no, Bileşen parça no, Miktar, Not. CAD / PLM çıktısı bu biçime getirilir.</p>
              <ErrorNote error={importFile.error ?? dlError} />
              {result && result.errors.length === 0 && (
                <div className="success-note" role="status">
                  {num(result.added)} satır eklendi{result.boms_created ? `, ${num(result.boms_created)} yeni mühendislik ağacı açıldı` : ""}
                  {result.existing ? `, ${num(result.existing)} satır zaten vardı` : ""}.
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
      </Panel>
      {selected && rows.some((r) => r.id === selected) && (
        <EbomDetail key={selected} id={selected} edit={edit} onDeleted={() => select("")}
                    onOpen={(partId) => { const t = rows.find((r) => r.part_id === partId); if (t) select(t.id); }} />
      )}
      {showRules && <RulesModal edit={edit} onClose={() => setShowRules(false)} />}
    </div>
  );
}

// ---------- Ayrıntı ----------
const STATUS: Record<MbomLine["status"], { label: string; tone: string }> = {
  new: { label: "yeni", tone: "t-watch" }, changed: { label: "değişecek", tone: "t-watch" }, same: { label: "aynı", tone: "chip-plain" },
};

function EbomDetail({ id, edit, onDeleted, onOpen }: { id: string; edit: boolean; onDeleted: () => void; onOpen: (partId: string) => void }) {
  const ebom = useEbom(id);
  const catalog = useCatalogParts();
  const { addLine, removeLine, remove, apply } = useEbomActions();
  const [partId, setPartId] = useState("");
  const [amount, setAmount] = useState("1");
  const [confirm, setConfirm] = useState(false);

  if (ebom.isLoading) return <Panel><Loading /></Panel>;
  if (ebom.error || !ebom.data) return <Panel><ErrorNote error={ebom.error} /></Panel>;
  const b = ebom.data;
  const m = b.mbom;
  const part = catalog.data?.find((p) => p.id === partId);
  const direct = new Set(b.lines.map((l) => l.part_id));
  const n = Number(amount.replace(",", "."));
  const submit = (e: FormEvent) => {
    e.preventDefault();
    addLine.mutate({ ebomId: id, part_id: partId, qty: n }, { onSuccess: () => { setPartId(""); setAmount("1"); } });
  };

  return (
    <Panel title={b.name ?? "Mühendislik ağacı"} sub={b.part_no ?? undefined}
           actions={edit ? <button type="button" className="btn btn-small" onClick={() => setConfirm(true)}>Ağacı sil</button> : undefined}>
      <h3 className="mini-head">Mühendislik ağacı (eBOM)</h3>
      {b.lines.length === 0 ? <Empty>Ağaç boş.{edit ? " Aşağıdan bileşen ekleyin." : ""}</Empty> : (
        <div className="table-wrap">
          <table className="table lib-table">
            <thead><tr><th>Bileşen</th><th>Tür</th><th className="num">Miktar</th><th /></tr></thead>
            <tbody>
              {b.lines.map((l) => (
                <tr key={l.line_id}>
                  <td><strong>{l.name}</strong>
                    <div className="muted small">
                      {[l.part_no, l.notes].filter(Boolean).join(" · ")}
                      {l.has_ebom && <> {l.part_no || l.notes ? "· " : ""}<button type="button" className="link-btn" onClick={() => onOpen(l.part_id)}>alt montaj</button></>}
                    </div></td>
                  <td>{l.category_code ? categoryLabel(l.category_code) : "–"}</td>
                  <td className="num">{qty(l.qty, l.unit)}</td>
                  <td className="row-actions">{edit && (
                    <button type="button" className="icon-btn" aria-label={`${l.name} satırını sil`} disabled={removeLine.isPending}
                            onClick={() => removeLine.mutate({ ebomId: id, lineId: l.line_id })}>×</button>)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <ErrorNote error={removeLine.error} />
      {edit && (
        <form className="form" onSubmit={submit}>
          <div className="form-row">
            <Field label="Bileşen ekle">
              <select value={partId} onChange={(e) => setPartId(e.target.value)} required>
                <option value="">Seçin</option>
                {catalog.data?.filter((p) => p.id !== b.part_id && !direct.has(p.id)).map((p) => (
                  <option key={p.id} value={p.id}>{p.category_name} · {p.name}{p.part_no ? ` · ${p.part_no}` : ""}</option>
                ))}
              </select>
            </Field>
            <Field label={`Miktar${part ? ` (${part.unit})` : ""}`}>
              <input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
            </Field>
          </div>
          <ErrorNote error={addLine.error} />
          <div className="actions"><button className="btn" disabled={!partId || !(n > 0) || addLine.isPending}>Bileşen ekle</button></div>
        </form>
      )}

      <div className="row-between sup-section">
        <h3 className="mini-head">Üretim ağacı önizlemesi (mBOM)</h3>
        <span className={`chip ${m.in_sync ? "t-ok" : "t-watch"}`}>
          {m.in_sync ? "üretim ağacı güncel" : m.mbom_id ? "üretim ağacından farklı" : "henüz üretim ağacı yok"}
        </span>
      </div>
      <p className="muted small">Kurallar uygulanınca 1 {b.unit ?? "adet"} ürün için çıkan ağaç. “Üretim ağacına yaz” deyince emirlerin ve üretilebilirliğin baktığı ürün ağacı bununla değişir.</p>
      {m.lines.length === 0 ? <Empty>Dönüşümün sonucu boş.</Empty> : (
        <div className="table-wrap">
          <table className="table lib-table mbom-table">
            <thead><tr><th>Bileşen</th><th className="num">eBOM</th><th className="num">mBOM</th><th>Uygulanan kural</th><th>Üretim ağacında</th></tr></thead>
            <tbody>
              {m.lines.map((l) => (
                <tr key={l.part_id}>
                  <td><strong>{l.name}</strong>
                    <div className="muted small">{[l.part_no, l.from_name && `${l.from_name} yerine`, l.ebom_qty == null && "kuralla eklendi"].filter(Boolean).join(" · ")}</div></td>
                  <td className="num">{qty(l.ebom_qty, l.unit)}</td>
                  <td className="num"><strong>{qty(l.qty, l.unit)}</strong></td>
                  <td className="small">{l.rules.length ? l.rules.map((r) => <div key={r}>{r}</div>) : <span className="muted">–</span>}</td>
                  <td><span className={`chip ${STATUS[l.status].tone}`}>{STATUS[l.status].label}</span>
                    {l.status === "changed" && <div className="muted small">şimdi {qty(l.current_qty, l.unit)}</div>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {m.removed.length > 0 && (
        <p className="small"><strong>Üretim ağacına girmeyenler:</strong> {m.removed.map((r) => `${r.name} (${r.rule})`).join("; ")}</p>
      )}
      {m.dropped.length > 0 && (
        <p className="small t-watch"><strong>Üretim ağacından silinecek:</strong> {m.dropped.map((r) => `${r.name} ${qty(r.qty, r.unit)}`).join("; ")}</p>
      )}
      <ErrorNote error={apply.error} />
      <div className="actions">
        {edit && <button type="button" className="btn btn-primary" disabled={m.in_sync || m.lines.length === 0 || apply.isPending}
                         onClick={() => apply.mutate(id)}>{m.in_sync ? "Üretim ağacı güncel" : "Üretim ağacına yaz"}</button>}
        {m.mbom_id && <Link className="btn" to={`/uretim?agac=${m.mbom_id}`}>Ürün ağacını aç</Link>}
      </div>
      {confirm && (
        <Modal title="Mühendislik ağacı silinsin mi?" onClose={() => setConfirm(false)}
               footer={<>
                 <button type="button" className="btn" onClick={() => setConfirm(false)}>Vazgeç</button>
                 <button type="button" className="btn btn-primary" disabled={remove.isPending}
                         onClick={() => remove.mutate(id, { onSuccess: onDeleted })}>Sil</button>
               </>}>
          <p>{b.name} mühendislik ağacı ve {num(b.lines.length)} satırı silinir. Üretim ağacı, katalog ve stok etkilenmez.</p>
          <ErrorNote error={remove.error} />
        </Modal>
      )}
    </Panel>
  );
}
