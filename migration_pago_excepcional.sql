-- ============================================================
-- MIGRACIÓN: Pago excepcional al docente ($10/h en vez de $7/h)
--
-- Propósito: la tarifa de docencia es SIEMPRE $7 por hora. En casos
-- esporádicos y justificados (una eventualidad concreta) se le puede
-- pagar más a un docente por UNA clase puntual. Esa excepción:
--   1. la registra quien gestiona (planificación / pagos a docentes),
--   2. queda PENDIENTE con un motivo obligatorio, y
--   3. solo empieza a pagarse cuando un SOCIO o el ADMINISTRADOR la
--      aprueba desde /pagos-excepcionales.
--
-- Dos piezas:
--   · sesiones.tarifa_docente_hora → la tarifa que realmente rige esa
--     clase. NULL = tarifa estándar ($7). La escribe únicamente la
--     aprobación, y se limpia si se rechaza o se revoca. Todos los
--     reportes (Módulo 5, Reportes, Liquidación, Mi reporte) leen el
--     pago desde la regla única pago_sesion_docente(), así que basta
--     esta columna para que la excepción se refleje en todos.
--   · pagos_excepcionales → la bitácora: quién pidió, por qué, quién
--     aprobó/rechazó y cuándo. Es el respaldo de la autorización.
--
-- Ejecutar en: Supabase Dashboard → SQL Editor
-- ============================================================

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

-- La app entra con la clave anon, igual que las demás tablas (ver
-- migration_rls_lockdown.sql para el plan de endurecimiento general).
ALTER TABLE pagos_excepcionales DISABLE ROW LEVEL SECURITY;

-- ---------- 3. Verificación ----------
SELECT id, docente, fecha_sesion, horas, tarifa_hora, estado, motivo
FROM pagos_excepcionales
ORDER BY fecha_solicitud DESC;

-- Sesiones que hoy tienen tarifa excepcional activa (debe coincidir con las
-- solicitudes en estado 'aprobado'):
SELECT id, fecha, profesor_terapeuta, horas, tarifa_docente_hora
FROM sesiones
WHERE tarifa_docente_hora IS NOT NULL
ORDER BY fecha DESC;
