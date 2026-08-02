-- 0002 — Jornada, horas extra y sueldo proporcional sobre las marcaciones
-- Se aplica con:  DATABASE_URL="..." python deploy/migrate.py  (túnel SSH)

-- 1) Horas extra por día. Se guardan en la propia marcación para que el
--    recálculo del mes sea la simple suma de la columna (sin tabla aparte).
ALTER TABLE marcaciones ADD COLUMN IF NOT EXISTS horas_extra numeric(5,2) DEFAULT 0;
ALTER TABLE marcaciones ADD COLUMN IF NOT EXISTS nota_extra text;

-- Tipo de recargo del Art. 55 del Código del Trabajo (Ecuador):
--   suplementaria   -> +50%  (fuera de jornada, entre 06h00 y 24h00; máx 4/día, 12/semana)
--   extraordinaria  -> +100% (entre 24h00 y 06h00, o sábados, domingos y feriados)
--   nocturna        -> +25%  (jornada cumplida entre las 19h00 y las 06h00, Art. 49)
ALTER TABLE marcaciones ADD COLUMN IF NOT EXISTS tipo_extra text;
ALTER TABLE marcaciones DROP CONSTRAINT IF EXISTS marcaciones_tipo_extra_check;
ALTER TABLE marcaciones ADD CONSTRAINT marcaciones_tipo_extra_check
    CHECK (tipo_extra IS NULL OR tipo_extra IN ('suplementaria', 'extraordinaria', 'nocturna'));

-- 2) Jornada pactada y sueldo de cada persona.
--    horas_dia               -> jornada diaria que DEBE cumplir (8 completo, 4 medio tiempo)
--    dias_mes                -> días laborables exigidos en el mes
--    horas_jornada_completa  -> referencia de tiempo completo; horas_dia/esta = proporción
--    sueldo_tiempo_completo  -> sueldo mensual SI trabajara a tiempo completo (SBU 2026: 482.00)
--    recargo_hora_extra      -> recargo por defecto cuando el día no trae tipo
--  El valor hora NO sale de esta tabla: es la remuneración mensual dividida
--  para las horas de un mes de 30 días a su jornada (240 a tiempo completo).
CREATE TABLE IF NOT EXISTS jornadas_laborales (
    id bigserial PRIMARY KEY,
    usuario_id bigint NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    horas_dia numeric(5,2) NOT NULL DEFAULT 8,
    dias_mes integer NOT NULL DEFAULT 22,
    horas_jornada_completa numeric(5,2) NOT NULL DEFAULT 8,
    sueldo_tiempo_completo numeric(10,2) NOT NULL DEFAULT 482,
    recargo_hora_extra numeric(4,2) NOT NULL DEFAULT 1.5,
    actualizado_en timestamptz DEFAULT now(),
    UNIQUE(usuario_id)
);

CREATE INDEX IF NOT EXISTS idx_jornadas_usuario ON jornadas_laborales(usuario_id);

ALTER TABLE jornadas_laborales ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON jornadas_laborales FROM anon, authenticated;
