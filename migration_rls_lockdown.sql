-- ============================================================
-- RLS LOCKDOWN — hallazgos críticos/altos de la auditoría ultracode
-- (usuario_passkeys, cuentas_pago_docentes, movimientos_cuenta,
--  liquidaciones, devoluciones, proformas/proforma_items, contactos,
--  docentes)
--
-- ⚠️ NO EJECUTAR TODAVÍA. Esta migración deja estas tablas SIN NINGÚN
-- acceso para los roles 'anon' y 'authenticated'. Como supabase_client.py
-- hoy conecta con la clave 'anon', aplicar esto tal cual ROMPE la app
-- (todas las lecturas/escrituras a estas tablas empezarían a fallar).
--
-- Orden correcto para desplegar esto sin causar una caída:
--   1. En el dashboard de Supabase → Settings → API, copiar la
--      'service_role key' (nunca se expone al navegador; solo la usa
--      el backend Flask).
--   2. Setear esa clave como env var SUPABASE_SERVICE_ROLE_KEY en Coolify.
--   3. Cambiar supabase_client.py para crear el cliente con esa clave
--      en vez de la anon key (el service_role bypassea RLS, así que
--      Flask sigue funcionando igual que ahora).
--   4. Deployar y verificar que la app funciona normal.
--   5. Recién ahí ejecutar esta migración en el SQL Editor de Supabase.
--   6. Como paso final, rotar también la clave 'anon' vieja (quedó
--      comprometida en el historial de git) — con este lockdown ya no
--      importa que se filtre de nuevo, porque no da acceso a nada.
--
-- Estas tablas no se acceden nunca desde el navegador con la clave anon
-- (todo pasa por las rutas Flask), así que "sin acceso para anon" no le
-- quita ninguna función legítima a la app una vez hecho el cambio a
-- service_role.
-- ============================================================

-- ---------- usuario_passkeys ----------
ALTER TABLE usuario_passkeys ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS usuario_passkeys_acceso ON usuario_passkeys;
REVOKE ALL ON usuario_passkeys FROM anon, authenticated;

-- ---------- cuentas_pago_docentes ----------
ALTER TABLE cuentas_pago_docentes ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cuentas_pago_acceso ON cuentas_pago_docentes;
REVOKE ALL ON cuentas_pago_docentes FROM anon, authenticated;

-- ---------- movimientos_cuenta ----------
ALTER TABLE movimientos_cuenta ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON movimientos_cuenta FROM anon, authenticated;

-- ---------- liquidaciones ----------
ALTER TABLE liquidaciones ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON liquidaciones FROM anon, authenticated;

-- ---------- devoluciones ----------
ALTER TABLE devoluciones ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON devoluciones FROM anon, authenticated;

-- ---------- proformas / proforma_items ----------
ALTER TABLE proformas ENABLE ROW LEVEL SECURITY;
ALTER TABLE proforma_items ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON proformas FROM anon, authenticated;
REVOKE ALL ON proforma_items FROM anon, authenticated;

-- ---------- contactos ----------
ALTER TABLE contactos ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON contactos FROM anon, authenticated;

-- ---------- docentes ----------
ALTER TABLE docentes ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON docentes FROM anon, authenticated;

-- Nota: no se crea ninguna política (policy) en estas tablas a propósito.
-- Con RLS activada y sin policies, el default de Postgres/Supabase es
-- denegar todo; el REVOKE explícito es una segunda barrera por si algún
-- GRANT ALL previo (heredado de migration_cuentas_pago.sql, etc.) seguía
-- vigente a nivel de rol.
