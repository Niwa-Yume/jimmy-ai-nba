"""
Service module for fetching and simulating NBA player betting odds.
"""
import os
import unicodedata
from datetime import datetime, timezone
from typing import Dict, Optional, Literal

import requests
from cachetools import TTLCache

# --- Constants ---
MARKET_TYPES = Literal["points", "rebounds", "assists", "three_points_made", "steals", "blocks"]
BASE_URL = "https://api.the-odds-api.com/v4/sports/basketball_nba"

# Mapping: Code NBA (Jimmy) -> Nom API (The-Odds-API)
NBA_TEAMS_MAP = {
    "ATL": "Atlanta Hawks", "BOS": "Boston Celtics", "BKN": "Brooklyn Nets",
    "CHA": "Charlotte Hornets", "CHI": "Chicago Bulls", "CLE": "Cleveland Cavaliers",
    "DAL": "Dallas Mavericks", "DEN": "Denver Nuggets", "DET": "Detroit Pistons",
    "GSW": "Golden State Warriors", "HOU": "Houston Rockets", "IND": "Indiana Pacers",
    "LAC": "Los Angeles Clippers", "LAL": "Los Angeles Lakers", "MEM": "Memphis Grizzlies",
    "MIA": "Miami Heat", "MIL": "Milwaukee Bucks", "MIN": "Minnesota Timberwolves",
    "NOP": "New Orleans Pelicans", "NYK": "New York Knicks", "OKC": "Oklahoma City Thunder",
    "ORL": "Orlando Magic", "PHI": "Philadelphia 76ers", "PHX": "Phoenix Suns",
    "POR": "Portland Trail Blazers", "SAC": "Sacramento Kings", "SAS": "San Antonio Spurs",
    "TOR": "Toronto Raptors", "UTA": "Utah Jazz", "WAS": "Washington Wizards"
}

