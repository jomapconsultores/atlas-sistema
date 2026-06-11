-- Anticipos: estado 'descontado' (ya restado de un pago al docente).
-- Ejecutar en el SQL Editor de Supabase. El código funciona sin esta columna
-- (guarda solo el estado), pero con ella se registra la fecha del descuento.
ALTER TABLE anticipos_solicitudes ADD COLUMN IF NOT EXISTS fecha_descuento date;
