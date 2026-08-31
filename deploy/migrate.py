#!/usr/bin/env python3
"""
Aplicador de migraciones para la base auto-alojada.

A partir de ahora, en vez de copiar/pegar SQL en un editor web, las migraciones
se versionan como archivos .sql en el repo y se aplican con este script,
conectando por el TÚNEL SSH (localhost:5432).

Sirve contra CUALQUIER Postgres, no solo el auto-alojado: basta la cadena de
conexión. Con la base todavía en Supabase, la de Settings -> Database del panel
(sirve igual y evita el copiar/pegar en el editor web).

Uso:
    # Base en Supabase (hoy):
    DATABASE_URL="postgresql://postgres:PASS@db.PROYECTO.supabase.co:5432/postgres"         python deploy/migrate.py --dry-run
    # Base auto-alojada, con el túnel abierto (ssh -L 5432:localhost:5432 user@servidor):
    DATABASE_URL="postgres://postgres:PASS@localhost:5432/atlas" python deploy/migrate.py

Busca archivos en  migrations/*.sql  (orden alfabético) y aplica los que falten.
Lleva el control en la tabla  public._migraciones.

--marcar-hasta NOMBRE registra migraciones como aplicadas SIN ejecutarlas. Es
para estrenar el control de versiones sobre una base que ya venía al día porque
las corrieron a mano en el editor web: sin eso, la primera corrida intentaría
reaplicarlas todas. NO usarlo para saltarse una migración que de verdad falta.
"""
import os
import sys
import glob

# La consola de Windows abre stdout en cp1252 y ahí un '✔' revienta con
# UnicodeEncodeError. Pasaba DESPUÉS de tocar la base: la migración quedaba
# aplicada pero el script moría con una traza que parecía un fallo del SQL.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

try:
    import psycopg
except ImportError:
    sys.exit("Falta psycopg. Instala con:  pip install 'psycopg[binary]'")

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR_MIGRACIONES = os.path.join(RAIZ, "migrations")


def conectar():
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("Define DATABASE_URL (postgres://usuario:pass@localhost:5432/atlas)")
    return psycopg.connect(url, autocommit=False)


def asegurar_tabla(con):
    with con.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS public._migraciones (
                nombre TEXT PRIMARY KEY,
                aplicada_en TIMESTAMPTZ DEFAULT now()
            )""")
    con.commit()


def aplicadas(con):
    with con.cursor() as cur:
        cur.execute("SELECT nombre FROM public._migraciones")
        return {r[0] for r in cur.fetchall()}


def marcar_hasta(con, archivos, ya, hasta):
    """Registra como aplicadas las migraciones hasta `hasta` (inclusive) sin
    ejecutar una sola línea de SQL. `hasta` puede ser el nombre completo del
    archivo o solo su número ('0009')."""
    nombres = [os.path.basename(a) for a in archivos]
    coincide = [n for n in nombres if n == hasta or n.startswith(hasta)]
    if not coincide:
        sys.exit(f"No hay ninguna migración que coincida con '{hasta}'.\n"
                 f"Disponibles: {', '.join(nombres)}")
    if len(coincide) > 1:
        sys.exit(f"'{hasta}' coincide con varias ({', '.join(coincide)}); sé más específico.")
    corte = nombres.index(coincide[0])
    marcar = [n for n in nombres[:corte + 1] if n not in ya]
    if not marcar:
        print("✔ Ya estaban todas registradas, no hay nada que marcar.")
        return
    print("Se registrarán como YA APLICADAS (no se ejecuta su SQL):")
    for n in marcar:
        print("  -", n)
    print("\nSolo es correcto si esas migraciones ya se corrieron a mano en la base.")
    if input("Escribe 'si' para confirmar: ").strip().lower() != "si":
        sys.exit("Cancelado, no se registró nada.")
    with con.cursor() as cur:
        for n in marcar:
            cur.execute("INSERT INTO public._migraciones(nombre) VALUES (%s)", (n,))
    con.commit()
    print(f"\n✔ {len(marcar)} migraciones registradas. "
          f"La próxima corrida solo aplicará las posteriores.")


def main():
    dry = "--dry-run" in sys.argv
    hasta = None
    if "--marcar-hasta" in sys.argv:
        i = sys.argv.index("--marcar-hasta")
        if i + 1 >= len(sys.argv):
            sys.exit("--marcar-hasta necesita el nombre (o el número) de una migración.")
        hasta = sys.argv[i + 1]
    archivos = sorted(glob.glob(os.path.join(DIR_MIGRACIONES, "*.sql")))
    if not archivos:
        print(f"No hay archivos en {DIR_MIGRACIONES}")
        return
    con = conectar()
    asegurar_tabla(con)
    ya = aplicadas(con)
    if hasta:
        marcar_hasta(con, archivos, ya, hasta)
        return
    pendientes = [a for a in archivos if os.path.basename(a) not in ya]
    if not pendientes:
        print("✔ Base al día, no hay migraciones pendientes.")
        return
    print(f"Pendientes ({len(pendientes)}):")
    for a in pendientes:
        print("  -", os.path.basename(a))
    if dry:
        return
    for a in pendientes:
        nombre = os.path.basename(a)
        sql = open(a, encoding="utf-8").read()
        print(f"\n▶ Aplicando {nombre} ...")
        try:
            with con.cursor() as cur:
                cur.execute(sql)
                cur.execute("INSERT INTO public._migraciones(nombre) VALUES (%s)", (nombre,))
            con.commit()
            print(f"  ✔ {nombre} aplicada")
        except Exception as e:
            con.rollback()
            sys.exit(f"  [X] ERROR en {nombre}: {e}\n(Se revirtio esta migracion; corrige y reintenta.)")
    print("\n✔ Migraciones completadas.")


if __name__ == "__main__":
    main()
