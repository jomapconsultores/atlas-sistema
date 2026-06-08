-- ============================================================
-- MIGRACIÓN: Tabla 'devoluciones'
-- Propósito: registrar devoluciones de dinero a clientes
-- (estudiantes y clientes externos de psicología) cuando no
-- quedan satisfechos. Una devolución RESTA ingresos y, si se
-- debe pagar igual al docente/psicólogo por el trabajo hecho,
-- genera un GASTO vinculado (categoría 'Devolución - pago docente').
-- Acceso: socios y administrador.
-- Ejecutar en: Supabase Dashboard → SQL Editor
-- ============================================================

CREATE TABLE IF NOT EXISTS devoluciones (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fecha          DATE        NOT NULL DEFAULT CURRENT_DATE,
    tipo_cliente   TEXT        NOT NULL DEFAULT 'estudiante',  -- 'estudiante' | 'externo'
    estudiante_id  BIGINT,                                     -- FK lógica a estudiantes
    cliente_id     BIGINT,                                     -- FK lógica a clientes_externos
    cita_id        BIGINT,                                     -- FK lógica a citas_psicologia
    pago_id        BIGINT,                                     -- pago original (opcional)
    monto          NUMERIC(10,2) NOT NULL,                     -- monto devuelto al cliente
    tipo_pago      TEXT        DEFAULT 'efectivo',             -- cómo se devolvió
    motivo         TEXT,
    pagar_docente  BOOLEAN     NOT NULL DEFAULT FALSE,
    docente_nombre TEXT,
    monto_docente  NUMERIC(10,2) NOT NULL DEFAULT 0,
    gasto_id       BIGINT,                                     -- gasto auto-creado vinculado
    mes_periodo    INT,                                        -- alineación con Liquidación
    anio_periodo   INT,
    registrado_por TEXT,
    fecha_registro TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- La app usa la clave anon (igual que las demás tablas). Desactivamos RLS.
ALTER TABLE devoluciones DISABLE ROW LEVEL SECURITY;

-- Índices para filtrar por estudiante y por período (Reportes/Liquidación)
CREATE INDEX IF NOT EXISTS idx_devoluciones_estudiante ON devoluciones (estudiante_id);
CREATE INDEX IF NOT EXISTS idx_devoluciones_periodo    ON devoluciones (anio_periodo, mes_periodo);
CREATE INDEX IF NOT EXISTS idx_devoluciones_fecha      ON devoluciones (fecha);

-- Verificación
SELECT * FROM devoluciones ORDER BY fecha_registro DESC;
