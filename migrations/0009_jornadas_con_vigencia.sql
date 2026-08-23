-- 0009 — La jornada de cada persona pasa a tener historial
-- Aplicar en el SQL Editor del proyecto Supabase de Atlas (el archivo entero),
-- o con deploy/migrate.py cuando la base ya esté auto-alojada.
--
-- 'jornadas_laborales' guardaba UNA fila por persona, sin fechas: la jornada
-- vigente y nada más. Cambiarla no era «a partir de ahora», era «desde
-- siempre», porque el reporte de CUALQUIER mes se calculaba con la última
-- jornada guardada. Pasar a alguien de medio tiempo a jornada completa
-- convertía sus meses anteriores en incumplimientos y cambiaba, hacia atrás,
-- el sueldo de meses que ya estaban pagados.
--
-- Ahora cada jornada rige DESDE una fecha. Guardar un cambio no pisa la
-- anterior: abre una etapa nueva. El reporte de un mes usa la etapa que estaba
-- vigente ese mes, así que el pasado deja de moverse.

-- 1) Desde cuándo rige cada jornada. Las que ya existen se dan por vigentes
--    «desde siempre» para que ningún mes anterior cambie de resultado al
--    aplicar esta migración.
ALTER TABLE jornadas_laborales ADD COLUMN IF NOT EXISTS vigente_desde date;

UPDATE jornadas_laborales SET vigente_desde = DATE '2000-01-01' WHERE vigente_desde IS NULL;

ALTER TABLE jornadas_laborales ALTER COLUMN vigente_desde SET NOT NULL;

-- 2) Fuera el «una jornada por persona»: es justo lo que impedía el historial.
--    Se busca la restricción por su definición y no por su nombre, que lo puso
--    Postgres al crear la tabla y puede no ser el mismo en otra instalación.
DO $$
DECLARE
    nombre text;
BEGIN
    SELECT c.conname INTO nombre
      FROM pg_constraint c
     WHERE c.conrelid = 'jornadas_laborales'::regclass
       AND c.contype = 'u'
       AND c.conkey = ARRAY[(SELECT a.attnum FROM pg_attribute a
                              WHERE a.attrelid = c.conrelid AND a.attname = 'usuario_id')];
    IF nombre IS NOT NULL THEN
        EXECUTE format('ALTER TABLE jornadas_laborales DROP CONSTRAINT %I', nombre);
    END IF;
END $$;

-- Una sola etapa por persona y fecha de inicio: guardar dos veces el mismo día
-- corrige la etapa, no crea una duplicada.
ALTER TABLE jornadas_laborales DROP CONSTRAINT IF EXISTS jornadas_usuario_vigencia_key;

ALTER TABLE jornadas_laborales
    ADD CONSTRAINT jornadas_usuario_vigencia_key UNIQUE (usuario_id, vigente_desde);

CREATE INDEX IF NOT EXISTS idx_jornadas_usuario_vigencia
    ON jornadas_laborales(usuario_id, vigente_desde DESC);
