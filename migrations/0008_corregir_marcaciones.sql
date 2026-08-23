-- 0008 — Corregir una entrada o una salida mal marcada
-- Aplicar en el SQL Editor del proyecto Supabase de Atlas (el archivo entero),
-- o con deploy/migrate.py cuando la base ya esté auto-alojada.
--
-- Hasta ahora una marcación era intocable: los únicos ajustes eran las horas
-- extra y el permiso del día. Quien olvidaba marcar su salida dejaba el tramo
-- abierto PARA SIEMPRE —el reporte no cuenta las horas de un tramo sin cerrar,
-- así que ese día valía 0— y no había forma de arreglarlo desde la aplicación.
-- El único apaño era marcar el día «con permiso», que dice algo que no pasó.
--
-- Corregir la hora de otra persona toca su sueldo, así que no se hace en
-- silencio: cada corrección guarda quién la hizo, cuándo y por qué.
ALTER TABLE marcaciones_tramos ADD COLUMN IF NOT EXISTS corregido_por text;

ALTER TABLE marcaciones_tramos ADD COLUMN IF NOT EXISTS corregido_en timestamptz;

ALTER TABLE marcaciones_tramos ADD COLUMN IF NOT EXISTS motivo_correccion text;
