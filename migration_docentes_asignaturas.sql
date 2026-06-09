-- ============================================================
-- Migración: tablas DOCENTES y ASIGNATURAS
-- Ejecutar en Supabase → SQL Editor (una sola vez para la semilla).
-- ============================================================

-- ---------- TABLAS ----------
CREATE TABLE IF NOT EXISTS docentes (
    id          bigserial PRIMARY KEY,
    nombres     text NOT NULL,
    apellidos   text NOT NULL,
    asignaturas text,                     -- asignaturas asignadas (separadas por coma)
    email       text,
    telefono    text,
    tipo        text DEFAULT 'profesor',  -- profesor | psicologo
    activo      boolean DEFAULT true,
    created_at  timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS asignaturas (
    id          bigserial PRIMARY KEY,
    nombre      text NOT NULL,
    activo      boolean DEFAULT true,
    created_at  timestamptz DEFAULT now()
);

-- ---------- SEMILLA (correr una sola vez) ----------
INSERT INTO docentes (nombres, apellidos, tipo) VALUES
('Carmen','Reinoso','profesor'),
('Rosalía','Moscoso','profesor'),
('Marco Antonio','Posligua','profesor'),
('Edwin','Rumipulla','profesor'),
('Catherine','Alvear','profesor'),
('Alexander','Nivelo','profesor'),
('Daniel','Castillo','profesor'),
('Johanna','Nievecela','profesor');

INSERT INTO asignaturas (nombre) VALUES
('Contabilidad general'),('Contabilidad de costos'),('Matemáticas'),('Geometría'),
('Cálculo diferencial'),('Cálculo integral'),('Física'),('Química'),('Biología'),
('Genética'),('Anatomía'),('Inglés'),('Lengua y Literatura'),('Matemáticas financieras'),
('Análisis financiero'),('Bioquímica'),('CCNN'),('Informática'),('Asesoría tesis'),
('Pre universitario - Matemáticas'),('Pre universitario - CCNN'),
('Pre universitario - Literatura'),('Pre universitario - Motivación');
