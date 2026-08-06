-- Migration: Neue Spalten und Tabellen fuer Prognose-Verbesserungen.
-- Idempotent: laeuft auch auf einer bereits migrierten DB ohne Fehler.

-- 1. Quantil- und Voll-Spalten in ai_predictions
ALTER TABLE ai_predictions
    ADD COLUMN IF NOT EXISTS predicted_free_q20 INT NULL AFTER total_at_pred,
    ADD COLUMN IF NOT EXISTS predicted_full_prob DECIMAL(5,4) NULL AFTER predicted_free_q20;

-- 2. Kantonale Feiertage
CREATE TABLE IF NOT EXISTS ai_feiertage (
    datum    DATE         NOT NULL,
    kanton   VARCHAR(4)   NOT NULL,
    name     VARCHAR(100) NOT NULL,
    PRIMARY KEY (datum, kanton)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. Kantonale Schulferien
CREATE TABLE IF NOT EXISTS ai_schulferien (
    kanton       VARCHAR(4)  NOT NULL,
    jahr         SMALLINT    NOT NULL,
    von          DATE        NOT NULL,
    bis          DATE        NOT NULL,
    bezeichnung  VARCHAR(64) NULL,
    PRIMARY KEY (kanton, jahr, von)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
