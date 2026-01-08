import os
import requests
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import func
from backend import models
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../.env'))

# Mapping des équipes (Code NBA -> Nom API Odds)
TEAM_MAPPING = {
    "LAL": "Los Angeles Lakers", "BOS": "Boston Celtics", "CLE": "Cleveland Cavaliers",
    "MIL": "Milwaukee Bucks", "PHI": "Philadelphia 76ers", "PHX": "Phoenix Suns",
    "GSW": "Golden State Warriors", "MIA": "Miami Heat", "NYK": "New York Knicks",
    "DEN": "Denver Nuggets", "DAL": "Dallas Mavericks", "LAC": "Los Angeles Clippers",
    "SAC": "Sacramento Kings", "MIN": "Minnesota Timberwolves", "OKC": "Oklahoma City Thunder",
    "MEM": "Memphis Grizzlies", "IND": "Indiana Pacers", "NOP": "New Orleans Pelicans",
    "ORL": "Orlando Magic", "HOU": "Houston Rockets", "TOR": "Toronto Raptors",
    "ATL": "Atlanta Hawks", "UTA": "Utah Jazz", "BKN": "Brooklyn Nets",
    "CHI": "Chicago Bulls", "SAS": "San Antonio Spurs", "POR": "Portland Trail Blazers",
    "CHA": "Charlotte Hornets", "WAS": "Washington Wizards", "DET": "Detroit Pistons"
}


def normalize_name(name):
    """Enlève les accents et met en minuscule pour la comparaison (Dončić -> doncic)."""
    if not name: return ""
    n = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('utf-8')
    return n.lower().replace(".", "").replace("'", "").strip()


