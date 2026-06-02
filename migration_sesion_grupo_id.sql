-- ============================================================
-- MIGRACIÓN: Agregar sesion_grupo_id a tabla sesiones
-- Propósito: identificar filas que pertenecen a la misma
-- sesión física (mismo docente, fecha y horario).
-- Ejecutar en: Supabase Dashboard → SQL Editor
-- ============================================================

-- 1. Agregar columna
ALTER TABLE sesiones
    ADD COLUMN IF NOT EXISTS sesion_grupo_id UUID;

-- 2. Backfill: asignar el mismo UUID a todas las filas que
--    comparten (profesor_terapeuta, fecha, hora_inicio, hora_fin).
--    DISTINCT ON garantiza un UUID por grupo.
WITH grupos AS (
    SELECT DISTINCT ON (profesor_terapeuta, fecha, hora_inicio, hora_fin)
        profesor_terapeuta,
        fecha,
        hora_inicio,
        hora_fin,
        gen_random_uuid() AS gid
    FROM sesiones
    ORDER BY profesor_terapeuta, fecha, hora_inicio, hora_fin, id
)
UPDATE sesiones s
SET sesion_grupo_id = g.gid
FROM grupos g
WHERE s.profesor_terapeuta = g.profesor_terapeuta
  AND s.fecha             = g.fecha
  AND s.hora_inicio       = g.hora_inicio
  AND s.hora_fin          = g.hora_fin;

-- 3. Verificar resultado
SELECT
    sesion_grupo_id,
    profesor_terapeuta,
    fecha,
    hora_inicio,
    hora_fin,
    COUNT(*) AS num_filas
FROM sesiones
GROUP BY sesion_grupo_id, profesor_terapeuta, fecha, hora_inicio, hora_fin
HAVING COUNT(*) > 1
ORDER BY fecha DESC;
-- Las filas devueltas son clases grupales (correcto).
-- Si no devuelve nada, todos son individuales hasta la fecha.
