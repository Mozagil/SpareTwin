// Makinenin üstten görünüş şeması. Pozisyonların x/y değerleri (0–100)
// veritabanındaki şablondan gelir; gövde çizimi makine tipine (layout) göre.
import type { KeyboardEvent } from "react";
import type { Layout, Position } from "../api/types";
import { BAND_LABEL, pct } from "../lib/format";

const X = (v: number) => 40 + v * 5.6;
const Y = (v: number) => 20 + v * 3.2;

function Body({ layout }: { layout: Layout | null }) {
  const s = { fill: "var(--body)", stroke: "var(--body-edge)", strokeWidth: 2 };
  const cab = { fill: "var(--surface)", stroke: "var(--body-edge)", strokeWidth: 2 };
  if (layout === "loader")
    return (
      <g>
        <rect x={X(-4)} y={Y(14)} width={44} height={Y(86) - Y(14)} rx={6} {...s} />
        <rect x={X(12)} y={Y(38)} width={X(42) - X(12)} height={Y(62) - Y(38)} rx={10} {...s} />
        <circle cx={X(46)} cy={Y(50)} r={14} {...s} />
        <rect x={X(50)} y={Y(34)} width={X(96) - X(50)} height={Y(66) - Y(34)} rx={14} {...s} />
        <rect x={X(60)} y={Y(38)} width={X(72) - X(60)} height={Y(62) - Y(38)} rx={6} {...cab} />
        <text x={X(66)} y={Y(52)} textAnchor="middle" className="sch-label">kabin</text>
      </g>
    );
  if (layout === "reach_stacker")
    return (
      <g>
        <rect x={X(-4)} y={Y(8)} width={26} height={Y(92) - Y(8)} rx={4} {...s} />
        <rect x={X(14)} y={Y(38)} width={X(96) - X(14)} height={Y(62) - Y(38)} rx={12} {...s} />
        <rect x={X(0)} y={Y(46)} width={X(70) - X(0)} height={Y(54) - Y(46)} rx={4} fill="var(--body-edge)" />
        <rect x={X(48)} y={Y(64)} width={X(62) - X(48)} height={Y(84) - Y(64)} rx={6} {...cab} />
        <text x={X(55)} y={Y(76)} textAnchor="middle" className="sch-label">kabin</text>
      </g>
    );
  if (layout === "forklift")
    return (
      <g>
        <rect x={X(-6)} y={Y(30)} width={X(6) - X(-6)} height={5} fill="var(--body-edge)" />
        <rect x={X(-6)} y={Y(68)} width={X(6) - X(-6)} height={5} fill="var(--body-edge)" />
        <rect x={X(4)} y={Y(20)} width={16} height={Y(80) - Y(20)} rx={3} {...s} />
        <rect x={X(16)} y={Y(22)} width={X(94) - X(16)} height={Y(78) - Y(22)} rx={18} {...s} />
        <rect x={X(38)} y={Y(34)} width={X(52) - X(38)} height={Y(66) - Y(34)} rx={6} {...cab} />
        <text x={X(45)} y={Y(52)} textAnchor="middle" className="sch-label">kabin</text>
      </g>
    );
  return <rect x={X(8)} y={Y(20)} width={X(92) - X(8)} height={Y(80) - Y(20)} rx={16} {...s} />;
}

const bandColor = (b: Position["band"]) => (b === "empty" ? "var(--surface-2)" : `var(--${b})`);

function slotA11y(p: Position) {
  if (!p.part_item_id) return `${p.label}, boş pozisyon`;
  if (p.band === "unknown") return `${p.label}, ${p.serial_no ?? ""}, ölçüm bekliyor`;
  return `${p.label}, ${p.category_code === "tire" ? "kalan diş" : "kalan ömür"} ${pct(p.condition_pct)}, ${BAND_LABEL[p.band]}`;
}

interface Props {
  layout: Layout | null;
  positions: Position[];
  selected?: string | null;
  showAll: boolean;
  onSelect: (p: Position) => void;
}

