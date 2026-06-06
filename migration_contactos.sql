-- ============================================================
-- MIGRACIÓN: Tabla 'contactos'
-- Propósito: guardar las solicitudes de contacto enviadas desde
-- la página de presentación (landing) pública. Genera alerta para
-- socios y administradores.
-- Ejecutar en: Supabase Dashboard → SQL Editor
-- ============================================================

CREATE TABLE IF NOT EXISTS contactos (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre         TEXT NOT NULL,
    telefono       TEXT,
    email          TEXT,
    mensaje        TEXT,
    estado         TEXT NOT NULL DEFAULT 'nuevo',   -- 'nuevo' | 'atendido'
    atendido_por   TEXT,
    fecha_atendido TIMESTAMPTZ,
    fecha_registro TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- La app usa la clave anon (igual que las demás tablas). Desactivamos RLS
-- para que el formulario público pueda insertar y los socios/admin leer.
ALTER TABLE contactos DISABLE ROW LEVEL SECURITY;

-- Índice para listar rápido los contactos nuevos (badge de alerta)
CREATE INDEX IF NOT EXISTS idx_contactos_estado ON contactos (estado);

-- Verificación
SELECT * FROM contactos ORDER BY fecha_registro DESC;
