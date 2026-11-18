-- =====================================================================
-- SpareTwin — 0021: Rota, üretim emri ve işlem süresi
-- ---------------------------------------------------------------------
-- Rota: bir ürün ağacının (0020) hangi işlemlerden, hangi sırayla geçtiği
-- ve 1 birim ürün için planlanan süre.
--
--   bom_operations         → rota: ürün ağacı başına sıralı işlemler
--   production_orders      → üretim emri: hangi üründen kaç birim (UE-2026-0001)
--   production_order_ops   → emir açılırken rotadan kopyalanan işlemler;
--                            planlanan süre = birim süre × emir miktarı
--   production_time_logs   → başla / durdur zaman kaydı (kim, hangi işlemde)
--
-- İşlemler emre kopyalanır: rota sonradan değişse de açılmış emrin planı
-- ve geçmiş emirlerin raporu değişmez.
--
-- Kurallar (prod_op_start / prod_op_stop / prod_set_status):
--   - Bir kişi aynı anda tek işlemde çalışır (açık tek zaman kaydı).
--   - İlk işlem başlayınca emir kendiliğinden 'in_progress' olur.
--   - İşlem bitince üzerinde süren bütün kayıtlar kapanır.
--   - Emir, bütün işlemleri bitmeden tamamlanamaz; iptal süren kayıtları kapatır.
-- Stok bu aşamada etkilenmez (malzeme tüketimi ve mamul girişi sonraki kalem).
-- =====================================================================

create type app.prod_status as enum ('open', 'in_progress', 'done', 'cancelled');

-- ---------- Rota ----------
create table public.bom_operations (
  id               bigint generated always as identity primary key,
  tenant_id        uuid not null references public.tenants(id) on delete cascade,
  bom_id           uuid not null references public.boms(id) on delete cascade,
  seq              integer not null check (seq > 0),
  name             text not null check (length(name) between 2 and 80),
  planned_minutes  numeric(10,2) check (planned_minutes > 0),   -- 1 birim ürün için; boş = bilinmiyor
  unique (bom_id, seq)
);

-- ---------- Üretim emri ----------
create table public.production_orders (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references public.tenants(id) on delete cascade,
  number        text not null,                                   -- UE-2026-0001
  part_id       uuid not null references public.parts(id),       -- üretilen kalem
  qty           numeric(14,4) not null check (qty > 0),
  status        app.prod_status not null default 'open',
  due_at        date,
  notes         text,
  created_by    uuid references public.app_users(id) on delete set null,
  completed_by  uuid references public.app_users(id) on delete set null,
  started_at    timestamptz,
  completed_at  timestamptz,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  unique (tenant_id, number)
);
create index on public.production_orders (tenant_id, status);
create trigger trg_production_orders_updated before update on public.production_orders
  for each row execute function app.touch_updated_at();

create table public.production_order_ops (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null references public.tenants(id) on delete cascade,
  order_id         uuid not null references public.production_orders(id) on delete cascade,
  seq              integer not null,
  name             text not null,
  planned_minutes  numeric(12,2),                                -- emrin tamamı için
  done_at          timestamptz,
  done_by          uuid references public.app_users(id) on delete set null,
  unique (order_id, seq)
);
create index on public.production_order_ops (tenant_id, name);

create table public.production_time_logs (
  id          bigint generated always as identity primary key,
  tenant_id   uuid not null references public.tenants(id) on delete cascade,
  op_id       uuid not null references public.production_order_ops(id) on delete cascade,
  user_id     uuid not null references public.app_users(id) on delete cascade,
  started_at  timestamptz not null default now(),
  ended_at    timestamptz,
  constraint time_log_order check (ended_at is null or ended_at >= started_at)
);
create index on public.production_time_logs (op_id);
-- Bir kişi aynı anda tek işlemde çalışır
create unique index production_time_logs_one_open on public.production_time_logs (tenant_id, user_id) where ended_at is null;

