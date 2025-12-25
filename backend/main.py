from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Query, Body
from sqlalchemy.orm import Session
import pandas as pd
import os
from backend.database import get_db, engine
from backend import models
from backend.ai_agent import ask_jimmy
from backend.defense_ratings import get_defensive_factor, get_defense_analysis, adjust_defense_for_injuries, get_pace_factor, NBA_TEAM_CODES
from backend.offensive_impact import get_offensive_boost
from backend.betting_service import BettingOddsProvider
from backend.probability import calculate_milestone_probabilities, cumulative_distribution_function
import requests
import time
from datetime import datetime, timedelta
import uuid
from typing import List, Optional
from pydantic import BaseModel
from sqlalchemy import text

# ✅ Import pour le fallback des rosters
from nba_api.stats.endpoints import commonteamroster

# ✅ Création des tables si elles n'existent pas (Réparation auto)
models.Base.metadata.create_all(bind=engine)

# ✅ MIGRATION AUTO : Ajout des colonnes manquantes
def run_migrations():
    try:
        with engine.connect() as conn:
            # Player Injuries
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS player_injuries (
                    id SERIAL PRIMARY KEY,
                    player_id INTEGER REFERENCES player(id) ON DELETE CASCADE,
                    nba_player_id INTEGER NOT NULL,
                    status VARCHAR(50) NOT NULL,
                    injury_type VARCHAR(100),
                    injury_detail TEXT,
                    injury_date DATE,
                    expected_return DATE,
                    play_probability INTEGER,
                    source VARCHAR(50) DEFAULT 'ESPN',
                    source_url TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            # Games Schedule
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS games_schedule (
                    id SERIAL PRIMARY KEY,
                    nba_game_id VARCHAR(50) UNIQUE NOT NULL,
                    game_date DATE NOT NULL,
                    game_time VARCHAR(20),
                    home_team_code VARCHAR(3) NOT NULL,
                    away_team_code VARCHAR(3) NOT NULL,
                    home_team_id INTEGER,
                    away_team_id INTEGER,
                    status VARCHAR(20) DEFAULT 'SCHEDULED',
                    home_score INTEGER,
                    away_score INTEGER,
                    arena VARCHAR(200),
                    tv_broadcast VARCHAR(100),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            # Add columns to player
            conn.execute(text("ALTER TABLE player ADD COLUMN IF NOT EXISTS current_injury_status VARCHAR(50) DEFAULT 'HEALTHY'"))
            conn.execute(text("ALTER TABLE player ADD COLUMN IF NOT EXISTS injury_updated_at TIMESTAMP"))
            
            # Add columns to player_game_stats
            conn.execute(text("ALTER TABLE player_game_stats ADD COLUMN IF NOT EXISTS content_hash VARCHAR(128)"))
            conn.execute(text("ALTER TABLE player_game_stats ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
            conn.execute(text("ALTER TABLE player_game_stats ADD COLUMN IF NOT EXISTS matchup VARCHAR(20)"))
            conn.execute(text("ALTER TABLE player_game_stats ADD COLUMN IF NOT EXISTS steals INTEGER DEFAULT 0"))
            conn.execute(text("ALTER TABLE player_game_stats ADD COLUMN IF NOT EXISTS blocks INTEGER DEFAULT 0"))
            conn.execute(text("ALTER TABLE player_game_stats ADD COLUMN IF NOT EXISTS three_points_made INTEGER DEFAULT 0"))
            
            conn.commit()
            print("✅ Migrations DB appliquées avec succès.")
    except Exception as e:
        print(f"⚠️ Erreur lors des migrations DB : {e}")

# Lancer les migrations au démarrage
run_migrations()

app = FastAPI(title="Jimmy.AI API", description="Moteur de prédiction NBA")

# ✅ Initialisation du service de paris (Singleton)
betting_provider = BettingOddsProvider()
ANALYSIS_JOBS = {}
# ✅ Cache journalier pour éviter de recalculer les mêmes joueurs
DAILY_CACHE = {}

# ✅ MODÈLE PYDANTIC POUR LA VALIDATION
class Bet(BaseModel):
    player: str
    team: str
    opponent: str
    market: str
    line: float
    odds: Optional[float]
    projection: float
    confidence: str
    ev: float
    game_id: str
    player_id: int
    bet_type: str # 'Over' ou 'Under'


# --- Modèle pour le scan (marchés + options) ---
class ScanRequest(BaseModel):
    markets: Optional[list[str]] = None

# Limite fixe pour performance (nombre max de joueurs analysés par équipe)
MAX_PLAYERS_PER_TEAM = 6

# --- FONCTIONS HELPER (ROSTERS) ---
_LINEUPS_CACHE: dict[str, dict] = {}
_ESPN_TEAMS_CACHE: dict = {"ts": 0, "map": {}}

def _normalize_team_code(code: str) -> str:
    if not code: return code
    code = code.upper()
    aliases = {"BRK": "BKN", "PHO": "PHX", "CHO": "CHA", "NO": "NOP", "NY": "NYK", "SA": "SAS", "GS": "GSW", "UT": "UTA", "UTAH": "UTA"}
    return aliases.get(code, code)

def _get_espn_team_id(team_code: str, timeout: int = 8) -> tuple[int | None, dict]:
    meta = {"cached": False, "status_code": None, "error": None, "source": "ESPN_TEAMS"}
    if not team_code: return None, meta
    code = team_code.upper()
    normalized = _normalize_team_code(code)
    now = time.time()
    if _ESPN_TEAMS_CACHE.get("map") and (now - _ESPN_TEAMS_CACHE.get("ts", 0)) < 86400:
        return _ESPN_TEAMS_CACHE["map"].get(code) or _ESPN_TEAMS_CACHE["map"].get(normalized), meta

    url = "https://site.web.api.espn.com/apis/site/v2/sports/basketball/nba/teams"
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout)
        if not r.ok: return None, meta
        data = r.json()
        mapping = {}
        for entry in data.get("sports", [])[0].get("leagues", [])[0].get("teams", []):
            t = entry.get("team", {})
            abbr = t.get("abbreviation", "").upper()
            tid = int(t.get("id", 0))
            if abbr and tid:
                mapping[abbr] = tid
                mapping[_normalize_team_code(abbr)] = tid
        
        _ESPN_TEAMS_CACHE["map"] = mapping
        _ESPN_TEAMS_CACHE["ts"] = now
        return mapping.get(code) or mapping.get(normalized), meta
    except Exception:
        return None, meta

def _fetch_team_roster_from_espn(team_code: str, timeout: int = 8):
    espn_team_id, _ = _get_espn_team_id(team_code, timeout)
    if not espn_team_id: return [], {}
    cache_key = f"ESPN:{team_code}"
    cached = _LINEUPS_CACHE.get(cache_key)
    if cached and (time.time() - cached.get("ts", 0)) < 600:
        return cached.get("players", []), {}
    url = f"https://site.web.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{espn_team_id}/roster"
    try:
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout)
        if not res.ok: return [], {}
        data = res.json()
        players = []
        for grp in data.get("athletes", []):
            for item in grp.get("items", []):
                p = {"full_name": item.get("fullName"), "position": item.get("position", {}).get("abbreviation", "")}
                inj = item.get("injuries", [])
                if inj: p["injury_status"] = inj[0].get("status", "").upper()
                players.append(p)
        if players: _LINEUPS_CACHE[cache_key] = {"ts": time.time(), "players": players}
        return players, {}
    except Exception:
        return [], {}

def _code_to_team_id(code: str) -> int | None:
    if not code: return None
    code = code.upper()
    reverse = getattr(_code_to_team_id, "_reverse_map", None)
    if reverse is None:
        reverse = {v: k for k, v in NBA_TEAM_CODES.items()}
        setattr(_code_to_team_id, "_reverse_map", reverse)
    return reverse.get(code)

def _fetch_team_roster_nba_api(team_code: str):
    try:
        team_id = _code_to_team_id(team_code)
        if not team_id: return []
        cache_key = f"NBA_API:{team_code}"
        cached = _LINEUPS_CACHE.get(cache_key)
        if cached and (time.time() - cached.get("ts", 0)) < 3600: return cached.get("players", [])
        roster = commonteamroster.CommonTeamRoster(team_id=team_id, season='2024-25')
        data = roster.get_normalized_dict()['CommonTeamRoster']
        players = [{"full_name": p['PLAYER'], "position": p['POSITION'], "injury_status": "UNKNOWN"} for p in data]
        if players: _LINEUPS_CACHE[cache_key] = {"ts": time.time(), "players": players}
        return players
    except Exception: return []

def _attach_local_ids_and_injuries(db: Session, players: list[dict]):
    from sqlalchemy import func
    for p in players:
        name = (p.get("full_name") or "").strip()
        if name:
            row = db.query(models.Player).filter(func.lower(models.Player.full_name) == name.lower()).first()
            if row:
                p["id"] = row.id
                inj = db.query(models.PlayerInjury).filter(models.PlayerInjury.player_id == row.id, models.PlayerInjury.is_active == True).first()
                if inj: p["injury_status"] = inj.status
                elif p.get("injury_status") == "UNKNOWN" or not p.get("injury_status"): p["injury_status"] = "HEALTHY"
            else:
                p["id"] = None
                p["injury_status"] = p.get("injury_status") or "UNKNOWN"
    return players

def get_roster_for_team(team_code: str, db: Session):
    roster, _ = _fetch_team_roster_from_espn(team_code)
    if not roster: roster = _fetch_team_roster_nba_api(team_code)
    return _attach_local_ids_and_injuries(db, roster)

# --- FONCTIONS HELPER (PROJECTIONS) ---
def get_game_context(player_nba_id, db: Session, game_id: str = None, player_name: str = None):
    if game_id and player_name:
        game = db.query(models.GameSchedule).filter(models.GameSchedule.nba_game_id == game_id).first()
        if game:
            home_roster = get_roster_for_team(game.home_team_code, db)
            away_roster = get_roster_for_team(game.away_team_code, db)
            p_name_norm = player_name.lower().strip()
            for p in home_roster:
                if p.get('full_name', '').lower().strip() == p_name_norm:
                    return game.home_team_code, game.away_team_code, 'Home'
            for p in away_roster:
                if p.get('full_name', '').lower().strip() == p_name_norm:
                    return game.away_team_code, game.home_team_code, 'Away'
    try:
        from nba_api.stats.endpoints import playergamelog
        log = playergamelog.PlayerGameLog(player_id=player_nba_id, season='2024-25')
        games = log.get_normalized_dict()['PlayerGameLog']
        if games:
            last_game = games[0]
            player_team = last_game.get('TEAM_ABBREVIATION')
            matchup = last_game.get('MATCHUP', '')
            if ' vs. ' in matchup: return player_team, matchup.split(' vs. ')[1], 'Home'
            elif ' @ ' in matchup: return player_team, matchup.split(' @ ')[1], 'Away'
    except: pass
    return None, None, "N/A"

def calculate_ema(series, alpha=0.3):
    if series.empty: return 0.0
    ema = series.iloc[0]
    for i in range(1, len(series)):
        ema = alpha * series.iloc[i] + (1 - alpha) * ema
    return ema

def calculate_weighted_moving_average(series, method='exponential', span=20):
    """
    Calcule une moyenne mobile pondérée.
    - `series` : pd.Series ordonnée du plus récent au plus ancien (comme dans notre code).
    - `method` : 'exponential' ou 'linear'.
    - `span` : paramètre de lissage pour la méthode exponentielle ou nombre de matchs pour la linéaire.
    Retourne un float.
    """
    if series is None or series.empty:
        return 0.0

    # Nous voulons travailler du plus ancien au plus récent pour ewm
    try:
        s = series.dropna().astype(float)
    except Exception:
        s = series.dropna()
    if s.empty:
        return 0.0

    # La série dans la BDD arrive triée par date DESC (plus récent en première position).
    # Pour ewm nous la renversons pour avoir ordre chronologique.
    s_chrono = s.iloc[::-1]

    if method == 'exponential':
        # Utiliser pandas EWM pour un calcul robuste
        try:
            wma = s_chrono.ewm(span=span, adjust=False).mean().iloc[-1]
            return float(wma)
        except Exception:
            # Fallback simple : moyenne pondérée linéaire
            weights = list(range(1, min(len(s), span) + 1))
            vals = s.iloc[:len(weights)].values
            w = weights[::-1]
            return float((vals * w).sum() / sum(w))

    # Méthode linéaire : pondération décroissante (plus récent = plus de poids)
    if method == 'linear':
        n = min(len(s), span)
        vals = s.iloc[:n].values
        weights = list(range(n, 0, -1))
        return float((vals * weights).sum() / sum(weights))

    # Par défaut moyenne simple
    return float(s.mean())

def calculate_success_rate(df, stat_column, threshold):
    if df.empty or stat_column not in df.columns: return 0.0
    successes = (df[stat_column] > threshold).sum()
    total = len(df)
    return (successes / total * 100) if total > 0 else 0.0

def calculate_stat_projection(df, stat_column, player_name, team_code, opponent_code, location, season_avg=None, defensive_factor=1.0, offensive_boost=1.0, pace_factor=1.0, alpha=0.3, wma_span=20, event_id: str = None):
    if df.empty or stat_column not in df.columns: return None
    # Calculer une moyenne mobile pondérée (WMA / EMA) sur l'historique fourni
    series_full = df[stat_column]
    recent_wma = calculate_weighted_moving_average(series_full, method='exponential', span=wma_span)
    # Garder aussi l'EMA courte pour capter la forme immédiate
    ema_value = calculate_ema(df.head(20)[stat_column], alpha)
    h2h_avg, loc_avg = None, None
    if 'matchup' in df.columns:
        if opponent_code:
            df_h2h = df[df['matchup'].str.contains(opponent_code, na=False)]
            if not df_h2h.empty: h2h_avg = df_h2h[stat_column].mean()
        if location == 'Home': df_loc = df[df['matchup'].str.contains(' vs. ', na=False)]
        elif location == 'Away': df_loc = df[df['matchup'].str.contains(' @ ', na=False)]
        else: df_loc = pd.DataFrame()
        if not df_loc.empty: loc_avg = df_loc[stat_column].mean()
    # Pondération combinant WMA (forme récente/pondérée), EMA (forme courte), saison et éventuels h2h/loc.
    weights = {"wma": 0.45, "ema": 0.25, "season": 0.15, "h2h": 0.10, "loc": 0.05}
    # Si h2h ou loc manquent, redistribuer leurs poids vers la saison
    if h2h_avg is None:
        weights["season"] += weights.pop("h2h", 0)
        h2h_avg = season_avg
    if loc_avg is None:
        weights["season"] += weights.pop("loc", 0)
        loc_avg = season_avg

    weighted_projection = (
        recent_wma * weights.get("wma", 0) +
        ema_value * weights.get("ema", 0) +
        (season_avg or 0) * weights.get("season", 0) +
        (h2h_avg or 0) * weights.get("h2h", 0) +
        (loc_avg or 0) * weights.get("loc", 0)
    )
    adjusted_projection = weighted_projection * offensive_boost * defensive_factor * pace_factor
    consistency = df[stat_column].std()
    if pd.isna(consistency): consistency = 0.0
    if stat_column == 'points': risk_threshold = 5.0
    elif stat_column in ['rebounds', 'assists']:
        risk_threshold = 2.5
    else: risk_threshold = 0.5
    risk_level = "FAIBLE" if consistency <= risk_threshold else "ÉLEVÉ"
    # Use pre-fetched event odds when available to avoid repeated API lookups per player
    if event_id:
        odds_data = betting_provider.get_odds(player_name, team_code, stat_column, adjusted_projection)
    else:
        odds_data = betting_provider.get_odds(player_name, team_code, stat_column, adjusted_projection)
    if not odds_data:
        bookmaker_line = None
        over_odds = None
        under_odds = None
        bookmaker = None
        is_simulation = False
        # Pas d'analyse de success_rate si pas de ligne
        success_rate_on_line = 0.0
    else:
        bookmaker_line = odds_data.get('line')
        over_odds = odds_data.get('over_odds')
        under_odds = odds_data.get('under_odds')
        bookmaker = odds_data.get('bookmaker')
        is_simulation = odds_data.get('source', '').lower().startswith('simulation')
        success_rate_on_line = calculate_success_rate(df, stat_column, bookmaker_line)
    if success_rate_on_line >= 65: confidence = "🔥 FORTE"
    elif success_rate_on_line >= 55: confidence = "✅ BONNE"
    else: confidence = "⚠️ MOYENNE"
    milestones = calculate_milestone_probabilities(adjusted_projection, consistency, stat_column)
    return {
        "projection": round(adjusted_projection, 1), "raw_projection": round(weighted_projection, 1), "ema": round(ema_value, 1),
        "recent_avg": round(recent_wma, 1), "h2h_avg": round(h2h_avg, 1) if h2h_avg else "N/A", "loc_avg": round(loc_avg, 1) if loc_avg else "N/A",
        "consistency": round(consistency, 2), "risk_level": risk_level, "games_analyzed": int(len(df)), "defensive_factor": round(defensive_factor, 2),
        "offensive_boost": round(offensive_boost, 2), "pace_factor": round(pace_factor, 2), "betting_line": bookmaker_line, "odds_over": over_odds,
        "odds_under": under_odds, "bookmaker": bookmaker, "is_simulation": is_simulation,
        "success_rate_on_line": round(success_rate_on_line, 1), "confidence": confidence, "milestones": milestones,
        "bet_analysis": [{"line": bookmaker_line, "success_rate": round(success_rate_on_line, 1), "confidence": confidence}]
    }

# --- ROUTES ---
@app.get("/players/")
def get_all_players(db: Session = Depends(get_db)):
    players = db.query(models.Player).limit(500).all()
    # ✅ Auto-réparation : Si la table est vide, on lance la synchro
    if not players:
        try:
            import sys, os
            sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'data-pipeline'))
            from populate_players import sync_players
            print("⚠️ Table joueurs vide. Lancement de la synchronisation...")
            sync_players()
            players = db.query(models.Player).limit(500).all()
        except Exception as e:
            print(f"❌ Erreur auto-sync joueurs : {e}")
    return players

