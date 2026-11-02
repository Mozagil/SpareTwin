import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type {
  AssetDetail,
  AssetModel,
  AssetSummary,
  CatalogPart,
  Category,
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
      ["assets", "asset", "parts", "part", "tire-cost", "catalog-parts"].map((k) =>
        qc.invalidateQueries({ queryKey: [k] }),
      ),
    );
}

export function useInstall() {
  const done = useInvalidateFleet();
  return useMutation({
    mutationFn: (v: { partId: string; asset_id: string; position: string; notes?: string }) =>
      api(`/parts/${v.partId}/install`, {
        method: "POST",
        body: { asset_id: v.asset_id, position: v.position, notes: v.notes || null },
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

export function useLabels() {
  return useMutation({
    mutationFn: (body: { asset_ids: string[]; part_ids: string[]; skip: number }) =>
      api<{ url: string; count: number }>("/labels", { method: "POST", body }),
  });
}

export const resolveQr = (code: string) => api<{ type: "asset" | "part"; id: string }>(`/qr/${encodeURIComponent(code)}`);
