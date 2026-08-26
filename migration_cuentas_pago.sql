-- Datos de cuenta de pago por persona (docentes/psicólogos).
--
-- ⚠️ NO REAPLICAR ESTE ARCHIVO TAL CUAL (agosto de 2026)
-- Se comprobó contra la base que la tabla existe pero que la POLÍTICA y el
-- GRANT del final nunca llegaron a aplicarse: en producción esta tabla solo la
-- alcanzan 'postgres' y 'service_role', y así debe seguir. Reejecutar el
-- archivo completo concedería a 'anon' lectura y ESCRITURA sobre las cuentas
-- bancarias del personal — y la clave anon de este proyecto quedó publicada en
-- el historial de un repositorio público, así que ese permiso equivale a
-- dejarlas abiertas a cualquiera.
-- Si hace falta recrear la tabla en otra base, ejecuta solo el CREATE TABLE y
-- deja fuera el bloque de RLS/policy/grant del final.
--
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