@app.get("/games/week")
def get_weekly_games(force_refresh: bool = False, db: Session = Depends(get_db)):
    import sys, os
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'data-pipeline'))
    from sync_weekly_games import sync_weekly_games, get_weekly_games_from_db
    
    # Synchro auto si nécessaire (géré par le script)
    sync_result = sync_weekly_games(force_refresh=force_refresh)
    games = get_weekly_games_from_db()

    # Enrichir les games avec un résumé des blessures de la semaine (par équipe)
    try:
        team_codes = set()
        for g in games:
            if g.get('home_team'): team_codes.add(g.get('home_team'))
            if g.get('away_team'): team_codes.add(g.get('away_team'))

        injuries_summary = {}
        if team_codes:
            from sqlalchemy import text
            codes_list = list(team_codes)
            # Query les blessures actives pour les joueurs de ces équipes
            q = text("""
                SELECT p.full_name, p.nba_player_id, pi.status, pi.injury_type, pi.injury_detail, pi.play_probability, pi.source, pi.last_verified_at
                FROM player_injuries pi
                JOIN player p ON p.id = pi.player_id
                WHERE pi.is_active = TRUE
                AND p.team_id IS NOT NULL
            """)
            res = db.execute(q).fetchall()
            for row in res:
                player_name = row[0]
                nba_player_id = row[1]
                status = row[2]
                injury_type = row[3]
                detail = row[4]
                prob = row[5]
                source = row[6]
                last_verified = row[7].isoformat() if row[7] else None
                # We don't have direct team code here; we'll search player's current team from player table
                player_row = db.query(models.Player).filter(models.Player.nba_player_id == nba_player_id).first()
                team_code = None
                if player_row and getattr(player_row, 'team_id', None):
                    # try to resolve code from team table
                    from sqlalchemy import text as _text
                    t = db.execute(_text("SELECT code FROM team WHERE id = :tid"), {"tid": player_row.team_id}).fetchone()
                    if t: team_code = t[0]

                if not team_code:
                    team_code = 'N/A'

                injuries_summary.setdefault(team_code, []).append({
                    'player': player_name,
                    'nba_player_id': nba_player_id,
                    'status': status,
                    'type': injury_type,
                    'detail': detail,
                    'play_probability': prob,
                    'source': source,
                    'last_verified': last_verified
                })
    except Exception:
        injuries_summary = {}

    return {"sync_info": sync_result, "total_games": len(games), "games": games, "injuries_summary": injuries_summary}
