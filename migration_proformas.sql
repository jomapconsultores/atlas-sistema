-- ============================================================
-- MÓDULO DE PROFORMAS DE CLASES / ATENCIÓN PSICOLÓGICA
-- Cotización de horarios y costos que se envía al representante
-- y/o al docente. Una vez APROBADA se incorpora a la
-- planificación (Módulo 1) creando las sesiones correspondientes.
--
-- Aplicar en: Supabase → SQL Editor (el MCP de Supabase es solo lectura).
-- ============================================================

CREATE TABLE IF NOT EXISTS proformas (
    id              BIGSERIAL PRIMARY KEY,
    numero          TEXT,                       -- nº legible de la proforma (ej. PRO-2026-0007)
    estudiante_id   BIGINT REFERENCES estudiantes(id),
    estudiante_nombre   TEXT,                   -- copia textual por si el estudiante es nuevo
    representante_nombre TEXT,
    representante_email  TEXT,
    profesor_nombre TEXT,
    profesor_email  TEXT,
    encargado_apertura TEXT,                    -- requerido al incorporar a planificación
    tipo_proforma   TEXT DEFAULT 'clase',       -- clase / terapia / mixto
    notas           TEXT,
    validez_dias    INTEGER DEFAULT 15,
    subtotal        NUMERIC DEFAULT 0,
    total           NUMERIC DEFAULT 0,
    estado          TEXT DEFAULT 'borrador',    -- borrador, enviado, aprobado, incorporado, rechazado
    incorporada     BOOLEAN DEFAULT FALSE,      -- TRUE cuando ya generó sesiones en planificación
    creado_por      BIGINT,
    created_at      TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    enviado_at      TIMESTAMPTZ,
    aprobado_at     TIMESTAMPTZ,
    incorporado_at  TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS proforma_items (
    id              BIGSERIAL PRIMARY KEY,
    proforma_id     BIGINT REFERENCES proformas(id) ON DELETE CASCADE,
    tipo_sesion     TEXT DEFAULT 'clase',       -- clase, terapia, preuniversitario, ambos
    asignatura      TEXT,
    tema_terapia    TEXT,                        -- tipo de atención psicológica
    profesor        TEXT,
    fecha           DATE,
    hora_inicio     TEXT,
    hora_fin        TEXT,
    horas           NUMERIC DEFAULT 0,
    precio_hora     NUMERIC DEFAULT 0,           -- para clases: $/hora; para terapia: precio de la atención
    subtotal        NUMERIC DEFAULT 0,           -- importe de la línea
    orden           INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_proformas_estado     ON proformas(estado);
CREATE INDEX IF NOT EXISTS idx_proformas_estudiante ON proformas(estudiante_id);
CREATE INDEX IF NOT EXISTS idx_proforma_items_pid   ON proforma_items(proforma_id);
