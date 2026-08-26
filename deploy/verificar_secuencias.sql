-- ============================================================
-- Secuencias después de una migración de datos
--
-- Es la comprobación que hay que hacer SIEMPRE que los datos se copian con
-- INSERT/SELECT en vez de con pg_dump/pg_restore. Al insertar las filas con su
-- id explícito, el contador de la secuencia NO avanza: se queda en 1. La base
-- parece perfecta —todas las filas están, los conteos cuadran— y revienta en el
-- primer INSERT nuevo con «duplicate key value violates unique constraint».
--
-- En atlas eso significa que la primera persona que marque su ingreso, o el
-- primer pago que se registre, falla. No es un fallo de lectura: la migración
-- se ve bien hasta que alguien escribe.
--
-- Uso: ejecutar la PARTE 1 en la base NUEVA. Si alguna fila sale como
-- 'DESALINEADA', ejecutar la PARTE 2.
-- ============================================================

-- ---------- PARTE 1 · Diagnóstico ----------
-- Compara el mayor id que existe de verdad en cada tabla con el contador de su
-- secuencia. El máximo se saca con SQL dinámico (query_to_xml) porque cada
-- tabla tiene su propia columna y no se puede escribir en una consulta plana.
WITH seriales AS (
    SELECT c.table_schema AS esquema,
           c.table_name   AS tabla,
           c.column_name  AS columna,
           pg_get_serial_sequence(quote_ident(c.table_schema) || '.' || quote_ident(c.table_name),
                                  c.column_name) AS secuencia
      FROM information_schema.columns c
     WHERE c.table_schema = 'public'
),
medido AS (
    SELECT s.tabla,
           s.columna,
           s.secuencia,
           COALESCE((xpath('/row/max/text()',
                           query_to_xml(format('SELECT max(%I) AS max FROM %I.%I',
                                               s.columna, s.esquema, s.tabla),
                                        false, true, '')))[1]::text::bigint, 0) AS max_real,
           q.last_value AS contador
      FROM seriales s
      LEFT JOIN pg_sequences q
             ON q.schemaname || '.' || q.sequencename = s.secuencia
     WHERE s.secuencia IS NOT NULL
)
SELECT tabla,
       columna,
       max_real,
       contador,
       CASE
           WHEN max_real = 0                        THEN 'tabla vacía'
           WHEN contador IS NULL                    THEN 'DESALINEADA (secuencia sin usar)'
           WHEN contador < max_real                 THEN 'DESALINEADA (el próximo id ya existe)'
           ELSE 'correcta'
       END AS estado
  FROM medido
 ORDER BY (CASE WHEN contador IS NULL OR contador < max_real THEN 0 ELSE 1 END),
          tabla;


-- ---------- PARTE 2 · Corrección ----------
-- Recoloca cada secuencia en el máximo real. Es idempotente: se puede repetir.
-- Con la tabla vacía deja la secuencia en 1 sin marcarla como usada.
DO $$
DECLARE
    r record;
    maximo bigint;
BEGIN
    FOR r IN
        SELECT c.table_schema AS esquema,
               c.table_name   AS tabla,
               c.column_name  AS columna,
               pg_get_serial_sequence(quote_ident(c.table_schema) || '.' || quote_ident(c.table_name),
                                      c.column_name) AS secuencia
          FROM information_schema.columns c
         WHERE c.table_schema = 'public'
           AND pg_get_serial_sequence(quote_ident(c.table_schema) || '.' || quote_ident(c.table_name),
                                      c.column_name) IS NOT NULL
    LOOP
        EXECUTE format('SELECT COALESCE(max(%I), 0) FROM %I.%I', r.columna, r.esquema, r.tabla)
           INTO maximo;
        IF maximo > 0 THEN
            -- is_called = true: el siguiente nextval devuelve maximo + 1
            PERFORM setval(r.secuencia, maximo, true);
            RAISE NOTICE 'setval %  ->  % (tabla %)', r.secuencia, maximo, r.tabla;
        ELSE
            PERFORM setval(r.secuencia, 1, false);
            RAISE NOTICE 'setval %  ->  1 sin usar (tabla % vacía)', r.secuencia, r.tabla;
        END IF;
    END LOOP;
END $$;


-- ---------- PARTE 3 · Prueba de que de verdad se puede escribir ----------
-- Un conteo correcto no prueba que la base sirva. Esto sí: inserta y borra.
-- Sobre 'feriados' porque no tiene claves ajenas que arrastren nada.
BEGIN;
INSERT INTO feriados (fecha, descripcion) VALUES (DATE '1999-12-31', 'prueba de escritura');
SELECT count(*) AS debe_ser_1 FROM feriados WHERE fecha = DATE '1999-12-31';
ROLLBACK;
