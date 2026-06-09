-- ============================================================
-- Migración: tablas DOCENTES y ASIGNATURAS
-- Ejecutar en Supabase → SQL Editor
-- ============================================================

-- ---------- DOCENTES ----------
CREATE TABLE IF NOT EXISTS docentes (
    id          bigserial PRIMARY KEY,
    nombres     text NOT NULL,
    apellidos   text NOT NULL,
    asignaturas text,                 -- asignaturas asignadas (separadas por coma)
    email       text,
    telefono    text,
    tipo        text DEFAULT 'profesor',  -- profesor | psicologo
    activo      boolean DEFAULT true,
    created_at  timestamptz DEFAULT now()
);

-- Semilla con los docentes que estaban hardcodeados en app.py.
-- Solo inserta si la tabla está vacía (evita duplicar al re-ejecutar).
INSERT INTO docentes (nombres, apellidos, tipo)
SELECT * FROM (VALUES
    ('Carmen',         'Reinoso',   'profesor'),
    ('Rosalía',        'Moscoso',   'profesor'),
    ('Marco Antonio',  'Posligua',  'profesor'),
    ('Edwin',          'Rumipulla', 'profesor'),
    ('Catherine',      'Alvear',    'profesor'),
    ('Alexander',      'Nivelo',    'profesor'),
    ('Daniel',         'Castillo',  'profesor'),
    ('Johanna',        'Nievecela', 'profesor')
) AS v(nombres, apellidos, tipo)
WHERE NOT EXISTS (SELECT 1 FROM docentes);

-- ---------- ASIGNATURAS ----------
CREATE TABLE IF NOT EXISTS asignaturas (
    id          bigserial PRIMARY KEY,
    nombre      text NOT NULL,
    activo      boolean DEFAULT true,
    created_at  timestamptz DEFAULT now()
);

-- Semilla con las asignaturas que estaban hardcodeadas en app.py.
INSERT INTO asignaturas (nombre)
SELECT * FROM (VALUES
    ('Contabilidad general'), ('Contabilidad de costos'), ('Matemáticas'), ('Geometría'),
    ('Cálculo diferencial'), ('Cálculo integral'), ('Física'), ('Química'), ('Biología'),
    ('Genética'), ('Anatomía'), ('Inglés'), ('Lengua y Literatura'), ('Matemáticas financieras'),
    ('Análisis financiero'), ('Bioquímica'), ('CCNN'), ('Informática'), ('Asesoría tesis'),
    ('Pre universitario - Matemáticas'), ('Pre universitario - CCNN'),
    ('Pre universitario - Literatura'), ('Pre universitario - Motivación')
) AS v(nombre)
WHERE NOT EXISTS (SELECT 1 FROM asignaturas);
