-- ============================================================
-- Marcación de asistencia (ingreso/salida) para psicólogos,
-- profesores y secretaría. Ejecutar en el SQL Editor de Supabase,
-- una sentencia a la vez.
-- ============================================================

CREATE TABLE IF NOT EXISTS marcaciones (
    id bigserial PRIMARY KEY,
    usuario_id bigint NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    fecha date NOT NULL,
    hora_ingreso time,
    hora_salida time,
    creado_en timestamptz DEFAULT now(),
    UNIQUE(usuario_id, fecha)
);

CREATE INDEX IF NOT EXISTS idx_marcaciones_usuario ON marcaciones(usuario_id);

CREATE INDEX IF NOT EXISTS idx_marcaciones_fecha ON marcaciones(fecha);

ALTER TABLE marcaciones ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON marcaciones FROM anon, authenticated;
