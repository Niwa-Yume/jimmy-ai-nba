# 🚨 ÉTAT ACTUEL ET PLAN DE REPRISE

## Ce qui a été fait

### 1. Synchronisation complète du code
✅ Copié TOUT le projet (backend + data-pipeline) sur le VPS via rsync

### 2. Configuration docker-compose.yml
✅ Modifié `docker-compose.yml` pour monter les volumes :
```yaml
volumes:
  - ./backend:/app/backend
  - ./data-pipeline:/app/data-pipeline
```
Cela force le conteneur à utiliser les sources locales au lieu d'une image "figée".

### 3. Rebuild complet du backend
✅ Rebuild sans cache : `docker compose build --no-cache backend`
✅ Redémarrage de tous les services : `docker compose up -d`

### 4. État actuel
⚠️ **Le VPS ne répond plus aux commandes SSH** (probablement surcharge ou problème réseau temporaire)

---

## Quand le VPS redeviendra accessible

### Étape 1 : Vérifier l'état des conteneurs
```bash
ssh juju@192.168.1.134
cd /home/juju/jimmy-ai-nba
docker compose ps
```

**Résultat attendu :** Tous les conteneurs (jimmy_db, jimmy_backend, jimmy_frontend, jimmy_caddy) doivent être UP.

### Étape 2 : Vérifier les routes du backend
```bash
docker compose exec backend sh -c "python - <<'PY'
from backend.main import app
routes = [r.path for r in app.routes]
print(f'Routes chargées: {len(routes)}')
print('/analysis/start-scan' in routes)
print('/games/week' in routes)
PY"
```

**Résultat attendu :**
```
Routes chargées: 15-20
True
True
```

### Étape 3 : Tester les routes
```bash
curl http://localhost:8000/health
curl http://localhost:8000/games/week
curl -X POST http://localhost:8000/analysis/start-scan
```

**Résultat attendu :**
- `/health` → `{"status":"ok"}`
- `/games/week` → JSON avec les matchs de la semaine
- `/analysis/start-scan` → `{"job_id":"..."}`

### Étape 4 : Lancer un scan depuis le frontend
1. Ouvrir http://192.168.1.134:8501
2. Menu "Best Bets"
3. Cliquer "Lancer le scan"
4. Attendre 30-60 secondes

### Étape 5 : Récupérer les logs complets pour voir les compteurs debug
```bash
docker compose logs backend --tail=300 > logs_backend.txt
```

Chercher dans les logs :
- `🧮 DEBUG picks counters:` → Compteurs détaillés du filtrage
- `✅ Scan terminé :` → Résultat final (nombre de picks)

---

## Si les routes ne sont toujours pas chargées

### Option A : Forcer le montage des volumes
```bash
cd /home/juju/jimmy-ai-nba
docker compose down
docker compose up -d
```

### Option B : Vérifier que les fichiers sont bien montés dans le conteneur
```bash
docker compose exec backend ls -la /app/backend/
docker compose exec backend wc -l /app/backend/main.py
docker compose exec backend head -100 /app/backend/main.py
```

**Résultat attendu :**
- `main.py` doit faire 609 lignes
- Les premières lignes doivent contenir les imports (`from fastapi import FastAPI`, etc.)

### Option C : Vérifier les constantes dans advanced_scoring.py
```bash
docker compose exec backend grep "MIN_EDGE\|MIN_SCORE\|MIN_SAMPLE" /app/backend/advanced_scoring.py
```

**Résultat attendu :**
```
MIN_SCORE = 50
MIN_EDGE = 1.5
MIN_SAMPLE_SIZE = 8
```

---

## Si ça marche et que vous avez toujours 0 picks

### Lire les compteurs debug dans les logs
Dans `docker compose logs backend --tail=300`, cherchez la ligne :
```
🧮 DEBUG picks counters: {...} | checked=X | no_projection=Y | no_line=Z | low_edge=A | low_score=B | low_sample=C | out_status=D | included=E | potential=F
```

