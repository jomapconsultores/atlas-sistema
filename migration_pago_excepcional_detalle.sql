-- ============================================================
-- MIGRACIÓN: contexto de la clase en el pago excepcional
--
-- Propósito: quien firma la excepción veía "2 h a $10/h, +$6" y nada más.
-- Con ese dato solo no se puede juzgar el pedido: una tarifa mayor no pesa
-- igual en una clase individual que en una GRUPAL. El pago al docente es uno
-- por clase física (se deduplica), pero el ingreso son varias matrículas, así
-- que en la grupal el margen aguanta y en la individual puede irse a cero.
--
-- Estas columnas guardan la FOTO del contexto al momento de solicitar —no se
-- recalcula después— porque es lo que quien autorizó tuvo a la vista y las
-- filas de la clase pueden cambiar más tarde (una baja, un reajuste de precio).
--
-- Requiere haber corrido antes migration_pago_excepcional.sql.
-- Ejecutar en: Supabase Dashboard → SQL Editor
-- ============================================================

ALTER TABLE pagos_excepcionales
    ADD COLUMN IF NOT EXISTS tipo_sesion         TEXT,
    ADD COLUMN IF NOT EXISTS es_grupal           BOOLEAN,
    ADD COLUMN IF NOT EXISTS n_estudiantes       INTEGER,
    ADD COLUMN IF NOT EXISTS estudiantes         TEXT,
    ADD COLUMN IF NOT EXISTS ingreso_clase       NUMERIC(10,2),
    ADD COLUMN IF NOT EXISTS pago_docente_actual NUMERIC(10,2),
    ADD COLUMN IF NOT EXISTS pago_docente_nuevo  NUMERIC(10,2),
    ADD COLUMN IF NOT EXISTS margen_actual       NUMERIC(10,2),
    ADD COLUMN IF NOT EXISTS margen_nuevo        NUMERIC(10,2);

COMMENT ON COLUMN pagos_excepcionales.es_grupal IS
    'TRUE si esa clase física la recibieron 2 o más estudiantes (una fila de sesiones por cada uno).';
COMMENT ON COLUMN pagos_excepcionales.n_estudiantes IS
    'Cuántos estudiantes asistieron (filas Realizado de la clase física). 1 = individual.';
COMMENT ON COLUMN pagos_excepcionales.estudiantes IS
    'Nombres de quienes recibieron la clase, separados por coma.';
COMMENT ON COLUMN pagos_excepcionales.ingreso_clase IS
    'Lo cobrado a TODOS los estudiantes por esa clase física (regla cobro_sesion_estudiante).';
COMMENT ON COLUMN pagos_excepcionales.margen_nuevo IS
    'Margen de Atlas en esa clase si se aprueba la excepción: ingreso_clase - pago_docente_nuevo.';

-- Las solicitudes anteriores quedan con estas columnas en NULL: la pantalla
-- muestra "—" en el histórico y reconstruye el dato al vuelo en las PENDIENTES,
-- que son las únicas que todavía hay que decidir.

-- ---------- Verificación ----------
SELECT id, docente, fecha_sesion, horas, tarifa_hora, estado,
       es_grupal, n_estudiantes, ingreso_clase, margen_actual, margen_nuevo
FROM pagos_excepcionales
ORDER BY fecha_solicitud DESC;
