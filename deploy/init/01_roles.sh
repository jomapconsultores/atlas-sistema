#!/bin/bash
# ============================================================
# Roles y permisos estilo Supabase para PostgREST.
# Se ejecuta UNA sola vez, en el primer arranque del contenedor db
# (cuando el volumen de datos está vacío).
# ============================================================
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Los tres roles que Supabase da por hechos. 'authenticated' no lo usa la
    -- app, pero SÍ aparece en las migraciones ("REVOKE ALL ON tabla FROM anon,
    -- authenticated"): sin crearlo, restaurar el dump falla con
    -- «role "authenticated" does not exist» en cada REVOKE.
    CREATE ROLE anon NOLOGIN;
    CREATE ROLE authenticated NOLOGIN;
    CREATE ROLE service_role NOLOGIN BYPASSRLS;

    -- Rol de login que PostgREST usa para "cambiar" al rol del JWT
    CREATE ROLE authenticator NOINHERIT LOGIN PASSWORD '${AUTHENTICATOR_PASSWORD}';
    GRANT anon          TO authenticator;
    GRANT authenticated TO authenticator;
    GRANT service_role  TO authenticator;

    -- Permisos: la app entra con la clave SERVICE_ROLE, no con la anon. Así es
    -- como está hoy en la nube (ver .env.example de la raíz) y es lo que exige
    -- migration_rls_lockdown.sql, que revoca a 'anon' el acceso a las tablas.
    -- Dar aquí permisos a 'anon' sería reabrir justo lo que ese lockdown cerró.
    GRANT USAGE ON SCHEMA public TO service_role;
    GRANT ALL ON ALL TABLES    IN SCHEMA public TO service_role;
    GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO service_role;
    GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO service_role;

    -- Que las tablas/seq futuras (las que se creen luego) hereden los permisos
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES    TO service_role;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO service_role;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO service_role;
EOSQL

echo "Roles anon/service_role/authenticator creados."
