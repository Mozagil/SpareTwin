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
  unknown_parts: number;
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
  rim_slot: string | null;
  mounted_rim: {
    id: string; serial_no: string | null; part_name: string; compliance: RimRow["compliance"];
    hours_since_ndt: number; ndt_interval_hours: number | null; hours_to_due: number | null;
  } | null;
  mounted_tire: { id: string; serial_no: string | null; part_name: string; condition_pct: number | null; band: Band } | null;
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
  unit: Unit;
  is_serialized: boolean;
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

// ---------- Jantlar ve bildirimler ----------
export interface RimRow {
  id: string;
  serial_no: string | null;
  part_name: string;
  asset_id: string | null;
  asset_code: string | null;
  current_position: string | null;
  hours_total: number;
  ndt_interval_hours: number | null;
  last_ndt_hours: number | null;
  last_ndt_at: string | null;
  hours_since_ndt: number;
  hours_to_due: number | null;
  compliance: "overdue" | "due_soon" | "ok" | "not_required";
}

export interface Notification {
  key: string;
  kind: "part_critical" | "rim_ndt" | "stock_low" | "asset_stale" | "rim_missing" | "purchase_need" | "po_late" | "maintenance_due" | "asset_down";
  severity: "critical" | "watch";
  title: string;
  body: string;
  link: { type: "part" | "rim" | "stock" | "asset" | "purchasing" | "order" | "maintenance" | "work_order"; id: string };
  at: string | null;
  read: boolean;
  /** Ekip bazlı durum: üstlenildi / gizlendi / yok. Durum değişince kendiliğinden düşer. */
  state: NotificationState | null;
  state_by: string | null;
  state_at: string | null;
  note: string | null;
}
export type NotificationState = "acknowledged" | "dismissed";
export interface NotificationList {
  items: Notification[];
  unread: number;
  dismissed: number;
}

// ---------- Firma ayarları ve denetim kaydı ----------
export interface Thresholds {
  critical_pct: number;
  watch_pct: number;
  rim_due_soon_pct: number;
  inspection_interval_days: number;
  need_horizon_hours: number;
  maint_warn_hours: number;
  maint_warn_days: number;
  downtime_cost_per_hour: number;
}
export interface Organization {
  id: string;
  name: string;
  slug: string;
  plan: string;
  currency: string;
  thresholds: Thresholds;
  defaults: Thresholds;
}
export interface AuditRow {
  id: number;
  at: string;
  user_id: string | null;
  user_email: string | null;
  user_name: string | null;
  method: string;
  path: string;
  status: number;
  entity_type: string | null;
  entity_id: string | null;
  action: string | null;
  detail: Record<string, unknown> | null;
  ip: string | null;
}

// ---------- Stok ----------
export type Unit = "adet" | "litre" | "kg" | "metre" | "takım";

export interface StockRow {
  part_id: string;
  name: string;
  manufacturer: string | null;
  part_no: string | null;
  unit: Unit;
  min_stock: number;
  category_code: string;
  category_name: string;
  is_serialized: boolean;
  qty: number;
  value: number | null;
  avg_cost: number | null;
  below_min: boolean;
  sites: { site_id: string | null; qty: number }[] | null;
  used_90d: number;
}

export interface StockMovement {
  id: number;
  kind: "in" | "out" | "adjust" | "transfer_out" | "transfer_in";
  qty: number;
  unit_cost: number | null;
  reason: string | null;
  ref: string | null;
  notes: string | null;
  occurred_at: string;
  site_name: string | null;
  asset_code: string | null;
  asset_id: string | null;
  performed_by_name: string | null;
}

// ---------- Satınalma (Faz 2) ----------
export type PoStatus = "draft" | "ordered" | "partial" | "received" | "cancelled";

export interface Supplier {
  id: string;
  name: string;
  contact_name: string | null;
  phone: string | null;
  email: string | null;
  tax_no: string | null;
  address: string | null;
  notes: string | null;
  lead_time_days: number | null;
  is_active: boolean;
  created_at: string;
  open_orders?: number;
}

