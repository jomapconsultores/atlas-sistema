# Atlas — Base de datos auto-alojada (Hetzner)

Reemplaza la dependencia de la Supabase en la nube por un stack propio en tu
servidor, **sin tocar el código de la app** (solo cambian 2 variables de entorno).

## Qué levanta

| Servicio | Imagen | Para qué |
|---|---|---|
| `db` | postgres:15 | Los datos |
| `rest` | postgrest | API REST `/rest/v1/` (lo que usa `supabase.table()`) |
| `adminer` | adminer | Panel web para ver/editar datos (`/adminer/`) |
| `proxy` | caddy | Enruta `/rest/v1/*` y `/adminer/*`; HTTPS automático |

La app sigue usando el cliente de Supabase: apunta `SUPABASE_URL` a este servidor
y `SUPABASE_KEY` a la clave **anon** generada con `gen_keys.py`.

---

## 1. Preparar el servidor (una vez)

```bash
# En el Hetzner (Ubuntu/Debian):
curl -fsSL https://get.docker.com | sh        # Docker + compose plugin
```

## 2. Subir esta carpeta y configurar

```bash
# Copiar la carpeta deploy/ al servidor (scp/git). Luego, dentro de deploy/:
cp .env.example .env
nano .env            # rellenar contraseñas y JWT_SECRET (32+ chars)
```

Genera el `JWT_SECRET` y las contraseñas con, por ejemplo:
```bash
openssl rand -base64 48     # úsalo para JWT_SECRET / POSTGRES_PASSWORD / AUTHENTICATOR_PASSWORD
```

## 3. Arrancar

```bash
docker compose up -d
docker compose ps          # todos "healthy/up"
```

## 4. Generar las claves de la app

```bash
pip install PyJWT           # o: docker run --rm -e JWT_SECRET=... python:3.12 ...
JWT_SECRET="<el de tu .env>" python gen_keys.py
```
Copia la clave **anon** → será `SUPABASE_KEY` en la app.
`SUPABASE_URL` será `https://TU_DOMINIO` (o `http://IP` si no usas dominio).

---

## 5. Migrar los datos desde la Supabase actual

```bash
# Dump de la nube (necesita la connection string de Supabase → Settings → Database):
pg_dump "postgresql://postgres:PASS@db.naubddczohedvtywmmmy.supabase.co:5432/postgres" \
        --no-owner --no-privileges --schema=public > atlas_dump.sql

# Restaurar en el servidor nuevo:
docker compose exec -T db psql -U postgres -d atlas < atlas_dump.sql
```

> Si prefieres no exponer Postgres, corre el `pg_dump` desde tu PC y el restore
> por el túnel SSH (ver abajo).

---

## 6. Repuntar la app

En el entorno de la app (Coolify o local), cambia:
```
SUPABASE_URL=https://TU_DOMINIO         # o http://IP
SUPABASE_KEY=<clave anon de gen_keys.py>
```
Nada más. El resto del código es idéntico.

---

## Migraciones a futuro (adiós al copiar/pegar SQL)

Las migraciones viven versionadas en `../migrations/*.sql` y se aplican con
`../deploy/migrate.py` por el **túnel SSH**:

```bash
# En TU PC, abre el túnel (deja la terminal abierta):
ssh -L 5432:localhost:5432 usuario@IP_DEL_SERVIDOR

# En otra terminal:
DATABASE_URL="postgres://postgres:PASS@localhost:5432/atlas" python deploy/migrate.py --dry-run
DATABASE_URL="postgres://postgres:PASS@localhost:5432/atlas" python deploy/migrate.py
```

Con esto, cuando yo (Claude) necesite crear/alterar tablas, agrego un archivo
`migrations/000X_descripcion.sql` y lo aplico por el túnel — **sin paneles web**.

## Seguridad

- Postgres se publica solo en `127.0.0.1` del servidor; desde tu PC se llega por
  túnel SSH. No queda expuesto a internet.
- Solo el proxy (80/443) mira a internet. Usa un dominio para que Caddy ponga HTTPS.
- Rota el `JWT_SECRET` y las contraseñas si alguna vez se filtran.
