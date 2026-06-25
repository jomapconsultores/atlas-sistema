#!/bin/bash
# ============================================================
# Roles y permisos estilo Supabase para PostgREST.
# Se ejecuta UNA sola vez, en el primer arranque del contenedor db
# (cuando el volumen de datos está vacío).
# ============================================================
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Rol anónimo (lo que usa la app con la clave anon) y rol de servicio
    CREATE ROLE anon NOLOGIN;
    CREATE ROLE service_role NOLOGIN BYPASSRLS;

    -- Rol de login que PostgREST usa para "cambiar" a anon/service_role
    CREATE ROLE authenticator NOINHERIT LOGIN PASSWORD '${AUTHENTICATOR_PASSWORD}';
    GRANT anon         TO authenticator;
    GRANT service_role TO authenticator;

    -- Permisos: la app (clave anon) hace CRUD completo, igual que hoy en la nube.
    -- (El servidor está cerrado a internet salvo el proxy; misma postura de seguridad actual.)
    GRANT USAGE ON SCHEMA public TO anon, service_role;
    GRANT ALL ON ALL TABLES    IN SCHEMA public TO anon, service_role;
    GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO anon, service_role;
    GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO anon, service_role;

    -- Que las tablas/seq futuras (las que yo cree luego) hereden los permisos
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES    TO anon, service_role;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO anon, service_role;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO anon, service_role;
EOSQL

echo "Roles anon/service_role/authenticator creados."
