-- 0003 — Permiso del día y hora extra sin recargo
-- Aplicar con deploy/migrate.py (túnel SSH al Postgres propio; ver
-- deploy/README.md). Ya no hay editor SQL en la nube: la base es nuestra.

-- 1) Permiso: el día en que la persona salió antes con autorización se le paga
--    igual la jornada completa. Sin esto, con el sueldo calculado por horas,
--    una salida autorizada le descontaba dinero.
ALTER TABLE marcaciones ADD COLUMN IF NOT EXISTS con_permiso boolean NOT NULL DEFAULT false;

ALTER TABLE marcaciones ADD COLUMN IF NOT EXISTS motivo_permiso text;

-- 2) 'normal' se suma a los tipos de hora extra: horas fuera de la jornada que
--    se pagan al valor hora, SIN recargo (acuerdo interno, compensaciones).
ALTER TABLE marcaciones DROP CONSTRAINT IF EXISTS marcaciones_tipo_extra_check;

ALTER TABLE marcaciones ADD CONSTRAINT marcaciones_tipo_extra_check
    CHECK (tipo_extra IS NULL OR tipo_extra IN ('normal', 'suplementaria', 'extraordinaria', 'nocturna'));
