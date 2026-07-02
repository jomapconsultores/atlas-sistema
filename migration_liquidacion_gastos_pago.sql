-- Ejecutar una vez en Supabase (SQL Editor → Run).

-- Parte 1: porcentaje del balance positivo que se reparte a los socios (0–100).
alter table liquidaciones add column if not exists porcentaje_reparto numeric default 100;

-- Parte 2: registrar el pago de cada gasto (además de los reembolsos).
alter table gastos add column if not exists pagado boolean default false;
alter table gastos add column if not exists fecha_pago date;