class BettingOddsProvider:
    """
    Provides real-time or simulated betting odds for NBA players.
    """

    def __init__(self, api_key: Optional[str] = None):
        # Support multi-keys
        self._api_keys: list[str] = []
        keys_env = os.getenv("THE_ODDS_API_KEYS")
        if keys_env:
            self._api_keys = [k.strip() for k in keys_env.split(",") if k.strip()]
        else:
            if os.getenv("THE_ODDS_API_KEY"):
                self._api_keys.append(os.getenv("THE_ODDS_API_KEY"))
            if os.getenv("THE_ODDS_API_KEY2"):
                self._api_keys.append(os.getenv("THE_ODDS_API_KEY2"))
        
        if api_key and api_key not in self._api_keys:
            self._api_keys.insert(0, api_key)

        self._current_key_index = 0
        self.api_key = self._api_keys[self._current_key_index] if self._api_keys else None

        # Caches
        self._events_cache = TTLCache(maxsize=1, ttl=3600)
        self._odds_cache = TTLCache(maxsize=50, ttl=1800)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Jimmy.AI/1.0"})

        self._api_enabled = bool(self.api_key)
        self._api_warned = False
        # Track failures per key index to avoid flip-flop rotation
        self._key_failures: dict[int, int] = {}
        # Preferred bookmakers list (comma-separated in env), lowercased
        pref = os.getenv('PREFERRED_BOOKMAKERS', '')
        if pref:
            self._preferred_bookmakers = [p.strip().lower() for p in pref.split(',') if p.strip()]
        else:
            # default empty -> meaning accept any bookmaker
            self._preferred_bookmakers = []

    def _get_current_key(self) -> Optional[str]:
        if not self._api_keys: return None
        return self._api_keys[self._current_key_index]

    def _rotate_key(self) -> bool:
        if len(self._api_keys) <= 1:
            self._api_enabled = False
            return False
        prev = self._current_key_index
        self._current_key_index = (self._current_key_index + 1) % len(self._api_keys)
        self.api_key = self._get_current_key()
        self._api_enabled = True
        self._api_warned = False
        # Note: ne pas vider les caches lors d'une simple rotation pour éviter
        # des re-fetch massifs d'événements/odds (cela provoquait une boucle
        # d'appels et une oscillation des clés si l'API était intermittente).
        # Les caches sont vidés uniquement quand une clé est retirée (_mark_current_key_failed).
        print(f"   ℹ️ Rotation clé API : {prev} -> {self._current_key_index}")
        return True

    def _mark_current_key_failed(self) -> bool:
        """Handle a failure for the current key. Increment failure counter; if it crosses threshold, remove the key.
        Returns True if rotation/swap to another key happened, False if no usable key remains.
        """
        if not self._api_keys:
            self._api_enabled = False
            return False
        idx = self._current_key_index
        self._key_failures[idx] = self._key_failures.get(idx, 0) + 1
        # If key fails repeatedly, remove it to avoid flip-flop rotation
        if self._key_failures[idx] >= 2:
            try:
                bad = self._api_keys.pop(idx)
                print(f"   ⚠️ Clé API retirée après échecs : index={idx}")
                # normalize current index
                if not self._api_keys:
                    self._api_enabled = False
                    self.api_key = None
                    return False
                self._current_key_index = self._current_key_index % len(self._api_keys)
                self.api_key = self._get_current_key()
                try:
                    self._events_cache.clear()
                    self._odds_cache.clear()
                except: pass
                return True
            except Exception:
                self._api_enabled = False
                return False
        # Otherwise try rotate to next key
        return self._rotate_key()

    def _normalize_name(self, name: str) -> str:
        nfkd_form = unicodedata.normalize('NFKD', name)
        return "".join([c for c in nfkd_form if not unicodedata.combining(c)]).lower()

    def _check_rate_limit(self, resp: requests.Response) -> bool:
        try:
            remaining = resp.headers.get('x-requests-remaining') or resp.headers.get('X-Requests-Remaining')
            if remaining is not None:
                if int(str(remaining).strip()) <= 0:
                    # mark current key failed (will rotate or disable)
                    self._mark_current_key_failed()
                    return True
        except: pass
        return False

    def get_api_status(self) -> Dict:
        """Return a small status dict about API keys and current enabled state."""
        return {
            'has_keys': len(self._api_keys) > 0,
            'keys_count': len(self._api_keys),
            'current_key_index': self._current_key_index if self._api_keys else None,
            'api_enabled': self._api_enabled,
        }

    def get_event_id_for_team(self, team_code: str) -> Optional[str]:
        full_team_name = NBA_TEAMS_MAP.get(team_code)
        if not full_team_name or not self._api_enabled: return None

        # Check cache
        events = self._events_cache.get("all_events")
        if not events:
            print("   📡 Récupération des événements The-Odds-API...")
            try:
                params = {"apiKey": self.api_key, "regions": "eu,us"}
                resp = self.session.get(f"{BASE_URL}/events", params=params, timeout=5) # Timeout court
                
                if resp.status_code == 401:
                    # mark current key failed and try another if available
                    if self._mark_current_key_failed():
                        params["apiKey"] = self.api_key
                        resp = self.session.get(f"{BASE_URL}/events", params=params, timeout=5)
                    else:
                        return None

                if resp.ok:
                    events = resp.json()
                    self._events_cache["all_events"] = events
                else:
                    print(f"   ⚠️ Erreur API Events: {resp.status_code}")
                    return None
            except Exception as e:
                print(f"   ❌ Exception API Events: {e}")
                return None
        
        target = full_team_name.lower()
        for event in events:
            home = event.get("home_team", "").lower()
            away = event.get("away_team", "").lower()
            if target in home or target in away:
                return event.get("id")
        return None

    def has_bet365_for_event(self, event_id: str, market: str = 'player_points') -> bool:
        # New behaviour: check for preferred bookmakers if configured; otherwise accept any bookmaker presence
        if not event_id or not self._api_enabled: return False
        
        cache_key = f"check_{event_id}_{market}"
        if cache_key in self._odds_cache: return self._odds_cache[cache_key]

        try:
            params = {"apiKey": self.api_key, "regions": "eu,us", "markets": market, "oddsFormat": "decimal"}
            resp = self.session.get(f"{BASE_URL}/events/{event_id}/odds", params=params, timeout=5)
            
            if resp.status_code == 401:
                if self._mark_current_key_failed():
                    params["apiKey"] = self.api_key
                    resp = self.session.get(f"{BASE_URL}/events/{event_id}/odds", params=params, timeout=5)
                else:
                    return False

            if resp.ok:
                data = resp.json()
                bookmakers = [ (b.get('title') or '').lower() for b in data.get('bookmakers', []) ]
                if not bookmakers:
                    self._odds_cache[cache_key] = False
                    return False

                # If user specified preferred bookmakers, check if any of them exist for the event
                if self._preferred_bookmakers:
                    has_pref = any(any(pref in bm for bm in bookmakers) for pref in self._preferred_bookmakers)
                    self._odds_cache[cache_key] = bool(has_pref)
                    return bool(has_pref)

                # Otherwise accept any bookmaker available (free plan may expose many alternatives)
                self._odds_cache[cache_key] = True
                return True
        except Exception:
            pass
        
        return False

    def get_odds(self, player_name: str, team_code: str, market_type: MARKET_TYPES, recent_avg: float) -> Optional[Dict]:
        # Backward-compatible signature kept; allow passing game_id via team_code if needed.
        # For compatibility we keep the original behavior: resolve event id from team_code.
        if not self._api_enabled: return None
        try:
            game_id = self.get_event_id_for_team(team_code)
            if not game_id: return None
            return self._fetch_event_odds(game_id, player_name, market_type)
        except:
            return None

    def get_odds_for_game(self, player_name: str, game_id: str, market_type: MARKET_TYPES) -> Optional[Dict]:
        """Direct lookup when caller already knows the game_id (avoids event lookups)."""
        if not self._api_enabled or not game_id: return None
        try:
            return self._fetch_event_odds(game_id, player_name, market_type)
        except:
            return None

    def prefetch_event_odds(self, game_id: str) -> bool:
        """Fetch all odds for a game in a single API call and cache them under <game_id>_all.
        Returns True when cached successfully, False otherwise."""
        if not self._api_enabled or not game_id: return False
        cache_key_all = f"{game_id}_all"
        # If already cached and recent, nothing to do
        if cache_key_all in self._odds_cache:
            return True
        try:
            params = {"apiKey": self.api_key, "regions": "eu,us", "oddsFormat": "decimal"}
            resp = self.session.get(f"{BASE_URL}/events/{game_id}/odds", params=params, timeout=6)
            if resp.status_code == 401:
                if self._mark_current_key_failed():
                    params["apiKey"] = self.api_key
                    resp = self.session.get(f"{BASE_URL}/events/{game_id}/odds", params=params, timeout=6)
                else:
                    return False
            # check rate limit header and possibly rotate
            try:
                self._check_rate_limit(resp)
            except: pass
            if resp.ok:
                data = resp.json()
                self._odds_cache[cache_key_all] = data
                return True
            return False
        except Exception:
            return False

    def _fetch_event_odds(self, game_id: str, player_name: str, market_type: MARKET_TYPES) -> Optional[Dict]:
        # Try to reuse a full-event cache (faster and reduces API calls)
        cache_key_all = f"{game_id}_all"
        cache_key_market = f"{game_id}_{market_type}"

        # If a per-market cache exists, use it
        cached_data = self._odds_cache.get(cache_key_market)
        if cached_data:
            return self._parse_api_response(cached_data, player_name, market_type)

        # If full cache exists, use the relevant portion
        full = self._odds_cache.get(cache_key_all)
        if not full:
            # Attempt to fetch full event odds once
            try:
                params = {"apiKey": self.api_key, "regions": "eu,us", "oddsFormat": "decimal"}
                resp = self.session.get(f"{BASE_URL}/events/{game_id}/odds", params=params, timeout=6)
                if resp.status_code == 401:
                    if self._mark_current_key_failed():
                        params["apiKey"] = self.api_key
                        resp = self.session.get(f"{BASE_URL}/events/{game_id}/odds", params=params, timeout=6)
                    else:
                        return None
                try:
                    self._check_rate_limit(resp)
                except: pass
                if resp.ok:
                    full = resp.json()
                    # Cache full event payload
                    self._odds_cache[cache_key_all] = full
                else:
                    return None
            except Exception:
                return None

        # Store a per-market cached slice to speed up next requests
        try:
            # We don't transform full; store full as is and parse directly
            return self._parse_api_response(full, player_name, market_type)
        except Exception:
            return None

    def _parse_api_response(self, api_data: dict, player_name: str, market_type: MARKET_TYPES) -> Optional[Dict]:
        if not api_data: return None
        normalized_target = self._normalize_name(player_name)
        
        bookmakers = api_data.get("bookmakers", [])
        # Build candidate bookmakers list ordered by user preference (if provided).
        candidate_bookmakers = []
        if self._preferred_bookmakers:
            lower_map = { (b.get('title') or '').lower(): b for b in bookmakers }
            # Add preferred in order if present
            for pref in self._preferred_bookmakers:
                for title_lower, bobj in lower_map.items():
                    if pref in title_lower and bobj not in candidate_bookmakers:
                        candidate_bookmakers.append(bobj)
            # Append remaining bookmakers not in candidate_bookmakers
            for b in bookmakers:
                if b not in candidate_bookmakers:
                    candidate_bookmakers.append(b)
        else:
            # Default: prefer bet365 if present, else accept all bookmakers
            bet365_entries = [b for b in bookmakers if 'bet365' in (b.get('title') or '').lower()]
            candidate_bookmakers = bet365_entries if bet365_entries else bookmakers

        # Iterate through candidate bookmakers (Bet365 first if available)
        for bookmaker in candidate_bookmakers:
            title = bookmaker.get('title') or 'Unknown'
            for market in bookmaker.get("markets", []):
                if market.get("key") != f"player_{market_type}":
                    continue

                # Find outcomes matching the player
                player_outcomes = [o for o in market.get('outcomes', []) if self._normalize_name(o.get('description', '')) == normalized_target]
                if not player_outcomes:
                    continue

                # Prefer the most common 'point' among outcomes for that player
                # Group by point
                points = {}
                for o in player_outcomes:
                    pt = o.get('point')
                    points.setdefault(pt, []).append(o)

                # Choose the point with most entries
                best_point = None
                best_len = 0
                for pt, outs in points.items():
                    if pt is None: continue
                    if len(outs) > best_len:
                        best_len = len(outs)
                        best_point = pt

                if best_point is None:
                    # fallback to first outcome point
                    best_point = player_outcomes[0].get('point')

                over_odds = None
                under_odds = None
                for o in market.get('outcomes', []):
                    if o.get('point') == best_point and self._normalize_name(o.get('description', '')) == normalized_target:
                        name = (o.get('name') or '').lower()
                        if 'over' in name: over_odds = o.get('price')
                        elif 'under' in name: under_odds = o.get('price')

                if over_odds or under_odds:
                    return {
                        "source": f"The-Odds-API ({title})",
                        "market_type": market_type,
                        "line": best_point,
                        "over_odds": over_odds,
                        "under_odds": under_odds,
                        "bookmaker": title,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }

        return None
