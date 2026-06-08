-- ============================================================
-- MIGRACIÓN: Tabla 'movimientos_cuenta'
-- Propósito: guardar el estado de cuenta bancario que sube el
-- ADMINISTRADOR (Excel/PDF) y cruzarlo con los pagos de
-- estudiantes y demás valores. Los movimientos que no cuadran
-- quedan 'pendiente' (se resaltan en otro color) para revisar
-- o justificar. La columna 'hash_mov' (UNIQUE) deduplica:
-- si un estado de cuenta ya está subido no se vuelve a insertar.
-- Acceso: solo administrador.
-- Ejecutar en: Supabase Dashboard → SQL Editor
-- ============================================================

CREATE TABLE IF NOT EXISTS movimientos_cuenta (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lote_id             UUID        NOT NULL,                  -- identifica el archivo/estado de cuenta
    banco               TEXT,
    fecha               DATE,
    descripcion         TEXT,
    referencia          TEXT,                                  -- N° documento bancario
    monto               NUMERIC(12,2) NOT NULL,                -- + crédito / - débito
    tipo                TEXT,                                  -- 'credito' | 'debito'
    saldo               NUMERIC(12,2),
    hash_mov            TEXT        NOT NULL UNIQUE,            -- md5(fecha|monto|descripcion|referencia)
    estado_conciliacion TEXT        NOT NULL DEFAULT 'pendiente',  -- 'conciliado' | 'pendiente' | 'justificado'
    conciliado_tipo     TEXT,                                  -- 'pago' | 'gasto' | 'cita' | 'devolucion'
    conciliado_id       BIGINT,
    justificacion       TEXT,
    fecha_carga         TIMESTAMPTZ NOT NULL DEFAULT now(),
    cargado_por         TEXT
);

-- La app usa la clave anon (igual que las demás tablas). Desactivamos RLS.
ALTER TABLE movimientos_cuenta DISABLE ROW LEVEL SECURITY;

-- Índices: dedup por hash (ya cubierto por UNIQUE), filtro por lote y por fecha
CREATE INDEX IF NOT EXISTS idx_movimientos_lote   ON movimientos_cuenta (lote_id);
CREATE INDEX IF NOT EXISTS idx_movimientos_fecha  ON movimientos_cuenta (fecha);
CREATE INDEX IF NOT EXISTS idx_movimientos_estado ON movimientos_cuenta (estado_conciliacion);

-- Verificación
SELECT * FROM movimientos_cuenta ORDER BY fecha DESC;
