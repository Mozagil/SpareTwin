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
  CategoryDef,
  Costs,
  Downtime,
  DowntimeCategory,
  MaintenancePlan,
  MaintenanceRecord,
  PoStatus,
  TemplateDef,
  TenantSettings,
  PoSummary,
  PurchaseOrder,
  StockMovement,
  Suggestion,
  Supplier,
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

// ---------- Satınalma ----------
export const useSuppliers = () => useQuery({ queryKey: ["suppliers"], queryFn: () => api<Supplier[]>("/suppliers") });
export const useSuggestions = () =>
  useQuery({ queryKey: ["po", "suggestions"], queryFn: () => api<Suggestion[]>("/purchasing/suggestions") });
export const useOrders = (status?: PoStatus) =>
  useQuery({ queryKey: ["po", "list", status ?? "all"], queryFn: () => api<PoSummary[]>("/purchase-orders", { query: { status } }) });
export const useOrder = (id: string | undefined) =>
  useQuery({ queryKey: ["po", "one", id], queryFn: () => api<PurchaseOrder>(`/purchase-orders/${id}`), enabled: !!id });

export function usePurchasing() {
  const qc = useQueryClient();
  const refresh = () => Promise.all(["po", "stock", "parts", "catalog-parts", "notifications", "suppliers"].map((k) => qc.invalidateQueries({ queryKey: [k] })));
  // Dönüş tipini koruyan yardımcı (talep oluştur → {id, number}, teslim al → {status, part_ids})
  const m = <T, R>(fn: (v: T) => Promise<R>) => useMutation<R, Error, T>({ mutationFn: fn, onSuccess: refresh });
  return {
    create: m((b: { supplier_id: string | null; notes?: string | null; lines: { part_id: string; qty: number; unit_cost?: number | null }[] }) =>
      api<{ id: string; number: string }>("/purchase-orders", { method: "POST", body: b })),
    patch: m((v: { id: string; supplier_id?: string | null; expected_date?: string | null; notes?: string | null }) => {
      const { id, ...body } = v;
      return api(`/purchase-orders/${id}`, { method: "PATCH", body });
    }),
    addLine: m((v: { id: string; part_id: string; qty: number; unit_cost?: number | null }) => {
      const { id, ...body } = v;
      return api(`/purchase-orders/${id}/lines`, { method: "POST", body });
    }),
    patchLine: m((v: { id: string; line: string; qty?: number; unit_cost?: number | null }) => {
      const { id, line, ...body } = v;
      return api(`/purchase-orders/${id}/lines/${line}`, { method: "PATCH", body });
    }),
    deleteLine: m((v: { id: string; line: string }) => api(`/purchase-orders/${v.id}/lines/${v.line}`, { method: "DELETE" })),
    place: m((v: { id: string; expected_date?: string | null }) =>
      api(`/purchase-orders/${v.id}/order`, { method: "POST", body: { expected_date: v.expected_date || null } })),
    cancel: m((id: string) => api(`/purchase-orders/${id}/cancel`, { method: "POST" })),
    receive: m((v: { id: string; site_id: string | null; ref?: string | null; lines: { line_id: string; qty: number; serials: string[] }[] }) => {
      const { id, ...body } = v;
      return api<{ status: string; part_ids: string[] }>(`/purchase-orders/${id}/receive`, { method: "POST", body });
    }),
    createSupplier: m((b: { name: string; contact?: string | null; phone?: string | null; email?: string | null }) =>
      api<Supplier>("/suppliers", { method: "POST", body: b })),
  };
}

// ---------- Bakım ve duruş ----------
export const usePlans = (assetId?: string) =>
  useQuery({ queryKey: ["ops", "plans", assetId ?? "all"], queryFn: () => api<MaintenancePlan[]>("/maintenance/plans", { query: { asset_id: assetId } }) });
export const useRecords = (assetId?: string) =>
  useQuery({ queryKey: ["ops", "records", assetId ?? "all"], queryFn: () => api<MaintenanceRecord[]>("/maintenance/records", { query: { asset_id: assetId } }) });
