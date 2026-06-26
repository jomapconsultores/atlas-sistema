-- ============================================================
-- MIGRACIÓN: Tabla 'liquidaciones'
-- Propósito: guardar el "Saldo de la Cuenta de Ahorros" (saldo_cuenta)
-- que el SOCIO/ADMIN registra por cada mes/año en la pantalla de
-- Liquidación. Ese saldo alimenta el balance del período:
--   balance = saldo_cuenta - total_gastos - pago_docentes_neto
-- Antes esta tabla NO existía: el guardado fallaba en silencio
-- (except: pass) y el valor en cuenta nunca se actualizaba.
-- Un único registro por (mes, anio) -> UNIQUE para poder hacer upsert.
-- Acceso: socio / administrador.
-- Ejecutar en: Supabase Dashboard -> SQL Editor
-- ============================================================

CREATE TABLE IF NOT EXISTS liquidaciones (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    mes             SMALLINT      NOT NULL,                 -- 1..12
    anio            SMALLINT      NOT NULL,
    saldo_cuenta    NUMERIC(12,2) NOT NULL DEFAULT 0,       -- saldo de la cuenta de ahorros del período
    registrado_por  TEXT,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT uq_liquidaciones_periodo UNIQUE (mes, anio)
);

-- La app usa la clave anon (igual que las demás tablas). Desactivamos RLS.
ALTER TABLE liquidaciones DISABLE ROW LEVEL SECURITY;

CREATE INDEX IF NOT EXISTS idx_liquidaciones_periodo ON liquidaciones (anio, mes);

-- Verificación
SELECT * FROM liquidaciones ORDER BY anio DESC, mes DESC;
