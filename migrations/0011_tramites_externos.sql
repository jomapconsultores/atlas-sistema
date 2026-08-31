-- 0011 — Trámites fuera del centro: trabajo que existe aunque no haya marcación
-- Aplicar en el SQL Editor del proyecto Supabase de Atlas (el archivo entero),
-- o con deploy/migrate.py cuando la base ya esté auto-alojada.
--
-- Secretaría hace gestiones fuera: el banco, el SRI, la imprenta, un trámite
-- en el municipio. Ese tiempo es trabajo, pero no hay dónde marcar: o el día
-- sale corto, o directamente sin marcación, y el reporte del mes lo cuenta
-- como incumplimiento. La única salida era corregir marcaciones a mano, que
-- deja el registro diciendo algo que no pasó (una entrada al centro que no
-- hubo) y sin rastro de para qué fue la salida.
--
-- Aquí el trámite se registra por lo que es: un tramo de trabajo fuera, con lo
-- que se fue a hacer escrito. Queda PENDIENTE hasta que un socio o el
-- administrador lo aprueba; recién entonces suma horas, igual que un tramo
-- marcado. Sin aprobar no suma nada: afecta al sueldo, así que lo firma
-- alguien, como los anticipos y los pagos excepcionales.

CREATE TABLE IF NOT EXISTS tramites_externos (
    id                bigserial PRIMARY KEY,
    usuario_id        bigint      NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    fecha             date        NOT NULL,
    hora_inicio       time        NOT NULL,
    hora_fin          time        NOT NULL,
    lugar             text,                  -- adónde fue (banco, SRI, imprenta…)
    detalle           text        NOT NULL,  -- qué fue a hacer: es el reporte
    estado            text        NOT NULL DEFAULT 'pendiente',
    registrado_en     timestamptz NOT NULL DEFAULT now(),
    resuelto_por      text,                  -- socio/admin que aprobó o rechazó
    fecha_resolucion  timestamptz,
    motivo_rechazo    text,
    CONSTRAINT ck_tramite_estado CHECK (estado IN ('pendiente', 'aprobado', 'rechazado')),
    -- Un trámite ocurre dentro del día: sin esto, un fin anterior al inicio
    -- daría horas negativas o, peor, un turno cruzado de 20 horas.
    CONSTRAINT ck_tramite_horario CHECK (hora_fin > hora_inicio)
);

CREATE INDEX IF NOT EXISTS idx_tramites_usuario_fecha ON tramites_externos (usuario_id, fecha);
CREATE INDEX IF NOT EXISTS idx_tramites_estado        ON tramites_externos (estado);

-- Las horas NO se guardan aquí. Se calculan al leer, con la misma regla que
-- las marcaciones (el día entero se redondea junto, no tramo a tramo): un
-- número guardado se quedaría viejo en cuanto esa regla cambie.

ALTER TABLE tramites_externos DISABLE ROW LEVEL SECURITY;

-- ---------- Verificación ----------
SELECT t.id, u.nombre, t.fecha, t.hora_inicio, t.hora_fin, t.lugar, t.estado, t.detalle
FROM tramites_externos t
JOIN usuarios u ON u.id = t.usuario_id
ORDER BY t.fecha DESC, t.hora_inicio;
