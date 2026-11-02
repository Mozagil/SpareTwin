// API yanıt tipleri. Kaynak: backend/sparetwin/api/*.py
// Sayısal kolonlar (numeric) JSON'da number olarak gelir.

export type Role = "owner" | "admin" | "manager" | "technician" | "viewer";
export type Band = "ok" | "watch" | "critical" | "unknown" | "empty";
export type PartStatus = "in_stock" | "installed" | "in_repair" | "refurbishing" | "quarantine" | "scrapped";
export type Layout = "loader" | "reach_stacker" | "forklift" | "generic";

export interface Membership {
  tenant_id: string;
  tenant_name: string;
  tenant_slug: string;
  role: Role;
}

export interface Me {
  id: string;
  email: string;
  full_name: string | null;
  locale: string;
  memberships: Membership[];
}

export interface TokenOut {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: Me;
}

/** Kısa ömürlü imzalı link (birkaç dakika geçerli; ekran tazelenince yenisi gelir). */
export interface Img {
  id: string | null;
  url: string;
  source?: "asset" | "model";
}

export interface Photo extends Img {
  angle: string | null;
  created_at: string;
  inspection_id: string | null;
  asset_hours: number | null;
}

export interface AssetSummary {
  id: string;
  code: string;
  status: string;
  meter_hours: number;
  site_id: string | null;
  site_name: string | null;
  manufacturer: string | null;
  model: string | null;
  category: string | null;
  layout: Layout | null;
  installed_parts: number;
  critical_parts: number;
  watch_parts: number;
  worst_condition_pct: number | null;
  last_inspection_at: string | null;
  image: Img | null;
}

export interface Position {
  code: string;
  label: string;
  category_code: string;
  axle: number | null;
  x: number | null;
  y: number | null;
  part_item_id: string | null;
  part_name: string | null;
  serial_no: string | null;
  condition_pct: number | null;
  band: Band;
  projected_hours_left: number | null;
  hours_total: number | null;
}

export interface AssetDetail extends AssetSummary {
  serial_no: string | null;
  year: number | null;
  meter_km: number;
  qr_code: string | null;
  notes: string | null;
  template_id: string | null;
  model_id: string | null;
  positions: Position[];
}

export interface PartListItem {
  id: string;
  current_asset_id: string | null;
  asset_code: string | null;
  current_position: string | null;
  category_code: string;
  part_name: string;
  serial_no: string | null;
  status: PartStatus;
  hours_total: number;
  condition_pct: number | null;
  band: Band;
  projected_hours_left: number | null;
  manufacturer: string | null;
  part_no: string | null;
  qr_code: string | null;
  cost_total: number;
}

export interface TireInfo {
  size: string;
  construction: string;
  otd_mm: number;
  scrap_tread_mm: number;
  tread_mm: number | null;
  pressure_kpa: number | null;
  tread_remaining_pct: number | null;
  wear_mm_per_hour: number | null;
  projected_hours_left: number | null;
  cost_per_hour: number | null;
  expected_cost_per_hour: number | null;
}

export interface RimInfo {
  ndt_interval_hours: number | null;
  last_ndt_hours: number | null;
  hours_since_ndt: number | null;
  compliance: "ok" | "due_soon" | "overdue" | "not_required";
}

export interface PartDetail {
  id: string;
  serial_no: string | null;
  qr_code: string | null;
  status: PartStatus;
  current_asset_id: string | null;
  asset_code: string | null;
  current_position: string | null;
  part_id: string;
  part_name: string;
  manufacturer: string | null;
  part_no: string | null;
  category_code: string;
  category_name: string;
  hours_total: number;
  expected_life_hours: number | null;
  cost_total: number;
  latest_measurements: Record<string, { value: number; unit: string | null; at: string }> | null;
  last_event_at: string | null;
  condition_pct: number | null;
  band: Band;
  projected_hours_left: number | null;
  tire: TireInfo | null;
  rim: RimInfo | null;
  image: Img | null;
  photos: Photo[];
}

export interface PartEvent {
  id: number;
  event_type: string;
  occurred_at: string;
  position: string | null;
  asset_hours: number | null;
  part_hours: number | null;
  cost: number | null;
  reason_code: string | null;
  notes: string | null;
  asset_code: string | null;
  performed_by_name: string | null;
}

export interface Wear {
  otd_mm: number;
  scrap_tread_mm: number;
  hours_total: number;
  wear_mm_per_hour: number | null;
  points: { part_hours: number; tread_mm: number; kind: "new" | "measured"; measured_at: string | null }[];
  projection: { from_hours: number; from_mm: number; to_hours: number; to_mm: number } | null;
}

export interface TireCost {
  asset_id: string;
  code: string;
  tires: number;
  tires_with_data: number;
  expected_cost_per_hour: number | null;
}

export interface Site {
  id: string;
  name: string;
  kind: string | null;
  city: string | null;
}

export interface Template {
  id: string;
  name: string;
  layout: Layout;
  is_library: boolean;
  positions: Pick<Position, "code" | "label" | "category_code" | "axle" | "x" | "y">[];
}

export interface AssetModel {
  id: string;
  manufacturer: string;
  model: string;
  category: string;
  template_id: string | null;
  template_name: string | null;
  layout: Layout | null;
  image: Img | null;
}

export interface CatalogPart {
  id: string;
  name: string;
  manufacturer: string | null;
  part_no: string | null;
  list_cost: number | null;
  min_stock: number;
  specs: Record<string, unknown>;
  category_code: string;
  category_name: string;
  tire_size: string | null;
  tire_construction: string | null;
  in_stock: number;
  installed: number;
  image: Img | null;
}

export interface Category {
  id: string;
  code: string;
  name: string;
  is_serialized: boolean;
  is_library: boolean;
}

// ---------- İnspeksiyon (mobil kontrol formu) ----------
export interface ProfileItem {
  metric: string;
  label: string;
  unit: string | null;
  required?: boolean;
  min?: number;
  max?: number;
}

export interface SheetItem {
  position: string;
  label: string;
  category_code: string;
  x: number | null;
  y: number | null;
  part_item_id: string;
  serial_no: string | null;
  part_name: string;
  profile: ProfileItem[];
  required_angles: string[];
  values: Record<string, number>;
  previous: Record<string, { value: number; at: string }>;
  photos: (Img & { angle: string })[];
  missing: ({ kind: "metric"; key: string; label: string } | { kind: "photo"; key: string })[];
  required: boolean;
  started: boolean;
  complete: boolean;
}

export interface QcFlag {
  gate: "KK1" | "KK2" | "KK3" | "KK4";
  message: string;
  position?: string;
  part_item_id?: string;
  metric?: string;
}

export interface Sheet {
  id: string;
  status: "draft" | "completed" | "rejected";
  asset_id: string;
  asset_code: string;
  manufacturer: string | null;
  model: string | null;
  layout: Layout | null;
  asset_hours: number | null;
  meter_hours: number;
  qc_flags: QcFlag[];
  started_at: string;
  completed_at: string | null;
  items: SheetItem[];
  progress: { done: number; total: number };
}

export interface InspectionSummary {
  id: string;
  status: string;
  asset_id: string;
  asset_code: string;
  asset_hours: number | null;
  started_at: string;
  completed_at: string | null;
  inspected_by_name: string | null;
  measured_parts: number;
}
