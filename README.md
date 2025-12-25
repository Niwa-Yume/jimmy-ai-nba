# Jimmy AI NBAce Projet

Bienvenue dans le projet Jimmy AI NBAce, une plateforme complète de prédiction et d'analyse de paris sportifs pour la NBA. Ce système utilise l'intelligence artificielle pour analyser les performances des joueurs, les cotes des bookmakers et les facteurs contextuels (blessures, défenses, etc.) afin de générer des recommandations de paris précises pour les matchs du jour.

## Choix d'Abstraction

Le projet repose sur plusieurs abstractions clés pour assurer la robustesse, la performance et la maintenabilité :

- **Architecture Modulaire** : Séparation en modules (`backend/`, `data-pipeline/`, `frontend/`) pour une séparation claire des responsabilités. Le backend (FastAPI) gère l'API et la logique métier, le data-pipeline synchronise les données externes, et le frontend (Streamlit) fournit l'interface utilisateur.
  
- **Gestion des APIs avec Fallbacks** : Pour chaque source de données, un système de fallback est implémenté (ex. : ESPN pour les blessures, NBA.com en secondaire). Cela garantit la disponibilité même en cas de panne d'une API.

- **Caching Intelligent** : Utilisation de `cachetools.TTLCache` pour éviter les appels répétés aux APIs (TTL de 10 minutes à 24 heures selon la source). Par exemple, les rosters ESPN sont cachés 10 minutes, les événements The-Odds-API 1 heure.

- **Gestion des Clés API Multiples** : Pour The-Odds-API, support de plusieurs clés avec rotation automatique en cas d'échec (rate limit ou erreur 401). Les clés défaillantes sont retirées après 2 échecs pour éviter les oscillations.

