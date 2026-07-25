-- Runs once when the postgres container's data directory is first initialized
-- (see docker-compose.yml volume mount at /docker-entrypoint-initdb.d/).
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
