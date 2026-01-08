# 🚀 Guide de Déploiement Production (VPS)

## 📋 Prérequis

- VPS Linux avec Docker installé
- Accès SSH configuré
- DuckDNS configuré (jimmyainba.duckdns.org)
- Ports 80/443 ouverts sur la box internet

---

## 🔧 Première Installation

### 1️⃣ Se connecter au VPS

```bash
ssh juju@192.168.1.134
```

### 2️⃣ Cloner le projet (si pas déjà fait)

```bash
cd ~
git clone https://github.com/Niwa-Yume/jimmy-ai-nba.git
cd jimmy-ai-nba
```

### 3️⃣ Créer le fichier `.env` (IMPORTANT)

```bash
nano .env
```

**Contenu à copier-coller :**

```bash
# API Keys
GEMINI_API_KEY=AIzaSyAttBZi1VZ7b4feeVe0ZU0WOctAeQ-O-0M
THE_ODDS_API_KEY=aa1a80d3f7844a86d5d7a95e98eeaad5

# Base de données (IMPORTANT : host=db pour Docker)
DB_NAME=jimmy_nba_db
DB_USER=jimmy_user
DB_PASSWORD=secure_password_123
DB_HOST=db
DB_PORT=5432

# PostgreSQL Container
POSTGRES_USER=jimmy_user
POSTGRES_PASSWORD=secure_password_123
POSTGRES_DB=jimmy_nba_db
```

**Sauvegarder :** `Ctrl+O`, `Entrée`, `Ctrl+X`

### 4️⃣ Lancer le déploiement

```bash
./deploy_prod.sh
```

✅ **C'est tout !** Le script va :
- Pull le code depuis GitHub
- Builder les images Docker
- Lancer tous les services
- Initialiser la base de données
- Afficher les vérifications

---

## 🔄 Mise à Jour (après changements sur GitHub)

### Option 1 : Script automatique (recommandé)

```bash
cd ~/jimmy-ai-nba
./deploy_prod.sh
```

### Option 2 : Commandes manuelles

```bash
cd ~/jimmy-ai-nba
git pull origin main
docker compose down
docker compose build
docker compose up -d
```

---

## 🧪 Vérifications

### Backend (API)

```bash
curl http://localhost:8000/health
# Doit retourner : {"status":"ok"}
```

### Frontend (Streamlit)

```bash
curl -I http://localhost:8501
# Doit retourner : HTTP/1.1 200 OK
```

### Caddy (Proxy HTTPS)

```bash
curl -I http://localhost
# Doit retourner : HTTP/1.1 308 (redirect vers HTTPS)
```

### Depuis l'extérieur

```bash
curl http://jimmyainba.duckdns.org/health
```

---

## 📊 Commandes Utiles

### Voir les logs

```bash
# Tous les services
docker compose logs -f

# Backend seulement
docker compose logs -f backend

# Frontend
docker compose logs -f frontend

# Caddy (proxy)
docker compose logs -f caddy
```

### État des services

```bash
docker compose ps
```

### Redémarrer un service

```bash
docker compose restart backend
docker compose restart frontend
docker compose restart caddy
```

### Arrêter tout

```bash
docker compose down
```

### Relancer tout

```bash
docker compose up -d
```

---

## 🗄️ Gestion de la Base de Données

### Se connecter à PostgreSQL

```bash
docker compose exec db psql -U jimmy_user -d jimmy_nba_db
```

### Exécuter un script SQL

```bash
docker compose exec -T db psql -U jimmy_user -d jimmy_nba_db < script.sql
```

### Backup de la DB

```bash
docker compose exec db pg_dump -U jimmy_user jimmy_nba_db > backup_$(date +%Y%m%d).sql
```

### Restaurer un backup

```bash
cat backup_20260108.sql | docker compose exec -T db psql -U jimmy_user -d jimmy_nba_db
```

### Réinitialiser les données (sans tout casser)

```bash
docker compose exec backend python /app/data-pipeline/init_db_prod.py
```

---

## 🌐 Configuration Box Internet (Swisscom)

Pour que ton VPS soit accessible depuis l'extérieur :

1. **Ouvrir les ports 80 et 443** :
   - Se connecter sur `http://192.168.1.1` (interface Swisscom)
   - Aller dans "Réseau Local" → "Redirection de port"
   - Ajouter :
     - **Port 80** → VPS (192.168.1.134) → Port 80
     - **Port 443** → VPS (192.168.1.134) → Port 443

2. **Vérifier l'IP publique** :
   ```bash
   curl ifconfig.me
   ```

3. **Mettre à jour DuckDNS** (si besoin) :
   - Aller sur https://www.duckdns.org/domains
   - Vérifier que `jimmyainba.duckdns.org` pointe vers ton IP publique

---

## 🔥 Dépannage

### Le backend ne démarre pas

**Symptôme :**
```
curl: (7) Failed to connect to localhost port 8000
```

**Solution :**
```bash
# Voir les logs
docker compose logs backend --tail=50

# Si erreur de connexion DB, vérifier le .env
cat .env | grep DB_HOST
# Doit retourner : DB_HOST=db (pas localhost!)

# Redémarrer
docker compose restart backend
```

### Le frontend ne charge pas

```bash
docker compose logs frontend --tail=50
docker compose restart frontend
```

### HTTPS ne marche pas

**Symptôme :**
```
curl: (35) OpenSSL error
```

**Cause :** Let's Encrypt ne peut pas atteindre ton VPS (ports fermés)

**Solution :**
1. Vérifier que les ports 80/443 sont ouverts sur ta box
2. Tester depuis l'extérieur (pas depuis le VPS) :
   ```bash
   # Depuis ton Mac
   curl http://jimmyainba.duckdns.org
   ```
3. Attendre 5-10 minutes que Let's Encrypt réessaie

### Les matchs ne s'affichent pas

```bash
# Réinitialiser les données
docker compose exec backend python /app/data-pipeline/init_db_prod.py
```

---

## 📝 Checklist Déploiement

- [ ] `.env` créé avec `DB_HOST=db`
- [ ] Ports 80/443 ouverts sur la box
- [ ] DuckDNS pointe vers l'IP publique
- [ ] `./deploy_prod.sh` exécuté sans erreur
- [ ] `curl http://localhost:8000/health` → `{"status":"ok"}`
- [ ] `curl http://jimmyainba.duckdns.org` → répond

---

## 🎯 URLs Finales

- **Frontend :** http://jimmyainba.duckdns.org
- **Backend API :** http://jimmyainba.duckdns.org/health
- **HTTPS :** https://jimmyainba.duckdns.org (une fois certif OK)

---

## 💬 Support

Si ça ne marche toujours pas, envoie-moi :

```bash
# État des services
docker compose ps

# Logs backend
docker compose logs backend --tail=100

# Logs caddy
docker compose logs caddy --tail=100

# Test DB
docker compose exec backend python -c "import psycopg2, os; print(psycopg2.connect(dbname=os.getenv('DB_NAME'), user=os.getenv('DB_USER'), password=os.getenv('DB_PASSWORD'), host=os.getenv('DB_HOST')).closed)"
```

