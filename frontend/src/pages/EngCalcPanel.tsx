// Mühendislik hesap araçları: sac büküm açınımı ve hidrolik silindir kuvveti / debisi.
// Hesap tarayıcıda yapılır, hiçbir şey kaydedilmez; sonuç ön kontrol içindir.
import { useState } from "react";
import { Field, Panel } from "../components/ui";
import { bend, cylinder } from "../lib/engcalc";

const n = (v: string) => (v.trim() === "" ? NaN : Number(v.replace(",", ".")));
const f = (v: number, digits = 2) => new Intl.NumberFormat("tr-TR", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(v);

function Warnings({ items }: { items: string[] }) {
  if (items.length === 0) return null;
  return <ul className="calc-warn">{items.map((w) => <li key={w}>{w}</li>)}</ul>;
}

function Fact({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return <div className="fact"><dt>{label}</dt><dd>{value}{sub && <span className="muted small"> {sub}</span>}</dd></div>;
}

function BendCalc() {
  const [v, setV] = useState({ thickness: "2", radius: "2", angle: "90", k: "", a: "50", b: "30" });
  const up = (key: keyof typeof v) => (e: { target: { value: string } }) => setV({ ...v, [key]: e.target.value });
  const r = bend({ thickness: n(v.thickness), radius: n(v.radius), angle: n(v.angle), kFactor: v.k.trim() === "" ? null : n(v.k), flangeA: n(v.a), flangeB: n(v.b) });
  return (
    <Panel title="Sac büküm açınımı" sub="Büküm payı, büküm kesintisi ve tek bükümlü parçanın açınım boyu">
      <div className="form">
        <div className="form-row">
          <Field label="Sac kalınlığı (mm)"><input inputMode="decimal" value={v.thickness} onChange={up("thickness")} /></Field>
          <Field label="İç yarıçap (mm)"><input inputMode="decimal" value={v.radius} onChange={up("radius")} /></Field>
          <Field label="Büküm açısı (°)"><input inputMode="decimal" value={v.angle} onChange={up("angle")} /></Field>
        </div>
        <div className="form-row">
          <Field label="Kenar A (mm)" hint="Dıştan dışa"><input inputMode="decimal" value={v.a} onChange={up("a")} /></Field>
          <Field label="Kenar B (mm)" hint="Dıştan dışa"><input inputMode="decimal" value={v.b} onChange={up("b")} /></Field>
          <Field label="K katsayısı" hint="Boşsa R/T oranından önerilir"><input inputMode="decimal" value={v.k} onChange={up("k")} placeholder="0,33 – 0,5" /></Field>
        </div>
      </div>
      {"error" in r ? <p className="muted">{r.error}.</p> : (
        <>
          <dl className="facts calc-facts">
            <Fact label="Açınım boyu" value={`${f(r.flat)} mm`} />
            <Fact label="Büküm payı" value={`${f(r.allowance)} mm`} />
            <Fact label="Büküm kesintisi" value={`${f(r.deduction)} mm`} />
          </dl>
          <p className="muted small">
            K = {f(r.kFactor)}{r.kSuggested ? " (önerilen)" : ""} · dış pay {f(r.setback)} mm · açınım = A + B − kesinti.
            Büküm payı = açı × (R + K × T).
          </p>
          <Warnings items={r.warnings} />
        </>
      )}
    </Panel>
  );
}

function CylinderCalc() {
  const [v, setV] = useState({ bore: "100", rod: "56", pressure: "200", stroke: "500", seconds: "10" });
  const up = (key: keyof typeof v) => (e: { target: { value: string } }) => setV({ ...v, [key]: e.target.value });
  const r = cylinder({ bore: n(v.bore), rod: n(v.rod), pressure: n(v.pressure), stroke: n(v.stroke), extendSeconds: n(v.seconds) });
  return (
    <Panel title="Hidrolik silindir" sub="İtme / çekme kuvveti ve istenen süre için gereken debi">
      <div className="form">
        <div className="form-row">
          <Field label="Piston çapı (mm)"><input inputMode="decimal" value={v.bore} onChange={up("bore")} /></Field>
          <Field label="Mil çapı (mm)"><input inputMode="decimal" value={v.rod} onChange={up("rod")} /></Field>
          <Field label="Basınç (bar)"><input inputMode="decimal" value={v.pressure} onChange={up("pressure")} /></Field>
        </div>
        <div className="form-row">
          <Field label="Strok (mm)"><input inputMode="decimal" value={v.stroke} onChange={up("stroke")} /></Field>
          <Field label="Açılma süresi (s)" hint="Tam strok için istenen süre"><input inputMode="decimal" value={v.seconds} onChange={up("seconds")} /></Field>
        </div>
      </div>
      {"error" in r ? <p className="muted">{r.error}.</p> : (
        <>
          <dl className="facts calc-facts">
            <Fact label="İtme kuvveti" value={`${f(r.pushKn, 1)} kN`} sub={`≈ ${f(r.pushTon, 1)} ton`} />
            <Fact label="Çekme kuvveti" value={`${f(r.pullKn, 1)} kN`} sub={`≈ ${f(r.pullTon, 1)} ton`} />
            <Fact label="Gereken debi" value={`${f(r.flowLpm, 1)} L/dk`} />
          </dl>
          <p className="muted small">
            Piston alanı {f(r.pistonArea)} cm² · halka alanı {f(r.annulusArea)} cm² · açılma hızı {f(r.extendSpeed, 0)} mm/s ·
            aynı debiyle kapanma {f(r.retractSeconds, 1)} s ({f(r.retractSpeed, 0)} mm/s) · strok hacmi {f(r.strokeLitres)} L.
          </p>
          <Warnings items={r.warnings} />
        </>
      )}
    </Panel>
  );
}

export function EngCalcPanel() {
  return (
    <div className="stack">
      <div className="calc-note" role="note">
        <strong>Ön kontrol içindir.</strong> Verim, sürtünme, geri yaylanma, burkulma ve emniyet katsayısı hesaba katılmaz;
        imalat ve tasarım kararı için mühendis onayı gerekir. Girilen değerler kaydedilmez.
      </div>
      <div className="calc-grid"><BendCalc /><CylinderCalc /></div>
    </div>
  );
}
