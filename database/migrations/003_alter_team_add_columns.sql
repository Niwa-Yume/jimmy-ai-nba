-- Migration: compléter la table team si déjà existante (conference, division, is_active, timestamps)
-- Date: 2026-01-01

-- Ajouter les colonnes manquantes si la table existe déjà sans ces champs
ALTER TABLE IF EXISTS team
    ADD COLUMN IF NOT EXISTS conference VARCHAR(10),
    ADD COLUMN IF NOT EXISTS division VARCHAR(20),
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- Index de confort si absents
CREATE INDEX IF NOT EXISTS idx_team_code ON team(code);
CREATE INDEX IF NOT EXISTS idx_team_nba_id ON team(nba_team_id);

