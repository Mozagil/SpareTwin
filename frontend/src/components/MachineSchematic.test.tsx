import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { Position } from "../api/types";
import { MachineSchematic } from "./MachineSchematic";

const pos = (o: Partial<Position>): Position => ({
  code: "A1-L", label: "Ön aks sol", category_code: "tire", axle: 1, x: 22, y: 30,
  part_item_id: "p1", part_name: "Lastik", serial_no: "S1", condition_pct: 64, band: "ok",
  projected_hours_left: 900, hours_total: 1500, ...o,
});

const positions = [
  pos({}),
  pos({ code: "A2-L", label: "Arka aks sol", x: 74, condition_pct: 12.8, band: "critical" }),
  pos({ code: "A1-R", label: "Ön aks sağ", y: 70, part_item_id: "p3", condition_pct: null, band: "unknown" }),
  pos({ code: "A2-R", label: "Arka aks sağ", x: 74, y: 70, part_item_id: null, serial_no: null, condition_pct: null, band: "empty" }),
  pos({ code: "MAIN-PUMP", label: "Ana pompa", category_code: "hyd_pump", x: 58, y: 50, condition_pct: 43, band: "ok" }),
];

describe("MachineSchematic", () => {
  it("lastik durumlarını erişilebilir etiketlerle gösterir", () => {
    render(<MachineSchematic layout="loader" positions={positions} showAll={false} onSelect={() => {}} />);
    expect(screen.getByRole("button", { name: /Arka aks sol, kalan diş %13, Kritik/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Ön aks sağ, S1, ölçüm bekliyor/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Arka aks sağ, boş pozisyon" })).toBeInTheDocument();
    // Lastik filtresi açıkken pompa görünmez
    expect(screen.queryByRole("button", { name: /Ana pompa/ })).not.toBeInTheDocument();
  });

  it("tüm parçalar modunda bileşenleri de gösterir ve seçimi bildirir", () => {
    const onSelect = vi.fn();
    render(<MachineSchematic layout="loader" positions={positions} showAll selected="A1-L" onSelect={onSelect} />);
    const pump = screen.getByRole("button", { name: /Ana pompa, kalan ömür %43/ });
    fireEvent.click(pump);
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ code: "MAIN-PUMP" }));
    fireEvent.keyDown(screen.getByRole("button", { name: /Arka aks sol/ }), { key: "Enter" });
    expect(onSelect).toHaveBeenLastCalledWith(expect.objectContaining({ code: "A2-L" }));
    expect(screen.getByRole("button", { name: /Ön aks sol/ })).toHaveAttribute("aria-pressed", "true");
  });
});
