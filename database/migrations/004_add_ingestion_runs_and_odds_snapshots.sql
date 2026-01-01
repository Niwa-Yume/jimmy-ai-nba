-- Migration: ajoute ingestion_runs et odds_snapshots pour traçabilité et cache des cotes
-- Date: 2026-01-01

CREATE TABLE IF NOT EXISTS ingestion_runs (
    id SERIAL PRIMARY KEY,
    source VARCHAR(50) NOT NULL,
    scope VARCHAR(50),
    version_tag VARCHAR(50),
    status VARCHAR(20) DEFAULT 'running',
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP,
    meta JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ingestion_runs_source ON ingestion_runs(source);
CREATE INDEX IF NOT EXISTS idx_ingestion_runs_status ON ingestion_runs(status);
CREATE INDEX IF NOT EXISTS idx_ingestion_runs_started_at ON ingestion_runs(started_at);

CREATE TABLE IF NOT EXISTS odds_snapshots (
    id SERIAL PRIMARY KEY,
    ingestion_run_id INTEGER REFERENCES ingestion_runs(id) ON DELETE SET NULL,
    game_id VARCHAR(50) NOT NULL,
    player_id INTEGER REFERENCES player(id) ON DELETE SET NULL,
    market VARCHAR(50) NOT NULL,
    line DECIMAL(10,2),
    price_over DECIMAL(10,2),
    price_under DECIMAL(10,2),
    bookmaker VARCHAR(50) NOT NULL,
    source VARCHAR(30) DEFAULT 'the-odds-api',
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ttl_expire_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_odds_snapshot UNIQUE(game_id, player_id, market, bookmaker, fetched_at)
);

CREATE INDEX IF NOT EXISTS idx_odds_snapshots_game ON odds_snapshots(game_id);
CREATE INDEX IF NOT EXISTS idx_odds_snapshots_player ON odds_snapshots(player_id);
CREATE INDEX IF NOT EXISTS idx_odds_snapshots_market ON odds_snapshots(market);
CREATE INDEX IF NOT EXISTS idx_odds_snapshots_bookmaker ON odds_snapshots(bookmaker);
CREATE INDEX IF NOT EXISTS idx_odds_snapshots_ttl ON odds_snapshots(ttl_expire_at);

