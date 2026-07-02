-- Datos de cuenta de pago por persona (docentes/psicólogos).
-- Ejecutar una sola vez en el proyecto Supabase de Atlas
-- (Dashboard → SQL Editor → pegar → Run).

create table if not exists cuentas_pago_docentes (
    id              bigserial primary key,
    persona         text unique not null,     -- nombre con el que se le identifica en el sistema
    nombre_completo text,
    cedula          text,
    banco           text,
    tipo_cuenta     text,                      -- 'Ahorros' | 'Corriente'
    numero_cuenta   text,
    correo          text,
    actualizado_por text,
    updated_at      timestamptz default now()
);

-- Acceso para la app (clave anon): RLS con política permisiva.
alter table cuentas_pago_docentes enable row level security;
drop policy if exists cuentas_pago_acceso on cuentas_pago_docentes;
create policy cuentas_pago_acceso on cuentas_pago_docentes
    for all to anon, authenticated using (true) with check (true);
grant all on cuentas_pago_docentes to anon, authenticated;
grant usage, select on all sequences in schema public to anon, authenticated;
