from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Float, Date, DateTime, Text
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
    three_points_made = Column(Integer, default=0) # 3PM
    
    # ✅ NOUVEAU : CONTEXTE DU MATCH
    matchup = Column(String(20)) # Ex: "LAL @ BOS" ou "LAL vs BOS"
    
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
