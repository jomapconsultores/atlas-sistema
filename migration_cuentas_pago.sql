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

-- Mismo modelo de acceso que el resto de tablas de la app (clave anon).
alter table cuentas_pago_docentes disable row level security;
grant all on cuentas_pago_docentes to anon, authenticated;
grant usage, select on all sequences in schema public to anon, authenticated;