@app.get("/injuries/active")
def get_active_injuries(force_refresh: bool = False, db: Session = Depends(get_db)):
    import sys, os
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'data-pipeline'))
    from sync_injuries import sync_injuries, get_active_injuries_from_db
    sync_result = sync_injuries(force_refresh=force_refresh)
    injuries = get_active_injuries_from_db()
    return {"sync_info": sync_result, "total_injuries": len(injuries), "injuries": injuries}
@app.get("/injuries/player/{player_id}")
def get_player_injury_status(player_id: int, db: Session = Depends(get_db)):
    player = db.query(models.Player).filter(models.Player.id == player_id).first()
    if not player: raise HTTPException(status_code=404, detail="Joueur non trouvé")
    active_injury = db.query(models.PlayerInjury).filter(models.PlayerInjury.player_id == player_id, models.PlayerInjury.is_active == True).first()
    if not active_injury: return {"player": player.full_name, "status": "HEALTHY", "injury": None}
    return {"player": player.full_name, "status": active_injury.status, "injury": {"type": active_injury.injury_type, "detail": active_injury.injury_detail, "play_probability": active_injury.play_probability, "injury_date": active_injury.injury_date.isoformat() if active_injury.injury_date else None, "last_verified": active_injury.last_verified_at.isoformat() if active_injury.last_verified_at else None}}
