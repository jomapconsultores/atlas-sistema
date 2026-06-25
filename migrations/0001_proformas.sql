-- 0001 — Módulo de proformas (cotización de horarios y costos)
CREATE TABLE IF NOT EXISTS proformas (
    id BIGSERIAL PRIMARY KEY,
    numero TEXT,
    estudiante_id BIGINT REFERENCES estudiantes(id),
    estudiante_nombre TEXT,
    representante_nombre TEXT,
    representante_email TEXT,
    profesor_nombre TEXT,
    profesor_email TEXT,
    encargado_apertura TEXT,
    tipo_proforma TEXT DEFAULT 'clase',
    notas TEXT,
    validez_dias INTEGER DEFAULT 15,
    subtotal NUMERIC DEFAULT 0,
    total NUMERIC DEFAULT 0,
    estado TEXT DEFAULT 'borrador',
    incorporada BOOLEAN DEFAULT FALSE,
    creado_por BIGINT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    enviado_at TIMESTAMPTZ,
    aprobado_at TIMESTAMPTZ,
    incorporado_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS proforma_items (
    id BIGSERIAL PRIMARY KEY,
    proforma_id BIGINT REFERENCES proformas(id) ON DELETE CASCADE,
    tipo_sesion TEXT DEFAULT 'clase',
    asignatura TEXT,
    tema_terapia TEXT,
    profesor TEXT,
    fecha DATE,
    hora_inicio TEXT,
    hora_fin TEXT,
    horas NUMERIC DEFAULT 0,
    precio_hora NUMERIC DEFAULT 0,
    subtotal NUMERIC DEFAULT 0,
    orden INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_proformas_estado ON proformas(estado);
CREATE INDEX IF NOT EXISTS idx_proformas_estudiante ON proformas(estudiante_id);
CREATE INDEX IF NOT EXISTS idx_proforma_items_pid ON proforma_items(proforma_id);
