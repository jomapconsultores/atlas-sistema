-- ============================================================
-- Multi-rol: un usuario puede tener varios roles asignados y
-- cambiar cual tiene ACTIVO (usuarios.rol sigue siendo el rol
-- activo actual; esta tabla es el conjunto de roles entre los que
-- puede elegir). Ejecutar en el SQL Editor de Supabase.
-- ============================================================

CREATE TABLE IF NOT EXISTS usuario_roles (
    id bigserial PRIMARY KEY,
    usuario_id bigint NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    rol text NOT NULL,
    otorgado_por text,
    otorgado_en timestamptz DEFAULT now(),
    UNIQUE(usuario_id, rol)
);
CREATE INDEX IF NOT EXISTS idx_usuario_roles_usuario ON usuario_roles(usuario_id);

ALTER TABLE usuario_roles ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON usuario_roles FROM anon, authenticated;
