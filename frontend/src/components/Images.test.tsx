import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

const role = { current: "manager" };
vi.mock("../auth/AuthProvider", () => ({
  useAuth: () => ({
    can: (min: string) => {
      const order = ["viewer", "technician", "manager", "admin", "owner"];
      return order.indexOf(role.current) >= order.indexOf(min);
    },
  }),
}));

import { ImageBox, Lightbox, PhotoStrip } from "./Images";

const wrap = (ui: ReactNode) =>
  render(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>);

describe("ImageBox", () => {
  it("görsel yoksa yöneticiye 'Görsel ekle' gösterir", () => {
    role.current = "manager";
    wrap(<ImageBox image={null} uploadPath="/catalog/parts/x/image" alt="Lastik" />);
    expect(screen.getByRole("button", { name: /Görsel ekle/ })).toBeInTheDocument();
  });

  it("görsel yoksa teknisyene hiçbir şey göstermez", () => {
    role.current = "technician";
    const { container } = wrap(<ImageBox image={null} uploadPath="/catalog/parts/x/image" alt="Lastik" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("model görselinde 'Kaldır' yoktur (makinenin kendisine ait değil)", () => {
    role.current = "manager";
    wrap(<ImageBox image={{ id: "1", url: "/x.jpg", source: "model" }} uploadPath="/assets/a/image" alt="LD-07" />);
    expect(screen.getByRole("button", { name: "Değiştir" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Kaldır" })).not.toBeInTheDocument();
  });
});

describe("Lightbox", () => {
  const items = [
    { url: "/1.jpg", caption: "Taban" },
    { url: "/2.jpg", caption: "Yanak" },
    { url: "/3.jpg", caption: "Hasar" },
  ];
  it("ok tuşlarıyla gezilir, Escape ile kapanır", () => {
    const onClose = vi.fn();
    render(<Lightbox items={items} start={0} onClose={onClose} />);
    expect(screen.getByRole("dialog", { name: "Taban" })).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "ArrowRight" });
    expect(screen.getByRole("dialog", { name: "Yanak" })).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "ArrowLeft" });
    fireEvent.keyDown(window, { key: "ArrowLeft" });
    expect(screen.getByRole("dialog", { name: "Hasar" })).toBeInTheDocument(); // başa sarar
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});

describe("PhotoStrip", () => {
  it("fotoğraf yoksa görünmez; varsa açı etiketleriyle listeler", () => {
    const { container, rerender } = render(<PhotoStrip photos={[]} title="LD-07 A2-L" />);
    expect(container).toBeEmptyDOMElement();
    rerender(<PhotoStrip title="LD-07 A2-L" photos={[
      { id: "a", url: "/a.jpg", angle: "tread", created_at: "2026-11-01T10:00:00Z", inspection_id: null, asset_hours: 12480 },
      { id: "b", url: "/b.jpg", angle: "sidewall", created_at: "2026-11-01T10:01:00Z", inspection_id: null, asset_hours: null },
    ]} />);
    expect(screen.getByText("Saha fotoğrafları")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Yanak/ }));
    expect(screen.getByRole("dialog", { name: /LD-07 A2-L · Yanak/ })).toBeInTheDocument();
  });
});
