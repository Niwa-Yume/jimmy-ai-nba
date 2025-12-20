from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Float, Date
from sqlalchemy.orm import relationship
from database import Base


# Miroir de la table 'player'
class Player(Base):
    __tablename__ = "player"

    id = Column(Integer, primary_key=True, index=True)
    nba_player_id = Column(Integer, unique=True)
    full_name = Column(String)
    position = Column(String)
    is_active = Column(Boolean)

    # Relation : Un joueur a plusieurs stats
    stats = relationship("PlayerGameStats", back_populates="player")


# Miroir de la table 'player_game_stats'
class PlayerGameStats(Base):
    __tablename__ = "player_game_stats"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("player.id"))
    game_id = Column(Integer)  # On simplifie la relation game pour le MVP

    points = Column(Integer)
    rebounds = Column(Integer)
    assists = Column(Integer)
    minutes_played = Column(Float)

    player = relationship("Player", back_populates="stats")