export function MachineSchematic({ layout, positions, selected, showAll, onSelect }: Props) {
  const tireW = layout === "reach_stacker" ? 56 : 70;
  const tireH = layout === "reach_stacker" ? 34 : 50;
  const visible = positions.filter((p) => p.x != null && p.y != null && (showAll || p.category_code === "tire"));

  const keyPick = (p: Position) => (e: KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onSelect(p);
    }
  };

  return (
    <svg className="schematic" viewBox="0 0 640 360" role="group" aria-label="Makine üstten görünüş şeması">
      <text x={X(-4)} y={18} className="sch-label">ön</text>
      <text x={X(96)} y={18} className="sch-label" textAnchor="end">arka</text>
      <Body layout={layout} />
      {visible
        .filter((p) => p.category_code === "tire")
        .map((p) => {
          const cx = X(p.x!), cy = Y(p.y!), x = cx - tireW / 2, y = cy - tireH / 2;
          const fill = p.condition_pct != null ? (tireH * Math.min(p.condition_pct, 100)) / 100 : 0;
          const top = p.y! < 50;
          const empty = !p.part_item_id;
          return (
            <g key={p.code} className="slot" tabIndex={0} role="button" aria-pressed={selected === p.code}
               aria-label={slotA11y(p)} onClick={() => onSelect(p)} onKeyDown={keyPick(p)}>
              <rect className="halo" x={x - 6} y={y - 6} width={tireW + 12} height={tireH + 12} rx={12} />
              {empty ? (
                <rect x={x} y={y} width={tireW} height={tireH} rx={8} fill="none"
                      stroke="var(--muted)" strokeWidth={2} strokeDasharray="5 4" />
              ) : (
                <>
                  <rect x={x} y={y} width={tireW} height={tireH} rx={8} fill="var(--rubber)" />
                  {Array.from({ length: 7 }, (_, i) => {
                    const gx = x + 6 + (i * (tireW - 12)) / 6;
                    return <line key={i} x1={gx} y1={y + 3} x2={gx} y2={y + tireH - 3} stroke="var(--rubber-groove)" strokeWidth={2} />;
                  })}
                  {p.band === "unknown" ? (
                    <rect x={x} y={y} width={tireW} height={tireH} rx={8} fill="var(--unknown)" opacity={0.35} />
                  ) : (
                    <rect x={x} y={y + tireH - fill} width={tireW} height={fill} rx={8} fill={bandColor(p.band)} opacity={0.82} />
                  )}
                </>
              )}
              <text x={cx} y={top ? y - 10 : y + tireH + 20} textAnchor="middle">
                <tspan className="sch-label">{p.code} </tspan>
                <tspan className="sch-val" fill={empty ? "var(--muted)" : bandColor(p.band)}>
                  {empty ? "boş" : p.band === "unknown" ? "ölçüm yok" : pct(p.condition_pct)}
                </tspan>
              </text>
            </g>
          );
        })}
      {visible
        .filter((p) => p.category_code !== "tire")
        .map((p) => {
          const cx = X(p.x!), cy = Y(p.y!), r = 13;
          const c = bandColor(p.band);
          const empty = !p.part_item_id;
          const shapeProps = empty
            ? { fill: "none", stroke: "var(--muted)", strokeWidth: 2, strokeDasharray: "4 3" }
            : { fill: c };
          return (
            <g key={p.code} className="slot" tabIndex={0} role="button" aria-pressed={selected === p.code}
               aria-label={slotA11y(p)} onClick={() => onSelect(p)} onKeyDown={keyPick(p)}>
              <circle className="halo" cx={cx} cy={cy} r={r + 7} />
              {p.category_code === "hyd_pump" ? (
                <rect x={cx - r} y={cy - r} width={2 * r} height={2 * r} rx={4} {...shapeProps} />
              ) : p.category_code === "battery" ? (
                <rect x={cx - r - 4} y={cy - r + 3} width={2 * r + 8} height={2 * r - 6} rx={3} {...shapeProps} />
              ) : (
                <circle cx={cx} cy={cy} r={r} {...shapeProps} />
              )}
              {!empty && <circle cx={cx} cy={cy} r={4} fill="var(--surface)" />}
            </g>
          );
        })}
    </svg>
  );
}
