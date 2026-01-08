-- Migration pour corriger la contrainte unique sur player_game_stats
-- Date: 8 Janvier 2026

-- Ajouter une contrainte unique sur (player_id, game_id) si elle n'existe pas
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'unique_player_game'
    ) THEN
        ALTER TABLE player_game_stats
        ADD CONSTRAINT unique_player_game UNIQUE(player_id, game_id);
    END IF;
END $$;

-- Ajouter la colonne content_hash si elle n'existe pas
ALTER TABLE player_game_stats
ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64);

-- Créer un index pour améliorer les performances
CREATE INDEX IF NOT EXISTS idx_player_game_stats_player ON player_game_stats(player_id);
CREATE INDEX IF NOT EXISTS idx_player_game_stats_game ON player_game_stats(game_id);
CREATE INDEX IF NOT EXISTS idx_player_game_stats_content ON player_game_stats(content_hash);

