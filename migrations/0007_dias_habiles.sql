-- 0007 — Los días exigidos del mes salen del calendario, no de un número fijo
-- Aplicar en el SQL Editor del proyecto Supabase de Atlas (el archivo entero),
-- o con deploy/migrate.py cuando la base ya esté auto-alojada.
--
-- Hasta ahora cada jornada guardaba 'dias_mes' a mano (22 por defecto) y el
-- sueldo proporcional se calculaba contra ese número, cayera como cayera el
-- calendario. Agosto de 2026 tiene 21 días de lunes a viernes y uno es feriado
-- (el 10), así que lo máximo trabajable son 20 días: con 22 exigidos, quien no
-- faltó un solo día cobraba 160/176 = 90.9% de su sueldo. El feriado y los
-- meses cortos le descontaban dinero a la persona.
--
-- Ahora los días exigidos se cuentan del mes real —lunes a viernes menos los
-- feriados de esta tabla— y 'dias_mes' queda como respaldo para quien no sigue
-- el calendario de oficina (por ejemplo, quien trabaja sábados).

-- 1) Feriados. Es una TABLA y no un cálculo dentro de la aplicación a
--    propósito: las reglas de traslado del Art. 65 del Código del Trabajo
--    tienen excepciones que un algoritmo aplica mal. En 2026, sin ir más
--    lejos, el 3 de noviembre cae martes y la regla genérica lo mandaría al
--    lunes 2, que ya es Día de los Difuntos: las dos fiestas colapsarían en un
--    día y se perdería una jornada de descanso. Con una tabla, las fechas se
--    ven, se auditan y se corrigen; con un algoritmo, el error es invisible y
--    mueve sueldos.
CREATE TABLE IF NOT EXISTS feriados (
    fecha date PRIMARY KEY,
    descripcion text NOT NULL,
    creado_en timestamptz DEFAULT now()
);

ALTER TABLE feriados ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON feriados FROM anon, authenticated;

-- Feriados nacionales de 2026 con el traslado ya aplicado (fecha de DESCANSO
-- efectivo, que es la que importa para contar días trabajables):
--   · 24 de mayo cae domingo -> se descansa el lunes 25.
--   · 2 y 3 de noviembre caen lunes y martes: se mantienen ambos, forman el
--     puente y no se trasladan.
-- Los demás caen ya en día laborable. Al empezar 2027 hay que cargar su lista;
-- las fechas móviles (Carnaval y Viernes Santo) dependen de la Pascua.
INSERT INTO feriados (fecha, descripcion) VALUES
    ('2026-01-01', 'Año Nuevo'),
    ('2026-02-16', 'Carnaval'),
    ('2026-02-17', 'Carnaval'),
    ('2026-04-03', 'Viernes Santo'),
    ('2026-05-01', 'Día del Trabajo'),
    ('2026-05-25', 'Batalla de Pichincha (trasladado del domingo 24)'),
    ('2026-08-10', 'Primer Grito de Independencia'),
    ('2026-10-09', 'Independencia de Guayaquil'),
    ('2026-11-02', 'Día de los Difuntos'),
    ('2026-11-03', 'Independencia de Cuenca'),
    ('2026-12-25', 'Navidad')
ON CONFLICT (fecha) DO NOTHING;

-- 2) Interruptor por persona. Activado (lo normal) los días exigidos se cuentan
--    del calendario; desactivado manda el 'dias_mes' de siempre.
ALTER TABLE jornadas_laborales
    ADD COLUMN IF NOT EXISTS dias_automaticos boolean NOT NULL DEFAULT true;