export interface SupplierIn {
  name: string;
  contact_name: string | null;
  phone: string | null;
  email: string | null;
  tax_no: string | null;
  address: string | null;
  notes: string | null;
  lead_time_days: number | null;
  is_active: boolean;
}

export interface PurchaseNeed {
  part_id: string;
  name: string;
  manufacturer: string | null;
  part_no: string | null;
  unit: Unit;
  category_code: string;
  is_serialized: boolean;
  min_stock: number;
  in_stock: number;
  avg_cost: number | null;
  /** Yaklaşan değişim sayısı (kritik ya da değişim ufku içinde) */
  upcoming: number;
  items: { id: string; asset_code: string; position: string; band: Band; condition_pct: number | null; hours_left: number | null }[] | null;
  on_order: number;
  requested: number;
  /** Önerilen sipariş miktarı */
  need: number;
}

export interface PurchaseOrder {
  id: string;
  number: string;
  status: PoStatus;
  supplier_id: string | null;
  supplier_name: string | null;
  site_id: string | null;
  site_name: string | null;
  expected_at: string | null;
  notes: string | null;
  ordered_at: string | null;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
  requested_by_name: string | null;
  ordered_by_name: string | null;
  line_count: number;
  total: number | null;
  received_total: number | null;
  summary: string | null;
  late: boolean;
}

export interface PurchaseOrderLine {
  id: number;
  part_id: string;
  name: string;
  manufacturer: string | null;
  part_no: string | null;
  unit: Unit;
  is_serialized: boolean;
  category_code: string;
  qty: number;
  received_qty: number;
  unit_cost: number | null;
  asset_id: string | null;
  asset_code: string | null;
  notes: string | null;
}

export interface PurchaseReceipt {
  id: number;
  line_id: number;
  name: string;
  qty: number;
  ref: string | null;
  serials: { id: string; serial_no: string | null }[] | null;
  received_at: string;
  site_name: string | null;
  received_by_name: string | null;
}

export interface PurchaseOrderDetail extends PurchaseOrder {
  lines: PurchaseOrderLine[];
  receipts: PurchaseReceipt[];
}

export interface PurchaseLineIn { part_id: string; qty: number; unit_cost: number | null; asset_id: string | null; notes: string | null }
export interface PurchaseOrderIn {
  supplier_id: string | null;
  site_id: string | null;
  expected_at: string | null;
  notes: string | null;
  lines: PurchaseLineIn[];
}
export interface ReceiveIn {
  site_id: string | null;
  ref: string | null;
  lines: { line_id: number; qty: number; serials?: { serial_no: string | null; qr_code?: string | null }[] }[];
}

// ---------- Bakım (Faz 2) ----------
export type WoKind = "planned" | "breakdown";
export type WoStatus = "open" | "in_progress" | "done" | "cancelled";
export type DueState = "overdue" | "due_soon" | "ok";
export type ReasonCode = "hydraulic" | "electrical" | "engine" | "tire" | "transmission" | "structural" | "operator" | "other";

export interface PlanPart { part_id: string; name: string; unit: Unit; qty: number; is_serialized: boolean }

export interface MaintenancePlan {
  id: string;
  name: string;
  asset_id: string | null;
  asset_code: string | null;
  model_id: string | null;
  model_name: string | null;
  interval_hours: number | null;
  interval_days: number | null;
  checklist: string[];
  notes: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  /** Planın kapsadığı (emekli olmayan) makine sayısı */
  asset_count: number;
  parts: PlanPart[];
}

export interface MaintenancePlanIn {
  name: string;
  asset_id: string | null;
  model_id: string | null;
  interval_hours: number | null;
  interval_days: number | null;
  checklist: string[];
  notes: string | null;
  is_active: boolean;
  parts: { part_id: string; qty: number }[];
}

