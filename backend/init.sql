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
    is_active BOOLEAN DEFAULT TRUE
);

-- 3. Les Matchs (Calendrier & Résultats)
CREATE TABLE game (
    id SERIAL PRIMARY KEY,
    nba_game_id VARCHAR(20) UNIQUE, -- ID unique du match
    game_date DATE NOT NULL,
    home_team_id INT REFERENCES team(id),
    visitor_team_id INT REFERENCES team(id),
    home_score INT,
    visitor_score INT,
    status VARCHAR(20) -- 'SCHEDULED', 'FINISHED'
);

-- 4. Les Stats par Joueur par Match (Le cœur du réacteur "DataHub" [cite: 63])
-- C'est ici que tu stockeras les "Points, Rebonds, Passes" pour l'analyse [cite: 62]
CREATE TABLE player_game_stats (
    id SERIAL PRIMARY KEY,
    player_id INT REFERENCES player(id),
    game_id INT REFERENCES game(id),

    -- Stats de base (Source 14: Luka 15+ points, etc.)
    points INT DEFAULT 0,
    rebounds INT DEFAULT 0,
    assists INT DEFAULT 0,
    blocks INT DEFAULT 0,
    steals INT DEFAULT 0,

    -- Stats avancées (Source 68: Minutes, Usage)
    minutes_played DECIMAL(5,2),
    fg_percentage DECIMAL(5,2), -- Pourcentage au tir

    -- Clé unique pour éviter les doublons
    UNIQUE(player_id, game_id)
);