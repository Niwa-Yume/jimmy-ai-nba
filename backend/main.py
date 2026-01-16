from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Query, Body
from sqlalchemy.orm import Session
from sqlalchemy import func, text
import pandas as pd
import os
from backend.database import get_db, engine
from backend import models
from backend.ai_agent import ask_jimmy
from backend.defense_ratings import get_defensive_factor, get_defense_analysis, adjust_defense_for_injuries, \
    get_pace_factor, NBA_TEAM_CODES
from backend.offensive_impact import get_offensive_boost
from backend.betting_service import BettingOddsProvider
from backend.probability import calculate_milestone_probabilities, cumulative_distribution_function
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
from datetime import datetime, timedelta
import uuid
from typing import List, Optional
from pydantic import BaseModel
import random
import subprocess
from pathlib import Path

# --- CACHE TTL CONFIGS ---
PLAYER_STATS_TTL_HOURS = 1


# ✅ Import du module de Scoring
from backend.scoring import calculate_confidence_score
from backend.advanced_scoring import AdvancedScorer

# ✅ Import NBA API
from nba_api.stats.endpoints import commonteamroster, playergamelog

# ✅ Création des tables
models.Base.metadata.create_all(bind=engine)

# ✅ CONFIGURATION DES HEADERS (Anti-Blocage NBA)
NBA_HEADERS = {
    'Host': 'stats.nba.com',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Referer': 'https://www.nba.com/',
    'Origin': 'https://www.nba.com',
}


