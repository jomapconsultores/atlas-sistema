-- 0005 — Varias marcaciones en el mismo día (doble jornada)
-- Aplicar en el SQL Editor del proyecto Supabase de Atlas (el archivo entero),
-- o con deploy/migrate.py cuando la base ya esté auto-alojada.

-- Hasta ahora cada persona tenía UN ingreso y UNA salida por día, y quien
-- trabaja doble jornada (mañana y tarde, con un corte al mediodía) no podía
-- marcar el regreso: el sistema le decía «ya marcaste tu ingreso hoy» y las
-- horas del día salían mal (contaba desde la primera entrada hasta la última
-- salida, almuerzo incluido, o directamente perdía la tarde).
--
-- La solución NO es partir el día en varias filas de 'marcaciones': ahí viven
-- datos que son del DÍA y no del tramo (permiso, horas extra y su recargo), y
-- duplicarlos rompería el reporte. Se añade una tabla hija con los tramos:
-- 'marcaciones' sigue siendo el registro del día —y guarda el primer ingreso
-- y la última salida, para que todo lo que ya los leía siga funcionando— y
-- 'marcaciones_tramos' guarda cada entrada/salida real.
CREATE TABLE IF NOT EXISTS marcaciones_tramos (
    id bigserial PRIMARY KEY,
    marcacion_id bigint NOT NULL REFERENCES marcaciones(id) ON DELETE CASCADE,
    -- usuario_id y fecha se repiten desde la marcación a propósito: así el mes
    -- de una persona se consulta por rango de fechas directamente sobre esta
    -- tabla, igual que se consulta 'marcaciones', sin traer antes los ids.
    usuario_id bigint NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    fecha date NOT NULL,
    hora_ingreso time NOT NULL,
    hora_salida time,
    creado_en timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tramos_usuario_fecha ON marcaciones_tramos(usuario_id, fecha);

CREATE INDEX IF NOT EXISTS idx_tramos_marcacion ON marcaciones_tramos(marcacion_id);

-- Un solo tramo abierto por persona y día: dos ingresos seguidos sin salida de
-- por medio no son una doble jornada, son un error de marcación. Se prohíbe en
-- la base y no solo en la aplicación (dos pestañas abiertas bastaban).
-- Se acota al día para que una salida olvidada ayer no bloquee el ingreso de
-- hoy: ese día queda «sin cerrar» en el reporte, como hasta ahora.
CREATE UNIQUE INDEX IF NOT EXISTS idx_tramos_abierto_unico
    ON marcaciones_tramos(usuario_id, fecha) WHERE hora_salida IS NULL;

ALTER TABLE marcaciones_tramos ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON marcaciones_tramos FROM anon, authenticated;

-- Las marcaciones que ya existen pasan a ser su primer (y único) tramo, para
-- que el historial anterior se lea con la misma regla que el nuevo.
INSERT INTO marcaciones_tramos (marcacion_id, usuario_id, fecha, hora_ingreso, hora_salida)
SELECT m.id, m.usuario_id, m.fecha, m.hora_ingreso, m.hora_salida
  FROM marcaciones m
 WHERE m.hora_ingreso IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM marcaciones_tramos t WHERE t.marcacion_id = m.id);