@app.get("/games/{nba_game_id}/lineups")
def get_game_lineups(nba_game_id: str, db: Session = Depends(get_db)):
    game = db.query(models.GameSchedule).filter(models.GameSchedule.nba_game_id == nba_game_id).first()
    if not game: raise HTTPException(status_code=404, detail="Match non trouvé")
    home_roster = get_roster_for_team(game.home_team_code, db)
    away_roster = get_roster_for_team(game.away_team_code, db)
    return {"nba_game_id": nba_game_id, "home_team": game.home_team_code, "away_team": game.away_team_code, "home_roster": home_roster, "away_roster": away_roster}
@app.get("/projection/{player_id}")
def compute_projection(player_id: int, games: int = 82, game_id: str = None, db: Session = Depends(get_db), odds_event_id: str = None):
    player = db.query(models.Player).filter(models.Player.id == player_id).first()
    if not player: raise HTTPException(status_code=404, detail="Joueur non trouvé")
    query = f"SELECT s.*, g.game_date FROM player_game_stats s JOIN game g ON s.game_id = g.id WHERE s.player_id = {player_id} ORDER BY g.game_date DESC"
    df = pd.read_sql(query, engine)
    if not df.empty and len(df) > games: df = df.head(games)
    if df.empty:
        try:
            import sys, os
            sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'data-pipeline'))
            from populate_stats import sync_player_stats
            new_games, cached_games, updated_count = sync_player_stats(player.nba_player_id, limit=games)
            if new_games == 0 and cached_games == 0 and updated_count == 0:
                return {"message": "Impossible de récupérer les données NBA pour ce joueur."}
            df = pd.read_sql(query, engine)
            if len(df) > games: df = df.head(games)
        except Exception as e: return {"message": f"Erreur lors du téléchargement des données : {str(e)}"}
    player_team_code, opponent_code, location = get_game_context(player.nba_player_id, db, game_id, player.full_name)
    defensive_factors = {"points": 1.0, "rebounds": 1.0, "assists": 1.0, "three_points_made": 1.0, "steals": 1.0, "blocks": 1.0}
    missing_defenders = []
    pace_factor = 1.0
    if opponent_code:
        pace_factor = get_pace_factor(opponent_code)
        opponent_roster = get_roster_for_team(opponent_code, db)
        adjustments, missing_defenders = adjust_defense_for_injuries(opponent_code, opponent_roster)
        for stat in defensive_factors.keys():
            base_factor = get_defensive_factor(opponent_code, player.position)
            defensive_factors[stat] = base_factor + adjustments.get(stat, 0.0)
        defense_info = get_defense_analysis(opponent_code, missing_defenders, pace_factor, player.position)
    else:
        defense_info = get_defense_analysis(None)
        player_team_code = "N/A"
    offensive_boosts = {"points": 1.0, "rebounds": 1.0, "assists": 1.0, "three_points_made": 1.0, "steals": 1.0, "blocks": 1.0}
    missing_stars = []
    if player_team_code and player_team_code != "N/A":
        player_roster = get_roster_for_team(player_team_code, db)
        offensive_boosts, missing_stars = get_offensive_boost(player.full_name, player_team_code, player_roster)
    stats_to_project = ["points", "rebounds", "assists", "three_points_made", "steals", "blocks"]
    projections = {}
    for stat in stats_to_project:
        season_avg = df[stat].mean()
        # pass the odds_event_id (if provided) to calculate_stat_projection so it can use pre-fetched odds
        use_event = odds_event_id or game_id
        projections[stat] = calculate_stat_projection(
            df, stat, player.full_name, player_team_code, opponent_code, location,
            season_avg, defensive_factors.get(stat, 1.0), offensive_boosts.get(stat, 1.0), pace_factor, event_id=use_event
        )
    if not all(projections.values()): return {"message": "Erreur lors du calcul des projections."}
    stats_payload = {
        "opponent": opponent_code, "location": location, "defense_rating": defense_info["rating"], "defense_description": defense_info["description"],
        "projection_points": projections["points"]["projection"], "betting_line_points": projections["points"]["betting_line"],
        "betting_odds_points": projections["points"]["odds_over"], "betting_bookmaker": projections["points"]["bookmaker"], "missing_stars": missing_stars
    }
    jimmy_narrative = ask_jimmy(player.full_name, stats_payload)
    last_games = []
    for _, row in df.head(10).iterrows():
        last_games.append({
            "date": row["game_date"].isoformat() if row["game_date"] else "N/A",
            "points": row["points"], "rebounds": row["rebounds"], "assists": row["assists"],
            "3pm": row.get("three_points_made", 0), "steals": row.get("steals", 0), "blocks": row.get("blocks", 0), "min": int(row.get("minutes_played", 0))
        })
    return {
        "player": player.full_name, "nba_player_id": player.nba_player_id, "position": player.position, "opponent": opponent_code, "location": location,
        "defensive_context": defense_info, "offensive_context": {"missing_stars": missing_stars}, "projections": projections,
        "jimmy_advice": jimmy_narrative, "games_analyzed": len(df), "last_games": last_games
    }

