-- FastAPI-ML: neue ai_* Tabellen. Idempotent (CREATE TABLE IF NOT EXISTS).
-- Bestehende Tabellen (pls_fetch_current, weather_forecasts, local_events,
-- event_parkhaus, cities, parkhaeuser) werden nur gelesen, nie veraendert.

-- Kanonisches Identity-Mapping: (city, pls_id) aus pls_fetch_current -> parkhaeuser.id
CREATE TABLE IF NOT EXISTS ai_parkhaus_map (
    city         VARCHAR(32)  NOT NULL,
    pls_id       VARCHAR(64)  NOT NULL,
    pls_name     VARCHAR(255) NOT NULL,
    parkhaus_id  VARCHAR(128) NULL,
    match_method VARCHAR(16)  NOT NULL,   -- 'id' | 'contain' | 'wordset' | 'none'
    updated_at   DATETIME     NOT NULL,
    PRIMARY KEY (city, pls_id),
    KEY idx_map_parkhaus (parkhaus_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Ein Eintrag pro Trainingslauf
CREATE TABLE IF NOT EXISTS ai_model_runs (
    run_id        INT AUTO_INCREMENT PRIMARY KEY,
    model_type    VARCHAR(16)  NOT NULL,   -- 'baseline' | 'ml'
    horizon_h     TINYINT      NULL,       -- 1/2/4/8; NULL fuer baseline
    trained_at    DATETIME     NOT NULL,
    train_rows    INT          NOT NULL,
    train_from    DATETIME     NULL,
    train_to      DATETIME     NULL,
    cv_mae_free   DECIMAL(10,3) NULL,      -- Holdout-MAE in freien Plaetzen
    cv_mae_occ    DECIMAL(6,3)  NULL,      -- Holdout-MAE in Belegungs-Prozentpunkten
    cv_r2         DECIMAL(6,4) NULL,      -- R² auf Holdout (Bestimmtheitsmass)
    params_json   TEXT         NULL,
    artifact_path VARCHAR(255) NULL,
    is_active     TINYINT(1)   NOT NULL DEFAULT 0,
    KEY idx_runs_active (model_type, horizon_h, is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Jede erzeugte Prognose; wird nach Reifung in-place evaluiert
CREATE TABLE IF NOT EXISTS ai_predictions (
    id             BIGINT AUTO_INCREMENT PRIMARY KEY,
    created_at     DATETIME     NOT NULL,   -- auf 15-Min-Raster gerundet
    target_time    DATETIME     NOT NULL,   -- created_at + horizon
    horizon_h      TINYINT      NOT NULL,   -- 1, 2, 4, 8
    model_type     VARCHAR(16)  NOT NULL,   -- 'baseline' | 'ml'
    run_id         INT          NULL,
    city           VARCHAR(32)  NOT NULL,
    pls_id         VARCHAR(64)  NOT NULL,
    predicted_free INT          NOT NULL,
    predicted_occ  DECIMAL(6,4) NOT NULL,   -- Belegungsquote 0..1
    total_at_pred  INT          NULL,
    predicted_free_q20 INT       NULL,       -- pessimistisches 20%-Quantil
    predicted_full_prob DECIMAL(5,4) NULL,  -- P(free < 5)
    actual_free    INT          NULL,
    actual_ts      DATETIME     NULL,
    abs_err_free   INT          NULL,
    abs_err_occ    DECIMAL(6,4) NULL,
    evaluated_at   DATETIME     NULL,
    UNIQUE KEY uq_pred (city, pls_id, model_type, horizon_h, created_at),
    KEY idx_pred_eval (evaluated_at, target_time),
    KEY idx_pred_target (city, pls_id, target_time),
    KEY idx_pred_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Tages-Aggregate fuer die Dashboards
-- city=''            -> globales Aggregat
-- pls_id=''          -> Stadt- (bzw. global-) Aggregat
CREATE TABLE IF NOT EXISTS ai_accuracy_daily (
    day          DATE          NOT NULL,
    city         VARCHAR(32)   NOT NULL,
    pls_id       VARCHAR(64)   NOT NULL,
    model_type   VARCHAR(16)   NOT NULL,
    horizon_h    TINYINT       NOT NULL,
    n            INT           NOT NULL,
    mae_free     DECIMAL(10,3) NOT NULL,
    mae_occ      DECIMAL(6,3)  NOT NULL,   -- Prozentpunkte 0..100
    rmse_free    DECIMAL(10,3) NULL,
    bias_free    DECIMAL(10,3) NULL,       -- mean(pred - actual)
    PRIMARY KEY (day, city, pls_id, model_type, horizon_h)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Kantonale Feiertage (berechnet oder manuell gepflegt)
CREATE TABLE IF NOT EXISTS ai_feiertage (
    datum    DATE         NOT NULL,
    kanton   VARCHAR(4)   NOT NULL,
    name     VARCHAR(100) NOT NULL,
    PRIMARY KEY (datum, kanton)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Kantonale Schulferien
CREATE TABLE IF NOT EXISTS ai_schulferien (
    kanton       VARCHAR(4)  NOT NULL,
    jahr         SMALLINT    NOT NULL,
    von          DATE        NOT NULL,
    bis          DATE        NOT NULL,
    bezeichnung  VARCHAR(64) NULL,
    PRIMARY KEY (kanton, jahr, von)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Chat-Verlauf
CREATE TABLE IF NOT EXISTS ai_chat_log (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    ts            DATETIME NOT NULL,
    session_id    VARCHAR(64) NOT NULL,
    user_text     TEXT NOT NULL,
    intent        VARCHAR(64) NULL,
    entities_json TEXT NULL,
    bot_text      TEXT NOT NULL,
    KEY idx_chat_session (session_id, ts)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
