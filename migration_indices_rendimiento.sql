-- Índices de rendimiento: aceleran las consultas más frecuentes del sistema
-- (sesiones por estudiante/fecha/estado, pagos por estudiante/fecha, etc.)
-- Ejecutar una vez en el SQL Editor de Supabase. Inofensivo si ya existen.
CREATE INDEX IF NOT EXISTS idx_sesiones_estudiante ON sesiones(estudiante_id);
CREATE INDEX IF NOT EXISTS idx_sesiones_fecha ON sesiones(fecha);
CREATE INDEX IF NOT EXISTS idx_sesiones_estado ON sesiones(estado);
CREATE INDEX IF NOT EXISTS idx_pagos_estudiante ON pagos(estudiante_id);
CREATE INDEX IF NOT EXISTS idx_pagos_fecha ON pagos(fecha_pago);
CREATE INDEX IF NOT EXISTS idx_devoluciones_estudiante ON devoluciones(estudiante_id);
CREATE INDEX IF NOT EXISTS idx_gastos_periodo ON gastos(anio_periodo, mes_periodo);
CREATE INDEX IF NOT EXISTS idx_movs_fecha ON movimientos_cuenta(fecha);
CREATE INDEX IF NOT EXISTS idx_anticipos_estado ON anticipos_solicitudes(estado);
