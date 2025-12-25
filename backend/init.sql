-- 1. Les Équipes (Statique)
CREATE TABLE team (
    id SERIAL PRIMARY KEY,
    nba_team_id INT UNIQUE, -- ID officiel NBA (ex: 1610612747 pour Lakers)
    name VARCHAR(100),
    code VARCHAR(10) -- Ex: LAL, BOS
);

-- 2. Les Joueurs (Statique mais mis à jour si transferts)
CREATE TABLE player (
    id SERIAL PRIMARY KEY,
    nba_player_id INT UNIQUE, -- ID officiel (ex: 203999 pour Jokic)
    full_name VARCHAR(150),
    position VARCHAR(10), -- G, F, C
    team_id INT REFERENCES team(id),
    is_active BOOLEAN DEFAULT TRUE,
    
    -- ✅ NOUVEAUX CHAMPS (Manquants précédemment)
    current_injury_status VARCHAR(50) DEFAULT 'HEALTHY',
    injury_updated_at TIMESTAMP
);

-- 3. Les Matchs (Calendrier & Résultats)
-- Renommé pour correspondre au modèle GameSchedule si besoin, ou on garde 'game' et on adapte le modèle
-- Le modèle Python utilise 'games_schedule', mais ici on a 'game'.
-- Pour éviter les conflits, créons la table games_schedule qui est utilisée par le modèle.
CREATE TABLE games_schedule (
    id SERIAL PRIMARY KEY,
    nba_game_id VARCHAR(50) UNIQUE NOT NULL,
    game_date DATE NOT NULL,
    game_time VARCHAR(20),
    home_team_code VARCHAR(3) NOT NULL,
    away_team_code VARCHAR(3) NOT NULL,
    home_team_id INT,
    away_team_id INT,
    status VARCHAR(20) DEFAULT 'SCHEDULED',
    home_score INT,
    away_score INT,
    arena VARCHAR(200),
    tv_broadcast VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- On garde l'ancienne table 'game' pour l'historique des stats si nécessaire, 
-- ou on la fusionne. Pour l'instant, populate_stats utilise 'game'.
CREATE TABLE game (
    id SERIAL PRIMARY KEY,
    nba_game_id VARCHAR(20) UNIQUE,
    game_date DATE NOT NULL,
    home_team_id INT REFERENCES team(id),
    visitor_team_id INT REFERENCES team(id),
    home_score INT,
    visitor_score INT,
    status VARCHAR(20)
);

-- 4. Les Stats par Joueur par Match
CREATE TABLE player_game_stats (
    id SERIAL PRIMARY KEY,
    player_id INT REFERENCES player(id),
    game_id INT REFERENCES game(id),

    points INT DEFAULT 0,
    rebounds INT DEFAULT 0,
    assists INT DEFAULT 0,
    blocks INT DEFAULT 0,
    steals INT DEFAULT 0,
    three_points_made INT DEFAULT 0,

    matchup VARCHAR(20),

    minutes_played DECIMAL(5,2),
    fg_percentage DECIMAL(5,2),

    UNIQUE(player_id, game_id)
);

-- 5. Blessures (Historique et Détail)
CREATE TABLE player_injuries (
    id SERIAL PRIMARY KEY,
    player_id INT REFERENCES player(id),
    nba_player_id INT NOT NULL,
    status VARCHAR(50) NOT NULL,
    injury_type VARCHAR(100),
    injury_detail TEXT,
    injury_date DATE,
    expected_return DATE,
    play_probability INT,
    source VARCHAR(50) DEFAULT 'ESPN',
    source_url TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
