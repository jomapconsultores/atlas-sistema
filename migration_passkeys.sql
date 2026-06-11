-- Passkeys (WebAuthn): inicio de sesión con huella digital / reconocimiento
-- facial desde el celular o la laptop. Cada fila es un dispositivo registrado
-- por un usuario. Ejecutar una vez en el SQL Editor de Supabase.
CREATE TABLE IF NOT EXISTS usuario_passkeys (
  id bigserial PRIMARY KEY,
  usuario_id bigint NOT NULL,
  credential_id text UNIQUE NOT NULL,
  public_key text NOT NULL,
  sign_count bigint DEFAULT 0,
  nombre text DEFAULT '',
  created_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_passkeys_usuario ON usuario_passkeys(usuario_id);
