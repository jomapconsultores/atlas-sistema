#!/usr/bin/env python3
"""
Aplicador de migraciones para la base auto-alojada.

A partir de ahora, en vez de copiar/pegar SQL en un editor web, las migraciones
se versionan como archivos .sql en el repo y se aplican con este script,
conectando por el TÚNEL SSH (localhost:5432).

Uso (con el túnel SSH abierto: ssh -L 5432:localhost:5432 user@servidor):
    DATABASE_URL="postgres://postgres:PASS@localhost:5432/atlas" python deploy/migrate.py
    DATABASE_URL="..." python deploy/migrate.py --dry-run     # solo muestra pendientes

Busca archivos en  migrations/*.sql  (orden alfabético) y aplica los que falten.
Lleva el control en la tabla  public._migraciones.
"""
import os
import sys
import glob

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


def main():
    dry = "--dry-run" in sys.argv
    archivos = sorted(glob.glob(os.path.join(DIR_MIGRACIONES, "*.sql")))
    if not archivos:
        print(f"No hay archivos en {DIR_MIGRACIONES}")
        return
    con = conectar()
    asegurar_tabla(con)
    ya = aplicadas(con)
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
