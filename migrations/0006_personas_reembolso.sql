-- 0006 — Personas a las que se les puede reembolsar un gasto
-- Aplicar en el SQL Editor del proyecto Supabase de Atlas (el archivo entero),
-- o con deploy/migrate.py cuando la base ya esté auto-alojada.

-- Hasta ahora la lista de «Reembolsar a» era la constante SOCIOS del código:
-- solo los tres socios podían recibir un reembolso, y sumar a alguien más
-- exigía tocar app.py y desplegar. Esta tabla guarda las personas EXTRA que se
-- crean desde /gastos; los socios se siguen incluyendo siempre desde el código,
-- así que si esta tabla no existiera todavía la aplicación sigue funcionando
-- exactamente como antes.
CREATE TABLE IF NOT EXISTS personas_reembolso (
    id         bigserial PRIMARY KEY,
    nombre     text NOT NULL,
    -- Baja lógica: al quitar una persona NO se borra la fila, porque los gastos
    -- ya reembolsados guardan el nombre como texto en gastos.reembolsado_a y
    -- perderlo dejaría esos reembolsos sin beneficiario en la liquidación.
    activo     boolean NOT NULL DEFAULT true,
    creado_por text,
    creado_en  timestamptz DEFAULT now()
);

-- Un mismo nombre no puede repetirse (ni con otra combinación de mayúsculas):
-- la liquidación agrupa los reembolsos por ese texto y dos variantes del mismo
-- nombre partirían el total de esa persona en dos.
CREATE UNIQUE INDEX IF NOT EXISTS idx_personas_reembolso_nombre
    ON personas_reembolso (lower(nombre));

ALTER TABLE personas_reembolso ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON personas_reembolso FROM anon, authenticated;

-- Si algún gasto ya tiene un beneficiario que no es socio (importado a mano o
-- de una versión anterior), queda registrado como persona válida para que su
-- reembolso siga siendo asignable y pagable.
INSERT INTO personas_reembolso (nombre, creado_por)
SELECT DISTINCT g.reembolsado_a, 'migración 0006'
  FROM gastos g
 WHERE g.reembolsado_a IS NOT NULL
   AND btrim(g.reembolsado_a) <> ''
   AND g.reembolsado_a NOT IN ('Carmen Reinoso', 'Rosalía Moscoso', 'Marco Antonio Posligua')
   AND NOT EXISTS (
        SELECT 1 FROM personas_reembolso p
         WHERE lower(p.nombre) = lower(g.reembolsado_a));
