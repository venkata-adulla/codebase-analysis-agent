-- Optional legacy: Alembic version row (only if you still run Alembic CLI manually).
-- Not used when schema is managed only via sql/repository_analysis_schema.sql and SKIP_ALEMBIC_UPGRADE=true.

CREATE TABLE IF NOT EXISTS public.alembic_version (
  version_num VARCHAR(32) NOT NULL,
  CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Head revision in this repo (see: uv run alembic heads). Replace if your migration chain differs.
DELETE FROM public.alembic_version;
INSERT INTO public.alembic_version (version_num) VALUES ('a1b2c3d4e5f6');
