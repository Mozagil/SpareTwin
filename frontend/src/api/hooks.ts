import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type {
  AssetDetail,
  AssetModel,
  AssetSummary,
  CatalogPart,
  Category,
  InspectionSummary,
  Notification,
  QcFlag,
  RimRow,
  StockMovement,
  StockRow,
  Sheet,
  PartDetail,
  PartEvent,
  PartListItem,
  Site,
  Template,
  TireCost,
  Wear,
} from "./types";

// ---------- Okuma ----------
export const useAssets = () => useQuery({ queryKey: ["assets"], queryFn: () => api<AssetSummary[]>("/assets") });

export const useAsset = (id: string | undefined) =>
  useQuery({ queryKey: ["asset", id], queryFn: () => api<AssetDetail>(`/assets/${id}`), enabled: !!id });

export interface PartFilters {
  status?: string;
  category?: string;
  band?: string;
  q?: string;
  asset_id?: string;
  limit?: number;
}
export const useParts = (f: PartFilters) =>
  useQuery({ queryKey: ["parts", f], queryFn: () => api<PartListItem[]>("/parts", { query: { ...f } }) });

export const usePart = (id: string | undefined) =>
  useQuery({ queryKey: ["part", id], queryFn: () => api<PartDetail>(`/parts/${id}`), enabled: !!id });

export const usePartEvents = (id: string | undefined) =>
  useQuery({ queryKey: ["part", id, "events"], queryFn: () => api<PartEvent[]>(`/parts/${id}/events`), enabled: !!id });

export const useWear = (id: string | undefined, enabled = true) =>
  useQuery({
    queryKey: ["part", id, "wear"],
    queryFn: () => api<Wear>(`/parts/${id}/wear`),
    enabled: !!id && enabled,
    retry: false,
  });

export const useTireCost = () => useQuery({ queryKey: ["tire-cost"], queryFn: () => api<TireCost[]>("/reports/tire-cost") });
export const useSites = () => useQuery({ queryKey: ["sites"], queryFn: () => api<Site[]>("/sites") });
export const useTemplates = () => useQuery({ queryKey: ["templates"], queryFn: () => api<Template[]>("/catalog/templates") });
export const useAssetModels = () =>
  useQuery({ queryKey: ["asset-models"], queryFn: () => api<AssetModel[]>("/catalog/asset-models") });
export const useCatalogParts = (category?: string) =>
  useQuery({
    queryKey: ["catalog-parts", category ?? "all"],
    queryFn: () => api<CatalogPart[]>("/catalog/parts", { query: { category } }),
  });
export const useCategories = () =>
  useQuery({ queryKey: ["categories"], queryFn: () => api<Category[]>("/catalog/categories"), staleTime: 10 * 60_000 });

// ---------- Yazma ----------
/** Parça veya makine durumu değişince ilgili tüm görünümleri tazeler. */
function useInvalidateFleet() {
  const qc = useQueryClient();
  return () =>
    Promise.all(
      ["assets", "asset", "parts", "part", "tire-cost", "catalog-parts", "rims", "notifications", "stock"].map((k) =>
        qc.invalidateQueries({ queryKey: [k] }),
      ),
    );
}

export function useInstall() {
  const done = useInvalidateFleet();
  return useMutation({
    mutationFn: (v: { partId: string; asset_id: string; position: string; notes?: string; rim_id?: string | null }) =>
      api(`/parts/${v.partId}/install`, {
        method: "POST",
        body: { asset_id: v.asset_id, position: v.position, notes: v.notes || null, rim_id: v.rim_id || null },
      }),
    onSuccess: done,
  });
}

export function useRemove() {
  const done = useInvalidateFleet();
  return useMutation({
    mutationFn: (v: { partId: string; reason: string; next_status: string; cost?: number | null; notes?: string }) =>
      api(`/parts/${v.partId}/remove`, {
        method: "POST",
        body: { reason: v.reason, next_status: v.next_status, cost: v.cost ?? null, notes: v.notes || null },
      }),
    onSuccess: done,
  });
}

export function useMove() {
  const done = useInvalidateFleet();
  return useMutation({
    mutationFn: (v: { partId: string; position: string }) =>
      api<{ from: string; to: string; swapped_with: string | null }>(`/parts/${v.partId}/move`, { method: "POST", body: { position: v.position } }),
    onSuccess: done,
  });
}

export function useLogEvent() {
  const done = useInvalidateFleet();
  return useMutation({
    mutationFn: (v: { partId: string; event: string; reason?: string | null; cost?: number | null; notes?: string }) =>
      api(`/parts/${v.partId}/events`, {
        method: "POST",
        body: { event: v.event, reason: v.reason ?? null, cost: v.cost ?? null, notes: v.notes || null },
      }),
    onSuccess: done,
  });
}

export function useMeter() {
  const done = useInvalidateFleet();
  return useMutation({
    mutationFn: (v: { assetId: string; hours: number }) =>
      api(`/assets/${v.assetId}/meter`, { method: "POST", body: { hours: v.hours } }),
    onSuccess: done,
  });
}

