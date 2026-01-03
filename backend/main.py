from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Query, Body
from sqlalchemy.orm import Session
from sqlalchemy import func
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
    if not player: return {}

    query = f"SELECT * FROM player_game_stats WHERE player_id = {player_id} ORDER BY game_id DESC LIMIT {games}"
    df = pd.read_sql(query, engine)

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


# --- SYNC INJURIES HELPER ---
def _run_sync_injuries():
    try:
        script_path = Path(__file__).resolve().parent.parent / "data-pipeline" / "sync_injuries.py"
        if not script_path.exists():
            print("⚠️ sync_injuries.py introuvable, skip refresh blessures.")
            return
        subprocess.run(["python", str(script_path), "--quiet"], check=False, timeout=120)
    except Exception as e:
        print(f"⚠️ sync_injuries échoué : {e}")


# --- MAIN SCAN LOOP ---

def run_best_bets_scan(job_id: str, markets: list[str] | None = None):
    print(f"🚀 Démarrage du scan {job_id}...")
    _run_sync_injuries()
    with Session(engine) as db:
        now = datetime.utcnow()
        # Prioriser les matchs pour lesquels on a des snapshots d'odds non expirés
        odds_games = [g[0] for g in db.query(models.OddsSnapshot.game_id)
                      .filter((models.OddsSnapshot.ttl_expire_at.is_(None)) | (models.OddsSnapshot.ttl_expire_at > now))
                      .distinct().all()]
        if odds_games:
            all_games = db.query(models.GameSchedule).filter(models.GameSchedule.nba_game_id.in_(odds_games)).all()
        else:
            today = datetime.now().date()
            all_games = db.query(models.GameSchedule).filter(models.GameSchedule.game_date == today).all()

        if not all_games:
            ANALYSIS_JOBS[job_id] = {"status": "complete", "data": [], "progress": 100, "message": "Aucun match ou aucune cote."}
            return

        best_bets = []
        total_games = len(all_games)

        # Check quota au début
        if betting_provider.quota_exceeded:
            print("🛑 SCAN ARRÊTÉ : Quota API Odds dépassé. Les cotes ne seront pas mises à jour.")

        for i, game in enumerate(all_games):
            ANALYSIS_JOBS[job_id] = {"status": "running", "data": best_bets, "progress": int((i / total_games) * 100)}
            print(f"🔍 Analyse match {game.away_team_code} @ {game.home_team_code}...")

            has_odds = betting_provider.update_odds_for_game(db, game.nba_game_id, game.home_team_code, game.away_team_code)
            if not has_odds and betting_provider.quota_exceeded:
                print("   ⚠️ Pas de mise à jour des cotes (Quota). Utilisation du cache existant si dispo.")

            home_roster = get_roster_for_team(game.home_team_code, db)
            away_roster = get_roster_for_team(game.away_team_code, db)
            all_players = home_roster + away_roster

            if not all_players:
                print("   ⚠️ Aucun joueur récupéré (roster vide).")
                continue

            print(f"   📊 Joueurs : {len(all_players)}")

            for p in all_players:
                if not p.get('id'): continue
                try:
                    proj_data = compute_projection(p['id'], games=82, game_id=game.nba_game_id, db=db)
                except Exception:
                    continue
                if not proj_data or "projections" not in proj_data: continue

                for stat in (markets or ["points", "rebounds", "assists"]):
                    data = proj_data["projections"].get(stat)
                    if not data: continue

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

                    score, tag = calculate_confidence_score(data, line if line else 0, 0)

                    injury_status = p.get('injury_status', 'HEALTHY')
                    play_prob = p.get('play_probability')
                    injury_factor = 1.0
                    status_penalty = {
                        'OUT': 0.0,
                        'DOUBTFUL': 0.5,
                        'QUESTIONABLE': 0.7,
                        'DAY_TO_DAY': 0.7,
                        'GTD': 0.7,
                        'PROBABLE': 0.9,
                    }
                    injury_factor *= status_penalty.get(str(injury_status).upper(), 1.0)
                    if play_prob is not None:
                        injury_factor *= max(0.0, min(1.0, float(play_prob) / 100.0))
                    score *= injury_factor

                    if score < 60 or not line:
                        continue

                    base_pick = {"player": p['full_name'], "team": game.home_team_code if p in home_roster else game.away_team_code,
                                 "opponent": game.away_team_code if p in home_roster else game.home_team_code,
                                 "market": stat, "line": line, "odds": odds_over if proj > line else odds_under,
                                 "projection": proj, "confidence": f"{tag} ({score:.0f})", "ev": score,
                                 "game_id": game.nba_game_id, "player_id": p['id'], "bet_type": "Over" if proj > line else "Under",
                                 "odds_source": odds_source, "injury_status": injury_status, "play_probability": play_prob}

                    if proj > line and odds_over:
                        best_bets.append(base_pick)
                    elif proj < line and odds_under:
                        base_pick["bet_type"] = "Under"
                        best_bets.append(base_pick)

        best_bets.sort(key=lambda x: x['ev'], reverse=True)
        ANALYSIS_JOBS[job_id] = {"status": "complete", "data": best_bets[:50], "progress": 100}
        print(f"✅ Scan terminé : {len(best_bets)} picks.")


