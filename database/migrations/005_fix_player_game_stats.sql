-- Migration 005: Ajouter contrainte unique et colonnes manquantes pour player_game_stats
-- Date: 2026-01-08

-- 1. Ajouter les colonnes content_hash et updated_at si elles n'existent pas
ALTER TABLE player_game_stats
  ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64),
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- 2. Supprimer les doublons existants (garder le plus récent)
DELETE FROM player_game_stats a
USING player_game_stats b
WHERE a.id < b.id
  AND a.player_id = b.player_id
  AND a.game_id = b.game_id;

-- 3. Ajouter la contrainte unique
ALTER TABLE player_game_stats
  ADD CONSTRAINT uq_player_game UNIQUE (player_id, game_id);

-- 4. Créer un index sur updated_at pour les performances
CREATE INDEX IF NOT EXISTS idx_player_game_stats_updated ON player_game_stats(updated_at);

COMMIT;

