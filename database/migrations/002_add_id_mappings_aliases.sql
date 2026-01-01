-- Migration: ajout tables team, id_mappings, aliases pour DataHub
-- Date: 2026-01-01

-- Table team
CREATE TABLE IF NOT EXISTS team (
    id SERIAL PRIMARY KEY,
    nba_team_id INTEGER UNIQUE,
    code VARCHAR(5) UNIQUE,
    name VARCHAR(255),
    conference VARCHAR(10),
    division VARCHAR(20),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_team_code ON team(code);
CREATE INDEX IF NOT EXISTS idx_team_nba_id ON team(nba_team_id);

-- Table id_mappings (polymorphique player/team)
CREATE TABLE IF NOT EXISTS id_mappings (
    id SERIAL PRIMARY KEY,
    entity_type VARCHAR(20) NOT NULL, -- 'player' ou 'team'
    entity_id INTEGER NOT NULL,
    source VARCHAR(30) NOT NULL,      -- 'nba', 'espn', 'odds'
    external_id VARCHAR(100) NOT NULL,
    display_name VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_id_mapping_source UNIQUE(entity_type, source, external_id)
);

CREATE INDEX IF NOT EXISTS idx_idmap_entity ON id_mappings(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_idmap_source ON id_mappings(source);

-- Table aliases (fuzzy/variantes)
CREATE TABLE IF NOT EXISTS aliases (
    id SERIAL PRIMARY KEY,
    entity_type VARCHAR(20) NOT NULL,
    entity_id INTEGER NOT NULL,
    source VARCHAR(30) DEFAULT 'manual',
    alias VARCHAR(150) NOT NULL,
    normalized_alias VARCHAR(150),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_alias_source UNIQUE(entity_type, alias, source)
);

CREATE INDEX IF NOT EXISTS idx_alias_entity ON aliases(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_alias_norm ON aliases(normalized_alias);