class BettingOddsProvider:
    def __init__(self):
        # DEBUG : On imprime ce qu'on trouve pour être sûr
        keys_from_env = os.getenv("THE_ODDS_API_KEY")

        env_path = Path(os.path.join(os.path.dirname(__file__), '../.env'))
        print(f"👀 DEBUG: Chemin du .env cherché : {env_path}")
        if env_path.exists():
            print("   ✅ Fichier .env TROUVÉ sur le disque.")
        else:
            print("   ❌ Fichier .env INTROUVABLE à cet endroit !")

        if keys_from_env:
            self.api_keys = keys_from_env.split(',')
            self.current_key_index = 0
            self.api_key = self.api_keys[self.current_key_index]
            masked = self.api_key[:4] + "***"
            print(f"   ✅ Clé chargée : {masked} (1/{len(self.api_keys)})")
        else:
            self.api_keys = []
            self.api_key = None
            print("   ❌ Variable 'THE_ODDS_API_KEY' vide ou inexistante dans le .env")

        self.base_url = "https://api.the-odds-api.com/v4/sports/basketball_nba"
        self.quota_exceeded = False

        if not self.api_key:
            print("🚨 ERREUR CRITIQUE : Clés THE_ODDS_API_KEY manquantes !")

    def switch_to_next_key(self):
        if self.current_key_index < len(self.api_keys) - 1:
            self.current_key_index += 1
            self.api_key = self.api_keys[self.current_key_index]
            self.quota_exceeded = False
            masked = self.api_key[:4] + "***"
            print(f"🔄 Changement de clé API : {masked} ({self.current_key_index + 1}/{len(self.api_keys)})")
            return True
        else:
            print("🚨 Toutes les clés API épuisées !")
            return False

    def get_event_id(self, home_team_code, away_team_code):
        """Récupère l'ID du match chez The-Odds-API en matching home/away (pas uniquement Bet365)."""
        if self.quota_exceeded or not self.api_key: return None

        try:
            params = {"apiKey": self.api_key, "regions": "us", "markets": "h2h"}
            res = requests.get(f"{self.base_url}/events", params=params, timeout=5)

            if res.status_code in [401, 429]:
                print(f"🚨 ALERTE API : Quota dépassé ou clé invalide ({res.status_code}). Tentative de changement de clé.")
                if self.switch_to_next_key():
                    params["apiKey"] = self.api_key
                    res = requests.get(f"{self.base_url}/events", params=params, timeout=5)
                    if res.status_code in [401, 429]:
                        self.quota_exceeded = True
                        return None
                else:
                    self.quota_exceeded = True
                    return None

            if res.status_code != 200:
                print(f"⚠️ Erreur HTTP API Odds : {res.status_code}")
                return None

            events = res.json()
            home_name = TEAM_MAPPING.get(home_team_code)
            away_name = TEAM_MAPPING.get(away_team_code)

            def norm(s):
                return (s or "").lower().strip()

            for e in events:
                h = norm(e.get("home_team"))
                a = norm(e.get("away_team"))
                if home_name and away_name:
                    if norm(home_name) in h and norm(away_name) in a:
                        return e["id"]
                    if norm(home_name) in a and norm(away_name) in h:  # swapped safety
                        return e["id"]

            # Fallback : premier event qui contient l'une des équipes
            for e in events:
                h = norm(e.get("home_team")); a = norm(e.get("away_team"))
                if (home_name and norm(home_name) in h) or (away_name and norm(away_name) in a):
                    return e["id"]

            print(f"⚠️ Match non trouvé sur The-Odds-API pour : {home_team_code} vs {away_team_code}")
            return None

        except Exception as e:
            print(f"❌ Exception API Events: {e}")
        return None

    def _select_bookmaker(self, bookmakers: list):
        """Choisit le bookmaker le plus pertinent (Bet365/FanDuel/DK sinon premier avec markets)."""
        if not bookmakers:
            return None
        preferred = ["bet365", "fanduel", "draftkings"]
        for key in preferred:
            for b in bookmakers:
                if key in b.get("key", "").lower() and b.get("markets"):
                    return b
        for b in bookmakers:
            if b.get("markets"):
                return b
        return bookmakers[0]

    def update_odds_for_game(self, db: Session, nba_game_id: str, home_code: str, away_code: str):
        """
        Met à jour les cotes en BDD si elles sont vieilles ou absentes.
        """
        # 1. Check BDD (Cache 1h) - UTILISE OddsSnapshot maintenant
        recent = datetime.now() - timedelta(hours=1)
        existing = db.query(models.OddsSnapshot).filter(
            models.OddsSnapshot.game_id == nba_game_id,
            models.OddsSnapshot.fetched_at > recent
        ).first()

        if existing:
            # print(f"   💾 Cotes trouvées en cache BDD pour {home_code}.")
            return True

        if self.quota_exceeded or not self.api_key:
            return False

        # 2. Appel API (Seulement si pas de cache)
        event_id = self.get_event_id(home_code, away_code)
        if not event_id: return False

        print(f"   📡 Téléchargement des cotes pour {home_code} vs {away_code}...")

        try:
            params = {
                "apiKey": self.api_key,
                "regions": "us",  # ou 'eu'
                "markets": "player_points,player_rebounds,player_assists",
                "oddsFormat": "decimal"
            }
            res = requests.get(f"{self.base_url}/events/{event_id}/odds", params=params, timeout=8)

            if res.status_code in [401, 429]:
                print(f"🚨 ALERTE API : Quota dépassé ou clé invalide ({res.status_code}) lors de la récupération des cotes. Tentative de changement de clé.")
                if self.switch_to_next_key():
                    params["apiKey"] = self.api_key
                    res = requests.get(f"{self.base_url}/events/{event_id}/odds", params=params, timeout=8)
                    if res.status_code not in [401, 429]:
                        print("   ✅ Nouvelle clé fonctionnelle pour les cotes.")
                    else:
                        print("   ❌ Nouvelle clé aussi épuisée pour les cotes.")
                        return False
                else:
                    return False

            if res.status_code != 200:
                return False

            data = res.json()
            bookmakers = data.get("bookmakers", [])
            if not bookmakers:
                print("   ⚠️ Aucune cote bookmaker disponible pour ce match.")
                return False

            bookie = self._select_bookmaker(bookmakers)
            if not bookie:
                return False
            print(f"   ✅ Source des cotes : {bookie['title']}")

            # Suppression anciens records pour ce match (utilise OddsSnapshot)
            db.query(models.OddsSnapshot).filter(models.OddsSnapshot.game_id == nba_game_id).delete()

            new_odds = []
            # On précharge tous les joueurs pour éviter les requêtes SQL en boucle
            players_cache = {p.id: normalize_name(p.full_name) for p in db.query(models.Player).all()}

            for market in bookie.get("markets", []):
                m_type = market["key"].replace("player_", "")
                for outcome in market["outcomes"]:
                    api_name_norm = normalize_name(outcome["description"])
                    line = outcome["point"]

                    # Correspondance ID Joueur (Matching Fuzzy)
                    matched_id = None
                    for pid, pname in players_cache.items():
                        if pname == api_name_norm:  # Match exact nom normalisé
                            matched_id = pid
                            break
                        # Fallback partiel (ex: "Luka" dans "Luka Doncic")
                        if len(api_name_norm) > 4 and api_name_norm in pname:
                            matched_id = pid
                            break

                    if not matched_id: continue

                    # Créer un OddsSnapshot (pas BettingOdds)
                    if outcome["name"] == "Over":
                        obj = models.OddsSnapshot(
                            game_id=nba_game_id,
                            player_id=matched_id,
                            market=m_type,
                            line=line,
                            price_over=outcome["price"],
                            price_under=1.85,  # Valeur par défaut
                            bookmaker=bookie["title"],
                            fetched_at=datetime.now(),
                            ttl_expire_at=datetime.now() + timedelta(hours=4)
                        )
                        new_odds.append(obj)

            if new_odds:
                db.add_all(new_odds)
                db.commit()
                print(f"   📥 {len(new_odds)} lignes sauvegardées en BDD.")
                return True
            else:
                print("   ⚠️ Cotes récupérées mais aucun joueur matché avec la BDD locale.")
                return False

        except Exception as e:
            print(f"   ❌ Crash update_odds: {e}")
            return False

    def get_odds_from_db(self, db: Session, player_id: int, game_id: str, market: str):
        """Lecture rapide depuis la BDD (utilise OddsSnapshot)."""
        snap = db.query(models.OddsSnapshot).filter(
            models.OddsSnapshot.player_id == player_id,
            models.OddsSnapshot.game_id == game_id,
            models.OddsSnapshot.market == market
        ).first()

        if not snap:
            return None

        # Convertir en format BettingOdds pour compatibilité
        class OddsCompat:
            def __init__(self, snap):
                self.line = snap.line
                self.odds_over = snap.price_over
                self.odds_under = snap.price_under
                self.bookmaker = snap.bookmaker

        return OddsCompat(snap)

    def _has_fresh_snapshots(self, db: Session, game_id: str, ttl_hours: int = 4):
        cutoff = datetime.utcnow() - timedelta(hours=ttl_hours)
        return db.query(models.OddsSnapshot).filter(
            models.OddsSnapshot.game_id == game_id,
            models.OddsSnapshot.fetched_at >= cutoff
        ).first() is not None

    def fetch_odds_snapshots_for_game(self, db: Session, game_id: str, home_code: str, away_code: str,
                                      ingestion_run_id: int | None = None, ttl_hours: int = 4):
        """Récupère les cotes et les écrit dans odds_snapshots avec TTL et optional ingestion_run_id."""
        if self.quota_exceeded or not self.api_key:
            return False

        if self._has_fresh_snapshots(db, game_id, ttl_hours=ttl_hours):
            return True  # cache valide

        event_id = self.get_event_id(home_code, away_code)
        if not event_id:
            return False

        try:
            params = {
                "apiKey": self.api_key,
                "regions": "us",
                "markets": "player_points,player_rebounds,player_assists",
                "oddsFormat": "decimal"
            }
            res = requests.get(f"{self.base_url}/events/{event_id}/odds", params=params, timeout=8)

            if res.status_code in [401, 429]:
                if self.switch_to_next_key():
                    params["apiKey"] = self.api_key
                    res = requests.get(f"{self.base_url}/events/{event_id}/odds", params=params, timeout=8)
                else:
                    return False

            if res.status_code != 200:
                return False

            data = res.json()
            bookmakers = data.get("bookmakers", [])
            if not bookmakers:
                return False

            bookie = self._select_bookmaker(bookmakers)
            if not bookie:
                return False

            players_cache = {p.id: normalize_name(p.full_name) for p in db.query(models.Player).all()}
            ttl_expire_at = datetime.utcnow() + timedelta(hours=ttl_hours)
            rows = []

            for market in bookie.get("markets", []):
                m_type = market["key"].replace("player_", "")
                for outcome in market.get("outcomes", []):
                    api_name_norm = normalize_name(outcome.get("description"))
                    line = outcome.get("point")

                    matched_id = None
                    for pid, pname in players_cache.items():
                        if pname == api_name_norm:
                            matched_id = pid; break
                        if len(api_name_norm) > 4 and api_name_norm in pname:
                            matched_id = pid; break

                    if not matched_id:
                        continue

                    if outcome.get("name") == "Over":
                        rows.append(models.OddsSnapshot(
                            ingestion_run_id=ingestion_run_id,
                            game_id=game_id,
                            player_id=matched_id,
                            market=m_type,
                            line=line,
                            price_over=outcome.get("price"),
                            price_under=None,
                            bookmaker=bookie.get("title"),
                            fetched_at=datetime.utcnow(),
                            ttl_expire_at=ttl_expire_at
                        ))

            if not rows:
                return False

            db.add_all(rows)
            db.commit()
            return True
        except Exception as e:
            print(f"   ❌ Crash fetch_odds_snapshots_for_game: {e}")
            db.rollback()
            return False

    def get_snapshot_odds(self, db: Session, game_id: str, player_id: int, market: str):
        """Retourne la dernière cote snapshot non expirée pour un joueur/marché/match."""
        now = datetime.utcnow()
        row = db.query(models.OddsSnapshot).filter(
            models.OddsSnapshot.game_id == game_id,
            models.OddsSnapshot.player_id == player_id,
            models.OddsSnapshot.market == market,
            (models.OddsSnapshot.ttl_expire_at.is_(None)) | (models.OddsSnapshot.ttl_expire_at > now)
        ).order_by(models.OddsSnapshot.fetched_at.desc()).first()
        if not row:
            return None
        return {
            "line": float(row.line) if row.line is not None else None,
            "price_over": float(row.price_over) if row.price_over is not None else None,
            "price_under": float(row.price_under) if row.price_under is not None else None,
            "bookmaker": row.bookmaker,
            "fetched_at": row.fetched_at,
        }
