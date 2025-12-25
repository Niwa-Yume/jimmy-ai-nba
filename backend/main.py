from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Query, Body
from sqlalchemy.orm import Session
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
from sqlalchemy import text, func
import random

# ✅ Import du module de Scoring
from backend.scoring import calculate_confidence_score

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
    bet_type: str


class ScanRequest(BaseModel):
    markets: Optional[list[str]] = None


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
    if not player: return {}

    query = f"SELECT * FROM player_game_stats WHERE player_id = {player_id} ORDER BY game_id DESC LIMIT {games}"
    df = pd.read_sql(query, engine)

    if df.empty:
        if not player.nba_player_id or player.nba_player_id == 0:
            return {}

        try:
            sys_path_added = False
            import sys
            if 'data-pipeline' not in sys.path:
                sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'data-pipeline'))
                sys_path_added = True

            from populate_stats import sync_player_stats
            time.sleep(0.8)  # Throttling
            sync_player_stats(player.nba_player_id, limit=games)
            df = pd.read_sql(query, engine)
        except Exception as e:
            return {}

    if df.empty: return {}

    projections = {}
    stats_list = ["points", "rebounds", "assists", "three_points_made"]

    game = db.query(models.GameSchedule).filter(models.GameSchedule.nba_game_id == game_id).first()
    team_code = game.home_team_code if game else "N/A"

    for stat in stats_list:
        if stat not in df.columns: continue
        season_avg = df[stat].mean()
        def_factor = 1.0

        proj = calculate_stat_projection(
            df, stat, player.full_name, team_code, None, None,
            season_avg, def_factor, 1.0, 1.0, event_id=odds_event_id
        )
        if proj: projections[stat] = proj

    return {
        "player": player.full_name,
        "opponent": "OPP",
        "projections": projections
    }


# --- MAIN SCAN LOOP ---

def run_best_bets_scan(job_id: str, markets: list[str] | None = None):
    print(f"🚀 Démarrage du scan {job_id}...")
    with Session(engine) as db:
        today = datetime.now().date()
        all_games = db.query(models.GameSchedule).filter(models.GameSchedule.game_date == today).all()

        if not all_games:
            ANALYSIS_JOBS[job_id] = {"status": "complete", "data": [], "progress": 100, "message": "Aucun match."}
            return

        best_bets = []
        total_games = len(all_games)

        # Check quota au début
        if betting_provider.quota_exceeded:
            print("🛑 SCAN ARRÊTÉ : Quota API Odds dépassé. Les cotes ne seront pas mises à jour.")

        for i, game in enumerate(all_games):
            ANALYSIS_JOBS[job_id] = {"status": "running", "data": best_bets, "progress": int((i / total_games) * 100)}
            print(f"🔍 Analyse match {game.away_team_code} @ {game.home_team_code}...")

            # 1. 📡 SYNCHRONISATION INTELLIGENTE DES COTES (BDD First)
            has_odds = betting_provider.update_odds_for_game(
                db,
                game.nba_game_id,
                game.home_team_code,
                game.away_team_code
            )

            if not has_odds and betting_provider.quota_exceeded:
                print("   ⚠️ Pas de mise à jour des cotes (Quota). Utilisation du cache existant si dispo.")

            home_roster = get_roster_for_team(game.home_team_code, db)
            away_roster = get_roster_for_team(game.away_team_code, db)
            all_players = home_roster + away_roster

            print(f"   📊 Joueurs : {len(all_players)}")

            for p in all_players:
                if not p.get('id'): continue

                try:
                    proj_data = compute_projection(p['id'], games=82, game_id=game.nba_game_id, db=db)
                except Exception:
                    continue

                if not proj_data or "projections" not in proj_data: continue

                markets_to_check = markets or ["points", "rebounds", "assists"]
                for stat in markets_to_check:
                    data = proj_data["projections"].get(stat)
                    if not data: continue

                    proj = data.get('projection')

                    # 2. 💾 LECTURE DES COTES DEPUIS LA BDD
                    odds_db = betting_provider.get_odds_from_db(db, p['id'], game.nba_game_id, stat)

                    line = None
                    odds_over = None
                    odds_under = None

                    if odds_db:
                        line = odds_db.line
                        odds_over = odds_db.odds_over
                        odds_under = odds_db.odds_under
                    else:
                        # Si c'est une star (>20pts) et qu'on n'a pas de cote, c'est louche
                        if stat == "points" and proj > 20:
                            print(f"      ❌ Pas de cote {stat} pour {p['full_name']} (Proj: {proj})")

                    # Scoring avec ligne à 0 si pas de cote (score sera bas)
                    score, tag = calculate_confidence_score(data, line if line else 0, 0)

                    if score < 50: continue

                    if line:
                        if odds_over and proj > line:
                            best_bets.append({
                                "player": p['full_name'],
                                "team": game.home_team_code if p in home_roster else game.away_team_code,
                                "opponent": "OPP",
                                "market": stat, "line": line, "odds": odds_over,
                                "projection": proj, "confidence": f"{tag} ({score})",
                                "ev": score, "game_id": game.nba_game_id,
                                "player_id": p['id'], "bet_type": "Over"
                            })
                            print(f"      ✅ PICK: {p['full_name']} {stat} Over {line} (Score: {score})")

                        elif odds_under and proj < line:
                            best_bets.append({
                                "player": p['full_name'],
                                "team": game.home_team_code if p in home_roster else game.away_team_code,
                                "opponent": "OPP",
                                "market": stat, "line": line, "odds": odds_under,
                                "projection": proj, "confidence": f"{tag} (Under) ({score})",
                                "ev": score, "game_id": game.nba_game_id,
                                "player_id": p['id'], "bet_type": "Under"
                            })
                            print(f"      ✅ PICK: {p['full_name']} {stat} < {line} ({score})")

        best_bets.sort(key=lambda x: x['ev'], reverse=True)
        ANALYSIS_JOBS[job_id] = {"status": "complete", "data": best_bets, "progress": 100}
        print(f"✅ Scan terminé : {len(best_bets)} picks.")


