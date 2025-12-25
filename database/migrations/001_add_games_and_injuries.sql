-- Migration pour ajouter les tables games_schedule et player_injuries
-- Date: 21 Décembre 2024

-- ============================================================================
-- Table : games_schedule (Matchs de la semaine)
-- ============================================================================
CREATE TABLE IF NOT EXISTS games_schedule (
    id SERIAL PRIMARY KEY,
    nba_game_id VARCHAR(50) UNIQUE NOT NULL,  -- ID unique NBA
    game_date DATE NOT NULL,
    game_time VARCHAR(20),  -- Heure du match (format: "19:30 ET")

    -- Équipes
    home_team_code VARCHAR(3) NOT NULL,       -- Ex: "LAL"
    away_team_code VARCHAR(3) NOT NULL,       -- Ex: "BOS"
    home_team_id INTEGER,
    away_team_id INTEGER,

    -- Statut du match
    status VARCHAR(20) DEFAULT 'SCHEDULED',   -- SCHEDULED, LIVE, FINAL, POSTPONED

    -- Scores (NULL si pas encore joué)
    home_score INTEGER,
    away_score INTEGER,

    -- Métadonnées
    arena VARCHAR(200),
    tv_broadcast VARCHAR(100),

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- Pour le cache

    -- Index pour recherches rapides
    CONSTRAINT unique_game UNIQUE(home_team_code, away_team_code, game_date)
);

CREATE INDEX idx_games_date ON games_schedule(game_date);
CREATE INDEX idx_games_status ON games_schedule(status);
CREATE INDEX idx_games_teams ON games_schedule(home_team_code, away_team_code);


-- ============================================================================
-- Table : player_injuries (Blessures des joueurs)
-- ============================================================================
CREATE TABLE IF NOT EXISTS player_injuries (
    id SERIAL PRIMARY KEY,
    player_id INTEGER REFERENCES player(id) ON DELETE CASCADE,
    nba_player_id INTEGER NOT NULL,

    -- Statut de la blessure
    status VARCHAR(50) NOT NULL,              -- OUT, QUESTIONABLE, DOUBTFUL, PROBABLE, DAY_TO_DAY, GTD
    injury_type VARCHAR(100),                 -- Ex: "Ankle Sprain", "Rest", "Knee Soreness"
    injury_detail TEXT,                       -- Description complète

    -- Dates
    injury_date DATE,                         -- Date de la blessure
    expected_return DATE,                     -- Date de retour estimée (NULL si inconnue)

    -- Probabilité de jouer (pour les GTD/Questionable)
    play_probability INTEGER,                 -- 0-100% (NULL si OUT/Healthy)

    -- Source de l'info
    source VARCHAR(50) DEFAULT 'ESPN',        -- ESPN, NBA, Team Report
    source_url TEXT,

    -- Est-ce toujours actif ?
    is_active BOOLEAN DEFAULT TRUE,           -- FALSE si le joueur est revenu

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- Dernière vérification

    CONSTRAINT unique_active_injury UNIQUE(player_id, is_active)
);

CREATE INDEX idx_injuries_player ON player_injuries(player_id);
CREATE INDEX idx_injuries_status ON player_injuries(status);
CREATE INDEX idx_injuries_active ON player_injuries(is_active);
CREATE INDEX idx_injuries_nba_id ON player_injuries(nba_player_id);


-- ============================================================================
-- Mise à jour de la table player (ajout de colonnes injury)
-- ============================================================================
ALTER TABLE player
    ADD COLUMN IF NOT EXISTS current_injury_status VARCHAR(50) DEFAULT 'HEALTHY',
    ADD COLUMN IF NOT EXISTS injury_updated_at TIMESTAMP;


-- ============================================================================
-- Vue : Matchs de la semaine avec infos blessures
-- ============================================================================
CREATE OR REPLACE VIEW weekly_games_with_injuries AS
SELECT
    g.*,
    COUNT(DISTINCT pi_home.id) as home_team_injuries,
    COUNT(DISTINCT pi_away.id) as away_team_injuries,
    STRING_AGG(DISTINCT CONCAT(p_home.full_name, ' (', pi_home.status, ')'), ', ') as home_injured_players,
    STRING_AGG(DISTINCT CONCAT(p_away.full_name, ' (', pi_away.status, ')'), ', ') as away_injured_players
FROM games_schedule g
LEFT JOIN player p_home ON p_home.position IS NOT NULL  -- Placeholder pour team lookup
LEFT JOIN player_injuries pi_home ON pi_home.player_id = p_home.id AND pi_home.is_active = TRUE
LEFT JOIN player p_away ON p_away.position IS NOT NULL
LEFT JOIN player_injuries pi_away ON pi_away.player_id = p_away.id AND pi_away.is_active = TRUE
WHERE g.game_date >= CURRENT_DATE
  AND g.game_date <= CURRENT_DATE + INTERVAL '7 days'
GROUP BY g.id
ORDER BY g.game_date, g.game_time;


-- ============================================================================
-- Commentaires
-- ============================================================================
COMMENT ON TABLE games_schedule IS 'Matchs NBA de la semaine avec cache intelligent';
COMMENT ON TABLE player_injuries IS 'Historique des blessures des joueurs NBA';
COMMENT ON COLUMN player_injuries.play_probability IS 'Probabilité de jouer (0-100%), calculée selon le statut';
COMMENT ON COLUMN games_schedule.last_fetched_at IS 'Utilisé pour éviter les appels API répétés (cache 6h)';

