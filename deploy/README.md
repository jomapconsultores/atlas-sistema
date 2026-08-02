# Atlas — Base de datos auto-alojada (Hetzner)

> **Estado a agosto de 2026: esto todavía NO está en uso.** La app sigue
> apuntando a la Supabase en la nube (`naubddczohedvtywmmmy`). Todo lo que
> sigue describe la mudanza **planificada**, no la realidad actual. Para saber
> cómo está desplegada la app hoy y cómo se aplican las migraciones ahora mismo,
> ve a [Cómo está desplegado hoy](#cómo-está-desplegado-hoy-agosto-2026), al final.

Reemplaza la dependencia de la Supabase en la nube por un stack propio en tu
servidor, **sin tocar el código de la app** (solo cambian 2 variables de entorno).

## Qué levanta

| Servicio | Imagen | Para qué |
|---|---|---|
| `db` | postgres:15 | Los datos |
| `rest` | postgrest | API REST `/rest/v1/` (lo que usa `supabase.table()`) |
| `adminer` | adminer | Panel web para ver/editar datos (`/adminer/`, con Basic Auth — ver `ADMINER_AUTH_USER`/`ADMINER_AUTH_HASH`) |
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

> Mientras la base siga en la nube, `migrate.py` **no se usa**: los archivos de
> `migrations/` se pegan en el editor SQL de Supabase. Lo de abajo aplica el día
> que se complete la mudanza. Escribir las migraciones en `migrations/000X_*.sql`
> vale para las dos épocas, así que se hace así desde ya.

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

---

# Cómo está desplegado hoy (agosto 2026)

Esto es lo que hay **en producción ahora**, a diferencia del stack de arriba,
que sigue siendo un plan.

| Pieza | Dónde |
|---|---|
| App | Coolify, aplicación «ATLAS sistema», build pack `nixpacks` |
| Dominio | https://atlas.pensamiento-libre.org |
| Origen del código | GitHub `jomapconsultores/atlas-sistema`, rama **`main`** |
| Base de datos | Supabase **en la nube** (proyecto `naubddczohedvtywmmmy`) |

**Se despliega lo que hay en `main`.** Trabajar en una rama y empujarla no
publica nada: hay que fusionar a `main`.

## Qué versión está corriendo

```
https://atlas.pensamiento-libre.org/version
```

Devuelve el commit que el servidor tiene cargado (lo inyecta Coolify en
`SOURCE_COMMIT`) y desde cuándo lleva ese proceso en marcha. Es la forma de
distinguir «el código no funciona» de «el código no está desplegado» — que es
lo que pasó en julio de 2026, cuando el servidor estuvo 13 días sirviendo un
commit viejo sin que nadie lo notara.

## El despliegue automático va por un webhook manual

El origen configurado en Coolify es la fuente genérica **«Public GitHub»**: no
hay una GitHub App instalada (`app_id` e `installation_id` vienen vacíos). Esa
fuente sabe **clonar** el repositorio —que es público, así que no hacen falta
credenciales— pero **no recibe avisos de push** por sí sola. Durante meses no
hubo auto-deploy por esto: no es que se rompiera, es que nunca estuvo conectado.

Desde agosto de 2026 hay un webhook de `push` en el repositorio que apunta al
endpoint manual de Coolify. **Si algún día deja de desplegarse solo, revísalo
primero** (*Settings → Webhooks*): mira si las entregas recientes salen en rojo
y qué respondió Coolify. Para recrearlo:

| Campo | Valor |
|---|---|
| Payload URL | `http://TU_COOLIFY:8000/webhooks/source/github/events/manual` |
| Content type | `application/json` |
| Secret | el `manual_webhook_secret_github` de la aplicación en Coolify |
| Events | *Just the push event* |

El secreto **no se guarda en este repositorio** (es público): se lee en Coolify,
en la configuración de la aplicación. Coolify cruza el aviso contra
`git_repository` + `git_branch`, así que el webhook vale para toda la app sin
más parámetros.

> GitHub avisará de que la URL no es HTTPS. El secreto firma el payload (HMAC),
> así que nadie puede falsificar un despliegue, pero el contenido viaja en claro
> y el panel de Coolify está expuesto por HTTP. Ponerle un dominio con HTTPS al
> propio Coolify es la asignatura pendiente.

## Desplegar a mano

Desde la interfaz: proyecto → **Deploy**. O por API, con un token de Coolify
(*Keys & Tokens → API tokens*), que **no se guarda aquí**:

```bash
# Encolar el despliegue (el uuid de la app se ve en su URL en Coolify)
curl -X GET "http://TU_COOLIFY:8000/api/v1/deploy?uuid=UUID_DE_LA_APP" \
     -H "Authorization: Bearer $COOLIFY_TOKEN"

# Seguir el estado hasta 'finished'
curl "http://TU_COOLIFY:8000/api/v1/deployments/UUID_DEL_DESPLIEGUE" \
     -H "Authorization: Bearer $COOLIFY_TOKEN"
```

Un despliegue completo tarda entre 45 segundos y 2 minutos y medio. Después,
comprueba `/version`: si el commit no cambió, el despliegue no surtió efecto.

## Migraciones, mientras la base siga en la nube

1. Escribe el archivo en `migrations/000X_descripcion.sql` (idempotente:
   `IF NOT EXISTS` en todo lo que se pueda).
2. Pégalo entero en el **editor SQL** del proyecto Supabase.
3. Si creaste o alteraste tablas, refresca el caché de la API o el cliente
   seguirá diciendo que no existen:
   ```sql
   NOTIFY pgrst, 'reload schema';
   ```
4. **Aplica la migración ANTES de desplegar** el código que la necesita.
   Si no, la app arranca contra columnas que no existen. En julio de 2026 se
   estuvo a punto de publicar el módulo de cuenta sin su migración: el login
   aguantaba (lee con `.get()`), pero editar perfil y cambiar clave habrían
   fallado.

Las migraciones sueltas en la raíz (`migration_*.sql`) son de la época anterior
a `migrations/`. Se conservan por historia; las nuevas van numeradas.
