-- =====================================================================
-- SpareTwin — 0014: Satınalma (Faz 2)
-- ---------------------------------------------------------------------
-- Tedarikçi → satınalma talebi (draft) → sipariş (ordered) → teslim alma
-- (partial / received). KOBİ ERP planındaki satınalma modülünün sade hali.
--
-- Teslim alma stokla aynı yerden geçer: sarf kalemleri stock_move('in') ile
-- deftere, seri numaralı parçalar (lastik, jant, silindir) part_items'a
-- 'received' olayıyla girer. Böylece "stok" ve "satınalma" iki ayrı sayı
-- tutmaz. Durum (ordered / partial / received) satırlardan hesaplanır.
--
-- İhtiyaç önerisi (v_purchase_needs): yaklaşan değişimler (kritik ya da
-- firmanın "değişim ufku" saatinden az ömrü kalan takılı parçalar) + kritik
-- stok seviyesi − stoktaki − siparişteki. "LD-07 için 2 lastik yaklaşıyor,
-- stokta 1 var" cümlesi buradan çıkar.
-- =====================================================================

-- ---------- Tedarikçi ----------
create table public.suppliers (
  id              uuid primary key default gen_random_uuid(),
  tenant_id       uuid not null references public.tenants(id) on delete cascade,
  name            text not null check (length(name) between 2 and 120),
  contact_name    text,
  phone           text,
  email           text,
  tax_no          text,
  address         text,
  notes           text,
  lead_time_days  integer check (lead_time_days between 0 and 365),  -- tipik teslim süresi
  is_active       boolean not null default true,
  created_at      timestamptz not null default now(),
  unique (tenant_id, name)
);
alter table public.suppliers enable row level security;
grant select, insert, update on public.suppliers to sparetwin_app;
create policy suppliers_select on public.suppliers for select to sparetwin_app
  using (app.is_member(tenant_id));
create policy suppliers_write on public.suppliers for insert to sparetwin_app
  with check (app.has_role(tenant_id, '{owner,admin,manager}'));
create policy suppliers_update on public.suppliers for update to sparetwin_app
  using (app.has_role(tenant_id, '{owner,admin,manager}'));

-- ---------- Sipariş ----------
create type app.po_status as enum ('draft', 'ordered', 'partial', 'received', 'cancelled');

create table public.purchase_orders (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references public.tenants(id) on delete cascade,
  number        text not null,                                   -- SA-2026-0001 (firma içinde)
  supplier_id   uuid references public.suppliers(id) on delete restrict,
  site_id       uuid references public.sites(id) on delete set null,  -- teslimat deposu
  status        app.po_status not null default 'draft',
  expected_at   date,
  notes         text,
  requested_by  uuid references public.app_users(id) on delete set null,
  ordered_by    uuid references public.app_users(id) on delete set null,
  ordered_at    timestamptz,
  closed_at     timestamptz,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  unique (tenant_id, number)
);
create index on public.purchase_orders (tenant_id, status);
create trigger trg_purchase_orders_updated before update on public.purchase_orders
  for each row execute function app.touch_updated_at();

create table public.purchase_order_lines (
  id            bigint generated always as identity primary key,
  tenant_id     uuid not null references public.tenants(id) on delete cascade,
  order_id      uuid not null references public.purchase_orders(id) on delete cascade,
  part_id       uuid not null references public.parts(id),
  qty           numeric(12,3) not null check (qty > 0),
  unit_cost     numeric(12,4) check (unit_cost >= 0),
  received_qty  numeric(12,3) not null default 0 check (received_qty >= 0 and received_qty <= qty),
  asset_id      uuid references public.assets(id) on delete set null,   -- hangi makine için
  notes         text,
  unique (order_id, part_id)
);
create index on public.purchase_order_lines (tenant_id, part_id);

