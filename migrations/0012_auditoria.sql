-- 0012 — Bitácora de cambios: qué se tocó, quién lo tocó y a qué hora
-- Aplicar con deploy/migrate.py (túnel SSH al Postgres propio; ver
-- deploy/README.md). Ya no hay editor SQL en la nube: la base es nuestra.
--
-- Hasta ahora el rastro de lo que pasa en el sistema estaba repartido y era
-- parcial: 'correcciones_pagos' guarda los cambios de un pago de estudiante,
-- 'marcaciones_tramos' guarda quién corrigió una marcación, y varias tablas
-- tienen un 'registrado_por' con la fecha de creación. Nada de eso cuenta las
-- ediciones ni las eliminaciones del resto del sistema, y no había una sola
-- pantalla donde mirar. Cuando una cifra amanecía distinta, la única respuesta
-- posible era «alguien lo cambió», sin saber quién ni cuándo.
--
-- Esta tabla es ese registro único. No la escribe cada pantalla a mano —eso
-- garantiza olvidos— sino el propio cliente de base de datos: toda escritura
-- que sale de la aplicación (alta, cambio o borrado, en cualquier tabla) deja
-- aquí su línea, con la hora exacta, quién estaba en sesión y el valor
-- anterior junto al nuevo. Lo que no se toca no aparece: las consultas de
-- lectura no se registran.

CREATE TABLE IF NOT EXISTS auditoria (
    id             bigserial PRIMARY KEY,
    -- Momento exacto del cambio. En UTC: la pantalla lo muestra en la hora de
    -- Ecuador, que es donde se trabaja.
    ocurrido_en    timestamptz NOT NULL DEFAULT now(),
    -- Quién. Se guarda el NOMBRE además del id porque el reporte se lee por
    -- nombre y una cuenta borrada no debe dejar la línea sin autor.
    usuario_id     bigint,
    usuario_nombre text,
    usuario_rol    text,
    -- Qué se hizo: crear | editar | eliminar.
    accion         text NOT NULL,
    -- Sobre qué: la tabla, su nombre legible y el módulo al que pertenece
    -- (Finanzas, Académico…), que es como se filtra en la pantalla.
    tabla          text NOT NULL,
    entidad        text,
    modulo         text,
    -- A qué fila. Puede quedar vacío en un cambio masivo (varias filas de una
    -- sola vez): para ese caso está 'filas', que dice a cuántas alcanzó.
    registro_id    text,
    filas          integer,
    -- Una línea en español, ya armada, para leer el reporte sin abrir detalles.
    descripcion    text,
    -- El detalle completo: valores anteriores y nuevos, y los filtros con los
    -- que se ubicó la fila. jsonb para poder consultarlo después.
    antes          jsonb,
    despues        jsonb,
    filtros        text,
    -- De dónde vino: la pantalla (endpoint de Flask) y la IP.
    endpoint       text,
    ip             text
);

-- El reporte se abre siempre por lo más reciente, y se filtra por persona,
-- módulo y fecha. Un índice por cada uno de esos caminos.
CREATE INDEX IF NOT EXISTS idx_auditoria_ocurrido  ON auditoria (ocurrido_en DESC);
CREATE INDEX IF NOT EXISTS idx_auditoria_usuario   ON auditoria (usuario_nombre, ocurrido_en DESC);
CREATE INDEX IF NOT EXISTS idx_auditoria_modulo    ON auditoria (modulo, ocurrido_en DESC);
CREATE INDEX IF NOT EXISTS idx_auditoria_tabla     ON auditoria (tabla, ocurrido_en DESC);

-- Mismo blindaje que el resto de tablas sensibles: la alcanzan 'postgres' y
-- 'service_role' y nadie más. La clave anon de este proyecto quedó publicada
-- en el historial de un repositorio público, y una bitácora que cualquiera
-- pudiera EDITAR o BORRAR no sirve de bitácora.
ALTER TABLE auditoria ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON auditoria FROM anon, authenticated;