# ✅ NOUVELLE LOGIQUE POUR LA CARTE DE JEU (ASYNCHRONE)
def run_best_bets_scan(job_id: str, markets: list[str] | None = None):
    """Exécute le scan des matchs du jour.
    Args:
        job_id: identifiant du job
        markets: liste des stat keys à analyser (ex: ['points','three_points_made'])
    """
    print(f"🚀 Démarrage du scan {job_id}...")
    with Session(engine) as db:
        # Utiliser un objet date pour la comparaison avec game_date (type DATE)
        today = datetime.now().date()
        all_games = db.query(models.GameSchedule).filter(models.GameSchedule.game_date == today).all()
        if not all_games:
            print("⚠️ Aucun match aujourd'hui.")
            ANALYSIS_JOBS[job_id] = {"status": "complete", "data": [], "progress": 100, "message": "Aucun match aujourd'hui."}
            return
        
        best_bets = []
        total_games = len(all_games)
        
        for i, game in enumerate(all_games):
            # Mise à jour progression
            progress = int((i / total_games) * 100)
            ANALYSIS_JOBS[job_id] = {"status": "running", "data": best_bets, "progress": progress}
            
            print(f"🔍 Analyse match {game.away_team_code} @ {game.home_team_code}...")

            # 1. Récupérer l'ID The-Odds-API pour ce match
            # On utilise l'équipe à domicile pour trouver le match
            try:
                odds_event_id = betting_provider.get_event_id_for_team(game.home_team_code)
            except Exception as e:
                print(f"   ❌ Erreur récupération event ID pour {game.home_team_code}: {e}")
                odds_event_id = None
            
            if not odds_event_id:
                 print(f"   ⏩ Pas d'événement The-Odds-API trouvé pour {game.home_team_code}, on continue sans cotes.")
                 # On continue quand même pour avoir les projections !

            # 2. Vérifier si l'événement a des cotes Bet365
            event_has_bet365 = False
            if odds_event_id:
                try:
                    event_has_bet365 = betting_provider.has_bet365_for_event(odds_event_id, market='player_points')
                except Exception as e:
                    print(f"   ❌ Erreur vérification Bet365 pour {odds_event_id}: {e}")
            
            if not event_has_bet365:
                print(f"   ⏩ Pas de cotes Bet365 pour l'event {odds_event_id}, on continue sans cotes.")

            home_roster = get_roster_for_team(game.home_team_code, db)
            away_roster = get_roster_for_team(game.away_team_code, db)
            # Limiter le nombre de joueurs par équipe (fixe)
            all_players = (home_roster[:MAX_PLAYERS_PER_TEAM] if home_roster else []) + (away_roster[:MAX_PLAYERS_PER_TEAM] if away_roster else [])
            # Dédupliquer joueurs déjà traités pour ce scan
            processed_players = set()
            
            for p in all_players:
                if not p.get('id'): continue
                if p['id'] in processed_players: continue
                if p.get('injury_status', 'HEALTHY') != 'HEALTHY': continue
                
                # ✅ Vérification Cache Journalier
                cache_key = f"{p['id']}_{today}"
                if cache_key in DAILY_CACHE:
                    # print(f"   📦 Joueur {p['full_name']} récupéré du cache.")
                    proj_data = DAILY_CACHE[cache_key]
                else:
                    try:
                        # Utiliser une fenêtre large (82 matchs) pour la projection
                        proj_data = compute_projection(p['id'], games=82, game_id=game.nba_game_id, db=db)
                        if "projections" in proj_data:
                            DAILY_CACHE[cache_key] = proj_data
                    except Exception as e:
                        print(f"   ❌ Erreur analyse {p.get('full_name')}: {e}")
                        continue

                if "projections" not in proj_data: continue
                
                # Marchés à analyser (par défaut si non fournis)
                markets_to_check = markets or ["three_points_made", "points", "assists", "rebounds"]
                for stat_name in markets_to_check:
                    stat_data = proj_data["projections"].get(stat_name)
                    if not stat_data: continue
                    
                    # Récupérer les cotes si disponibles
                    line = stat_data.get('betting_line')
                    odds_over = stat_data.get('odds_over')
                    odds_under = stat_data.get('odds_under')
                    
                    projection = stat_data.get('projection')
                    consistency = stat_data.get('consistency')

                    # Si on a une ligne, on calcule l'EV
                    if line is not None:
                        prob_over = 1 - cumulative_distribution_function(line - 0.5, projection, consistency)
                        prob_under = cumulative_distribution_function(line + 0.5, projection, consistency)
                        
                        if odds_over and odds_over >= 1.075:
                            ev_over = (prob_over * odds_over) - 1
                            if ev_over > 0.05: # On ne garde que les EV > 5%
                                best_bets.append({
                                    "player": proj_data['player'], "team": game.home_team_code if p in home_roster else game.away_team_code,
                                    "opponent": proj_data['opponent'], "market": stat_name, "line": line, "odds": odds_over,
                                    "projection": projection, "confidence": stat_data['confidence'], "ev": round(ev_over * 100, 1),
                                    "game_id": game.nba_game_id, "player_id": p['id'], "bet_type": "Over"
                                })
                        
                        if odds_under and odds_under >= 1.075:
                            ev_under = (prob_under * odds_under) - 1
                            if ev_under > 0.05:
                                best_bets.append({
                                    "player": proj_data['player'], "team": game.home_team_code if p in home_roster else game.away_team_code,
                                    "opponent": proj_data['opponent'], "market": stat_name, "line": line, "odds": odds_under,
                                    "projection": projection, "confidence": "🔥 FORTE (Under)", "ev": round(ev_under * 100, 1),
                                    "game_id": game.nba_game_id, "player_id": p['id'], "bet_type": "Under"
                                })
                    
                    # 🚨 NOUVEAU : Si pas de ligne, on ajoute quand même les "Top Projections" si l'écart est grand
                    # Cela permet d'avoir des résultats même sans API de paris
                    elif projection > 20: # Exemple arbitraire pour filtrer
                         # On simule une entrée pour que l'utilisateur voit quelque chose
                         pass 

                processed_players.add(p['id'])

        best_bets.sort(key=lambda x: x['ev'], reverse=True)
        ANALYSIS_JOBS[job_id] = {"status": "complete", "data": best_bets, "progress": 100}
        print(f"✅ Scan terminé : {len(best_bets)} opportunités trouvées.")

