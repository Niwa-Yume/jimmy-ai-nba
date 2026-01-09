# 📖 Guide de Déploiement - Jimmy AI NBA

## 🧪 Test en Local

### Étape 1: Rendre les scripts exécutables
```bash
chmod +x test_deployment.sh deploy_to_vps.sh
```

### Étape 2: Tester en local
```bash
# Assure-toi que Docker tourne en local
docker-compose up -d

# Lance le test complet
./test_deployment.sh local
```

**Ce que le script teste:**
- ✅ Les 4 conteneurs Docker tournent
- ✅ Le backend répond sur http://localhost:8000
- ✅ Les données sont présentes en base
- ✅ Les 3 marchés (points, rebounds, assists) sont actifs
- ✅ Aucun marché `three_points_made` présent
- ✅ Un scan de test fonctionne et retourne des picks
- ✅ Pas d'erreurs critiques dans les logs

### Étape 3: Vérifier manuellement
```bash
# Voir les logs backend
docker logs -f jimmy_backend

# Tester l'API manuellement
curl http://localhost:8000/games/week

# Accéder au frontend
open http://localhost:8501
```

---

## 🚀 Déploiement sur le VPS

### Méthode automatique (recommandée)

```bash
# 1. Déployer automatiquement
./deploy_to_vps.sh

# 2. Tester le déploiement
./test_deployment.sh vps

# 3. Accéder au frontend
open http://192.168.1.134
```

### Méthode manuelle

Si tu préfères faire étape par étape:

#### 1. Transférer les fichiers
```bash
# Backend
scp backend/advanced_scoring.py juju@192.168.1.134:/home/juju/jimmy-ai-nba/backend/
scp backend/betting_service.py juju@192.168.1.134:/home/juju/jimmy-ai-nba/backend/
scp backend/main.py juju@192.168.1.134:/home/juju/jimmy-ai-nba/backend/

# Data pipeline
scp data-pipeline/fetch_odds_snapshots.py juju@192.168.1.134:/home/juju/jimmy-ai-nba/data-pipeline/

# Scripts de vérification
scp check_data_health.py juju@192.168.1.134:/home/juju/jimmy-ai-nba/
```

#### 2. Copier le .env
```bash
# Si tu as des changements dans le .env
scp .env juju@192.168.1.134:/home/juju/jimmy-ai-nba/
```

#### 3. Se connecter au VPS
```bash
ssh juju@192.168.1.134
cd /home/juju/jimmy-ai-nba
```

#### 4. Rebuild et redémarrer
```bash
# Arrêter les conteneurs
docker-compose down

# Rebuild le backend
docker-compose build backend

# Redémarrer
docker-compose up -d

# Attendre que tout démarre
sleep 10

# Vérifier les logs
docker logs -f jimmy_backend
```

#### 5. Tester
```bash
# Test API
curl http://192.168.1.134:8000/games/week

# Vérifier la santé des données
docker exec jimmy_backend python check_data_health.py

# Lancer un scan de test
curl -X POST http://192.168.1.134:8000/analysis/start-scan -H "Content-Type: application/json" -d '{}'
```

---

## 🐛 Résolution de problèmes

### Le test échoue avec "0 picks potentiels"

**Cause:** Les lignes de paris ne sont pas récupérées depuis The Odds API

**Solution:**
```bash
# Sur le VPS
ssh juju@192.168.1.134
cd /home/juju/jimmy-ai-nba

# Récupérer manuellement les lignes
docker exec jimmy_backend python data-pipeline/fetch_odds_snapshots.py

# Vérifier qu'on a bien des lignes
docker exec jimmy_backend python check_data_health.py
```

### Le backend ne démarre pas

**Vérifier les logs:**
```bash
docker logs jimmy_backend --tail 100
```

**Erreurs communes:**
- `NameError: name 'ScanRequest' is not defined` → Redémarre le backend
- `Database connection failed` → Vérifie que PostgreSQL tourne

**Solution:**
```bash
docker-compose down
docker-compose up -d
```

### Les conteneurs ne tournent pas

```bash
# Voir l'état de tous les conteneurs
docker ps -a

# Redémarrer ceux qui sont arrêtés
docker-compose up -d

# Vérifier les logs de chaque service
docker logs jimmy_backend
docker logs jimmy_frontend
docker logs jimmy_db
docker logs jimmy_caddy
```

### Problème de quota API (The Odds API)

**Symptôme:** Aucune ligne de paris récupérée

**Vérifier:**
```bash
# Regarde les logs pour voir si tu as un message d'erreur de quota
docker logs jimmy_backend | grep -i "quota\|rate limit"
```

**Solution:**
- Attends le renouvellement du quota (généralement quotidien)
- Ou utilise les lignes en cache si elles sont encore valides

---

## 📊 Commandes utiles

### Surveillance
```bash
# Logs en temps réel
docker logs -f jimmy_backend

# Voir les picks générés
docker exec jimmy_backend python -c "from backend.database import get_db; db=next(get_db()); print(db.execute('SELECT COUNT(*) FROM picks').scalar())"

# Voir les snapshots de cotes
docker exec jimmy_backend python check_data_health.py | grep Snapshots
```

### Maintenance
```bash
# Nettoyer les vieux logs
docker-compose logs --tail 0

# Redémarrer un seul service
docker-compose restart backend

# Rebuild complet
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Backup base de données
```bash
# Sur le VPS
docker exec jimmy_db pg_dump -U jimmy_user jimmy_nba > backup_$(date +%Y%m%d).sql
```

---

## ✅ Checklist finale

Avant de considérer le déploiement comme réussi:

- [ ] Le script `./test_deployment.sh vps` passe tous les tests
- [ ] Le frontend est accessible sur http://192.168.1.134
- [ ] Un scan manuel génère des picks (> 0 picks potentiels)
- [ ] Les 3 marchés (points, rebounds, assists) sont présents
- [ ] Aucun marché `three_points_made` n'apparaît
- [ ] Les logs backend ne montrent pas d'erreurs critiques
- [ ] Le cache des cotes est actif (vérifie avec check_data_health.py)

---

## 📞 Support

Si un test échoue:
1. Consulte les logs: `docker logs jimmy_backend`
2. Vérifie la santé des données: `docker exec jimmy_backend python check_data_health.py`
3. Lance un scan manuel et observe les logs en temps réel

