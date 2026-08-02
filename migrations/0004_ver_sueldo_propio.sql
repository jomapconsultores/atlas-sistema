-- 0004 — Permitir que una persona vea su propio sueldo
-- Aplicar en el SQL Editor del proyecto Supabase de Atlas.

-- Hasta ahora, quien tuviera jornada configurada veía su proporcional en
-- «Mi asistencia» sin que nadie lo hubiera autorizado. Ahora es una casilla
-- por persona, y el valor por defecto es NO: el sueldo es dato sensible y
-- mostrarlo debe ser una decisión explícita de quien administra.
ALTER TABLE jornadas_laborales
    ADD COLUMN IF NOT EXISTS ver_sueldo boolean NOT NULL DEFAULT false;