alter table public.bom_operations enable row level security;
alter table public.production_orders enable row level security;
alter table public.production_order_ops enable row level security;
alter table public.production_time_logs enable row level security;
grant select, insert, update, delete on public.bom_operations to sparetwin_app;
grant select, insert, update on public.production_orders, public.production_order_ops, public.production_time_logs to sparetwin_app;

create policy bom_ops_select on public.bom_operations for select to sparetwin_app
  using (app.is_member(tenant_id));
create policy bom_ops_write on public.bom_operations for all to sparetwin_app
  using (app.has_role(tenant_id, '{owner,admin,manager}'))
  with check (app.has_role(tenant_id, '{owner,admin,manager}'));
create policy prod_orders_select on public.production_orders for select to sparetwin_app
  using (app.is_member(tenant_id));
create policy prod_orders_insert on public.production_orders for insert to sparetwin_app
  with check (app.has_role(tenant_id, '{owner,admin,manager}'));
create policy prod_orders_update on public.production_orders for update to sparetwin_app
  using (app.has_role(tenant_id, '{owner,admin,manager,technician}'));
create policy prod_ops_select on public.production_order_ops for select to sparetwin_app
  using (app.is_member(tenant_id));
create policy prod_ops_insert on public.production_order_ops for insert to sparetwin_app
  with check (app.has_role(tenant_id, '{owner,admin,manager}'));
create policy prod_ops_update on public.production_order_ops for update to sparetwin_app
  using (app.has_role(tenant_id, '{owner,admin,manager,technician}'));
create policy prod_logs_select on public.production_time_logs for select to sparetwin_app
  using (app.is_member(tenant_id));
create policy prod_logs_insert on public.production_time_logs for insert to sparetwin_app
  with check (app.has_role(tenant_id, '{owner,admin,manager,technician}'));
create policy prod_logs_update on public.production_time_logs for update to sparetwin_app
  using (app.has_role(tenant_id, '{owner,admin,manager,technician}'));

-- ---------- Emir numarası: UE-<yıl>-<sıra>, firma içinde ----------
create or replace function app.next_prod_number(p_tenant uuid)
returns text language plpgsql volatile
set search_path = public, app
as $$
declare
  y text := to_char(now(), 'YYYY');
  n integer;
begin
  perform pg_advisory_xact_lock(hashtextextended('prod:' || p_tenant::text, 0));
  select coalesce(max(split_part(number, '-', 3)::integer), 0) + 1 into n
    from public.production_orders
   where tenant_id = p_tenant and number ~ ('^UE-' || y || '-[0-9]+$');
  return 'UE-' || y || '-' || lpad(n::text, 4, '0');
end $$;
grant execute on function app.next_prod_number(uuid) to sparetwin_app;

-- ---------- İşlemde çalışmaya başla ----------
create or replace function public.prod_op_start(p_op uuid)
returns public.production_time_logs
language plpgsql security invoker
set search_path = public, app
as $$
declare
  op   public.production_order_ops;
  o    public.production_orders;
  busy text;
  l    public.production_time_logs;
begin
  select * into op from public.production_order_ops where id = p_op for update;
  if not found then raise exception 'İşlem bulunamadı' using errcode = 'P0002'; end if;
  select * into o from public.production_orders where id = op.order_id for update;
  if o.status not in ('open', 'in_progress') then
    raise exception 'Kapanmış emirde süre kaydı açılamaz' using errcode = '22023';
  end if;
  if op.done_at is not null then
    raise exception 'Bu işlem bitmiş' using errcode = '22023';
  end if;
  select po.number || ' · ' || x.name into busy
    from public.production_time_logs t
    join public.production_order_ops x on x.id = t.op_id
    join public.production_orders po on po.id = x.order_id
   where t.tenant_id = op.tenant_id and t.user_id = app.current_user_id() and t.ended_at is null;
  if busy is not null then
    raise exception 'Süren bir işiniz var (%); önce onu durdurun', busy using errcode = '22023';
  end if;
  insert into public.production_time_logs (tenant_id, op_id, user_id)
  values (op.tenant_id, p_op, app.current_user_id()) returning * into l;
  if o.status = 'open' then
    update public.production_orders set status = 'in_progress', started_at = now() where id = o.id;
  end if;
  return l;