@app.post("/analysis/start-scan")
def start_best_bets_scan(scan_req: ScanRequest | None = Body(default=None), background_tasks: BackgroundTasks = None):
    job_id = str(uuid.uuid4())
    ANALYSIS_JOBS[job_id] = {"status": "running", "data": [], "progress": 0}
    markets = scan_req.markets if scan_req else None
    background_tasks.add_task(run_best_bets_scan, job_id, markets)
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


class IngestionRunDTO(BaseModel):
    id: int
    source: str
    scope: Optional[str]
    version_tag: Optional[str]
    status: str
    started_at: datetime
    ended_at: Optional[datetime]
    meta: Optional[str]

    class Config:
        orm_mode = True


class OddsSnapshotDTO(BaseModel):
    id: int
    game_id: str
    player_id: Optional[int]
    market: str
    line: Optional[float]
    price_over: Optional[float]
    price_under: Optional[float]
    bookmaker: str
    fetched_at: datetime
    ttl_expire_at: Optional[datetime]

    class Config:
        orm_mode = True


@app.get("/datahub/ingestion-runs", response_model=List[IngestionRunDTO])
def list_ingestion_runs(source: Optional[str] = None, limit: int = 50, db: Session = Depends(get_db)):
    q = db.query(models.IngestionRun).order_by(models.IngestionRun.started_at.desc())
    if source:
        q = q.filter(models.IngestionRun.source == source)
    return q.limit(min(limit, 200)).all()


@app.get("/datahub/odds-snapshots", response_model=List[OddsSnapshotDTO])
def list_odds_snapshots(game_id: str = Query(...), bookmaker: Optional[str] = None, limit: int = 200, db: Session = Depends(get_db)):
    q = db.query(models.OddsSnapshot).filter(models.OddsSnapshot.game_id == game_id).order_by(models.OddsSnapshot.fetched_at.desc())
    if bookmaker:
        q = q.filter(models.OddsSnapshot.bookmaker == bookmaker)
    return q.limit(min(limit, 500)).all()


@app.get("/analysis/odds-cache/{nba_game_id}")
def get_odds_cache_for_game(nba_game_id: str, bookmaker: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(models.OddsSnapshot).filter(models.OddsSnapshot.game_id == nba_game_id)
    if bookmaker:
        q = q.filter(models.OddsSnapshot.bookmaker == bookmaker)
    rows = q.order_by(models.OddsSnapshot.fetched_at.desc()).all()
    out = []
    for r in rows:
        out.append({
            "game_id": r.game_id,
            "player_id": r.player_id,
            "market": r.market,
            "line": float(r.line) if r.line is not None else None,
            "price_over": float(r.price_over) if r.price_over is not None else None,
            "price_under": float(r.price_under) if r.price_under is not None else None,
            "bookmaker": r.bookmaker,
            "fetched_at": r.fetched_at,
            "ttl_expire_at": r.ttl_expire_at
        })
    return {"odds": out}