@app.post("/analysis/start-scan")
def start_best_bets_scan(scan_req: ScanRequest, background_tasks: BackgroundTasks):
    """Démarre un job d'analyse asynchrone.
    Corps attendu JSON: {"markets": ["points","three_points_made"], "max_players_per_team": 6}
    """
    job_id = str(uuid.uuid4())
    ANALYSIS_JOBS[job_id] = {"status": "running", "data": [], "progress": 0}
    # Lancer la tâche en arrière-plan avec les paramètres fournis
    background_tasks.add_task(run_best_bets_scan, job_id, scan_req.markets)
    return {"job_id": job_id}

@app.get("/analysis/scan-results/{job_id}")
def get_scan_results(job_id: str):
    job = ANALYSIS_JOBS.get(job_id)
    if not job: raise HTTPException(status_code=404, detail="Job non trouvé.")
    return job

# ✅ NOUVEL ENDPOINT : GÉNÉRATEUR DE TICKET
@app.post("/analysis/build-parlay")
def build_parlay(bets: List[Bet]):
    """Construit des tickets optimisés à partir d'une liste de paris."""
    if not bets:
        return {"safe_bet": None, "value_bet": None}

    # 1. Ticket "Sûreté" (Haute probabilité, même si cote faible)
    # On trie par confiance puis par EV
    bets.sort(key=lambda x: (x.confidence, x.ev), reverse=True)
    safe_bets = bets[:3] # On prend les 3 plus sûrs
    
    safe_parlay = {
        "legs": [],
        "total_odds": 1.0,
        "type": "Sûreté"
    }
    
    # Calcul de la cote totale
    for bet in safe_bets:
        safe_parlay["legs"].append(bet.dict())
        safe_parlay["total_odds"] *= bet.odds
    
    # 2. Ticket "Value" (Meilleur EV)
    bets.sort(key=lambda x: x.ev, reverse=True)
    value_bets = bets[:2] # On prend les 2 meilleurs EV
    
    value_parlay = {
        "legs": [],
        "total_odds": 1.0,
        "type": "Value"
    }
    
    for bet in value_bets:
        value_parlay["legs"].append(bet.dict())
        value_parlay["total_odds"] *= bet.odds

    return {"safe_bet": safe_parlay, "value_bet": value_parlay}

@app.get("/health")
def health():
    return {"status": "ok"}