-- Teslim alma kayıtları: hangi satırdan, ne zaman, kaç adet, hangi irsaliyeyle
create table public.purchase_receipts (
  id           bigint generated always as identity primary key,
  tenant_id    uuid not null references public.tenants(id) on delete cascade,
  order_id     uuid not null references public.purchase_orders(id) on delete cascade,
  line_id      bigint not null references public.purchase_order_lines(id) on delete cascade,
  qty          numeric(12,3) not null check (qty > 0),
  site_id      uuid references public.sites(id) on delete set null,
  ref          text,                       -- irsaliye / fatura no
  serials      jsonb,                      -- seri numaralı parçalarda oluşturulan kalemler
  received_by  uuid references public.app_users(id) on delete set null,
  received_at  timestamptz not null default now()
);
create index on public.purchase_receipts (order_id);

alter table public.purchase_orders enable row level security;
alter table public.purchase_order_lines enable row level security;
alter table public.purchase_receipts enable row level security;
grant select, insert, update on public.purchase_orders to sparetwin_app;
grant select, insert, update, delete on public.purchase_order_lines to sparetwin_app;
grant select, insert on public.purchase_receipts to sparetwin_app;

create policy po_select on public.purchase_orders for select to sparetwin_app
  using (app.is_member(tenant_id));
create policy po_insert on public.purchase_orders for insert to sparetwin_app
  with check (app.has_role(tenant_id, '{owner,admin,manager,technician}'));
create policy po_update on public.purchase_orders for update to sparetwin_app
  using (app.has_role(tenant_id, '{owner,admin,manager,technician}'));
create policy pol_select on public.purchase_order_lines for select to sparetwin_app
  using (app.is_member(tenant_id));
create policy pol_write on public.purchase_order_lines for all to sparetwin_app
  using (app.has_role(tenant_id, '{owner,admin,manager,technician}'))
  with check (app.has_role(tenant_id, '{owner,admin,manager,technician}'));
create policy pr_select on public.purchase_receipts for select to sparetwin_app
  using (app.is_member(tenant_id));
create policy pr_insert on public.purchase_receipts for insert to sparetwin_app
  with check (app.has_role(tenant_id, '{owner,admin,manager,technician}'));

-- ---------- Sipariş numarası: SA-<yıl>-<sıra>, firma içinde ----------
create or replace function app.next_po_number(p_tenant uuid)
returns text language plpgsql volatile
set search_path = public, app
as $$
declare
  y text := to_char(now(), 'YYYY');
  n integer;
begin
  perform pg_advisory_xact_lock(hashtextextended('po:' || p_tenant::text, 0));
  select coalesce(max(split_part(number, '-', 3)::integer), 0) + 1 into n
    from public.purchase_orders
   where tenant_id = p_tenant and number ~ ('^SA-' || y || '-[0-9]+$');
  return 'SA-' || y || '-' || lpad(n::text, 4, '0');
end $$;
grant execute on function app.next_po_number(uuid) to sparetwin_app;

-- ---------- Durum geçişleri (kurallar tek yerde) ----------
-- draft → ordered (tedarikçi ve en az bir satır gerekir)
-- draft | ordered → cancelled (teslim alınmış satır varsa iptal edilemez)
-- partial → received (kalanı kapat)
create or replace function public.po_set_status(p_order uuid, p_status text)
returns public.purchase_orders
language plpgsql security invoker
set search_path = public, app
as $$
declare
  o public.purchase_orders;
begin
  select * into o from public.purchase_orders where id = p_order for update;
  if not found then raise exception 'Sipariş bulunamadı' using errcode = 'P0002'; end if;

  if p_status = 'ordered' then
    if o.status <> 'draft' then
      raise exception 'Yalnızca talep durumundaki kayıt sipariş verilebilir' using errcode = '22023';
    end if;
    if o.supplier_id is null then
      raise exception 'Sipariş vermek için tedarikçi seçin' using errcode = '22023';
    end if;
    if not exists (select 1 from public.purchase_order_lines where order_id = p_order) then
      raise exception 'Siparişte en az bir kalem olmalı' using errcode = '22023';
    end if;
    update public.purchase_orders
       set status = 'ordered', ordered_by = app.current_user_id(), ordered_at = now()
     where id = p_order returning * into o;
  elsif p_status = 'cancelled' then
    if o.status not in ('draft', 'ordered') then
      raise exception 'Teslim alınmaya başlanan veya kapanmış sipariş iptal edilemez' using errcode = '22023';
    end if;
    update public.purchase_orders set status = 'cancelled', closed_at = now()
     where id = p_order returning * into o;
  elsif p_status = 'received' then
    if o.status <> 'partial' then
      raise exception 'Yalnızca kısmen teslim alınmış sipariş kapatılabilir' using errcode = '22023';
    end if;
    update public.purchase_orders set status = 'received', closed_at = now()
     where id = p_order returning * into o;
  else
    raise exception 'Geçersiz durum: %', p_status using errcode = '22023';
  end if;
  return o;