- **Normalisation des Données** : Fonctions de normalisation (ex. : `_normalize_team_code` pour les codes d'équipes, `_normalize_name` pour les noms de joueurs) pour gérer les variations (abrégés, accents).

- **Modèle de Données Abstrait** : Utilisation de SQLAlchemy pour une abstraction ORM, permettant de changer de SGBD facilement (PostgreSQL en prod, SQLite en dev).

- **IA avec Fallback Local** : L'agent IA utilise Gemini (Google GenAI) si disponible, sinon un algorithme rule-based local pour garantir le fonctionnement sans dépendance externe.

## Sources de Données

Les données proviennent de sources fiables et officielles :

- **NBA Stats API (nba_api)** : Bibliothèque Python officielle pour accéder aux statistiques NBA. Utilisée pour :
  - Récupération des rosters d'équipes (`CommonTeamRoster`).
  - Logs de matchs des joueurs (`PlayerGameLog`).
  - Calendrier des matchs (`ScoreBoard` pour les scores live, `LeagueGameFinder` pour l'historique).

- **ESPN API** : API non officielle mais fiable pour les données en temps réel.
  - Blessures des joueurs : `https://site.web.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}/roster` pour les statuts d'injury.
  - Mapping des équipes : `https://site.web.api.espn.com/apis/site/v2/sports/basketball/nba/teams` pour obtenir les IDs ESPN à partir des codes NBA.

- **The-Odds-API** : API payante pour les cotes de paris.
  - Événements : `https://api.the-odds-api.com/v4/sports/basketball_nba/events` pour lister les matchs du jour.
  - Cotes : `https://api.the-odds-api.com/v4/sports/basketball_nba/events/{event_id}/odds` pour les lignes de paris par joueur (points, rebonds, etc.).

Les données sont synchronisées quotidiennement via des scripts dans `data-pipeline/` (ex. : `sync_weekly_games.py`, `sync_injuries.py`).

## Traitement des Données

Le traitement est effectué en Python avec les bibliothèques suivantes :
- **Pandas** : Manipulation des datasets (nettoyage, agrégation, calculs statistiques comme les moyennes de points par joueur).
- **SQLAlchemy** : Persistance en base de données (PostgreSQL ou SQLite). Tables principales : `player`, `player_game_stats`, `games_schedule`, `player_injuries`.
- **Requests** : Appels HTTP aux APIs externes avec gestion des timeouts (5-8 secondes) et headers User-Agent pour éviter les blocages.

Étapes de traitement :
1. **Collecte** : Scripts de pipeline récupèrent les données brutes (ex. : blessures ESPN toutes les 2 heures).
2. **Nettoyage** : Suppression des valeurs nulles, normalisation des noms/équipes, calcul des probabilités de jeu basées sur le statut d'injury (ex. : 'OUT' = 0%, 'PROBABLE' = 75%).
3. **Enrichissement** : Ajout de contextes (matchup, localisation domicile/extérieur).
4. **Stockage** : Insertion en BDD avec gestion des doublons et timestamps (`last_fetched_at`).

Exemple de script de traitement (fichier `data-pipeline/sync_injuries.py`) :
```python
import requests
from datetime import datetime

def fetch_espn_injuries():
    url = "https://site.web.api.espn.com/apis/site/v2/sports/basketball/nba/teams"
    # Récupération des équipes, puis des rosters pour extraire les injuries
    # Nettoyage et mapping vers STATUS_PROBABILITY
    # Insertion en BDD via SQLAlchemy
```

## Algorithme et Calcul des Choix de Picks

L'algorithme combine statistiques historiques, facteurs contextuels et cotes de bookmakers pour calculer des projections et recommandations.

### Composants Clés :
- **Projections de Joueurs** : Basées sur les stats moyennes ajustées par :
  - **Défense** (`defense_ratings.py`) : Facteur défensif par équipe (ex. : ajustement pour les équipes rapides ou lentes via `get_pace_factor`).
  - **Offensive** (`offensive_impact.py`) : Boost offensif si des joueurs clés sont absents (`get_offensive_boost`).
  - **Probabilités** (`probability.py`) : Calcul de milestones (ex. : probabilité de dépasser une ligne via `cumulative_distribution_function`).

- **Analyse IA** (`ai_agent.py`) : 
  - Utilise Gemini 2.0-flash pour une analyse narrative (3-4 phrases en français).
  - Prompt inclut projection, ligne bookmaker, défense, localisation.
  - Fallback local : Règles simples (différence projection-ligne >1.5 pts = OVER, <-1.5 = UNDER).

- **Calcul des Picks** :
  1. Récupération des matchs du jour via NBA API.
  2. Pour chaque joueur clé (limité à 6 par équipe pour performance), calcul de projection ajustée.
  3. Récupération des cotes via The-Odds-API (préférence pour Bet365 si configuré).
  4. Comparaison projection vs ligne : Calcul de EV (Expected Value) = (probabilité * gain) - (1-probabilité * mise).
  5. Recommandation : OVER/UNDER si EV positif et confiance > seuil (ex. : 60%).

Exemple de calcul (fichier `backend/main.py`, endpoint `/scan`) :
```python
# Pour un joueur : projection = moyenne ajustée + boost offense - facteur défense
projection = get_offensive_boost(player) - get_defensive_factor(opponent)
# Comparaison avec ligne The-Odds-API
if projection - line > 1.5:
    pick = "OVER"
```

## Installation et Utilisation

1. **Prérequis** : Python 3.12+, PostgreSQL ou SQLite.
2. **Installation** :
   ```bash
   git clone <repo>
   cd jimmy-ai-nba
   python -m venv venv
   source venv/bin/activate  # ou venv\Scripts\activate sur Windows
   pip install -r backend/requirements.txt
   pip install -r frontend/requirements.txt
   ```
3. **Configuration** : Créer un `.env` avec :
   - `THE_ODDS_API_KEYS` : Clés API séparées par virgules.
   - `GEMINI_API_KEY` : Clé Google GenAI (optionnel).
   - Variables BDD (host, user, etc.).
4. **Synchronisation des Données** :
   ```bash
   python data-pipeline/sync_weekly_games.py
   python data-pipeline/sync_injuries.py
   ```
5. **Lancement** :
   - Backend : `uvicorn backend.main:app --reload`
   - Frontend : `streamlit run frontend/app.py`
6. **Utilisation** : Accéder à l'interface Streamlit pour scanner les matchs et voir les picks.

## Contribuer

- Respecter les bonnes pratiques : Tests unitaires, commits descriptifs.
- Pour les APIs : Gérer les rate limits (The-Odds-API : 500 req/jour gratuit).
- Sécurité : Ne commiter jamais les clés API (utiliser `.env`).

Ce projet est conçu pour être évolutif, avec une abstraction forte permettant d'ajouter de nouvelles APIs ou algorithmes facilement. Pour toute question, ouvrir une issue.
