-- SCRUM-423. Run with the database migration owner before deploying API 0.2.
-- Source rows are never modified by this migration. Future changes are tracked.
BEGIN;
SET LOCAL TIME ZONE 'America/Sao_Paulo';
CREATE SCHEMA IF NOT EXISTS astro_api;
LOCK TABLE public.usuario, public.cargo IN SHARE ROW EXCLUSIVE MODE;

CREATE TABLE IF NOT EXISTS astro_api.history_control (
  singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
  installed_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
INSERT INTO astro_api.history_control(singleton) VALUES (true) ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS astro_api.usuario_history (
  version_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  id_usuario bigint NOT NULL,
  id_unidade bigint,
  cargo_id bigint,
  cargo text,
  tipo text,
  status text,
  criado_em timestamp,
  valid_from timestamptz NOT NULL,
  valid_to timestamptz,
  CHECK (valid_to IS NULL OR valid_to > valid_from)
);
CREATE UNIQUE INDEX IF NOT EXISTS usuario_history_open
  ON astro_api.usuario_history(id_usuario) WHERE valid_to IS NULL;
CREATE INDEX IF NOT EXISTS usuario_history_interval
  ON astro_api.usuario_history(valid_from, valid_to, id_usuario);

INSERT INTO astro_api.usuario_history
  (id_usuario, id_unidade, cargo_id, cargo, tipo, status, criado_em, valid_from)
SELECT u.id_usuario, u.unidade_id, u.cargo_id, NULLIF(LOWER(BTRIM(c.nome)), ''),
  NULLIF(LOWER(BTRIM(u.tipo::text)), ''), NULLIF(LOWER(BTRIM(u.status::text)), ''),
  u.criado_em, clock_timestamp()
FROM public.usuario u LEFT JOIN public.cargo c ON c.id_cargo = u.cargo_id
WHERE NOT EXISTS (SELECT 1 FROM astro_api.usuario_history h
                  WHERE h.id_usuario = u.id_usuario AND h.valid_to IS NULL);

CREATE OR REPLACE FUNCTION astro_api.track_usuario() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public, astro_api AS $$
DECLARE at_time timestamptz := clock_timestamp();
BEGIN
  IF TG_OP = 'UPDATE' AND ROW(NEW.id_usuario, NEW.unidade_id, NEW.cargo_id,
      NEW.tipo, NEW.status, NEW.criado_em) IS NOT DISTINCT FROM
      ROW(OLD.id_usuario, OLD.unidade_id, OLD.cargo_id, OLD.tipo, OLD.status, OLD.criado_em)
    THEN RETURN NEW;
  END IF;
  IF TG_OP <> 'INSERT' THEN
    UPDATE astro_api.usuario_history SET valid_to = at_time
      WHERE id_usuario = OLD.id_usuario AND valid_to IS NULL;
  END IF;
  IF TG_OP <> 'DELETE' THEN
    INSERT INTO astro_api.usuario_history
      (id_usuario, id_unidade, cargo_id, cargo, tipo, status, criado_em, valid_from)
    SELECT NEW.id_usuario, NEW.unidade_id, NEW.cargo_id,
      (SELECT NULLIF(LOWER(BTRIM(c.nome)), '') FROM public.cargo c
       WHERE c.id_cargo = NEW.cargo_id),
      NULLIF(LOWER(BTRIM(NEW.tipo::text)), ''), NULLIF(LOWER(BTRIM(NEW.status::text)), ''),
      NEW.criado_em, at_time;
    RETURN NEW;
  END IF;
  RETURN OLD;
END;
$$;
DROP TRIGGER IF EXISTS astro_api_usuario_scd ON public.usuario;
CREATE TRIGGER astro_api_usuario_scd AFTER INSERT OR UPDATE OR DELETE ON public.usuario
  FOR EACH ROW EXECUTE FUNCTION astro_api.track_usuario();

CREATE OR REPLACE FUNCTION astro_api.track_cargo() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public, astro_api AS $$
DECLARE at_time timestamptz := clock_timestamp();
BEGIN
  IF NULLIF(LOWER(BTRIM(NEW.nome)), '') IS NOT DISTINCT FROM
      NULLIF(LOWER(BTRIM(OLD.nome)), '') THEN RETURN NEW; END IF;
  UPDATE astro_api.usuario_history SET valid_to = at_time
    WHERE cargo_id = NEW.id_cargo AND valid_to IS NULL;
  INSERT INTO astro_api.usuario_history
    (id_usuario, id_unidade, cargo_id, cargo, tipo, status, criado_em, valid_from)
  SELECT u.id_usuario, u.unidade_id, u.cargo_id, NULLIF(LOWER(BTRIM(NEW.nome)), ''),
    NULLIF(LOWER(BTRIM(u.tipo::text)), ''), NULLIF(LOWER(BTRIM(u.status::text)), ''),
    u.criado_em, at_time FROM public.usuario u WHERE u.cargo_id = NEW.id_cargo;
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS astro_api_cargo_scd ON public.cargo;
CREATE TRIGGER astro_api_cargo_scd AFTER UPDATE OF nome ON public.cargo
  FOR EACH ROW EXECUTE FUNCTION astro_api.track_cargo();

CREATE SEQUENCE IF NOT EXISTS astro_api.fact_id_seq;
CREATE TABLE IF NOT EXISTS astro_api.snapshots (
  snapshot_id uuid PRIMARY KEY,
  layer text NOT NULL CHECK (layer IN ('bronze', 'silver', 'gold')),
  dataset text NOT NULL,
  scope jsonb NOT NULL,
  payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'array'),
  captured_at timestamptz NOT NULL,
  expires_at timestamptz,
  retained boolean NOT NULL DEFAULT false,
  CHECK (retained OR expires_at IS NOT NULL)
);
CREATE UNIQUE INDEX IF NOT EXISTS snapshots_daily
  ON astro_api.snapshots(layer, dataset, scope) WHERE retained;
CREATE INDEX IF NOT EXISTS snapshots_expiry ON astro_api.snapshots(expires_at) WHERE NOT retained;
CREATE TABLE IF NOT EXISTS astro_api.rate_buckets (
  client_key text NOT NULL,
  bucket timestamptz NOT NULL,
  requests integer NOT NULL CHECK (requests > 0),
  PRIMARY KEY (client_key, bucket)
);
REVOKE ALL ON FUNCTION astro_api.track_usuario() FROM PUBLIC;
REVOKE ALL ON FUNCTION astro_api.track_cargo() FROM PUBLIC;
COMMIT;

-- Grant to the API database role, replacing api_runtime with the real role:
-- GRANT USAGE ON SCHEMA astro_api TO api_runtime;
-- GRANT SELECT ON astro_api.history_control, astro_api.usuario_history TO api_runtime;
-- GRANT SELECT, INSERT, DELETE ON astro_api.snapshots TO api_runtime;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON astro_api.rate_buckets TO api_runtime;
-- GRANT USAGE ON SEQUENCE astro_api.fact_id_seq TO api_runtime;
-- Keep existing SELECT permissions on the public source relations.