### Interprétation des compteurs
- **`checked`** : Nombre total de combinaisons joueur/stat analysées
- **`no_projection`** : Projections manquantes → Problème de données stats en BDD
- **`no_line`** : Pas de cotes disponibles → Problème OddsAPI/snapshots
- **`low_edge`** : Edge < 1.5% → Projections trop proches des lignes
- **`low_score`** : Score < 50 → Combinaison edge/forme/matchup/minutes insuffisante
- **`low_sample`** : Moins de 8 matchs en historique → Joueurs peu utilisés
- **`out_status`** : Joueurs marqués OUT → Normal, ils sont filtrés
- **`included`** : Picks qui passent tous les filtres
- **`potential`** : Total de picks avant la limite des 15 meilleurs

### Actions selon les compteurs

#### Si `no_projection` élevé (> 50% de `checked`)
**Problème :** Pas assez de stats en BDD pour les joueurs.

**Solution :**
```bash
cd /home/juju/jimmy-ai-nba
docker compose exec backend python -c "
from backend.database import get_db, engine
import pandas as pd
db = next(get_db())
count = db.execute('SELECT COUNT(*) FROM player_game_stats').scalar()
print(f'Stats en BDD: {count}')
"
```

Si < 1000 stats → Populer la BDD :
```bash
cd /home/juju/jimmy-ai-nba/data-pipeline
python populate_stats.py
```

#### Si `no_line` élevé (> 50% de `checked`)
**Problème :** Pas de cotes disponibles pour les matchs.

**Solution :** Vérifier les snapshots d'odds :
```bash
docker compose exec backend python -c "
from backend.database import get_db
from backend import models
db = next(get_db())
count = db.query(models.OddsSnapshot).count()
print(f'Snapshots odds en BDD: {count}')
"
```

Si 0 snapshots → Fetch manuel des odds :
```bash
cd /home/juju/jimmy-ai-nba/data-pipeline
python fetch_odds_snapshots.py
```

#### Si `low_edge` ou `low_score` élevé
**Problème :** Seuils trop stricts ou bookmakers trop précis.

**Solution temporaire :** Baisser les seuils dans `advanced_scoring.py` :
```python
MIN_SCORE = 40  # Au lieu de 50
MIN_EDGE = 1.0  # Au lieu de 1.5
MIN_SAMPLE_SIZE = 5  # Au lieu de 8
```

Puis rebuild et restart :
```bash
docker compose restart backend
```

#### Si `included` > 0 mais `potential` = 0
**Problème :** Bug dans la logique de tri/filtrage final.

**Solution :** Vérifier la fin de la fonction `run_best_bets_scan` dans `main.py` (lignes 580-610).

---

## Fichiers modifiés à conserver

### Sur le VPS (`/home/juju/jimmy-ai-nba`)
- ✅ `docker-compose.yml` (avec volumes montés)
- ✅ `backend/main.py` (avec compteurs debug)
- ✅ `backend/advanced_scoring.py` (MIN_EDGE=1.5, MIN_SCORE=50, MIN_SAMPLE_SIZE=8)
- ✅ `.env` (clés API)

### Sur votre machine locale
- ✅ Tous les fichiers synchronisés avec rsync

---

## En résumé

1. **Attendre que le VPS redevienne accessible** (connexion SSH bloquée temporairement)
2. **Vérifier que les conteneurs tournent** (`docker compose ps`)
3. **Vérifier que les routes sont chargées** (test curl sur `/health`, `/games/week`, `/analysis/start-scan`)
4. **Lancer un scan depuis le frontend** (http://192.168.1.134:8501)
5. **Récupérer les logs complets** pour voir les compteurs debug
6. **Ajuster les seuils** si nécessaire selon les compteurs

---

**Prochaine étape quand le VPS répond :** Exécuter les commandes de la section "Étape 1" ci-dessus.

