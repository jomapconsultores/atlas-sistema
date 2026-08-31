-- 0010 — El pago excepcional guarda el contexto de la clase
-- Aplicar en el SQL Editor del proyecto Supabase de Atlas (el archivo entero),
-- o con deploy/migrate.py cuando la base ya esté auto-alojada.
--
-- Quien firma la excepción veía "2 h a $10/h, +$6" y nada más. Con ese dato
-- solo no se puede juzgar el pedido: una tarifa mayor no pesa igual en una
-- clase individual que en una GRUPAL. El pago al docente es UNO por clase
-- física (se deduplica), pero el ingreso son tantas matrículas como
-- estudiantes, así que en la grupal el margen aguanta y en la individual
-- puede irse a cero.
--
-- Estas columnas guardan la FOTO del contexto al momento de solicitar —no se
-- recalcula después— porque es lo que quien autorizó tuvo a la vista, y las
-- filas de la clase pueden cambiar más tarde (una baja, un reajuste de precio).
--
-- Es AUTOSUFICIENTE: crea también la tabla y la columna de
-- migration_pago_excepcional.sql (el archivo suelto de la raíz, anterior a
-- migrations/) si nunca se corrieron. Todo va con IF NOT EXISTS, así que
-- aplicarla sobre una base que ya las tiene no cambia nada.

-- ---------- 1. Tarifa excepcional en la sesión ----------
ALTER TABLE sesiones
    ADD COLUMN IF NOT EXISTS tarifa_docente_hora NUMERIC(10,2);

COMMENT ON COLUMN sesiones.tarifa_docente_hora IS
    'Tarifa/hora de docencia aprobada como excepción para esta clase. NULL = tarifa estándar ($7/h). Solo la escribe la aprobación de un socio/admin en /pagos-excepcionales.';

-- ---------- 2. Bitácora de solicitudes ----------
CREATE TABLE IF NOT EXISTS pagos_excepcionales (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sesion_id         BIGINT        NOT NULL,          -- fila de 'sesiones' sobre la que se pidió
    sesion_grupo_id   UUID,                            -- clase física (todas sus filas comparten la tarifa)
    docente           TEXT          NOT NULL,
    fecha_sesion      DATE,
    hora_inicio       TEXT,
    hora_fin          TEXT,
    horas             NUMERIC(6,2),
    asignatura        TEXT,
    tarifa_hora       NUMERIC(10,2) NOT NULL,          -- tarifa excepcional pedida (ej. 10.00)
    tarifa_estandar   NUMERIC(10,2) NOT NULL DEFAULT 7,-- la vigente al pedirla (para auditar el diferencial)
    diferencia        NUMERIC(10,2),                   -- (tarifa_hora - tarifa_estandar) * horas
    motivo            TEXT          NOT NULL,          -- justificación obligatoria
    estado            TEXT          NOT NULL DEFAULT 'pendiente',  -- pendiente | aprobado | rechazado | revocado
    solicitado_por    TEXT,
    fecha_solicitud   TIMESTAMPTZ   NOT NULL DEFAULT now(),
    resuelto_por      TEXT,                            -- socio/admin que aprobó, rechazó o revocó
    fecha_resolucion  TIMESTAMPTZ,
    motivo_rechazo    TEXT,
    CONSTRAINT ck_pagos_exc_estado CHECK (estado IN ('pendiente','aprobado','rechazado','revocado')),
    CONSTRAINT ck_pagos_exc_tarifa CHECK (tarifa_hora > 0 AND tarifa_hora <= 50)
);

-- Una sola excepción viva por sesión: no se pueden acumular dos aprobadas
-- (ni dos pendientes) sobre la misma clase.
CREATE UNIQUE INDEX IF NOT EXISTS uq_pagos_exc_sesion_viva
    ON pagos_excepcionales (sesion_id)
    WHERE estado IN ('pendiente', 'aprobado');

CREATE INDEX IF NOT EXISTS idx_pagos_exc_estado ON pagos_excepcionales (estado);
CREATE INDEX IF NOT EXISTS idx_pagos_exc_fecha  ON pagos_excepcionales (fecha_sesion DESC);

ALTER TABLE pagos_excepcionales DISABLE ROW LEVEL SECURITY;

-- ---------- 3. El contexto de la clase (lo nuevo) ----------
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

-- ---------- 4. Verificación ----------
SELECT id, docente, fecha_sesion, horas, tarifa_hora, estado,
       es_grupal, n_estudiantes, ingreso_clase, margen_actual, margen_nuevo
FROM pagos_excepcionales
ORDER BY fecha_solicitud DESC;