end $$;
grant execute on function public.po_set_status(uuid, text) to sparetwin_app;

-- Satırlardan durum: hepsi tamamsa received, biri bile başladıysa partial
create or replace function app.po_refresh_status(p_order uuid)
returns void language plpgsql
set search_path = public, app
as $$
declare
  all_done boolean;
  any_done boolean;
begin
  select bool_and(received_qty >= qty), bool_or(received_qty > 0) into all_done, any_done
    from public.purchase_order_lines where order_id = p_order;
  update public.purchase_orders
     set status = case when all_done then 'received' when any_done then 'partial' else 'ordered' end::app.po_status,
         closed_at = case when all_done then now() end
   where id = p_order and status in ('ordered', 'partial');
end $$;
grant execute on function app.po_refresh_status(uuid) to sparetwin_app;

-- ---------- Teslim alma ----------
-- Sarf kalemi: stok defterine giriş (maliyet = sipariş fiyatı, ref = sipariş no / irsaliye).
-- Seri numaralı kalem: p_serials dizisindeki her öğe için ({serial_no, qr_code}) bir
-- part_item + 'received' olayı; dizi uzunluğu miktara eşit olmalı.
create or replace function public.po_receive(
  p_line bigint, p_qty numeric, p_site uuid default null, p_ref text default null, p_serials jsonb default null
) returns public.purchase_receipts
language plpgsql security invoker
set search_path = public, app
as $$
declare
  ln   public.purchase_order_lines;
  o    public.purchase_orders;
  part record;
  site uuid;
  s    jsonb;
  item uuid;
  made jsonb := '[]'::jsonb;
  rc   public.purchase_receipts;
begin
  select * into ln from public.purchase_order_lines where id = p_line for update;
  if not found then raise exception 'Sipariş kalemi bulunamadı' using errcode = 'P0002'; end if;
  select * into o from public.purchase_orders where id = ln.order_id for update;
  if o.status not in ('ordered', 'partial') then
    raise exception 'Bu sipariş teslim alınabilir durumda değil (%)', o.status using errcode = '22023';
  end if;
  if p_qty is null or p_qty <= 0 then
    raise exception 'Miktar sıfırdan büyük olmalı' using errcode = '22023';
  end if;
  if ln.received_qty + p_qty > ln.qty then
    raise exception 'Siparişte kalan % %, istenen %', trim_scale(ln.qty - ln.received_qty),
      (select unit from public.parts where id = ln.part_id), trim_scale(p_qty) using errcode = '22023';
  end if;
  site := coalesce(p_site, o.site_id);
  if site is not null and not exists (select 1 from public.sites where id = site and tenant_id = o.tenant_id) then
    raise exception 'Depo bulunamadı' using errcode = 'P0002';
  end if;

  select p.id, p.list_cost, pc.is_serialized into part
    from public.parts p join public.part_categories pc on pc.id = p.category_id where p.id = ln.part_id;

  if part.is_serialized then
    if p_qty <> trunc(p_qty) then
      raise exception 'Seri numaralı parça tam adet teslim alınır' using errcode = '22023';
    end if;
    if p_serials is null or jsonb_typeof(p_serials) <> 'array' or jsonb_array_length(p_serials) <> p_qty::int then
      raise exception 'Seri numaralı parçada her adet için bir satır girin (% adet)', trim_scale(p_qty) using errcode = '22023';
    end if;
    for s in select * from jsonb_array_elements(p_serials) loop
      insert into public.part_items (tenant_id, part_id, serial_no, qr_code, status, site_id, purchase_cost, acquired_at)
      values (o.tenant_id, ln.part_id, nullif(s->>'serial_no', ''), coalesce(nullif(s->>'qr_code', ''), app.new_qr('ST-P-')),
              'in_stock', site, coalesce(ln.unit_cost, part.list_cost), current_date)
      returning id into item;
      -- maliyet part_items.purchase_cost'ta; olaya yazılmaz (cost_total iki kez saymasın)
      insert into public.part_events (tenant_id, part_item_id, event_type, part_hours, notes, performed_by)
      values (o.tenant_id, item, 'received', 0, 'Sipariş ' || o.number || coalesce(' / ' || p_ref, ''), app.current_user_id());
      made := made || jsonb_build_object('id', item, 'serial_no', nullif(s->>'serial_no', ''));
    end loop;
  else
    perform public.stock_move(ln.part_id, site, 'in', p_qty, coalesce(ln.unit_cost, part.list_cost), null,
                              'satınalma', o.number || coalesce(' / ' || p_ref, ''), null, null, o.tenant_id);
  end if;

  update public.purchase_order_lines set received_qty = received_qty + p_qty where id = p_line;
  insert into public.purchase_receipts (tenant_id, order_id, line_id, qty, site_id, ref, serials, received_by)
  values (o.tenant_id, o.id, p_line, p_qty, site, p_ref, case when part.is_serialized then made end, app.current_user_id())
  returning * into rc;
  perform app.po_refresh_status(o.id);
  return rc;
