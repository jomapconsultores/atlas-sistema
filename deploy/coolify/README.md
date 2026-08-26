# Mover la base de Atlas y calendario al servidor de Coolify

> Alcance: **solo atlas y calendario**, que comparten el proyecto Supabase
> `naubddczohedvtywmmmy` y solo usan tablas (PostgREST). No entran aquí las apps
> con Auth y Storage — para esas, ver `MIGRACION_SUPABASE_A_HETZNER.md`.

Las dos aplicaciones son el caso más fácil de los nueve proyectos: no usan
GoTrue, ni Storage, ni Realtime, ni Edge Functions. Todo lo que hace falta es un
Postgres y un PostgREST detrás de las mismas rutas que expone Supabase.

## Por qué este compose y no el de `deploy/`

`deploy/docker-compose.yml` está escrito para un VPS vacío: publica los puertos
80 y 443 con su propio Caddy. En el servidor de Coolify esos puertos ya son del
proxy de Coolify, así que levantarlo tal cual **tumba las apps que ya corren
ahí**. Este de aquí:

- no publica puertos: Caddy escucha en la red interna y Coolify le enruta el
  dominio (se configura en la interfaz, no con etiquetas de Traefik — las suyas
  las escribe Coolify y chocarían con las nuestras);
- pone **Postgres 17**, no 15: la Supabase de origen corre 17.x y un dump de 17
  no restaura en 15;
- limita la memoria de cada contenedor. En un servidor compartido, un Postgres
  sin techo es el que se lleva por delante al resto cuando aprieta el OOM killer.

Reutiliza el `Caddyfile` y el `init/` de `deploy/`, así que no hay dos copias que
se vayan separando con el tiempo.

## Antes de empezar: medir

Con 4 GB en el servidor esto va justo. **Medir no es opcional**:

```bash
free -h
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}"
df -h /
```

El stack pide **~0,6–0,8 GB**. Con menos de 1 GB libre, no se despliega: se
amplía el servidor primero. Meterlo a la fuerza no da «un poco lento», da
Postgres muerto de madrugada.

Y el tamaño de la base, desde el editor SQL de Supabase:

```sql
SELECT pg_size_pretty(pg_database_size(current_database()));
```

## Pasos

### 1. Claves

```bash
JWT_SECRET="<32+ caracteres aleatorios>" python ../gen_keys.py
```

Guarda la clave **`service_role`**: es la que va en `SUPABASE_KEY` de las dos
apps. **No la `anon`** — aunque el README de `deploy/` dijera lo contrario, las
apps entran como service_role y `migration_rls_lockdown.sql` revoca a `anon` el
acceso a las tablas. Con la clave anon la app no leería ni una fila.

### 2. Recurso en Coolify

Nuevo recurso → **Docker Compose**, apuntando a este repositorio:

| Campo | Valor |
|---|---|
| Base directory | `/deploy` |
| Compose file | `coolify/docker-compose.yml` |
| Dominio | `db.atlas.pensamiento-libre.org` → servicio `proxy`, puerto `80` |

Variables de entorno: las de `../.env.example` (`POSTGRES_PASSWORD`,
`AUTHENTICATOR_PASSWORD`, `JWT_SECRET`, `ADMINER_AUTH_USER`,
`ADMINER_AUTH_HASH`). `DOMAIN` no se toca: va fijo a `:80`.

### 3. Traer los datos

```bash
# Dump desde Supabase (connection string en Settings → Database)
pg_dump "postgresql://postgres:PASS@db.naubddczohedvtywmmmy.supabase.co:5432/postgres" \
        --no-owner --no-privileges --schema=public > atlas_dump.sql

# Restaurar (desde el terminal del contenedor en Coolify)
psql -U postgres -d atlas < atlas_dump.sql
```

El `init/01_roles.sh` corre solo en el **primer** arranque, con el volumen
vacío: los roles `anon`, `authenticated`, `service_role` y `authenticator`
tienen que existir **antes** del restore, o cada `REVOKE ... FROM anon,
authenticated` del dump falla.

### 4. Repuntar las apps

En Coolify, en **atlas** y en **calendario**:

```
SUPABASE_URL=https://db.atlas.pensamiento-libre.org
SUPABASE_KEY=<clave service_role del paso 1>
```

Redeploy. Ninguna línea de código cambia.

### 5. Comprobar

- `https://atlas.pensamiento-libre.org/version` responde y la app entra;
- las marcaciones y el calendario se leen y se escriben;
- si PostgREST no ve una tabla nueva: `NOTIFY pgrst, 'reload schema';`
- **la Supabase vieja se deja intacta dos semanas** antes de borrar nada.

### 6. Lo que pasa a ser tuyo

En la nube esto venía incluido; aquí no:

- **Backups.** `pg_dump` diario a un Storage Box, retención 30 días, y una
  restauración de prueba al mes. Un backup sin probar no es un backup.
  Ojo: el proyecto Supabase actual está en plan Free y **hoy tampoco tiene
  backups** («No backups» en su panel), así que esto no empeora — pero es la
  ocasión de arreglarlo.
- **Alertas** de disco lleno y de Postgres caído.
- **Migraciones**: se acabó el copiar y pegar en el editor SQL.
  `python deploy/migrate.py` por túnel SSH, que además es mejor que lo de ahora.