export interface MaintenanceDue {
  plan_id: string;
  name: string;
  interval_hours: number | null;
  interval_days: number | null;
  checklist: string[];
  asset_id: string;
  asset_code: string;
  meter_hours: number;
  asset_status: string;
  site_id: string | null;
  last_done_at: string | null;
  last_done_hours: number | null;
  last_done_number: string | null;
  next_due_hours: number | null;
  next_due_at: string | null;
  hours_left: number | null;
  days_left: number | null;
  hours_per_day: number | null;
  /** Saat bazlı bakım için günlük kullanımdan tahmini tarih; takvimde hedef tarih */
  eta_at: string | null;
  state: DueState;
  open_work_order_id: string | null;
  open_work_order_number: string | null;
  open_work_order_status: WoStatus | null;
}

export interface WorkOrder {
  id: string;
  number: string;
  kind: WoKind;
  status: WoStatus;
  title: string;
  asset_id: string;
  asset_code: string;
  asset_meter_hours: number;
  plan_id: string | null;
  plan_name: string | null;
  due_at: string | null;
  due_hours: number | null;
  down_from: string | null;
  down_to: string | null;
  downtime_minutes: number | null;
  reason_code: ReasonCode | null;
  part_item_id: string | null;
  part_serial_no: string | null;
  part_name: string | null;
  asset_hours_at_done: number | null;
  labor_cost: number | null;
  external_cost: number | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  created_by_name: string | null;
  assigned_to_name: string | null;
  completed_by_name: string | null;
  assigned_to: string | null;
  description: string | null;
  part_count: number;
  parts_cost: number | null;
  late: boolean;
}

export interface WorkOrderPart {
  id: number;
  part_id: string;
  name: string;
  unit: Unit;
  qty: number;
  site_id: string | null;
  site_name: string | null;
  unit_cost: number | null;
  in_stock: number;
}

export interface WorkOrderDetail extends WorkOrder {
  parts: WorkOrderPart[];
  checklist: string[] | null;
}

export interface WoPartIn { part_id: string; qty: number; site_id: string | null }
export interface WorkOrderIn {
  asset_id: string;
  kind: WoKind;
  plan_id: string | null;
  title: string | null;
  description: string | null;
  due_at: string | null;
  due_hours: number | null;
  down_from: string | null;
  reason_code: ReasonCode | null;
  part_item_id: string | null;
  parts: WoPartIn[] | null;
}
export interface WorkOrderPatch {
  title?: string;
  description?: string | null;
  due_at?: string | null;
  due_hours?: number | null;
  down_from?: string | null;
  reason_code?: ReasonCode | null;
  part_item_id?: string | null;
  labor_cost?: number | null;
  external_cost?: number | null;
  parts?: WoPartIn[];
}
export interface WoStatusIn {
  status: "in_progress" | "done" | "cancelled";
  asset_hours?: number | null;
  down_to?: string | null;
  labor_cost?: number | null;
  external_cost?: number | null;
  notes?: string | null;
}

export interface AssetMaintenance {
  asset_id: string;
  asset_code: string;
  asset_status: string;
  planned_done: number;
  breakdowns: number;
  open_orders: number;
  downtime_minutes: number;
  cost_12m: number;
  last_done_at: string | null;
}

// ---------- Maliyet raporu (TCO) ----------
export interface TcoCosts {
  parts_cost: number;
  consumables_cost: number;
  labor_cost: number;
  external_cost: number;
  downtime_cost: number;
  total: number;
}
export interface TcoRow extends TcoCosts {
  asset_id: string;
  asset_code: string;
  asset_status: string;
  site_id: string | null;
  site_name: string | null;
  model_name: string | null;
  downtime_minutes: number;
  planned_done: number;
  breakdowns: number;
  hours_worked: number;
  /** Saat kaydının başladığı an; dönem başından sonraysa saat başı maliyet eksik saate bölünmüştür */
  hours_from: string | null;
  cost_per_hour: number | null;
  /** Geçerli duruş saat maliyeti: makineye özel oran, yoksa firma oranı */
  downtime_rate: number;
  downtime_rate_own: boolean;
}
export interface TcoReport {
  months: number;
  from: string;
  to: string;
  currency: string;
  downtime_cost_per_hour: number;
  totals: TcoCosts & { downtime_minutes: number; hours_worked: number; cost_per_hour: number | null };
  assets: TcoRow[];
}