end $$;
grant execute on function public.po_receive(bigint, numeric, uuid, text, jsonb) to sparetwin_app;

-- ---------- Siparişteki / talepteki miktar (kalem bazında) ----------
create or replace view public.v_purchase_on_order
with (security_invoker = true) as
select l.tenant_id, l.part_id,
       sum(l.qty - l.received_qty) filter (where o.status in ('ordered', 'partial')) as on_order,
       sum(l.qty) filter (where o.status = 'draft') as requested
  from public.purchase_order_lines l
  join public.purchase_orders o on o.id = l.order_id
 where o.status in ('draft', 'ordered', 'partial')
 group by l.tenant_id, l.part_id;

-- ---------- İhtiyaç önerisi ----------
-- upcoming: takılı olup kritik olan ya da firmanın "değişim ufku" (varsayılan 500 saat)
-- içinde ömrü biten parçalar. need = upcoming + kritik seviye − stok − siparişte.
create or replace view public.v_purchase_needs
with (security_invoker = true) as
with up as (
  select ph.tenant_id, l.part_id, count(*) as upcoming,
         jsonb_agg(jsonb_build_object(
           'id', ph.id, 'asset_code', ph.asset_code, 'position', ph.current_position, 'band', ph.band,
           'condition_pct', ph.condition_pct, 'hours_left', ph.projected_hours_left)
           order by ph.band, ph.projected_hours_left nulls last, ph.asset_code) as items
    from public.v_part_health ph
    join public.v_part_items_live l on l.id = ph.id
    join public.tenants t on t.id = ph.tenant_id
   where ph.status = 'installed'
     and (ph.band = 'critical'
          or ph.projected_hours_left <= coalesce((t.settings->'thresholds'->>'need_horizon_hours')::numeric, 500))
   group by ph.tenant_id, l.part_id
)
select st.tenant_id, st.part_id, st.name, st.manufacturer, st.part_no, st.unit, st.category_code, st.is_serialized,
       st.min_stock, st.qty as in_stock, st.avg_cost,
       coalesce(up.upcoming, 0) as upcoming, up.items,
       coalesce(oo.on_order, 0) as on_order, coalesce(oo.requested, 0) as requested,
       greatest(coalesce(up.upcoming, 0) + st.min_stock - st.qty - coalesce(oo.on_order, 0), 0) as need
  from public.v_stock_totals st
  left join up on up.tenant_id = st.tenant_id and up.part_id = st.part_id
  left join public.v_purchase_on_order oo on oo.tenant_id = st.tenant_id and oo.part_id = st.part_id
 where coalesce(up.upcoming, 0) > 0 or st.qty + coalesce(oo.on_order, 0) < st.min_stock;

grant select on public.v_purchase_on_order, public.v_purchase_needs to sparetwin_app;