@app.post("/analysis/start-scan")
def start_best_bets_scan(scan_req: ScanRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    ANALYSIS_JOBS[job_id] = {"status": "running", "data": [], "progress": 0}
    background_tasks.add_task(run_best_bets_scan, job_id, scan_req.markets)
    return {"job_id": job_id}


@app.get("/analysis/scan-results/{job_id}")
def get_scan_results(job_id: str):
    return ANALYSIS_JOBS.get(job_id, {"status": "not_found"})


@app.post("/analysis/build-parlay")
def build_parlay(bets: List[Bet]):
    if not bets: return {"safe_bet": None, "value_bet": None}
    bets.sort(key=lambda x: (x.confidence, x.ev), reverse=True)
    safe_bets = bets[:3]
    safe_parlay = {"legs": [], "total_odds": 1.0, "type": "Sûreté"}
    for bet in safe_bets:
        safe_parlay["legs"].append(bet.dict())
        safe_parlay["total_odds"] *= (bet.odds or 1.0)
    bets.sort(key=lambda x: x.ev, reverse=True)
    value_bets = bets[:2]
    value_parlay = {"legs": [], "total_odds": 1.0, "type": "Value"}
    for bet in value_bets:
        value_parlay["legs"].append(bet.dict())
        value_parlay["total_odds"] *= (bet.odds or 1.0)
    return {"safe_bet": safe_parlay, "value_bet": value_parlay}


@app.get("/health")
def health(): return {"status": "ok"}


@app.get("/analysis/list-jobs")
def list_analysis_jobs():
    """Retourne la liste des jobs persistés (job_id, status, nombre de picks)"""
    out = []
    for jid, obj in ANALYSIS_JOBS.items():
        out.append({
            "job_id": jid,
            "status": obj.get("status"),
            "count": len(obj.get("data", []))
        })
    # Trier par date de fichier si possible
    try:
        files = list(PERSIST_DIR.glob('*.json'))
        files_sorted = sorted(files, key=lambda x: x.stat().st_mtime, reverse=True)
        # ajouter aussi les jobs qui sont sur disque mais pas encore dans ANALYSIS_JOBS
        for f in files_sorted:
            jid = f.stem
            if jid in ANALYSIS_JOBS: continue
            try:
                with open(f, 'r') as fh:
                    obj = json.load(fh)
                    out.append({"job_id": jid, "status": obj.get('status'), "count": len(obj.get('data', []))})
            except: pass
    except Exception:
        pass
    return out


@app.get("/analysis/latest-job")
def get_latest_job():
    """Retourne l'ID du dernier job persisté (ou 404 si aucun)."""
    files = list(PERSIST_DIR.glob('*.json'))
    if not files:
        return {"job_id": None}
    latest = max(files, key=lambda x: x.stat().st_mtime)
    return {"job_id": latest.stem}


@app.get("/analysis/best-bets")
def get_best_bets():
    """Retourne les picks du dernier job persisté (ou []) pour usage frontend rapide."""
    # 1. Chercher le dernier job dans ANALYSIS_JOBS avec status complete
    complete_jobs = [(jid, obj) for jid, obj in ANALYSIS_JOBS.items() if obj.get('status') == 'complete']
    if complete_jobs:
        # trier par présence dans PERSIST_DIR (mtime) ou retourner le premier
        try:
            files = {f.stem: f for f in PERSIST_DIR.glob('*.json')}
            # choisir le job avec fichier le plus récent
            best = None
            latest_mtime = 0
            for jid, obj in complete_jobs:
                f = files.get(jid)
                if f and f.stat().st_mtime > latest_mtime:
                    latest_mtime = f.stat().st_mtime
                    best = (jid, obj)
            if best:
                return best[1].get('data', [])
        except Exception:
            pass
        # fallback: return the largest data list
        best = max(complete_jobs, key=lambda x: len(x[1].get('data', [])))
        return best[1].get('data', [])

    # 2. Aucun job en mémoire, regarder sur disque
    try:
        files = list(PERSIST_DIR.glob('*.json'))
        if not files:
            return []
        latest = max(files, key=lambda x: x.stat().st_mtime)
        with open(latest, 'r') as fh:
            obj = json.load(fh)
            return obj.get('data', [])
    except Exception:
        return []


@app.get("/games/week")
def get_games_week(db: Session = Depends(get_db)):
    """Retourne les matchs de la semaine (aujourd'hui -> +7 jours) sous forme de liste.
    Format retourné attendu par le frontend : {"games": [ {"nba_game_id":..., "game_date": "YYYY-MM-DD", "game_time": "HH:MM", "home_team": "LAL", "away_team": "BOS", "arena": "..."}, ... ]}
    """
    today = datetime.now().date()
    end = today + timedelta(days=7)
    games = db.query(models.GameSchedule).filter(models.GameSchedule.game_date >= today, models.GameSchedule.game_date <= end).all()

    out = []
    for g in games:
        out.append({
            "nba_game_id": g.nba_game_id,
            "game_date": g.game_date.isoformat() if g.game_date else None,
            "game_time": g.game_time,
            "home_team": g.home_team_code,
            "away_team": g.away_team_code,
            "arena": g.arena,
            "status": g.status
        })
    return {"games": out}


@app.get("/games/{nba_game_id}/lineups")
def get_game_lineups(nba_game_id: str, db: Session = Depends(get_db)):
    """Retourne les lineups (home_roster, away_roster) pour un match donné en utilisant get_roster_for_team.
    Le frontend attend un dict contenant home_team, away_team, home_roster, away_roster.
    """
    game = db.query(models.GameSchedule).filter(models.GameSchedule.nba_game_id == nba_game_id).first()
    if not game:
        return {"error": "game_not_found"}

    home_code = game.home_team_code
    away_code = game.away_team_code

    home_roster = get_roster_for_team(home_code, db)
    away_roster = get_roster_for_team(away_code, db)

    # Normaliser le format pour le frontend
    def _normalize_roster(roster):
        out = []
        for p in roster:
            out.append({
                "id": p.get('id'),
                "full_name": p.get('full_name'),
                "position": p.get('position'),
                "nba_player_id": p.get('nba_id') or p.get('nba_player_id'),
                "injury_status": p.get('injury_status', 'HEALTHY')
            })
        return out

    return {
        "home_team": home_code,
        "away_team": away_code,
        "home_roster": _normalize_roster(home_roster),
        "away_roster": _normalize_roster(away_roster)
    }
