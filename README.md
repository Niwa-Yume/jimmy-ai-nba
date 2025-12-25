# 🏀 Jimmy.AI - NBA Betting Predictor

> *"L'intelligence artificielle au service de tes paris sportifs, avec la logique analytique de Jimmy Highroller."*

**Jimmy.AI** est un agent autonome de prédiction NBA qui croise la data science avancée (statistiques, défense, blessures) avec les cotes des bookmakers en temps réel pour dénicher les meilleurs **Value Bets** et **Parlays**.

---

## 🚀 Fonctionnalités Clés

### 🧠 1. Moteur de Projection "Jimmy Brain"
L'algorithme ne se contente pas de faire une moyenne. Il calcule une projection précise pour chaque joueur (Points, Rebonds, Passes) en prenant en compte :
* **Historique pondéré :** Saison en cours, 10 derniers matchs, et historique face à l'adversaire (H2H).
* **Contexte Défensif (DvP) :** Analyse fine de la défense adverse *par position* (ex: "Les Lakers défendent mal contre les meneurs").
* **Impact des Blessures (Usage Rate) :** Boost automatique des stats d'un joueur si une star de son équipe est absente (ex: Tyrese Maxey prend +20% de tirs sans Embiid).
* **Rythme (Pace) :** Ajustement selon la vitesse de jeu des deux équipes.

### 💰 2. Gestion Intelligente des Cotes (Smart Betting)
* **Intégration API Réelle :** Récupération des lignes et cotes via *The-Odds-API* (Bet365, FanDuel, etc.).
* **Système de Caching Avancé :** Sauvegarde automatique des cotes en base de données locale pour économiser les quotas API (1 appel par match max).
* **Détection de Value :** Comparaison mathématique entre la projection de Jimmy et la ligne du bookmaker pour identifier les "Edges".

### 📊 3. Interface & UX
* **Dashboard Streamlit :** Visualisation claire des matchs, des joueurs et des recommandations.
* **Analyse Narrative :** "L'avis de Jimmy" généré par IA pour expliquer le pari avec des mots simples.
* **Indicateurs de Risque :** Calcul de la régularité (écart-type) pour signaler les joueurs instables.

---

## 🛠️ Architecture Technique

Le projet est construit de manière modulaire :

* **Backend :** FastAPI (Python) - Gestion de l'API, logique métier et calculs.
* **Database :** SQLAlchemy (SQLite/PostgreSQL) - Stockage des joueurs, stats, calendrier et cotes.
* **Frontend :** Streamlit - Interface utilisateur interactive.
* **Data Pipeline :** Scripts d'ingestion (NBA API, ESPN, The-Odds-API).

---

## 📦 Installation

