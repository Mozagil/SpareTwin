// Üretilebilirlik: eldeki stokla kaç birim çıkar, istenen miktar için hangi kalem ne kadar eksik; eksikler satınalma talebine dönüşür.
import { useState } from "react";
import { Link } from "react-router";
import { useBuildable, usePurchaseActions } from "../api/hooks";
import { useAuth } from "../auth/AuthProvider";
import { ErrorNote, Field, Loading } from "../components/ui";
import { num, num1 } from "../lib/format";

const qty = (v: number | string, unit: string | null) => `${Number.isInteger(Number(v)) ? num(Number(v)) : num1(Number(v))} ${unit ?? ""}`.trim();

export function BuildablePanel({ bomId, name, unit }: { bomId: string; name: string | null; unit: string | null }) {
  const { can } = useAuth();
  const [amount, setAmount] = useState("1");
  const n = Number(amount.replace(",", "."));
  const valid = n > 0 && n <= 1_000_000;
  const data = useBuildable(bomId, valid ? n : 1);
  const { createOrder } = usePurchaseActions();
  const b = data.data;
  const short = b?.lines.filter((l) => Number(l.shortage) > 0) ?? [];
  const toBuy = short.filter((l) => Number(l.to_buy) > 0);
  const fromStock = b?.lines.filter((l) => Number(l.shortage) === 0) ?? [];

  const request = () => createOrder.mutate({
    supplier_id: null, site_id: null, expected_at: null, notes: `${qty(n, unit)} ${name ?? "ürün"} üretimi için eksikler`,
    lines: toBuy.map((l) => ({ part_id: l.part_id, qty: Number(l.to_buy), unit_cost: null, asset_id: null, notes: null })),
  });

  return (
    <div className="form">
      <h3 className="mini-head">Üretilebilirlik</h3>
      {data.isLoading && !b ? <Loading /> : data.error ? <ErrorNote error={data.error} /> : b && (
        <>
          <div className="build-head">
            <p className={b.can_build > 0 ? "build-can t-ok" : "build-can t-watch"}>
              {b.can_build > 0 ? <>Eldeki stokla <strong>{qty(b.can_build, unit)}</strong> üretilebilir.</> : <>Eldeki stokla üretilemiyor.</>}
            </p>
            <Field label={`Kaç ${unit ?? "adet"} üretilecek?`}>
              <input inputMode="decimal" value={amount} onChange={(e) => { setAmount(e.target.value); createOrder.reset(); }} />
            </Field>
          </div>
          {!valid ? null : short.length === 0 ? (
            <p className="success-note" role="status">{qty(n, unit)} için stok yeterli; eksik kalem yok.</p>
          ) : (
            <>
              <div className="table-wrap">
                <table className="table lib-table">
                  <thead><tr><th>Eksik kalem</th><th className="num">Gerekli</th><th className="num">Stokta</th><th className="num">Eksik</th>
                    <th className="num">Siparişte</th><th className="num">Alınacak</th></tr></thead>
                  <tbody>
                    {short.map((l) => (
                      <tr key={l.part_id}>
                        <td><strong>{l.name}</strong><div className="muted small">{l.part_no}</div></td>
                        <td className="num">{qty(l.required, l.unit)}</td>
                        <td className="num">{Number(l.in_stock) > 0 ? qty(l.in_stock, l.unit) : <span className="muted">yok</span>}</td>
                        <td className="num t-watch">{qty(l.shortage, l.unit)}</td>
                        <td className="num">{Number(l.on_order) > 0 ? qty(l.on_order, l.unit) : <span className="muted">–</span>}</td>
                        <td className="num">{Number(l.to_buy) > 0 ? <strong>{qty(l.to_buy, l.unit)}</strong> : <span className="t-ok">yolda</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="muted small">
                {qty(n, unit)} için {num(short.length)} kalem eksik{fromStock.length ? `, ${num(fromStock.length)} kalem stoktan karşılanıyor` : ""}.
                Stokta hazır alt montaj varsa önce o kullanılır; kalanı bileşenlerinden hesaplanır.
              </p>
              <ErrorNote error={createOrder.error} />
              {createOrder.data ? (
                <p className="success-note" role="status">
                  Satınalma talebi açıldı: <Link to={`/satinalma?sekme=siparisler&siparis=${createOrder.data.id}`}>{createOrder.data.number}</Link>
                </p>
              ) : can("technician") && toBuy.length > 0 && (
                <div className="actions">
                  <button type="button" className="btn btn-small" disabled={createOrder.isPending} onClick={request}>
                    {num(toBuy.length)} eksik kalem için satınalma talebi aç</button>
                </div>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}