export function useCreate<TBody, TOut = unknown>(path: string, invalidate: string[]) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: TBody) => api<TOut>(path, { method: "POST", body }),
    onSuccess: () => Promise.all(invalidate.map((k) => qc.invalidateQueries({ queryKey: [k] }))),
  });
}

/** Görsel yükle / kaldır. path örn. "/catalog/parts/{id}/image" */
export function useImage(path: string) {
  const qc = useQueryClient();
  const refresh = () =>
    Promise.all(["assets", "asset", "part", "catalog-parts", "asset-models"].map((k) => qc.invalidateQueries({ queryKey: [k] })));
  const upload = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return api(path, { method: "PUT", form });
    },
    onSuccess: refresh,
  });
  const remove = useMutation({ mutationFn: () => api(path, { method: "DELETE" }), onSuccess: refresh });
  return { upload, remove };
}

export function useLabels() {
  return useMutation({
    mutationFn: (body: { asset_ids: string[]; part_ids: string[]; skip: number }) =>
      api<{ url: string; count: number }>("/labels", { method: "POST", body }),
  });
}

export const resolveQr = (code: string) => api<{ type: "asset" | "part"; id: string }>(`/qr/${encodeURIComponent(code)}`);

// ---------- İnspeksiyon ----------
export const useDrafts = () =>
  useQuery({ queryKey: ["inspections", "draft"], queryFn: () => api<InspectionSummary[]>("/inspections", { query: { status: "draft" } }) });

export const useSheet = (id: string | undefined) =>
  useQuery({ queryKey: ["sheet", id], queryFn: () => api<Sheet>(`/inspections/${id}/sheet`), enabled: !!id });

export const startInspection = (assetId: string, assetHours: number) =>
  api<{ id: string }>("/inspections", { method: "POST", body: { asset_id: assetId, asset_hours: assetHours } });

export function useInspectionActions(id: string) {
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: ["sheet", id] });
  const refreshAll = () =>
    Promise.all(["sheet", "inspections", "assets", "asset", "part", "parts", "tire-cost"].map((k) => qc.invalidateQueries({ queryKey: [k] })));
  return {
    save: useMutation({
      mutationFn: (items: { part_item_id: string; metric: string; value: number; unit?: string | null }[]) =>
        api(`/inspections/${id}/measurements`, { method: "PUT", body: { items } }),
      onSuccess: refresh,
    }),
    photo: useMutation({
      mutationFn: (v: { part_item_id: string; angle: string; blob: Blob }) => {
        const form = new FormData();
        form.append("file", v.blob, `${v.angle}.jpg`);
        form.append("part_item_id", v.part_item_id);
        form.append("angle", v.angle);
        return api(`/inspections/${id}/photos`, { method: "POST", form });
      },
      onSuccess: refresh,
    }),
    hours: useMutation({
      mutationFn: (asset_hours: number) => api(`/inspections/${id}`, { method: "PATCH", body: { asset_hours } }),
      onSuccess: refresh,
    }),
    complete: useMutation({
      mutationFn: () => api<{ status: string; qc_flags: QcFlag[] }>(`/inspections/${id}/complete`, { method: "POST" }),
      onSuccess: refreshAll,
    }),
    cancel: useMutation({ mutationFn: () => api(`/inspections/${id}/cancel`, { method: "POST" }), onSuccess: refreshAll }),
  };
}

// ---------- Jantlar ve bildirimler ----------
export const useRims = () => useQuery({ queryKey: ["rims"], queryFn: () => api<RimRow[]>("/rims/compliance") });

export const useNotifications = () =>
  useQuery({
    queryKey: ["notifications"],
    queryFn: () => api<{ items: Notification[]; unread: number }>("/notifications"),
    refetchInterval: 60_000, // dakikada bir tazele
  });

export function useMarkRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { keys?: string[]; all?: boolean }) => api("/notifications/read", { method: "POST", body: v }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });
}

// ---------- Stok ----------
export const useStock = (f: { category?: string; below?: boolean; q?: string }) =>
  useQuery({ queryKey: ["stock", f], queryFn: () => api<StockRow[]>("/stock", { query: { ...f, below: f.below || undefined } }) });

export const useStockMovements = (partId: string | undefined) =>
  useQuery({ queryKey: ["stock", "movements", partId], queryFn: () => api<StockMovement[]>(`/stock/${partId}/movements`), enabled: !!partId });

export function useStockActions() {
  const qc = useQueryClient();
  const refresh = () => Promise.all(["stock", "catalog-parts", "notifications"].map((k) => qc.invalidateQueries({ queryKey: [k] })));
  return {
    move: useMutation({
      mutationFn: (b: { part_id: string; site_id: string | null; kind: "in" | "out" | "adjust"; qty: number;
                        unit_cost?: number | null; asset_id?: string | null; reason?: string | null; ref?: string | null; notes?: string | null }) =>
        api("/stock/movements", { method: "POST", body: b }),
      onSuccess: refresh,
    }),
    transfer: useMutation({
      mutationFn: (b: { part_id: string; from_site_id: string | null; to_site_id: string | null; qty: number; notes?: string | null }) =>
        api("/stock/transfer", { method: "POST", body: b }),
      onSuccess: refresh,
    }),
  };
}