### Prérequis
* Python 3.10+
* Une clé API gratuite sur [The-Odds-API](https://the-odds-api.com/)

### 1. Cloner le projet
```bash
git clone https://github.com/ton-repo/jimmy-ai.git
cd jimmy-ai
```

### 2. Environnement Virtuel
```bash
python -m venv venv
source venv/bin/activate  # Sur Mac/Linux
# ou
venv\Scripts\activate     # Sur Windows
```

### 3. Installation des dépendances
```bash
pip install -r backend/requirements.txt
pip install -r frontend/requirements.txt
```

### 4. Configuration (.env)
Créez un fichier `.env` dans le dossier racine et ajoutez vos clés :

```env

```

---

## ⚡ Lancement Rapide

Il faut lancer deux terminaux séparés.

### Terminal 1 : Le Backend (Cerveau)
```bash
# Depuis la racine
uvicorn backend.main:app --reload
```
L'API sera accessible sur http://127.0.0.1:8000

### Terminal 2 : Le Frontend (Visage)
```bash
# Depuis la racine
streamlit run frontend/app.py
```
L'interface s'ouvrira dans votre navigateur.

---

## 🔄 Mise à jour des Données

Si la base de données est vide au premier lancement, utilisez les scripts de population :

```bash
# Remplir la liste des joueurs
python data-pipeline/populate_players.py

# Récupérer les matchs de la semaine
python data-pipeline/sync_weekly_games.py
```

---

## 📝 Roadmap & Améliorations

- [x] MVP : Projections de points et comparaison Cotes.
- [x] Système anti-ban NBA API (Throttling & Headers).
- [x] Caching BDD pour The-Odds-API.
- [ ] Ajout des marchés Rebonds & Passes.
- [ ] Algorithme de génération de Parlays (Combinés) pour viser une cote de 100.
- [ ] Backtesting automatisé des prédictions passées.

---

## 🔍 Détails Techniques : Origine des Données et Traitement

### Sources de Données
- **Statistiques Joueurs :** API NBA officielle (via nba_api Python) pour les stats saisonnières, matchs récents et historiques H2H.
- **Calendrier Matchs :** ESPN API pour les programmes hebdomadaires et les blessures en temps réel.
- **Cotes Bookmakers :** The-Odds-API pour les lignes de paris (points, rebonds, assists) de Bet365, FanDuel, DraftKings.
- **Blessures :** ESPN et NBA.com pour les statuts (Out, Questionable, Probable) et ajustements automatiques.

### Traitement des Données
1. **Ingestion :** Scripts Python (`data-pipeline/`) récupèrent les données brutes via requests, avec gestion d'erreurs et throttling pour éviter les bans.
2. **Nettoyage :** Normalisation des noms (suppression accents, minuscules) pour matcher les joueurs entre APIs.
3. **Calculs :** 
   - Projections : Moyenne pondérée (saison 40%, 10 derniers 40%, H2H 20%) ajustée par DvP et blessures.
   - DvP : Stats défensives par position (ex: PPG allowed to PG).
   - Usage Rate : Redistribution des possessions si star absente.
4. **Stockage :** SQLAlchemy ORM avec modèles (Player, Game, Stats, BettingOdds) pour requêtes efficaces.

### Algorithme de Sélection des Picks
1. **Projection Individuelle :** Pour chaque joueur éligible, calcule projection Points/Rebounds/Assists.
2. **Comparaison Cotes :** Récupère ligne bookmaker (ex: Over 25.5 points à 1.85).
3. **Value Detection :** Si projection > ligne + marge (ex: 26.2 > 25.5), c'est un "Edge".
4. **Filtrage Risque :** Écart-type < seuil pour éviter les joueurs volatiles.
5. **Génération Picks :** Liste des Value Bets avec explication IA (Gemini API pour narratif).

### APIs Utilisées et Utilisation
- **NBA API (nba_api) :** Récupération stats joueurs/matchs. Utilisation : `from nba_api.stats.endpoints import PlayerGameLog` pour historiques.
- **ESPN API :** Calendrier et blessures. Utilisation : Requests GET sur endpoints ESPN avec parsing JSON.
- **The-Odds-API :** Cotes temps réel. Utilisation : Clés multiples pour rotation quota, endpoints `/events` et `/events/{id}/odds`, régions US, marchés player_points/assists/rebonds.
- **Gemini API (optionnel) :** Génération explications. Utilisation : Prompt "Explique ce pari NBA simplement".

### Choix d'Abstraction
- **Modulaire :** Séparation backend/frontend pour scalabilité.
- **Caching :** Évite appels répétés, économise quota.
- **Rotation Clés :** Gestion automatique quota dépassé (401/429) en switchant clés.
- **Fuzzy Matching :** Pour noms joueurs entre APIs (normalisation + fallback partiel).
- **FastAPI :** Async pour performances, Pydantic pour validation.

---

## 🤝 Contribution
PRs bienvenues ! Respectez le style PEP8 et ajoutez des tests.

## 📄 Licence
MIT - Libre utilisation, créditez Jimmy Highroller.