end $$;
grant execute on function public.prod_op_start(uuid) to sparetwin_app;

-- ---------- Durdur (p_done: işlem bitti) ----------
-- Durdur yalnızca çağıranın kaydını kapatır; "bitti" işlemde süren herkesin kaydını kapatır.
-- Süre kaydı hiç açılmamış işlem de bitti işaretlenebilir (süre tutulmadan yapılmış iş).
create or replace function public.prod_op_stop(p_op uuid, p_done boolean default false)
returns public.production_order_ops
language plpgsql security invoker
set search_path = public, app
as $$
declare
  op public.production_order_ops;
  o  public.production_orders;
  n  integer;
begin
  select * into op from public.production_order_ops where id = p_op for update;
  if not found then raise exception 'İşlem bulunamadı' using errcode = 'P0002'; end if;
  select * into o from public.production_orders where id = op.order_id for update;
  if o.status not in ('open', 'in_progress') then
    raise exception 'Emir kapanmış' using errcode = '22023';
  end if;
  if op.done_at is not null then
    raise exception 'Bu işlem bitmiş' using errcode = '22023';
  end if;
  update public.production_time_logs set ended_at = now()
   where op_id = p_op and ended_at is null and (p_done or user_id = app.current_user_id());
  get diagnostics n = row_count;
  if not p_done and n = 0 then
    raise exception 'Bu işlemde süren bir kaydınız yok' using errcode = '22023';
  end if;
  if p_done then
    update public.production_order_ops set done_at = now(), done_by = app.current_user_id()
     where id = p_op returning * into op;
    if o.status = 'open' then
      update public.production_orders set status = 'in_progress', started_at = now() where id = o.id;
    end if;
  end if;
  return op;
end $$;
grant execute on function public.prod_op_stop(uuid, boolean) to sparetwin_app;

-- ---------- Emri tamamla / iptal et ----------
create or replace function public.prod_set_status(p_order uuid, p_status text)
returns public.production_orders
language plpgsql security invoker
set search_path = public, app
as $$
declare
  o public.production_orders;
begin
  select * into o from public.production_orders where id = p_order for update;
  if not found then raise exception 'Üretim emri bulunamadı' using errcode = 'P0002'; end if;
  if o.status not in ('open', 'in_progress') then
    raise exception 'Emir zaten kapanmış' using errcode = '22023';
  end if;
  if p_status = 'done' then
    if exists (select 1 from public.production_order_ops where order_id = p_order and done_at is null) then
      raise exception 'Bitmemiş işlem var; emir bütün işlemler bitince tamamlanır' using errcode = '22023';
    end if;
  elsif p_status = 'cancelled' then
    update public.production_time_logs t set ended_at = now()
      from public.production_order_ops x
     where x.id = t.op_id and x.order_id = p_order and t.ended_at is null;
  else
    raise exception 'Geçersiz durum: %', p_status using errcode = '22023';
  end if;
  update public.production_orders
     set status = p_status::app.prod_status, completed_at = now(), completed_by = app.current_user_id(),
         started_at = coalesce(started_at, now())
   where id = p_order returning * into o;
  return o;
end $$;
grant execute on function public.prod_set_status(uuid, text) to sparetwin_app;

-- ---------- İşlem başına gerçekleşen süre ----------
-- Süren kayıt şu ana kadar sayılır.
create or replace view public.v_production_ops
with (security_invoker = true) as
select x.id, x.tenant_id, x.order_id, x.seq, x.name, x.planned_minutes, x.done_at, x.done_by,
       coalesce(t.actual_minutes, 0) as actual_minutes,
       coalesce(t.running, 0) as running
  from public.production_order_ops x
  left join lateral (
    select round(sum(extract(epoch from (coalesce(l.ended_at, now()) - l.started_at)) / 60)::numeric, 1) as actual_minutes,
           count(*) filter (where l.ended_at is null) as running
      from public.production_time_logs l where l.op_id = x.id
  ) t on true;
grant select on public.v_production_ops to sparetwin_app;
