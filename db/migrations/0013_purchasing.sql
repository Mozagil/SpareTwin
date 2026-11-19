-- =====================================================================
-- SpareTwin — 0013: Satınalma (Faz 2)
-- ---------------------------------------------------------------------
-- Tedarikçi → satınalma belgesi (talep → sipariş → teslim) → stok.
-- Talep teknisyen tarafından açılabilir; siparişi vermek ve iptal etmek
-- yönetici işidir (para harcatan adım). Teslim alma: sarf malzemesi
-- stock_move ile stoğa, seri numaralı parça part_items olarak girer.
-- =====================================================================

create table public.suppliers (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references public.tenants(id) on delete cascade,
  name        text not null,
  contact     text,
  phone       text,
  email       text,
  notes       text,
  active      boolean not null default true,
  created_at  timestamptz not null default now(),
  unique (tenant_id, name)
);

create type app.po_status as enum ('draft', 'ordered', 'partial', 'received', 'cancelled');

create table public.purchase_orders (
  id             uuid primary key default gen_random_uuid(),
  tenant_id      uuid not null references public.tenants(id) on delete cascade,
  number         text not null,
  supplier_id    uuid references public.suppliers(id),
  status         app.po_status not null default 'draft',
  expected_date  date,
  notes          text,
  created_by     uuid references public.app_users(id),
  created_at     timestamptz not null default now(),
  ordered_by     uuid references public.app_users(id),
  ordered_at     timestamptz,
  received_at    timestamptz,
  unique (tenant_id, number)
);
create index on public.purchase_orders (tenant_id, status);

create table public.purchase_order_lines (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references public.tenants(id) on delete cascade,
  po_id         uuid not null references public.purchase_orders(id) on delete cascade,
  part_id       uuid not null references public.parts(id),
  qty           numeric(12,3) not null check (qty > 0),
  unit_cost     numeric(12,4) check (unit_cost >= 0),
  received_qty  numeric(12,3) not null default 0 check (received_qty >= 0),
  note          text,
  check (received_qty <= qty)
);
create index on public.purchase_order_lines (po_id);
create index on public.purchase_order_lines (tenant_id, part_id);

-- Firma içinde yıla göre sıralı belge numarası: SA-2026-0001
create or replace function app.next_po_number(p_tenant uuid)
returns text language plpgsql as $$
declare
  y text := to_char(now(), 'YYYY');
  n int;
begin
  perform pg_advisory_xact_lock(hashtextextended('po:' || p_tenant::text, 0));
  select coalesce(max(split_part(number, '-', 3)::int), 0) + 1 into n
    from public.purchase_orders where tenant_id = p_tenant and number like 'SA-' || y || '-%';
  return 'SA-' || y || '-' || lpad(n::text, 4, '0');
end $$;
grant execute on function app.next_po_number(uuid) to sparetwin_app;

-- RLS: standart firma tabloları. Silme yok (iptal durumu kullanılır).
do $$
declare t text;
begin
  foreach t in array array['suppliers', 'purchase_orders', 'purchase_order_lines'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('grant select, insert, update on public.%I to sparetwin_app', t);
    execute format('create policy %1$s_select on public.%1$I for select to sparetwin_app using (app.is_member(tenant_id))', t);
    execute format('create policy %1$s_insert on public.%1$I for insert to sparetwin_app
                      with check (app.has_role(tenant_id, ''{owner,admin,manager,technician}''))', t);
    execute format('create policy %1$s_update on public.%1$I for update to sparetwin_app
                      using (app.has_role(tenant_id, ''{owner,admin,manager,technician}''))', t);
  end loop;
end $$;
-- Taslak satırları silinebilir (taslak düzenleme)
grant delete on public.purchase_order_lines to sparetwin_app;
create policy purchase_order_lines_delete on public.purchase_order_lines for delete to sparetwin_app
  using (app.has_role(tenant_id, '{owner,admin,manager,technician}')
         and exists (select 1 from public.purchase_orders po where po.id = po_id and po.status = 'draft'));

-- Yoldaki miktar: verilmiş ama henüz teslim alınmamış siparişler
create or replace view public.v_on_order
with (security_invoker = true) as
select l.tenant_id, l.part_id, sum(l.qty - l.received_qty) as qty
  from public.purchase_order_lines l
  join public.purchase_orders po on po.id = l.po_id
 where po.status in ('ordered', 'partial')
 group by l.tenant_id, l.part_id;
grant select on public.v_on_order to sparetwin_app;