# ✅ MIGRATION AUTO
def run_migrations():
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                              CREATE TABLE IF NOT EXISTS player_injuries
                              (
                                  id
                                  SERIAL
                                  PRIMARY
                                  KEY,
                                  player_id
                                  INTEGER
                                  REFERENCES
                                  player
                              (
                                  id
                              ) ON DELETE CASCADE,
                                  nba_player_id INTEGER NOT NULL,
                                  status VARCHAR
                              (
                                  50
                              ) NOT NULL,
                                  injury_type VARCHAR
                              (
                                  100
                              ),
                                  injury_detail TEXT,
                                  injury_date DATE,
                                  expected_return DATE,
                                  play_probability INTEGER,
                                  source VARCHAR
                              (
                                  50
                              ) DEFAULT 'ESPN',
                                  source_url TEXT,
                                  is_active BOOLEAN DEFAULT TRUE,
                                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                  last_verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                                  )
                              """))
            conn.execute(text("""
                              CREATE TABLE IF NOT EXISTS games_schedule
                              (
                                  id
                                  SERIAL
                                  PRIMARY
                                  KEY,
                                  nba_game_id
                                  VARCHAR
                              (
                                  50
                              ) UNIQUE NOT NULL,
                                  game_date DATE NOT NULL,
                                  game_time VARCHAR
                              (
                                  20
                              ),
                                  home_team_code VARCHAR
                              (
                                  3
                              ) NOT NULL,
                                  away_team_code VARCHAR
                              (
                                  3
                              ) NOT NULL,
                                  home_team_id INTEGER,
                                  away_team_id INTEGER,
                                  status VARCHAR
                              (
                                  20
                              ) DEFAULT 'SCHEDULED',
                                  home_score INTEGER,
                                  away_score INTEGER,
                                  arena VARCHAR
                              (
                                  200
                              ),
                                  tv_broadcast VARCHAR
                              (
                                  100
                              ),
                                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                  last_fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                                  )
                              """))
            # La table betting_odds est gérée par models.Base.metadata.create_all
            conn.execute(
                text("ALTER TABLE player ADD COLUMN IF NOT EXISTS current_injury_status VARCHAR(50) DEFAULT 'HEALTHY'"))
            conn.execute(text("ALTER TABLE player ADD COLUMN IF NOT EXISTS injury_updated_at TIMESTAMP"))
            conn.commit()
    except Exception as e:
        print(f"⚠️ Erreur migrations : {e}")


run_migrations()

app = FastAPI(title="Jimmy.AI API", description="Moteur de prédiction NBA")

betting_provider = BettingOddsProvider()
ANALYSIS_JOBS = {}
DAILY_CACHE = {}


class Bet(BaseModel):
    # ...existing code...
    bet_type: str


class ScanRequest(BaseModel):
    markets: Optional[list[str]] = None


# --- ROUTES ANALYSE / SCAN ---
@app.post("/analysis/start-scan")
async def start_scan(req: ScanRequest | None = Body(None), background_tasks: BackgroundTasks = None):
    job_id = str(uuid.uuid4())
    ANALYSIS_JOBS[job_id] = {"status": "queued", "data": [], "progress": 0}
    markets = req.markets if req and req.markets else None
    background_tasks.add_task(run_best_bets_scan, job_id, markets)
    return {"job_id": job_id, "status": "queued"}


@app.get("/games/week")
def get_weekly_games(days: int = 7, db: Session = Depends(get_db)):
    days = max(1, min(days, 14))  # clamp between 1 and 14 days
    # ✅ FIX TIMEZONE: Utiliser la timezone NBA (US Eastern)
    from zoneinfo import ZoneInfo
    eastern = ZoneInfo("America/New_York")
    today = datetime.now(eastern).date()
    end = today + timedelta(days=days)
    games = db.query(models.GameSchedule).filter(models.GameSchedule.game_date >= today,
                                                models.GameSchedule.game_date <= end).order_by(models.GameSchedule.game_date).all()
    return {
        "games": [
            {
                "nba_game_id": g.nba_game_id,
                "game_date": g.game_date.isoformat() if g.game_date else None,
                "game_time": g.game_time,
                "home_team": g.home_team_code,
                "away_team": g.away_team_code,
                "status": g.status,
                "arena": g.arena,
            }
            for g in games
        ]
    }


@app.get("/analysis/scan-results/{job_id}")
def get_scan_results(job_id: str):
    job = ANALYSIS_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job inconnu")
    return job


# --- HELPERS ---
_LINEUPS_CACHE: dict[str, dict] = {}


# --- HELPER FUNCTIONS ---

def _normalize_team_code(code: str) -> str:
    if not code: return code
    code = code.upper()
    aliases = {"BRK": "BKN", "PHO": "PHX", "CHO": "CHA", "NO": "NOP", "NY": "NYK", "SA": "SAS", "GS": "GSW",
               "UT": "UTA", "UTAH": "UTA"}
    return aliases.get(code, code)


def _code_to_team_id(code: str) -> int | None:
    if not code: return None
    code = code.upper()
    reverse = {v: k for k, v in NBA_TEAM_CODES.items()}
    return reverse.get(code)


def _get_espn_team_id(team_code: str) -> int | None:
    ESPN_IDS = {"ATL": 1, "BOS": 2, "NOP": 3, "CHI": 4, "CLE": 5, "DAL": 6, "DEN": 7, "DET": 8, "GSW": 9, "HOU": 10,
                "IND": 11, "LAC": 12, "LAL": 13, "MIA": 14, "MIL": 15, "MIN": 16, "BKN": 17, "NYK": 18, "ORL": 19,
                "IND": 20, "PHI": 21, "PHX": 22, "POR": 23, "SAC": 24, "SAS": 25, "OKC": 25, "TOR": 28, "UTA": 26,
                "MEM": 29, "WAS": 30, "CHA": 30}
    return ESPN_IDS.get(_normalize_team_code(team_code))


def _fetch_roster_fallback_espn(team_code: str):
    tid = _get_espn_team_id(team_code)
    if not tid: return []
    try:
        url = f"https://site.web.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{tid}/roster"
        res = requests.get(url, timeout=5).json()
        players = []
        for grp in res.get('athletes', []):
            for it in grp.get('items', []):
                players.append({
                    "full_name": it.get('fullName'),
                    "nba_id": 0,
                    "position": it.get('position', {}).get('abbreviation'),
                    "injury_status": "UNKNOWN"
                })
        return players
    except:
        return []


def _fetch_team_roster_nba_api(team_code: str):
    team_id = _code_to_team_id(team_code)
    if not team_id: return []

    cache_key = f"NBA_API:{team_code}"
    cached = _LINEUPS_CACHE.get(cache_key)
    if cached and (time.time() - cached.get("ts", 0)) < 3600:
        return cached.get("players", [])

    max_retries = 3
    for attempt in range(max_retries):
        try:
            time.sleep(random.uniform(0.5, 1.5))
            roster = commonteamroster.CommonTeamRoster(team_id=team_id, season='2024-25', headers=NBA_HEADERS,
                                                       timeout=10)
            data = roster.get_normalized_dict()['CommonTeamRoster']
            players = []
            for p in data:
                players.append({
                    "full_name": p['PLAYER'],
                    "nba_id": p['PLAYER_ID'],
                    "position": p['POSITION'],
                    "injury_status": "UNKNOWN"
                })
            if players:
                _LINEUPS_CACHE[cache_key] = {"ts": time.time(), "players": players}
                return players
        except Exception as e:
            print(f"   ⚠️ Essai {attempt + 1}/{max_retries} échoué pour {team_code} : {e}")
            time.sleep(2)

    print(f"   ❌ Échec total NBA API pour {team_code}. Passage au Fallback ESPN.")
    return _fetch_roster_fallback_espn(team_code)


def _attach_local_ids_and_injuries(db: Session, players: list[dict]):
    for p in players:
        name = (p.get("full_name") or "").strip()
        nba_id = p.get("nba_id", 0)

        if name:
            row = None
            if nba_id > 0:
                row = db.query(models.Player).filter(models.Player.nba_player_id == nba_id).first()
            if not row:
                row = db.query(models.Player).filter(func.lower(models.Player.full_name) == name.lower()).first()

            if row:
                p["id"] = row.id
                if row.current_injury_status:
                    p["injury_status"] = row.current_injury_status
                else:
                    inj = db.query(models.PlayerInjury).filter(models.PlayerInjury.player_id == row.id,
                                                               models.PlayerInjury.is_active == True).first()
                    p["injury_status"] = inj.status if inj else "HEALTHY"
                inj = db.query(models.PlayerInjury).filter(models.PlayerInjury.player_id == row.id,
                                                           models.PlayerInjury.is_active == True).first()
                if inj:
                    p["play_probability"] = inj.play_probability
                if row.nba_player_id == 0 and nba_id > 0:
                    row.nba_player_id = nba_id
                    db.commit()
            else:
                try:
                    new_p = models.Player(
                        full_name=name,
                        nba_player_id=nba_id,
                        position=p.get('position', 'UNK'),
                        is_active=True,
                        current_injury_status="HEALTHY"
                    )
                    db.add(new_p)
                    db.commit()
                    db.refresh(new_p)
                    p["id"] = new_p.id
                    p["injury_status"] = "HEALTHY"
                except Exception as e:
                    print(f"   ❌ Erreur création joueur {name}: {e}")
                    db.rollback()
                    p["id"] = None
    return players


def get_roster_for_team(team_code: str, db: Session):
    roster = _fetch_team_roster_nba_api(team_code)
    return _attach_local_ids_and_injuries(db, roster)


# --- PROJECTIONS & STATS ---

def calculate_stat_projection(df, stat_column, player_name, team_code, opponent_code, location, season_avg=None,
                              defensive_factor=1.0, offensive_boost=1.0, pace_factor=1.0, event_id: str = None):
    if df.empty or stat_column not in df.columns: return None

    recent_stats = df.head(10)[stat_column]
    recent_avg = recent_stats.mean()
    consistency = recent_stats.std()
    if pd.isna(consistency): consistency = 0.0

    weighted_proj = (recent_avg * 0.6) + ((season_avg or recent_avg) * 0.4)
    final_proj = weighted_proj * offensive_boost * defensive_factor * pace_factor

    # On ne renvoie pas de cotes ici, elles seront attachées dans la boucle principale

    return {
        "projection": round(final_proj, 1),
        "consistency": round(consistency, 2)
    }


def compute_projection(player_id: int, games: int = 82, game_id: str = None, db: Session = Depends(get_db),
                       odds_event_id: str = None):
    player = db.query(models.Player).filter(models.Player.id == player_id).first()
    if not player:
        print(f"   ⚠️ compute_projection: player_id={player_id} introuvable")
        return {}

    query = f"SELECT * FROM player_game_stats WHERE player_id = {player_id} ORDER BY game_id DESC LIMIT {games}"
    df = pd.read_sql(query, engine)

    print(f"   🔍 Stats pour {player.full_name} (id={player_id}): {len(df)} matchs trouvés")

    # TTL pour éviter les re-fetch API si déjà rafraîchi récemment
    if df.empty:
        last_updated = None
    else:
        try:
            # suppose une colonne created_at/updated_at; fallback si absent
            last_updated = df['game_id'].max()  # placeholder fallback
        except Exception:
            last_updated = None

    needs_refresh = df.empty
    if last_updated:
        try:
            # Simpliste : on ne re-fetch pas si stats présentes et TTL 1h sur la dernière stat
            # On considère que game_id max ~ ordre chrono; si besoin, remplacer par updated_at
            needs_refresh = False
        except Exception:
            needs_refresh = True

    if needs_refresh:
        if not player.nba_player_id or player.nba_player_id == 0:
            return {}
        try:
            sys_path_added = False
            import sys
            if 'data-pipeline' not in sys.path:
                sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'data-pipeline'))
                sys_path_added = True

            from populate_stats import sync_player_stats
            time.sleep(0.4)  # Throttling léger
            sync_player_stats(player.nba_player_id, limit=games)
            df = pd.read_sql(query, engine)
        except Exception as e:
            return {}

    if df.empty:
        print(f"   ⚠️ Aucune stat pour {player.full_name} (nba_player_id={player.nba_player_id}), tentative refresh...")
        if not player.nba_player_id or player.nba_player_id == 0:
            return {}
        try:
            sys_path_added = False
            import sys
            if 'data-pipeline' not in sys.path:
                sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'data-pipeline'))
                sys_path_added = True

            from populate_stats import sync_player_stats
            time.sleep(0.4)  # Throttling léger
            sync_player_stats(player.nba_player_id, limit=games)
            df = pd.read_sql(query, engine)
        except Exception as e:
            return {}

    if df.empty:
        print(f"   ❌ TOUJOURS vide après refresh pour {player.full_name}")
        return {}

    projections = {}
    stats_list = ["points", "rebounds", "assists"]

    game = db.query(models.GameSchedule).filter(models.GameSchedule.nba_game_id == game_id).first()
    team_code = game.home_team_code if game else "N/A"

    # Taille d'échantillon sur le dataframe complet
    sample_size = len(df)

    for stat in stats_list:
        if stat not in df.columns: continue
        season_avg = df[stat].mean()
        def_factor = 1.0

        proj = calculate_stat_projection(
            df, stat, player.full_name, team_code, None, None,
            season_avg, def_factor, 1.0, 1.0, event_id=odds_event_id
        )
        if proj: projections[stat] = proj

    print(f"   ✅ Projections calculées pour {player.full_name}: {list(projections.keys())}")
    return {
        "player": player.full_name,
        "opponent": "OPP",
        "projections": projections,
        "sample_size": sample_size
    }


# --- SYNC INJURIES HELPER ---
def _run_sync_injuries():
    try:
        base_dir = Path(__file__).resolve().parent.parent
        script_path = base_dir / "data-pipeline" / "sync_injuries.py"
        if not script_path.exists():
            # Essayer un autre chemin éventuel
            alt_path = base_dir / "data" / "data-pipeline" / "sync_injuries.py"
            if alt_path.exists():
                script_path = alt_path
        if not script_path.exists():
            print("⚠️ sync_injuries.py introuvable (paths testés: data-pipeline/, data/data-pipeline/). Skip refresh blessures.")
            return
        subprocess.run(["python", str(script_path), "--quiet"], check=False, timeout=120)
    except Exception as e:
        print(f"⚠️ sync_injuries échoué : {e}")


def _run_sync_games():
    try:
        base_dir = Path(__file__).resolve().parent.parent
        script_path = base_dir / "data-pipeline" / "sync_weekly_games_v2.py"
        if not script_path.exists():
            print("⚠️ sync_weekly_games_v2.py introuvable. Skip refresh matchs.")
            return
        subprocess.run(["python", str(script_path)], check=False, timeout=120)
    except Exception as e:
        print(f"⚠️ sync_games échoué : {e}")


def _run_sync_players():
    try:
        base_dir = Path(__file__).resolve().parent.parent
        script_path = base_dir / "data-pipeline" / "populate_players.py"
        if not script_path.exists():
            print("⚠️ populate_players.py introuvable. Skip refresh joueurs.")
            return
        subprocess.run(["python", str(script_path)], check=False, timeout=120)
    except Exception as e:
        print(f"⚠️ sync_players échoué : {e}")


def _run_sync_stats():
    try:
        base_dir = Path(__file__).resolve().parent.parent
        script_path = base_dir / "data-pipeline" / "populate_stats.py"
        if not script_path.exists():
            print("⚠️ populate_stats.py introuvable. Skip refresh stats.")
            return
        subprocess.run(["python", str(script_path)], check=False, timeout=120)
    except Exception as e:
        print(f"⚠️ sync_stats échoué : {e}")


# --- MAIN SCAN LOOP ---


def run_best_bets_scan(job_id: str, markets: list[str] | None = None):
    print(f"🚀 Démarrage du scan {job_id}...")

    # Afficher l'état du quota API
    if betting_provider.api_keys:
        print(f"🔑 The-Odds-API: {len(betting_provider.api_keys)} clé(s) disponible(s)")
        print(f"   📡 Clé active: {betting_provider.api_key[:6]}*** ({betting_provider.current_key_index + 1}/{len(betting_provider.api_keys)})")
    else:
        print(f"🚨 AUCUNE CLÉ The-Odds-API DISPONIBLE - Configurez THE_ODDS_API_KEY dans .env")

    _run_sync_injuries()
    _run_sync_games()
    _run_sync_players()
    _run_sync_stats()
    with Session(engine) as db:
        scorer = AdvancedScorer(db)

        # ✅ TOUJOURS calculer la date du jour en timezone NBA (Eastern)
        from zoneinfo import ZoneInfo
        eastern = ZoneInfo("America/New_York")
        now_eastern = datetime.now(eastern)
        today_eastern = now_eastern.date()
        tomorrow_eastern = today_eastern + timedelta(days=1)

        print(f"🕐 Heure serveur (UTC): {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🕐 Heure NBA (Eastern): {now_eastern.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📅 Recherche des matchs: {today_eastern} et {tomorrow_eastern}")

        # ✅ PURGER automatiquement les snapshots obsolètes (matchs d'hier ou avant)
        cutoff_date = today_eastern - timedelta(days=1)
        obsolete_game_ids = [g[0] for g in db.query(models.GameSchedule.nba_game_id).filter(
            models.GameSchedule.game_date < cutoff_date
        ).all()]

        if obsolete_game_ids:
            deleted = db.query(models.OddsSnapshot).filter(
                models.OddsSnapshot.game_id.in_(obsolete_game_ids)
            ).delete(synchronize_session=False)
            if deleted > 0:
                db.commit()
                print(f"🗑️ {deleted} snapshots obsolètes supprimés (matchs < {cutoff_date})")

        # ✅ RÉCUPÉRER UNIQUEMENT les matchs d'aujourd'hui/demain avec statut valide
        all_games = db.query(models.GameSchedule).filter(
            models.GameSchedule.game_date.in_([today_eastern, tomorrow_eastern]),
            models.GameSchedule.status.in_(['SCHEDULED', 'IN_PROGRESS', 'PREGAME'])
        ).order_by(
            models.GameSchedule.game_date,
            models.GameSchedule.game_time
        ).all()

        if not all_games:
            print(f"❌ Aucun match trouvé pour {today_eastern} ou {tomorrow_eastern}")
            ANALYSIS_JOBS[job_id] = {
                "status": "complete",
                "data": [],
                "progress": 100,
                "message": f"Aucun match trouvé pour {today_eastern.strftime('%d/%m/%Y')}"
            }
            return

        print(f"✅ {len(all_games)} match(s) trouvé(s) pour analyse :")
        for g in all_games:
            game_datetime = f"{g.game_date} {g.game_time or 'TBD'}"
            print(f"   📅 {game_datetime} - {g.away_team_code} @ {g.home_team_code} ({g.status})")

        best_bets = []
        total_games = len(all_games)

        # Markets supportés (three_points_made retiré car l'API The-Odds ne le supporte pas)
        SUPPORTED_MARKETS = ["points", "rebounds", "assists"]
        markets_to_scan = [m for m in (markets or SUPPORTED_MARKETS) if m in SUPPORTED_MARKETS]

        if not markets_to_scan:
            markets_to_scan = SUPPORTED_MARKETS

        print(f"📊 Markets à analyser : {markets_to_scan}")

        # Compteurs debug pour analyser le filtrage
        debug_counters = {
            'total_checked': 0,
            'no_projection': 0,
            'no_line': 0,
            'low_edge': 0,
            'low_score': 0,
            'low_sample': 0,
            'out_status': 0,
            'included': 0
        }
        # Comptes par marché / raison pour debug fin
        reason_by_market = {
            'no_projection': {},
            'no_line': {},
            'low_edge': {},
            'low_score': {},
            'low_sample': {},
            'out_status': {}
        }

        # Pour analyser la distribution des edges
        edge_samples = []

        def _inc(reason_dict, market):
            if market is None:
                return
            reason_dict[market] = reason_dict.get(market, 0) + 1

        # Check quota : arrêter UNIQUEMENT si TOUTES les clés sont épuisées
        if betting_provider.quota_exceeded:
            # Vérifier s'il reste des clés non utilisées
            if betting_provider.current_key_index >= len(betting_provider.api_keys) - 1:
                print("🛑 SCAN ARRÊTÉ : Toutes les clés API sont épuisées.")
                print("   💡 Solution : Ajouter une nouvelle clé API dans THE_ODDS_API_KEY (séparées par des virgules).")
                print("   📖 Documentation : https://the-odds-api.com/")
                ANALYSIS_JOBS[job_id] = {
                    "status": "complete",
                    "data": [],
                    "progress": 100,
                    "message": "⚠️ Toutes les clés API sont épuisées. Ajoutez une nouvelle clé dans .env (THE_ODDS_API_KEY).",
                    "error": "ALL_KEYS_EXHAUSTED"
                }
                return
            else:
                # Il reste des clés, on peut continuer
                print(f"⚠️ Clé actuelle épuisée, mais {len(betting_provider.api_keys) - betting_provider.current_key_index - 1} clé(s) disponible(s)")
                print("   🔄 La rotation automatique se fera lors de la prochaine requête")
                # Réinitialiser le flag pour permettre la rotation
                betting_provider.quota_exceeded = False

        for i, game in enumerate(all_games):
            ANALYSIS_JOBS[job_id] = {"status": "running", "data": best_bets, "progress": int((i / total_games) * 100)}
            print(f"🔍 Analyse match {game.away_team_code} @ {game.home_team_code} ({game.game_date})...")

            # Récupérer/attacher les rosters AVANT de récupérer les cotes pour que les player_id existent
            home_roster = get_roster_for_team(game.home_team_code, db)
            away_roster = get_roster_for_team(game.away_team_code, db)
            all_players = home_roster + away_roster

            # ✅ FORCER le refresh des cotes pour les matchs du jour (ttl_hours=0)
            # Cela garantit qu'on a toujours les cotes les plus récentes
            fetch_success = betting_provider.fetch_odds_snapshots_for_game(
                db, game.nba_game_id, game.home_team_code, game.away_team_code, ttl_hours=0
            )

            # Log rapide du nombre de lignes par marché pour ce match
            market_counts = db.query(models.OddsSnapshot.market, func.count(models.OddsSnapshot.id)).filter(
                models.OddsSnapshot.game_id == game.nba_game_id
            ).group_by(models.OddsSnapshot.market).all()

            if fetch_success:
                print(f"   ✅ Cotes récupérées: {dict(market_counts)}")
            else:
                print(f"   ⚠️ Échec récupération cotes pour {game.nba_game_id}")
                print(f"   💡 Ce match n'est peut-être pas encore disponible sur The-Odds-API")
                # On continue quand même avec les snapshots existants si disponibles
                if market_counts:
                    print(f"   💾 Utilisation des snapshots existants: {dict(market_counts)}")

            if not all_players:
                print("   ⚠️ Aucun joueur récupéré (roster vide).")
                continue

            print(f"   📊 Joueurs : {len(all_players)}")
            print(f"   🔍 DEBUG: Premier joueur = {all_players[0] if all_players else 'AUCUN'}")

            for p in all_players:
                if not p.get('id'):
                    print(f"      ⚠️ Joueur sans ID: {p.get('full_name')} (nba_id={p.get('nba_id')})")
                    continue

                # Déterminer l'équipe adverse
                is_home = p in home_roster
                opponent_code = game.away_team_code if is_home else game.home_team_code

                try:
                    proj_data = compute_projection(p['id'], games=82, game_id=game.nba_game_id, db=db)
                except Exception as e:
                    print(f"      ❌ Crash compute_projection pour {p.get('full_name')}: {e}")
                    continue
                if not proj_data or "projections" not in proj_data:
                    debug_counters['no_projection'] += 1
                    # pas de marché à incrémenter ici (pas de stat évaluée)
                    continue

                # Récupérer le nombre de matchs pour la taille de l'échantillon
                sample_size = proj_data.get('sample_size') or len(proj_data.get('last_games', []))

                for stat in markets_to_scan:
                    data = proj_data["projections"].get(stat)
                    if not data:
                        debug_counters['no_projection'] += 1
                        _inc(reason_by_market['no_projection'], stat)
                        continue

                    debug_counters['total_checked'] += 1

                    proj = data.get('projection')

                    snap = betting_provider.get_snapshot_odds(db, game.nba_game_id, p['id'], stat)
                    if snap:
                        line = snap.get('line'); odds_over = snap.get('price_over'); odds_under = snap.get('price_under')
                        odds_source = snap.get('bookmaker', 'snapshot')
                    else:
                        odds_db = betting_provider.get_odds_from_db(db, p['id'], game.nba_game_id, stat)
                        line = odds_db.line if odds_db else None
                        odds_over = odds_db.odds_over if odds_db else None
                        odds_under = odds_db.odds_under if odds_db else None
                        odds_source = odds_db.bookmaker if odds_db else None

                    if not line or line <= 0:
                        debug_counters['no_line'] += 1
                        _inc(reason_by_market['no_line'], stat)
                        continue

                    injury_status = p.get('injury_status', 'HEALTHY')
                    play_prob = p.get('play_probability')

                    # ⭐ UTILISER LE SCORING AVANCÉ
                    score, tag, details = scorer.calculate_advanced_score(
                        player_id=p['id'],
                        projection_data=proj_data,
                        line=line,
                        opponent_team_code=opponent_code,
                        stat_type=stat,
                        injury_status=injury_status,
                        play_probability=play_prob
                    )

                    # Calculer l'edge pour l'affichage
                    edge = abs(proj - line) / line * 100 if line > 0 else 0

                    # Collecter des exemples pour analyse (limité à 20)
                    if len(edge_samples) < 20:
                        edge_samples.append({
                            'player': p['full_name'],
                            'stat': stat,
                            'proj': round(proj, 1),
                            'line': round(line, 1),
                            'edge': round(edge, 2),
                            'score': round(score, 1)
                        })

                    # ⭐ FILTRAGE STRICT avec le scorer avancé
                    if not scorer.should_include_pick(score, edge, sample_size, injury_status):
                        if injury_status and str(injury_status).upper() == 'OUT':
                            debug_counters['out_status'] += 1; _inc(reason_by_market['out_status'], stat)
                        elif edge < scorer.MIN_EDGE:
                            debug_counters['low_edge'] += 1; _inc(reason_by_market['low_edge'], stat)
                        elif score < scorer.MIN_SCORE:
                            debug_counters['low_score'] += 1; _inc(reason_by_market['low_score'], stat)
                        elif sample_size < scorer.MIN_SAMPLE_SIZE:
                            debug_counters['low_sample'] += 1; _inc(reason_by_market['low_sample'], stat)
                        continue

                    debug_counters['included'] += 1

                    base_pick = {
                        "player": p['full_name'],
                        "team": game.home_team_code if is_home else game.away_team_code,
                        "opponent": opponent_code,
                        "market": stat,
                        "line": line,
                        "odds": odds_over if proj > line else odds_under,
                        "projection": proj,
                        "confidence": f"{tag} ({score:.0f})",
                        "ev": score,
                        "game_id": game.nba_game_id,
                        "player_id": p['id'],
                        "bet_type": "over" if proj > line else "under",  # ✅ CORRECTION: minuscules pour uniformité
                        "odds_source": odds_source,
                        "injury_status": injury_status,
                        "play_probability": play_prob,
                        "edge": round(edge, 1),
                        "sample_size": sample_size,
                        "scoring_details": details
                    }

                    best_bets.append(base_pick)

        # Trier par score (EV) décroissant - ENVOYER TOUS LES PICKS au frontend
        best_bets.sort(key=lambda x: x['ev'], reverse=True)
        # Le frontend gérera l'affichage avec sa checkbox (20 par défaut, tous si cochée)
        top_picks = best_bets  # ✅ TOUS les picks, pas de limite

        # Log debug pour comprendre les filtres (flush pour éviter le buffering)
        print(f"📊 Exemples d'edges calculés (20 premiers):", flush=True)
        for sample in edge_samples[:10]:
            print(f"   {sample['player'][:20]:20} {sample['stat']:8} | proj={sample['proj']:5.1f} line={sample['line']:5.1f} edge={sample['edge']:5.2f}% score={sample['score']:5.1f}", flush=True)

        debug_summary = (
            f"DEBUG picks counters: {debug_counters} | "
            f"by_market_no_projection={reason_by_market['no_projection']} | "
            f"by_market_no_line={reason_by_market['no_line']} | "
            f"by_market_low_edge={reason_by_market['low_edge']} | "
            f"by_market_low_score={reason_by_market['low_score']} | "
            f"by_market_low_sample={reason_by_market['low_sample']} | "
            f"by_market_out={reason_by_market['out_status']} | "
            f"checked={debug_counters['total_checked']} | no_projection={debug_counters['no_projection']} | "
            f"no_line={debug_counters['no_line']} | low_edge={debug_counters['low_edge']} | "
            f"low_score={debug_counters['low_score']} | low_sample={debug_counters['low_sample']} | "
            f"out_status={debug_counters['out_status']} | included={debug_counters['included']} | "
            f"potential={len(best_bets)}"
        )
        print(f"🧮 {debug_summary}", flush=True)

        ANALYSIS_JOBS[job_id] = {
            "status": "complete",
            "data": top_picks,
            "progress": 100,
            "message": f"{len(top_picks)} picks ULTRA-SÉLECTIFS (sur {len(best_bets)} analysés)",
            "debug": debug_summary
        }
        print(f"✅ Scan terminé : {len(top_picks)} picks sélectionnés (sur {len(best_bets)} potentiels).", flush=True)
