-- Performance-Index fuer pls_fetch_current
-- Beschleunigt: past_values(), inactive-check (48h MIN/MAX), latest_snapshots()
--
-- Auf beiden DBs ausfuehren:
--   mysql -u root ph_fetch_prod < migrations/add_index_pls_fetch_current.sql
--   mysql -u root ph_fetch_test < migrations/add_index_pls_fetch_current.sql

CREATE INDEX IF NOT EXISTS idx_pls_city_fetchts
    ON pls_fetch_current (city, fetch_ts);

CREATE INDEX IF NOT EXISTS idx_pls_city_id_fetchts
    ON pls_fetch_current (city, id, fetch_ts);