export const useDowntime = (assetId?: string) =>
  useQuery({ queryKey: ["ops", "downtime", assetId ?? "all"], queryFn: () => api<Downtime[]>("/downtime", { query: { asset_id: assetId } }) });

export function useOps() {
  const qc = useQueryClient();
  const refresh = () => Promise.all(["ops", "assets", "asset", "stock", "notifications", "costs"].map((k) => qc.invalidateQueries({ queryKey: [k] })));
  const m = <T, R>(fn: (v: T) => Promise<R>) => useMutation<R, Error, T>({ mutationFn: fn, onSuccess: refresh });
  return {
    createPlan: m((b: { asset_id: string; name: string; interval_hours: number | null; interval_days: number | null;
                         last_done_hours?: number | null; materials: { part_id: string; qty: number }[]; notes?: string | null }) =>
      api("/maintenance/plans", { method: "POST", body: b })),
    complete: m((v: { id: string; asset_hours?: number | null; labor_cost?: number | null; notes?: string | null;
                      site_id?: string | null; consume_materials: boolean }) => {
      const { id, ...body } = v;
      return api(`/maintenance/plans/${id}/complete`, { method: "POST", body });
    }),
    setActive: m((v: { id: string; active: boolean }) => api(`/maintenance/plans/${v.id}`, { method: "PATCH", body: { active: v.active } })),
    startDowntime: m((b: { asset_id: string; category: DowntimeCategory; description?: string | null }) =>
      api("/downtime", { method: "POST", body: b })),
    endDowntime: m((v: { id: string; cost?: number | null }) => api(`/downtime/${v.id}/end`, { method: "POST", body: { cost: v.cost ?? null } })),
  };
}

// ---------- Maliyet ----------
export const useCosts = (days: number) =>
  useQuery({ queryKey: ["costs", days], queryFn: () => api<Costs>("/costs/assets", { query: { days } }) });

// ---------- Ayarlar ----------
export const useTenantSettings = () =>
  useQuery({ queryKey: ["settings"], queryFn: () => api<TenantSettings>("/settings"), staleTime: 5 * 60_000 });

/** Firmanın açık modülleri. Yüklenene kadar hepsi açık sayılır (menü titremesin). */
export function useModules() {
  const s = useTenantSettings();
  return s.data?.modules ?? { tireiq: true, parts: true, erp: false };
}
export const useCategoryDefs = () => useQuery({ queryKey: ["settings", "categories"], queryFn: () => api<CategoryDef[]>("/settings/categories") });
export const useTemplateDefs = () => useQuery({ queryKey: ["settings", "templates"], queryFn: () => api<TemplateDef[]>("/settings/templates") });

export function useSettingsActions() {
  const qc = useQueryClient();
  const refresh = () => Promise.all(["settings", "categories", "templates", "notifications", "po"].map((k) => qc.invalidateQueries({ queryKey: [k] })));
  const m = <T, R>(fn: (v: T) => Promise<R>) => useMutation<R, Error, T>({ mutationFn: fn, onSuccess: refresh });
  return {
    save: m((b: { inspection_interval_days: number; purchase_horizon_hours: number; modules: { tireiq: boolean; parts: boolean } }) =>
      api("/settings", { method: "PUT", body: b })),
    addCategory: m((b: { code: string; name: string; is_serialized: boolean; measurement_profile: object[]; required_photo_angles: string[] }) =>
      api("/settings/categories", { method: "POST", body: b })),
    copyTemplate: m((b: { name: string; copy_from: string }) => api("/settings/templates", { method: "POST", body: b })),
    addPosition: m((v: { id: string; code: string; label: string; category_code: string; axle: number | null }) => {
      const { id, ...body } = v;
      return api(`/settings/templates/${id}/positions`, { method: "POST", body });
    }),
    deletePosition: m((v: { id: string; code: string }) => api(`/settings/templates/${v.id}/positions/${encodeURIComponent(v.code)}`, { method: "DELETE" })),
  };
}
