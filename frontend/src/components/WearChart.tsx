import type { Band, Wear } from "../api/types";
import { num } from "../lib/format";

/** Diş derinliği – parça saati grafiği; kesikli çizgi doğrusal tahmin. */
export function WearChart({ wear, band }: { wear: Wear; band: Band }) {
  const W = 460, H = 170, pad = { l: 34, r: 14, t: 12, b: 26 };
  const xMax = Math.max(wear.projection?.to_hours ?? wear.hours_total, wear.hours_total, 1);
  const yMax = wear.otd_mm;
  const sx = (v: number) => pad.l + (v / xMax) * (W - pad.l - pad.r);
  const sy = (v: number) => pad.t + (1 - v / yMax) * (H - pad.t - pad.b);
  const pts = wear.points;
  const path = pts.map((p, i) => `${i ? "L" : "M"}${sx(p.part_hours).toFixed(1)},${sy(p.tread_mm).toFixed(1)}`).join(" ");
  const last = pts[pts.length - 1];
  const color = `var(--${band === "empty" ? "unknown" : band})`;
  return (
    <svg className="wear" viewBox={`0 0 ${W} ${H}`} role="img"
         aria-label={`Diş derinliği ${num(wear.otd_mm)} mm'den ${last ? num(last.tread_mm) : "?"} mm'ye düştü`}>
      <line x1={pad.l} x2={W - pad.r} y1={sy(wear.scrap_tread_mm)} y2={sy(wear.scrap_tread_mm)}
            stroke="var(--critical)" strokeDasharray="3 4" />
      <text x={pad.l + 6} y={sy(wear.scrap_tread_mm) + 14}>hurda sınırı {num(wear.scrap_tread_mm)} mm</text>
      <line x1={pad.l} x2={pad.l} y1={pad.t} y2={H - pad.b} stroke="var(--line)" />
      <line x1={pad.l} x2={W - pad.r} y1={H - pad.b} y2={H - pad.b} stroke="var(--line)" />
      <text x={pad.l - 6} y={sy(wear.otd_mm) + 4} textAnchor="end">{num(wear.otd_mm)}</text>
      <text x={pad.l - 6} y={H - pad.b} textAnchor="end">0</text>
      <text x={pad.l} y={H - 6}>0 saat</text>
      <text x={W - pad.r} y={H - 6} textAnchor="end">{num(xMax)} saat</text>
      <path d={path} fill="none" stroke="var(--ink)" strokeWidth={2.5} />
      {wear.projection && (
        <line x1={sx(wear.projection.from_hours)} y1={sy(wear.projection.from_mm)}
              x2={sx(wear.projection.to_hours)} y2={sy(wear.projection.to_mm)}
              stroke={color} strokeWidth={2.5} strokeDasharray="6 5" />
      )}
      {pts.map((p, i) => (
        <circle key={i} cx={sx(p.part_hours)} cy={sy(p.tread_mm)} r={4} fill="var(--surface)" stroke="var(--ink)" strokeWidth={2} />
      ))}
      {last && last.kind === "measured" && <circle cx={sx(last.part_hours)} cy={sy(last.tread_mm)} r={6} fill={color} />}
    </svg>
  );
}
