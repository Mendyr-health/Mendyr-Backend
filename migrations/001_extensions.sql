-- Required Postgres extensions. The postgis/postgis Docker image (see docker-compose.yml)
-- ships these already; this file exists so a managed/non-Docker Postgres (RDS, Supabase,
-- Cloud SQL) can be brought to the same baseline by just running every file in this folder
-- in order.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
