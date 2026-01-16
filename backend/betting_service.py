import os
import requests
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import func, or_  # ajout pour requêtes IdMapping
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


def _player_name_cache(db: Session):
    cache = []
    aliases = {}
    for a in db.query(models.Alias).filter(models.Alias.entity_type == 'player').all():
        aliases.setdefault(a.entity_id, set()).add((a.alias or '').lower())
        if a.normalized_alias:
            aliases.setdefault(a.entity_id, set()).add(a.normalized_alias.lower())
    # IdMappings display_name en alias supplémentaires
    idmap_aliases = {}
    for m in db.query(models.IdMapping).filter(models.IdMapping.entity_type == 'player').all():
        if m.display_name:
            idmap_aliases.setdefault(m.entity_id, set()).add(normalize_name(m.display_name))
    for p in db.query(models.Player).all():
        base = normalize_name(p.full_name)
        alias_set = aliases.get(p.id, set()) | idmap_aliases.get(p.id, set())
        cache.append((p.id, base, alias_set))
    return cache


def _tokenize(name: str):
    n = normalize_name(name)
    return [t for t in n.replace('-', ' ').split() if t]


def _match_player_id(api_name_norm: str, cache: list[tuple[int, str, set]]):
    api_tokens = _tokenize(api_name_norm)
    api_first = api_tokens[0] if api_tokens else ""
    api_last = api_tokens[-1] if api_tokens else ""

    for pid, pname, alias_set in cache:
        if not pname:
            continue
        p_tokens = _tokenize(pname)
        p_first = p_tokens[0] if p_tokens else ""
        p_last = p_tokens[-1] if p_tokens else ""

        # Exact ou contains
        if api_name_norm == pname:
            return pid
        if api_name_norm in pname or pname in api_name_norm:
            if len(api_name_norm) > 3:
                return pid

        # Match sur first+last tokens
        if api_first and api_last and p_first and p_last:
            if api_first == p_first and api_last == p_last:
                return pid

        # Match sur intersection de tokens (>=2)
        if len(api_tokens) >= 2 and len(p_tokens) >= 2:
            inter = set(api_tokens) & set(p_tokens)
            if len(inter) >= 2:
                return pid

        # Alias / tokens alias
        if alias_set:
            for al in alias_set:
                if not al:
                    continue
                al_tokens = _tokenize(al)
                al_first = al_tokens[0] if al_tokens else ""
                al_last = al_tokens[-1] if al_tokens else ""
                if api_name_norm == al or api_name_norm in al or al in api_name_norm:
                    if len(api_name_norm) > 3:
                        return pid
                if api_first and api_last and al_first and al_last:
                    if api_first == al_first and api_last == al_last:
                        return pid
                if len(api_tokens) >= 2 and len(al_tokens) >= 2:
                    inter2 = set(api_tokens) & set(al_tokens)
                    if len(inter2) >= 2:
                        return pid
    return None


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
            # ✅ IMPORTANT: strip() pour enlever les espaces avant/après chaque clé
            self.api_keys = [k.strip() for k in keys_from_env.split(',') if k.strip()]
            self.current_key_index = 0
            self.api_key = self.api_keys[self.current_key_index] if self.api_keys else None
            if self.api_key:
                masked = self.api_key[:4] + "***"
                print(f"   ✅ {len(self.api_keys)} clé(s) API chargée(s)")
                print(f"   ✅ Clé active : {masked} (1/{len(self.api_keys)})")
            else:
                print("   ❌ Aucune clé API valide après parsing")
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

    def _select_bookmaker(self, bookmakers):
        """Sélectionne le bookmaker avec le plus de markets disponibles."""
        best_bookie = None
        max_markets = 0

        for bookie in bookmakers:
            markets = bookie.get("markets", [])
            if len(markets) > max_markets:
                max_markets = len(markets)
                best_bookie = bookie

        return best_bookie

    def get_event_id(self, home_team_code, away_team_code):
        """Récupère l'ID du match chez The-Odds-API en matching home/away (pas uniquement Bet365)."""
        if self.quota_exceeded or not self.api_key: return None

        regions_to_try = ["us", "us2", "ca", "uk", "eu"]
        home_name = TEAM_MAPPING.get(home_team_code)
        away_name = TEAM_MAPPING.get(away_team_code)

        if not home_name or not away_name:
            print(f"   ❌ Codes équipe invalides: {home_team_code} ou {away_team_code} non trouvés dans TEAM_MAPPING")
            return None

        def norm(s):
            return (s or "").lower().strip()

        for region in regions_to_try:
            # ✅ Si toutes les clés sont déjà épuisées, inutile de continuer
            if self.quota_exceeded:
                print(f"   🚨 Abandon: Toutes les clés API ont été épuisées")
                break

            try:
                params = {"apiKey": self.api_key, "regions": region, "markets": "h2h"}
                res = requests.get(f"{self.base_url}/events", params=params, timeout=5)

                # ✅ Boucle pour essayer TOUTES les clés disponibles (incluant la dernière)
                keys_tested = 0
                max_keys_to_test = len(self.api_keys)

                while res.status_code in [401, 429] and keys_tested < max_keys_to_test:
                    print(f"   🚨 ALERTE API ({region}) : Quota dépassé ou clé invalide (HTTP {res.status_code})")
                    print(f"   🔄 Tentative de changement de clé... (clé actuelle: {self.current_key_index + 1}/{len(self.api_keys)})")

                    if self.switch_to_next_key():
                        keys_tested += 1
                        params["apiKey"] = self.api_key
                        res = requests.get(f"{self.base_url}/events", params=params, timeout=5)

                        if res.status_code == 200:
                            print(f"   ✅ Nouvelle clé fonctionnelle! (clé {self.current_key_index + 1}/{len(self.api_keys)})")
                            break
                    else:
                        # Plus de clés disponibles
                        self.quota_exceeded = True
                        print(f"   🚨 Toutes les {len(self.api_keys)} clés API ont été testées et sont épuisées")
                        return None

                # Si après avoir essayé toutes les clés, on a encore une erreur pour cette région
                if res.status_code in [401, 429]:
                    print(f"   ❌ Toutes les clés épuisées pour région {region}, passage à la région suivante")
                    # ✅ NE PAS break ici, tenter la région suivante avec les clés restantes
                    continue

                if res.status_code != 200:
                    print(f"⚠️ Erreur HTTP API Odds ({region}) : {res.status_code}")
                    continue

                events = res.json() or []

                # ✅ Afficher la liste des matchs disponibles pour debug
                if not events:
                    print(f"   ⚠️ The-Odds-API ({region}): Aucun événement NBA disponible")
                    continue

                print(f"   🔍 The-Odds-API ({region}): {len(events)} événements NBA disponibles")

                # Afficher les 3 premiers matchs pour debug
                for idx, e in enumerate(events[:3]):
                    commence_time = e.get('commence_time', 'N/A')
                    if commence_time != 'N/A':
                        try:
                            dt = datetime.fromisoformat(commence_time.replace('Z', '+00:00'))
                            from zoneinfo import ZoneInfo
                            eastern = ZoneInfo("America/New_York")
                            dt_eastern = dt.astimezone(eastern)
                            commence_time = dt_eastern.strftime('%Y-%m-%d %H:%M ET')
                        except:
                            pass
                    print(f"      {idx+1}. {e.get('away_team')} @ {e.get('home_team')} ({commence_time})")

                # Recherche du match
                for e in events:
                    h = norm(e.get("home_team")); a = norm(e.get("away_team"))
                    if home_name and away_name:
                        if norm(home_name) in h and norm(away_name) in a:
                            print(f"   ✅ Match trouvé: {e['id']} - {e.get('away_team')} @ {e.get('home_team')}")
                            return e["id"]
                        if norm(home_name) in a and norm(away_name) in h:
                            print(f"   ✅ Match trouvé (inversé): {e['id']} - {e.get('home_team')} @ {e.get('away_team')}")
                            return e["id"]

                # Fallback partiel sur une seule équipe
                for e in events:
                    h = norm(e.get("home_team")); a = norm(e.get("away_team"))
                    if (home_name and norm(home_name) in h) or (away_name and norm(away_name) in a):
                        print(f"   ⚠️ Match partiel trouvé: {e['id']} (une seule équipe correspond)")
                        return e["id"]

            except Exception as e:
                print(f"❌ Exception API Events ({region}): {e}")
                continue

        print(f"⚠️ Match NON TROUVÉ sur The-Odds-API pour : {home_team_code} vs {away_team_code}")
        print(f"   💡 Noms recherchés: {home_name} (home) vs {away_name} (away)")
        print(f"   💡 Ce match n'existe peut-être pas encore sur The-Odds-API")
        print(f"   💡 Vérifiez manuellement : https://the-odds-api.com/sports-odds-data/basketball-nba-odds.html")
        return None

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
        if not event_id:
            print(f"   ⚠️ Abandon update_odds: event_id introuvable pour {home_code} vs {away_code}")
            return False

        print(f"   📡 Téléchargement des cotes pour {home_code} vs {away_code}...")

        try:
            params = {
                "apiKey": self.api_key,
                "regions": "us",  # ou 'eu'
                "markets": "player_points,player_rebounds,player_assists,player_threes",
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
                print("   ⚠️ Aucune cote bookmaker disponible pour ce match (bookmakers vide).")
                return False

            bookie = self._select_bookmaker(bookmakers)
            if not bookie:
                print("   ⚠️ Aucun bookmaker sélectionnable (markets manquants).")
                return False
            print(f"   ✅ Source des cotes : {bookie['title']}")

            # Suppression anciens records pour ce match (utilise OddsSnapshot)
            # db.query(models.OddsSnapshot).filter(models.OddsSnapshot.game_id == nba_game_id).delete()
            # On ne supprime qu'après avoir collecté de nouvelles lignes, pour éviter de vider en cas d'échec API
            new_odds = []
            snapshots_to_purge = db.query(models.OddsSnapshot).filter(models.OddsSnapshot.game_id == nba_game_id)
            players_cache = _player_name_cache(db)
            unmatched = []

            seen_keys = set()
            for market in bookie.get("markets", []):
                raw_key = market.get("key", "")
                seen_keys.add(raw_key)
                m_type = raw_key.replace("player_", "")

                # Ignorer les marchés three_points (non disponible dans nos données)
                if m_type in ("threes", "three_points_made", "three_point_made", "three_points"):
                    continue

                for outcome in market.get("outcomes", []):
                    api_name_norm = normalize_name(outcome.get("description"))
                    line = outcome.get("point")

                    matched_id = _match_player_id(api_name_norm, players_cache)
                    if not matched_id:
                        unmatched.append(api_name_norm)
                        continue

                    obj = models.OddsSnapshot(
                        game_id=nba_game_id,
                        player_id=matched_id,
                        market=m_type,
                        line=line,
                        price_over=outcome.get("price"),
                        price_under=1.85,
                        bookmaker=bookie.get("title"),
                        fetched_at=datetime.now(),
                        ttl_expire_at=datetime.now() + timedelta(hours=4)
                    )
                    new_odds.append(obj)

            if new_odds:
                snapshots_to_purge.delete()
                db.add_all(new_odds)
                db.commit()
                print(f"   📥 {len(new_odds)} lignes sauvegardées en BDD.")
                if unmatched:
                    print(f"   ⚠️ Non matchés (sample): {list(set(unmatched))[:5]}")
                return True
            else:
                print("   ⚠️ Cotes récupérées mais aucun joueur matché avec la BDD locale.")
                if unmatched:
                    print(f"   ⚠️ Noms non matchés (sample): {list(set(unmatched))[:10]}")
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
        # ✅ Si ttl_hours == 0, toujours forcer le refresh (pour les matchs du jour)
        if ttl_hours <= 0:
            return False

        cutoff = datetime.utcnow() - timedelta(hours=ttl_hours)
        return db.query(models.OddsSnapshot).filter(
            models.OddsSnapshot.game_id == game_id,
            models.OddsSnapshot.fetched_at >= cutoff
        ).first() is not None

    def fetch_odds_snapshots_for_game(self, db: Session, game_id: str, home_code: str, away_code: str,
                                      ingestion_run_id: int | None = None, ttl_hours: int = 4):
        """Récupère les cotes et les écrit dans odds_snapshots avec TTL et optional ingestion_run_id."""
        if self.quota_exceeded:
            print(f"   🚨 QUOTA API ÉPUISÉ - Impossible de récupérer les cotes pour {home_code} vs {away_code}")
            return False

        if not self.api_key:
            print(f"   🚨 AUCUNE CLÉ API DISPONIBLE - Impossible de récupérer les cotes pour {home_code} vs {away_code}")
            return False

        if self._has_fresh_snapshots(db, game_id, ttl_hours=ttl_hours):
            # print(f"   💾 Cache valide pour {home_code} vs {away_code}")
            return True  # cache valide

        # Initialisation des variables pour stocker les résultats
        rows = []
        unmatched = []
        ttl_expire_at = datetime.utcnow() + timedelta(hours=ttl_hours) if ttl_hours > 0 else None

        event_id = self.get_event_id(home_code, away_code)
        if not event_id:
            print(f"   ⚠️ MATCH NON TROUVÉ sur The-Odds-API pour {home_code} vs {away_code}")
            print(f"   💡 Vérifiez que le match existe sur The-Odds-API avec vos codes d'équipe")
            return False

        try:
            params = {
                "apiKey": self.api_key,
                "regions": "us",
                "markets": "player_points,player_rebounds,player_assists,player_threes",
                "oddsFormat": "decimal"
            }
            res = requests.get(f"{self.base_url}/events/{event_id}/odds", params=params, timeout=8)

            # ✅ Boucle pour essayer TOUTES les clés disponibles (incluant la dernière)
            keys_tested = 0
            max_keys_to_test = len(self.api_keys)

            while res.status_code in [401, 429] and keys_tested < max_keys_to_test:
                print(f"   🚨 The-Odds-API: QUOTA DÉPASSÉ ou CLÉ INVALIDE (HTTP {res.status_code})")
                print(f"   🔄 Tentative de changement de clé API... (clé actuelle: {self.current_key_index + 1}/{len(self.api_keys)}, clés testées: {keys_tested}/{max_keys_to_test})")

                if self.switch_to_next_key():
                    keys_tested += 1
                    params["apiKey"] = self.api_key
                    res = requests.get(f"{self.base_url}/events/{event_id}/odds", params=params, timeout=8)

                    if res.status_code == 200:
                        print(f"   ✅ Nouvelle clé fonctionnelle! (clé {self.current_key_index + 1}/{len(self.api_keys)})")
                        break
                else:
                    print(f"   ❌ Plus aucune clé API disponible - Abandon")
                    self.quota_exceeded = True
                    return False

            # Si après avoir essayé toutes les clés, on a encore une erreur
            if res.status_code in [401, 429]:
                print(f"   ❌ Toutes les clés ({len(self.api_keys)}) ont été essayées, toutes épuisées")
                self.quota_exceeded = True
                return False

            if res.status_code != 200:
                if res.status_code == 422:
                    print(f"   🚨 The-Odds-API: MARCHÉS INVALIDES (HTTP 422) pour {home_code} vs {away_code}")
                    print(f"   💡 L'API ne supporte pas certains marchés demandés (ex: player_threes)")
                else:
                    print(f"   ⚠️ The-Odds-API: Erreur HTTP {res.status_code} pour {home_code} vs {away_code}")
                return False

            data = res.json()
            bookmakers = data.get("bookmakers", [])
            if not bookmakers:
                print(f"   ⚠️ The-Odds-API: Aucun bookmaker disponible pour {home_code} vs {away_code}")
                print(f"   💡 Ce match n'a peut-être pas encore de cotes joueur disponibles")
                return False

            bookie = self._select_bookmaker(bookmakers)
            if not bookie:
                print(f"   ⚠️ Aucun bookmaker sélectionnable (markets joueur manquants) pour {home_code} vs {away_code}")
                return False

            print(f"   ✅ Récupération réussie des cotes via {bookie.get('title')}")

            players_cache = _player_name_cache(db)
            # 4. Parse markets
            bookie_name = bookie.get("title", "N/A")

            seen_keys = set()
            # Grouper les outcomes par (player_id, market, line) pour combiner Over/Under
            odds_map = {}  # key: (player_id, market, line) -> {over: price, under: price}

            for market in bookie.get("markets", []):
                raw_key = market.get("key", "")
                seen_keys.add(raw_key)
                m_type = raw_key.replace("player_", "")

                # Ignorer les marchés three_points (non disponible dans nos données)
                if m_type in ("threes", "three_points_made", "three_point_made", "three_points"):
                    continue

                for outcome in market.get("outcomes", []):
                    api_name_norm = normalize_name(outcome.get("description"))
                    line = outcome.get("point")

                    matched_id = _match_player_id(api_name_norm, players_cache)
                    if not matched_id:
                        unmatched.append(api_name_norm)
                        continue

                    key = (matched_id, m_type, line)
                    if key not in odds_map:
                        odds_map[key] = {"over": None, "under": None, "player_name": outcome.get("description")}

                    if outcome.get("name") == "Over":
                        odds_map[key]["over"] = outcome.get("price")
                    elif outcome.get("name") == "Under":
                        odds_map[key]["under"] = outcome.get("price")

            # Créer les lignes OddsSnapshot à partir du mapping
            for (player_id, market_type, line), prices in odds_map.items():
                rows.append(models.OddsSnapshot(
                    ingestion_run_id=ingestion_run_id,
                    game_id=game_id,
                    player_id=player_id,
                    market=market_type,
                    line=line,
                    price_over=prices["over"],
                    price_under=prices["under"],
                    bookmaker=bookie.get("title"),
                    fetched_at=datetime.utcnow(),
                    ttl_expire_at=ttl_expire_at
                ))

            if seen_keys:
                print(f"   🏷️ Markets récupérés: {sorted(seen_keys)}")

            if not rows:
                print(f"   ⚠️ AUCUNE LIGNE MATCHÉE - Aucun nom de joueur ne correspond entre The-Odds-API et votre BDD")
                if unmatched:
                    print(f"   ⚠️ Noms non matchés (sample): {list(set(unmatched))[:10]}")
                print(f"   💡 Vérifiez que les noms de joueurs dans votre BDD correspondent aux noms de The-Odds-API")
                return False

            db.add_all(rows)
            db.commit()
            print(f"   ✅ {len(rows)} lignes de cotes sauvegardées en BDD")
            if unmatched:
                print(f"   ⚠️ {len(set(unmatched))} joueurs non matchés (sample): {list(set(unmatched))[:5]}")
            return True
        except Exception as e:
            print(f"   ❌ Crash fetch_odds_snapshots_for_game: {e}")
            db.rollback()
            return False

    def get_snapshot_odds(self, db: Session, game_id: str, player_id: int, market: str):
        """Retourne la dernière cote snapshot (on ignore désormais le TTL pour ne pas tomber en no_line)."""
        row = db.query(models.OddsSnapshot).filter(
            models.OddsSnapshot.game_id == game_id,
            models.OddsSnapshot.player_id == player_id,
            models.OddsSnapshot.market == market,
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
