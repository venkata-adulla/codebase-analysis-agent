-- Repository Analysis — schema + tables (admin / DDL role only).
-- Apply in psql, Supabase SQL editor, or any session with CREATE privileges on the database.
--
-- After tables exist, grant DML-only access to the application login:
--   sql/admin_grant_app_role.sql
--
-- Application: set POSTGRES_SCHEMA=repository_analysis and SKIP_ALEMBIC_UPGRADE=true in .env
-- so the API does not run Alembic (no CREATE/ALTER from the app user).

CREATE SCHEMA IF NOT EXISTS repository_analysis;

CREATE TABLE IF NOT EXISTS repository_analysis.repositories (
  id text PRIMARY KEY,
  name text NOT NULL,
  url text,
  local_path text,
  github_owner text,
  github_repo text,
  branch text DEFAULT 'main',
  status text DEFAULT 'pending',
  progress double precision DEFAULT 0,
  message text,
  meta_data jsonb,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz
);

CREATE TABLE IF NOT EXISTS repository_analysis.services (
  id text PRIMARY KEY,
  repository_id text NOT NULL REFERENCES repository_analysis.repositories(id),
  name text NOT NULL,
  language text,
  description text,
  summary text,
  file_path text,
  meta_data jsonb,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz
);

CREATE TABLE IF NOT EXISTS repository_analysis.analysis_runs (
  id text PRIMARY KEY,
  repository_id text NOT NULL REFERENCES repository_analysis.repositories(id),
  status text DEFAULT 'running',
  started_at timestamptz DEFAULT now(),
  completed_at timestamptz,
  error_message text,
  meta_data jsonb
);

CREATE TABLE IF NOT EXISTS repository_analysis.documentation (
  id text PRIMARY KEY,
  service_id text NOT NULL REFERENCES repository_analysis.services(id),
  content text NOT NULL,
  api_specification jsonb,
  architecture_diagram text,
  version integer DEFAULT 1,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz
);

CREATE TABLE IF NOT EXISTS repository_analysis.impact_analyses (
  id text PRIMARY KEY,
  repository_id text NOT NULL REFERENCES repository_analysis.repositories(id),
  change_description text NOT NULL,
  affected_files jsonb,
  affected_services jsonb,
  impacted_services jsonb,
  risk_level text,
  recommendations jsonb,
  created_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS repository_analysis.human_reviews (
  id text PRIMARY KEY,
  checkpoint_id text NOT NULL UNIQUE,
  agent_name text NOT NULL,
  question text NOT NULL,
  context jsonb,
  options jsonb,
  response text,
  status text DEFAULT 'pending',
  created_at timestamptz DEFAULT now(),
  resolved_at timestamptz
);

CREATE TABLE IF NOT EXISTS repository_analysis.tech_debt_items (
  id text PRIMARY KEY,
  repository_id text NOT NULL REFERENCES repository_analysis.repositories(id),
  service_id text REFERENCES repository_analysis.services(id),
  file_path text,
  category text NOT NULL,
  severity text NOT NULL,
  priority integer,
  title text NOT NULL,
  description text,
  code_snippet text,
  line_start integer,
  line_end integer,
  impact_score double precision,
  effort_estimate text,
  meta_data jsonb,
  status text DEFAULT 'open',
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz
);

CREATE TABLE IF NOT EXISTS repository_analysis.tech_debt_reports (
  id text PRIMARY KEY,
  repository_id text NOT NULL REFERENCES repository_analysis.repositories(id),
  total_debt_score double precision,
  debt_density double precision,
  code_quality_score double precision,
  architecture_score double precision,
  dependency_score double precision,
  documentation_score double precision,
  test_coverage_score double precision,
  total_items integer,
  items_by_category jsonb,
  items_by_severity jsonb,
  report_data jsonb,
  created_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS repository_analysis.debt_remediation_plans (
  id text PRIMARY KEY,
  repository_id text NOT NULL REFERENCES repository_analysis.repositories(id),
  plan_name text,
  total_estimated_effort text,
  priority_breakdown jsonb,
  sprint_allocation jsonb,
  roi_analysis jsonb,
  recommendations jsonb,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz
);

CREATE TABLE IF NOT EXISTS repository_analysis.debt_metrics_history (
  id text PRIMARY KEY,
  repository_id text NOT NULL REFERENCES repository_analysis.repositories(id),
  total_debt_score double precision,
  debt_density double precision,
  total_items integer,
  items_by_category jsonb,
  remediation_velocity double precision,
  recorded_at timestamptz DEFAULT now()
);
