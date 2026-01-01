from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Float, Date, DateTime, Text, UniqueConstraint, DECIMAL
from sqlalchemy.orm import relationship
from .database import Base
from datetime import datetime


# Miroir de la table 'player'
class Player(Base):
    __tablename__ = "player"

    id = Column(Integer, primary_key=True, index=True)
    nba_player_id = Column(Integer, unique=True)
    full_name = Column(String)
    position = Column(String)
    is_active = Column(Boolean)

    # Nouveaux champs pour injuries
    current_injury_status = Column(String, default='HEALTHY')
    injury_updated_at = Column(DateTime)

    # Relations
    stats = relationship("PlayerGameStats", back_populates="player")
    injuries = relationship("PlayerInjury", back_populates="player")


# Miroir de la table 'player_game_stats'
class PlayerGameStats(Base):
    __tablename__ = "player_game_stats"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("player.id"))
    game_id = Column(Integer)

    points = Column(Integer)
    rebounds = Column(Integer)
    assists = Column(Integer)

    # ✅ NOUVELLES STATS
    steals = Column(Integer, default=0)
    blocks = Column(Integer, default=0)
    three_points_made = Column(Integer, default=0)  # 3PM

    # ✅ NOUVEAU : CONTEXTE DU MATCH
    matchup = Column(String(20))  # Ex: "LAL @ BOS" ou "LAL vs BOS"

    minutes_played = Column(Float)
    fg_percentage = Column(Float)

    player = relationship("Player", back_populates="stats")


# Nouvelle table : games_schedule
class GameSchedule(Base):
    __tablename__ = "games_schedule"

    id = Column(Integer, primary_key=True, index=True)
    nba_game_id = Column(String(50), unique=True, nullable=False)
    game_date = Column(Date, nullable=False)
    game_time = Column(String(20))

    # Équipes
    home_team_code = Column(String(3), nullable=False)
    away_team_code = Column(String(3), nullable=False)
    home_team_id = Column(Integer)
    away_team_id = Column(Integer)

    # Statut
    status = Column(String(20), default='SCHEDULED')
    home_score = Column(Integer)
    away_score = Column(Integer)

    # Métadonnées
    arena = Column(String(200))
    tv_broadcast = Column(String(100))

    # Timestamps
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    last_fetched_at = Column(DateTime, default=datetime.now)


# Nouvelle table : player_injuries
class PlayerInjury(Base):
    __tablename__ = "player_injuries"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("player.id"), nullable=False)
    nba_player_id = Column(Integer, nullable=False)

    # Statut
    status = Column(String(50), nullable=False)
    injury_type = Column(String(100))
    injury_detail = Column(Text)

    # Dates
    injury_date = Column(Date)
    expected_return = Column(Date)

    # Probabilité
    play_probability = Column(Integer)  # 0-100%

    # Source
    source = Column(String(50), default='ESPN')
    source_url = Column(Text)

    # Actif
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    last_verified_at = Column(DateTime, default=datetime.now)

    # Relation
    player = relationship("Player", back_populates="injuries")


# ✅ NOUVELLE TABLE : Stockage des Cotes
class BettingOdds(Base):
    __tablename__ = "betting_odds"

    id = Column(Integer, primary_key=True, index=True)
    game_id = Column(String, index=True)  # ID NBA du match (ex: "0022401185")
    player_id = Column(Integer, ForeignKey("player.id"))

    market = Column(String)  # "points", "rebounds", "assists"
    line = Column(Float)
    odds_over = Column(Float)
    odds_under = Column(Float)
    bookmaker = Column(String)

    # Pour savoir si la donnée est périmée
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    player = relationship("Player")


class Team(Base):
    __tablename__ = "team"

    id = Column(Integer, primary_key=True, index=True)
    nba_team_id = Column(Integer, unique=True)
    code = Column(String(5), unique=True, index=True)
    name = Column(String)
    conference = Column(String(10))
    division = Column(String(20))
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class IdMapping(Base):
    __tablename__ = "id_mappings"

    id = Column(Integer, primary_key=True, index=True)
    entity_type = Column(String(20), index=True)  # 'player' ou 'team'
    entity_id = Column(Integer, index=True)
    source = Column(String(30), index=True)  # 'nba', 'espn', 'odds'
    external_id = Column(String(100))
    display_name = Column(String)

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (UniqueConstraint('entity_type', 'source', 'external_id', name='uq_id_mapping_source'),)


class Alias(Base):
    __tablename__ = "aliases"

    id = Column(Integer, primary_key=True, index=True)
    entity_type = Column(String(20), index=True)  # 'player' ou 'team'
    entity_id = Column(Integer, index=True)
    source = Column(String(30), default='manual')
    alias = Column(String(150), index=True)
    normalized_alias = Column(String(150), index=True)

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (UniqueConstraint('entity_type', 'alias', 'source', name='uq_alias_source'),)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(50), index=True, nullable=False)
    scope = Column(String(50))
    version_tag = Column(String(50))
    status = Column(String(20), default='running')
    started_at = Column(DateTime, default=datetime.now)
    ended_at = Column(DateTime)
    meta = Column(Text)  # store JSON as text; convert at service layer
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class OddsSnapshot(Base):
    __tablename__ = "odds_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    ingestion_run_id = Column(Integer, ForeignKey("ingestion_runs.id"))
    game_id = Column(String(50), index=True, nullable=False)
    player_id = Column(Integer, ForeignKey("player.id"))
    market = Column(String(50), index=True, nullable=False)
    line = Column(DECIMAL(10, 2))
    price_over = Column(DECIMAL(10, 2))
    price_under = Column(DECIMAL(10, 2))
    bookmaker = Column(String(50), index=True, nullable=False)
    source = Column(String(30), default='the-odds-api')
    fetched_at = Column(DateTime, default=datetime.now)
    ttl_expire_at = Column(DateTime, index=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    ingestion_run = relationship("IngestionRun")
    player = relationship("Player")
