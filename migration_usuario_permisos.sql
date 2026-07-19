-- ============================================================
-- Permisos granulares por modulo/submodulo (rol 'secretaria' y
-- override individual para cualquier usuario).
-- Ejecutar en el SQL Editor de Supabase. El backend ya usa la
-- service_role key, así que se activa RLS real desde el día 1
-- (sin el paso intermedio que hizo falta para las tablas viejas).
-- ============================================================

CREATE TABLE IF NOT EXISTS usuario_permisos (
    id bigserial PRIMARY KEY,
    usuario_id bigint NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    modulo text NOT NULL,          -- ej. 'academico', 'finanzas.gastos'
    otorgado_por text,             -- nombre del admin/socio que lo otorgó
    otorgado_en timestamptz DEFAULT now(),
    UNIQUE(usuario_id, modulo)
);
CREATE INDEX IF NOT EXISTS idx_usuario_permisos_usuario ON usuario_permisos(usuario_id);

ALTER TABLE usuario_permisos ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON usuario_permisos FROM anon, authenticated;
